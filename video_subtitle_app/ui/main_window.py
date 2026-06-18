import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
from typing import Optional, List
from pathlib import Path

# 尝试导入拖拽支持库
try:
    from tkinterdnd2 import TkinterDnD
    DRAG_DROP_AVAILABLE = True
    print("[OK] 主窗口: tkinterdnd2 导入成功")
except ImportError as e:
    DRAG_DROP_AVAILABLE = False
    print(f"[ERROR] 主窗口: tkinterdnd2 导入失败: {e}")

from database.manager import db_manager
from database.models import Project
from core.enhanced_video_processor import EnhancedVideoProcessor
from core.player_factory import get_player, reset_player, PlayerFactory
from core.exporter import exporter
from config.settings import app_config
from core.merger import standalone_merge

# 导入队列管理器
# 强制使用原版队列管理器
print("[INFO] 开始导入原版队列管理器...")
try:
    print("[INFO] 导入 ExportQueue...")
    from core.export_queue import ExportQueue
    print("[INFO] 导入 QueueProcessor...")
    from core.export_processor import QueueProcessor
    print("[INFO] 导入 QueueManagerDialog...")
    from ui.dialogs.queue_manager_dialog import QueueManagerDialog
    print("[OK] 使用原版队列管理器")
    QUEUE_AVAILABLE = True
    USE_SIMPLE_QUEUE = False
except ImportError as e:
    import traceback
    print(f"[ERROR] 原版队列管理器导入失败: {e}")
    print(f"[DEBUG] 详细错误:\n{traceback.format_exc()}")
    print("[ERROR] 队列功能不可用")
    QUEUE_AVAILABLE = False
    USE_SIMPLE_QUEUE = False
    ExportQueue = None
    QueueProcessor = None
    QueueManagerDialog = None

from utils.format_utils import FormatUtils

from ui.components.subtitle_list import SubtitleListWidget
from ui.components.search_bar import SearchBarWidget
from ui.components.progress_dialog import ProgressDialog
from ui.dialogs.import_dialog import ImportDialog
from ui.dialogs.integrated_export_dialog import IntegratedExportDialog

# 导入图标和帮助管理器
try:
    from icon_manager import set_window_icon, get_app_info
    from help_manager import show_help
    ICON_AVAILABLE = True
except ImportError:
    ICON_AVAILABLE = False
    def set_window_icon(window):
        pass
    def get_app_info():
        return {'name': 'SubtitleLearn', 'version': '1.0.0'}
    def show_help(parent=None):
        messagebox.showinfo("帮助", "帮助功能暂不可用")
from ui.dialogs.integrated_merge_dialog import IntegratedMergeDialog
from ui.dialogs.storage_dialog import StorageDialog
from ui.dialogs.import_result_dialog import show_import_result
from ui.dialogs.video_to_audio_dialog import VideoToAudioDialog

