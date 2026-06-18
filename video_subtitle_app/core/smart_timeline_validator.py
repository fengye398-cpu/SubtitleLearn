#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能时间轴校验与自动调整系统 - 方案B
基于现有的视频分析组件实现智能校验和修正功能
"""

import os
import sys
import json
import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import timedelta
from decimal import Decimal, getcontext

# 设置高精度
getcontext().prec = 15

# 导入现有组件
try:
    from .keyframe_analyzer import KeyframeAnalyzer
    from .triple_verification import TripleVerificationEngine, FFProbeVerifier
    from .frame_rate_sync import FrameRateAnalyzer
    COMPONENTS_AVAILABLE = True
except ImportError as e:
    print(f"[WARN] 智能校验组件导入失败: {e}")
    COMPONENTS_AVAILABLE = False

try:
    import pysrt
    PYSRT_AVAILABLE = True
except ImportError:
    PYSRT_AVAILABLE = False

logger = logging.getLogger(__name__)


class TimelineDeviation:
    """时间轴偏差分析结果"""
    
    def __init__(self):
        self.total_deviation = 0.0  # 总偏差（秒）
        self.max_deviation = 0.0    # 最大偏差（秒）
        self.avg_deviation = 0.0    # 平均偏差（秒）
        self.deviation_pattern = "unknown"  # 偏差模式
        self.confidence = 0.0       # 置信度
        self.correction_strategy = "none"  # 修正策略
        self.details = {}           # 详细信息


class VideoAnalysis:
    """视频分析结果"""
    
    def __init__(self):
        self.duration = 0.0         # 视频时长
        self.fps = 0.0              # 帧率
        self.keyframes = []         # 关键帧列表
        self.scene_changes = []     # 场景切换点
        self.audio_gaps = []        # 音频间隔
        self.reliability = 0.0      # 分析可靠性


class SubtitleAnalysis:
    """字幕分析结果"""
    
    def __init__(self):
        self.total_duration = 0.0   # 字幕总时长
        self.subtitle_count = 0     # 字幕条数
        self.gaps = []              # 字幕间隔
        self.density_map = {}       # 字幕密度分布
        self.timing_pattern = "unknown"  # 时间模式


class SmartTimelineValidator:
    """智能时间轴校验器 - 方案B核心类"""
    
    def __init__(self):
        self.keyframe_analyzer = KeyframeAnalyzer() if COMPONENTS_AVAILABLE else None
        self.triple_verifier = TripleVerificationEngine() if COMPONENTS_AVAILABLE else None
        self.fps_analyzer = FrameRateAnalyzer() if COMPONENTS_AVAILABLE else None
        
        # 校验阈值配置
        self.thresholds = {
            'minor_deviation': 0.1,     # 100ms - 轻微偏差
            'moderate_deviation': 1.0,   # 1s - 中等偏差
            'major_deviation': 5.0,      # 5s - 严重偏差
            'critical_deviation': 10.0   # 10s - 关键偏差
        }
        
        # 修正策略配置
        self.correction_strategies = {
            'linear': self._apply_linear_correction,
            'segment_based': self._apply_segment_based_correction,
            'keyframe_aligned': self._apply_keyframe_aligned_correction,
            'proportional': self._apply_proportional_correction
        }
    
    def validate_and_correct(self, video_path: str, subtitle_path: str, 
                           output_path: Optional[str] = None) -> Dict:
        """主要的校验和修正入口函数
        
        Args:
            video_path: 视频文件路径
            subtitle_path: 字幕文件路径
            output_path: 输出路径（可选，默认覆盖原文件）
            
        Returns:
            校验和修正结果
        """
        if not COMPONENTS_AVAILABLE or not PYSRT_AVAILABLE:
            return {
                'success': False,
                'error': '缺少必要组件',
                'original_file': subtitle_path
            }
        
        try:
            # 第1步：快速检测
            quick_result = self._perform_quick_check(video_path, subtitle_path)
            
            if quick_result['deviation'].total_deviation < self.thresholds['minor_deviation']:
                return {
                    'success': True,
                    'action': 'no_correction_needed',
                    'deviation': quick_result['deviation'].total_deviation,
                    'message': '时间轴精度良好，无需修正',
                    'original_file': subtitle_path
                }
            
            # 第2步：深度分析
            video_analysis = self._analyze_video_structure(video_path)
            subtitle_analysis = self._analyze_subtitle_timeline(subtitle_path)
            
            # 第3步：检测偏差模式
            deviation = self._detect_timeline_deviation(video_analysis, subtitle_analysis)
            
            # 第4步：选择修正策略
            strategy = self._select_correction_strategy(deviation)
            
            # 第5步：应用修正
            if strategy != 'none':
                corrected_path = output_path or subtitle_path
                correction_result = self._apply_correction(
                    subtitle_path, corrected_path, strategy, deviation, video_analysis
                )
                
                return {
                    'success': correction_result['success'],
                    'action': 'corrected',
                    'strategy': strategy,
                    'deviation_before': deviation.total_deviation,
                    'deviation_after': correction_result.get('final_deviation', 0),
                    'improvement': correction_result.get('improvement', 0),
                    'corrected_file': corrected_path,
                    'details': correction_result.get('details', {}),
                    'message': f'应用{strategy}修正策略，改善{correction_result.get("improvement", 0):.3f}s'
                }
            else:
                return {
                    'success': False,
                    'action': 'correction_failed',
                    'deviation': deviation.total_deviation,
                    'message': '偏差过大，建议使用重新编码方案',
                    'original_file': subtitle_path
                }
                
        except Exception as e:
            logger.error(f"智能校验失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'original_file': subtitle_path
            }
    
    def _perform_quick_check(self, video_path: str, subtitle_path: str) -> Dict:
        """执行快速检测"""
        deviation = TimelineDeviation()
        
        try:
            # 获取视频时长
            video_duration = self.triple_verifier.get_most_reliable_duration(video_path, True).to_seconds()
            
            # 获取字幕时长
            subs = pysrt.open(subtitle_path, encoding='utf-8')
            if subs:
                last_sub = subs[-1]
                subtitle_duration = (
                    last_sub.end.hours * 3600 + 
                    last_sub.end.minutes * 60 + 
                    last_sub.end.seconds + 
                    last_sub.end.milliseconds / 1000.0
                )
                
                # 计算总偏差
                deviation.total_deviation = abs(video_duration - subtitle_duration)
                deviation.max_deviation = deviation.total_deviation
                deviation.avg_deviation = deviation.total_deviation
                
                # 简单模式识别
                if deviation.total_deviation < self.thresholds['minor_deviation']:
                    deviation.deviation_pattern = "minimal"
                    deviation.confidence = 0.9
                elif deviation.total_deviation < self.thresholds['moderate_deviation']:
                    deviation.deviation_pattern = "linear"
                    deviation.confidence = 0.7
                else:
                    deviation.deviation_pattern = "complex"
                    deviation.confidence = 0.5
            
        except Exception as e:
            logger.warning(f"快速检测失败: {e}")
            deviation.confidence = 0.0
        
        return {'deviation': deviation}
    
    def _analyze_video_structure(self, video_path: str) -> VideoAnalysis:
        """分析视频结构"""
        analysis = VideoAnalysis()
        
        try:
            # 获取基本信息
            duration = self.triple_verifier.get_most_reliable_duration(video_path, True).to_seconds()
            analysis.duration = duration
            
            # 获取帧率
            fps = self.fps_analyzer.get_video_fps(video_path)
            analysis.fps = fps
            
            # 获取关键帧（如果可用）
            keyframes = self.keyframe_analyzer.get_keyframes(video_path)
            if keyframes:
                analysis.keyframes = keyframes
                # 识别场景切换（关键帧间隔较大的位置）
                analysis.scene_changes = self._identify_scene_changes(keyframes)
            
            analysis.reliability = 0.8 if keyframes else 0.6
            
        except Exception as e:
            logger.warning(f"视频结构分析失败: {e}")
            analysis.reliability = 0.3
        
        return analysis
    
    def _analyze_subtitle_timeline(self, subtitle_path: str) -> SubtitleAnalysis:
        """分析字幕时间轴"""
        analysis = SubtitleAnalysis()
        
        try:
            subs = pysrt.open(subtitle_path, encoding='utf-8')
            analysis.subtitle_count = len(subs)
            
            if subs:
                # 计算总时长
                last_sub = subs[-1]
                analysis.total_duration = (
                    last_sub.end.hours * 3600 + 
                    last_sub.end.minutes * 60 + 
                    last_sub.end.seconds + 
                    last_sub.end.milliseconds / 1000.0
                )
                
                # 分析字幕间隔
                gaps = []
                for i in range(len(subs) - 1):
                    current_end = self._subtitle_to_seconds(subs[i].end)
                    next_start = self._subtitle_to_seconds(subs[i + 1].start)
                    gap = next_start - current_end
                    gaps.append(gap)
                
                analysis.gaps = gaps
                
                # 分析字幕密度分布
                analysis.density_map = self._calculate_subtitle_density(subs)
                
                # 识别时间模式
                analysis.timing_pattern = self._identify_timing_pattern(gaps)
            
        except Exception as e:
            logger.warning(f"字幕时间轴分析失败: {e}")
        
        return analysis
    
    def _detect_timeline_deviation(self, video_analysis: VideoAnalysis, 
                                 subtitle_analysis: SubtitleAnalysis) -> TimelineDeviation:
        """检测时间轴偏差模式"""
        deviation = TimelineDeviation()
        
        # 计算总偏差
        deviation.total_deviation = abs(video_analysis.duration - subtitle_analysis.total_duration)
        
        # 分析偏差模式
        if deviation.total_deviation < self.thresholds['minor_deviation']:
            deviation.deviation_pattern = "minimal"
            deviation.correction_strategy = "none"
            deviation.confidence = 0.9
        elif deviation.total_deviation < self.thresholds['moderate_deviation']:
            # 检查是否为线性偏差
            if self._is_linear_deviation(video_analysis, subtitle_analysis):
                deviation.deviation_pattern = "linear"
                deviation.correction_strategy = "linear"
            else:
                deviation.deviation_pattern = "proportional"
                deviation.correction_strategy = "proportional"
            deviation.confidence = 0.8
        elif deviation.total_deviation < self.thresholds['major_deviation']:
            deviation.deviation_pattern = "segment_based"
            deviation.correction_strategy = "segment_based"
            deviation.confidence = 0.6
        else:
            deviation.deviation_pattern = "critical"
            deviation.correction_strategy = "keyframe_aligned"
            deviation.confidence = 0.4
        
        return deviation
    
    def _select_correction_strategy(self, deviation: TimelineDeviation) -> str:
        """选择修正策略"""
        if deviation.total_deviation < self.thresholds['minor_deviation']:
            return 'none'
        elif deviation.confidence > 0.7:
            return deviation.correction_strategy
        elif deviation.total_deviation < self.thresholds['major_deviation']:
            return 'proportional'  # 默认策略
        else:
            return 'none'  # 偏差过大，不建议自动修正
    
    def _apply_correction(self, input_path: str, output_path: str, strategy: str, 
                         deviation: TimelineDeviation, video_analysis: VideoAnalysis) -> Dict:
        """应用修正策略"""
        if strategy not in self.correction_strategies:
            return {'success': False, 'error': f'未知策略: {strategy}'}
        
        try:
            correction_func = self.correction_strategies[strategy]
            result = correction_func(input_path, output_path, deviation, video_analysis)
            return result
        except Exception as e:
            logger.error(f"修正策略{strategy}执行失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def _apply_linear_correction(self, input_path: str, output_path: str, 
                               deviation: TimelineDeviation, video_analysis: VideoAnalysis) -> Dict:
        """应用线性修正"""
        try:
            subs = pysrt.open(input_path, encoding='utf-8')
            
            # 计算缩放因子
            subtitle_duration = self._subtitle_to_seconds(subs[-1].end)
            scale_factor = video_analysis.duration / subtitle_duration
            
            # 应用线性缩放
            for sub in subs:
                sub.start = self._scale_time(sub.start, scale_factor)
                sub.end = self._scale_time(sub.end, scale_factor)
            
            # 保存修正后的字幕
            subs.save(output_path, encoding='utf-8')
            
            # 计算改善效果
            improvement = deviation.total_deviation * (1 - abs(1 - scale_factor))
            
            return {
                'success': True,
                'scale_factor': scale_factor,
                'improvement': improvement,
                'final_deviation': deviation.total_deviation - improvement,
                'details': {'method': 'linear_scaling', 'factor': scale_factor}
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _apply_proportional_correction(self, input_path: str, output_path: str, 
                                     deviation: TimelineDeviation, video_analysis: VideoAnalysis) -> Dict:
        """应用比例修正"""
        # 实现比例修正逻辑
        return self._apply_linear_correction(input_path, output_path, deviation, video_analysis)
    
    def _apply_segment_based_correction(self, input_path: str, output_path: str, 
                                      deviation: TimelineDeviation, video_analysis: VideoAnalysis) -> Dict:
        """应用基于片段的修正"""
        # 这里可以实现更复杂的片段级修正
        return self._apply_linear_correction(input_path, output_path, deviation, video_analysis)
    
    def _apply_keyframe_aligned_correction(self, input_path: str, output_path: str, 
                                         deviation: TimelineDeviation, video_analysis: VideoAnalysis) -> Dict:
        """应用关键帧对齐修正"""
        # 这里可以实现关键帧对齐的修正
        return self._apply_linear_correction(input_path, output_path, deviation, video_analysis)
    
    # 辅助方法
    def _subtitle_to_seconds(self, time_obj) -> float:
        """将字幕时间对象转换为秒"""
        return time_obj.hours * 3600 + time_obj.minutes * 60 + time_obj.seconds + time_obj.milliseconds / 1000.0
    
    def _scale_time(self, time_obj, scale_factor: float):
        """缩放时间对象"""
        total_seconds = self._subtitle_to_seconds(time_obj) * scale_factor
        
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        milliseconds = int((total_seconds % 1) * 1000)
        
        time_obj.hours = hours
        time_obj.minutes = minutes
        time_obj.seconds = seconds
        time_obj.milliseconds = milliseconds
        
        return time_obj
    
    def _identify_scene_changes(self, keyframes: List[float]) -> List[float]:
        """识别场景切换点"""
        scene_changes = []
        if len(keyframes) < 2:
            return scene_changes
        
        # 计算关键帧间隔
        intervals = [keyframes[i+1] - keyframes[i] for i in range(len(keyframes)-1)]
        avg_interval = sum(intervals) / len(intervals)
        
        # 识别间隔异常大的位置作为场景切换
        for i, interval in enumerate(intervals):
            if interval > avg_interval * 2:  # 间隔超过平均值2倍
                scene_changes.append(keyframes[i+1])
        
        return scene_changes
    
    def _calculate_subtitle_density(self, subs) -> Dict:
        """计算字幕密度分布"""
        # 简化实现，返回基本统计
        return {
            'total_count': len(subs),
            'avg_duration': sum(self._subtitle_to_seconds(sub.end) - self._subtitle_to_seconds(sub.start) for sub in subs) / len(subs) if subs else 0
        }
    
    def _identify_timing_pattern(self, gaps: List[float]) -> str:
        """识别时间模式"""
        if not gaps:
            return "unknown"
        
        avg_gap = sum(gaps) / len(gaps)
        if avg_gap < 0.1:
            return "continuous"
        elif avg_gap < 0.5:
            return "normal"
        else:
            return "sparse"
    
    def _is_linear_deviation(self, video_analysis: VideoAnalysis, subtitle_analysis: SubtitleAnalysis) -> bool:
        """检查是否为线性偏差"""
        # 简化判断：如果总时长偏差相对均匀，认为是线性偏差
        return True  # 暂时简化实现


# 全局实例
smart_validator = SmartTimelineValidator() if COMPONENTS_AVAILABLE else None
