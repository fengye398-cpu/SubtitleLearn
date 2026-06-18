"""
自定义消息框 - 避免 Windows MessageBox 导致非模态窗口最小化的问题
模仿 Windows 原生 MessageBox 样式
"""

import tkinter as tk

# 尝试导入图标管理器
try:
    from icon_manager import set_window_icon
    ICON_AVAILABLE = True
except ImportError:
    ICON_AVAILABLE = False
    def set_window_icon(window):
        pass


def showerror(title, message, parent=None):
    """显示错误对话框 - 模仿 Windows 原生样式，避免最小化问题"""
    _show_custom_dialog(title, message, parent, dialog_type="error")


def showwarning(title, message, parent=None):
    """显示警告对话框 - 模仿 Windows 原生样式，避免最小化问题"""
    _show_custom_dialog(title, message, parent, dialog_type="warning")


def showinfo(title, message, parent=None):
    """显示信息对话框 - 模仿 Windows 原生样式，避免最小化问题"""
    _show_custom_dialog(title, message, parent, dialog_type="info")


def showwarning_with_action(title, message, parent=None, on_confirm=None):
    """显示警告对话框（带确认和取消按钮）- 点击确认后执行回调函数"""
    _show_custom_dialog_with_buttons(title, message, parent, dialog_type="warning", on_confirm=on_confirm)


