import tkinter as tk
from tkinter import ttk
from database.models import ImportResult


class ImportResultDialog:
    """导入结果对话框"""
    
    def __init__(self, parent, result: ImportResult):
        self.parent = parent
        self.result = result
        self.dialog = None
    
    def show(self):
        """显示导入结果"""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("导入完成")
        self.dialog.geometry("500x400")
        self.dialog.resizable(False, False)
        
        # 居中显示
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        
        # 创建主框架
        main_frame = ttk.Frame(self.dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        if self.result.skipped:
            self._show_skipped_result(main_frame)
        elif self.result.success:
            self._show_success_result(main_frame)
        else:
            self._show_error_result(main_frame)
        
        # 按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(20, 0))
        
        ttk.Button(
            button_frame,
            text="确定",
            command=self.dialog.destroy,
            width=15
        ).pack(side=tk.RIGHT)
        
        # 等待对话框关闭
        self.dialog.wait_window()
    
    def _show_skipped_result(self, parent):
        """显示跳过结果"""
        # 图标
        icon_label = ttk.Label(
            parent,
            text="ℹ️",
            font=('', 48)
        )
        icon_label.pack(pady=(0, 20))
        
        # 标题
        title_label = ttk.Label(
            parent,
            text="项目已存在",
            font=('', 16, 'bold')
        )
        title_label.pack(pady=(0, 10))
        
        # 消息
        message = f"项目 \"{self.result.project_name}\" 已经导入过了\n\n已跳过重复导入"
        message_label = ttk.Label(
            parent,
            text=message,
            font=('', 11),
            justify=tk.CENTER
        )
        message_label.pack(pady=(0, 20))
    
    def _show_success_result(self, parent):
        """显示成功结果"""
        # 图标
        icon_label = ttk.Label(
            parent,
            text="[OK]",
            font=('', 48)
        )
        icon_label.pack(pady=(0, 20))
        
        # 标题
        title_label = ttk.Label(
            parent,
            text="导入成功！",
            font=('', 16, 'bold')
        )
        title_label.pack(pady=(0, 10))
        
        # 统计信息框架
        stats_frame = ttk.LabelFrame(parent, text="导入统计", padding=15)
        stats_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # 项目信息
        self._add_stat_row(stats_frame, "项目名称：", self.result.project_name, 0)
        self._add_stat_row(stats_frame, "总片段数：", str(self.result.total_segments), 1)
        
        # 分隔线
        ttk.Separator(stats_frame, orient=tk.HORIZONTAL).grid(
            row=2, column=0, columnspan=2, sticky='ew', pady=10
        )
        
        # 视频统计
        video_text = f"{self.result.video_success} 成功"
        if self.result.video_failed > 0:
            video_text += f", {self.result.video_failed} 失败"
        self._add_stat_row(stats_frame, "视频片段：", video_text, 3, 
                          color='green' if self.result.video_failed == 0 else 'orange')
        
        # 音频统计
        audio_text = f"{self.result.audio_success} 成功"
        if self.result.audio_failed > 0:
            audio_text += f", {self.result.audio_failed} 失败"
        self._add_stat_row(stats_frame, "音频提取：", audio_text, 4,
                          color='green' if self.result.audio_failed == 0 else 'orange')
        
        # 字幕统计
        subtitle_text = f"{self.result.subtitle_success} 成功"
        if self.result.subtitle_failed > 0:
            subtitle_text += f", {self.result.subtitle_failed} 失败"
        self._add_stat_row(stats_frame, "字幕文件：", subtitle_text, 5,
                          color='green' if self.result.subtitle_failed == 0 else 'orange')
        
        # 分隔线
        ttk.Separator(stats_frame, orient=tk.HORIZONTAL).grid(
            row=6, column=0, columnspan=2, sticky='ew', pady=10
        )
        
        # 耗时
        duration_text = f"{self.result.duration:.1f} 秒"
        if self.result.duration >= 60:
            minutes = int(self.result.duration // 60)
            seconds = int(self.result.duration % 60)
            duration_text = f"{minutes} 分 {seconds} 秒"
        self._add_stat_row(stats_frame, "总耗时：", duration_text, 7)
        
        # 警告信息
        if self.result.audio_failed > 0 or self.result.video_failed > 0:
            warning_label = ttk.Label(
                parent,
                text="[WARN] 部分文件处理失败，请检查日志",
                font=('', 10),
                foreground='orange'
            )
            warning_label.pack(pady=(10, 0))
    
    def _show_error_result(self, parent):
        """显示错误结果"""
        # 图标
        icon_label = ttk.Label(
            parent,
            text="[ERROR]",
            font=('', 48)
        )
        icon_label.pack(pady=(0, 20))
        
        # 标题
        title_label = ttk.Label(
            parent,
            text="导入失败",
            font=('', 16, 'bold'),
            foreground='red'
        )
        title_label.pack(pady=(0, 10))
        
        # 错误信息框架
        error_frame = ttk.LabelFrame(parent, text="错误信息", padding=15)
        error_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # 错误消息
        error_text = tk.Text(
            error_frame,
            height=10,
            width=50,
            wrap=tk.WORD,
            font=('', 10)
        )
        error_text.pack(fill=tk.BOTH, expand=True)
        error_text.insert('1.0', self.result.error_message or "未知错误")
        error_text.config(state=tk.DISABLED)
        
        # 滚动条
        scrollbar = ttk.Scrollbar(error_text, command=error_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        error_text.config(yscrollcommand=scrollbar.set)
    
    def _add_stat_row(self, parent, label_text, value_text, row, color=None):
        """添加统计行"""
        # 标签
        label = ttk.Label(
            parent,
            text=label_text,
            font=('', 11, 'bold')
        )
        label.grid(row=row, column=0, sticky='w', pady=5)
        
        # 值
        value = ttk.Label(
            parent,
            text=value_text,
            font=('', 11),
            foreground=color or 'black'
        )
        value.grid(row=row, column=1, sticky='w', padx=(10, 0), pady=5)
        
        # 配置列权重
        parent.columnconfigure(0, weight=0)
        parent.columnconfigure(1, weight=1)


def show_import_result(parent, result: ImportResult):
    """显示导入结果对话框（便捷函数）"""
    dialog = ImportResultDialog(parent, result)
    dialog.show()

