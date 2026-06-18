#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MPV 播放器实现
使用进程方式调用MPV，完全避免python-mpv库的事件循环问题
"""

import os
import threading
import time
import subprocess
import tempfile
import hashlib
from typing import List, Optional, Dict
from pathlib import Path
from urllib.parse import quote

from database.models import SubtitleSegment
from database.manager import db_manager
from config.settings import app_config
from core.player_base import PlayerBase

# 导入MPV管理器
try:
    from mpv_manager import get_mpv_path, get_mpv_info
except ImportError:
    # 如果导入失败，使用默认的MPV查找方式
    def get_mpv_path():
        return "mpv"
    def get_mpv_info():
        return None


class MPVPlayer(PlayerBase):
    """基于进程调用的MPV播放器实现，避免事件循环冲突"""

    def __init__(self):
        """初始化 MPV 播放器"""
        super().__init__()

        # 使用进程方式，不再使用python-mpv库
        self.current_process = None
        self.monitor_thread = None

        # 跳转模式设置
        self.seek_mode = app_config.get('player.seek_mode', 'precise')

        # 播放状态
        self.is_playing = False
        self.current_segment = None

        # 重复播放设置
        self.repeat_count = app_config.get('player.repeat_count', 1)
        self.volume = app_config.get('player.volume', 80)

        # 字幕预切割缓存
        self.subtitle_cache_dir = Path(tempfile.gettempdir()) / "video_subtitle_cache"
        self.subtitle_cache_dir.mkdir(exist_ok=True)

        # MPV窗口大小设置
        self.window_width = app_config.get('player.window_width', 800)
        self.window_height = app_config.get('player.window_height', 600)

        # 临时文件管理（播放列表和字幕文件）
        self.temp_files = []

        print("MPV播放器初始化完成（进程模式）")

    @staticmethod
    def is_available() -> bool:
        """检查MPV是否可用"""
        try:
            # 使用MPV管理器检查可用性
            mpv_path = get_mpv_path()
            result = subprocess.run(
                [mpv_path, "--version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def get_name() -> str:
        """获取播放器名称"""
        return "MPV"

    @staticmethod
    def get_description() -> str:
        """获取播放器描述"""
        return "MPV（进程模式，更稳定）"




    def set_seek_mode(self, mode: str):
        """设置跳转模式"""
        if mode in ['smart', 'precise']:
            self.seek_mode = mode
            app_config.set('player.seek_mode', mode)

    def set_repeat_count(self, count: int):
        """设置重复次数"""
        self.repeat_count = max(1, count)
        app_config.set('player.repeat_count', self.repeat_count)

    def set_volume(self, volume: int):
        """设置音量"""
        self.volume = max(0, min(100, volume))
        app_config.set('player.volume', self.volume)

    def play_segment(self, segment: SubtitleSegment) -> bool:
        """播放单个片段 - 使用进程方式"""
        if not segment:
            print("播放失败: 片段为空")
            return False

        # 清理上一次播放的临时文件
        self._cleanup_temp_files()

        print(f"开始播放片段: ID={segment.id}, 时间={segment.start_time:.2f}s-{segment.end_time:.2f}s")

        # 获取视频文件路径
        project = db_manager.get_project(segment.project_id)
        if not project or not project.video_path or not os.path.exists(project.video_path):
            error_msg = "视频文件不存在或路径无效"
            print(error_msg)
            if self.on_error:
                self.on_error(error_msg)
            return False

        print(f"视频文件: {project.video_path}")

        try:
            # 停止当前播放
            self.stop()

            # 设置播放参数
            self.is_playing = True
            self.current_segment = {
                'start': segment.start_time,
                'end': segment.end_time,
                'text': segment.text,
                'repeat_count': self.repeat_count,
                'current_repeat': 0
            }

            # 启动播放进程
            return self._start_segment_playback(project.video_path, segment.start_time, segment.end_time)

        except Exception as e:
            print(f"播放失败: {e}")
            if self.on_error:
                self.on_error(f"播放失败：{e}")
            return False

    def _start_segment_playback(self, video_path: str, start_time: float, end_time: float) -> bool:
        """启动片段播放进程"""
        try:
            total_repeat = self.current_segment['repeat_count'] if self.current_segment else 1

            # 创建临时播放列表文件，包含重复的片段
            import tempfile
            playlist_content = []

            # 为每次重复添加一个播放项，使用EDL格式
            duration = end_time - start_time
            for i in range(total_repeat):
                playlist_content.append(f"edl://{video_path},{start_time},{duration}")

            # 写入临时播放列表文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.m3u', delete=False, encoding='utf-8') as f:
                f.write('\n'.join(playlist_content))
                playlist_file = f.name

            # 注册临时文件
            self._register_temp_file(playlist_file)

            # 检查是否有对应的字幕文件
            subtitle_file = self._find_subtitle_file(video_path)

            # 获取MPV可执行文件路径
            mpv_path = get_mpv_path()

            # 使用播放列表，一次性播放所有重复 
            # "--osc=yes",  # 显示控制界面
            #f"--geometry={self.window_width}x{self.window_height}",  #自定义MPV播放界面
            cmd = [
                mpv_path,
                f"--playlist={playlist_file}",
                f"--volume={self.volume}",
                
                "--keep-open=no",
                "--force-window=immediate",
                "--idle=no",
                "--input-default-bindings=yes",
              
                "--no-terminal",
                "--sub-auto=fuzzy",  # 自动加载字幕
                "--sub-file-paths=.:subtitles:subs",  # 字幕搜索路径
            ]



            # 单独片段播放时显示字幕
            if subtitle_file:
                cmd.extend([
                    f"--sub-file={subtitle_file}",
                    f"--sub-delay=-{start_time}",  # 设置字幕延迟，使字幕与视频片段时间同步
                    "--sub-visibility=yes",  # 确保字幕可见
                ])
                print(f"单独片段播放模式：加载字幕文件 {subtitle_file}, 时间偏移: -{start_time}秒")
            else:
                # 即使没有找到字幕文件，也启用自动搜索
                cmd.extend([
                    "--sub-visibility=yes",  # 确保字幕可见
                ])
                print("单独片段播放模式：启用字幕显示")



            # 启动进程
            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            print(f"MPV进程已启动: PID={self.current_process.pid}, 连续播放{total_repeat}次")
            print(f"播放列表文件: {playlist_file}")

            # 启动监控线程
            self.monitor_thread = threading.Thread(target=self._monitor_playback, daemon=True)
            self.monitor_thread.start()

            if self.on_play_start:
                repeat_info = f" (连续{total_repeat}次)" if total_repeat > 1 else ""
                self.on_play_start(f"播放片段: {self.current_segment['text'][:30]}...{repeat_info}")

            return True

        except Exception as e:
            print(f"启动播放进程失败: {e}")
            return False

    def _monitor_playback(self):
        """监控播放进程，支持用户随时停止"""
        if not self.current_process:
            return

        try:
            # 等待进程结束
            self.current_process.wait()
            return_code = self.current_process.returncode
            print(f"MPV进程已结束: 返回码={return_code}")

            # 检查结束原因
            if return_code == 0:
                # 正常播放完成
                print("播放正常完成")
                if self.on_play_end:
                    self.on_play_end("播放完成")
            else:
                # 用户手动关闭或其他原因
                print(f"播放被中断 (返回码: {return_code})")
                if self.on_play_end:
                    self.on_play_end("播放被中断")

            # 清理状态
            self.is_playing = False
            self.current_segment = None
            self.current_process = None

            # 清理批量播放状态
            if hasattr(self, 'batch_queue'):
                delattr(self, 'batch_queue')

        except Exception as e:
            print(f"监控播放异常: {e}")
            self.is_playing = False
            self.current_segment = None
            self.current_process = None

    def play_segments(self, segments: List[SubtitleSegment], continuous: bool = True) -> bool:
        """播放多个片段 - 批量播放逻辑：(片段1→片段2→...→片段N) × 重复次数"""
        if not segments:
            return False

        # 清理上一次播放的临时文件
        self._cleanup_temp_files()

        print(f"开始批量播放 {len(segments)} 个片段，重复 {self.repeat_count} 次")

        # 按视频文件分组片段（支持不同视频文件）
        video_groups = {}
        for segment in segments:
            project = db_manager.get_project(segment.project_id)
            if not project or not project.video_path:
                print(f"错误：找不到项目或视频路径 ID {segment.project_id}")
                continue

            video_path = project.video_path
            if not os.path.exists(video_path):
                print(f"警告：视频文件不存在，跳过 {video_path}")
                continue

            if video_path not in video_groups:
                video_groups[video_path] = []
            video_groups[video_path].append(segment)

        if not video_groups:
            error_msg = "没有有效的视频片段"
            print(error_msg)
            if self.on_error:
                self.on_error(error_msg)
            return False

        print(f"涉及 {len(video_groups)} 个视频文件:")
        for video_path, video_segments in video_groups.items():
            print(f"  {Path(video_path).name}: {len(video_segments)} 个片段")

        try:
            # 停止当前播放
            self.stop()

            # 使用新的多视频批量播放方法
            return self._create_multi_video_playlist(video_groups)

        except Exception as e:
            print(f"批量播放失败: {e}")
            if self.on_error:
                self.on_error(f"批量播放失败：{e}")
            return False

    def _create_multi_video_playlist(self, video_groups: Dict[str, List[SubtitleSegment]]) -> bool:
        """创建支持多个视频文件的批量播放列表（方案A实现）"""
        try:
            # 预切割所有片段的字幕
            all_segments = []
            for segments in video_groups.values():
                all_segments.extend(segments)

            # 最简单精准的字幕方案：直接使用原始字幕，播放时调整时间偏移
            segment_subtitles = self._simple_precise_subtitles(all_segments)

            # 【关键修复】创建单个EDL字符串，将所有片段串联
            # EDL格式：edl://file1,start1,len1,file2,start2,len2,...
            edl_parts = []
            current_time_offset = 0.0

            # 为每轮重复创建播放项
            for repeat_round in range(self.repeat_count):
                print(f"\n添加第 {repeat_round + 1}/{self.repeat_count} 轮播放（当前累积时间: {current_time_offset:.3f}s）")

                # 按原始顺序播放所有片段
                for seg_idx, segment in enumerate(all_segments, 1):
                    # 获取视频路径
                    project = db_manager.get_project(segment.project_id)
                    if not project:
                        continue

                    video_path = project.video_path
                    duration = segment.end_time - segment.start_time

                    # 【修复】将Windows路径转换为正斜杠，避免转义问题
                    video_path_normalized = video_path.replace('\\', '/')

                    # 【修复】使用固定精度格式化时间，避免浮点数精度误差
                    # 保留3位小数（毫秒级精度），避免 3.879999999999999 这样的误差
                    start_time_str = f"{segment.start_time:.3f}"
                    duration_str = f"{duration:.3f}"

                    # 添加到EDL字符串（所有片段串联成一个连续的播放序列）
                    edl_parts.append(f"{video_path_normalized},{start_time_str},{duration_str}")

                    print(f"  [片段{seg_idx}] {Path(video_path).name} 原始: {segment.start_time:.3f}s-{segment.end_time:.3f}s (时长: {duration:.3f}s) → EDL播放: {current_time_offset:.3f}s")
                    current_time_offset += duration

            # 【关键修复】创建单个EDL播放列表（使用分号分隔不同片段）
            # MPV EDL格式: edl://[file,start,length];[file,start,length];...
            edl_string = "edl://" + ";".join(edl_parts)
            playlist_content = [edl_string]

            print(f"\n【EDL串联】生成单个EDL字符串，包含 {len(edl_parts)} 个片段")
            print(f"【EDL串联】总播放时长: {current_time_offset:.3f}s")
            print(f"【EDL完整】{edl_string}")
            print(f"【EDL长度】{len(edl_string)} 字符")

            # 写入临时播放列表文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.m3u', delete=False, encoding='utf-8') as f:
                f.write('\n'.join(playlist_content))
                playlist_file = f.name

            # 注册临时文件
            self._register_temp_file(playlist_file)

            print(f"【播放列表】文件: {playlist_file}")
            print(f"【播放列表】条目数: {len(playlist_content)} (串联模式)")

            # 创建最简单精准的批量播放字幕文件
            batch_subtitle_file = None
            if segment_subtitles:
                batch_subtitle_file = self._create_simple_precise_subtitle_file(all_segments, segment_subtitles)
                # 注册字幕文件
                if batch_subtitle_file:
                    self._register_temp_file(batch_subtitle_file)

            # 获取MPV可执行文件路径
            mpv_path = get_mpv_path()

            # 启动MPV播放 
            # "--osc=yes", # 显示控制界面
            #f"--geometry={self.window_width}x{self.window_height}",  #自定义MPV播放界面
            cmd = [
                mpv_path,
                f"--playlist={playlist_file}",
                f"--volume={self.volume}",
                
                "--keep-open=no",
                "--force-window=immediate",
                "--idle=no",
                "--input-default-bindings=yes",
               
                "--no-terminal",
            ]

            # 批量播放时加载合并字幕
            if batch_subtitle_file:
                cmd.extend([
                    f"--sub-file={batch_subtitle_file}",
                    "--sub-visibility=yes",  # 显示字幕
                ])
                print(f"批量播放模式：加载合并字幕文件 {batch_subtitle_file}")
            else:
                cmd.extend([
                    "--sub-auto=no",  # 禁用自动字幕搜索
                    "--sub-visibility=no",  # 隐藏字幕
                ])
                print("批量播放模式：无字幕文件，禁用字幕显示")

            # 启动进程
            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            print(f"\n【MPV播放】进程已启动: PID={self.current_process.pid}")
            print(f"【MPV播放】播放模式: EDL串联 ({len(edl_parts)} 个片段连续播放)")
            print(f"【MPV播放】字幕文件: {batch_subtitle_file if batch_subtitle_file else '无'}")

            # 启动监控线程
            self.monitor_thread = threading.Thread(target=self._monitor_playback, daemon=True)
            self.monitor_thread.start()

            if self.on_play_start:
                self.on_play_start(f"批量播放 {len(all_segments)} 个片段，重复 {self.repeat_count} 次")

            return True

        except Exception as e:
            print(f"多视频批量播放失败: {e}")
            if self.on_error:
                self.on_error(f"多视频批量播放失败: {e}")
            return False

    def _create_batch_playlist(self, video_path: str, segments: List[SubtitleSegment]) -> bool:
        """创建批量播放列表，窗口只开关一次，支持字幕时间同步"""
        try:
            import tempfile
            playlist_content = []

            print(f"创建批量播放列表: {len(segments)} 个片段 × {self.repeat_count} 次重复")

            # 检查是否有对应的字幕文件
            original_subtitle_file = self._find_subtitle_file(video_path)
            batch_subtitle_file = None

            if original_subtitle_file:
                # 为批量播放创建合并的字幕文件
                batch_subtitle_file = self._create_batch_subtitle_file(original_subtitle_file, segments)
                # 注册字幕文件
                if batch_subtitle_file:
                    self._register_temp_file(batch_subtitle_file)

            # 创建播放列表：(片段1→片段2→...→片段N) × 重复次数
            current_time_offset = 0.0  # 当前时间偏移

            for repeat_round in range(self.repeat_count):
                print(f"添加第 {repeat_round + 1}/{self.repeat_count} 轮播放")
                for i, segment in enumerate(segments):
                    duration = segment.end_time - segment.start_time
                    playlist_content.append(f"edl://{video_path},{segment.start_time},{duration}")
                    print(f"  片段 {i + 1}: {segment.start_time:.2f}s-{segment.end_time:.2f}s ({segment.text[:20]}...) -> 播放时间: {current_time_offset:.2f}s")
                    current_time_offset += duration

            # 写入临时播放列表文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.m3u', delete=False, encoding='utf-8') as f:
                f.write('\n'.join(playlist_content))
                playlist_file = f.name

            # 注册临时文件
            self._register_temp_file(playlist_file)

            # 设置播放状态
            self.is_playing = True
            self.current_segment = {
                'start': segments[0].start_time,
                'end': segments[-1].end_time,
                'text': f"批量播放 {len(segments)} 个片段",
                'repeat_count': self.repeat_count,
                'current_repeat': 0
            }

            # 获取MPV可执行文件路径
            mpv_path = get_mpv_path()

            # 使用播放列表，一次性播放所有片段和重复 
            # "--osc=yes",  # 显示控制界面
            #f"--geometry={self.window_width}x{self.window_height}",  #自定义MPV播放界面
            cmd = [
                mpv_path,
                f"--playlist={playlist_file}",
                f"--volume={self.volume}",
                
                "--keep-open=no",
                "--force-window=immediate",
                "--idle=no",
                "--input-default-bindings=yes",
                
                "--no-terminal",
                "--sub-auto=fuzzy",  # 自动加载字幕
                "--sub-file-paths=.:subtitles:subs",  # 字幕搜索路径
            ]

            # 批量播放时不显示字幕
            cmd.extend([
                "--sub-auto=no",  # 禁用自动字幕搜索
                "--sub-visibility=no",  # 隐藏字幕
            ])
            print("批量播放模式：已禁用字幕显示")

            # 启动进程
            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            print(f"MPV批量播放进程已启动: PID={self.current_process.pid}")
            print(f"播放列表文件: {playlist_file}")
            print(f"总播放项目: {len(playlist_content)} 个")

            # 启动监控线程
            self.monitor_thread = threading.Thread(target=self._monitor_playback, daemon=True)
            self.monitor_thread.start()

            if self.on_play_start:
                self.on_play_start(f"批量播放 {len(segments)} 个片段，重复 {self.repeat_count} 次")

            return True

        except Exception as e:
            print(f"创建批量播放列表失败: {e}")
            return False








    def stop(self):
        """停止播放"""
        print("停止播放...")

        self.is_playing = False
        self.current_segment = None

        # 终止当前播放进程
        if self.current_process:
            try:
                print(f"终止MPV进程: PID={self.current_process.pid}")
                self.current_process.terminate()

                # 等待进程结束，最多等待2秒
                try:
                    self.current_process.wait(timeout=2)
                    print("MPV进程已正常终止")
                except subprocess.TimeoutExpired:
                    print("MPV进程未及时响应，强制杀死")
                    self.current_process.kill()
                    self.current_process.wait()

            except Exception as e:
                print(f"终止播放进程时出错: {e}")
            finally:
                self.current_process = None

        # 等待监控线程结束
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=1)
            if self.monitor_thread.is_alive():
                print("监控线程未及时结束，但继续")

        print("播放已停止")

    def _find_subtitle_file(self, video_path: str) -> str:
        """查找对应的字幕文件"""
        try:
            from pathlib import Path
            video_file = Path(video_path)
            video_dir = video_file.parent
            video_name = video_file.stem

            print(f"查找字幕文件: 视频={video_name}, 目录={video_dir}")

            # 常见字幕文件扩展名
            subtitle_extensions = ['.srt', '.ass', '.ssa', '.vtt', '.sub', '.idx']

            # 在视频文件同目录下查找同名字幕文件
            for ext in subtitle_extensions:
                subtitle_file = video_dir / f"{video_name}{ext}"
                print(f"检查字幕文件: {subtitle_file}")
                if subtitle_file.exists():
                    print(f"找到字幕文件: {subtitle_file}")
                    return str(subtitle_file)

            # 查找subtitles子目录
            subtitles_dir = video_dir / "subtitles"
            if subtitles_dir.exists():
                print(f"检查subtitles子目录: {subtitles_dir}")
                for ext in subtitle_extensions:
                    subtitle_file = subtitles_dir / f"{video_name}{ext}"
                    print(f"检查字幕文件: {subtitle_file}")
                    if subtitle_file.exists():
                        print(f"找到字幕文件: {subtitle_file}")
                        return str(subtitle_file)

            # 查找任何包含视频名称的字幕文件
            print(f"在目录中查找包含'{video_name}'的字幕文件...")
            for file in video_dir.glob("*.srt"):
                if video_name.lower() in file.stem.lower():
                    print(f"找到相关字幕文件: {file}")
                    return str(file)

            print("未找到字幕文件")
            return None
        except Exception as e:
            print(f"查找字幕文件时出错: {e}")
            return None



    def _parse_srt_subtitles(self, content: str) -> list:
        """解析SRT字幕文件"""
        entries = []
        blocks = content.strip().split('\n\n')

        for block in blocks:
            lines = block.strip().split('\n')
            if len(lines) >= 3:
                try:
                    # 解析时间行
                    time_line = lines[1]
                    times = time_line.split(' --> ')
                    if len(times) == 2:
                        start_time = self._parse_srt_time(times[0])
                        end_time = self._parse_srt_time(times[1])
                        text = '\n'.join(lines[2:])

                        entries.append({
                            'start_time': start_time,
                            'end_time': end_time,
                            'text': text
                        })
                except Exception as e:
                    print(f"解析字幕条目失败: {e}")
                    continue

        return entries

    def _parse_srt_time(self, time_str: str) -> float:
        """解析SRT时间格式 (HH:MM:SS,mmm) 为秒数"""
        try:
            time_str = time_str.strip()
            # 替换逗号为点号
            time_str = time_str.replace(',', '.')

            parts = time_str.split(':')
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = float(parts[2])

            return hours * 3600 + minutes * 60 + seconds
        except Exception:
            return 0.0

    def _format_srt_time(self, seconds: float) -> str:
        """将秒数格式化为SRT时间格式 (HH:MM:SS,mmm)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60

        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}".replace('.', ',')

    def _get_cache_key(self, subtitle_file: str, segment_start: float, segment_end: float) -> str:
        """生成字幕缓存键"""
        key_str = f"{subtitle_file}_{segment_start}_{segment_end}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def _cut_subtitle_for_segment(self, subtitle_file: str, segment: SubtitleSegment) -> Optional[str]:
        """为单个片段切割字幕文件（方案A：预切割储存）"""
        try:
            # 检查缓存
            cache_key = self._get_cache_key(subtitle_file, segment.start_time, segment.end_time)
            cached_file = self.subtitle_cache_dir / f"{cache_key}.srt"

            if cached_file.exists():
                print(f"    使用缓存字幕文件: {cached_file}")
                return str(cached_file)

            # 读取原始字幕文件
            print(f"    读取字幕文件: {subtitle_file}")
            try:
                with open(subtitle_file, 'r', encoding='utf-8') as f:
                    original_content = f.read()
            except UnicodeDecodeError:
                # 尝试其他编码
                try:
                    with open(subtitle_file, 'r', encoding='utf-8-sig') as f:
                        original_content = f.read()
                    print(f"    使用UTF-8-sig编码读取成功")
                except UnicodeDecodeError:
                    with open(subtitle_file, 'r', encoding='gbk') as f:
                        original_content = f.read()
                    print(f"    使用GBK编码读取成功")

            print(f"    字幕文件大小: {len(original_content)} 字符")
            print(f"    字幕文件前100字符: {repr(original_content[:100])}")

            # 解析字幕
            subtitle_entries = self._parse_srt_subtitles(original_content)
            print(f"    解析出 {len(subtitle_entries)} 条字幕")

            # 显示片段时间范围
            print(f"    片段时间范围: {segment.start_time:.2f}s - {segment.end_time:.2f}s")

            # 找到片段对应的字幕
            segment_subtitles = []
            matched_count = 0
            for i, entry in enumerate(subtitle_entries):
                # 字幕与片段有重叠就包含
                if (entry['start_time'] < segment.end_time and
                    entry['end_time'] > segment.start_time):
                    matched_count += 1
                    print(f"      匹配字幕 {i+1}: {entry['start_time']:.2f}s-{entry['end_time']:.2f}s | {entry['text'][:30]}...")

                    # 裁剪字幕时间到片段范围内
                    clipped_start = max(entry['start_time'], segment.start_time)
                    clipped_end = min(entry['end_time'], segment.end_time)

                    if clipped_end - clipped_start > 0.1:
                        # 重新计算时间：相对于片段开始时间
                        new_start = clipped_start - segment.start_time
                        new_end = clipped_end - segment.start_time

                        segment_subtitles.append({
                            'start_time': new_start,
                            'end_time': new_end,
                            'text': entry['text']
                        })
                        print(f"        -> 切割后: {new_start:.2f}s-{new_end:.2f}s")
                    else:
                        print(f"        -> 跳过: 时长太短 ({clipped_end - clipped_start:.2f}s)")

            print(f"    匹配到 {matched_count} 条字幕，有效 {len(segment_subtitles)} 条")

            if not segment_subtitles:
                return None

            # 生成切割后的字幕文件
            cut_content = []
            for i, subtitle in enumerate(segment_subtitles, 1):
                cut_content.append(str(i))
                cut_content.append(f"{self._format_srt_time(subtitle['start_time'])} --> {self._format_srt_time(subtitle['end_time'])}")
                cut_content.append(subtitle['text'])
                cut_content.append("")  # 空行分隔

            # 写入缓存文件
            with open(cached_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(cut_content))

            print(f"切割字幕: {segment.start_time:.2f}s-{segment.end_time:.2f}s -> {len(segment_subtitles)} 条 -> {cached_file.name}")
            return str(cached_file)

        except Exception as e:
            print(f"切割字幕文件失败: {e}")
            return None

    def _dynamic_preprocess_subtitles(self, segments: List[SubtitleSegment]) -> Dict[str, List[Dict]]:
        """动态预处理字幕数据（不切割文件，只在内存中处理）"""
        print(f"动态预处理 {len(segments)} 个片段的字幕...")

        # 按视频文件分组
        video_groups = {}
        for segment in segments:
            video_path = segment.video_file_path if hasattr(segment, 'video_file_path') else None
            if not video_path:
                # 从数据库获取视频路径
                project = db_manager.get_project(segment.project_id)
                if project:
                    video_path = project.video_path

            if video_path:
                if video_path not in video_groups:
                    video_groups[video_path] = []
                video_groups[video_path].append(segment)

        segment_subtitles = {}

        # 为每个视频文件预加载字幕数据到内存
        for video_path, video_segments in video_groups.items():
            subtitle_file = self._find_subtitle_file(video_path)
            if not subtitle_file:
                print(f"未找到字幕文件: {video_path}")
                continue

            print(f"预加载视频字幕: {Path(video_path).name} ({len(video_segments)} 个片段)")

            # 读取并解析整个字幕文件到内存
            subtitle_entries = self._parse_subtitle_file(subtitle_file)
            if not subtitle_entries:
                print(f"  字幕文件解析失败，跳过")
                continue

            print(f"  解析出 {len(subtitle_entries)} 条字幕")

            # 为每个片段精准匹配对应的字幕条目
            for segment in video_segments:
                segment_key = f"{segment.project_id}_{segment.id}"

                # 精准找到片段时间范围内的字幕
                matching_subtitles = []
                for entry in subtitle_entries:
                    # 更精确的重叠检查：字幕必须在片段时间范围内
                    if (entry['start_time'] >= segment.start_time and
                        entry['start_time'] < segment.end_time) or \
                       (entry['end_time'] > segment.start_time and
                        entry['end_time'] <= segment.end_time) or \
                       (entry['start_time'] <= segment.start_time and
                        entry['end_time'] >= segment.end_time):

                        # 精确调整字幕时间：确保字幕时间完全在片段范围内
                        # 计算字幕在片段中的相对时间
                        relative_start = max(0, entry['start_time'] - segment.start_time)
                        relative_end = min(segment.end_time - segment.start_time,
                                         entry['end_time'] - segment.start_time)

                        # 只有当调整后的时间有效时才添加
                        if relative_end > relative_start and relative_start >= 0:
                            adjusted_entry = {
                                'start_time': relative_start,
                                'end_time': relative_end,
                                'text': entry['text'],
                                'original_start': entry['start_time'],
                                'original_end': entry['end_time']
                            }
                            matching_subtitles.append(adjusted_entry)

                if matching_subtitles:
                    segment_subtitles[segment_key] = matching_subtitles
                    print(f"  片段 {segment.id} ({segment.start_time:.2f}s-{segment.end_time:.2f}s): 精准匹配 {len(matching_subtitles)} 条字幕")
                    for i, sub in enumerate(matching_subtitles):
                        print(f"    字幕{i+1}: {sub['start_time']:.2f}s-{sub['end_time']:.2f}s (原始: {sub['original_start']:.2f}s-{sub['original_end']:.2f}s)")

        print(f"动态预处理完成: {len(segment_subtitles)} 个片段有字幕")
        return segment_subtitles

    def _simple_precise_subtitles(self, segments: List[SubtitleSegment]) -> Dict[str, str]:
        """最简单精准的字幕方案：直接使用原始字幕文件路径"""
        print(f"使用最简单精准字幕方案，共 {len(segments)} 个片段")

        segment_subtitles = {}

        # 按视频文件分组
        video_groups = {}
        for segment in segments:
            video_path = segment.video_file_path if hasattr(segment, 'video_file_path') else None
            if not video_path:
                project = db_manager.get_project(segment.project_id)
                if project:
                    video_path = project.video_path

            if video_path:
                if video_path not in video_groups:
                    video_groups[video_path] = []
                video_groups[video_path].append(segment)

        # 为每个视频文件找到字幕文件
        for video_path, video_segments in video_groups.items():
            subtitle_file = self._find_subtitle_file(video_path)
            if subtitle_file:
                print(f"找到字幕文件: {Path(subtitle_file).name} (对应 {len(video_segments)} 个片段)")
                for segment in video_segments:
                    segment_key = f"{segment.project_id}_{segment.id}"
                    segment_subtitles[segment_key] = subtitle_file
            else:
                print(f"未找到字幕文件: {Path(video_path).name}")

        print(f"简单精准方案完成: {len(segment_subtitles)} 个片段有字幕")
        return segment_subtitles

    def _create_batch_subtitle_file(self, original_subtitle_file: str, segments: List[SubtitleSegment]) -> Optional[str]:
        """
        【终极方案】为批量播放创建合并的字幕文件 - 使用EDL时间映射

        核心原理：
        1. EDL播放列表让视频按连续时间轴播放（0s开始）
        2. 字幕文件也必须使用相同的连续时间轴
        3. 关键：确保字幕时间与EDL播放时间完全对应
        """
        try:
            print(f"\n========== 【终极方案】创建批量字幕文件 ==========")
            print(f"片段数: {len(segments)}, 重复次数: {self.repeat_count}")

            # 读取原始字幕文件
            subtitle_entries = self._parse_subtitle_file(original_subtitle_file)
            if not subtitle_entries:
                print("无法解析原始字幕文件")
                return None

            print(f"解析出 {len(subtitle_entries)} 条字幕")

            batch_content = []
            entry_index = 1

            # 为每轮重复创建字幕
            for repeat_round in range(self.repeat_count):
                edl_playback_time = 0.0  # EDL播放时间轴（从0开始）

                print(f"\n--- 处理第 {repeat_round + 1}/{self.repeat_count} 轮 ---")

                for seg_idx, segment in enumerate(segments):
                    # 过滤出片段时间范围内的字幕
                    matching_subs = self._filter_subtitles_in_segment(
                        subtitle_entries, segment.start_time, segment.end_time
                    )

                    print(f"  [片段{seg_idx+1}] {segment.start_time:.2f}s-{segment.end_time:.2f}s")
                    print(f"    → EDL播放: {edl_playback_time:.2f}s开始")
                    print(f"    → 匹配字幕: {len(matching_subs)}条")

                    # 转换字幕时间到EDL播放时间轴
                    for sub_entry in matching_subs:
                        # 步骤1：裁剪到片段范围内
                        clipped_start = max(sub_entry['start_time'], segment.start_time)
                        clipped_end = min(sub_entry['end_time'], segment.end_time)

                        # 步骤2：转换为相对于片段开始的时间
                        relative_start = clipped_start - segment.start_time
                        relative_end = clipped_end - segment.start_time

                        # 步骤3：映射到EDL播放时间轴
                        edl_sub_start = edl_playback_time + relative_start
                        edl_sub_end = edl_playback_time + relative_end

                        # 添加到批量字幕文件
                        batch_content.append(str(entry_index))
                        batch_content.append(
                            f"{self._format_srt_time(edl_sub_start)} --> "
                            f"{self._format_srt_time(edl_sub_end)}"
                        )
                        batch_content.append(sub_entry['text'])
                        batch_content.append("")  # 空行分隔

                        if entry_index <= 3 or entry_index % 10 == 0:
                            print(f"      字幕{entry_index}: "
                                  f"{self._format_srt_time(edl_sub_start)} → "
                                  f"{self._format_srt_time(edl_sub_end)}")

                        entry_index += 1

                    # 更新EDL播放时间
                    segment_duration = segment.end_time - segment.start_time
                    edl_playback_time += segment_duration

            if not batch_content:
                print("\n[错误] 没有生成任何字幕内容")
                return None

            # 写入临时文件
            batch_file = tempfile.NamedTemporaryFile(
                mode='w', suffix='.srt', delete=False, encoding='utf-8'
            )
            batch_file.write('\n'.join(batch_content))
            batch_file.close()

            print(f"\n========== 字幕文件创建成功 ==========")
            print(f"文件路径: {batch_file.name}")
            print(f"字幕条目数: {entry_index - 1}")
            print(f"总播放时长: {edl_playback_time:.2f}s")

            # 验证生成的文件
            self._verify_subtitle_file(batch_file.name)

            return batch_file.name

        except Exception as e:
            print(f"\n[致命错误] 创建批量字幕失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _create_simple_precise_subtitle_file(self, segments: List[SubtitleSegment], segment_subtitles: Dict[str, str]) -> Optional[str]:
        """
        【终极方案】创建批量播放字幕文件 - 使用EDL时间映射

        核心原理：
        1. EDL播放列表让视频按连续时间轴播放（0s开始）
        2. 字幕文件也必须使用相同的连续时间轴
        3. 关键：确保字幕时间与EDL播放时间完全对应

        时间映射示例：
        片段1: 视频10s-15s → EDL播放0s-5s  → 字幕0s-5s
        片段2: 视频30s-35s → EDL播放5s-10s → 字幕5s-10s
        片段3: 视频50s-55s → EDL播放10s-15s → 字幕10s-15s
        """
        try:
            print(f"\n========== 【终极方案】创建批量字幕文件 ==========")
            print(f"片段数: {len(segments)}, 重复次数: {self.repeat_count}")

            batch_content = []
            entry_index = 1

            # 【关键修复】将 edl_playback_time 移到循环外，确保连续累加
            # 这样重复播放时，字幕时间也会连续增长，与播放时间保持一致
            edl_playback_time = 0.0  # EDL播放时间轴（从0开始，连续累加）

            # 为每轮重复创建字幕
            for repeat_round in range(self.repeat_count):
                print(f"\n--- 处理第 {repeat_round + 1}/{self.repeat_count} 轮（当前EDL时间: {edl_playback_time:.3f}s）---")

                for seg_idx, segment in enumerate(segments):
                    segment_key = f"{segment.project_id}_{segment.id}"
                    subtitle_file = segment_subtitles.get(segment_key)

                    # 计算片段持续时间（保持完整精度）
                    segment_duration = segment.end_time - segment.start_time

                    if not subtitle_file:
                        print(f"  [片段{seg_idx+1}] 无字幕，跳过")
                        print(f"    → 片段时长: {segment_duration:.3f}s，EDL时间前进: {edl_playback_time:.3f}s → {edl_playback_time + segment_duration:.3f}s")
                        edl_playback_time += segment_duration
                        continue

                    # 读取原始字幕
                    subtitle_entries = self._parse_subtitle_file(subtitle_file)
                    if not subtitle_entries:
                        print(f"  [片段{seg_idx+1}] 字幕解析失败")
                        print(f"    → 片段时长: {segment_duration:.3f}s，EDL时间前进: {edl_playback_time:.3f}s → {edl_playback_time + segment_duration:.3f}s")
                        edl_playback_time += segment_duration
                        continue

                    print(f"  [片段{seg_idx+1}] 视频原始时间: {segment.start_time:.3f}s-{segment.end_time:.3f}s （时长: {segment_duration:.3f}s）")
                    print(f"    → 原始字幕文件: {subtitle_file}")
                    print(f"    → 字幕总数: {len(subtitle_entries)}条")
                    print(f"    → EDL播放开始时间: {edl_playback_time:.3f}s")

                    # 过滤出片段时间范围内的字幕
                    matching_subs = self._filter_subtitles_in_segment(
                        subtitle_entries, segment.start_time, segment.end_time
                    )

                    print(f"    → 匹配字幕: {len(matching_subs)}条")
                    if len(matching_subs) == 0:
                        print(f"    ⚠️ 警告：未找到匹配字幕！")
                        print(f"    → 显示前5条原始字幕时间范围：")
                        for i, sub in enumerate(subtitle_entries[:5]):
                            print(f"       字幕{i+1}: {sub['start_time']:.3f}s-{sub['end_time']:.3f}s")
                    else:
                        print(f"    → 匹配字幕详情（原始视频时间）：")
                        for i, sub in enumerate(matching_subs):
                            print(f"       匹配{i+1}: [原始]{sub['start_time']:.3f}s-{sub['end_time']:.3f}s | {sub['text'][:50]}...")

                    # 转换字幕时间到EDL播放时间轴
                    for sub_idx, sub_entry in enumerate(matching_subs, 1):
                        # 步骤1：裁剪到片段范围内
                        clipped_start = max(sub_entry['start_time'], segment.start_time)
                        clipped_end = min(sub_entry['end_time'], segment.end_time)

                        # 步骤2：转换为相对于片段开始的时间
                        relative_start = clipped_start - segment.start_time
                        relative_end = clipped_end - segment.start_time

                        # 步骤3：映射到EDL播放时间轴
                        edl_sub_start = edl_playback_time + relative_start
                        edl_sub_end = edl_playback_time + relative_end

                        # 【调试日志】显示完整的时间转换过程
                        if sub_idx <= 2:  # 只显示前2条字幕的详细转换过程
                            print(f"      → 字幕{sub_idx}转换过程:")
                            print(f"        步骤1-裁剪: [{sub_entry['start_time']:.3f}s, {sub_entry['end_time']:.3f}s] → [{clipped_start:.3f}s, {clipped_end:.3f}s]")
                            print(f"        步骤2-相对: [{clipped_start:.3f}s, {clipped_end:.3f}s] - {segment.start_time:.3f}s → [{relative_start:.3f}s, {relative_end:.3f}s]")
                            print(f"        步骤3-EDL: [{relative_start:.3f}s, {relative_end:.3f}s] + {edl_playback_time:.3f}s → [{edl_sub_start:.3f}s, {edl_sub_end:.3f}s]")
                            print(f"        最终SRT格式: {self._format_srt_time(edl_sub_start)} --> {self._format_srt_time(edl_sub_end)}")

                        # 添加到批量字幕文件
                        batch_content.append(str(entry_index))
                        batch_content.append(
                            f"{self._format_srt_time(edl_sub_start)} --> "
                            f"{self._format_srt_time(edl_sub_end)}"
                        )
                        batch_content.append(sub_entry['text'])
                        batch_content.append("")  # 空行分隔

                        entry_index += 1

                    # 【关键】更新EDL播放时间，为下一个片段做准备
                    edl_playback_time_before = edl_playback_time
                    edl_playback_time += segment_duration
                    print(f"    → EDL时间推进: {edl_playback_time_before:.3f}s + {segment_duration:.3f}s = {edl_playback_time:.3f}s")

            if not batch_content:
                print("\n[错误] 没有生成任何字幕内容")
                return None

            # 写入临时文件
            batch_file = tempfile.NamedTemporaryFile(
                mode='w', suffix='.srt', delete=False, encoding='utf-8'
            )
            batch_file.write('\n'.join(batch_content))
            batch_file.close()

            print(f"\n========== 字幕文件创建成功 ==========")
            print(f"文件路径: {batch_file.name}")
            print(f"字幕条目数: {entry_index - 1}")
            print(f"总播放时长: {edl_playback_time:.3f}s")
            print(f"【关键验证】EDL播放时间轴范围: 0.000s ~ {edl_playback_time:.3f}s")

            # 验证生成的文件
            self._verify_subtitle_file(batch_file.name)

            return batch_file.name

        except Exception as e:
            print(f"\n[致命错误] 创建批量字幕失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _filter_subtitles_in_segment(self, subtitle_entries: List[Dict],
                                     seg_start: float, seg_end: float) -> List[Dict]:
        """过滤出片段时间范围内的字幕（更精准的算法）"""
        matching = []
        for entry in subtitle_entries:
            # 字幕与片段有任何时间重叠即包含
            if (entry['start_time'] < seg_end and entry['end_time'] > seg_start):
                matching.append(entry)
        return matching

    def _verify_subtitle_file(self, subtitle_file: str):
        """验证生成的字幕文件"""
        try:
            with open(subtitle_file, 'r', encoding='utf-8') as f:
                content = f.read()

            lines = content.split('\n')[:30]
            print(f"\n--- 字幕文件预览（前30行）---")
            for line in lines:
                if line.strip():
                    print(f"  {line}")
        except Exception as e:
            print(f"  [警告] 无法验证字幕文件: {e}")

    def _parse_subtitle_file(self, subtitle_file: str) -> List[Dict]:
        """解析字幕文件到内存"""
        try:
            with open(subtitle_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # 移除BOM
            if content.startswith('\ufeff'):
                content = content[1:]

            entries = []
            blocks = content.strip().split('\n\n')

            for block in blocks:
                lines = block.strip().split('\n')
                if len(lines) >= 3:
                    try:
                        # 解析时间行
                        time_line = lines[1]
                        if ' --> ' in time_line:
                            start_str, end_str = time_line.split(' --> ')
                            start_time = self._parse_srt_time(start_str.strip())
                            end_time = self._parse_srt_time(end_str.strip())

                            # 合并文本行
                            text = '\n'.join(lines[2:])

                            entries.append({
                                'start_time': start_time,
                                'end_time': end_time,
                                'text': text
                            })
                    except Exception as e:
                        print(f"解析字幕条目失败: {e}")
                        continue

            return entries

        except Exception as e:
            print(f"读取字幕文件失败: {e}")
            return []

    def _create_dynamic_batch_subtitle_file(self, segments: List[SubtitleSegment], segment_subtitles: Dict[str, List[Dict]]) -> Optional[str]:
        """动态创建批量播放字幕文件（内存处理版本）"""
        try:
            import tempfile

            print(f"动态创建批量字幕文件，共 {len(segments)} 个片段，重复 {self.repeat_count} 次")

            # 创建合并的字幕内容
            batch_content = []
            entry_index = 1
            current_time_offset = 0.0

            # 为每轮重复创建字幕条目
            for repeat_round in range(self.repeat_count):
                print(f"处理第 {repeat_round + 1}/{self.repeat_count} 轮字幕")

                for segment_idx, segment in enumerate(segments):
                    segment_key = f"{segment.project_id}_{segment.id}"

                    # 获取预处理的字幕数据
                    subtitle_entries = segment_subtitles.get(segment_key)
                    if not subtitle_entries:
                        print(f"    片段 {segment_idx + 1}: 无字幕数据")
                        segment_duration = segment.end_time - segment.start_time
                        current_time_offset += segment_duration
                        continue

                    print(f"    片段 {segment_idx + 1} ({segment.start_time:.2f}s-{segment.end_time:.2f}s): 找到 {len(subtitle_entries)} 条字幕，时间偏移: {current_time_offset:.2f}s")

                    # [TOOL] 动态处理：使用连续时间轴匹配EDL播放列表
                    for entry in subtitle_entries:
                        # 字幕时间已经相对于片段开始调整过了（0开始）
                        # 需要加上当前时间偏移，形成连续时间轴
                        continuous_start = entry['start_time'] + current_time_offset
                        continuous_end = entry['end_time'] + current_time_offset

                        batch_content.append(str(entry_index))
                        batch_content.append(f"{self._format_srt_time(continuous_start)} --> {self._format_srt_time(continuous_end)}")
                        batch_content.append(entry['text'])
                        batch_content.append("")  # 空行分隔
                        entry_index += 1

                        print(f"      字幕 {entry_index-1}: 连续时间 {self._format_srt_time(continuous_start)} --> {self._format_srt_time(continuous_end)} | {entry['text'][:30]}...")

                    # 更新时间偏移（加上这个片段的实际时长）
                    segment_duration = segment.end_time - segment.start_time
                    current_time_offset += segment_duration

            if not batch_content:
                print("[ERROR] 没有找到任何字幕内容")
                return None

            # 写入临时字幕文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False, encoding='utf-8') as f:
                f.write('\n'.join(batch_content))
                batch_subtitle_file = f.name

            print(f"[OK] 批量播放字幕文件已创建: {batch_subtitle_file}")
            print(f"[OK] 包含 {entry_index - 1} 条字幕条目，总时长: {current_time_offset:.2f}s")

            # 验证生成的字幕文件
            with open(batch_subtitle_file, 'r', encoding='utf-8') as f:
                verification_content = f.read()
                print(f"[OK] 字幕文件大小: {len(verification_content)} 字符")

                # 显示前几条字幕用于调试
                lines = verification_content.split('\n')[:20]
                print("[OK] 字幕文件前几行内容:")
                for i, line in enumerate(lines, 1):
                    if line.strip():
                        print(f"    {i:2d}: {line}")

            return batch_subtitle_file

        except Exception as e:
            print(f"[ERROR] 创建批量字幕文件失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def pause(self):
        """暂停播放（进程模式不支持暂停）"""
        print("进程模式不支持暂停功能")

    def cleanup(self):
        """清理资源"""
        print("清理MPV播放器资源...")

        # 停止播放
        self.stop()

        # 清理所有临时文件
        self._cleanup_temp_files()

        print("清理完成")

    def _register_temp_file(self, file_path: str):
        """注册临时文件，用于后续清理"""
        if file_path and file_path not in self.temp_files:
            self.temp_files.append(file_path)
            print(f"[临时文件] 已注册: {file_path}")

    def _cleanup_temp_files(self):
        """清理所有临时文件（播放列表和字幕文件）"""
        if not self.temp_files:
            return

        print(f"[清理] 开始清理 {len(self.temp_files)} 个临时文件...")
        cleaned_count = 0
        failed_files = []

        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    cleaned_count += 1
                    print(f"[清理] 已删除: {temp_file}")
            except PermissionError:
                # 文件可能仍在被使用，记录但不报错
                print(f"[清理] 文件正在使用，稍后重试: {temp_file}")
                failed_files.append(temp_file)
            except Exception as e:
                print(f"[清理] 删除失败: {temp_file}, 错误: {e}")
                failed_files.append(temp_file)

        # 只清除成功删除的文件，保留失败的以便下次重试
        self.temp_files = failed_files
        print(f"[清理] 完成，成功删除 {cleaned_count} 个文件，{len(failed_files)} 个文件稍后重试")

    def __del__(self):
        """析构函数 - 确保播放器被正确清理"""
        try:
            self.cleanup()
        except:
            pass

