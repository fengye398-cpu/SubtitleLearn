#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MPV播放器管理模块
负责MPV播放器的查找、验证和管理
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

class MPVManager:
    """MPV播放器管理器"""
    
    _instance = None
    _mpv_path = None
    _mpv_verified = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MPVManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._base_path = self._get_base_path()
    
    def _get_base_path(self):
        """获取应用程序基础路径"""
        try:
            # PyInstaller打包环境
            base_path = sys._MEIPASS
            print(f"[MPV管理器] 检测到打包环境，基础路径: {base_path}")
        except AttributeError:
            # 开发环境
            base_path = os.path.dirname(os.path.abspath(__file__))
            print(f"[MPV管理器] 检测到开发环境，基础路径: {base_path}")
        return base_path
    
    def find_mpv_executable(self):
        """查找MPV可执行文件"""
        if self._mpv_path and self._mpv_verified:
            return self._mpv_path
        
        print("[MPV管理器] 开始查找MPV播放器...")
        
        # 1. 优先查找相对路径的MPV（与应用程序同目录）
        relative_paths = [
            # 当前目录下的mpv文件夹
            os.path.join(self._base_path, "mpv", "mpv.exe"),
            os.path.join(self._base_path, "mpv", "mpv"),
            # 当前目录下直接的mpv可执行文件
            os.path.join(self._base_path, "mpv.exe"),
            os.path.join(self._base_path, "mpv"),
            # 上级目录的mpv文件夹
            os.path.join(os.path.dirname(self._base_path), "mpv", "mpv.exe"),
            os.path.join(os.path.dirname(self._base_path), "mpv", "mpv"),
            # 兄弟目录
            os.path.join(os.path.dirname(self._base_path), "bin", "mpv.exe"),
            os.path.join(os.path.dirname(self._base_path), "bin", "mpv"),
        ]
        
        for mpv_path in relative_paths:
            if os.path.exists(mpv_path) and os.path.isfile(mpv_path):
                if self._verify_mpv(mpv_path):
                    print(f"[MPV管理器] 找到相对路径MPV: {mpv_path}")
                    self._mpv_path = mpv_path
                    self._mpv_verified = True
                    return mpv_path
        
        # 2. 查找环境变量中的MPV
        env_mpv = shutil.which("mpv")
        if env_mpv:
            if self._verify_mpv(env_mpv):
                print(f"[MPV管理器] 找到环境变量MPV: {env_mpv}")
                self._mpv_path = env_mpv
                self._mpv_verified = True
                return env_mpv
        
        # 3. 在常见安装路径查找
        common_paths = [
            r"C:\Program Files\mpv\mpv.exe",
            r"C:\Program Files (x86)\mpv\mpv.exe",
            r"C:\mpv\mpv.exe",
            "/usr/bin/mpv",
            "/usr/local/bin/mpv",
            "/opt/mpv/bin/mpv",
        ]
        
        for mpv_path in common_paths:
            if os.path.exists(mpv_path) and os.path.isfile(mpv_path):
                if self._verify_mpv(mpv_path):
                    print(f"[MPV管理器] 找到系统安装MPV: {mpv_path}")
                    self._mpv_path = mpv_path
                    self._mpv_verified = True
                    return mpv_path
        
        # 4. 都没找到，返回None
        print("[MPV管理器] 未找到MPV播放器")
        return None
    
    def _verify_mpv(self, mpv_path):
        """验证MPV可执行文件是否有效"""
        try:
            # 运行mpv --version来验证
            result = subprocess.run([mpv_path, "--version"], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and "mpv" in result.stdout.lower():
                return True
        except Exception as e:
            print(f"[MPV管理器] 验证MPV失败 {mpv_path}: {e}")
        return False
    
    def get_mpv_path(self):
        """获取MPV路径，如果没有则抛出异常"""
        mpv_path = self.find_mpv_executable()
        if not mpv_path:
            self._raise_mpv_not_found_error()
        return mpv_path
    
    def _raise_mpv_not_found_error(self):
        """抛出MPV未找到的详细错误信息"""
        error_message = """
[ERROR] 未找到MPV播放器

MPV播放器是本软件的核心组件，用于视频播放功能。请按以下方式之一解决：

解决方案：

方案1：使用内置MPV（推荐）
• 将MPV播放器文件夹放在软件同目录下
• 确保路径为：软件目录/mpv/mpv.exe
• 可从官网下载：https://mpv.io/

方案2：安装系统MPV
• 下载MPV安装包并安装到系统
• 确保MPV添加到系统PATH环境变量
• 重启软件后重试

方案3：手动指定路径
• 将MPV可执行文件复制到软件目录
• 确保文件名为 mpv.exe (Windows) 或 mpv (Linux/Mac)

查找路径顺序：
1. 软件目录/mpv/mpv.exe
2. 软件目录/mpv.exe
3. 系统环境变量PATH中的mpv
4. 常见安装路径

提示：
• 建议使用方案1，将MPV与软件一起分发
• 确保MPV版本兼容（建议使用最新稳定版）
• 如果问题持续，请检查文件权限和防病毒软件设置
        """
        raise FileNotFoundError(error_message)
    
    def get_mpv_info(self):
        """获取MPV版本信息"""
        mpv_path = self.find_mpv_executable()
        if not mpv_path:
            return None
        
        try:
            result = subprocess.run([mpv_path, "--version"], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                version_line = lines[0] if lines else "Unknown"
                return {
                    'path': mpv_path,
                    'version': version_line,
                    'full_output': result.stdout
                }
        except Exception as e:
            print(f"[MPV管理器] 获取MPV信息失败: {e}")
        
        return None
    
    def test_mpv_playback(self, test_duration=3):
        """测试MPV播放功能"""
        mpv_path = self.get_mpv_path()
        
        try:
            # 使用MPV播放一个测试视频（空白视频）
            cmd = [
                mpv_path,
                "--no-video",  # 不显示视频
                "--length=1",  # 播放1秒
                "--really-quiet",  # 静默模式
                "av://lavfi:testsrc=duration=1:size=320x240:rate=1"  # 测试源
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=10)
            return result.returncode == 0
            
        except Exception as e:
            print(f"[MPV管理器] MPV播放测试失败: {e}")
            return False
    
    def reset_cache(self):
        """重置缓存，强制重新查找MPV"""
        self._mpv_path = None
        self._mpv_verified = False
        print("[MPV管理器] 缓存已重置")

# 全局MPV管理器实例
_mpv_manager = MPVManager()

def get_mpv_path():
    """获取MPV路径的便捷函数"""
    return _mpv_manager.get_mpv_path()

def find_mpv():
    """查找MPV的便捷函数"""
    return _mpv_manager.find_mpv_executable()

def get_mpv_info():
    """获取MPV信息的便捷函数"""
    return _mpv_manager.get_mpv_info()

def test_mpv():
    """测试MPV的便捷函数"""
    return _mpv_manager.test_mpv_playback()

def reset_mpv_cache():
    """重置MPV缓存的便捷函数"""
    _mpv_manager.reset_cache()

# 测试函数
def test_mpv_manager():
    """测试MPV管理器功能"""
    print("=" * 50)
    print("MPV管理器测试")
    print("=" * 50)
    
    try:
        # 测试查找MPV
        mpv_path = find_mpv()
        if mpv_path:
            print(f"[OK] MPV查找成功: {mpv_path}")

            # 获取MPV信息
            mpv_info = get_mpv_info()
            if mpv_info:
                print(f"[INFO] MPV版本: {mpv_info['version']}")
                print(f"[INFO] MPV路径: {mpv_info['path']}")

            # 测试播放功能
            print("[TEST] 测试MPV播放功能...")
            if test_mpv():
                print("[OK] MPV播放测试成功")
            else:
                print("[ERROR] MPV播放测试失败")
        else:
            print("[ERROR] 未找到MPV播放器")

    except Exception as e:
        print(f"[ERROR] 测试过程中出错: {e}")

if __name__ == "__main__":
    test_mpv_manager()
