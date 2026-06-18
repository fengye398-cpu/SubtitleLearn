import tkinter as tk
from tkinter import ttk, messagebox
from typing import List, Callable, Optional

from database.models import SubtitleSegment
from utils.format_utils import FormatUtils
from config.settings import app_config

class SubtitleListWidget(ttk.Frame):
    """字幕列表组件"""
    
    def __init__(self, parent):
        super().__init__(parent)

        self.segments: List[SubtitleSegment] = []
        self.selected_segments: List[SubtitleSegment] = []

        # 用字典存储item_id到segment的映射
        self.item_segment_map = {}

        # 项目全选模式相关变量
        self.project_select_mode = False  # 是否启用了项目全选模式
        self.project_select_total = 0  # 项目全选的总字幕数

        # 主窗口引用（由外部设置）
        self.main_window = None

        # 回调函数
        self.double_click_callback: Optional[Callable] = None
        self.selection_callback: Optional[Callable] = None
        self.page_change_callback: Optional[Callable] = None
        self.play_video_callback: Optional[Callable] = None  # 播放视频回调

        # 分页信息
        self.current_page = 0
        self.total_pages = 0
        self.items_per_page = app_config.get('pagination.items_per_page', 30)
        self.total_items = 0

        # 记录当前生效的每页显示数量
        self.current_items_per_page = self.items_per_page

        self.create_widgets()
        self.bind_events()
    
    def create_widgets(self):
        """创建组件"""
        # 创建工具栏
        self.create_toolbar()
        
        # 创建列表
        self.create_list()
        
        # 创建分页控件
        self.create_pagination()
    
    def create_toolbar(self):
        """创建工具栏"""
        toolbar_frame = ttk.Frame(self)
        toolbar_frame.pack(fill=tk.X, pady=(0, 5))
        
        # 选择操作
        ttk.Button(toolbar_frame, text="单页全选", command=self.select_all).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar_frame, text="项目全选", command=self.select_all_in_project).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar_frame, text="取消全选", command=self.select_none).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar_frame, text="反选", command=self.select_inverse).pack(side=tk.LEFT, padx=(0, 5))

        # 每页显示数量（使用 tk.Spinbox 支持背景颜色修改）
        ttk.Label(toolbar_frame, text="每页显示:").pack(side=tk.LEFT, padx=(0, 5))

        self.items_per_page_var = tk.StringVar(value=str(self.items_per_page))
        self.items_spinbox = tk.Spinbox(
            toolbar_frame,
            from_=30,
            to=5000,
            increment=10,
            textvariable=self.items_per_page_var,
            width=8,
            command=self.on_items_per_page_changed,
            bg='white',
            relief='solid',
            bd=1
        )
        self.items_spinbox.pack(side=tk.LEFT, padx=(0, 5))
        self.items_spinbox.bind('<Return>', lambda e: self.on_items_per_page_changed(e))
        self.items_spinbox.bind('<FocusOut>', lambda e: self.on_items_per_page_changed(e))

        # 监听输入框内容变化，显示视觉提示
        self.items_per_page_var.trace('w', self.on_items_per_page_input_changed)

        # 分隔符
        ttk.Separator(toolbar_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)

        # 播放模式选择
        ttk.Label(toolbar_frame, text="播放模式:").pack(side=tk.LEFT, padx=(0, 5))
        self.play_mode_var = tk.StringVar(value="片段播放")
        play_mode_combo = ttk.Combobox(
            toolbar_frame,
            textvariable=self.play_mode_var,
            values=["片段播放", "连续播放"],
            state="readonly",
            width=10
        )
        play_mode_combo.pack(side=tk.LEFT, padx=(0, 5))
        play_mode_combo.bind('<<ComboboxSelected>>', self.on_play_mode_changed)

        # 提取音频按钮
        ttk.Button(toolbar_frame, text="提取音频", command=self.on_extract_audio_clicked).pack(side=tk.LEFT, padx=(0, 5))

        # 字幕功能按钮
        ttk.Button(toolbar_frame, text="字幕功能", command=self.on_subtitle_function_clicked).pack(side=tk.LEFT, padx=(0, 5))

        # 帮助按钮
        ttk.Button(toolbar_frame, text="帮助", command=self.on_help_clicked).pack(side=tk.LEFT, padx=(0, 5))

        # 右侧信息
        self.info_label = ttk.Label(toolbar_frame, text="")
        self.info_label.pack(side=tk.RIGHT)
    
    def create_list(self):
        """创建列表"""
        # 创建框架
        list_frame = ttk.Frame(self)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建Treeview（添加项目名称列和双语字幕列）
        columns = ('index', 'start_time', 'end_time', 'duration', 'project_name', 'text_primary', 'text_secondary')
        self.tree = ttk.Treeview(list_frame, columns=columns, show='headings', selectmode='extended')

        # 设置列标题和宽度
        self.tree.heading('index', text='序号')
        self.tree.heading('start_time', text='开始时间')
        self.tree.heading('end_time', text='结束时间')
        self.tree.heading('duration', text='时长')
        self.tree.heading('project_name', text='项目名称')
        self.tree.heading('text_primary', text='原文')
        self.tree.heading('text_secondary', text='译文')

        # 设置默认列宽
        default_widths = {
            'index': 60,
            'start_time': 115,      # 从100增加到115，适配毫秒显示 (HH:MM:SS.mmm)
            'end_time': 115,        # 从100增加到115，适配毫秒显示
            'duration': 95,         # 从80增加到95，适配毫秒显示
            'project_name': 120,
            'text_primary': 300,
            'text_secondary': 300
        }

        # 加载保存的列宽
        saved_widths = app_config.get_column_widths()

        for col in columns:
            width = saved_widths.get(col, default_widths.get(col, 100))
            anchor = tk.CENTER if col in ('index', 'start_time', 'end_time', 'duration') else tk.W
            self.tree.column(col, width=width, anchor=anchor)

        # 创建滚动条
        v_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        h_scrollbar = ttk.Scrollbar(list_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        
        self.tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        # 布局
        self.tree.grid(row=0, column=0, sticky='nsew')
        v_scrollbar.grid(row=0, column=1, sticky='ns')
        h_scrollbar.grid(row=1, column=0, sticky='ew')
        
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
    
    def create_pagination(self):
        """创建分页控件"""
        pagination_frame = ttk.Frame(self)
        pagination_frame.pack(fill=tk.X, pady=(5, 0))
        
        # 左侧：页面导航
        nav_frame = ttk.Frame(pagination_frame)
        nav_frame.pack(side=tk.LEFT)
        
        ttk.Button(nav_frame, text="首页", command=self.go_first_page).pack(side=tk.LEFT, padx=(0, 2))
        ttk.Button(nav_frame, text="上页", command=self.go_prev_page).pack(side=tk.LEFT, padx=(0, 2))
        
        # 页码输入
        ttk.Label(nav_frame, text="第").pack(side=tk.LEFT, padx=(10, 2))
        
        self.page_var = tk.StringVar(value="1")
        page_entry = ttk.Entry(nav_frame, textvariable=self.page_var, width=6)
        page_entry.pack(side=tk.LEFT, padx=(0, 2))
        page_entry.bind('<Return>', self.on_page_entry_return)
        
        self.page_info_label = ttk.Label(nav_frame, text="/ 1 页")
        self.page_info_label.pack(side=tk.LEFT, padx=(2, 10))
        
        ttk.Button(nav_frame, text="下页", command=self.go_next_page).pack(side=tk.LEFT, padx=(2, 0))
        ttk.Button(nav_frame, text="末页", command=self.go_last_page).pack(side=tk.LEFT, padx=(2, 0))
        
        # 右侧：统计信息
        self.stats_label = ttk.Label(pagination_frame, text="")
        self.stats_label.pack(side=tk.RIGHT)
    
    def bind_events(self):
        """绑定事件"""
        self.tree.bind('<Double-1>', self.on_double_click)
        self.tree.bind('<<TreeviewSelect>>', self.on_selection_changed)
        self.tree.bind('<Button-3>', self.on_right_click)  # 右键菜单

        # 快捷键绑定
        self.tree.bind('<Control-a>', self.on_select_all_hotkey)  # Ctrl+A 单页全选
        self.tree.bind('<Escape>', self.on_escape_hotkey)  # ESC 退出选择

        # 编辑相关变量
        self.editing_item = None
        self.editing_column = None
        self.edit_entry = None
    
    def set_double_click_callback(self, callback: Callable):
        """设置双击回调"""
        self.double_click_callback = callback
    
    def set_selection_callback(self, callback: Callable):
        """设置选择回调"""
        self.selection_callback = callback

    def set_page_change_callback(self, callback: Callable):
        """设置页面改变回调"""
        self.page_change_callback = callback
    
    def load_segments(self, segments: List[SubtitleSegment]):
        """加载字幕片段"""
        # 加载新数据时清除项目全选模式（因为可能是搜索或切换项目）
        # 但是如果是翻页操作，项目全选模式应该保持
        # 所以这里不清除，而是在主窗口的项目切换和搜索时手动清除
        self.segments = segments
        self.refresh_list()

    def clear_project_select_mode(self):
        """清除项目全选模式（供外部调用）"""
        self.project_select_mode = False
        self.project_select_total = 0
        print("[项目全选] 已清除项目全选模式")
    
    def refresh_list(self):
        """刷新列表显示"""
        from database.manager import db_manager
        from utils.file_utils import FileUtils

        # 清空现有项目和映射
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.item_segment_map.clear()

        # 缓存项目类型，避免重复查询数据库
        project_type_cache = {}

        # 添加新项目
        for segment in self.segments:
            start_time = FormatUtils.format_time_with_ms(segment.start_time)
            end_time = FormatUtils.format_time_with_ms(segment.end_time)
            duration = FormatUtils.format_time_with_ms(segment.duration)

            # 获取项目名称
            project_name = getattr(segment, 'project_name', f"项目{segment.project_id}")

            # 判断项目类型（使用缓存优化性能）
            project_id = segment.project_id
            if project_id not in project_type_cache:
                # 查询项目信息
                project = db_manager.get_project(project_id)
                if project and project.video_path:
                    # 判断是音频还是视频
                    is_audio = FileUtils.is_audio_file(project.video_path)
                    project_type_cache[project_id] = "[音频]" if is_audio else "[视频]"
                else:
                    # 项目不存在或路径无效
                    project_type_cache[project_id] = "[未知]"

            # 添加类型前缀到项目名称
            media_type = project_type_cache[project_id]
            project_name_with_type = f"{media_type} {project_name}"

            # 显示双语字幕
            text_primary = FormatUtils.truncate_text(segment.text_primary or segment.text, 100)
            text_secondary = FormatUtils.truncate_text(segment.text_secondary or "", 100) if segment.text_secondary else ""

            item_id = self.tree.insert('', tk.END, values=(
                segment.index_num,
                start_time,
                end_time,
                duration,
                project_name_with_type,  # 使用带类型标签的项目名称
                text_primary,
                text_secondary
            ))

            # 使用字典存储segment对象
            self.item_segment_map[item_id] = segment

        # 如果启用了项目全选模式，自动选中当前页的所有项
        if self.project_select_mode:
            self.tree.selection_set(self.tree.get_children())
            print(f"[项目全选] 刷新列表后自动选中当前页所有项")
    
    def update_pagination(self, current_page: int, total_items: int):
        """更新分页信息"""
        self.current_page = current_page
        self.total_items = total_items
        self.total_pages = max(1, (total_items + self.items_per_page - 1) // self.items_per_page)
        
        # 更新显示
        self.page_var.set(str(current_page + 1))
        self.page_info_label.config(text=f"/ {self.total_pages} 页")
        
        start_item = current_page * self.items_per_page + 1
        end_item = min((current_page + 1) * self.items_per_page, total_items)
        
        self.stats_label.config(text=f"显示 {start_item}-{end_item} / 共 {total_items} 项")
        self.info_label.config(text=f"已选择 {len(self.selected_segments)} 项")
    
    def clear(self):
        """清空列表"""
        # 清空时也要清除项目全选模式
        self.project_select_mode = False
        self.project_select_total = 0

        self.segments = []
        self.selected_segments = []
        self.refresh_list()
        self.update_pagination(0, 0)

    # 事件处理方法
    def on_double_click(self, event):
        """双击事件"""
        item = self.tree.selection()[0] if self.tree.selection() else None
        if item and self.double_click_callback:
            segment = self.get_segment_by_item(item)
            if segment:
                self.double_click_callback(segment)

    def on_selection_changed(self, event):
        """选择改变事件"""
        selected_items = self.tree.selection()
        self.selected_segments = []

        for item in selected_items:
            segment = self.get_segment_by_item(item)
            if segment:
                self.selected_segments.append(segment)

        # 更新信息显示
        # 如果是项目全选模式，显示总数；否则显示当前选中数
        if self.project_select_mode:
            self.info_label.config(text=f"已选择 {self.project_select_total} 项")
        else:
            self.info_label.config(text=f"已选择 {len(self.selected_segments)} 项")

        # 调用回调
        if self.selection_callback:
            self.selection_callback(self.selected_segments)

    def on_items_per_page_input_changed(self, *args):
        """输入框内容变化时的处理（显示视觉提示）"""
        try:
            input_value = self.items_per_page_var.get().strip()
            if not input_value:
                # 空值，显示警告颜色
                self.items_spinbox.config(bg='#ffff00')  # 黄色
                return

            # 尝试解析输入值
            try:
                input_count = int(input_value)
                # 检查是否与当前生效值不同
                if input_count != self.current_items_per_page:
                    # 未生效，显示黄色背景
                    self.items_spinbox.config(bg='#ffff00')  # 黄色
                else:
                    # 已生效，恢复默认背景
                    self.items_spinbox.config(bg='white')
            except ValueError:
                # 无效输入，显示警告颜色
                self.items_spinbox.config(bg='#FFCDD2')  # 淡红色
        except Exception as e:
            print(f"每页显示输入变化处理失败: {e}")

    def on_play_mode_changed(self, event=None):
        """播放模式改变事件"""
        play_mode = self.play_mode_var.get()
        print(f"[播放模式] 切换为: {play_mode}")
        # 播放模式改变只是修改选项，实际播放时才会使用

    def get_play_mode(self) -> str:
        """获取当前播放模式"""
        return self.play_mode_var.get()

    def on_extract_audio_clicked(self):
        """提取音频按钮点击事件"""
        if self.main_window:
            self.main_window.show_video_to_audio_dialog()

    def on_subtitle_function_clicked(self):
        """字幕功能按钮点击事件"""
        if self.main_window:
            self.main_window.show_subtitle_tools_dialog()

    def on_help_clicked(self):
        """帮助按钮点击事件"""
        if self.main_window:
            self.main_window.show_help_dialog()

    def on_items_per_page_changed(self, event=None):
        """每页显示数量改变（应用修改）"""
        try:
            new_items_per_page = int(self.items_per_page_var.get())

            # 验证范围
            if new_items_per_page < 10:
                new_items_per_page = 10
                self.items_per_page_var.set('10')
            elif new_items_per_page > 5000:
                new_items_per_page = 5000
                self.items_per_page_var.set('5000')

            # 检查是否真的改变了
            if new_items_per_page == self.current_items_per_page:
                # 没有变化，恢复背景色即可
                self.items_spinbox.config(bg='white')
                return

            # 应用修改
            self.items_per_page = new_items_per_page
            self.current_items_per_page = new_items_per_page
            app_config.set('pagination.items_per_page', new_items_per_page)

            # 恢复背景色
            self.items_spinbox.config(bg='white')

            # 触发重新加载数据
            if self.page_change_callback:
                self.page_change_callback(0, new_items_per_page)

        except ValueError:
            # 输入无效，重置为当前生效值
            self.items_per_page_var.set(str(self.current_items_per_page))
            self.items_spinbox.config(bg='white')

    def on_right_click(self, event):
        """右键菜单事件"""
        # 获取点击的项目和列
        item = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)

        if not item:
            return

        # 如果右键点击的项目不在当前选中列表中，才选中该项目
        # 这样可以保持多选状态
        selected_items = self.tree.selection()
        if item not in selected_items:
            self.tree.selection_set(item)

        # 创建右键菜单
        context_menu = tk.Menu(self, tearoff=0)

        # 原文、译文、时长、开始时间、结束时间、项目名称列可以编辑（只读复制）
        if column in ('#2', '#3', '#4', '#5', '#6', '#7'):  # start_time, end_time, duration, project_name, text_primary, text_secondary
            if column == '#2':
                column_name = 'start_time'
                display_name = '开始'
            elif column == '#3':
                column_name = 'end_time'
                display_name = '结束'
            elif column == '#4':
                column_name = 'duration'
                display_name = '时长'
            elif column == '#5':
                column_name = 'project_name'
                display_name = '名称'
            elif column == '#6':
                column_name = 'text_primary'
                display_name = '原文'
            else:  # column == '#7'
                column_name = 'text_secondary'
                display_name = '译文'

            context_menu.add_command(
                label=f"编辑{display_name}",
                command=lambda: self.start_edit(item, column_name)
            )

        context_menu.add_separator()
        context_menu.add_command(label="播放视频", command=self._on_play_video_from_menu)
        context_menu.add_command(label="调整时间轴", command=lambda: self.edit_timeline(item))

        # 添加队列相关菜单（新增）
        context_menu.add_separator()
        context_menu.add_command(label="快速添加", command=lambda: self.quick_add_to_queue(item))
        context_menu.add_command(label="配置添加", command=lambda: self.config_add_to_queue(item))

        # 删除菜单
        context_menu.add_separator()
        context_menu.add_command(label="删除", command=self._on_delete_from_menu)

        # 显示菜单
        try:
            context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            context_menu.grab_release()

    def start_edit(self, item, column_name):
        """开始编辑字幕（支持选择复制，禁用删除粘贴）"""
        if self.editing_item:
            self.cancel_edit()

        # 获取当前值
        segment = self.item_segment_map.get(item)
        if not segment:
            return

        # 根据列名获取对应的值
        if column_name in ('start_time', 'end_time', 'duration'):
            # 时间字段需要格式化显示
            time_value = getattr(segment, column_name, 0)
            current_value = FormatUtils.format_time_with_ms(time_value)
        elif column_name == 'project_name':
            # 项目名称需要从树形控件中获取显示值（包含类型前缀）
            values = self.tree.item(item, 'values')
            # project_name 是第5列（索引4）
            current_value = values[4] if len(values) > 4 else ''
        else:
            # text_primary, text_secondary 直接获取
            current_value = getattr(segment, column_name, '') or ''

        # 获取单元格位置
        bbox = self.tree.bbox(item, column_name)
        if not bbox:
            return

        # 创建编辑框（允许选择但禁用修改）
        self.editing_item = item
        self.editing_column = column_name

        self.edit_entry = tk.Entry(self.tree)
        self.edit_entry.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])
        self.edit_entry.insert(0, current_value)
        self.edit_entry.focus()

        # 绑定事件
        self.edit_entry.bind('<Escape>', self.cancel_edit)
        self.edit_entry.bind('<FocusOut>', self.cancel_edit)
        self.edit_entry.bind('<Return>', self.cancel_edit)

        # 禁用删除和粘贴功能
        def disable_modify(event):
            # 禁用删除键
            if event.keysym in ['Delete', 'BackSpace']:
                return "break"
            # 禁用粘贴快捷键
            if event.state & 0x4 and event.keysym.lower() == 'v':  # Ctrl+V
                return "break"
            # 禁用剪切快捷键
            if event.state & 0x4 and event.keysym.lower() == 'x':  # Ctrl+X
                return "break"
            # 允许复制快捷键
            if event.state & 0x4 and event.keysym.lower() == 'c':  # Ctrl+C
                return None
            # 允许全选快捷键
            if event.state & 0x4 and event.keysym.lower() == 'a':  # Ctrl+A
                return None
            # 禁用其他可能的修改操作
            if event.char and event.char.isprintable():
                return "break"
            return None

        self.edit_entry.bind('<Key>', disable_modify)

        # 右键菜单只显示复制选项
        def show_copy_menu(event):
            copy_menu = tk.Menu(self, tearoff=0)
            copy_menu.add_command(label="复制", command=self.copy_selected_text)
            try:
                copy_menu.tk_popup(event.x_root, event.y_root)
            finally:
                copy_menu.grab_release()

        self.edit_entry.bind('<Button-3>', show_copy_menu)

    def copy_selected_text(self):
        """复制选中的文本到剪贴板"""
        if self.edit_entry:
            try:
                # 获取选中的文本
                if self.edit_entry.selection_present():
                    selected_text = self.edit_entry.selection_get()
                else:
                    # 如果没有选中文本，复制全部文本
                    selected_text = self.edit_entry.get()

                self.clipboard_clear()
                self.clipboard_append(selected_text)
                print(f"已复制到剪贴板: {selected_text}")
            except Exception as e:
                print(f"复制失败: {e}")



    def cancel_edit(self, event=None):
        """取消编辑"""
        if self.edit_entry:
            self.edit_entry.destroy()
            self.edit_entry = None

        self.editing_item = None
        self.editing_column = None

    def edit_timeline(self, item):
        """编辑时间轴"""
        segment = self.item_segment_map.get(item)
        if segment:
            print(f"[字幕列表] 开始编辑时间轴，片段ID: {segment.id}")

            # 尝试调用主窗口的时间轴编辑方法
            main_window = None

            # 方法1：通过 master.master 查找主窗口
            if hasattr(self.master, 'master') and hasattr(self.master.master, 'edit_timeline'):
                main_window = self.master.master
                print("[字幕列表] 找到主窗口 (方法1)")

            # 方法2：通过 winfo_toplevel 查找主窗口
            elif hasattr(self.winfo_toplevel(), 'edit_timeline'):
                main_window = self.winfo_toplevel()
                print("[字幕列表] 找到主窗口 (方法2)")

            # 方法3：遍历所有父级窗口查找
            else:
                parent = self.master
                while parent and not hasattr(parent, 'edit_timeline'):
                    parent = getattr(parent, 'master', None)
                if parent and hasattr(parent, 'edit_timeline'):
                    main_window = parent
                    print("[字幕列表] 找到主窗口 (方法3)")

            if main_window:
                print("[字幕列表] 调用主窗口的 edit_timeline 方法")
                main_window.edit_timeline(segment)
            else:
                print("[字幕列表] 未找到主窗口，直接创建对话框并处理刷新")
                # 如果找不到主窗口，直接创建对话框并处理刷新
                from ui.dialogs.timeline_editor_dialog import TimelineEditorDialog
                dialog = TimelineEditorDialog(self.winfo_toplevel(), segment)

                # 等待对话框关闭
                self.winfo_toplevel().wait_window(dialog.dialog)

                # 检查刷新标记并刷新列表
                if hasattr(dialog.dialog, 'needs_refresh') and dialog.dialog.needs_refresh:
                    print("[字幕列表] 检测到需要刷新，重新加载数据")
                    # 触发页面刷新回调
                    if hasattr(self, 'page_change_callback') and self.page_change_callback:
                        self.page_change_callback(self.current_page, self.items_per_page)
                    else:
                        print("[字幕列表] 警告：没有找到页面刷新回调")

    def play_selected_segment(self, item):
        """播放选中的片段"""
        segment = self.item_segment_map.get(item)
        if segment and self.double_click_callback:
            self.double_click_callback(segment)

    def on_page_entry_return(self, event):
        """页码输入回车事件"""
        try:
            page = int(self.page_var.get()) - 1
            if 0 <= page < self.total_pages:
                self.go_to_page(page)
            else:
                self.page_var.set(str(self.current_page + 1))
        except ValueError:
            self.page_var.set(str(self.current_page + 1))

    # 选择操作方法
    def select_all(self):
        """单页全选"""
        self.tree.selection_set(self.tree.get_children())

    def select_all_in_project(self):
        """项目全选 - 选中整个项目的所有字幕"""
        # 获取主窗口以访问current_project
        main_window = self._get_main_window()
        if not main_window:
            messagebox.showwarning("警告", "无法获取主窗口信息")
            return

        from database.manager import db_manager

        # 根据当前项目获取总数
        if main_window.current_project is None:
            # "全部视频" - 获取所有字幕总数
            total_count = db_manager.get_total_segment_count()
            project_name = "全部视频"
        else:
            # 具体项目 - 获取该项目的字幕总数
            total_count = db_manager.get_segment_count(main_window.current_project.id)
            project_name = main_window.current_project.name

        if total_count == 0:
            messagebox.showinfo("提示", f"{project_name} 中没有字幕")
            return

        # 启用项目全选模式
        self.project_select_mode = True
        self.project_select_total = total_count

        # 选中当前页面的所有项
        self.tree.selection_set(self.tree.get_children())

        # 更新显示（显示真实总数）
        self.info_label.config(text=f"已选择 {total_count} 项")

        print(f"[项目全选] 已启用项目全选模式：{project_name}，总计 {total_count} 项")

    def _get_main_window(self):
        """获取主窗口对象"""
        # 方法0：优先使用直接引用
        if self.main_window is not None:
            return self.main_window

        # 方法1：通过 master.master 查找主窗口
        if hasattr(self.master, 'master') and hasattr(self.master.master, 'current_project'):
            return self.master.master

        # 方法2：通过 winfo_toplevel 查找主窗口
        toplevel = self.winfo_toplevel()
        if hasattr(toplevel, 'current_project'):
            return toplevel

        # 方法3：遍历所有父级窗口查找
        parent = self.master
        max_depth = 10  # 防止无限循环
        depth = 0
        while parent and depth < max_depth:
            if hasattr(parent, 'current_project'):
                return parent
            parent = getattr(parent, 'master', None)
            depth += 1

        return None

    def select_none(self):
        """取消全选"""
        # 清除项目全选模式
        self.project_select_mode = False
        self.project_select_total = 0

        # 取消树形控件的选择
        self.tree.selection_remove(self.tree.get_children())

    def on_select_all_hotkey(self, event):
        """Ctrl+A 快捷键处理：单页全选"""
        self.select_all()
        return 'break'  # 阻止事件传播

    def on_escape_hotkey(self, event):
        """ESC 快捷键处理：退出单页全选"""
        self.select_none()
        return 'break'  # 阻止事件传播

    def select_inverse(self):
        """反选"""
        # 反选操作会清除项目全选模式
        self.project_select_mode = False
        self.project_select_total = 0

        all_items = self.tree.get_children()
        selected_items = set(self.tree.selection())

        # 取消当前选择
        self.tree.selection_remove(all_items)

        # 选择未选中的项目
        for item in all_items:
            if item not in selected_items:
                self.tree.selection_add(item)

    # 分页操作方法
    def go_first_page(self):
        """跳转到首页"""
        if self.current_page > 0:
            self.go_to_page(0)

    def go_prev_page(self):
        """上一页"""
        if self.current_page > 0:
            self.go_to_page(self.current_page - 1)

    def go_next_page(self):
        """下一页"""
        if self.current_page < self.total_pages - 1:
            self.go_to_page(self.current_page + 1)

    def go_last_page(self):
        """跳转到末页"""
        if self.current_page < self.total_pages - 1:
            self.go_to_page(self.total_pages - 1)

    def go_to_page(self, page: int):
        """跳转到指定页面"""
        if 0 <= page < self.total_pages:
            if self.page_change_callback:
                # 触发页面改变回调，传递页码和每页数量
                self.page_change_callback(page, self.items_per_page)

    # 工具方法
    def get_segment_by_item(self, item) -> Optional[SubtitleSegment]:
        """根据树项目获取对应的片段对象"""
        return self.item_segment_map.get(item)

    def get_selected_segments(self) -> List[SubtitleSegment]:
        """获取选中的片段

        如果启用了项目全选模式，返回整个项目的所有片段
        否则返回当前选中的片段
        """
        if self.project_select_mode:
            # 项目全选模式：从数据库获取所有片段
            from database.manager import db_manager

            # 获取主窗口以访问current_project
            main_window = self._get_main_window()
            if not main_window:
                print("[警告] 无法获取主窗口信息，返回当前选中片段")
                return self.selected_segments.copy()

            # 根据当前项目获取所有片段
            if main_window.current_project is None:
                # "全部视频" - 获取所有字幕
                all_segments = db_manager.get_all_segments(offset=0, limit=100000)
                print(f"[项目全选] 获取全部视频的所有片段：{len(all_segments)} 项")
            else:
                # 具体项目 - 获取该项目的所有字幕
                all_segments = db_manager.get_segments_by_project(
                    main_window.current_project.id,
                    offset=0,
                    limit=100000
                )
                print(f"[项目全选] 获取项目 {main_window.current_project.name} 的所有片段：{len(all_segments)} 项")

            return all_segments
        else:
            # 普通模式：返回当前页面选中的片段
            return self.selected_segments.copy()

    def get_all_segments(self) -> List[SubtitleSegment]:
        """获取所有片段"""
        return self.segments.copy()

    def quick_add_to_queue(self, item):
        """快速添加到队列（使用默认配置）- 支持项目全选"""
        # 使用统一的获取方法（自动处理项目全选和单页全选）
        segments = self.get_selected_segments()

        # 如果没有选中任何片段，则只添加右键点击的项
        if not segments:
            segment = self.get_segment_by_item(item)
            if segment:
                segments = [segment]

        if not segments:
            messagebox.showwarning("警告", "没有选择任何片段")
            return

        # 触发快速添加回调
        if hasattr(self, 'quick_add_callback') and self.quick_add_callback:
            self.quick_add_callback(segments)

    def config_add_to_queue(self, item):
        """配置后添加到队列（打开配置窗口）- 支持项目全选"""
        # 使用统一的获取方法（自动处理项目全选和单页全选）
        segments = self.get_selected_segments()

        # 如果没有选中任何片段，则只添加右键点击的项
        if not segments:
            segment = self.get_segment_by_item(item)
            if segment:
                segments = [segment]

        if not segments:
            messagebox.showwarning("警告", "没有选择任何片段")
            return

        # 触发配置添加回调
        if hasattr(self, 'config_add_callback') and self.config_add_callback:
            self.config_add_callback(segments)

    def _on_play_video_from_menu(self):
        """从右键菜单播放视频"""
        if hasattr(self, 'play_video_callback') and self.play_video_callback:
            self.play_video_callback()

    def _on_delete_from_menu(self):
        """从右键菜单删除"""
        if self.main_window:
            self.main_window.delete_selected()
