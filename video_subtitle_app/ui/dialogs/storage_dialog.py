import tkinter as tk
from tkinter import ttk, messagebox
import os
import shutil
import json
import tempfile
from pathlib import Path

from database.manager import db_manager
from config.settings import app_config

# 导入图标管理器
try:
    from icon_manager import set_window_icon
    ICON_AVAILABLE = True
except ImportError:
    ICON_AVAILABLE = False
    def set_window_icon(window):
        pass
from utils.file_utils import FileUtils

class StorageDialog:
    """存储管理对话框"""
    
    def __init__(self, parent):
        self.parent = parent

        # 配置文件路径
        self.config_file = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'storage_dialog_config.json')

        # 默认配置
        self.default_config = {
            'column_widths': {
                'ID': 50,
                '项目名称': 250,  # 增加宽度以容纳类型标签
                '片段数': 80,
                '创建时间': 150,
                '视频路径': 600
            },
            'items_per_page': 20
        }

        # 加载配置
        self.config = self.load_config()

        self.create_dialog()
        self.refresh_stats()

    def load_config(self):
        """加载配置"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                # 合并默认配置，确保所有必要的键都存在
                for key, value in self.default_config.items():
                    if key not in config:
                        config[key] = value
                    elif isinstance(value, dict):
                        for sub_key, sub_value in value.items():
                            if sub_key not in config[key]:
                                config[key][sub_key] = sub_value
                return config
            else:
                return self.default_config.copy()
        except Exception as e:
            print(f"加载存储对话框配置失败: {e}")
            return self.default_config.copy()

    def save_config(self):
        """保存配置"""
        try:
            # 确保配置目录存在
            config_dir = os.path.dirname(self.config_file)
            os.makedirs(config_dir, exist_ok=True)

            # 保存当前列宽
            if hasattr(self, 'project_tree'):
                for col in self.config['column_widths'].keys():
                    try:
                        width = self.project_tree.column(col, 'width')
                        self.config['column_widths'][col] = width
                    except:
                        pass

            # 保存每页显示数量
            if hasattr(self, 'page_size_var'):
                try:
                    self.config['items_per_page'] = int(self.page_size_var.get())
                except:
                    pass

            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"保存存储对话框配置失败: {e}")
    
    def create_dialog(self):
        """创建对话框"""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("存储管理")
        #self.dialog.geometry("1200x1200")
        self.dialog.resizable(True, True)
        
        # 设置为模态对话框
        self.dialog.transient(self.parent)
        self.dialog.grab_set()

        # 设置窗口图标
        if ICON_AVAILABLE:
            set_window_icon(self.dialog)

        # 居中显示
        self.center_dialog()
        
        # 创建内容
        self.create_content()
        
        # 绑定事件
        self.dialog.protocol("WM_DELETE_WINDOW", self.close)
    
    def center_dialog(self):
        """居中显示对话框"""
        self.dialog.update_idletasks()

        # 使用设定的窗口尺寸
        dialog_width = 850
        dialog_height = 750

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
        title_label = ttk.Label(main_frame, text="存储管理", font=('', 14, 'bold'))
        title_label.pack(pady=(0, 20))
        
        # 项目管理区域（移除缓存详情和统计信息，让项目管理界面更大）
        self.create_project_management_section(main_frame)

        # 管理操作和存储信息
        self.create_management_and_storage_section(main_frame)

        # 按钮
        self.create_buttons(main_frame)
    
    def create_management_and_storage_section(self, parent):
        """创建管理操作和存储信息区域"""
        container_frame = ttk.Frame(parent)
        container_frame.pack(fill=tk.X, pady=(0, 15))

        # 左侧：管理操作
        management_frame = ttk.LabelFrame(container_frame, text="管理操作")
        management_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        # 管理操作按钮
        buttons_frame = ttk.Frame(management_frame)
        buttons_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(buttons_frame, text="清空数据库", command=self.clear_database).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(buttons_frame, text="清空所有缓存", command=self.clear_all_cache).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(buttons_frame, text="清理临时文件", command=self.clean_temp_files).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(buttons_frame, text="导出数据库", command=self.export_database).pack(side=tk.LEFT)

        # 右侧：存储信息
        storage_frame = ttk.LabelFrame(container_frame, text="存储信息")
        storage_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))

        # 存储信息内容
        self.storage_content = ttk.Frame(storage_frame)
        self.storage_content.pack(fill=tk.BOTH, padx=10, pady=10)

        # 这里会动态创建存储信息标签
    


    def create_project_management_section(self, parent):
        """创建项目管理区域"""
        project_frame = ttk.LabelFrame(parent, text="项目管理")
        project_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        # 项目列表
        list_frame = ttk.Frame(project_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 创建项目列表
        columns = ("ID", "项目名称", "片段数", "创建时间", "视频路径")
        self.project_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=12)

        # 设置列标题和宽度
        self.project_tree.heading("ID", text="ID")
        self.project_tree.heading("项目名称", text="项目名称")
        self.project_tree.heading("片段数", text="片段数")
        self.project_tree.heading("创建时间", text="创建时间")
        self.project_tree.heading("视频路径", text="视频路径")

        # 使用保存的列宽配置 - 所有列都可调整
        column_widths = self.config['column_widths']
        self.project_tree.column("ID", width=column_widths['ID'], minwidth=50, stretch=False)
        self.project_tree.column("项目名称", width=column_widths['项目名称'], minwidth=100, stretch=False)
        self.project_tree.column("片段数", width=column_widths['片段数'], minwidth=60, stretch=False)
        self.project_tree.column("创建时间", width=column_widths['创建时间'], minwidth=100, stretch=False)
        self.project_tree.column("视频路径", width=column_widths['视频路径'], minwidth=200, stretch=False)

        # 绑定列宽变化事件
        self.project_tree.bind('<Button-1>', self.on_column_click)
        self.project_tree.bind('<ButtonRelease-1>', self.on_column_release)
        self.project_tree.bind('<B1-Motion>', self.on_column_drag)

        # 项目列表滚动条
        project_v_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.project_tree.yview)
        project_h_scrollbar = ttk.Scrollbar(list_frame, orient=tk.HORIZONTAL, command=self.project_tree.xview)
        self.project_tree.configure(yscrollcommand=project_v_scrollbar.set, xscrollcommand=project_h_scrollbar.set)

        # 布局项目列表和滚动条
        self.project_tree.grid(row=0, column=0, sticky="nsew")
        project_v_scrollbar.grid(row=0, column=1, sticky="ns")
        project_h_scrollbar.grid(row=1, column=0, sticky="ew")

        # 配置grid权重
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)

        # 分页控制区域
        pagination_frame = ttk.Frame(project_frame)
        pagination_frame.pack(fill=tk.X, padx=10, pady=(0, 5))

        # 分页变量
        self.current_page = 1
        self.page_size = self.config['items_per_page']  # 使用保存的配置
        self.total_projects = 0
        self.total_pages = 1

        # 分页控件
        ttk.Button(pagination_frame, text="首页", command=self.go_first_page).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(pagination_frame, text="上页", command=self.go_prev_page).pack(side=tk.LEFT, padx=(0, 5))

        # 页码输入
        ttk.Label(pagination_frame, text="第").pack(side=tk.LEFT, padx=(10, 2))
        self.page_var = tk.StringVar(value="1")
        page_entry = ttk.Entry(pagination_frame, textvariable=self.page_var, width=5)
        page_entry.pack(side=tk.LEFT, padx=(0, 2))
        page_entry.bind('<Return>', self.go_to_page)

        self.page_info_label = ttk.Label(pagination_frame, text="页 (共1页)")
        self.page_info_label.pack(side=tk.LEFT, padx=(2, 10))

        ttk.Button(pagination_frame, text="跳转", command=self.go_to_page).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(pagination_frame, text="下页", command=self.go_next_page).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(pagination_frame, text="末页", command=self.go_last_page).pack(side=tk.LEFT, padx=(0, 5))

        # 每页显示数量 - 改为自定义数值输入，使用保存的配置
        ttk.Label(pagination_frame, text="每页").pack(side=tk.LEFT, padx=(20, 2))
        self.page_size_var = tk.StringVar(value=str(self.config['items_per_page']))
        page_size_entry = ttk.Entry(pagination_frame, textvariable=self.page_size_var, width=5)
        page_size_entry.pack(side=tk.LEFT, padx=(0, 2))
        page_size_entry.bind('<Return>', self.change_page_size)
        page_size_entry.bind('<FocusOut>', self.change_page_size)
        ttk.Label(pagination_frame, text="条").pack(side=tk.LEFT, padx=(2, 0))

        # 项目操作按钮
        project_buttons_frame = ttk.Frame(project_frame)
        project_buttons_frame.pack(fill=tk.X, padx=10, pady=(5, 10))

        ttk.Button(project_buttons_frame, text="刷新项目列表", command=self.refresh_project_list).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(project_buttons_frame, text="删除选中项目", command=self.delete_selected_project).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(project_buttons_frame, text="查看项目详情", command=self.show_project_details).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(project_buttons_frame, text="打开输入目录", command=self.open_input_directory).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(project_buttons_frame, text="全选", command=self.select_all).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(project_buttons_frame, text="取消全选", command=self.deselect_all).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(project_buttons_frame, text="反选", command=self.invert_selection).pack(side=tk.LEFT)

        # 加载项目列表
        self.refresh_project_list()

    def on_column_click(self, event):
        """列点击事件"""
        # 记录点击位置，用于检测是否在调整列宽
        self.column_resize_start = event.x

    def on_column_drag(self, event):
        """列拖拽事件"""
        # 检测是否在调整列宽
        pass

    def on_column_release(self, event):
        """列释放事件 - 保存列宽"""
        try:
            # 延迟保存，确保列宽已更新
            self.dialog.after(100, self.save_column_widths)
        except:
            pass

    def save_column_widths(self):
        """保存当前列宽"""
        try:
            if hasattr(self, 'project_tree'):
                for col in self.config['column_widths'].keys():
                    try:
                        width = self.project_tree.column(col, 'width')
                        self.config['column_widths'][col] = width
                    except:
                        pass
                self.save_config()
        except Exception as e:
            print(f"保存列宽失败: {e}")
    

    
    def create_buttons(self, parent):
        """创建按钮区域"""
        button_frame = ttk.Frame(parent)
        button_frame.pack(fill=tk.X)
        
        ttk.Button(button_frame, text="关闭", command=self.close).pack(side=tk.RIGHT)
    
    def refresh_stats(self):
        """刷新存储信息"""
        try:
            # 清空现有内容
            for widget in self.storage_content.winfo_children():
                widget.destroy()

            # 获取数据库统计
            db_stats = db_manager.get_database_stats()

            # 获取缓存目录统计
            cache_dir = app_config.cache_dir
            cache_size = FileUtils.get_directory_size(str(cache_dir)) if cache_dir.exists() else 0

            # 只显示数据库大小和缓存大小
            storage_info = [
                ("数据库大小", FileUtils.format_size(db_stats['db_size'])),
                ("缓存大小", FileUtils.format_size(cache_size))
            ]

            for label, value in storage_info:
                row_frame = ttk.Frame(self.storage_content)
                row_frame.pack(fill=tk.X, pady=3)

                ttk.Label(row_frame, text=f"{label}:", width=12).pack(side=tk.LEFT)
                ttk.Label(row_frame, text=value, foreground="blue", font=("", 9, "bold")).pack(side=tk.LEFT, padx=(5, 0))

        except Exception as e:
            messagebox.showerror("错误", f"刷新存储信息失败：{e}")
    

    
    def open_cache_dir(self):
        """打开缓存目录"""
        try:
            cache_dir = app_config.cache_dir
            if cache_dir.exists():
                os.startfile(str(cache_dir))
            else:
                messagebox.showwarning("警告", "缓存目录不存在")
        except Exception as e:
            messagebox.showerror("错误", f"打开缓存目录失败：{e}")
    
    def clean_temp_files(self):
        """清理临时文件（包括播放器临时文件、波形图、字幕缓存等）"""
        try:
            temp_files = []
            total_size = 0

            # 1. 清理缓存目录中的临时文件
            cache_dir = app_config.cache_dir
            if cache_dir.exists():
                for root, dirs, files in os.walk(cache_dir):
                    for file in files:
                        if file.startswith('temp_') or file.endswith('.tmp'):
                            file_path = os.path.join(root, file)
                            temp_files.append(file_path)
                            try:
                                total_size += os.path.getsize(file_path)
                            except:
                                pass

            # 2. 清理系统Temp目录中的播放器临时文件
            system_temp_dir = Path(tempfile.gettempdir())
            if system_temp_dir.exists():
                # 播放器临时文件：字幕、播放列表、合并视频/音频、波形图
                patterns = [
                    'tmp*.srt',      # 批量播放字幕
                    'tmp*.m3u',      # MPV播放列表
                    'tmp*.txt',      # FFmpeg concat列表
                    'tmp*.mp4',      # 临时合并视频
                    'tmp*.mp3',      # 临时合并音频
                    'waveform_*.png',      # 单段波形图
                    'multi_waveform_*.png', # 多段波形图
                    'temp_audio_*.wav'     # 临时音频（波形生成用）
                ]

                for pattern in patterns:
                    for file_path in system_temp_dir.glob(pattern):
                        temp_files.append(str(file_path))
                        try:
                            total_size += file_path.stat().st_size
                        except:
                            pass

            # 3. 清理专用字幕缓存目录
            subtitle_cache_dir = system_temp_dir / "video_subtitle_cache"
            if subtitle_cache_dir.exists():
                for file_path in subtitle_cache_dir.glob("*.srt"):
                    temp_files.append(str(file_path))
                    try:
                        total_size += file_path.stat().st_size
                    except:
                        pass

            # 4. 清理关键帧缓存
            keyframe_cache_dir = cache_dir / "keyframes"
            if keyframe_cache_dir.exists():
                for file_path in keyframe_cache_dir.glob("*.json"):
                    temp_files.append(str(file_path))
                    try:
                        total_size += file_path.stat().st_size
                    except:
                        pass

            # 5. 清理预加载缓存
            preload_cache_dir = cache_dir / "preload"
            if preload_cache_dir.exists():
                for file_path in preload_cache_dir.rglob("*"):
                    if file_path.is_file():
                        temp_files.append(str(file_path))
                        try:
                            total_size += file_path.stat().st_size
                        except:
                            pass

            if not temp_files:
                messagebox.showinfo("信息", "没有找到临时文件")
                return

            # 显示确认对话框（包含大小信息）
            size_text = FileUtils.format_size(total_size)
            result = messagebox.askyesno(
                "确认清理临时文件",
                f"找到 {len(temp_files)} 个临时文件（总计 {size_text}）：\n\n"
                f"• 缓存目录临时文件\n"
                f"• 播放器临时文件 (.srt, .m3u, .txt, .mp4, .mp3)\n"
                f"• 波形图文件 (.png, .wav)\n"
                f"• 字幕缓存文件\n"
                f"• 关键帧缓存 (.json)\n"
                f"• 预加载缓存\n\n"
                f"是否删除？"
            )

            if result:
                deleted_count = 0
                failed_count = 0
                for temp_file in temp_files:
                    try:
                        os.remove(temp_file)
                        deleted_count += 1
                    except Exception:
                        failed_count += 1

                if failed_count == 0:
                    messagebox.showinfo("完成", f"已清理 {deleted_count} 个临时文件（{size_text}）")
                else:
                    messagebox.showwarning(
                        "部分成功",
                        f"已清理 {deleted_count} 个临时文件（{size_text}）\n"
                        f"失败 {failed_count} 个文件（可能正在使用）"
                    )

                self.refresh_stats()

        except Exception as e:
            messagebox.showerror("错误", f"清理临时文件失败：{e}")

    def clear_all_cache(self):
        """清空所有缓存（包括主缓存和字幕缓存）"""
        try:
            cache_dir = app_config.cache_dir

            # 字幕缓存目录（MPV播放器使用）
            subtitle_cache_dir = Path(tempfile.gettempdir()) / "video_subtitle_cache"

            # 计算总缓存大小
            total_size = 0
            main_cache_size = 0
            subtitle_cache_size = 0

            if cache_dir.exists():
                main_cache_size = FileUtils.get_directory_size(str(cache_dir))
                total_size += main_cache_size

            if subtitle_cache_dir.exists():
                subtitle_cache_size = FileUtils.get_directory_size(str(subtitle_cache_dir))
                total_size += subtitle_cache_size

            if total_size == 0:
                messagebox.showinfo("信息", "缓存目录不存在或已为空，无需清理")
                return

            # 格式化大小显示
            total_size_text = FileUtils.format_size(total_size)
            main_cache_text = FileUtils.format_size(main_cache_size)
            subtitle_cache_text = FileUtils.format_size(subtitle_cache_size)

            # 第一次确认
            result = messagebox.askyesno(
                "确认清空缓存",
                f"这将删除所有缓存文件（总计 {total_size_text}）：\n\n"
                f"• 主缓存：{main_cache_text}\n"
                f"• 字幕缓存：{subtitle_cache_text}\n\n"
                "删除后需要重新导入视频才能播放片段。\n\n"
                "确定要继续吗？"
            )

            if result:
                # 第二次确认
                result2 = messagebox.askyesno(
                    "最终确认",
                    f"即将清空 {total_size_text} 的缓存数据！\n\n"
                    "此操作不可恢复，请再次确认！"
                )

                if not result2:
                    return

                deleted_count = 0

                # 删除主缓存目录内容
                if cache_dir.exists():
                    for item in cache_dir.iterdir():
                        try:
                            if item.is_file():
                                item.unlink()
                                deleted_count += 1
                            elif item.is_dir():
                                shutil.rmtree(item)
                                deleted_count += 1
                        except Exception as e:
                            print(f"删除缓存项失败 {item}: {e}")

                # 删除字幕缓存目录内容
                if subtitle_cache_dir.exists():
                    for item in subtitle_cache_dir.iterdir():
                        try:
                            if item.is_file():
                                item.unlink()
                                deleted_count += 1
                            elif item.is_dir():
                                shutil.rmtree(item)
                                deleted_count += 1
                        except Exception as e:
                            print(f"删除字幕缓存项失败 {item}: {e}")

                messagebox.showinfo("完成", f"已清空缓存（{total_size_text}）\n共删除 {deleted_count} 个文件/文件夹")
                self.refresh_stats()

        except Exception as e:
            messagebox.showerror("错误", f"清空缓存失败：{e}")

    def clear_database(self):
        """清空数据库"""
        try:
            # 获取统计信息
            stats = db_manager.get_database_stats()

            # 确认删除
            result = messagebox.askyesno(
                "确认清空数据库",
                f"这将删除所有数据库记录：\n"
                f"• {stats['project_count']} 个项目\n"
                f"• {stats['segment_count']} 个片段\n"
                f"• {stats['export_count']} 个导出记录\n\n"
                "此操作不可恢复，确定要继续吗？"
            )

            if result:
                # 再次确认
                result2 = messagebox.askyesno(
                    "最终确认",
                    "数据库清空后无法恢复，请再次确认！"
                )

                if result2:
                    db_manager.clear_all_data()
                    messagebox.showinfo("完成", "数据库已清空")
                    self.refresh_stats()

        except Exception as e:
            messagebox.showerror("错误", f"清空数据库失败：{e}")

    def export_database(self):
        """导出数据库"""
        try:
            from tkinter import filedialog

            # 选择导出位置
            export_path = filedialog.asksaveasfilename(
                title="导出数据库",
                defaultextension=".db",
                filetypes=[("数据库文件", "*.db"), ("所有文件", "*.*")],
                parent=self.dialog
            )

            if export_path:
                # 复制数据库文件
                db_path = app_config.db_file
                if db_path.exists():
                    shutil.copy2(str(db_path), export_path)
                    messagebox.showinfo("完成", f"数据库已导出到：\n{export_path}")
                else:
                    messagebox.showerror("错误", "数据库文件不存在")

        except Exception as e:
            messagebox.showerror("错误", f"导出数据库失败：{e}")

    def refresh_project_list(self):
        """刷新项目列表（分页显示）"""
        try:
            # 清空现有项目列表
            for item in self.project_tree.get_children():
                self.project_tree.delete(item)

            # 获取所有项目
            all_projects = db_manager.get_all_projects()
            self.total_projects = len(all_projects)

            # 计算总页数
            self.total_pages = max(1, (self.total_projects + self.page_size - 1) // self.page_size)

            # 确保当前页在有效范围内
            if self.current_page > self.total_pages:
                self.current_page = self.total_pages
            if self.current_page < 1:
                self.current_page = 1

            # 计算当前页的项目范围
            start_index = (self.current_page - 1) * self.page_size
            end_index = min(start_index + self.page_size, self.total_projects)

            # 显示当前页的项目
            current_projects = all_projects[start_index:end_index]

            for project in current_projects:
                # 获取项目的片段数量
                segment_count = db_manager.get_segment_count(project.id)

                # 格式化创建时间
                created_time = project.created_at.strftime("%Y-%m-%d %H:%M") if project.created_at else "未知"

                # 判断项目类型并添加类型标签
                is_audio = FileUtils.is_audio_file(project.video_path)
                media_type = "[音频]" if is_audio else "[视频]"
                project_name_with_type = f"{media_type} {project.name}"

                # 插入项目数据（使用带类型标签的项目名称）
                self.project_tree.insert("", "end", values=(
                    project.id,
                    project_name_with_type,  # 使用带类型标签的项目名称
                    segment_count,
                    created_time,
                    project.video_path
                ))

            # 更新分页信息
            self.update_pagination_info()

        except Exception as e:
            messagebox.showerror("错误", f"刷新项目列表失败：{e}")

    def update_pagination_info(self):
        """更新分页信息显示"""
        self.page_var.set(str(self.current_page))
        self.page_info_label.config(text=f"页 (共{self.total_pages}页, {self.total_projects}项)")

    def go_first_page(self):
        """跳转到首页"""
        self.current_page = 1
        self.refresh_project_list()

    def go_prev_page(self):
        """跳转到上一页"""
        if self.current_page > 1:
            self.current_page -= 1
            self.refresh_project_list()

    def go_next_page(self):
        """跳转到下一页"""
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.refresh_project_list()

    def go_last_page(self):
        """跳转到末页"""
        self.current_page = self.total_pages
        self.refresh_project_list()

    def go_to_page(self, event=None):
        """跳转到指定页"""
        try:
            page = int(self.page_var.get())
            if 1 <= page <= self.total_pages:
                self.current_page = page
                self.refresh_project_list()
            else:
                messagebox.showwarning("提示", f"页码必须在1-{self.total_pages}之间")
                self.page_var.set(str(self.current_page))
        except ValueError:
            messagebox.showerror("错误", "请输入有效的页码")
            self.page_var.set(str(self.current_page))

    def change_page_size(self, event=None):
        """改变每页显示数量"""
        try:
            new_size = int(self.page_size_var.get())
            if new_size <= 0:
                raise ValueError("页面大小必须大于0")
            if new_size > 1000:
                raise ValueError("页面大小不能超过1000")

            self.page_size = new_size
            self.current_page = 1  # 重置到第一页

            # 保存配置
            self.config['items_per_page'] = new_size
            self.save_config()

            self.refresh_project_list()
        except ValueError as e:
            if "页面大小" in str(e):
                messagebox.showwarning("提示", str(e), parent=self.dialog)
            else:
                messagebox.showwarning("提示", "请输入有效的数字", parent=self.dialog)
            self.page_size_var.set(str(self.page_size))

    def select_all(self):
        """全选所有项目"""
        try:
            # 获取所有项目
            all_items = self.project_tree.get_children()
            # 选中所有项目
            self.project_tree.selection_set(all_items)
        except Exception as e:
            messagebox.showerror("错误", f"全选失败：{e}")

    def deselect_all(self):
        """取消全选"""
        try:
            # 清除所有选中项
            self.project_tree.selection_remove(self.project_tree.selection())
        except Exception as e:
            messagebox.showerror("错误", f"取消全选失败：{e}")

    def invert_selection(self):
        """反选"""
        try:
            # 获取所有项目
            all_items = self.project_tree.get_children()
            # 获取当前选中的项目
            selected_items = self.project_tree.selection()

            # 计算需要选中的项目（未选中的项目）
            items_to_select = [item for item in all_items if item not in selected_items]

            # 先清除所有选中
            for item in selected_items:
                self.project_tree.selection_remove(item)

            # 选中之前未选中的项目
            for item in items_to_select:
                self.project_tree.selection_add(item)
        except Exception as e:
            messagebox.showerror("错误", f"反选失败：{e}")

    def delete_selected_project(self):
        """删除选中的项目（支持多选）"""
        try:
            selected_items = self.project_tree.selection()
            if not selected_items:
                messagebox.showwarning("提示", "请先选择要删除的项目")
                return

            # 获取所有选中项目的信息
            projects_to_delete = []
            total_segments = 0

            for selected_item in selected_items:
                values = self.project_tree.item(selected_item)['values']
                project_id = values[0]
                project_name_with_type = values[1]  # 包含类型标签的项目名称
                segment_count = values[2]

                # 提取纯项目名称（去掉类型标签）
                if project_name_with_type.startswith('[音频] '):
                    project_name = project_name_with_type[4:]  # 去掉 '[音频] '（4个字符）
                elif project_name_with_type.startswith('[视频] '):
                    project_name = project_name_with_type[4:]  # 去掉 '[视频] '（4个字符）
                else:
                    project_name = project_name_with_type  # 兜底处理

                projects_to_delete.append({
                    'id': project_id,
                    'name': project_name,
                    'segments': segment_count
                })
                total_segments += segment_count

            # 构建确认信息
            if len(projects_to_delete) == 1:
                # 单个项目删除
                project = projects_to_delete[0]
                confirm_msg = (
                    f"确定要删除项目 '{project['name']}' 吗？\n\n"
                    f"项目ID: {project['id']}\n"
                    f"片段数: {project['segments']}\n\n"
                    f"此操作将删除：\n"
                    f"• 项目记录\n"
                    f"• 所有字幕片段数据\n"
                    f"• 相关导出记录\n\n"
                    f"此操作不可恢复！"
                )
            else:
                # 多个项目删除
                project_list = "\n".join([f"  • {p['name']} (ID: {p['id']}, 片段数: {p['segments']})"
                                         for p in projects_to_delete[:5]])  # 最多显示5个
                if len(projects_to_delete) > 5:
                    project_list += f"\n  • ... 等共 {len(projects_to_delete)} 个项目"

                confirm_msg = (
                    f"确定要删除以下 {len(projects_to_delete)} 个项目吗？\n\n"
                    f"{project_list}\n\n"
                    f"总片段数: {total_segments}\n\n"
                    f"此操作将删除：\n"
                    f"• 所有项目记录\n"
                    f"• 所有字幕片段数据\n"
                    f"• 所有相关导出记录\n\n"
                    f"此操作不可恢复！"
                )

            # 确认删除
            result = messagebox.askyesno("确认删除项目", confirm_msg)

            if result:
                # 执行删除
                success_count = 0
                failed_projects = []

                for project in projects_to_delete:
                    success = db_manager.delete_project_completely(project['id'])
                    if success:
                        success_count += 1
                    else:
                        failed_projects.append(project['name'])

                # 显示结果
                if success_count == len(projects_to_delete):
                    messagebox.showinfo("成功", f"已成功删除 {success_count} 个项目")
                elif success_count > 0:
                    failed_msg = "、".join(failed_projects)
                    messagebox.showwarning(
                        "部分成功",
                        f"成功删除 {success_count} 个项目\n"
                        f"失败 {len(failed_projects)} 个项目：{failed_msg}"
                    )
                else:
                    messagebox.showerror("失败", "删除所有项目失败")

                # 刷新列表和统计
                self.refresh_project_list()
                self.refresh_stats()

        except Exception as e:
            messagebox.showerror("错误", f"删除项目失败：{e}")

    def show_project_details(self):
        """显示项目详情"""
        try:
            selected_items = self.project_tree.selection()
            if not selected_items:
                messagebox.showwarning("提示", "请先选择要查看的项目")
                return

            # 获取选中项目的信息
            selected_item = selected_items[0]
            values = self.project_tree.item(selected_item)['values']
            project_id = values[0]

            # 获取项目详细信息
            projects = db_manager.get_all_projects()
            project = None
            for p in projects:
                if p.id == project_id:
                    project = p
                    break

            if not project:
                messagebox.showerror("错误", "项目不存在")
                return

            # 获取项目统计信息
            segment_count = db_manager.get_segment_count(project.id)
            project_exports = db_manager.get_export_records(project.id)

            # 显示详情对话框
            detail_info = f"""项目详细信息：

