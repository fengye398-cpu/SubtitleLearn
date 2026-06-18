#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PyInstaller runtime hook for MoviePy
强制MoviePy使用系统FFmpeg，避免使用imageio_ffmpeg
"""

import os
import sys

# 在导入MoviePy前配置环境变量
os.environ['FFMPEG_BINARY'] = 'ffmpeg'
os.environ['IMAGEIO_FFMPEG_EXE'] = 'ffmpeg'

# 创建假的imageio_ffmpeg模块，防止MoviePy尝试导入
if 'imageio_ffmpeg' not in sys.modules:
    class FakeImageIOFFmpeg:
        """假的imageio_ffmpeg模块，直接返回系统ffmpeg路径"""
        @staticmethod
        def get_ffmpeg_exe():
            return 'ffmpeg'

        @staticmethod
        def get_ffmpeg_version():
            return '4.0.0'  # 返回一个假版本号

    sys.modules['imageio_ffmpeg'] = FakeImageIOFFmpeg()

print("[Hook] MoviePy已配置使用系统FFmpeg")
