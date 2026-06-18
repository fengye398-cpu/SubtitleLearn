"""
视频转音频对话框
使用FFmpeg将视频文件转换为音频文件
支持单个文件和批量转换
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import subprocess
import threading
import re
from pathlib import Path

# 尝试导入拖拽支持库
try:
    from tkinterdnd2 import DND_FILES
    DRAG_DROP_AVAILABLE = True
except ImportError:
    DRAG_DROP_AVAILABLE = False
    print("[WARN] tkinterdnd2 not available, drag-drop disabled")

# 导入自定义消息框
try:
    from utils import custom_messagebox
    CUSTOM_MESSAGEBOX_AVAILABLE = True
except ImportError:
    CUSTOM_MESSAGEBOX_AVAILABLE = False
    print("[WARN] custom_messagebox not available, using standard messagebox")

# 导入图标管理器
try:
    from icon_manager import set_window_icon
    ICON_AVAILABLE = True
except ImportError:
    ICON_AVAILABLE = False
    def set_window_icon(window):
        pass


# 音频格式配置（使用VBR方式）
AUDIO_FORMATS = {
    'MP3': {
        'encoder': 'libmp3lame',
        'extension': '.mp3',
        'qualities': {
            '最高质量': '-q:a 0',           # ~245 kbps
            '高质量 (推荐)': '-q:a 2',      # ~190 kbps (默认)
            '标准质量': '-q:a 4',            # ~165 kbps
            '较低质量': '-q:a 6',            # ~130 kbps
        },
        'default_quality': '高质量 (推荐)'
    },
    'AAC': {
        'encoder': 'aac',
        'extension': '.m4a',
        'qualities': {
            '高质量': '-b:a 256k',
            '标准质量 (推荐)': '-b:a 192k',
            '较低质量': '-b:a 128k',
        },
        'default_quality': '标准质量 (推荐)'
    },
    'WAV': {
        'encoder': 'pcm_s16le',
        'extension': '.wav',
        'lossless': True,
        'qualities': {'无损': ''},
        'default_quality': '无损'
    },
    'FLAC': {
        'encoder': 'flac',
        'extension': '.flac',
        'lossless': True,
        'qualities': {'无损': ''},
        'default_quality': '无损'
    },
    'M4A': {
        'encoder': 'aac',
        'extension': '.m4a',
        'qualities': {
            '高质量': '-b:a 256k',
            '标准质量 (推荐)': '-b:a 192k',
            '较低质量': '-b:a 128k',
        },
        'default_quality': '标准质量 (推荐)'
    }
}

# 支持的视频格式
VIDEO_EXTENSIONS = [
    '.mp4', '.avi', '.mkv', '.mov', '.flv',
    '.wmv', '.webm', '.m4v', '.mpg', '.mpeg',
    '.3gp', '.ts', '.vob'
]


class VideoToAudioDialog:
    """视频转音频对话框"""

    def __init__(self, parent):
        self.parent = parent

        # 创建非模态对话框
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("提取音频")
        self.dialog.geometry("700x700")
        self.dialog.resizable(True, True)
        # 不使用模态窗口设置，允许窗口自由最小化和切换
        # self.dialog.transient(parent)  # 会隐藏最小化按钮
        # self.dialog.grab_set()  # 会阻止窗口最小化

        # 设置窗口图标
        if ICON_AVAILABLE:
            set_window_icon(self.dialog)

        # 变量
        self.mode_var = tk.BooleanVar(value=False)  # False=单文件, True=批量
        self.video_file_var = tk.StringVar()
        self.batch_dir_var = tk.StringVar()
        self.output_dir_var = tk.StringVar()
        self.format_var = tk.StringVar(value='MP3')
        self.quality_var = tk.StringVar(value='高质量 (推荐)')

        # 监控输入路径变化，自动更新输出路径
        self.video_file_var.trace_add("write", self.auto_set_output_dir)
        self.batch_dir_var.trace_add("write", self.auto_set_batch_output_dir)

        # 标记用户是否手动选择了输出目录
        self.user_selected_output = False

        # 批量文件列表
        self.batch_files = []  # [(file_path, size, var), ...]
        self.file_check_vars = []

        # 处理状态
        self.is_processing = False
        self.cancel_requested = False
        self.process = None

        # 创建UI
        self.setup_ui()

        # 设置占位符提示
        self.setup_placeholder_hints()

        # 检查FFmpeg
        self.check_ffmpeg()

        # 居中显示
        self.center_dialog()

    def setup_ui(self):
        """设置用户界面"""
        # 主框架
        main_frame = ttk.Frame(self.dialog, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 转换模式选择（放在最前面）
        self.create_mode_frame(main_frame)

        # 输出设置区域
        self.create_output_settings_frame(main_frame)

        # 单个文件选择区域
        self.create_single_file_frame(main_frame)

        # 批量转换区域
        self.create_batch_frame(main_frame)

        # 按钮区域
        self.create_button_frame(main_frame)

        # 进度条区域
        self.create_progress_frame(main_frame)

        # 状态栏
        self.create_status_bar(main_frame)

        # 初始化界面状态
        self.on_mode_changed()

    def create_mode_frame(self, parent):
        """创建转换模式选择区域"""
        frame = ttk.LabelFrame(parent, text="转换模式", padding="10")
        frame.pack(fill=tk.X, pady=(0, 10))

        mode_frame = ttk.Frame(frame)
        mode_frame.pack(fill=tk.X)

        self.single_radio = ttk.Radiobutton(
            mode_frame,
            text="单个文件",
            variable=self.mode_var,
            value=False,
            command=self.on_mode_changed
        )
        self.single_radio.pack(side=tk.LEFT, padx=(0, 20))

        self.batch_radio = ttk.Radiobutton(
            mode_frame,
            text="批量转换",
            variable=self.mode_var,
            value=True,
            command=self.on_mode_changed
        )
        self.batch_radio.pack(side=tk.LEFT)

    def create_single_file_frame(self, parent):
        """创建单个文件选择区域"""
        self.single_file_frame = ttk.LabelFrame(parent, text="单个文件选择", padding="10")
        self.single_file_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(self.single_file_frame, text="视频文件:").pack(anchor=tk.W)

        input_frame = ttk.Frame(self.single_file_frame)
        input_frame.pack(fill=tk.X, pady=(5, 0))

        self.video_entry = ttk.Entry(input_frame, textvariable=self.video_file_var)
        self.video_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        ttk.Button(input_frame, text="浏览...", command=self.browse_video_file).pack(side=tk.LEFT)

        # 拖拽支持
        if DRAG_DROP_AVAILABLE:
            self.video_entry.drop_target_register(DND_FILES)
            self.video_entry.dnd_bind('<<Drop>>', self.on_video_drop)

    def create_batch_frame(self, parent):
        """创建批量转换区域"""
        self.batch_frame = ttk.LabelFrame(parent, text="批量转换", padding="10")
        self.batch_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # 文件/目录输入
        dir_frame = ttk.Frame(self.batch_frame)
        dir_frame.pack(fill=tk.X, pady=(0, 10))

        self.batch_input_entry = ttk.Entry(dir_frame, textvariable=self.batch_dir_var)
        self.batch_input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(dir_frame, text="浏览...", command=self.browse_batch_files).pack(side=tk.LEFT)

        # 拖拽支持（支持文件和文件夹）
        if DRAG_DROP_AVAILABLE:
            self.batch_input_entry.drop_target_register(DND_FILES)
            self.batch_input_entry.dnd_bind('<<Drop>>', self.on_batch_drop)

        # 创建滚动区域
        list_container = ttk.Frame(self.batch_frame)
        list_container.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        canvas = tk.Canvas(list_container, height=150)
        scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=canvas.yview)
        self.files_list_frame = ttk.Frame(canvas)

        self.files_list_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.files_list_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.canvas = canvas

        # 批量操作按钮
        batch_btn_frame = ttk.Frame(self.batch_frame)
        batch_btn_frame.pack(fill=tk.X)

        ttk.Button(batch_btn_frame, text="全选", command=self.select_all_files).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(batch_btn_frame, text="取消全选", command=self.deselect_all_files).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(batch_btn_frame, text="清空列表", command=self.clear_file_list).pack(side=tk.LEFT)

    def create_output_settings_frame(self, parent):
        """创建输出设置区域"""
        frame = ttk.LabelFrame(parent, text="输出设置", padding="10")
        frame.pack(fill=tk.X, pady=(0, 10))

        # 输出目录
        ttk.Label(frame, text="输出目录:").pack(anchor=tk.W)

        output_frame = ttk.Frame(frame)
        output_frame.pack(fill=tk.X, pady=(5, 10))

        ttk.Entry(output_frame, textvariable=self.output_dir_var, state='readonly').pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5)
        )
        ttk.Button(output_frame, text="选择目录", command=self.select_output_dir).pack(side=tk.LEFT)

        # 音频格式和质量（同一行）
        format_quality_frame = ttk.Frame(frame)
        format_quality_frame.pack(fill=tk.X)

        # 音频格式
        ttk.Label(format_quality_frame, text="音频格式:").pack(side=tk.LEFT, padx=(0, 5))
        self.format_combo = ttk.Combobox(
            format_quality_frame,
            textvariable=self.format_var,
            values=list(AUDIO_FORMATS.keys()),
            state="readonly",
            width=12
        )
        self.format_combo.pack(side=tk.LEFT, padx=(0, 20))
        self.format_combo.bind('<<ComboboxSelected>>', self.on_format_changed)

        # 音频质量
        ttk.Label(format_quality_frame, text="音频质量:").pack(side=tk.LEFT, padx=(0, 5))
        self.quality_combo = ttk.Combobox(
            format_quality_frame,
            textvariable=self.quality_var,
            state="readonly",
            width=15
        )
        self.quality_combo.pack(side=tk.LEFT)

        # 初始化质量选项
        self.on_format_changed()

    def create_button_frame(self, parent):
        """创建按钮区域"""
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=10)

        self.start_btn = ttk.Button(frame, text="开始转换", command=self.start_conversion)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 5))

        ttk.Button(frame, text="输出目录", command=self.open_output_folder).pack(side=tk.LEFT, padx=(0, 5))

        self.cancel_btn = ttk.Button(frame, text="取消", command=self.cancel_conversion, state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT, padx=(0, 5))

        ttk.Button(frame, text="关闭", command=self.dialog.destroy).pack(side=tk.LEFT)

    def create_progress_frame(self, parent):
        """创建进度条区域"""
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=5)

        # 批量模式进度显示区域
        self.total_progress_frame = ttk.Frame(frame)

        # 当前文件进度（纯文本显示）
        current_file_frame = ttk.Frame(self.total_progress_frame)
        current_file_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(current_file_frame, text="当前文件:").pack(side=tk.LEFT, padx=(0, 5))
        self.current_file_label = ttk.Label(current_file_frame, text="", foreground="blue")
        self.current_file_label.pack(side=tk.LEFT)

        current_progress_frame = ttk.Frame(self.total_progress_frame)
        current_progress_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(current_progress_frame, text="当前进度:").pack(side=tk.LEFT, padx=(0, 5))
        self.current_progress_label = ttk.Label(current_progress_frame, text="0%", foreground="green", font=("", 10, "bold"))
        self.current_progress_label.pack(side=tk.LEFT)

        # 总体进度（进度条 + 百分比 + 文件计数）
        total_frame = ttk.Frame(self.total_progress_frame)
        total_frame.pack(fill=tk.X)

        ttk.Label(total_frame, text="总体进度:").pack(side=tk.LEFT, padx=(0, 5))

        self.total_progress_var = tk.DoubleVar()
        self.total_progress_bar = ttk.Progressbar(
            total_frame,
            variable=self.total_progress_var,
            maximum=100
        )
        self.total_progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        self.total_progress_label = ttk.Label(total_frame, text="0% (0/0)", width=15)
        self.total_progress_label.pack(side=tk.LEFT)

        # 单个文件进度（单文件模式显示）
        self.single_progress_frame = ttk.Frame(frame)

        ttk.Label(self.single_progress_frame, text="总体进度:").pack(side=tk.LEFT, padx=(0, 5))

        self.single_progress_var = tk.DoubleVar()
        self.single_progress_bar = ttk.Progressbar(
            self.single_progress_frame,
            variable=self.single_progress_var,
            maximum=100
        )
        self.single_progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        self.single_progress_label = ttk.Label(self.single_progress_frame, text="0%", width=15)
        self.single_progress_label.pack(side=tk.LEFT)

    def create_status_bar(self, parent):
        """创建状态栏"""
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X)

        self.status_var = tk.StringVar(value="就绪")
        self.status_label = ttk.Label(frame, textvariable=self.status_var, foreground="gray")
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def on_mode_changed(self):
        """转换模式改变"""
        is_batch = self.mode_var.get()

        # 切换模式时重置手动选择标记，允许自动更新输出路径
        self.user_selected_output = False

        if is_batch:
            # 批量模式
            self.single_file_frame.pack_forget()
            self.single_progress_frame.pack_forget()
            self.batch_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
            self.total_progress_frame.pack(fill=tk.X)
        else:
            # 单文件模式
            self.batch_frame.pack_forget()
            self.total_progress_frame.pack_forget()
            self.single_file_frame.pack(fill=tk.X, pady=(0, 10))
            self.single_progress_frame.pack(fill=tk.X)

    def on_format_changed(self, event=None):
        """音频格式改变"""
        format_name = self.format_var.get()
        format_config = AUDIO_FORMATS.get(format_name, {})

        # 更新质量选项
        qualities = list(format_config.get('qualities', {}).keys())
        self.quality_combo['values'] = qualities

        # 设置默认质量
        default_quality = format_config.get('default_quality', qualities[0] if qualities else '')
        self.quality_var.set(default_quality)

        # 如果是无损格式，禁用质量选择
        if format_config.get('lossless', False):
            self.quality_combo.config(state='disabled')
        else:
            self.quality_combo.config(state='readonly')

    def browse_video_file(self):
        """浏览选择视频文件"""
        filetypes = [
            ("视频文件", " ".join(f"*{ext}" for ext in VIDEO_EXTENSIONS)),
            ("所有文件", "*.*")
        ]
        file_path = filedialog.askopenfilename(parent=self.dialog, title="选择视频文件", filetypes=filetypes)

        if file_path:
            # 清除占位符
            if self.video_entry.get() == "拖拽视频文件到此处或点击浏览..":
                self.video_entry.delete(0, tk.END)
                self.video_entry.config(foreground='black')
            self.video_file_var.set(file_path)
            self.update_status(f"[成功] 已选择视频: {os.path.basename(file_path)}")

    def on_video_drop(self, event):
        """处理视频文件拖拽"""
        try:
            file_path = self.parse_drop_file(event.data)
            if file_path:
                ext = os.path.splitext(file_path)[1].lower()
                if ext in VIDEO_EXTENSIONS:
                    # 清除占位符
                    if self.video_entry.get() == "拖拽视频文件到此处或点击浏览..":
                        self.video_entry.delete(0, tk.END)
                        self.video_entry.config(foreground='black')
                    self.video_file_var.set(file_path)
                    self.update_status(f"[成功] 已拖入视频: {os.path.basename(file_path)}")
                else:
                    self._show_warning("警告", "[警告] 请拖入视频文件")
        except Exception as e:
            print(f"[视频转音频] 拖拽处理失败: {e}")

    def parse_drop_file(self, data):
        """解析拖拽的文件数据"""
        file_path = data.strip().strip('{}').strip('"').strip("'")
        if os.path.exists(file_path):
            return file_path
        return None

    def browse_batch_files(self):
        """浏览选择视频文件（支持多选）"""
        filetypes = [
            ("视频文件", " ".join(f"*{ext}" for ext in VIDEO_EXTENSIONS)),
            ("所有文件", "*.*")
        ]
        file_paths = filedialog.askopenfilenames(parent=self.dialog, title="选择视频文件（可多选）", filetypes=filetypes)

        if file_paths:
            # 直接添加到文件列表
            self.add_files_to_list(list(file_paths))
            self.update_status(f"[成功] 已添加 {len(file_paths)} 个视频文件")

    def on_batch_drop(self, event):
        """处理批量拖拽（支持文件和文件夹）"""
        try:
            # 清除占位符
            if self.batch_input_entry.get() == "拖拽视频文件或文件夹到此处":
                self.batch_input_entry.delete(0, tk.END)
                self.batch_input_entry.config(foreground='black')

            # 解析拖拽数据（可能包含多个文件/文件夹）
            data = event.data.strip().strip('{}')
            paths = data.split('} {') if '} {' in data else [data]

            video_files = []
            for path in paths:
                path = path.strip().strip('{}').strip('"').strip("'")
                if not os.path.exists(path):
                    continue

                if os.path.isfile(path):
                    # 文件：检查是否是视频
                    ext = os.path.splitext(path)[1].lower()
                    if ext in VIDEO_EXTENSIONS:
                        video_files.append(path)
                elif os.path.isdir(path):
                    # 文件夹：扫描所有视频
                    for file in os.listdir(path):
                        file_path = os.path.join(path, file)
                        if os.path.isfile(file_path):
                            ext = os.path.splitext(file)[1].lower()
                            if ext in VIDEO_EXTENSIONS:
                                video_files.append(file_path)

            if video_files:
                self.add_files_to_list(video_files)
                self.update_status(f"[成功] 已添加 {len(video_files)} 个视频文件")
            else:
                self._show_info("提示", "[提示] 未找到视频文件")

        except Exception as e:
            print(f"[视频转音频] 拖拽处理失败: {e}")
            import traceback
            traceback.print_exc()

    def add_files_to_list(self, file_paths):
        """添加文件到列表（去重）"""
        # 获取已存在的文件路径
        existing_paths = set(path for path, _, _ in self.batch_files)

        # 添加新文件
        added_count = 0
        for file_path in file_paths:
            if file_path not in existing_paths:
                size = os.path.getsize(file_path)
                var = tk.BooleanVar(value=True)
                self.file_check_vars.append(var)
                self.batch_files.append((file_path, size, var))
                added_count += 1

        if added_count > 0:
            # 刷新显示
            self.refresh_file_list_display()

            # 自动设置输出目录
            if not self.output_dir_var.get() and self.batch_files:
                first_file = self.batch_files[0][0]
                output_dir = os.path.dirname(first_file)
                self.output_dir_var.set(output_dir)

    def scan_directory(self):
        """扫描目录中的视频文件"""
        # 检查是否是占位符
        current_text = self.batch_input_entry.get()
        if current_text == "拖拽视频文件或文件夹到此处":
            self._show_warning("警告", "[警告] 请先输入或选择目录")
            return

        directory = self.batch_dir_var.get().strip()

        if not directory:
            self._show_warning("警告", "[警告] 请先选择目录")
            return

        if not os.path.exists(directory):
            self._show_error("错误", f"[错误] 目录不存在:\n{directory}")
            return

        self.update_status("[提示] 正在扫描目录...")

        try:
            # 清空现有列表
            for widget in self.files_list_frame.winfo_children():
                widget.destroy()

            self.batch_files = []
            self.file_check_vars = []

            # 扫描视频文件
            video_files = []
            for file in os.listdir(directory):
                file_path = os.path.join(directory, file)
                if os.path.isfile(file_path):
                    ext = os.path.splitext(file)[1].lower()
                    if ext in VIDEO_EXTENSIONS:
                        size = os.path.getsize(file_path)
                        video_files.append((file_path, size))

            if not video_files:
                self._show_info("提示", "[提示] 该目录中没有找到视频文件")
                self.update_status("[提示] 未找到视频文件")
                self.files_hint_label = ttk.Label(
                    self.files_list_frame,
                    text="[提示] 该目录中没有视频文件",
                    foreground="gray"
                )
                self.files_hint_label.pack(pady=20)
                return

            # 显示文件列表
            for file_path, size in video_files:
                var = tk.BooleanVar(value=True)
                self.file_check_vars.append(var)

                file_frame = ttk.Frame(self.files_list_frame)
                file_frame.pack(fill=tk.X, pady=2, anchor=tk.W)

                # 格式化文件大小
                size_str = self.format_file_size(size)

                # 文件名
                filename = os.path.basename(file_path)
                display_text = f"{filename}    ({size_str})"

                checkbox = ttk.Checkbutton(file_frame, text=display_text, variable=var)
                checkbox.pack(side=tk.LEFT, anchor=tk.W)

                self.batch_files.append((file_path, size, var))

            self.update_status(f"[成功] 找到 {len(video_files)} 个视频文件")

            # 自动设置输出目录
            if not self.output_dir_var.get():
                self.output_dir_var.set(directory)

        except Exception as e:
            import traceback
            error_msg = f"[错误] 扫描目录失败:\n\n{str(e)}\n\n{traceback.format_exc()}"
            self._show_error("错误", error_msg)
            self.update_status("[错误] 扫描失败")

    def format_file_size(self, size_bytes):
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"

    def refresh_file_list_display(self):
        """刷新文件列表显示"""
        # 清空现有显示
        for widget in self.files_list_frame.winfo_children():
            widget.destroy()

        if not self.batch_files:
            # 显示提示
            self.files_hint_label = ttk.Label(
                self.files_list_frame,
                text="[提示] 拖拽视频文件或文件夹到此处",
                foreground="gray"
            )
            #self.files_hint_label.pack(pady=20)
            return

        # 显示文件列表
        for file_path, size, var in self.batch_files:
            file_frame = ttk.Frame(self.files_list_frame)
            file_frame.pack(fill=tk.X, pady=2, anchor=tk.W)

            # 格式化文件大小
            size_str = self.format_file_size(size)

            # 文件名
            filename = os.path.basename(file_path)
            display_text = f"{filename}    ({size_str})"

            checkbox = ttk.Checkbutton(file_frame, text=display_text, variable=var)
            checkbox.pack(side=tk.LEFT, anchor=tk.W)

    def clear_file_list(self):
        """清空文件列表（带确认）"""
        if not self.batch_files:
            self._show_info("提示", "[提示] 文件列表已经是空的")
            return

        # 确认对话框
        response = self._ask_yes_no(
            "确认",
            f"确定要清空文件列表吗？\n\n当前有 {len(self.batch_files)} 个文件"
        )

        if response:
            # 清空列表
            self.batch_files = []
            self.file_check_vars = []
            self.refresh_file_list_display()
            self.update_status("[成功] 已清空文件列表")

    def select_all_files(self):
        """全选所有文件"""
        for var in self.file_check_vars:
            var.set(True)
        self.update_status("[提示] 已全选所有文件")

    def deselect_all_files(self):
        """取消全选所有文件"""
        for var in self.file_check_vars:
            var.set(False)
        self.update_status("[提示] 已取消全选")

    def select_output_dir(self):
        """选择输出目录"""
        directory = filedialog.askdirectory(parent=self.dialog, title="选择输出目录")
        if directory:
            self.output_dir_var.set(directory)
            self.user_selected_output = True  # 标记用户手动选择了输出目录
            self.update_status(f"[成功] 输出目录: {directory}")

    def auto_set_output_dir(self, *args):
        """自动设置输出目录（单文件模式）"""
        # 如果用户手动选择了输出目录，则不自动更新
        if not self.mode_var.get() and not self.user_selected_output:  # 单文件模式
            video_path = self.video_file_var.get().strip()
            if video_path and os.path.exists(video_path):
                # 自动更新输出目录为视频所在目录
                output_dir = os.path.dirname(video_path)
                self.output_dir_var.set(output_dir)

    def auto_set_batch_output_dir(self, *args):
        """自动设置输出目录（批量模式）"""
        # 如果用户手动选择了输出目录，则不自动更新
        if self.mode_var.get() and not self.user_selected_output:  # 批量模式
            dir_path = self.batch_dir_var.get().strip()
            if dir_path and os.path.exists(dir_path) and os.path.isdir(dir_path):
                # 自动更新输出目录为输入目录
                self.output_dir_var.set(dir_path)

    def setup_placeholder_hints(self):
        """设置占位符提示"""
        # 单文件模式输入框占位符
        if not self.video_file_var.get():
            self.video_entry.insert(0, "拖拽视频文件到此处或点击浏览..")
            self.video_entry.config(foreground='gray')

        # 批量模式输入框占位符
        if not self.batch_dir_var.get():
            self.batch_input_entry.insert(0, "拖拽视频文件或文件夹到此处")
            self.batch_input_entry.config(foreground='gray')

        # 绑定焦点事件
        self.video_entry.bind('<FocusIn>', self.on_video_entry_focus_in)
        self.video_entry.bind('<FocusOut>', self.on_video_entry_focus_out)
        self.batch_input_entry.bind('<FocusIn>', self.on_batch_entry_focus_in)
        self.batch_input_entry.bind('<FocusOut>', self.on_batch_entry_focus_out)

    def on_video_entry_focus_in(self, event):
        """单文件输入框获得焦点 - 清除占位符"""
        if self.video_entry.get() == "拖拽视频文件到此处或点击浏览..":
            self.video_entry.delete(0, tk.END)
            self.video_entry.config(foreground='black')

    def on_video_entry_focus_out(self, event):
        """单文件输入框失去焦点 - 恢复占位符"""
        if not self.video_entry.get():
            self.video_entry.insert(0, "拖拽视频文件到此处或点击浏览..")
            self.video_entry.config(foreground='gray')

    def on_batch_entry_focus_in(self, event):
        """批量输入框获得焦点 - 清除占位符"""
        if self.batch_input_entry.get() == "拖拽视频文件或文件夹到此处":
            self.batch_input_entry.delete(0, tk.END)
            self.batch_input_entry.config(foreground='black')

    def on_batch_entry_focus_out(self, event):
        """批量输入框失去焦点 - 恢复占位符"""
        if not self.batch_input_entry.get():
            self.batch_input_entry.insert(0, "拖拽视频文件或文件夹到此处")
            self.batch_input_entry.config(foreground='gray')

    def check_ffmpeg(self):
        """检查FFmpeg是否可用"""
        try:
            # Windows: 添加 CREATE_NO_WINDOW 标志隐藏CMD窗口
            import platform
            if platform.system() == 'Windows':
                result = subprocess.run(
                    ['ffmpeg', '-version'],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                result = subprocess.run(
                    ['ffmpeg', '-version'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
            if result.returncode == 0:
                self.update_status("[成功] FFmpeg已就绪")
                return True
            else:
                self.show_ffmpeg_error()
                return False
        except FileNotFoundError:
            self.show_ffmpeg_error()
            return False
        except Exception as e:
            self.update_status(f"[错误] FFmpeg检测失败: {e}")
            return False

    def show_ffmpeg_error(self):
        """显示FFmpeg未安装的错误提示"""
        error_msg = (
            "[错误] 未检测到FFmpeg\n\n"
            "[提示] 解决方案：\n"
            "1. 下载FFmpeg: https://ffmpeg.org/download.html\n"
            "2. 解压到任意目录\n"
            "3. 将FFmpeg的bin目录添加到系统PATH环境变量\n"
            "4. 重启本程序\n\n"
            "[提示] 验证安装：在命令行运行 'ffmpeg -version'"
        )
        self._show_error("FFmpeg未安装", error_msg)
        self.update_status("[错误] 请先安装FFmpeg")
        self.start_btn.config(state=tk.DISABLED)

    def validate_inputs(self):
        """验证输入"""
        is_batch = self.mode_var.get()

        if is_batch:
            # 批量模式
            if not self.batch_files:
                self._show_warning("警告", "[警告] 请先扫描目录")
                return False

            selected_count = sum(1 for _, _, var in self.batch_files if var.get())
            if selected_count == 0:
                self._show_warning("警告", "[警告] 请至少选择一个视频文件")
                return False
        else:
            # 单文件模式
            video_file = self.video_file_var.get().strip()
            if not video_file:
                self._show_warning("警告", "[警告] 请选择视频文件")
                return False

            if not os.path.exists(video_file):
                self._show_error("错误", f"[错误] 视频文件不存在:\n{video_file}")
                return False

        # 检查输出目录
        output_dir = self.output_dir_var.get().strip()
        if not output_dir:
            self._show_warning("警告", "[警告] 请指定输出目录")
            return False

        return True

    def start_conversion(self):
        """开始转换"""
        if not self.validate_inputs():
            return

        # 禁用开始按钮，启用取消按钮
        self.start_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)
        self.is_processing = True
        self.cancel_requested = False

        # 禁用模式切换按钮（转换过程中不允许切换）
        self.single_radio.config(state=tk.DISABLED)
        self.batch_radio.config(state=tk.DISABLED)

        # 重置进度
        self.single_progress_var.set(0)
        self.total_progress_var.set(0)

        # 重置批量模式的进度显示
        if self.mode_var.get():
            self.current_file_label.config(text="")
            self.current_progress_label.config(text="0%")
            self.total_progress_label.config(text="0% (0/0)")

        self.update_status("[提示] 开始转换...")

        # 在新线程中执行转换
        thread = threading.Thread(target=self._conversion_thread)
        thread.daemon = True
        thread.start()

    def _conversion_thread(self):
        """转换线程"""
        print(f"\n[视频转音频] ========== 转换线程启动 ==========")
        try:
            is_batch = self.mode_var.get()
            output_dir = self.output_dir_var.get().strip()

            # 批量模式：创建带时间戳的子文件夹
            if is_batch:
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                batch_output_dir = os.path.join(output_dir, f"extracted_audio_{timestamp}")
                os.makedirs(batch_output_dir, exist_ok=True)
                print(f"[视频转音频] 批量输出目录: {batch_output_dir}")
                self._batch_convert(batch_output_dir)
            else:
                # 单文件模式：直接输出到指定目录
                os.makedirs(output_dir, exist_ok=True)
                self._single_convert(output_dir)

        except Exception as e:
            import traceback
            print(f"\n[视频转音频] ========== 发生异常 ==========")
            print(f"[视频转音频] 异常信息: {str(e)}")
            print(f"[视频转音频] 异常堆栈:\n{traceback.format_exc()}")

            error_msg = f"[错误] 转换过程发生错误:\n\n{str(e)}"
            self.dialog.after(0, lambda msg=f"[错误] 转换失败: {e}": self.update_status(msg))
            self.dialog.after(0, lambda m=error_msg: self._show_error("错误", m))

        finally:
            print(f"\n[视频转音频] ========== 转换线程结束 ==========")
            # 恢复按钮状态
            self.dialog.after(0, lambda: self.start_btn.config(state=tk.NORMAL))
            self.dialog.after(0, lambda: self.cancel_btn.config(state=tk.DISABLED))
            # 恢复模式切换按钮
            self.dialog.after(0, lambda: self.single_radio.config(state=tk.NORMAL))
            self.dialog.after(0, lambda: self.batch_radio.config(state=tk.NORMAL))
            self.is_processing = False
            self.process = None

    def _single_convert(self, output_dir):
        """单文件转换"""
        video_file = self.video_file_var.get().strip()
        video_name = os.path.splitext(os.path.basename(video_file))[0]

        # 获取输出格式和扩展名
        format_name = self.format_var.get()
        format_config = AUDIO_FORMATS[format_name]
        extension = format_config['extension']

        output_file = os.path.join(output_dir, f"{video_name}{extension}")

        self.update_status(f"[提示] 正在转换: {os.path.basename(video_file)}...")

        success = self._convert_file(video_file, output_file)

        if success and not self.cancel_requested:
            self.dialog.after(0, lambda: self.single_progress_var.set(100))
            self.dialog.after(0, lambda: self.single_progress_label.config(text="100%"))
            self.dialog.after(0, lambda: self.update_status("[成功] 转换完成！"))
            self.dialog.after(0, lambda: self.ask_open_output_folder(output_dir))
        elif self.cancel_requested:
            self.dialog.after(0, lambda: self.update_status("[提示] 操作已取消"))
        else:
            self.dialog.after(0, lambda: self.update_status("[错误] 转换失败"))

    def _batch_convert(self, output_dir):
        """批量转换"""
        selected_files = [(path, size) for path, size, var in self.batch_files if var.get()]
        total = len(selected_files)
        success_count = 0
        failed_files = []

        print(f"[视频转音频] 批量转换开始，共 {total} 个文件")

        for index, (video_file, size) in enumerate(selected_files, 1):
            if self.cancel_requested:
                print(f"[视频转音频] 用户取消操作")
                break

            # 更新状态
            filename = os.path.basename(video_file)
            status_msg = f"[提示] 正在转换 {filename}... ({index}/{total})"
            self.dialog.after(0, lambda msg=status_msg: self.update_status(msg))

            # 更新当前文件名
            self.dialog.after(0, lambda name=filename:
                self.current_file_label.config(text=name))

            # 重置当前文件进度为 0%
            self.dialog.after(0, lambda:
                self.current_progress_label.config(text="0%"))

            # 生成输出文件名
            video_name = os.path.splitext(filename)[0]
            format_name = self.format_var.get()
            format_config = AUDIO_FORMATS[format_name]
            extension = format_config['extension']
            output_file = os.path.join(output_dir, f"{video_name}{extension}")

            # 转换文件（_monitor_progress 会实时更新 current_progress_label）
            success = self._convert_file(video_file, output_file)

            if success:
                success_count += 1
                # 确保当前文件进度显示为100%
                self.dialog.after(0, lambda:
                    self.current_progress_label.config(text="100%"))
            else:
                failed_files.append(filename)

            # 更新总体进度（基于已完成的文件数）
            total_progress = (success_count / total) * 100
            self.dialog.after(0, lambda p=total_progress: self.total_progress_var.set(p))
            self.dialog.after(0, lambda sc=success_count, t=total, p=total_progress:
                self.total_progress_label.config(text=f"{int(p)}% ({sc}/{t})"))

        # 处理完成
        if not self.cancel_requested:
            if success_count == total:
                success_msg = f"[成功] 全部转换完成！共 {success_count} 个文件"
                self.dialog.after(0, lambda msg=success_msg: self.update_status(msg))
                self.dialog.after(0, lambda d=output_dir: self.ask_open_output_folder(d))
            elif success_count > 0:
                fail_msg = f"成功: {success_count}/{total}\n失败: {', '.join(failed_files)}"
                warning_msg = f"[警告] 部分转换完成: {success_count}/{total}"
                self.dialog.after(0, lambda msg=warning_msg: self.update_status(msg))
                self.dialog.after(0, lambda m=fail_msg: self._show_warning("部分成功", f"[警告] 转换部分完成\n\n{m}"))
            else:
                self.dialog.after(0, lambda: self.update_status("[错误] 转换失败"))
                self.dialog.after(0, lambda: self._show_error("错误", "[错误] 所有文件转换失败"))
        else:
            self.dialog.after(0, lambda: self.update_status("[提示] 操作已取消"))

    def _convert_file(self, input_file, output_file):
        """转换单个文件"""
        try:
            # 获取格式配置
            format_name = self.format_var.get()
            format_config = AUDIO_FORMATS[format_name]

            encoder = format_config['encoder']
            quality = self.quality_var.get()
            quality_param = format_config['qualities'].get(quality, '')

            # 构建FFmpeg命令
            cmd = ['ffmpeg', '-i', input_file, '-vn', '-acodec', encoder]

            # 添加质量参数
            if quality_param:
                quality_parts = quality_param.split()
                cmd.extend(quality_parts)

            cmd.extend(['-y', output_file])

            print(f"[视频转音频] FFmpeg命令: {' '.join(cmd)}")

            # 执行FFmpeg命令
            import platform
            if platform.system() == 'Windows':
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='ignore',
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='ignore'
                )

            # 实时读取进度
            duration = self._get_video_duration(input_file)
            self._monitor_progress(self.process, duration)

            # 等待完成
            self.process.wait()
            returncode = self.process.returncode

            if returncode == 0:
                print(f"[视频转音频] ✓ 成功转换: {output_file}")
                return True
            else:
                print(f"[视频转音频] ✗ 转换失败，返回码: {returncode}")
                return False

        except Exception as e:
            import traceback
            print(f"[视频转音频] ✗ 转换时发生异常: {e}")
            print(f"[视频转音频] 异常堆栈: {traceback.format_exc()}")
            return False

    def _get_video_duration(self, video_file):
        """获取视频时长"""
        try:
            cmd = [
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                video_file
            ]
            # Windows: 添加 CREATE_NO_WINDOW 标志隐藏CMD窗口
            import platform
            if platform.system() == 'Windows':
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return float(result.stdout.strip())
        except Exception as e:
            print(f"[视频转音频] 获取视频时长失败: {e}")
        return 0

    def _monitor_progress(self, process, duration):
        """监控FFmpeg进度"""
        if duration <= 0:
            return

        # 判断当前是单文件模式还是批量模式
        is_batch = self.mode_var.get()

        def read_stderr():
            for line in process.stderr:
                if self.cancel_requested:
                    break

                # 解析时间进度 (time=00:01:23.45)
                match = re.search(r'time=(\d+):(\d+):(\d+\.\d+)', line)
                if match:
                    hours = int(match.group(1))
                    minutes = int(match.group(2))
                    seconds = float(match.group(3))
                    current_time = hours * 3600 + minutes * 60 + seconds

                    progress = min((current_time / duration) * 100, 100)

                    if is_batch:
                        # 批量模式：更新当前文件进度（纯文本百分比）
                        self.dialog.after(0, lambda p=progress:
                            self.current_progress_label.config(text=f"{int(p)}%"))
                    else:
                        # 单文件模式：更新进度条和百分比
                        self.dialog.after(0, lambda p=progress: self.single_progress_var.set(p))
                        self.dialog.after(0, lambda p=progress: self.single_progress_label.config(text=f"{int(p)}%"))

        thread = threading.Thread(target=read_stderr)
        thread.daemon = True
        thread.start()

    def cancel_conversion(self):
        """取消转换"""
        if self.is_processing and self.process:
            try:
                self.cancel_requested = True
                self.process.terminate()
                self.update_status("[提示] 正在取消...")
            except Exception as e:
                print(f"[视频转音频] 取消进程失败: {e}")

    def update_status(self, message: str):
        """更新状态栏"""
        self.status_var.set(message)
        self.dialog.update_idletasks()

    def center_dialog(self):
        """居中显示对话框"""
        try:
            self.dialog.update_idletasks()

            # 获取父窗口位置
            parent_x = self.parent.winfo_x()
            parent_y = self.parent.winfo_y()
            parent_width = self.parent.winfo_width()
            parent_height = self.parent.winfo_height()

            # 获取对话框尺寸
            dialog_width = 700
            dialog_height = 700

            # 计算居中位置
            x = parent_x + (parent_width - dialog_width) // 2
            y = parent_y + (parent_height - dialog_height) // 2

            self.dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")

        except Exception as e:
            print(f"居中对话框失败: {e}")

    def open_output_folder(self):
        """打开输出文件夹"""
        output_dir = self.output_dir_var.get().strip()

        if not output_dir:
            self._show_warning("警告", "[警告] 请先指定输出目录")
            return

        if not os.path.exists(output_dir):
            self._show_warning("警告", f"[警告] 输出目录不存在:\n{output_dir}")
            return

        try:
            import subprocess
            import platform

            system = platform.system()
            if system == 'Windows':
                subprocess.run(['explorer', os.path.abspath(output_dir)])
            elif system == 'Darwin':
                subprocess.run(['open', output_dir])
            else:
                subprocess.run(['xdg-open', output_dir])

            self.update_status(f"[成功] 已打开输出文件夹: {output_dir}")

        except Exception as e:
            self._show_error("错误", f"[错误] 无法打开文件夹: {e}")

    def ask_open_output_folder(self, output_dir):
        """询问是否打开输出文件夹"""
        try:
            response = self._ask_yes_no(
                "完成",
                f"[成功] 转换完成！\n\n输出目录:\n{output_dir}\n\n是否打开输出文件夹?"
            )

            if response:
                if output_dir and os.path.exists(output_dir):
                    import subprocess
                    import platform

                    system = platform.system()
                    if system == 'Windows':
                        subprocess.run(['explorer', os.path.abspath(output_dir)])
                    elif system == 'Darwin':
                        subprocess.run(['open', output_dir])
                    else:
                        subprocess.run(['xdg-open', output_dir])

                    print(f"[视频转音频] 已打开输出文件夹: {output_dir}")

        except Exception as e:
            print(f"[视频转音频] 打开输出文件夹失败: {e}")
        finally:
            # 恢复父窗口焦点
            self._restore_dialog_focus()

    def _restore_dialog_focus(self):
        """恢复对话框焦点 - 避免最小化问题"""
        try:
            self.dialog.deiconify()
            self.dialog.lift()
            self.dialog.focus_force()
        except:
            pass

    def _show_error(self, title, message):
        """显示错误对话框 - 使用自定义消息框避免最小化"""
        if CUSTOM_MESSAGEBOX_AVAILABLE:
            custom_messagebox.showerror(title, message, parent=self.dialog)
        else:
            messagebox.showerror(title, message, parent=self.dialog)
            self._restore_dialog_focus()

    def _show_warning(self, title, message):
        """显示警告对话框 - 使用自定义消息框避免最小化"""
        if CUSTOM_MESSAGEBOX_AVAILABLE:
            custom_messagebox.showwarning(title, message, parent=self.dialog)
        else:
            messagebox.showwarning(title, message, parent=self.dialog)
            self._restore_dialog_focus()

    def _show_info(self, title, message):
        """显示信息对话框 - 使用自定义消息框避免最小化"""
        if CUSTOM_MESSAGEBOX_AVAILABLE:
            custom_messagebox.showinfo(title, message, parent=self.dialog)
        else:
            messagebox.showinfo(title, message, parent=self.dialog)
            self._restore_dialog_focus()

    def _ask_yes_no(self, title, message):
        """显示是否对话框 - 使用自定义消息框避免最小化"""
        try:
            response = messagebox.askyesno(title, message, icon='info', parent=self.dialog)
            return response
        finally:
            self._restore_dialog_focus()
