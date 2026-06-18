"""
字幕提取对话框
使用FFmpeg从MKV视频中提取内封字幕
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


class SubtitleExtractDialog:
    """字幕提取对话框"""

    def __init__(self, parent):
        self.parent = parent

        # 创建模态对话框
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("字幕提取")
        self.dialog.geometry("700x600")
        self.dialog.resizable(True, True)
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # 设置窗口图标
        if ICON_AVAILABLE:
            set_window_icon(self.dialog)

        # 文件路径变量
        self.video_file = ""
        self.output_dir = ""

        # 字幕轨道列表
        self.subtitle_tracks = []  # [(index, codec, language), ...]
        self.track_vars = []  # [BooleanVar(), ...] 复选框状态

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
        title_label = ttk.Label(main_frame, text="字幕提取工具", font=('Arial', 14, 'bold'))
        title_label.pack(pady=(0, 10))

        # 说明文字
        info_text = "[提示] 使用FFmpeg从MKV视频中提取内封字幕（支持多轨道）"
        info_label = ttk.Label(main_frame, text=info_text, foreground="#666666")
        info_label.pack(pady=(0, 10))

        # 视频文件选择
        self.create_video_frame(main_frame)

        # 输出目录选择
        self.create_output_frame(main_frame)

        # 字幕轨道列表
        self.create_tracks_frame(main_frame)

        # 按钮区域
        self.create_button_frame(main_frame)

        # 进度条
        self.create_progress_frame(main_frame)

        # 状态栏
        self.create_status_bar(main_frame)

    def create_video_frame(self, parent):
        """创建视频文件选择区域"""
        frame = ttk.LabelFrame(parent, text="视频文件 (MKV)", padding="10")
        frame.pack(fill=tk.X, pady=(0, 10))

        input_frame = ttk.Frame(frame)
        input_frame.pack(fill=tk.X)

        self.video_var = tk.StringVar()
        self.video_entry = ttk.Entry(input_frame, textvariable=self.video_var)
        self.video_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        ttk.Button(input_frame, text="浏览...", command=self.browse_video_file).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(input_frame, text="检测字幕", command=self.detect_subtitles).pack(side=tk.LEFT)

        # 拖拽支持
        if DRAG_DROP_AVAILABLE:
            self.video_entry.drop_target_register(DND_FILES)
            self.video_entry.dnd_bind('<<Drop>>', self.on_video_drop)

    def create_output_frame(self, parent):
        """创建输出目录选择区域"""
        frame = ttk.LabelFrame(parent, text="输出目录", padding="10")
        frame.pack(fill=tk.X, pady=(0, 10))

        path_frame = ttk.Frame(frame)
        path_frame.pack(fill=tk.X)

        self.output_var = tk.StringVar()
        output_entry = ttk.Entry(path_frame, textvariable=self.output_var, state='readonly')
        output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        ttk.Button(path_frame, text="选择目录", command=self.select_output_dir).pack(side=tk.LEFT)

        # 自动设置输出目录
        self.video_var.trace_add("write", self.auto_set_output)

    def create_tracks_frame(self, parent):
        """创建字幕轨道列表区域"""
        frame = ttk.LabelFrame(parent, text="字幕轨道列表", padding="10")
        frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # 创建滚动区域
        canvas = tk.Canvas(frame, height=150)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        self.tracks_frame = ttk.Frame(canvas)

        self.tracks_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.tracks_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.canvas = canvas

        # 提示标签
        self.tracks_hint_label = ttk.Label(
            self.tracks_frame,
            text="[提示] 请先选择视频文件并点击\"检测字幕\"",
            foreground="gray"
        )
        self.tracks_hint_label.pack(pady=20)

    def create_button_frame(self, parent):
        """创建按钮区域"""
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=10)

        self.start_btn = ttk.Button(frame, text="开始提取", command=self.start_extract, state=tk.DISABLED)
        self.start_btn.pack(side=tk.LEFT, padx=5)

        ttk.Button(frame, text="输出目录", command=self.open_output_folder).pack(side=tk.LEFT, padx=5)

        self.cancel_btn = ttk.Button(frame, text="取消", command=self.cancel_extract, state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT, padx=5)

        ttk.Button(frame, text="关闭", command=self.dialog.destroy).pack(side=tk.LEFT, padx=5)

        # 新增：字幕分离复选框
        self.remove_subs_var = tk.BooleanVar(value=False)
        remove_checkbox = ttk.Checkbutton(
            frame,
            text="字幕分离",
            variable=self.remove_subs_var
        )
        remove_checkbox.pack(side=tk.LEFT, padx=(15, 5))

        # 绑定鼠标悬浮提示
        remove_checkbox.bind('<Enter>', self.on_remove_checkbox_enter)
        remove_checkbox.bind('<Leave>', self.on_remove_checkbox_leave)

        # 绑定复选框值变化事件
        self.remove_subs_var.trace_add('write', self.on_remove_mode_change)

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
            self.video_entry.insert(0, "拖拽MKV视频文件到此处或点击浏览..")
            self.video_entry.config(foreground='gray')

        # 绑定焦点事件
        self.video_entry.bind('<FocusIn>', self.on_video_entry_focus_in)
        self.video_entry.bind('<FocusOut>', self.on_video_entry_focus_out)

    def on_video_entry_focus_in(self, event):
        """视频输入框获得焦点 - 清除占位符"""
        if self.video_entry.get() == "拖拽MKV视频文件到此处或点击浏览..":
            self.video_entry.delete(0, tk.END)
            self.video_entry.config(foreground='black')

    def on_video_entry_focus_out(self, event):
        """视频输入框失去焦点 - 恢复占位符"""
        if not self.video_entry.get():
            self.video_entry.insert(0, "拖拽MKV视频文件到此处或点击浏览..")
            self.video_entry.config(foreground='gray')

    def check_ffmpeg(self):
        """检查FFmpeg是否可用"""
        try:
            result = subprocess.run(['ffmpeg', '-version'],
                                  capture_output=True,
                                  text=True,
                                  timeout=5)
            if result.returncode == 0:
                # 同时检查ffprobe
                result2 = subprocess.run(['ffprobe', '-version'],
                                       capture_output=True,
                                       text=True,
                                       timeout=5)
                if result2.returncode == 0:
                    self.update_status("[成功] FFmpeg和FFprobe已就绪")
                    return True
                else:
                    self.show_ffmpeg_error("FFprobe")
                    return False
            else:
                self.show_ffmpeg_error("FFmpeg")
                return False
        except FileNotFoundError as e:
            tool_name = "FFprobe" if "ffprobe" in str(e) else "FFmpeg"
            self.show_ffmpeg_error(tool_name)
            return False
        except Exception as e:
            self.update_status(f"[错误] FFmpeg检测失败: {e}")
            return False

    def show_ffmpeg_error(self, tool_name="FFmpeg"):
        """显示FFmpeg未安装的错误提示"""
        error_msg = (
            f"[错误] 未检测到{tool_name}\n\n"
            "[提示] 解决方案：\n"
            "1. 下载FFmpeg: https://ffmpeg.org/download.html\n"
            "2. 解压到任意目录\n"
            "3. 将FFmpeg的bin目录添加到系统PATH环境变量\n"
            "4. 重启本程序\n\n"
            "[提示] 验证安装：在命令行运行 'ffmpeg -version' 和 'ffprobe -version'"
        )
        messagebox.showerror(f"{tool_name}未安装", error_msg)
        self.update_status(f"[错误] 请先安装{tool_name}")
        self.start_btn.config(state=tk.DISABLED)

    def browse_video_file(self):
        """浏览选择视频文件"""
        file_path = filedialog.askopenfilename(
            title="选择视频文件",
            filetypes=[
                ("MKV文件", "*.mkv"),
                ("所有文件", "*.*")
            ]
        )
        if file_path:
            # 清除占位符
            if self.video_entry.get() == "拖拽MKV视频文件到此处或点击浏览..":
                self.video_entry.delete(0, tk.END)
                self.video_entry.config(foreground='black')
            self.video_var.set(file_path)
            self.update_status(f"[成功] 已选择视频: {os.path.basename(file_path)}")
            # 自动检测字幕
            self.detect_subtitles()

    def on_video_drop(self, event):
        """处理视频文件拖拽"""
        try:
            file_path = self.parse_drop_file(event.data)
            if file_path:
                ext = os.path.splitext(file_path)[1].lower()
                if ext == '.mkv':
                    # 清除占位符
                    if self.video_entry.get() == "拖拽MKV视频文件到此处或点击浏览..":
                        self.video_entry.delete(0, tk.END)
                        self.video_entry.config(foreground='black')
                    self.video_var.set(file_path)
                    self.update_status(f"[成功] 已拖入视频: {os.path.basename(file_path)}")
                    # 自动检测字幕
                    self.detect_subtitles()
                else:
                    messagebox.showwarning("警告", "[警告] 请拖入MKV视频文件")
        except Exception as e:
            print(f"[字幕提取] 拖拽处理失败: {e}")

    def parse_drop_file(self, data):
        """解析拖拽的文件数据"""
        # 移除大括号和引号
        file_path = data.strip().strip('{}').strip('"').strip("'")
        if os.path.exists(file_path):
            return file_path
        return None

    def select_output_dir(self):
        """选择输出目录"""
        directory = filedialog.askdirectory(title="选择输出目录")
        if directory:
            self.output_dir = directory
            self.output_var.set(directory)
            self.update_status(f"[成功] 输出目录: {directory}")

    def auto_set_output(self, *args):
        """自动设置输出目录"""
        video_path = self.video_var.get().strip()
        # 排除占位符文本
        if video_path and video_path != "拖拽MKV视频文件到此处或点击浏览.." and os.path.exists(video_path):
            # 生成输出目录
            video_dir = os.path.dirname(video_path)
            video_name = os.path.splitext(os.path.basename(video_path))[0]
            output_dir = os.path.join(video_dir, f"{video_name}_subtitles")

            # 如果输出目录为空，自动设置
            if not self.output_var.get():
                self.output_dir = output_dir
                self.output_var.set(output_dir)

    def detect_subtitles(self):
        """检测视频中的字幕轨道"""
        video_path = self.video_var.get().strip()

        # 排除占位符文本
        if not video_path or video_path == "拖拽MKV视频文件到此处或点击浏览..":
            messagebox.showwarning("警告", "[警告] 请先选择视频文件")
            return

        if not os.path.exists(video_path):
            messagebox.showerror("错误", f"[错误] 视频文件不存在:\n{video_path}")
            return

        self.update_status("[提示] 正在检测字幕轨道...")

        try:
            # 使用ffprobe检测字幕轨道
            cmd = [
                'ffprobe',
                '-v', 'error',
                '-select_streams', 's',
                '-show_entries', 'stream=index,codec_name:stream_tags=language,title',
                '-of', 'csv=p=0',
                video_path
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=10
            )

            if result.returncode != 0:
                messagebox.showerror("错误", f"[错误] FFprobe执行失败:\n{result.stderr}")
                self.update_status("[错误] 字幕检测失败")
                return

            # 解析输出
            lines = result.stdout.strip().split('\n')
            self.subtitle_tracks = []

            if not lines or lines[0] == '':
                messagebox.showinfo("提示", "[提示] 未检测到字幕轨道\n\n该视频可能不包含内封字幕")
                self.update_status("[提示] 未检测到字幕轨道")
                self.clear_tracks_display()
                return

            for line in lines:
                if not line.strip():
                    continue

                # 解析格式: stream_index,codec_name,language,title
                # 例如: 2,subrip,eng,English
                parts = line.split(',')
                if len(parts) >= 2:
                    stream_index = parts[0]
                    codec_name = parts[1] if len(parts) > 1 else 'unknown'
                    language = parts[2] if len(parts) > 2 else 'und'
                    title = parts[3] if len(parts) > 3 else ''

                    self.subtitle_tracks.append({
                        'index': stream_index,
                        'codec': codec_name,
                        'language': language,
                        'title': title
                    })

            if self.subtitle_tracks:
                self.display_subtitle_tracks()
                self.update_status(f"[成功] 检测到 {len(self.subtitle_tracks)} 个字幕轨道")
                self.start_btn.config(state=tk.NORMAL)
            else:
                messagebox.showinfo("提示", "[提示] 未检测到有效的字幕轨道")
                self.update_status("[提示] 未检测到字幕轨道")
                self.clear_tracks_display()

        except subprocess.TimeoutExpired:
            messagebox.showerror("错误", "[错误] 字幕检测超时")
            self.update_status("[错误] 检测超时")
        except Exception as e:
            import traceback
            error_msg = f"[错误] 字幕检测失败:\n\n{str(e)}\n\n{traceback.format_exc()}"
            messagebox.showerror("错误", error_msg)
            self.update_status("[错误] 字幕检测失败")

    def clear_tracks_display(self):
        """清空轨道列表显示"""
        # 清空复选框
        for widget in self.tracks_frame.winfo_children():
            widget.destroy()

        self.track_vars = []
        self.start_btn.config(state=tk.DISABLED)

        # 显示提示
        self.tracks_hint_label = ttk.Label(
            self.tracks_frame,
            text="[提示] 该视频不包含字幕轨道",
            foreground="gray"
        )
        self.tracks_hint_label.pack(pady=20)

    def display_subtitle_tracks(self):
        """显示字幕轨道列表"""
        # 清空现有内容
        for widget in self.tracks_frame.winfo_children():
            widget.destroy()

        self.track_vars = []

        # 添加全选/取消全选按钮
        control_frame = ttk.Frame(self.tracks_frame)
        control_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Button(control_frame, text="全选", command=self.select_all_tracks).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(control_frame, text="取消全选", command=self.deselect_all_tracks).pack(side=tk.LEFT)

        # 创建复选框列表
        for i, track in enumerate(self.subtitle_tracks):
            var = tk.BooleanVar(value=True)  # 默认全选
            self.track_vars.append(var)

            # 格式化显示文本
            lang_text = f"{track['language']}" if track['language'] != 'und' else "未知语言"
            title_text = f" - {track['title']}" if track['title'] else ""
            codec_text = f"[{track['codec']}]"

            display_text = f"轨道 {i} (流索引:{track['index']}): {lang_text}{title_text} {codec_text}"

            checkbox = ttk.Checkbutton(
                self.tracks_frame,
                text=display_text,
                variable=var
            )
            checkbox.pack(anchor=tk.W, pady=2)

    def select_all_tracks(self):
        """全选所有轨道"""
        for var in self.track_vars:
            var.set(True)
        self.update_status("[提示] 已全选所有轨道")

    def deselect_all_tracks(self):
        """取消全选所有轨道"""
        for var in self.track_vars:
            var.set(False)
        self.update_status("[提示] 已取消全选")

    def validate_inputs(self):
        """验证输入"""
        video_file = self.video_var.get().strip()
        output_dir = self.output_var.get().strip()

        # 排除占位符文本
        if not video_file or video_file == "拖拽MKV视频文件到此处或点击浏览..":
            messagebox.showwarning("警告", "[警告] 请选择视频文件")
            return False

        if not os.path.exists(video_file):
            messagebox.showerror("错误", f"[错误] 视频文件不存在:\n{video_file}")
            return False

        if not output_dir:
            messagebox.showwarning("警告", "[警告] 请指定输出目录")
            return False

        # 检查是否至少选择了一个轨道
        selected_count = sum(1 for var in self.track_vars if var.get())
        if selected_count == 0:
            messagebox.showwarning("警告", "[警告] 请至少选择一个字幕轨道")
            return False

        return True

    def start_extract(self):
        """开始提取"""
        if not self.validate_inputs():
            return

        # 禁用开始按钮，启用取消按钮
        self.start_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)
        self.is_processing = True

        # 重置进度
        self.progress_var.set(0)
        self.update_status("[提示] 开始提取字幕...")

        # 在新线程中执行提取
        thread = threading.Thread(target=self._extract_thread)
        thread.daemon = True
        thread.start()

    def _extract_thread(self):
        """提取线程"""
        print(f"\n[字幕提取] ========== 提取线程启动 ==========")
        try:
            video_file = self.video_var.get().strip()
            output_dir = self.output_dir
            video_name = os.path.splitext(os.path.basename(video_file))[0]

            print(f"[字幕提取] 视频文件: {video_file}")
            print(f"[字幕提取] 输出目录: {output_dir}")
            print(f"[字幕提取] 视频名称: {video_name}")

            # 创建输出目录
            os.makedirs(output_dir, exist_ok=True)
            print(f"[字幕提取] 输出目录已创建/确认")

            # 获取选中的轨道
            selected_tracks = [
                (i, track) for i, (var, track) in enumerate(zip(self.track_vars, self.subtitle_tracks))
                if var.get()
            ]

            total_tracks = len(selected_tracks)
            success_count = 0
            failed_tracks = []

            print(f"[字幕提取] 选中的轨道数: {total_tracks}")
            print(f"[字幕提取] 轨道详情: {selected_tracks}")

            for track_num, (i, track) in enumerate(selected_tracks, 1):
                if not self.is_processing:
                    print(f"[字幕提取] 用户取消操作")
                    break

                print(f"\n[字幕提取] ========== 开始处理轨道 {track_num}/{total_tracks} ==========")
                print(f"[字幕提取] 轨道索引: {i}")
                print(f"[字幕提取] 轨道信息: {track}")

                # 更新状态
                status_msg = f"[提示] 正在提取轨道 {track_num}/{total_tracks}..."
                print(f"[字幕提取] 更新状态: {status_msg}")
                self.dialog.after(0, lambda msg=status_msg: self.update_status(msg))

                # 根据编码格式确定输出扩展名
                codec = track['codec']
                if codec == 'ass':
                    ext = '.ass'
                    codec_param = 'copy'  # ASS直接复制，保留样式
                elif codec == 'subrip':
                    ext = '.srt'
                    codec_param = 'srt'
                else:
                    # 其他格式默认转换为SRT
                    ext = '.srt'
                    codec_param = 'srt'

                # 生成输出文件名
                lang_suffix = f"_{track['language']}" if track['language'] != 'und' else ""
                output_file = os.path.join(output_dir, f"{video_name}_track{i}{lang_suffix}{ext}")
                print(f"[字幕提取] 输出文件: {output_file} (编码: {codec})")

                # 构建FFmpeg命令
                # 使用 -map 0:s:i 选择第i个字幕流
                cmd = [
                    'ffmpeg',
                    '-i', video_file,
                    '-map', f"0:s:{i}",
                    '-c', codec_param,
                    '-y',  # 覆盖输出文件
                    output_file
                ]
                print(f"[字幕提取] FFmpeg命令: {' '.join(cmd)}")

                try:
                    # 执行FFmpeg命令
                    print(f"[字幕提取] 启动FFmpeg进程...")
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

                    # 等待完成
                    print(f"[字幕提取] 等待FFmpeg完成...")
                    stdout, stderr = self.process.communicate()
                    returncode = self.process.returncode

                    print(f"[字幕提取] FFmpeg返回码: {returncode}")
                    print(f"[字幕提取] FFmpeg stdout: {stdout[:200] if stdout else '(空)'}")
                    print(f"[字幕提取] FFmpeg stderr: {stderr[:500] if stderr else '(空)'}")

                    if returncode == 0:
                        success_count += 1
                        file_size = os.path.getsize(output_file) if os.path.exists(output_file) else 0
                        print(f"[字幕提取] ✓ 成功提取轨道{i}: {output_file} (大小: {file_size} 字节)")
                    else:
                        failed_tracks.append(f"轨道{i}")
                        print(f"[字幕提取] ✗ 提取轨道{i}失败，返回码: {returncode}")

                except Exception as e:
                    import traceback
                    failed_tracks.append(f"轨道{i}")
                    print(f"[字幕提取] ✗ 提取轨道{i}时发生异常: {e}")
                    print(f"[字幕提取] 异常堆栈: {traceback.format_exc()}")

                # 更新进度
                progress = int((track_num / total_tracks) * 100)
                print(f"[字幕提取] 更新进度: {progress}% (轨道 {track_num}/{total_tracks})")

                # 修复lambda闭包问题
                def update_progress(p):
                    self.progress_var.set(p)
                    print(f"[字幕提取] 进度条已更新为: {p}%")

                self.dialog.after(0, lambda p=progress: update_progress(p))

            # 处理完成
            print(f"\n[字幕提取] ========== 所有轨道处理完成 ==========")
            print(f"[字幕提取] is_processing: {self.is_processing}")
            print(f"[字幕提取] success_count: {success_count}")
            print(f"[字幕提取] total_tracks: {total_tracks}")
            print(f"[字幕提取] failed_tracks: {failed_tracks}")

            # 如果勾选了"字幕分离"，清空原视频字幕流
            if self.is_processing and self.remove_subs_var.get() and success_count > 0:
                print(f"\n[字幕提取] ========== 开始字幕分离 ==========")
                self.dialog.after(0, lambda: self.update_status("[提示] 正在生成无字幕视频..."))

                # 生成无字幕视频文件名
                video_dir = os.path.dirname(video_file)
                no_subs_video = os.path.join(video_dir, f"{video_name}_no_subs.mkv")
                print(f"[字幕提取] 无字幕视频路径: {no_subs_video}")

                # 构建FFmpeg命令：只保留视频和音频流
                cmd = [
                    'ffmpeg',
                    '-i', video_file,
                    '-map', '0:v',  # 映射视频流
                    '-map', '0:a',  # 映射音频流
                    '-c', 'copy',
                    '-y',
                    no_subs_video
                ]
                print(f"[字幕提取] FFmpeg命令: {' '.join(cmd)}")

                try:
                    # 执行FFmpeg命令
                    import platform
                    if platform.system() == 'Windows':
                        process = subprocess.Popen(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            encoding='utf-8',
                            errors='ignore',
                            creationflags=subprocess.CREATE_NO_WINDOW
                        )
                    else:
                        process = subprocess.Popen(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            encoding='utf-8',
                            errors='ignore'
                        )

                    stdout, stderr = process.communicate()
                    returncode = process.returncode

                    print(f"[字幕提取] 字幕分离返回码: {returncode}")

                    if returncode == 0:
                        print(f"[字幕提取] ✓ 字幕分离成功: {no_subs_video}")
                        self.dialog.after(0, lambda: self.update_status("[成功] 字幕分离完成"))
                    else:
                        print(f"[字幕提取] ✗ 字幕分离失败，返回码: {returncode}")
                        self.dialog.after(0, lambda: messagebox.showwarning(
                            "警告", f"[警告] 字幕分离失败\n\n字幕已成功提取，但生成无字幕视频失败"))

                except Exception as e:
                    print(f"[字幕提取] ✗ 字幕分离异常: {e}")
                    self.dialog.after(0, lambda: messagebox.showwarning(
                        "警告", f"[警告] 字幕分离失败\n\n字幕已成功提取，但生成无字幕视频时发生错误"))

            if self.is_processing:
                print(f"[字幕提取] 设置进度条为100%")
                self.dialog.after(0, lambda: self.progress_var.set(100))

                if success_count == total_tracks:
                    print(f"[字幕提取] 全部成功，准备显示成功提示")
                    success_msg = f"[成功] 全部提取完成! 共 {success_count} 个轨道"
                    self.dialog.after(0, lambda msg=success_msg: self.update_status(msg))
                    self.dialog.after(0, lambda d=output_dir, s=success_count, t=total_tracks:
                        self.ask_open_output_folder(d, s, t))
                elif success_count > 0:
                    print(f"[字幕提取] 部分成功，准备显示警告")
                    fail_msg = f"成功: {success_count}/{total_tracks}\n失败: {', '.join(failed_tracks)}"
                    warning_msg = f"[警告] 部分提取完成: {success_count}/{total_tracks}"
                    self.dialog.after(0, lambda msg=warning_msg: self.update_status(msg))
                    self.dialog.after(0, lambda m=fail_msg:
                        messagebox.showwarning("部分成功", f"[警告] 字幕提取部分完成\n\n{m}"))
                    self.dialog.after(0, lambda d=output_dir, s=success_count, t=total_tracks:
                        self.ask_open_output_folder(d, s, t))
                else:
                    print(f"[字幕提取] 全部失败，准备显示错误")
                    self.dialog.after(0, lambda: self.update_status("[错误] 提取失败"))
                    self.dialog.after(0, lambda: messagebox.showerror("错误", "[错误] 所有字幕轨道提取失败"))
            else:
                print(f"[字幕提取] 操作已取消")
                self.dialog.after(0, lambda: self.update_status("[提示] 操作已取消"))

        except Exception as e:
            import traceback
            print(f"\n[字幕提取] ========== 发生异常 ==========")
            print(f"[字幕提取] 异常类型: {type(e).__name__}")
            print(f"[字幕提取] 异常信息: {str(e)}")
            print(f"[字幕提取] 异常堆栈:\n{traceback.format_exc()}")

            error_msg = f"[错误] 提取过程发生错误:\n\n{str(e)}\n\n{traceback.format_exc()}"
            self.dialog.after(0, lambda msg=f"[错误] 提取失败: {e}": self.update_status(msg))
            self.dialog.after(0, lambda m=error_msg: messagebox.showerror("错误", m))

        finally:
            print(f"\n[字幕提取] ========== 提取线程结束 ==========")
            print(f"[字幕提取] 恢复按钮状态")
            # 恢复按钮状态
            self.dialog.after(0, lambda: self.start_btn.config(state=tk.NORMAL))
            self.dialog.after(0, lambda: self.cancel_btn.config(state=tk.DISABLED))
            self.is_processing = False
            self.process = None
            print(f"[字幕提取] 线程清理完成")

    def cancel_extract(self):
        """取消提取"""
        if self.is_processing and self.process:
            try:
                self.is_processing = False
                self.process.terminate()
                self.update_status("[提示] 正在取消...")
            except Exception as e:
                print(f"[字幕提取] 取消进程失败: {e}")

    def on_remove_mode_change(self, *args):
        """复选框值变化时更新状态栏"""
        if self.remove_subs_var.get():
            # 勾选状态：字幕分离模式
            self.update_status("[提示] 字幕分离：提取字幕后，生成一个移除所有字幕流的新视频文件")
            print(f"[字幕提取] 模式切换: 字幕分离")
        else:
            # 未勾选状态：仅提取模式（默认）
            self.update_status("[提示] 仅提取模式（默认）：只提取字幕文件，不修改原视频")
            print(f"[字幕提取] 模式切换: 仅提取字幕")

    def on_remove_checkbox_enter(self, event):
        """鼠标悬浮到复选框 - 显示提示"""
        if self.remove_subs_var.get():
            hint = "[提示] 字幕分离：提取字幕后，生成一个移除所有字幕流的新视频文件"
        else:
            hint = "[提示] 仅提取模式（默认）：只提取字幕文件，不修改原视频"
        self.update_status(hint)

    def on_remove_checkbox_leave(self, event):
        """鼠标离开复选框 - 恢复到当前模式状态"""
        # 恢复到当前选择模式的状态信息
        if self.remove_subs_var.get():
            self.update_status("[提示] 字幕分离：提取字幕后，生成一个移除所有字幕流的新视频文件")
        else:
            self.update_status("[提示] 仅提取模式（默认）：只提取字幕文件，不修改原视频")

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
        if not self.output_dir:
            messagebox.showwarning("警告", "[警告] 请先指定输出目录")
            return

        if not os.path.exists(self.output_dir):
            messagebox.showwarning("警告", f"[警告] 输出目录不存在:\n{self.output_dir}")
            return

        try:
            import subprocess
            import platform

            system = platform.system()
            if system == 'Windows':
                subprocess.run(['explorer', os.path.abspath(self.output_dir)])
            elif system == 'Darwin':
                subprocess.run(['open', self.output_dir])
            else:
                subprocess.run(['xdg-open', self.output_dir])

            self.update_status(f"[成功] 已打开输出文件夹: {self.output_dir}")

        except Exception as e:
            messagebox.showerror("错误", f"[错误] 无法打开文件夹: {e}")

    def ask_open_output_folder(self, output_dir, success_count, total_count):
        """询问是否打开输出文件夹"""
        try:
            response = messagebox.askyesno(
                "完成",
                f"[成功] 字幕提取完成！\n\n成功: {success_count}/{total_count} 个轨道\n输出目录:\n{output_dir}\n\n是否打开输出文件夹?",
                icon='info'
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

                    print(f"[字幕提取] 已打开输出文件夹: {output_dir}")

        except Exception as e:
            print(f"[字幕提取] 打开输出文件夹失败: {e}")