基本信息：
• 项目ID: {project.id}
• 项目名称: {project.name}
• 创建时间: {project.created_at.strftime('%Y-%m-%d %H:%M:%S') if project.created_at else '未知'}

文件信息：
• 视频路径: {project.video_path}
• 字幕路径: {project.subtitle_path}
• 缓存目录: {project.cache_dir}

统计信息：
• 字幕片段数: {segment_count}
• 导出记录数: {len(project_exports)}

文件状态：
• 视频文件存在: {'是' if os.path.exists(project.video_path) else '否'}
• 字幕文件存在: {'是' if os.path.exists(project.subtitle_path) else '否'}
• 缓存目录存在: {'是' if os.path.exists(project.cache_dir) else '否'}"""

            messagebox.showinfo(f"项目详情 - {project.name}", detail_info)

        except Exception as e:
            messagebox.showerror("错误", f"显示项目详情失败：{e}")

    def open_input_directory(self):
        """打开输入目录（视频/音频文件所在目录）"""
        try:
            selected_items = self.project_tree.selection()
            if not selected_items:
                messagebox.showwarning("提示", "请先选择要打开目录的项目")
                return

            # 获取选中项目的信息
            selected_item = selected_items[0]
            values = self.project_tree.item(selected_item)['values']
            project_id = values[0]
            video_path = values[4]  # 视频路径在第5列

            # 检查视频路径是否存在
            if not os.path.exists(video_path):
                messagebox.showerror("错误", f"视频/音频文件不存在：\n{video_path}")
                return

            # 获取文件所在目录
            input_dir = os.path.dirname(video_path)

            # 检查目录是否存在
            if not os.path.exists(input_dir):
                messagebox.showerror("错误", f"目录不存在：\n{input_dir}")
                return

            # 打开目录
            os.startfile(input_dir)

        except Exception as e:
            messagebox.showerror("错误", f"打开输入目录失败：{e}")

    def close(self):
        """关闭对话框"""
        # 保存配置
        self.save_config()

        if self.dialog:
            self.dialog.grab_release()
            self.dialog.destroy()
            self.dialog = None

    def show(self):
        """显示对话框"""
        self.dialog.wait_window()
