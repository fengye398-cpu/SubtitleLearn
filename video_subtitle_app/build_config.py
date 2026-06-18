#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
打包配置脚本
使用PyInstaller打包SubtitleLearn应用程序
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

class BuildConfig:
    """打包配置管理器"""
    
    def __init__(self):
        self.app_name = "SubtitleLearn"
        self.version = "1.0.0"
        self.base_dir = Path(__file__).parent
        self.dist_dir = self.base_dir / "dist"
        self.build_dir = self.base_dir / "build"
        self.spec_file = self.base_dir / f"{self.app_name}.spec"
        
    def get_pyinstaller_args(self):
        """获取PyInstaller打包参数"""
        args = [
            "pyinstaller",
            "--name", self.app_name,
            "--onedir",  # 打包成目录模式，而不是单个exe文件

            "--clean",  # 清理临时文件
            
            # 图标设置"--windowed",  # Windows下不显示控制台
            "--icon", str(self.base_dir / "icons" / "app_icon.ico"),
            
            # 添加数据文件
            "--add-data", f"{self.base_dir / 'icons'};icons",
            "--add-data", f"{self.base_dir / 'mpv'};mpv",
            
            # 隐藏导入
            "--hidden-import", "tkinter",
            "--hidden-import", "tkinter.ttk",
            "--hidden-import", "sqlite3",
            "--hidden-import", "pathlib",
            "--hidden-import", "subprocess",
            "--hidden-import", "threading",
            "--hidden-import", "tempfile",
            "--hidden-import", "json",
            "--hidden-import", "configparser",
            "--hidden-import", "psutil",
            
            # 排除不需要的模块以减小体积
            "--exclude-module", "matplotlib",
            "--exclude-module", "numpy",
            "--exclude-module", "pandas",
            "--exclude-module", "scipy",
            "--exclude-module", "PIL.ImageQt",
            "--exclude-module", "PyQt5",
            "--exclude-module", "PyQt6",
            "--exclude-module", "PySide2",
            "--exclude-module", "PySide6",
            "--exclude-module", "IPython",
            "--exclude-module", "jupyter",
            "--exclude-module", "notebook",
            "--exclude-module", "pytest",
            "--exclude-module", "unittest",
            "--exclude-module", "doctest",
            "--exclude-module", "pydoc",
            "--exclude-module", "distutils",
            "--exclude-module", "setuptools",
            "--exclude-module", "pip",
            
            # 主程序入口
            str(self.base_dir / "main.py")
        ]
        
        return args
    
    def create_spec_file(self):
        """创建自定义的spec文件"""
        spec_content = f'''# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path

# 获取基础路径
base_dir = Path(r"{self.base_dir}")

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
    hooksconfig={{}},
    runtime_hooks=[str(base_dir / "hook-moviepy.py")],  # 添加MoviePy运行时钩子
    excludes=excludes,
    noarchive=False,
    optimize=0,
    # 添加模块收集模式配置
    module_collection_mode={{
        'PIL': 'pyz',  # 将PIL模块打包到PYZ中，避免二进制解压问题
    }},
)

# PYZ配置
pyz = PYZ(a.pure)

# EXE配置
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # 使用目录模式
    name='{self.app_name}',
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
    name='{self.app_name}',
)
'''
        
        with open(self.spec_file, 'w', encoding='utf-8') as f:
            f.write(spec_content)
        
        print(f"[OK] 已创建spec文件: {self.spec_file}")
    
    def check_dependencies(self):
        """检查打包依赖"""
        print("[SEARCH] 检查打包依赖...")
        
        # 检查PyInstaller
        try:
            import PyInstaller
            print(f"[OK] PyInstaller: {PyInstaller.__version__}")
        except ImportError:
            print("[ERROR] PyInstaller未安装，请运行: pip install pyinstaller")
            return False
        
        # 检查图标文件
        icon_file = self.base_dir / "icons" / "app_icon.ico"
        if icon_file.exists():
            print(f"[OK] 图标文件: {icon_file}")
        else:
            print(f"[ERROR] 图标文件不存在: {icon_file}")
            return False
        
        # 检查MPV文件
        mpv_dir = self.base_dir / "mpv"
        if mpv_dir.exists():
            mpv_exe = mpv_dir / "mpv.exe"
            if mpv_exe.exists():
                print(f"[OK] MPV播放器: {mpv_exe}")
            else:
                print(f"[WARN] MPV可执行文件不存在: {mpv_exe}")
        else:
            print(f"[WARN] MPV目录不存在: {mpv_dir}")
        
        # 检查主程序
        main_file = self.base_dir / "main.py"
        if main_file.exists():
            print(f"[OK] 主程序: {main_file}")
        else:
            print(f"[ERROR] 主程序不存在: {main_file}")
            return False
        
        return True
    
    def clean_build_files(self):
        """清理构建文件"""
        print("🧹 清理构建文件...")
        
        dirs_to_clean = [self.build_dir, self.dist_dir]
        files_to_clean = [self.spec_file]
        
        for dir_path in dirs_to_clean:
            if dir_path.exists():
                shutil.rmtree(dir_path)
                print(f"[TRASH] 已删除目录: {dir_path}")
        
        for file_path in files_to_clean:
            if file_path.exists():
                file_path.unlink()
                print(f"[TRASH] 已删除文件: {file_path}")
    
    def build_application(self, use_spec=True):
        """构建应用程序"""
        print(f"🚀 开始构建 {self.app_name} v{self.version}")
        print("="*60)

        # 自动清理旧的构建文件
        print("\n🧹 清理旧的构建文件...")
        self.clean_build_files()

        # 检查依赖
        if not self.check_dependencies():
            print("[ERROR] 依赖检查失败，无法继续构建")
            return False
        
        try:
            if use_spec:
                # 创建spec文件
                self.create_spec_file()

                # 使用spec文件构建（添加 -y 选项自动覆盖）
                cmd = ["pyinstaller", "-y", str(self.spec_file)]
            else:
                # 使用命令行参数构建
                cmd = self.get_pyinstaller_args()
            
            print(f"[PACKAGE] 执行构建命令: {' '.join(cmd)}")
            
            # 执行构建
            result = subprocess.run(cmd, cwd=self.base_dir, capture_output=True, text=True)
            
            if result.returncode == 0:
                print("[OK] 构建成功！")
                
                # 检查输出文件（目录模式）
                exe_file_dir = self.dist_dir / self.app_name / f"{self.app_name}.exe"
                exe_file_single = self.dist_dir / f"{self.app_name}.exe"

                if exe_file_dir.exists():
                    size_mb = exe_file_dir.stat().st_size / (1024 * 1024)
                    print(f"[FOLDER] 输出文件: {exe_file_dir}")
                    print(f"[CHART] 文件大小: {size_mb:.1f} MB")

                    # 显示构建信息
                    self.show_build_info()
                    return True
                elif exe_file_single.exists():
                    size_mb = exe_file_single.stat().st_size / (1024 * 1024)
                    print(f"[FOLDER] 输出文件: {exe_file_single}")
                    print(f"[CHART] 文件大小: {size_mb:.1f} MB")

                    # 显示构建信息
                    self.show_build_info()
                    return True
                else:
                    print(f"[ERROR] 输出文件不存在")
                    print(f"检查路径: {exe_file_dir}")
                    print(f"检查路径: {exe_file_single}")
                    return False
            else:
                print("[ERROR] 构建失败！")
                print("错误输出:")
                print(result.stderr)
                return False
                
        except Exception as e:
            print(f"[ERROR] 构建过程中出错: {e}")
            return False
    
    def show_build_info(self):
        """显示构建信息"""
        print("\n" + "="*60)
        print("📦 构建信息")
        print("="*60)
        print(f"应用名称: {self.app_name}")
        print(f"版本号: {self.version}")
        print(f"输出目录: {self.dist_dir / self.app_name}")

        # 检查目录模式的exe
        exe_file = self.dist_dir / self.app_name / f"{self.app_name}.exe"
        if exe_file.exists():
            size_mb = exe_file.stat().st_size / (1024 * 1024)
            print(f"可执行文件: {exe_file.name}")
            print(f"文件大小: {size_mb:.1f} MB")

            # 计算整个dist目录大小
            total_size = 0
            dist_path = self.dist_dir / self.app_name
            for item in dist_path.rglob('*'):
                if item.is_file():
                    total_size += item.stat().st_size
            total_size_mb = total_size / (1024 * 1024)
            print(f"总体积: {total_size_mb:.1f} MB")

        # 验证是否成功排除 imageio_ffmpeg
        print("\n🔍 验证FFmpeg排除状态:")
        dist_path = self.dist_dir / self.app_name
        imageio_found = False
        ffmpeg_exe_found = False

        if dist_path.exists():
            # 检查是否有imageio_ffmpeg目录
            for item in dist_path.rglob('imageio_ffmpeg*'):
                if item.is_dir():
                    print(f"   ⚠️ 发现 imageio_ffmpeg 目录: {item.relative_to(dist_path)}")
                    imageio_found = True

            # 检查是否有ffmpeg二进制文件
            for item in dist_path.rglob('ffmpeg*.exe'):
                if 'imageio' in str(item):
                    print(f"   ⚠️ 发现 FFmpeg 二进制: {item.relative_to(dist_path)}")
                    ffmpeg_exe_found = True

        if not imageio_found and not ffmpeg_exe_found:
            print("   ✅ imageio_ffmpeg: 已成功排除")
            print("   ✅ FFmpeg二进制: 已成功排除")
            print("   ✅ 预计减小体积: 50-80MB")
        else:
            print("   ❌ 警告：检测到未排除的文件！")
            print("   提示：删除 build 和 dist 目录后重新打包")

        print("\n💡 使用说明:")
        print("1. 分发整个文件夹给用户: dist/SubtitleLearn/")
        print("2. 用户首次运行会提示配置FFmpeg")
        print("3. 提供 '分发说明-README.txt' 给用户参考")
        print("4. 确保用户系统支持Windows 10+")

        print("\n📋 测试清单:")
        print("☐ 在干净环境中测试启动（无FFmpeg）")
        print("☐ 验证FFmpeg配置提示是否正常显示")
        print("☐ 配置FFmpeg后测试所有功能")
        print("☐ 检查是否包含imageio_ffmpeg（不应该有）")

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="SubtitleLearn 打包工具")
    parser.add_argument("--clean", action="store_true", help="清理构建文件")
    parser.add_argument("--no-spec", action="store_true", help="不使用spec文件")
    parser.add_argument("--check", action="store_true", help="仅检查依赖")
    
    args = parser.parse_args()
    
    builder = BuildConfig()
    
    if args.clean:
        builder.clean_build_files()
        return
    
    if args.check:
        builder.check_dependencies()
        return
    
    # 构建应用程序
    success = builder.build_application(use_spec=not args.no_spec)
    
    if success:
        print("\n[PARTY] 构建完成！")
    else:
        print("\n[BOOM] 构建失败！")
        sys.exit(1)

if __name__ == "__main__":
    main()
