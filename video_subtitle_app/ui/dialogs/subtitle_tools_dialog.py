"""
字幕功能对话框
提供字幕处理工具:
1. 双语字幕分离
2. 单语字幕合并
3. 提取纯文本
4. 提取时间轴
5. 双语行互换
6. SRT⇄ASS格式转换
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
from pathlib import Path
from typing import Optional, List, Tuple
import pysrt
import re

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


class SubtitleToolsDialog:
    """字幕功能对话框"""

    def __init__(self, parent):
        self.parent = parent

        # 创建对话框
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("字幕功能")
        self.dialog.geometry("800x600")
        self.dialog.resizable(True, True)
        self.dialog.transient(parent)

        # 设置窗口图标
        if ICON_AVAILABLE:
            set_window_icon(self.dialog)

        # 文件路径变量
        self.input_files = []  # 输入文件列表
        self.output_dir = ""   # 输出目录

        # 创建UI
        self.setup_ui()

        # 绑定拖拽事件
        if DRAG_DROP_AVAILABLE:
            self.setup_drag_drop()

        # 居中显示
        self.center_dialog()

    def setup_ui(self):
        """设置用户界面"""
        # 主框架
        main_frame = ttk.Frame(self.dialog, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 标题
        title_label = ttk.Label(main_frame, text="字幕处理工具", font=('Arial', 14, 'bold'))
        title_label.pack(pady=(0, 10))

        # 输入文件区域
        self.create_input_frame(main_frame)

        # 输出目录区域
        self.create_output_frame(main_frame)

        # 功能按钮区域
        self.create_function_buttons(main_frame)

        # 状态栏
        self.create_status_bar(main_frame)

    def create_input_frame(self, parent):
        """创建输入文件区域"""
        frame = ttk.LabelFrame(parent, text="输入文件（支持拖拽）", padding="10")
        frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # 文件列表框架
        list_frame = ttk.Frame(frame)
        list_frame.pack(fill=tk.BOTH, expand=True)

        # 创建列表框和滚动条
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.input_listbox = tk.Listbox(
            list_frame,
            height=8,
            yscrollcommand=scrollbar.set,
            selectmode=tk.EXTENDED
        )
        self.input_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.input_listbox.yview)

        # 按钮框架
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(5, 0))

        ttk.Button(btn_frame, text="添加文件", command=self.add_input_files).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="删除选中", command=self.delete_selected_files).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="清空列表", command=self.clear_input_files).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="输出目录", command=self.open_output_folder).pack(side=tk.LEFT, padx=(0, 5))

        # 绑定快捷键
        self.input_listbox.bind("<Control-a>", self.select_all_files)
        self.input_listbox.bind("<Escape>", self.deselect_all_files)
        self.input_listbox.bind("<Delete>", self.delete_selected_files_by_key)

        # 拖拽提示
        if DRAG_DROP_AVAILABLE:
            hint_label = ttk.Label(btn_frame, text="[提示] 支持拖拽文件到列表", foreground="gray", font=('', 8))
            hint_label.pack(side=tk.RIGHT)

    def create_output_frame(self, parent):
        """创建输出目录区域"""
        frame = ttk.LabelFrame(parent, text="输出目录", padding="10")
        frame.pack(fill=tk.X, pady=(0, 10))

        # 输出路径显示框架
        path_frame = ttk.Frame(frame)
        path_frame.pack(fill=tk.X)

        self.output_var = tk.StringVar()
        output_entry = ttk.Entry(path_frame, textvariable=self.output_var, state='readonly')
        output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        ttk.Button(path_frame, text="选择目录", command=self.select_output_dir).pack(side=tk.LEFT)

    def create_function_buttons(self, parent):
        """创建功能按钮区域"""
        frame = ttk.LabelFrame(parent, text="字幕处理功能", padding="10")
        frame.pack(fill=tk.X, pady=(0, 10))

        # 第一行按钮 (4个)
        row1 = ttk.Frame(frame)
        row1.pack(fill=tk.X, pady=(0, 5))

        ttk.Button(row1, text="双语分离",
                  command=self.split_bilingual).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(row1, text="单语合并",
                  command=self.merge_monolingual).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(row1, text="提取纯文本",
                  command=self.extract_text).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(row1, text="字幕压制",
                  command=self.open_burn_dialog).pack(side=tk.LEFT)

        # 第二行按钮 (4个)
        row2 = ttk.Frame(frame)
        row2.pack(fill=tk.X)

        ttk.Button(row2, text="提取时间轴",
                  command=self.extract_timeline).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(row2, text="双语互换",
                  command=self.swap_bilingual).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(row2, text="SRT⇄ASS",
                  command=self.convert_format).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(row2, text="字幕提取",
                  command=self.open_extract_dialog).pack(side=tk.LEFT)

    def create_status_bar(self, parent):
        """创建状态栏"""
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X)

        self.status_var = tk.StringVar(value="就绪")
        self.status_label = ttk.Label(frame, textvariable=self.status_var, foreground="gray")
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def setup_drag_drop(self):
        """设置拖拽功能"""
        if not DRAG_DROP_AVAILABLE:
            return

        try:
            # 注册拖拽目标
            self.input_listbox.drop_target_register(DND_FILES)
            self.input_listbox.dnd_bind('<<Drop>>', self.on_drop)
            print("[字幕功能] 拖拽功能已启用")
        except Exception as e:
            print(f"[字幕功能] 拖拽设置失败: {e}")

    def on_drop(self, event):
        """处理拖拽事件"""
        try:
            # 解析拖拽的文件列表
            files = self.parse_drop_files(event.data)

            # 添加到输入列表
            for file_path in files:
                if os.path.isfile(file_path):
                    ext = os.path.splitext(file_path)[1].lower()
                    if ext in ['.srt', '.ass']:
                        if file_path not in self.input_files:
                            self.input_files.append(file_path)
                            self.input_listbox.insert(tk.END, os.path.basename(file_path))

            self.update_status(f"已添加 {len(files)} 个文件")
        except Exception as e:
            print(f"[字幕功能] 拖拽处理失败: {e}")

    def parse_drop_files(self, data):
        """解析拖拽的文件数据"""
        files = []

        # 处理不同平台的文件路径格式
        if data.startswith('{'):
            # Windows格式: {C:/path/file1.srt} {C:/path/file2.srt}
            import re
            pattern = r'\{([^}]+)\}'
            matches = re.findall(pattern, data)
            files = matches
        else:
            # Unix格式: /path/file1.srt /path/file2.srt
            files = data.split()

        # 清理路径
        cleaned_files = []
        for f in files:
            # 移除可能的引号
            f = f.strip().strip('"').strip("'")
            if os.path.exists(f):
                cleaned_files.append(f)

        return cleaned_files

    def add_input_files(self):
        """添加输入文件"""
        files = filedialog.askopenfilenames(
            title="选择字幕文件",
            filetypes=[
                ("字幕文件", "*.srt *.ass"),
                ("SRT文件", "*.srt"),
                ("ASS文件", "*.ass"),
                ("所有文件", "*.*")
            ]
        )

        for file_path in files:
            if file_path not in self.input_files:
                self.input_files.append(file_path)
                self.input_listbox.insert(tk.END, os.path.basename(file_path))

        if files:
            self.update_status(f"已添加 {len(files)} 个文件")

    def clear_input_files(self):
        """清空输入文件列表"""
        self.input_files.clear()
        self.input_listbox.delete(0, tk.END)
        self.update_status("已清空输入列表")

    def select_all_files(self, event=None):
        """全选所有文件（Ctrl+A）"""
        self.input_listbox.selection_set(0, tk.END)
        selected_count = self.input_listbox.size()
        self.update_status(f"已全选 {selected_count} 个文件")
        return "break"  # 阻止事件继续传播

    def deselect_all_files(self, event=None):
        """取消所有选中（ESC）"""
        self.input_listbox.selection_clear(0, tk.END)
        self.update_status("已取消选中")
        return "break"

    def delete_selected_files(self):
        """删除选中的文件（按钮触发）"""
        selected_indices = self.input_listbox.curselection()

        if not selected_indices:
            messagebox.showinfo("提示", "[提示] 请先选择要删除的文件")
            return

        # 确认删除
        count = len(selected_indices)
        if count == 1:
            confirm_msg = f"[提示] 确定要删除选中的 1 个文件吗？"
        else:
            confirm_msg = f"[提示] 确定要删除选中的 {count} 个文件吗？"

        if not messagebox.askyesno("确认删除", confirm_msg):
            return

        # 从后往前删除，避免索引变化问题
        for index in reversed(selected_indices):
            # 从文件列表中删除
            if index < len(self.input_files):
                del self.input_files[index]
            # 从列表框中删除
            self.input_listbox.delete(index)

        self.update_status(f"[成功] 已删除 {count} 个文件")

    def delete_selected_files_by_key(self, event=None):
        """删除选中的文件（Delete键触发）"""
        selected_indices = self.input_listbox.curselection()

        if not selected_indices:
            return "break"

        count = len(selected_indices)

        # 从后往前删除，避免索引变化问题
        for index in reversed(selected_indices):
            # 从文件列表中删除
            if index < len(self.input_files):
                del self.input_files[index]
            # 从列表框中删除
            self.input_listbox.delete(index)

        self.update_status(f"[成功] 已删除 {count} 个文件")
        return "break"

    def open_output_folder(self):
        """打开输出文件夹"""
        if not self.output_dir:
            messagebox.showwarning("警告", "请先选择输出目录")
            return

        if not os.path.exists(self.output_dir):
            messagebox.showwarning("警告", f"输出目录不存在:\n{self.output_dir}")
            return

        try:
            import subprocess
            import platform

            system = platform.system()
            if system == 'Windows':
                # Windows: 使用 explorer 打开文件夹
                subprocess.run(['explorer', os.path.abspath(self.output_dir)])
            elif system == 'Darwin':
                # macOS: 使用 open 打开文件夹
                subprocess.run(['open', self.output_dir])
            else:
                # Linux: 使用 xdg-open 打开文件夹
                subprocess.run(['xdg-open', self.output_dir])

            self.update_status(f"已打开输出文件夹: {self.output_dir}")

        except Exception as e:
            messagebox.showerror("错误", f"无法打开文件夹: {e}")

    def select_output_dir(self):
        """选择输出目录"""
        directory = filedialog.askdirectory(title="选择输出目录")
        if directory:
            self.output_dir = directory
            self.output_var.set(directory)
            self.update_status(f"输出目录: {directory}")

    def update_status(self, message: str):
        """更新状态栏"""
        self.status_var.set(message)
        self.dialog.update_idletasks()

    def ask_open_output_folder(self, title: str):
        """询问是否打开输出文件夹"""
        try:
            response = messagebox.askyesno(
                "完成",
                f"{title}\n\n是否打开输出文件夹?",
                icon='info'
            )

            if response and self.output_dir and os.path.exists(self.output_dir):
                import subprocess
                import platform

                system = platform.system()
                if system == 'Windows':
                    subprocess.run(['explorer', os.path.abspath(self.output_dir)])
                elif system == 'Darwin':
                    subprocess.run(['open', self.output_dir])
                else:
                    subprocess.run(['xdg-open', self.output_dir])

                print(f"[字幕功能] 已打开输出文件夹: {self.output_dir}")

        except Exception as e:
            print(f"[字幕功能] 打开输出文件夹失败: {e}")

    def validate_input(self, min_files: int = 1, max_files: int = None) -> bool:
        """验证输入文件

        Args:
            min_files: 最少文件数
            max_files: 最多文件数（None表示不限制）

        Returns:
            是否通过验证
        """
        if len(self.input_files) < min_files:
            messagebox.showwarning("警告", f"请至少选择 {min_files} 个输入文件")
            return False

        if max_files and len(self.input_files) > max_files:
            messagebox.showwarning("警告", f"最多只能选择 {max_files} 个输入文件")
            return False

        if not self.output_dir:
            messagebox.showwarning("警告", "请选择输出目录")
            return False

        return True

    def validate_srt_structure(self, srt_path: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """验证SRT文件结构（参考外部脚本的详细校验逻辑，不使用emoji）

        Args:
            srt_path: SRT文件路径

        Returns:
            (is_valid, error_type, error_message)
            is_valid: 是否有效
            error_type: 错误类型 ('bilingual', 'monolingual', 'invalid', None)
            error_message: 错误详情
        """
        try:
            # 尝试以utf-8-sig编码打开（兼容带BOM和不带BOM的UTF-8文件）
            try:
                with open(srt_path, 'r', encoding='utf-8-sig') as f:
                    lines = [(i+1, line.rstrip('\n')) for i, line in enumerate(f.readlines())]
            except UnicodeDecodeError:
                # 明确提示文件不是UTF-8系列编码
                error_msg = (
                    "[错误] 文件编码错误：请确保输入文件为UTF-8编码（可含BOM），当前文件使用了非UTF-8编码\n"
                    "[提示] 解决方案：\n"
                    "   1. 使用记事本打开文件，点击'另存为'，编码选择'UTF-8'\n"
                    "   2. 使用VS Code等编辑器，右下角点击编码，选择'通过编码重新打开'，选择正确编码后保存为UTF-8\n"
                    "   3. 确保文件不是GBK、ANSI等其他编码格式"
                )
                return False, 'invalid', error_msg

            i = 0
            blocks = []
            content_lengths = []  # 记录每个块的序号和内容行数
            expected_index = 1  # 期望的序号，用于检查序号连续性

            while i < len(lines):
                # 跳过块间空行
                while i < len(lines) and not lines[i][1].strip():
                    i += 1
                if i >= len(lines):
                    break

                # 校验序号行
                index_line_num, index_line_content = lines[i]
                if not index_line_content.strip().isdigit():
                    # 详细的序号检测错误提示
                    actual_content = index_line_content.strip()[:50]  # 限制显示长度
                    if not actual_content:
                        error_msg = (
                            f"[错误] 序号检测错误：第{index_line_num}行为空行，应为字幕块序号（纯数字）\n"
                            f"[提示] 解决方案：检查SRT文件格式，确保每个字幕块都以序号开始"
                        )
                    else:
                        error_msg = (
                            f"[错误] 序号检测错误：第{index_line_num}行内容为 '{actual_content}'，应为字幕块序号（纯数字）\n"
                            f"[提示] 解决方案：\n"
                            f"   1. 检查该行内容字幕块是否缺失序号\n"
                            f"   2. 确保序号为纯数字，且不包含肉眼可见的特殊字符\n"
                            f"   3. 修正序号为纯数字，如：1、2、3..."
                        )
                    return False, 'invalid', error_msg

                index = index_line_content.strip()

                # 检查序号连续性
                try:
                    current_index = int(index)
                    if current_index != expected_index:
                        # 提供详细的序号连续性错误提示
                        if current_index < expected_index:
                            error_msg = (
                                f"[错误] 序号连续性错误：第{index_line_num}行序号{current_index}重复或倒退\n"
                                f"[提示] 期望序号：{expected_index}，实际序号：{current_index}\n"
                                f"[提示] 解决方案：\n"
                                f"   1. 检查是否有重复的序号\n"
                                f"   2. 确保序号按1、2、3...顺序递增\n"
                                f"   3. 删除重复的字幕块或修正序号"
                            )
                        else:
                            error_msg = (
                                f"[错误] 序号连续性错误：第{index_line_num}行序号{current_index}跳跃过大\n"
                                f"[提示] 期望序号：{expected_index}，实际序号：{current_index}\n"
                                f"[提示] 解决方案：\n"
                                f"   1. 检查是否缺少序号{expected_index}到{current_index-1}的字幕块\n"
                                f"   2. 修正当前序号为{expected_index}\n"
                                f"   3. 确保序号连续无跳跃"
                            )
                        return False, 'invalid', error_msg
                    expected_index += 1
                except ValueError:
                    error_msg = f"[错误] 序号格式错误：第{index_line_num}行序号 '{index}' 不是有效数字"
                    return False, 'invalid', error_msg

                i += 1

                # 校验时间轴行
                if i >= len(lines):
                    error_msg = (
                        f"[错误] 时间轴检测错误：序号{index}字幕块后缺少时间轴行\n"
                        f"[提示] 解决方案：在序号{index}后添加时间轴行，格式如：00:00:01,000 --> 00:00:03,000"
                    )
                    return False, 'invalid', error_msg

                time_line_num, time_line_content = lines[i]
                if '-->' not in time_line_content:
                    # 详细的时间轴检测错误提示
                    actual_content = time_line_content.strip()[:50]  # 限制显示长度
                    error_msg = (
                        f"[错误] 时间轴格式错误：第{time_line_num}行内容为 '{actual_content}'，缺少时间轴分隔符 '-->' \n"
                        f"[提示] 正确格式：HH:MM:SS,mmm --> HH:MM:SS,mmm\n"
                        f"[提示] 示例：00:00:01,000 --> 00:00:03,000\n"
                        f"[提示] 当前字幕块：序号{index}"
                    )
                    return False, 'invalid', error_msg

                # 进一步验证时间轴格式
                time_parts = time_line_content.split('-->')
                if len(time_parts) != 2:
                    error_msg = (
                        f"[错误] 时间轴格式错误：第{time_line_num}行时间轴分隔符 '-->' 数量不正确\n"
                        f"[提示] 正确格式：开始时间 --> 结束时间\n"
                        f"[提示] 当前内容：{time_line_content.strip()}\n"
                        f"[提示] 当前字幕块：序号{index}"
                    )
                    return False, 'invalid', error_msg

                start_time, end_time = time_parts[0].strip(), time_parts[1].strip()

                # 验证时间格式 (HH:MM:SS,mmm)
                time_pattern = r'^\d{2}:\d{2}:\d{2},\d{3}$'
                if not re.match(time_pattern, start_time):
                    error_msg = (
                        f"[错误] 开始时间格式错误：第{time_line_num}行开始时间 '{start_time}' 格式不正确\n"
                        f"[提示] 正确格式：HH:MM:SS,mmm（如：00:00:01,000）\n"
                        f"[提示] 当前字幕块：序号{index}"
                    )
                    return False, 'invalid', error_msg

                if not re.match(time_pattern, end_time):
                    error_msg = (
                        f"[错误] 结束时间格式错误：第{time_line_num}行结束时间 '{end_time}' 格式不正确\n"
                        f"[提示] 正确格式：HH:MM:SS,mmm（如：00:00:03,000）\n"
                        f"[提示] 当前字幕块：序号{index}"
                    )
                    return False, 'invalid', error_msg

                # 验证时间逻辑（开始时间应小于结束时间）
                try:
                    start_parts = start_time.split(':')
                    start_seconds = int(start_parts[0]) * 3600 + int(start_parts[1]) * 60 + float(start_parts[2].replace(',', '.'))

                    end_parts = end_time.split(':')
                    end_seconds = int(end_parts[0]) * 3600 + int(end_parts[1]) * 60 + float(end_parts[2].replace(',', '.'))

                    if start_seconds >= end_seconds:
                        error_msg = (
                            f"[错误] 时间逻辑错误：第{time_line_num}行开始时间 '{start_time}' 应小于结束时间 '{end_time}'\n"
                            f"[提示] 解决方案：\n"
                            f"   1. 检查时间轴是否写反了\n"
                            f"   2. 确保开始时间早于结束时间\n"
                            f"   3. 当前字幕块：序号{index}"
                        )
                        return False, 'invalid', error_msg

                    # 检查时间是否合理（不能超过24小时）
                    if start_seconds >= 86400 or end_seconds >= 86400:
                        error_msg = (
                            f"[错误] 时间范围错误：第{time_line_num}行时间超过24小时限制\n"
                            f"[提示] 开始时间：{start_time}，结束时间：{end_time}\n"
                            f"[提示] 解决方案：检查时间格式是否正确\n"
                            f"[提示] 当前字幕块：序号{index}"
                        )
                        return False, 'invalid', error_msg

                    # 检查字幕持续时间是否过短（小于0.1秒可能有问题）
                    duration = end_seconds - start_seconds
                    if duration < 0.1:
                        error_msg = (
                            f"[警告] 时间持续过短：第{time_line_num}行字幕持续时间仅{duration:.3f}秒\n"
                            f"[提示] 开始时间：{start_time}，结束时间：{end_time}\n"
                            f"[提示] 解决方案：检查时间是否设置正确，字幕持续时间建议至少0.5秒\n"
                            f"[提示] 当前字幕块：序号{index}"
                        )
                        # 这里只是警告，不返回False
                        print(f"[字幕功能] {error_msg}")

                except ValueError as ve:
                    error_msg = (
                        f"[错误] 时间解析错误：第{time_line_num}行时间格式包含无效数值\n"
                        f"[提示] 开始时间：{start_time}，结束时间：{end_time}\n"
                        f"[提示] 错误详情：{str(ve)}\n"
                        f"[提示] 当前字幕块：序号{index}"
                    )
                    return False, 'invalid', error_msg

                time = time_line_content.strip()
                i += 1

                # 收集内容行
                contents = []
                while i < len(lines) and lines[i][1].strip():
                    contents.append(lines[i][1])
                    i += 1

                if not contents:
                    error_msg = (
                        f"[错误] 内容检测错误：序号{index}字幕块的时间轴后缺少字幕内容行\n"
                        f"[提示] 解决方案：在时间轴行后添加字幕内容（1-2行文本）"
                    )
                    return False, 'invalid', error_msg

                if len(contents) > 2:
                    error_msg = (
                        f"[错误] 内容行数错误：序号{index}字幕块包含{len(contents)}行内容，超出支持范围（最多2行）\n"
                        f"[提示] 解决方案：检查字幕块间是否缺少空行分隔，或将多行内容合并为1-2行\n"
                        f"[提示] 当前内容：{contents[:3]}{'...' if len(contents) > 3 else ''}"
                    )
                    return False, 'invalid', error_msg

                # 记录当前块的内容行数
                content_lengths.append((index, len(contents)))

                # 记录块间空行状态
                has_empty_line = False
                if i < len(lines) and not lines[i][1].strip():
                    has_empty_line = True
                    i += 1

                # 保存块信息
                blocks.append({
                    'index': index,
                    'time': time,
                    'contents': contents,
                    'has_empty_line': has_empty_line
                })

            if not blocks:
                error_msg = (
                    "[错误] 文件结构错误：文件中未检测到有效的字幕块\n"
                    "[提示] 解决方案：\n"
                    "   1. 检查文件是否为有效的SRT格式\n"
                    "   2. 确保文件包含序号、时间轴和内容三个基本元素\n"
                    "   3. 检查文件是否为空或只包含空行\n"
                    "   4. 标准SRT格式示例：\n"
                    "      1\n"
                    "      00:00:01,000 --> 00:00:03,000\n"
                    "      字幕内容\n"
                    "      \n"
                    "      2\n"
                    "      00:00:03,000 --> 00:00:05,000\n"
                    "      下一行字幕内容"
                )
                return False, 'invalid', error_msg

            # 检查所有块的内容行数是否一致
            content_counts = {length for _, length in content_lengths}
            if len(content_counts) > 1:
                # 找出所有不一致的块
                base_length = content_lengths[0][1]
                inconsistent_blocks = []
                for idx, length in content_lengths:
                    if length != base_length:
                        inconsistent_blocks.append(f"序号{idx}({length}行)")

                if inconsistent_blocks:
                    error_msg = (
                        f"[错误] 字幕块结构不一致：检测到混合的单语/双语字幕块\n"
                        f"[提示] 基准格式：{base_length}行内容（{'单语' if base_length == 1 else '双语'}）\n"
                        f"[提示] 不一致的块：{', '.join(inconsistent_blocks[:5])}{'...' if len(inconsistent_blocks) > 5 else ''}\n"
                        f"[提示] 解决方案：统一所有字幕块的格式，要么全部单语（1行），要么全部双语（2行）"
                    )
                    return False, 'invalid', error_msg

            # 确定类型代码和类型文本
            lang_type_code = 'single' if content_lengths[0][1] == 1 else 'double'

            # 转换为统一的类型标识
            if lang_type_code == 'single':
                return True, 'monolingual', None
            else:
                return True, 'bilingual', None

        except Exception as e:
            error_msg = f"[错误] 文件读取失败：{str(e)}"
            return False, 'invalid', error_msg

    # ========== 功能1: 双语字幕分离 ==========
    def split_bilingual(self):
        """双语字幕分离"""
        try:
            # 验证输入（至少1个文件）
            if not self.validate_input(min_files=1):
                return

            self.update_status("正在分离双语字幕...")

            success_count = 0  # 成功处理的文件计数
            failed_count = 0   # 失败文件计数
            total_files = len(self.input_files)

            for file_index, input_file in enumerate(self.input_files, 1):
                # 更新处理进度
                progress_msg = f"正在分离 ({file_index}/{total_files}): {os.path.basename(input_file)}"
                self.update_status(progress_msg)
                print(f"[字幕功能] {progress_msg}")

                # 验证文件结构
                is_valid, error_type, error_msg = self.validate_srt_structure(input_file)

                if not is_valid:
                    messagebox.showerror("错误", f"[错误] 文件 {os.path.basename(input_file)} 验证失败:\n\n{error_msg}")
                    failed_count += 1
                    continue

                if error_type != 'bilingual':
                    warning_msg = (
                        f"[警告] 文件 {os.path.basename(input_file)} 不是双语字幕文件\n\n"
                        f"[提示] 检测到的类型: {'单语' if error_type == 'monolingual' else '未知'}\n"
                        f"[提示] 请选择包含两行内容的双语字幕文件"
                    )
                    messagebox.showwarning("警告", warning_msg)
                    failed_count += 1
                    continue

                # 读取字幕
                subs = pysrt.open(input_file, encoding='utf-8-sig')

                # 创建两个单语字幕列表
                lang1_subs = pysrt.SubRipFile()
                lang2_subs = pysrt.SubRipFile()

                for sub in subs:
                    text = sub.text.strip()
                    lines = text.split('\n')
                    lines = [line.strip() for line in lines if line.strip()]

                    if len(lines) == 2:
                        # 第一语言（原文）
                        lang1_sub = pysrt.SubRipItem(
                            index=sub.index,
                            start=sub.start,
                            end=sub.end,
                            text=lines[0]
                        )
                        lang1_subs.append(lang1_sub)

                        # 第二语言（译文）
                        lang2_sub = pysrt.SubRipItem(
                            index=sub.index,
                            start=sub.start,
                            end=sub.end,
                            text=lines[1]
                        )
                        lang2_subs.append(lang2_sub)

                # 生成输出文件名
                base_name = os.path.splitext(os.path.basename(input_file))[0]
                lang1_output = os.path.join(self.output_dir, f"{base_name}_lang1.srt")
                lang2_output = os.path.join(self.output_dir, f"{base_name}_lang2.srt")

                # 保存文件
                lang1_subs.save(lang1_output, encoding='utf-8')
                lang2_subs.save(lang2_output, encoding='utf-8')

                print(f"[字幕功能] 双语分离: {lang1_output}, {lang2_output}")
                success_count += 1

            # 根据处理结果显示不同消息
            if success_count > 0:
                if failed_count > 0:
                    # 部分成功
                    self.update_status(f"[警告] 分离完成: 成功{success_count}个, 失败{failed_count}个")
                    self.ask_open_output_folder(f"[成功] 双语字幕分离完成!\n\n成功: {success_count}个文件\n失败: {failed_count}个文件")
                else:
                    # 全部成功
                    self.update_status(f"[成功] 分离完成: {success_count} 个文件")
                    self.ask_open_output_folder("[成功] 双语字幕分离完成!")
            else:
                # 全部失败
                self.update_status(f"[错误] 分离失败: 所有文件({failed_count}个)均校验失败")
                messagebox.showerror("错误", f"[错误] 分离失败\n\n所有文件({failed_count}个)均校验失败，未生成任何输出文件")

        except Exception as e:
            import traceback
            error_msg = f"[错误] 双语分离失败:\n\n{str(e)}\n\n{traceback.format_exc()}"
            messagebox.showerror("错误", error_msg)
            self.update_status("[错误] 双语分离失败")

    # ========== 功能2: 单语字幕合并 ==========
    def merge_monolingual(self):
        """单语字幕合并"""
        try:
            # 验证输入（需要2个文件）
            if not self.validate_input(min_files=2, max_files=2):
                return

            file1 = self.input_files[0]
            file2 = self.input_files[1]

            # 验证文件结构
            is_valid1, type1, msg1 = self.validate_srt_structure(file1)
            is_valid2, type2, msg2 = self.validate_srt_structure(file2)

            if not is_valid1:
                messagebox.showerror("错误", f"[错误] 文件1验证失败:\n\n{msg1}")
                return

            if not is_valid2:
                messagebox.showerror("错误", f"[错误] 文件2验证失败:\n\n{msg2}")
                return

            if type1 != 'monolingual' or type2 != 'monolingual':
                error_msg = (
                    "[错误] 两个输入文件必须都是单语字幕\n\n"
                    f"[提示] 文件1类型: {'单语' if type1 == 'monolingual' else '双语'}\n"
                    f"[提示] 文件2类型: {'单语' if type2 == 'monolingual' else '双语'}\n\n"
                    "[提示] 请选择两个单语字幕文件进行合并"
                )
                messagebox.showwarning("警告", error_msg)
                return

            self.update_status("正在合并单语字幕...")

            # 读取字幕
            subs1 = pysrt.open(file1, encoding='utf-8-sig')
            subs2 = pysrt.open(file2, encoding='utf-8-sig')

            # 检查数量是否一致
            if len(subs1) != len(subs2):
                warning_msg = (
                    f"[警告] 两个文件的字幕数量不一致:\n\n"
                    f"文件1: {len(subs1)} 条\n"
                    f"文件2: {len(subs2)} 条\n\n"
                    f"[提示] 将以较少的为准进行合并"
                )
                messagebox.showwarning("警告", warning_msg)

            # 创建双语字幕
            merged_subs = pysrt.SubRipFile()

            count = min(len(subs1), len(subs2))

            for i in range(count):
                sub1 = subs1[i]
                sub2 = subs2[i]

                # 合并文本（第一语言\n第二语言）
                merged_text = f"{sub1.text.strip()}\n{sub2.text.strip()}"

                # 使用第一个文件的时间轴
                merged_sub = pysrt.SubRipItem(
                    index=sub1.index,
                    start=sub1.start,
                    end=sub1.end,
                    text=merged_text
                )

                merged_subs.append(merged_sub)

            # 生成输出文件名
            base_name1 = os.path.splitext(os.path.basename(file1))[0]
            output_file = os.path.join(self.output_dir, f"{base_name1}_merged.srt")

            # 保存文件
            merged_subs.save(output_file, encoding='utf-8')

            self.update_status(f"[成功] 合并完成: {len(merged_subs)} 条字幕")

            # 询问是否打开输出文件夹
            self.ask_open_output_folder("[成功] 单语字幕合并完成!")

        except Exception as e:
            import traceback
            error_msg = f"[错误] 单语合并失败:\n\n{str(e)}\n\n{traceback.format_exc()}"
            messagebox.showerror("错误", error_msg)
            self.update_status("[错误] 单语合并失败")

    # ========== 功能3: 提取纯文本 ==========
    def extract_text(self):
        """提取纯文本（自动检测单语/双语）"""
        try:
            # 验证输入（至少1个文件）
            if not self.validate_input(min_files=1):
                return

            self.update_status("正在提取纯文本...")

            success_count = 0  # 成功处理的文件计数
            failed_count = 0   # 失败文件计数

            for input_file in self.input_files:
                # 验证文件结构
                is_valid, error_type, error_msg = self.validate_srt_structure(input_file)

                if not is_valid:
                    messagebox.showerror("错误", f"[错误] 文件 {os.path.basename(input_file)} 验证失败:\n\n{error_msg}")
                    failed_count += 1
                    continue

                # 读取字幕
                subs = pysrt.open(input_file, encoding='utf-8-sig')
                base_name = os.path.splitext(os.path.basename(input_file))[0]

                if error_type == 'monolingual':
                    # 单语文件 → 输出1个文本文件
                    lines = []
                    for sub in subs:
                        text = sub.text.strip()
                        if text:  # 过滤空行
                            lines.append(text)

                    output_file = os.path.join(self.output_dir, f"{base_name}_text.txt")

                    with open(output_file, 'w', encoding='utf-8') as f:
                        f.write('\n'.join(lines))

                    print(f"[字幕功能] 提取纯文本(单语): {output_file}")
                    success_count += 1

                elif error_type == 'bilingual':
                    # 双语文件 → 输出2个文本文件
                    lang1_lines = []
                    lang2_lines = []

                    for sub in subs:
                        text = sub.text.strip()
                        if not text:  # 跳过空字幕
                            continue

                        lines = text.split('\n')
                        lines = [line.strip() for line in lines if line.strip()]

                        if len(lines) == 2:
                            lang1_lines.append(lines[0])  # 第一行(原文)
                            lang2_lines.append(lines[1])  # 第二行(译文)

                    # 保存第一语言文本
                    lang1_output = os.path.join(self.output_dir, f"{base_name}_lang1.txt")
                    with open(lang1_output, 'w', encoding='utf-8') as f:
                        f.write('\n'.join(lang1_lines))

                    # 保存第二语言文本
                    lang2_output = os.path.join(self.output_dir, f"{base_name}_lang2.txt")
                    with open(lang2_output, 'w', encoding='utf-8') as f:
                        f.write('\n'.join(lang2_lines))

                    print(f"[字幕功能] 提取纯文本(双语): {lang1_output}, {lang2_output}")
                    success_count += 1

            # 根据处理结果显示不同消息
            if success_count > 0:
                if failed_count > 0:
                    # 部分成功
                    self.update_status(f"[警告] 提取完成: 成功{success_count}个, 失败{failed_count}个")
                    self.ask_open_output_folder(f"[成功] 纯文本提取完成!\n\n成功: {success_count}个文件\n失败: {failed_count}个文件")
                else:
                    # 全部成功
                    self.update_status(f"[成功] 提取完成: {success_count} 个文件")
                    self.ask_open_output_folder("[成功] 纯文本提取完成!")
            else:
                # 全部失败
                self.update_status(f"[错误] 提取失败: 所有文件({failed_count}个)均校验失败")
                messagebox.showerror("错误", f"[错误] 提取失败\n\n所有文件({failed_count}个)均校验失败，未生成任何输出文件")

        except Exception as e:
            import traceback
            error_msg = f"[错误] 提取纯文本失败:\n\n{str(e)}\n\n{traceback.format_exc()}"
            messagebox.showerror("错误", error_msg)
            self.update_status("[错误] 提取纯文本失败")

    # ========== 功能4: 提取时间轴 ==========
    def extract_timeline(self):
        """提取时间轴（4行格式：序号\n时间轴\n序号\n空行）"""
        try:
            # 验证输入（至少1个文件）
            if not self.validate_input(min_files=1):
                return

            self.update_status("正在提取时间轴...")

            for input_file in self.input_files:
                # 读取字幕
                subs = pysrt.open(input_file, encoding='utf-8-sig')

                # 提取时间轴（新格式）
                lines = []
                for sub in subs:
                    # 4行格式：
                    # 第1行: 序号
                    # 第2行: 时间轴
                    # 第3行: 序号（重复）
                    # 第4行: 空行
                    timeline_block = f"{sub.index}\n{sub.start} --> {sub.end}\n{sub.index}\n"
                    lines.append(timeline_block)

                # 生成输出文件名
                base_name = os.path.splitext(os.path.basename(input_file))[0]
                output_file = os.path.join(self.output_dir, f"{base_name}_timeline.txt")

                # 保存文件
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(lines))

                print(f"[字幕功能] 提取时间轴: {output_file}")

            self.update_status(f"[成功] 提取完成: {len(self.input_files)} 个文件")

            # 询问是否打开输出文件夹
            self.ask_open_output_folder("[成功] 时间轴提取完成!")

        except Exception as e:
            import traceback
            error_msg = f"[错误] 提取时间轴失败:\n\n{str(e)}\n\n{traceback.format_exc()}"
            messagebox.showerror("错误", error_msg)
            self.update_status("[错误] 提取时间轴失败")

    # ========== 功能5: 双语行互换 ==========
    def swap_bilingual(self):
        """双语行互换"""
        try:
            # 验证输入（至少1个文件）
            if not self.validate_input(min_files=1):
                return

            self.update_status("正在互换双语行...")

            success_count = 0  # 成功处理的文件计数
            failed_count = 0   # 失败文件计数

            for input_file in self.input_files:
                # 验证文件结构
                is_valid, error_type, error_msg = self.validate_srt_structure(input_file)

                if not is_valid:
                    messagebox.showerror("错误", f"[错误] 文件 {os.path.basename(input_file)} 验证失败:\n\n{error_msg}")
                    failed_count += 1
                    continue

                if error_type != 'bilingual':
                    warning_msg = (
                        f"[警告] 文件 {os.path.basename(input_file)} 不是双语字幕文件\n\n"
                        f"[提示] 检测到的类型: {'单语' if error_type == 'monolingual' else '未知'}\n"
                        f"[提示] 请选择包含两行内容的双语字幕文件"
                    )
                    messagebox.showwarning("警告", warning_msg)
                    failed_count += 1
                    continue

                # 读取字幕
                subs = pysrt.open(input_file, encoding='utf-8-sig')

                # 互换双语行
                swapped_subs = pysrt.SubRipFile()

                for sub in subs:
                    text = sub.text.strip()
                    lines = text.split('\n')
                    lines = [line.strip() for line in lines if line.strip()]

                    if len(lines) == 2:
                        # 互换第一行和第二行
                        swapped_text = f"{lines[1]}\n{lines[0]}"

                        swapped_sub = pysrt.SubRipItem(
                            index=sub.index,
                            start=sub.start,
                            end=sub.end,
                            text=swapped_text
                        )

                        swapped_subs.append(swapped_sub)

                # 生成输出文件名
                base_name = os.path.splitext(os.path.basename(input_file))[0]
                output_file = os.path.join(self.output_dir, f"{base_name}_swapped.srt")

                # 保存文件
                swapped_subs.save(output_file, encoding='utf-8')

                print(f"[字幕功能] 双语互换: {output_file}")
                success_count += 1

            # 根据处理结果显示不同消息
            if success_count > 0:
                if failed_count > 0:
                    # 部分成功
                    self.update_status(f"[警告] 互换完成: 成功{success_count}个, 失败{failed_count}个")
                    self.ask_open_output_folder(f"[成功] 双语行互换完成!\n\n成功: {success_count}个文件\n失败: {failed_count}个文件")
                else:
                    # 全部成功
                    self.update_status(f"[成功] 互换完成: {success_count} 个文件")
                    self.ask_open_output_folder("[成功] 双语行互换完成!")
            else:
                # 全部失败
                self.update_status(f"[错误] 互换失败: 所有文件({failed_count}个)均校验失败")
                messagebox.showerror("错误", f"[错误] 互换失败\n\n所有文件({failed_count}个)均校验失败，未生成任何输出文件")

        except Exception as e:
            import traceback
            error_msg = f"[错误] 双语互换失败:\n\n{str(e)}\n\n{traceback.format_exc()}"
            messagebox.showerror("错误", error_msg)
            self.update_status("[错误] 双语互换失败")

    # ========== 功能6: SRT⇄ASS格式转换 ==========
    def convert_format(self):
        """SRT⇄ASS格式转换（简单转换，只转文本和时间）"""
        try:
            # 验证输入（至少1个文件）
            if not self.validate_input(min_files=1):
                return

            self.update_status("正在转换格式...")

            success_count = 0  # 成功处理的文件计数
            failed_count = 0   # 失败文件计数

            for input_file in self.input_files:
                ext = os.path.splitext(input_file)[1].lower()

                if ext == '.srt':
                    # SRT → ASS
                    try:
                        self.srt_to_ass(input_file)
                        success_count += 1
                    except Exception as e:
                        messagebox.showerror("错误", f"[错误] 转换文件失败:\n{os.path.basename(input_file)}\n\n{str(e)}")
                        failed_count += 1
                elif ext == '.ass':
                    # ASS → SRT
                    try:
                        self.ass_to_srt(input_file)
                        success_count += 1
                    except Exception as e:
                        messagebox.showerror("错误", f"[错误] 转换文件失败:\n{os.path.basename(input_file)}\n\n{str(e)}")
                        failed_count += 1
                else:
                    warning_msg = (
                        f"[警告] 不支持的文件格式: {ext}\n\n"
                        f"[提示] 支持的格式: .srt, .ass\n"
                        f"[提示] 文件: {os.path.basename(input_file)}"
                    )
                    messagebox.showwarning("警告", warning_msg)
                    failed_count += 1
                    continue

            # 根据处理结果显示不同消息
            if success_count > 0:
                if failed_count > 0:
                    # 部分成功
                    self.update_status(f"[警告] 转换完成: 成功{success_count}个, 失败{failed_count}个")
                    self.ask_open_output_folder(f"[成功] 格式转换完成!\n\n成功: {success_count}个文件\n失败: {failed_count}个文件")
                else:
                    # 全部成功
                    self.update_status(f"[成功] 转换完成: {success_count} 个文件")
                    self.ask_open_output_folder("[成功] 格式转换完成!")
            else:
                # 全部失败
                self.update_status(f"[错误] 转换失败: 所有文件({failed_count}个)均转换失败")
                messagebox.showerror("错误", f"[错误] 转换失败\n\n所有文件({failed_count}个)均转换失败，未生成任何输出文件")

        except Exception as e:
            import traceback
            error_msg = f"[错误] 格式转换失败:\n\n{str(e)}\n\n{traceback.format_exc()}"
            messagebox.showerror("错误", error_msg)
            self.update_status("[错误] 格式转换失败")

    def srt_to_ass(self, srt_path: str):
        """SRT转ASS（简单转换）"""
        # 读取SRT
        subs = pysrt.open(srt_path, encoding='utf-8-sig')

        # 生成输出文件名
        base_name = os.path.splitext(os.path.basename(srt_path))[0]
        output_file = os.path.join(self.output_dir, f"{base_name}.ass")

        # ASS文件头
        ass_header = """[Script Info]
