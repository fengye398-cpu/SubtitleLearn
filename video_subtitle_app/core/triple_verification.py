#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
方案7：三重验证机制模块
集成ffprobe、MoviePy、OpenCV三重验证，确保时长获取绝对可靠
"""

import subprocess
import os
import json
from typing import Optional, Dict, List, Tuple
from decimal import Decimal
from .high_precision_time import HighPrecisionTime
import logging

logger = logging.getLogger(__name__)

# MoviePy延迟导入，避免启动时FFmpeg检查失败
MOVIEPY_AVAILABLE = False
VideoFileClip = None
AudioFileClip = None

def _ensure_moviepy():
    """确保MoviePy可用"""
    global MOVIEPY_AVAILABLE, VideoFileClip, AudioFileClip

    if MOVIEPY_AVAILABLE:
        return True

    try:
        # 强制配置MoviePy使用系统FFmpeg
        import os
        os.environ['FFMPEG_BINARY'] = 'ffmpeg'  # 设置环境变量

        import moviepy.config as mp_config
        mp_config.FFMPEG_BINARY = "ffmpeg"  # 使用系统FFmpeg

        from moviepy.editor import VideoFileClip as VFC, AudioFileClip as AFC
        VideoFileClip = VFC
        AudioFileClip = AFC
        MOVIEPY_AVAILABLE = True
        return True
    except Exception as e:
        logger.warning(f"MoviePy不可用，将跳过MoviePy验证: {e}")
        return False

try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    logger.warning("OpenCV不可用，将跳过OpenCV验证")


class FFProbeVerifier:
    """FFProbe验证器 - 方案7核心组件"""
    
    @staticmethod
    def get_duration(media_file: str) -> Optional[float]:
        """使用ffprobe获取媒体文件时长
        
        Args:
            media_file: 媒体文件路径
            
        Returns:
            时长（秒），失败返回None
        """
        if not os.path.exists(media_file):
            return None
        
        try:
            cmd = [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=nw=1:nk=1", media_file
            ]
            
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            if result.returncode == 0:
                duration_str = result.stdout.strip()
                return float(duration_str)
            
        except FileNotFoundError:
            logger.error(f"FFProbe不可用，请检查FFmpeg环境变量配置")
            return None
        except Exception as e:
            logger.warning(f"FFProbe获取时长失败 {media_file}: {e}")

        return None
    
    @staticmethod
    def get_detailed_info(media_file: str) -> Dict:
        """获取详细的媒体信息
        
        Args:
            media_file: 媒体文件路径
            
        Returns:
            详细信息字典
        """
        if not os.path.exists(media_file):
            return {'error': '文件不存在'}
        
        try:
            cmd = [
                "ffprobe", "-v", "error", "-show_entries",
                "format=duration,size,bit_rate:stream=duration,codec_type,width,height,r_frame_rate",
                "-of", "json", media_file
            ]
            
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return data
            
        except FileNotFoundError:
            logger.error(f"FFProbe不可用，请检查FFmpeg环境变量配置")
            return {'error': 'FFProbe不可用，请检查FFmpeg环境变量配置'}
        except Exception as e:
            logger.warning(f"FFProbe获取详细信息失败 {media_file}: {e}")

        return {'error': '获取信息失败'}


class MoviePyVerifier:
    """MoviePy验证器 - 方案7核心组件"""
    
    @staticmethod
    def get_duration(media_file: str, is_video: bool = True) -> Optional[float]:
        """使用MoviePy获取媒体文件时长
        
        Args:
            media_file: 媒体文件路径
            is_video: 是否为视频文件
            
        Returns:
            时长（秒），失败返回None
        """
        if not _ensure_moviepy() or not os.path.exists(media_file):
            return None

        try:
            if is_video:
                with VideoFileClip(media_file) as clip:
                    return clip.duration
            else:
                with AudioFileClip(media_file) as clip:
                    return clip.duration
                    
        except Exception as e:
            logger.warning(f"MoviePy获取时长失败 {media_file}: {e}")
        
        return None
    
    @staticmethod
    def get_video_info(video_file: str) -> Dict:
        """获取视频详细信息
        
        Args:
            video_file: 视频文件路径
            
        Returns:
            视频信息字典
        """
        if not _ensure_moviepy() or not os.path.exists(video_file):
            return {'error': 'MoviePy不可用或文件不存在'}

        try:
            with VideoFileClip(video_file) as clip:
                return {
                    'duration': clip.duration,
                    'fps': clip.fps,
                    'size': clip.size,
                    'width': clip.w,
                    'height': clip.h,
                    'has_audio': clip.audio is not None
                }
                
        except Exception as e:
            logger.warning(f"MoviePy获取视频信息失败 {video_file}: {e}")
            return {'error': str(e)}


class OpenCVVerifier:
    """OpenCV验证器 - 方案7核心组件"""
    
    @staticmethod
    def get_duration(video_file: str) -> Optional[float]:
        """使用OpenCV获取视频时长
        
        Args:
            video_file: 视频文件路径
            
        Returns:
            时长（秒），失败返回None
        """
        if not OPENCV_AVAILABLE or not os.path.exists(video_file):
            return None
        
        try:
            cap = cv2.VideoCapture(video_file)
            
            if not cap.isOpened():
                return None
            
            # 获取帧数和帧率
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            
            cap.release()
            
            if fps > 0:
                return frame_count / fps
            
        except Exception as e:
            logger.warning(f"OpenCV获取时长失败 {video_file}: {e}")
        
        return None
    
    @staticmethod
    def get_video_info(video_file: str) -> Dict:
        """获取视频详细信息
        
        Args:
            video_file: 视频文件路径
            
        Returns:
            视频信息字典
        """
        if not OPENCV_AVAILABLE or not os.path.exists(video_file):
            return {'error': 'OpenCV不可用或文件不存在'}
        
        try:
            cap = cv2.VideoCapture(video_file)
            
            if not cap.isOpened():
                return {'error': '无法打开视频文件'}
            
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            cap.release()
            
            duration = frame_count / fps if fps > 0 else 0
            
            return {
                'duration': duration,
                'fps': fps,
                'frame_count': frame_count,
                'width': width,
                'height': height,
                'size': (width, height)
            }
            
        except Exception as e:
            logger.warning(f"OpenCV获取视频信息失败 {video_file}: {e}")
            return {'error': str(e)}


class TripleVerificationEngine:
    """三重验证引擎 - 方案7核心组件"""
    
    def __init__(self):
        self.ffprobe = FFProbeVerifier()
        self.moviepy = MoviePyVerifier()
        self.opencv = OpenCVVerifier()
    
    def get_most_reliable_duration(self, media_file: str, is_video: bool = True) -> HighPrecisionTime:
        """获取最可靠的媒体时长
        
        Args:
            media_file: 媒体文件路径
            is_video: 是否为视频文件
            
        Returns:
            最可靠的高精度时长
        """
        if not os.path.exists(media_file):
            return HighPrecisionTime(0)
        
        # 收集所有验证结果
        verifications = []
        
        # FFProbe验证
        ffprobe_duration = self.ffprobe.get_duration(media_file)
        if ffprobe_duration is not None:
            verifications.append(('ffprobe', ffprobe_duration))
        
        # MoviePy验证
        if _ensure_moviepy():
            moviepy_duration = self.moviepy.get_duration(media_file, is_video)
            if moviepy_duration is not None:
                verifications.append(('moviepy', moviepy_duration))
        
        # OpenCV验证（仅视频）
        if is_video and OPENCV_AVAILABLE:
            opencv_duration = self.opencv.get_duration(media_file)
            if opencv_duration is not None:
                verifications.append(('opencv', opencv_duration))
        
        # 选择最可靠的结果
        if not verifications:
            logger.warning(f"所有验证方法都失败: {media_file}")
            return HighPrecisionTime(0)
        
        # 如果只有一个结果，直接返回
        if len(verifications) == 1:
            return HighPrecisionTime(verifications[0][1])
        
        # 多个结果时，选择最一致的
        return self._select_most_consistent_duration(verifications)
    
    def _select_most_consistent_duration(self, verifications: List[Tuple[str, float]]) -> HighPrecisionTime:
        """从多个验证结果中选择最一致的时长
        
        Args:
            verifications: 验证结果列表 [(方法名, 时长), ...]
            
        Returns:
            最一致的高精度时长
        """
        if not verifications:
            return HighPrecisionTime(0)
        
        durations = [v[1] for v in verifications]
        
        # 计算平均值
        avg_duration = sum(durations) / len(durations)
        
        # 找到最接近平均值的结果
        best_verification = min(verifications, key=lambda x: abs(x[1] - avg_duration))
        
        # 计算一致性分数
        max_deviation = max(abs(d - avg_duration) for d in durations)
        consistency_score = 1.0 - min(max_deviation / max(avg_duration, 1), 1.0)
        
        logger.info(f"三重验证结果: {verifications}, 选择: {best_verification[0]}={best_verification[1]:.6f}s, 一致性: {consistency_score:.3f}")
        
        return HighPrecisionTime(best_verification[1])
    
    def perform_comprehensive_verification(self, media_file: str, is_video: bool = True) -> Dict:
        """执行全面的三重验证
        
        Args:
            media_file: 媒体文件路径
            is_video: 是否为视频文件
            
        Returns:
            全面的验证报告
        """
        if not os.path.exists(media_file):
            return {'error': '文件不存在'}
        
        report = {
            'file_path': media_file,
            'is_video': is_video,
            'verifications': {},
            'selected_duration': 0.0,
            'consistency_analysis': {},
            'reliability_score': 0.0
        }
        
        # FFProbe验证
        ffprobe_duration = self.ffprobe.get_duration(media_file)
        if ffprobe_duration is not None:
            report['verifications']['ffprobe'] = {
                'duration': ffprobe_duration,
                'available': True,
                'precision': 'high'
            }
        else:
            report['verifications']['ffprobe'] = {
                'available': False,
                'error': 'FFProbe验证失败'
            }
        
        # MoviePy验证
        if _ensure_moviepy():
            moviepy_duration = self.moviepy.get_duration(media_file, is_video)
            if moviepy_duration is not None:
                report['verifications']['moviepy'] = {
                    'duration': moviepy_duration,
                    'available': True,
                    'precision': 'very_high'
                }
            else:
                report['verifications']['moviepy'] = {
                    'available': False,
                    'error': 'MoviePy验证失败'
                }
        else:
            report['verifications']['moviepy'] = {
                'available': False,
                'error': 'MoviePy不可用'
            }
        
        # OpenCV验证（仅视频）
        if is_video:
            if OPENCV_AVAILABLE:
                opencv_duration = self.opencv.get_duration(media_file)
                if opencv_duration is not None:
                    report['verifications']['opencv'] = {
                        'duration': opencv_duration,
                        'available': True,
                        'precision': 'medium'
                    }
                else:
                    report['verifications']['opencv'] = {
                        'available': False,
                        'error': 'OpenCV验证失败'
                    }
            else:
                report['verifications']['opencv'] = {
                    'available': False,
                    'error': 'OpenCV不可用'
                }
        
        # 分析一致性
        available_durations = []
        for method, result in report['verifications'].items():
            if result.get('available', False):
                available_durations.append((method, result['duration']))
        
        if available_durations:
            # 选择最可靠的时长
            selected_duration = self._select_most_consistent_duration(available_durations)
            report['selected_duration'] = selected_duration.to_seconds()
            
            # 计算一致性分析
            durations = [d[1] for d in available_durations]
            if len(durations) > 1:
                avg = sum(durations) / len(durations)
                max_deviation = max(abs(d - avg) for d in durations)
                report['consistency_analysis'] = {
                    'average_duration': avg,
                    'max_deviation': max_deviation,
                    'relative_deviation': max_deviation / max(avg, 1),
                    'is_consistent': max_deviation < 0.1  # 100ms阈值
                }
            else:
                report['consistency_analysis'] = {
                    'single_source': True,
                    'is_consistent': True
                }
            
            # 计算可靠性分数
            method_count = len(available_durations)
            consistency_bonus = 0.5 if report['consistency_analysis'].get('is_consistent', False) else 0
            report['reliability_score'] = min(1.0, (method_count / 3.0) + consistency_bonus)
        
        return report
    
    def batch_verify_durations(self, media_files: List[str]) -> Dict:
        """批量验证媒体文件时长
        
        Args:
            media_files: 媒体文件路径列表
            
        Returns:
            批量验证报告
        """
        batch_report = {
            'total_files': len(media_files),
            'verified_files': 0,
            'failed_files': 0,
            'average_reliability': 0.0,
            'files': {}
        }
        
        total_reliability = 0.0
        
        for media_file in media_files:
            is_video = media_file.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv'))
            
            verification_report = self.perform_comprehensive_verification(media_file, is_video)
            
            if 'error' not in verification_report:
                batch_report['verified_files'] += 1
                total_reliability += verification_report.get('reliability_score', 0)
            else:
                batch_report['failed_files'] += 1
            
            batch_report['files'][media_file] = verification_report
        
        if batch_report['verified_files'] > 0:
            batch_report['average_reliability'] = total_reliability / batch_report['verified_files']
        
        return batch_report
