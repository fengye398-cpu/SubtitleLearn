"""
字幕压制对话框
使用FFmpeg将SRT字幕内封到视频文件中
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

# 导入图标管理器
try:
    from icon_manager import set_window_icon
    ICON_AVAILABLE = True
except ImportError:
    ICON_AVAILABLE = False
    def set_window_icon(window):
        pass


class SubtitleBurnDialog:
    """字幕压制对话框"""

    def __init__(self, parent):
        self.parent = parent

        # 创建模态对话框
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("字幕压制")
        self.dialog.geometry("700x500")
        self.dialog.resizable(True, True)
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # 设置窗口图标
        if ICON_AVAILABLE:
            set_window_icon(self.dialog)

        # 文件路径变量
        self.video_file = ""
        self.subtitle_file = ""
        self.output_file = ""
        self.output_dir = ""

        # 处理状态
        self.is_processing = False
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

        # 标题
        title_label = ttk.Label(main_frame, text="字幕压制工具", font=('Arial', 14, 'bold'))
        title_label.pack(pady=(0, 10))

        # 说明文字
        info_text = "[提示] 使用FFmpeg将SRT/ASS字幕内封到视频文件中（输出MKV格式）"
        info_label = ttk.Label(main_frame, text=info_text, foreground="#666666")
        info_label.pack(pady=(0, 10))

        # 视频文件选择
        self.create_video_frame(main_frame)

        # 字幕文件选择
        self.create_subtitle_frame(main_frame)

        # 输出文件选择
        self.create_output_frame(main_frame)

        # 按钮区域
        self.create_button_frame(main_frame)

        # 进度条
        self.create_progress_frame(main_frame)

        # 状态栏
        self.create_status_bar(main_frame)

    def create_video_frame(self, parent):
        """创建视频文件选择区域"""
        frame = ttk.LabelFrame(parent, text="视频文件 (MP4/MKV)", padding="10")
        frame.pack(fill=tk.X, pady=(0, 10))

        input_frame = ttk.Frame(frame)
        input_frame.pack(fill=tk.X)

        self.video_var = tk.StringVar()
        self.video_entry = ttk.Entry(input_frame, textvariable=self.video_var)
        self.video_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        ttk.Button(input_frame, text="浏览...", command=self.browse_video_file).pack(side=tk.LEFT)

        # 拖拽支持
        if DRAG_DROP_AVAILABLE:
            self.video_entry.drop_target_register(DND_FILES)
            self.video_entry.dnd_bind('<<Drop>>', self.on_video_drop)

    def create_subtitle_frame(self, parent):
        """创建字幕文件选择区域"""
        frame = ttk.LabelFrame(parent, text="字幕文件 (SRT/ASS)", padding="10")
        frame.pack(fill=tk.X, pady=(0, 10))

        input_frame = ttk.Frame(frame)
        input_frame.pack(fill=tk.X)

        self.subtitle_var = tk.StringVar()
        self.subtitle_entry = ttk.Entry(input_frame, textvariable=self.subtitle_var)
        self.subtitle_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        ttk.Button(input_frame, text="浏览...", command=self.browse_subtitle_file).pack(side=tk.LEFT)

        # 拖拽支持
        if DRAG_DROP_AVAILABLE:
            self.subtitle_entry.drop_target_register(DND_FILES)
            self.subtitle_entry.dnd_bind('<<Drop>>', self.on_subtitle_drop)

    def create_output_frame(self, parent):
        """创建输出目录区域"""
        frame = ttk.LabelFrame(parent, text="输出目录", padding="10")
        frame.pack(fill=tk.X, pady=(0, 10))

        input_frame = ttk.Frame(frame)
        input_frame.pack(fill=tk.X)

        self.output_var = tk.StringVar()
        self.output_entry = ttk.Entry(input_frame, textvariable=self.output_var, state='readonly')
        self.output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        ttk.Button(input_frame, text="选择目录", command=self.select_output_dir).pack(side=tk.LEFT)

        # 自动设置输出路径
        self.video_var.trace_add("write", self.auto_set_output)
        self.subtitle_var.trace_add("write", self.auto_set_output)

    def create_button_frame(self, parent):
        """创建按钮区域"""
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=10)

        self.start_btn = ttk.Button(frame, text="开始压制", command=self.start_burn)
        self.start_btn.pack(side=tk.LEFT, padx=5)

        ttk.Button(frame, text="输出目录", command=self.open_output_folder).pack(side=tk.LEFT, padx=5)

        self.cancel_btn = ttk.Button(frame, text="取消", command=self.cancel_burn, state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT, padx=5)

        ttk.Button(frame, text="关闭", command=self.dialog.destroy).pack(side=tk.LEFT, padx=5)

        # 新增：替换模式复选框
        self.replace_mode_var = tk.BooleanVar(value=False)  # False=追加模式(默认)
        replace_checkbox = ttk.Checkbutton(
            frame,
            text="替换模式",
            variable=self.replace_mode_var
        )
        replace_checkbox.pack(side=tk.LEFT, padx=(15, 5))

        # 绑定鼠标悬浮提示
        replace_checkbox.bind('<Enter>', self.on_replace_checkbox_enter)
        replace_checkbox.bind('<Leave>', self.on_replace_checkbox_leave)

        # 绑定复选框值变化事件
        self.replace_mode_var.trace_add('write', self.on_replace_mode_change)

    def create_progress_frame(self, parent):
        """创建进度条区域"""
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=5)

        ttk.Label(frame, text="处理进度:").pack(side=tk.LEFT)

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

    def create_status_bar(self, parent):
        """创建状态栏"""
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X)

        self.status_var = tk.StringVar(value="就绪")
        self.status_label = ttk.Label(frame, textvariable=self.status_var, foreground="gray")
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def setup_placeholder_hints(self):
        """设置占位符提示"""
        # 设置初始提示文本
        if not self.video_var.get():
            self.video_entry.insert(0, "拖拽视频文件到此处或点击浏览..")
            self.video_entry.config(foreground='gray')

        if not self.subtitle_var.get():
            self.subtitle_entry.insert(0, "拖拽字幕文件到此处或点击浏览..")
            self.subtitle_entry.config(foreground='gray')

        # 绑定焦点事件
        self.video_entry.bind('<FocusIn>', self.on_video_entry_focus_in)
        self.video_entry.bind('<FocusOut>', self.on_video_entry_focus_out)
        self.subtitle_entry.bind('<FocusIn>', self.on_subtitle_entry_focus_in)
        self.subtitle_entry.bind('<FocusOut>', self.on_subtitle_entry_focus_out)

    def on_video_entry_focus_in(self, event):
        """视频输入框获得焦点 - 清除占位符"""
        if self.video_entry.get() == "拖拽视频文件到此处或点击浏览..":
            self.video_entry.delete(0, tk.END)
            self.video_entry.config(foreground='black')

    def on_video_entry_focus_out(self, event):
        """视频输入框失去焦点 - 恢复占位符"""
        if not self.video_entry.get():
            self.video_entry.insert(0, "拖拽视频文件到此处或点击浏览..")
            self.video_entry.config(foreground='gray')

    def on_subtitle_entry_focus_in(self, event):
        """字幕输入框获得焦点 - 清除占位符"""
        if self.subtitle_entry.get() == "拖拽字幕文件到此处或点击浏览..":
            self.subtitle_entry.delete(0, tk.END)
            self.subtitle_entry.config(foreground='black')

    def on_subtitle_entry_focus_out(self, event):
        """字幕输入框失去焦点 - 恢复占位符"""
        if not self.subtitle_entry.get():
            self.subtitle_entry.insert(0, "拖拽字幕文件到此处或点击浏览..")
            self.subtitle_entry.config(foreground='gray')

    def check_ffmpeg(self):
        """检查FFmpeg是否可用"""
        try:
            result = subprocess.run(['ffmpeg', '-version'],
                                  capture_output=True,
                                  text=True,
                                  timeout=5)
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
        messagebox.showerror("FFmpeg未安装", error_msg)
        self.update_status("[错误] 请先安装FFmpeg")
        self.start_btn.config(state=tk.DISABLED)

    def browse_video_file(self):
        """浏览选择视频文件"""
        file_path = filedialog.askopenfilename(
            title="选择视频文件",
            filetypes=[
                ("视频文件", "*.mp4 *.mkv"),
                ("MP4文件", "*.mp4"),
                ("MKV文件", "*.mkv"),
                ("所有文件", "*.*")
            ]
        )
        if file_path:
            # 清除占位符
            if self.video_entry.get() == "拖拽视频文件到此处或点击浏览..":
                self.video_entry.delete(0, tk.END)
                self.video_entry.config(foreground='black')
            self.video_var.set(file_path)
            self.update_status(f"[成功] 已选择视频: {os.path.basename(file_path)}")

    def browse_subtitle_file(self):
        """浏览选择字幕文件"""
        file_path = filedialog.askopenfilename(
            title="选择字幕文件",
            filetypes=[
                ("字幕文件", "*.srt *.ass"),
                ("SRT文件", "*.srt"),
                ("ASS文件", "*.ass"),
                ("所有文件", "*.*")
            ]
        )
        if file_path:
            # 清除占位符
            if self.subtitle_entry.get() == "拖拽字幕文件到此处或点击浏览..":
                self.subtitle_entry.delete(0, tk.END)
                self.subtitle_entry.config(foreground='black')
            self.subtitle_var.set(file_path)
            self.update_status(f"[成功] 已选择字幕: {os.path.basename(file_path)}")

    def select_output_dir(self):
        """选择输出目录"""
        directory = filedialog.askdirectory(title="选择输出目录")
        if directory:
            # 更新输出目录（这将触发auto_set_output重新设置输出文件名）
            self.output_var.set(directory)
            self.update_status(f"[成功] 已选择输出目录: {directory}")

    def browse_output_file(self):
        """浏览选择输出文件"""
        file_path = filedialog.asksaveasfilename(
            title="保存输出文件",
            defaultextension=".mkv",
            filetypes=[
                ("MKV文件", "*.mkv"),
                ("所有文件", "*.*")
            ]
        )
        if file_path:
            self.output_var.set(file_path)
            self.update_status(f"[成功] 已设置输出: {os.path.basename(file_path)}")

    def on_video_drop(self, event):
        """处理视频文件拖拽"""
        try:
            file_path = self.parse_drop_file(event.data)
            if file_path:
                ext = os.path.splitext(file_path)[1].lower()
                if ext in ['.mp4', '.mkv']:
                    # 清除占位符
                    if self.video_entry.get() == "拖拽视频文件到此处或点击浏览..":
                        self.video_entry.delete(0, tk.END)
                        self.video_entry.config(foreground='black')
                    self.video_var.set(file_path)
                    self.update_status(f"[成功] 已拖入视频: {os.path.basename(file_path)}")
                else:
                    messagebox.showwarning("警告", "[警告] 请拖入MP4或MKV视频文件")
        except Exception as e:
            print(f"[字幕压制] 拖拽处理失败: {e}")

    def on_subtitle_drop(self, event):
        """处理字幕文件拖拽"""
        try:
            file_path = self.parse_drop_file(event.data)
            if file_path:
                ext = os.path.splitext(file_path)[1].lower()
                if ext in ['.srt', '.ass']:
                    # 清除占位符
                    if self.subtitle_entry.get() == "拖拽字幕文件到此处或点击浏览..":
                        self.subtitle_entry.delete(0, tk.END)
                        self.subtitle_entry.config(foreground='black')
                    self.subtitle_var.set(file_path)
                    self.update_status(f"[成功] 已拖入字幕: {os.path.basename(file_path)}")
                else:
                    messagebox.showwarning("警告", "[警告] 请拖入SRT或ASS字幕文件")
        except Exception as e:
            print(f"[字幕压制] 拖拽处理失败: {e}")

    def parse_drop_file(self, data):
        """解析拖拽的文件数据"""
        # 移除大括号和引号
        file_path = data.strip().strip('{}').strip('"').strip("'")
        if os.path.exists(file_path):
            return file_path
        return None

    def auto_set_output(self, *args):
        """自动设置输出目录路径"""
        video_path = self.video_var.get().strip()
        # 排除占位符文本
        if video_path and video_path != "拖拽视频文件到此处或点击浏览.." and os.path.exists(video_path):
            # 自动设置输出目录为视频所在目录
            video_dir = os.path.dirname(video_path)

            if not self.output_var.get():
                # 设置输出目录路径（不是具体文件）
                self.output_var.set(video_dir)
                print(f"[字幕压制] 自动设置输出目录: {video_dir}")

            # 如果已设置了目录，检查是否需要更新防覆盖序号
            elif self.output_var.get() != video_dir:
                self.output_var.set(video_dir)
                print(f"[字幕压制] 更新输出目录: {video_dir}")

    def validate_inputs(self):
        """验证输入"""
        video_file = self.video_var.get().strip()
        subtitle_file = self.subtitle_var.get().strip()
        output_dir = self.output_var.get().strip()

        # 排除占位符文本
        if not video_file or video_file == "拖拽视频文件到此处或点击浏览..":
            messagebox.showwarning("警告", "[警告] 请选择视频文件")
            return False

        if not os.path.exists(video_file):
            messagebox.showerror("错误", f"[错误] 视频文件不存在:\n{video_file}")
            return False

        # 排除占位符文本
        if not subtitle_file or subtitle_file == "拖拽字幕文件到此处或点击浏览..":
            messagebox.showwarning("警告", "[警告] 请选择字幕文件")
            return False

        if not os.path.exists(subtitle_file):
            messagebox.showerror("错误", f"[错误] 字幕文件不存在:\n{subtitle_file}")
            return False

        if not output_dir:
            messagebox.showwarning("警告", "[警告] 请选择输出目录")
            return False

        # 检查输出目录是否存在
        if not os.path.exists(output_dir):
            messagebox.showerror("错误", f"[错误] 输出目录不存在:\n{output_dir}")
            return False

        return True

    def start_burn(self):
        """开始压制"""
        if not self.validate_inputs():
            return

        # 禁用开始按钮，启用取消按钮
        self.start_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)
        self.is_processing = True

        # 重置进度
        self.progress_var.set(0)
        self.update_status("[提示] 开始压制字幕...")

        # 在新线程中执行压制
        thread = threading.Thread(target=self._burn_thread)
        thread.daemon = True
        thread.start()

    def on_replace_mode_change(self, *args):
        """复选框值变化时更新状态栏"""
        if self.replace_mode_var.get():
            # 勾选状态：替换模式
            self.update_status("[提示] 替换模式：将移除视频中的所有原有字幕轨道，只保留新压制的字幕")
            print(f"[字幕压制] 模式切换: 替换原有字幕")
        else:
            # 未勾选状态：追加模式（默认）
            self.update_status("[提示] 追加模式（默认）：保留视频中的原有字幕轨道，新增1个字幕轨道")
            print(f"[字幕压制] 模式切换: 追加字幕轨道（保留原有字幕）")

    def on_replace_checkbox_enter(self, event):
        """鼠标悬浮到复选框 - 显示提示"""
        if self.replace_mode_var.get():
            hint = "[提示] 替换模式：将移除视频中的所有原有字幕轨道，只保留新压制的字幕"
        else:
            hint = "[提示] 追加模式（默认）：保留视频中的原有字幕轨道，新增1个字幕轨道"
        self.update_status(hint)

    def on_replace_checkbox_leave(self, event):
        """鼠标离开复选框 - 恢复到当前模式状态"""
        # 恢复到当前选择模式的状态信息
        if self.replace_mode_var.get():
            self.update_status("[提示] 替换模式：将移除视频中的所有原有字幕轨道，只保留新压制的字幕")
        else:
            self.update_status("[提示] 追加模式（默认）：保留视频中的原有字幕轨道，新增1个字幕轨道")

    def _burn_thread(self):
        """压制线程"""
        try:
            video_file = self.video_var.get().strip()
            subtitle_file = self.subtitle_var.get().strip()
            output_dir = self.output_var.get().strip()

            # 生成完整的输出文件路径（带防覆盖逻辑）
            video_name = os.path.splitext(os.path.basename(video_file))[0]
            base_path = os.path.join(output_dir, f"{video_name}_subtitled.mkv")
            output_file = base_path

            # 防覆盖检查：如果文件存在则自动递增序号
            counter = 1
            while os.path.exists(output_file):
                output_file = os.path.join(output_dir, f"{video_name}_subtitled_{counter}.mkv")
                counter += 1

            print(f"[字幕压制] 生成输出文件路径: {output_file}")

            # 获取压制模式
            replace_mode = self.replace_mode_var.get()

            # 构建FFmpeg命令
            if replace_mode:
                # 替换模式：移除所有原字幕，只保留新字幕
                cmd = [
                    'ffmpeg',
                    '-i', video_file,
                    '-i', subtitle_file,
                    '-map', '0:v',        # 映射视频流
                    '-map', '0:a',        # 映射音频流
                    '-map', '1:s',        # 映射新字幕流（不映射原字幕）
                    '-c', 'copy',
                    '-y',  # 覆盖输出文件
                    output_file
                ]
                print(f"[字幕压制] 使用模式: 替换原有字幕")
            else:
                # 追加模式（默认）：保留原字幕，追加新字幕
                cmd = [
                    'ffmpeg',
                    '-i', video_file,
                    '-i', subtitle_file,
                    '-map', '0',          # 保留输入0的所有流(视频/音频/原字幕)
                    '-map', '1:s',        # 添加输入1的字幕流
                    '-c', 'copy',
                    '-y',  # 覆盖输出文件
                    output_file
                ]
                print(f"[字幕压制] 使用模式: 追加字幕轨道（保留原有字幕）")

            print(f"[字幕压制] FFmpeg命令: {' '.join(cmd)}")

            # 执行FFmpeg命令
            # Windows: 添加 CREATE_NO_WINDOW 标志隐藏CMD窗口
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

            # 读取FFmpeg输出以显示进度
            for line in self.process.stderr:
                if not self.is_processing:
                    break

                # 解析进度信息
                # FFmpeg输出格式: frame=  123 fps= 45 q=-1.0 size=    1234kB time=00:01:23.45 bitrate= 123.4kbits/s speed=1.23x
                if 'time=' in line:
                    # 简单进度显示（由于无法准确获取视频总时长，使用模糊进度）
                    self.dialog.after(0, lambda: self.update_status("[提示] 正在处理..."))
                    self.dialog.after(0, lambda: self.progress_var.set(50))

            # 等待进程完成
            self.process.wait()

            # 检查返回码
            if self.process.returncode == 0 and self.is_processing:
                self.dialog.after(0, lambda: self.progress_var.set(100))
                self.dialog.after(0, lambda: self.update_status("[成功] 字幕压制完成！"))
                self.dialog.after(0, lambda: self.ask_open_output_folder(output_file))
            elif not self.is_processing:
                self.dialog.after(0, lambda: self.update_status("[提示] 操作已取消"))
            else:
                error_output = self.process.stderr.read() if self.process.stderr else ""
                self.dialog.after(0, lambda: self.update_status("[错误] 压制失败"))
                self.dialog.after(0, lambda: messagebox.showerror("错误", f"[错误] FFmpeg执行失败\n\n{error_output[:500]}"))

        except Exception as e:
            self.dialog.after(0, lambda: self.update_status(f"[错误] 处理失败: {e}"))
            self.dialog.after(0, lambda: messagebox.showerror("错误", f"[错误] 处理过程中发生错误:\n{e}"))

        finally:
            # 恢复按钮状态
            self.dialog.after(0, lambda: self.start_btn.config(state=tk.NORMAL))
            self.dialog.after(0, lambda: self.cancel_btn.config(state=tk.DISABLED))
            self.is_processing = False
            self.process = None

    def cancel_burn(self):
        """取消压制"""
        if self.is_processing and self.process:
            try:
                self.is_processing = False
                self.process.terminate()
                self.update_status("[提示] 正在取消...")
            except Exception as e:
                print(f"[字幕压制] 取消进程失败: {e}")

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
            dialog_width = self.dialog.winfo_reqwidth()
            dialog_height = self.dialog.winfo_reqheight()

            # 计算居中位置
            x = parent_x + (parent_width - dialog_width) // 2
            y = parent_y + (parent_height - dialog_height) // 2

            self.dialog.geometry(f"+{x}+{y}")

        except Exception as e:
            print(f"居中对话框失败: {e}")

    def open_output_folder(self):
        """打开输出文件夹"""
        output_dir = self.output_var.get().strip()

        if not output_dir:
            messagebox.showwarning("警告", "[警告] 请先选择输出目录")
            return

        if not os.path.exists(output_dir):
            messagebox.showwarning("警告", f"[警告] 输出目录不存在:\n{output_dir}")
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
            messagebox.showerror("错误", f"[错误] 无法打开文件夹: {e}")

    def ask_open_output_folder(self, output_file):
        """询问是否打开输出文件夹"""
        try:
            response = messagebox.askyesno(
                "完成",
                f"[成功] 字幕压制完成！\n\n输出文件:\n{output_file}\n\n是否打开输出文件夹?",
                icon='info'
            )

            if response:
                output_dir = os.path.dirname(output_file)
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

                    print(f"[字幕压制] 已打开输出文件夹: {output_dir}")

        except Exception as e:
            print(f"[字幕压制] 打开输出文件夹失败: {e}")
