import tkinter as tk
from tkinter import ttk
import time
from typing import Callable, Optional

class ProgressDialog:
    """进度对话框"""
    
    def __init__(self, parent, title: str = "处理中...", cancelable: bool = True):
        self.parent = parent
        self.title = title
        self.cancelable = cancelable
        self.cancelled = False
        
        # 回调函数
        self.cancel_callback: Optional[Callable] = None
        
        # 进度信息
        self.start_time = time.time()
        self.current_progress = 0
        self.total_progress = 100
        
        self.create_dialog()
    
    def create_dialog(self):
        """创建对话框"""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title(self.title)
        self.dialog.geometry("400x00")
        self.dialog.resizable(False, False)
        
        # 设置为模态对话框
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        
        # 居中显示
        self.center_dialog()
        
        # 创建内容
        self.create_content()
        
        # 绑定关闭事件
        self.dialog.protocol("WM_DELETE_WINDOW", self.on_close)
    
    def center_dialog(self):
        """居中显示对话框"""
        self.dialog.update_idletasks()
        
        # 获取父窗口位置和大小
        parent_x = self.parent.winfo_rootx()
        parent_y = self.parent.winfo_rooty()
        parent_width = self.parent.winfo_width()
        parent_height = self.parent.winfo_height()
        
        # 计算对话框位置
        dialog_width = self.dialog.winfo_reqwidth()
        dialog_height = self.dialog.winfo_reqheight()
        
        x = parent_x + (parent_width - dialog_width) // 2
        y = parent_y + (parent_height - dialog_height) // 2
        
        self.dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
    
    def create_content(self):
        """创建对话框内容"""
        main_frame = ttk.Frame(self.dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # 标题标签
        self.title_label = ttk.Label(main_frame, text=self.title, font=('', 12, 'bold'))
        self.title_label.pack(pady=(0, 10))
        
        # 当前操作标签
        self.operation_label = ttk.Label(main_frame, text="正在初始化...")
        self.operation_label.pack(pady=(0, 10))
        
        # 进度条
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            main_frame,
            variable=self.progress_var,
            maximum=100,
            length=300
        )
        self.progress_bar.pack(pady=(0, 10))
        
        # 进度信息
        progress_info_frame = ttk.Frame(main_frame)
        progress_info_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.progress_label = ttk.Label(progress_info_frame, text="0%")
        self.progress_label.pack(side=tk.LEFT)
        
        self.time_label = ttk.Label(progress_info_frame, text="")
        self.time_label.pack(side=tk.RIGHT)
        
        # 详细信息
        self.detail_label = ttk.Label(main_frame, text="", foreground="gray")
        self.detail_label.pack(pady=(0, 10))
        
        # 按钮
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)
        
        if self.cancelable:
            self.cancel_button = ttk.Button(
                button_frame,
                text="取消",
                command=self.cancel
            )
            self.cancel_button.pack(side=tk.RIGHT)
    
    def set_cancel_callback(self, callback: Callable):
        """设置取消回调"""
        self.cancel_callback = callback
    
    def update_progress(self, current: int, total: int, message: str = ""):
        """更新进度"""
        if self.cancelled:
            return
        
        self.current_progress = current
        self.total_progress = total
        
        # 计算百分比
        if total > 0:
            percentage = (current / total) * 100
            self.progress_var.set(percentage)
            self.progress_label.config(text=f"{percentage:.1f}%")
        else:
            self.progress_var.set(0)
            self.progress_label.config(text="0%")
        
        # 更新操作信息
        if message:
            self.operation_label.config(text=message)
        
        # 更新时间信息
        self.update_time_info()
        
        # 刷新界面
        self.dialog.update_idletasks()
    
    def update_time_info(self):
        """更新时间信息"""
        elapsed_time = time.time() - self.start_time
        
        if self.total_progress > 0 and self.current_progress > 0:
            # 估算剩余时间
            estimated_total_time = elapsed_time * self.total_progress / self.current_progress
            remaining_time = estimated_total_time - elapsed_time
            
            if remaining_time > 0:
                if remaining_time < 60:
                    time_text = f"剩余约 {int(remaining_time)} 秒"
                elif remaining_time < 3600:
                    time_text = f"剩余约 {int(remaining_time // 60)} 分钟"
                else:
                    hours = int(remaining_time // 3600)
                    minutes = int((remaining_time % 3600) // 60)
                    time_text = f"剩余约 {hours} 小时 {minutes} 分钟"
            else:
                time_text = "即将完成"
        else:
            # 只显示已用时间
            if elapsed_time < 60:
                time_text = f"已用 {int(elapsed_time)} 秒"
            elif elapsed_time < 3600:
                time_text = f"已用 {int(elapsed_time // 60)} 分钟"
            else:
                hours = int(elapsed_time // 3600)
                minutes = int((elapsed_time % 3600) // 60)
                time_text = f"已用 {hours} 小时 {minutes} 分钟"
        
        self.time_label.config(text=time_text)
    
    def set_detail(self, detail: str):
        """设置详细信息"""
        self.detail_label.config(text=detail)
    
    def set_title(self, title: str):
        """设置标题"""
        self.title_label.config(text=title)
        self.dialog.title(title)
    
    def cancel(self):
        """取消操作"""
        if not self.cancelable:
            return
        
        self.cancelled = True
        
        if self.cancel_callback:
            self.cancel_callback()
        
        self.close()
    
    def close(self):
        """关闭对话框"""
        if self.dialog:
            self.dialog.grab_release()
            self.dialog.destroy()
            self.dialog = None
    
    def on_close(self):
        """窗口关闭事件"""
        if self.cancelable:
            self.cancel()
    
    def is_cancelled(self) -> bool:
        """检查是否已取消"""
        return self.cancelled
    
    def show(self):
        """显示对话框"""
        if self.dialog:
            self.dialog.focus_set()
    
    def hide(self):
        """隐藏对话框"""
        if self.dialog:
            self.dialog.withdraw()
    
    def show_again(self):
        """重新显示对话框"""
        if self.dialog:
            self.dialog.deiconify()
