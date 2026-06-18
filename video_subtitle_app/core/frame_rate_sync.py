#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
方案7：视频帧率同步技术模块
获取视频帧率并实现帧率对齐的精确时长计算
"""

import subprocess
import os
import json
from typing import Optional, Dict, Tuple, List
from decimal import Decimal
from .high_precision_time import HighPrecisionTime
import logging

logger = logging.getLogger(__name__)


class FrameRateAnalyzer:
    """帧率分析器 - 方案7核心组件"""
    
    def __init__(self):
        self.fps_cache = {}  # 帧率缓存
        self.frame_count_cache = {}  # 帧数缓存
    
    def get_video_fps(self, video_path: str) -> float:
        """获取视频帧率
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            视频帧率，失败返回0.0
        """
        if not os.path.exists(video_path):
            return 0.0
        
        # 检查缓存
        cache_key = f"{video_path}_{os.path.getmtime(video_path)}"
        if cache_key in self.fps_cache:
            return self.fps_cache[cache_key]
        
        try:
            # 使用ffprobe获取帧率
            cmd = [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=r_frame_rate,avg_frame_rate",
                "-of", "json", video_path
            ]
            
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                streams = data.get('streams', [])
                
                if streams:
                    stream = streams[0]
                    
                    # 优先使用r_frame_rate
                    fps_str = stream.get('r_frame_rate', '')
                    if not fps_str or fps_str == '0/0':
                        fps_str = stream.get('avg_frame_rate', '')
                    
                    if fps_str and fps_str != '0/0':
                        if '/' in fps_str:
                            num, den = fps_str.split('/')
                            fps = float(num) / float(den)
                        else:
                            fps = float(fps_str)
                        
                        # 缓存结果
                        self.fps_cache[cache_key] = fps
                        return fps
            
        except Exception as e:
            logger.warning(f"获取视频帧率失败 {video_path}: {e}")
        
        return 0.0
    
    def get_video_frame_count(self, video_path: str) -> int:
        """获取视频总帧数
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            视频总帧数，失败返回0
        """
        if not os.path.exists(video_path):
            return 0
        
        # 检查缓存
        cache_key = f"{video_path}_{os.path.getmtime(video_path)}"
        if cache_key in self.frame_count_cache:
            return self.frame_count_cache[cache_key]
        
        try:
            # 使用ffprobe获取帧数
            cmd = [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=nb_frames",
                "-of", "csv=p=0", video_path
            ]
            
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            if result.returncode == 0:
                frame_count = int(result.stdout.strip())
                self.frame_count_cache[cache_key] = frame_count
                return frame_count
            
        except Exception as e:
            logger.warning(f"获取视频帧数失败 {video_path}: {e}")
        
        return 0
    
    def get_video_info(self, video_path: str) -> Dict:
        """获取视频完整信息
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            包含fps、frame_count、duration等信息的字典
        """
        fps = self.get_video_fps(video_path)
        frame_count = self.get_video_frame_count(video_path)
        
        # 计算基于帧率的精确时长
        duration = 0.0
        if fps > 0 and frame_count > 0:
            duration = frame_count / fps
        
        return {
            'fps': fps,
            'frame_count': frame_count,
            'duration': duration,
            'has_video': fps > 0
        }


class FrameAlignedDurationCalculator:
    """帧对齐时长计算器 - 方案7核心组件"""
    
    def __init__(self):
        self.analyzer = FrameRateAnalyzer()
    
    def get_frame_aligned_duration(self, video_path: str, duration: float) -> HighPrecisionTime:
        """获取帧率对齐的精确时长
        
        Args:
            video_path: 视频文件路径
            duration: 原始时长（秒）
            
        Returns:
            帧率对齐的高精度时长
        """
        fps = self.analyzer.get_video_fps(video_path)
        
        if fps > 0:
            # 计算最接近的帧数
            frame_count = round(duration * fps)
            # 返回帧率对齐的精确时长
            aligned_duration = Decimal(str(frame_count)) / Decimal(str(fps))
            return HighPrecisionTime(aligned_duration)
        else:
            # 没有视频或无法获取帧率，返回原始时长
            return HighPrecisionTime(duration)
    
    def get_segment_frame_aligned_duration(self, video_path: str, 
                                         start_time: float, end_time: float) -> HighPrecisionTime:
        """获取片段的帧对齐时长
        
        Args:
            video_path: 视频文件路径
            start_time: 开始时间（秒）
            end_time: 结束时间（秒）
            
        Returns:
            帧对齐的片段时长
        """
        fps = self.analyzer.get_video_fps(video_path)
        
        if fps > 0:
            # 将开始和结束时间对齐到帧边界
            start_frame = round(start_time * fps)
            end_frame = round(end_time * fps)
            
            # 计算帧对齐的时长
            frame_duration = end_frame - start_frame
            aligned_duration = Decimal(str(frame_duration)) / Decimal(str(fps))
            return HighPrecisionTime(aligned_duration)
        else:
            # 没有视频或无法获取帧率，返回原始时长
            return HighPrecisionTime(end_time - start_time)
    
    def align_timestamp_to_frame(self, video_path: str, timestamp: float) -> HighPrecisionTime:
        """将时间戳对齐到最近的帧
        
        Args:
            video_path: 视频文件路径
            timestamp: 时间戳（秒）
            
        Returns:
            帧对齐的时间戳
        """
        fps = self.analyzer.get_video_fps(video_path)
        
        if fps > 0:
            frame_number = round(timestamp * fps)
            aligned_timestamp = Decimal(str(frame_number)) / Decimal(str(fps))
            return HighPrecisionTime(aligned_timestamp)
        else:
            return HighPrecisionTime(timestamp)
    
    def calculate_frame_perfect_gaps(self, video_path: str, gap_seconds: float) -> HighPrecisionTime:
        """计算帧完美的间隔时间
        
        Args:
            video_path: 视频文件路径
            gap_seconds: 期望的间隔时间（秒）
            
        Returns:
            帧对齐的间隔时间
        """
        fps = self.analyzer.get_video_fps(video_path)
        
        if fps > 0:
            # 计算最接近的帧数（至少1帧）
            frame_count = max(1, round(gap_seconds * fps))
            aligned_gap = Decimal(str(frame_count)) / Decimal(str(fps))
            return HighPrecisionTime(aligned_gap)
        else:
            return HighPrecisionTime(gap_seconds)


class MultiVideoFrameRateSync:
    """多视频帧率同步器 - 方案7核心组件"""
    
    def __init__(self):
        self.calculator = FrameAlignedDurationCalculator()
        self.analyzer = FrameRateAnalyzer()
    
    def analyze_cross_project_frame_rates(self, video_paths: List[str]) -> Dict:
        """分析跨项目视频的帧率情况
        
        Args:
            video_paths: 视频文件路径列表
            
        Returns:
            帧率分析结果
        """
        frame_rates = []
        video_info = {}
        
        for video_path in video_paths:
            if os.path.exists(video_path):
                info = self.analyzer.get_video_info(video_path)
                video_info[video_path] = info
                if info['fps'] > 0:
                    frame_rates.append(info['fps'])
        
        # 分析帧率一致性
        unique_fps = list(set(frame_rates))
        is_consistent = len(unique_fps) <= 1
        
        # 选择主要帧率（最常见的）
        primary_fps = 0.0
        if frame_rates:
            fps_count = {}
            for fps in frame_rates:
                fps_count[fps] = fps_count.get(fps, 0) + 1
            primary_fps = max(fps_count.keys(), key=lambda x: fps_count[x])
        
        return {
            'video_info': video_info,
            'frame_rates': frame_rates,
            'unique_fps': unique_fps,
            'is_consistent': is_consistent,
            'primary_fps': primary_fps,
            'total_videos': len(video_paths),
            'videos_with_fps': len(frame_rates)
        }
    
    def get_unified_frame_aligned_durations(self, segments_info: List[Dict]) -> List[HighPrecisionTime]:
        """获取统一帧对齐的时长列表
        
        Args:
            segments_info: 片段信息列表，每个包含video_path, start_time, end_time
            
        Returns:
            帧对齐的时长列表
        """
        durations = []
        
        for segment in segments_info:
            video_path = segment.get('video_path', '')
            start_time = segment.get('start_time', 0)
            end_time = segment.get('end_time', 0)
            
            if os.path.exists(video_path):
                duration = self.calculator.get_segment_frame_aligned_duration(
                    video_path, start_time, end_time
                )
            else:
                duration = HighPrecisionTime(end_time - start_time)
            
            durations.append(duration)
        
        return durations
    
    def calculate_cross_project_timeline(self, segments_info: List[Dict], 
                                       gap_seconds: float = 0.2) -> List[Dict]:
        """计算跨项目的精确时间轴
        
        Args:
            segments_info: 片段信息列表
            gap_seconds: 间隔时间（秒）
            
        Returns:
            包含精确时间轴的片段信息列表
        """
        result = []
        current_time = HighPrecisionTime(0)
        
        for i, segment in enumerate(segments_info):
            video_path = segment.get('video_path', '')
            
            # 获取帧对齐的时长
            if os.path.exists(video_path):
                duration = self.calculator.get_segment_frame_aligned_duration(
                    video_path, 
                    segment.get('start_time', 0),
                    segment.get('end_time', 0)
                )
                # 计算帧对齐的间隔
                gap = self.calculator.calculate_frame_perfect_gaps(video_path, gap_seconds)
            else:
                duration = HighPrecisionTime(segment.get('end_time', 0) - segment.get('start_time', 0))
                gap = HighPrecisionTime(gap_seconds)
            
            # 计算片段在时间轴上的位置
            segment_start = current_time
            segment_end = current_time.add(duration)
            
            result.append({
                **segment,
                'timeline_start': segment_start,
                'timeline_end': segment_end,
                'frame_aligned_duration': duration,
                'frame_aligned_gap': gap,
                'fps': self.analyzer.get_video_fps(video_path) if os.path.exists(video_path) else 0
            })
            
            # 更新当前时间（加上时长和间隔）
            if i < len(segments_info) - 1:  # 不是最后一个片段
                current_time = segment_end.add(gap)
            else:
                current_time = segment_end
        
        return result
    
    def generate_frame_sync_report(self, segments_info: List[Dict]) -> Dict:
        """生成帧同步报告
        
        Args:
            segments_info: 片段信息列表
            
        Returns:
            帧同步分析报告
        """
        video_paths = [seg.get('video_path', '') for seg in segments_info if seg.get('video_path')]
        video_paths = [p for p in video_paths if os.path.exists(p)]
        
        if not video_paths:
            return {'error': '没有有效的视频文件'}
        
        # 分析帧率情况
        fps_analysis = self.analyze_cross_project_frame_rates(video_paths)
        
        # 计算时间轴
        timeline = self.calculate_cross_project_timeline(segments_info)
        
        # 统计信息
        total_duration = HighPrecisionTime(0)
        frame_aligned_count = 0
        
        for item in timeline:
            total_duration = total_duration.add(item['frame_aligned_duration'])
            if item['fps'] > 0:
                frame_aligned_count += 1
        
        return {
            'fps_analysis': fps_analysis,
            'timeline': timeline,
            'statistics': {
                'total_segments': len(segments_info),
                'frame_aligned_segments': frame_aligned_count,
                'frame_alignment_rate': frame_aligned_count / max(len(segments_info), 1),
                'total_duration': total_duration.to_seconds(),
                'precision_level': 'frame-perfect' if fps_analysis['is_consistent'] else 'mixed-fps'
            }
        }
