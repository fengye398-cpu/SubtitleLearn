"""
导出队列管理模块

提供导出任务的数据模型和队列管理功能
"""

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum
from pathlib import Path


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"      # 等待处理
    PROCESSING = "processing"  # 处理中
    COMPLETED = "completed"    # 已完成
    FAILED = "failed"          # 失败
    PAUSED = "paused"          # 暂停


@dataclass
class ExportConfig:
    """导出配置"""
    # 输出设置
    output_dir: str

    # 命名方式
    naming_mode: str = "sequence"  # sequence: 按序号, sequence_subtitle: 按序号+字幕

    # 编码参数
    encoding_preset: str = "veryfast"
    crf: int = 24
    target_resolution: Optional[str] = None  # 例如: "1920x1080"
    target_fps: Optional[float] = None  # 支持非整数帧率(如23.98)

    # 导出模式
    fast_copy_mode: bool = True  # True: 标准模式, False: 重新编码
    continuous_cut_mode: bool = False  # True: 连续切割, False: 片段切割

    # 智能校验
    smart_validation: bool = True
    auto_fix_deviation: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExportConfig':
        """从字典创建"""
        return cls(**data)


@dataclass
class SegmentInfo:
    """片段信息"""
    segment_id: int
    start_time: float
    end_time: float
    subtitle_text: str
    duration: float
    project_id: Optional[int] = None  # 所属项目ID（跨项目导出时必需）

    # 处理状态
    is_processed: bool = False
    output_path: Optional[str] = None
    file_size: Optional[int] = None  # 字节
    process_time: Optional[float] = None  # 秒
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SegmentInfo':
        """从字典创建"""
        return cls(**data)


@dataclass
class ExportTask:
    """导出任务"""
    # 基本信息
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project_name: str = ""
    video_path: str = ""

    # 任务配置
    segments: List[SegmentInfo] = field(default_factory=list)
    config: Optional[ExportConfig] = None

    # 任务状态
    status: TaskStatus = TaskStatus.PENDING
    create_time: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    start_time: Optional[str] = None
    end_time: Optional[str] = None

    # 进度信息
    total_segments: int = 0
    processed_segments: int = 0
    failed_segments: int = 0
    progress_percentage: float = 0.0

    # 时间统计
    estimated_time: Optional[float] = None  # 预计总耗时(秒)
    elapsed_time: Optional[float] = None     # 已用时间(秒)
    remaining_time: Optional[float] = None   # 剩余时间(秒)

    # 错误信息
    error_message: Optional[str] = None

    # 跨项目标识
    is_cross_project: bool = False  # 是否为跨项目导出
    output_base_dir: Optional[str] = None  # 完整输出路径（含时间戳子目录）

    def __post_init__(self):
        """初始化后处理"""
        self.total_segments = len(self.segments)
        if isinstance(self.status, str):
            self.status = TaskStatus(self.status)

    def update_progress(self):
        """更新进度"""
        if self.total_segments > 0:
            self.processed_segments = sum(1 for seg in self.segments if seg.is_processed)
            self.failed_segments = sum(1 for seg in self.segments if seg.error_message)
            # 四舍五入为整数，避免小数点显示
            self.progress_percentage = round((self.processed_segments / self.total_segments) * 100)

    def get_current_segment(self) -> Optional[SegmentInfo]:
        """获取当前正在处理的片段"""
        for seg in self.segments:
            if not seg.is_processed and not seg.error_message:
                return seg
        return None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['status'] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExportTask':
        """从字典创建"""
        # 转换状态
        if 'status' in data and isinstance(data['status'], str):
            data['status'] = TaskStatus(data['status'])

        # 转换配置
        if 'config' in data and data['config'] and isinstance(data['config'], dict):
            data['config'] = ExportConfig.from_dict(data['config'])

        # 转换片段
        if 'segments' in data and data['segments']:
            data['segments'] = [SegmentInfo.from_dict(seg) if isinstance(seg, dict) else seg
                               for seg in data['segments']]

        return cls(**data)


