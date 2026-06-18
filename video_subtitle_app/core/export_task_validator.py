#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导出任务检测工具 - 检测跨项目、音视频混合、文件丢失等问题
"""

import os
from typing import List, Dict, Optional, Tuple
from database.models import SubtitleSegment
from utils.file_utils import FileUtils


class ExportTaskValidator:
    """导出任务校验器 - 检测添加队列前的各种问题"""

    @staticmethod
    def validate_segments(segments: List[SubtitleSegment], fast_copy_mode: bool = True) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """校验片段列表，检测所有可能的问题

        Args:
            segments: 片段列表
            fast_copy_mode: 是否标准模式（影响跨项目检测）

        Returns:
            (是否通过校验, 错误信息, 错误详情字典)

        错误详情字典格式:
        {
            "type": "cross_project" | "mixed_media" | "missing_files",
            "details": {...具体错误信息...}
        }
        """
        if not segments:
            return False, "没有选择任何片段", None

        # 1. 检测跨项目（根据导出模式）
        is_valid, error_msg, error_details = ExportTaskValidator.check_cross_project(segments, fast_copy_mode)
        if not is_valid:
            return False, error_msg, error_details

        # 2. 检测音视频混合
        is_valid, error_msg, error_details = ExportTaskValidator.check_mixed_media(segments)
        if not is_valid:
            return False, error_msg, error_details

        # 3. 检测文件丢失
        is_valid, error_msg, error_details = ExportTaskValidator.check_missing_files(segments)
        if not is_valid:
            return False, error_msg, error_details

        # 所有检测通过
        return True, None, None

    @staticmethod
    def check_cross_project(segments: List[SubtitleSegment], fast_copy_mode: bool = True) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """检测是否跨项目

        Args:
            segments: 片段列表
            fast_copy_mode: 是否标准模式（快速模式不允许跨项目，重新编码允许）

        Returns:
            (是否通过, 错误信息, 错误详情)
        """
        # 统计项目
        project_stats = {}
        for seg in segments:
            project_name = getattr(seg, 'project_name', None) or "未知项目"
            if project_name not in project_stats:
                project_stats[project_name] = 0
            project_stats[project_name] += 1

        # 如果有多个项目
        if len(project_stats) > 1:
            # 只有在标准模式下才阻止跨项目
            if fast_copy_mode:
                # 构建错误消息
                project_list = "\n".join([f"• {name}: {count} 个片段" for name, count in project_stats.items()])
                error_msg = f"检测到选择的片段来自不同项目：\n\n{project_list}\n\n标准模式不支持跨项目导出。\n\n建议：\n1. 切换到'重新编码'（支持跨项目）\n2. 或分别为每个项目创建导出任务"

                error_details = {
                    "type": "cross_project",
                    "details": {
                        "projects": project_stats,
                        "fast_copy_mode": fast_copy_mode
                    }
                }

                return False, error_msg, error_details
            # 重新编码允许跨项目
            else:
                return True, None, None

        # 通过检测
        return True, None, None

    @staticmethod
    def check_mixed_media(segments: List[SubtitleSegment]) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """检测是否音视频混合

        Args:
            segments: 片段列表

        Returns:
            (是否通过, 错误信息, 错误详情)
        """
        # 统计音频和视频片段数
        video_count = 0
        audio_count = 0

        # 导入数据库管理器
        from database.manager import db_manager

        for seg in segments:
            # 从项目获取视频路径
            project = db_manager.get_project(seg.project_id) if hasattr(seg, 'project_id') and seg.project_id else None
            if not project:
                continue

            video_path = project.video_path
            if video_path and os.path.exists(video_path):
                if FileUtils.is_audio_file(video_path):
                    audio_count += 1
                else:
                    video_count += 1

        # 如果同时存在音频和视频
        if video_count > 0 and audio_count > 0:
            error_msg = f"检测到同时选择了音频和视频片段：\n\n• 视频片段: {video_count} 个\n• 音频片段: {audio_count} 个\n\n无法混合导出音频和视频片段。\n请分别为音频和视频创建导出任务。"

            error_details = {
                "type": "mixed_media",
                "details": {
                    "video_count": video_count,
                    "audio_count": audio_count
                }
            }

            return False, error_msg, error_details

        # 通过检测
        return True, None, None

    @staticmethod
    def check_missing_files(segments: List[SubtitleSegment]) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """检测文件是否丢失

        Args:
            segments: 片段列表

        Returns:
            (是否通过, 错误信息, 错误详情)
        """
        # 统计丢失的文件
        missing_files = {}

        # 导入数据库管理器
        from database.manager import db_manager

        for seg in segments:
            # 从项目获取视频路径
            project = db_manager.get_project(seg.project_id) if hasattr(seg, 'project_id') and seg.project_id else None
            if not project:
                continue

            video_path = project.video_path
            project_name = project.name

            if video_path and not os.path.exists(video_path):
                if project_name not in missing_files:
                    missing_files[project_name] = []
                if video_path not in missing_files[project_name]:
                    missing_files[project_name].append(video_path)

        # 如果有丢失的文件
        if missing_files:
            # 构建错误消息
            file_list = []
            for project_name, paths in missing_files.items():
                file_list.append(f"• {project_name}: {len(paths)} 个文件不存在")
                for path in paths[:3]:  # 最多显示3个路径
                    file_list.append(f"  路径: {path}")
                if len(paths) > 3:
                    file_list.append(f"  ... 还有 {len(paths) - 3} 个文件")

            error_msg = f"检测到以下项目的源文件无法访问：\n\n" + "\n".join(file_list) + "\n\n请检查文件是否被移动或删除。"

            error_details = {
                "type": "missing_files",
                "details": {
                    "missing_files": missing_files
                }
            }

            return False, error_msg, error_details

        # 通过检测
        return True, None, None


# 便捷函数
def validate_export_segments(segments: List[SubtitleSegment], fast_copy_mode: bool = True) -> Tuple[bool, Optional[str], Optional[Dict]]:
    """校验导出片段

    Args:
        segments: 片段列表
        fast_copy_mode: 是否标准模式

    Returns:
        (是否通过, 错误信息, 错误详情)
    """
    return ExportTaskValidator.validate_segments(segments, fast_copy_mode)
