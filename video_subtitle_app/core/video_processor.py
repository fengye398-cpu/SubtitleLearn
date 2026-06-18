import os
import re
import pysrt
import subprocess
import time
from datetime import timedelta
from pathlib import Path
from typing import Callable, Optional, List

# 延迟导入MoviePy，避免启动时FFmpeg检查失败
# MoviePy将在需要时动态导入

from database.manager import db_manager
from database.models import Project, SubtitleSegment, ImportResult
from utils.file_utils import FileUtils
from config.settings import app_config

# MoviePy相关变量，延迟初始化
VideoFileClip = None
AudioFileClip = None
_moviepy_initialized = False

def _ensure_moviepy():
    """确保MoviePy已正确初始化"""
    global VideoFileClip, AudioFileClip, _moviepy_initialized

    if _moviepy_initialized:
        return True

    try:
        # 强制配置MoviePy使用系统FFmpeg
        import os
        os.environ['FFMPEG_BINARY'] = 'ffmpeg'  # 设置环境变量

        import moviepy.config as mp_config
        mp_config.FFMPEG_BINARY = "ffmpeg"

        from moviepy.editor import VideoFileClip as VFC, AudioFileClip as AFC
        VideoFileClip = VFC
        AudioFileClip = AFC
        _moviepy_initialized = True
        return True

    except Exception as e:
        print(f"MoviePy初始化失败: {e}")
        return False

