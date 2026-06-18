#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
方案7：关键帧精确对齐技术模块
获取关键帧列表并实现精确的关键帧对齐技术
"""

import subprocess
import os
import json
import bisect
from typing import List, Optional, Dict, Tuple
from decimal import Decimal
from .high_precision_time import HighPrecisionTime
import logging

logger = logging.getLogger(__name__)


class KeyframeExtractor:
    """关键帧提取器 - 方案7核心组件"""
    
    def __init__(self):
        self.keyframe_cache = {}  # 关键帧缓存
    
    def get_keyframes_list(self, video_path: str) -> List[float]:
        """获取视频的所有关键帧时间点
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            关键帧时间点列表（秒）
        """
        if not os.path.exists(video_path):
            return []
        
        # 检查缓存
        cache_key = f"{video_path}_{os.path.getmtime(video_path)}"
        if cache_key in self.keyframe_cache:
            return self.keyframe_cache[cache_key]
        
        try:
            # 使用ffprobe获取关键帧信息
            cmd = [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "packet=pts_time,flags",
                "-of", "csv=p=0", video_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            keyframes = []
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line:
                        parts = line.split(',')
                        if len(parts) >= 2:
                            try:
                                pts_time = float(parts[0])
                                flags = parts[1]
                                # K表示关键帧
                                if 'K' in flags:
                                    keyframes.append(pts_time)
                            except (ValueError, IndexError):
                                continue
            
            # 排序并缓存
            keyframes = sorted(keyframes)
            self.keyframe_cache[cache_key] = keyframes
            
            logger.info(f"提取关键帧: {video_path} -> {len(keyframes)} 个关键帧")
            return keyframes
            
        except Exception as e:
            logger.warning(f"提取关键帧失败 {video_path}: {e}")
            return []
    
    def get_keyframes_in_range(self, video_path: str, start_time: float, end_time: float) -> List[float]:
        """获取指定时间范围内的关键帧
        
        Args:
            video_path: 视频文件路径
            start_time: 开始时间（秒）
            end_time: 结束时间（秒）
            
        Returns:
            范围内的关键帧时间点列表
        """
        all_keyframes = self.get_keyframes_list(video_path)
        return [kf for kf in all_keyframes if start_time <= kf <= end_time]
    
    def find_nearest_keyframe(self, video_path: str, target_time: float) -> Optional[float]:
        """找到离目标时间最近的关键帧
        
        Args:
            video_path: 视频文件路径
            target_time: 目标时间（秒）
            
        Returns:
            最近的关键帧时间，没有找到返回None
        """
        keyframes = self.get_keyframes_list(video_path)
        if not keyframes:
            return None
        
        # 使用二分查找
        pos = bisect.bisect_left(keyframes, target_time)
        
        if pos == 0:
            return keyframes[0]
        elif pos == len(keyframes):
            return keyframes[-1]
        else:
            before = keyframes[pos - 1]
            after = keyframes[pos]
            
            # 返回距离更近的关键帧
            if abs(before - target_time) <= abs(after - target_time):
                return before
            else:
                return after
    
    def find_keyframe_boundaries(self, video_path: str, start_time: float, end_time: float) -> Tuple[Optional[float], Optional[float]]:
        """找到时间范围的关键帧边界
        
        Args:
            video_path: 视频文件路径
            start_time: 开始时间（秒）
            end_time: 结束时间（秒）
            
        Returns:
            (开始关键帧, 结束关键帧) 元组
        """
        start_keyframe = self.find_nearest_keyframe(video_path, start_time)
        end_keyframe = self.find_nearest_keyframe(video_path, end_time)
        
        return start_keyframe, end_keyframe


class KeyframeAlignedDurationCalculator:
    """关键帧对齐时长计算器 - 方案7核心组件"""
    
    def __init__(self):
        self.extractor = KeyframeExtractor()
    
    def get_keyframe_aligned_duration(self, video_path: str, start_time: float, end_time: float) -> HighPrecisionTime:
        """获取关键帧对齐的精确时长
        
        Args:
            video_path: 视频文件路径
            start_time: 开始时间（秒）
            end_time: 结束时间（秒）
            
        Returns:
            关键帧对齐的精确时长
        """
        if not os.path.exists(video_path):
            return HighPrecisionTime(end_time - start_time)
        
        try:
            # 找到关键帧边界
            start_keyframe, end_keyframe = self.extractor.find_keyframe_boundaries(
                video_path, start_time, end_time
            )
            
            if start_keyframe is not None and end_keyframe is not None:
                # 使用关键帧对齐的时长
                aligned_duration = end_keyframe - start_keyframe
                return HighPrecisionTime(aligned_duration)
            else:
                # 没有找到关键帧，使用原始时长
                return HighPrecisionTime(end_time - start_time)
                
        except Exception as e:
            logger.warning(f"关键帧对齐计算失败 {video_path}: {e}")
            return HighPrecisionTime(end_time - start_time)
    
    def get_keyframe_perfect_timestamps(self, video_path: str, timestamps: List[float]) -> List[HighPrecisionTime]:
        """获取关键帧完美对齐的时间戳列表
        
        Args:
            video_path: 视频文件路径
            timestamps: 原始时间戳列表
            
        Returns:
            关键帧对齐的高精度时间戳列表
        """
        if not os.path.exists(video_path):
            return [HighPrecisionTime(ts) for ts in timestamps]
        
        aligned_timestamps = []
        
        for timestamp in timestamps:
            keyframe = self.extractor.find_nearest_keyframe(video_path, timestamp)
            if keyframe is not None:
                aligned_timestamps.append(HighPrecisionTime(keyframe))
            else:
                aligned_timestamps.append(HighPrecisionTime(timestamp))
        
        return aligned_timestamps
    
    def calculate_keyframe_gap(self, video_path: str, end_time: float, next_start_time: float, 
                             min_gap: float = 0.2) -> HighPrecisionTime:
        """计算关键帧对齐的间隔时间
        
        Args:
            video_path: 视频文件路径
            end_time: 前一个片段的结束时间
            next_start_time: 下一个片段的开始时间
            min_gap: 最小间隔时间（秒）
            
        Returns:
            关键帧对齐的间隔时间
        """
        if not os.path.exists(video_path):
            return HighPrecisionTime(min_gap)
        
        try:
            # 找到结束时间和开始时间的最近关键帧
            end_keyframe = self.extractor.find_nearest_keyframe(video_path, end_time)
            start_keyframe = self.extractor.find_nearest_keyframe(video_path, next_start_time)
            
            if end_keyframe is not None and start_keyframe is not None:
                natural_gap = start_keyframe - end_keyframe
                
                # 确保间隔不小于最小值
                if natural_gap >= min_gap:
                    return HighPrecisionTime(natural_gap)
                else:
                    # 寻找下一个合适的关键帧
                    keyframes = self.extractor.get_keyframes_list(video_path)
                    target_time = end_keyframe + min_gap
                    
                    suitable_keyframe = None
                    for kf in keyframes:
                        if kf >= target_time:
                            suitable_keyframe = kf
                            break
                    
                    if suitable_keyframe is not None:
                        return HighPrecisionTime(suitable_keyframe - end_keyframe)
            
            return HighPrecisionTime(min_gap)
            
        except Exception as e:
            logger.warning(f"关键帧间隔计算失败 {video_path}: {e}")
            return HighPrecisionTime(min_gap)


class KeyframePrecisionAnalyzer:
    """关键帧精度分析器 - 方案7核心组件"""
    
    def __init__(self):
        self.extractor = KeyframeExtractor()
        self.calculator = KeyframeAlignedDurationCalculator()
    
    def analyze_keyframe_density(self, video_path: str) -> Dict:
        """分析视频的关键帧密度
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            关键帧密度分析结果
        """
        if not os.path.exists(video_path):
            return {'error': '视频文件不存在'}
        
        try:
            keyframes = self.extractor.get_keyframes_list(video_path)
            
            if not keyframes:
                return {'error': '无法获取关键帧信息'}
            
            # 计算基本统计信息
            total_duration = keyframes[-1] - keyframes[0] if len(keyframes) > 1 else 0
            keyframe_count = len(keyframes)
            
            # 计算间隔统计
            intervals = []
            for i in range(1, len(keyframes)):
                intervals.append(keyframes[i] - keyframes[i-1])
            
            avg_interval = sum(intervals) / len(intervals) if intervals else 0
            min_interval = min(intervals) if intervals else 0
            max_interval = max(intervals) if intervals else 0
            
            # 计算密度等级
            if avg_interval <= 1.0:
                density_level = 'high'
            elif avg_interval <= 3.0:
                density_level = 'medium'
            else:
                density_level = 'low'
            
            return {
                'total_duration': total_duration,
                'keyframe_count': keyframe_count,
                'density': keyframe_count / max(total_duration, 1),  # 关键帧/秒
                'avg_interval': avg_interval,
                'min_interval': min_interval,
                'max_interval': max_interval,
                'density_level': density_level,
                'precision_suitable': density_level in ['high', 'medium']
            }
            
        except Exception as e:
            logger.error(f"关键帧密度分析失败 {video_path}: {e}")
            return {'error': str(e)}
    
    def compare_alignment_methods(self, video_path: str, segments: List[Dict]) -> Dict:
        """比较不同对齐方法的效果
        
        Args:
            video_path: 视频文件路径
            segments: 片段列表，每个包含start_time和end_time
            
        Returns:
            对齐方法比较结果
        """
        if not segments:
            return {'error': '没有片段数据'}
        
        results = {
            'original': [],
            'keyframe_aligned': [],
            'precision_improvement': []
        }
        
        for segment in segments:
            start_time = segment.get('start_time', 0)
            end_time = segment.get('end_time', 0)
            
            # 原始时长
            original_duration = end_time - start_time
            results['original'].append(original_duration)
            
            # 关键帧对齐时长
            aligned_duration = self.calculator.get_keyframe_aligned_duration(
                video_path, start_time, end_time
            )
            results['keyframe_aligned'].append(aligned_duration.to_seconds())
            
            # 计算精度改进
            improvement = abs(aligned_duration.to_seconds() - original_duration)
            results['precision_improvement'].append(improvement)
        
        # 统计信息
        avg_improvement = sum(results['precision_improvement']) / len(results['precision_improvement'])
        max_improvement = max(results['precision_improvement'])
        
        return {
            'segments_analyzed': len(segments),
            'results': results,
            'statistics': {
                'avg_precision_improvement': avg_improvement,
                'max_precision_improvement': max_improvement,
                'total_segments': len(segments),
                'alignment_effective': avg_improvement > 0.001  # 1毫秒阈值
            }
        }
    
    def generate_keyframe_report(self, video_paths: List[str]) -> Dict:
        """生成关键帧分析报告
        
        Args:
            video_paths: 视频文件路径列表
            
        Returns:
            关键帧分析报告
        """
        report = {
            'total_videos': len(video_paths),
            'analyzed_videos': 0,
            'videos_with_keyframes': 0,
            'density_analysis': {},
            'overall_suitability': 'unknown'
        }
        
        density_levels = {'high': 0, 'medium': 0, 'low': 0}
        
        for video_path in video_paths:
            if os.path.exists(video_path):
                report['analyzed_videos'] += 1
                
                density_info = self.analyze_keyframe_density(video_path)
                if 'error' not in density_info:
                    report['videos_with_keyframes'] += 1
                    report['density_analysis'][video_path] = density_info
                    
                    level = density_info.get('density_level', 'low')
                    density_levels[level] += 1
        
        # 确定整体适用性
        total_analyzed = report['videos_with_keyframes']
        if total_analyzed > 0:
            high_medium_ratio = (density_levels['high'] + density_levels['medium']) / total_analyzed
            if high_medium_ratio >= 0.8:
                report['overall_suitability'] = 'excellent'
            elif high_medium_ratio >= 0.5:
                report['overall_suitability'] = 'good'
            else:
                report['overall_suitability'] = 'limited'
        
        report['density_distribution'] = density_levels
        
        return report
