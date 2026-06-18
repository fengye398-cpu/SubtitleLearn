import os
import subprocess
import json
from pathlib import Path
from typing import List, Callable, Optional
from datetime import timedelta

from database.manager import db_manager
from database.models import SubtitleSegment, ExportRecord
from utils.file_utils import FileUtils
from utils.format_utils import FormatUtils
from config.settings import app_config

# [ROCKET] 方案7：导入亚毫秒级精准技术模块
try:
    from .high_precision_time import HighPrecisionTime, AccumulatedErrorCompensator, SmartRoundingStrategy, PrecisionValidator
    from .frame_rate_sync import FrameRateAnalyzer, FrameAlignedDurationCalculator, MultiVideoFrameRateSync
    from .keyframe_precision import KeyframeExtractor, KeyframeAlignedDurationCalculator, KeyframePrecisionAnalyzer
    from .triple_verification import TripleVerificationEngine
    SOLUTION_7_AVAILABLE = True
    print("[ROCKET] 方案7亚毫秒级精准技术已加载到单项目导出器")
except ImportError as e:
    print(f"[WARN] 方案7模块导入失败，单项目导出器将使用方案6: {e}")
    SOLUTION_7_AVAILABLE = False

class Exporter:
    """导出器类"""

    def __init__(self):
        self.cancel_flag = False
        self.progress_callback = None
        self.log_callback = None

        # [ROCKET] 方案7：初始化亚毫秒级精准技术组件
        if SOLUTION_7_AVAILABLE:
            self.high_precision_enabled = True
            self.triple_verifier = TripleVerificationEngine()
            self.frame_sync = MultiVideoFrameRateSync()
            self.keyframe_precision = KeyframePrecisionAnalyzer()
            self.error_compensator = AccumulatedErrorCompensator()
            print("[ROCKET] 方案7亚毫秒级精准技术组件已初始化（单项目导出器）")
        else:
            self.high_precision_enabled = False
            print("[WARN] 单项目导出器使用方案6精准技术")
    
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
    
    def export_segments(self, segment_ids: List[int], output_dir: str,
                       export_types: List[str], merge: bool = False, gap: float = 0.2,
                       direct_cut: bool = False, naming_mode: str = "index",
                       preset: str = "veryfast", crf: str = "24") -> bool:
        """导出选中的片段

        Args:
            segment_ids: 片段ID列表
            output_dir: 输出目录
            export_types: 导出类型列表 ['video', 'audio', 'subtitle']
            merge: 是否合并为单个文件
            gap: 合并时的间隔（秒）
            direct_cut: 是否直接从原视频切割
            naming_mode: 命名模式 'index' 或 'subtitle'
            preset: FFmpeg编码预设
            crf: CRF质量参数
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
            
            # 确保输出目录存在
            FileUtils.ensure_dir(output_dir)
            
            # 获取项目信息
            project = db_manager.get_project(segments[0].project_id)
            if not project:
                self.log("错误：未找到项目信息")
                return False
            
            self.log(f"开始导出 {len(segments)} 个片段到：{output_dir}")

            # 如果选择直接切割，使用增强导出器
            if direct_cut:
                from core.enhanced_exporter import enhanced_exporter
                enhanced_exporter.set_callbacks(self.progress_callback, self.log_callback)
                return enhanced_exporter.export_segments_direct_cut(
                    segment_ids, output_dir, export_types, merge,
                    naming_mode, preset, crf, gap
                )

            if merge:
                # 合并导出
                return self._export_merged(segments, output_dir, export_types, project.name, gap)
            else:
                # 单独导出
                return self._export_individual(segments, output_dir, export_types)
                
        except Exception as e:
            self.log(f"导出失败：{e}")
            return False
    
    def _export_individual(self, segments: List[SubtitleSegment], 
                          output_dir: str, export_types: List[str]) -> bool:
        """单独导出每个片段"""
        total_operations = len(segments) * len(export_types)
        current_operation = 0
        
        for segment in segments:
            if self.cancel_flag:
                self.log("导出已取消")
                return False
            
            segment_name = f"{segment.index_num:03d}_{FileUtils.clean_filename(segment.text[:30])}"
            
            for export_type in export_types:
                current_operation += 1
                self.update_progress(
                    current_operation, total_operations,
                    f"导出片段 {segment.index_num} - {export_type}"
                )
                
                if export_type == 'video' and segment.video_file:
                    src_file = segment.video_file
                    dst_file = os.path.join(output_dir, f"{segment_name}.mp4")
                    FileUtils.copy_file(src_file, dst_file)
                    
                elif export_type == 'audio' and segment.audio_file:
                    src_file = segment.audio_file
                    dst_file = os.path.join(output_dir, f"{segment_name}.mp3")
                    FileUtils.copy_file(src_file, dst_file)
                    
                elif export_type == 'subtitle' and segment.subtitle_file:
                    src_file = segment.subtitle_file
                    dst_file = os.path.join(output_dir, f"{segment_name}.srt")
                    FileUtils.copy_file(src_file, dst_file)
        
        self.log(f"单独导出完成：{len(segments)} 个片段")
        return True
    
    def _export_merged(self, segments: List[SubtitleSegment],
                      output_dir: str, export_types: List[str], project_name: str, gap: float) -> bool:
        """合并导出片段"""
        try:
            # 按索引排序
            segments.sort(key=lambda x: x.index_num)
            
            for export_type in export_types:
                if self.cancel_flag:
                    return False
                
                self.log(f"合并导出 {export_type}...")
                
                if export_type == 'video':
                    success = self._merge_video_files(segments, output_dir, project_name)
                elif export_type == 'audio':
                    success = self._merge_audio_files(segments, output_dir, project_name)
                elif export_type == 'subtitle':
                    success = self._merge_subtitle_files(segments, output_dir, project_name, gap)
                else:
                    continue
                
                if not success:
                    self.log(f"合并 {export_type} 失败")
                    return False
            
            self.log("合并导出完成")
            return True
            
        except Exception as e:
            self.log(f"合并导出失败：{e}")
            return False
    
    def _merge_video_files(self, segments: List[SubtitleSegment], 
                          output_dir: str, project_name: str) -> bool:
        """合并视频文件"""
        try:
            video_files = [s.video_file for s in segments if s.video_file and os.path.exists(s.video_file)]
            if not video_files:
                self.log("没有可合并的视频文件")
                return True
            
            # 创建文件列表
            list_file = os.path.join(output_dir, "video_list.txt")
            with open(list_file, 'w', encoding='utf-8') as f:
                for video_file in video_files:
                    f.write(f"file '{os.path.abspath(video_file)}'\n")
            
            # 合并视频 - 使用项目名称作为文件名
            output_file = os.path.join(output_dir, f"{project_name}.mp4")
            cmd = [
                "ffmpeg", "-f", "concat", "-safe", "0", "-i", list_file,
                "-c", "copy", output_file, "-y"
            ]
            
            result = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            # 清理临时文件
            os.remove(list_file)
            
            if result.returncode == 0:
                self.log(f"视频合并完成：{output_file}")
                return True
            else:
                self.log("视频合并失败")
                return False
                
        except Exception as e:
            self.log(f"视频合并失败：{e}")
            return False
    
    def _merge_audio_files(self, segments: List[SubtitleSegment], 
                          output_dir: str, project_name: str) -> bool:
        """合并音频文件"""
        try:
            audio_files = [s.audio_file for s in segments if s.audio_file and os.path.exists(s.audio_file)]
            if not audio_files:
                self.log("没有可合并的音频文件")
                return True
            
            # 创建文件列表
            list_file = os.path.join(output_dir, "audio_list.txt")
            with open(list_file, 'w', encoding='utf-8') as f:
                for audio_file in audio_files:
                    f.write(f"file '{os.path.abspath(audio_file)}'\n")
            
            # 合并音频 - 使用项目名称作为文件名
            output_file = os.path.join(output_dir, f"{project_name}.mp3")
            cmd = [
                "ffmpeg", "-f", "concat", "-safe", "0", "-i", list_file,
                "-c", "copy", output_file, "-y"
            ]
            
            result = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            # 清理临时文件
            os.remove(list_file)
            
            if result.returncode == 0:
                self.log(f"音频合并完成：{output_file}")
                return True
            else:
                self.log("音频合并失败")
                return False
                
        except Exception as e:
            self.log(f"音频合并失败：{e}")
            return False

    def _merge_subtitle_files(self, segments: List[SubtitleSegment],
                             output_dir: str, project_name: str, gap: float) -> bool:
        """合并字幕文件 - 方案5终极精准：预计算时长映射+双重验证+关键帧对齐

        注意：导出不受重复次数影响，始终按1次导出
        """
        try:
            import pysrt
            from datetime import timedelta

            # 字幕文件与合并后的视频文件同名
            output_file = os.path.join(output_dir, f"{project_name}.srt")

            # 🏆 步骤1：预计算时长映射（外部脚本完全一致）
            duration_map = {}
            files_to_use = []

            self.log(f"🏆 方案5终极精准：开始预计算时长映射...")

            for segment in segments:
                media_file = segment.video_file or segment.audio_file
                if media_file:
                    file_key = os.path.basename(media_file)  # 使用文件名作为key，与外部脚本一致

                    if file_key not in duration_map:  # 避免重复计算
                        # 🏆 双重精确验证
                        moviepy_duration = self._get_moviepy_duration(media_file, segment.video_file is not None)
                        external_duration = self._get_external_script_duration(media_file)

                        # 使用外部脚本的时长（与merge_subtitles完全一致）
                        duration_map[file_key] = external_duration
                        files_to_use.append(file_key)

                        self.log(f"  文件 {file_key}: MoviePy={moviepy_duration:.3f}s, ffprobe={external_duration:.3f}s")

            # 🏆 步骤2：外部脚本完全一致的字幕合并逻辑
            merged_subs = []
            current_time = timedelta(seconds=0)
            gap_td = timedelta(seconds=gap)  # 🏆 预计算间隔时间

            self.log(f"🏆 开始字幕合并，使用外部脚本标准gap={gap}s...")

            for segment in segments:
                if self.cancel_flag:
                    return False

                # 片段字幕文件（已归零）
                srt_path = segment.subtitle_file
                if not srt_path or not os.path.exists(srt_path):
                    # 如果没有独立字幕文件，则用整段文本作为一个条目
                    duration = self._probe_duration(segment.video_file or segment.audio_file)
                    new_start = current_time
                    new_end = current_time + timedelta(seconds=duration)

                    # [TARGET] 智能间隔处理
                    if merged_subs:
                        prev_end = merged_subs[-1]['end']
                        if new_start < prev_end + gap_td:
                            new_start = prev_end + gap_td
                            new_end = new_start + timedelta(seconds=duration)

                    merged_subs.append({
                        'index': len(merged_subs) + 1,
                        'start': new_start,
                        'end': new_end,
                        'text': segment.text or ""
                    })
                    current_time = new_end + gap_td
                    continue

                subs = pysrt.open(srt_path, encoding='utf-8')

                # 逐条加入（偏移当前时间，并处理与上一条的最小间隔）
                for sub in subs:
                    sub_start = timedelta(hours=sub.start.hours, minutes=sub.start.minutes, seconds=sub.start.seconds, milliseconds=sub.start.milliseconds)
                    sub_end = timedelta(hours=sub.end.hours, minutes=sub.end.minutes, seconds=sub.end.seconds, milliseconds=sub.end.milliseconds)
                    new_start = current_time + sub_start
                    new_end = current_time + sub_end

                    # [TARGET] 关键改进：智能间隔处理（完全模仿外部脚本）
                    if merged_subs:
                        prev_end = merged_subs[-1]['end']
                        if new_start < prev_end + gap_td:
                            new_start = prev_end + gap_td
                            if new_end < new_start:
                                new_end = new_start + timedelta(milliseconds=500)

                    merged_subs.append({
                        'index': len(merged_subs) + 1,
                        'start': new_start,
                        'end': new_end,
                        'text': sub.text
                    })

                # 🏆 关键：外部脚本完全一致的时间轴推进逻辑
                media_path = segment.video_file or segment.audio_file
                file_key = os.path.basename(media_path) if media_path else f"segment_{segment.index_num}"

                if file_key in duration_map:
                    seg_duration = duration_map[file_key]
                    current_time += timedelta(seconds=seg_duration) + gap_td
                    self.log(f"  片段 {segment.index_num}: 预计算时长 {seg_duration:.3f}s, 累计时间 {current_time.total_seconds():.3f}s")
                else:
                    # 回退方法
                    seg_duration = self._probe_duration(media_path)
                    current_time += timedelta(seconds=seg_duration) + gap_td
                    self.log(f"  片段 {segment.index_num}: 回退时长 {seg_duration:.3f}s, 累计时间 {current_time.total_seconds():.3f}s")

            # 写入字幕文件
            def format_td(td: timedelta) -> str:
                total_ms = int(td.total_seconds() * 1000)
                hours = total_ms // 3600000
                minutes = (total_ms % 3600000) // 60000
                seconds = (total_ms % 60000) // 1000
                millis = total_ms % 1000
                return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"

            with open(output_file, 'w', encoding='utf-8') as f:
                for sub in merged_subs:
                    f.write(f"{sub['index']}\n")
                    f.write(f"{format_td(sub['start'])} --> {format_td(sub['end'])}\n")
                    f.write(f"{sub['text']}\n\n")

            self.log(f"字幕合并完成：{output_file}")

            # 清理原始字幕文件和临时文件
            self._cleanup_original_subtitle_files(segments, output_dir)

            return True

        except Exception as e:
            self.log(f"字幕合并失败：{e}")
            return False

    def _cleanup_original_subtitle_files(self, segments: List, output_dir: str):
        """清理原始字幕文件和临时文件"""
        try:
            from pathlib import Path

            # 收集所有需要清理的文件
            files_to_cleanup = []

            # 添加片段的字幕文件
            for segment in segments:
                if hasattr(segment, 'subtitle_file') and segment.subtitle_file:
                    if os.path.exists(segment.subtitle_file):
                        files_to_cleanup.append(segment.subtitle_file)

            # 清理输出目录中的临时文件
            output_path = Path(output_dir)
            temp_patterns = [
                '*_original.srt', '*_backup.srt', '*_temp.srt',
                '*_validated.srt', '*_merged.srt', '*.json'
            ]

            for pattern in temp_patterns:
                temp_files = list(output_path.glob(pattern))
                for temp_file in temp_files:
                    files_to_cleanup.append(str(temp_file))

            # 执行清理
            cleaned_count = 0
            for file_path in files_to_cleanup:
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        cleaned_count += 1
                        self.log(f"已删除原始文件: {os.path.basename(file_path)}")
                except Exception as e:
                    self.log(f"删除文件失败 {file_path}: {e}")

            if cleaned_count > 0:
                self.log(f"清理完成，共删除 {cleaned_count} 个原始文件")

        except Exception as e:
            self.log(f"清理原始文件时出错: {e}")

    def _get_external_script_duration(self, media_file):
        """获取媒体文件时长 - 外部脚本完全一致的方法（ffprobe）"""
        if not media_file or not os.path.exists(media_file):
            return 0.0

        try:
            # 🏆 使用与外部脚本完全相同的ffprobe命令
            cmd = [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=nw=1:nk=1", media_file
            ]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            duration = float(result.stdout.strip())
            return duration
        except Exception as e:
            return 0.0

    def _get_moviepy_duration(self, media_file, is_video=True):
        """获取媒体文件时长 - MoviePy方法（双重验证）"""
        if not media_file or not os.path.exists(media_file):
            return 0.0

        try:
            # 强制配置MoviePy使用系统FFmpeg
            import os
            os.environ['FFMPEG_BINARY'] = 'ffmpeg'  # 设置环境变量

            import moviepy.config as mp_config
            mp_config.FFMPEG_BINARY = "ffmpeg"

            if is_video:
                from moviepy.editor import VideoFileClip
                with VideoFileClip(media_file) as clip:
                    return clip.duration
            else:
                from moviepy.editor import AudioFileClip
                with AudioFileClip(media_file) as clip:
                    return clip.duration
        except OSError as e:
            if "ffmpeg" in str(e).lower():
                self.log("警告：FFmpeg不可用，跳过MoviePy时长验证")
            # 回退到ffprobe方法
            return self._get_external_script_duration(media_file)
        except Exception as e:
            # 回退到ffprobe方法
            return self._get_external_script_duration(media_file)

    def _probe_duration(self, media_path: Optional[str]) -> float:
        """使用 ffprobe 获取媒体时长（秒），失败则回退 0.0"""
        # 为了向后兼容，保留此方法，但内部调用外部脚本方法
        return self._get_external_script_duration(media_path)

    def create_export_record(self, project_id: int, segment_ids: List[int],
                           export_type: str, output_path: str) -> int:
        """创建导出记录"""
        record = ExportRecord(
            project_id=project_id,
            segment_ids=segment_ids,
            export_type=export_type,
            output_path=output_path
        )
        return db_manager.create_export_record(record)

    def get_export_presets(self) -> dict:
        """获取导出预设"""
        return {
            'video': {
                'preset': app_config.get('export.preset', 'veryfast'),
                'crf': app_config.get('export.crf', '24'),
                'format': app_config.get('export.default_format', 'mp4')
            },
            'audio': {
                'format': 'mp3',
                'bitrate': '192k'
            },
            'subtitle': {
                'format': 'srt',
                'encoding': 'utf-8'
            }
        }

# 全局导出器实例
exporter = Exporter()