class VideoProcessor:
    """视频处理核心类"""
    
    def __init__(self):
        self.cancel_flag = False
        self.progress_callback = None
        self.log_callback = None
    
    def set_callbacks(self, progress_callback: Callable = None, log_callback: Callable = None):
        """设置回调函数"""
        self.progress_callback = progress_callback
        self.log_callback = log_callback
    
    def cancel_operation(self):
        """取消当前操作"""
        self.cancel_flag = True
    
    def log(self, message: str):
        """记录日志"""
        if self.log_callback:
            self.log_callback(message)
        print(message)
    
    def update_progress(self, current: int, total: int, message: str = ""):
        """更新进度"""
        if self.progress_callback:
            self.progress_callback(current, total, message)

    @staticmethod
    def parse_subtitle_text(text: str) -> tuple:
        """解析字幕文本，分离原文和译文

        Args:
            text: 字幕文本

        Returns:
            (原文, 译文) 元组，如果只有一行则译文为None
        """
        lines = text.strip().split('\n')
        if len(lines) >= 2:
            return lines[0].strip(), lines[1].strip()
        else:
            return lines[0].strip() if lines else "", None

    def import_video_subtitle(self, video_path: str, subtitle_path: str = None,
                            preset: str = "veryfast", crf: str = "24") -> ImportResult:
        """导入视频和字幕，返回导入结果

        Returns:
            ImportResult: 导入结果统计
        """
        start_time = time.time()
        result = ImportResult()

        try:
            self.cancel_flag = False

            # 验证文件
            if not os.path.exists(video_path):
                self.log(f"错误：视频文件不存在 - {video_path}")
                result.error_message = f"视频文件不存在：{video_path}"
                return result

            # 自动查找字幕文件
            if not subtitle_path:
                subtitle_path = FileUtils.find_matching_subtitle(video_path)

            if not subtitle_path or not os.path.exists(subtitle_path):
                self.log(f"错误：字幕文件不存在 - {subtitle_path}")
                result.error_message = f"字幕文件不存在：{subtitle_path}"
                return result

            # 检查是否已存在相同的项目
            video_name = Path(video_path).stem
            result.project_name = video_name

            # 使用新的查找方法
            existing_project = db_manager.find_project_by_paths(video_path, subtitle_path)

            if existing_project:
                self.log(f"发现已存在的项目：{existing_project.name}")

                # 检查缓存文件是否完整
                if self._verify_cache_integrity(existing_project):
                    self.log("缓存文件完整，跳过导入")
                    result.success = True
                    result.skipped = True
                    result.project_id = existing_project.id
                    result.duration = time.time() - start_time
                    return result
                else:
                    self.log("缓存文件不完整，重新处理...")
                    # 删除不完整的缓存
                    self._cleanup_project_cache(existing_project)

            # 创建或更新项目
            cache_dir = str(app_config.cache_dir / video_name)
            FileUtils.ensure_dir(cache_dir)

            if existing_project:
                # 更新现有项目
                existing_project.video_path = video_path
                existing_project.subtitle_path = subtitle_path
                existing_project.cache_dir = cache_dir
                project_id = existing_project.id
                self.log(f"更新项目：{video_name} (ID: {project_id})")
            else:
                # 创建新项目
                project = Project(
                    name=video_name,
                    video_path=video_path,
                    subtitle_path=subtitle_path,
                    cache_dir=cache_dir
                )
                project_id = db_manager.create_project(project)
                self.log(f"创建项目：{video_name} (ID: {project_id})")

            result.project_id = project_id

            # 解析字幕（支持BOM和非BOM的UTF-8）
            self.log("解析字幕文件...")
            subs = self._parse_subtitle_file(subtitle_path)
            if not subs:
                result.error_message = "字幕文件解析失败"
                return result

            self.log(f"找到 {len(subs)} 个字幕片段")
            result.total_segments = len(subs)

            # 开始切割
            stats = self._cut_video_segments(
                project_id, video_path, subs, cache_dir, preset, crf
            )

            # 更新结果统计
            result.success = stats['success']
            result.video_success = stats['video_success']
            result.video_failed = stats['video_failed']
            result.audio_success = stats['audio_success']
            result.audio_failed = stats['audio_failed']
            result.subtitle_success = stats['subtitle_success']
            result.subtitle_failed = stats['subtitle_failed']
            result.duration = time.time() - start_time

            if result.success and not self.cancel_flag:
                self.log(f"项目导入完成：{video_name}")
            else:
                # 清理失败的项目
                db_manager.delete_project(project_id)
                FileUtils.safe_remove(cache_dir)
                result.error_message = "导入过程中出现错误或被取消"

            return result

        except Exception as e:
            self.log(f"导入失败：{e}")
            result.error_message = str(e)
            result.duration = time.time() - start_time
            return result

    def _check_existing_project(self, video_path: str, subtitle_path: str) -> Optional[Project]:
        """检查是否存在相同的项目"""
        try:
            # 根据视频文件名查找项目
            video_name = Path(video_path).stem
            projects = db_manager.get_projects()

            for project in projects:
                if project.name == video_name:
                    # 检查文件路径和修改时间
                    if (project.video_path == video_path and
                        project.subtitle_path == subtitle_path):
                        return project

                    # 检查文件是否被修改
                    if os.path.exists(project.video_path) and os.path.exists(project.subtitle_path):
                        video_mtime = os.path.getmtime(video_path)
                        subtitle_mtime = os.path.getmtime(subtitle_path)

                        # 如果文件没有被修改，认为是同一个项目
                        if (abs(video_mtime - os.path.getmtime(project.video_path)) < 1 and
                            abs(subtitle_mtime - os.path.getmtime(project.subtitle_path)) < 1):
                            return project

            return None
        except Exception as e:
            self.log(f"检查现有项目失败：{e}")
            return None

    def _verify_cache_integrity(self, project: Project) -> bool:
        """验证缓存文件完整性"""
        try:
            # 检查缓存目录是否存在
            cache_dir = Path(project.cache_dir)
            if not cache_dir.exists():
                return False

            # 获取数据库中的片段数量
            segments = db_manager.get_segments_by_project(project.id)
            if not segments:
                return False

            # 检查每个片段的文件是否存在
            missing_files = 0
            for segment in segments:
                video_file = cache_dir / f"{segment.index_num:03d}_{FileUtils.clean_filename(segment.text[:20])}.mp4"
                audio_file = cache_dir / f"{segment.index_num:03d}_{FileUtils.clean_filename(segment.text[:20])}.mp3"
                subtitle_file = cache_dir / f"{segment.index_num:03d}_{FileUtils.clean_filename(segment.text[:20])}.srt"

                if not video_file.exists() or not audio_file.exists() or not subtitle_file.exists():
                    missing_files += 1

            # 如果缺失文件超过10%，认为缓存不完整
            integrity_ratio = (len(segments) - missing_files) / len(segments)
            return integrity_ratio >= 0.9

        except Exception as e:
            self.log(f"验证缓存完整性失败：{e}")
            return False

    def _cleanup_project_cache(self, project: Project):
        """清理项目缓存"""
        try:
            cache_dir = Path(project.cache_dir)
            if cache_dir.exists():
                import shutil
                shutil.rmtree(cache_dir)
                self.log(f"已清理缓存目录：{cache_dir}")

            # 删除数据库中的片段记录
            db_manager.delete_segments_by_project(project.id)
            self.log("已清理数据库中的片段记录")

        except Exception as e:
            self.log(f"清理缓存失败：{e}")

    def _parse_subtitle_file(self, subtitle_path: str):
        """解析字幕文件，支持BOM和非BOM的UTF-8"""
        try:
            # 首先尝试使用utf-8-sig（自动处理BOM）
            try:
                subs = pysrt.open(subtitle_path, encoding="utf-8-sig")
                if subs:
                    self.log("使用UTF-8-sig编码解析字幕成功")
                    return subs
            except Exception:
                pass

            # 尝试使用utf-8
            try:
                subs = pysrt.open(subtitle_path, encoding="utf-8")
                if subs:
                    self.log("使用UTF-8编码解析字幕成功")
                    return subs
            except Exception:
                pass

            # 尝试使用gbk（中文字幕常用编码）
            try:
                subs = pysrt.open(subtitle_path, encoding="gbk")
                if subs:
                    self.log("使用GBK编码解析字幕成功")
                    return subs
            except Exception:
                pass

            # 尝试自动检测编码
            try:
                import chardet
                with open(subtitle_path, 'rb') as f:
                    raw_data = f.read()
                    encoding = chardet.detect(raw_data)['encoding']
                    if encoding:
                        subs = pysrt.open(subtitle_path, encoding=encoding)
                        if subs:
                            self.log(f"使用自动检测编码 {encoding} 解析字幕成功")
                            return subs
            except Exception:
                pass

            self.log("所有编码尝试失败，字幕解析失败")
            return None

        except Exception as e:
            self.log(f"字幕解析失败：{e}")
            return None
    
    def _cut_video_segments(self, project_id: int, video_path: str, subs: List,
                          cache_dir: str, preset: str, crf: str) -> dict:
        """切割视频片段 - 完全按照参考代码实现

        Returns:
            统计信息字典: {
                'success': bool,
                'total_segments': int,
                'video_success': int,
                'video_failed': int,
                'audio_success': int,
                'audio_failed': int,
                'subtitle_success': int,
                'subtitle_failed': int
            }
        """
        media = None
        # 统计信息
        stats = {
            'success': False,
            'total_segments': len(subs),
            'video_success': 0,
            'video_failed': 0,
            'audio_success': 0,
            'audio_failed': 0,
            'subtitle_success': 0,
            'subtitle_failed': 0
        }

        try:
            # 判断文件类型
            ext = Path(video_path).suffix.lower()
            is_audio = ext in FileUtils.get_audio_extensions()

            # 确保MoviePy可用
            if not _ensure_moviepy():
                self.log("错误：MoviePy不可用，无法处理媒体文件")
                return

            # 打开媒体文件
            if is_audio:
                media = AudioFileClip(video_path)
                self.log("处理音频文件")
            else:
                media = VideoFileClip(video_path)
                self.log("处理视频文件")

            total_segments = len(subs)

            for i, sub in enumerate(subs, 1):
                if self.cancel_flag:
                    self.log("操作已取消")
                    break

                self.update_progress(i, total_segments, f"切割片段 {i}/{total_segments}")

                # 生成文件名
                segment_name = f"{i:03d}_{FileUtils.clean_filename(sub.text[:20])}"

                # 时间转换（完全按照参考代码）
                start_time = sub.start.ordinal / 1000.0
                end_time = sub.end.ordinal / 1000.0

                clip = None
                try:
                    # 切割片段
                    clip = media.subclip(start_time, end_time)

                    # 生成文件路径
                    if is_audio:
                        video_file = None
                        audio_file = os.path.join(cache_dir, f"{segment_name}.mp3")
                        # 保存音频
                        clip.write_audiofile(audio_file, logger=None)
                    else:
                        video_file = os.path.join(cache_dir, f"{segment_name}.mp4")
                        audio_file = os.path.join(cache_dir, f"{segment_name}.mp3")

                        # [TOOL] 改用 FFmpeg 直接切割视频，避免 MoviePy 音频错误
                        # 这样更快、更稳定、不会出现音频处理错误
                        has_audio = False
                        try:
                            import subprocess

                            # 使用 FFmpeg 直接切割视频（保留音频）
                            ffmpeg_cut_cmd = [
                                "ffmpeg", "-y",
                                "-ss", str(start_time),  # 开始时间
                                "-i", video_path,        # 输入文件
                                "-t", str(end_time - start_time),  # 持续时间
                                "-c:v", "libx264",       # 视频编码器
                                "-preset", preset,       # 编码速度
                                "-crf", crf,             # 质量
                                "-c:a", "aac",           # 音频编码器
                                "-b:a", "192k",          # 音频比特率
                                video_file
                            ]

                            result = subprocess.run(
                                ffmpeg_cut_cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                creationflags=subprocess.CREATE_NO_WINDOW,
                                timeout=120
                            )

                            if result.returncode != 0:
                                # FFmpeg 切割失败，回退到 MoviePy
                                self.log(f"警告：片段 {i} FFmpeg 切割失败，使用 MoviePy")
                                raise Exception("FFmpeg failed, fallback to MoviePy")

                        except FileNotFoundError:
                            # FFmpeg不可用，直接使用MoviePy
                            self.log(f"警告：FFmpeg不可用，片段 {i} 使用 MoviePy")
                            raise Exception("FFmpeg not found, fallback to MoviePy")

                            # 检查视频文件是否成功生成
                            if not os.path.exists(video_file) or os.path.getsize(video_file) == 0:
                                raise Exception("Video file not created")

                            # 检查视频是否有音频流
                            probe_cmd = [
                                "ffprobe", "-v", "error",
                                "-select_streams", "a:0",
                                "-show_entries", "stream=codec_name",
                                "-of", "default=nw=1:nk=1",
                                video_file
                            ]
                            probe_result = subprocess.run(
                                probe_cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                creationflags=subprocess.CREATE_NO_WINDOW,
                                timeout=5
                            )
                            has_audio = probe_result.returncode == 0 and probe_result.stdout.strip()

                        except Exception as fallback_error:
                            # 回退到 MoviePy 方法
                            self.log(f"使用 MoviePy 处理片段 {i}")
                            try:
                                clip.write_videofile(
                                    video_file,
                                    codec="libx264",
                                    audio_codec="aac",
                                    bitrate="3000k",
                                    preset=preset,
                                    ffmpeg_params=["-crf", crf],
                                    logger=None
                                )
                                has_audio = clip.audio is not None
                            except AttributeError as e:
                                # MoviePy 音频处理错误，尝试不带音频导出
                                if "'NoneType' object has no attribute 'stdout'" in str(e):
                                    has_audio = False
                                    self.log(f"警告：片段 {i} 检测到 MoviePy 音频错误，尝试无音频导出")
                                    clip_no_audio = clip.without_audio()
                                    clip_no_audio.write_videofile(
                                        video_file,
                                        codec="libx264",
                                        audio_codec="aac",
                                        bitrate="3000k",
                                        preset=preset,
                                        ffmpeg_params=["-crf", crf],
                                        logger=None
                                    )
                                else:
                                    raise

                        # 使用 FFmpeg 直接提取音频（仅在有音频时）
                        if has_audio:
                            audio_extracted = False
                            try:
                                import subprocess
                                ffmpeg_cmd = [
                                    "ffmpeg", "-y",
                                    "-i", video_file,
                                    "-vn",  # 不处理视频
                                    "-acodec", "libmp3lame",
                                    "-ab", "192k",
                                    audio_file
                                ]
                                result = subprocess.run(
                                    ffmpeg_cmd,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    creationflags=subprocess.CREATE_NO_WINDOW,
                                    timeout=60
                                )

                                # 检查 FFmpeg 返回码和音频文件是否成功生成
                                if result.returncode == 0 and os.path.exists(audio_file) and os.path.getsize(audio_file) > 0:
                                    audio_extracted = True
                                    stats['audio_success'] += 1
                                else:
                                    # 记录详细错误信息
                                    if result.returncode != 0:
                                        stderr_output = result.stderr.decode('utf-8', errors='ignore')
                                        self.log(f"警告：片段 {i} 音频提取失败（FFmpeg返回码: {result.returncode}）")
                                        # 只在调试时显示详细错误
                                        # self.log(f"FFmpeg错误: {stderr_output}")
                                    else:
                                        self.log(f"警告：片段 {i} 音频提取失败（文件为空或不存在）")
                                    stats['audio_failed'] += 1
                            except subprocess.TimeoutExpired:
                                self.log(f"警告：片段 {i} 音频提取超时")
                                stats['audio_failed'] += 1
                            except Exception as e:
                                self.log(f"警告：片段 {i} 音频提取失败：{e}")
                                stats['audio_failed'] += 1

                            # 如果音频提取失败，将 audio_file 设为 None
                            if not audio_extracted:
                                audio_file = None
                        else:
                            # 视频本身没有音频
                            audio_file = None

                    # 生成字幕文件（字幕归零，使用深拷贝避免修改原对象）
                    subtitle_file = os.path.join(cache_dir, f"{segment_name}.srt")
                    import copy
                    sub_rel = copy.deepcopy(sub)
                    sub_rel.start.ordinal -= int(start_time * 1000)
                    sub_rel.end.ordinal -= int(start_time * 1000)
                    pysrt.SubRipFile([sub_rel]).save(subtitle_file)
                    stats['subtitle_success'] += 1

                    # 解析双语字幕
                    text_primary, text_secondary = self.parse_subtitle_text(sub.text)

                    # 保存到数据库
                    segment = SubtitleSegment(
                        project_id=project_id,
                        index_num=i,
                        start_time=start_time,
                        end_time=end_time,
                        text=sub.text,
                        text_primary=text_primary,
                        text_secondary=text_secondary,
                        video_file=video_file,
                        audio_file=audio_file,
                        subtitle_file=subtitle_file
                    )

                    db_manager.create_segment(segment)

                    # 更新视频统计
                    if video_file and os.path.exists(video_file):
                        stats['video_success'] += 1
                    elif video_file:
                        stats['video_failed'] += 1

                except Exception as clip_error:
                    self.log(f"处理片段 {i} 失败：{clip_error}")
                    import traceback
                    self.log(f"详细错误：{traceback.format_exc()}")
                    continue
                finally:
                    if clip:
                        try:
                            clip.close()
                        except:
                            pass

            # 输出音频提取统计信息
            if not is_audio and (stats['audio_success'] > 0 or stats['audio_failed'] > 0):
                self.log(f"音频提取统计：成功 {stats['audio_success']} 个，失败 {stats['audio_failed']} 个")
                if stats['audio_failed'] > 0:
                    self.log(f"提示：{stats['audio_failed']} 个片段没有音频，预览时将只有画面")

            stats['success'] = not self.cancel_flag
            return stats

        except Exception as e:
            self.log(f"切割失败：{e}")
            import traceback
            self.log(f"详细错误：{traceback.format_exc()}")
            stats['success'] = False
            return stats
        finally:
            if media:
                try:
                    media.close()
                except:
                    pass
    

    
    def regenerate_segment_files(self, segment: SubtitleSegment, new_start_time: float,
                                new_end_time: float, preset: str = "veryfast",
                                crf: str = "24") -> dict:
        """重新生成单个片段的视频、音频、字幕文件（用于完整模式保存）

        Args:
            segment: 片段对象
            new_start_time: 新的开始时间（秒）
            new_end_time: 新的结束时间（秒）
            preset: 编码速度预设
            crf: 视频质量参数

        Returns:
            结果字典: {
                'success': bool,
                'video_file': str,
                'audio_file': str,
                'subtitle_file': str,
                'error': str
            }
        """
        result = {
            'success': False,
            'video_file': None,
            'audio_file': None,
            'subtitle_file': None,
            'error': None
        }

        try:
            # 导入必要的模块
            from pathlib import Path
            from config.settings import app_config

            # 获取项目信息
            project = db_manager.get_project(segment.project_id)
            if not project:
                result['error'] = "项目不存在"
                return result

            video_path = project.video_path
            cache_dir = project.cache_dir

            print(f"[文件重新生成] 项目ID: {project.id}")
            print(f"[文件重新生成] 视频路径: {video_path}")
            print(f"[文件重新生成] 原缓存目录: {cache_dir}")
            print(f"[文件重新生成] 当前工作目录: {os.getcwd()}")

            # 如果缓存目录为空，创建一个新的
            if not cache_dir or not cache_dir.strip():
                video_name = Path(video_path).stem
                cache_dir = str(app_config.cache_dir / video_name)
                print(f"[文件重新生成] 缓存目录为空，创建新的: {cache_dir}")

                # 更新数据库中的缓存目录
                project.cache_dir = cache_dir
                db_manager.update_project(project)
                print(f"[文件重新生成] 已更新数据库中的缓存目录")

            if not os.path.exists(video_path):
                result['error'] = f"源视频文件不存在：{video_path}"
                return result

            # 确保缓存目录存在
            FileUtils.ensure_dir(cache_dir)
            print(f"[文件重新生成] 缓存目录已确保存在: {cache_dir}")

            # 生成新文件名（使用更安全的方式）
            # 对于包含特殊字符的文本，使用简化的命名方式
            try:
                text_for_name = segment.text_primary[:10] if segment.text_primary else segment.text[:10]
                clean_text = FileUtils.clean_filename(text_for_name)

                # 进一步清理：只保留字母、数字、空格和常见标点
                import re
                clean_text = re.sub(r'[^\w\s\-_.]', '', clean_text, flags=re.UNICODE)
                clean_text = clean_text.strip()

                # 如果清理后的文本为空或太短，使用默认名称
                if not clean_text or len(clean_text) < 2:
                    clean_text = f"segment_{segment.id}"

                segment_name = f"{segment.index_num:03d}_{clean_text}"

                # 最终安全检查：如果文件名仍然有问题，使用纯数字名称
                if len(segment_name) > 50 or any(ord(c) > 127 for c in segment_name):
                    segment_name = f"{segment.index_num:03d}_seg_{segment.id}"

            except Exception as e:
                print(f"[文件重新生成] 文件名生成失败，使用默认名称: {e}")
                segment_name = f"{segment.index_num:03d}_seg_{segment.id}"

            print(f"[文件重新生成] 生成的文件名前缀: {segment_name}")

            # 判断是否为音频文件
            ext = Path(video_path).suffix.lower()
            is_audio = ext in FileUtils.get_audio_extensions()

            # 确保MoviePy可用
            if not _ensure_moviepy():
                result['error'] = "MoviePy不可用"
                return result

            # 打开媒体文件
            media = None
            clip = None
            try:
                if is_audio:
                    media = AudioFileClip(video_path)
                    self.log("处理音频文件")
                else:
                    media = VideoFileClip(video_path)
                    self.log(f"处理视频文件：{video_path}")

                # 切割片段
                clip = media.subclip(new_start_time, new_end_time)

                # 生成文件路径
                if is_audio:
                    audio_file = os.path.join(cache_dir, f"{segment_name}.mp3")
                    print(f"[文件重新生成] 目标音频文件: {audio_file}")

                    # 保存当前工作目录
                    original_cwd = os.getcwd()
                    try:
                        # 切换到缓存目录
                        os.chdir(cache_dir)
                        print(f"[文件重新生成] 切换到缓存目录进行音频处理: {cache_dir}")

                        # 保存音频
                        clip.write_audiofile(audio_file, logger=None)
                        result['audio_file'] = audio_file
                        print(f"[文件重新生成] 音频文件生成成功: {audio_file}")

                    finally:
                        # 恢复原工作目录
                        os.chdir(original_cwd)
                        print(f"[文件重新生成] 恢复工作目录: {original_cwd}")

                        # 检查是否有文件意外生成在原工作目录
                        work_dir_audio = os.path.join(original_cwd, f"{segment_name}.mp3")
                        if os.path.exists(work_dir_audio) and work_dir_audio != audio_file:
                            print(f"[文件重新生成] 发现音频文件在原工作目录: {work_dir_audio}")
                            # 移动到正确位置
                            import shutil
                            if os.path.exists(audio_file):
                                FileUtils.safe_remove(audio_file)
                            shutil.move(work_dir_audio, audio_file)
                            result['audio_file'] = audio_file
                            print(f"[文件重新生成] 已移动音频文件到正确位置: {audio_file}")
                else:
                    video_file = os.path.join(cache_dir, f"{segment_name}.mp4")
                    audio_file = os.path.join(cache_dir, f"{segment_name}.mp3")

                    print(f"[文件重新生成] 目标视频文件: {video_file}")
                    print(f"[文件重新生成] 目标音频文件: {audio_file}")

                    # 删除旧文件
                    FileUtils.safe_remove(video_file)
                    if os.path.exists(audio_file):
                        FileUtils.safe_remove(audio_file)

                    # 使用 FFmpeg 直接切割视频
                    has_audio = False
                    try:
                        ffmpeg_cut_cmd = [
                            "ffmpeg", "-y",
                            "-ss", str(new_start_time),
                            "-i", video_path,
                            "-t", str(new_end_time - new_start_time),
                            "-c:v", "libx264",
                            "-preset", preset,
                            "-crf", crf,
                            "-c:a", "aac",
                            "-b:a", "192k",
                            video_file
                        ]

                        print(f"[文件重新生成] 执行FFmpeg命令: {' '.join(ffmpeg_cut_cmd)}")

                        result_ffmpeg = subprocess.run(
                            ffmpeg_cut_cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            creationflags=subprocess.CREATE_NO_WINDOW,
                            timeout=120,
                            cwd=cache_dir  # 设置工作目录为缓存目录
                        )

                        print(f"[文件重新生成] FFmpeg返回码: {result_ffmpeg.returncode}")
                        if result_ffmpeg.stderr:
                            print(f"[文件重新生成] FFmpeg错误输出: {result_ffmpeg.stderr.decode('utf-8', errors='ignore')[:200]}")

                        # 检查文件是否在正确位置生成
                        if os.path.exists(video_file):
                            print(f"[文件重新生成] 视频文件生成成功: {video_file}")
                        else:
                            print(f"[文件重新生成] 警告：视频文件未在预期位置生成: {video_file}")
                            # 检查是否在工作目录生成了文件
                            work_dir_file = os.path.join(os.getcwd(), f"{segment_name}.mp4")
                            if os.path.exists(work_dir_file):
                                print(f"[文件重新生成] 发现文件在工作目录: {work_dir_file}")
                                # 移动文件到正确位置
                                import shutil
                                shutil.move(work_dir_file, video_file)
                                print(f"[文件重新生成] 已移动文件到正确位置: {video_file}")

                        if result_ffmpeg.returncode != 0:
                            raise Exception("FFmpeg failed")

                        # 检查视频是否有音频流
                        probe_cmd = [
                            "ffprobe", "-v", "error",
                            "-select_streams", "a:0",
                            "-show_entries", "stream=codec_name",
                            "-of", "default=nw=1:nk=1",
                            video_file
                        ]
                        probe_result = subprocess.run(
                            probe_cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            creationflags=subprocess.CREATE_NO_WINDOW,
                            timeout=5
                        )
                        has_audio = probe_result.returncode == 0 and probe_result.stdout.strip()

                    except Exception as e:
                        # 回退到 MoviePy
                        print(f"[文件重新生成] FFmpeg 失败，使用 MoviePy: {e}")
                        self.log("FFmpeg 失败，使用 MoviePy")

                        # 保存当前工作目录
                        original_cwd = os.getcwd()
                        try:
                            # 切换到缓存目录
                            os.chdir(cache_dir)
                            print(f"[文件重新生成] 切换到缓存目录: {cache_dir}")

                            clip.write_videofile(
                                video_file,
                                codec="libx264",
                                audio_codec="aac",
                                bitrate="3000k",
                                preset=preset,
                                ffmpeg_params=["-crf", crf],
                                logger=None
                            )
                            has_audio = clip.audio is not None
                            print(f"[文件重新生成] MoviePy 视频文件生成成功: {video_file}")

                        finally:
                            # 恢复原工作目录
                            os.chdir(original_cwd)
                            print(f"[文件重新生成] 恢复工作目录: {original_cwd}")

                            # 检查是否有文件意外生成在原工作目录
                            work_dir_video = os.path.join(original_cwd, f"{segment_name}.mp4")
                            if os.path.exists(work_dir_video) and work_dir_video != video_file:
                                print(f"[文件重新生成] 发现视频文件在原工作目录: {work_dir_video}")
                                # 移动到正确位置
                                import shutil
                                if os.path.exists(video_file):
                                    FileUtils.safe_remove(video_file)
                                shutil.move(work_dir_video, video_file)
                                print(f"[文件重新生成] 已移动视频文件到正确位置: {video_file}")

                    result['video_file'] = video_file

                    # 提取音频
                    if has_audio:
                        try:
                            ffmpeg_cmd = [
                                "ffmpeg", "-y",
                                "-i", video_file,
                                "-vn",
                                "-acodec", "libmp3lame",
                                "-ab", "192k",
                                audio_file
                            ]
                            print(f"[文件重新生成] 执行音频提取命令: {' '.join(ffmpeg_cmd)}")

                            subprocess.run(
                                ffmpeg_cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                creationflags=subprocess.CREATE_NO_WINDOW,
                                timeout=60,
                                cwd=cache_dir  # 设置工作目录为缓存目录
                            )

                            if os.path.exists(audio_file) and os.path.getsize(audio_file) > 0:
                                result['audio_file'] = audio_file
                                print(f"[文件重新生成] 音频文件生成成功: {audio_file}")
                            else:
                                print(f"[文件重新生成] 警告：音频文件未在预期位置生成: {audio_file}")
                                # 检查是否在工作目录生成了文件
                                work_dir_audio = os.path.join(os.getcwd(), f"{segment_name}.mp3")
                                if os.path.exists(work_dir_audio):
                                    print(f"[文件重新生成] 发现音频文件在工作目录: {work_dir_audio}")
                                    # 移动文件到正确位置
                                    import shutil
                                    shutil.move(work_dir_audio, audio_file)
                                    result['audio_file'] = audio_file
                                    print(f"[文件重新生成] 已移动音频文件到正确位置: {audio_file}")
                        except Exception as e:
                            self.log(f"音频提取失败：{e}")

                # 生成字幕文件（使用新时间，归零）
                subtitle_file = os.path.join(cache_dir, f"{segment_name}.srt")

                print(f"[文件重新生成] 目标字幕文件: {subtitle_file}")

                # 删除旧字幕文件
                FileUtils.safe_remove(subtitle_file)

                # 创建新字幕（时间归零）
                import pysrt
                new_sub = pysrt.SubRipItem()
                new_sub.index = 1
                new_sub.start = pysrt.SubRipTime(milliseconds=0)
                new_sub.end = pysrt.SubRipTime(milliseconds=int((new_end_time - new_start_time) * 1000))
                new_sub.text = segment.text

                pysrt.SubRipFile([new_sub]).save(subtitle_file, encoding='utf-8')
                result['subtitle_file'] = subtitle_file
                print(f"[文件重新生成] 字幕文件生成成功: {subtitle_file}")

                # 检查是否有文件意外生成在工作目录
                work_dir_srt = os.path.join(os.getcwd(), f"{segment_name}.srt")
                if os.path.exists(work_dir_srt) and work_dir_srt != subtitle_file:
                    print(f"[文件重新生成] 发现字幕文件在工作目录: {work_dir_srt}")
                    FileUtils.safe_remove(work_dir_srt)
                    print(f"[文件重新生成] 已删除工作目录中的字幕文件")

                result['success'] = True
                self.log(f"片段 #{segment.id} 文件重新生成完成")
                print(f"[文件重新生成] 所有文件已生成在缓存目录: {cache_dir}")

            finally:
                if clip:
                    try:
                        clip.close()
                    except:
                        pass
                if media:
                    try:
                        media.close()
                    except:
                        pass

        except Exception as e:
            result['error'] = str(e)
            self.log(f"重新生成片段文件失败：{e}")
            import traceback
            self.log(f"详细错误：{traceback.format_exc()}")

        return result

    def get_video_duration(self, video_path: str) -> float:
        """获取视频时长"""
        try:
            command = [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=nw=1:nk=1", video_path
            ]
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            return float(result.stdout.strip())
        except Exception:
            return 0.0
