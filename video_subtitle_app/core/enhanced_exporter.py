#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增强导出器 - 集成外部脚本的切割功能
支持直接从原视频切割导出片段
"""

import os
import re
import pysrt
import subprocess
import tempfile
import multiprocessing
from datetime import timedelta
from pathlib import Path
from typing import List, Optional, Callable, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
from moviepy.editor import VideoFileClip, AudioFileClip

from database.models import SubtitleSegment
from database.manager import db_manager
from utils.file_utils import FileUtils
from config.settings import app_config

# 尝试导入psutil用于RAM检测
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def calculate_optimal_workers(operation_type='video', log_callback=None):
    """根据可用RAM和CPU核心数计算最优worker数量

    Args:
        operation_type: 'video' (视频编码，内存密集) 或 'light' (音频/stream copy，轻量级)
        log_callback: 可选的日志回调函数，用于输出到UI

    Returns:
        int: 最优worker数量
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    cpu_count = multiprocessing.cpu_count()

    if not HAS_PSUTIL:
        # 没有psutil，使用保守默认值
        if operation_type == 'video':
            return min(3, max(2, cpu_count // 2))
        else:
            return min(6, cpu_count)

    # 获取可用RAM（GB）
    available_ram_gb = psutil.virtual_memory().available / (1024 ** 3)
    total_ram_gb = psutil.virtual_memory().total / (1024 ** 3)

    log(f"  [系统资源] 总内存: {total_ram_gb:.1f}GB, 可用: {available_ram_gb:.1f}GB")

    if operation_type == 'video':
        # 视频编码：每个worker约250-300MB，使用40%可用RAM
        usable_ram_gb = max(0, available_ram_gb - 0.8)
        target_ram_gb = usable_ram_gb * 0.4
        workers = int(target_ram_gb * 1024 / 300)
        workers = max(2, min(workers, cpu_count, 8))

        log(f"  [自动调整] 视频编码worker: {workers}个 (基于{available_ram_gb:.1f}GB可用内存)")
        return workers
    else:
        # 轻量级操作（音频/stream copy）：每个worker约50MB
        usable_ram_gb = max(0, available_ram_gb - 0.5)
        target_ram_gb = usable_ram_gb * 0.3
        workers = int(target_ram_gb * 1024 / 50)
        workers = max(4, min(workers, cpu_count, 12))

        log(f"  [自动调整] 轻量级操作worker: {workers}个")
        return workers


class EnhancedExporter:
    """增强导出器 - 集成外部脚本功能"""
    
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
    
    def export_segments_direct_cut(self, segment_ids: List[int], output_dir: str,
                                  export_types: List[str], merge: bool = False,
                                  naming_mode: str = "index", preset: str = "veryfast", 
                                  crf: str = "24", gap: float = 0.2) -> bool:
        """直接从原视频切割导出片段
        
        Args:
            segment_ids: 片段ID列表
            output_dir: 输出目录
            export_types: 导出类型列表 ['video', 'audio', 'subtitle']
            merge: 是否合并为单个文件
            naming_mode: 命名模式 'index' 或 'subtitle'
            preset: FFmpeg编码预设
            crf: CRF质量参数
            gap: 合并时的间隔（秒）
        """
        try:
            self.cancel_flag = False
            
            if not segment_ids:
                self.log("错误：没有选择要导出的片段")
                return False
            
            # 获取片段数据
            segments = db_manager.get_segments_by_ids(segment_ids)
            if not segments:
                self.log("错误：未找到要导出的片段")
                return False
            
            # 获取项目信息
            project = db_manager.get_project(segments[0].project_id)
            if not project or not project.video_path:
                self.log("错误：未找到项目或视频文件")
                return False
            
            if not os.path.exists(project.video_path):
                self.log(f"错误：视频文件不存在：{project.video_path}")
                return False
            
            # 确保输出目录存在
            FileUtils.ensure_dir(output_dir)
            
            self.log(f"开始直接切割导出 {len(segments)} 个片段到：{output_dir}")
            self.log(f"源视频：{project.video_path}")
            
            # 按索引排序
            segments.sort(key=lambda x: x.index_num)
            
            # 创建临时字幕文件
            temp_srt_file = self._create_temp_subtitle_file(segments, project.subtitle_path)
            if not temp_srt_file:
                self.log("错误：无法创建临时字幕文件")
                return False
            
            try:
                # 执行切割
                success = self._cut_video_audio_subs(
                    project.video_path, temp_srt_file, output_dir,
                    naming_mode, preset, crf, export_types
                )
                
                if not success:
                    return False
                
                # 如果需要合并
                if merge:
                    success = self._merge_exported_files(output_dir, export_types, 
                                                       project.name, gap)
                
                return success
                
            finally:
                # 清理临时文件
                try:
                    if os.path.exists(temp_srt_file):
                        os.unlink(temp_srt_file)
                except:
                    pass
                    
        except Exception as e:
            self.log(f"导出失败：{e}")
            return False
    
    def _create_temp_subtitle_file(self, segments: List[SubtitleSegment], 
                                  original_srt_path: Optional[str]) -> Optional[str]:
        """创建临时字幕文件，只包含选中的片段"""
        try:
            # 如果有原始字幕文件，从中提取对应片段
            if original_srt_path and os.path.exists(original_srt_path):
                original_subs = pysrt.open(original_srt_path, encoding="utf-8-sig")
                
                # 创建新的字幕文件，只包含选中的片段
                new_subs = pysrt.SubRipFile()
                
                for i, segment in enumerate(segments, 1):
                    # 查找对应的字幕条目
                    for sub in original_subs:
                        if (abs(sub.start.ordinal / 1000 - segment.start_time) < 0.1 and
                            abs(sub.end.ordinal / 1000 - segment.end_time) < 0.1):
                            # 创建新的字幕条目
                            new_sub = pysrt.SubRipItem(
                                index=i,
                                start=sub.start,
                                end=sub.end,
                                text=sub.text
                            )
                            new_subs.append(new_sub)
                            break
            else:
                # 从片段数据创建字幕文件
                new_subs = pysrt.SubRipFile()
                
                for i, segment in enumerate(segments, 1):
                    start_time = pysrt.SubRipTime(seconds=segment.start_time)
                    end_time = pysrt.SubRipTime(seconds=segment.end_time)
                    
                    new_sub = pysrt.SubRipItem(
                        index=i,
                        start=start_time,
                        end=end_time,
                        text=segment.text
                    )
                    new_subs.append(new_sub)
            
            # 保存临时字幕文件
            temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.srt', 
                                                   delete=False, encoding='utf-8')
            temp_file.close()
            
            new_subs.save(temp_file.name, encoding='utf-8')
            return temp_file.name
            
        except Exception as e:
            self.log(f"创建临时字幕文件失败：{e}")
            return None
    
    def _cut_single_segment(self, video_file: str, sub: pysrt.SubRipItem, index: int,
                           total: int, output_dir: str, naming_mode: str,
                           preset: str, crf: str, export_types: List[str],
                           is_audio: bool) -> tuple[bool, Optional[str]]:
        """切割单个片段（用于并行处理）

        Args:
            video_file: 媒体文件路径
            sub: 字幕条目
            index: 片段索引（从1开始）
            total: 总片段数
            output_dir: 输出目录
            naming_mode: 命名模式
            preset: FFmpeg预设
            crf: CRF质量参数
            export_types: 导出类型列表
            is_audio: 是否为纯音频文件

        Returns:
            (是否成功, 错误信息)
        """
        try:
            # 每个worker独立打开媒体文件（线程安全）
            if is_audio:
                media = AudioFileClip(video_file)
            else:
                media = VideoFileClip(video_file)

            # 生成文件名
            if naming_mode == "subtitle":
                subtitle_text = sub.text.replace('\n', ' ').replace('\r', ' ')
                subtitle_text = ''.join(c for c in subtitle_text if c.isalnum() or c in (' ', '_', '-'))
                subtitle_text = subtitle_text.strip().replace(' ', '_')
                if not subtitle_text:
                    subtitle_text = f"clip_{index}"
                name = f"{index:02d}.{subtitle_text}"
            else:
                name = f"{index:02d}"

            # 切割时间
            start = sub.start.ordinal / 1000
            end = sub.end.ordinal / 1000
            clip = media.subclip(start, end)

            # 导出视频
            if 'video' in export_types and not is_audio:
                video_path = os.path.join(output_dir, f"{name}.mp4")
                clip.write_videofile(
                    video_path,
                    codec="libx264",
                    audio_codec="aac",
                    bitrate="3000k",
                    preset=preset,
                    ffmpeg_params=["-crf", crf],
                    logger=None
                )

            # 导出音频
            if 'audio' in export_types:
                audio_path = os.path.join(output_dir, f"{name}.mp3")
                if is_audio:
                    clip.write_audiofile(audio_path, logger=None)
                else:
                    clip.audio.write_audiofile(audio_path, logger=None)

            # 导出字幕
            if 'subtitle' in export_types:
                sub_rel = pysrt.SubRipItem(
                    index=1,
                    start=pysrt.SubRipTime(seconds=0),
                    end=pysrt.SubRipTime(seconds=end-start),
                    text=sub.text
                )
                srt_path = os.path.join(output_dir, f"{name}.srt")
                pysrt.SubRipFile([sub_rel]).save(srt_path, encoding='utf-8')

            # 关闭媒体文件
            media.close()

            self.log(f"  [{index}/{total}] 切割完成: {name}")
            return True, None

        except Exception as e:
            error_msg = f"片段 {index} 切割失败: {str(e)}"
            self.log(f"  [错误] {error_msg}")
            return False, error_msg

    def _cut_video_audio_subs(self, video_file: str, srt_file: str, output_dir: str,
                             naming_mode: str, preset: str, crf: str,
                             export_types: List[str]) -> bool:
        """切割视频/音频/字幕 - 支持并行处理"""
        try:
            # 读取字幕文件
            subs = pysrt.open(srt_file, encoding="utf-8-sig")
            if not subs:
                self.log("错误：无法读取字幕文件")
                return False

            # 检查文件类型
            ext = os.path.splitext(video_file)[1].lower()
            is_audio = ext in [".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg"]

            total_segments = len(subs)

            # 计算最优worker数量
            max_workers = calculate_optimal_workers(
                'video' if not is_audio else 'light',
                log_callback=self.log
            )
            self.log(f"使用 {max_workers} 个并行worker处理 {total_segments} 个片段")

            # 并行处理片段
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = []
                for i, sub in enumerate(subs, 1):
                    if self.cancel_flag:
                        self.log("导出已取消")
                        return False

                    future = executor.submit(
                        self._cut_single_segment,
                        video_file, sub, i, total_segments, output_dir,
                        naming_mode, preset, crf, export_types, is_audio
                    )
                    futures.append((future, i))

                # 等待所有任务完成
                completed = 0
                failed = 0
                for future, seg_index in futures:
                    if self.cancel_flag:
                        self.log("导出已取消")
                        return False

                    try:
                        success, error_msg = future.result()
                        if success:
                            completed += 1
                        else:
                            failed += 1

                        # 更新进度
                        self.update_progress(
                            completed + failed,
                            total_segments,
                            f"切割片段 {completed + failed}/{total_segments}"
                        )
                    except Exception as e:
                        self.log(f"  [错误] 片段 {seg_index} 处理异常: {e}")
                        failed += 1

            if failed > 0:
                self.log(f"切割完成：成功 {completed} 个，失败 {failed} 个")
                return False
            else:
                self.log(f"切割完成：{completed} 个片段")
                return True

        except Exception as e:
            self.log(f"切割失败：{e}")
            return False

    def _merge_exported_files(self, output_dir: str, export_types: List[str],
                             project_name: str, gap: float) -> bool:
        """合并导出的文件"""
        try:
            self.log("开始合并文件...")

            # 支持的文件扩展名
            video_exts = ['.mp4', '.mkv', '.avi', '.mov']
            audio_exts = ['.mp3', '.wav', '.flac', '.aac', '.m4a', '.ogg']

            # 合并视频
            if 'video' in export_types:
                for ext in video_exts:
                    video_files = [f for f in os.listdir(output_dir) if f.endswith(ext)]
                    if video_files:
                        merged_video = os.path.join(output_dir, f"{project_name}{ext}")
                        success = self._merge_files(output_dir, ext, merged_video)
                        if success:
                            self.log(f"视频合并完成：{merged_video}")
                        break

            # 合并音频
            if 'audio' in export_types:
                for ext in audio_exts:
                    audio_files = [f for f in os.listdir(output_dir) if f.endswith(ext)]
                    if audio_files:
                        merged_audio = os.path.join(output_dir, f"{project_name}{ext}")
                        success = self._merge_files(output_dir, ext, merged_audio)
                        if success:
                            self.log(f"音频合并完成：{merged_audio}")
                        break

            # 合并字幕
            if 'subtitle' in export_types:
                srt_files = [f for f in os.listdir(output_dir) if f.endswith('.srt')]
                if srt_files:
                    merged_srt = os.path.join(output_dir, f"{project_name}.srt")
                    success = self._merge_subtitle_files(output_dir, srt_files, merged_srt, gap)
                    if success:
                        self.log(f"字幕合并完成：{merged_srt}")
                        # 清理原始字幕文件
                        self._cleanup_original_files(output_dir, srt_files)

            return True

        except Exception as e:
            self.log(f"合并失败：{e}")
            return False

    def _merge_files(self, output_dir: str, ext: str, merged_file: str) -> bool:
        """合并媒体文件 - 基于外部脚本的逻辑"""
        try:
            files = [f for f in os.listdir(output_dir) if f.endswith(ext)]
            files.sort(key=self._extract_leading_number)

            if not files:
                return False

            # 创建播放列表文件
            list_file = os.path.join(output_dir, f"list_{ext.replace('.', '_')}.txt")
            with open(list_file, "w", encoding="utf-8") as f:
                for file in files:
                    file_path = os.path.abspath(os.path.join(output_dir, file))
                    f.write(f"file '{file_path}'\n")

            # 使用FFmpeg合并
            cmd = [
                "ffmpeg", "-f", "concat", "-safe", "0", "-i", list_file,
                "-c", "copy", merged_file, "-y"
            ]

            result = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            # 清理临时文件
            try:
                os.remove(list_file)
            except:
                pass

            return result.returncode == 0

        except Exception as e:
            self.log(f"合并媒体文件失败：{e}")
            return False

    def _merge_subtitle_files(self, output_dir: str, files: List[str],
                             merged_srt: str, gap: float) -> bool:
        """合并字幕文件 - 基于外部脚本的逻辑"""
        try:
            files.sort(key=self._extract_leading_number)
            merged_subs = []
            current_time = timedelta(seconds=0)

            for i, file in enumerate(files):
                srt_file = os.path.join(output_dir, file)
                if not os.path.exists(srt_file):
                    continue

                subs = pysrt.open(srt_file, encoding='utf-8')
                for sub in subs:
                    sub_start = timedelta(
                        hours=sub.start.hours,
                        minutes=sub.start.minutes,
                        seconds=sub.start.seconds,
                        milliseconds=sub.start.milliseconds
                    )
                    sub_end = timedelta(
                        hours=sub.end.hours,
                        minutes=sub.end.minutes,
                        seconds=sub.end.seconds,
                        milliseconds=sub.end.milliseconds
                    )

                    new_start = current_time + sub_start
                    new_end = current_time + sub_end

                    # 处理重叠
                    if merged_subs:
                        prev_end = merged_subs[-1]['end']
                        if new_start < prev_end + timedelta(seconds=gap):
                            new_start = prev_end + timedelta(seconds=gap)
                            if new_end < new_start:
                                new_end = new_start + timedelta(milliseconds=500)

                    merged_subs.append({
                        'index': len(merged_subs) + 1,
                        'start': new_start,
                        'end': new_end,
                        'text': sub.text
                    })

                # 获取文件时长并推进时间轴
                video_file = file.replace('.srt', '.mp4')
                audio_file = file.replace('.srt', '.mp3')

                duration = 0
                if os.path.exists(os.path.join(output_dir, video_file)):
                    duration = self._get_media_duration(os.path.join(output_dir, video_file))
                elif os.path.exists(os.path.join(output_dir, audio_file)):
                    duration = self._get_media_duration(os.path.join(output_dir, audio_file))

                if duration > 0:
                    current_time += timedelta(seconds=duration)
                else:
                    # 如果无法获取时长，使用字幕的结束时间
                    if subs:
                        last_sub = subs[-1]
                        sub_duration = (last_sub.end.ordinal - last_sub.start.ordinal) / 1000
                        current_time += timedelta(seconds=sub_duration)

                current_time += timedelta(seconds=gap)

            # 写入合并后的字幕文件
            with open(merged_srt, "w", encoding="utf-8") as f:
                for sub in merged_subs:
                    f.write(f"{sub['index']}\n")
                    f.write(f"{self._format_timedelta(sub['start'])} --> {self._format_timedelta(sub['end'])}\n")
                    f.write(f"{sub['text']}\n\n")

            return True

        except Exception as e:
            self.log(f"合并字幕文件失败：{e}")
            return False

    def _extract_leading_number(self, filename: str) -> int:
        """提取文件名前面的数字用于排序"""
        m = re.match(r"(\d+)", os.path.splitext(filename)[0])
        return int(m.group(1)) if m else 0

    def _get_media_duration(self, file_path: str) -> float:
        """获取媒体文件时长"""
        try:
            command = [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=nw=1:nk=1", file_path
            ]
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            return float(result.stdout.strip())
        except:
            return 0.0

    def _format_timedelta(self, td: timedelta) -> str:
        """格式化时间差为SRT格式"""
        total_seconds = int(td.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        milliseconds = td.microseconds // 1000
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

    def _cleanup_original_files(self, output_dir: str, original_srt_files: List[str]):
        """清理原始字幕文件和临时文件"""
        try:
            from pathlib import Path

            # 清理原始字幕文件（除了合并后的文件）
            for srt_file in original_srt_files:
                file_path = os.path.join(output_dir, srt_file)
                try:
                    if os.path.exists(file_path) and not srt_file.endswith('.srt') or '_' in srt_file:
                        os.remove(file_path)
                        self.log(f"已删除原始字幕: {srt_file}")
                except Exception as e:
                    self.log(f"删除字幕文件失败 {srt_file}: {e}")

            # 清理临时文件
            output_path = Path(output_dir)
            temp_patterns = [
                '*_original.srt', '*_backup.srt', '*_temp.srt',
                '*_validated.srt', '*.json', 'list_*.txt'
            ]

            for pattern in temp_patterns:
                temp_files = list(output_path.glob(pattern))
                for temp_file in temp_files:
                    try:
                        temp_file.unlink()
                        self.log(f"已删除临时文件: {temp_file.name}")
                    except Exception as e:
                        self.log(f"删除临时文件失败 {temp_file.name}: {e}")

        except Exception as e:
            self.log(f"清理文件时出错: {e}")


# 全局增强导出器实例
enhanced_exporter = EnhancedExporter()
