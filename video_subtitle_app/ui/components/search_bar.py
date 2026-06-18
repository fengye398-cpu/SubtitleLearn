import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

class SearchBarWidget(ttk.Frame):
    """搜索栏组件"""
    
    def __init__(self, parent):
        super().__init__(parent)

        self.search_callback: Optional[Callable] = None
        self.current_keyword = ""
        self.current_mode = "fuzzy"  # 记录当前搜索模式

        # 缓存扩展字幕行参数，用于判断是否需要重新搜索
        self.current_context_before = 0
        self.current_context_after = 0

        # 上下文扩展设置
        self.context_enabled = False
        self.context_before = 0
        self.context_after = 0

        self.create_widgets()
        self.bind_events()
    
    def create_widgets(self):
        """创建组件"""
        # 第一行：文本搜索
        first_row = ttk.Frame(self)
        first_row.pack(fill=tk.X, pady=(0, 5))

        # 搜索标签
        ttk.Label(first_row, text="搜索:").pack(side=tk.LEFT, padx=(0, 5))

        # 搜索输入框
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(first_row, textvariable=self.search_var, width=30)
        self.search_entry.pack(side=tk.LEFT, padx=(0, 5))

        # 搜索按钮
        ttk.Button(first_row, text="搜索", command=self.do_search).pack(side=tk.LEFT, padx=(0, 5))

        # 清空按钮
        ttk.Button(first_row, text="清空", command=self.clear_search).pack(side=tk.LEFT, padx=(0, 10))

        # 搜索模式选择
        mode_frame = ttk.Frame(first_row)
        mode_frame.pack(side=tk.LEFT, padx=(10, 0))

        ttk.Label(mode_frame, text="模式:").pack(side=tk.LEFT, padx=(0, 5))

        self.search_mode_var = tk.StringVar(value="fuzzy")
        ttk.Radiobutton(mode_frame, text="模糊", variable=self.search_mode_var,
                       value="fuzzy", command=self.on_mode_changed).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Radiobutton(mode_frame, text="精确", variable=self.search_mode_var,
                       value="exact", command=self.on_mode_changed).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Radiobutton(mode_frame, text="正则", variable=self.search_mode_var,
                       value="regex", command=self.on_mode_changed).pack(side=tk.LEFT)

        # 上下文扩展控制
        context_frame = ttk.Frame(first_row)
        context_frame.pack(side=tk.LEFT, padx=(10, 0))

        # 扩展字幕行复选框
        self.context_enabled_var = tk.BooleanVar(value=False)
        self.context_checkbox = ttk.Checkbutton(
            context_frame,
            text="扩展字幕行",
            variable=self.context_enabled_var,
            command=self.on_context_enabled_changed
        )
        self.context_checkbox.pack(side=tk.LEFT, padx=(0, 5))

        # 添加 tooltip 提示
        self._create_tooltip(self.context_checkbox, "为匹配字幕行添加上下文，便于学习理解")

        # 上文行数
        ttk.Label(context_frame, text="上:").pack(side=tk.LEFT, padx=(0, 2))
        self.context_before_var = tk.IntVar(value=0)
        self.context_before_spinbox = ttk.Spinbox(
            context_frame,
            from_=0,
            to=99,
            width=5,
            textvariable=self.context_before_var,
            command=self.on_context_changed
        )
        self.context_before_spinbox.pack(side=tk.LEFT, padx=(0, 5))

        # 下文行数
        ttk.Label(context_frame, text="下:").pack(side=tk.LEFT, padx=(0, 2))
        self.context_after_var = tk.IntVar(value=0)
        self.context_after_spinbox = ttk.Spinbox(
            context_frame,
            from_=0,
            to=99,
            width=5,
            textvariable=self.context_after_var,
            command=self.on_context_changed
        )
        self.context_after_spinbox.pack(side=tk.LEFT, padx=(0, 5))

        # 搜索结果信息
        self.result_label = ttk.Label(first_row, text="", foreground="gray")
        self.result_label.pack(side=tk.RIGHT, padx=(10, 0))

        # 第二行：时间区间过滤
        second_row = ttk.Frame(self)
        second_row.pack(fill=tk.X)

        # 时间区间标签
        ttk.Label(second_row, text="时间区间:").pack(side=tk.LEFT, padx=(0, 5))

        # 开始时间输入框
        ttk.Label(second_row, text="开始时间:").pack(side=tk.LEFT, padx=(10, 5))
        self.start_time_var = tk.StringVar()
        self.start_time_entry = ttk.Entry(second_row, textvariable=self.start_time_var, width=15)
        self.start_time_entry.pack(side=tk.LEFT, padx=(0, 5))

        # 结束时间输入框
        ttk.Label(second_row, text="结束时间:").pack(side=tk.LEFT, padx=(10, 5))
        self.end_time_var = tk.StringVar()
        self.end_time_entry = ttk.Entry(second_row, textvariable=self.end_time_var, width=15)
        self.end_time_entry.pack(side=tk.LEFT, padx=(0, 5))

        # 时间过滤按钮
        ttk.Button(second_row, text="时间过滤", command=self.do_time_filter).pack(side=tk.LEFT, padx=(10, 5))

        # 清空时间过滤按钮
        ttk.Button(second_row, text="清空时间", command=self.clear_time_filter).pack(side=tk.LEFT, padx=(0, 5))

        # 时间格式提示
        self.time_hint_label = ttk.Label(second_row, text="(格式: HH:MM:SS,mmm)", foreground="gray", font=('', 8))
        self.time_hint_label.pack(side=tk.LEFT, padx=(10, 0))
    
    def bind_events(self):
        """绑定事件"""
        # 回车键搜索
        self.search_entry.bind('<Return>', lambda e: self.do_search())

        # 时间输入框回车键触发过滤
        self.start_time_entry.bind('<Return>', lambda e: self.do_time_filter())
        self.end_time_entry.bind('<Return>', lambda e: self.do_time_filter())

        # 实时搜索（可选）
        # self.search_var.trace('w', self.on_search_text_changed)
    
    def set_search_callback(self, callback: Callable):
        """设置搜索回调函数"""
        self.search_callback = callback
    
    def do_search(self):
        """执行搜索"""
        keyword = self.search_var.get().strip()
        current_mode = self.search_mode_var.get()

        # 获取当前的扩展字幕行参数
        current_context_before = 0
        current_context_after = 0
        if self.context_enabled_var.get():
            try:
                current_context_before = self.context_before_var.get()
                current_context_after = self.context_after_var.get()
            except:
                pass

        # 当关键词、模式或扩展字幕行参数改变时，触发搜索
        if (keyword != self.current_keyword or
            current_mode != self.current_mode or
            current_context_before != self.current_context_before or
            current_context_after != self.current_context_after):

            # 更新缓存值
            self.current_keyword = keyword
            self.current_mode = current_mode
            self.current_context_before = current_context_before
            self.current_context_after = current_context_after

            if self.search_callback:
                self.search_callback(keyword)

            # 更新结果显示
            if keyword:
                self.result_label.config(text=f"搜索: '{keyword}'")
            else:
                self.result_label.config(text="")
    
    def clear_search(self):
        """清空搜索"""
        self.search_var.set("")
        self.current_keyword = ""
        self.current_mode = self.search_mode_var.get()  # 同步当前模式
        self.result_label.config(text="")

        if self.search_callback:
            self.search_callback("")
    
    def focus_search(self):
        """聚焦到搜索框"""
        self.search_entry.focus_set()
        self.search_entry.select_range(0, tk.END)
    
    def get_search_keyword(self) -> str:
        """获取当前搜索关键词"""
        return self.current_keyword
    
    def set_search_keyword(self, keyword: str):
        """设置搜索关键词"""
        self.search_var.set(keyword)
        self.current_keyword = keyword
    
    def get_search_options(self) -> dict:
        """获取搜索选项"""
        options = {
            'mode': self.search_mode_var.get()
        }

        # 添加上下文扩展参数
        if self.context_enabled_var.get():
            try:
                before = self.context_before_var.get()
                after = self.context_after_var.get()
                if 0 <= before <= 99 and 0 <= after <= 99:
                    options['context_before'] = before
                    options['context_after'] = after
            except:
                pass  # 输入无效时不添加上下文参数

        return options

    def get_search_mode(self) -> str:
        """获取搜索模式"""
        return self.search_mode_var.get()
    
    def set_result_info(self, info: str):
        """设置搜索结果信息"""
        self.result_label.config(text=info)
    
    def on_search_text_changed(self, *args):
        """搜索文本改变事件（实时搜索用）"""
        # 可以实现实时搜索功能
        pass

    def on_mode_changed(self):
        """搜索模式改变事件"""
        # 当搜索模式改变时，如果有搜索关键词，自动重新搜索
        if self.current_keyword:
            self.do_search()

    def on_context_enabled_changed(self):
        """上下文扩展启用状态改变事件"""
        self.context_enabled = self.context_enabled_var.get()
        # 如果有搜索关键词，自动重新搜索
        if self.current_keyword:
            self.do_search()

    def on_context_changed(self):
        """上下文行数改变事件"""
        # 如果启用了上下文扩展且有搜索关键词，自动重新搜索
        if self.context_enabled and self.current_keyword:
            # 验证输入值
            try:
                before = self.context_before_var.get()
                after = self.context_after_var.get()
                if 0 <= before <= 99 and 0 <= after <= 99:
                    self.context_before = before
                    self.context_after = after
                    self.do_search()
            except:
                pass  # 输入无效时不触发搜索

    def _create_tooltip(self, widget, text):
        """为控件创建 tooltip 提示"""
        def on_enter(event):
            # 创建提示窗口
            tooltip = tk.Toplevel()
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")

            label = tk.Label(
                tooltip,
                text=text,
                background="lightyellow",
                relief=tk.SOLID,
                borderwidth=1,
                font=('', 9)
            )
            label.pack()

            # 保存引用
            widget._tooltip = tooltip

        def on_leave(event):
            # 销毁提示窗口
            if hasattr(widget, '_tooltip'):
                widget._tooltip.destroy()
                del widget._tooltip

        widget.bind('<Enter>', on_enter)
        widget.bind('<Leave>', on_leave)

    def do_time_filter(self):
        """执行时间区间过滤"""
        start_time_str = self.start_time_var.get().strip()
        end_time_str = self.end_time_var.get().strip()

        # 验证时间格式并转换为秒数
        start_time_seconds = None
        end_time_seconds = None

        if start_time_str:
            start_time_seconds = self.parse_time_to_seconds(start_time_str)
            if start_time_seconds is None:
                from tkinter import messagebox
                messagebox.showerror(
                    "时间格式错误",
                    f"开始时间格式错误\n\n正确格式: HH:MM:SS,mmm\n示例: 00:00:05,000"
                )
                return

        if end_time_str:
            end_time_seconds = self.parse_time_to_seconds(end_time_str)
            if end_time_seconds is None:
                from tkinter import messagebox
                messagebox.showerror(
                    "时间格式错误",
                    f"结束时间格式错误\n\n正确格式: HH:MM:SS,mmm\n示例: 00:00:10,000"
                )
                return

        # 验证时间范围合理性
        if start_time_seconds is not None and end_time_seconds is not None:
            if start_time_seconds >= end_time_seconds:
                from tkinter import messagebox
                messagebox.showerror(
                    "时间范围错误",
                    "开始时间必须小于结束时间"
                )
                return

        # 执行过滤（通过搜索回调）
        if self.search_callback:
            # 构建时间过滤关键词（特殊格式）
            filter_keyword = f"__TIME_FILTER__:{start_time_seconds or 0}:{end_time_seconds or float('inf')}"
            self.search_callback(filter_keyword)

            # 更新结果显示
            if start_time_str or end_time_str:
                time_range_text = ""
                if start_time_str and end_time_str:
                    time_range_text = f"{start_time_str} ~ {end_time_str}"
                elif start_time_str:
                    time_range_text = f">= {start_time_str}"
                else:
                    time_range_text = f"<= {end_time_str}"
                self.result_label.config(text=f"时间过滤: {time_range_text}")
            else:
                self.result_label.config(text="")

    def clear_time_filter(self):
        """清空时间过滤"""
        self.start_time_var.set("")
        self.end_time_var.set("")
        self.result_label.config(text="")

        # 重新加载所有数据
        if self.search_callback:
            self.search_callback("")

    def parse_time_to_seconds(self, time_str: str) -> Optional[float]:
        """解析时间字符串为秒数

        Args:
            time_str: 时间字符串，格式: HH:MM:SS,mmm

        Returns:
            秒数（浮点数），格式错误返回None
        """
        import re

        # 时间格式正则：HH:MM:SS,mmm
        pattern = r'^(\d{2}):(\d{2}):(\d{2}),(\d{3})$'
        match = re.match(pattern, time_str)

        if not match:
            return None

        try:
            hours = int(match.group(1))
            minutes = int(match.group(2))
            seconds = int(match.group(3))
            milliseconds = int(match.group(4))

            # 验证范围
            if minutes >= 60 or seconds >= 60 or milliseconds >= 1000:
                return None

            # 转换为总秒数
            total_seconds = hours * 3600 + minutes * 60 + seconds + milliseconds / 1000.0
            return total_seconds

        except ValueError:
            return None

    def get_time_filter(self) -> tuple:
        """获取当前时间过滤条件

        Returns:
            (start_seconds, end_seconds) 元组，未设置的返回None
        """
        start_time_str = self.start_time_var.get().strip()
        end_time_str = self.end_time_var.get().strip()

        start_seconds = self.parse_time_to_seconds(start_time_str) if start_time_str else None
        end_seconds = self.parse_time_to_seconds(end_time_str) if end_time_str else None

        return (start_seconds, end_seconds)

