import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import threading
import time
import codecs
import re
from typing import Optional, Tuple, List
from pathlib import Path

from utils.file_utils import FileUtils
from config.settings import app_config
from utils import custom_messagebox

# 尝试导入拖拽支持库 - 参考外部文件的实现方式
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DRAG_DROP_AVAILABLE = True
    print("tkinterdnd2 导入成功")
except ImportError as e:
    DRAG_DROP_AVAILABLE = False
    print(f"tkinterdnd2 导入失败: {e}")

# 导入图标管理器
try:
    from icon_manager import set_window_icon
    ICON_AVAILABLE = True
except ImportError:
    ICON_AVAILABLE = False
    def set_window_icon(window):
        pass

class ImportDialog:
    """导入对话框"""
    
    def __init__(self, parent):
        self.parent = parent
        self.result = None

        # 变量
        self.video_path_var = tk.StringVar()
        self.subtitle_path_var = tk.StringVar()
        # 保留编码设置变量用于兼容性，但使用默认值
        self.preset_var = tk.StringVar(value='veryfast')
        self.crf_var = tk.StringVar(value='24')

        # 批量导入变量
        self.batch_mode_var = tk.BooleanVar(value=False)
        self.batch_directory_var = tk.StringVar()
        self.batch_pairs = []  # 存储找到的视频-字幕对

        # 导入状态控制
        self.is_importing = False
        self.cancel_flag = False  # 取消标志，用于优雅退出导入线程
        self.import_start_button = None
        self.import_cancel_button = None
        self.open_input_dir_button = None
        self.batch_scan_button = None

        # 回调函数（用于通知主窗口立即刷新）
        self.on_close_callback = None

        self.create_dialog()
    
    def create_dialog(self):
        """创建对话框"""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("导入视频和字幕")
        self.dialog.geometry("900x800")
        self.dialog.resizable(True, True)

        # 不使用模态窗口设置，允许窗口自由最小化和切换
        # self.dialog.transient(self.parent)  # 会隐藏最小化按钮
        # self.dialog.grab_set()  # 会阻止窗口最小化，导入任务时间长，应允许用户最小化窗口

        # 设置窗口图标
        if ICON_AVAILABLE:
            set_window_icon(self.dialog)

        # 居中显示
        self.center_dialog()

        # 创建内容
        self.create_content()

        # 绑定事件
        self.dialog.protocol("WM_DELETE_WINDOW", self.on_cancel)

        # 设置拖拽功能
        self.setup_drag_drop()
    
    def center_dialog(self):
        """居中显示对话框"""
        self.dialog.update_idletasks()

        # 使用设定的窗口尺寸
        dialog_width = 900
        dialog_height = 800

        # 获取屏幕尺寸
        screen_width = self.dialog.winfo_screenwidth()
        screen_height = self.dialog.winfo_screenheight()

        # 计算居中位置
        x = (screen_width - dialog_width) // 2
        y = (screen_height - dialog_height) // 2

        # 确保窗口不会超出屏幕
        if y < 0:
            y = 0
        if x < 0:
            x = 0

        self.dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
    
    def create_content(self):
        """创建对话框内容"""
        main_frame = ttk.Frame(self.dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # 标题
        title_label = ttk.Label(main_frame, text="导入视频和字幕", font=('', 14, 'bold'))
        title_label.pack(pady=(0, 20))

        # 导入模式选择
        self.create_mode_selection(main_frame)

        # 文件选择区域（包含按钮）
        self.create_file_selection(main_frame)

        # 批量导入区域
        self.create_batch_selection(main_frame)

        # 日志区域（移除说明区域，让日志窗口更大）
        self.create_log_area(main_frame)

    def create_mode_selection(self, parent):
        """创建导入模式选择区域"""
        mode_frame = ttk.LabelFrame(parent, text="导入模式")
        mode_frame.pack(fill=tk.X, pady=(0, 15))

        mode_inner_frame = ttk.Frame(mode_frame)
        mode_inner_frame.pack(fill=tk.X, padx=10, pady=10)

        # 单个文件导入（保存为实例变量，方便禁用）
        self.single_radio = ttk.Radiobutton(
            mode_inner_frame,
            text="单个文件导入",
            variable=self.batch_mode_var,
            value=False,
            command=self.on_mode_changed
        )
        self.single_radio.pack(side=tk.LEFT, padx=(0, 20))

        # 批量导入（保存为实例变量，方便禁用）
        self.batch_radio = ttk.Radiobutton(
            mode_inner_frame,
            text="批量导入（扫描目录）",
            variable=self.batch_mode_var,
            value=True,
            command=self.on_mode_changed
        )
        self.batch_radio.pack(side=tk.LEFT)

    def create_file_selection(self, parent):
        """创建文件选择区域"""
        self.file_frame = ttk.LabelFrame(parent, text="单个文件选择")
        self.file_frame.pack(fill=tk.X, pady=(0, 15))

        # 视频文件
        video_frame = ttk.Frame(self.file_frame)
        video_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(video_frame, text="视频文件:").pack(anchor=tk.W)

        video_input_frame = ttk.Frame(video_frame)
        video_input_frame.pack(fill=tk.X, pady=(5, 0))

        self.video_entry = ttk.Entry(video_input_frame, textvariable=self.video_path_var)
        self.video_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.video_browse_button = ttk.Button(video_input_frame, text="浏览", command=self.browse_video_file)
        self.video_browse_button.pack(side=tk.RIGHT, padx=(5, 0))

        # 字幕文件
        subtitle_frame = ttk.Frame(self.file_frame)
        subtitle_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        ttk.Label(subtitle_frame, text="字幕文件:").pack(anchor=tk.W)

        subtitle_input_frame = ttk.Frame(subtitle_frame)
        subtitle_input_frame.pack(fill=tk.X, pady=(5, 0))

        self.subtitle_entry = ttk.Entry(subtitle_input_frame, textvariable=self.subtitle_path_var)
        self.subtitle_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.subtitle_browse_button = ttk.Button(subtitle_input_frame, text="浏览", command=self.browse_subtitle_file)
        self.subtitle_browse_button.pack(side=tk.RIGHT, padx=(5, 0))

        # 操作按钮区域
        button_area_frame = ttk.Frame(subtitle_frame)
        button_area_frame.pack(fill=tk.X, pady=(5, 0))

        # 左侧：操作按钮
        self.import_start_button = ttk.Button(button_area_frame, text="开始导入", command=self.on_import)
        self.import_start_button.pack(side=tk.LEFT)

        self.open_input_dir_button = ttk.Button(button_area_frame, text="打开输入目录", command=self.open_input_directory)
        self.open_input_dir_button.pack(side=tk.LEFT, padx=(5, 0))

        self.import_cancel_button = ttk.Button(button_area_frame, text="取消", command=self.on_cancel)
        self.import_cancel_button.pack(side=tk.LEFT, padx=(5, 0))

    def create_batch_selection(self, parent):
        """创建批量导入区域"""
        self.batch_frame = ttk.LabelFrame(parent, text="批量导入")
        self.batch_frame.pack(fill=tk.X, pady=(0, 15))

        # 目录选择
        dir_frame = ttk.Frame(self.batch_frame)
        dir_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(dir_frame, text="扫描目录:").pack(anchor=tk.W)

        dir_input_frame = ttk.Frame(dir_frame)
        dir_input_frame.pack(fill=tk.X, pady=(5, 0))

        self.batch_dir_entry = ttk.Entry(dir_input_frame, textvariable=self.batch_directory_var)
        self.batch_dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.batch_dir_browse_button = ttk.Button(dir_input_frame, text="浏览", command=self.browse_batch_directory)
        self.batch_dir_browse_button.pack(side=tk.RIGHT, padx=(5, 0))

        # 导入按钮（移除扫描按钮，改为自动扫描）
        scan_frame = ttk.Frame(self.batch_frame)
        scan_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        self.batch_import_button = ttk.Button(scan_frame, text="开始导入", command=self.on_import)
        self.batch_import_button.pack(side=tk.LEFT)

        self.batch_cancel_button = ttk.Button(scan_frame, text="取消", command=self.on_cancel)
        self.batch_cancel_button.pack(side=tk.LEFT, padx=(10, 0))

        # 文件列表
        list_frame = ttk.Frame(self.batch_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        ttk.Label(list_frame, text="找到的视频-字幕对:").pack(anchor=tk.W)

        # 创建列表框和滚动条
        list_container = ttk.Frame(list_frame)
        list_container.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

        self.batch_listbox = tk.Listbox(list_container, height=6)
        self.batch_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        batch_scrollbar = ttk.Scrollbar(list_container, command=self.batch_listbox.yview)
        batch_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.batch_listbox.config(yscrollcommand=batch_scrollbar.set)

        # 初始状态：隐藏批量导入区域
        self.batch_frame.pack_forget()
    

    


    def create_log_area(self, parent):
        """创建日志区域"""
        self.log_frame = ttk.LabelFrame(parent, text="导入日志")
        self.log_frame.pack(fill=tk.BOTH, expand=True, pady=(15, 0))

        # 创建日志文本框和滚动条
        log_container = ttk.Frame(self.log_frame)
        log_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 日志文本框（增加高度，因为移除了说明区域）
        self.log_text = tk.Text(
            log_container,
            height=15,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=('Consolas', 9)
        )
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 滚动条
        log_scrollbar = ttk.Scrollbar(log_container, command=self.log_text.yview)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=log_scrollbar.set)

        # 添加初始日志
        self.log_message("准备导入...")

    def on_mode_changed(self):
        """导入模式切换"""
        if self.batch_mode_var.get():
            # 切换到批量模式
            self.file_frame.pack_forget()
            self.batch_frame.pack(fill=tk.X, pady=(0, 15), before=self.log_frame)
            self.log_message("切换到批量导入模式")

            # 禁用单个文件相关按钮
            self.open_input_dir_button.config(state="disabled")
        else:
            # 切换到单个文件模式
            self.batch_frame.pack_forget()
            self.file_frame.pack(fill=tk.X, pady=(0, 15), before=self.log_frame)
            self.log_message("切换到单个文件导入模式")

            # 启用单个文件相关按钮
            self.open_input_dir_button.config(state="normal")

    def disable_controls_during_import(self):
        """导入过程中禁用控件"""
        # 禁用模式切换（防止导入中切换模式）
        if hasattr(self, 'single_radio'):
            self.single_radio.config(state="disabled")
        if hasattr(self, 'batch_radio'):
            self.batch_radio.config(state="disabled")

        # 禁用文件选择相关按钮
        if hasattr(self, 'video_browse_button'):
            self.video_browse_button.config(state="disabled")
        if hasattr(self, 'subtitle_browse_button'):
            self.subtitle_browse_button.config(state="disabled")
        if hasattr(self, 'batch_dir_browse_button'):
            self.batch_dir_browse_button.config(state="disabled")
        if hasattr(self, 'batch_import_button'):
            self.batch_import_button.config(state="disabled")
        if hasattr(self, 'open_input_dir_button'):
            self.open_input_dir_button.config(state="disabled")

    def enable_controls_after_import(self):
        """导入完成后启用控件"""
        # 启用模式切换
        if hasattr(self, 'single_radio'):
            self.single_radio.config(state="normal")
        if hasattr(self, 'batch_radio'):
            self.batch_radio.config(state="normal")

        # 启用文件选择相关按钮
        if hasattr(self, 'video_browse_button'):
            self.video_browse_button.config(state="normal")
        if hasattr(self, 'subtitle_browse_button'):
            self.subtitle_browse_button.config(state="normal")
        if hasattr(self, 'batch_dir_browse_button'):
            self.batch_dir_browse_button.config(state="normal")
        if hasattr(self, 'batch_import_button'):
            self.batch_import_button.config(state="normal")

        # 根据当前模式设置按钮状态
        if not self.batch_mode_var.get() and hasattr(self, 'open_input_dir_button'):
            self.open_input_dir_button.config(state="normal")

    def browse_batch_directory(self):
        """浏览批量导入目录"""
        directory = filedialog.askdirectory(
            title="选择包含视频和字幕文件的目录",
            parent=self.dialog
        )

        if directory:
            # 标准化路径分隔符
            normalized_path = os.path.normpath(directory)

            # 清除批量目录输入框的提示文字并设置路径
            self.batch_dir_entry.delete(0, tk.END)
            self.batch_dir_entry.insert(0, normalized_path)
            self.batch_dir_entry.config(foreground='black')
            self.batch_directory_var.set(normalized_path)

            self.log_message(f"选择目录: {normalized_path}")
            # 自动扫描文件
            self.scan_batch_files()

    def scan_batch_files(self):
        """扫描批量文件"""
        directory = self.batch_directory_var.get().strip()
        if not directory:
            custom_messagebox.showwarning("提示", "请先选择扫描目录", parent=self.dialog)
            return

        if not os.path.exists(directory):
            custom_messagebox.showerror("错误", "目录不存在", parent=self.dialog)
            return

        self.log_message("开始扫描视频-字幕对...")

        # 清空之前的结果
        self.batch_pairs.clear()
        self.batch_listbox.delete(0, tk.END)

        try:
            # 扫描目录中的视频文件 - 改用os.listdir避免glob对特殊符号的问题
            video_files = []

            # 直接遍历目录，避免glob模式匹配对特殊符号的限制
            try:
                all_files = os.listdir(directory)
                supported_exts = FileUtils.get_video_extensions() + FileUtils.get_audio_extensions()

                for filename in all_files:
                    file_ext = os.path.splitext(filename)[1].lower()
                    if file_ext in supported_exts:
                        full_path = os.path.join(directory, filename)
                        if os.path.isfile(full_path):
                            video_files.append(full_path)

                self.log_message(f"扫描到 {len(video_files)} 个媒体文件")

            except Exception as e:
                self.log_message(f"扫描目录时出错: {e}")
                return

            found_pairs = 0
            for video_file in video_files:
                # 查找匹配的字幕文件
                subtitle_file = FileUtils.find_matching_subtitle(video_file)
                if subtitle_file:
                    self.batch_pairs.append((video_file, subtitle_file))

                    # 显示在列表中
                    video_name = os.path.basename(video_file)
                    subtitle_name = os.path.basename(subtitle_file)
                    display_text = f"{video_name} + {subtitle_name}"
                    self.batch_listbox.insert(tk.END, display_text)
                    found_pairs += 1

            self.log_message(f"扫描完成，找到 {found_pairs} 个视频-字幕对")

            if found_pairs == 0:
                custom_messagebox.showinfo("扫描结果", "未找到匹配的视频-字幕对\n\n请确保视频文件和字幕文件名称相同（扩展名除外）", parent=self.dialog)

        except Exception as e:
            self.log_message(f"扫描失败: {e}")
            custom_messagebox.showerror("错误", f"扫描目录时发生错误：{e}", parent=self.dialog)

    def log_message(self, message):
        """添加日志消息"""
        import time
        timestamp = time.strftime('%H:%M:%S')
        log_entry = f"[{timestamp}] {message}\n"

        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, log_entry)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

        # 更新界面
        self.dialog.update_idletasks()
    


    def browse_video_file(self):
        """浏览视频文件"""
        filetypes = [
            ("视频文件", "*.mp4 *.mkv *.avi *.mov *.flv *.wmv *.m4v *.mpeg *.mpg"),
            ("音频文件", "*.mp3 *.wav *.flac *.aac *.m4a *.ogg"),
            ("所有文件", "*.*")
        ]

        filename = filedialog.askopenfilename(
            title="选择视频文件",
            filetypes=filetypes,
            parent=self.dialog
        )

        if filename:
            # 标准化路径分隔符
            normalized_path = os.path.normpath(filename)

            # 清除视频输入框的提示文字并设置路径
            self.video_entry.delete(0, tk.END)
            self.video_entry.insert(0, normalized_path)
            self.video_entry.config(foreground='black')
            self.video_path_var.set(normalized_path)

            # 后端自动查找匹配的字幕文件（不显示提示）
            self.auto_find_subtitle_silent()

    def browse_subtitle_file(self):
        """浏览字幕文件"""
        filetypes = [
            ("字幕文件", "*.srt *.ass *.ssa *.vtt"),
            ("所有文件", "*.*")
        ]

        filename = filedialog.askopenfilename(
            title="选择字幕文件",
            filetypes=filetypes,
            parent=self.dialog
        )

        if filename:
            # 标准化路径分隔符
            normalized_path = os.path.normpath(filename)

            # 清除字幕输入框的提示文字并设置路径
            self.subtitle_entry.delete(0, tk.END)
            self.subtitle_entry.insert(0, normalized_path)
            self.subtitle_entry.config(foreground='black')
            self.subtitle_path_var.set(normalized_path)

    def open_input_directory(self):
        """打开输入目录（视频文件所在目录）"""
        video_path = self.video_path_var.get().strip()
        if not video_path:
            custom_messagebox.showwarning("提示", "请先选择视频文件", parent=self.dialog)
            return

        if not os.path.exists(video_path):
            custom_messagebox.showerror("错误", "视频文件不存在，无法打开目录", parent=self.dialog)
            return

        import subprocess
        import platform

        # 获取视频文件所在的目录
        directory = os.path.dirname(os.path.abspath(video_path))

        try:
            if platform.system() == "Windows":
                # Windows下直接打开目录，使用os.startfile更可靠
                os.startfile(directory)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(['open', directory], check=False)
            else:  # Linux
                subprocess.run(['xdg-open', directory], check=False)

            self.log_message(f"已打开输入目录: {directory}")
        except Exception as e:
            # 即使打开成功也可能报错，所以只在真正失败时才显示错误
            try:
                # 验证目录是否存在，如果存在说明操作成功
                if os.path.exists(directory):
                    self.log_message(f"已打开输入目录: {directory}")
                else:
                    custom_messagebox.showerror("错误", f"目录不存在：{directory}", parent=self.dialog)
            except:
                custom_messagebox.showerror("错误", f"打开目录时发生错误：{e}", parent=self.dialog)

    def auto_find_subtitle(self):
        """自动查找匹配的字幕文件（带提示）"""
        video_path = self.video_path_var.get()
        if not video_path:
            return

        subtitle_path = FileUtils.find_matching_subtitle(video_path)
        if subtitle_path:
            self.subtitle_path_var.set(subtitle_path)
            messagebox.showinfo("找到字幕", f"已自动找到匹配的字幕文件：\n{os.path.basename(subtitle_path)}")
        else:
            messagebox.showwarning("未找到字幕", "未找到匹配的字幕文件，请手动选择。")

    def auto_find_subtitle_silent(self):
        """静默自动查找匹配的字幕文件（不显示提示）"""
        video_path = self.video_path_var.get()
        if not video_path:
            return

        subtitle_path = FileUtils.find_matching_subtitle(video_path)
        if subtitle_path:
            # 标准化路径分隔符（Windows使用反斜杠）
            normalized_path = os.path.normpath(subtitle_path)

            # 清除字幕输入框的提示文字并设置路径
            self.subtitle_entry.delete(0, tk.END)
            self.subtitle_entry.insert(0, normalized_path)
            self.subtitle_entry.config(foreground='black')
            self.subtitle_path_var.set(normalized_path)

            self.log_message(f"已自动找到匹配的字幕文件: {os.path.basename(normalized_path)}")



    def validate_inputs(self) -> bool:
        """验证输入"""
        if self.batch_mode_var.get():
            # 批量模式验证
            if not self.batch_pairs:
                custom_messagebox.showerror("错误", "请先扫描目录以找到视频-字幕对", parent=self.dialog)
                return False
            return True
        else:
            # 单个文件模式验证
            video_path = self.video_path_var.get().strip()
            subtitle_path = self.subtitle_path_var.get().strip()

            if not video_path:
                custom_messagebox.showerror("错误", "请选择视频文件", parent=self.dialog)
                return False

            if not os.path.exists(video_path):
                custom_messagebox.showerror("错误", "视频文件不存在", parent=self.dialog)
                return False

            if not (FileUtils.is_video_file(video_path) or FileUtils.is_audio_file(video_path)):
                custom_messagebox.showerror("错误", "不支持的视频/音频文件格式", parent=self.dialog)
                return False

            if not subtitle_path:
                custom_messagebox.showerror("错误", "请选择字幕文件", parent=self.dialog)
                return False

            if not os.path.exists(subtitle_path):
                custom_messagebox.showerror("错误", "字幕文件不存在", parent=self.dialog)
                return False

            if not FileUtils.is_subtitle_file(subtitle_path):
                custom_messagebox.showerror("错误", "不支持的字幕文件格式", parent=self.dialog)
                return False

            return True

    def on_import(self):
        """开始导入"""
        # 防止重复点击（参考集成合并/导出窗口）
        if self.is_importing:
            return

        if not self.validate_inputs():
            return

        # 开始导入处理
        self.is_importing = True
        self.cancel_flag = False  # 重置取消标志

        # 根据当前模式禁用相应的按钮
        if self.batch_mode_var.get():
            # 批量模式：禁用批量导入按钮
            self.batch_import_button.config(text="导入中...", state="disabled")
            self.batch_cancel_button.config(text="关闭", command=self.close_after_import)
        else:
            # 单个文件模式：禁用单个文件导入按钮
            self.import_start_button.config(text="导入中...", state="disabled")
            self.import_cancel_button.config(text="关闭", command=self.close_after_import)

        # 禁用其他控件
        self.disable_controls_during_import()

        if self.batch_mode_var.get():
            # 批量导入
            self.log_message("开始批量导入处理...")
            self.log_message(f"找到 {len(self.batch_pairs)} 个视频-字幕对")

            # 在新线程中执行批量导入
            thread = threading.Thread(
                target=self.batch_import_worker,
                daemon=True
            )
            thread.start()
        else:
            # 单个文件导入
            self.log_message("开始导入处理...")
            self.log_message(f"视频文件: {os.path.basename(self.video_path_var.get())}")
            self.log_message(f"字幕文件: {os.path.basename(self.subtitle_path_var.get())}")

            # 先进行字幕文件校验
            subtitle_path = self.subtitle_path_var.get().strip()
            self.log_message("开始字幕文件校验...")

            is_valid, errors, warnings = self.validate_subtitle_file(subtitle_path)

            # 显示警告信息
            if warnings:
                for warning in warnings:
                    self.log_message(f"{warning}")

            # 如果校验失败，停止导入
            if not is_valid:
                # 不重复记录错误日志，validate_subtitle_file 已经记录过了
                # 只显示错误对话框
                error_msg = "字幕文件校验失败：\n" + "\n".join(errors)
                if warnings:
                    error_msg += "\n\n警告：\n" + "\n".join(warnings)
                messagebox.showerror("字幕校验失败", error_msg, parent=self.dialog)

                # 恢复按钮状态
                self.is_importing = False
                self.import_start_button.config(text="开始导入", state="normal")
                self.import_cancel_button.config(text="取消", command=self.on_cancel)
                self.enable_controls_after_import()
                return

            self.log_message("字幕文件校验通过，开始导入...")

            # 在新线程中执行导入
            video_path = self.video_path_var.get().strip()
            preset = self.preset_var.get()
            crf = self.crf_var.get()

            thread = threading.Thread(
                target=self.import_worker,
                args=(video_path, subtitle_path, preset, crf),
                daemon=True
            )
            thread.start()

    def batch_import_worker(self):
        """批量导入工作线程"""
        try:
            from core.enhanced_video_processor import EnhancedVideoProcessor

            total_pairs = len(self.batch_pairs)
            success_count = 0
            failed_count = 0
            skipped_count = 0
            failed_files = []

            for i, (video_path, subtitle_path) in enumerate(self.batch_pairs, 1):
                # 检查是否需要取消（优雅退出）
                if self.cancel_flag:
                    self.dialog.after(0, self.log_message, "用户取消了批量导入")
                    break

                try:
                    video_name = os.path.basename(video_path)
                    self.dialog.after(0, self.log_message, f"[{i}/{total_pairs}] 处理: {video_name}")

                    # 先进行字幕文件校验 - 照搬外部脚本的校验方式
                    self.dialog.after(0, self.log_message, f"开始字幕文件校验: {os.path.basename(subtitle_path)}")

                    is_valid, errors, warnings = self.validate_subtitle_file(subtitle_path)

                    # 显示警告信息
                    if warnings:
                        for warning in warnings:
                            self.dialog.after(0, self.log_message, f"{warning}")

                    # 如果校验失败，跳过此文件
                    if not is_valid:
                        # 不重复记录错误日志，validate_subtitle_file 已经记录过了
                        self.dialog.after(0, self.log_message, f"字幕文件校验失败，跳过: {os.path.basename(subtitle_path)}")
                        failed_count += 1
                        failed_files.append(video_name)
                        continue

                    self.dialog.after(0, self.log_message, f"字幕文件校验通过: {os.path.basename(subtitle_path)}")

                    # 创建处理器实例
                    processor = EnhancedVideoProcessor()

                    # 设置日志回调
                    def log_callback(message):
                        self.dialog.after(0, self.log_message, f"  {message}")

                    processor.set_callbacks(log_callback=log_callback)

                    # 设置过短片段检测回调（必须在UI线程中调用确认对话框）
                    import threading
                    def short_segments_callback(short_segments_info, total_count):
                        # 使用列表保存结果和事件同步
                        result = ['cancel']  # 默认取消
                        dialog_done = threading.Event()

                        def show_dialog():
                            # 在UI线程中显示对话框
                            user_choice = self.on_short_segments_detected(short_segments_info, total_count)
                            result[0] = user_choice
                            dialog_done.set()  # 通知对话框已完成

                        # 必须在UI线程中执行
                        self.dialog.after(0, show_dialog)

                        # 等待对话框关闭（使用Event同步）
                        dialog_done.wait(timeout=300)  # 最多等待5分钟

                        return result[0]

                    processor.set_short_segments_callback(short_segments_callback)

                    # 执行导入
                    result = processor.import_video_subtitle(
                        video_path, subtitle_path,
                        self.preset_var.get(), self.crf_var.get()
                    )

                    if result.success:
                        if result.skipped:
                            skipped_count += 1
                            self.dialog.after(0, self.log_message, f"  ✓ 已跳过（项目已存在）")
                        else:
                            success_count += 1
                            self.dialog.after(0, self.log_message, f"  ✓ 导入成功")
                    else:
                        failed_count += 1
                        failed_files.append(video_name)
                        error_msg = result.error_message or "未知错误"
                        self.dialog.after(0, self.log_message, f"  ✗ 导入失败: {error_msg}")

                except Exception as e:
                    failed_count += 1
                    failed_files.append(os.path.basename(video_path))
                    self.dialog.after(0, self.log_message, f"  ✗ 处理异常: {e}")

            # 在主线程中显示最终结果
            self.dialog.after(0, self.on_batch_import_complete,
                            total_pairs, success_count, failed_count, skipped_count, failed_files)

        except Exception as e:
            # 在主线程中处理错误
            self.dialog.after(0, self.on_import_error, f"批量导入异常: {e}")

    def import_worker(self, video_path, subtitle_path, preset, crf):
        """导入工作线程"""
        try:
            # 导入视频处理器
            from core.enhanced_video_processor import EnhancedVideoProcessor
            processor = EnhancedVideoProcessor()

            # 设置日志回调，将EnhancedVideoProcessor的日志显示在导入窗口中
            def log_callback(message):
                self.dialog.after(0, self.log_message, message)

            processor.set_callbacks(log_callback=log_callback)

            # 设置过短片段检测回调（必须在UI线程中调用确认对话框）
            import threading
            def short_segments_callback(short_segments_info, total_count):
                # 使用列表保存结果和事件同步
                result = ['cancel']  # 默认取消
                dialog_done = threading.Event()

                def show_dialog():
                    # 在UI线程中显示对话框
                    user_choice = self.on_short_segments_detected(short_segments_info, total_count)
                    result[0] = user_choice
                    dialog_done.set()  # 通知对话框已完成

                # 必须在UI线程中执行
                self.dialog.after(0, show_dialog)

                # 等待对话框关闭（使用Event同步）
                dialog_done.wait(timeout=300)  # 最多等待5分钟

                return result[0]

            processor.set_short_segments_callback(short_segments_callback)

            # 执行导入
            result = processor.import_video_subtitle(video_path, subtitle_path, preset, crf)

            # 在主线程中更新UI
            self.dialog.after(0, self.on_import_complete, result)

        except Exception as e:
            # 在主线程中处理错误
            self.dialog.after(0, self.on_import_error, str(e))

    def on_import_complete(self, result):
        """导入完成回调"""
        from database.models import ImportResult

        if result.skipped:
            self.log_message("项目已存在，已跳过重复导入")
            self.log_message(f"项目名称: {result.project_name}")
        elif result.success:
            self.log_message("导入成功完成！")
            self.log_message(f"项目名称: {result.project_name}")
            self.log_message(f"总片段数: {result.total_segments}")
            self.log_message(f"视频片段: {result.video_success} 成功" +
                           (f", {result.video_failed} 失败" if result.video_failed > 0 else ""))
            self.log_message(f"音频提取: {result.audio_success} 成功" +
                           (f", {result.audio_failed} 失败" if result.audio_failed > 0 else ""))
            self.log_message(f"字幕文件: {result.subtitle_success} 成功" +
                           (f", {result.subtitle_failed} 失败" if result.subtitle_failed > 0 else ""))

            # 格式化耗时
            duration_text = f"{result.duration:.1f} 秒"
            if result.duration >= 60:
                minutes = int(result.duration // 60)
                seconds = int(result.duration % 60)
                duration_text = f"{minutes} 分 {seconds} 秒"
            self.log_message(f"总耗时: {duration_text}")

            if result.audio_failed > 0 or result.video_failed > 0:
                self.log_message("部分文件处理失败，请检查上述日志")
        else:
            self.log_message("导入失败")
            if result.error_message:
                self.log_message(f"错误信息: {result.error_message}")

        # 重置状态
        self.is_importing = False

        # 根据当前模式恢复相应的按钮
        if self.batch_mode_var.get():
            # 批量模式：恢复批量导入按钮
            if hasattr(self, 'batch_import_button'):
                self.batch_import_button.config(text="开始导入", state="normal")
            if hasattr(self, 'batch_cancel_button'):
                self.batch_cancel_button.config(text="关闭", command=self.close_after_import)
        else:
            # 单个文件模式：恢复单个文件导入按钮
            self.import_start_button.config(text="开始导入", state="normal")
            self.import_cancel_button.config(text="关闭", command=self.close_after_import)

        self.enable_controls_after_import()

        # 设置结果（用于主窗口刷新）
        self.result = result

        # 单个文件模式显示结果弹窗
        if not self.batch_mode_var.get():
            self.show_single_import_result(result)

    def on_batch_import_complete(self, total_pairs, success_count, failed_count, skipped_count, failed_files):
        """批量导入完成回调"""
        self.log_message("=" * 50)
        self.log_message("批量导入完成！")
        self.log_message(f"总计: {total_pairs} 个文件对")
        self.log_message(f"成功: {success_count} 个")
        self.log_message(f"跳过: {skipped_count} 个（项目已存在）")
        self.log_message(f"失败: {failed_count} 个")

        if failed_files:
            self.log_message("失败的文件:")
            for file in failed_files:
                self.log_message(f"  - {file}")

        # 重置状态
        self.is_importing = False

        # 根据当前模式恢复相应的按钮
        if self.batch_mode_var.get():
            # 批量模式：恢复批量导入按钮
            if hasattr(self, 'batch_import_button'):
                self.batch_import_button.config(text="开始导入", state="normal")
            if hasattr(self, 'batch_cancel_button'):
                self.batch_cancel_button.config(text="关闭", command=self.close_after_import)
        else:
            # 单个文件模式：恢复单个文件导入按钮
            self.import_start_button.config(text="开始导入", state="normal")
            self.import_cancel_button.config(text="关闭", command=self.close_after_import)

        self.enable_controls_after_import()

        # 显示结果弹窗前，确保主窗口和导入对话框都可见
        try:
            self.parent.deiconify()
            self.parent.update_idletasks()
            self.dialog.deiconify()
            self.dialog.lift()
            self.dialog.update_idletasks()
        except:
            pass

        if failed_count == 0:
            # 全部成功
            if success_count > 0:
                messagebox.showinfo(
                    "批量导入完成",
                    f"批量导入成功完成！\n\n"
                    f"总计: {total_pairs} 个文件对\n"
                    f"成功导入: {success_count} 个\n"
                    f"跳过: {skipped_count} 个（项目已存在）",
                    parent=self.dialog
                )
            else:
                messagebox.showinfo(
                    "批量导入完成",
                    f"批量导入完成！\n\n"
                    f"总计: {total_pairs} 个文件对\n"
                    f"全部跳过: {skipped_count} 个（项目已存在）",
                    parent=self.dialog
                )
        else:
            # 有失败的
            messagebox.showwarning(
                "批量导入完成",
                f"批量导入完成，但有部分失败！\n\n"
                f"总计: {total_pairs} 个文件对\n"
                f"成功: {success_count} 个\n"
                f"跳过: {skipped_count} 个\n"
                f"失败: {failed_count} 个\n\n"
                f"详细信息请查看导入日志。",
                parent=self.dialog
            )

        # messagebox 关闭后，确保导入对话框和主窗口都保持可见（防止被最小化）
        try:
            self.parent.deiconify()
            self.parent.lift()
            self.dialog.deiconify()
            self.dialog.lift()
            self.dialog.focus_force()
        except:
            pass

        # 设置结果（用于主窗口刷新）
        from database.models import ImportResult
        self.result = ImportResult(
            success=success_count > 0 or skipped_count > 0,
            total_segments=success_count + skipped_count,
            duration=0  # 批量导入不计算总时间
        )

    def on_import_error(self, error_message):
        """导入错误回调"""
        self.log_message(f"导入过程中发生错误: {error_message}")

        # 重置状态
        self.is_importing = False

        # 根据当前模式恢复相应的按钮
        if self.batch_mode_var.get():
            # 批量模式：恢复批量导入按钮
            if hasattr(self, 'batch_import_button'):
                self.batch_import_button.config(text="开始导入", state="normal")
            if hasattr(self, 'batch_cancel_button'):
                self.batch_cancel_button.config(text="关闭", command=self.close_after_import)
        else:
            # 单个文件模式：恢复单个文件导入按钮
            self.import_start_button.config(text="开始导入", state="normal")
            self.import_cancel_button.config(text="关闭", command=self.close_after_import)

        self.enable_controls_after_import()

    def close_after_import(self):
        """导入后关闭对话框"""
        if not self.is_importing:
            self.close()

    def on_cancel(self):
        """取消/关闭"""
        # 如果正在导入，需要确认（参考集成合并/导出窗口）
        if self.is_importing:
            if messagebox.askyesno("确认", "正在导入中，确定要取消吗？", parent=self.dialog):
                # 设置取消标志，通知工作线程停止
                self.cancel_flag = True
                self.log_message("用户请求取消导入...")
                # 延迟关闭，给线程一点时间清理
                self.dialog.after(1000, self._force_close)
            return

        # 未导入或已完成，直接关闭
        self.result = None
        self.close()

    def _force_close(self):
        """强制关闭对话框（参考集成合并/导出窗口）"""
        try:
            if self.dialog:
                self.dialog.destroy()
                self.dialog = None
        except:
            pass

    def close(self):
        """关闭对话框"""
        if self.dialog:
            # 非模态窗口不需要 grab_release
            # self.dialog.grab_release()
            self.dialog.destroy()
            self.dialog = None

            # 通知主窗口立即刷新
            if self.on_close_callback:
                self.on_close_callback()

    def set_close_callback(self, callback):
        """设置关闭回调函数"""
        self.on_close_callback = callback

    def setup_drag_drop(self):
        """设置拖拽功能"""
        #self.log_message(f"检查拖拽功能状态: DRAG_DROP_AVAILABLE = {DRAG_DROP_AVAILABLE}")

        if DRAG_DROP_AVAILABLE:
            try:
                # 检查父窗口是否支持拖拽
                # 获取根窗口
                root = self.dialog.winfo_toplevel()
                while root.master:
                    root = root.master.winfo_toplevel()

                #self.log_message(f"根窗口类型: {type(root).__name__}")
                #self.log_message(f"根窗口是否有drop_target_register: {hasattr(root, 'drop_target_register')}")

                # 检查根窗口是否是 TkinterDnD.Tk 类型
                if not hasattr(root, 'drop_target_register'):
                    #self.log_message("拖拽功能不可用 - 主窗口未使用 TkinterDnD.Tk")
                    #self.log_message("提示：请重启应用程序以启用拖拽功能")
                    return

                # 为视频文件输入框设置拖拽支持
                self.video_entry.drop_target_register(DND_FILES)
                self.video_entry.dnd_bind('<<Drop>>', self.on_video_drop)
                #self.log_message("视频输入框拖拽已设置")

                # 为字幕文件输入框设置拖拽支持
                self.subtitle_entry.drop_target_register(DND_FILES)
                self.subtitle_entry.dnd_bind('<<Drop>>', self.on_subtitle_drop)
                #self.log_message("字幕输入框拖拽已设置")

                # 为批量导入目录输入框设置拖拽支持
                self.batch_dir_entry.drop_target_register(DND_FILES)
                self.batch_dir_entry.dnd_bind('<<Drop>>', self.on_batch_dir_drop)
                #self.log_message("批量导入目录拖拽已设置")

                # 添加拖拽提示
                self.setup_drag_hints()

                #self.log_message("拖拽功能已启用 - 可以直接拖拽文件或目录到输入框")
            except Exception as e:
                self.log_message(f"拖拽功能初始化失败: {str(e)}")
                import traceback
                self.log_message(f"详细错误: {traceback.format_exc()}")
        else:
            self.log_message("拖拽功能不可用 - tkinterdnd2 库未正确导入")
            self.log_message("解决方案：")
            self.log_message("1. 确认已安装 tkinterdnd2: pip install tkinterdnd2")
            self.log_message("2. 重启应用程序")

    def setup_drag_hints(self):
        """设置拖拽提示"""
        # 确保输入框状态正常
        self.video_entry.config(state='normal')
        self.subtitle_entry.config(state='normal')
        self.batch_dir_entry.config(state='normal')

        # 设置初始提示文本（当输入框为空时显示）
        if not self.video_path_var.get():
            self.video_entry.insert(0, "拖拽视频文件到此处或点击浏览...")
            self.video_entry.config(foreground='gray')

        if not self.subtitle_path_var.get():
            self.subtitle_entry.insert(0, "拖拽字幕文件到此处或点击浏览...")
            self.subtitle_entry.config(foreground='gray')

        if not self.batch_directory_var.get():
            self.batch_dir_entry.insert(0, "拖拽目录或文件到此处或点击浏览...")
            self.batch_dir_entry.config(foreground='gray')

        # 绑定焦点事件来处理提示文本
        self.video_entry.bind('<FocusIn>', self.on_video_entry_focus_in)
        self.video_entry.bind('<FocusOut>', self.on_video_entry_focus_out)
        self.subtitle_entry.bind('<FocusIn>', self.on_subtitle_entry_focus_in)
        self.subtitle_entry.bind('<FocusOut>', self.on_subtitle_entry_focus_out)
        self.batch_dir_entry.bind('<FocusIn>', self.on_batch_dir_entry_focus_in)
        self.batch_dir_entry.bind('<FocusOut>', self.on_batch_dir_entry_focus_out)

    def update_video_hint(self):
        """更新视频输入框提示"""
        current_value = self.video_entry.get()
        if not current_value or current_value == "拖拽视频文件到此处或点击浏览...":
            self.video_entry.delete(0, tk.END)
            self.video_entry.insert(0, "拖拽视频文件到此处或点击浏览...")
            self.video_entry.config(foreground='gray')
        else:
            self.video_entry.config(foreground='black')

    def update_subtitle_hint(self):
        """更新字幕输入框提示"""
        current_value = self.subtitle_entry.get()
        if not current_value or current_value == "拖拽字幕文件到此处或点击浏览...":
            self.subtitle_entry.delete(0, tk.END)
            self.subtitle_entry.insert(0, "拖拽字幕文件到此处或点击浏览...")
            self.subtitle_entry.config(foreground='gray')
        else:
            self.subtitle_entry.config(foreground='black')

    def on_video_entry_focus_in(self, event):
        """视频输入框获得焦点"""
        current_value = self.video_entry.get()
        if current_value == "拖拽视频文件到此处或点击浏览...":
            self.video_entry.delete(0, tk.END)
            self.video_entry.config(foreground='black')

    def on_video_entry_focus_out(self, event):
        """视频输入框失去焦点"""
        current_value = self.video_entry.get()
        if not current_value:
            self.update_video_hint()
        else:
            # 同步到变量
            self.video_path_var.set(current_value)

    def on_subtitle_entry_focus_in(self, event):
        """字幕输入框获得焦点"""
        current_value = self.subtitle_entry.get()
        if current_value == "拖拽字幕文件到此处或点击浏览...":
            self.subtitle_entry.delete(0, tk.END)
            self.subtitle_entry.config(foreground='black')

    def on_subtitle_entry_focus_out(self, event):
        """字幕输入框失去焦点"""
        current_value = self.subtitle_entry.get()
        if not current_value:
            self.update_subtitle_hint()
        else:
            # 同步到变量
            self.subtitle_path_var.set(current_value)

    def on_batch_dir_entry_focus_in(self, event):
        """批量目录输入框获得焦点"""
        current_value = self.batch_dir_entry.get()
        if current_value == "拖拽目录或文件到此处或点击浏览...":
            self.batch_dir_entry.delete(0, tk.END)
            self.batch_dir_entry.config(foreground='black')

    def on_batch_dir_entry_focus_out(self, event):
        """批量目录输入框失去焦点"""
        current_value = self.batch_dir_entry.get()
        if not current_value:
            self.update_batch_dir_hint()
        else:
            # 同步到变量
            self.batch_directory_var.set(current_value)

    def update_batch_dir_hint(self):
        """更新批量目录输入框提示"""
        current_value = self.batch_dir_entry.get()
        if not current_value or current_value == "拖拽目录或文件到此处或点击浏览...":
            self.batch_dir_entry.delete(0, tk.END)
            self.batch_dir_entry.insert(0, "拖拽目录或文件到此处或点击浏览...")
            self.batch_dir_entry.config(foreground='gray')
        else:
            self.batch_dir_entry.config(foreground='black')

    def parse_drop_files(self, data):
        """解析拖拽的文件数据"""
        try:
            # 处理不同格式的拖拽数据
            if isinstance(data, str):
                files = []

                # 处理包含特殊字符和空格的文件路径
                # tkinterdnd2 通常会用大括号包围包含空格的路径
                if '{' in data and '}' in data:
                    # 处理大括号包围的路径格式: {path1} {path2} 或 {path with spaces}
                    import re
                    # 匹配大括号内的内容
                    matches = re.findall(r'\{([^}]*)\}', data)
                    for match in matches:
                        if match.strip():
                            files.append(match.strip())

                    # 如果没有找到大括号格式，尝试其他方式
                    if not files:
                        # 移除所有大括号后按空格分割
                        cleaned_data = data.replace('{', '').replace('}', '')
                        for item in cleaned_data.split():
                            file_path = item.strip('"').strip("'")
                            if file_path:
                                files.append(file_path)
                else:
                    # 处理没有大括号的简单路径
                    for item in data.split():
                        file_path = item.strip('{}').strip('"').strip("'")
                        if file_path:
                            files.append(file_path)

                # 验证和清理路径
                valid_files = []
                for file_path in files:
                    # 标准化路径
                    normalized_path = os.path.normpath(file_path)
                    if normalized_path and normalized_path != '.':
                        valid_files.append(normalized_path)

                return valid_files

            elif isinstance(data, (list, tuple)):
                return [os.path.normpath(str(f).strip('{}').strip('"').strip("'")) for f in data if str(f).strip()]
            else:
                return []
        except Exception as e:
            self.log_message(f"解析拖拽文件数据时出错: {str(e)}")
            self.log_message(f"原始数据: {repr(data)}")
            return []

    def validate_subtitle_file(self, subtitle_path):
        """校验字幕文件 - 完全照搬外部脚本的严格校验逻辑"""
        try:
            # 检查文件是否存在
            if not os.path.exists(subtitle_path):
                error_msg = f"字幕文件不存在：{subtitle_path}"
                self.log_message(error_msg)
                return False, [error_msg], []

            # 使用外部脚本的严格校验方法 - validate_srt_structure
            try:
                # 尝试以utf-8-sig编码打开（兼容带BOM和不带BOM的UTF-8文件）
                try:
                    with open(subtitle_path, 'r', encoding='utf-8-sig') as f:
                        lines = [(i+1, line.rstrip('\n')) for i, line in enumerate(f.readlines())]
                    self.log_message("使用 UTF-8-sig 编码读取字幕文件")

                    # 检查文件是否为空
                    if not lines or all(not line[1].strip() for line in lines):
                        error_msg = "字幕文件为空或只包含空行"
                        self.log_message(error_msg)
                        return False, [error_msg], []
                except UnicodeDecodeError:
                    # 明确提示文件不是UTF-8系列编码（含带BOM和不带BOM）
                    error_msg = (f"[PAGE] 文件编码错误：请确保输入文件为UTF-8编码（可含BOM），当前文件使用了非UTF-8编码\n"
                               f"解决方案：\n"
                               f"   1. 使用记事本打开文件，点击'另存为'，编码选择'UTF-8'\n"
                               f"   2. 使用VS Code等编辑器，右下角点击编码，选择'通过编码重新打开'，选择正确编码后保存为UTF-8\n"
                               f"   3. 确保文件不是GBK、ANSI等其他编码格式")
                    self.log_message(error_msg)
                    return False, [error_msg], []

                i = 0
                blocks = []  # 保存所有字幕块的完整信息
                block_count = 0
                expected_index = 1  # 期望的序号，用于检查序号连续性
                content_lengths = []  # 记录每个块的内容行数，用于检测单语/双语混合

                while i < len(lines):
                    # 跳过块间空行
                    while i < len(lines) and not lines[i][1].strip():
                        i += 1
                    if i >= len(lines):
                        break

                    # 校验序号行 - 完全照搬外部脚本的严格检查
                    index_line_num, index_line_content = lines[i]
                    if not index_line_content.strip().isdigit():
                        # 详细的序号检测错误提示
                        actual_content = index_line_content.strip()[:50]  # 限制显示长度
                        if not actual_content:
                            error_msg = (f"序号检测错误：第{index_line_num}行为空行，应为字幕块序号（纯数字）\n"
                                       f"解决方案：检查SRT文件格式，确保每个字幕块都以序号开始")
                        else:
                            error_msg = (f"序号检测错误：第{index_line_num}行内容为 '{actual_content}'，应为字幕块序号（纯数字）\n"
                                       f"解决方案：\n"
                                       f"   1. 检查该行内容字幕块是否缺失序号\n"
                                       f"   2. 确保序号为纯数字，且不包含特殊字符\n"
                                       f"   3. 修正序号为纯数字，如：1、2、3...")
                        self.log_message(error_msg)
                        return False, [error_msg], []

                    index = index_line_content.strip()

                    # 检查序号连续性 - 完全照搬外部脚本
                    try:
                        current_index = int(index)
                        if current_index != expected_index:
                            # 提供详细的序号连续性错误提示
                            if current_index < expected_index:
                                error_msg = (f"序号连续性错误：第{index_line_num}行序号{current_index}重复或倒退\n"
                                           f"期望序号：{expected_index}，实际序号：{current_index}\n"
                                           f"解决方案：\n"
                                           f"   1. 检查是否有重复的序号\n"
                                           f"   2. 确保序号按1、2、3...顺序递增\n"
                                           f"   3. 删除重复的字幕块或修正序号")
                            else:
                                error_msg = (f"序号连续性错误：第{index_line_num}行序号{current_index}跳跃过大\n"
                                           f"期望序号：{expected_index}，实际序号：{current_index}\n"
                                           f"解决方案：\n"
                                           f"   1. 检查是否缺少序号{expected_index}到{current_index-1}的字幕块\n"
                                           f"   2. 修正当前序号为{expected_index}\n"
                                           f"   3. 确保序号连续无跳跃")
                            self.log_message(error_msg)
                            return False, [error_msg], []
                        expected_index += 1
                    except ValueError:
                        error_msg = f"序号格式错误：第{index_line_num}行序号 '{index}' 不是有效数字"
                        self.log_message(error_msg)
                        return False, [error_msg], []

                    i += 1

                    # 校验时间轴行 - 完全照搬外部脚本
                    if i >= len(lines):
                        error_msg = (f"时间轴检测错误：序号{index}字幕块后缺少时间轴行\n"
                                   f"解决方案：在序号{index}后添加时间轴行，格式如：00:00:01,000 --> 00:00:03,000")
                        self.log_message(error_msg)
                        return False, [error_msg], []

                    time_line_num, time_line_content = lines[i]
                    if '-->' not in time_line_content:
                        # 详细的时间轴检测错误提示
                        actual_content = time_line_content.strip()[:50]  # 限制显示长度
                        error_msg = (f"时间轴格式错误：第{time_line_num}行内容为 '{actual_content}'，缺少时间轴分隔符 '-->' \n"
                                   f"正确格式：HH:MM:SS,mmm --> HH:MM:SS,mmm\n"
                                   f"示例：00:00:01,000 --> 00:00:03,000\n"
                                   f"当前字幕块：序号{index}")
                        self.log_message(error_msg)
                        return False, [error_msg], []

                    # 进一步验证时间轴格式 - 完全照搬外部脚本
                    time_parts = time_line_content.split('-->')
                    if len(time_parts) != 2:
                        error_msg = (f"时间轴格式错误：第{time_line_num}行时间轴分隔符 '-->' 数量不正确\n"
                                   f"正确格式：开始时间 --> 结束时间\n"
                                   f"当前内容：{time_line_content.strip()}\n"
                                   f"当前字幕块：序号{index}")
                        self.log_message(error_msg)
                        return False, [error_msg], []

                    start_time, end_time = time_parts[0].strip(), time_parts[1].strip()

                    # 验证时间格式 (HH:MM:SS,mmm) - 完全照搬外部脚本
                    time_pattern = r'^\d{2}:\d{2}:\d{2},\d{3}$'
                    if not re.match(time_pattern, start_time):
                        error_msg = (f"开始时间格式错误：第{time_line_num}行开始时间 '{start_time}' 格式不正确\n"
                                   f"正确格式：HH:MM:SS,mmm（如：00:00:01,000）\n"
                                   f"当前字幕块：序号{index}")
                        self.log_message(error_msg)
                        return False, [error_msg], []

                    if not re.match(time_pattern, end_time):
                        error_msg = (f"结束时间格式错误：第{time_line_num}行结束时间 '{end_time}' 格式不正确\n"
                                   f"正确格式：HH:MM:SS,mmm（如：00:00:03,000）\n"
                                   f"当前字幕块：序号{index}")
                        self.log_message(error_msg)
                        return False, [error_msg], []

                    i += 1

                    # 收集内容行 - 完全照搬外部脚本
                    contents = []
                    while i < len(lines) and lines[i][1].strip():
                        contents.append(lines[i][1])
                        i += 1

                    if not contents:
                        error_msg = (f"内容检测错误：序号{index}字幕块的时间轴后缺少字幕内容行\n"
                                   f"解决方案：在时间轴行后添加字幕内容（1-2行文本）")
                        self.log_message(error_msg)
                        return False, [error_msg], []

                    # 检查内容行数是否超过2行 - 照搬外部脚本
                    if len(contents) > 2:
                        error_msg = (f"内容行数错误：序号{index}字幕块包含{len(contents)}行内容，超出支持范围（最多2行）\n"
                                   f"解决方案：检查字幕块间是否缺少空行分隔，或将多行内容合并为1-2行\n"
                                   f"当前内容：{contents[:3]}{'...' if len(contents) > 3 else ''}")
                        self.log_message(error_msg)
                        return False, [error_msg], []

                    # 保存字幕块的完整信息
                    blocks.append({
                        'index': index,
                        'time': time_line_content.strip(),
                        'contents': contents
                    })

                    # 记录当前块的内容行数 - 照搬外部脚本
                    content_lengths.append((index, len(contents)))

                    block_count += 1

                # 检查所有块的内容行数是否一致 - 照搬外部脚本
                if content_lengths:
                    content_counts = {length for _, length in content_lengths}
                    if len(content_counts) > 1:
                        # 统计各行数的字幕块数量（多数原则）
                        from collections import Counter
                        length_counter = Counter([length for _, length in content_lengths])

                        # 找出数量最多的作为基准格式
                        base_length = length_counter.most_common(1)[0][0]  # 最多的行数
                        base_count = length_counter[base_length]  # 基准格式的数量

                        # 找出所有不一致的块
                        inconsistent_blocks_info = []
                        inconsistent_length_counts = {}

                        for idx, length in content_lengths:
                            if length != base_length:
                                inconsistent_blocks_info.append((idx, length))
                                inconsistent_length_counts[length] = inconsistent_length_counts.get(length, 0) + 1

                        if inconsistent_blocks_info:
                            # 在日志窗口显示所有不一致的字幕块详细内容
                            self.log_message("" + "=" * 60)
                            self.log_message("检测到混合的单语/双语字幕块")
                            self.log_message(f"基准格式：{base_length}行内容（{'单语' if base_length == 1 else '双语'}） - 共{base_count}个字幕块")

                            # 显示不一致格式的统计
                            for length, count in sorted(inconsistent_length_counts.items()):
                                self.log_message(f"不一致的格式：{length}行内容 - 共{count}个字幕块")

                            self.log_message(f"发现 {len(inconsistent_blocks_info)} 个不一致的字幕块")
                            self.log_message("" + "=" * 60)
                            self.log_message(f"以下是所有 {len(inconsistent_blocks_info)} 个不一致的字幕块详细信息：")
                            self.log_message("")

                            # 显示所有不一致的字幕块（不限制数量）
                            for i, (block_index, block_length) in enumerate(inconsistent_blocks_info, 1):
                                # 从blocks中找到对应的字幕块
                                block_data = next((b for b in blocks if b['index'] == block_index), None)
                                if block_data:
                                    self.log_message(f"--- 字幕块 #{i} (序号{block_index}, {block_length}行) ---")
                                    self.log_message(f"序号: {block_data['index']}")
                                    self.log_message(f"时间轴: {block_data['time']}")
                                    for j, content in enumerate(block_data['contents'], 1):
                                        self.log_message(f"内容{j}: {content}")
                                    self.log_message("")

                            self.log_message("" + "=" * 60)

                            # 弹出确认对话框（只弹一次）
                            inconsistent_format_text = ", ".join([f"{length}行内容({inconsistent_length_counts[length]}个)"
                                                                 for length in sorted(inconsistent_length_counts.keys())])

                            user_choice = messagebox.askyesno(
                                "字幕块结构不一致",
                                f"检测到混合的单语/双语字幕块！\n\n"
                                f"基准格式：{base_length}行内容（{'单语' if base_length == 1 else '双语'}） - 共{base_count}个字幕块\n"
                                f"不一致的格式：{inconsistent_format_text}\n\n"
                                f"所有{len(inconsistent_blocks_info)}个不一致字幕块的详细内容已显示在下方的日志窗口中，\n"
                                f"请向下滚动查看具体信息。\n\n"
                                f"是否继续导入？",
                                parent=self.dialog
                            )

                            if not user_choice:
                                # 用户选择取消导入
                                error_msg = (f"用户取消导入：字幕块结构不一致\n"
                                           f"基准格式：{base_length}行内容（{'单语' if base_length == 1 else '双语'}） - 共{base_count}个\n"
                                           f"不一致的格式：{inconsistent_format_text}\n"
                                           f"解决方案：统一所有字幕块的格式，要么全部单语（1行），要么全部双语（2行）")
                                self.log_message(error_msg)
                                return False, [error_msg], []
                            else:
                                # 用户选择继续导入
                                self.log_message("用户确认继续导入，忽略字幕块结构不一致问题")
                                self.log_message("")

                    # 确定类型（使用多数原则）
                    from collections import Counter
                    length_counter = Counter([length for _, length in content_lengths])
                    most_common_length = length_counter.most_common(1)[0][0]
                    lang_type_text = '单语' if most_common_length == 1 else '双语'
                    self.log_message(f"字幕文件校验通过，共检测到{block_count}个有效字幕块，类型：{lang_type_text}")
                else:
                    self.log_message(f"字幕文件校验通过，共检测到{block_count}个有效字幕块")

                return True, [], []

            except Exception as e:
                # 外部脚本抛出的详细错误信息
                error_msg = str(e)
                self.log_message(f"字幕文件校验失败：{error_msg}")
                return False, [error_msg], []

        except Exception as e:
            error_msg = f"校验过程中发生错误：{str(e)}"
            self.log_message(error_msg)
            return False, [error_msg], []

    def parse_subtitle_blocks(self, lines):
        """解析字幕文件为字幕块 - 照搬外部脚本的解析逻辑（严格模式）"""
        blocks = []
        i = 0

        while i < len(lines):
            # 跳过空行
            while i < len(lines) and not lines[i].strip():
                i += 1

            if i >= len(lines):
                break

            # 读取序号 - 严格模式：即使错误也要记录
            index_line = lines[i].strip()

            i += 1
            if i >= len(lines):
                # 如果只有序号没有时间轴，也要记录这个错误块
                blocks.append({
                    'index': index_line,
                    'time': '',
                    'content': []
                })
                break

            # 读取时间轴 - 严格模式：即使错误也要记录
            time_line = lines[i].strip()

            i += 1

            # 读取内容行
            content_lines = []
            while i < len(lines) and lines[i].strip():
                content_lines.append(lines[i].strip())
                i += 1

            # 记录所有块，包括错误的块
            blocks.append({
                'index': index_line,
                'time': time_line,
                'content': content_lines
            })

        return blocks

    def on_video_drop(self, event):
        """处理视频文件拖拽事件"""
        try:
            # 解析拖拽的文件路径
            files = self.parse_drop_files(event.data)
            if not files:
                return

            # 支持批量拖拽，处理第一个有效的视频/音频文件
            valid_file = None
            for file_path in files:
                if os.path.exists(file_path) and (FileUtils.is_video_file(file_path) or FileUtils.is_audio_file(file_path)):
                    valid_file = file_path
                    break

            if valid_file:
                # 清除提示文本并设置实际路径
                self.video_entry.delete(0, tk.END)
                self.video_entry.insert(0, valid_file)
                self.video_entry.config(foreground='black')
                self.video_path_var.set(valid_file)
                self.log_message(f"已通过拖拽设置视频文件: {os.path.basename(valid_file)}")

                # 如果拖拽了多个文件，提示用户
                if len(files) > 1:
                    self.log_message(f"检测到 {len(files)} 个文件，已选择第一个有效的视频文件")

                # 自动查找匹配的字幕文件
                self.auto_find_subtitle_silent()
            else:
                # 显示更详细的错误信息
                file_types = [os.path.splitext(f)[1].lower() for f in files if os.path.exists(f)]
                self.log_message(f"拖拽的文件类型: {file_types}")
                self.log_message("请拖拽有效的视频或音频文件")
                self.log_message("支持的视频格式: " + ", ".join(FileUtils.get_video_extensions()))
                self.log_message("支持的音频格式: " + ", ".join(FileUtils.get_audio_extensions()))

        except Exception as e:
            self.log_message(f"处理拖拽视频文件时出错: {str(e)}")
            import traceback
            self.log_message(f"详细错误: {traceback.format_exc()}")

    def on_subtitle_drop(self, event):
        """处理字幕文件拖拽事件"""
        try:
            # 解析拖拽的文件路径
            files = self.parse_drop_files(event.data)
            if not files:
                return

            # 支持批量拖拽，处理第一个有效的字幕文件
            valid_file = None
            for file_path in files:
                if os.path.exists(file_path) and FileUtils.is_subtitle_file(file_path):
                    valid_file = file_path
                    break

            if valid_file:
                # 清除提示文本并设置实际路径
                self.subtitle_entry.delete(0, tk.END)
                self.subtitle_entry.insert(0, valid_file)
                self.subtitle_entry.config(foreground='black')
                self.subtitle_path_var.set(valid_file)
                self.log_message(f"已通过拖拽设置字幕文件: {os.path.basename(valid_file)}")

                # 如果拖拽了多个文件，提示用户
                if len(files) > 1:
                    self.log_message(f"检测到 {len(files)} 个文件，已选择第一个有效的字幕文件")
            else:
                # 显示更详细的错误信息
                file_types = [os.path.splitext(f)[1].lower() for f in files if os.path.exists(f)]
                self.log_message(f"拖拽的文件类型: {file_types}")
                self.log_message("请拖拽有效的字幕文件")
                self.log_message("支持的字幕格式: " + ", ".join(FileUtils.get_subtitle_extensions()))

        except Exception as e:
            self.log_message(f"处理拖拽字幕文件时出错: {str(e)}")
            import traceback
            self.log_message(f"详细错误: {traceback.format_exc()}")

    def on_batch_dir_drop(self, event):
        """处理批量导入目录拖拽事件"""
        try:
            # 解析拖拽的文件路径
            files = self.parse_drop_files(event.data)
            if not files:
                return

            # 查找第一个有效的目录或包含视频文件的目录
            valid_dir = None
            for file_path in files:
                if os.path.isdir(file_path):
                    valid_dir = file_path
                    break
                elif os.path.isfile(file_path):
                    # 如果拖拽的是文件，使用其父目录
                    parent_dir = os.path.dirname(file_path)
                    if os.path.isdir(parent_dir):
                        valid_dir = parent_dir
                        break

            if valid_dir:
                # 标准化路径分隔符
                normalized_path = os.path.normpath(valid_dir)

                # 清除批量目录输入框的提示文字并设置路径
                self.batch_dir_entry.delete(0, tk.END)
                self.batch_dir_entry.insert(0, normalized_path)
                self.batch_dir_entry.config(foreground='black')
                self.batch_directory_var.set(normalized_path)

                self.log_message(f"已通过拖拽设置批量导入目录: {normalized_path}")

                # 如果拖拽了多个项目，提示用户
                if len(files) > 1:
                    self.log_message(f"检测到 {len(files)} 个项目，已选择第一个有效的目录")

                # 自动扫描文件
                self.scan_batch_files()
            else:
                self.log_message("请拖拽有效的目录或文件到此处")
                self.log_message("支持拖拽目录或文件（将使用文件所在目录）")

        except Exception as e:
            self.log_message(f"处理拖拽目录时出错: {str(e)}")
            import traceback
            self.log_message(f"详细错误: {traceback.format_exc()}")

    def on_short_segments_detected(self, short_segments_info: dict, total_count: int) -> str:
        """过短片段检测回调（在UI线程中显示确认对话框）

        Args:
            short_segments_info: 过短片段信息字典
            total_count: 总片段数量

        Returns:
            用户选择：'filter' / 'keep_all' / 'cancel'
        """
        try:
            # 在日志窗口显示所有过短片段的详细内容
            self.log_message("=" * 60)
            self.log_message("检测到过短的字幕片段（<200ms）")
            self.log_message(f"总片段数：{total_count} 个")
            self.log_message(f"过短片段数：{short_segments_info['count']} 个")
            self.log_message(f"占比：{short_segments_info['count'] / total_count * 100:.1f}%")
            self.log_message("=" * 60)
            self.log_message(f"以下是所有 {short_segments_info['count']} 个过短片段的详细信息：")
            self.log_message("")

            # 显示所有过短片段（不限制数量）
            for i, seg_info in enumerate(short_segments_info['segments'], 1):
                self.log_message(f"--- 片段 #{i} (序号{seg_info['index']}, 时长{seg_info['duration']:.3f}秒) ---")
                self.log_message(f"{seg_info['index']}")
                self.log_message(f"{seg_info['time_str']}")
                for line in seg_info['text'].split('\n'):
                    self.log_message(f"{line}")
                self.log_message("")

            self.log_message("=" * 60)

            # 确保主窗口和导入对话框都可见
            try:
                self.parent.deiconify()
                self.parent.update_idletasks()
                self.dialog.deiconify()
                self.dialog.lift()
                self.dialog.update_idletasks()
            except:
                pass

            # 弹出简洁的确认对话框（参考混合格式检测的样式）
            from tkinter import messagebox
            user_choice = messagebox.askyesnocancel(
                "检测到过短片段",
                f"检测到过短的字幕片段（<200ms）！\n\n"
                f"总片段数：{total_count} 个\n"
                f"过短片段数：{short_segments_info['count']} 个\n"
                f"占比：{short_segments_info['count'] / total_count * 100:.1f}%\n\n"
                f"所有{short_segments_info['count']}个过短片段的详细内容已显示在下方的日志窗口中，\n"
                f"请向下滚动查看具体信息。\n\n"
                f"过短片段可能导致视频合并后出现画面静止、编码异常等问题。\n\n"
                f'点击"是"：过滤并导入（推荐，自动移除过短片段）\n'
                f'点击"否"：全部导入（不推荐，保留所有片段）\n'
                f'点击"取消"：取消导入',
                parent=self.dialog
            )

            # 对话框关闭后，确保导入对话框和主窗口都保持可见
            try:
                self.parent.deiconify()
                self.parent.lift()
                self.dialog.deiconify()
                self.dialog.lift()
                self.dialog.focus_force()
            except:
                pass

            # 转换返回值
            if user_choice is True:
                self.log_message("用户选择：过滤并导入（移除过短片段）")
                return 'filter'
            elif user_choice is False:
                self.log_message("用户选择：全部导入（保留所有片段）")
                return 'keep_all'
            else:  # None (取消)
                self.log_message("用户取消导入（检测到过短片段）")
                return 'cancel'

        except Exception as e:
            self.log_message(f"显示过短片段确认对话框时出错: {str(e)}")
            import traceback
            self.log_message(f"详细错误: {traceback.format_exc()}")
            # 出错时默认取消导入
            return 'cancel'

    def show_single_import_result(self, result):
        """显示单个文件导入结果弹窗"""
        try:
            # 显示 messagebox 前，确保主窗口和导入对话框都可见
            try:
                self.parent.deiconify()
                self.parent.update_idletasks()
                self.dialog.deiconify()
                self.dialog.lift()
                self.dialog.update_idletasks()
            except:
                pass

            if result.skipped:
                # 项目已存在，跳过导入
                messagebox.showinfo(
                    "导入跳过",
                    f"项目已存在，已跳过重复导入\n\n项目名称: {result.project_name}",
                    parent=self.dialog
                )
            elif result.success:
                # 导入成功
                success_msg = f"导入成功完成！\n\n"
                success_msg += f"项目名称: {result.project_name}\n"
                success_msg += f"总片段数: {result.total_segments}\n"
                success_msg += f"视频片段: {result.video_success} 成功"
                if result.video_failed > 0:
                    success_msg += f", {result.video_failed} 失败"
                success_msg += f"\n音频提取: {result.audio_success} 成功"
                if result.audio_failed > 0:
                    success_msg += f", {result.audio_failed} 失败"
                success_msg += f"\n字幕文件: {result.subtitle_success} 成功"
                if result.subtitle_failed > 0:
                    success_msg += f", {result.subtitle_failed} 失败"

                # 格式化耗时
                duration_text = f"{result.duration:.1f} 秒"
                if result.duration >= 60:
                    minutes = int(result.duration // 60)
                    seconds = int(result.duration % 60)
                    duration_text = f"{minutes} 分 {seconds} 秒"
                success_msg += f"\n总耗时: {duration_text}"

                if result.audio_failed > 0 or result.video_failed > 0:
                    messagebox.showwarning(
                        "导入部分成功",
                        success_msg + "\n\n部分文件处理失败，请检查日志",
                        parent=self.dialog
                    )
                else:
                    messagebox.showinfo(
                        "导入成功",
                        success_msg,
                        parent=self.dialog
                    )
            else:
                # 导入失败
                error_msg = "导入失败"
                if result.error_message:
                    error_msg += f"\n\n错误信息: {result.error_message}"

                messagebox.showerror(
                    "导入失败",
                    error_msg,
                    parent=self.dialog
                )

            # messagebox 关闭后，确保导入对话框和主窗口都保持可见（防止被最小化）
            try:
                self.parent.deiconify()
                self.parent.lift()
                self.dialog.deiconify()
                self.dialog.lift()
                self.dialog.focus_force()
            except:
                pass

        except Exception as e:
            self.log_message(f"显示结果弹窗时出错: {str(e)}")

    def show(self):
        """显示对话框并返回导入结果"""
        self.dialog.wait_window()
        return self.result
