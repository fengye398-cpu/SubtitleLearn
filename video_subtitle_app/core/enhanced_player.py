#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增强播放器
支持基于原视频的精确时间跳转，集成test3.py的精确跳转逻辑
"""

import os
import subprocess
import threading
import time
import tempfile
from pathlib import Path
from typing import List, Optional, Callable, Dict, Any

from database.models import SubtitleSegment
from config.settings import app_config
from core.keyframe_analyzer import keyframe_analyzer
from core.player_base import PlayerBase


class EnhancedPlayer(PlayerBase):
    """增强播放器 - 支持精确跳转"""
    
    def __init__(self):
        super().__init__()
        self.current_process = None
        self.current_video_path = None
        self.current_time = 0.0
        self.duration = 0.0

        # 播放设置
        self.volume = app_config.get('player.volume', 80)
        self.repeat_count = app_config.get('player.repeat_count', 1)
        self.seek_mode = app_config.get('player.seek_mode', 'smart')  # smart, precise, keyframe

        # 窗口设置
        self.window_width = app_config.get('player.window_width', 800)
        self.window_height = app_config.get('player.window_height', 600)

        # 跳转历史记录
        self.seek_history = []
        
    def set_callbacks(self, on_play_start: Callable = None,
                     on_play_end: Callable = None, on_error: Callable = None):
        """设置回调函数"""
        self.on_play_start = on_play_start
        self.on_play_end = on_play_end
        self.on_error = on_error
        
    def set_repeat_count(self, count: int):
        """设置重复次数"""
        self.repeat_count = max(1, min(99, count))
        
    def set_seek_mode(self, mode: str):
        """设置跳转模式: smart, precise, keyframe"""
        if mode in ['smart', 'precise', 'keyframe']:
            self.seek_mode = mode
            app_config.set('player.seek_mode', mode)
            
    def play_segment(self, segment: SubtitleSegment):
        """播放单个片段（使用精确跳转）"""
        if not segment:
            return False
            
        # 获取原视频路径
        from database.manager import db_manager
        project = db_manager.get_project(segment.project_id)
        if not project or not project.video_path or not os.path.exists(project.video_path):
            if self.on_error:
                self.on_error(f"原视频文件不存在：{project.video_path if project else 'Unknown'}")
            return False

        video_path = project.video_path
        start_time = segment.start_time
        end_time = segment.end_time
        
        # 如果重复次数 > 1，创建重复播放
        if self.repeat_count > 1:
            return self._play_segment_repeated(video_path, start_time, end_time, segment.text)
        else:
            return self._play_segment_once(video_path, start_time, end_time, segment.text)
            
    def play_segments(self, segments: List[SubtitleSegment], continuous: bool = True):
        """播放多个片段"""
        if not segments:
            return False
            
        if continuous:
            # 连续播放多个片段
            self.is_playing = True
            threading.Thread(target=self._play_segments_continuous, args=(segments,), daemon=True).start()
        else:
            # 只播放第一个
            self.play_segment(segments[0])
            
        return True
        
    def _play_segment_once(self, video_path: str, start_time: float, end_time: float, title: str = "") -> bool:
        """播放单个片段一次"""
        try:
            self.stop()  # 停止当前播放
            self.current_video_path = video_path
            
            # 使用增强跳转确定实际开始时间
            actual_start_time = self._enhanced_seek_time(video_path, start_time)
            duration = end_time - start_time
            
            # 构建ffplay命令 - 使用精确跳转参数
            cmd = [
                "ffplay",
                "-autoexit",
                "-volume", str(self.volume),
                "-window_title", f"播放器 - {title[:30]}..." if title else "播放器",
                "-x", str(self.window_width),
                "-y", str(self.window_height),
                "-accurate_seek",  # 启用精确跳转
                "-ss", str(actual_start_time),  # 开始时间
                "-t", str(duration),  # 播放时长
                "-seek_timestamp", "1",  # 使用时间戳跳转
                "-framedrop"
            ]
            cmd.append(video_path)
            
            # 启动播放进程
            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            self.is_playing = True
            
            if self.on_play_start:
                self.on_play_start(f"开始播放：{title}")
                
            # 监控播放状态
            threading.Thread(target=self._monitor_playback, daemon=True).start()
            
            return True
            
        except Exception as e:
            if self.on_error:
                self.on_error(f"播放失败：{e}")
            return False
            
    def _play_segment_repeated(self, video_path: str, start_time: float, end_time: float, title: str = "") -> bool:
        """重复播放片段"""
        try:
            self.stop()
            self.current_video_path = video_path
            
            # 使用增强跳转确定实际开始时间
            actual_start_time = self._enhanced_seek_time(video_path, start_time)
            duration = end_time - start_time
            
            # 创建临时播放列表文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                list_file = f.name
                for _ in range(self.repeat_count):
                    abs_path = os.path.abspath(video_path).replace('\\', '\\\\').replace("'", "\\'")
                    f.write(f"file '{abs_path}'\n")
                    f.write(f"inpoint {actual_start_time}\n")
                    f.write(f"outpoint {end_time}\n")
                    
            # 使用ffplay播放列表 - 使用精确跳转参数
            cmd = [
                "ffplay",
                "-autoexit",
                "-volume", str(self.volume),
                "-window_title", f"重复播放 {self.repeat_count} 次 - {title[:20]}..." if title else f"重复播放 {self.repeat_count} 次",
                "-x", str(self.window_width),
                "-y", str(self.window_height),
                "-accurate_seek",  # 启用精确跳转
                "-seek_timestamp", "1",  # 使用时间戳跳转
                "-f", "concat",
                "-safe", "0",
                "-framedrop"
            ]
            cmd.append(list_file)
            
            # 启动播放进程
            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            self.is_playing = True
            
            if self.on_play_start:
                self.on_play_start(f"开始重复播放：{title}")
                
            # 监控播放状态，播放完成后清理临时文件
            threading.Thread(target=self._monitor_playback_with_cleanup, args=(list_file,), daemon=True).start()
            
            return True
            
        except Exception as e:
            if self.on_error:
                self.on_error(f"重复播放失败：{e}")
            return False
            
    def _play_segments_continuous(self, segments: List[SubtitleSegment]):
        """连续播放多个片段"""
        try:
            if not segments:
                return
                
            # 检查所有片段是否来自同一个视频
            from database.manager import db_manager
            video_paths = set()
            for segment in segments:
                project = db_manager.get_project(segment.project_id)
                if project and project.video_path:
                    video_paths.add(project.video_path)

            if len(video_paths) != 1:
                if self.on_error:
                    self.on_error("连续播放的片段必须来自同一个视频文件")
                return

            video_path = list(video_paths)[0]
            if not os.path.exists(video_path):
                if self.on_error:
                    self.on_error(f"视频文件不存在：{video_path}")
                return
                
            self.current_video_path = video_path
            
            # 创建播放列表
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                list_file = f.name
                
                # 根据重复次数重复写入片段
                for _ in range(self.repeat_count):
                    for segment in segments:
                        abs_path = os.path.abspath(video_path).replace('\\', '\\\\').replace("'", "\\'")
                        actual_start = self._enhanced_seek_time(video_path, segment.start_time)
                        
                        f.write(f"file '{abs_path}'\n")
                        f.write(f"inpoint {actual_start}\n")
                        f.write(f"outpoint {segment.end_time}\n")
                        
            # 播放连续片段
            title = f"连续播放 {len(segments)} 段"
            if self.repeat_count > 1:
                title += f" × {self.repeat_count} 次"
                
            cmd = [
                "ffplay",
                "-autoexit",
                "-volume", str(self.volume),
                "-window_title", title,
                "-x", str(self.window_width),
                "-y", str(self.window_height),
                "-f", "concat",
                "-safe", "0",
                "-framedrop"
            ]
            cmd.append(list_file)
            
            # 启动播放
            self.stop()
            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            self.is_playing = True
            
            if self.on_play_start:
                self.on_play_start(f"开始连续播放 {len(segments)} 段")
                
            # 监控播放状态
            threading.Thread(target=self._monitor_playback_with_cleanup, args=(list_file,), daemon=True).start()
            
        except Exception as e:
            if self.on_error:
                self.on_error(f"连续播放失败：{e}")
        finally:
            self.is_playing = False
            
    def _enhanced_seek_time(self, video_path: str, target_time: float) -> float:
        """
        增强跳转时间计算 - 集成test3.py的精确跳转逻辑
        
        Args:
            video_path: 视频文件路径
            target_time: 目标时间
            
        Returns:
            float: 实际跳转时间
        """
        original_time = target_time
        actual_time = target_time
        
        try:
            if self.seek_mode == "smart":
                # 智能模式：结合关键帧和精确跳转
                keyframes = keyframe_analyzer.get_keyframes(video_path)
                if keyframes:
                    # 找到最近的关键帧
                    keyframe_time = keyframe_analyzer.find_nearest_keyframe(video_path, target_time)
                    
                    # 如果关键帧距离目标较远，使用精确跳转
                    if keyframe_time and abs(keyframe_time - target_time) > 2.0:  # 2秒阈值
                        actual_time = target_time  # 精确跳转
                    else:
                        actual_time = keyframe_time or target_time  # 关键帧跳转
                else:
                    # 没有关键帧数据，使用精确跳转
                    actual_time = target_time
                    
            elif self.seek_mode == "precise":
                # 精确模式：强制精确跳转
                actual_time = target_time
                
            elif self.seek_mode == "keyframe":
                # 关键帧模式：只跳转到关键帧
                keyframe_time = keyframe_analyzer.find_nearest_keyframe(video_path, target_time)
                actual_time = keyframe_time or target_time
                
            # 记录跳转历史
            self._record_seek_history(original_time, actual_time)
            
        except Exception as e:
            print(f"增强跳转计算失败: {e}")
            actual_time = target_time
            
        return actual_time
        
    def _record_seek_history(self, target_time: float, actual_time: float):
        """记录跳转历史"""
        deviation = actual_time - target_time
        self.seek_history.append((target_time, deviation))
        
        # 限制历史记录大小
        if len(self.seek_history) > 50:
            self.seek_history.pop(0)
            
    def _monitor_playback(self):
        """监控播放状态"""
        if self.current_process:
            self.current_process.wait()
            self.is_playing = False
            
            if self.on_play_end:
                self.on_play_end("播放结束")
                
    def _monitor_playback_with_cleanup(self, temp_file: str):
        """监控播放状态并清理临时文件"""
        if self.current_process:
            self.current_process.wait()
            self.is_playing = False
            
            # 清理临时文件
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception as e:
                print(f"清理临时文件失败: {e}")
                
            if self.on_play_end:
                self.on_play_end("播放结束")
                
    def stop(self):
        """停止播放"""
        if self.current_process and self.current_process.poll() is None:
            try:
                self.current_process.terminate()
                self.current_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.current_process.kill()
            except Exception:
                pass
                
        self.current_process = None
        self.is_playing = False
        

            
    def set_volume(self, volume: int):
        """设置音量（0-100）"""
        self.volume = max(0, min(100, volume))
        app_config.set('player.volume', self.volume)
        
    def get_seek_accuracy_stats(self) -> Dict[str, Any]:
        """获取跳转精度统计"""
        if not self.seek_history:
            return {"count": 0, "avg_deviation": 0, "max_deviation": 0}
            
        deviations = [abs(deviation) for _, deviation in self.seek_history]
        return {
            "count": len(deviations),
            "avg_deviation": sum(deviations) / len(deviations),
            "max_deviation": max(deviations),
            "min_deviation": min(deviations)
        }

    @staticmethod
    def is_available() -> bool:
        """检查增强播放器是否可用（依赖ffplay）"""
        try:
            subprocess.run(
                ["ffplay", "-version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                timeout=5
            )
            return True
        except Exception:
            return False

    @staticmethod
    def get_name() -> str:
        """获取播放器名称"""
        return "增强播放器"

    @staticmethod
    def get_description() -> str:
        """获取播放器描述"""
        return "支持精确跳转和关键帧优化的播放器，基于FFplay实现"


# 全局增强播放器实例
enhanced_player = EnhancedPlayer()
