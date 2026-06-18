"""
导出队列处理器

后台处理队列中的导出任务
"""

import time
import threading
from typing import Optional, Callable
from datetime import datetime

from core.export_queue import ExportQueue, ExportTask, TaskStatus, SegmentInfo
from utils.power_manager import PowerManager


class QueueProcessor:
    """队列处理器 - 后台处理导出任务"""

    def __init__(self, queue: ExportQueue):
        """初始化处理器

        Args:
            queue: 导出队列
        """
        self.queue = queue
        self.is_running = False
        self.is_paused = False
        self.cancel_requested = False  # 新增：取消请求标志
        self.current_task: Optional[ExportTask] = None
        self.worker_thread: Optional[threading.Thread] = None

        # 回调函数
        self.on_task_start: Optional[Callable[[ExportTask], None]] = None
        self.on_task_complete: Optional[Callable[[ExportTask], None]] = None
        self.on_task_failed: Optional[Callable[[ExportTask, str], None]] = None
        self.on_segment_complete: Optional[Callable[[ExportTask, SegmentInfo], None]] = None
        self.on_progress_update: Optional[Callable[[ExportTask, float], None]] = None
        self.on_status_change: Optional[Callable[[str], None]] = None
        self.on_log_message: Optional[Callable[[ExportTask, str], None]] = None  # 新增：日志消息回调
        self.on_all_tasks_complete: Optional[Callable[[], None]] = None  # 新增：所有任务完成回调

    def start(self):
        """启动处理器"""
        if self.is_running:
            return

        self.is_running = True
        self.is_paused = False
        self.worker_thread = threading.Thread(target=self._process_loop, daemon=True)
        self.worker_thread.start()

        self._notify_status_change("运行中")

    def pause(self):
        """暂停处理器"""
        if not self.is_running or self.is_paused:
            return

        self.is_paused = True
        self._notify_status_change("已暂停")

    def resume(self):
        """恢复处理器"""
        if not self.is_running or not self.is_paused:
            return

        self.is_paused = False
        self._notify_status_change("运行中")

    def stop(self):
        """停止处理器"""
        if not self.is_running:
            return

        self.is_running = False
        self.is_paused = False
        self.cancel_requested = True  # 设置取消标志

        # 等待工作线程结束
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2.0)

        # 重置当前任务状态
        if self.current_task and self.current_task.status == TaskStatus.PROCESSING:
            self.current_task.status = TaskStatus.PENDING
            self.current_task.start_time = None

        self.current_task = None
        # 注意：不要立即重置 cancel_requested，让后台任务有机会检测到取消信号
        # self.cancel_requested = False  # 暂时注释掉，让导出任务能检测到取消
        self._notify_status_change("已停止")

    def _process_loop(self):
        """处理循环（在后台线程中运行）"""
        while self.is_running:
            # 检查是否暂停
            if self.is_paused:
                time.sleep(0.5)
                continue

            # 获取下一个待处理任务
            pending_tasks = self.queue.get_tasks_by_status(TaskStatus.PENDING)
            if not pending_tasks:
                # 没有待处理任务，检查是否有已完成的任务
                completed_tasks = self.queue.get_tasks_by_status(TaskStatus.COMPLETED)
                if completed_tasks:
                    # 有已完成的任务，触发全部完成回调
                    print("[QueueProcessor] 所有任务已完成，触发完成回调")
                    if self.on_all_tasks_complete:
                        self.on_all_tasks_complete()

                print("[QueueProcessor] 所有任务已完成，自动停止处理器")
                self.is_running = False
                break

            # 处理第一个待处理任务
            task = pending_tasks[0]
            self._process_task(task)

        # 循环结束
        self._notify_status_change("已停止")

    def _process_task(self, task: ExportTask):
        """处理单个任务

        Args:
            task: 要处理的任务
        """
        # 阻止系统休眠
        PowerManager.prevent_sleep()

        try:
            # 重置取消标志（开始新任务时）
            self.cancel_requested = False

            # 更新任务状态
            task.status = TaskStatus.PROCESSING
            task.start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            task.processed_segments = 0
            task.failed_segments = 0
            task.progress_percentage = 0.0
            self.current_task = task

            # 通知任务开始
            if self.on_task_start:
                self.on_task_start(task)

            # 记录开始时间
            start_timestamp = time.time()

            # 检查是否有完整任务导出函数（方案B）
            if hasattr(self, 'export_task_func') and self.export_task_func:
                print(f"[QueueProcessor] 使用完整导出流程...")

                # 检查是否需要停止（在开始导出前检查）
                if not self.is_running or self.cancel_requested:
                    print(f"[QueueProcessor] 任务被取消，停止导出")
                    task.status = TaskStatus.PENDING
                    task.start_time = None
                    return

                success, error_msg = self.export_task_func(task)

                # 更新任务状态
                task.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                task.elapsed_time = time.time() - start_timestamp

                # 检查是否被取消（导出完成后再次检查）
                if not self.is_running or self.cancel_requested:
                    print(f"[QueueProcessor] 任务在导出过程中被取消")
                    task.status = TaskStatus.PENDING
                    task.start_time = None
                    return

                if success:
                    task.processed_segments = task.total_segments
                    task.progress_percentage = 100.0
                    task.status = TaskStatus.COMPLETED
                    if self.on_task_complete:
                        self.on_task_complete(task)
                else:
                    task.failed_segments = task.total_segments
                    task.error_message = error_msg or "导出失败"
                    task.status = TaskStatus.FAILED
                    if self.on_task_failed:
                        self.on_task_failed(task, task.error_message)

                return

            # 否则使用逐片段处理（原有逻辑）
            print(f"[QueueProcessor] 使用逐片段导出流程...")

            # 处理每个片段
            for i, segment in enumerate(task.segments):
                # 检查是否需要停止或暂停
                while self.is_paused and self.is_running:
                    time.sleep(0.5)

                if not self.is_running:
                    # 任务被中断，重置状态
                    task.status = TaskStatus.PENDING
                    task.start_time = None
                    return

                # 处理片段
                success, error_msg = self._process_segment(task, segment)

                if success:
                    segment.is_processed = True
                    task.processed_segments += 1

                    # 通知片段完成
                    if self.on_segment_complete:
                        self.on_segment_complete(task, segment)
                else:
                    segment.error_message = error_msg
                    task.failed_segments += 1

                # 更新进度
                task.update_progress()

                # 计算剩余时间
                elapsed = time.time() - start_timestamp
                task.elapsed_time = elapsed
                if task.processed_segments > 0:
                    avg_time_per_segment = elapsed / task.processed_segments
                    remaining_segments = task.total_segments - task.processed_segments
                    task.remaining_time = avg_time_per_segment * remaining_segments

                # 通知进度更新
                if self.on_progress_update:
                    self.on_progress_update(task, task.progress_percentage)

            # 任务完成
            task.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            task.elapsed_time = time.time() - start_timestamp

            if task.failed_segments == 0:
                task.status = TaskStatus.COMPLETED
                if self.on_task_complete:
                    self.on_task_complete(task)
            else:
                task.status = TaskStatus.FAILED
                error_msg = f"部分片段处理失败 ({task.failed_segments}/{task.total_segments})"
                task.error_message = error_msg
                if self.on_task_failed:
                    self.on_task_failed(task, error_msg)

        except Exception as e:
            # 任务失败
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            task.end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if self.on_task_failed:
                self.on_task_failed(task, str(e))

        finally:
            # 恢复系统休眠设置
            PowerManager.allow_sleep()

            self.current_task = None

    def _process_segment(self, task: ExportTask, segment: SegmentInfo) -> tuple[bool, Optional[str]]:
        """处理单个片段

        Args:
            task: 任务对象
            segment: 片段信息

        Returns:
            (是否成功, 错误信息)
        """
        print(f"[QueueProcessor] 处理片段 {segment.segment_id}")

        # 调用外部注入的导出函数
        if hasattr(self, 'export_segment_func') and self.export_segment_func:
            try:
                print(f"[QueueProcessor] 调用导出函数...")
                result = self.export_segment_func(task, segment)
                print(f"[QueueProcessor] 导出函数返回: {result}")
                return result
            except Exception as e:
                import traceback
                error_msg = f"导出失败: {str(e)}\n{traceback.format_exc()}"
                print(f"[QueueProcessor] {error_msg}")
                return False, error_msg

        # 如果没有注入导出函数，返回错误
        print(f"[QueueProcessor] 错误：未设置导出函数")
        return False, "未设置导出函数"

    def set_export_function(self, func: Callable[[ExportTask, SegmentInfo], tuple[bool, Optional[str]]]):
        """设置导出函数（单片段导出）

        Args:
            func: 导出函数，接收 (task, segment)，返回 (success, error_msg)
        """
        self.export_segment_func = func

    def set_export_task_function(self, func: Callable[[ExportTask], tuple[bool, Optional[str]]]):
        """设置完整任务导出函数（方案B：完整导出）

        Args:
            func: 导出函数，接收整个任务，返回 (success, error_msg)
        """
        self.export_task_func = func

    def _notify_status_change(self, status: str):
        """通知状态变化

        Args:
            status: 状态描述
        """
        if self.on_status_change:
            self.on_status_change(status)

    def get_status(self) -> str:
        """获取处理器状态

        Returns:
            状态描述
        """
        if not self.is_running:
            return "已停止"
        elif self.is_paused:
            return "已暂停"
        else:
            return "运行中"
