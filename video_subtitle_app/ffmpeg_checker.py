#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FFmpeg环境检查模块
提供用户友好的FFmpeg环境变量检查和配置指导
"""

import os
import subprocess
import tkinter as tk
from tkinter import messagebox, ttk
import webbrowser
from icon_manager import set_window_icon

class FFmpegChecker:
    """FFmpeg环境检查器"""
    
    @staticmethod
    def check_ffmpeg_availability():
        """检查FFmpeg是否可用
        
        Returns:
            tuple: (is_available, error_details)
        """
        missing_tools = []
        
        # 检查ffmpeg
        if not FFmpegChecker._check_tool("ffmpeg"):
            missing_tools.append("ffmpeg")
            
        # 检查ffprobe
        if not FFmpegChecker._check_tool("ffprobe"):
            missing_tools.append("ffprobe")
            
        # 检查ffplay
        if not FFmpegChecker._check_tool("ffplay"):
            missing_tools.append("ffplay")
            
        if missing_tools:
            return False, missing_tools
        return True, []
    
    @staticmethod
    def _check_tool(tool_name):
        """检查单个工具是否可用"""
        try:
            result = subprocess.run(
                [tool_name, "-version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False
    
    @staticmethod
    def show_ffmpeg_setup_dialog(parent=None, missing_tools=None):
        """显示FFmpeg配置指导对话框"""
        dialog = FFmpegSetupDialog(parent, missing_tools or [])
        return dialog.result

class FFmpegSetupDialog(tk.Toplevel):
    """FFmpeg配置指导对话框"""
    
    def __init__(self, parent=None, missing_tools=None):
        if parent is None:
            # 创建临时根窗口
            self.temp_root = tk.Tk()
            self.temp_root.withdraw()
            parent = self.temp_root
        else:
            self.temp_root = None
            
        super().__init__(parent)
        
        self.missing_tools = missing_tools or []
        self.result = False
        
        self.title("FFmpeg环境配置")
        self.geometry("600x500")
        self.resizable(False, False)
        
        # 设置窗口图标
        try:
            set_window_icon(self)
        except:
            pass
        
        # 设置为模态对话框
        self.transient(parent)
        self.grab_set()
        
        self.create_widgets()
        self.center_window()
        
        # 绑定关闭事件
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # 等待对话框关闭
        self.wait_window()
    
    def center_window(self):
        """窗口居中显示"""
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")
    
    def create_widgets(self):
        """创建界面组件"""
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 标题
        title_label = ttk.Label(main_frame, text="⚠️ FFmpeg环境配置", 
                               font=("", 16, "bold"), foreground="red")
        title_label.pack(pady=(0, 15))
        
        # 问题描述
        problem_frame = ttk.LabelFrame(main_frame, text="检测到的问题", padding="10")
        problem_frame.pack(fill=tk.X, pady=(0, 15))
        
        if self.missing_tools:
            problem_text = f"系统环境变量中未找到以下FFmpeg工具：\n"
            for tool in self.missing_tools:
                problem_text += f"• {tool}\n"
        else:
            problem_text = "FFmpeg工具未正确配置到系统环境变量中。"
            
        problem_label = ttk.Label(problem_frame, text=problem_text, 
                                 font=("", 10), foreground="darkred")
        problem_label.pack(anchor=tk.W)
        
        # 解决方案
        solution_frame = ttk.LabelFrame(main_frame, text="解决方案", padding="10")
        solution_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        solution_text = """请按照以下步骤配置FFmpeg环境变量：

1. 下载FFmpeg
   • 访问官网：https://ffmpeg.org/download.html
   • 选择Windows版本下载
   • 解压到任意目录（如：C:\\ffmpeg）

2. 配置环境变量
   • 右键"此电脑" → "属性" → "高级系统设置"
   • 点击"环境变量"按钮
   • 在"系统变量"中找到"Path"，点击"编辑"
   • 点击"新建"，添加FFmpeg的bin目录路径
   • 例如：C:\\ffmpeg\\bin

3. 验证配置
   • 打开命令提示符（cmd）
   • 输入：ffmpeg -version
   • 如果显示版本信息，说明配置成功

4. 重启应用程序
   • 配置完成后，重启SubtitleLearn即可正常使用"""
        
        # 使用Text组件显示解决方案，支持滚动
        solution_text_widget = tk.Text(solution_frame, wrap=tk.WORD, height=12,
                                      font=("", 9), bg="#f8f9fa", relief=tk.FLAT)
        solution_text_widget.insert(tk.END, solution_text)
        solution_text_widget.config(state=tk.DISABLED)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(solution_frame, orient=tk.VERTICAL, 
                                 command=solution_text_widget.yview)
        solution_text_widget.config(yscrollcommand=scrollbar.set)
        
        solution_text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 按钮区域
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        # 下载FFmpeg按钮
        download_btn = ttk.Button(button_frame, text="下载FFmpeg", 
                                 command=self.open_ffmpeg_download)
        download_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # 重新检测按钮
        recheck_btn = ttk.Button(button_frame, text="重新检测", 
                                command=self.recheck_ffmpeg)
        recheck_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # 关闭按钮
        close_btn = ttk.Button(button_frame, text="关闭", 
                              command=self.on_close)
        close_btn.pack(side=tk.RIGHT)
    
    def open_ffmpeg_download(self):
        """打开FFmpeg下载页面"""
        try:
            webbrowser.open("https://ffmpeg.org/download.html")
        except Exception as e:
            messagebox.showerror("错误", f"无法打开浏览器：{e}")
    
    def recheck_ffmpeg(self):
        """重新检测FFmpeg"""
        is_available, missing_tools = FFmpegChecker.check_ffmpeg_availability()
        
        if is_available:
            messagebox.showinfo("检测成功", "✅ FFmpeg环境配置成功！\n\n所有必需的工具都已正确配置。")
            self.result = True
            self.on_close()
        else:
            missing_text = "、".join(missing_tools)
            messagebox.showwarning("检测失败", 
                                 f"❌ 仍然缺少以下工具：{missing_text}\n\n"
                                 f"请确保已正确配置环境变量并重启命令提示符。")
    
    def on_close(self):
        """关闭对话框"""
        self.grab_release()
        self.destroy()
        if self.temp_root:
            self.temp_root.destroy()

def check_and_prompt_ffmpeg(parent=None):
    """检查FFmpeg并在需要时显示配置对话框
    
    Args:
        parent: 父窗口
        
    Returns:
        bool: FFmpeg是否可用
    """
    is_available, missing_tools = FFmpegChecker.check_ffmpeg_availability()
    
    if not is_available:
        # 显示配置对话框
        return FFmpegChecker.show_ffmpeg_setup_dialog(parent, missing_tools)
    
    return True

# 测试函数
if __name__ == "__main__":
    result = check_and_prompt_ffmpeg()
    print(f"FFmpeg检查结果: {result}")