class ExportQueue:
    """导出队列管理器"""

    def __init__(self):
        self.tasks: List[ExportTask] = []

    def add_task(self, task: ExportTask) -> str:
        """添加任务到队列

        Args:
            task: 导出任务

        Returns:
            任务ID
        """
        self.tasks.append(task)
        return task.task_id

    def remove_task(self, task_id: str) -> bool:
        """删除任务

        Args:
            task_id: 任务ID

        Returns:
            是否删除成功
        """
        for i, task in enumerate(self.tasks):
            if task.task_id == task_id:
                self.tasks.pop(i)
                return True
        return False

    def get_task(self, task_id: str) -> Optional[ExportTask]:
        """获取任务

        Args:
            task_id: 任务ID

        Returns:
            任务对象，不存在则返回None
        """
        for task in self.tasks:
            if task.task_id == task_id:
                return task
        return None

    def get_tasks_by_status(self, status: TaskStatus) -> List[ExportTask]:
        """获取指定状态的任务列表

        Args:
            status: 任务状态

        Returns:
            任务列表
        """
        return [task for task in self.tasks if task.status == status]

    def move_task(self, task_id: str, new_index: int) -> bool:
        """移动任务位置

        Args:
            task_id: 任务ID
            new_index: 新位置索引

        Returns:
            是否移动成功
        """
        for i, task in enumerate(self.tasks):
            if task.task_id == task_id:
                task_obj = self.tasks.pop(i)
                self.tasks.insert(new_index, task_obj)
                return True
        return False

    def clear_completed(self):
        """清空已完成的任务"""
        self.tasks = [task for task in self.tasks if task.status != TaskStatus.COMPLETED]

    def clear_failed(self):
        """清空失败的任务"""
        self.tasks = [task for task in self.tasks if task.status != TaskStatus.FAILED]

    def get_statistics(self) -> Dict[str, int]:
        """获取队列统计信息

        Returns:
            统计信息字典
        """
        stats = {
            'total': len(self.tasks),
            'pending': 0,
            'processing': 0,
            'completed': 0,
            'failed': 0,
            'paused': 0,
            'total_segments': 0,
            'processed_segments': 0,
            'remaining_segments': 0
        }

        for task in self.tasks:
            stats[task.status.value] += 1
            stats['total_segments'] += task.total_segments

            # 实时统计所有任务中已处理的片段数（而不是等任务完成后才累加）
            actual_processed = sum(1 for seg in task.segments if seg.is_processed)
            stats['processed_segments'] += actual_processed
            stats['remaining_segments'] += (task.total_segments - actual_processed)

        return stats

    def save_to_file(self, filepath: str) -> bool:
        """保存队列到文件

        Args:
            filepath: 文件路径

        Returns:
            是否保存成功
        """
        try:
            data = {
                'version': '1.0',
                'save_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'tasks': [task.to_dict() for task in self.tasks]
            }

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            return True
        except Exception as e:
            print(f"保存队列失败: {e}")
            return False

    def load_from_file(self, filepath: str, replace: bool = True) -> bool:
        """从文件加载队列

        Args:
            filepath: 文件路径
            replace: 是否替换当前队列（True）或追加（False）

        Returns:
            是否加载成功
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            tasks = [ExportTask.from_dict(task_data) for task_data in data.get('tasks', [])]

            # 处理处理中的任务，重置为等待状态
            for task in tasks:
                if task.status == TaskStatus.PROCESSING:
                    task.status = TaskStatus.PENDING
                    task.start_time = None
                    task.processed_segments = 0
                    task.progress_percentage = 0.0
                    # 重置片段状态
                    for seg in task.segments:
                        if not seg.error_message:  # 保留失败的片段状态
                            seg.is_processed = False
                            seg.output_path = None

            if replace:
                self.tasks = tasks
            else:
                self.tasks.extend(tasks)

            return True
        except Exception as e:
            print(f"加载队列失败: {e}")
            return False
