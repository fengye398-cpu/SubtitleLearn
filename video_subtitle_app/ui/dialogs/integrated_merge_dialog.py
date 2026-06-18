#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
集成合并对话框 - 完全复用外部脚本的合并功能
直接集成 cut_video_audio_subs_v0.3.py 的 standalone_merge 逻辑
"""

import os
import re
import pysrt
import subprocess
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from typing import Optional

from config.settings import app_config
from utils import custom_messagebox

# 导入图标管理器
try:
    from icon_manager import set_window_icon
    ICON_AVAILABLE = True
except ImportError:
    ICON_AVAILABLE = False
    def set_window_icon(window):
        pass


class IntegratedMergeDialog:
    """集成合并对话框 - 直接复用外部脚本的standalone_merge功能"""
    
    def __init__(self, parent):
        self.parent = parent
        self.result = None
        
        # 控制变量
        self.is_processing = False
        self.cancel_flag = False
        
        # 界面变量
        self.input_dir_var = tk.StringVar(value=str(app_config.get('merge.input_dir', '')))
        self.output_dir_var = tk.StringVar(value=str(app_config.get('merge.output_dir', '')))
        self.gap_var = tk.StringVar(value=str(app_config.get('merge.gap', 0.2)))
        self.progress_var = tk.DoubleVar()
        self.progress_percent_var = tk.StringVar(value="0%")
        
        # 按钮引用
        self.start_button = None
        
        self.create_dialog()
    
    def create_dialog(self):
        """创建对话框 - 复用外部脚本的界面布局"""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("片段合并工具 - 集成版")
        self.dialog.geometry("700x500")
        self.dialog.resizable(True, True)
        
        # 不使用模态窗口设置，允许窗口自由最小化和切换
        # self.dialog.transient(self.parent)  # 会隐藏最小化按钮
        # self.dialog.grab_set()  # 会阻止窗口最小化，合并任务时间长，应允许用户最小化窗口

        # 设置窗口图标
        if ICON_AVAILABLE:
            set_window_icon(self.dialog)

        # 居中显示
        self.center_dialog()
        
        # 创建内容
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
        """创建对话框内容 - 复用外部脚本的界面"""
        # 路径设置区域
        self.create_path_settings()
        
        # 参数设置区域
        self.create_parameter_settings()
        
        # 按钮区域
        self.create_buttons()
        
        # 进度条
        self.create_progress_bar()
        
        # 日志区域
        self.create_log_area()
    
    def create_path_settings(self):
        """创建路径设置区域"""
        path_frame = ttk.LabelFrame(self.dialog, text="路径设置", padding=10)
        path_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 输入文件夹路径
        tk.Label(path_frame, text="输入文件夹路径：").grid(row=0, column=0, sticky="e", padx=5, pady=5)
        tk.Entry(path_frame, textvariable=self.input_dir_var, width=50).grid(row=0, column=1, padx=5)
        ttk.Button(path_frame, text="选择", command=self.select_input_dir).grid(row=0, column=2, padx=5)

        # 输出文件夹路径
        tk.Label(path_frame, text="输出文件夹路径：").grid(row=1, column=0, sticky="e", padx=5, pady=5)
        tk.Entry(path_frame, textvariable=self.output_dir_var, width=50).grid(row=1, column=1, padx=5)
        ttk.Button(path_frame, text="选择", command=self.select_output_dir).grid(row=1, column=2, padx=5)
    
    def create_parameter_settings(self):
        """创建参数设置区域 - 改为固定数值0.2纯后端自动运行"""
        # 合并参数固定为0.2，不显示UI
        self.gap_var.set("0.2")
    
    def create_buttons(self):
        """创建按钮区域"""
        button_frame = tk.Frame(self.dialog)
        button_frame.pack(fill=tk.X, padx=10, pady=5)

        self.start_button = ttk.Button(button_frame, text="开始合并", command=self.start_merge, width=12)
        self.start_button.grid(row=0, column=0, pady=5)

        ttk.Button(button_frame, text="输出目录", command=self.open_output, width=12).grid(row=0, column=1, padx=5)
        ttk.Button(button_frame, text="取消", command=self.on_close, width=8).grid(row=0, column=2, padx=5)
    
    def create_progress_bar(self):
        """创建进度条"""
        progress_frame = tk.Frame(self.dialog)
        progress_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(progress_frame, text="进度：").grid(row=0, column=0, sticky="e", padx=5, pady=5)
        progressbar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        progressbar.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        tk.Label(progress_frame, textvariable=self.progress_percent_var, width=5).grid(row=0, column=2, sticky="ew")
        
        # 让进度条自动拉伸
        progress_frame.grid_columnconfigure(1, weight=1)
    
    def create_log_area(self):
        """创建日志区域"""
        log_frame = tk.Frame(self.dialog)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        tk.Label(log_frame, text="日志：").pack(anchor="nw")
        
        # 创建日志框架和滚动条
        log_container = tk.Frame(log_frame)
        log_container.pack(fill=tk.BOTH, expand=True)
        
        # 创建垂直滚动条
        log_scrollbar = tk.Scrollbar(log_container)
        log_scrollbar.pack(side="right", fill="y")
        
        self.log_text = tk.Text(log_container, width=80, height=10, state='disabled', yscrollcommand=log_scrollbar.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        
        log_scrollbar.config(command=self.log_text.yview)
    
    # ========== 事件处理方法 ==========
    
    def select_input_dir(self):
        """选择输入文件夹"""
        folder = filedialog.askdirectory(parent=self.dialog, title="选择包含分段文件的文件夹")
        if folder:
            self.input_dir_var.set(folder)

    def select_output_dir(self):
        """选择输出文件夹"""
        folder = filedialog.askdirectory(parent=self.dialog, title="选择输出文件夹")
        if folder:
            self.output_dir_var.set(folder)
    
    def open_output(self):
        """打开输出文件夹"""
        output_path = self.output_dir_var.get()
        if output_path and os.path.exists(output_path):
            os.startfile(output_path)
        else:
            custom_messagebox.showwarning("警告", "输出文件夹不存在", parent=self.dialog)
    
    def log_message(self, message):
        """添加日志消息"""
        import time
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, f"{time.strftime('%H:%M:%S')} - {message}\n")
        self.log_text.config(state='disabled')
        self.log_text.see(tk.END)
        self.dialog.update()
    
    def update_progress(self, current, total, message=""):
        """更新进度条 - 参考导出窗口的实现"""
        if total > 0:
            progress = (current / total) * 100
            self.progress_var.set(progress)
            self.progress_percent_var.set(f"{progress:.1f}%")

        if message:
            self.log_message(message)

        self.dialog.update()
    
    def start_merge(self):
        """开始合并"""
        if self.is_processing:
            return
        
        # 验证输入
        input_dir = self.input_dir_var.get().strip()
        output_dir = self.output_dir_var.get().strip()

        if not input_dir or not output_dir:
            custom_messagebox.showerror("错误", "请选择输入文件夹和输出文件夹", parent=self.dialog)
            return

        if not os.path.exists(input_dir):
            custom_messagebox.showerror("错误", "输入文件夹不存在", parent=self.dialog)
            return

        try:
            gap = float(self.gap_var.get())
        except ValueError:
            custom_messagebox.showerror("错误", "字幕间隔必须是数字（秒）", parent=self.dialog)
            return
        
        # 保存配置
        app_config.set('merge.input_dir', input_dir)
        app_config.set('merge.output_dir', output_dir)
        app_config.set('merge.gap', gap)
        
        # 在新线程中执行合并
        self.is_processing = True
        self.cancel_flag = False
        self.start_button.config(text="合并中...", state="disabled")
        
        thread = threading.Thread(
            target=self.run_standalone_merge,
            args=(input_dir, output_dir, gap),
            daemon=True
        )
        thread.start()
    
    def run_standalone_merge(self, input_dir, output_dir, gap):
        """运行standalone_merge - 使用更新后的合并逻辑"""
        try:
            # 使用更新后的standalone_merge函数，支持项目名称和文件清理
            from core.merger import standalone_merge

            # 从输入目录名称推断项目名称
            project_name = os.path.basename(input_dir.rstrip('/\\'))
            if not project_name or project_name == '.':
                project_name = "merged_project"

            # 进度回调，同时更新进度条和日志
            total_steps = 4  # 大致步骤：检查文件、合并媒体、合并字幕、清理
            current_step = 0

            def progress_callback(message):
                nonlocal current_step
                # 根据消息内容估算进度
                if "开始合并媒体" in message or "开始合并视频" in message or "开始合并音频" in message:
                    current_step = 1
                elif "开始合并字幕" in message:
                    current_step = 2
                elif "清理" in message:
                    current_step = 3
                elif "合并完成" in message:
                    current_step = 4

                # 更新进度条（update_progress内部会调用log_message，避免重复输出）
                self.update_progress(current_step, total_steps, message)

            success = standalone_merge(input_dir, output_dir, gap, progress_callback, project_name)
            if success:
                # merger.py已经输出"合并完成"，这里只更新进度条到100%
                self.progress_var.set(100)
                self.progress_percent_var.set("100.0%")
                self.dialog.update()
                self.show_success_dialog(output_dir)
            else:
                self.log_message("合并失败！")
                # 注意：这里需要延迟显示，因为是在后台线程中
                self.dialog.after(0, lambda: custom_messagebox.showerror("失败", "合并失败，请检查输入目录与文件格式", parent=self.dialog))
        except Exception as e:
            self.log_message(f"合并过程中发生错误: {e}")
            # 注意：这里需要延迟显示，因为是在后台线程中
            error_msg = str(e)
            self.dialog.after(0, lambda: custom_messagebox.showerror("错误", f"合并发生错误：{error_msg}", parent=self.dialog))
        finally:
            # 重置状态
            self.is_processing = False
            self.start_button.config(text="开始合并", state="normal")



    def get_video_duration(self, path):
        """获取视频时长 - 完全照搬外部脚本"""
        command = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1", path
        ]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            return float(result.stdout.strip())
        except Exception:
            return 0.0

    def format_timedelta(self, td):
        """格式化时间差 - 完全照搬外部脚本"""
        total_seconds = int(td.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        milliseconds = td.microseconds // 1000
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

    def merge_files(self, output_dir, ext, merged_file, progress_callback=None):
        """合并文件 - 完全照搬外部脚本的实现"""
        files = [f for f in os.listdir(output_dir) if f.endswith(ext)]
        def extract_leading_number(filename):
            match = re.match(r"(\d+)", os.path.splitext(filename)[0])
            return int(match.group(1)) if match else 0
        files.sort(key=extract_leading_number)
        if not files:
            return
        list_file = os.path.join(output_dir, f"list_{ext.replace('.', '_')}.txt")
        with open(list_file, "w", encoding="utf-8") as f:
            for file in files:
                f.write(f"file '{os.path.abspath(os.path.join(output_dir, file))}'\n")

        # 根据文件扩展名确定输出格式和编码 - 完全照搬外部脚本
        if ext in ['.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.m4v', '.mpeg', '.mpg', '.ts', '.mts', '.m2ts']:
            # 视频文件
            cmd = [
                "ffmpeg", "-f", "concat", "-safe", "0", "-i", list_file,
                "-c", "copy", merged_file, "-y"
            ]
        else:
            # 音频文件
            cmd = [
                "ffmpeg", "-f", "concat", "-safe", "0", "-i", list_file,
                "-c", "copy", merged_file, "-y"
            ]

        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                      creationflags=subprocess.CREATE_NO_WINDOW)
        os.remove(list_file)
        if progress_callback:
            progress_callback()

    def merge_subtitles(self, output_dir, files, merged_srt, gap=0.2, duration_map=None, progress_callback=None):
        """合并字幕 - 完全照搬外部脚本的实现"""
        import pysrt
        from datetime import timedelta

        def extract_leading_number(filename):
            match = re.match(r"(\d+)", os.path.splitext(filename)[0])
            return int(match.group(1)) if match else 0

        files.sort(key=extract_leading_number)
        merged_subs = []
        current_time = timedelta(seconds=0)
        for i, file in enumerate(files):
            srt_file = os.path.join(output_dir, f"{os.path.splitext(file)[0]}.srt")
            if not os.path.exists(srt_file):
                continue
            subs = pysrt.open(srt_file)
            for sub in subs:
                sub_start = timedelta(hours=sub.start.hours, minutes=sub.start.minutes, seconds=sub.start.seconds, milliseconds=sub.start.milliseconds)
                sub_end = timedelta(hours=sub.end.hours, minutes=sub.end.minutes, seconds=sub.end.seconds, milliseconds=sub.end.milliseconds)
                new_start = current_time + sub_start
                new_end = current_time + sub_end
                if merged_subs:
                    prev_end = merged_subs[-1]['end']
                    if new_start < prev_end + timedelta(seconds=gap):
                        new_start = prev_end + timedelta(seconds=gap)
                        if new_end < new_start:
                            new_end = new_start + timedelta(milliseconds=500)
                merged_subs.append({
                    'index': len(merged_subs) + 1,
                    'start': new_start,
                    'end': new_end,
                    'text': sub.text
                })
            # 用真实时长推进时间轴 - 完全照搬外部脚本
            if duration_map:
                current_time += timedelta(seconds=duration_map[file])
            else:
                v_path = os.path.join(output_dir, file)
                current_time += timedelta(seconds=self.get_video_duration(v_path))
        with open(merged_srt, "w", encoding="utf-8") as f:
            for sub in merged_subs:
                f.write(f"{sub['index']}\n")
                f.write(f"{self.format_timedelta(sub['start'])} --> {self.format_timedelta(sub['end'])}\n")
                f.write(f"{sub['text']}\n\n")
        if progress_callback:
            progress_callback()

    def merge_subtitle_files_with_validation(self, input_folder, srt_files, output_file, gap):
        """合并字幕文件并进行校验 - 照搬导出窗口的逻辑"""
        try:
            from datetime import timedelta
            import pysrt

            merged_subs = []
            current_time = timedelta(seconds=0)
            gap_td = timedelta(seconds=gap)
            subtitle_index = 1

            self.log_message(f"[TARGET] 开始精确字幕合并，gap={gap}s...")

            for srt_file in srt_files:
                srt_path = os.path.join(input_folder, srt_file)
                if not os.path.exists(srt_path):
                    self.log_message(f"[WARN] 字幕文件不存在，跳过: {srt_file}")
                    continue

                try:
                    # [TARGET] 参考导出窗口：支持多种编码读取
                    subs = None
                    try:
                        subs = pysrt.open(srt_path, encoding='utf-8-sig')
                        self.log_message(f"  使用UTF-8-sig编码读取: {srt_file}")
                    except:
                        try:
                            subs = pysrt.open(srt_path, encoding='utf-8')
                            self.log_message(f"  使用UTF-8编码读取: {srt_file}")
                        except:
                            try:
                                subs = pysrt.open(srt_path, encoding='gbk')
                                self.log_message(f"  使用GBK编码读取: {srt_file}")
                            except Exception as e:
                                self.log_message(f"  [ERROR] 无法读取字幕文件: {srt_file} - {e}")
                                continue

                    if not subs:
                        self.log_message(f"  [WARN] 字幕文件为空，跳过: {srt_file}")
                        continue

                    # [TARGET] 参考导出窗口：智能间隔处理
                    for sub in subs:
                        sub_start = timedelta(hours=sub.start.hours, minutes=sub.start.minutes,
                                            seconds=sub.start.seconds, milliseconds=sub.start.milliseconds)
                        sub_end = timedelta(hours=sub.end.hours, minutes=sub.end.minutes,
                                          seconds=sub.end.seconds, milliseconds=sub.end.milliseconds)

                        new_start = current_time + sub_start
                        new_end = current_time + sub_end

                        # [TARGET] 关键改进：智能间隔处理（完全模仿导出窗口）
                        if merged_subs:
                            prev_end = merged_subs[-1]['end']
                            if new_start < prev_end + gap_td:
                                new_start = prev_end + gap_td
                                if new_end < new_start:
                                    new_end = new_start + timedelta(milliseconds=500)

                        merged_subs.append({
                            'index': subtitle_index,
                            'start': new_start,
                            'end': new_end,
                            'text': sub.text
                        })
                        subtitle_index += 1

                    # [TARGET] 参考导出窗口：使用实际媒体文件时长推进时间
                    media_file = srt_file.replace('.srt', '.mp4')
                    if not os.path.exists(os.path.join(input_folder, media_file)):
                        media_file = srt_file.replace('.srt', '.mkv')
                    if not os.path.exists(os.path.join(input_folder, media_file)):
                        media_file = srt_file.replace('.srt', '.mp3')

                    if os.path.exists(os.path.join(input_folder, media_file)):
                        duration = self._probe_duration(os.path.join(input_folder, media_file))
                        current_time += timedelta(seconds=duration) + gap_td
                        self.log_message(f"  文件时长: {duration:.1f}s, 累计时间: {current_time.total_seconds():.1f}s")
                    else:
                        current_time += timedelta(seconds=1.0) + gap_td  # 默认时长
                        self.log_message(f"  使用默认时长: 1.0s")

                except Exception as e:
                    self.log_message(f"  [ERROR] 处理字幕文件失败: {srt_file} - {e}")
                    continue

            # 保存合并后的字幕
            if merged_subs:
                with open(output_file, 'w', encoding='utf-8') as f:
                    for sub in merged_subs:
                        f.write(f"{sub['index']}\n")
                        f.write(f"{self._format_timedelta(sub['start'])} --> {self._format_timedelta(sub['end'])}\n")
                        f.write(f"{sub['text']}\n\n")

                self.log_message(f"[OK] 字幕合并成功: {output_file} ({len(merged_subs)} 条字幕)")
            else:
                self.log_message("[WARN] 没有有效的字幕内容可合并")

                current_step += 1
                #self.update_progress(current_step, total_steps, f"字幕合并完成 ({current_step}/{total_steps})")

            self.log_message("所有文件合并完成！")
            return True

        except Exception as e:
            self.log_message(f"合并过程中发生错误: {e}")
            import traceback
            self.log_message(traceback.format_exc())
            return False

    def on_close(self):
        """关闭对话框"""
        if self.is_processing:
            if messagebox.askyesno("确认", "正在合并中，确定要取消吗？"):
                self.cancel_flag = True
                # 等待一小段时间让处理线程检查取消标志
                self.dialog.after(1000, self._force_close)
            return

        self.dialog.destroy()

    def _force_close(self):
        """强制关闭对话框"""
        self.dialog.destroy()

    def _cleanup_temp_files_only(self, output_folder):
        """只清理临时文件，绝不删除任何输入文件"""
        try:
            self.log_message("🧹 开始清理临时文件...")
            self.log_message("   注意：保留所有输入文件和合并后的文件")

            # 只删除明确的临时文件
            temp_file_patterns = [
                '*.txt',  # concat列表文件
                '*_temp.srt',  # 临时字幕文件
                '*_backup.srt',  # 备份字幕文件
                '*_original.srt',  # 原始字幕文件
                '*.json'  # JSON配置文件
            ]

            cleaned_count = 0
            if os.path.exists(output_folder):
                for file in os.listdir(output_folder):
                    file_path = os.path.join(output_folder, file)
                    if os.path.isfile(file_path):
                        # 只删除明确的临时文件
                        should_delete = False
                        if (file.endswith('.txt') and ('concat' in file.lower() or 'list' in file.lower())):
                            should_delete = True
                        elif file.endswith(('_temp.srt', '_backup.srt', '_original.srt')):
                            should_delete = True
                        elif file.endswith('.json'):
                            should_delete = True

                        if should_delete:
                            try:
                                os.remove(file_path)
                                cleaned_count += 1
                                self.log_message(f"   [DELETE] 已删除临时文件: {file}")
                            except Exception as e:
                                self.log_message(f"   [ERROR] 删除失败 {file}: {e}")

            self.log_message(f"🧹 清理完成: 删除了 {cleaned_count} 个临时文件")
            self.log_message("✅ 所有输入文件和合并后的文件都已保留")

        except Exception as e:
            self.log_message(f"[ERROR] 文件清理过程异常: {e}")
            import traceback
            self.log_message(f"   详细错误: {traceback.format_exc()}")

    def show_success_dialog(self, output_dir):
        """显示合并成功提示窗口 - 参考导出窗口的实现"""
        try:
            # 参考导出窗口的成功弹窗实现
            result = messagebox.askquestion(
                "合并完成",
                f"片段合并完成！\n\n输出目录：{output_dir}\n\n是否打开输出文件夹？",
                icon='question',
                parent=self.dialog
            )

            # 如果用户选择是，则打开文件夹
            if result == 'yes':
                try:
                    import os
                    os.startfile(output_dir)
                except Exception as e:
                    messagebox.showerror("错误", f"无法打开文件夹：{e}", parent=self.dialog)

        except Exception as e:
            # 如果创建弹窗失败，至少显示一个简单的消息框
            messagebox.showinfo("合并完成", f"片段合并完成！\n输出目录：{output_dir}", parent=self.dialog)



    def show(self):
        """显示对话框"""
        self.dialog.wait_window()
        return self.result

    def apply_smart_validation_to_merged_subtitle(self, subtitle_file, output_dir):
        """对合并后的字幕应用智能校验修正 - 参考导出窗口逻辑"""
        try:
            from core.smart_timeline_validator import smart_validator

            if not smart_validator:
                self.log_message("[WARN] 智能校验功能不可用，跳过校验修正")
                return

            self.log_message("[TARGET] 开始智能校验修正...")

            # 创建临时视频文件路径（用于校验）
            # 由于这是合并后的字幕，我们使用一个虚拟的视频路径
            temp_video_path = subtitle_file.replace('.srt', '.mp4')
            if not os.path.exists(temp_video_path):
                # 如果没有对应的视频文件，跳过智能校验
                self.log_message(f"[WARN] 未找到对应的视频文件: {temp_video_path}")
                self.log_message("[WARN] 跳过智能校验修正")
                return

            # 检查字幕文件是否存在
            if not os.path.exists(subtitle_file):
                self.log_message(f"[ERROR] 字幕文件不存在: {subtitle_file}")
                return

            # 对于合并文件，智能校验可能不适用，因为：
            # 1. 合并后的视频和字幕是从多个片段组合而成
            # 2. 时间轴偏差计算可能不准确
            # 3. 合并过程已经确保了时间轴的连续性
            self.log_message("ℹ️ 检测到合并文件，智能校验可能不适用")
            self.log_message("ℹ️ 合并过程已确保时间轴连续性，跳过智能校验")
            self.log_message("[OK] 字幕合并完成，无需额外校验")
            return

            # 以下代码保留但不执行（用于单个文件的智能校验）
            """
            # 创建输出路径
            output_subtitle_path = subtitle_file.replace('.srt', '_validated.srt')

            # 执行智能校验修正
            try:
                validation_result = smart_validator.validate_and_correct(
                    temp_video_path, subtitle_file, output_subtitle_path
                )
            except Exception as validate_error:
                self.log_message(f"[ERROR] 智能校验调用失败: {str(validate_error)}")
                import traceback
                self.log_message(f"详细错误: {traceback.format_exc()}")
                return
            """

            if validation_result.get('success'):
                action = validation_result.get('action', 'unknown')

                if action == 'no_correction_needed':
                    self.log_message("[OK] 字幕时间轴精度良好，无需修正")
                elif action == 'corrected':
                    strategy = validation_result.get('strategy', 'unknown')
                    improvement = validation_result.get('improvement', 0)
                    self.log_message(f"[OK] 智能校验修正完成:")
                    self.log_message(f"   修正策略: {strategy}")
                    self.log_message(f"   改善程度: {improvement:.3f}s")

                    # 如果修正成功，替换原文件
                    if os.path.exists(output_subtitle_path):
                        import shutil
                        shutil.move(output_subtitle_path, subtitle_file)
                        self.log_message(f"[OK] 已应用智能校验修正到: {subtitle_file}")
            else:
                error = validation_result.get('error', '未知错误')
                action = validation_result.get('action', 'unknown')
                message = validation_result.get('message', '')
                deviation = validation_result.get('deviation', 0)

                if action == 'correction_failed':
                    self.log_message(f"[WARN] 智能校验修正失败: {message}")
                    self.log_message(f"   时间轴偏差: {deviation:.3f}秒")
                    self.log_message("   建议: 字幕时间轴偏差较大，可能需要手动调整")
                    self.log_message("   解决方案: 检查原始字幕文件的时间轴是否正确")
                else:
                    self.log_message(f"[ERROR] 智能校验失败: {error}")
                    if message:
                        self.log_message(f"   详细信息: {message}")

                # 输出完整的校验结果用于调试（仅在开发模式下）
                # self.log_message(f"完整校验结果: {validation_result}")

        except Exception as e:
            self.log_message(f"[ERROR] 智能校验过程异常: {str(e)}")
            import traceback
            self.log_message(f"详细错误: {traceback.format_exc()}")

    def _probe_duration(self, media_file):
        """获取媒体文件时长 - 参考导出窗口的实现"""
        try:
            import subprocess
            result = subprocess.run([
                'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                '-of', 'default=nw=1:nk=1', media_file
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
               creationflags=subprocess.CREATE_NO_WINDOW)

            if result.returncode == 0:
                return float(result.stdout.strip())
            else:
                return 1.0
        except:
            return 1.0

    def _format_timedelta(self, td):
        """格式化时间差为SRT格式 - 参考导出窗口的实现"""
        total_seconds = int(td.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        milliseconds = int((td.total_seconds() - total_seconds) * 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