def _show_custom_dialog(title, message, parent, dialog_type="error", on_confirm=None):
    """内部函数：创建自定义对话框"""
    if parent:
        parent.update_idletasks()

    # 创建对话框
    dialog = tk.Toplevel(parent) if parent else tk.Toplevel()
    dialog.title(title)
    dialog.withdraw()

    # 窗口大小
    dialog_width = 500
    dialog_height = 250
    dialog.geometry(f"{dialog_width}x{dialog_height}")
    dialog.resizable(False, False)

    # 设置图标
    if ICON_AVAILABLE:
        set_window_icon(dialog)

    # 主容器
    main_frame = tk.Frame(dialog, bg="white")
    main_frame.pack(fill=tk.BOTH, expand=True)

    # 内容区域
    content_frame = tk.Frame(main_frame, bg="white", padx=20, pady=20)
    content_frame.pack(fill=tk.BOTH, expand=True)

    # 图标和消息区域
    msg_frame = tk.Frame(content_frame, bg="white")
    msg_frame.pack(fill=tk.BOTH, expand=True)

    # 图标 Canvas
    icon_canvas = tk.Canvas(msg_frame, width=40, height=40, bg="white", highlightthickness=0)
    icon_canvas.pack(side=tk.LEFT, padx=(0, 15), anchor=tk.N)

    # 根据类型绘制不同图标
    if dialog_type == "error":
        # 红色圆形 + 白色 X
        icon_canvas.create_oval(2, 2, 38, 38, fill="#D32F2F", outline="")
        icon_canvas.create_line(12, 12, 28, 28, fill="white", width=3, capstyle=tk.ROUND)
        icon_canvas.create_line(28, 12, 12, 28, fill="white", width=3, capstyle=tk.ROUND)
    elif dialog_type == "warning":
        # 黄色三角形 + 黑色感叹号
        icon_canvas.create_polygon(20, 5, 35, 35, 5, 35, fill="#FFC107", outline="")
        icon_canvas.create_text(20, 23, text="!", font=("Arial", 20, "bold"), fill="black")
    else:  # info
        # 蓝色圆形 + 白色 i
        icon_canvas.create_oval(2, 2, 38, 38, fill="#2196F3", outline="")
        icon_canvas.create_text(20, 20, text="i", font=("Arial", 20, "bold"), fill="white")

    # 消息文本
    message_label = tk.Label(msg_frame, text=message, font=("Segoe UI", 9),
                            bg="white", justify=tk.LEFT, anchor=tk.W, wraplength=380)
    message_label.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    # 分隔线
    separator = tk.Frame(main_frame, height=1, bg="#D0D0D0")
    separator.pack(fill=tk.X)

    # 按钮区域
    button_frame = tk.Frame(main_frame, bg="#F0F0F0")
    button_frame.pack(fill=tk.X)

    button_container = tk.Frame(button_frame, bg="#F0F0F0", padx=15, pady=12)
    button_container.pack(side=tk.RIGHT)

    def close_dialog():
        try:
            dialog.grab_release()
            dialog.destroy()
        except:
            pass
        finally:
            if parent:
                try:
                    parent.deiconify()
                    parent.lift()
                    parent.focus_force()
                except:
                    pass

            # 如果有回调函数，执行回调
            if on_confirm and callable(on_confirm):
                try:
                    on_confirm()
                except Exception as e:
                    print(f"[自定义消息框] 执行回调失败: {e}")

    # 确定按钮
    ok_button = tk.Button(button_container, text="确定", command=close_dialog,
                         width=12, height=1, font=("Segoe UI", 9),
                         relief=tk.FLAT, bg="#0078D7", fg="white",
                         activebackground="#005A9E", activeforeground="white",
                         cursor="hand2", borderwidth=0, highlightthickness=1,
                         highlightbackground="#0078D7", highlightcolor="#0078D7")
    ok_button.pack()

    # 悬停效果
    def on_enter(e):
        ok_button.config(bg="#005A9E")
    def on_leave(e):
        ok_button.config(bg="#0078D7")
    ok_button.bind("<Enter>", on_enter)
    ok_button.bind("<Leave>", on_leave)

    # 绑定事件
    dialog.protocol("WM_DELETE_WINDOW", close_dialog)
    dialog.bind("<Return>", lambda e: close_dialog())
    dialog.bind("<Escape>", lambda e: close_dialog())

    # 居中
    dialog.update_idletasks()
    if parent:
        try:
            x = parent.winfo_x() + (parent.winfo_width() - dialog_width) // 2
            y = parent.winfo_y() + (parent.winfo_height() - dialog_height) // 2
            dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
        except:
            dialog.geometry(f"{dialog_width}x{dialog_height}")
    else:
        # 屏幕居中
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()
        x = (screen_width - dialog_width) // 2
        y = (screen_height - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")

    # 显示
    if parent:
        dialog.transient(parent)
    dialog.deiconify()
    dialog.grab_set()
    dialog.lift()
    dialog.focus_force()
    ok_button.focus_set()

    # 等待关闭
    try:
        dialog.wait_window()
    except:
        pass

    # 确保父窗口正常
    if parent:
        try:
            parent.deiconify()
            parent.lift()
            parent.focus_force()
        except:
            pass


def _show_custom_dialog_with_buttons(title, message, parent, dialog_type="warning", on_confirm=None):
    """内部函数：创建带确认和取消按钮的自定义对话框"""
    if parent:
        parent.update_idletasks()

    # 创建对话框
    dialog = tk.Toplevel(parent) if parent else tk.Toplevel()
    dialog.title(title)
    dialog.withdraw()

    # 窗口大小
    dialog_width = 500
    dialog_height = 250
    dialog.geometry(f"{dialog_width}x{dialog_height}")
    dialog.resizable(False, False)

    # 设置图标
    if ICON_AVAILABLE:
        set_window_icon(dialog)

    # 主容器
    main_frame = tk.Frame(dialog, bg="white")
    main_frame.pack(fill=tk.BOTH, expand=True)

    # 内容区域
    content_frame = tk.Frame(main_frame, bg="white", padx=20, pady=20)
    content_frame.pack(fill=tk.BOTH, expand=True)

    # 图标和消息区域
    msg_frame = tk.Frame(content_frame, bg="white")
    msg_frame.pack(fill=tk.BOTH, expand=True)

    # 图标 Canvas
    icon_canvas = tk.Canvas(msg_frame, width=40, height=40, bg="white", highlightthickness=0)
    icon_canvas.pack(side=tk.LEFT, padx=(0, 15), anchor=tk.N)

    # 根据类型绘制不同图标
    if dialog_type == "error":
        # 红色圆形 + 白色 X
        icon_canvas.create_oval(2, 2, 38, 38, fill="#D32F2F", outline="")
        icon_canvas.create_line(12, 12, 28, 28, fill="white", width=3, capstyle=tk.ROUND)
        icon_canvas.create_line(28, 12, 12, 28, fill="white", width=3, capstyle=tk.ROUND)
    elif dialog_type == "warning":
        # 黄色三角形 + 黑色感叹号
        icon_canvas.create_polygon(20, 5, 35, 35, 5, 35, fill="#FFC107", outline="")
        icon_canvas.create_text(20, 23, text="!", font=("Arial", 20, "bold"), fill="black")
    else:  # info
        # 蓝色圆形 + 白色 i
        icon_canvas.create_oval(2, 2, 38, 38, fill="#2196F3", outline="")
        icon_canvas.create_text(20, 20, text="i", font=("Arial", 20, "bold"), fill="white")

    # 消息文本
    message_label = tk.Label(msg_frame, text=message, font=("Segoe UI", 9),
                            bg="white", justify=tk.LEFT, anchor=tk.W, wraplength=380)
    message_label.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    # 分隔线
    separator = tk.Frame(main_frame, height=1, bg="#D0D0D0")
    separator.pack(fill=tk.X)

    # 按钮区域
    button_frame = tk.Frame(main_frame, bg="#F0F0F0")
    button_frame.pack(fill=tk.X)

    button_container = tk.Frame(button_frame, bg="#F0F0F0", padx=15, pady=12)
    button_container.pack(side=tk.RIGHT)

    # 用户的选择结果
    user_confirmed = [False]  # 使用列表来在闭包中修改

    def on_confirm_click():
        user_confirmed[0] = True
        try:
            dialog.grab_release()
            dialog.destroy()
        except:
            pass
        finally:
            if parent:
                try:
                    parent.deiconify()
                    parent.lift()
                    parent.focus_force()
                except:
                    pass

            # 执行回调
            if on_confirm and callable(on_confirm):
                try:
                    on_confirm()
                except Exception as e:
                    print(f"[自定义消息框] 执行回调失败: {e}")

    def on_cancel_click():
        user_confirmed[0] = False
        try:
            dialog.grab_release()
            dialog.destroy()
        except:
            pass
        finally:
            if parent:
                try:
                    parent.deiconify()
                    parent.lift()
                    parent.focus_force()
                except:
                    pass

    

    # 确认按钮
    ok_button = tk.Button(button_container, text="确认", command=on_confirm_click,
                         width=12, height=1, font=("Segoe UI", 9),
                         relief=tk.FLAT, bg="#0078D7", fg="white",
                         activebackground="#005A9E", activeforeground="white",
                         cursor="hand2", borderwidth=0, highlightthickness=1,
                         highlightbackground="#0078D7", highlightcolor="#0078D7")
    ok_button.pack(side=tk.LEFT)

    # 悬停效果
    def on_ok_enter(e):
        ok_button.config(bg="#005A9E")
    def on_ok_leave(e):
        ok_button.config(bg="#0078D7")
    ok_button.bind("<Enter>", on_ok_enter)
    ok_button.bind("<Leave>", on_ok_leave)

    

    # 绑定事件（关闭窗口 = 取消）
    dialog.protocol("WM_DELETE_WINDOW", on_cancel_click)
    dialog.bind("<Escape>", lambda e: on_cancel_click())
    dialog.bind("<Return>", lambda e: on_confirm_click())

    # 居中
    dialog.update_idletasks()
    if parent:
        try:
            x = parent.winfo_x() + (parent.winfo_width() - dialog_width) // 2
            y = parent.winfo_y() + (parent.winfo_height() - dialog_height) // 2
            dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
        except:
            dialog.geometry(f"{dialog_width}x{dialog_height}")
    else:
        # 屏幕居中
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()
        x = (screen_width - dialog_width) // 2
        y = (screen_height - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")

    # 显示
    if parent:
        dialog.transient(parent)
    dialog.deiconify()
    dialog.grab_set()
    dialog.lift()
    dialog.focus_force()
    ok_button.focus_set()

    # 等待关闭
    try:
        dialog.wait_window()
    except:
        pass

    # 确保父窗口正常
    if parent:
        try:
            parent.deiconify()
            parent.lift()
            parent.focus_force()
        except:
            pass
