#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图标管理模块
统一管理应用程序图标，支持开发环境和打包后的EXE环境
"""

import os
import sys
import tkinter as tk
from pathlib import Path

class IconManager:
    """图标管理器"""
    
    _instance = None
    _icon_cache = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(IconManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._base_path = self._get_base_path()
            self._icon_dir = self._find_icon_directory()
    
    def _get_base_path(self):
        """获取资源文件的基础路径，支持开发环境和打包后的EXE"""
        try:
            # PyInstaller创建临时文件夹，并将路径存储在_MEIPASS中
            base_path = sys._MEIPASS
            print(f"[图标管理器] 检测到打包环境，资源路径: {base_path}")
        except AttributeError:
            # 开发环境中使用当前目录
            base_path = os.path.dirname(os.path.abspath(__file__))
            print(f"[图标管理器] 检测到开发环境，资源路径: {base_path}")
        return base_path
    
    def _find_icon_directory(self):
        """查找图标目录"""
        # 可能的图标目录位置
        possible_dirs = [
            os.path.join(self._base_path, "icons"),
            os.path.join(self._base_path, "assets", "icons"),
            os.path.join(self._base_path, "resources", "icons"),
            os.path.join(os.path.dirname(self._base_path), "icons"),  # 上级目录
        ]
        
        for icon_dir in possible_dirs:
            if os.path.exists(icon_dir):
                print(f"[图标管理器] 找到图标目录: {icon_dir}")
                return icon_dir
        
        # 如果都没找到，使用默认目录
        default_dir = os.path.join(self._base_path, "icons")
        print(f"[图标管理器] 未找到图标目录，使用默认路径: {default_dir}")
        return default_dir
    
    def get_icon_path(self, icon_name="app_icon.ico"):
        """获取图标文件的完整路径"""
        if not icon_name:
            icon_name = "app_icon.ico"
        
        icon_path = os.path.join(self._icon_dir, icon_name)
        
        # 检查文件是否存在
        if os.path.exists(icon_path):
            print(f"[图标管理器] 图标文件存在: {icon_path}")
            return icon_path
        else:
            print(f"[图标管理器] 图标文件不存在: {icon_path}")
            # 尝试查找其他格式的图标
            base_name = os.path.splitext(icon_name)[0]
            for ext in ['.ico', '.png', '.gif']:
                alt_path = os.path.join(self._icon_dir, f"{base_name}{ext}")
                if os.path.exists(alt_path):
                    print(f"[图标管理器] 找到替代图标: {alt_path}")
                    return alt_path
            
            print(f"[图标管理器] 警告: 未找到任何图标文件")
            return None
    
    def load_icon(self, icon_name="app_icon.ico"):
        """加载图标对象（PhotoImage）"""
        if icon_name in self._icon_cache:
            return self._icon_cache[icon_name]
        
        icon_path = self.get_icon_path(icon_name)
        if icon_path and os.path.exists(icon_path):
            try:
                # 根据文件扩展名选择加载方式
                ext = os.path.splitext(icon_path)[1].lower()
                if ext in ['.png', '.gif']:
                    icon = tk.PhotoImage(file=icon_path)
                    self._icon_cache[icon_name] = icon
                    print(f"[图标管理器] 成功加载图标: {icon_path}")
                    return icon
                else:
                    # ICO文件需要特殊处理
                    print(f"[图标管理器] ICO文件将由系统处理: {icon_path}")
                    return icon_path
            except Exception as e:
                print(f"[图标管理器] 加载图标失败: {e}")
                return None
        
        return None

# 全局图标管理器实例
_icon_manager = IconManager()

def get_icon_path(icon_name="app_icon.ico"):
    """获取图标路径的便捷函数"""
    return _icon_manager.get_icon_path(icon_name)

def load_icon(icon_name="app_icon.ico"):
    """加载图标的便捷函数"""
    return _icon_manager.load_icon(icon_name)

def set_window_icon(window, icon_name="app_icon.ico"):
    """为窗口设置图标的便捷函数"""
    try:
        icon_path = get_icon_path(icon_name)
        if icon_path:
            # 对于ICO文件，直接设置路径
            if icon_path.endswith('.ico'):
                window.iconbitmap(icon_path)
                print(f"[图标管理器] 窗口图标设置成功: {icon_path}")
            else:
                # 对于PNG/GIF文件，加载为PhotoImage
                icon = load_icon(icon_name)
                if icon:
                    window.iconphoto(True, icon)
                    print(f"[图标管理器] 窗口图标设置成功: {icon_path}")
        else:
            print(f"[图标管理器] 警告: 无法为窗口设置图标，图标文件不存在")
    except Exception as e:
        print(f"[图标管理器] 设置窗口图标失败: {e}")

def get_app_info():
    """获取应用程序信息"""
    return {
        'name': 'SubtitleLearn',
        'version': '2.0.8',
        'description': '外语学习字幕片段工具',
        'author': '开发者',
        'icon_path': get_icon_path()
    }

# 测试函数
def test_icon_manager():
    """测试图标管理器功能"""
    print("=" * 50)
    print("图标管理器测试")
    print("=" * 50)
    
    # 测试获取图标路径
    icon_path = get_icon_path()
    print(f"主图标路径: {icon_path}")
    
    # 测试应用信息
    app_info = get_app_info()
    print(f"应用信息: {app_info}")
    
    # 创建测试窗口
    try:
        root = tk.Tk()
        root.title("图标测试窗口")
        root.geometry("300x200")
        
        # 设置窗口图标
        set_window_icon(root)
        
        # 添加标签
        label = tk.Label(root, text="图标测试窗口\n如果看到窗口图标，说明图标管理器工作正常", 
                        justify=tk.CENTER, pady=50)
        label.pack()
        
        # 添加关闭按钮
        close_btn = tk.Button(root, text="关闭", command=root.destroy)
        close_btn.pack(pady=10)
        
        print("测试窗口已创建，请检查窗口是否显示图标")
        root.mainloop()
        
    except Exception as e:
        print(f"创建测试窗口失败: {e}")

if __name__ == "__main__":
    test_icon_manager()
