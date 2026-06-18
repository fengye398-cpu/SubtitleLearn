#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Toast通知组件 - 非阻塞式提示
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional, Callable, List, Dict


class ToastNotification:
    """Toast通知组件 - 显示在窗口右下角的非阻塞式通知"""

    def __init__(self, parent, message: str, duration: int = 3000,
                 actions: Optional[List[Dict[str, any]]] = None):
        """初始化Toast通知

        Args:
            parent: 父窗口
            message: 提示消息
            duration: 显示时长(毫秒)，默认3000ms(3秒)
            actions: 可选操作按钮列表，格式: [{"text": "按钮文字", "command": 回调函数}]
        """
        self.parent = parent
        self.message = message
        self.duration = duration
        self.actions = actions or []

        # 控制变量
        self.is_hovering = False
        self.is_closing = False
        self.close_timer_id = None

        # 创建Toast窗口
        self.toast_window = None
        self._create_toast()

    def _create_toast(self):
        """创建Toast窗口"""
        # 创建顶层窗口
        self.toast_window = tk.Toplevel(self.parent)
        self.toast_window.withdraw()  # 先隐藏

        # 移除窗口装饰（标题栏等）
        self.toast_window.overrideredirect(True)

        # 设置窗口属性
        self.toast_window.attributes('-topmost', True)  # 置顶

        # Windows平台设置半透明背景
        try:
            self.toast_window.attributes('-alpha', 0.95)
        except:
            pass

        # 创建主框架
        main_frame = tk.Frame(self.toast_window, bg='#2C3E50', relief=tk.RAISED, bd=2)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # 内容框架
        content_frame = tk.Frame(main_frame, bg='#34495E', padx=20, pady=15)
        content_frame.pack(fill=tk.BOTH, expand=True)

        # 显示消息（支持多行）
        message_label = tk.Label(
            content_frame,
            text=self.message,
            bg='#34495E',
            fg='white',
            font=('Microsoft YaHei UI', 10),
            justify=tk.LEFT,
            wraplength=400
        )
        message_label.pack(anchor=tk.W, pady=(0, 10) if self.actions else (0, 0))

        # 如果有操作按钮，创建按钮区域
        if self.actions:
            button_frame = tk.Frame(content_frame, bg='#34495E')
            button_frame.pack(fill=tk.X, pady=(10, 0))

            # 创建居中容器
            button_container = tk.Frame(button_frame, bg='#34495E')
            button_container.pack(anchor=tk.CENTER)

            for action in self.actions:
                btn = tk.Button(
                    button_container,
                    text=action.get('text', '操作'),
                    command=lambda cmd=action.get('command'): self._on_action_click(cmd),
                    bg='#3498DB',
                    fg='white',
                    font=('Microsoft YaHei UI', 9),
                    relief=tk.FLAT,
                    cursor='hand2',
                    padx=15,
                    pady=5
                )
                btn.pack(side=tk.LEFT, padx=5)

                # 鼠标悬停效果
                btn.bind('<Enter>', lambda e, b=btn: b.config(bg='#2980B9'))
                btn.bind('<Leave>', lambda e, b=btn: b.config(bg='#3498DB'))

        # 绑定鼠标悬停事件（暂停自动消失）
        self.toast_window.bind('<Enter>', self._on_mouse_enter)
        self.toast_window.bind('<Leave>', self._on_mouse_leave)

        # 绑定点击关闭事件
        self.toast_window.bind('<Button-1>', lambda e: self.close())

        # 更新窗口并计算位置
        self.toast_window.update_idletasks()
        self._position_toast()

        # 显示窗口（淡入效果）
        self.toast_window.deiconify()
        self._fade_in()

    def _position_toast(self):
        """定位Toast窗口到父窗口底部中央"""
        # 获取父窗口位置和大小
        parent_x = self.parent.winfo_x()
        parent_y = self.parent.winfo_y()
        parent_width = self.parent.winfo_width()
        parent_height = self.parent.winfo_height()

        # 获取Toast窗口大小
        toast_width = self.toast_window.winfo_width()
        toast_height = self.toast_window.winfo_height()

        # 计算位置（底部中央，距离底部60px）
        x = parent_x + (parent_width - toast_width) // 2
        y = parent_y + parent_height - toast_height - 60

        self.toast_window.geometry(f"+{x}+{y}")

    def _fade_in(self):
        """淡入动画"""
        try:
            alpha = 0.0
            def animate():
                nonlocal alpha
                if alpha < 0.95:
                    alpha += 0.1
                    self.toast_window.attributes('-alpha', alpha)
                    self.toast_window.after(30, animate)
                else:
                    # 淡入完成，启动自动关闭计时器
                    self._start_close_timer()
            animate()
        except:
            # 如果不支持透明度动画，直接显示并启动计时器
            self._start_close_timer()

    def _fade_out(self):
        """淡出动画"""
        try:
            alpha = 0.95
            def animate():
                nonlocal alpha
                if alpha > 0:
                    alpha -= 0.1
                    self.toast_window.attributes('-alpha', alpha)
                    self.toast_window.after(30, animate)
                else:
                    self._destroy()
            animate()
        except:
            # 如果不支持透明度动画，直接销毁
            self._destroy()

    def _start_close_timer(self):
        """启动自动关闭计时器"""
        if not self.is_hovering and not self.is_closing:
            self.close_timer_id = self.toast_window.after(self.duration, self.close)

    def _cancel_close_timer(self):
        """取消自动关闭计时器"""
        if self.close_timer_id:
            self.toast_window.after_cancel(self.close_timer_id)
            self.close_timer_id = None

    def _on_mouse_enter(self, event):
        """鼠标进入时暂停自动消失"""
        self.is_hovering = True
        self._cancel_close_timer()

    def _on_mouse_leave(self, event):
        """鼠标离开时恢复自动消失"""
        self.is_hovering = False
        self._start_close_timer()

    def _on_action_click(self, command: Optional[Callable]):
        """操作按钮点击事件"""
        # 先保存父窗口引用
        parent_window = self.parent

        # 立即关闭Toast
        self.close()

        # 延迟执行回调函数（避免窗口最小化问题）
        if command and callable(command):
            def delayed_command():
                try:
                    # 延迟150ms后执行回调，确保Toast完全关闭且父窗口恢复焦点
                    parent_window.after(150, command)
                except Exception as e:
                    print(f"[Toast] 执行操作回调失败: {e}")

            delayed_command()

        # 确保父窗口保持在前台
        def restore_parent_focus():
            try:
                # 如果父窗口存在且可见
                if parent_window.winfo_exists():
                    parent_window.lift()
                    parent_window.attributes('-topmost', True)
                    parent_window.attributes('-topmost', False)
                    parent_window.focus_force()
            except:
                pass

        # 延迟100ms执行
        try:
            parent_window.after(100, restore_parent_focus)
        except:
            pass

    def close(self):
        """关闭Toast"""
        if self.is_closing:
            return

        self.is_closing = True
        self._cancel_close_timer()
        self._fade_out()

    def _destroy(self):
        """销毁窗口"""
        if self.toast_window:
            try:
                self.toast_window.destroy()
            except:
                pass
            self.toast_window = None


# 便捷函数
def show_toast(parent, message: str, duration: int = 3000,
               actions: Optional[List[Dict[str, any]]] = None) -> ToastNotification:
    """显示Toast通知

    Args:
        parent: 父窗口
        message: 提示消息
        duration: 显示时长(毫秒)，默认3000ms
        actions: 可选操作按钮列表

    Returns:
        ToastNotification实例

    Example:
        show_toast(
            parent=main_window,
            message="✓ 已添加 47 个片段到队列\n当前队列: 3 个任务",
            actions=[
                {"text": "📂 打开队列管理器", "command": open_queue_manager},
                {"text": "↩ 撤销", "command": undo_add_task}
            ]
        )
    """
    return ToastNotification(parent, message, duration, actions)
