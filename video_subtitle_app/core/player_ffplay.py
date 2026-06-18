#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FFplay 播放器实现
基于 FFmpeg 的 ffplay 工具
"""

import os
import subprocess
import threading
import time
import tempfile

from typing import List, Optional
from pathlib import Path

from database.models import SubtitleSegment
from config.settings import app_config
from core.preloader import preloader
from core.player_base import PlayerBase


class FFplayPlayer(PlayerBase):
    """基于 FFplay 的播放器实现"""

    def __init__(self):
        """初始化 FFplay 播放器"""
        super().__init__()
        
        self.current_process = None
        self.volume = app_config.get('player.volume', 80)
        self.auto_play = app_config.get('player.auto_play', False)
        self.loop = app_config.get('player.loop', False)
        self.repeat_count = app_config.get('player.repeat_count', 1)

        # 窗口参数
        self.window_width = app_config.get('player.window_width', 800)
        self.window_height = app_config.get('player.window_height', 600)

    def play_segment(self, segment: SubtitleSegment) -> bool:
        """播放单个片段（支持重复播放）"""
        if not segment:
            return False

        # 优先播放视频，如果没有则播放音频
        file_to_play = segment.video_file or segment.audio_file

        if not file_to_play or not os.path.exists(file_to_play):
            if self.on_error:
                self.on_error(f"文件不存在：{file_to_play}")
            return False

        # 触发预加载（后台提取缩略图/音频头，加速下次播放）
        preloader.preload_segment(file_to_play)

        # 如果重复次数 > 1，创建重复播放列表
        if self.repeat_count > 1:
            return self._play_file_repeated(file_to_play, self.repeat_count)
        else:
            return self._play_file(file_to_play)

    def play_segments(self, segments: List[SubtitleSegment], continuous: bool = True) -> bool:
        """播放多个片段"""
        if not segments:
            return False

        if continuous:
            # 使用 concat 一次性播放，避免频繁开关窗口
            self.is_playing = True
            threading.Thread(target=self._play_segments_concat, args=(segments,), daemon=True).start()
        else:
            # 只播放第一个
            self.play_segment(segments[0])

        return True

    def _play_segments_concat(self, segments: List[SubtitleSegment]):
        """使用 ffplay concat 一次性连续播放多个片段（单进程，支持重复播放）"""
        list_path = None
        try:
            # 选择同类型的文件：优先视频，没有视频再用音频
            video_files = [s.video_file for s in segments if s.video_file and os.path.exists(s.video_file)]
            audio_files = [s.audio_file for s in segments if s.audio_file and os.path.exists(s.audio_file)]
            files = video_files if video_files else audio_files
            if not files:
                if self.on_error:
                    self.on_error("没有可播放的文件")
                return

            # 生成 concat 列表文件（支持重复播放）
            with tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8") as f:
                list_path = f.name
                # 根据 repeat_count 重复写入文件列表
                for _ in range(self.repeat_count):
                    for p in files:
                        escaped = os.path.abspath(p).replace("\\", "\\\\").replace("'", "\\'")
                        f.write("file '{}'\n".format(escaped))

            # 先使用 ffmpeg concat 生成临时合并文件，避免实时拼接导致的音调/速度变化
            has_video = len(video_files) > 0
            merged_path = tempfile.NamedTemporaryFile(delete=False, suffix=(".mp4" if has_video else ".mp3")).name
            ff_cmd = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path,
                "-c", "copy", merged_path
            ]
            try:
                subprocess.run(ff_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
            except Exception:
                pass

            # 播放合并后的单一文件，保持原始音色
            title = f"连续播放 - 共{len(files)}段"
            if self.repeat_count > 1:
                title += f" × {self.repeat_count}次"
            
            cmd = [
                "ffplay",
                "-autoexit",
                "-volume", str(self.volume),
                "-window_title", title,
                "-x", str(self.window_width),
                "-y", str(self.window_height),
                "-fast"
            ]
            cmd.append(merged_path)

            if self.on_play_start:
                self.on_play_start(f"连续播放 {len(files)} 个片段")

            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            self.current_process.wait()

            if self.on_play_end:
                self.on_play_end("连续播放完成")

            # 清理临时文件
            try:
                os.unlink(list_path)
                os.unlink(merged_path)
            except:
                pass

        except Exception as e:
            if self.on_error:
                self.on_error(f"播放失败：{e}")
        finally:
            if list_path and os.path.exists(list_path):
                try:
                    os.unlink(list_path)
                except:
                    pass

            self.is_playing = False

    def _play_file_repeated(self, file_path: str, repeat_count: int) -> bool:
        """重复播放文件（使用 ffmpeg concat）"""
        try:
            # 创建临时文件列表
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                list_file = f.name
                for _ in range(repeat_count):
                    # 使用绝对路径，并转义特殊字符
                    abs_path = os.path.abspath(file_path).replace('\\', '\\\\').replace("'", "\\'")
                    f.write(f"file '{abs_path}'\n")

            # 使用 ffmpeg concat 合并后播放
            self.is_playing = True
            threading.Thread(target=self._play_concat_list, args=(list_file, f"重复 {repeat_count} 次"), daemon=True).start()
            return True
        except Exception as e:
            if self.on_error:
                self.on_error(f"重复播放失败：{e}")
            return False

    def _play_concat_list(self, list_file: str, title: str = "播放"):
        """播放 concat 列表文件"""
        merged_path = None
        try:
            # 先使用 ffmpeg concat 生成临时合并文件
            # 判断是否有视频（通过读取列表文件的第一个文件）
            has_video = False
            with open(list_file, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
                if first_line.startswith("file '"):
                    first_file = first_line[6:-1].replace('\\\\', '\\').replace("\\'", "'")
                    if os.path.exists(first_file):
                        ext = os.path.splitext(first_file)[1].lower()
                        has_video = ext in ['.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv']

            merged_path = tempfile.NamedTemporaryFile(delete=False, suffix=(".mp4" if has_video else ".mp3")).name
            ff_cmd = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
                "-c", "copy", merged_path
            ]
            subprocess.run(ff_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          creationflags=subprocess.CREATE_NO_WINDOW, timeout=300)

            # 播放合并后的文件
            cmd = [
                "ffplay",
                "-autoexit",
                "-volume", str(self.volume),
                "-window_title", f"播放器 - {title}",
                "-x", str(self.window_width),
                "-y", str(self.window_height),
            ]
            cmd.append(merged_path)

            if self.on_play_start:
                self.on_play_start(title)

            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            self.current_process.wait()

            if self.on_play_end:
                self.on_play_end("播放完成")

        except Exception as e:
            if self.on_error:
                self.on_error(f"播放失败：{e}")
        finally:
            # 清理临时文件
            try:
                if list_file and os.path.exists(list_file):
                    os.unlink(list_file)
                if merged_path and os.path.exists(merged_path):
                    os.unlink(merged_path)
            except:
                pass
            
            self.is_playing = False

    def _play_file(self, file_path: str) -> bool:
        """播放单个文件"""
        try:
            cmd = [
                "ffplay",
                "-autoexit",
                "-volume", str(self.volume),
                "-window_title", f"播放器 - {Path(file_path).stem}",
                "-x", str(self.window_width),
                "-y", str(self.window_height),
            ]
            cmd.append(file_path)

            if self.on_play_start:
                self.on_play_start(Path(file_path).stem)

            self.is_playing = True
            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            # 在后台线程中等待播放完成
            def wait_for_completion():
                self.current_process.wait()
                self.is_playing = False
                if self.on_play_end:
                    self.on_play_end("播放完成")
            
            threading.Thread(target=wait_for_completion, daemon=True).start()
            return True

        except Exception as e:
            self.is_playing = False
            if self.on_error:
                self.on_error(f"播放失败：{e}")
            return False

    def stop(self) -> None:
        """停止播放"""
        if self.current_process:
            try:
                self.current_process.terminate()
                self.current_process.wait(timeout=2)
            except:
                try:
                    self.current_process.kill()
                except:
                    pass
            finally:
                self.current_process = None
        
        self.is_playing = False

    @staticmethod
    def is_available() -> bool:
        """检查 FFplay 是否可用"""
        try:
            result = subprocess.run(
                ['ffplay', '-version'],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=5
            )
            return result.returncode == 0
        except:
            return False

    @staticmethod
    def get_name() -> str:
        """获取播放器名称"""
        return "FFplay"

    @staticmethod
    def get_description() -> str:
        """获取播放器描述"""
        return "FFplay（默认，基于 FFmpeg）"