Title: Converted from SRT
ScriptType: v4.00+
Collisions: Normal
PlayDepth: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

        # 转换时间格式（SRT → ASS）
        def srt_time_to_ass(srt_time):
            """将SRT时间格式转换为ASS格式
            SRT: 00:00:10,500
            ASS: 0:00:10.50
            """
            time_str = str(srt_time)
            # 替换逗号为点
            time_str = time_str.replace(',', '.')
            # 去掉前导零
            parts = time_str.split(':')
            if len(parts) == 3:
                h = int(parts[0])
                time_str = f"{h}:{parts[1]}:{parts[2]}"
            return time_str

        # 写入ASS文件
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(ass_header)

            for sub in subs:
                start = srt_time_to_ass(sub.start)
                end = srt_time_to_ass(sub.end)
                text = sub.text.replace('\n', '\\N')  # ASS使用\N表示换行

                # 格式: Dialogue: 0,开始时间,结束时间,样式,名称,边距L,边距R,边距V,特效,文本
                line = f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n"
                f.write(line)

        print(f"[字幕功能] SRT→ASS: {output_file}")

    def ass_to_srt(self, ass_path: str):
        """ASS转SRT（简单转换）"""
        # 生成输出文件名
        base_name = os.path.splitext(os.path.basename(ass_path))[0]
        output_file = os.path.join(self.output_dir, f"{base_name}.srt")

        # 读取ASS文件
        with open(ass_path, 'r', encoding='utf-8-sig') as f:
            lines = f.readlines()

        # 提取对话行
        dialogues = []
        in_events = False

        for line in lines:
            line = line.strip()

            if line.startswith('[Events]'):
                in_events = True
                continue

            if in_events and line.startswith('Dialogue:'):
                dialogues.append(line)

        # 转换为SRT
        srt_subs = pysrt.SubRipFile()

        for i, dialogue in enumerate(dialogues, 1):
            # 解析Dialogue行
            # 格式: Dialogue: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
            parts = dialogue.split(',', 9)

            if len(parts) < 10:
                continue

            start_str = parts[1].strip()
            end_str = parts[2].strip()
            text = parts[9].strip()

            # 转换时间格式（ASS → SRT）
            def ass_time_to_srt(ass_time):
                """将ASS时间格式转换为SRT格式
                ASS: 0:00:10.50
                SRT: 00:00:10,500
                """
                # 确保小时部分有两位数
                parts = ass_time.split(':')
                if len(parts) == 3:
                    h = int(parts[0])
                    time_str = f"{h:02d}:{parts[1]}:{parts[2]}"
                else:
                    time_str = ass_time

                # 替换点为逗号
                time_str = time_str.replace('.', ',')

                # 确保毫秒部分有三位数
                if ',' in time_str:
                    time_part, ms_part = time_str.rsplit(',', 1)
                    ms_part = ms_part.ljust(3, '0')[:3]  # 补齐或截断到3位
                    time_str = f"{time_part},{ms_part}"
                else:
                    time_str += ',000'

                return time_str

            try:
                start = pysrt.SubRipTime.from_string(ass_time_to_srt(start_str))
                end = pysrt.SubRipTime.from_string(ass_time_to_srt(end_str))

                # ASS使用\N表示换行，转换为实际换行
                text = text.replace('\\N', '\n').replace('\\n', '\n')

                sub = pysrt.SubRipItem(
                    index=i,
                    start=start,
                    end=end,
                    text=text
                )

                srt_subs.append(sub)

            except Exception as e:
                print(f"[字幕功能] 跳过无效行: {dialogue[:50]}... 错误: {e}")
                continue

        # 保存SRT文件
        srt_subs.save(output_file, encoding='utf-8')

        print(f"[字幕功能] ASS→SRT: {output_file}")

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

    def open_burn_dialog(self):
        """打开字幕压制对话框"""
        try:
            from .subtitle_burn_dialog import SubtitleBurnDialog
            burn_dialog = SubtitleBurnDialog(self.dialog)
        except Exception as e:
            messagebox.showerror("错误", f"打开字幕压制对话框失败: {e}")
            print(f"[字幕功能] 打开字幕压制对话框失败: {e}")

    def open_extract_dialog(self):
        """打开字幕提取对话框"""
        try:
            from .subtitle_extract_dialog import SubtitleExtractDialog
            extract_dialog = SubtitleExtractDialog(self.dialog)
        except Exception as e:
            messagebox.showerror("错误", f"打开字幕提取对话框失败: {e}")
            print(f"[字幕功能] 打开字幕提取对话框失败: {e}")

    def show(self):
        """显示对话框"""
        self.dialog.wait_window()


def show_subtitle_tools(parent):
    """显示字幕功能对话框（快捷函数）"""
    dialog = SubtitleToolsDialog(parent)
    dialog.show()
