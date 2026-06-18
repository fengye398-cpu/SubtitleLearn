#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
队列管理器对话框 - Tkinter版本
管理导出队列的专用窗口
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
from typing import Optional, Callable, Dict, Any
from datetime import datetime

from core.export_queue import ExportQueue, ExportTask, TaskStatus
from core.export_processor import QueueProcessor


class QueueManagerDialog:
    """队列管理器对话框 - Tkinter版本"""

    def __init__(self, queue: ExportQueue, processor: QueueProcessor, parent=None):
        """
        初始化队列管理器

        Args:
            queue: 导出队列
            processor: 队列处理器
            parent: 父窗口
        """
        self.queue = queue
        self.processor = processor
        self.parent = parent

        # 状态变量
        self.is_closing = False
        self.update_timer = None
        self.selected_task_id = None
        self.last_clicked_item = None  # 记录上一次点击的项目（用于shift多选）

        # 回调函数
        self.on_finished = None  # 窗口关闭回调

        # 创建窗口
        self.create_dialog()

        # 设置处理器回调
        self.setup_processor_callbacks()

        # 开始更新
        self.start_update_timer()

    def create_dialog(self):
        """创建对话框窗口"""
        self.dialog = tk.Toplevel(self.parent) if self.parent else tk.Tk()
        self.dialog.title("队列管理器")
        self.dialog.geometry("900x700")
        self.dialog.resizable(True, True)

        # 设置窗口图标
        try:
            from icon_manager import set_window_icon
            set_window_icon(self.dialog)
        except ImportError:
            pass

        # 居中显示
        self.center_dialog()

        # 创建界面
        self.create_widgets()

        # 绑定事件
        self.dialog.protocol("WM_DELETE_WINDOW", self.on_close)

        # 初始更新
        self.update_display()

    def center_dialog(self):
        """居中显示对话框"""
        self.dialog.update_idletasks()
        width = self.dialog.winfo_width()
        height = self.dialog.winfo_height()
        x = (self.dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (height // 2)
        self.dialog.geometry(f"{width}x{height}+{x}+{y}")

    def create_widgets(self):
        """创建界面组件"""
        # 主容器
        main_frame = ttk.Frame(self.dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 1. 工具栏（队列控制）
        self.create_toolbar(main_frame)

        # 2. 统计信息面板
        self.create_stats_panel(main_frame)

        # 3. 任务列表
        self.create_task_list(main_frame)

        # 4. 日志面板
        self.create_log_panel(main_frame)

    def create_toolbar(self, parent):
        """创建工具栏"""
        toolbar_frame = ttk.LabelFrame(parent, text="队列控制", padding=5)
        toolbar_frame.pack(fill=tk.X, pady=(0, 10))

        # 所有按钮在一行显示
        button_row = ttk.Frame(toolbar_frame)
        button_row.pack(fill=tk.X)

        # 左侧：队列控制按钮
        self.start_button = ttk.Button(button_row, text="开始处理", command=self.start_queue, width=10)
        self.start_button.pack(side=tk.LEFT, padx=(0, 3))

        self.stop_button = ttk.Button(button_row, text="停止处理", command=self.stop_queue, width=10)
        self.stop_button.pack(side=tk.LEFT, padx=(0, 3))

        # 批量选择按钮
        ttk.Button(button_row, text="全选", command=self.select_all, width=6).pack(side=tk.LEFT, padx=(0, 3))
        ttk.Button(button_row, text="取消全选", command=self.deselect_all, width=8).pack(side=tk.LEFT, padx=(0, 3))
        ttk.Button(button_row, text="反选", command=self.invert_selection, width=6).pack(side=tk.LEFT, padx=(0, 3))

        # 任务移动按钮
        self.move_up_button = ttk.Button(button_row, text="上移", command=self.move_task_up, width=6)
        self.move_up_button.pack(side=tk.LEFT, padx=(0, 3))

        self.move_down_button = ttk.Button(button_row, text="下移", command=self.move_task_down, width=6)
        self.move_down_button.pack(side=tk.LEFT, padx=(0, 3))

        # 右侧：任务管理按钮
        ttk.Button(button_row, text="清空全部", command=self.clear_all, width=8).pack(side=tk.RIGHT)
        ttk.Button(button_row, text="清空完成", command=self.clear_completed, width=8).pack(side=tk.RIGHT, padx=(0, 3))
        ttk.Button(button_row, text="删除任务", command=self.remove_selected_tasks, width=8).pack(side=tk.RIGHT, padx=(0, 3))

    def create_stats_panel(self, parent):
        """创建统计信息面板"""
        # 统计面板容器
        stats_container = ttk.Frame(parent)
        stats_container.pack(fill=tk.X, pady=(0, 10))

        # 左侧：队列统计
        queue_stats_frame = ttk.LabelFrame(stats_container, text="队列统计", padding=5)
        queue_stats_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        # 统计信息容器
        stats_inner = ttk.Frame(queue_stats_frame)
        stats_inner.pack(fill=tk.X)

        # 左列统计
        left_stats = ttk.Frame(stats_inner)
        left_stats.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.total_label = ttk.Label(left_stats, text="总任务数: 0")
        self.total_label.pack(anchor=tk.W, pady=2)

        self.pending_label = ttk.Label(left_stats, text="等待中: 0")
        self.pending_label.pack(anchor=tk.W, pady=2)

        self.processing_label = ttk.Label(left_stats, text="处理中: 0")
        self.processing_label.pack(anchor=tk.W, pady=2)

        # 右列统计
        right_stats = ttk.Frame(stats_inner)
        right_stats.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))

        self.completed_label = ttk.Label(right_stats, text="已完成: 0")
        self.completed_label.pack(anchor=tk.W, pady=2)

        self.failed_label = ttk.Label(right_stats, text="失败: 0")
        self.failed_label.pack(anchor=tk.W, pady=2)

        self.segments_label = ttk.Label(right_stats, text="片段进度: 0/0")
        self.segments_label.pack(anchor=tk.W, pady=2)

        # 右侧：预计处理时间
        time_stats_frame = ttk.LabelFrame(stats_container, text="预计处理时间", padding=5)
        time_stats_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 预计处理时间
        estimated_frame = ttk.Frame(time_stats_frame)
        estimated_frame.pack(anchor=tk.W, pady=2)
        ttk.Label(estimated_frame, text="⏱️", font=("Arial", 10)).pack(side=tk.LEFT)
        self.estimated_time_label = ttk.Label(estimated_frame, text="预计时间: --",
                                              font=("Arial", 9), foreground="blue")
        self.estimated_time_label.pack(side=tk.LEFT, padx=(3, 0))

        # 已用时间
        elapsed_frame = ttk.Frame(time_stats_frame)
        elapsed_frame.pack(anchor=tk.W, pady=2)
        ttk.Label(elapsed_frame, text="⏳", font=("Arial", 10)).pack(side=tk.LEFT)
        self.elapsed_time_label = ttk.Label(elapsed_frame, text="已用时间: --",
                                            font=("Arial", 9), foreground="green")
        self.elapsed_time_label.pack(side=tk.LEFT, padx=(3, 0))

        # 剩余时间
        remaining_frame = ttk.Frame(time_stats_frame)
        remaining_frame.pack(anchor=tk.W, pady=2)
        ttk.Label(remaining_frame, text="⏰", font=("Arial", 10)).pack(side=tk.LEFT)
        self.remaining_time_label = ttk.Label(remaining_frame, text="剩余时间: --",
                                              font=("Arial", 9), foreground="orange")
        self.remaining_time_label.pack(side=tk.LEFT, padx=(3, 0))

    def create_task_list(self, parent):
        """创建任务列表"""
        list_frame = ttk.LabelFrame(parent, text="任务列表", padding=5)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # 创建Treeview
        columns = ('project', 'status', 'segments', 'time')
        self.task_tree = ttk.Treeview(list_frame, columns=columns, show='tree headings',
                                      height=8, selectmode='extended')  # 支持多选

        # 设置列标题
        self.task_tree.heading('#0', text='任务ID')
        self.task_tree.heading('project', text='项目组成')
        self.task_tree.heading('status', text='状态')
        self.task_tree.heading('segments', text='进度')
        self.task_tree.heading('time', text='创建时间')

        # 设置列宽
        self.task_tree.column('#0', width=80, minwidth=60)
        self.task_tree.column('project', width=200, minwidth=150)
        self.task_tree.column('status', width=80, minwidth=60)
        self.task_tree.column('segments', width=120, minwidth=100)
        self.task_tree.column('time', width=140, minwidth=120)

        # 添加滚动条
        scrollbar_y = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.task_tree.yview)
        self.task_tree.configure(yscrollcommand=scrollbar_y.set)

        # 布局
        self.task_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)

        # 绑定选择事件
        self.task_tree.bind('<<TreeviewSelect>>', self.on_task_select)
        self.task_tree.bind('<Double-1>', self.on_task_double_click)

        # 绑定左键点击事件（用于自定义shift多选）
        self.task_tree.bind('<Button-1>', self.on_left_click)

        # 绑定右键菜单
        self.task_tree.bind('<Button-3>', self.show_context_menu)  # Windows/Linux
        self.task_tree.bind('<Button-2>', self.show_context_menu)  # macOS

        # 创建右键菜单
        self.create_context_menu()

    def create_context_menu(self):
        """创建右键菜单"""
        self.context_menu = tk.Menu(self.dialog, tearoff=0)

        # 添加菜单项
        self.context_menu.add_command(label="置顶", command=self.move_to_top)
        self.context_menu.add_command(label="置底", command=self.move_to_bottom)
        self.context_menu.add_command(label="删除任务", command=self.remove_selected_tasks)
        self.context_menu.add_command(label="输出目录", command=self.open_output_directory)

    def show_context_menu(self, event):
        """显示右键菜单"""
        # 获取鼠标点击位置的任务
        item = self.task_tree.identify_row(event.y)
        if item:
            # 只有在该项未被选中时才选中它（保持多选状态）
            if item not in self.task_tree.selection():
                self.task_tree.selection_set(item)
            self.selected_task_id = item

            # 获取任务对象，根据状态启用/禁用菜单项
            task = self.queue.get_task(item)
            if task:
                # 检查是否可以置顶/置底
                current_index = self.queue.tasks.index(task)
                if current_index == 0:
                    self.context_menu.entryconfig("置顶", state="disabled")
                else:
                    self.context_menu.entryconfig("置顶", state="normal")

                if current_index == len(self.queue.tasks) - 1:
                    self.context_menu.entryconfig("置底", state="disabled")
                else:
                    self.context_menu.entryconfig("置底", state="normal")

            # 显示菜单
            try:
                self.context_menu.tk_popup(event.x_root, event.y_root)
            finally:
                self.context_menu.grab_release()

    def create_progress_panel(self, parent):
        """创建进度面板"""
        progress_frame = ttk.LabelFrame(parent, text="当前任务进度", padding=5)
        progress_frame.pack(fill=tk.X, pady=(0, 10))

        # 进度条
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=(0, 5))

        # 进度信息
        progress_info = ttk.Frame(progress_frame)
        progress_info.pack(fill=tk.X)

        self.progress_label = ttk.Label(progress_info, text="进度: 0%")
        self.progress_label.pack(side=tk.LEFT)

        self.current_task_label = ttk.Label(progress_info, text="当前任务: 无")
        self.current_task_label.pack(side=tk.RIGHT)

    def create_log_panel(self, parent):
        """创建日志面板"""
        log_frame = ttk.LabelFrame(parent, text="处理日志", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True)

        # 日志文本框和滚动条
        log_container = ttk.Frame(log_frame)
        log_container.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(log_container)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.log_text = tk.Text(log_container, height=15, wrap=tk.WORD, yscrollcommand=scrollbar.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.log_text.yview)

        # 设置只读
        self.log_text.config(state='disabled')

    # ========== 处理器回调设置 ==========

    def setup_processor_callbacks(self):
        """设置处理器回调函数"""
        self.processor.on_task_start = self.on_task_start
        self.processor.on_task_complete = self.on_task_complete
        self.processor.on_task_failed = self.on_task_failed
        self.processor.on_segment_complete = self.on_segment_complete
        self.processor.on_progress_update = self.on_progress_update
        self.processor.on_status_change = self.on_status_change
        self.processor.on_log_message = self.on_log_message  # 新增：日志消息回调
        self.processor.on_all_tasks_complete = self.on_all_tasks_complete  # 新增：所有任务完成回调

    def on_task_start(self, task):
        """任务开始回调"""
        self.log_message(f"[{task.project_name}] 开始处理 ({task.total_segments}个片段)")

    def on_task_complete(self, task):
        """任务完成回调"""
        elapsed = self.format_time_duration(task.elapsed_time) if task.elapsed_time else "未知"
        self.log_message(f"✓ [{task.project_name}] 处理完成 (耗时: {elapsed})")

    def on_task_failed(self, task, error_msg):
        """任务失败回调"""
        self.log_message(f"✗ [{task.project_name}] 处理失败: {error_msg}")

    def on_segment_complete(self, task, segment):
        """片段完成回调"""
        self.log_message(f"  ✓ 片段 {segment.segment_id} 处理完成")
        # 立即更新统计信息，实现片段进度的实时更新
        self.update_stats()

    def on_progress_update(self, task, progress):
        """进度更新回调"""
        # 进度更新不记录日志，避免刷屏
        pass

    def on_status_change(self, status):
        """处理器状态变化回调"""
        self.log_message(f"处理器状态: {status}")

    def on_log_message(self, task, message):
        """日志消息回调 - 接收来自导出过程的详细日志"""
        # 直接显示消息，不添加任务名称前缀（因为消息本身已经包含足够的上下文）
        self.log_message(message)

    def on_all_tasks_complete(self):
        """所有任务完成回调"""
        try:
            # 获取统计信息
            stats = self.queue.get_statistics()
            completed_count = stats.get('completed', 0)
            failed_count = stats.get('failed', 0)

            # 构建提示消息
            if failed_count == 0:
                # 全部成功
                title = "✓ 队列处理完成"
                message = f"所有任务已完成！\n\n共处理 {completed_count} 个任务，全部成功。"
                self.log_message(f"✓✓✓ 所有任务已完成！共 {completed_count} 个任务，全部成功 ✓✓✓")
            else:
                # 有失败任务
                title = "队列处理完成"
                message = f"所有任务已完成！\n\n成功: {completed_count} 个\n失败: {failed_count} 个"
                self.log_message(f"所有任务已完成！成功: {completed_count} 个，失败: {failed_count} 个")

            # 使用 after 确保在主线程中显示对话框
            self.dialog.after(0, lambda: messagebox.showinfo(title, message, parent=self.dialog))

        except Exception as e:
            print(f"显示完成提示失败: {e}")

    # ========== 事件处理方法 ==========

    def on_left_click(self, event):
        """左键点击事件 - 处理shift多选"""
        # 获取点击的项目
        item = self.task_tree.identify_row(event.y)
        if not item:
            return

        # 检查是否按下shift键
        if event.state & 0x0001:  # Shift键被按下
            # 如果有上一次点击的项目，执行范围选择
            if self.last_clicked_item and self.last_clicked_item != item:
                # 获取所有项目
                all_items = self.task_tree.get_children()

                # 找到两个项目的索引
                try:
                    start_idx = all_items.index(self.last_clicked_item)
                    end_idx = all_items.index(item)

                    # 确保start_idx <= end_idx
                    if start_idx > end_idx:
                        start_idx, end_idx = end_idx, start_idx

                    # 选中范围内的所有项目
                    items_to_select = all_items[start_idx:end_idx + 1]
                    self.task_tree.selection_set(items_to_select)

                    # 阻止默认行为
                    return "break"
                except ValueError:
                    pass
        else:
            # 普通点击，记录这次点击的项目
            self.last_clicked_item = item

    def on_task_select(self, event):
        """任务选择事件"""
        selection = self.task_tree.selection()
        if selection:
            # 使用 iid（item id）作为任务ID
            item_id = selection[0]
            self.selected_task_id = item_id
        else:
            self.selected_task_id = None

    def on_task_double_click(self, event):
        """任务双击事件 - 显示详细信息"""
        selection = self.task_tree.selection()
        if selection:
            # 使用 iid（item id）作为任务ID
            item_id = selection[0]
            self.show_task_details(item_id)

    def show_task_details(self, task_id: str):
        """显示任务详细信息"""
        task = self.queue.get_task(task_id)
        if not task:
            return

        # 创建详细信息对话框
        details_dialog = tk.Toplevel(self.dialog)
        details_dialog.title(f"任务详情 - {task.project_name}")
        details_dialog.geometry("600x500")
        details_dialog.resizable(True, True)

        # 设置窗口图标
        try:
            from icon_manager import set_window_icon
            set_window_icon(details_dialog)
        except ImportError:
            pass

        # 居中显示
        details_dialog.update_idletasks()
        width = details_dialog.winfo_width()
        height = details_dialog.winfo_height()
        x = (self.dialog.winfo_x() + (self.dialog.winfo_width() - width) // 2)
        y = (self.dialog.winfo_y() + (self.dialog.winfo_height() - height) // 2)
        details_dialog.geometry(f"{width}x{height}+{x}+{y}")

        # 内容框架（无滚动条）
        content_frame = ttk.Frame(details_dialog, padding=10)
        content_frame.pack(fill=tk.BOTH, expand=True)

        # 基本信息标题
        info_title = ttk.Label(content_frame, text="基本信息", font=("", 10, "bold"))
        info_title.pack(anchor=tk.W, pady=(0, 5))

        # 基本信息内容（无边框）
        info_frame = ttk.Frame(content_frame, padding=5)
        info_frame.pack(fill=tk.X, pady=(0, 15))

        # 计算实际运行时间
        actual_runtime = "-"
        if task.start_time and task.end_time:
            try:
                start_dt = datetime.strptime(task.start_time, "%Y-%m-%d %H:%M:%S")
                end_dt = datetime.strptime(task.end_time, "%Y-%m-%d %H:%M:%S")
                runtime_seconds = (end_dt - start_dt).total_seconds()
                actual_runtime = self.format_time_duration(runtime_seconds)
            except:
                actual_runtime = "-"
        elif task.start_time and task.status == TaskStatus.PROCESSING:
            # 任务正在处理中，显示当前已用时间
            try:
                start_dt = datetime.strptime(task.start_time, "%Y-%m-%d %H:%M:%S")
                runtime_seconds = (datetime.now() - start_dt).total_seconds()
                actual_runtime = self.format_time_duration(runtime_seconds) + " (处理中)"
            except:
                actual_runtime = "-"

        # 优化视频路径显示
        # - 单项目：显示实际视频路径
        # - 跨项目：显示 [跨项目]
        video_path_display = "[跨项目]" if task.is_cross_project else task.video_path

        info_items = [
            ("任务ID", task.task_id),
            ("项目名称", task.project_name),
            ("视频路径", video_path_display),
            ("任务状态", task.status.value),
            ("创建时间", task.create_time),
            ("开始时间", task.start_time or "-"),
            ("结束时间", task.end_time or "-"),
            ("实际运行时间", actual_runtime)
        ]

        for label, value in info_items:
            row = ttk.Frame(info_frame)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=f"{label}:", width=15, anchor=tk.W).pack(side=tk.LEFT)
            ttk.Label(row, text=value, wraplength=430, anchor=tk.W, justify=tk.LEFT).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 导出配置
        if task.config:
            # 导出配置标题
            config_title = ttk.Label(content_frame, text="导出配置", font=("", 10, "bold"))
            config_title.pack(anchor=tk.W, pady=(0, 5))

            # 导出配置内容（无边框）
            config_frame = ttk.Frame(content_frame, padding=5)
            config_frame.pack(fill=tk.X, pady=(0, 10))

            # 命名方式映射
            naming_mode_map = {
                "sequence": "按序号",
                "sequence_subtitle": "按序号+字幕"
            }

            # 获取实际输出路径：优先使用完整路径(output_base_dir)，否则使用配置路径
            actual_output_dir = task.output_base_dir if task.output_base_dir else task.config.output_dir

            # 导出模式显示
            # 标准模式/重新编码 + 切片切割/连续切割
            copy_mode = "标准模式" if task.config.fast_copy_mode else "重新编码"
            cut_mode = "连续切割" if task.config.continuous_cut_mode else "切片切割"
            export_mode = f"{copy_mode} + {cut_mode}"

            config_items = [
                ("导出模式", export_mode),
                ("分割命名方式", naming_mode_map.get(task.config.naming_mode, task.config.naming_mode)),
                ("编码预设", task.config.encoding_preset),
                ("CRF参数", str(task.config.crf)),
                ("目标分辨率", task.config.target_resolution or "保持原分辨率"),
                ("目标帧率", f"{task.config.target_fps} fps" if task.config.target_fps else "保持原帧率"),
                ("输出路径", actual_output_dir)
            ]

            for label, value in config_items:
                row = ttk.Frame(config_frame)
                row.pack(fill=tk.X, pady=2)
                ttk.Label(row, text=f"{label}:", width=12, anchor=tk.W).pack(side=tk.LEFT)
                ttk.Label(row, text=value, wraplength=450, anchor=tk.W, justify=tk.LEFT).pack(side=tk.LEFT, fill=tk.X, expand=True)

    # ========== 批量选择方法 ==========

    def select_all(self):
        """全选所有任务"""
        all_items = self.task_tree.get_children()
        if all_items:
            self.task_tree.selection_set(all_items)
            self.log_message(f"已选中全部 {len(all_items)} 个任务")

    def deselect_all(self):
        """取消全选"""
        self.task_tree.selection_remove(self.task_tree.get_children())
        self.log_message("已取消全部选中")

    def invert_selection(self):
        """反选"""
        all_items = self.task_tree.get_children()
        selected_items = set(self.task_tree.selection())

        # 反选：选中的变未选中，未选中的变选中
        new_selection = [item for item in all_items if item not in selected_items]

        self.task_tree.selection_set(new_selection)
        self.log_message(f"已反选，当前选中 {len(new_selection)} 个任务")

    # ========== 队列控制方法 ==========

    def start_queue(self):
        """开始处理队列"""
        try:
            if not self.processor.is_running:
                self.processor.start()
                self.log_message("队列处理已开始")
            else:
                self.log_message("队列正在运行中")
        except Exception as e:
            self.log_message(f"启动队列失败: {e}")
            messagebox.showerror("错误", f"启动队列失败: {e}", parent=self.dialog)


    def stop_queue(self):
        """停止处理队列"""
        try:
            if self.processor.is_running:
                # 弹出确认对话框
                result = messagebox.askyesno(
                    "确认停止",
                    "⚠️  当前任务正在处理中，\n停止后进度将丢失，是否继续？",
                    parent=self.dialog
                )

                if result:
                    # 用户点击"是"，停止队列
                    # 获取当前正在处理的任务
                    processing_tasks = self.queue.get_tasks_by_status(TaskStatus.PROCESSING)

                    # 停止处理器
                    self.processor.stop()
                    self.log_message("队列处理已停止")

                    # 清理部分生成的文件
                    for task in processing_tasks:
                        self._cleanup_task_output(task)
                        # 将任务状态改回PENDING
                        task.status = TaskStatus.PENDING
                        task.start_time = None
                        task.processed_segments = 0
                        task.progress_percentage = 0.0
                        # 重置片段状态
                        for seg in task.segments:
                            if not seg.error_message:  # 保留失败的片段状态
                                seg.is_processed = False
                                seg.output_path = None

                    self.update_display()
                # 用户点击"否"，取消操作
            else:
                self.log_message("队列未在运行")
        except Exception as e:
            self.log_message(f"停止队列失败: {e}")
            messagebox.showerror("错误", f"停止队列失败: {e}", parent=self.dialog)

    def _cleanup_task_output(self, task):
        """清理任务的部分输出文件

        Args:
            task: 要清理的任务
        """
        try:
            if not task.config or not task.config.output_dir:
                return

            output_dir = task.config.output_dir

            if os.path.exists(output_dir):
                # 获取输出目录中的所有文件
                import glob
                files = glob.glob(os.path.join(output_dir, "*"))

                # 删除所有文件
                for file_path in files:
                    try:
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                            self.log_message(f"已删除文件: {os.path.basename(file_path)}")
                    except Exception as e:
                        self.log_message(f"删除文件失败 {os.path.basename(file_path)}: {e}")

                # 如果目录为空，删除目录
                if not os.listdir(output_dir):
                    try:
                        os.rmdir(output_dir)
                        self.log_message(f"已删除空目录: {output_dir}")
                    except Exception as e:
                        self.log_message(f"删除目录失败: {e}")

        except Exception as e:
            self.log_message(f"清理输出文件失败: {e}")

    def remove_selected_tasks(self):
        """删除选中的任务（支持批量删除）"""
        selected_items = self.task_tree.selection()

        if not selected_items:
            messagebox.showwarning("警告", "请先选择要删除的任务", parent=self.dialog)
            return

        # 总是弹出确认对话框
        task_count = len(selected_items)
        if task_count == 1:
            confirm_msg = f"确定要删除选中的 1 个任务吗？"
        else:
            confirm_msg = f"确定要删除选中的 {task_count} 个任务吗？"

        if messagebox.askyesno("确认删除", confirm_msg, parent=self.dialog):
            success_count = 0
            for task_id in selected_items:
                if self.queue.remove_task(task_id):
                    success_count += 1

            if success_count > 0:
                self.log_message(f"已删除 {success_count} 个任务")
                self.update_display()

            if success_count < task_count:
                messagebox.showwarning("警告", f"有 {task_count - success_count} 个任务删除失败", parent=self.dialog)

    def move_task_up(self):
        """上移任务"""
        if not self.selected_task_id:
            messagebox.showwarning("警告", "请先选择要移动的任务", parent=self.dialog)
            return

        # 找到当前索引
        current_index = -1
        for i, task in enumerate(self.queue.tasks):
            if task.task_id == self.selected_task_id:
                current_index = i
                break

        if current_index > 0:
            if self.queue.move_task(self.selected_task_id, current_index - 1):
                self.log_message(f"已上移任务: {self.selected_task_id[:8]}...")
                self.update_display()
                # 保持选中状态
                self._restore_selection(self.selected_task_id)

    def move_task_down(self):
        """下移任务"""
        if not self.selected_task_id:
            messagebox.showwarning("警告", "请先选择要移动的任务", parent=self.dialog)
            return

        # 找到当前索引
        current_index = -1
        for i, task in enumerate(self.queue.tasks):
            if task.task_id == self.selected_task_id:
                current_index = i
                break

        if current_index >= 0 and current_index < len(self.queue.tasks) - 1:
            if self.queue.move_task(self.selected_task_id, current_index + 1):
                self.log_message(f"已下移任务: {self.selected_task_id[:8]}...")
                self.update_display()
                # 保持选中状态
                self._restore_selection(self.selected_task_id)

    def clear_completed(self):
        """清空已完成的任务"""
        if not self.queue.get_tasks_by_status(TaskStatus.COMPLETED):
            messagebox.showinfo("信息", "没有已完成的任务", parent=self.dialog)
            return

        if messagebox.askyesno("确认清空", "确定要清空所有已完成的任务吗？", parent=self.dialog):
            self.queue.clear_completed()
            self.log_message("已清空所有已完成的任务")
            self.update_display()

    def clear_all(self):
        """清空所有任务"""
        if not self.queue.tasks:
            messagebox.showinfo("信息", "队列为空", parent=self.dialog)
            return

        if messagebox.askyesno("确认清空", "确定要清空所有任务吗？\n注意：这将删除所有任务，包括正在处理的任务！", parent=self.dialog):
            # 停止处理器
            if self.processor.is_running:
                self.processor.stop()

            # 清空队列
            self.queue.tasks.clear()
            self.log_message("已清空所有任务")
            self.update_display()

    def move_to_top(self):
        """置顶任务"""
        if not self.selected_task_id:
            messagebox.showwarning("警告", "请先选择要置顶的任务", parent=self.dialog)
            return

        # 找到当前索引
        current_index = -1
        for i, task in enumerate(self.queue.tasks):
            if task.task_id == self.selected_task_id:
                current_index = i
                break

        if current_index > 0:
            if self.queue.move_task(self.selected_task_id, 0):
                self.log_message(f"已置顶任务: {self.selected_task_id[:8]}...")
                self.update_display()
                self._restore_selection(self.selected_task_id)
        else:
            messagebox.showinfo("提示", "该任务已在顶部", parent=self.dialog)

    def move_to_bottom(self):
        """置底任务"""
        if not self.selected_task_id:
            messagebox.showwarning("警告", "请先选择要置底的任务", parent=self.dialog)
            return

        # 找到当前索引
        current_index = -1
        for i, task in enumerate(self.queue.tasks):
            if task.task_id == self.selected_task_id:
                current_index = i
                break

        last_index = len(self.queue.tasks) - 1
        if current_index >= 0 and current_index < last_index:
            if self.queue.move_task(self.selected_task_id, last_index):
                self.log_message(f"已置底任务: {self.selected_task_id[:8]}...")
                self.update_display()
                self._restore_selection(self.selected_task_id)
        else:
            messagebox.showinfo("提示", "该任务已在底部", parent=self.dialog)


    def open_output_directory(self):
        """打开输出目录"""
        if not self.selected_task_id:
            messagebox.showwarning("警告", "请先选择任务", parent=self.dialog)
            return

        task = self.queue.get_task(self.selected_task_id)
        if not task:
            messagebox.showerror("错误", "任务不存在", parent=self.dialog)
            return

        # 获取输出目录：优先使用完整路径(output_base_dir)，否则使用配置路径
        output_dir = task.output_base_dir if task.output_base_dir else (task.config.output_dir if task.config else None)

        if not output_dir:
            messagebox.showwarning("警告", "该任务没有设置输出目录", parent=self.dialog)
            return

        # 检查目录是否存在
        if not os.path.exists(output_dir):
            result = messagebox.askyesno(
                "目录不存在",
                f"输出目录不存在：\n{output_dir}\n\n是否创建该目录？",
                parent=self.dialog
            )

            if result:
                try:
                    os.makedirs(output_dir, exist_ok=True)
                    self.log_message(f"已创建输出目录: {output_dir}")
                except Exception as e:
                    messagebox.showerror("错误", f"创建目录失败: {e}", parent=self.dialog)
                    return
            else:
                return

        # 打开目录
        try:
            import subprocess
            if os.name == 'nt':  # Windows
                os.startfile(output_dir)
            elif os.name == 'posix':  # macOS, Linux
                subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', output_dir])

            self.log_message(f"已打开输出目录: {output_dir}")
        except Exception as e:
            messagebox.showerror("错误", f"无法打开目录: {e}", parent=self.dialog)

    # ========== 显示更新方法 ==========

    def update_display(self):
        """更新显示"""
        try:
            # 更新统计信息
            self.update_stats()

            # 更新任务列表
            self.update_task_list()

            # 更新进度
            self.update_progress()

        except Exception as e:
            print(f"更新显示失败: {e}")

    def update_stats(self):
        """更新统计信息"""
        try:
            stats = self.queue.get_statistics()

            self.total_label.config(text=f"总任务数: {stats['total']}")
            self.pending_label.config(text=f"等待中: {stats['pending']}")
            self.processing_label.config(text=f"处理中: {stats['processing']}")
            self.completed_label.config(text=f"已完成: {stats['completed']}")
            self.failed_label.config(text=f"失败: {stats['failed']}")

            # 智能显示片段进度：根据当前处理任务的模式决定显示格式
            processing_tasks = self.queue.get_tasks_by_status(TaskStatus.PROCESSING)
            if processing_tasks:
                # 如果有正在处理的任务，根据第一个任务的模式显示
                current_task = processing_tasks[0]
                if current_task.config and current_task.config.continuous_cut_mode:
                    # 连续切割模式：显示百分比（整数）
                    self.segments_label.config(text=f"片段进度: {int(current_task.progress_percentage)}%")
                else:
                    # 切片切割模式：显示片段数
                    actual_processed = sum(1 for seg in current_task.segments if seg.is_processed)
                    self.segments_label.config(text=f"片段进度: {actual_processed}/{current_task.total_segments}")
            else:
                # 没有正在处理的任务，显示总体统计
                self.segments_label.config(text=f"片段进度: {stats['processed_segments']}/{stats['total_segments']}")

            # 更新时间统计
            self.update_time_stats()

        except Exception as e:
            print(f"更新统计信息失败: {e}")

    def update_time_stats(self):
        """更新时间统计"""
        try:
            # 计算预计总时间
            total_estimated = 0
            total_elapsed = 0
            total_remaining = 0

            for task in self.queue.tasks:
                # 计算每个任务的预计时间
                if task.status == TaskStatus.PENDING or task.status == TaskStatus.PROCESSING:
                    # 使用简化的预估公式
                    task_estimated = self.calculate_task_estimated_time(task)
                    total_estimated += task_estimated

                    # 已用时间：只有正在处理的任务才计算实时已用时间
                    if task.status == TaskStatus.PROCESSING and task.start_time:
                        try:
                            start_dt = datetime.strptime(task.start_time, "%Y-%m-%d %H:%M:%S")
                            elapsed = (datetime.now() - start_dt).total_seconds()
                            total_elapsed += elapsed

                            # 剩余时间 = 预计时间 - 已用时间
                            remaining = max(0, task_estimated - elapsed)
                            total_remaining += remaining
                        except:
                            pass
                    else:
                        # 待处理任务的剩余时间就是预计时间
                        total_remaining += task_estimated

                # 累加所有已完成任务的处理时间
                elif task.status == TaskStatus.COMPLETED:
                    if task.elapsed_time:
                        total_elapsed += task.elapsed_time

            # 更新显示
            if total_estimated > 0:
                self.estimated_time_label.config(text=f"预计时间: {self.format_time_duration(total_estimated)}")
            else:
                self.estimated_time_label.config(text="预计时间: --")

            if total_elapsed > 0:
                self.elapsed_time_label.config(text=f"已用时间: {self.format_time_duration(total_elapsed)}")
            else:
                self.elapsed_time_label.config(text="已用时间: --")

            if total_remaining > 0:
                self.remaining_time_label.config(text=f"剩余时间: {self.format_time_duration(total_remaining)}")
            else:
                self.remaining_time_label.config(text="剩余时间: --")

        except Exception as e:
            print(f"更新时间统计失败: {e}")

    def calculate_task_estimated_time(self, task):
        """计算单个任务的预计时间"""
        try:
            # 计算总时长
            total_duration = sum(seg.end_time - seg.start_time for seg in task.segments)

            # 使用简化的预估公式（参考 IntegratedExportDialog）
            # 1. 视频加载时间
            loading_time = 12

            # 2. 编码时间（使用默认速度因子）
            preset = task.config.encoding_preset if task.config else "veryfast"
            preset_speeds = {
                "ultrafast": 0.35,
                "superfast": 0.45,
                "veryfast": 0.55,
                "faster": 0.75,
                "fast": 0.95,
                "medium": 1.25,
                "slow": 1.9,
                "slower": 2.8,
                "veryslow": 4.2
            }
            speed_factor = preset_speeds.get(preset, 0.55)
            encoding_time = total_duration * speed_factor

            # 3. 合并时间
            merge_time = 8

            # 4. 总时间（加20%缓冲）
            total_time = (loading_time + encoding_time + merge_time) * 1.2

            return total_time

        except Exception as e:
            print(f"计算任务预计时间失败: {e}")
            return 0

    def format_time_duration(self, seconds):
        """格式化时间显示"""
        if seconds < 60:
            return f"{int(seconds)}秒"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}分{secs}秒"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            return f"{hours}时{minutes}分{secs}秒"

    def update_task_list(self):
        """更新任务列表"""
        try:
            # 保存当前选中的所有任务ID（支持多选）
            current_selection = self.task_tree.selection()
            selected_task_ids = list(current_selection) if current_selection else []

            # 清空现有项目
            for item in self.task_tree.get_children():
                self.task_tree.delete(item)

            # 添加任务
            for task in self.queue.tasks:
                # 状态映射
                status_map = {
                    TaskStatus.PENDING: "等待中",
                    TaskStatus.PROCESSING: "处理中",
                    TaskStatus.COMPLETED: "已完成",
                    TaskStatus.FAILED: "失败",
                    TaskStatus.PAUSED: "暂停"
                }

                status_text = status_map.get(task.status, task.status.value)

                # 格式化时间
                create_time = task.create_time[:16] if task.create_time else ""

                # 实时统计该任务中已处理的片段数（与队列统计栏逻辑一致）
                actual_processed = sum(1 for seg in task.segments if seg.is_processed)

                # 根据是否跨项目显示项目组成
                project_composition = "跨项目" if task.is_cross_project else "单项目"

                # 智能进度显示：根据切割模式显示不同格式
                # - 连续切割模式(continuous_cut_mode=True)：显示百分比 (50.0%)
                # - 切片切割模式(continuous_cut_mode=False)：显示片段数 (3/4)
                if task.config and task.config.continuous_cut_mode:
                    # 连续切割：只显示百分比
                    progress_text = f"{task.progress_percentage:.1f}%"
                else:
                    # 切片切割：显示片段数
                    progress_text = f"{actual_processed}/{task.total_segments}"

                # 插入项目 - 使用 iid 参数指定任务ID，text 参数显示任务ID
                item_id = self.task_tree.insert(
                    '', 'end',
                    iid=task.task_id,  # 使用完整任务ID作为item id
                    text=task.task_id[:8] + "...",  # 在第一列显示缩短的任务ID
                    values=(
                        project_composition,  # 显示"跨项目"或"单项目"
                        status_text,
                        progress_text,  # 智能显示进度
                        create_time
                    )
                )

                # 设置标签颜色（通过tag方式）
                if task.status == TaskStatus.FAILED:
                    self.task_tree.item(item_id, tags=('failed',))
                elif task.status == TaskStatus.COMPLETED:
                    self.task_tree.item(item_id, tags=('completed',))
                elif task.status == TaskStatus.PROCESSING:
                    self.task_tree.item(item_id, tags=('processing',))

            # 配置标签样式
            self.task_tree.tag_configure('failed', foreground='red')
            self.task_tree.tag_configure('completed', foreground='green')
            self.task_tree.tag_configure('processing', foreground='blue')

            # 恢复之前的选中状态（支持多选）
            if selected_task_ids:
                for task_id in selected_task_ids:
                    if self.task_tree.exists(task_id):
                        self.task_tree.selection_add(task_id)
                # 滚动到第一个选中的任务
                if self.task_tree.exists(selected_task_ids[0]):
                    self.task_tree.see(selected_task_ids[0])

        except Exception as e:
            print(f"更新任务列表失败: {e}")

    def update_progress(self):
        """更新按钮状态"""
        try:
            # 找到正在处理的任务
            processing_tasks = self.queue.get_tasks_by_status(TaskStatus.PROCESSING)

            # 更新开始/停止按钮状态和文本
            if processing_tasks:
                # 处理中：开始按钮改为"处理中..."并禁用，停止按钮启用
                self.start_button.config(text="处理中...", state='disabled')
                self.stop_button.config(state='normal')
            else:
                # 未处理：开始按钮恢复文本并启用，停止按钮禁用
                self.start_button.config(text="开始处理", state='normal')
                self.stop_button.config(state='normal')  # 保持启用状态

            # 检查多选状态，控制移动按钮
            selected_items = self.task_tree.selection()
            if len(selected_items) > 1:
                # 多选时禁用移动按钮
                self.move_up_button.config(state='disabled')
                self.move_down_button.config(state='disabled')
            else:
                # 单选或无选择时启用移动按钮
                self.move_up_button.config(state='normal')
                self.move_down_button.config(state='normal')

        except Exception as e:
            print(f"更新按钮状态失败: {e}")

    def _restore_selection(self, task_id: str):
        """恢复任务选中状态

        Args:
            task_id: 要选中的任务ID
        """
        try:
            # 检查任务是否仍在树中
            if self.task_tree.exists(task_id):
                # 选中该任务
                self.task_tree.selection_set(task_id)
                # 确保任务可见（滚动到视图中）
                self.task_tree.see(task_id)
        except Exception as e:
            print(f"恢复选中状态失败: {e}")

    def log_message(self, message: str):
        """添加日志消息"""
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_entry = f"[{timestamp}] {message}\n"

            self.log_text.config(state='normal')
            self.log_text.insert(tk.END, log_entry)
            self.log_text.see(tk.END)
            self.log_text.config(state='disabled')

            # 限制日志行数
            lines = int(self.log_text.index('end-1c').split('.')[0])
            if lines > 1000:  # 最多保留1000行
                self.log_text.config(state='normal')
                self.log_text.delete('1.0', '2.0')
                self.log_text.config(state='disabled')

        except Exception as e:
            print(f"添加日志失败: {e}")

    # ========== 定时器方法 ==========

    def start_update_timer(self):
        """启动更新定时器"""
        self.update_timer = self.dialog.after(1000, self.update_timer_callback)  # 每秒更新

    def update_timer_callback(self):
        """定时器回调"""
        if not self.is_closing:
            self.update_display()
            self.start_update_timer()  # 重新设置定时器

    def stop_update_timer(self):
        """停止更新定时器"""
        if self.update_timer:
            self.dialog.after_cancel(self.update_timer)
            self.update_timer = None

    # ========== 窗口管理方法 ==========

    def on_close(self):
        """窗口关闭事件"""
        if self.processor.is_running:
            # 有任务在运行，询问用户是否关闭
            result = messagebox.askyesno(
                "确认关闭",
                "队列正在处理中，确定要关闭窗口吗？\n\n"
                "点击「是」：关闭窗口，队列继续在后台运行\n"
                "点击「否」：取消关闭，窗口保持打开",
                parent=self.dialog
            )

            if result:
                # 用户点击"是"，关闭窗口
                self.close_window()
            # 用户点击"否"，什么都不做，窗口保持打开状态
        else:
            # 没有任务运行，直接关闭
            self.close_window()

    def close_window(self):
        """关闭窗口"""
        self.is_closing = True
        self.stop_update_timer()

        # 调用关闭回调
        if self.on_finished:
            self.on_finished()

        self.dialog.destroy()

    def exec_(self):
        """显示模态对话框（兼容PyQt5接口）"""
        if self.parent:
            self.dialog.transient(self.parent)
        self.dialog.grab_set()
        self.dialog.wait_window()

    def show(self):
        """显示非模态对话框"""
        self.dialog.deiconify()
        self.dialog.lift()

    def finished(self, callback: Callable):
        """设置完成回调"""
        self.on_finished = callback