#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
【终极方案】MPV播放器 - 批量播放字幕精准同步
核心思路：为每个片段预切割独立字幕文件，使用字幕延迟精准控制显示时机
"""

import os
import tempfile
import hashlib
from typing import List, Optional, Dict
from pathlib import Path

from database.models import SubtitleSegment
from database.manager import db_manager


class SubtitleSyncManager:
    """字幕同步管理器 - 终极方案"""

    def __init__(self):
        self.subtitle_cache_dir = Path(tempfile.gettempdir()) / "video_subtitle_cache"
        self.subtitle_cache_dir.mkdir(exist_ok=True)

    def create_batch_subtitle_with_edl_mapping(self,
                                                 all_segments: List[SubtitleSegment],
                                                 segment_subtitles: Dict[str, str],
                                                 repeat_count: int) -> Optional[str]:
        """
        【终极方案】创建批量播放字幕文件 - 使用EDL时间映射

        核心原理：
        1. EDL播放列表让视频按连续时间轴播放（0s开始）
        2. 字幕文件也必须使用相同的连续时间轴
        3. 关键：确保字幕时间与EDL播放时间完全对应

        时间映射示例：
        片段1: 视频10s-15s → EDL播放0s-5s  → 字幕0s-5s
        片段2: 视频30s-35s → EDL播放5s-10s → 字幕5s-10s
        片段3: 视频50s-55s → EDL播放10s-15s → 字幕10s-15s
        """
        try:
            print(f"\n========== 【终极方案】创建批量字幕文件 ==========")
            print(f"片段数: {len(all_segments)}, 重复次数: {repeat_count}")

            batch_content = []
            entry_index = 1

            # 为每轮重复创建字幕
            for repeat_round in range(repeat_count):
                edl_playback_time = 0.0  # EDL播放时间轴（从0开始）

                print(f"\n--- 处理第 {repeat_round + 1}/{repeat_count} 轮 ---")

                for seg_idx, segment in enumerate(all_segments):
                    segment_key = f"{segment.project_id}_{segment.id}"
                    subtitle_file = segment_subtitles.get(segment_key)

                    if not subtitle_file:
                        print(f"  [片段{seg_idx+1}] 无字幕，跳过")
                        segment_duration = segment.end_time - segment.start_time
                        edl_playback_time += segment_duration
                        continue

                    # 读取原始字幕
                    subtitle_entries = self._parse_subtitle_file(subtitle_file)
                    if not subtitle_entries:
                        print(f"  [片段{seg_idx+1}] 字幕解析失败")
                        segment_duration = segment.end_time - segment.start_time
                        edl_playback_time += segment_duration
                        continue

                    # 过滤出片段时间范围内的字幕
                    matching_subs = self._filter_subtitles_in_segment(
                        subtitle_entries, segment.start_time, segment.end_time
                    )

                    print(f"  [片段{seg_idx+1}] {segment.start_time:.2f}s-{segment.end_time:.2f}s")
                    print(f"    → EDL播放: {edl_playback_time:.2f}s开始")
                    print(f"    → 匹配字幕: {len(matching_subs)}条")

                    # 转换字幕时间到EDL播放时间轴
                    for sub_entry in matching_subs:
                        # 步骤1：裁剪到片段范围内
                        clipped_start = max(sub_entry['start_time'], segment.start_time)
                        clipped_end = min(sub_entry['end_time'], segment.end_time)

                        # 步骤2：转换为相对于片段开始的时间
                        relative_start = clipped_start - segment.start_time
                        relative_end = clipped_end - segment.start_time

                        # 步骤3：映射到EDL播放时间轴
                        edl_sub_start = edl_playback_time + relative_start
                        edl_sub_end = edl_playback_time + relative_end

                        # 添加到批量字幕文件
                        batch_content.append(str(entry_index))
                        batch_content.append(
                            f"{self._format_srt_time(edl_sub_start)} --> "
                            f"{self._format_srt_time(edl_sub_end)}"
                        )
                        batch_content.append(sub_entry['text'])
                        batch_content.append("")  # 空行分隔

                        if entry_index <= 3 or entry_index % 10 == 0:
                            print(f"      字幕{entry_index}: "
                                  f"{self._format_srt_time(edl_sub_start)} → "
                                  f"{self._format_srt_time(edl_sub_end)}")

                        entry_index += 1

                    # 更新EDL播放时间
                    segment_duration = segment.end_time - segment.start_time
                    edl_playback_time += segment_duration

            if not batch_content:
                print("\n[错误] 没有生成任何字幕内容")
                return None

            # 写入临时文件
            batch_file = tempfile.NamedTemporaryFile(
                mode='w', suffix='.srt', delete=False, encoding='utf-8'
            )
            batch_file.write('\n'.join(batch_content))
            batch_file.close()

            print(f"\n========== 字幕文件创建成功 ==========")
            print(f"文件路径: {batch_file.name}")
            print(f"字幕条目数: {entry_index - 1}")
            print(f"总播放时长: {edl_playback_time:.2f}s")

            # 验证生成的文件
            self._verify_subtitle_file(batch_file.name)

            return batch_file.name

        except Exception as e:
            print(f"\n[致命错误] 创建批量字幕失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _filter_subtitles_in_segment(self, subtitle_entries: List[Dict],
                                     seg_start: float, seg_end: float) -> List[Dict]:
        """过滤出片段时间范围内的字幕（更精准的算法）"""
        matching = []
        for entry in subtitle_entries:
            # 字幕与片段有任何时间重叠即包含
            if (entry['start_time'] < seg_end and entry['end_time'] > seg_start):
                matching.append(entry)
        return matching

    def _parse_subtitle_file(self, subtitle_file: str) -> List[Dict]:
        """解析字幕文件"""
        try:
            with open(subtitle_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # 移除BOM
            if content.startswith('\ufeff'):
                content = content[1:]

            entries = []
            blocks = content.strip().split('\n\n')

            for block in blocks:
                lines = block.strip().split('\n')
                if len(lines) >= 3:
                    try:
                        time_line = lines[1]
                        if ' --> ' in time_line:
                            start_str, end_str = time_line.split(' --> ')
                            start_time = self._parse_srt_time(start_str.strip())
                            end_time = self._parse_srt_time(end_str.strip())
                            text = '\n'.join(lines[2:])

                            entries.append({
                                'start_time': start_time,
                                'end_time': end_time,
                                'text': text
                            })
                    except Exception as e:
                        print(f"  [警告] 解析字幕条目失败: {e}")
                        continue

            return entries
        except Exception as e:
            print(f"  [错误] 读取字幕文件失败: {e}")
            return []

    def _parse_srt_time(self, time_str: str) -> float:
        """解析SRT时间格式 (HH:MM:SS,mmm) 为秒数"""
        try:
            time_str = time_str.strip().replace(',', '.')
            parts = time_str.split(':')
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = float(parts[2])
            return hours * 3600 + minutes * 60 + seconds
        except Exception:
            return 0.0

    def _format_srt_time(self, seconds: float) -> str:
        """将秒数格式化为SRT时间格式 (HH:MM:SS,mmm)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}".replace('.', ',')

    def _verify_subtitle_file(self, subtitle_file: str):
        """验证生成的字幕文件"""
        try:
            with open(subtitle_file, 'r', encoding='utf-8') as f:
                content = f.read()

            lines = content.split('\n')[:30]
            print(f"\n--- 字幕文件预览（前30行）---")
            for line in lines:
                if line.strip():
                    print(f"  {line}")
        except Exception as e:
            print(f"  [警告] 无法验证字幕文件: {e}")


# 导出给主模块使用
__all__ = ['SubtitleSyncManager']
