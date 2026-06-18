#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
方案7：高精度时间处理模块
实现亚毫秒级时间戳精度，避免浮点数累积误差
"""

from decimal import Decimal, getcontext, ROUND_HALF_UP
from datetime import timedelta
from typing import Union, List
import math

# 设置高精度上下文
getcontext().prec = 15  # 15位精度，足够处理亚毫秒级时间


class HighPrecisionTime:
    """高精度时间类 - 方案7核心组件"""
    
    def __init__(self, seconds: Union[float, str, Decimal]):
        """初始化高精度时间
        
        Args:
            seconds: 时间（秒），支持float、str、Decimal
        """
        if isinstance(seconds, Decimal):
            self.decimal_seconds = seconds
        else:
            # 转换为字符串再转Decimal，避免浮点精度问题
            self.decimal_seconds = Decimal(str(seconds))
    
    @classmethod
    def from_milliseconds(cls, milliseconds: Union[int, float]) -> 'HighPrecisionTime':
        """从毫秒创建高精度时间"""
        return cls(Decimal(str(milliseconds)) / 1000)
    
    @classmethod
    def from_microseconds(cls, microseconds: Union[int, float]) -> 'HighPrecisionTime':
        """从微秒创建高精度时间"""
        return cls(Decimal(str(microseconds)) / 1000000)
    
    def to_seconds(self) -> float:
        """转换为秒（浮点数）"""
        return float(self.decimal_seconds)
    
    def to_milliseconds(self) -> int:
        """转换为毫秒（整数）"""
        return int((self.decimal_seconds * 1000).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    
    def to_microseconds(self) -> int:
        """转换为微秒（整数）"""
        return int((self.decimal_seconds * 1000000).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    
    def to_timedelta(self) -> timedelta:
        """转换为timedelta对象"""
        total_microseconds = self.to_microseconds()
        return timedelta(microseconds=total_microseconds)
    
    def add(self, other: Union['HighPrecisionTime', float, Decimal]) -> 'HighPrecisionTime':
        """高精度加法"""
        if isinstance(other, HighPrecisionTime):
            return HighPrecisionTime(self.decimal_seconds + other.decimal_seconds)
        else:
            return HighPrecisionTime(self.decimal_seconds + Decimal(str(other)))
    
    def subtract(self, other: Union['HighPrecisionTime', float, Decimal]) -> 'HighPrecisionTime':
        """高精度减法"""
        if isinstance(other, HighPrecisionTime):
            return HighPrecisionTime(self.decimal_seconds - other.decimal_seconds)
        else:
            return HighPrecisionTime(self.decimal_seconds - Decimal(str(other)))
    
    def multiply(self, factor: Union[float, Decimal]) -> 'HighPrecisionTime':
        """高精度乘法"""
        return HighPrecisionTime(self.decimal_seconds * Decimal(str(factor)))
    
    def divide(self, divisor: Union[float, Decimal]) -> 'HighPrecisionTime':
        """高精度除法"""
        return HighPrecisionTime(self.decimal_seconds / Decimal(str(divisor)))
    
    def round_to_frame(self, fps: float) -> 'HighPrecisionTime':
        """舍入到最接近的帧时间"""
        if fps <= 0:
            return self
        
        frame_duration = Decimal('1') / Decimal(str(fps))
        frame_number = (self.decimal_seconds / frame_duration).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        return HighPrecisionTime(frame_number * frame_duration)
    
    def round_to_millisecond(self) -> 'HighPrecisionTime':
        """舍入到毫秒"""
        milliseconds = (self.decimal_seconds * 1000).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        return HighPrecisionTime(milliseconds / 1000)
    
    def format_srt(self) -> str:
        """格式化为SRT时间格式 HH:MM:SS,mmm"""
        total_seconds = self.to_seconds()
        if total_seconds < 0:
            return "00:00:00,000"
        
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        milliseconds = self.to_milliseconds() % 1000
        
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
    
    def format_precise(self, precision: int = 6) -> str:
        """格式化为高精度字符串"""
        return f"{float(self.decimal_seconds):.{precision}f}"
    
    def __str__(self) -> str:
        return self.format_precise()
    
    def __repr__(self) -> str:
        return f"HighPrecisionTime({self.decimal_seconds})"
    
    def __eq__(self, other) -> bool:
        if isinstance(other, HighPrecisionTime):
            return self.decimal_seconds == other.decimal_seconds
        return False
    
    def __lt__(self, other) -> bool:
        if isinstance(other, HighPrecisionTime):
            return self.decimal_seconds < other.decimal_seconds
        return False
    
    def __le__(self, other) -> bool:
        if isinstance(other, HighPrecisionTime):
            return self.decimal_seconds <= other.decimal_seconds
        return False
    
    def __gt__(self, other) -> bool:
        if isinstance(other, HighPrecisionTime):
            return self.decimal_seconds > other.decimal_seconds
        return False
    
    def __ge__(self, other) -> bool:
        if isinstance(other, HighPrecisionTime):
            return self.decimal_seconds >= other.decimal_seconds
        return False


class AccumulatedErrorCompensator:
    """累积误差补偿器 - 方案7核心组件"""
    
    def __init__(self, error_threshold: float = 0.001):
        """初始化误差补偿器
        
        Args:
            error_threshold: 误差阈值（秒），超过此值将进行补偿
        """
        self.accumulated_error = HighPrecisionTime(0)
        self.error_threshold = HighPrecisionTime(error_threshold)
        self.compensation_count = 0
        self.total_segments = 0
    
    def add_segment_with_compensation(self, current_time: HighPrecisionTime, 
                                    segment_duration: HighPrecisionTime) -> HighPrecisionTime:
        """添加片段时进行误差补偿
        
        Args:
            current_time: 当前时间
            segment_duration: 片段时长
            
        Returns:
            补偿后的新时间
        """
        self.total_segments += 1
        
        # 计算理论时间
        theoretical_time = current_time.add(segment_duration)
        
        # 应用累积误差补偿
        compensated_time = theoretical_time.subtract(self.accumulated_error)
        
        # 计算实际误差
        actual_error = compensated_time.subtract(theoretical_time)
        self.accumulated_error = self.accumulated_error.add(actual_error)
        
        # 如果累积误差超过阈值，进行重置
        if abs(self.accumulated_error.to_seconds()) > self.error_threshold.to_seconds():
            compensated_time = compensated_time.subtract(self.accumulated_error)
            self.accumulated_error = HighPrecisionTime(0)
            self.compensation_count += 1
        
        return compensated_time
    
    def get_statistics(self) -> dict:
        """获取补偿统计信息"""
        return {
            'total_segments': self.total_segments,
            'compensation_count': self.compensation_count,
            'current_accumulated_error': self.accumulated_error.to_seconds(),
            'error_threshold': self.error_threshold.to_seconds(),
            'compensation_rate': self.compensation_count / max(self.total_segments, 1)
        }
    
    def reset(self):
        """重置补偿器"""
        self.accumulated_error = HighPrecisionTime(0)
        self.compensation_count = 0
        self.total_segments = 0


class SmartRoundingStrategy:
    """智能舍入策略 - 方案7核心组件"""
    
    @staticmethod
    def round_to_frame_boundary(time: HighPrecisionTime, fps: float) -> HighPrecisionTime:
        """舍入到帧边界"""
        if fps <= 0:
            return time.round_to_millisecond()
        
        return time.round_to_frame(fps)
    
    @staticmethod
    def round_to_safe_boundary(time: HighPrecisionTime, fps: float = 25.0, 
                             min_precision: str = 'millisecond') -> HighPrecisionTime:
        """舍入到安全边界
        
        Args:
            time: 输入时间
            fps: 视频帧率
            min_precision: 最小精度 ('millisecond', 'frame')
        """
        if min_precision == 'frame' and fps > 0:
            return time.round_to_frame(fps)
        else:
            return time.round_to_millisecond()
    
    @staticmethod
    def batch_round_timestamps(timestamps: List[HighPrecisionTime], 
                             fps: float = 25.0) -> List[HighPrecisionTime]:
        """批量舍入时间戳"""
        return [SmartRoundingStrategy.round_to_frame_boundary(ts, fps) for ts in timestamps]


class PrecisionValidator:
    """精度验证器 - 方案7核心组件"""
    
    @staticmethod
    def validate_precision_loss(original: float, processed: HighPrecisionTime, 
                              max_loss: float = 0.0001) -> bool:
        """验证精度损失是否在可接受范围内
        
        Args:
            original: 原始值
            processed: 处理后的高精度时间
            max_loss: 最大可接受精度损失（秒）
        """
        loss = abs(original - processed.to_seconds())
        return loss <= max_loss
    
    @staticmethod
    def calculate_precision_improvement(old_method_error: float, 
                                      new_method_error: float) -> float:
        """计算精度改进倍数"""
        if old_method_error == 0:
            return float('inf') if new_method_error == 0 else 0
        
        return old_method_error / max(new_method_error, 1e-10)
    
    @staticmethod
    def generate_precision_report(test_cases: List[dict]) -> dict:
        """生成精度报告
        
        Args:
            test_cases: 测试用例列表，每个包含 'original', 'processed', 'expected'
        """
        total_cases = len(test_cases)
        passed_cases = 0
        total_error = 0.0
        max_error = 0.0
        
        for case in test_cases:
            original = case['original']
            processed = case['processed'].to_seconds()
            expected = case.get('expected', original)
            
            error = abs(processed - expected)
            total_error += error
            max_error = max(max_error, error)
            
            if PrecisionValidator.validate_precision_loss(expected, case['processed']):
                passed_cases += 1
        
        return {
            'total_cases': total_cases,
            'passed_cases': passed_cases,
            'pass_rate': passed_cases / max(total_cases, 1),
            'average_error': total_error / max(total_cases, 1),
            'max_error': max_error,
            'precision_grade': 'A+' if max_error < 0.0001 else 'A' if max_error < 0.001 else 'B'
        }
