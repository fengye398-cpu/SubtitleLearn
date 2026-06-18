from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
import json

@dataclass
class Project:
    """项目数据模型"""
    id: Optional[int] = None
    name: str = ""
    video_path: str = ""
    subtitle_path: str = ""
    cache_dir: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'video_path': self.video_path,
            'subtitle_path': self.subtitle_path,
            'cache_dir': self.cache_dir,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

@dataclass
class SubtitleSegment:
    """字幕片段数据模型"""
    id: Optional[int] = None
    project_id: int = 0
    index_num: int = 0
    start_time: float = 0.0
    end_time: float = 0.0
    text: str = ""
    text_primary: str = ""  # 原文（第一行）
    text_secondary: Optional[str] = None  # 译文（第二行）
    video_file: Optional[str] = None
    audio_file: Optional[str] = None
    subtitle_file: Optional[str] = None
    created_at: Optional[datetime] = None
    
    @property
    def duration(self) -> float:
        """片段时长（秒）"""
        return self.end_time - self.start_time
    
    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'index_num': self.index_num,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'text': self.text,
            'video_file': self.video_file,
            'audio_file': self.audio_file,
            'subtitle_file': self.subtitle_file,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

@dataclass
class ExportRecord:
    """导出记录数据模型"""
    id: Optional[int] = None
    project_id: int = 0
    segment_ids: List[int] = None
    export_type: str = ""  # video, audio, subtitle, merged
    output_path: str = ""
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.segment_ids is None:
            self.segment_ids = []

    @property
    def segment_ids_json(self) -> str:
        """将segment_ids转换为JSON字符串"""
        return json.dumps(self.segment_ids)

    @segment_ids_json.setter
    def segment_ids_json(self, value: str):
        """从JSON字符串设置segment_ids"""
        try:
            self.segment_ids = json.loads(value) if value else []
        except json.JSONDecodeError:
            self.segment_ids = []

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'segment_ids': self.segment_ids,
            'export_type': self.export_type,
            'output_path': self.output_path,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

@dataclass
class ImportResult:
    """导入结果统计"""
    success: bool = False
    project_id: Optional[int] = None
    project_name: str = ""
    total_segments: int = 0
    video_success: int = 0
    video_failed: int = 0
    audio_success: int = 0
    audio_failed: int = 0
    subtitle_success: int = 0
    subtitle_failed: int = 0
    duration: float = 0.0  # 耗时（秒）
    error_message: Optional[str] = None
    skipped: bool = False  # 是否跳过（已存在）

    def to_dict(self):
        return {
            'success': self.success,
            'project_id': self.project_id,
            'project_name': self.project_name,
            'total_segments': self.total_segments,
            'video_success': self.video_success,
            'video_failed': self.video_failed,
            'audio_success': self.audio_success,
            'audio_failed': self.audio_failed,
            'subtitle_success': self.subtitle_success,
            'subtitle_failed': self.subtitle_failed,
            'duration': self.duration,
            'error_message': self.error_message,
            'skipped': self.skipped
        }
