#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
设置对话框
"""

import tkinter as tk
from tkinter import ttk, messagebox
from config.settings import app_config
from core.player_factory import PlayerFactory, reset_player


class SettingsDialog:
    """设置对话框"""
    
    def __init__(self, parent, on_player_changed=None):
        """初始化设置对话框
        
        Args:
            parent: 父窗口
            on_player_changed: 播放器切换回调函数
        """
        self.parent = parent
        self.on_player_changed = on_player_changed
        
        # 创建对话框窗口
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("设置")
        self.dialog.geometry("600x600")
        self.dialog.resizable(False, False)
        
        # 设置为模态对话框
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # 创建界面
        self.create_widgets()
        
        # 居中显示
        self.center_window()
    
    def center_window(self):
        """居中显示窗口"""
        self.dialog.update_idletasks()
        width = self.dialog.winfo_width()
        height = self.dialog.winfo_height()
        x = (self.dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (height // 2)
        self.dialog.geometry(f'{width}x{height}+{x}+{y}')
    
    def create_widgets(self):
        """创建界面组件"""
        # 创建主框架
        main_frame = ttk.Frame(self.dialog, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建选项卡
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # 播放器设置选项卡
        player_frame = ttk.Frame(notebook, padding=10)
        notebook.add(player_frame, text="播放器")
        self.create_player_settings(player_frame)
        
        # 按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)
        
        ttk.Button(button_frame, text="确定", command=self.on_ok).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="取消", command=self.on_cancel).pack(side=tk.RIGHT)
    
    def create_player_settings(self, parent):
        """创建播放器设置界面"""
        # 标题
        title_label = ttk.Label(parent, text="播放器设置", font=('', 12, 'bold'))
        title_label.pack(anchor=tk.W, pady=(0, 10))
        
        # 获取可用的播放器列表
        available_players = PlayerFactory.get_available_players()
        current_player_info = PlayerFactory.get_current_player_info()
        
        if not available_players:
            ttk.Label(parent, text="[WARN]  没有可用的播放器！", foreground="red").pack(anchor=tk.W)
            return
        
        # 播放器选择
        player_select_frame = ttk.LabelFrame(parent, text="选择播放器", padding=10)
        player_select_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.player_var = tk.StringVar()
        if current_player_info:
            self.player_var.set(current_player_info[0])
        
        for ptype, name, desc in available_players:
            rb = ttk.Radiobutton(
                player_select_frame,
                text=f"{name} - {desc}",
                variable=self.player_var,
                value=ptype
            )
            rb.pack(anchor=tk.W, pady=2)
        
        # 当前播放器信息
        info_frame = ttk.LabelFrame(parent, text="当前播放器", padding=10)
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        if current_player_info:
            ptype, name, desc = current_player_info
            info_text = f"类型：{name}\n描述：{desc}\n状态：✓ 可用"
        else:
            info_text = "状态：✗ 无可用播放器"
        
        ttk.Label(info_frame, text=info_text, justify=tk.LEFT).pack(anchor=tk.W)
        
        # 播放器说明
        help_frame = ttk.LabelFrame(parent, text="播放器说明", padding=10)
        help_frame.pack(fill=tk.BOTH, expand=True)
        
        help_text = """
FFplay 播放器：
• 基于 FFmpeg，无需额外安装
• 内存占用低（~30MB）
• 适合基础播放需求

MPV 播放器：
• 需要安装 MPV 播放器和 python-mpv 库
• 启动速度更快（~100ms）
• 跳转精度更高（毫秒级）
• 用户体验更好（进度条、音量控制）
• 原生支持重复播放和播放列表
• 推荐用于频繁预览和学习场景

安装 MPV：
1. 下载 MPV：https://mpv.io/installation/
2. 安装 python-mpv：pip install python-mpv
        """
        
        text_widget = tk.Text(help_frame, wrap=tk.WORD, height=12, width=50)
        text_widget.insert('1.0', help_text.strip())
        text_widget.config(state=tk.DISABLED)
        text_widget.pack(fill=tk.BOTH, expand=True)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(text_widget, command=text_widget.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        text_widget.config(yscrollcommand=scrollbar.set)
    
    def on_ok(self):
        """确定按钮"""
        # 获取选择的播放器
        selected_player = self.player_var.get()
        current_player = app_config.get('player.type', 'ffplay')
        
        # 如果播放器改变了
        if selected_player != current_player:
            # 保存配置
            if PlayerFactory.set_player_type(selected_player):
                messagebox.showinfo(
                    "设置成功",
                    f"播放器已切换到：{selected_player}\n\n"
                    "新的播放器将在下次播放时生效。"
                )
                
                # 调用回调函数
                if self.on_player_changed:
                    self.on_player_changed(selected_player)
            else:
                messagebox.showerror(
                    "设置失败",
                    f"无法切换到播放器：{selected_player}\n\n"
                    "请确保播放器已正确安装。"
                )
                return
        
        self.dialog.destroy()
    
    def on_cancel(self):
        """取消按钮"""
        self.dialog.destroy()
    
    def show(self):
        """显示对话框"""
        self.dialog.wait_window()

