#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
电源管理模块
防止导出任务期间系统进入休眠状态
"""

import platform
import ctypes


class PowerManager:
    """电源管理器 - 防止系统休眠"""

    # Windows API 常量
    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001

    _is_prevented = False  # 跟踪当前状态

    @classmethod
    def prevent_sleep(cls):
        """阻止系统进入休眠状态"""
        if platform.system() != 'Windows':
            # 仅支持 Windows
            return

        if cls._is_prevented:
            # 已经阻止过了，避免重复调用
            return

        try:
            # 调用 Windows API 阻止休眠
            ctypes.windll.kernel32.SetThreadExecutionState(
                cls.ES_CONTINUOUS | cls.ES_SYSTEM_REQUIRED
            )
            cls._is_prevented = True
            print("[PowerManager] 已阻止系统休眠")
        except Exception as e:
            print(f"[PowerManager] 阻止休眠失败: {e}")

    @classmethod
    def allow_sleep(cls):
        """恢复系统休眠设置"""
        if platform.system() != 'Windows':
            # 仅支持 Windows
            return

        if not cls._is_prevented:
            # 没有阻止过，无需恢复
            return

        try:
            # 调用 Windows API 恢复休眠
            ctypes.windll.kernel32.SetThreadExecutionState(cls.ES_CONTINUOUS)
            cls._is_prevented = False
            print("[PowerManager] 已恢复系统休眠设置")
        except Exception as e:
            print(f"[PowerManager] 恢复休眠设置失败: {e}")
