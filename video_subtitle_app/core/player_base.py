#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
播放器抽象基类
定义统一的播放器接口
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Callable
from database.models import SubtitleSegment


class PlayerBase(ABC):
    """播放器抽象基类"""
    
    def __init__(self):
        """初始化播放器"""
        from config.settings import app_config

        self.is_playing = False
        self.volume = app_config.get('player.volume', 100)  # 从配置读取音量，默认100
        self.auto_play = app_config.get('player.auto_play', False)
        self.loop = app_config.get('player.loop', False)
        self.repeat_count = app_config.get('player.repeat_count', 1)
        
        # 回调函数
        self.on_play_start: Optional[Callable] = None
        self.on_play_end: Optional[Callable] = None
        self.on_error: Optional[Callable] = None
    
    @abstractmethod
    def play_segment(self, segment: SubtitleSegment) -> bool:
        """播放单个片段
        
        Args:
            segment: 字幕片段对象
            
        Returns:
            bool: 播放是否成功
        """
        pass
    
    @abstractmethod
    def play_segments(self, segments: List[SubtitleSegment], continuous: bool = True) -> bool:
        """播放多个片段
        
        Args:
            segments: 片段列表
            continuous: 是否连续播放
            
        Returns:
            bool: 播放是否成功
        """
        pass
    
    @abstractmethod
    def stop(self) -> None:
        """停止播放"""
        pass
    
    def set_volume(self, volume: int) -> None:
        """设置音量
        
        Args:
            volume: 音量值 (0-100)
        """
        self.volume = max(0, min(100, volume))
    
    def set_repeat_count(self, count: int) -> None:
        """设置重复次数
        
        Args:
            count: 重复次数 (1-99)
        """
        self.repeat_count = max(1, min(99, count))
    
    def set_callbacks(self, on_play_start: Callable = None,
                     on_play_end: Callable = None, on_error: Callable = None) -> None:
        """设置回调函数
        
        Args:
            on_play_start: 播放开始回调
            on_play_end: 播放结束回调
            on_error: 错误回调
        """
        if on_play_start:
            self.on_play_start = on_play_start
        if on_play_end:
            self.on_play_end = on_play_end
        if on_error:
            self.on_error = on_error
    
    @staticmethod
    @abstractmethod
    def is_available() -> bool:
        """检查播放器是否可用
        
        Returns:
            bool: 播放器是否可用
        """
        pass
    
    @staticmethod
    @abstractmethod
    def get_name() -> str:
        """获取播放器名称
        
        Returns:
            str: 播放器名称
        """
        pass
    
    @staticmethod
    @abstractmethod
    def get_description() -> str:
        """获取播放器描述
        
        Returns:
            str: 播放器描述
        """
        pass

