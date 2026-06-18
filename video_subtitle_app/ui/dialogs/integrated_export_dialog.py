#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
集成导出对话框 - 完全复用外部脚本的功能和界面
直接集成 cut_video_audio_subs_v0.3.py 的所有逻辑
"""

import os
import re
import pysrt
import subprocess
import time
import threading
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from datetime import timedelta
from glob import glob
# 不再使用MoviePy，改用FFmpeg直接切割
from pathlib import Path
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from database.models import SubtitleSegment
from core.script_adapter import script_adapter
from utils.file_utils import FileUtils
from utils import custom_messagebox
from utils.power_manager import PowerManager

# 导入并行处理函数
try:
    from core.enhanced_exporter import calculate_optimal_workers
    PARALLEL_PROCESSING_AVAILABLE = True
except ImportError:
    PARALLEL_PROCESSING_AVAILABLE = False

# 导入图标管理器
try:
    from icon_manager import set_window_icon
    ICON_AVAILABLE = True
except ImportError:
    ICON_AVAILABLE = False
    def set_window_icon(window):
        pass

#  方案B：导入智能校验系统
try:
    from core.export_with_validation import export_validator, create_validation_config, ValidationConfig
    from core.smart_timeline_validator import smart_validator
    SMART_VALIDATION_AVAILABLE = True
    print(" 方案B智能校验系统已加载")
except ImportError as e:
    print(f"[WARN] 方案B智能校验系统导入失败，将使用方案6: {e}")
    SMART_VALIDATION_AVAILABLE = False


class IntegratedExportDialog:
    """集成导出对话框 - 直接复用外部脚本的所有功能"""
    
    def __init__(self, parent, segments: List[SubtitleSegment]):
        self.parent = parent
        self.segments = segments
        self.result = None
        
        # 从外部脚本复制的变量
        self.progress_var = tk.DoubleVar()
        self.progress_percent_var = tk.StringVar(value="0%")
        self.preset_var = tk.StringVar(value="veryfast")
        self.crf_var = tk.StringVar(value="24")
        self.naming_mode = tk.StringVar(value="index")
        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()

        # 导出模式变量
        self.export_mode_var = tk.StringVar(value="reencode")  # fast 或 reencode（默认使用重新编码）

        # 重新编码参数
        self.resolution_var = tk.StringVar(value="1920x1080")
        self.fps_var = tk.StringVar(value="25")

        # 连续切割模式变量
        self.continuous_cut_var = tk.BooleanVar(value=False)  # 默认不勾选，使用片段切割

        # 控制变量
        self.is_processing = False
        self.cancel_flag = False

        # 按钮引用
        self.start_button = None

        # 时间统计变量
        self.estimated_time_var = tk.StringVar(value="计算中...")
        self.actual_time_var = tk.StringVar(value="未开始")
        self.start_time = None
        self.time_update_thread = None
        self.time_update_running = False

        #  方案B：初始化智能校验系统
        if SMART_VALIDATION_AVAILABLE:
            self.smart_validation_enabled = True
            self.validation_config = create_validation_config(
                enabled=True,
                auto_correct=True,
                validation_level="standard"
            )
            print(" 方案B智能校验系统已初始化")
        else:
            self.smart_validation_enabled = False
            print("使用方案6稳定精准技术（片段级时长计算）")

        # 准备数据
        self.project_info = script_adapter.get_project_info(segments)
        if not self.project_info:
            messagebox.showerror("错误", "无法获取项目信息")
            return
        
        self.create_dialog()
    
    def create_dialog(self):
        """创建对话框 - 完全复用外部脚本的界面"""
        # 获取 Tkinter 根窗口
        # parent 可能是 MainWindow 实例或 Tkinter 窗口
        if hasattr(self.parent, 'root'):
            # parent 是 MainWindow 实例
            parent_window = self.parent.root
        else:
            # parent 是 Tkinter 窗口
            parent_window = self.parent

        self.dialog = tk.Toplevel(parent_window)
        self.dialog.title(f"导出片段 - {self.project_info['project_name']}")
        self.dialog.geometry("700x650")
        self.dialog.resizable(True, True)

        # 不使用模态窗口设置，允许窗口自由最小化和切换
        # self.dialog.transient(parent_window)  # 会隐藏最小化按钮
        # self.dialog.grab_set()  # 会阻止窗口最小化，导出任务时间长，应允许用户最小化窗口

        # 设置窗口图标
        if ICON_AVAILABLE:
            set_window_icon(self.dialog)

        # 居中显示
        self.center_dialog()

        # 创建内容 - 直接复用外部脚本的界面布局
        self.create_content()

        # 绑定事件
        self.dialog.protocol("WM_DELETE_WINDOW", self.on_close)
    
    def center_dialog(self):
        """居中显示对话框"""
        self.dialog.update_idletasks()
        width = self.dialog.winfo_width()
        height = self.dialog.winfo_height()
        x = (self.dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (height // 2)
        self.dialog.geometry(f"{width}x{height}+{x}+{y}")
    
    def create_content(self):
        """创建对话框内容 - 完全复用外部脚本的界面"""
        # 输入输出路径设置
        self.create_path_settings()

        # 参数设置
        self.create_parameter_settings()

        # 按钮区域
        self.create_buttons()

        # 进度条
        self.create_progress_bar()

        # 日志区域
        self.create_log_area()

        # 初始化模式（所有UI创建完成后）
        self.on_export_mode_change("reencode")  # 默认使用重新编码
    

    
    def create_path_settings(self):
        """创建路径设置 - 复用外部脚本的界面"""
        path_frame = ttk.LabelFrame(self.dialog, text="输出设置", padding=10)
        path_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 输出文件夹路径
        tk.Label(path_frame, text="输出文件夹路径：").grid(row=0, column=0, sticky="e", padx=5, pady=5)
        tk.Entry(path_frame, textvariable=self.output_var, width=50).grid(row=0, column=1, padx=5)
        ttk.Button(path_frame, text="选择目录", command=self.select_output).grid(row=0, column=2, padx=5)
    
    def create_parameter_settings(self):
        """创建参数设置 - 左右分栏布局"""
        # 创建主参数框架
        main_param_frame = ttk.Frame(self.dialog)
        main_param_frame.pack(fill=tk.X, padx=10, pady=5)

        # 左侧：切割参数
        param_frame = ttk.LabelFrame(main_param_frame, text="切割参数", padding=10)
        param_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        # 右侧：时间统计显示
        time_frame = ttk.LabelFrame(main_param_frame, text="预计处理时间", padding=10)
        time_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 0))

        # === 左侧切割参数内容 ===
        # 命名方式 - 改为复选框样式
        tk.Label(param_frame, text="分割片段命名方式：").grid(row=0, column=0, sticky="e", padx=5, pady=5)

        # 创建命名方式的复选框变量
        self.naming_index_var = tk.BooleanVar(value=True)  # 默认选择按序号
        self.naming_subtitle_var = tk.BooleanVar(value=False)

        # 按序号命名复选框
        index_check = tk.Checkbutton(param_frame, text="按序号", variable=self.naming_index_var,
                                   command=lambda: self.on_naming_mode_change("index"))
        index_check.grid(row=0, column=1, sticky="w")

        # 按序号+字幕内容命名复选框
        subtitle_check = tk.Checkbutton(param_frame, text="按序号+字幕内容", variable=self.naming_subtitle_var,
                                      command=lambda: self.on_naming_mode_change("subtitle"))
        subtitle_check.grid(row=0, column=2, sticky="w")

        # FFmpeg编码预设
        tk.Label(param_frame, text="编码预设：").grid(row=1, column=0, sticky="e", padx=5, pady=5)
        preset_choices = ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"]
        preset_combo = ttk.Combobox(param_frame, textvariable=self.preset_var, values=preset_choices, state="readonly", width=12)
        preset_combo.grid(row=1, column=1, sticky="w", padx=2)
        preset_combo.current(preset_choices.index(self.preset_var.get()))
        # 绑定预设改变事件，重新计算预计时间
        preset_combo.bind('<<ComboboxSelected>>', lambda e: self.calculate_estimated_time())

        # CRF质量参数
        tk.Label(param_frame, text="CRF参数：").grid(row=1, column=2, sticky="e", padx=5, pady=5)
        crf_choices = [str(i) for i in range(16, 32)]
        crf_combo = ttk.Combobox(param_frame, textvariable=self.crf_var, values=crf_choices, state="readonly", width=8)
        crf_combo.grid(row=1, column=3, sticky="w", padx=2)
        crf_combo.current(crf_choices.index(self.crf_var.get()))

        # 重新编码参数（放在编码预设下面）
        tk.Label(param_frame, text="编码分辨率：").grid(row=2, column=0, sticky="e", padx=5, pady=5)
        self.res_combo = ttk.Combobox(
            param_frame,
            textvariable=self.resolution_var,
            values=["1920x1080", "1280x720", "854x480", "640x360"],
            state="disabled",
            width=12
        )
        self.res_combo.grid(row=2, column=1, sticky="w", padx=2)

        tk.Label(param_frame, text="编码帧率：").grid(row=2, column=2, sticky="e", padx=5, pady=5)
        self.fps_combo = ttk.Combobox(
            param_frame,
            textvariable=self.fps_var,
            values=["25", "30", "24", "60"],
            state="disabled",
            width=8
        )
        self.fps_combo.grid(row=2, column=3, sticky="w", padx=2)

        # 导出模式（改为复选框）
        row_offset = 3
        tk.Label(param_frame, text="导出模式：").grid(row=row_offset, column=0, sticky="e", padx=5, pady=5)

        # 快速模式复选框（已隐藏，保留代码以便将来重新启用）
        # self.fast_mode_var = tk.BooleanVar(value=True)
        # tk.Checkbutton(param_frame, text="标准模式",
        #               variable=self.fast_mode_var,
        #               command=lambda: self.on_export_mode_change("fast")).grid(
        #                   row=row_offset, column=1, sticky="w")

        # 重新编码复选框
        self.reencode_mode_var = tk.BooleanVar(value=True)
        tk.Checkbutton(param_frame, text="重新编码",
                      variable=self.reencode_mode_var,
                      command=lambda: self.on_export_mode_change("reencode")).grid(
                          row=row_offset, column=1, sticky="w")

        # 连续切割复选框
        tk.Checkbutton(param_frame, text="连续切割",
                      variable=self.continuous_cut_var).grid(
                          row=row_offset, column=3, sticky="w")

        # 保存为默认配置复选框（新增）
        row_offset += 1
        self.save_as_default_var = tk.BooleanVar(value=False)
        save_default_check = tk.Checkbutton(param_frame, text="保存默认配置",
                                           variable=self.save_as_default_var)
        save_default_check.grid(row=row_offset, column=1, columnspan=2, sticky="w", pady=(5, 0))

        # 提示文字
        tip_label = tk.Label(param_frame, text="(下次“快速添加”将使用此配置)",
                            font=("Arial", 9), fg="gray")
        tip_label.grid(row=row_offset, column=2, columnspan=2, sticky="w", padx=(5, 0), pady=(5, 0))

        # === 右侧时间统计内容 ===
        self.create_time_statistics(time_frame)

    def create_time_statistics(self, parent):
        """创建时间统计显示区域"""
        # 预计处理时间
        tk.Label(parent, text="预计处理时间：", font=("Arial", 9, "bold")).pack(anchor=tk.W, pady=(0, 5))
        estimated_frame = tk.Frame(parent)
        estimated_frame.pack(fill=tk.X, pady=(0, 10))

        tk.Label(estimated_frame, text="⏱️", font=("Arial", 12)).pack(side=tk.LEFT)
        estimated_label = tk.Label(estimated_frame, textvariable=self.estimated_time_var,
                                 font=("Arial", 10), fg="blue")
        estimated_label.pack(side=tk.LEFT, padx=(5, 0))

        # 实际运行时间
        tk.Label(parent, text="实际运行时间：", font=("Arial", 9, "bold")).pack(anchor=tk.W, pady=(0, 5))
        actual_frame = tk.Frame(parent)
        actual_frame.pack(fill=tk.X, pady=(0, 10))

        tk.Label(actual_frame, text="⏳", font=("Arial", 12)).pack(side=tk.LEFT)
        actual_label = tk.Label(actual_frame, textvariable=self.actual_time_var,
                              font=("Arial", 10), fg="green")
        actual_label.pack(side=tk.LEFT, padx=(5, 0))

        # 处理状态
        tk.Label(parent, text="处理状态：", font=("Arial", 9, "bold")).pack(anchor=tk.W, pady=(0, 5))
        status_frame = tk.Frame(parent)
        status_frame.pack(fill=tk.X)

        tk.Label(status_frame, text="", font=("Arial", 12)).pack(side=tk.LEFT)
        self.status_label = tk.Label(status_frame, text="准备就绪",
                                   font=("Arial", 10), fg="gray")
        self.status_label.pack(side=tk.LEFT, padx=(5, 0))

        # 计算预计时间
        self.calculate_estimated_time()

    def calculate_estimated_time(self):
        """计算预计处理时间 - Level 1 通用公式（MoviePy优化版）"""
        try:
            # 基础数据
            segment_count = len(self.segments)
            total_duration = sum(seg.end_time - seg.start_time for seg in self.segments)

            # === Level 1 通用公式：针对 MoviePy 优化 ===

            # 1️⃣ 视频加载时间（一次性开销）
            # 统计不同的视频源数量
            video_paths = set()
            for seg in self.segments:
                if hasattr(seg, 'video_path') and seg.video_path:
                    video_paths.add(seg.video_path)
            video_count = len(video_paths) if video_paths else 1

            # 每个视频平均加载时间：12秒
            loading_time = video_count * 12

            # 2️⃣ 编码时间（核心瓶颈）
            # MoviePy 的实际编码速度因子（针对不同preset）
            preset_speeds = {
                "ultrafast": 0.35,   # 编码1秒视频需要0.35秒
                "superfast": 0.45,
                "veryfast": 0.55,    # 默认推荐
                "faster": 0.75,
                "fast": 0.95,
                "medium": 1.25,      # 比实时慢
                "slow": 1.9,
                "slower": 2.8,
                "veryslow": 4.2
            }

            # CRF 质量参数影响（数值越小=质量越高=编码越慢）
            crf_value = int(self.crf_var.get())
            if crf_value <= 18:
                crf_factor = 1.25    # 高质量，慢25%
            elif crf_value <= 22:
                crf_factor = 1.1     # 平衡质量，慢10%
            elif crf_value >= 28:
                crf_factor = 0.9     # 低质量，快10%
            else:
                crf_factor = 1.0     # 标准质量

            # 计算编码时间
            preset = self.preset_var.get()
            speed_factor = preset_speeds.get(preset, 1.0)
            encoding_time = total_duration * speed_factor * crf_factor

            # 3️⃣ 合并时间（FFmpeg concat，很快）
            merge_time = 8

            # 4️⃣ 安全缓冲（考虑系统负载、硬件差异等未知因素）
            # 加20%的缓冲，使预估更保守可靠
            total_time = (loading_time + encoding_time + merge_time) * 1.2

            # 格式化显示
            estimated_time = self.format_time_duration(total_time)
            self.estimated_time_var.set(f"{estimated_time}")

            # 调试信息（可选）
            if False:  # 设为 True 可查看详细计算过程
                print(f"[预估] 视频数: {video_count}, 总时长: {total_duration:.1f}s")
                print(f"[预估] 加载: {loading_time}s, 编码: {encoding_time:.1f}s, 合并: {merge_time}s")
                print(f"[预估] 缓冲后总时间: {total_time:.1f}s = {estimated_time}")

        except Exception as e:
            self.estimated_time_var.set("计算失败")
            print(f"计算预计时间失败: {e}")

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

    def start_time_tracking(self):
        """开始时间跟踪"""
        self.start_time = time.time()
        self.time_update_running = True
        self._time_tracking_stopped = False  # 重置停止标志
        self.status_label.config(text="处理中...", fg="orange")

        # 启动时间更新线程
        self.time_update_thread = threading.Thread(target=self.update_actual_time, daemon=True)
        self.time_update_thread.start()

    def pause_time_tracking(self):
        """暂停时间跟踪"""
        if hasattr(self, 'time_update_running') and self.time_update_running:
            self.time_update_running = False
            if hasattr(self, 'start_time') and self.start_time:
                self._paused_time = time.time() - self.start_time
                self.log_message(f"⏸️ 时间跟踪已暂停，已用时: {self.format_time_duration(self._paused_time)}")
            self.status_label.config(text="等待用户确认...", fg="blue")

    def resume_time_tracking(self):
        """恢复时间跟踪"""
        # 确保时间跟踪没有被其他地方停止
        if hasattr(self, '_time_tracking_stopped') and self._time_tracking_stopped:
            self._time_tracking_stopped = False

        # 调整开始时间以补偿暂停期���的时间
        if hasattr(self, '_paused_time') and self._paused_time:
            self.start_time = time.time() - self._paused_time
            self.log_message(f"⏯️ 时间跟踪已恢复，继续从: {self.format_time_duration(self._paused_time)}")
            delattr(self, '_paused_time')

        # 重新启动时间更新
        self.time_update_running = True
        self.status_label.config(text="处理中...", fg="orange")

        # 重新启动时间更新线程
        self.time_update_thread = threading.Thread(target=self.update_actual_time, daemon=True)
        self.time_update_thread.start()

    def stop_time_tracking(self, success=True):
        """停止时间跟踪"""
        # 防止重复调用
        if hasattr(self, '_time_tracking_stopped') and self._time_tracking_stopped:
            return

        self.time_update_running = False
        self._time_tracking_stopped = True

        if self.start_time:
            elapsed = time.time() - self.start_time
            final_time = self.format_time_duration(elapsed)
            self.actual_time_var.set(final_time)

            # 添加运行时间到日志
            self.log_message(f"实际运行时间: {final_time}")

            if success:
                self.status_label.config(text="处理完成", fg="green")
            else:
                self.status_label.config(text="处理失败", fg="red")

    def update_actual_time(self):
        """更新实际运行时间（在后台线程中运行）"""
        while self.time_update_running and self.start_time:
            try:
                elapsed = time.time() - self.start_time
                formatted_time = self.format_time_duration(elapsed)
                # 使用after方法在主线程中更新UI
                self.dialog.after(0, lambda: self.actual_time_var.set(formatted_time))
                time.sleep(1)  # 每秒更新一次
            except Exception as e:
                print(f"更新时间失败: {e}")
                break
    
    def create_buttons(self):
        """创建按钮区域 - 复用外部脚本的界面"""
        button_frame = tk.Frame(self.dialog)
        button_frame.pack(fill=tk.X, padx=10, pady=5)

        # 创建按钮并存储引用
        self.start_button = ttk.Button(button_frame, text="开始处理", command=self.start_process, width=12)
        self.start_button.grid(row=0, column=0, pady=5)

        # 新增：添加到队列按钮
        self.add_to_queue_button = ttk.Button(button_frame, text="添加队列", command=self.add_to_queue, width=12)
        self.add_to_queue_button.grid(row=0, column=1, padx=5)

        # 新增：打开队列管理器按钮
        self.open_queue_button = ttk.Button(button_frame, text="打开队列", command=self.open_queue_manager, width=12)
        self.open_queue_button.grid(row=0, column=2, padx=5)

        ttk.Button(button_frame, text="输出目录", command=self.open_output, width=12).grid(row=0, column=3, padx=5)

        ttk.Button(button_frame, text="取消", command=self.on_close, width=8).grid(row=0, column=4, padx=5)
    
    def create_progress_bar(self):
        """创建进度条 - 复用外部脚本的界面"""
        progress_frame = tk.Frame(self.dialog)
        progress_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(progress_frame, text="进度：").grid(row=0, column=0, sticky="e", padx=5, pady=5)
        progressbar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        progressbar.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        tk.Label(progress_frame, textvariable=self.progress_percent_var, width=5).grid(row=0, column=2, sticky="ew")
        
        # 让进度条自动拉伸
        progress_frame.grid_columnconfigure(1, weight=1)
    
    def create_log_area(self):
        """创建日志区域 - 复用外部脚本的界面"""
        log_frame = tk.Frame(self.dialog)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        tk.Label(log_frame, text="日志：").pack(anchor="nw")
        
        # 创建日志框架和滚动条
        log_container = tk.Frame(log_frame)
        log_container.pack(fill=tk.BOTH, expand=True)
        
        # 创建垂直滚动条
        log_scrollbar = tk.Scrollbar(log_container)
        log_scrollbar.pack(side="right", fill="y")
        
        self.log_text = tk.Text(log_container, width=80, height=12, state='disabled', yscrollcommand=log_scrollbar.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        
        log_scrollbar.config(command=self.log_text.yview)



    # ========== 事件处理方法 - 复用外部脚本的逻辑 ==========

    def select_output(self):
        """选择输出文件夹"""
        folder = filedialog.askdirectory(parent=self.dialog, title="选择输出文件夹")
        if folder:
            self.output_var.set(folder)

    def open_output(self):
        """打开输出文件夹"""
        output_path = self.output_var.get()
        if output_path and os.path.exists(output_path):
            os.startfile(output_path)
        else:
            custom_messagebox.showwarning("警告", "输出文件夹不存在", parent=self.dialog)

    def log_message(self, message):
        """添加日志消息 - 复用外部脚本的日志功能"""
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, f"{time.strftime('%H:%M:%S')} - {message}\n")
        self.log_text.config(state='disabled')
        self.log_text.see(tk.END)
        self.dialog.update()

    def update_progress(self, current, total, message=""):
        """更新进度条 - 复用外部脚本的进度更新逻辑"""
        if total > 0:
            progress = (current / total) * 100
            self.progress_var.set(progress)
            self.progress_percent_var.set(f"{progress:.1f}%")

        if message:
            self.log_message(message)

        self.dialog.update()

    def show_success_dialog(self, output_dir):
        """显示处理成功提示窗口 - 改为普通弹窗提示，参考导入窗口的弹窗提示"""
        try:
            # 使用普通的messagebox弹窗，参考导入窗口的样式
            result = messagebox.askquestion(
                "导出完成",
                f"视频片段导出完成！\n\n输出目录：{output_dir}\n\n是否打开输出文件夹？",
                icon='question',
                parent=self.dialog
            )

            # 如果用户选择是，则打开文件夹
            if result == 'yes':
                try:
                    os.startfile(output_dir)
                except Exception as e:
                    messagebox.showerror("错误", f"无法打开文件夹：{e}", parent=self.dialog)

        except Exception as e:
            # 如果创建弹窗失败，至少显示一个简单的消息框
            messagebox.showinfo("导出完成", f"视频片段导出完成！\n输出目录：{output_dir}", parent=self.dialog)

    def show_failure_dialog(self, error_message):
        """显示处理失败提示窗口 - 使用自定义对话框避免 Windows MessageBox 导致的最小化问题"""
        try:
            # 使用自定义对话框，完全避免 Windows 原生 MessageBox 的问题
            self._show_custom_error_dialog("导出失败", error_message)
        except Exception as e:
            # 如果自定义对话框失败，降级到原生 messagebox
            try:
                self.dialog.deiconify()
                self.dialog.lift()
                self.dialog.focus_force()
                messagebox.showerror("导出失败", f"视频片段导出失败！\n错误：{error_message}", parent=self.dialog)
            except:
                pass

    def _detect_cross_project(self):
        """检测是否为跨项目导出"""
        if not self.segments:
            return False

        # 获取所有片段的项目ID
        project_ids = set(seg.project_id for seg in self.segments)

        # 如果有多个不同的项目ID，则为跨项目导出
        return len(project_ids) > 1

    def _detect_mixed_audio_video(self):
        """检测是否为音频和视频混合导出"""
        if not self.segments:
            return False

        from database.manager import db_manager

        has_audio = False
        has_video = False

        # 遍历所有片段，检查所属项目的文件类型
        for segment in self.segments:
            project = db_manager.get_project(segment.project_id)
            if project and project.video_path:
                if FileUtils.is_audio_file(project.video_path):
                    has_audio = True
                else:
                    has_video = True

                # 如果已经检测到两种类型，可以提前返回
                if has_audio and has_video:
                    return True

        return False

    def _show_mixed_audio_video_warning(self):
        """显示音频视频混合导出警告对话框"""
        try:
            # 在显示对话框前，先确保父窗口处于稳定状态
            self.dialog.update_idletasks()

            # 创建自定义警告对话框
            warning_dialog = tk.Toplevel(self.dialog)
            warning_dialog.title("音频视频混合导出警告")

            # 先隐藏窗口，配置完成后再显示
            warning_dialog.withdraw()

            # 设置窗口大小
            dialog_width = 500
            dialog_height = 280
            warning_dialog.geometry(f"{dialog_width}x{dialog_height}")
            warning_dialog.resizable(False, False)

            # 设置窗口图标
            if ICON_AVAILABLE:
                set_window_icon(warning_dialog)

            # 主容器 - 使用白色背景
            main_frame = tk.Frame(warning_dialog, bg="white")
            main_frame.pack(fill=tk.BOTH, expand=True)

            # 内容区域
            content_frame = tk.Frame(main_frame, bg="white", padx=20, pady=20)
            content_frame.pack(fill=tk.BOTH, expand=True)

            # 图标和消息区域（横向布局）
            msg_frame = tk.Frame(content_frame, bg="white")
            msg_frame.pack(fill=tk.BOTH, expand=True)

            # 警告图标 - 橙色三角形 + 白色感叹号
            icon_canvas = tk.Canvas(msg_frame, width=40, height=40, bg="white",
                                   highlightthickness=0)
            icon_canvas.pack(side=tk.LEFT, padx=(0, 15), anchor=tk.N)

            # 绘制橙色三角形
            icon_canvas.create_polygon(
                20, 5,   # 顶点
                5, 35,   # 左下角
                35, 35,  # 右下角
                fill="#FF9800", outline=""
            )

            # 绘制白色感叹号
            icon_canvas.create_text(20, 18, text="!", font=("Arial", 20, "bold"),
                                   fill="white")

            # 警告消息
            warning_text = (
                "检测到音频和视频混合导出！\n\n"
                "不支持同时导出音频片段和视频片段。\n\n"
                "请分别导出音频项目和视频项目。\n\n"
                "点击确定返回。"
            )

            message_label = tk.Label(msg_frame, text=warning_text,
                                    font=("Segoe UI", 9),
                                    bg="white", justify=tk.LEFT,
                                    anchor=tk.W, wraplength=380)
            message_label.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            # 分隔线
            separator = tk.Frame(main_frame, height=1, bg="#D0D0D0")
            separator.pack(fill=tk.X)

            # 按钮区域 - 浅灰色背景
            button_frame = tk.Frame(main_frame, bg="#F0F0F0")
            button_frame.pack(fill=tk.X)

            # 按钮容器 - 右对齐
            button_container = tk.Frame(button_frame, bg="#F0F0F0", padx=15, pady=12)
            button_container.pack(side=tk.RIGHT)

            def close_dialog():
                try:
                    warning_dialog.grab_release()
                    warning_dialog.destroy()
                except:
                    pass
                finally:
                    try:
                        self.dialog.deiconify()
                        self.dialog.lift()
                        self.dialog.focus_force()
                    except:
                        pass

            # 确定按钮
            ok_button = tk.Button(button_container, text="我知道了", command=close_dialog,
                                 width=12, height=1, font=("Segoe UI", 9),
                                 relief=tk.FLAT, bg="#FF9800", fg="white",
                                 activebackground="#F57C00", activeforeground="white",
                                 cursor="hand2", borderwidth=0, highlightthickness=1,
                                 highlightbackground="#FF9800", highlightcolor="#FF9800")
            ok_button.pack()

            # 按钮悬停效果
            def on_enter(e):
                ok_button.config(bg="#F57C00")
            def on_leave(e):
                ok_button.config(bg="#FF9800")
            ok_button.bind("<Enter>", on_enter)
            ok_button.bind("<Leave>", on_leave)

            # 绑定窗口关闭事件
            warning_dialog.protocol("WM_DELETE_WINDOW", close_dialog)

            # 绑定快捷键
            warning_dialog.bind("<Return>", lambda e: close_dialog())
            warning_dialog.bind("<Escape>", lambda e: close_dialog())

            # 居中显示
            warning_dialog.update_idletasks()
            x = self.dialog.winfo_x() + (self.dialog.winfo_width() - dialog_width) // 2
            y = self.dialog.winfo_y() + (self.dialog.winfo_height() - dialog_height) // 2
            warning_dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")

            # 设置父子关系和模态
            warning_dialog.transient(self.dialog)
            warning_dialog.deiconify()
            warning_dialog.grab_set()

            # 获取焦点
            warning_dialog.lift()
            warning_dialog.focus_force()
            ok_button.focus_set()

            # 记录日志
            self.log_message("⚠️ 检测到音频和视频混合导出")
            self.log_message("   不支持同时导出音频片段和视频片段")
            self.log_message("   已停止当前导出，请分别导出")

            # 等待对话框关闭
            try:
                warning_dialog.wait_window()
            except:
                pass

            # 确保父窗口正常
            try:
                self.dialog.deiconify()
                self.dialog.lift()
                self.dialog.focus_force()
            except:
                pass

        except Exception as e:
            # 如果自定义对话框失败，降级到原生 messagebox
            try:
                self.dialog.deiconify()
                self.dialog.lift()
                self.dialog.focus_force()
                messagebox.showwarning(
                    "音频视频混合导出警告",
                    "检测到音频和视频混合导出！\n\n"
                    "不支持同时导出音频片段和视频片段。\n\n"
                    "请分别导出音频项目和视频项目。\n\n"
                    "点击确定返回。",
                    parent=self.dialog
                )
            except:
                pass

    def _show_cross_project_warning(self):
        """显示跨项目导出警告对话框"""
        try:
            # 在显示对话框前，先确保父窗口处于稳定状态
            self.dialog.update_idletasks()

            # 创建自定义警告对话框
            warning_dialog = tk.Toplevel(self.dialog)
            warning_dialog.title("跨项目导出警告")

            # 先隐藏窗口，配置完成后再显示
            warning_dialog.withdraw()

            # 设置窗口大小
            dialog_width = 500
            dialog_height = 280
            warning_dialog.geometry(f"{dialog_width}x{dialog_height}")
            warning_dialog.resizable(False, False)

            # 设置窗口图标
            if ICON_AVAILABLE:
                set_window_icon(warning_dialog)

            # 主容器 - 使用白色背景
            main_frame = tk.Frame(warning_dialog, bg="white")
            main_frame.pack(fill=tk.BOTH, expand=True)

            # 内容区域
            content_frame = tk.Frame(main_frame, bg="white", padx=20, pady=20)
            content_frame.pack(fill=tk.BOTH, expand=True)

            # 图标和消息区域（横向布局）
            msg_frame = tk.Frame(content_frame, bg="white")
            msg_frame.pack(fill=tk.BOTH, expand=True)

            # 警告图标 - 橙色三角形 + 白色感叹号
            icon_canvas = tk.Canvas(msg_frame, width=40, height=40, bg="white",
                                   highlightthickness=0)
            icon_canvas.pack(side=tk.LEFT, padx=(0, 15), anchor=tk.N)

            # 绘制橙色三角形
            icon_canvas.create_polygon(
                20, 5,   # 顶点
                5, 35,   # 左下角
                35, 35,  # 右下角
                fill="#FF9800", outline=""
            )

            # 绘制白色感叹号
            icon_canvas.create_text(20, 18, text="!", font=("Arial", 20, "bold"),
                                   fill="white")

            # 警告消息
            warning_text = (
                "检测到跨项目片段导出！\n\n"
                "当前选择的是「标准模式」，该模式不支持跨项目导出。\n\n"
                "跨项目导出需要使用「重新编码」来统一不同视频的参数。\n\n"
                "请手动切换到「重新编码」后重新开始导出。"
            )

            message_label = tk.Label(msg_frame, text=warning_text,
                                    font=("Segoe UI", 9),
                                    bg="white", justify=tk.LEFT,
                                    anchor=tk.W, wraplength=380)
            message_label.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            # 分隔线
            separator = tk.Frame(main_frame, height=1, bg="#D0D0D0")
            separator.pack(fill=tk.X)

            # 按钮区域 - 浅灰色背景
            button_frame = tk.Frame(main_frame, bg="#F0F0F0")
            button_frame.pack(fill=tk.X)

            # 按钮容器 - 右对齐
            button_container = tk.Frame(button_frame, bg="#F0F0F0", padx=15, pady=12)
            button_container.pack(side=tk.RIGHT)

            def close_dialog():
                try:
                    warning_dialog.grab_release()
                    warning_dialog.destroy()
                except:
                    pass
                finally:
                    try:
                        self.dialog.deiconify()
                        self.dialog.lift()
                        self.dialog.focus_force()
                    except:
                        pass

            # 确定按钮
            ok_button = tk.Button(button_container, text="我知道了", command=close_dialog,
                                 width=12, height=1, font=("Segoe UI", 9),
                                 relief=tk.FLAT, bg="#FF9800", fg="white",
                                 activebackground="#F57C00", activeforeground="white",
                                 cursor="hand2", borderwidth=0, highlightthickness=1,
                                 highlightbackground="#FF9800", highlightcolor="#FF9800")
            ok_button.pack()

            # 按钮悬停效果
            def on_enter(e):
                ok_button.config(bg="#F57C00")
            def on_leave(e):
                ok_button.config(bg="#FF9800")
            ok_button.bind("<Enter>", on_enter)
            ok_button.bind("<Leave>", on_leave)

            # 绑定窗口关闭事件
            warning_dialog.protocol("WM_DELETE_WINDOW", close_dialog)

            # 绑定快捷键
            warning_dialog.bind("<Return>", lambda e: close_dialog())
            warning_dialog.bind("<Escape>", lambda e: close_dialog())

            # 居中显示
            warning_dialog.update_idletasks()
            x = self.dialog.winfo_x() + (self.dialog.winfo_width() - dialog_width) // 2
            y = self.dialog.winfo_y() + (self.dialog.winfo_height() - dialog_height) // 2
            warning_dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")

            # 设置父子关系和模态
            warning_dialog.transient(self.dialog)
            warning_dialog.deiconify()
            warning_dialog.grab_set()

            # 获取焦点
            warning_dialog.lift()
            warning_dialog.focus_force()
            ok_button.focus_set()

            # 记录日志
            self.log_message("⚠️ 跨项目导出需要使用「重新编码」")
            self.log_message("   已停止当前导出，请切换导出模式后重试")

            # 等待对话框关闭
            try:
                warning_dialog.wait_window()
            except:
                pass

            # 确保父窗口正常
            try:
                self.dialog.deiconify()
                self.dialog.lift()
                self.dialog.focus_force()
            except:
                pass

        except Exception as e:
            # 如果自定义对话框失败，降级到原生 messagebox
            try:
                self.dialog.deiconify()
                self.dialog.lift()
                self.dialog.focus_force()
                messagebox.showwarning(
                    "跨项目导出警告",
                    "检测到跨项目片段导出！\n\n"
                    "当前选择的是「标准模式」，该模式不支持跨项目导出。\n\n"
                    "跨项目导出需要使用「重新编码」来统一不同视频的参数。\n\n"
                    "请手动切换到「重新编码」后重新开始导出。",
                    parent=self.dialog
                )
            except:
                pass

    def _show_custom_error_dialog(self, title, message):
        """自定义错误对话框 - 模仿 Windows 原生 MessageBox 样式，避免最小化问题"""
        # 在显示对话框前，先确保父窗口处于稳定状态
        self.dialog.update_idletasks()

        # 创建自定义对话框
        error_dialog = tk.Toplevel(self.dialog)
        error_dialog.title(title)

        # 先隐藏窗口，配置完成后再显示
        error_dialog.withdraw()

        # 设置窗口大小 - 更紧凑，接近原生 MessageBox
        dialog_width = 400
        dialog_height = 180
        error_dialog.geometry(f"{dialog_width}x{dialog_height}")
        error_dialog.resizable(False, False)

        # 设置窗口图标
        if ICON_AVAILABLE:
            set_window_icon(error_dialog)

        # 主容器 - 使用白色背景模仿原生样式
        main_frame = tk.Frame(error_dialog, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 内容区域
        content_frame = tk.Frame(main_frame, bg="white", padx=20, pady=20)
        content_frame.pack(fill=tk.BOTH, expand=True)

        # 图标和消息区域（横向布局）
        msg_frame = tk.Frame(content_frame, bg="white")
        msg_frame.pack(fill=tk.BOTH, expand=True)

        # 错误图标 - 红色圆形背景 + 白色 X，模仿 Windows 原生错误图标
        icon_canvas = tk.Canvas(msg_frame, width=40, height=40, bg="white",
                               highlightthickness=0)
        icon_canvas.pack(side=tk.LEFT, padx=(0, 15), anchor=tk.N)

        # 绘制红色圆形背景
        icon_canvas.create_oval(2, 2, 38, 38, fill="#D32F2F", outline="")

        # 绘制白色 X（两条交叉的线）
        icon_canvas.create_line(12, 12, 28, 28, fill="white", width=3, capstyle=tk.ROUND)
        icon_canvas.create_line(28, 12, 12, 28, fill="white", width=3, capstyle=tk.ROUND)

        # 消息文本 - 使用 Label 而不是 Text，更接近原生样式
        message_label = tk.Label(msg_frame, text=message, font=("Segoe UI", 9),
                                bg="white", justify=tk.LEFT, anchor=tk.W, wraplength=280)
        message_label.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 分隔线 - 模仿 Windows 对话框的灰色分隔线
        separator = tk.Frame(main_frame, height=1, bg="#D0D0D0")
        separator.pack(fill=tk.X)

        # 按钮区域 - 浅灰色背景
        button_frame = tk.Frame(main_frame, bg="#F0F0F0")
        button_frame.pack(fill=tk.X)

        # 按钮容器 - 右对齐
        button_container = tk.Frame(button_frame, bg="#F0F0F0", padx=15, pady=12)
        button_container.pack(side=tk.RIGHT)

        def close_dialog():
            try:
                error_dialog.grab_release()
                error_dialog.destroy()
            except:
                pass
            finally:
                try:
                    self.dialog.deiconify()
                    self.dialog.lift()
                    self.dialog.focus_force()
                except:
                    pass

        # 确定按钮 - 使用标准按钮样式
        ok_button = tk.Button(button_container, text="确定", command=close_dialog,
                             width=12, height=1, font=("Segoe UI", 9),
                             relief=tk.FLAT, bg="#0078D7", fg="white",
                             activebackground="#005A9E", activeforeground="white",
                             cursor="hand2", borderwidth=0, highlightthickness=1,
                             highlightbackground="#0078D7", highlightcolor="#0078D7")
        ok_button.pack()

        # 按钮悬停效果
        def on_enter(e):
            ok_button.config(bg="#005A9E")
        def on_leave(e):
            ok_button.config(bg="#0078D7")
        ok_button.bind("<Enter>", on_enter)
        ok_button.bind("<Leave>", on_leave)

        # 绑定窗口关闭事件
        error_dialog.protocol("WM_DELETE_WINDOW", close_dialog)

        # 绑定快捷键
        error_dialog.bind("<Return>", lambda e: close_dialog())
        error_dialog.bind("<Escape>", lambda e: close_dialog())

        # 居中显示
        error_dialog.update_idletasks()
        x = self.dialog.winfo_x() + (self.dialog.winfo_width() - dialog_width) // 2
        y = self.dialog.winfo_y() + (self.dialog.winfo_height() - dialog_height) // 2
        error_dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")

        # 设置父子关系和模态
        error_dialog.transient(self.dialog)
        error_dialog.deiconify()
        error_dialog.grab_set()

        # 获取焦点
        error_dialog.lift()
        error_dialog.focus_force()
        ok_button.focus_set()

        # 等待对话框关闭
        try:
            error_dialog.wait_window()
        except:
            pass

        # 确保父窗口正常
        try:
            self.dialog.deiconify()
            self.dialog.lift()
            self.dialog.focus_force()
        except:
            pass

    def start_process(self):
        """开始处理 - 复用外部脚本的主要逻辑"""
        if self.is_processing:
            return

        # 验证输出路径
        output_path = self.output_var.get().strip()
        if not output_path:
            self._show_custom_error_dialog("错误", "请选择输出文件夹")
            return

        # 创建输出目录
        try:
            os.makedirs(output_path, exist_ok=True)
        except Exception as e:
            self._show_custom_error_dialog("错误", f"无法创建输出目录: {e}")
            return

        # 🚨 新增：跨项目检测逻辑
        is_cross_project = self._detect_cross_project()
        if is_cross_project:
            self.log_message("⚠️ 检测到跨项目导出，验证导出模式...")

            # 检查当前导出模式
            current_mode = self.export_mode_var.get()
            if current_mode == "fast":
                # 快速模式不支持跨项目导出，弹出警告
                self._show_cross_project_warning()
                return  # 停止导出进程

        # 🚨 新增：音频视频混合导出检测
        if self._detect_mixed_audio_video():
            self._show_mixed_audio_video_warning()
            return  # 停止导出进程

        # 准备数据
        self.log_message(f"开始准备片段数据，输入片段数量: {len(self.segments)}")
        for i, segment in enumerate(self.segments, 1):
            self.log_message(f"片段 {i}: ID={segment.id}, 项目ID={segment.project_id}, 时间={segment.start_time:.1f}-{segment.end_time:.1f}s")

        result = script_adapter.prepare_segments_for_script(self.segments)
        if not result:
            self._show_custom_error_dialog("错误", "无法准备片段数据 \n请确认视频文件是否存在或移动过")
            return

        video_file, temp_srt_file, temp_dir = result
        self.log_message(f"ScriptAdapter结果: video_file={video_file}, temp_srt_file={temp_srt_file}")

        # 开始时间跟踪
        self.start_time_tracking()

        # 检查是否为跨项目导出
        if video_file == "CROSS_PROJECT":
            # 跨项目导出
            self.log_message("检测到跨项目片段导出，使用跨项目处理模式")

            # 在新线程中执行跨项目处理
            self.is_processing = True
            self.cancel_flag = False
            self.start_button.config(text="处理中...", state="disabled")

            thread = threading.Thread(
                target=self.process_cross_project_segments,
                args=(temp_srt_file, output_path),  # temp_srt_file 实际是 segments_info_file
                daemon=True
            )
            thread.start()
        else:
            # 单项目导出，使用原有逻辑
            self.is_processing = True
            self.cancel_flag = False
            self.start_button.config(text="处理中...", state="disabled")

            thread = threading.Thread(
                target=self.process_segments,
                args=(video_file, temp_srt_file, output_path),
                daemon=True
            )
            thread.start()



    # ========== 核心处理方法 - 直接复用外部脚本的逻辑 ==========

    def process_cross_project_segments(self, segments_info_file, output_dir):
        """处理跨项目片段 - 每��片段使用对应的视频源"""
        # 生成唯一的线程ID（使用更精确的方式避免冲突）
        import threading
        import time
        import random
        thread_id = f"{threading.current_thread().ident}_{int(time.time() * 1000000)}_{random.randint(1000, 9999)}"

        # 阻止系统休眠
        PowerManager.prevent_sleep()

        try:
            self.log_message("开始处理跨项目视频片段...")

            # 读取片段信息
            import json
            with open(segments_info_file, 'r', encoding='utf-8') as f:
                segments_data = json.load(f)

            if not segments_data:
                self.log_message("错误：没有找到片段数据")
                return

            # 方案6关键：保存片段信息供后续使用
            self.current_segments_info = segments_data

            total_segments = len(segments_data)
            self.log_message(f"方案6：找到 {total_segments} 个跨项目片段，已保存片段信息")

            # 创建输出目录结构 - 添加时间戳
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            video_name = "cross_project_export"
            base_dir_name = f"{video_name}_{timestamp}"

            base_dir = os.path.join(output_dir, base_dir_name)  # 外层目录(带时间戳)
            chunk_dir = os.path.join(base_dir, video_name)  # 内层目录（存放片段）

            os.makedirs(chunk_dir, exist_ok=True)
            os.makedirs(base_dir, exist_ok=True)

            self.log_message(f"输出目录结构:")
            self.log_message(f"  片段目录: {chunk_dir}")
            self.log_message(f"  合并目录: {base_dir}")

            # 🔍 检测连续切割模式 - 兼容队列模式和直接模式
            if hasattr(self, 'continuous_cut_var') and self.continuous_cut_var:
                # 直接导出模式：从 UI 控件读取
                continuous_mode = self.continuous_cut_var.get()
            elif hasattr(self, 'queue_processor') and self.queue_processor:
                # 队列导出模式：从 queue_processor 获取当前任务的配置
                current_task = self.queue_processor.current_task
                if current_task and current_task.config:
                    continuous_mode = current_task.config.continuous_cut_mode
                else:
                    continuous_mode = False  # 默认不启用连续切割
            else:
                # 无法确定模式，使用默认值
                continuous_mode = False

            if continuous_mode:
                self.log_message("✓ 跨项目连续切割模式已启用")
                # 🔄 跨项目连续切割：使用重新编码切割一个连续片段
                return self._process_cross_project_continuous_cut(
                    segments_data, chunk_dir, base_dir, video_name, output_dir
                )
            else:
                self.log_message("✓ 跨项目片段切割模式（默认）")

            # 核心修复：按 project_id 排序处理，与合并阶段保持一致
            from moviepy.editor import VideoFileClip
            from collections import defaultdict

            # 第1步：按 project_id 分组并排序片段
            self.log_message("按 project_id 排序处理片段（与合并阶段保持一致）")
            project_groups = defaultdict(list)

            for i, segment_data in enumerate(segments_data, 1):
                # 检查视频文件路径
                video_path = segment_data['video_path']

                # 检查视频文件是否存在
                if not os.path.exists(video_path):
                    self.log_message(f"警告：视频文件不存在: {video_path}")
                    # 尝试修复路径问题
                    project_id = segment_data.get('project_id')
                    if project_id:
                        from database.manager import db_manager
                        project = db_manager.get_project(project_id)
                        if project and project.video_path and os.path.exists(project.video_path):
                            self.log_message(f"使用数据库中的路径: {project.video_path}")
                            video_path = project.video_path
                            segment_data['video_path'] = video_path
                        else:
                            self.log_message(f"跳过片段 {i}（路径无效）")
                            continue
                    else:
                        continue

                # 按 project_id 分组（包含原始索引）
                project_id = segment_data.get('project_id')
                project_groups[project_id].append((i, segment_data))

            # 按 project_id 正序排序
            sorted_project_ids = sorted(project_groups.keys())
            self.log_message(f"检测到 {len(sorted_project_ids)} 个项目: {sorted_project_ids}，总计 {total_segments} 个片段")

            # 第2步：按 project_id 顺序处理每个项目的片段
            processed_count = 0
            for project_idx, project_id in enumerate(sorted_project_ids, 1):
                segments_in_project = project_groups[project_id]

                # 项目内按原始索引排序（保持时间顺序）
                segments_in_project.sort(key=lambda x: x[0])

                self.log_message(f"\n处理项目 {project_id} ({project_idx}/{len(sorted_project_ids)}): {len(segments_in_project)} 个片段")

                # 处理该项目的所有片段
                for i, segment_data in segments_in_project:
                    # 检查取消标志（本地取消或队列处理器取消）
                    if self.cancel_flag or (hasattr(self, 'queue_processor') and
                                           self.queue_processor and
                                           self.queue_processor.cancel_requested):
                        self.log_message("用户取消操作")
                        break

                    try:
                        # 获取片段信息
                        video_path = segment_data['video_path']
                        start_time = segment_data['start_time']
                        end_time = segment_data['end_time']
                        text = segment_data['text']
                        duration = end_time - start_time

                        self.log_message(f"处理片段 {i}/{total_segments}: {text[:20]}...")

                        # 生成文件名 - 支持序号+字幕内容命名（序号确保唯一性）
                        segment_index = processed_count + 1

                        if self.naming_mode.get() == "subtitle":
                            # 清理字幕文本用于文件名
                            subtitle_text = text.replace('\n', ' ').replace('\r', ' ')
                            subtitle_text = ''.join(c for c in subtitle_text if c.isalnum() or c in (' ', '_', '-'))
                            subtitle_text = subtitle_text.strip().replace(' ', '_')
                            if not subtitle_text:
                                subtitle_text = f"clip_{segment_index}"
                            filename_base = f"{segment_index:02d}.{subtitle_text}"
                        else:
                            filename_base = f"{segment_index:02d}"

                        # 输出路径
                        video_output = os.path.join(chunk_dir, f"{filename_base}.mp4")
                        audio_output = os.path.join(chunk_dir, f"{filename_base}.mp3")
                        sub_output = os.path.join(chunk_dir, f"{filename_base}.srt")

                        # 跨项目导出强制使用重新编码
                        self.log_message(f"  使用重新编码切割片段 {segment_index} (原始索引:{i})")

                        # 使用FFmpeg重新编码切割
                        success = self.cut_segment_with_reencode(
                            video_path, start_time, end_time, video_output
                        )

                        if success:
                            self.log_message(f"  ✓ 视频切割成功（已统一参数）{i}")

                            # 提取音频（使用FFmpeg）
                            try:
                                audio_cmd = [
                                    "ffmpeg", "-y",
                                    "-i", video_output,
                                    "-vn",  # 不处理视频
                                    "-acodec", "libmp3lame",
                                    "-b:a", "192k",
                                    audio_output
                                ]
                                subprocess.run(
                                    audio_cmd,
                                    capture_output=True,
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                                )
                                self.log_message(f"  ✓ 音频提取成功 {i}")
                            except Exception as e:
                                self.log_message(f"  ⚠ 音频提取失败: {e}")
                        else:
                            self.log_message(f"  ✗ 视频切割失败 {i}")
                            continue

                        # 创建字幕文件
                        with open(sub_output, 'w', encoding='utf-8') as f:
                            f.write(f"1\n")
                            f.write(f"00:00:00,000 --> {self._format_time(duration)}\n")
                            f.write(f"{text}\n\n")
                        self.log_message(f"  ✓ 字幕文件创建成功 {i}")

                        # 更新进度（片段切割阶段占0-90%）
                        processed_count += 1
                        progress_percent = int((processed_count / total_segments) * 90)
                        self.update_progress(progress_percent, 100,
                                           f"处理片段 {processed_count}/{total_segments}")

                        # 触发片段完成回调（用于队列导出模式的实时进度更新）
                        if hasattr(self, 'on_segment_exported') and self.on_segment_exported:
                            try:
                                self.on_segment_exported(processed_count - 1)  # 传递片段索引（从0开始）
                            except Exception as callback_error:
                                # 回调失败不应影响导出流程，仅记录日志
                                self.log_message(f"  ⚠ 回调通知失败: {callback_error}")

                    except Exception as e:
                        self.log_message(f"  ✗ 处理片段 {i} 失败: {e}")
                        import traceback
                        self.log_message(f"详细错误: {traceback.format_exc()}")
                        continue

            # 完成片段切割（进度90%，后续还有合并任务）
            self.update_progress(90, 100, "片段切割完成！开始合并...")
            self.log_message(f"所有片段切割完成，输出到: {chunk_dir}")

            # 详细检查生成的文件
            all_files = os.listdir(chunk_dir)
            generated_files = [f for f in all_files if f.endswith('.mp4')]
            audio_files = [f for f in all_files if f.endswith('.mp3')]
            srt_files = [f for f in all_files if f.endswith('.srt')]

            #self.log_message(f"目录中所有文件: {sorted(all_files)}")
            #self.log_message(f"实际生成了 {len(generated_files)} 个视频文件")
            #self.log_message(f"实际生成了 {len(audio_files)} 个音频文件")
            #self.log_message(f"实际生成了 {len(srt_files)} 个字幕文件")
            #self.log_message(f"预期生成 {total_segments} 个视频文件")

            if len(generated_files) != total_segments:
                self.log_message(f"警告：文件数量不匹配！")
                self.log_message(f"预期文件名:")
                for i in range(1, total_segments + 1):
                    expected_name = f"{i:02d}.mp4"
                    self.log_message(f"  预期: {expected_name}")

                self.log_message(f"实际生成的文件:")
                for f in sorted(generated_files):
                    file_path = os.path.join(chunk_dir, f)
                    file_size = os.path.getsize(file_path)
                    self.log_message(f"  生成的文件: {f} ({file_size} 字节)")

                # 分析文件名模式
                pattern_analysis = {}
                for f in generated_files:
                    match = re.match(r'(\d+)', f)
                    if match:
                        num = int(match.group(1))
                        if num not in pattern_analysis:
                            pattern_analysis[num] = []
                        pattern_analysis[num].append(f)

                self.log_message(f"文件名编号分析:")
                for num in sorted(pattern_analysis.keys()):
                    files = pattern_analysis[num]
                    if len(files) > 1:
                        self.log_message(f"  编号 {num}: {files} (重复!)")
                    else:
                        self.log_message(f"  编号 {num}: {files[0]}")
            else:
                self.log_message(f"文件数量匹配，生成正确")
                for f in sorted(generated_files):
                    self.log_message(f"  生成的文件: {f}")

            # 自动合并片段 - 根据导出模式选择合并策略
            self.log_message("开始合并片段...")

            # 跨项目导出强制使用重新编码的简单合并逻辑
            self.log_message("使用简单合并策略（重新编码，参数已统一）")
            self._simple_merge_with_unified_params(chunk_dir, base_dir, video_name, segments_data)

            self.log_message(f"跨项目处理完成！输出目录: {base_dir}")

            # 所有任务完成，进度更新到100%
            self.update_progress(100, 100, "处理完成！")

            # 停止时间跟踪（成功）
            self.stop_time_tracking(success=True)

            # 队列模式下不显示弹窗，直接返回输出路径
            # 检测是否为队列模式（dialog 是 DummyWidget）
            is_queue_mode = (hasattr(self, 'dialog') and
                           self.dialog.__class__.__name__ == 'DummyWidget')

            if not is_queue_mode:
                # 非队列模式，显示成功提示窗口
                self.show_success_dialog(base_dir)
            else:
                # 队列模式，只记录日志
                self.log_message(f"[队列模式] 跨项目导出完成，输出路径: {base_dir}")

            # 返回输出路径（供队列导出使用）
            return base_dir

        except Exception as e:
            self.log_message(f"跨项目处理失败: {e}")
            import traceback
            self.log_message(traceback.format_exc())

            # 停止时间跟踪（失败）
            self.stop_time_tracking(success=False)
            # 显示失败提示弹窗 - 参考导入窗口的弹窗提示
            self.show_failure_dialog(str(e))

        finally:
            # 恢复系统休眠设置
            PowerManager.allow_sleep()

            # 正常完成处理，重置状态
            self.is_processing = False
            self.start_button.config(text="开始处理", state="normal")


    def _process_cross_project_continuous_cut(self, segments_data, chunk_dir, base_dir, video_name, output_dir):
        """
        跨项目连续切割处理 - 切割一个连续片段跨越所有选中的字幕

        Args:
            segments_data: 所有片段的数据列表
            chunk_dir: 片段输出目录
            base_dir: 合并输出目录
            video_name: 输出视频名称
            output_dir: 用户指定的输出根目录

        Returns:
            str: 输出目录路径
        """
        try:
            self.log_message("=" * 60)
            self.log_message("跨项目连续切割模式")
            self.log_message("=" * 60)

            total_segments = len(segments_data)
            if total_segments == 0:
                self.log_message("错误：没有片段数据")
                return None

            # 按 project_id 分组并排序（与片段切割保持一致）
            from collections import defaultdict
            project_groups = defaultdict(list)

            for i, segment_data in enumerate(segments_data, 1):
                project_id = segment_data.get('project_id')
                project_groups[project_id].append((i, segment_data))

            sorted_project_ids = sorted(project_groups.keys())
            self.log_message(f"涉及 {len(sorted_project_ids)} 个项目: {sorted_project_ids}")

            # 按项目顺序构建所有片段（保持项目内原始顺序）
            ordered_segments = []
            for project_id in sorted_project_ids:
                segments_in_project = project_groups[project_id]
                segments_in_project.sort(key=lambda x: x[0])  # 按原始索引排序
                ordered_segments.extend(segments_in_project)

            # 计算总时间范围
            first_segment = ordered_segments[0][1]
            last_segment = ordered_segments[-1][1]

            total_start_time = first_segment['start_time']
            total_end_time = last_segment['end_time']

            self.log_message(f"连续切割时间范围:")
            self.log_message(f"  起始: {total_start_time:.1f}s (项目 {first_segment.get('project_id')})")
            self.log_message(f"  结束: {total_end_time:.1f}s (项目 {last_segment.get('project_id')})")
            self.log_message(f"  跨度: {total_end_time - total_start_time:.1f}s")
            self.log_message(f"  包含 {total_segments} 个字幕片段")

            # 生成输出文件名（固定为 01）
            filename_base = "01"
            video_output = os.path.join(chunk_dir, f"{filename_base}.mp4")
            audio_output = os.path.join(chunk_dir, f"{filename_base}.mp3")
            sub_output = os.path.join(chunk_dir, f"{filename_base}.srt")

            # 跨项目连续切割：需要按顺序处理每个项目的片段
            self.log_message("\n开始按项目顺序切割并合并...")

            temp_segments = []  # 存储临时切割的片段路径

            # 处理每个项目的片段
            processed_count = 0
            for project_idx, project_id in enumerate(sorted_project_ids, 1):
                segments_in_project = project_groups[project_id]
                segments_in_project.sort(key=lambda x: x[0])

                self.log_message(f"\n处理项目 {project_id} ({project_idx}/{len(sorted_project_ids)}): {len(segments_in_project)} 个片段")

                # 获取该项目的视频路径
                project_video_path = segments_in_project[0][1]['video_path']

                # 处理该项目内的所有片段
                for i, segment_data in segments_in_project:
                    # 检查取消标志
                    if self.cancel_flag or (hasattr(self, 'queue_processor') and
                                           self.queue_processor and
                                           self.queue_processor.cancel_requested):
                        self.log_message("用户取消操作")
                        return None

                    start_time = segment_data['start_time']
                    end_time = segment_data['end_time']
                    text = segment_data['text'][:30]

                    self.log_message(f"  切割片段 {i}: {start_time:.1f}-{end_time:.1f}s, '{text}...'")

                    # 切割临时片段
                    temp_segment_path = os.path.join(chunk_dir, f"temp_{processed_count:03d}.mp4")

                    success = self.cut_segment_with_reencode(
                        project_video_path, start_time, end_time, temp_segment_path
                    )

                    if success:
                        temp_segments.append(temp_segment_path)
                        self.log_message(f"    ✓ 切割成功")

                        # 📊 触发片段完成回调（实现动态进度更新）
                        if hasattr(self, 'on_segment_exported') and self.on_segment_exported:
                            try:
                                self.on_segment_exported(processed_count)  # 传递片段索引
                            except Exception as callback_error:
                                # 回调失败不应影响导出流程
                                pass
                    else:
                        self.log_message(f"    ✗ 切割失败")
                        continue

                    processed_count += 1
                    # 切割阶段占0-80%（后续还有合并、提取音频、生成字幕）
                    progress_percent = int((processed_count / total_segments) * 80)
                    self.update_progress(progress_percent, 100,
                                       f"切割片段 {processed_count}/{total_segments}")

            # 合并所有临时片段为一个连续视频
            if not temp_segments:
                self.log_message("\n错误：没有成功切割的片段")
                return None

            self.log_message(f"\n合并 {len(temp_segments)} 个临时片段为连续视频...")
            self.update_progress(82, 100, "正在合并连续视频...")

            # 使用 FFmpeg concat 合并
            concat_file = os.path.join(chunk_dir, "continuous_concat.txt")
            with open(concat_file, 'w', encoding='utf-8') as f:
                for temp_path in temp_segments:
                    abs_path = os.path.abspath(temp_path)
                    f.write(f"file '{abs_path}'\n")

            cmd = [
                'ffmpeg', '-f', 'concat', '-safe', '0', '-i', concat_file,
                '-c', 'copy',  # 直接复制（已经重新编码统一参数）
                video_output, '-y'
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore',
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)

            if result.returncode == 0:
                self.log_message("  ✓ 连续视频合并成功")
                self.update_progress(90, 100, "连续视频合并完成")

                # 清理临时片段
                for temp_path in temp_segments:
                    try:
                        os.remove(temp_path)
                    except:
                        pass
                os.remove(concat_file)
            else:
                self.log_message(f"  ✗ 视频合并失败: {result.stderr[:200]}")
                return None

            # 提取音频
            self.update_progress(92, 100, "正在提取音频...")
            try:
                audio_cmd = [
                    "ffmpeg", "-y",
                    "-i", video_output,
                    "-vn",
                    "-acodec", "libmp3lame",
                    "-b:a", "192k",
                    audio_output
                ]
                subprocess.run(
                    audio_cmd,
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                self.log_message("  ✓ 音频提取成功")
                self.update_progress(95, 100, "音频提取完成")
            except Exception as e:
                self.log_message(f"  ⚠ 音频提取失败: {e}")

            # 生成连续字幕文件（时间轴从 0 开始）
            # 📊 字幕已在切割时触发过片段完成回调，这里不再重复触发
            self.log_message("\n生成连续字幕文件（时间轴调整为从 0 开始）...")
            self.update_progress(96, 100, "正在生成字幕文件...")

            with open(sub_output, 'w', encoding='utf-8') as f:
                subtitle_index = 1
                current_offset = 0.0  # 累计时间偏移

                for project_id in sorted_project_ids:
                    segments_in_project = project_groups[project_id]
                    segments_in_project.sort(key=lambda x: x[0])

                    for i, segment_data in segments_in_project:
                        start_time = segment_data['start_time']
                        end_time = segment_data['end_time']
                        duration = end_time - start_time
                        text = segment_data['text']

                        # 调整时间轴：基于累计偏移
                        new_start = current_offset
                        new_end = current_offset + duration

                        # 写入字幕
                        f.write(f"{subtitle_index}\n")
                        f.write(f"{self._format_time(new_start)} --> {self._format_time(new_end)}\n")
                        f.write(f"{text}\n\n")

                        # 注意：跨项目连续切割已在切割阶段触发过片段回调，这里不再重复触发

                        subtitle_index += 1
                        current_offset = new_end  # 更新累计偏移

            self.log_message(f"  ✓ 字幕文件创建成功 (包含 {total_segments} 条字幕)")
            self.update_progress(98, 100, "字幕文件生成完成")

            # 更新进度（移除旧的100%更新）
            # self.update_progress(100, 100, "跨项目连续切割完成！")

            self.log_message("\n" + "=" * 60)
            self.log_message("跨项目连续切割完成！")
            self.log_message(f"输出目录: {base_dir}")
            self.log_message("=" * 60)

            # 所有任务完成，进度更新到100%
            self.update_progress(100, 100, "处理完成！")

            # 停止时间跟踪（成功）
            self.stop_time_tracking(success=True)

            # 检测是否为队列模式
            is_queue_mode = (hasattr(self, 'dialog') and
                           self.dialog.__class__.__name__ == 'DummyWidget')

            if not is_queue_mode:
                # 非队列模式，显示成功提示
                self.show_success_dialog(base_dir)
            else:
                # 队列模式，只记录日志
                self.log_message(f"[队列模式] 跨项目连续切割完成，输出路径: {base_dir}")

            return base_dir

        except Exception as e:
            self.log_message(f"跨项目连续切割失败: {e}")
            import traceback
            self.log_message(traceback.format_exc())
            self.stop_time_tracking(success=False)
            self.show_failure_dialog(str(e))
            return None
        finally:
            # 恢复按钮状态
            self.is_processing = False
            self.start_button.config(text="开始处理", state="normal")

    def _trigger_segment_callbacks(self, start_index, end_index):
        """触发指定范围的片段完成回调

        Args:
            start_index: 起始片段索引（包含）
            end_index: 结束片段索引（不包含）
        """
        if hasattr(self, 'on_segment_exported') and self.on_segment_exported:
            for i in range(start_index, end_index):
                try:
                    self.on_segment_exported(i)
                except Exception:
                    # 回调失败不应影响导出流程
                    pass

    def _format_time(self, seconds):
        """格式化时间为SRT格式"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


    def _apply_smart_validation(self, final_output, base_dir):
        """应用智能校验与自动调整 - 方案B核心功能"""
        try:
            if not SMART_VALIDATION_AVAILABLE or not export_validator:
                self.log_message("[WARN] 智能校验功能不可用，跳过校验")
                return

            video_file = final_output.get('video_file')
            srt_file = final_output.get('srt_file')

            if not video_file or not srt_file or not os.path.exists(video_file) or not os.path.exists(srt_file):
                self.log_message("[WARN] 视频或字幕文件不存在，跳过智能校验")
                return

            self.log_message("开始智能时间轴校验与自动调整...")

            # 更新校验配置
            if hasattr(self, 'smart_validation_var'):
                export_validator.config.enabled = self.smart_validation_var.get()
            if hasattr(self, 'auto_correct_var'):
                export_validator.config.auto_correct = self.auto_correct_var.get()
            if hasattr(self, 'validation_level_var'):
                export_validator.config.validation_level = self.validation_level_var.get()

            # 创建进度回调
            def validation_progress(current, total, message):
                progress = int((current / total) * 100)
                self.log_message(f"智能校验进度 {progress}%: {message}")

            # 执行智能校验，生成Calibrated.srt
            validation_result = export_validator.export_with_smart_validation(
                video_file, srt_file, base_dir, "Calibrated", validation_progress
            )

            # 处理校验结果
            if validation_result['success']:
                status = validation_result['validation'].get('action', 'unknown')

                if status == 'no_correction_needed':
                    deviation = validation_result['validation'].get('deviation', 0)
                    self.log_message(f"智能校验通过: 时间轴精度良好 (偏差: {deviation:.3f}s)")

                elif status == 'corrected':
                    strategy = validation_result['validation'].get('strategy', 'unknown')
                    improvement = validation_result['validation'].get('improvement', 0)
                    deviation_before = validation_result['validation'].get('deviation_before', 0)
                    deviation_after = validation_result['validation'].get('deviation_after', 0)

                    self.log_message(f"智能校验修正完成:")
                    self.log_message(f"修正策略: {strategy}")
                    self.log_message(f"修正前偏差: {deviation_before:.3f}s")
                    self.log_message(f"修正后偏差: {deviation_after:.3f}s")
                    self.log_message(f"改善程度: {improvement:.3f}s")

                    # 处理校验后的文件
                    corrected_file = validation_result.get('corrected_file')
                    if corrected_file and os.path.exists(corrected_file):
                        # 确保校验后的文件命名为Calibrated.srt
                        calibrated_file = os.path.join(base_dir, "Calibrated.srt")
                        if corrected_file != calibrated_file:
                            try:
                                import shutil
                                shutil.copy2(corrected_file, calibrated_file)
                                self.log_message(f"校准字幕已保存为: Calibrated.srt")
                            except Exception as e:
                                self.log_message(f"保存校准字幕失败: {e}")

                        # 保留原始合并文件，不更新final_output['srt_file']
                        self.log_message(f"已生成校准字幕: Calibrated.srt")

                # 显示报告路径
                report_path = validation_result.get('report_path')
                if report_path and os.path.exists(report_path):
                    self.log_message(f"校验报告已生成: {os.path.basename(report_path)}")

            else:
                error = validation_result.get('error', '未知错误')
                self.log_message(f"智能校验失败: {error}")

                if validation_result.get('fallback'):
                    self.log_message("   已回退到原始字幕文件")

        except Exception as e:
            self.log_message(f"智能校验过程异常: {e}")
            import traceback
            self.log_message(f"详细错误: {traceback.format_exc()}")

    def _apply_single_project_smart_validation(self, base_dir, video_name):
        """应用单项目智能校验与自动调整 - 方案B扩展到单项目"""
        try:
            if not SMART_VALIDATION_AVAILABLE or not export_validator:
                self.log_message("[WARN] 智能校验功能不可用，跳过单项目校验")
                return

            # 查找合并后的文件
            merged_video = os.path.join(base_dir, f"{video_name}.mp4")
            merged_srt = os.path.join(base_dir, f"{video_name}.srt")

            # 检查文件是否存在
            if not os.path.exists(merged_video) or not os.path.exists(merged_srt):
                self.log_message("[WARN] 合并后的视频或字幕文件不存在，跳过单项目智能校验")
                return

            self.log_message("开始单项目智能时间轴校验与自动调整...")

            # 更新校验配置
            if hasattr(self, 'smart_validation_var'):
                export_validator.config.enabled = self.smart_validation_var.get()
            if hasattr(self, 'auto_correct_var'):
                export_validator.config.auto_correct = self.auto_correct_var.get()
            if hasattr(self, 'validation_level_var'):
                export_validator.config.validation_level = self.validation_level_var.get()

            # 创建进度回调
            def validation_progress(current, total, message):
                progress = int((current / total) * 100)
                self.log_message(f"单项目校验进度 {progress}%: {message}")

            # 执行智能校验，生成Calibrated.srt
            validation_result = export_validator.export_with_smart_validation(
                merged_video, merged_srt, base_dir, "Calibrated", validation_progress
            )

            # 处理校验结果
            if validation_result['success']:
                status = validation_result['validation'].get('action', 'unknown')

                if status == 'no_correction_needed':
                    deviation = validation_result['validation'].get('deviation', 0)
                    self.log_message(f"单项目智能校验通过: 时间轴精度良好 (偏差: {deviation:.3f}s)")

                elif status == 'corrected':
                    strategy = validation_result['validation'].get('strategy', 'unknown')
                    improvement = validation_result['validation'].get('improvement', 0)
                    deviation_before = validation_result['validation'].get('deviation_before', 0)
                    deviation_after = validation_result['validation'].get('deviation_after', 0)

                    self.log_message(f"单项目智能校验修正完成:")
                    self.log_message(f"修正策略: {strategy}")
                    self.log_message(f"修正前偏差: {deviation_before:.3f}s")
                    self.log_message(f"修正后偏差: {deviation_after:.3f}s")
                    self.log_message(f"改善程度: {improvement:.3f}s")

                    # 检查是否生成了修正后的文件
                    corrected_file = validation_result.get('corrected_file')
                    if corrected_file and os.path.exists(corrected_file):
                        self.log_message(f"已生成校准字幕: {os.path.basename(corrected_file)}")

                        # 确保校准后的文件命名为Calibrated.srt
                        calibrated_file = os.path.join(base_dir, "Calibrated.srt")
                        if corrected_file != calibrated_file:
                            try:
                                import shutil
                                shutil.copy2(corrected_file, calibrated_file)
                                self.log_message(f"校准字幕已保存为: Calibrated.srt")
                            except Exception as e:
                                self.log_message(f"保存校准字幕失败: {e}")

                        # 保留原始合并文件，不进行替换

                # 显示报告路径
                report_path = validation_result.get('report_path')
                if report_path and os.path.exists(report_path):
                    self.log_message(f"单项目校验报告已生成: {os.path.basename(report_path)}")

            else:
                error = validation_result.get('error', '未知错误')
                self.log_message(f"单项目智能校验失败: {error}")

                if validation_result.get('fallback'):
                    self.log_message("   已保持原始字幕文件")

            # 显示校验统计
            if hasattr(export_validator, 'get_validation_statistics'):
                stats = export_validator.get_validation_statistics()
                if stats.get('total_validations', 0) > 0:
                    self.log_message(f"校验统计: 总计{stats['total_validations']}次, 成功{stats['successful_validations']}次")

        except Exception as e:
            self.log_message(f"单项目智能校验过程异常: {e}")
            import traceback
            self.log_message(f"详细错误: {traceback.format_exc()}")




    def _format_timedelta(self, td):
        """格式化时间差为SRT格式"""
        total_seconds = int(td.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        milliseconds = int(td.microseconds / 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


    def _get_video_duration(self, video_file):
        """获取视频时长"""
        if not video_file or not os.path.exists(video_file):
            return 0

        try:
            cmd = ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
                   '-of', 'csv=p=0', video_file]
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore',
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            return float(result.stdout.strip())
        except:
            return 0

    def _get_external_script_duration(self, media_file):
        """获取媒体文件时长 - 方案7三重验证增强方法"""
        if not media_file or not os.path.exists(media_file):
            return 0.0

        # 方案6：使用稳定可靠的标准方法
        try:
            # 🏆 使用与外部脚本完全相同的ffprobe命令
            cmd = [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=nw=1:nk=1", media_file
            ]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            duration = float(result.stdout.strip())
            return duration
        except Exception as e:
            # 回退方法：使用简单的ffprobe命令
            try:
                cmd = ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
                       '-of', 'csv=p=0', media_file]
                result = subprocess.run(cmd, capture_output=True, text=True,
                                      encoding='utf-8', errors='ignore',
                                      creationflags=subprocess.CREATE_NO_WINDOW)
                return float(result.stdout.strip())
            except:
                return 0.0

    def _get_moviepy_duration(self, media_file, is_video=True):
        """获取媒体文件时长 - MoviePy方法（双重验证）"""
        if not media_file or not os.path.exists(media_file):
            return 0.0

        try:
            if is_video:
                from moviepy.editor import VideoFileClip
                with VideoFileClip(media_file) as clip:
                    return clip.duration
            else:
                from moviepy.editor import AudioFileClip
                with AudioFileClip(media_file) as clip:
                    return clip.duration
        except Exception as e:
            # 回退到ffprobe方法
            return self._get_external_script_duration(media_file)

    def _get_keyframe_aligned_duration(self, media_file):
        """获取关键帧对齐的精确时长（方案5高级技术）"""
        if not media_file or not os.path.exists(media_file):
            return 0.0

        try:
            # 🏆 关键帧对齐：获取最后一个关键帧的时间
            cmd = [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "packet=pts_time,flags",
                "-of", "csv=p=0", media_file
            ]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, creationflags=subprocess.CREATE_NO_WINDOW)

            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                last_keyframe_time = 0.0

                for line in lines:
                    if line and ',' in line:
                        parts = line.split(',')
                        if len(parts) >= 2:
                            try:
                                pts_time = float(parts[0])
                                flags = parts[1]
                                # 检查是否为关键帧（I帧）
                                if 'K' in flags:
                                    last_keyframe_time = pts_time
                            except:
                                continue

                if last_keyframe_time > 0:
                    return last_keyframe_time

            # 回退到标准方法
            return self._get_external_script_duration(media_file)

        except Exception as e:
            return self._get_external_script_duration(media_file)

    def _calculate_selected_segments_duration(self, project_id):
        """计算指定项目中实际选择的片段总时长 - 方案7亚毫秒级精准方法"""
        try:
            # 获取当前导出中该项目的所有片段
            selected_segments = []

            # 从segments_info中获取该项目的片段信息
            if hasattr(self, 'current_segments_info'):
                for segment_info in self.current_segments_info:
                    if segment_info.get('project_id') == project_id:
                        selected_segments.append(segment_info)

            if not selected_segments:
                self.log_message(f"[WARN] 项目 {project_id} 没有找到选择的片段信息")
                return 0.0

            # 方案6核心：标准精度计算（确保稳定性）
            total_duration = 0.0

            self.log_message(f"方案6片段级精准计算 - 项目 {project_id}")

            for segment_info in selected_segments:
                start_time = segment_info.get('start_time', 0)
                end_time = segment_info.get('end_time', 0)
                segment_duration = end_time - start_time
                total_duration += segment_duration
                self.log_message(f" 片段 {segment_info.get('index_num', '?')}: {start_time:.1f}s-{end_time:.1f}s = {segment_duration:.3f}s")

            self.log_message(f"项目 {project_id} 方案6精准总时长: {total_duration:.3f}s")
            return total_duration
            return total_duration

        except Exception as e:
            self.log_message(f"计算项目 {project_id} 片段时长失败: {e}")
            return 0.0

    def _get_real_media_duration(self, media_file):
        """获取媒体文件的真实时长（精确方法，类似单项目策略）"""
        # 为了向后兼容，保留此方法，但内部调用外部脚本方法
        return self._get_external_script_duration(media_file)

    def _cleanup_project_temp_dirs(self, base_dir):
        """清理项目临时目录"""
        import shutil
        import glob

        try:
            # 查找所有项目临时目录
            temp_pattern = os.path.join(base_dir, "project_*_temp")
            temp_dirs = glob.glob(temp_pattern)

            #if not temp_dirs:
                #self.log_message("🗂️ 没有找到需要清理的临时目录")
                #return

            #self.log_message(f"🗂️ 开始清理 {len(temp_dirs)} 个临时目录...")

            cleaned_count = 0
            for temp_dir in temp_dirs:
                try:
                    if os.path.exists(temp_dir):
                        # 获取目录名用于日志
                        dir_name = os.path.basename(temp_dir)

                        # 计算目录大小（用于统计）
                        dir_size = self._get_directory_size(temp_dir)

                        # 删除目录及其所有内容
                        shutil.rmtree(temp_dir)

                        #self.log_message(f"已删除: {dir_name} ({self._format_file_size(dir_size)})")
                        cleaned_count += 1

                except Exception as e:
                    dir_name = os.path.basename(temp_dir)
                    self.log_message(f"删除失败: {dir_name} - {e}")

            #if cleaned_count > 0:
                #self.log_message(f"🗂️ 临时目录清理完成: 成功删除 {cleaned_count} 个目录")
            #else:
                #self.log_message("[WARN]  没有成功删除任何临时目录")

        except Exception as e:
            self.log_message(f"临时目录清理异常: {e}")

    def _cleanup_original_files_after_merge(self, chunk_dir, base_dir, final_output):
        """合并完成后清理原始字幕文件和JSON文件（保留切割的片段文件）"""
        try:
            #self.log_message("🧹 开始清理原始字幕文件和JSON文件...")
            #self.log_message("   注意：保留所有切割的片段文件（视频、音频、字幕片段）")

            # 获取最终输出的文件名（不包括扩展名）
            final_video = final_output.get('video_file', '')
            final_srt = final_output.get('srt_file', '')

            if final_video:
                final_base_name = os.path.splitext(os.path.basename(final_video))[0]
                #self.log_message(f"最终输出基础名称: {final_base_name}")

            files_to_cleanup = []

            # 1. 只清理base_dir中的特定临时文件，不删除chunk_dir中的片段文件
            if os.path.exists(base_dir):
                for file in os.listdir(base_dir):
                    file_path = os.path.join(base_dir, file)
                    if os.path.isfile(file_path):
                        # 删除JSON文件
                        if file.endswith('.json'):
                            files_to_cleanup.append(file_path)
                        # 删除临时字幕文件（校验前的原始字幕）
                        elif file.endswith(('_original.srt', '_backup.srt', '_temp.srt')):
                            files_to_cleanup.append(file_path)
                        # 删除concat列表文件
                        elif file.endswith('.txt') and ('concat' in file or 'list' in file):
                            files_to_cleanup.append(file_path)
                        # 删除校验报告文件
                        elif file.endswith('_validation_report.txt'):
                            files_to_cleanup.append(file_path)

            # 2. 执行清理
            cleaned_count = 0
            for file_path in files_to_cleanup:
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        cleaned_count += 1
                        #self.log_message(f"已删除: {os.path.basename(file_path)}")
                except Exception as e:
                    self.log_message(f"删除失败 {os.path.basename(file_path)}: {e}")

            # 3. 清理项目临时目录（但保留chunk_dir）
            self._cleanup_project_temp_dirs(base_dir)

            if cleaned_count > 0:
                #self.log_message(f"🧹 文件清理完成: 成功删除 {cleaned_count} 个原始/临时文件")

                # 显示保留的文件
                #if final_video and os.path.exists(final_video):
                    #self.log_message(f"[KEEP] 保留最终视频: {os.path.basename(final_video)}")
                #if final_srt and os.path.exists(final_srt):
                    #self.log_message(f"[KEEP] 保留未校准字幕: {os.path.basename(final_srt)}")
                #if final_calibrated_srt and os.path.exists(final_calibrated_srt):
                    #self.log_message(f"[KEEP] 保留校准字幕: {os.path.basename(final_calibrated_srt)}")

                # 显示保留的片段文件
                if os.path.exists(chunk_dir):
                    chunk_files = [f for f in os.listdir(chunk_dir) if f.endswith(('.mp4', '.mp3', '.srt'))]
                    if chunk_files:
                        self.log_message(f"保留 {len(chunk_files)} 个切割片段文件")
            else:
                self.log_message("🧹 没有找到需要清理的文件")

        except Exception as e:
            self.log_message(f"文件清理过程异常: {e}")
            import traceback
            self.log_message(f"详细错误: {traceback.format_exc()}")

    def _cleanup_single_project_files(self, chunk_dir, base_dir, video_name):
        """单项目合并完成后清理原始字幕文件和JSON文件（保留切割的片段文件）"""
        try:
            #self.log_message("🧹 开始清理单项目原始字幕文件和JSON文件...")
            #self.log_message("   注意：保留所有切割的片段文件（视频、音频、字幕片段）")

            # 最终输出文件
            final_video = os.path.join(base_dir, f"{video_name}.mp4")
            final_srt = os.path.join(base_dir, f"{video_name}.srt")  # 未校准字幕
            final_calibrated_srt = os.path.join(base_dir, "Calibrated.srt")  # 校准后字幕
            final_audio = os.path.join(base_dir, f"{video_name}_audio.mp3")
            final_audio_srt = os.path.join(base_dir, f"{video_name}_audio.srt")  # 音频字幕

            files_to_cleanup = []

            # 1. 不删除chunk_dir中的片段文件，保留所有切割的片段
            # chunk_dir中的文件是切割生成的片段，需要保留

            # 2. 只清理base_dir中的特定临时文件
            if os.path.exists(base_dir):
                for file in os.listdir(base_dir):
                    file_path = os.path.join(base_dir, file)
                    if os.path.isfile(file_path):
                        # 保留最终输出文件
                        if file_path in [final_video, final_srt, final_calibrated_srt, final_audio, final_audio_srt]:
                            continue

                        # 删除JSON文件
                        if file.endswith('.json'):
                            files_to_cleanup.append(file_path)
                        # 删除临时字幕文件（校验前的原始字幕）
                        elif file.endswith(('_original.srt', '_backup.srt', '_temp.srt')):
                            files_to_cleanup.append(file_path)
                        # 删除concat列表文件
                        elif file.endswith('.txt') and ('concat' in file or 'list' in file):
                            files_to_cleanup.append(file_path)
                        # 删除校验报告文件
                        elif file.endswith('_validation_report.txt'):
                            files_to_cleanup.append(file_path)

            # 3. 执行清理
            cleaned_count = 0
            for file_path in files_to_cleanup:
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        cleaned_count += 1
                        #self.log_message(f"已删除: {os.path.basename(file_path)}")
                except Exception as e:
                    self.log_message(f"删除失败 {os.path.basename(file_path)}: {e}")

            #if cleaned_count > 0:
                #self.log_message(f"🧹 单项目文件清理完成: 成功删除 {cleaned_count} 个原始/临时文件")

                # 显示保留的最终文件
                #if os.path.exists(final_video):
                    #self.log_message(f"[KEEP] 保留最终视频: {os.path.basename(final_video)}")
                #if os.path.exists(final_srt):
                    #self.log_message(f"[KEEP] 保留未校准字幕: {os.path.basename(final_srt)}")
                #if os.path.exists(final_calibrated_srt):
                    #self.log_message(f"[KEEP] 保留校准字幕: {os.path.basename(final_calibrated_srt)}")
                #if os.path.exists(final_audio):
                    #self.log_message(f"[KEEP] 保留最终音频: {os.path.basename(final_audio)}")

                # 显示保留的片段文件
                #if os.path.exists(chunk_dir):
                    #chunk_files = [f for f in os.listdir(chunk_dir) if f.endswith(('.mp4', '.mp3', '.srt'))]
                    #if chunk_files:
                        #self.log_message(f"[KEEP] 保留 {len(chunk_files)} 个切割片段文件在: {os.path.basename(chunk_dir)}")
            #else:
                #self.log_message("🧹 没有找到需要清理的文件")

        except Exception as e:
            self.log_message(f"单项目文件清理过程异常: {e}")
            import traceback
            self.log_message(f"详细错误: {traceback.format_exc()}")

    def _get_directory_size(self, directory):
        """计算目录大小"""
        total_size = 0
        try:
            for dirpath, dirnames, filenames in os.walk(directory):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    if os.path.exists(filepath):
                        total_size += os.path.getsize(filepath)
        except Exception:
            pass
        return total_size

    def _format_file_size(self, size_bytes):
        """格式化文件大小显示"""
        if size_bytes == 0:
            return "0 B"

        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1

        return f"{size_bytes:.1f} {size_names[i]}"

    def _analyze_time_conflicts(self, segments_data):
        """分析时间轴冲突"""
        conflicts = []

        for i, segment1 in enumerate(segments_data):
            for j, segment2 in enumerate(segments_data[i+1:], i+1):
                # 检查时间轴是否重叠
                start1, end1 = segment1['start_time'], segment1['end_time']
                start2, end2 = segment2['start_time'], segment2['end_time']

                # 判断是否有重叠
                if not (end1 <= start2 or end2 <= start1):
                    conflict = {
                        'segment1': {'index': i+1, 'project': segment1['project_name'],
                                   'time': f"{start1:.1f}-{end1:.1f}s", 'text': segment1['text'][:20]},
                        'segment2': {'index': j+1, 'project': segment2['project_name'],
                                   'time': f"{start2:.1f}-{end2:.1f}s", 'text': segment2['text'][:20]},
                        'overlap_start': max(start1, start2),
                        'overlap_end': min(end1, end2)
                    }
                    conflicts.append(conflict)

        return conflicts

    def _handle_time_conflicts(self, conflicts):
        """处理时间轴冲突"""
        self.log_message("处理时间轴冲突策略：")

        for i, conflict in enumerate(conflicts, 1):
            seg1 = conflict['segment1']
            seg2 = conflict['segment2']
            overlap_duration = conflict['overlap_end'] - conflict['overlap_start']

            self.log_message(f"  冲突 {i}:")
            self.log_message(f" 片段{seg1['index']} ({seg1['project']}): {seg1['time']} \"{seg1['text']}...\"")
            self.log_message(f" 片段{seg2['index']} ({seg2['project']}): {seg2['time']} \"{seg2['text']}...\"")
            self.log_message(f" 重叠时长: {overlap_duration:.1f}秒")
            self.log_message(f" 策略: 顺序播放，保持原有时长")

    def _merge_cross_project_subtitles(self, chunk_dir, srt_files, output_file, segments_data):
        """跨项目字幕合并 - 处理不同项目相同时间轴的情况"""
        try:
            from datetime import timedelta

            merged_subs = []
            current_time = timedelta(seconds=0)
            subtitle_index = 1

            self.log_message("使用跨项目字幕合并策略...")

            for i, srt_file in enumerate(srt_files):
                srt_path = os.path.join(chunk_dir, srt_file)
                if not os.path.exists(srt_path):
                    continue

                # 检查是否有对应的片段数据
                if i >= len(segments_data):
                    self.log_message(f"警告：字幕文件 {srt_file} 没有对应的片段数据，跳过")
                    continue

                try:
                    # 获取对应的片段数据
                    segment_data = segments_data[i]

                    subs = pysrt.open(srt_path, encoding='utf-8-sig')

                    for sub in subs:
                        # 计算新的时间偏移
                        sub_start = timedelta(
                            hours=sub.start.hours,
                            minutes=sub.start.minutes,
                            seconds=sub.start.seconds,
                            milliseconds=sub.start.milliseconds
                        )
                        sub_end = timedelta(
                            hours=sub.end.hours,
                            minutes=sub.end.minutes,
                            seconds=sub.end.seconds,
                            milliseconds=sub.end.milliseconds
                        )

                        # 调整时间轴到当前位置
                        new_start = current_time + sub_start
                        new_end = current_time + sub_end

                        # 使用原始字幕文本，不添加项目标识（避免影响字幕显示）
                        enhanced_text = sub.text

                        # 项目标识仅用于调试日志，不写入最终字幕文件
                        if segment_data and len(set(seg['project_name'] for seg in segments_data)) > 1:
                            project_name = segment_data['project_name']
                            # 在日志中显示项目信息，但不写入字幕文件
                            if subtitle_index <= 3:  # 只在前几个字幕中显示调试信息
                                self.log_message(f" 字幕 {subtitle_index}: [{project_name}] {sub.text[:30]}...")

                        merged_sub = {
                            'index': subtitle_index,
                            'start': new_start,
                            'end': new_end,
                            'text': enhanced_text
                        }
                        merged_subs.append(merged_sub)
                        subtitle_index += 1

                    # 使用实际视频时长推进时间轴
                    if segment_data:
                        actual_duration = segment_data['end_time'] - segment_data['start_time']
                        current_time += timedelta(seconds=actual_duration)
                        self.log_message(f"  片段 {i+1}: 时长 {actual_duration:.1f}s, 累计时间 {current_time.total_seconds():.1f}s")
                    else:
                        current_time += timedelta(seconds=1.0)  # 默认时长

                except Exception as e:
                    self.log_message(f"处理字幕文件失败 {srt_file}: {e}")
                    continue

            # 保存合并后的字幕
            if merged_subs:
                def format_td(td: timedelta) -> str:
                    total_ms = int(td.total_seconds() * 1000)
                    hours = total_ms // 3600000
                    minutes = (total_ms % 3600000) // 60000
                    seconds = (total_ms % 60000) // 1000
                    millis = total_ms % 1000
                    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"

                with open(output_file, 'w', encoding='utf-8') as f:
                    for sub in merged_subs:
                        f.write(f"{sub['index']}\n")
                        f.write(f"{format_td(sub['start'])} --> {format_td(sub['end'])}\n")
                        f.write(f"{sub['text']}\n\n")

                self.log_message(f"跨项目字幕合并完成: {output_file}")
                self.log_message(f"合并了 {len(merged_subs)} 个字幕条目")
            else:
                self.log_message("没有有效的字幕内容可合并")

        except Exception as e:
            self.log_message(f"跨项目字幕合并错误: {e}")
            import traceback
            self.log_message(traceback.format_exc())

    def _process_single_segment_fast(self, video_file, sub, index, total, chunk_dir, is_audio_only):
        """处理单个片段（快速模式，用于并行处理）

        Args:
            video_file: 媒体文件路径
            sub: 字幕条目
            index: 片段索引（从1开始）
            total: 总片段数
            chunk_dir: 输出目录
            is_audio_only: 是否为纯音频文件

        Returns:
            (是否成功, 错误信息)
        """
        try:
            from moviepy.editor import VideoFileClip, AudioFileClip

            # 每个worker独立打开媒体文件（线程安全）
            if is_audio_only:
                media_clip = AudioFileClip(video_file)
            else:
                media_clip = VideoFileClip(video_file)

            # 计算时间
            start_time = sub.start.ordinal / 1000.0
            end_time = sub.end.ordinal / 1000.0

            # 生成文件名
            if self.naming_mode.get() == "subtitle":
                subtitle_text = sub.text.replace('\n', ' ').replace('\r', ' ')
                subtitle_text = ''.join(c for c in subtitle_text if c.isalnum() or c in (' ', '_', '-'))
                subtitle_text = subtitle_text.strip().replace(' ', '_')
                if not subtitle_text:
                    subtitle_text = f"clip_{index}"
                filename_base = f"{index:02d}.{subtitle_text}"
            else:
                filename_base = f"{index:02d}"

            # 输出路径
            video_output = os.path.join(chunk_dir, f"{filename_base}.mp4")
            audio_output = os.path.join(chunk_dir, f"{filename_base}.mp3")
            sub_output = os.path.join(chunk_dir, f"{filename_base}.srt")

            # 切割片段
            clip = media_clip.subclip(start_time, end_time)

            # 导出视频/音频
            if is_audio_only:
                clip.write_audiofile(
                    audio_output,
                    bitrate='192k',
                    logger=None,
                    verbose=False
                )
            else:
                clip.write_videofile(
                    video_output,
                    codec='libx264',
                    preset=self.preset_var.get(),
                    ffmpeg_params=['-crf', self.crf_var.get()],
                    audio_codec='aac',
                    logger=None,
                    verbose=False
                )
                if clip.audio is not None:
                    clip.audio.write_audiofile(
                        audio_output,
                        bitrate='192k',
                        logger=None,
                        verbose=False
                    )

            # 创建字幕文件
            sub_rel = pysrt.SubRipItem(
                index=1,
                start=pysrt.SubRipTime(seconds=0),
                end=pysrt.SubRipTime(seconds=end_time - start_time),
                text=sub.text
            )
            pysrt.SubRipFile([sub_rel]).save(sub_output, encoding='utf-8')

            # 关闭媒体文件
            media_clip.close()

            return True, None

        except Exception as e:
            return False, str(e)

    def _process_single_segment_reencode(self, video_file, sub, seg_index, chunk_dir, filename_base):
        """
        处理单个片段（重新编码）- 用于并行处理

        Args:
            video_file: 视频文件路径
            sub: 字幕对象
            seg_index: 片段索引
            chunk_dir: 输出目录
            filename_base: 文件名基础

        Returns:
            (success, error_msg): 成功返回(True, None)，失败返回(False, error_msg)
        """
        try:
            start_time = sub.start.ordinal / 1000.0
            end_time = sub.end.ordinal / 1000.0
            duration = end_time - start_time

            # 输出路径
            video_output = os.path.join(chunk_dir, f"{filename_base}.mp4")
            audio_output = os.path.join(chunk_dir, f"{filename_base}.mp3")
            sub_output = os.path.join(chunk_dir, f"{filename_base}.srt")

            # 使用FFmpeg重新编码切割
            success = self.cut_segment_with_reencode(
                video_file, start_time, end_time, video_output
            )

            if not success:
                return False, f"视频切割失败"

            # 提取音频（使用FFmpeg）
            try:
                audio_cmd = [
                    "ffmpeg", "-y",
                    "-i", video_output,
                    "-vn",  # 不处理视频
                    "-acodec", "libmp3lame",
                    "-b:a", "192k",
                    audio_output
                ]
                subprocess.run(
                    audio_cmd,
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
            except Exception as e:
                return False, f"音频提取失败: {e}"

            # 创建对应的字幕文件
            single_sub = pysrt.SubRipFile()
            new_sub = pysrt.SubRipItem(
                index=1,
                start=pysrt.SubRipTime(seconds=0),
                end=pysrt.SubRipTime(seconds=duration),
                text=sub.text
            )
            single_sub.append(new_sub)
            single_sub.save(sub_output, encoding='utf-8')

            return True, None

        except Exception as e:
            return False, str(e)

    def process_segments(self, video_file, srt_file, output_dir):
        """处理片段 - 使用FFmpeg直接切割，更稳定"""
        # 阻止系统休眠
        PowerManager.prevent_sleep()

        # 生成唯一的线程ID（使用更精确的方式避免冲突）
        import threading
        import time
        import random
        thread_id = f"{threading.current_thread().ident}_{int(time.time() * 1000000)}_{random.randint(1000, 9999)}"

        try:
            self.log_message("开始处理视频片段...")
            self.log_message(f"处理参数: video_file={video_file}")
            self.log_message(f"处理参数: srt_file={srt_file}")
            self.log_message(f"处理参数: output_dir={output_dir}")

            # 🔍 DEBUG: 输出导出参数
            self.log_message(f"[DEBUG-导出参数] 导出模式: {self.export_mode_var.get()}")
            self.log_message(f"[DEBUG-导出参数] 命名模式: {self.naming_mode.get()}")
            self.log_message(f"[DEBUG-导出参数] 编码预设: {self.preset_var.get()}")
            self.log_message(f"[DEBUG-导出参数] CRF质量: {self.crf_var.get()}")
            if self.export_mode_var.get() == "reencode":
                self.log_message(f"[DEBUG-导出参数] 编码分辨率: {self.resolution_var.get()}")
                self.log_message(f"[DEBUG-导出参数] 编码帧率: {self.fps_var.get()}")

            # 判断是否为队列导出
            is_queue_export = hasattr(self, 'queue_processor') and self.queue_processor is not None
            self.log_message(f"[DEBUG-导出来源] {'队列导出' if is_queue_export else '直接导出'}")

            # 🚨 大文件警告：检查视频文件大小（单项目导出）
            if self.export_mode_var.get() == "fast" and os.path.exists(video_file):
                video_size = os.path.getsize(video_file)
                video_size_gb = video_size / (1024**3)

                # 单个视频超过2GB显示简单警告
                if video_size > 2 * 1024**3:
                    self.log_message(f"⚠️ 检测到大文件: {os.path.basename(video_file)} ({video_size_gb:.2f}GB)")
                    self.log_message(f"⚠️ 快速模式预计内存占用: {video_size_gb * 3:.1f}GB - {video_size_gb * 5:.1f}GB")
                    self.log_message(f"⚠️ 建议使用重新编码以避免内存溢出问题")

                    # 在主线程中弹出简单警告对话框
                    def show_warning():
                        messagebox.showwarning(
                            "内存警告",
                            f"检测到大视频文件（{video_size_gb:.1f}GB）\n\n"
                            f"快速模式预计占用内存：{video_size_gb * 3:.1f}GB - {video_size_gb * 5:.1f}GB\n"
                            f"可能导致内存溢出或系统卡顿！\n\n"
                            f"建议：\n"
                            f"• 如需处理大文件，请手动切换到「重新编码」\n"
                            f"• 重新编码内存占用稳定，更适合大文件处理\n\n"
                            f"点击确定继续当前处理",
                            parent=self.dialog
                        )

                    # 暂停时间跟踪，等待用户确认警告
                    self.pause_time_tracking()
                    import threading
                    warning_event = threading.Event()

                    def show_warning_sync():
                        show_warning()
                        warning_event.set()  # 用户点击确认后设置事件

                    self.dialog.after(0, show_warning_sync)
                    self.log_message("⏳ 等待用户确认内存警告...")
                    warning_event.wait()  # 等待用户点击确定

                    # 恢复时间跟踪，继续处理
                    self.resume_time_tracking()
                    self.log_message("✓ 用户已确认警告，继续处理")

            # 读取字幕文件
            subs = pysrt.open(srt_file, encoding='utf-8-sig')
            total_subs = len(subs)

            if total_subs == 0:
                self.log_message("错误：字幕文件为空")
                return

            self.log_message(f"找到 {total_subs} 个字幕片段")

            # 获取视频基本信息（连续切割模式需要使用）
            video_name = Path(video_file).stem

            # 🔍 检测连续切割模式 - 兼容队列模式和直接模式
            if hasattr(self, 'continuous_cut_var') and self.continuous_cut_var:
                # 直接导出模式：从 UI 控件读取
                continuous_mode = self.continuous_cut_var.get()
            elif hasattr(self, 'queue_processor') and self.queue_processor:
                # 队列导出模式：从 queue_processor 获取当前任务的配置
                current_task = self.queue_processor.current_task
                if current_task and current_task.config:
                    continuous_mode = current_task.config.continuous_cut_mode
                else:
                    continuous_mode = False  # 默认不启用连续切割
            else:
                # 无法确定模式，使用默认值
                continuous_mode = False

            if continuous_mode:
                self.log_message("✓ 连续切割模式已启用")
            else:
                self.log_message("✓ 片段切割模式（默认）")

            self.log_message(f"字幕文件详细内容:")
            for i, sub in enumerate(subs, 1):
                start_time = sub.start.ordinal / 1000
                end_time = sub.end.ordinal / 1000
                self.log_message(f"  字幕 {i}: {start_time:.1f}-{end_time:.1f}s, '{sub.text[:30]}...'")

            # 🔄 连续切割模式处理：如果启用，则计算总时间范围
            if continuous_mode:
                # 计算总时间范围
                total_start_time = subs[0].start.ordinal / 1000.0
                total_end_time = subs[-1].end.ordinal / 1000.0
                total_duration = total_end_time - total_start_time

                self.log_message(f"连续切割时间范围: {total_start_time:.1f}s - {total_end_time:.1f}s (总时长: {total_duration:.1f}s)")

                # 🎯 连续切割模式：切割单个连续片段
                self.log_message("开始连续切割处理...")

                # 创建输出目录结构
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                base_dir_name = f"{video_name}_{timestamp}"
                base_dir = os.path.join(output_dir, base_dir_name)
                chunk_dir = os.path.join(base_dir, video_name)

                os.makedirs(chunk_dir, exist_ok=True)
                os.makedirs(base_dir, exist_ok=True)

                self.log_message(f"输出目录: {base_dir}")

                # 生成输出文件名 (固定为 01)
                filename_base = "01"
                video_output = os.path.join(chunk_dir, f"{filename_base}.mp4")
                audio_output = os.path.join(chunk_dir, f"{filename_base}.mp3")
                sub_output = os.path.join(chunk_dir, f"{filename_base}.srt")

                # 切割单个连续片段
                self.update_progress(0, 100, "正在切割连续片段...")

                # 获取字幕总数（用于进度计算）
                total_subs_count = len(subs)

                if self.export_mode_var.get() == "reencode":
                    # 重新编码 - 使用阶段性进度更新
                    self.log_message("  使用重新编码切割连续片段")

                    # 📊 开始处理（显示初始进度20%）
                    self.update_progress(20, 100, "正在切割视频...")
                    self._trigger_segment_callbacks(0, int(0.2 * total_subs_count))

                    success = self.cut_segment_with_reencode(
                        video_file, total_start_time, total_end_time, video_output
                    )

                    if success:
                        self.log_message("  ✓ 视频切割成功")

                        # 📊 视频切割完成（触发70%的片段完成回调）
                        self.update_progress(70, 100, "视频切割完成...")
                        self._trigger_segment_callbacks(int(0.2 * total_subs_count), int(0.7 * total_subs_count))

                        # 📊 音频提取
                        self.update_progress(75, 100, "正在提取音频...")
                        try:
                            audio_cmd = [
                                "ffmpeg", "-y",
                                "-i", video_output,
                                "-vn",
                                "-acodec", "libmp3lame",
                                "-b:a", "192k",
                                audio_output
                            ]
                            subprocess.run(
                                audio_cmd,
                                capture_output=True,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                            )
                            self.log_message("  ✓ 音频提取成功")

                            # 📊 音频提取完成（触发90%的片段完成回调）
                            self.update_progress(90, 100, "音频提取完成...")
                            self._trigger_segment_callbacks(int(0.7 * total_subs_count), int(0.9 * total_subs_count))

                        except Exception as e:
                            self.log_message(f"  ⚠ 音频提取失败: {e}")
                    else:
                        self.log_message("  ✗ 视频切割失败")
                        return
                else:
                    # 快速模式 - 使用 MoviePy
                    self.log_message("  使用快速模式切割连续片段")
                    from moviepy.editor import VideoFileClip, AudioFileClip
                    from utils.file_utils import FileUtils

                    try:
                        is_audio_only = FileUtils.is_audio_file(video_file)

                        if is_audio_only:
                            # 纯音频文件
                            self.log_message("  正在加载音频...")
                            self.update_progress(0, 100, "正在处理音频...")
                            audio_clip = AudioFileClip(video_file)
                            clip = audio_clip.subclip(total_start_time, total_end_time)

                            # 📊 开始处理（显示初始进度20%）
                            self.update_progress(20, 100, "正在写入音频...")
                            self._trigger_segment_callbacks(0, int(0.2 * total_subs_count))

                            clip.write_audiofile(
                                audio_output,
                                bitrate='192k',
                                logger=None,
                                verbose=False
                            )
                            self.log_message("  ✓ 音频切割成功")

                            # 📊 音频切割完成（触发90%的片段）
                            self.update_progress(90, 100, "音频切割完成...")
                            self._trigger_segment_callbacks(int(0.2 * total_subs_count), int(0.9 * total_subs_count))

                            audio_clip.close()
                        else:
                            # 视频文件
                            self.log_message("  正在加载视频...")
                            video_clip = VideoFileClip(video_file)
                            clip = video_clip.subclip(total_start_time, total_end_time)

                            # 📊 开始处理（显示初始进度20%）
                            self.update_progress(20, 100, "正在写入视频...")
                            self._trigger_segment_callbacks(0, int(0.2 * total_subs_count))

                            # 写入视频
                            clip.write_videofile(
                                video_output,
                                codec='libx264',
                                preset=self.preset_var.get(),
                                ffmpeg_params=['-crf', self.crf_var.get()],
                                audio_codec='aac',
                                logger=None,
                                verbose=False
                            )
                            self.log_message("  ✓ 视频切割成功")

                            # 📊 视频写入完成（触发70%的片段）
                            self.update_progress(70, 100, "视频写入完成...")
                            self._trigger_segment_callbacks(int(0.2 * total_subs_count), int(0.7 * total_subs_count))

                            # 写入音频
                            if clip.audio is not None:
                                self.update_progress(75, 100, "正在写入音频...")

                                clip.audio.write_audiofile(
                                    audio_output,
                                    bitrate='192k',
                                    logger=None,
                                    verbose=False
                                )
                                self.log_message("  ✓ 音频切割成功")

                                # 📊 音频写入完成（触发90%的片段）
                                self.update_progress(90, 100, "音频写入完成...")
                                self._trigger_segment_callbacks(int(0.7 * total_subs_count), int(0.9 * total_subs_count))

                            video_clip.close()
                    except Exception as e:
                        self.log_message(f"  ✗ 快速模式切割失败: {e}")
                        return

                # 生成合并的字幕文件 (时间轴调整为从0开始)
                # 📊 在生成字幕文件的同时，触发剩余未完成片段的回调（90% → 100%）
                self.log_message("  生成连续切割字幕文件...")

                # 字幕生成阶段：触发剩余10%的片段（90% → 100%）
                already_triggered = int(0.9 * total_subs_count)

                with open(sub_output, 'w', encoding='utf-8') as f:
                    for idx, sub in enumerate(subs, 1):
                        # 调整时间轴: 减去起始时间
                        new_start_sec = (sub.start.ordinal / 1000.0) - total_start_time
                        new_end_sec = (sub.end.ordinal / 1000.0) - total_start_time

                        # 转换为 SRT 时间格式
                        new_start = self._format_time(new_start_sec)
                        new_end = self._format_time(new_end_sec)

                        f.write(f"{idx}\n")
                        f.write(f"{new_start} --> {new_end}\n")
                        f.write(f"{sub.text}\n\n")

                        # 📊 每写入一条字幕，检查是否需要触发片段完成回调
                        # 只触发尚未触发的片段（idx-1 >= already_triggered 的片段）
                        if (idx - 1) >= already_triggered:
                            if hasattr(self, 'on_segment_exported') and self.on_segment_exported:
                                try:
                                    self.on_segment_exported(idx - 1)  # 传递片段索引（从0开始）
                                except Exception as callback_error:
                                    # 回调失败不应影响导出流程，仅记录日志
                                    self.log_message(f"  ⚠ 片段完成回调失败 (片段 {idx}): {callback_error}")

                self.log_message(f"  ✓ 字幕文件创建成功 (包含 {total_subs_count} 条字幕)")

                # 更新进度
                self.update_progress(100, 100, "连续切割完成！")
                self.log_message(f"连续切割完成！输出到: {chunk_dir}")

                # 停止时间跟踪（成功）
                self.stop_time_tracking(success=True)

                # 检测是否为队列模式
                is_queue_mode = (hasattr(self, 'dialog') and
                               self.dialog.__class__.__name__ == 'DummyWidget')

                if not is_queue_mode:
                    # 非队列模式，显示成功提示
                    def on_success_complete():
                        self.is_processing = False
                        self.start_button.config(text="开始处理", state="normal")
                        self.show_success_dialog(base_dir)

                    self.dialog.after(0, on_success_complete)
                else:
                    # 队列模式，只记录日志
                    self.log_message(f"[队列模式] 连续切割完成，输出路径: {base_dir}")

                # 连续切割模式完成，直接返回
                return base_dir

            # 验证字幕文件路径
            if not os.path.exists(srt_file):
                self.log_message(f"字幕文件不存在: {srt_file}")
                return

            # 检查字幕文件大小
            file_size = os.path.getsize(srt_file)
            self.log_message(f"字幕文件大小: {file_size} 字节")

            # 获取视频基本信息
            video_name = Path(video_file).stem

            # 使用FFprobe获取视频时长
            try:
                cmd = ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
                       '-of', 'csv=p=0', video_file]
                result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore',
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                video_duration = float(result.stdout.strip())
                self.log_message(f"视频时长: {video_duration:.2f}秒")
            except:
                self.log_message("无法获取视频时长，继续处理...")
            # 创建输出目录结构 - 添加时间戳
            # 生成时间戳
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_dir_name = f"{video_name}_{timestamp}"

            # 🔍 DEBUG: 文件命名逻辑
            self.log_message(f"[DEBUG-命名逻辑] 视频名称: {video_name}")
            self.log_message(f"[DEBUG-命名逻辑] 时间戳: {timestamp}")
            self.log_message(f"[DEBUG-命名逻辑] 基础目录名: {base_dir_name}")

            # 创建输出目录结构 - 完全复用外部脚本逻辑
            # 外部脚本结构：output_root/video_name/video_name/
            base_dir = os.path.join(output_dir, base_dir_name)  # 外层目录（带时间戳）
            chunk_dir = os.path.join(base_dir, video_name)   # 内层目录（存放片段）

            # 🔍 DEBUG: 输出目录路径
            self.log_message(f"[DEBUG-目录结构] 用户指定输出目录: {output_dir}")
            self.log_message(f"[DEBUG-目录结构] 外层目录(base_dir): {base_dir}")
            self.log_message(f"[DEBUG-目录结构] 片段目录(chunk_dir): {chunk_dir}")

            # 创建目录
            os.makedirs(chunk_dir, exist_ok=True)
            os.makedirs(base_dir, exist_ok=True)

            self.log_message(f"输出目录结构:")
            self.log_message(f"  片段目录: {chunk_dir}")
            self.log_message(f"  合并目录: {base_dir}")

            # ⚡ 性能优化：使用MoviePy，媒体只加载一次
            from moviepy.editor import VideoFileClip, AudioFileClip
            from utils.file_utils import FileUtils

            video_clip = None
            audio_clip = None
            parallel_done = False  # 标记是否已完成并行处理

            try:
                # 加载媒体文件（仅在快速模式下）
                if self.export_mode_var.get() == "fast":
                    # 检测文件类型
                    is_audio_only = FileUtils.is_audio_file(video_file)

                    # 使用并行处理
                    if PARALLEL_PROCESSING_AVAILABLE:
                        self.log_message("⚡ 使用并行处理模式（多线程切割）")

                        # 计算最优worker数量
                        max_workers = calculate_optimal_workers(
                            'video' if not is_audio_only else 'light',
                            log_callback=self.log_message
                        )
                        self.log_message(f"使用 {max_workers} 个并行worker处理 {total_subs} 个片段")

                        # 并行处理片段
                        with ThreadPoolExecutor(max_workers=max_workers) as executor:
                            futures = []
                            for i, sub in enumerate(subs, 1):
                                if self.cancel_flag or (hasattr(self, 'queue_processor') and self.queue_processor and self.queue_processor.cancel_requested):
                                    self.log_message("用户取消操作")
                                    break

                                future = executor.submit(
                                    self._process_single_segment_fast,
                                    video_file, sub, i, total_subs, chunk_dir, is_audio_only
                                )
                                futures.append((future, i, sub))

                            # 等待所有任务完成
                            completed = 0
                            failed = 0
                            for future, seg_index, sub in futures:
                                if self.cancel_flag or (hasattr(self, 'queue_processor') and self.queue_processor and self.queue_processor.cancel_requested):
                                    self.log_message("用户取消操作")
                                    break

                                try:
                                    success, error_msg = future.result()
                                    if success:
                                        completed += 1
                                        self.log_message(f"  [{seg_index}/{total_subs}] 切割完成")

                                        # 触发片段完成回调
                                        if hasattr(self, 'on_segment_exported') and self.on_segment_exported:
                                            try:
                                                self.on_segment_exported(seg_index - 1)
                                            except Exception as callback_error:
                                                self.log_message(f"  ⚠ 片段完成回调失败: {callback_error}")
                                    else:
                                        failed += 1
                                        self.log_message(f"  [错误] 片段 {seg_index} 切割失败: {error_msg}")

                                    # 更新进度
                                    progress_percent = int(((completed + failed) / total_subs) * 90)
                                    self.update_progress(progress_percent, 100, f"处理片段 {completed + failed}/{total_subs}")
                                except Exception as e:
                                    self.log_message(f"  [错误] 片段 {seg_index} 处理异常: {e}")
                                    failed += 1

                        if failed > 0:
                            self.log_message(f"片段切割完成：成功 {completed} 个，失败 {failed} 个")
                        else:
                            self.log_message(f"片段切割完成：{completed} 个片段")

                        # 跳过后面的串行处理逻辑
                        video_clip = None
                        audio_clip = None
                        parallel_done = True  # 标记并行处理已完成
                    else:
                        # Fallback: 使用原有的串行处理
                        self.log_message("⚡ 使用MoviePy优化处理（媒体只加载一次）")
                        parallel_done = False

                        if is_audio_only:
                            self.log_message(f"正在加载音频到内存...")
                            audio_clip = AudioFileClip(video_file)
                            self.log_message(f"✓ 音频加载成功，时长: {audio_clip.duration:.2f}秒")
                        else:
                            self.log_message(f"正在加载视频到内存...")
                            video_clip = VideoFileClip(video_file)
                            self.log_message(f"✓ 视频加载成功，时长: {video_clip.duration:.2f}秒")

                # 重新编码的并行处理
                elif self.export_mode_var.get() == "reencode":
                    self.log_message("使用重新编码，跳过MoviePy加载")

                    if PARALLEL_PROCESSING_AVAILABLE:
                        self.log_message("⚡ 使用并行处理模式（多线程重新编码）")

                        max_workers = calculate_optimal_workers(
                            'video',
                            log_callback=self.log_message
                        )
                        self.log_message(f"使用 {max_workers} 个并行worker处理 {total_subs} 个片段")

                        with ThreadPoolExecutor(max_workers=max_workers) as executor:
                            futures = []
                            for i, sub in enumerate(subs, 1):
                                # 检查取消标志
                                if self.cancel_flag or (hasattr(self, 'queue_processor') and self.queue_processor and self.queue_processor.cancel_requested):
                                    self.log_message("用户取消操作")
                                    break

                                # 生成文件名
                                if self.naming_mode.get() == "subtitle":
                                    subtitle_text = sub.text.replace('\n', ' ').replace('\r', ' ')
                                    subtitle_text = ''.join(c for c in subtitle_text if c.isalnum() or c in (' ', '_', '-'))
                                    subtitle_text = subtitle_text.strip().replace(' ', '_')
                                    if not subtitle_text:
                                        subtitle_text = f"clip_{i}"
                                    filename_base = f"{i:02d}.{subtitle_text}"
                                else:
                                    filename_base = f"{i:02d}"

                                future = executor.submit(
                                    self._process_single_segment_reencode,
                                    video_file, sub, i, chunk_dir, filename_base
                                )
                                futures.append((future, i, sub))

                            # 等待所有任务完成
                            completed = 0
                            failed = 0
                            for future, seg_index, sub in futures:
                                if self.cancel_flag or (hasattr(self, 'queue_processor') and self.queue_processor and self.queue_processor.cancel_requested):
                                    self.log_message("用户取消操作")
                                    break

                                try:
                                    success, error_msg = future.result()
                                    if success:
                                        completed += 1
                                        self.log_message(f"  [{seg_index}/{total_subs}] 切割完成")

                                        # 触发片段完成回调
                                        if hasattr(self, 'on_segment_exported') and self.on_segment_exported:
                                            try:
                                                self.on_segment_exported(seg_index - 1)
                                            except Exception as callback_error:
                                                self.log_message(f"  ⚠ 片段完成回调失败: {callback_error}")
                                    else:
                                        failed += 1
                                        self.log_message(f"  [错误] 片段 {seg_index} 切割失败: {error_msg}")

                                    # 更新进度
                                    progress_percent = int(((completed + failed) / total_subs) * 90)
                                    self.update_progress(progress_percent, 100, f"处理片段 {completed + failed}/{total_subs}")
                                except Exception as e:
                                    self.log_message(f"  [错误] 片段 {seg_index} 处理异常: {e}")
                                    failed += 1

                            if failed > 0:
                                self.log_message(f"片段切割完成：成功 {completed} 个，失败 {failed} 个")
                            else:
                                self.log_message(f"片段切割完成：{completed} 个片段")

                        # 跳过后面的串行处理逻辑
                        video_clip = None
                        audio_clip = None
                        parallel_done = True  # 标记并行处理已完成
                    else:
                        # Fallback: 使用串行处理
                        self.log_message("使用重新编码（串行处理）")
                        parallel_done = False
                else:
                    self.log_message("使用重新编码，跳过MoviePy加载")
                    parallel_done = False

                # 处理每个字幕片段（仅在非并行模式或重新编码下执行）
                # 如果并行处理已完成，跳过串行处理
                if not parallel_done and (video_clip or audio_clip or self.export_mode_var.get() == "reencode"):
                    for i, sub in enumerate(subs, 1):
                        # DEBUG: 记录循环开始和标志状态
                        self.log_message(f"[DEBUG] 开始处理片段 {i}, self.cancel_flag={self.cancel_flag if hasattr(self, 'cancel_flag') else 'N/A'}, queue_processor={hasattr(self, 'queue_processor')}, queue_processor.cancel_requested={self.queue_processor.cancel_requested if hasattr(self, 'queue_processor') and self.queue_processor else 'N/A'}")

                        # 检查取消标志（本地取消或队列处理器取消）
                        cancel_requested = False
                        if self.cancel_flag:
                            cancel_requested = True
                            self.log_message(f"检测到本地取消标志 (片段 {i})")
                        elif hasattr(self, 'queue_processor') and self.queue_processor and self.queue_processor.cancel_requested:
                            cancel_requested = True
                            self.log_message(f"检测到队列处理器取消请求 (片段 {i})")

                        if cancel_requested:
                            self.log_message("用户取消操作")
                            break

                        try:
                            # 计算时间
                            start_time = sub.start.ordinal / 1000.0
                            end_time = sub.end.ordinal / 1000.0
                            duration = end_time - start_time

                            # 确保时间有效
                            if start_time >= end_time or duration <= 0:
                                self.log_message(f"跳过无效片段 {i}: 时间范围错误")
                                continue

                            # 生成文件名 - 完全复用外部脚本的命名逻辑
                            if self.naming_mode.get() == "subtitle":
                                subtitle_text = sub.text.replace('\n', ' ').replace('\r', ' ')
                                subtitle_text = ''.join(c for c in subtitle_text if c.isalnum() or c in (' ', '_', '-'))
                                subtitle_text = subtitle_text.strip().replace(' ', '_')
                                if not subtitle_text:
                                    subtitle_text = f"clip_{i}"
                                filename_base = f"{i:02d}.{subtitle_text}"
                            else:
                                filename_base = f"{i:02d}"

                            self.log_message(f"处理片段 {i}/{total_subs}: 文件名={filename_base}, 时间={start_time:.1f}-{end_time:.1f}s")

                            # 更新进度（片段切割阶段占0-90%）
                            progress_percent = int(((i-1) / total_subs) * 90)
                            self.update_progress(progress_percent, 100, f"处理片段 {i}/{total_subs}: {sub.text[:30]}...")

                            # 输出路径
                            video_output = os.path.join(chunk_dir, f"{filename_base}.mp4")
                            audio_output = os.path.join(chunk_dir, f"{filename_base}.mp3")
                            sub_output = os.path.join(chunk_dir, f"{filename_base}.srt")

                            # 根据导出模式选择处理方法
                            if self.export_mode_var.get() == "reencode":
                                # 重新编码：从原视频重新切割，统一参数
                                self.log_message(f"  使用重新编码切割片段 {i}")

                                # 使用FFmpeg重新编码切割
                                success = self.cut_segment_with_reencode(
                                    video_file, start_time, end_time, video_output
                                )

                                if success:
                                    self.log_message(f"  ✓ 视频切割成功（已统一参数）{i}")

                                    # 提取音频（使用FFmpeg）
                                    try:
                                        audio_cmd = [
                                            "ffmpeg", "-y",
                                            "-i", video_output,
                                            "-vn",  # 不处理视频
                                            "-acodec", "libmp3lame",
                                            "-b:a", "192k",
                                            audio_output
                                        ]
                                        subprocess.run(
                                            audio_cmd,
                                            capture_output=True,
                                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                                        )
                                        self.log_message(f"  ✓ 音频提取成功 {i}")
                                    except Exception as e:
                                        self.log_message(f"  ⚠ 音频提取失败: {e}")
                                else:
                                    self.log_message(f"  ✗ 视频切割失败 {i}")
                                    continue
                            else:
                                # 快速模式：使用MoviePy在内存中快速切割
                                self.log_message(f"  使用快速模式切割片段 {i}")

                                if video_clip:
                                    # 视频文件：切割视频和音频
                                    clip = video_clip.subclip(start_time, end_time)

                                    # 写入视频文件
                                    clip.write_videofile(
                                        video_output,
                                        codec='libx264',
                                        preset=self.preset_var.get(),
                                        ffmpeg_params=['-crf', self.crf_var.get()],
                                        audio_codec='aac',
                                        logger=None,
                                        verbose=False
                                    )
                                    self.log_message(f"  ✓ 视频切割成功 {i}")

                                    # 写入音频文件
                                    if clip.audio is not None:
                                        clip.audio.write_audiofile(
                                            audio_output,
                                            bitrate='192k',
                                            logger=None,
                                            verbose=False
                                        )
                                        self.log_message(f"  ✓ 音频切割成功 {i}")
                                    else:
                                        self.log_message(f"  ⚠ 警告：该片段无音频轨道 {i}")

                                elif audio_clip:
                                    # 纯音频文件：只切割音频
                                    clip = audio_clip.subclip(start_time, end_time)

                                    # 写入音频文件
                                    clip.write_audiofile(
                                        audio_output,
                                        bitrate='192k',
                                        logger=None,
                                        verbose=False
                                    )
                                    self.log_message(f"  ✓ 音频切割成功 {i}")

                                    # 纯音频模式不生成视频文件
                                    self.log_message(f"  ⓘ 纯音频模式，跳过视频生成 {i}")

                            # 创建对应的字幕文件
                            single_sub = pysrt.SubRipFile()
                            new_sub = pysrt.SubRipItem(
                                index=1,
                                start=pysrt.SubRipTime(seconds=0),
                                end=pysrt.SubRipTime(seconds=duration),
                                text=sub.text
                            )
                            single_sub.append(new_sub)
                            single_sub.save(sub_output, encoding='utf-8')
                            self.log_message(f"  ✓ 字幕文件创建成功 {i}")

                            # 触发片段完成回调（用于队列导出模式的实时进度更新）
                            if hasattr(self, 'on_segment_exported') and self.on_segment_exported:
                                try:
                                    self.on_segment_exported(i - 1)  # 传递片段索引（从0开始）
                                except Exception as callback_error:
                                    # 回调失败不应影响导出流程，仅记录日志
                                    self.log_message(f"  ⚠ 片段完成回调失败: {callback_error}")

                        except Exception as e:
                            self.log_message(f"  ✗ 处理片段 {i} 失败: {e}")
                            import traceback
                            self.log_message(f"详细错误: {traceback.format_exc()}")
                            continue

            finally:
                # 关闭媒体文件释放内存
                if video_clip:
                    try:
                        video_clip.close()
                        self.log_message(f"✓ 视频文件已关闭，释放内存")
                    except:
                        pass
                if audio_clip:
                    try:
                        audio_clip.close()
                        self.log_message(f"✓ 音频文件已关闭，释放内存")
                    except:
                        pass

            # 完成片段切割（进度90%，后续还有合并任务）
            self.update_progress(90, 100, "片段切割完成！开始合并...")
            self.log_message(f"所有片段切割完成，输出到: {chunk_dir}")

            # 自动合并片段 - 根据导出模式选择合并策略
            self.log_message("开始合并片段...")

            if self.export_mode_var.get() == "reencode":
                # 重新编码：使用简单合并策略（与跨项目重编码一致）
                self.log_message("使用简单合并策略（重新编码，参数已统一）")

                # 准备 segments_data（单项目场景）
                segments_data = []
                for sub in subs:
                    segments_data.append({
                        'project_id': self.segments[0].project_id if self.segments else 1,
                        'start_time': sub.start.ordinal / 1000.0,
                        'end_time': sub.end.ordinal / 1000.0,
                        'text': sub.text,
                        'video_path': video_file
                    })

                # 调用简单合并方法（生成2个字幕文件）
                self._simple_merge_with_unified_params(chunk_dir, base_dir, video_name, segments_data)
            else:
                # 快速模式：使用原有合并逻辑（生成1个字幕文件）
                self.merge_segments_like_external_script(chunk_dir, base_dir, video_name)

            self.log_message(f"处理完成！输出目录: {base_dir}")

            # 所有任务完成，进度更新到100%
            self.update_progress(100, 100, "处理完成！")

            # 停止时间跟踪（成功）
            self.stop_time_tracking(success=True)

            # 队列模式下不显示弹窗，直接返回输出路径
            # 检测是否为队列模式（dialog 是 DummyWidget）
            is_queue_mode = (hasattr(self, 'dialog') and
                           self.dialog.__class__.__name__ == 'DummyWidget')

            if not is_queue_mode:
                # 非队列模式，在主线程中处理完成后的UI更新
                def on_success_complete():
                    # 先恢复按钮状态
                    self.is_processing = False
                    self.start_button.config(text="开始处理", state="normal")
                    # 然后显示成功对话框（messagebox是模态的，会阻止用户点击其他控件）
                    self.show_success_dialog(base_dir)

                self.dialog.after(0, on_success_complete)
            else:
                # 队列模式，只记录日志
                self.log_message(f"[队列模式] 单项目导出完成，输出路径: {base_dir}")

            # 返回输出路径（供队列导出使用）
            return base_dir

        except Exception as e:
            self.log_message(f"处理过程中发生错误: {e}")
            import traceback
            self.log_message(traceback.format_exc())

            # 停止时间跟踪（失败）
            self.stop_time_tracking(success=False)

            # 在主线程中处理失败后的UI更新（参考导入对话框的方式）
            error_msg = str(e)
            def on_failure_complete():
                # 先恢复按钮状态
                self.is_processing = False
                self.start_button.config(text="开始处理", state="normal")
                # 延迟显示失败对话框，等待 UI 更新完成并稳定，防止 Windows MessageBox 关闭时误触发最小化
                self.dialog.after(100, lambda: self.show_failure_dialog(error_msg))

            self.dialog.after(0, on_failure_complete)

        finally:
            # 恢复系统休眠设置
            PowerManager.allow_sleep()

    def merge_segments_like_external_script(self, chunk_dir, base_dir, video_name):
        """合并片段 - 完全复用外部脚本的合并逻辑"""
        try:
            # 获取所有片段文件并排序
            def extract_leading_number(filename):
                match = re.match(r"(\d+)", os.path.splitext(filename)[0])
                return int(match.group(1)) if match else 0

            # 获取视频、音频、字幕文件
            video_files = [f for f in os.listdir(chunk_dir) if f.endswith('.mp4')]
            audio_files = [f for f in os.listdir(chunk_dir) if f.endswith('.mp3')]
            srt_files = [f for f in os.listdir(chunk_dir) if f.endswith('.srt')]

            video_files.sort(key=extract_leading_number)
            audio_files.sort(key=extract_leading_number)
            srt_files.sort(key=extract_leading_number)

            self.log_message(f"找到 {len(video_files)} 个视频片段")
            self.log_message(f"找到 {len(audio_files)} 个音频片段")
            self.log_message(f"找到 {len(srt_files)} 个字幕片段")

            # 检测是否为纯音频模式
            is_audio_only = len(video_files) == 0 and len(audio_files) > 0

            if is_audio_only:
                self.log_message("检测到纯音频模式（无视频文件）")
            else:
                # 检查文件数量是否匹配
                if len(video_files) != len(audio_files) or len(video_files) != len(srt_files):
                    self.log_message(f"[WARN] 文件数量不匹配！视频:{len(video_files)}, 音频:{len(audio_files)}, 字幕:{len(srt_files)}")
                else:
                    self.log_message(f"文件数量匹配: {len(video_files)} 个完整的片段组")

            # 合并视频文件（纯音频模式跳过）
            if video_files:
                # 检查取消标志
                if self.cancel_flag or (hasattr(self, 'queue_processor') and
                                       self.queue_processor and
                                       self.queue_processor.cancel_requested):
                    self.log_message("用户取消操作（合并视频前）")
                    return

                self.log_message("合并视频文件...")
                merged_video = os.path.join(base_dir, f"{video_name}.mp4")
                self.merge_video_files(chunk_dir, video_files, merged_video)
            elif is_audio_only:
                self.log_message("纯音频模式，跳过视频合并")

            # 合并音频文件
            if audio_files:
                # 检查取消标志
                if self.cancel_flag or (hasattr(self, 'queue_processor') and
                                       self.queue_processor and
                                       self.queue_processor.cancel_requested):
                    self.log_message("用户取消操作（合并音频前）")
                    return

                self.log_message("合并音频文件...")
                # 纯音频模式：不添加_audio后缀
                if is_audio_only:
                    merged_audio = os.path.join(base_dir, f"{video_name}.mp3")
                else:
                    merged_audio = os.path.join(base_dir, f"{video_name}_audio.mp3")
                self.merge_audio_files(chunk_dir, audio_files, merged_audio)

            # 合并字幕文件
            if srt_files:
                # 检查取消标志
                if self.cancel_flag or (hasattr(self, 'queue_processor') and
                                       self.queue_processor and
                                       self.queue_processor.cancel_requested):
                    self.log_message("用户取消操作（合并字幕前）")
                    return
                if is_audio_only:
                    # 纯音频模式：基于音频时长合并字幕
                    self.log_message("合并音频字幕文件（纯音频模式）...")
                    merged_srt = os.path.join(base_dir, f"{video_name}.srt")
                    self._merge_audio_subtitle_files_with_duration(chunk_dir, audio_files, merged_srt)
                else:
                    # 视频模式：基于视频时长合并字幕
                    self.log_message("合并视频字幕文件...")
                    merged_srt = os.path.join(base_dir, f"{video_name}.srt")
                    self.merge_subtitle_files_with_duration(chunk_dir, video_files, merged_srt)

                    # 同时生成音频字幕（基于音频时长）
                    if audio_files:
                        self.log_message("合并音频字幕文件...")
                        merged_audio_srt = os.path.join(base_dir, f"{video_name}_audio.srt")
                        self._merge_audio_subtitle_files_with_duration(chunk_dir, audio_files, merged_audio_srt)

            self.log_message("片段合并完成！")

            # 清理原始字幕文件和临时文件
            self._cleanup_single_project_files(chunk_dir, base_dir, video_name)

        except Exception as e:
            self.log_message(f"合并过程中发生错误: {e}")
            import traceback
            self.log_message(traceback.format_exc())

    def merge_video_files(self, chunk_dir, video_files, output_file):
        """合并视频文件"""
        try:
            # 创建临时文件列表
            temp_dir = tempfile.mkdtemp()
            list_file = os.path.join(temp_dir, "video_list.txt")

            with open(list_file, 'w', encoding='utf-8') as f:
                for video_file in video_files:
                    video_path = os.path.join(chunk_dir, video_file)
                    f.write(f"file '{video_path}'\n")

            # 使用FFmpeg合并
            cmd = [
                'ffmpeg', '-f', 'concat', '-safe', '0', '-i', list_file,
                '-c', 'copy', output_file, '-y'
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore',
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)

            if result.returncode == 0:
                self.log_message(f"视频合并成功: {output_file}")
            else:
                self.log_message(f"视频合并失败: {result.stderr}")

            # 清理临时文件
            try:
                os.unlink(list_file)
                os.rmdir(temp_dir)
            except:
                pass

        except Exception as e:
            self.log_message(f"视频合并错误: {e}")

    def merge_audio_files(self, chunk_dir, audio_files, output_file):
        """合并音频文件"""
        try:
            # 创建临时文件列表
            temp_dir = tempfile.mkdtemp()
            list_file = os.path.join(temp_dir, "audio_list.txt")

            with open(list_file, 'w', encoding='utf-8') as f:
                for audio_file in audio_files:
                    audio_path = os.path.join(chunk_dir, audio_file)
                    f.write(f"file '{audio_path}'\n")

            # 使用FFmpeg合并
            cmd = [
                'ffmpeg', '-f', 'concat', '-safe', '0', '-i', list_file,
                '-c', 'copy', output_file, '-y'
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore',
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)

            if result.returncode == 0:
                self.log_message(f"音频合并成功: {output_file}")
            else:
                self.log_message(f"音频合并失败: {result.stderr}")

            # 清理临时文件
            try:
                os.unlink(list_file)
                os.rmdir(temp_dir)
            except:
                pass

        except Exception as e:
            self.log_message(f"音频合并错误: {e}")

    def merge_subtitle_files_with_duration(self, chunk_dir, video_files, output_file):
        """合并字幕文件 - 统一使用直接调用方式获取时长"""
        try:
            from datetime import timedelta

            merged_subs = []
            current_time = timedelta(seconds=0)
            gap = 0.2  # 标准 gap
            gap_td = timedelta(seconds=gap)

            for i, video_file in enumerate(video_files):
                srt_file = os.path.join(chunk_dir, f"{os.path.splitext(video_file)[0]}.srt")
                if not os.path.exists(srt_file):
                    continue

                try:
                    subs = pysrt.open(srt_file, encoding='utf-8-sig')
                    for sub in subs:
                        sub_start = timedelta(
                            hours=sub.start.hours,
                            minutes=sub.start.minutes,
                            seconds=sub.start.seconds,
                            milliseconds=sub.start.milliseconds
                        )
                        sub_end = timedelta(
                            hours=sub.end.hours,
                            minutes=sub.end.minutes,
                            seconds=sub.end.seconds,
                            milliseconds=sub.end.milliseconds
                        )

                        # 调整时间轴
                        new_start = current_time + sub_start
                        new_end = current_time + sub_end

                        # 智能 gap 处理（防止字幕重叠）
                        if merged_subs:
                            prev_end = merged_subs[-1]['end']
                            if new_start < prev_end + gap_td:
                                new_start = prev_end + gap_td
                                if new_end < new_start:
                                    new_end = new_start + timedelta(milliseconds=500)

                        merged_subs.append({
                            'index': len(merged_subs) + 1,
                            'start': new_start,
                            'end': new_end,
                            'text': sub.text
                        })

                    # 使用 ffprobe 直接获取真实视频时长
                    video_path = os.path.join(chunk_dir, video_file)
                    duration = self._get_video_duration_ffprobe(video_path)
                    current_time += timedelta(seconds=duration)
                    self.log_message(f"  片段 {i+1}: 视频时长 {duration:.3f}s, 累计时间 {current_time.total_seconds():.3f}s")

                except Exception as e:
                    self.log_message(f"处理字幕文件失败 {srt_file}: {e}")

            # 保存合并后的字幕
            def format_timedelta(td):
                total_seconds = int(td.total_seconds())
                hours, remainder = divmod(total_seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                milliseconds = td.microseconds // 1000
                return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

            with open(output_file, 'w', encoding='utf-8') as f:
                for sub in merged_subs:
                    f.write(f"{sub['index']}\n")
                    f.write(f"{format_timedelta(sub['start'])} --> {format_timedelta(sub['end'])}\n")
                    f.write(f"{sub['text']}\n\n")

            self.log_message(f"字幕合并成功: {output_file}")
            # 不在这里停止时间跟踪或重置按钮状态
            # 这些操作应该在 process_segments 方法的最后统一处理

        except Exception as e:
            self.log_message(f"字幕合并错误: {e}")
            # 不在这里停止时间跟踪或重置按钮状态
            # 这些操作应该在 process_segments 方法的最后统一处理

    def _merge_audio_subtitle_files_with_duration(self, chunk_dir, audio_files, output_file):
        """合并音频字幕文件 - 统一使用直接调用方式获取时长"""
        try:
            from datetime import timedelta

            merged_subs = []
            current_time = timedelta(seconds=0)
            gap = 0.2  # 标准 gap
            gap_td = timedelta(seconds=gap)

            for i, audio_file in enumerate(audio_files):
                srt_file = os.path.join(chunk_dir, f"{os.path.splitext(audio_file)[0]}.srt")
                if not os.path.exists(srt_file):
                    continue

                try:
                    subs = pysrt.open(srt_file, encoding='utf-8-sig')
                    for sub in subs:
                        sub_start = timedelta(
                            hours=sub.start.hours,
                            minutes=sub.start.minutes,
                            seconds=sub.start.seconds,
                            milliseconds=sub.start.milliseconds
                        )
                        sub_end = timedelta(
                            hours=sub.end.hours,
                            minutes=sub.end.minutes,
                            seconds=sub.end.seconds,
                            milliseconds=sub.end.milliseconds
                        )

                        # 调整时间轴
                        new_start = current_time + sub_start
                        new_end = current_time + sub_end

                        # 智能 gap 处理（防止字幕重叠）
                        if merged_subs:
                            prev_end = merged_subs[-1]['end']
                            if new_start < prev_end + gap_td:
                                new_start = prev_end + gap_td
                                if new_end < new_start:
                                    new_end = new_start + timedelta(milliseconds=500)

                        merged_subs.append({
                            'index': len(merged_subs) + 1,
                            'start': new_start,
                            'end': new_end,
                            'text': sub.text
                        })

                    # 使用 ffprobe 直接获取真实音频时长
                    audio_path = os.path.join(chunk_dir, audio_file)
                    duration = self._get_audio_duration_ffprobe(audio_path)
                    current_time += timedelta(seconds=duration)
                    self.log_message(f"  片段 {i+1}: 音频时长 {duration:.3f}s, 累计时间 {current_time.total_seconds():.3f}s")

                except Exception as e:
                    self.log_message(f"处理字幕文件失败 {srt_file}: {e}")

            # 保存合并后的字幕
            def format_timedelta(td):
                total_seconds = int(td.total_seconds())
                hours, remainder = divmod(total_seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                milliseconds = td.microseconds // 1000
                return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

            with open(output_file, 'w', encoding='utf-8') as f:
                for sub in merged_subs:
                    f.write(f"{sub['index']}\n")
                    f.write(f"{format_timedelta(sub['start'])} --> {format_timedelta(sub['end'])}\n")
                    f.write(f"{sub['text']}\n\n")

            self.log_message(f"音频字幕合并成功: {output_file}")
            # 不在这里停止时间跟踪或重置按钮状态
            # 这些操作应该在 process_segments 方法的最后统一处理

        except Exception as e:
            self.log_message(f"音频字幕合并错误: {e}")
            # 不在这里停止时间跟踪或重置按钮状态
            # 这些操作应该在 process_segments 方法的最后统一处理

    def merge_files(self, input_dir, output_file):
        """合并文件 - 直接复用外部脚本的合并逻辑"""
        try:
            self.log_message("开始合并文件...")

            # 查找所有视频文件
            video_files = []
            for ext in ['*.mp4', '*.avi', '*.mov', '*.mkv']:
                video_files.extend(glob(os.path.join(input_dir, ext)))

            if not video_files:
                self.log_message("错误：在输入文件夹中未找到视频文件")
                return

            # 按文件名中的数字排序
            def extract_number(filename):
                match = re.search(r'(\d+)', os.path.basename(filename))
                return int(match.group(1)) if match else 0

            video_files.sort(key=extract_number)
            self.log_message(f"找到 {len(video_files)} 个视频文件")

            # 创建临时文件列表
            temp_dir = tempfile.mkdtemp()
            list_file = os.path.join(temp_dir, "filelist.txt")

            with open(list_file, 'w', encoding='utf-8') as f:
                for video_file in video_files:
                    f.write(f"file '{video_file}'\n")

            # 使用FFmpeg合并
            self.log_message("使用FFmpeg合并视频文件...")
            cmd = [
                'ffmpeg', '-f', 'concat', '-safe', '0', '-i', list_file,
                '-c', 'copy', output_file, '-y'
            ]

            process = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore',
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)

            if process.returncode == 0:
                self.log_message(f"视频合并完成: {output_file}")

                # 合并音频文件
                self.merge_audio_files(input_dir, output_file)

                # 合并字幕文件
                self.merge_subtitle_files(input_dir, output_file)

                # 不在这里停止时间跟踪或重置按钮状态
                # 这些操作应该在调用方法的最后统一处理

            else:
                self.log_message(f"FFmpeg合并失败: {process.stderr}")
                # 不在这里停止时间跟踪或重置按钮状态
                # 这些操作应该在调用方法的最后统一处理

            # 清理临时文件
            try:
                os.unlink(list_file)
                os.rmdir(temp_dir)
            except:
                pass

        except Exception as e:
            self.log_message(f"合并过程中发生错误: {e}")
            import traceback
            self.log_message(traceback.format_exc())
            # 不在这里停止时间跟踪或重置按钮状态
            # 这些操作应该在调用方法的最后统一处理



    def on_close(self):
        """关闭对话框"""
        if self.is_processing:
            if messagebox.askyesno("确认", "正在处理中，确定要取消吗？"):
                self.cancel_flag = True
                # 停止时间跟踪（取消）
                self.stop_time_tracking(success=False)
                # 等待一小段时间让处理线程检查取消标志
                self.dialog.after(1000, self._force_close)
            return

        # 停止时间跟踪（如果还在运行的话）
        if hasattr(self, 'time_update_running') and self.time_update_running:
            self.stop_time_tracking(success=False)

        # 清理临时文件
        script_adapter.cleanup_temp_files()

        self.dialog.destroy()

    def _force_close(self):
        """强制关闭对话框"""
        script_adapter.cleanup_temp_files()
        self.dialog.destroy()

    def show(self):
        """显示对话框"""
        # 设置默认输出路径
        if self.project_info and self.project_info.get('video_path'):
            default_output = os.path.join(
                os.path.dirname(self.project_info['video_path']),
                f"{self.project_info['project_name']}_export"
            )
            self.output_var.set(default_output)

        self.dialog.wait_window()
        return self.result

    def on_naming_mode_change(self, mode):
        """处理命名方式切换"""
        if mode == "index":
            self.naming_index_var.set(True)
            self.naming_subtitle_var.set(False)
            self.naming_mode.set("index")
        elif mode == "subtitle":
            self.naming_index_var.set(False)
            self.naming_subtitle_var.set(True)
            self.naming_mode.set("subtitle")

    def on_export_mode_change(self, mode):
        """导出模式互斥切换"""
        if mode == "fast":
            # self.fast_mode_var.set(True)  # 已隐藏标准模式
            self.reencode_mode_var.set(False)
            self.export_mode_var.set("fast")
            # 禁用重新编码参数
            if hasattr(self, 'res_combo'):
                self.res_combo.configure(state='disabled')
                self.fps_combo.configure(state='disabled')
            # 只有在日志组件存在时才输出
            if hasattr(self, 'log_text'):
                self.log_message("✓ 切换到快速模式（使用已切割片段）")
        else:
            # self.fast_mode_var.set(False)  # 已隐藏标准模式
            self.reencode_mode_var.set(True)
            self.export_mode_var.set("reencode")
            # 启用重新编码参数
            if hasattr(self, 'res_combo'):
                self.res_combo.configure(state='readonly')
                self.fps_combo.configure(state='readonly')
            # 只有在日志组件存在时才输出
            if hasattr(self, 'log_text'):
                self.log_message("  ✓ 切换到重新编码")
                # 启动视频参数分析
                self.analyze_video_parameters()

    def analyze_video_parameters(self):
        """分析原视频参数（异步执行）"""
        def analyze_thread():
            try:
                self.log_message("  正在分析视频参数...")

                # 收集所有原视频路径
                from database.manager import db_manager
                project_ids = set(seg.project_id for seg in self.segments)
                original_videos = []

                for pid in project_ids:
                    project = db_manager.get_project(pid)
                    if project and project.video_path and os.path.exists(project.video_path):
                        original_videos.append(project.video_path)

                if not original_videos:
                    self.log_message("  ⚠ 未找到原视频文件")
                    return

                self.log_message(f"  检测到 {len(original_videos)} 个原视频")

                # 分析每个视频的参数
                resolution_list = []
                fps_list = []

                for video_path in original_videos:
                    resolution, fps = self._probe_video_info(video_path)
                    if resolution:
                        width, height = resolution
                        resolution_str = f"{width}x{height}"
                        resolution_list.append((resolution_str, width * height))

                        self.log_message(f"  - {os.path.basename(video_path)}: {width}x{height}, {fps}fps")

                    if fps:
                        fps_list.append(fps)

                # 智能选择默认分辨率
                if resolution_list:
                    from collections import Counter

                    # 统计每种分辨率的出现次数
                    resolution_strings = [res[0] for res in resolution_list]
                    resolution_counter = Counter(resolution_strings)

                    # 创建分辨率到像素数的映射
                    resolution_pixels = {res[0]: res[1] for res in resolution_list}

                    # 按出现次数降序，次数相同时按像素数降序
                    most_common_resolution = sorted(
                        resolution_counter.items(),
                        key=lambda x: (x[1], resolution_pixels[x[0]]),
                        reverse=True
                    )[0][0]

                    # 获取最大分辨率（用于更新下拉框选项）
                    max_resolution = max(resolution_list, key=lambda x: x[1])[0]

                    # 设置默认分辨率
                    self.resolution_var.set(most_common_resolution)

                    # 显示分辨率统计信息
                    if len(resolution_counter) > 1:
                        res_stats = ", ".join([f"{res}({count}个)" for res, count in resolution_counter.most_common()])
                        self.log_message(f"  ✓ 检测到多种分辨率: {res_stats}")
                        self.log_message(f"  ✓ 默认分辨率: {most_common_resolution} （最常见且最大）")

                        # 如果默认分辨率不是最大分辨率，给出提示
                        if most_common_resolution != max_resolution:
                            self.log_message(f"  ⚠️ 提示: 部分{max_resolution}视频将被缩小到{most_common_resolution}")
                    else:
                        self.log_message(f"  ✓ 原始分辨率: {most_common_resolution}")

                    # 更新分辨率下拉框选项（使用最大分辨率作为上限）
                    self._update_resolution_options(max_resolution)
                else:
                    self.log_message("  ⚠ 无法检测分辨率")

                # 设置原始帧率（保持原视频帧率，不强制转换）
                if fps_list:
                    # 智能选择默认帧率：
                    # 1. 优先使用最常见的帧率（按出现次数）
                    # 2. 如果次数相同，使用最高帧率（保证流畅度）
                    from collections import Counter
                    fps_counter = Counter(fps_list)
                    # 按出现次数降序，次数相同时按帧率降序
                    most_common_fps = sorted(fps_counter.items(), key=lambda x: (x[1], x[0]), reverse=True)[0][0]

                    # 格式化帧率（保留2位小数，去除不必要的0）
                    fps_str = f"{most_common_fps:.2f}".rstrip('0').rstrip('.')
                    self.fps_var.set(fps_str)

                    # 更新帧率下拉框选项
                    self._update_fps_options(fps_list)

                    # 显示帧率统计信息
                    if len(fps_counter) > 1:
                        fps_stats = ", ".join([f"{fps:.2f}fps({count}个)" for fps, count in fps_counter.most_common()])
                        self.log_message(f"  ✓ 检测到多种帧率: {fps_stats}")
                        self.log_message(f"  ✓ 默认帧率: {fps_str}fps （最常见且最高）")
                    else:
                        self.log_message(f"  ✓ 原始帧率: {fps_str}fps")
                else:
                    self.log_message("  ⚠ 无法检测帧率")

                # 检测纯音频文件
                if not resolution_list and not fps_list:
                    self.log_message("  ⚠ 检测到纯音频文件")

            except Exception as e:
                self.log_message(f"  ✗ 分析失败: {e}")

        # 在后台线程中执行分析
        threading.Thread(target=analyze_thread, daemon=True).start()

    def _probe_video_info(self, video_path):
        """使用ffprobe获取视频信息"""
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,r_frame_rate",
                "-of", "json",
                video_path
            ]

            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=10
            )

            if result.returncode == 0:
                import json
                data = json.loads(result.stdout)

                if 'streams' in data and len(data['streams']) > 0:
                    stream = data['streams'][0]
                    width = stream.get('width')
                    height = stream.get('height')

                    # 解析帧率（格式可能是 "25/1" 或 "30000/1001"）
                    fps_str = stream.get('r_frame_rate', '0/1')
                    if '/' in fps_str:
                        num, den = map(int, fps_str.split('/'))
                        fps = round(num / den, 2) if den != 0 else 0
                    else:
                        fps = float(fps_str)

                    return (width, height), fps

            return None, None

        except Exception as e:
            print(f"探测视频信息失败 {video_path}: {e}")
            return None, None

    def _update_resolution_options(self, max_resolution):
        """更新分辨率下拉框选项（智能显示：原视频 + 标准 + 接近的分辨率）"""
        try:
            # 解析最大分辨率
            max_width, max_height = map(int, max_resolution.split('x'))
            max_pixels = max_width * max_height

            # 标准分辨率列表（从大到小）
            standard_resolutions = [
                ("3840x2160", 3840 * 2160),  # 4K
                ("2560x1440", 2560 * 1440),  # 2K
                ("1920x1080", 1920 * 1080),  # 1080p
                ("1280x720", 1280 * 720),    # 720p
                ("854x480", 854 * 480),      # 480p
                ("640x360", 640 * 360),      # 360p
            ]

            # 构建可选分辨率列表
            available_resolutions = []

            # 1. 如果原视频分辨率不是标准值，添加到开头
            if max_resolution not in [res for res, _ in standard_resolutions]:
                available_resolutions.append(max_resolution)

            # 2. 添加所有≤最大分辨率的标准选项
            for res, pixels in standard_resolutions:
                if pixels <= max_pixels:
                    available_resolutions.append(res)

            # 3. 添加"接近的"标准分辨率（像素数在±10%范围内）
            tolerance = 0.10  # 10%容差
            min_pixels = max_pixels * (1 - tolerance)
            max_pixels_upper = max_pixels * (1 + tolerance)

            for res, pixels in standard_resolutions:
                if res not in available_resolutions:
                    # 如果像素数在±10%范围内，认为是"接近的"
                    if min_pixels <= pixels <= max_pixels_upper:
                        available_resolutions.append(res)

            # 4. 始终添加常用的标准分辨率（供用户选择）
            common_resolutions = ["1920x1080", "1280x720", "854x480", "640x360"]
            for res in common_resolutions:
                if res not in available_resolutions:
                    # 只添加比原视频小的常用分辨率
                    res_pixels = int(res.split('x')[0]) * int(res.split('x')[1])
                    if res_pixels < max_pixels:
                        available_resolutions.append(res)

            # 去重并按像素数从大到小排序
            seen = set()
            unique_resolutions = []
            for res in available_resolutions:
                if res not in seen:
                    seen.add(res)
                    unique_resolutions.append(res)

            # 按像素数排序（从大到小）
            def get_pixels(res_str):
                w, h = map(int, res_str.split('x'))
                return w * h

            unique_resolutions.sort(key=get_pixels, reverse=True)

            # 更新下拉框
            if hasattr(self, 'res_combo'):
                self.res_combo['values'] = unique_resolutions
                self.log_message(f"  ✓ 可选分辨率: {', '.join(unique_resolutions)}")

        except Exception as e:
            print(f"更新分辨率选项失败: {e}")

    def _update_fps_options(self, fps_list):
        """更新帧率下拉框选项，包含检测到的原始帧率"""
        try:
            # 标准帧率列表
            standard_fps = ["23.98", "24", "25", "29.97", "30", "50", "59.94", "60"]

            # 添加检测到的帧率
            detected_fps_set = set()
            for fps in fps_list:
                # 格式化帧率（保留2位小数，去除不必要的0）
                fps_str = f"{fps:.2f}".rstrip('0').rstrip('.')
                detected_fps_set.add(fps_str)

            # 合并标准帧率和检测到的帧率
            all_fps = list(detected_fps_set)
            for fps in standard_fps:
                if fps not in all_fps:
                    all_fps.append(fps)

            # 按数值排序
            all_fps.sort(key=lambda x: float(x))

            # 更新下拉框
            if hasattr(self, 'fps_combo'):
                self.fps_combo['values'] = all_fps
                self.log_message(f"  ✓ 可选帧率: {', '.join(all_fps)}fps")

        except Exception as e:
            print(f"更新帧率选项失败: {e}")

    def cut_segment_with_reencode(self, video_path, start_time, end_time, output_path):
        """
        使用FFmpeg重新编码切割片段，统一视频参数

        Args:
            video_path: 原视频路径
            start_time: 开始时间（秒）
            end_time: 结束时间（秒）
            output_path: 输出文件路径

        Returns:
            bool: 成功返回True，失败返回False
        """
        try:
            duration = end_time - start_time

            # 获取目标参数
            target_resolution = self.resolution_var.get()  # 如 "1920x1080"
            target_fps = self.fps_var.get()  # 如 "25"
            target_width, target_height = map(int, target_resolution.split('x'))

            # 构建FFmpeg命令
            # 使用scale滤镜统一分辨率，保持宽高比，不足部分填充黑边
            # 使用fps滤镜统一帧率
            video_filters = (
                f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
                f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2,"
                f"fps={target_fps}"
            )

            cmd = [
                "ffmpeg",
                "-y",  # 覆盖输出文件
                "-ss", str(start_time),  # 开始时间
                "-i", video_path,  # 输入文件
                "-t", str(duration),  # 持续时间
                "-vf", video_filters,  # 视频滤镜
                "-c:v", "libx264",  # 视频编码器
                "-preset", self.preset_var.get(),  # 编码预设
                "-crf", self.crf_var.get(),  # 质量参数
                "-c:a", "aac",  # 音频编码器
                "-ar", "48000",  # 音频采样率 48kHz
                "-ac", "2",  # 音频声道数（立体声）
                "-b:a", "192k",  # 音频比特率
                output_path
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            if result.returncode == 0:
                return True
            else:
                if result.stderr:
                    self.log_message(f"  ✗ FFmpeg错误: {result.stderr[:200]}")
                return False

        except Exception as e:
            self.log_message(f"  ✗ 重新编码切割失败: {e}")
            return False

    # ========== 简单合并方法 - 复用 integrated_merge_dialog 逻辑 ==========

    def _simple_merge_with_unified_params(self, chunk_dir, base_dir, video_name, segments_data):
        """
        简单合并策略 - 适用于重新编码（参数已统一）
        生成两个字幕文件：视频字幕和音频字幕
        """
        try:
            self.log_message("=" * 60)
            self.log_message("开始简单合并策略（音频、音频字幕同名）")
            self.log_message("=" * 60)

            # 获取所有片段文件
            def extract_leading_number(filename):
                match = re.match(r"(\d+)", os.path.splitext(filename)[0])
                return int(match.group(1)) if match else 0

            all_video_files = [f for f in os.listdir(chunk_dir) if f.endswith('.mp4')]
            all_audio_files = [f for f in os.listdir(chunk_dir) if f.endswith('.mp3')]
            all_srt_files = [f for f in os.listdir(chunk_dir) if f.endswith('.srt')]

            self.log_message(f"找到 {len(all_video_files)} 个视频片段")
            self.log_message(f"找到 {len(all_audio_files)} 个音频片段")
            self.log_message(f"找到 {len(all_srt_files)} 个字幕片段")

            # 核心改进：按 project_id 分组排序
            self.log_message("\n步骤1: 按 project_id 分组片段...")
            from collections import defaultdict

            # 创建 project_id -> 片段索引列表 的映射
            project_segments = defaultdict(list)
            for i, segment_data in enumerate(segments_data, 1):
                project_id = segment_data.get('project_id')
                project_segments[project_id].append({
                    'index': i,  # 保持原始索引用于日志显示
                    'data': segment_data
                })

            # 按 project_id 正序排序
            sorted_project_ids = sorted(project_segments.keys())
            self.log_message(f"检测到 {len(sorted_project_ids)} 个项目: {sorted_project_ids}")

            # 构建按项目分组后的文件列表
            video_files = []
            audio_files = []
            srt_files = []

            # 关键修复：使用连续的文件序号来查找文件（而不是原始片段索引）
            file_index = 1
            for project_id in sorted_project_ids:
                segments = project_segments[project_id]
                self.log_message(f"\n项目 {project_id}: {len(segments)} 个片段")

                # 每个项目内按原始索引排序（保持原有顺序）
                segments.sort(key=lambda x: x['index'])

                for segment in segments:
                    original_index = segment['index']
                    # 使用连续的文件序号查找文件
                    filename_base = f"{file_index:02d}"

                    # 查找对应的文件
                    for video_file in all_video_files:
                        if video_file.startswith(filename_base):
                            video_files.append(video_file)
                            break

                    for audio_file in all_audio_files:
                        if audio_file.startswith(filename_base):
                            audio_files.append(audio_file)
                            break

                    for srt_file in all_srt_files:
                        if srt_file.startswith(filename_base):
                            srt_files.append(srt_file)
                            break

                    # 显示片段信息（使用原始索引便于追踪）
                    start_time = segment['data']['start_time']
                    end_time = segment['data']['end_time']
                    text = segment['data']['text'][:30]
                    self.log_message(f"  片段 {original_index} (文件#{file_index}): {start_time:.1f}-{end_time:.1f}s, '{text}...'")

                    file_index += 1  # 递增文件序号

            self.log_message(f"\n按项目分组后的文件列表:")
            self.log_message(f"  视频文件: {len(video_files)} 个")
            self.log_message(f"  音频文件: {len(audio_files)} 个")
            self.log_message(f"  字幕文件: {len(srt_files)} 个")

            # 2. 合并视频（使用 FFmpeg concat）
            if video_files:
                # 检查取消标志
                if self.cancel_flag or (hasattr(self, 'queue_processor') and
                                       self.queue_processor and
                                       self.queue_processor.cancel_requested):
                    self.log_message("用户取消操作（合并视频前）")
                    return

                self.log_message("\n步骤2: 按项目顺序合并视频文件...")
                self.update_progress(91, 100, "正在合并视频...")
                merged_video = os.path.join(base_dir, f"{video_name}.mp4")
                self._simple_merge_videos(chunk_dir, video_files, merged_video)
                self.update_progress(93, 100, "视频合并完成")

            # 3. 合并音频（使用 FFmpeg concat）- 音频文件名添加 _audio 后缀
            if audio_files:
                # 检查取消标志
                if self.cancel_flag or (hasattr(self, 'queue_processor') and
                                       self.queue_processor and
                                       self.queue_processor.cancel_requested):
                    self.log_message("用户取消操作（合并音频前）")
                    return

                self.log_message("\n步骤3: 按项目顺序合并音频文件...")
                self.update_progress(94, 100, "正在合并音频...")
                merged_audio = os.path.join(base_dir, f"{video_name}_audio.mp3")
                self._simple_merge_audios(chunk_dir, audio_files, merged_audio)
                self.update_progress(96, 100, "音频合并完成")

            # 4A. 合并字幕 - 基于视频时长（原有逻辑）
            if srt_files:
                # 检查取消标志
                if self.cancel_flag or (hasattr(self, 'queue_processor') and
                                       self.queue_processor and
                                       self.queue_processor.cancel_requested):
                    self.log_message("用户取消操作（合并视频字幕前）")
                    return

                self.log_message("\n步骤4A: 基于视频时长合并字幕...")
                self.update_progress(97, 100, "正在合并视频字幕...")
                merged_srt = os.path.join(base_dir, f"{video_name}.srt")
                self._simple_merge_subtitles_with_video_duration(chunk_dir, video_files, srt_files, merged_srt)

            # 4B. 合并字幕 - 基于音频时长（新增）
            if srt_files and audio_files:
                # 检查取消标志
                if self.cancel_flag or (hasattr(self, 'queue_processor') and
                                       self.queue_processor and
                                       self.queue_processor.cancel_requested):
                    self.log_message("用户取消操作（合并音频字幕前）")
                    return

                self.log_message("\n步骤4B: 基于音频时长合并字幕...")
                self.update_progress(98, 100, "正在合并音频字幕...")
                merged_srt_audio = os.path.join(base_dir, f"{video_name}_audio.srt")
                self._simple_merge_subtitles_with_audio_duration(chunk_dir, audio_files, srt_files, merged_srt_audio)

            #self.log_message("\n" + "=" * 60)
            self.log_message("简单合并策略完成！")
            #self.log_message("=" * 60)

            # 清理临时文件
            final_output = {
                "video_file": merged_video if video_files else None,
                "srt_file": merged_srt if srt_files else None,
                "srt_audio_file": merged_srt_audio if (srt_files and audio_files) else None
            }
            self._cleanup_simple_merge_files(chunk_dir, base_dir, final_output)

        except Exception as e:
            self.log_message(f"简单合并过程中发生错误: {e}")
            import traceback
            self.log_message(traceback.format_exc())

    def _simple_merge_videos(self, chunk_dir, video_files, output_file):
        """简单合并视频 - 使用 FFmpeg concat"""
        try:
            concat_file = os.path.join(chunk_dir, "simple_video_concat.txt")
            with open(concat_file, 'w', encoding='utf-8') as f:
                for video_file in video_files:
                    video_path = os.path.join(chunk_dir, video_file)
                    abs_path = os.path.abspath(video_path)
                    f.write(f"file '{abs_path}'\n")

            cmd = [
                'ffmpeg', '-f', 'concat', '-safe', '0', '-i', concat_file,
                '-c', 'copy',  # 直接复制，不重新编码
                output_file, '-y'
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore',
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)

            if result.returncode == 0:
                self.log_message(f"  ✓ 视频合并成功: {os.path.basename(output_file)}")
                os.remove(concat_file)
            else:
                self.log_message(f"  ✗ 视频合并失败: {result.stderr[:200]}")

        except Exception as e:
            self.log_message(f"  ✗ 视频合并异常: {e}")

    def _simple_merge_audios(self, chunk_dir, audio_files, output_file):
        """简单合并音频 - 使用 FFmpeg concat"""
        try:
            concat_file = os.path.join(chunk_dir, "simple_audio_concat.txt")
            with open(concat_file, 'w', encoding='utf-8') as f:
                for audio_file in audio_files:
                    audio_path = os.path.join(chunk_dir, audio_file)
                    abs_path = os.path.abspath(audio_path)
                    f.write(f"file '{abs_path}'\n")

            cmd = [
                'ffmpeg', '-f', 'concat', '-safe', '0', '-i', concat_file,
                '-c', 'copy',  # 直接复制
                output_file, '-y'
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore',
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)

            if result.returncode == 0:
                self.log_message(f"  ✓ 音频合并成功: {os.path.basename(output_file)}")
                os.remove(concat_file)
            else:
                self.log_message(f"  ✗ 音频合并失败: {result.stderr[:200]}")

        except Exception as e:
            self.log_message(f"  ✗ 音频合并异常: {e}")

    def _simple_merge_subtitles_with_video_duration(self, chunk_dir, video_files, srt_files, output_file):
        """
        简单合并字幕 - 基于视频时长
        使用 ffprobe 获取每个视频片段的真实时长，推进时间轴
        """
        try:
            from datetime import timedelta

            self.log_message("  使用 ffprobe 测量每个片段的真实时长...")

            merged_subs = []
            current_time = timedelta(seconds=0)
            gap = 0.2  # 标准 gap
            gap_td = timedelta(seconds=gap)

            for i, video_file in enumerate(video_files):
                # 获取对应的字幕文件
                srt_file_name = os.path.splitext(video_file)[0] + '.srt'
                srt_path = os.path.join(chunk_dir, srt_file_name)

                if not os.path.exists(srt_path):
                    self.log_message(f"  ⚠ 字幕文件不存在，跳过: {srt_file_name}")
                    continue

                # 读取字幕
                subs = pysrt.open(srt_path, encoding='utf-8-sig')

                for sub in subs:
                    sub_start = timedelta(
                        hours=sub.start.hours,
                        minutes=sub.start.minutes,
                        seconds=sub.start.seconds,
                        milliseconds=sub.start.milliseconds
                    )
                    sub_end = timedelta(
                        hours=sub.end.hours,
                        minutes=sub.end.minutes,
                        seconds=sub.end.seconds,
                        milliseconds=sub.end.milliseconds
                    )

                    new_start = current_time + sub_start
                    new_end = current_time + sub_end

                    # 智能 gap 处理（防止字幕重叠）
                    if merged_subs:
                        prev_end = merged_subs[-1]['end']
                        if new_start < prev_end + gap_td:
                            new_start = prev_end + gap_td
                            if new_end < new_start:
                                new_end = new_start + timedelta(milliseconds=500)

                    merged_subs.append({
                        'index': len(merged_subs) + 1,
                        'start': new_start,
                        'end': new_end,
                        'text': sub.text
                    })

                # 关键：使用 ffprobe 获取真实视频时长（复用 integrated_merge_dialog 逻辑）
                video_path = os.path.join(chunk_dir, video_file)
                duration = self._get_video_duration_ffprobe(video_path)
                current_time += timedelta(seconds=duration)

                self.log_message(f"  片段 {i+1}: 时长 {duration:.3f}s, 累计时间 {current_time.total_seconds():.3f}s")

            # 写入合并后的字幕
            with open(output_file, 'w', encoding='utf-8') as f:
                for sub in merged_subs:
                    f.write(f"{sub['index']}\n")
                    f.write(f"{self._format_timedelta(sub['start'])} --> {self._format_timedelta(sub['end'])}\n")
                    f.write(f"{sub['text']}\n\n")

            self.log_message(f"  ✓ 字幕合并成功: {os.path.basename(output_file)} ({len(merged_subs)} 条字幕)")
            self.log_message(f"  ✓ 最终时间轴长度: {current_time.total_seconds():.3f}s")

        except Exception as e:
            self.log_message(f"  ✗ 字幕合并异常: {e}")
            import traceback
            self.log_message(f"  详细错误: {traceback.format_exc()}")

    def _simple_merge_subtitles_with_audio_duration(self, chunk_dir, audio_files, srt_files, output_file):
        """
        简单合并字幕 - 基于音频时长
        使用 ffprobe 获取每个音频片段的真实时长，推进时间轴
        """
        try:
            from datetime import timedelta

            self.log_message("  使用 ffprobe 测量每个音频片段的真实时长...")

            merged_subs = []
            current_time = timedelta(seconds=0)
            gap = 0.2  # 标准 gap
            gap_td = timedelta(seconds=gap)

            for i, audio_file in enumerate(audio_files):
                # 获取对应的字幕文件
                srt_file_name = os.path.splitext(audio_file)[0] + '.srt'
                srt_path = os.path.join(chunk_dir, srt_file_name)

                if not os.path.exists(srt_path):
                    self.log_message(f"  ⚠ 字幕文件不存在，跳过: {srt_file_name}")
                    continue

                # 读取字幕
                subs = pysrt.open(srt_path, encoding='utf-8-sig')

                for sub in subs:
                    sub_start = timedelta(
                        hours=sub.start.hours,
                        minutes=sub.start.minutes,
                        seconds=sub.start.seconds,
                        milliseconds=sub.start.milliseconds
                    )
                    sub_end = timedelta(
                        hours=sub.end.hours,
                        minutes=sub.end.minutes,
                        seconds=sub.end.seconds,
                        milliseconds=sub.end.milliseconds
                    )

                    new_start = current_time + sub_start
                    new_end = current_time + sub_end

                    # 智能 gap 处理（防止字幕重叠）
                    if merged_subs:
                        prev_end = merged_subs[-1]['end']
                        if new_start < prev_end + gap_td:
                            new_start = prev_end + gap_td
                            if new_end < new_start:
                                new_end = new_start + timedelta(milliseconds=500)

                    merged_subs.append({
                        'index': len(merged_subs) + 1,
                        'start': new_start,
                        'end': new_end,
                        'text': sub.text
                    })

                # 关键：使用 ffprobe 获取真实音频时长
                audio_path = os.path.join(chunk_dir, audio_file)
                duration = self._get_audio_duration_ffprobe(audio_path)
                current_time += timedelta(seconds=duration)

                self.log_message(f"  片段 {i+1}: 音频时长 {duration:.3f}s, 累计时间 {current_time.total_seconds():.3f}s")

            # 写入合并后的字幕
            with open(output_file, 'w', encoding='utf-8') as f:
                for sub in merged_subs:
                    f.write(f"{sub['index']}\n")
                    f.write(f"{self._format_timedelta(sub['start'])} --> {self._format_timedelta(sub['end'])}\n")
                    f.write(f"{sub['text']}\n\n")

            self.log_message(f"  ✓ 音频字幕合并成功: {os.path.basename(output_file)} ({len(merged_subs)} 条字幕)")
            self.log_message(f"  ✓ 最终时间轴长度: {current_time.total_seconds():.3f}s")

        except Exception as e:
            self.log_message(f"  ✗ 音频字幕合并异常: {e}")
            import traceback
            self.log_message(f"  详细错误: {traceback.format_exc()}")

    def _get_video_duration_ffprobe(self, video_path):
        """使用 ffprobe 获取视频时长 - 复用 integrated_merge_dialog 的方法"""
        try:
            cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                   '-of', 'default=nw=1:nk=1', video_path]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            if result.returncode == 0:
                return float(result.stdout.strip())
            else:
                return 1.0  # 默认时长
        except:
            return 1.0  # 默认时长

    def _get_audio_duration_ffprobe(self, audio_path):
        """使用 ffprobe 获取音频时长"""
        try:
            cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                   '-of', 'default=nw=1:nk=1', audio_path]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            if result.returncode == 0:
                return float(result.stdout.strip())
            else:
                return 1.0  # 默认时长
        except:
            return 1.0  # 默认时长


    def _cleanup_simple_merge_files(self, chunk_dir, base_dir, final_output):
        """清理简单合并的临时文件，保留最终输出文件"""
        try:
            # 获取需要保留的文件
            final_video = final_output.get('video_file')
            final_srt = final_output.get('srt_file')
            final_srt_audio = final_output.get('srt_audio_file')  # 新增的音频字幕文件

            files_to_cleanup = []

            # 只清理 base_dir 中的临时文件
            if os.path.exists(base_dir):
                for file in os.listdir(base_dir):
                    file_path = os.path.join(base_dir, file)
                    if os.path.isfile(file_path):
                        # 保留最终输出文件
                        if file_path in [final_video, final_srt, final_srt_audio]:
                            continue

                        # 删除 concat 列表文件
                        if file.endswith('.txt') and ('concat' in file or 'list' in file):
                            files_to_cleanup.append(file_path)
                        # 删除 JSON 文件
                        elif file.endswith('.json'):
                            files_to_cleanup.append(file_path)

            # 执行清理
            for file_path in files_to_cleanup:
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except:
                    pass

            # 保留切割的片段文件
            if os.path.exists(chunk_dir):
                chunk_files = [f for f in os.listdir(chunk_dir) if f.endswith(('.mp4', '.mp3', '.srt'))]
                if chunk_files:
                    self.log_message(f"保留 {len(chunk_files)} 个切割片段文件在: {os.path.basename(chunk_dir)}")

        except Exception as e:
            self.log_message(f"清理临时文件异常: {e}")

    # ========== 队列功能 ==========

    def add_to_queue(self):
        """添加任务到队列"""
        try:
            # 验证输出路径
            output_path = self.output_var.get().strip()
            if not output_path:
                messagebox.showerror("错误", "请选择输出文件夹", parent=self.dialog)
                return

            # 创建输出目录
            try:
                os.makedirs(output_path, exist_ok=True)
            except Exception as e:
                messagebox.showerror("错误", f"无法创建输出目录: {e}", parent=self.dialog)
                return

            # 检查队列管理器是否可用
            if not hasattr(self.parent, 'export_queue') or self.parent.export_queue is None:
                messagebox.showerror("错误", "队列管理器未初始化\n\n请确保主窗口已正确加载队列管理器模块", parent=self.dialog)
                return

            # 获取队列管理器
            queue = self.parent.export_queue
            processor = self.parent.queue_processor

            self.log_message(f"[队列] 使用原版队列管理器")

            # 检查跨项目导出 + 标准模式的冲突
            if self._detect_cross_project() and self.export_mode_var.get() == "fast":
                self.log_message("[队列] 检测到跨项目导出 + 标准模式，显示警告")
                self._show_cross_project_warning()
                return

            # 🚨 新增：音频视频混合导出检测
            if self._detect_mixed_audio_video():
                self._show_mixed_audio_video_warning()
                return  # 停止添加到队列

            # 准备导出配置 - 使用原版队列管理器的数据类
            from core.export_queue import ExportConfig, ExportTask, SegmentInfo

            config = ExportConfig(
                output_dir=output_path,
                naming_mode="sequence" if self.naming_mode.get() == "index" else "sequence_subtitle",
                encoding_preset=self.preset_var.get(),
                crf=int(self.crf_var.get()),
                target_resolution=self.resolution_var.get() if self.export_mode_var.get() == "reencode" else None,
                target_fps=float(self.fps_var.get()) if self.export_mode_var.get() == "reencode" else None,
                fast_copy_mode=(self.export_mode_var.get() == "fast"),
                continuous_cut_mode=self.continuous_cut_var.get(),  # 连续切割模式配置
                smart_validation=self.smart_validation_var.get() if hasattr(self, 'smart_validation_var') else True,
                auto_fix_deviation=self.auto_correct_var.get() if hasattr(self, 'auto_correct_var') else True
            )

            # 准备片段信息
            segments = []
            for seg in self.segments:
                segment_info = SegmentInfo(
                    segment_id=seg.id,
                    start_time=seg.start_time,
                    end_time=seg.end_time,
                    subtitle_text=seg.text,
                    duration=seg.end_time - seg.start_time,
                    project_id=seg.project_id  # 传递 project_id（跨项目导出必需）
                )
                segments.append(segment_info)

            # 检测是否跨项目导出
            unique_project_ids = set(seg.project_id for seg in segments if seg.project_id is not None)
            is_cross_project = len(unique_project_ids) > 1

            # 准备项目名称和相关信息
            if is_cross_project:
                # 跨项目导出：收集所有项目名称
                from database.manager import db_manager
                project_names = []
                for pid in sorted(unique_project_ids):
                    project = db_manager.get_project(pid)
                    if project:
                        project_names.append(project.name)

                # 拼接项目名称 [项目1][项目2]
                display_project_name = "".join(f"[{name}]" for name in project_names)
                task_video_path = "[跨项目]"
                export_mode_text = "跨项目导出"
            else:
                # 单项目导出
                display_project_name = self.project_info['project_name']
                task_video_path = self.project_info['video_path']
                export_mode_text = "单项目导出"

            # 创建任务
            task = ExportTask(
                project_name=display_project_name,
                video_path=task_video_path,
                segments=segments,
                config=config,
                total_segments=len(segments),
                is_cross_project=is_cross_project
            )

            # 添加到队列
            task_id = queue.add_task(task)

            # 如果勾选了"保存为默认配置"，保存当前配置
            if hasattr(self, 'save_as_default_var') and self.save_as_default_var.get():
                self._save_current_config_as_default()

            # 日志输出
            self.log_message(f"任务已添加到队列 (ID: {task_id[:8]}...)")
            self.log_message(f"  导出模式: {export_mode_text}")
            if is_cross_project:
                self.log_message(f"  涉及项目: {', '.join(project_names)} (共{len(unique_project_ids)}个)")
                # 统计每个项目的片段数
                from collections import Counter
                project_segment_count = Counter(seg.project_id for seg in segments)
                for pid in sorted(unique_project_ids):
                    project = db_manager.get_project(pid)
                    if project:
                        self.log_message(f"    {project.name}: {project_segment_count[pid]}个片段")
            else:
                self.log_message(f"  项目: {task.project_name}")
            self.log_message(f"  片段总数: {len(segments)}")
            self.log_message(f"  当前队列: {len(queue.tasks)}个任务")

            # 提示用户
            if is_cross_project:
                message_text = (
                    f"任务已添加到队列！\n\n"
                    f"导出模式: {export_mode_text}\n"
                    f"涉及项目: {', '.join(project_names)}\n"
                    f"片段总数: {len(segments)}\n"
                    f"当前队列: {len(queue.tasks)}个任务\n\n"
                    f"是否打开队列管理器？"
                )
            else:
                message_text = (
                    f"任务已添加到队列！\n\n"
                    f"项目: {task.project_name}\n"
                    f"片段数: {len(segments)}\n"
                    f"当前队列: {len(queue.tasks)}个任务\n\n"
                    f"是否打开队列管理器？"
                )

            result = messagebox.askquestion(
                "添加成功",
                message_text,
                icon='question',
                parent=self.dialog
            )

            if result == 'yes':
                self.open_queue_manager()

        except Exception as e:
            self.log_message(f"添加到队列失败: {e}")
            import traceback
            self.log_message(f"详细错误: {traceback.format_exc()}")
            messagebox.showerror("错误", f"添加到队列失败: {e}", parent=self.dialog)

    def _save_current_config_as_default(self):
        """保存当前配置为默认配置"""
        try:
            from core.export_config_manager import save_export_config, ExportConfigManager
            from utils import custom_messagebox

            config = {
                "output_dir": self.output_var.get().strip(),
                "naming_mode": self.naming_mode.get(),
                "fast_copy_mode": (self.export_mode_var.get() == "fast"),
                "continuous_cut_mode": self.continuous_cut_var.get(),
                "encoding_preset": self.preset_var.get(),
                "crf": self.crf_var.get(),
                "target_resolution": self.resolution_var.get(),
                "target_fps": self.fps_var.get(),
                "smart_validation": self.smart_validation_var.get() if hasattr(self, 'smart_validation_var') else True,
                "auto_fix_deviation": self.auto_correct_var.get() if hasattr(self, 'auto_correct_var') else True
            }

            if save_export_config(config):
                self.log_message("[配置] 已保存为默认配置")
                print(f"[配置管理器] 已保存默认配置: {config}")

                # 获取配置文件路径并弹窗提示
                config_file = ExportConfigManager._get_config_file()
                custom_messagebox.showinfo(
                    "保存成功",
                    f"默认配置已保存成功！\n\n配置文件位置：\n{config_file}\n\n下次使用'快速添加'功能时将自动使用此配置。",
                    parent=self.dialog
                )
            else:
                self.log_message("[配置] 保存默认配置失败")

        except Exception as e:
            self.log_message(f"[配置] 保存默认配置失败: {e}")
            print(f"[配置管理器] 保存配置失败: {e}")

    def open_queue_manager(self):
        """打开队列管理器窗口（通过主窗口统一管理，防止多开）"""
        try:
            # 检查队列管理器是否可用
            if not hasattr(self.parent, 'export_queue') or self.parent.export_queue is None:
                messagebox.showerror("错误", "队列管理器未初始化\n\n请确保主窗口已正确加载队列管理器模块", parent=self.dialog)
                return

            # 直接调用主窗口的 show_queue_manager 方法
            # 这样可以利用主窗口的单例管理，防止重复打开
            if hasattr(self.parent, 'show_queue_manager'):
                self.parent.show_queue_manager()
                self.log_message("[队列] 已通过主窗口打开队列管理器")
            else:
                messagebox.showerror("错误", "无法访问主窗口的队列管理器方法", parent=self.dialog)

        except Exception as e:
            self.log_message(f"打开队列管理器失败: {e}")
            import traceback
            self.log_message(f"详细错误: {traceback.format_exc()}")
            messagebox.showerror("错误", f"打开队列管理器失败: {e}", parent=self.dialog)
