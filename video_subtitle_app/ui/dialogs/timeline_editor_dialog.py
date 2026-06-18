"""
字幕时间轴调整对话框（简化版）
提供精确的时间轴调整功能
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional
import os

from database.models import SubtitleSegment
from utils.format_utils import FormatUtils

# 导入图标管理器
try:
    from icon_manager import set_window_icon
    ICON_AVAILABLE = True
except ImportError:
    ICON_AVAILABLE = False
    def set_window_icon(window):
        pass

class TimelineEditorDialog:
    """时间轴编辑对话框"""

    def __init__(self, parent, segment: SubtitleSegment):
        self.parent = parent
        self.segment = segment
        self.original_start_time = segment.start_time
        self.original_end_time = segment.end_time

        # 对话框窗口
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(f"字幕时间轴调整 - 片段 #{segment.id}")
        self.dialog.geometry("600x450")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # 添加刷新标记，用于通知主界面是否需要刷新数据
        self.dialog.needs_refresh = False

        # 设置窗口图标
        if ICON_AVAILABLE:
            set_window_icon(self.dialog)

        # 时间调整
        self.start_time = segment.start_time
        self.end_time = segment.end_time

        # 微调步长（秒）- 从配置中加载
        self.adjust_step = self.load_adjust_step_from_config()

        # 记录当前生效的步长
        self.current_adjust_step = self.adjust_step

        # 保存模式
        self.save_mode = tk.StringVar(value="fast")

        # 相邻片段
        self.previous_segment = None
        self.next_segment = None

        # 创建界面
        self.setup_ui()
        self.load_adjacent_segments()
        self.update_display()

        # 绑定事件
        self.bind_events()

        # 绑定窗口关闭事件，保存微调步长
        self.dialog.protocol("WM_DELETE_WINDOW", self.on_dialog_close)

        # 居中显示
        self.center_dialog()

    def setup_ui(self):
        """设置用户界面"""
        # 主框架
        main_frame = ttk.Frame(self.dialog, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 标题栏
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(title_frame, text=f"字幕时间轴调整 - 片段 #{self.segment.id}",
                 font=('Arial', 12, 'bold')).pack()

        # 字幕内容区域
        self.create_subtitle_content_frame(main_frame)

        # 时间调整区域（新设计）
        self.create_time_adjustment_frame(main_frame)

        # 片段信息区域
        self.create_segment_info_frame(main_frame)

        # 保存选项区域（已隐藏，默认使用快速模式）
        # self.create_save_options_frame(main_frame)

        # 操作按钮区域
        self.create_button_frame(main_frame)

    def create_subtitle_content_frame(self, parent):
        """创建字幕内容区域（可编辑）"""
        frame = ttk.LabelFrame(parent, text="字幕内容（可编辑）", padding="5")
        frame.pack(fill=tk.X, pady=(0, 10))

        # 创建带滚动条的文本框容器
        text_container = ttk.Frame(frame)
        text_container.pack(fill=tk.BOTH, expand=True)

        # 显示原始字幕内容（第一行原文，第二行译文）
        content_text = f"{self.segment.text_primary or self.segment.text or ''}\n{self.segment.text_secondary or ''}"

        # 创建可编辑的文本框（高度6行，支持滚动）
        self.subtitle_text_widget = tk.Text(text_container, height=6, wrap=tk.WORD)
        self.subtitle_text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 添加垂直滚动条
        scrollbar = ttk.Scrollbar(text_container, orient=tk.VERTICAL, command=self.subtitle_text_widget.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.subtitle_text_widget.configure(yscrollcommand=scrollbar.set)

        # 插入初始内容
        self.subtitle_text_widget.insert('1.0', content_text)

    def create_time_adjustment_frame(self, parent):
        """创建时间调整区域（新设计）"""
        frame = ttk.LabelFrame(parent, text="时间调整", padding="10")
        frame.pack(fill=tk.X, pady=(0, 10))

        # 第一行：时间输入框
        time_frame = ttk.Frame(frame)
        time_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(time_frame, text="入点时间:", font=('Arial', 9)).pack(side=tk.LEFT)
        self.start_time_var = tk.StringVar(value=FormatUtils.format_time_with_ms(self.start_time))
        self.start_time_entry = ttk.Entry(time_frame, textvariable=self.start_time_var, width=12)
        self.start_time_entry.pack(side=tk.LEFT, padx=(5, 30))

        ttk.Label(time_frame, text="出点时间:", font=('Arial', 9)).pack(side=tk.LEFT)
        self.end_time_var = tk.StringVar(value=FormatUtils.format_time_with_ms(self.end_time))
        self.end_time_entry = ttk.Entry(time_frame, textvariable=self.end_time_var, width=12)
        self.end_time_entry.pack(side=tk.LEFT, padx=(5, 0))

        # 第二行：微调按钮
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(button_frame, text="时间调整:", font=('Arial', 9)).pack(side=tk.LEFT)

        # A按钮（入点调整）
        ttk.Button(button_frame, text="A左微调", width=8,
                  command=lambda: self.adjust_time_by_step('start', -1)).pack(side=tk.LEFT, padx=(5, 2))
        ttk.Button(button_frame, text="A右微调", width=8,
                  command=lambda: self.adjust_time_by_step('start', 1)).pack(side=tk.LEFT, padx=(2, 15))

        # B按钮（出点调整）
        ttk.Button(button_frame, text="B左微调", width=8,
                  command=lambda: self.adjust_time_by_step('end', -1)).pack(side=tk.LEFT, padx=(0, 2))
        ttk.Button(button_frame, text="B右微调", width=8,
                  command=lambda: self.adjust_time_by_step('end', 1)).pack(side=tk.LEFT, padx=2)

        # 第三行：微调步长设置
        step_frame = ttk.Frame(frame)
        step_frame.pack(fill=tk.X)

        ttk.Label(step_frame, text="微调系数(秒):", font=('Arial', 9)).pack(side=tk.LEFT)
        self.step_var = tk.StringVar(value=str(self.adjust_step))
        # 使用 tk.Spinbox 以支持背景颜色修改
        self.step_spinbox = tk.Spinbox(
            step_frame,
            textvariable=self.step_var,
            from_=0.001,
            to=10.0,
            increment=0.1,
            width=8,
            command=self.on_step_apply,
            bg='white',
            relief='solid',
            bd=1
        )
        self.step_spinbox.pack(side=tk.LEFT, padx=(5, 0))
        # 绑定回车和失焦事件
        self.step_spinbox.bind('<Return>', lambda e: self.on_step_apply())
        self.step_spinbox.bind('<FocusOut>', lambda e: self.on_step_apply())

        # 绑定键盘输入事件，修复小数点输入问题
        self.step_spinbox.bind('<KeyRelease>', self.on_step_key_release)

        # 添加记忆功能提示
        #memory_label = ttk.Label(step_frame, text="💾 自动记忆", font=('Arial', 8), foreground='gray')
        #memory_label.pack(side=tk.LEFT, padx=(10, 0))

    def on_step_key_release(self, event):
        """处理键盘输入事件，修复小数点输入问题"""
        try:
            # 获取当前输入值
            current_value = self.step_var.get().strip()

            # 如果输入为空，不处理
            if not current_value:
                return

            # 检查是否是数字输入（包括小数点）
            if current_value.count('.') <= 1:
                try:
                    # 尝试转换为浮点数验证
                    float_val = float(current_value)
                    # 如果转换成功，且格式正确（没有前导零问题），则不处理
                    if current_value == str(float_val) or current_value.startswith('0.') or current_value == '0' or current_value.startswith('0.0'):
                        return
                except ValueError:
                    # 如果不是有效数字，可能需要修正格式
                    pass

            # 修正格式：如果是类似 "01" 这样的格式，转换为 "1"
            if current_value.startswith('0') and len(current_value) > 1 and '.' not in current_value:
                corrected_value = str(int(current_value))
                self.step_var.set(corrected_value)

            # 如果是 "0.1" 这样的正确格式，保持不变
            elif current_value.startswith('0.') and len(current_value) >= 3:
                try:
                    float_val = float(current_value)
                    # 保持原格式不变
                    pass
                except ValueError:
                    pass

        except Exception as e:
            print(f"键盘输入处理失败: {e}")

    def create_segment_info_frame(self, parent):
        """创建片段信息区域"""
        frame = ttk.LabelFrame(parent, text="片段信息", padding="5")
        frame.pack(fill=tk.X, pady=(0, 10))

        self.info_label = ttk.Label(frame, text="")
        self.info_label.pack()

    def create_save_options_frame(self, parent):
        """创建保存选项区域"""
        frame = ttk.LabelFrame(parent, text="保存选项", padding="5")
        frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Radiobutton(frame, text="快速模式：不更新数据库，导出片段字幕仍用旧时间点。",
                       variable=self.save_mode, value="fast").pack(anchor=tk.W)
        ttk.Radiobutton(frame, text="完整模式：更新数据库，导出片段字幕用新时间点。",
                       variable=self.save_mode, value="full").pack(anchor=tk.W)

    def create_button_frame(self, parent):
        """创建操作按钮区域"""
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(frame, text="预览播放", command=self.preview_play).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(frame, text="重置", command=self.reset_timeline).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(frame, text="取消", command=self.cancel).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(frame, text="保存修改", command=self.save_changes).pack(side=tk.RIGHT, padx=(0, 5))

    def bind_events(self):
        """绑定事件处理"""
        # 时间输入框事件（失焦验证，避免打断用户编辑）
        self.start_time_entry.bind('<FocusOut>', lambda e: self.validate_time_input('start'))
        self.start_time_entry.bind('<Return>', lambda e: self.validate_time_input('start'))
        self.end_time_entry.bind('<FocusOut>', lambda e: self.validate_time_input('end'))
        self.end_time_entry.bind('<Return>', lambda e: self.validate_time_input('end'))

        # 微调步长输入框事件（监听输入变化，显示视觉提示）
        self.step_var.trace('w', lambda *args: self.on_step_input_changed())

    def load_adjacent_segments(self):
        """加载相邻片段"""
        try:
            from database.manager import db_manager

            # 获取同一项目中的所有片段，按时间排序
            all_segments = db_manager.get_segments_by_project(
                self.segment.project_id,
                offset=0,
                limit=1000
            )

            # 按开始时间排序
            all_segments.sort(key=lambda s: s.start_time)

            # 找到当前片段的相邻片段
            for i, segment in enumerate(all_segments):
                if segment.id == self.segment.id:
                    if i > 0:
                        self.previous_segment = all_segments[i-1]
                    if i < len(all_segments) - 1:
                        self.next_segment = all_segments[i+1]
                    break

        except Exception as e:
            print(f"加载相邻片段失败: {e}")

    def on_step_input_changed(self):
        """输入框内容变化时的处理（显示视觉提示）"""
        try:
            input_value = self.step_var.get().strip()
            if not input_value:
                # 空值，显示黄色警告
                self.step_spinbox.config(bg='#ffff00')
                return

            # 尝试解析输入值
            try:
                input_step = float(input_value)
                # 检查范围有效性
                if input_step <= 0 or input_step > 10.0:
                    # 超出范围，显示淡红色
                    self.step_spinbox.config(bg='#FFCDD2')
                    return

                # 检查是否与当前生效值不同
                if abs(input_step - self.current_adjust_step) > 0.0001:
                    # 未生效，显示黄色背景
                    self.step_spinbox.config(bg='#ffff00')
                else:
                    # 已生效，恢复默认背景
                    self.step_spinbox.config(bg='white')
            except ValueError:
                # 无效输入，显示淡红色
                self.step_spinbox.config(bg='#FFCDD2')
        except Exception as e:
            print(f"步长输入变化处理失败: {e}")

    def on_step_apply(self):
        """应用步长修改（回车/失焦/点击上下箭头时触发）"""
        try:
            input_value = self.step_var.get().strip()

            # 防止清空
            if not input_value:
                self.step_var.set(str(self.current_adjust_step))
                self.step_spinbox.config(bg='white')
                return

            step_value = float(input_value)

            # 验证范围
            if step_value <= 0:
                step_value = 0.001
                self.step_var.set('0.001')
            elif step_value > 10.0:
                step_value = 10.0
                self.step_var.set('10.0')

            # 检查是否真的改变了
            if abs(step_value - self.current_adjust_step) < 0.0001:
                # 没有变化，恢复背景色即可
                self.step_spinbox.config(bg='white')
                return

            # 应用修改
            self.adjust_step = step_value
            self.current_adjust_step = step_value

            # 恢复背景色
            self.step_spinbox.config(bg='white')

            # 立即保存到配置（实时保存）
            self.save_adjust_step_to_config()

            print(f"[OK] 微调步长已设置为 {step_value} 秒（已保存到配置）")

        except ValueError:
            # 输入无效，重置为当前生效值
            self.step_var.set(str(self.current_adjust_step))
            self.step_spinbox.config(bg='white')
            print("[WARN] 输入无效，已恢复为之前的设置")

    def adjust_time_by_step(self, time_type: str, direction: int):
        """使用步长调整时间

        Args:
            time_type: 'start' 或 'end'
            direction: -1(左/减少) 或 1(右/增加)
        """
        try:
            # 确保步长有效（应用当前输入的步长）
            self.on_step_apply()

            delta = self.adjust_step * direction

            # 直接修改时间值（不需要删除/恢复trace，因为已经改为失焦验证）
            if time_type == 'start':
                new_time = max(0, self.start_time + delta)
                new_time = min(new_time, self.end_time - 0.1)
                self.start_time = new_time
                self.start_time_var.set(FormatUtils.format_time_with_ms(new_time))
            else:
                new_time = self.end_time + delta
                new_time = max(new_time, self.start_time + 0.1)
                self.end_time = new_time
                self.end_time_var.set(FormatUtils.format_time_with_ms(new_time))

            self.update_display()

        except Exception as e:
            print(f"按步长调整时间失败: {e}")

    def validate_time_input(self, time_type):
        """验证时间输入（失焦或回车时触发）"""
        try:
            if time_type == 'start':
                time_str = self.start_time_var.get()
                new_time = FormatUtils.parse_time(time_str)

                if new_time is not None:
                    # 格式正确，更新时间
                    self.start_time = max(0, min(new_time, self.end_time - 0.1))
                    self.start_time_var.set(FormatUtils.format_time_with_ms(self.start_time))
                else:
                    # 格式错误，静默恢复原值
                    self.start_time_var.set(FormatUtils.format_time_with_ms(self.start_time))
                    print(f"[时间验证] 入点时间格式错误，已恢复原值: {self.start_time}")
            else:
                time_str = self.end_time_var.get()
                new_time = FormatUtils.parse_time(time_str)

                if new_time is not None:
                    # 格式正确，更新时间
                    self.end_time = max(self.start_time + 0.1, new_time)
                    self.end_time_var.set(FormatUtils.format_time_with_ms(self.end_time))
                else:
                    # 格式错误，静默恢复原值
                    self.end_time_var.set(FormatUtils.format_time_with_ms(self.end_time))
                    print(f"[时间验证] 出点时间格式错误，已恢复原值: {self.end_time}")

            self.update_display()

        except Exception as e:
            print(f"时间输入验证失败: {e}")

    def update_display(self):
        """更新显示信息"""
        try:
            # 更新片段信息
            duration = self.end_time - self.start_time

            # 计算与相邻片段的关系
            prev_status = ""
            if self.previous_segment:
                if self.start_time >= self.previous_segment.end_time:
                    gap = self.start_time - self.previous_segment.end_time
                    prev_status = f"与片段#{self.previous_segment.id}: 间隔 {gap:.1f}秒 [OK]"
                else:
                    overlap = self.previous_segment.end_time - self.start_time
                    if overlap <= 0.5:
                        prev_status = f"与片段#{self.previous_segment.id}: 重叠 {overlap:.1f}秒 [WARN]"
                    else:
                        prev_status = f"与片段#{self.previous_segment.id}: 重叠 {overlap:.1f}秒 [ERROR]"

            next_status = ""
            if self.next_segment:
                if self.end_time <= self.next_segment.start_time:
                    gap = self.next_segment.start_time - self.end_time
                    next_status = f"与片段#{self.next_segment.id}: 间隔 {gap:.1f}秒 [OK]"
                else:
                    overlap = self.end_time - self.next_segment.start_time
                    if overlap <= 0.5:
                        next_status = f"与片段#{self.next_segment.id}: 重叠 {overlap:.1f}秒 [WARN]"
                    else:
                        next_status = f"与片段#{self.next_segment.id}: 重叠 {overlap:.1f}秒 [ERROR]"

            # 片段时长状态
            if 1.0 <= duration <= 10.0:
                duration_status = f"片段时长: {duration:.3f} 秒 [OK]"
            elif 0.5 <= duration <= 15.0:
                duration_status = f"片段时长: {duration:.3f} 秒 [WARN]"
            else:
                duration_status = f"片段时长: {duration:.3f} 秒 [ERROR]"

            # 组合信息
            info_parts = [duration_status]
            if prev_status:
                info_parts.append(prev_status)
            if next_status:
                info_parts.append(next_status)

            info_text = " | ".join(info_parts)
            self.info_label.config(text=info_text)

        except Exception as e:
            print(f"更新显示失败: {e}")

    def preview_play(self):
        """预览播放"""
        try:
            # 创建临时片段对象
            temp_segment = SubtitleSegment(
                id=self.segment.id,
                project_id=self.segment.project_id,
                start_time=self.start_time,
                end_time=self.end_time,
                text=self.segment.text,
                text_primary=self.segment.text_primary,
                text_secondary=self.segment.text_secondary,
                video_file=self.segment.video_file,
                audio_file=self.segment.audio_file,
                subtitle_file=self.segment.subtitle_file
            )

            # 尝试获取播放器
            player = None

            # 方法1：通过父窗口获取
            if hasattr(self.parent, 'player'):
                player = self.parent.player

            # 方法2：通过递归查找MainWindow
            if not player and hasattr(self.parent, 'winfo_toplevel'):
                root = self.parent.winfo_toplevel()

                def find_player(widget):
                    if hasattr(widget, 'player'):
                        return widget.player
                    for child in widget.winfo_children():
                        result = find_player(child)
                        if result:
                            return result
                    return None

                player = find_player(root)

            # 方法3：通过播放器工厂
            if not player:
                try:
                    from core.player_factory import get_player
                    player = get_player()
                except Exception:
                    pass

            if player and hasattr(player, 'play_segment'):
                player.play_segment(temp_segment)
            else:
                messagebox.showinfo("提示", "播放器不可用")

        except Exception as e:
            print(f"预览播放失败: {e}")
            messagebox.showerror("错误", f"预览播放失败: {e}")

    def reset_timeline(self):
        """重置时间轴"""
        try:
            # 恢复原始时间
            self.start_time = self.original_start_time
            self.end_time = self.original_end_time

            # 更新输入框显示（使用带毫秒的格式）
            self.start_time_var.set(FormatUtils.format_time_with_ms(self.start_time))
            self.end_time_var.set(FormatUtils.format_time_with_ms(self.end_time))

            # 更新显示
            self.update_display()

        except Exception as e:
            messagebox.showerror("错误", f"重置失败: {e}")

    def save_changes(self):
        """保存修改（时间轴和字幕内容）"""
        try:
            # 检查时间有效性
            if self.start_time >= self.end_time:
                messagebox.showerror("错误", "入点时间必须早于出点时间")
                return

            # 用户确认对话框
            confirm = messagebox.askyesno(
                "确认保存",
                "确定要保存修改吗？\n\n将会更新：\n• 字幕内容\n• 时间轴\n• 数据库\n• SRT源文件（自动备份）",
                icon='question'
            )
            if not confirm:
                return

            # 根据保存模式处理（默认快速模式）
            save_mode = self.save_mode.get()

            if save_mode == "fast":
                # 快速模式：更新数据库和SRT文件
                self.save_fast_mode()
            else:
                # 完整模式：重新生成文件
                self.save_full_mode()

        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {e}")

    def save_fast_mode(self):
        """快速模式保存（更新时间轴和字幕内容）"""
        try:
            from database.manager import db_manager
            import os
            import shutil

            # 1. 获取编辑后的字幕文本
            edited_text = self.subtitle_text_widget.get('1.0', 'end-1c').strip()

            # 按换行分隔原文和译文
            lines = edited_text.split('\n', 1)  # 最多分割成2部分
            text_primary = lines[0].strip() if len(lines) > 0 else ''
            text_secondary = lines[1].strip() if len(lines) > 1 else ''

            # 2. 更新数据库 - 时间轴
            db_manager.update_segment_times(
                self.segment.id,
                self.start_time,
                self.end_time
            )

            # 3. 更新数据库 - 字幕文本
            self.segment.text = edited_text  # 完整文本（兼容旧字段）
            self.segment.text_primary = text_primary
            self.segment.text_secondary = text_secondary
            db_manager.update_segment(self.segment)

            # 4. 更新SRT源文件
            self.update_srt_file(text_primary, text_secondary)

            # 5. 更新片段对象的属性
            self.segment.start_time = self.start_time
            self.segment.end_time = self.end_time

            # 6. 标记需要刷新主界面
            self.dialog.needs_refresh = True
            print(f"[时间轴编辑器] 快速模式保存成功，已设置刷新标记: {self.dialog.needs_refresh}")

            # 7. 询问用户是否跳转到文件路径； icon='info'  # ✅ 改为 'info'，会有提示音；question则是安静
            project = db_manager.get_project(self.segment.project_id)
            if project and project.subtitle_path:
                response = messagebox.askyesno(
                    "保存成功",
                    "字幕内容和时间轴已保存！\n\n是否打开文件所在文件夹？",
                    icon='info'
                )

                if response:
                    # 打开文件所在文件夹并选中文件
                    import os
                    import subprocess
                    import platform

                    srt_path = project.subtitle_path
                    if os.path.exists(srt_path):
                        try:
                            system = platform.system()
                            if system == 'Windows':
                                # Windows: 使用 explorer /select 选中文件
                                subprocess.run(['explorer', '/select,', os.path.abspath(srt_path)])
                            elif system == 'Darwin':
                                # macOS: 使用 open -R 选中文件
                                subprocess.run(['open', '-R', srt_path])
                            else:
                                # Linux: 打开文件夹（不选中文件）
                                folder_path = os.path.dirname(srt_path)
                                subprocess.run(['xdg-open', folder_path])

                            print(f"[时间轴编辑器] 已打开文件夹: {os.path.dirname(srt_path)}")
                        except Exception as e:
                            print(f"[错误] 打开文件夹失败: {e}")
                            messagebox.showwarning("警告", f"无法打开文件夹: {e}")
            else:
                messagebox.showinfo("成功", "字幕内容和时间轴已保存")

            print("[时间轴编辑器] 快速模式对话框即将关闭")
            self.dialog.destroy()

        except Exception as e:
            import traceback
            messagebox.showerror("错误", f"保存失败: {e}\n\n{traceback.format_exc()}")

    def update_srt_file(self, text_primary, text_secondary):
        """更新SRT源文件（字幕文本和时间轴）

        Args:
            text_primary: 原文
            text_secondary: 译文
        """
        try:
            import pysrt
            import os
            import shutil
            from database.manager import db_manager

            # 获取项目信息
            project = db_manager.get_project(self.segment.project_id)
            if not project:
                print("[警告] 无法获取项目信息，跳过SRT文件更新")
                return

            srt_path = project.subtitle_path
            if not os.path.exists(srt_path):
                messagebox.showwarning(
                    "警告",
                    f"无法找到SRT源文件，文件可能已被移动或删除。\n\n文件路径：{srt_path}\n\n只更新了数据库，源文件未更新。"
                )
                return

            # 备份SRT文件（固定备份文件名，每次覆盖）
            backup_path = srt_path.rsplit('.', 1)[0] + '.backup.srt'
            shutil.copy2(srt_path, backup_path)
            print(f"[时间轴编辑器] SRT文件已备份到: {backup_path}")

            # 读取SRT文件
            subs = pysrt.open(srt_path, encoding='utf-8-sig')

            # 查找匹配的字幕条目（双重匹配机制）
            found = False
            matched_sub = None
            match_method = ""

            # 方法1：序号匹配（优先，最可靠）
            if hasattr(self.segment, 'index_num') and self.segment.index_num:
                for sub in subs:
                    if sub.index == self.segment.index_num:
                        matched_sub = sub
                        match_method = "序号匹配"
                        found = True
                        print(f"[时间轴编辑器] 通过序号匹配找到SRT条目 #{sub.index}")
                        break

            # 方法2：时间匹配（备选）
            if not found:
                for sub in subs:
                    start_seconds = sub.start.ordinal / 1000.0
                    end_seconds = sub.end.ordinal / 1000.0

                    # 2.1 先尝试用原始时间匹配（最可能匹配）
                    if (abs(start_seconds - self.original_start_time) < 0.1 and
                        abs(end_seconds - self.original_end_time) < 0.1):
                        matched_sub = sub
                        match_method = "原始时间匹配"
                        found = True
                        print(f"[时间轴编辑器] 通过原始时间匹配找到SRT条目 #{sub.index}")
                        break

                    # 2.2 再尝试用新时间匹配（如果只改了文本）
                    if (abs(start_seconds - self.start_time) < 0.1 and
                        abs(end_seconds - self.end_time) < 0.1):
                        matched_sub = sub
                        match_method = "新时间匹配"
                        found = True
                        print(f"[时间轴编辑器] 通过新时间匹配找到SRT条目 #{sub.index}")
                        break

            # 如果没找到，显示警告
            if not found or not matched_sub:
                messagebox.showwarning(
                    "警告",
                    "在SRT文件中找不到匹配的字幕条目。\n\n可能原因：\n• 序号不匹配\n• 时间轴已多次变化\n• SRT文件已被外部修改\n\n数据库已更新，但源文件未更新。"
                )
                return

            # 找到后，同时更新文本和时间轴
            # 1. 更新字幕文本
            if text_secondary:
                # 双语字幕：原文\n译文
                matched_sub.text = f"{text_primary}\n{text_secondary}"
            else:
                # 单语字幕
                matched_sub.text = text_primary

            # 2. 更新时间轴（同步到SRT文件）
            matched_sub.start = pysrt.SubRipTime(seconds=self.start_time)
            matched_sub.end = pysrt.SubRipTime(seconds=self.end_time)

            print(f"[时间轴编辑器] SRT条目已更新:")
            print(f"  - 匹配方式: {match_method}")
            print(f"  - 条目序号: #{matched_sub.index}")
            print(f"  - 新时间轴: {matched_sub.start} --> {matched_sub.end}")
            print(f"  - 字幕文本: {matched_sub.text[:50]}...")

            # 保存SRT文件
            subs.save(srt_path, encoding='utf-8')
            print(f"[时间轴编辑器] SRT文件已保存: {srt_path}")

        except Exception as e:
            import traceback
            print(f"[错误] 更新SRT文件失败: {e}\n{traceback.format_exc()}")
            messagebox.showerror(
                "错误",
                f"更新SRT源文件失败: {e}\n\n数据库已更新，但源文件未更新。"
            )

    def save_full_mode(self):
        """完整模式保存（重新生成视频、音频、字幕文件）"""
        try:
            from database.manager import db_manager
            from core.video_processor import VideoProcessor
            from config.settings import app_config
            import threading

            # 确认操作
            confirm = messagebox.askyesno(
                "确认操作",
                "完整模式将重新生成片段的视频、音频、字幕文件，可能需要较长时间。\n\n是否继续？"
            )
            if not confirm:
                return

            # 禁用保存按钮，显示进度
            self.dialog.config(cursor="watch")
            self.set_status("正在重新生成文件...")

            def regenerate_worker():
                """后台线程执行文件重新生成"""
                try:
                    # 创建视频处理器
                    processor = VideoProcessor()

                    # 从配置获取编码参数
                    preset = app_config.get('ffmpeg.preset', 'veryfast')
                    crf = app_config.get('ffmpeg.crf', '24')

                    # 重新生成片段文件
                    result = processor.regenerate_segment_files(
                        self.segment,
                        self.start_time,
                        self.end_time,
                        preset=preset,
                        crf=crf
                    )

                    # 在主线程中更新UI
                    self.dialog.after(0, self.on_regenerate_complete, result)

                except Exception as e:
                    error_msg = str(e)
                    self.dialog.after(0, self.on_regenerate_failed, error_msg)

            # 在后台线程中执行文件重新生成
            threading.Thread(target=regenerate_worker, daemon=True).start()

        except Exception as e:
            messagebox.showerror("错误", f"完整模式保存失败: {e}")
            self.dialog.config(cursor="")

    def set_status(self, message: str):
        """设置状态信息（在片段信息区域显示）"""
        try:
            self.info_label.config(text=message)
            self.dialog.update_idletasks()
        except Exception:
            pass

    def on_regenerate_complete(self, result: dict):
        """文件重新生成完成回调"""
        try:
            self.dialog.config(cursor="")

            if result['success']:
                # 更新数据库
                from database.manager import db_manager

                db_manager.update_segment_times(
                    self.segment.id,
                    self.start_time,
                    self.end_time
                )

                # 保存旧文件路径用于清理
                old_video_file = self.segment.video_file
                old_audio_file = self.segment.audio_file
                old_subtitle_file = self.segment.subtitle_file

                # 更新片段对象的属性
                self.segment.start_time = self.start_time
                self.segment.end_time = self.end_time
                if result['video_file']:
                    self.segment.video_file = result['video_file']
                if result['audio_file']:
                    self.segment.audio_file = result['audio_file']
                if result['subtitle_file']:
                    self.segment.subtitle_file = result['subtitle_file']

                # 清理旧文件（如果文件名发生了变化）
                self._cleanup_old_files(
                    [old_video_file, old_audio_file, old_subtitle_file],
                    [result.get('video_file'), result.get('audio_file'), result.get('subtitle_file')]
                )

                # 清理处理过程中的临时文件
                self._cleanup_processing_temp_files()

                # 标记需要刷新主界面
                self.dialog.needs_refresh = True
                print(f"[时间轴编辑器] 完整模式保存成功，已设置刷新标记: {self.dialog.needs_refresh}")

                messagebox.showinfo(
                    "成功",
                    f"时间轴已保存（完整模式）\n\n"
                    f"视频文件：{'已更新' if result['video_file'] else '无'}\n"
                    f"音频文件：{'已更新' if result['audio_file'] else '无'}\n"
                    f"字幕文件：{'已更新' if result['subtitle_file'] else '无'}"
                )
                print("[时间轴编辑器] 完整模式对话框即将关闭")
                self.dialog.destroy()
            else:
                error_msg = result.get('error', '未知错误')
                messagebox.showerror("错误", f"文件重新生成失败：\n{error_msg}")
                self.update_display()

        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {e}")
            self.update_display()

    def on_regenerate_failed(self, error_msg: str):
        """文件重新生成失败回调"""
        try:
            self.dialog.config(cursor="")
            messagebox.showerror("错误", f"文件重新生成失败：\n{error_msg}")
            self.update_display()
        except Exception as e:
            print(f"错误回调失败: {e}")

    def _cleanup_old_files(self, old_files: list, new_files: list):
        """清理旧文件（如果文件名发生了变化）"""
        try:
            from utils.file_utils import FileUtils

            for old_file, new_file in zip(old_files, new_files):
                if old_file and os.path.exists(old_file):
                    # 如果新文件路径不同，说明文件名发生了变化，需要删除旧文件
                    if new_file and old_file != new_file:
                        FileUtils.safe_remove(old_file)
                        print(f"已清理旧文件: {old_file}")

        except Exception as e:
            print(f"清理旧文件失败: {e}")

    def _cleanup_processing_temp_files(self):
        """清理处理过程中产生的临时文件"""
        try:
            import tempfile
            from pathlib import Path
            from utils.file_utils import FileUtils

            cleaned_files = []

            # 1. 清理系统临时目录中的 MoviePy/FFmpeg 临时文件
            temp_dir = Path(tempfile.gettempdir())
            temp_patterns = [
                'moviepy_*', 'ffmpeg_*', 'video_export_*',
                'segment_*', '*_regenerate*', '*_processing*',
                'tmp*.m3u', 'tmp*.wav', 'tmp*.mp4', 'tmp*.mp3'
            ]

            print(f"[临时文件清理] 检查系统临时目录: {temp_dir}")

            for pattern in temp_patterns:
                temp_files = list(temp_dir.glob(pattern))
                for temp_file in temp_files:
                    try:
                        if temp_file.is_file():
                            # 只删除最近2小时内创建的文件
                            import time
                            file_age = time.time() - temp_file.stat().st_mtime
                            if file_age < 7200:  # 2小时
                                FileUtils.safe_remove(str(temp_file))
                                cleaned_files.append(str(temp_file))
                                print(f"[临时文件清理] 删除系统临时文件: {temp_file}")
                        elif temp_file.is_dir():
                            # 删除空的临时目录
                            try:
                                if not any(temp_file.iterdir()):
                                    FileUtils.safe_remove(str(temp_file))
                                    cleaned_files.append(str(temp_file))
                                    print(f"[临时文件清理] 删除空临时目录: {temp_file}")
                            except:
                                pass
                    except Exception as e:
                        print(f"[临时文件清理] 删除系统临时文件失败 {temp_file}: {e}")

            # 2. 清理工作目录中可能残留的临时文件
            workspace_dir = Path(os.getcwd())
            workspace_patterns = [
                '*.tmp', '*.temp', '*_temp.*', '*_tmp.*',
                '*_processing.*', '*_regenerate.*', '*_backup.*',
                'ffmpeg2pass-*.log', '*.log.mbtree'
            ]

            print(f"[临时文件清理] 检查工作目录: {workspace_dir}")

            for pattern in workspace_patterns:
                temp_files = list(workspace_dir.glob(pattern))
                for temp_file in temp_files:
                    try:
                        if temp_file.is_file():
                            FileUtils.safe_remove(str(temp_file))
                            cleaned_files.append(str(temp_file))
                            print(f"[临时文件清理] 删除工作目录临时文件: {temp_file}")
                    except Exception as e:
                        print(f"[临时文件清理] 删除工作目录临时文件失败 {temp_file}: {e}")

            # 3. 清理项目缓存目录中的临时文件（如果存在）
            try:
                from database.manager import db_manager
                project = db_manager.get_project(self.segment.project_id)
                if project and project.cache_dir:
                    cache_dir = Path(project.cache_dir)
                    if cache_dir.exists():
                        print(f"[临时文件清理] 检查项目缓存目录: {cache_dir}")

                        # 清理缓存目录中的临时文件
                        cache_temp_patterns = [
                            '*.tmp', '*.temp', '*_temp.*', '*_processing.*',
                            'ffmpeg2pass-*.log', '*.log.mbtree'
                        ]

                        for pattern in cache_temp_patterns:
                            temp_files = list(cache_dir.glob(pattern))
                            for temp_file in temp_files:
                                try:
                                    if temp_file.is_file():
                                        FileUtils.safe_remove(str(temp_file))
                                        cleaned_files.append(str(temp_file))
                                        print(f"[临时文件清理] 删除缓存目录临时文件: {temp_file}")
                                except Exception as e:
                                    print(f"[临时文件清理] 删除缓存目录临时文件失败 {temp_file}: {e}")
            except Exception as e:
                print(f"[临时文件清理] 检查项目缓存目录失败: {e}")

            # 4. 清理脚本适配器的临时文件
            try:
                from core.script_adapter import script_adapter
                script_adapter.cleanup_temp_files()
                print("[临时文件清理] 已清理脚本适配器临时文件")
            except Exception as e:
                print(f"[临时文件清理] 清理脚本适配器临时文件失败: {e}")

            # 5. 清理 Python 临时文件
            try:
                import glob
                python_temp_patterns = [
                    os.path.join(tempfile.gettempdir(), '__pycache__'),
                    os.path.join(tempfile.gettempdir(), '*.pyc'),
                    os.path.join(os.getcwd(), '__pycache__'),
                    os.path.join(os.getcwd(), '*.pyc')
                ]

                for pattern in python_temp_patterns:
                    for temp_file in glob.glob(pattern):
                        try:
                            temp_path = Path(temp_file)
                            if temp_path.is_file():
                                FileUtils.safe_remove(str(temp_path))
                                cleaned_files.append(str(temp_path))
                                print(f"[临时文件清理] 删除Python临时文件: {temp_path}")
                            elif temp_path.is_dir():
                                import shutil
                                shutil.rmtree(str(temp_path), ignore_errors=True)
                                cleaned_files.append(str(temp_path))
                                print(f"[临时文件清理] 删除Python临时目录: {temp_path}")
                        except Exception as e:
                            print(f"[临时文件清理] 删除Python临时文件失败 {temp_file}: {e}")
            except Exception as e:
                print(f"[临时文件清理] 清理Python临时文件失败: {e}")

            if cleaned_files:
                print(f"[临时文件清理] 总共清理了 {len(cleaned_files)} 个临时文件")
                for file in cleaned_files[:3]:  # 只显示前3个
                    print(f"  - {file}")
                if len(cleaned_files) > 3:
                    print(f"  ... 还有 {len(cleaned_files) - 3} 个文件")
            else:
                print("[临时文件清理] 无需清理的处理临时文件")

        except Exception as e:
            print(f"[临时文件清理] 清理处理临时文件失败: {e}")
            import traceback
            traceback.print_exc()

    def cancel(self):
        """取消操作"""
        self.dialog.destroy()

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

    def load_adjust_step_from_config(self):
        """从配置中加载微调步长"""
        try:
            from config.settings import app_config

            # 检查是否启用记忆功能
            remember_step = app_config.get('timeline_editor.remember_adjust_step', True)

            if remember_step:
                # 加载上次使用的步长
                last_step = app_config.get('timeline_editor.last_adjust_step', 0.1)
                print(f"[配置] 加载上次使用的微调步长: {last_step} 秒")
                return last_step
            else:
                # 使用默认步长
                default_step = app_config.get('timeline_editor.default_adjust_step', 0.1)
                print(f"[配置] 使用默认微调步长: {default_step} 秒")
                return default_step

        except Exception as e:
            print(f"[配置] 加载微调步长失败，使用默认值: {e}")
            return 0.1

    def save_adjust_step_to_config(self):
        """保存微调步长到配置"""
        try:
            from config.settings import app_config

            # 检查是否启用记忆功能
            remember_step = app_config.get('timeline_editor.remember_adjust_step', True)

            if remember_step and hasattr(self, 'current_adjust_step'):
                # 保存当前步长
                app_config.set('timeline_editor.last_adjust_step', self.current_adjust_step)
                app_config.save_config()
                print(f"[配置] 已保存微调步长: {self.current_adjust_step} 秒")

        except Exception as e:
            print(f"[配置] 保存微调步长失败: {e}")

    def on_dialog_close(self):
        """对话框关闭时的处理"""
        # 保存微调步长
        self.save_adjust_step_to_config()

        # 关闭对话框
        self.dialog.destroy()
