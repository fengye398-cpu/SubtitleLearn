#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本适配器 - 将选中片段转换为外部脚本需要的输入格式
"""

import os
import tempfile
import pysrt
from pathlib import Path
from typing import List, Optional, Tuple

from database.models import SubtitleSegment
from database.manager import db_manager
from utils.file_utils import FileUtils


class ScriptAdapter:
    """脚本适配器 - 连接应用数据和外部脚本"""
    
    def __init__(self):
        self.temp_files = []  # 跟踪临时文件，用于清理
    
    def prepare_segments_for_script(self, segments: List[SubtitleSegment]) -> Optional[Tuple[str, str, str]]:
        """
        将选中的片段准备为外部脚本需要的格式

        Args:
            segments: 选中的字幕片段列表

        Returns:
            Tuple[video_file, srt_file, temp_dir] 或 None
            - video_file: 原视频文件路径（如果跨项目则返回None）
            - srt_file: 临时字幕文件路径（只包含选中片段）
            - temp_dir: 临时目录路径
        """
        if not segments:
            return None

        try:
            # 检查是否跨项目
            project_ids = set(segment.project_id for segment in segments)
            if len(project_ids) > 1:
                print(f"检测到跨项目片段导出，涉及 {len(project_ids)} 个项目")
                # 跨项目情况，返回特殊标记
                return self._prepare_cross_project_segments(segments)

            # 单项目情况，使用原有逻辑
            project = db_manager.get_project(segments[0].project_id)
            if not project or not project.video_path:
                return None

            if not os.path.exists(project.video_path):
                return None

            # 按索引排序片段
            segments.sort(key=lambda x: x.index_num)

            # 创建临时目录
            temp_dir = tempfile.mkdtemp(prefix="video_export_")
            self.temp_files.append(temp_dir)

            # 创建临时字幕文件，只包含选中的片段
            temp_srt_file = self._create_filtered_subtitle_file(segments, project.subtitle_path, temp_dir)
            if not temp_srt_file:
                return None

            return project.video_path, temp_srt_file, temp_dir

        except Exception as e:
            print(f"准备片段数据失败: {e}")
            return None

    def _prepare_cross_project_segments(self, segments: List[SubtitleSegment]) -> Optional[Tuple[str, str, str]]:
        """
        准备跨项目片段数据

        Returns:
            Tuple["CROSS_PROJECT", segments_info_file, temp_dir]
        """
        try:
            # 创建临时目录
            temp_dir = tempfile.mkdtemp(prefix="cross_project_export_")
            self.temp_files.append(temp_dir)

            # 按索引排序片段
            segments.sort(key=lambda x: x.index_num)

            # 创建片段信息文件
            segments_info_file = os.path.join(temp_dir, "segments_info.json")
            segments_data = []

            for i, segment in enumerate(segments, 1):
                # 获取片段对应的项目信息
                project = db_manager.get_project(segment.project_id)
                if not project:
                    continue

                segment_info = {
                    "index": i,
                    "project_id": segment.project_id,
                    "project_name": project.name,
                    "video_path": project.video_path,
                    "subtitle_path": project.subtitle_path,
                    "start_time": segment.start_time,
                    "end_time": segment.end_time,
                    "text": segment.text,
                    "index_num": segment.index_num
                }
                segments_data.append(segment_info)

            # 保存片段信息
            import json
            with open(segments_info_file, 'w', encoding='utf-8') as f:
                json.dump(segments_data, f, ensure_ascii=False, indent=2)

            print(f"跨项目片段信息已保存到: {segments_info_file}")
            return "CROSS_PROJECT", segments_info_file, temp_dir

        except Exception as e:
            print(f"准备跨项目片段数据失败: {e}")
            return None
    
    def _create_filtered_subtitle_file(self, segments: List[SubtitleSegment],
                                     original_srt_path: Optional[str], temp_dir: str) -> Optional[str]:
        """创建过滤后的字幕文件，只包含选中的片段"""
        try:
            print(f"[SEARCH] [DEBUG] ScriptAdapter: 开始创建过滤字幕文件")
            print(f"[SEARCH] [DEBUG] ScriptAdapter: 输入片段数量: {len(segments)}")
            print(f"[SEARCH] [DEBUG] ScriptAdapter: 原始字幕文件: {original_srt_path}")

            # 创建新的字幕文件
            new_subs = pysrt.SubRipFile()

            if original_srt_path and os.path.exists(original_srt_path):
                # 从原始字幕文件中提取对应片段
                original_subs = pysrt.open(original_srt_path, encoding="utf-8-sig")
                print(f"[SEARCH] [DEBUG] ScriptAdapter: 原始字幕文件包含 {len(original_subs)} 个条目")

                for i, segment in enumerate(segments, 1):
                    print(f"[SEARCH] [DEBUG] ScriptAdapter: 处理片段 {i}: {segment.start_time:.1f}-{segment.end_time:.1f}s")

                    # 查找匹配的字幕条目
                    matching_sub = None
                    matched_count = 0
                    for sub in original_subs:
                        sub_start = sub.start.ordinal / 1000
                        sub_end = sub.end.ordinal / 1000

                        # 允许一定的时间误差（0.1秒）
                        if (abs(sub_start - segment.start_time) < 0.1 and
                            abs(sub_end - segment.end_time) < 0.1):
                            if matching_sub is None:
                                matching_sub = sub
                            matched_count += 1

                    if matched_count > 1:
                        print(f"[WARN] [WARNING] ScriptAdapter: 片段 {i} 匹配到 {matched_count} 个字幕条目！")
                    elif matched_count == 1:
                        print(f"[OK] [INFO] ScriptAdapter: 片段 {i} 成功匹配到字幕条目")
                    else:
                        print(f"[ERROR] [ERROR] ScriptAdapter: 片段 {i} 没有匹配到字幕条目")
                    
                    if matching_sub:
                        # 使用原始字幕的时间和文本
                        new_sub = pysrt.SubRipItem(
                            index=i,
                            start=matching_sub.start,
                            end=matching_sub.end,
                            text=matching_sub.text
                        )
                    else:
                        # 如果找不到匹配的字幕，使用片段数据创建
                        start_time = pysrt.SubRipTime(seconds=segment.start_time)
                        end_time = pysrt.SubRipTime(seconds=segment.end_time)
                        
                        new_sub = pysrt.SubRipItem(
                            index=i,
                            start=start_time,
                            end=end_time,
                            text=segment.text
                        )
                    
                    new_subs.append(new_sub)
            else:
                # 从片段数据直接创建字幕文件
                for i, segment in enumerate(segments, 1):
                    start_time = pysrt.SubRipTime(seconds=segment.start_time)
                    end_time = pysrt.SubRipTime(seconds=segment.end_time)
                    
                    new_sub = pysrt.SubRipItem(
                        index=i,
                        start=start_time,
                        end=end_time,
                        text=segment.text
                    )
                    new_subs.append(new_sub)
            
            # 保存临时字幕文件
            temp_srt_file = os.path.join(temp_dir, "selected_segments.srt")
            new_subs.save(temp_srt_file, encoding='utf-8')

            print(f"[SEARCH] [DEBUG] ScriptAdapter: 过滤后字幕文件包含 {len(new_subs)} 个条目")
            print(f"[SEARCH] [DEBUG] ScriptAdapter: 临时字幕文件保存到: {temp_srt_file}")

            return temp_srt_file
            
        except Exception as e:
            print(f"创建过滤字幕文件失败: {e}")
            return None
    
    def get_project_info(self, segments: List[SubtitleSegment]) -> Optional[dict]:
        """获取项目信息"""
        if not segments:
            return None
        
        try:
            project = db_manager.get_project(segments[0].project_id)
            if not project:
                return None
            
            return {
                'project_name': project.name,
                'video_path': project.video_path,
                'subtitle_path': project.subtitle_path,
                'total_segments': len(segments),
                'selected_segments': [
                    {
                        'index': seg.index_num,
                        'start_time': seg.start_time,
                        'end_time': seg.end_time,
                        'duration': seg.duration,
                        'text': seg.text[:50] + '...' if len(seg.text) > 50 else seg.text
                    }
                    for seg in segments
                ]
            }
            
        except Exception as e:
            print(f"获取项目信息失败: {e}")
            return None
    
    def create_input_folder_structure(self, segments: List[SubtitleSegment]) -> Optional[str]:
        """
        创建外部脚本需要的输入文件夹结构
        
        Returns:
            输入文件夹路径，包含视频文件和对应的字幕文件
        """
        try:
            # 准备数据
            result = self.prepare_segments_for_script(segments)
            if not result:
                return None
            
            video_file, temp_srt_file, temp_dir = result
            
            # 创建输入文件夹
            input_folder = os.path.join(temp_dir, "input")
            os.makedirs(input_folder, exist_ok=True)
            
            # 获取视频文件名（不含扩展名）
            video_name = Path(video_file).stem
            video_ext = Path(video_file).suffix
            
            # 复制视频文件到输入文件夹
            input_video_file = os.path.join(input_folder, f"{video_name}{video_ext}")
            FileUtils.copy_file(video_file, input_video_file)
            
            # 复制字幕文件到输入文件夹，使用相同的基础名称
            input_srt_file = os.path.join(input_folder, f"{video_name}.srt")
            FileUtils.copy_file(temp_srt_file, input_srt_file)
            
            return input_folder
            
        except Exception as e:
            print(f"创建输入文件夹结构失败: {e}")
            return None
    
    def cleanup_temp_files(self):
        """清理临时文件"""
        for temp_path in self.temp_files:
            try:
                if os.path.exists(temp_path):
                    if os.path.isdir(temp_path):
                        import shutil
                        shutil.rmtree(temp_path)
                    else:
                        os.unlink(temp_path)
            except Exception as e:
                print(f"清理临时文件失败 {temp_path}: {e}")
        
        self.temp_files.clear()
    
    def __del__(self):
        """析构函数，自动清理临时文件"""
        self.cleanup_temp_files()


# 全局适配器实例
script_adapter = ScriptAdapter()
