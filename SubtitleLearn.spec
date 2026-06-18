# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path

# 获取基础路径
base_dir = Path(r"D:\桌面\video_subtitle_cut\video_subtitle_app")

# 数据文件配置
datas = [
    (str(base_dir / "icons"), "icons"),
    (str(base_dir / "mpv"), "mpv"),
]

# 添加tkinterdnd2的数据文件
import sys
import os
if hasattr(sys, '_MEIPASS'):
    # 打包环境
    pass
else:
    # 开发环境，添加tkinterdnd2数据文件
    try:
        import tkinterdnd2
        tkdnd_path = os.path.join(os.path.dirname(tkinterdnd2.__file__), 'tkdnd')
        if os.path.exists(tkdnd_path):
            datas.append((tkdnd_path, 'tkinterdnd2/tkdnd'))
    except ImportError:
        pass

# 隐藏导入
hiddenimports = [
    'tkinter',
    'tkinter.ttk',
    'sqlite3',
    'pathlib',
    'subprocess',
    'threading',
    'tempfile',
    'json',
    'configparser',
    'psutil',
    'icon_manager',
    'mpv_manager',
    'help_manager',
    'tkinterdnd2',
    'tkinterdnd2.TkinterDnD',
]

# 排除模块
excludes = [
    'matplotlib',
    # 'numpy',  # MoviePy需要numpy，不能排除
    'pandas',
    'scipy',
    'PIL.ImageQt',
    'PyQt5',
    'PyQt6',
    'PySide2',
    'PySide6',
    'IPython',
    'jupyter',
    'notebook',
    'pytest',
    'test',
    'unittest',
    'doctest',
    'pydoc',
    'distutils',
    'setuptools',
    'pip',
    'wheel',
    'pkg_resources',
    'cv2',  # 排除OpenCV
    'opencv-python',
    'opencv-contrib-python',
    'opencv-python-headless',
    'PIL._avif',  # 排除PIL的AVIF支持模块
    'PIL._webp_anim',  # 排除PIL的WebP动画支持
    'PIL.ImageQt',  # 排除PIL的Qt支持
    'PIL.ImageTk',  # 排除PIL的Tkinter支持
    'PIL.ImageWin',  # 排除PIL的Windows特定功能
    'PIL.FpxImagePlugin',  # 排除FPX格式支持
    'PIL.MicImagePlugin',  # 排除MIC格式支持
    'imageio_ffmpeg',  # 排除内置FFmpeg，使用系统FFmpeg（减小50MB+）
    'imageio_ffmpeg.binaries',  # 排除FFmpeg二进制文件
]

# 分析配置
a = Analysis(
    [str(base_dir / "main.py")],
    pathex=[str(base_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(base_dir / "hook-moviepy.py")],  # 添加MoviePy运行时钩子
    excludes=excludes,
    noarchive=False,
    optimize=0,
    # 添加模块收集模式配置
    module_collection_mode={
        'PIL': 'pyz',  # 将PIL模块打包到PYZ中，避免二进制解压问题
    },
)

# PYZ配置
pyz = PYZ(a.pure)

# EXE配置
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # 使用目录模式
    name='SubtitleLearn',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # 关闭UPX压缩以避免解压问题
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 不显示控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(base_dir / "icons" / "app_icon.ico"),
    version_file=None,
)

# COLLECT配置（目录模式）
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='SubtitleLearn',
)