class MainWindow:
    """主窗口类"""

    def __init__(self):
        # 设置队列管理器可用性标志
        self.QUEUE_AVAILABLE = QUEUE_AVAILABLE
        self.USE_SIMPLE_QUEUE = USE_SIMPLE_QUEUE

        # 根据是否支持拖拽来创建不同的根窗口
        if DRAG_DROP_AVAILABLE:
            self.root = TkinterDnD.Tk()
            print(f"[OK] 主窗口: 使用 TkinterDnD.Tk，类型: {type(self.root).__name__}")
            print(f"[OK] 主窗口: 拖拽方法可用: {hasattr(self.root, 'drop_target_register')}")
        else:
            self.root = tk.Tk()
            print("[WARN] 主窗口: 使用普通 tk.Tk，拖拽功能不可用")

        self.current_project: Optional[Project] = None
        self.video_processor = EnhancedVideoProcessor()

        # 初始化播放器
        self.player = get_player()

        # 搜索状态（用于翻页时保持搜索）
        self.search_state = {
            'keyword': '',
            'mode': 'fuzzy',
            'context_before': 0,
            'context_after': 0,
            'filter_type': None,  # None, 'text', 'duration', 'time_range'
            'filter_params': None
        }

        # 临时字幕文件列表（用于连续播放时的清理）
        self.temp_subtitle_files = []

        # 窗口引用（用于防止多开）
        self.help_window = None
        self.integrated_merge_window = None
        self.integrated_export_window = None
        self.import_dialog_window = None
        self.subtitle_tools_window = None
        self.video_to_audio_window = None

        # 记录当前生效的重复次数
        self.current_repeat_count = app_config.get('player.repeat_count', 1)

        # 初始化队列管理器
        if self.QUEUE_AVAILABLE:
            try:
                self.export_queue = ExportQueue()
                self.queue_processor = QueueProcessor(self.export_queue)
                # 注入完整任务导出函数（方案B：完整导出）
                self.queue_processor.set_export_task_function(self._export_task_for_queue)
                print("[OK] 原版队列管理器初始化成功（使用完整导出流程）")
                self.queue_manager_window = None
                # 用于撤销功能的最近添加任务ID
                self.last_added_task_id = None
            except Exception as e:
                print(f"[ERROR] 队列管理器初始化失败: {e}")
                import traceback
                traceback.print_exc()
                self.export_queue = None
                self.queue_processor = None
                self.queue_manager_window = None
                self.last_added_task_id = None
                self.QUEUE_AVAILABLE = False
        else:
            self.export_queue = None
            self.queue_processor = None
            self.queue_manager_window = None
            self.last_added_task_id = None

        # 设置窗口
        self.setup_window()

        # 创建界面
        self.create_widgets()

        # 绑定事件
        self.bind_events()

        # 加载数据
        self.load_projects()

        # 设置回调
        self.setup_callbacks()

    def setup_window(self):
        """设置窗口属性"""
        # 获取应用信息并设置标题
        app_info = get_app_info()
        self.root.title(f"{app_info['name']} v{app_info['version']} - 外语学习字幕片段工具")

        # 从配置加载窗口大小和位置
        width = app_config.get('window.width', 1200)
        height = app_config.get('window.height', 800)
        x = app_config.get('window.x', 100)
        y = app_config.get('window.y', 100)

        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.minsize(800, 600)

        # 设置窗口图标
        if ICON_AVAILABLE:
            set_window_icon(self.root)
            print("[OK] 主窗口图标设置成功")
        else:
            print("[WARN] 图标管理器不可用，跳过图标设置")

    def create_widgets(self):
        """创建界面组件"""
        # 创建主框架
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 创建工具栏（包含状态信息）
        self.create_toolbar()

        # 创建内容区域
        self.create_content_area()

    def create_toolbar(self):
        """创建工具栏"""
        # 第一行工具栏：项目选择和主要按钮
        toolbar_frame1 = ttk.Frame(self.main_frame)
        toolbar_frame1.pack(fill=tk.X, pady=(0, 3))

        # 项目选择
        ttk.Label(toolbar_frame1, text="当前项目:").pack(side=tk.LEFT, padx=(0, 5))

        self.project_var = tk.StringVar()
        self.project_combo = ttk.Combobox(
            toolbar_frame1,
            textvariable=self.project_var,
            state="readonly",
            width=30
        )
        self.project_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.project_combo.bind('<<ComboboxSelected>>', self.on_project_changed)

        # 按钮组
        ttk.Button(toolbar_frame1, text="导入项目", command=self.show_import_dialog).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar_frame1, text="导出项目", command=self.show_export_dialog).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar_frame1, text="队列管理", command=self.show_queue_manager).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar_frame1, text="片段合并", command=self.show_merge_dialog).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar_frame1, text="存储管理", command=self.show_storage_dialog).pack(side=tk.LEFT, padx=(0, 5))

        # 右侧统计信息
        self.stats_label = ttk.Label(toolbar_frame1, text="")
        self.stats_label.pack(side=tk.RIGHT, padx=(10, 0))

        # 播放器选项

        # 预加载功能改为纯后端运行，不在界面显示，始终启用
        self.preload_var = tk.BooleanVar(value=True)  # 强制启用预加载
        # ttk.Checkbutton(toolbar_frame1, text="预加载", variable=self.preload_var,
        #                 command=self.on_toggle_preload).pack(side=tk.RIGHT, padx=(5, 0))

        # 确保预加载功能启用
        self.on_toggle_preload()

        # 跳转模式选择（仅对支持的播放器显示）
        seek_mode_frame = ttk.Frame(toolbar_frame1)
        seek_mode_frame.pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Label(seek_mode_frame, text="片段跳转:").pack(side=tk.LEFT)

        # 跳转模式映射
        self.seek_mode_mapping = {'智能': 'smart', '精确': 'precise'}
        self.seek_mode_reverse_mapping = {'smart': '智能', 'precise': '精确'}

        # 获取当前模式并转换为中文显示
        current_mode = app_config.get('player.seek_mode', 'precise')
        current_display = self.seek_mode_reverse_mapping.get(current_mode, '精确')

        self.seek_mode_var = tk.StringVar(value=current_display)
        self.seek_mode_combo = ttk.Combobox(seek_mode_frame, textvariable=self.seek_mode_var,
                                           values=['智能', '精确'],
                                           state="readonly", width=6)
        self.seek_mode_combo.pack(side=tk.LEFT, padx=(3, 0))
        self.seek_mode_combo.bind('<<ComboboxSelected>>', self.on_seek_mode_changed)

        # 根据播放器类型显示/隐藏跳转模式选择
        self._update_seek_mode_visibility()

        # 重复次数设置（使用 tk.Spinbox 以支持背景颜色修改）
        repeat_frame = ttk.Frame(toolbar_frame1)
        repeat_frame.pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Label(repeat_frame, text="片段重复:").pack(side=tk.LEFT)
        self.repeat_var = tk.StringVar(value=str(self.current_repeat_count))
        self.repeat_spinbox = tk.Spinbox(repeat_frame, textvariable=self.repeat_var, from_=1, to=99, width=5,
                                     command=self.on_repeat_changed, bg='white', relief='solid', bd=1)
        self.repeat_spinbox.pack(side=tk.LEFT, padx=(3, 0))
        self.repeat_spinbox.bind('<Return>', lambda e: self.on_repeat_changed())
        self.repeat_spinbox.bind('<FocusOut>', lambda e: self.on_repeat_changed())
        ttk.Label(repeat_frame, text="次").pack(side=tk.LEFT, padx=(2, 0))

        # 监听输入框内容变化，显示视觉提示
        self.repeat_var.trace('w', self.on_repeat_input_changed)

        # 第二行工具栏：状态信息和进度条
        toolbar_frame2 = ttk.Frame(self.main_frame)
        toolbar_frame2.pack(fill=tk.X, pady=(0, 5))

        # 状态标签容器（固定宽度，防止界面动态调整）
        status_frame = ttk.Frame(toolbar_frame2, width=600)
        status_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        status_frame.pack_propagate(False)  # 防止子组件改变容器大小

        self.status_label = ttk.Label(status_frame, text="就绪", anchor='w')
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 进度条容器（固定宽度，防止界面动态调整）
        progress_frame = ttk.Frame(toolbar_frame2, width=250)
        progress_frame.pack(side=tk.RIGHT, padx=(10, 0))
        progress_frame.pack_propagate(False)  # 防止子组件改变容器大小

        # 进度条（默认隐藏）
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            variable=self.progress_var,
            maximum=100,
            length=150
        )

        # 进度标签
        self.progress_label = ttk.Label(progress_frame, text="", width=10)

        self.update_stats()

    def create_content_area(self):
        """创建内容区域"""
        content_frame = ttk.Frame(self.main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True)

        # 搜索栏
        self.search_bar = SearchBarWidget(content_frame)
        self.search_bar.pack(fill=tk.X, pady=(0, 5))
        self.search_bar.set_search_callback(self.on_search)

        # 字幕列表
        self.subtitle_list = SubtitleListWidget(content_frame)
        self.subtitle_list.pack(fill=tk.BOTH, expand=True)
        # 设置主窗口引用
        self.subtitle_list.main_window = self
        self.subtitle_list.set_double_click_callback(self.on_subtitle_double_click)
        self.subtitle_list.set_selection_callback(self.on_selection_changed)
        self.subtitle_list.set_page_change_callback(self.on_page_changed)
        # 设置快速添加和配置添加回调（新增）
        self.subtitle_list.quick_add_callback = self.on_quick_add_to_queue
        self.subtitle_list.config_add_callback = self.on_config_add_to_queue
        # 设置播放视频回调（新增）
        self.subtitle_list.play_video_callback = self.play_selected

    def bind_events(self):
        """绑定事件"""
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # 键盘快捷键
        self.root.bind('<Control-i>', lambda e: self.show_import_dialog())
        self.root.bind('<Control-e>', lambda e: self.show_export_dialog())
        self.root.bind('<Control-f>', lambda e: self.search_bar.focus_search())
        self.root.bind('<F5>', lambda e: self.refresh_data())
        self.root.bind('<Delete>', lambda e: self.delete_selected())
        self.root.bind('<Escape>', lambda e: self.stop_playback())  # Esc 停止播放

    def setup_callbacks(self):
        """设置回调函数"""

        # 初始化播放器的跳转模式
        if hasattr(self.player, 'set_seek_mode'):
            seek_mode = app_config.get('player.seek_mode', 'precise')
            self.player.set_seek_mode(seek_mode)

        # 启动队列状态更新定��器
        if self.QUEUE_AVAILABLE and self.export_queue:
            self.update_queue_status()

    def update_queue_status(self):
        """更新队列状态（定时调用）"""
        if self.QUEUE_AVAILABLE and self.export_queue:
            try:
                # 更新统计信息（包含队列状态）
                self.update_stats()
            except Exception as e:
                print(f"更新队列状态失败: {e}")

            # 每5秒更新一次
            self.root.after(5000, self.update_queue_status)

    def _update_seek_mode_visibility(self):
        """根据播放器类型更新跳转模式选择的可见性"""
        # 只有MPV播放器支持跳转模式选择
        if hasattr(self.player, 'set_seek_mode'):
            self.seek_mode_combo.pack(side=tk.LEFT, padx=(3, 0))
        else:
            self.seek_mode_combo.pack_forget()

        self.video_processor.set_callbacks(
            progress_callback=self.on_import_progress,
            log_callback=self.on_import_log
        )

        self.player.set_callbacks(
            on_play_start=self.on_play_start,
            on_play_end=self.on_play_end,
            on_error=self.on_play_error
        )

    def load_projects(self):
        """加载项目列表"""
        try:
            from utils.file_utils import FileUtils

            projects = db_manager.get_all_projects()

            # 添加"全部视频"选项
            project_names = ["全部视频"]

            # 为每个项目添加类型标签
            for p in projects:
                # 判断项目类型（基于文件扩展名）
                is_audio = FileUtils.is_audio_file(p.video_path)
                media_type = "[音频]" if is_audio else "[视频]"

                # 格式化项目名称：[类型] 项目名 (ID: X)
                project_names.append(f"{media_type} {p.name} (ID: {p.id})")

            self.project_combo['values'] = project_names

            # 默认选择"全部视频"
            self.project_combo.current(0)
            self.current_project = None  # None 表示全部视频
            self.load_project_data()

        except Exception as e:
            messagebox.showerror("错误", f"加载项目失败：{e}")

    def load_project_data(self):
        """加载当前项目的数据"""
        try:
            # 清空搜索状态和搜索框（切换项目时）
            self.search_state = {
                'keyword': '',
                'mode': 'fuzzy',
                'context_before': 0,
                'context_after': 0,
                'filter_type': None,
                'filter_params': None
            }
            self.search_bar.clear_search()

            items_per_page = app_config.get('pagination.items_per_page', 30)

            if self.current_project is None:
                # 加载全部视频
                segments = db_manager.get_all_segments(
                    offset=0,
                    limit=items_per_page
                )
                total_count = db_manager.get_total_segment_count()
            else:
                # 加载单个项目
                segments = db_manager.get_segments_by_project(
                    self.current_project.id,
                    offset=0,
                    limit=items_per_page
                )
                total_count = db_manager.get_segment_count(self.current_project.id)

            # 更新列表
            self.subtitle_list.load_segments(segments)

            # 更新分页信息
            self.subtitle_list.update_pagination(0, total_count)

        except Exception as e:
            messagebox.showerror("错误", f"加载项目数据失败：{e}")

    def update_stats(self):
        """更新统计信息"""
        try:
            stats = db_manager.get_database_stats()
            stats_text = f"视频: {stats['project_count']} | 片段: {stats['segment_count']}"

            # 添加队列状态信息
            #if self.QUEUE_AVAILABLE and self.export_queue:
                #try:
                    #queue_stats = self.export_queue.get_statistics()
                    #pending_count = queue_stats.get('pending', 0)
                    #processing_count = queue_stats.get('processing', 0)
                    #total_count = queue_stats.get('total', 0)

                    #if total_count > 0:
                        #queue_text = f" | 队列: {total_count}个任务"
                        #if processing_count > 0:
                            #queue_text += f" (处理中: {processing_count})"
                        #stats_text += queue_text
                #except Exception as e:
                    #print(f"获取队列统计失败: {e}")

            self.stats_label.config(text=stats_text)
        except Exception:
            self.stats_label.config(text="统计信息获取失败")

    def show_progress(self, show: bool = True):
        """显示/隐藏进度条"""
        if show:
            self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.progress_label.pack(side=tk.RIGHT, padx=(5, 0))
        else:
            self.progress_bar.pack_forget()
            self.progress_label.pack_forget()

    def set_status(self, message: str):
        """设置状态栏消息"""
        try:
            # 智能截断长消息，保持界面稳定
            max_length = 100  # 适当的长度限制
            if len(message) > max_length:
                # 保留开头和结尾，中间用...连接
                start_part = message[:50]
                end_part = message[-30:]
                display_message = f"{start_part}...{end_part}"
            else:
                display_message = message

            self.status_label.config(text=display_message)
            self.root.update_idletasks()
        except Exception as e:
            # 如果UI更新失败（比如窗口正在关闭），只打印消息不抛出异常
            print(f"状态更新失败: {message} (错误: {e})")

    # 事件处理方法
    def on_project_changed(self, event=None):
        """项目选择改变"""
        selection = self.project_combo.get()
        if not selection:
            return

        try:
            from utils.file_utils import FileUtils

            # 清除项目全选模式（因为切换了项目）
            self.subtitle_list.clear_project_select_mode()

            # 检查是否选择"全部视频"
            if selection == "全部视频":
                self.current_project = None
                self.load_project_data()
                self.set_status("已切换到：全部视频")
            else:
                # 从选择文本中提取项目ID
                project_id = int(selection.split("ID: ")[1].split(")")[0])
                self.current_project = db_manager.get_project(project_id)
                self.load_project_data()

                # 判断项目类型并显示在状态栏
                is_audio = FileUtils.is_audio_file(self.current_project.video_path)
                media_type = "音频项目" if is_audio else "视频项目"
                self.set_status(f"已切换到{media_type}：{self.current_project.name}")

        except Exception as e:
            messagebox.showerror("错误", f"切换项目失败：{e}")

    def on_search(self, keyword: str):
        """搜索事件（支持全局搜索、多种模式、时长过滤和时间区间过滤）"""
        try:
            # 清除项目全选模式（因为进行了搜索）
            self.subtitle_list.clear_project_select_mode()

            items_per_page = app_config.get('pagination.items_per_page', 30)

            # 检测是否为时间区间过滤（特殊格式）
            if keyword.startswith("__TIME_FILTER__:"):
                # 解析时间区间过滤参数
                parts = keyword.split(":")
                if len(parts) == 3:
                    try:
                        start_time = float(parts[1])
                        end_time = float(parts[2])

                        # 保存搜索状态
                        self.search_state = {
                            'keyword': keyword,
                            'mode': 'fuzzy',
                            'context_before': 0,
                            'context_after': 0,
                            'filter_type': 'time_range',
                            'filter_params': {'start_time': start_time, 'end_time': end_time}
                        }

                        # 执行时间区间过滤
                        segments = self.filter_by_time_range(start_time, end_time, offset=0, limit=items_per_page)
                        total_count = self.count_by_time_range(start_time, end_time)

                        scope_text = "全部视频" if self.current_project is None else self.current_project.name

                        # 格式化时间显示
                        start_str = self.format_seconds_to_time(start_time) if start_time > 0 else "开始"
                        end_str = self.format_seconds_to_time(end_time) if end_time < float('inf') else "结束"

                        self.set_status(f"在 {scope_text} 中按时间区间过滤到 {total_count} 个结果 ({start_str} ~ {end_str})")

                        self.subtitle_list.load_segments(segments)
                        self.subtitle_list.update_pagination(0, total_count)
                        return
                    except ValueError:
                        pass  # 解析失败，继续下面的逻辑

            if keyword.strip():
                # 检测是否为时长搜索
                duration_filter_result = self.parse_duration_filter(keyword)

                if duration_filter_result:
                    # 时长过滤
                    conditions = duration_filter_result

                    # 保存搜索状态
                    self.search_state = {
                        'keyword': keyword,
                        'mode': 'fuzzy',
                        'context_before': 0,
                        'context_after': 0,
                        'filter_type': 'duration',
                        'filter_params': {'conditions': conditions}
                    }

                    segments = self.filter_by_duration(conditions, offset=0, limit=items_per_page)
                    total_count = self.count_by_duration(conditions)

                    scope_text = "全部视频" if self.current_project is None else self.current_project.name
                    self.set_status(f"在 {scope_text} 中按时长过滤到 {total_count} 个结果")
                else:
                    # 普通文本搜索
                    search_mode = self.search_bar.get_search_mode()
                    search_options = self.search_bar.get_search_options()

                    # 获取上下文参数
                    context_before = search_options.get('context_before', 0)
                    context_after = search_options.get('context_after', 0)

                    # 保存搜索状态
                    self.search_state = {
                        'keyword': keyword,
                        'mode': search_mode,
                        'context_before': context_before,
                        'context_after': context_after,
                        'filter_type': 'text',
                        'filter_params': None
                    }

                    segments = db_manager.search_segments(
                        self.current_project.id if self.current_project else None,
                        keyword,
                        mode=search_mode,
                        offset=0,
                        limit=items_per_page,
                        context_before=context_before,
                        context_after=context_after
                    )
                    total_count = db_manager.get_search_count(
                        self.current_project.id if self.current_project else None,
                        keyword,
                        mode=search_mode,
                        context_before=context_before,
                        context_after=context_after
                    )

                    mode_text = {"fuzzy": "模糊", "exact": "精确", "regex": "正则"}[search_mode]
                    scope_text = "全部视频" if self.current_project is None else self.current_project.name

                    # 添加上下文提示信息
                    context_info = ""
                    if context_before > 0 or context_after > 0:
                        context_info = f" (扩展: 上{context_before}行 下{context_after}行)"

                    self.set_status(f"在 {scope_text} 中使用 {mode_text} 模式搜索到 {total_count} 个结果{context_info}")
            else:
                # 清空搜索，显示所有
                # 清空搜索状态
                self.search_state = {
                    'keyword': '',
                    'mode': 'fuzzy',
                    'context_before': 0,
                    'context_after': 0,
                    'filter_type': None,
                    'filter_params': None
                }

                if self.current_project is None:
                    segments = db_manager.get_all_segments(offset=0, limit=items_per_page)
                    total_count = db_manager.get_total_segment_count()
                else:
                    segments = db_manager.get_segments_by_project(
                        self.current_project.id,
                        offset=0,
                        limit=items_per_page
                    )
                    total_count = db_manager.get_segment_count(self.current_project.id)
                self.set_status("显示所有片段")

            self.subtitle_list.load_segments(segments)
            self.subtitle_list.update_pagination(0, total_count)

        except Exception as e:
            messagebox.showerror("错误", f"搜索失败：{e}")

    def parse_duration_filter(self, text: str):
        """解析时长过滤条件

        支持格式：
        - <=00:00:05,000  (小于等于5秒)
        - >00:00:03,000   (大于3秒)
        - >00:00:03,000 <=00:00:10,000 (3-10秒之间)

        Returns:
            list of (operator, seconds) tuples, or None if not a duration filter
        """
        import re

        # 检测是否包含时长过滤的操作符
        if not any(op in text for op in ['<', '>', '=']):
            return None

        # 时长格式正则：(操作符)(HH:MM:SS,mmm)
        pattern = r'([<>=]{1,2})\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})'

        matches = re.findall(pattern, text)
        if not matches:
            # 包含操作符但格式不对，显示错误提示
            messagebox.showerror(
                "时长搜索格式错误",
                "正确格式示例：\n\n"
                "• <=00:00:05,000  （小于等于5秒）\n"
                "• >00:00:03,000   （大于3秒）\n"
                "• >00:00:03,000 <=00:00:10,000  （3-10秒之间）\n\n"
                "格式说明：\n"
                "• 支持操作符：< <= > >=\n"
                "• 时间格式：HH:MM:SS,mmm\n"
                "• 可以组合多个条件进行范围搜索"
            )
            return None

        conditions = []
        for match in matches:
            operator, hours, minutes, seconds, milliseconds = match

            # 验证时间格式
            try:
                h = int(hours)
                m = int(minutes)
                s = int(seconds)
                ms = int(milliseconds)

                # 验证范围
                if m >= 60 or s >= 60 or ms >= 1000:
                    raise ValueError("时间格式无效")

                # 转换为总秒数
                total_seconds = h * 3600 + m * 60 + s + ms / 1000.0

                # 验证操作符
                if operator not in ['<', '<=', '>', '>=']:
                    raise ValueError("操作符无效")

                conditions.append((operator, total_seconds))

            except ValueError:
                # 格式错误，显示提示
                messagebox.showerror(
                    "时长搜索格式错误",
                    "正确格式示例：\n\n"
                    "• <=00:00:05,000  （小于等于5秒）\n"
                    "• >00:00:03,000   （大于3秒）\n"
                    "• >00:00:03,000 <=00:00:10,000  （3-10秒之间）\n\n"
                    "格式说明：\n"
                    "• 支持操作符：< <= > >=\n"
                    "• 时间格式：HH:MM:SS,mmm\n"
                    "• 可以组合多个条件进行范围搜索"
                )
                return None

        return conditions if conditions else None

    def filter_by_duration(self, conditions, offset=0, limit=30):
        """按时长过滤片段"""
        if self.current_project is None:
            all_segments = db_manager.get_all_segments(offset=0, limit=100000)
        else:
            all_segments = db_manager.get_segments_by_project(
                self.current_project.id, offset=0, limit=100000
            )

        # 应用时长过滤
        filtered = []
        for seg in all_segments:
            duration = seg.duration
            match = True
            for operator, value in conditions:
                if operator == '<':
                    if not (duration < value):
                        match = False
                        break
                elif operator == '<=':
                    if not (duration <= value):
                        match = False
                        break
                elif operator == '>':
                    if not (duration > value):
                        match = False
                        break
                elif operator == '>=':
                    if not (duration >= value):
                        match = False
                        break

            if match:
                filtered.append(seg)

        # 分页
        return filtered[offset:offset+limit]

    def count_by_duration(self, conditions):
        """统计符合时长条件的片段数量"""
        filtered = self.filter_by_duration(conditions, offset=0, limit=100000)
        return len(filtered)

    def filter_by_time_range(self, start_time, end_time, offset=0, limit=30):
        """按时间区间过滤片段

        过滤条件：片段的开始时间或结束时间在指定区间内

        Args:
            start_time: 开始时间（秒），0表示不限制
            end_time: 结束时间（秒），float('inf')表示不限制
            offset: 偏移量
            limit: 限制数量

        Returns:
            符合条件的片段列表
        """
        if self.current_project is None:
            all_segments = db_manager.get_all_segments(offset=0, limit=100000)
        else:
            all_segments = db_manager.get_segments_by_project(
                self.current_project.id, offset=0, limit=100000
            )

        # 应用时间区间过滤
        filtered = []
        for seg in all_segments:
            # 片段的开始时间或结束时间在指定区间内，则保留该片段
            # 或者片段完全包含指定区间
            seg_start = seg.start_time
            seg_end = seg.end_time

            # 情况1：片段开始时间在区间内
            # 情况2：片段结束时间在区间内
            # 情况3：片段完全包含区间
            in_range = False

            if start_time == 0 and end_time == float('inf'):
                # 不限制时间范围，保留所有片段
                in_range = True
            elif start_time == 0:
                # 只限制结束时间：片段开始时间 <= 结束时间
                in_range = seg_start <= end_time
            elif end_time == float('inf'):
                # 只限制开始时间：片段结束时间 >= 开始时间
                in_range = seg_end >= start_time
            else:
                # 限制开始和结束时间：片段与时间区间有交集
                # 交集条件：片段结束时间 >= 区间开始时间 AND 片段开始时间 <= 区间结束时间
                in_range = (seg_end >= start_time) and (seg_start <= end_time)

            if in_range:
                filtered.append(seg)

        # 分页
        return filtered[offset:offset+limit]

    def count_by_time_range(self, start_time, end_time):
        """统计符合时间区间条件的片段数量"""
        filtered = self.filter_by_time_range(start_time, end_time, offset=0, limit=100000)
        return len(filtered)

    def format_seconds_to_time(self, seconds):
        """将秒数格式化为时间字符串

        Args:
            seconds: 秒数（浮点数）

        Returns:
            格式化的时间字符串 HH:MM:SS,mmm
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        milliseconds = int((seconds % 1) * 1000)

        return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


    def on_subtitle_double_click(self, segment):
        """字幕双击事件（支持播放模式）"""
        if not segment:
            return

        # 获取播放模式
        play_mode = self.subtitle_list.get_play_mode()

        if play_mode == "连续播放":
            # 连续播放模式：双击播放该字幕所在的完整上下文
            # 这里可以选择播放单个片段，或者调用 play_continuous_mode
            # 为了简化，单个片段双击时仍然使用片段播放
            self.player.play_segment(segment)
        else:
            # 片段播放模式（默认）
            self.player.play_segment(segment)

    def on_selection_changed(self, selected_segments):
        """选择改变事件"""
        count = len(selected_segments)
        if count == 0:
            self.set_status("未选择任何片段")
        elif count == 1:
            segment = selected_segments[0]
            duration = FormatUtils.format_time(segment.duration)
            self.set_status(f"已选择 1 个片段，时长：{duration}")
        else:
            total_duration = sum(s.duration for s in selected_segments)
            duration = FormatUtils.format_time(total_duration)
            self.set_status(f"已选择 {count} 个片段，总时长：{duration}")

    def on_page_changed(self, page: int, items_per_page: int):
        """页面改变事件（支持搜索状态下的翻页）"""
        try:
            offset = page * items_per_page

            # 根据搜索状态加载数据
            filter_type = self.search_state.get('filter_type')

            if filter_type == 'text':
                # 文本搜索翻页
                keyword = self.search_state['keyword']
                mode = self.search_state['mode']
                context_before = self.search_state['context_before']
                context_after = self.search_state['context_after']

                segments = db_manager.search_segments(
                    self.current_project.id if self.current_project else None,
                    keyword,
                    mode=mode,
                    offset=offset,
                    limit=items_per_page,
                    context_before=context_before,
                    context_after=context_after
                )
                total_count = db_manager.get_search_count(
                    self.current_project.id if self.current_project else None,
                    keyword,
                    mode=mode,
                    context_before=context_before,
                    context_after=context_after
                )

            elif filter_type == 'duration':
                # 时长过滤翻页
                conditions = self.search_state['filter_params']['conditions']
                segments = self.filter_by_duration(conditions, offset=offset, limit=items_per_page)
                total_count = self.count_by_duration(conditions)

            elif filter_type == 'time_range':
                # 时间区间过滤翻页
                start_time = self.search_state['filter_params']['start_time']
                end_time = self.search_state['filter_params']['end_time']
                segments = self.filter_by_time_range(start_time, end_time, offset=offset, limit=items_per_page)
                total_count = self.count_by_time_range(start_time, end_time)

            else:
                # 普通浏览翻页（无搜索）
                if self.current_project is None:
                    segments = db_manager.get_all_segments(
                        offset=offset,
                        limit=items_per_page
                    )
                    total_count = db_manager.get_total_segment_count()
                else:
                    segments = db_manager.get_segments_by_project(
                        self.current_project.id,
                        offset=offset,
                        limit=items_per_page
                    )
                    total_count = db_manager.get_segment_count(self.current_project.id)

            self.subtitle_list.load_segments(segments)
            self.subtitle_list.update_pagination(page, total_count)

        except Exception as e:
            messagebox.showerror("错误", f"加载数据失败：{e}")

    def on_import_progress(self, current: int, total: int, message: str = ""):
        """导入进度回调"""
        if total > 0:
            progress = (current / total) * 100
            self.progress_var.set(progress)
            self.progress_label.config(text=f"{current}/{total}")

            if message:
                self.set_status(message)

        try:
            self.root.update_idletasks()
        except Exception as e:
            print(f"进度更新失败: {e}")

    def on_import_log(self, message: str):
        """导入日志回调"""
        self.set_status(message)

    def on_play_start(self, message: str):
        """播放开始回调"""
        # 状态栏已设置固定宽度，可以显示完整消息
        self.set_status(f"播放中：{message}")

    def on_play_end(self, message: str):
        """播放结束回调"""
        self.set_status("播放结束")

    def on_play_error(self, message: str):
        """播放错误回调"""
        self.set_status(f"播放错误：{message}")
        messagebox.showerror("播放错误", message)

    def on_closing(self):
        """窗口关闭事件"""
        print("开始关闭应用程序...")

        # 清理临时字幕文件
        try:
            self._cleanup_temp_subtitle_files()
        except Exception as e:
            print(f"清理临时文件失败：{e}")

        # 保存窗口位置和大小
        try:
            geometry = self.root.geometry()
            width, height, x, y = map(int, geometry.replace('x', '+').replace('+', ' ').split())
            app_config.save_window_geometry(width, height, x, y)
            print("窗口几何信息已保存")
        except Exception as e:
            print(f"保存窗口几何信息失败：{e}")

        # 保存列宽
        try:
            widths = {}
            for col in self.subtitle_list.tree['columns']:
                widths[col] = self.subtitle_list.tree.column(col, 'width')
            app_config.save_column_widths(widths)
            print("列宽信息已保存")
        except Exception as e:
            print(f"保存列宽失败：{e}")

        # 停止播放 - 使用超时机制
        try:
            print("正在停止播放器...")
            import threading
            import time

            # 在后台线程中停止播放器，避免阻塞主线程
            def stop_player():
                try:
                    self.player.stop()
                    print("播放器已停止")
                except Exception as e:
                    print(f"停止播放器时出错: {e}")

            stop_thread = threading.Thread(target=stop_player, daemon=True)
            stop_thread.start()

            # 等待最多1秒
            stop_thread.join(timeout=1.0)
            if stop_thread.is_alive():
                print("停止播放器超时，继续关闭程序")

        except Exception as e:
            print(f"停止播放时异常：{e}")

        # 取消正在进行的操作
        try:
            print("取消正在进行的操作...")
            self.video_processor.cancel_operation()
            exporter.cancel_operation()

            # 停止队列处理器
            if self.QUEUE_AVAILABLE and self.queue_processor:
                self.queue_processor.stop()
                print("队列处理器已停止")

            print("操作已取消")
        except Exception as e:
            print(f"取消操作时出错：{e}")

        # 关闭窗口
        try:
            print("销毁主窗口...")
            self.root.quit()  # 先退出主循环
            self.root.destroy()  # 再销毁窗口
            print("应用程序已关闭")
        except Exception as e:
            print(f"销毁窗口时出错：{e}")

        # 强制退出，确保程序完全关闭
        print("强制退出程序...")
        import sys
        import os
        try:
            # 尝试正常退出
            sys.exit(0)
        except:
            # 如果正常退出失败，强制终止进程
            os._exit(0)

    # 对话框方法
    def show_import_dialog(self):
        """显示导入对话框（防止多开）"""
        try:
            # 检查窗口是否已存在
            if self.import_dialog_window and self.import_dialog_window.winfo_exists():
                # 窗口已存在，恢复显示并聚焦
                self.import_dialog_window.deiconify()  # 如果是最小化状态，先恢复
                self.import_dialog_window.lift()
                self.import_dialog_window.focus_force()
                self.set_status("导入窗口已打开")
            else:
                # 创建新窗口
                dialog = ImportDialog(self.root)
                self.import_dialog_window = dialog.dialog

                # 设置关闭回调，让导入窗口关闭时立即刷新主窗口并清理引用
                def on_close_wrapper():
                    self.on_import_dialog_closed()
                    self.import_dialog_window = None

                dialog.set_close_callback(on_close_wrapper)

                # 不使用阻塞的show()方法，让窗口非模态
                self.set_status("已打开导入窗口")

        except Exception as e:
            messagebox.showerror("错误", f"显示导入对话框失败：{e}")
            self.set_status("导入对话框显示失败")

    def show_export_dialog(self):
        """显示导出对话框（防止多开）"""
        selected_segments = self.subtitle_list.get_selected_segments()
        if not selected_segments:
            messagebox.showwarning("警告", "请先选择要导出的片段")
            return

        try:
            # 检查窗口是否已存在
            if self.integrated_export_window and self.integrated_export_window.winfo_exists():
                # 窗口已存在，恢复显示并聚焦
                self.integrated_export_window.deiconify()  # 如果是最小化状态，先恢复
                self.integrated_export_window.lift()
                self.integrated_export_window.focus_force()
                self.set_status("导出窗口已打开")
            else:
                # 创建新窗口 - 传递 MainWindow 实例而不是 root 窗口
                # 这样 IntegratedExportDialog 可以访问 export_queue 等属性
                dialog = IntegratedExportDialog(self, selected_segments)
                self.integrated_export_window = dialog.dialog

                # 绑定关闭事件，清理引用
                original_protocol = self.integrated_export_window.protocol("WM_DELETE_WINDOW")
                def on_close_wrapper():
                    if hasattr(dialog, 'on_close'):
                        dialog.on_close()
                    else:
                        self.integrated_export_window.destroy()
                    self.integrated_export_window = None
                self.integrated_export_window.protocol("WM_DELETE_WINDOW", on_close_wrapper)

                self.set_status("已打开导出窗口")
        except Exception as e:
            messagebox.showerror("错误", f"无法显示导出对话框: {e}")

    def on_quick_add_to_queue(self, segments):
        """快速添加到队列（使用默认配置）"""
        try:
            from core.export_task_validator import validate_export_segments
            from core.export_config_manager import has_export_config, get_default_export_config
            from utils import custom_messagebox

            # 1. 检查是否有默认配置
            if not has_export_config():
                # 首次使用，强制打开配置窗口
                custom_messagebox.showinfo(
                    "首次使用",
                    "检测到您是首次使用快速添加功能。\n\n请先配置导出参数。",
                    parent=self.root
                )
                self.on_config_add_to_queue(segments)
                return

            # 3. 获取默认配置
            config = get_default_export_config()

            # 2. 检测问题（跨项目、音视频混合、文件丢失） - 根据配置的导出模式判断
            is_valid, error_msg, error_details = validate_export_segments(segments, config['fast_copy_mode'])
            if not is_valid:
                # 判断是否为跨项目错误，如果是则提供跳转配置窗口的选项
                if error_details and error_details.get('type') == 'cross_project':
                    # 跨项目错误：点击确认后自动打开配置窗口
                    # 使用 after 延迟执行，避免窗口最小化问题
                    def delayed_open_config():
                        self.root.after(150, lambda: self.on_config_add_to_queue(segments))

                    custom_messagebox.showwarning_with_action(
                        "无法添加到队列",
                        error_msg,
                        parent=self.root,
                        on_confirm=delayed_open_config
                    )
                else:
                    # 其他错误：普通弹窗
                    custom_messagebox.showwarning(
                        "无法添加到队列",
                        error_msg,
                        parent=self.root
                    )
                return

            # 4. 添加到队列
            from core.export_queue import ExportConfig, ExportTask, SegmentInfo

            export_config = ExportConfig(
                output_dir=config['output_dir'],
                naming_mode="sequence" if config['naming_mode'] == "index" else "sequence_subtitle",
                encoding_preset=config['encoding_preset'],
                crf=int(config['crf']),
                target_resolution=config['target_resolution'] if not config['fast_copy_mode'] else None,
                target_fps=int(config['target_fps']) if not config['fast_copy_mode'] else None,
                fast_copy_mode=config['fast_copy_mode'],
                continuous_cut_mode=config['continuous_cut_mode'],
                smart_validation=config.get('smart_validation', True),
                auto_fix_deviation=config.get('auto_fix_deviation', True)
            )

            # 准备片段信息
            segment_infos = []
            for seg in segments:
                segment_info = SegmentInfo(
                    segment_id=seg.id,
                    start_time=seg.start_time,
                    end_time=seg.end_time,
                    subtitle_text=seg.text,
                    duration=seg.end_time - seg.start_time,
                    project_id=seg.project_id
                )
                segment_infos.append(segment_info)

            # 检测是否为跨项目导出
            unique_project_ids = set(seg.project_id for seg in segments)
            is_cross_project = len(unique_project_ids) > 1

            # 获取项目信息
            from database.manager import db_manager
            if is_cross_project:
                # 跨项目导出：收集所有项目名称
                project_names = []
                for pid in sorted(unique_project_ids):
                    project = db_manager.get_project(pid)
                    if project:
                        project_names.append(project.name)

                # 拼接项目名称 [项目1][项目2]
                project_name = "".join(f"[{name}]" for name in project_names)
                video_path = "[跨项目]"
            else:
                # 单项目导出
                if segments:
                    first_segment = segments[0]
                    project = db_manager.get_project(first_segment.project_id)
                    project_name = project.name if project else "未知项目"
                    video_path = project.video_path if project else ""
                else:
                    project_name = "未知项目"
                    video_path = ""

            # 创建任务
            task = ExportTask(
                project_name=project_name,
                video_path=video_path,
                segments=segment_infos,
                config=export_config,
                total_segments=len(segment_infos),
                is_cross_project=is_cross_project
            )

            # 添加到队列
            task_id = self.export_queue.add_task(task)

            # 保存最近添加的任务ID（用于撤销功能）
            self.last_added_task_id = task_id

            # 5. 显示Toast通知
            from ui.components.toast_notification import show_toast

            mode_text = "标准模式" if config['fast_copy_mode'] else "重新编码"
            cut_mode_text = "连续切割" if config['continuous_cut_mode'] else "片段切割"

            message = f"✓ 已添加 {len(segments)} 个片段到队列\n\n项目: {project_name}\n模式: {mode_text} | {cut_mode_text}\n输出: {config['output_dir']}\n当前队列: {len(self.export_queue.tasks)} 个任务"

            show_toast(
                parent=self.root,
                message=message,
                duration=1000,
                actions=[
                    {"text": "📋 打开队列管理器", "command": self.show_queue_manager},
                    {"text": "↩ 撤销", "command": lambda: self.undo_add_task(task_id)}
                    
                ]
            )

            self.set_status(f"已添加 {len(segments)} 个片段到队列")

        except Exception as e:
            import traceback
            messagebox.showerror("错误", f"快速添加失败: {e}\n\n{traceback.format_exc()}")

    def on_config_add_to_queue(self, segments):
        """配置后添加到队列（打开配置窗口）"""
        try:
            from core.export_task_validator import ExportTaskValidator
            from utils import custom_messagebox

            # 只检测音视频混合和文件丢失（跨项目检测留到配置窗口中根据模式判断）
            is_valid, error_msg, error_details = ExportTaskValidator.check_mixed_media(segments)
            if not is_valid:
                custom_messagebox.showwarning(
                    "无法添加到队列",
                    error_msg,
                    parent=self.root
                )
                return

            is_valid, error_msg, error_details = ExportTaskValidator.check_missing_files(segments)
            if not is_valid:
                custom_messagebox.showwarning(
                    "无法添加到队列",
                    error_msg,
                    parent=self.root
                )
                return

            # 打开导出配置对话框
            self.show_export_dialog()

        except Exception as e:
            import traceback
            messagebox.showerror("错误", f"配置添加失败: {e}\n\n{traceback.format_exc()}")

    def undo_add_task(self, task_id):
        """撤销添加任务"""
        try:
            # 从队列中移除任务
            if self.export_queue.remove_task(task_id):
                from ui.components.toast_notification import show_toast
                show_toast(
                    parent=self.root,
                    message="✓ 已撤销添加任务",
                    duration=500
                )
                self.set_status("已撤销添加任务")
            else:
                messagebox.showwarning("警告", "任务已开始处理，无法撤销")
        except Exception as e:
            messagebox.showerror("错误", f"撤销失败: {e}")

    def show_merge_dialog(self):
        """显示片段合并对话框（防止多开）"""
        try:
            # 检查窗口是否已存在
            if self.integrated_merge_window and self.integrated_merge_window.winfo_exists():
                # 窗口已存在，恢复显示并聚焦
                self.integrated_merge_window.deiconify()  # 如果是最小化状态，先恢复
                self.integrated_merge_window.lift()
                self.integrated_merge_window.focus_force()
                self.set_status("片段合并窗口已打开")
            else:
                # 创建新窗口
                dialog = IntegratedMergeDialog(self.root)
                self.integrated_merge_window = dialog.dialog

                # 绑定关闭事件，清理引用
                original_on_close = dialog.on_close
                def on_close_wrapper():
                    original_on_close()
                    self.integrated_merge_window = None
                dialog.on_close = on_close_wrapper

                # 不使用 show() 方法，因为它会阻塞
                # dialog.show()
                self.set_status("已打开片段合并窗口")
        except Exception as e:
            messagebox.showerror("错误", f"无法显示合并对话框: {e}")


    def show_storage_dialog(self):
        """显示存储管理对话框"""
        dialog = StorageDialog(self.root)
        dialog.show()

        # 刷新统计信息和项目列表
        self.update_stats()
        self.load_projects()

    def show_video_to_audio_dialog(self):
        """显示提取音频对话框（防止多开）"""
        try:
            # 检查窗口是否已存在
            if hasattr(self, 'video_to_audio_window') and self.video_to_audio_window and \
               self.video_to_audio_window.winfo_exists():
                # 窗口已存在，恢复显示并聚焦
                self.video_to_audio_window.deiconify()  # 如果是最小化状态，先恢复
                self.video_to_audio_window.lift()
                self.video_to_audio_window.focus_force()
                self.set_status("提取音频窗口已打开")
            else:
                # 创建新窗口
                dialog = VideoToAudioDialog(self.root)
                self.video_to_audio_window = dialog.dialog

                # 绑定关闭事件，清理引用
                def on_close_wrapper():
                    self.video_to_audio_window.destroy()
                    self.video_to_audio_window = None

                dialog.dialog.protocol("WM_DELETE_WINDOW", on_close_wrapper)
                self.set_status("已打开提取音频窗口")
        except Exception as e:
            import traceback
            messagebox.showerror("错误", f"无法显示提取音频对话框: {e}\n\n{traceback.format_exc()}")
            self.set_status("提取音频窗口打开失败")

    def show_queue_manager(self):
        """显示队列管理器对话框（防止多开）"""
        if not self.QUEUE_AVAILABLE or not self.export_queue or not self.queue_processor:
            messagebox.showerror("错误", "队列管理器不可用")
            return

        try:
            # 检查窗口是否已存在（Tkinter版本）
            if (self.queue_manager_window and
                hasattr(self.queue_manager_window, 'dialog') and
                self.queue_manager_window.dialog.winfo_exists()):
                # 窗口已存在，恢复显示并聚焦
                self.queue_manager_window.dialog.deiconify()  # 如果是最小化状态，先恢复
                self.queue_manager_window.dialog.lift()
                self.queue_manager_window.dialog.focus_force()
                self.set_status("队列管理器窗口已打开")
                print("[队列管理器] 窗口已存在，已聚焦")
            else:
                # 创建新窗口（只使用原版队列）
                dialog = QueueManagerDialog(self.export_queue, self.queue_processor, self.root)
                self.set_status("已打开队列管理器")

                self.queue_manager_window = dialog

                # 绑定关闭事件，清理引用（使用回调函数而不是信号）
                dialog.finished(self.on_queue_manager_closed)

                print("[队列管理器] 创建新窗口")

        except Exception as e:
            messagebox.showerror("错误", f"无法显示队列管理器: {e}")

    def on_queue_manager_closed(self):
        """队列管理器关闭回调"""
        self.queue_manager_window = None
        # 更新统计信息
        self.update_stats()

    def on_player_changed(self, player_type: str):
        """播放器切换回调"""
        # 重置播放器实例
        self.player = reset_player()

        # 重新设置回调
        self.player.set_callbacks(
            on_play_start=self.on_play_start,
            on_play_end=self.on_play_end,
            on_error=self.on_play_error
        )

        # 重新设置重复次数
        repeat_count = app_config.get('player.repeat_count', 1)
        self.player.set_repeat_count(repeat_count)



        # 如果播放器支持跳转模式，设置跳转模式
        if hasattr(self.player, 'set_seek_mode'):
            seek_mode = app_config.get('player.seek_mode', 'precise')
            self.player.set_seek_mode(seek_mode)
            # 更新下拉框显示为对应的中文选项
            display_mode = self.seek_mode_reverse_mapping.get(seek_mode, '精确')
            self.seek_mode_var.set(display_mode)

        # 更新跳转模式选择的可见性
        self._update_seek_mode_visibility()

        self.set_status(f"播放器已切换到：{player_type}")

    # 异步操作方法
    def import_video_async(self, video_path: str, subtitle_path: str, preset: str, crf: str):
        """异步导入视频"""
        self.show_progress(True)
        self.set_status("正在导入...")

        def import_worker():
            try:
                from database.models import ImportResult
                result = self.video_processor.import_video_subtitle(
                    video_path, subtitle_path, preset, crf
                )

                # 在主线程中更新UI并显示结果
                self.root.after(0, self.on_import_complete, result)

            except Exception as e:
                from database.models import ImportResult
                result = ImportResult(
                    success=False,
                    error_message=str(e)
                )
                self.root.after(0, self.on_import_complete, result)

        threading.Thread(target=import_worker, daemon=True).start()

    def export_segments_async(self, segments, output_dir: str, export_types: List[str],
                             merge: bool, gap: float, direct_cut: bool = False,
                             naming_mode: str = "index", preset: str = "veryfast", crf: str = "24"):
        """异步导出片段"""
        self.show_progress(True)
        self.set_status("正在导出...")

        def export_worker():
            try:
                segment_ids = [s.id for s in segments]
                success = exporter.export_segments(
                    segment_ids, output_dir, export_types, merge, gap,
                    direct_cut, naming_mode, preset, crf
                )

                if success:
                    self.root.after(0, self.on_export_success, output_dir)
                else:
                    self.root.after(0, self.on_export_failed, "导出失败")

            except Exception as e:
                self.root.after(0, self.on_export_failed, str(e))

        threading.Thread(target=export_worker, daemon=True).start()
    def merge_standalone_async(self, input_dir: str, output_dir: str, gap: float):
        """异步执行独立文件夹合并（standalone_merge）"""
        self.show_progress(True)
        self.set_status("正在合并片段...")

        def worker():
            ok = False
            try:
                ok = standalone_merge(input_dir, output_dir, gap, progress=lambda m: self.root.after(0, self.set_status, m))
                if ok:
                    self.root.after(0, messagebox.showinfo, "完成", f"合并完成！\n输出目录：{output_dir}")
                else:
                    self.root.after(0, messagebox.showerror, "失败", "合并失败，请检查输入目录与文件格式是否一致")
            except Exception as e:
                self.root.after(0, messagebox.showerror, "错误", f"合并发生错误：{e}")
            finally:
                self.root.after(0, self.show_progress, False)

        threading.Thread(target=worker, daemon=True).start()


    def on_import_complete(self, result):
        """导入完成回调（不再显示单独的结果对话框）"""
        from database.models import ImportResult
        self.show_progress(False)

        # 不再显示导入结果对话框，信息已在导入对话框的日志中显示

        if result.success:
            if result.skipped:
                self.set_status("项目已存在，已跳过")
            else:
                self.set_status("导入完成")

            # 刷新项目列表
            self.load_projects()

            # 选择导入的项目
            if result.project_id:
                projects = db_manager.get_all_projects()
                for i, project in enumerate(projects):
                    if project.id == result.project_id:
                        self.project_combo.current(i)
                        self.current_project = project
                        self.load_project_data()
                        break

            self.update_stats()
        else:
            self.set_status("导入失败")

    def on_import_dialog_closed(self):
        """导入对话框关闭时的回调（立即刷新主窗口）"""
        # 立即刷新项目列表和数据
        self.load_projects()

        # 如果有当前项目，重新加载项目数据
        if self.current_project:
            self.load_project_data()

        # 更新统计信息
        self.update_stats()

    def on_import_success(self, project_id: int):
        """导入成功回调（保留用于兼容性）"""
        self.show_progress(False)
        self.set_status("导入完成")

        # 刷新项目列表
        self.load_projects()

        # 选择新导入的项目
        projects = db_manager.get_all_projects()
        for i, project in enumerate(projects):
            if project.id == project_id:
                self.project_combo.current(i)
                self.current_project = project
                self.load_project_data()
                break

        self.update_stats()
        messagebox.showinfo("成功", "视频导入完成！")



    def on_toggle_preload(self):
        """预加载切换（现在为纯后端功能，始终启用）"""
        from core.preloader import preloader
        # 预加载功能改为纯后端运行，始终启用
        enabled = True  # 强制启用
        self.preload_var.set(enabled)  # 同步变量状态
        preloader.set_enabled(enabled)

    def on_repeat_input_changed(self, *args):
        """输入框内容变化时的处理（显示视觉提示）"""
        try:
            input_value = self.repeat_var.get().strip()
            if not input_value:
                # 空值，显示警告颜色
                self.repeat_spinbox.config(bg='#ffff00')  # 淡黄色FFF9C4、黄色ffff00
                return

            # 尝试解析输入值
            try:
                input_count = int(input_value)
                # 检查是否与当前生效值不同
                if input_count != self.current_repeat_count:
                    # 未生效，显示淡黄色背景
                    self.repeat_spinbox.config(bg='#ffff00')  # 淡黄色FFF9C4
                else:
                    # 已生效，恢复默认背景
                    self.repeat_spinbox.config(bg='white')
            except ValueError:
                # 无效输入，显示警告颜色
                self.repeat_spinbox.config(bg='#FFCDD2')  # 淡红色
        except Exception as e:
            print(f"输入变化处理失败: {e}")

    def on_repeat_changed(self):
        """重复次数改变（应用修改）"""
        try:
            repeat_count = int(self.repeat_var.get())
            if repeat_count < 1:
                repeat_count = 1
                self.repeat_var.set('1')
            elif repeat_count > 99:
                repeat_count = 99
                self.repeat_var.set('99')

            # 检查是否真的改变了
            if repeat_count == self.current_repeat_count:
                # 没有变化，恢复背景色即可
                self.repeat_spinbox.config(bg='white')
                return

            # 应用修改
            app_config.set('player.repeat_count', repeat_count)
            self.player.set_repeat_count(repeat_count)
            self.current_repeat_count = repeat_count

            # 恢复背景色
            self.repeat_spinbox.config(bg='white')

            # 状态栏提示（保持2秒）
            self.set_status(f"✓ 重复次数已设置为 {repeat_count} 次")
            # 2秒后恢复状态栏
            self.root.after(2000, lambda: self.set_status("就绪"))

        except ValueError:
            # 输入无效，重置为当前生效值
            self.repeat_var.set(str(self.current_repeat_count))
            self.repeat_spinbox.config(bg='white')
            self.set_status("⚠ 输入无效，已恢复为之前的设置")
            self.root.after(2000, lambda: self.set_status("就绪"))

    def on_seek_mode_changed(self, event=None):
        """跳转模式改变"""
        display_mode = self.seek_mode_var.get()
        # 将中文显示转换为英文配置值
        seek_mode = self.seek_mode_mapping.get(display_mode, 'precise')
        app_config.set('player.seek_mode', seek_mode)

        # 如果播放器支持设置跳转模式
        if hasattr(self.player, 'set_seek_mode'):
            self.player.set_seek_mode(seek_mode)

        self.set_status(f"跳转模式设置为：{display_mode}")

    def on_import_failed(self, error_message: str):
        """导入失败回调"""
        self.show_progress(False)
        self.set_status("导入失败")
        messagebox.showerror("导入失败", error_message)

    def on_export_success(self, output_dir: str):
        """导出成功回调"""
        self.show_progress(False)
        self.set_status("导出完成")

        result = messagebox.askyesno("导出完成", f"文件已导出到：\n{output_dir}\n\n是否打开输出目录？")
        if result:
            import os
            os.startfile(output_dir)

    def on_export_failed(self, error_message: str):
        """导出失败回调"""
        self.show_progress(False)
        self.set_status("导出失败")
        messagebox.showerror("导出失败", error_message)

    # 其他操作方法
    def play_selected(self):
        """播放选中的片段（根据播放模式调用不同方法）"""
        selected_segments = self.subtitle_list.get_selected_segments()
        if not selected_segments:
            messagebox.showwarning("警告", "请先选择要播放的片段")
            return

        # 获取播放模式
        play_mode = self.subtitle_list.get_play_mode()
        print(f"[播放] 当前播放模式: {play_mode}, 选中片段数: {len(selected_segments)}")

        if play_mode == "连续播放":
            # 连续播放模式
            print(f"[播放] 使用连续播放模式")
            self.play_continuous_mode(selected_segments)
        else:
            # 片段播放模式（默认）
            print(f"[播放] 使用片段播放模式")
            self.play_segments_mode(selected_segments)

    def play_segments_mode(self, selected_segments):
        """片段播放模式（原逻辑）"""
        if len(selected_segments) == 1:
            # 单片段播放，无需加载反馈（速度快）
            self.player.play_segment(selected_segments[0])
        else:
            # 多片段直接连续播放，无需确认弹窗
            self.set_status(f'正在准备 {len(selected_segments)} 个片段的字幕，请稍候...')

            def play_worker():
                """后台线程执行播放"""
                try:
                    # 执行实际的播放操作（包括字幕准备）
                    self.player.play_segments(selected_segments, continuous=True)
                except Exception as e:
                    # 错误处理
                    self.root.after(0, messagebox.showerror, "播放错误", f"播放失败：{e}")
                    self.root.after(0, self.set_status, "播放失败")

            # 在后台线程中执行播放准备
            threading.Thread(target=play_worker, daemon=True).start()

    def play_continuous_mode(self, selected_segments):
        """连续播放模式（新逻辑）"""
        # 清理之前的临时文件
        self._cleanup_temp_subtitle_files()

        # 计算时间区间
        start_time = min(seg.start_time for seg in selected_segments)
        end_time = max(seg.end_time for seg in selected_segments)

        # 获取第一个片段的项目信息（假设选中的片段来自同一项目）
        first_segment = selected_segments[0]
        project_id = first_segment.project_id
        video_file = first_segment.video_file

        # 从数据库查询该时间区间内的所有字幕
        all_segments = db_manager.get_segments_in_time_range(project_id, start_time, end_time)

        print(f"[连续播放] 选中 {len(selected_segments)} 个片段，时间区间: {start_time:.3f}s ~ {end_time:.3f}s")
        print(f"[连续播放] 该区间包含 {len(all_segments)} 个字幕片段")

        # 创建一个虚拟片段，代表整个连续区间
        from database.models import SubtitleSegment
        continuous_segment = SubtitleSegment(
            id=first_segment.id,
            project_id=project_id,
            index_num=first_segment.index_num,
            start_time=start_time,
            end_time=end_time,
            text=f"连续播放 {len(all_segments)} 个字幕",
            text_primary=f"连续播放 {len(all_segments)} 个字幕",
            text_secondary="",
            video_file=video_file,
            audio_file=first_segment.audio_file,
            subtitle_file=first_segment.subtitle_file,
            created_at=first_segment.created_at
        )

        self.set_status(f'连续播放模式：播放 {start_time:.3f}s ~ {end_time:.3f}s 区间（含 {len(all_segments)} 个字幕）')

        def play_worker():
            """后台线程执行连续播放"""
            try:
                # 获取重复次数
                repeat_count = self.current_repeat_count

                print(f"[连续播放] 连续播放整段视频，重复 {repeat_count} 次")

                # 重复播放整个区间
                for i in range(repeat_count):
                    print(f"[连续播放] 第 {i+1}/{repeat_count} 次播放")
                    # 使用单片段播放，但传入完整的时间区间
                    # 注意：这里需要为该区间生成包含所有字幕的字幕文件
                    self._play_continuous_range_with_subtitles(
                        continuous_segment,
                        all_segments,
                        is_last=(i == repeat_count - 1)
                    )

            except Exception as e:
                # 错误处理
                self.root.after(0, messagebox.showerror, "播放错误", f"连续播放失败：{e}")
                self.root.after(0, self.set_status, "播放失败")

        # 在后台线程中执行播放
        threading.Thread(target=play_worker, daemon=True).start()

    def _play_continuous_range_with_subtitles(self, segment, all_subtitles, is_last=False):
        """播放连续区间并加载该区间的所有字幕"""
        import tempfile
        import os

        # 生成包含所有字幕的临时字幕文件
        subtitle_file = self._create_continuous_subtitle_file(
            segment.start_time,
            segment.end_time,
            all_subtitles
        )

        # 修改片段的字幕文件路径
        segment.subtitle_file = subtitle_file

        # 调用播放器播放该片段
        self.player.play_segment(segment)

    def _create_continuous_subtitle_file(self, start_time, end_time, subtitles):
        """为连续播放区间创建字幕文件"""
        import tempfile

        # 创建临时字幕文件
        temp_file = tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.srt', delete=False)

        print(f"[连续播放字幕] 创建字幕文件，时间区间: {start_time:.3f}s ~ {end_time:.3f}s")
        print(f"[连续播放字幕] 包含 {len(subtitles)} 条字幕")

        # 写入字幕
        for idx, seg in enumerate(subtitles, 1):
            # 将字幕时间调整为相对于区间开始的时间
            sub_start = seg.start_time - start_time
            sub_end = seg.end_time - start_time

            # 确保时间在有效范围内
            if sub_start < 0:
                sub_start = 0
            if sub_end > (end_time - start_time):
                sub_end = end_time - start_time

            # 转换为SRT时间格式
            start_str = self._format_srt_time(sub_start)
            end_str = self._format_srt_time(sub_end)

            # 写入字幕条目
            temp_file.write(f"{idx}\n")
            temp_file.write(f"{start_str} --> {end_str}\n")

            # 写入字幕文本（原文和译文）
            if seg.text_primary:
                temp_file.write(f"{seg.text_primary}\n")
            if seg.text_secondary:
                temp_file.write(f"{seg.text_secondary}\n")
            temp_file.write("\n")

        temp_file.close()
        print(f"[连续播放字幕] 字幕文件已创建: {temp_file.name}")

        # 将临时文件添加到清理列表
        self.temp_subtitle_files.append(temp_file.name)

        return temp_file.name

    def _format_srt_time(self, seconds):
        """将秒数转换为SRT时间格式 HH:MM:SS,mmm"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        milliseconds = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"

    def _cleanup_temp_subtitle_files(self):
        """清理临时字幕文件"""
        import os

        if not self.temp_subtitle_files:
            return

        print(f"[清理] 开始清理 {len(self.temp_subtitle_files)} 个临时字幕文件...")
        cleaned_count = 0
        failed_files = []

        for temp_file in self.temp_subtitle_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    cleaned_count += 1
                    print(f"[清理] 已删除临时字幕文件: {temp_file}")
            except PermissionError:
                # 文件可能仍在被使用，记录但不报错
                print(f"[清理] 文件正在使用，稍后重试: {temp_file}")
                failed_files.append(temp_file)
            except Exception as e:
                print(f"[清理] 删除临时字幕文件失败: {temp_file}, 错误: {e}")
                failed_files.append(temp_file)

        # 只清除成功删除的文件，保留失败的以便下次重试
        self.temp_subtitle_files = failed_files
        print(f"[清理] 完成，成功删除 {cleaned_count} 个文件，{len(failed_files)} 个文件稍后重试")

    def stop_playback(self):
        """停止播放（快捷键：Esc）"""
        try:
            self.player.stop()
            self.set_status("播放已停止")
        except Exception as e:
            print(f"停止播放失败：{e}")



    def refresh_data(self):
        """刷新数据"""
        self.load_projects()
        self.update_stats()
        self.set_status("数据已刷新")

    def delete_selected(self):
        """删除选中的字幕片段"""
        selected = self.subtitle_list.get_selected_segments()
        if not selected:
            messagebox.showwarning("警告", "请先选择要删除的片段")
            return

        if not messagebox.askyesno("确认删除", f"确定要删除选中的 {len(selected)} 个片段吗？"):
            return

        for seg in selected:
            db_manager.delete_segment(seg.id)

        # 检查当前页是否为空，如果为空且不是第一页则跳转到上一页
        current_page = self.subtitle_list.current_page
        items_per_page = self.subtitle_list.items_per_page

        if self.current_project is None:
            total_count = db_manager.get_total_segment_count()
        else:
            total_count = db_manager.get_segment_count(self.current_project.id)

        # 如果当前页已空且不是第一页，跳转到上一页
        if total_count > 0 and current_page > 0 and current_page * items_per_page >= total_count:
            self.subtitle_list.current_page = current_page - 1

        self.refresh_current_page()
        self.update_stats()
        self.set_status(f"已删除 {len(selected)} 个片段")

    def run(self):
        """运行主窗口"""
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            print("收到键盘中断，强制退出...")
            self.force_exit()
        except Exception as e:
            print(f"主循环异常: {e}")
            self.force_exit()

    def force_exit(self):
        """强制退出程序"""
        print("执行强制退出...")
        try:
            # 停止播放器
            if hasattr(self, 'player') and self.player:
                self.player.stop()

            # 退出主循环
            if hasattr(self, 'root') and self.root:
                self.root.quit()
                self.root.destroy()
        except:
            pass

        # 强制退出进程
        import sys
        import os
        print("强制终止进程...")
        os._exit(0)

    def show_subtitle_tools_dialog(self):
        """显示字幕功能对话框（防止多开）"""
        try:
            # 检查窗口是否已存在
            if hasattr(self, 'subtitle_tools_window') and self.subtitle_tools_window and self.subtitle_tools_window.winfo_exists():
                # 窗口已存在，恢复显示并聚焦
                self.subtitle_tools_window.deiconify()  # 如果是最小化状态，先恢复
                self.subtitle_tools_window.lift()
                self.subtitle_tools_window.focus_force()
                self.set_status("字幕功能窗口已打开")
            else:
                # 创建新窗口
                from ui.dialogs.subtitle_tools_dialog import SubtitleToolsDialog
                dialog = SubtitleToolsDialog(self.root)
                self.subtitle_tools_window = dialog.dialog

                # 绑定关闭事件，清理引用
                def on_close_wrapper():
                    self.subtitle_tools_window.destroy()
                    self.subtitle_tools_window = None

                self.subtitle_tools_window.protocol("WM_DELETE_WINDOW", on_close_wrapper)
                self.set_status("已打开字幕功能窗口")
        except Exception as e:
            import traceback
            messagebox.showerror("错误", f"无法显示字幕功能: {e}\n\n{traceback.format_exc()}")
            self.set_status("字幕功能窗口打开失败")

    def show_help_dialog(self):
        """显示帮助对话框（防止多开）"""
        try:
            # 检查窗口是否已存在
            if self.help_window and self.help_window.winfo_exists():
                # 窗口已存在，恢复显示并聚焦
                self.help_window.deiconify()  # 如果是最小化状态，先恢复
                self.help_window.lift()
                self.help_window.focus_force()
                self.set_status("帮助窗口已打开")
            else:
                # 创建新窗口
                from help_manager import HelpWindow
                self.help_window = HelpWindow(self.root, on_close_callback=self._on_help_window_close)
                self.set_status("已打开帮助窗口")
        except Exception as e:
            messagebox.showerror("错误", f"无法显示帮助: {e}")

    def _on_help_window_close(self):
        """帮助窗口关闭回调"""
        self.help_window = None

    def edit_timeline(self, segment):
        """编辑片段时间轴"""
        try:
            from ui.dialogs.timeline_editor_dialog import TimelineEditorDialog
            dialog = TimelineEditorDialog(self.root, segment)
            # 对话框关闭后检查是否需要刷新数据
            self.root.wait_window(dialog.dialog)

            # 检查对话框的刷新标记，只有在需要时才刷新
            print(f"[主窗口] 检查对话框刷新标记...")
            print(f"[主窗口] hasattr(dialog.dialog, 'needs_refresh'): {hasattr(dialog.dialog, 'needs_refresh')}")
            if hasattr(dialog.dialog, 'needs_refresh'):
                print(f"[主窗口] dialog.dialog.needs_refresh: {dialog.dialog.needs_refresh}")

            if hasattr(dialog.dialog, 'needs_refresh') and dialog.dialog.needs_refresh:
                print("[主窗口] 时间轴已更新，刷新主界面数据...")
                # 刷新当前页面数据，保持当前页码
                self.refresh_current_page()
                self.set_status("时间轴已更新，数据已刷新")
                print("[主窗口] 主界面数据刷新完成")
            else:
                print("[主窗口] 时间轴未更新，无需刷新数据")

        except Exception as e:
            messagebox.showerror("错误", f"打开时间轴编辑器失败: {e}")

    def refresh_current_page(self):
        """刷新当前页面数据，保持当前页码和分页状态"""
        try:
            current_page = self.subtitle_list.current_page
            items_per_page = self.subtitle_list.items_per_page

            print(f"[主窗口] 开始刷新当前页面数据")
            print(f"[主窗口] 当前页码: {current_page}, 每页项目数: {items_per_page}")
            print(f"[主窗口] 当前项目: {self.current_project.name if self.current_project else '全部视频'}")

            if self.current_project is None:
                # 加载全部视频的当前页
                print(f"[主窗口] 加载全部视频的第 {current_page + 1} 页")
                segments = db_manager.get_all_segments(
                    offset=current_page * items_per_page,
                    limit=items_per_page
                )
                total_count = db_manager.get_total_segment_count()
            else:
                # 加载单个项目的当前页
                print(f"[主窗口] 加载项目 {self.current_project.id} 的第 {current_page + 1} 页")
                segments = db_manager.get_segments_by_project(
                    self.current_project.id,
                    offset=current_page * items_per_page,
                    limit=items_per_page
                )
                total_count = db_manager.get_segment_count(self.current_project.id)

            print(f"[主窗口] 从数据库加载了 {len(segments)} 个片段，总数: {total_count}")

            # 更新列表，保持当前页码
            self.subtitle_list.load_segments(segments)
            self.subtitle_list.update_pagination(current_page, total_count)

            print(f"[主窗口] 已刷新第 {current_page + 1} 页数据，显示 {len(segments)} 个片段")

        except Exception as e:
            print(f"[主窗口] 刷新当前页面失败：{e}")
            import traceback
            traceback.print_exc()
            # 如果刷新失败，回退到加载第一页

    # ========== 队列导出方法 ==========

    def _export_task_for_queue(self, task):
        """队列导出 - 完整任务导出（方案B）

        这个方法会执行完整的导出流程，包括：
        1. 切割所有片段
        2. 合并片段
        3. 生成字幕文件
        4. 创建完整的目录结构

        Args:
            task: ExportTask 对象

        Returns:
            (success: bool, error_msg: Optional[str])
        """
        try:
            print(f"[队列导出] 开始完整导出任务...")
            print(f"[队列导出] 任务ID: {task.task_id}")
            print(f"[队列导出] 片段数: {len(task.segments)}")
            print(f"[队列导出] 输出目录: {task.config.output_dir}")

            # 从任务中提取片段信息，转换为 SubtitleSegment 对象
            from database.models import SubtitleSegment

            # 🔍 DEBUG: 显示任务的原始片段信息
            print(f"[DEBUG-队列] 任务包含 {len(task.segments)} 个片段，视频路径: {task.video_path}")
            unique_project_ids = set()
            for i, seg_info in enumerate(task.segments):
                # 检查 seg_info 是否包含 project_id 属性
                if hasattr(seg_info, 'project_id'):
                    unique_project_ids.add(seg_info.project_id)
                    if i < 3:  # 只显示前3个
                        print(f"[DEBUG-队列] 片段 {i+1}: segment_id={seg_info.segment_id}, project_id={seg_info.project_id}")

            print(f"[DEBUG-队列] 检测到的唯一 project_id 数量: {len(unique_project_ids)}, IDs: {unique_project_ids}")

            # 🔍 修复跨项目检测：保留每个片段的原始 project_id
            # 不再强制所有片段使用同一个 project_id
            segments = []
            for seg_info in task.segments:
                # 优先使用片段自带的 project_id（跨项目场景）
                # 如果没有，则通过 video_path 查找项目 ID（单项目场景）
                if hasattr(seg_info, 'project_id') and seg_info.project_id is not None:
                    # 片段已包含 project_id，直接使用（跨项目导出的关键）
                    segment_project_id = seg_info.project_id
                else:
                    # 片段没有 project_id，通过 task.video_path 查找
                    # 这种情况通常只在老版本数据或单项目导出时出现
                    project = None
                    all_projects = db_manager.get_all_projects()
                    for p in all_projects:
                        if p.video_path == task.video_path:
                            project = p
                            break

                    if not project:
                        return False, f"无法找到项目: {task.video_path}"

                    segment_project_id = project.id

                # 创建 SubtitleSegment 对象，使用正确的 project_id
                segment = SubtitleSegment(
                    id=seg_info.segment_id,
                    project_id=segment_project_id,  # ✅ 使用保留的原始 project_id
                    index_num=seg_info.segment_id,
                    start_time=seg_info.start_time,
                    end_time=seg_info.end_time,
                    text=seg_info.subtitle_text
                )
                segments.append(segment)

            # 🔍 DEBUG: 显示转换后的 project_id 分布
            converted_project_ids = set(seg.project_id for seg in segments)
            print(f"[DEBUG-队列] 转换后的唯一 project_id 数量: {len(converted_project_ids)}, IDs: {converted_project_ids}")

            print(f"[队列导出] 已转换 {len(segments)} 个片段对象")

            # 创建 IntegratedExportDialog 实例（不显示对话框）
            from ui.dialogs.integrated_export_dialog import IntegratedExportDialog

            # 创建一个临时的导出对话框实例
            # 注意：我们不调用 create_dialog()，所以不会显示窗口
            dialog = object.__new__(IntegratedExportDialog)

            # 手动初始化必要的属性
            dialog.parent = self
            dialog.segments = segments
            dialog.is_processing = False
            dialog.cancel_flag = False
            dialog.queue_processor = self.queue_processor  # 传递处理器引用，用于取消检测

            # 初始化时间跟踪相关属性
            dialog.start_time = None
            dialog.time_update_running = False
            dialog._time_tracking_stopped = False

            # 创建虚拟的UI组件（避免AttributeError）
            class DummyWidget:
                def config(self, **kwargs): pass
                def after(self, delay, func):
                    # 立即执行回调，不延迟
                    try:
                        func()
                    except:
                        pass

            dialog.dialog = DummyWidget()
            dialog.start_button = DummyWidget()
            dialog.cancel_button = DummyWidget()
            dialog.progress_bar = DummyWidget()
            dialog.status_label = DummyWidget()

            # 设置导出模式和参数
            import tkinter as tk
            dialog.export_mode_var = tk.StringVar(value="reencode" if not task.config.fast_copy_mode else "fast")
            dialog.preset_var = tk.StringVar(value=task.config.encoding_preset or "veryfast")
            dialog.crf_var = tk.StringVar(value=str(task.config.crf or 24))

            # 转换命名模式：队列格式 → 对话框格式
            naming_mode_value = "index"  # 默认值
            if task.config.naming_mode == "sequence":
                naming_mode_value = "index"
            elif task.config.naming_mode == "sequence_subtitle":
                naming_mode_value = "subtitle"
            dialog.naming_mode = tk.StringVar(value=naming_mode_value)

            dialog.output_var = tk.StringVar(value=task.config.output_dir)
            dialog.resolution_var = tk.StringVar(value=task.config.target_resolution or "1920x1080")
            dialog.fps_var = tk.StringVar(value=str(task.config.target_fps or 25))

            # 初始化智能校验系统（如果可用）
            try:
                from ui.dialogs.integrated_export_dialog import SMART_VALIDATION_AVAILABLE, create_validation_config
                if SMART_VALIDATION_AVAILABLE:
                    dialog.smart_validation_enabled = True
                    dialog.validation_config = create_validation_config(
                        enabled=True,
                        auto_correct=True,
                        validation_level="standard"
                    )
                else:
                    dialog.smart_validation_enabled = False
            except:
                dialog.smart_validation_enabled = False

            # 准备项目信息
            from core.script_adapter import script_adapter
            dialog.project_info = script_adapter.get_project_info(segments)
            if not dialog.project_info:
                return False, "无法获取项目信息"

            # 创建日志方法（输出到控制台 + 回调到队列管理器）
            def log_message(msg):
                print(f"[队列导出] {msg}")
                # 如果处理器有日志回调，也调用它
                if hasattr(self, 'queue_processor') and self.queue_processor:
                    if hasattr(self.queue_processor, 'on_log_message') and self.queue_processor.on_log_message:
                        try:
                            self.queue_processor.on_log_message(task, msg)
                        except:
                            pass
            dialog.log_message = log_message

            # 创建进度更新方法（输出到控制台 + 回调到队列管理器）
            def update_progress(current, total, message):
                progress = (current / total) * 100 if total > 0 else 0
                print(f"[队列导出] 进度: {progress:.1f}% - {message}")
                # 如果处理器有进度回调，也调用它
                if hasattr(self, 'queue_processor') and self.queue_processor:
                    if hasattr(self.queue_processor, 'on_progress_update') and self.queue_processor.on_progress_update:
                        try:
                            self.queue_processor.on_progress_update(task, progress / 100.0)
                        except:
                            pass
            dialog.update_progress = update_progress

            # 创建片段完成回调（用于实时更新队列管理器的片段进度）
            processed_count = [0]  # 使用列表来在闭包中保持可变性
            def on_segment_exported(segment_index):
                """每个片段导出完成时的回调"""
                # 更新任务中对应片段的状态
                if 0 <= segment_index < len(task.segments):
                    task.segments[segment_index].is_processed = True
                    processed_count[0] += 1
                    # 🔄 关键修复：重新计算任务进度百分比（用于队列管理器UI的实时更新）
                    task.update_progress()
                    print(f"[队列导出] 片段 {segment_index + 1}/{len(task.segments)} 已完成，当前进度: {task.progress_percentage:.1f}%")

                    # 触发队列处理器的片段完成回调
                    if hasattr(self, 'queue_processor') and self.queue_processor:
                        if hasattr(self.queue_processor, 'on_segment_complete') and self.queue_processor.on_segment_complete:
                            try:
                                # 创建一个临时的片段信息对象用于回调
                                segment_info = task.segments[segment_index]
                                self.queue_processor.on_segment_complete(task, segment_info)
                            except Exception as e:
                                print(f"[队列导出] 触发片段完成回调失败: {e}")

            # 将回调注入到 dialog 对象（IntegratedExportDialog 可以选择性地调用它）
            dialog.on_segment_exported = on_segment_exported

            # 准备数据
            result = script_adapter.prepare_segments_for_script(segments)
            if not result:
                return False, "无法准备片段数据"

            video_file, temp_srt_file, temp_dir = result
            output_path = task.config.output_dir

            print(f"[队列导出] 视频文件: {video_file}")
            print(f"[队列导出] 字幕文件: {temp_srt_file}")
            print(f"[队列导出] 输出路径: {output_path}")

            # 检查是否为跨项目导出
            if video_file == "CROSS_PROJECT":
                print(f"[队列导出] 使用跨项目导出模式")
                # 调用跨项目处理方法（同步调用，不使用线程）
                # 捕获返回的输出路径
                base_dir = dialog.process_cross_project_segments(temp_srt_file, output_path)
            else:
                print(f"[队列导出] 使用单项目导出模式")
                # 调用单项目处理方法（同步调用，不使用线程）
                # 捕获返回的输出路径
                base_dir = dialog.process_segments(video_file, temp_srt_file, output_path)

            # 保存输出路径到任务对象
            if base_dir:
                task.output_base_dir = base_dir
                print(f"[队列导出] 已保存输出路径: {base_dir}")

            print(f"[队列导出] ✓ 任务导出完成")
            return True, None

        except Exception as e:
            import traceback
            error_msg = f"导出失败: {str(e)}\n{traceback.format_exc()}"
            print(f"[队列导出] ✗ {error_msg}")
            return False, error_msg

    def _export_segment_for_queue(self, task, segment):
        """
        为队列处理器导出单个片段

        Args:
            task: ExportTask 对象
            segment: SegmentInfo 对象

        Returns:
            (success: bool, error_msg: Optional[str])
        """
        import os
        import subprocess
        from utils.file_utils import FileUtils

        try:
            print(f"[队列导出] 开始导出片段 {segment.segment_id}")
            print(f"[队列导出] 视频路径: {task.video_path}")
            print(f"[队列导出] 时间范围: {segment.start_time:.2f}s - {segment.end_time:.2f}s")

            # 获取配置
            config = task.config
            if not config:
                return False, "任务配置为空"

            # 创建输出目录
            output_dir = config.output_dir
            print(f"[队列导出] 输出目录: {output_dir}")
            os.makedirs(output_dir, exist_ok=True)

            # 确定文件名
            if config.naming_mode == "sequence_subtitle":
                # 按序号+字幕内容命名
                clean_text = FileUtils.clean_filename(segment.subtitle_text[:20])
                base_name = f"{segment.segment_id:03d}_{clean_text}"
            else:
                # 按序号命名
                base_name = f"{segment.segment_id:03d}"

            # 输出路径
            video_output = os.path.join(output_dir, f"{base_name}.mp4")
            audio_output = os.path.join(output_dir, f"{base_name}.mp3")

            # 根据导出模式选择处理方法
            if config.fast_copy_mode:
                # 快速模式：使用MoviePy
                print(f"[队列导出] 使用快速模式")
                result = self._export_segment_fast_mode(
                    task.video_path, segment, video_output, audio_output, config
                )
            else:
                # 重新编码：使用FFmpeg
                print(f"[队列导出] 使用重新编码")
                result = self._export_segment_reencode_mode(
                    task.video_path, segment, video_output, audio_output, config
                )

            if result[0]:
                print(f"[队列导出] ✓ 片段 {segment.segment_id} 导出成功")
                print(f"[队列导出]   视频: {video_output}")
                print(f"[队列导出]   音频: {audio_output}")
            else:
                print(f"[队列导出] ✗ 片段 {segment.segment_id} 导出失败: {result[1]}")

            return result

        except Exception as e:
            import traceback
            error_msg = f"导出片段失败: {str(e)}\n{traceback.format_exc()}"
            print(f"[队列导出] {error_msg}")
            return False, error_msg

    def _export_segment_fast_mode(self, video_path, segment, video_output, audio_output, config):
        """快速模式导出片段（使用MoviePy）"""
        try:
            from moviepy.editor import VideoFileClip, AudioFileClip
            from utils.file_utils import FileUtils

            # 检测文件类型
            is_audio_only = FileUtils.is_audio_file(video_path)

            if is_audio_only:
                # 音频文件
                clip = AudioFileClip(video_path)
                audio_clip = clip.subclip(segment.start_time, segment.end_time)
                audio_clip.write_audiofile(
                    audio_output,
                    bitrate='192k',
                    logger=None,
                    verbose=False
                )
                audio_clip.close()
                clip.close()
            else:
                # 视频文件
                clip = VideoFileClip(video_path)
                video_clip = clip.subclip(segment.start_time, segment.end_time)

                # 写入视频
                video_clip.write_videofile(
                    video_output,
                    codec='libx264',
                    preset=config.encoding_preset,
                    ffmpeg_params=['-crf', str(config.crf)],
                    audio_codec='aac',
                    logger=None,
                    verbose=False
                )

                # 提取音频
                if video_clip.audio is not None:
                    video_clip.audio.write_audiofile(
                        audio_output,
                        bitrate='192k',
                        logger=None,
                        verbose=False
                    )

                video_clip.close()
                clip.close()

            return True, None

        except Exception as e:
            return False, f"快速模式导出失败: {str(e)}"

    def _export_segment_reencode_mode(self, video_path, segment, video_output, audio_output, config):
        """重新编码导出片段（使用FFmpeg）"""
        try:
            import os
            import subprocess

            # 计算持续时间
            duration = segment.end_time - segment.start_time

            # 构建视频滤镜
            video_filters = []
            if config.target_resolution:
                video_filters.append(f"scale={config.target_resolution}")
            if config.target_fps:
                video_filters.append(f"fps={config.target_fps}")

            video_filter_str = ",".join(video_filters) if video_filters else "copy"

            # 构建FFmpeg命令
            cmd = [
                "ffmpeg",
                "-y",  # 覆盖输出文件
                "-ss", str(segment.start_time),  # 开始时间
                "-i", video_path,  # 输入文件
                "-t", str(duration),  # 持续时间
            ]

            if video_filter_str != "copy":
                cmd.extend(["-vf", video_filter_str])

            cmd.extend([
                "-c:v", "libx264",  # 视频编码器
                "-preset", config.encoding_preset,  # 编码预设
                "-crf", str(config.crf),  # 质量参数
                "-c:a", "aac",  # 音频编码器
                "-ar", "48000",  # 音频采样率
                "-ac", "2",  # 音频声道数
                "-b:a", "192k",  # 音频比特率
                video_output
            ])

            # 执行FFmpeg命令
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            if result.returncode != 0:
                return False, f"FFmpeg错误: {result.stderr[:200]}"

            # 提取音频
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

            return True, None

        except Exception as e:
            return False, f"重新编码导出失败: {str(e)}"
