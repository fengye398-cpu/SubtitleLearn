#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增强MPV播放器 - 直接照搬test3.py的实现方式
支持精确跳转和智能跳转模式
"""

import os
import sys
import threading
import time
from typing import List, Optional, Callable

# 设置MPV DLL路径（在导入mpv之前）
def setup_mpv_path():
    """设置MPV DLL路径"""
    try:
        # 获取应用程序基础路径
        if hasattr(sys, '_MEIPASS'):
            # PyInstaller打包环境
            base_path = sys._MEIPASS
        else:
            # 开发环境
            base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        # MPV目录路径
        mpv_dir = os.path.join(base_path, 'mpv')

        if os.path.exists(mpv_dir):
            # 将MPV目录添加到PATH环境变量的开头
            current_path = os.environ.get('PATH', '')
            os.environ['PATH'] = mpv_dir + os.pathsep + current_path
            print(f"[MPV] 已设置MPV路径: {mpv_dir}")
            return True
        else:
            print(f"[MPV] MPV目录不存在: {mpv_dir}")
            return False
    except Exception as e:
        print(f"[MPV] 设置MPV路径失败: {e}")
        return False

# 设置MPV路径
setup_mpv_path()

try:
    import mpv
    MPV_AVAILABLE = True
    print("[MPV] python-mpv库导入成功")
except ImportError as e:
    MPV_AVAILABLE = False
    print(f"[MPV] python-mpv库导入失败: {e}")
except OSError as e:
    MPV_AVAILABLE = False
    print(f"[MPV] MPV DLL加载失败: {e}")
    print("[MPV] 提示: 请确保MPV目录包含所有必要的DLL文件")

from database.models import SubtitleSegment
from database.manager import db_manager
from config.settings import app_config
from core.player_base import PlayerBase
from core.keyframe_analyzer import keyframe_analyzer


class EnhancedMPVPlayer(PlayerBase):
    """增强MPV播放器 - 基于test3.py的实现"""
    
    def __init__(self):
        super().__init__()
        
        # MPV播放器实例
        self.player = None
        self.current_time = None
        self.duration = None
        
        # 跳转模式设置
        self.seek_mode = app_config.get('player.seek_mode', 'precise')  # 默认精确模式
        
        # 播放状态
        self.is_playing_segments = False
        self.current_segment_index = 0
        self.selected_segments = []
        
        # 单个片段重复播放
        self.current_single_segment = None
        self.single_segment_repeat_count = 1
        self.current_single_repeat = 0
        
        # 重复播放设置
        self.repeat_count = app_config.get('player.repeat_count', 1)
        
        # 初始化MPV播放器
        self._init_mpv_player()
        
    def _init_mpv_player(self):
        """初始化MPV播放器"""
        if not MPV_AVAILABLE:
            return
            
        try:
            self.player = mpv.MPV(
                vo='gpu',
                hwdec='auto',
                keep_open='yes',
                idle='yes',
                input_default_bindings=True,
                input_vo_keyboard=True,
                cache=True
            )
            
            # 设置事件回调
            @self.player.property_observer('time-pos')
            def time_observer(_name, value):
                if value is not None:
                    self.current_time = value
                    
            @self.player.property_observer('duration')
            def duration_observer(_name, value):
                if value is not None:
                    self.duration = value
                    
            @self.player.event_callback('playback-restart')
            def playback_restart_callback(event):
                if self.on_play_start:
                    self.on_play_start()
                    
            @self.player.event_callback('end-file')
            def end_file_callback(event):
                if self.on_play_end:
                    self.on_play_end()
                    
        except Exception as e:
            print(f"MPV播放器初始化失败: {e}")
            self.player = None
    
    @staticmethod
    def is_available() -> bool:
        """检查播放器是否可用"""
        return MPV_AVAILABLE
    
    @staticmethod
    def get_name() -> str:
        """获取播放器名称"""
        return "增强MPV播放器"
    
    @staticmethod
    def get_description() -> str:
        """获取播放器描述"""
        return "基于python-mpv的增强播放器，支持精确跳转，照搬test3.py实现"
    
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
        if self.player:
            self.player.volume = max(0, min(100, volume))
    
    def play_segment(self, segment: SubtitleSegment) -> bool:
        """播放单个片段 - 照搬test3.py的实现"""
        if not segment or not self.player:
            return False
            
        # 获取原视频路径
        project = db_manager.get_project(segment.project_id)
        if not project or not project.video_path or not os.path.exists(project.video_path):
            if self.on_error:
                self.on_error(f"原视频文件不存在：{project.video_path if project else 'Unknown'}")
            return False
        
        try:
            # 停止当前的片段播放模式（如果正在进行）
            self.is_playing_segments = False
            
            # 加载视频文件
            self.player.loadfile(project.video_path)

            # 等待视频加载完成
            import time
            max_wait = 3.0  # 最多等待3秒
            wait_time = 0.0
            while wait_time < max_wait:
                try:
                    if self.player.duration is not None:
                        break
                except:
                    pass
                time.sleep(0.1)
                wait_time += 0.1

            # 设置单个片段播放
            self.is_playing_segments = True
            self.current_single_segment = {
                'start': segment.start_time,
                'end': segment.end_time,
                'text': segment.text
            }
            self.single_segment_repeat_count = self.repeat_count
            self.current_single_repeat = 0

            # 单独片段播放时启用字幕
            try:
                self.player.sub_visibility = True
                print("单独片段播放模式：启用字幕显示")
            except Exception as e:
                print(f"设置字幕显示失败: {e}")

            # 执行增强跳转
            self.enhanced_seek(segment.start_time)

            # 确保播放器开始播放
            self.player.pause = False

            # 启动单个片段播放监控
            threading.Thread(target=self._monitor_single_segment_playback, daemon=True).start()
            
            return True
            
        except Exception as e:
            if self.on_error:
                self.on_error(f"播放失败：{e}")
            return False
    
    def enhanced_seek(self, target_time: float):
        """增强跳转：结合精确跳转和关键帧优化 - 直接照搬test3.py"""
        if not self.player:
            return

        # 检查播放器是否已加载文件
        try:
            # 尝试获取播放器状态，如果没有加载文件会抛出异常
            duration = self.player.duration
            if duration is None:
                print("跳转失败: 播放器未加载视频文件")
                return
        except:
            print("跳转失败: 播放器未就绪")
            return

        seek_mode = self.seek_mode
        original_time = target_time
        actual_time = target_time

        try:
            if seek_mode == "smart":
                # 智能模式：结合关键帧和精确跳转
                # 获取当前播放的视频路径
                current_video = getattr(self.player, 'filename', None)
                if current_video:
                    keyframe_time = keyframe_analyzer.find_nearest_keyframe(current_video, target_time)

                    # 如果关键帧距离目标较远，使用精确跳转
                    if keyframe_time and abs(keyframe_time - target_time) > 2.0:  # 2秒阈值
                        self.player.seek(target_time, reference='absolute', precision='exact')
                        actual_time = target_time
                    else:
                        # 跳转到关键帧
                        self.player.seek(keyframe_time or target_time, reference='absolute')
                        actual_time = keyframe_time or target_time
                else:
                    # 没有关键帧数据，使用精确跳转
                    self.player.seek(target_time, reference='absolute', precision='exact')
                    actual_time = target_time

            elif seek_mode == "precise":
                # 精确模式：强制精确跳转 - 这是test3.py的核心逻辑
                self.player.seek(target_time, reference='absolute', precision='exact')
                actual_time = target_time

            print(f"跳转: {original_time:.2f}s -> {actual_time:.2f}s (模式: {seek_mode})")

        except Exception as e:
            print(f"跳转失败: {e}")
            try:
                # 降级到普通跳转 - 照搬test3.py的降级处理
                self.player.seek(target_time, reference='absolute')
                print(f"降级跳转: {target_time:.2f}s")
            except Exception as e2:
                print(f"降级跳转也失败: {e2}")
                if self.on_error:
                    self.on_error(f"跳转失败：{e2}")
    
    def _monitor_single_segment_playback(self):
        """监控单个片段播放 - 照搬test3.py的逻辑"""
        while self.is_playing_segments and self.current_single_segment:
            try:
                time.sleep(0.1)  # 100ms检查间隔
                
                if not self.player or self.current_time is None:
                    continue
                    
                segment = self.current_single_segment
                
                # 检查是否播放到片段结束
                if self.current_time >= segment['end']:
                    self.current_single_repeat += 1
                    
                    # 检查是否需要重复播放
                    if self.current_single_repeat < self.single_segment_repeat_count:
                        # 重复播放：跳转到开始位置
                        self.enhanced_seek(segment['start'])
                        print(f"重复播放 {self.current_single_repeat + 1}/{self.single_segment_repeat_count}")
                    else:
                        # 播放完成，停止片段播放
                        self.is_playing_segments = False
                        if self.player:
                            self.player.pause = True
                        print("片段播放完成")
                        break
                        
            except Exception as e:
                print(f"监控播放异常: {e}")
                break
    
    def play_segments(self, segments: List[SubtitleSegment], continuous: bool = True) -> bool:
        """播放多个片段"""
        if not segments or not self.player:
            return False
            
        # 检查所有片段是否来自同一个视频
        video_paths = set()
        for segment in segments:
            project = db_manager.get_project(segment.project_id)
            if project and project.video_path:
                video_paths.add(project.video_path)
                
        if len(video_paths) != 1:
            if self.on_error:
                self.on_error("连续播放的片段必须来自同一个视频文件")
            return False
            
        video_path = list(video_paths)[0]
        if not os.path.exists(video_path):
            if self.on_error:
                self.on_error(f"视频文件不存在：{video_path}")
            return False
        
        try:
            # 加载视频文件
            self.player.loadfile(video_path)

            # 等待视频加载完成
            import time
            max_wait = 3.0  # 最多等待3秒
            wait_time = 0.0
            while wait_time < max_wait:
                try:
                    if self.player.duration is not None:
                        break
                except:
                    pass
                time.sleep(0.1)
                wait_time += 0.1

            # 批量播放时禁用字幕
            try:
                self.player.sub_visibility = False
                print("批量播放模式：禁用字幕显示")
            except Exception as e:
                print(f"设置字幕隐藏失败: {e}")

            # 设置连续播放模式
            self.is_playing_segments = True
            self.selected_segments = [
                {
                    'start': seg.start_time,
                    'end': seg.end_time,
                    'text': seg.text
                }
                for seg in segments
            ]
            self.current_segment_index = 0

            # 开始播放第一个片段
            self._play_next_segment()
            
            return True
            
        except Exception as e:
            if self.on_error:
                self.on_error(f"连续播放失败：{e}")
            return False
    
    def _play_next_segment(self):
        """播放下一个片段"""
        if not self.is_playing_segments or self.current_segment_index >= len(self.selected_segments):
            return
            
        segment = self.selected_segments[self.current_segment_index]
        self.enhanced_seek(segment['start'])
        
        # 启动监控线程
        threading.Thread(target=self._monitor_segments_playback, daemon=True).start()
    
    def _monitor_segments_playback(self):
        """监控连续片段播放"""
        while self.is_playing_segments and self.current_segment_index < len(self.selected_segments):
            try:
                time.sleep(0.1)
                
                if not self.player or self.current_time is None:
                    continue
                    
                segment = self.selected_segments[self.current_segment_index]
                
                # 检查是否播放到当前片段结束
                if self.current_time >= segment['end']:
                    self.current_segment_index += 1
                    
                    if self.current_segment_index < len(self.selected_segments):
                        # 播放下一个片段
                        next_segment = self.selected_segments[self.current_segment_index]
                        self.enhanced_seek(next_segment['start'])
                    else:
                        # 所有片段播放完成
                        self.is_playing_segments = False
                        if self.player:
                            self.player.pause = True
                        print("连续播放完成")
                        break
                        
            except Exception as e:
                print(f"监控连续播放异常: {e}")
                break
    
    def stop(self):
        """停止播放"""
        self.is_playing_segments = False
        if self.player:
            try:
                self.player.pause = True
            except:
                pass
    
    def pause(self):
        """暂停播放"""
        if self.player:
            try:
                self.player.pause = not self.player.pause
            except:
                pass
    
    def cleanup(self):
        """清理资源"""
        self.stop()
        if self.player:
            try:
                self.player.terminate()
            except:
                pass
            self.player = None
