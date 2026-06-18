#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增强视频处理器
使用关键帧分析和元数据储存，替代视频切割储存机制
"""

import os
import time
import threading
from pathlib import Path
from typing import List, Optional, Callable, Dict, Any

import pysrt
from database.manager import db_manager
from database.models import Project, SubtitleSegment, ImportResult
from config.settings import app_config
from utils.file_utils import FileUtils
from core.keyframe_analyzer import keyframe_analyzer


class EnhancedVideoProcessor:
    """增强视频处理器 - 基于关键帧分析和元数据储存"""
    
    def __init__(self):
        self.cancel_flag = False
        self.progress_callback: Optional[Callable] = None
        self.log_callback: Optional[Callable] = None
        
    def set_callbacks(self, progress_callback: Optional[Callable] = None,
                     log_callback: Optional[Callable] = None):
        """设置回调函数"""
        self.progress_callback = progress_callback
        self.log_callback = log_callback
        
    def cancel_operation(self):
        """取消当前操作"""
        self.cancel_flag = True
        
    def log(self, message: str):
        """记录日志"""
        print(f"[EnhancedVideoProcessor] {message}")
        if self.log_callback:
            self.log_callback(message)
            
    def update_progress(self, current: int, total: int, message: str = ""):
        """更新进度"""
        if self.progress_callback:
            self.progress_callback(current, total, message)
            
    def import_video_subtitle(self, video_path: str, subtitle_path: str, 
                            preset: str = "medium", crf: str = "23") -> ImportResult:
        """
        导入视频和字幕 - 使用增强模式（关键帧分析 + 元数据储存）
        
        Args:
            video_path: 视频文件路径
            subtitle_path: 字幕文件路径
            preset: 编码预设（保留兼容性，实际不使用）
            crf: 质量参数（保留兼容性，实际不使用）
            
        Returns:
            ImportResult: 导入结果
        """
        start_time = time.time()
        result = ImportResult()
        
        try:
            self.cancel_flag = False
            
            # 验证文件
            if not os.path.exists(video_path):
                result.error_message = f"视频文件不存在：{video_path}"
                return result
                
            if not os.path.exists(subtitle_path):
                result.error_message = f"字幕文件不存在：{subtitle_path}"
                return result
                
            # 获取原始视频名称（保留特殊字符用于显示）
            original_video_name = Path(video_path).stem
            # 清理项目名称（用于数据库存储和文件系统操作）
            video_name = self._clean_project_name(original_video_name)
            self.log(f"开始导入项目：{original_video_name}")
            
            # 检查项目是否已存在
            existing_projects = db_manager.get_all_projects()
            for project in existing_projects:
                if project.name == video_name:
                    self.log(f"项目 {video_name} 已存在，跳过导入")
                    result.success = True
                    result.skipped = True
                    result.project_id = project.id
                    result.duration = time.time() - start_time
                    return result
                    
            self.update_progress(10, 100, "创建项目...")
            
            # 创建项目记录
            from database.models import Project
            from config.settings import app_config
            from utils.file_utils import FileUtils

            # 创建缓存目录
            cache_dir = str(app_config.cache_dir / video_name)
            FileUtils.ensure_dir(cache_dir)

            project = Project(
                name=video_name,
                video_path=video_path,
                subtitle_path=subtitle_path,
                cache_dir=cache_dir
            )
            project_id = db_manager.create_project(project)
            
            if not project_id:
                result.error_message = "创建项目失败"
                return result
                
            result.project_id = project_id
            self.log(f"项目创建成功，ID: {project_id}")
            
            self.update_progress(20, 100, "解析字幕文件...")
            
            # 解析字幕
            subs = self._parse_subtitle_file(subtitle_path)
            if not subs:
                db_manager.delete_project(project_id)
                result.error_message = "字幕解析失败"
                return result
                
            self.log(f"找到 {len(subs)} 个字幕片段")
            result.total_segments = len(subs)

            # 检测过短的字幕片段（<200ms）
            self.update_progress(30, 100, "检测过短字幕片段...")
            short_segments_info = self._detect_short_segments(subs)

            if short_segments_info:
                # 有过短片段，需要用户确认
                user_choice = self._handle_short_segments_confirmation(short_segments_info, subs)

                if user_choice == "cancel":
                    # 用户取消导入 - 需要删除已创建的项目
                    self.log("用户取消导入（检测到过短片段）")
                    db_manager.delete_project(project_id)  # 删除已创建的项目
                    result.error_message = "用户取消导入（检测到过短片段）"
                    return result
                elif user_choice == "filter":
                    # 过滤掉过短片段
                    original_count = len(subs)
                    subs = [sub for i, sub in enumerate(subs) if (i + 1) not in short_segments_info['indices']]
                    filtered_count = original_count - len(subs)
                    self.log(f"已过滤掉 {filtered_count} 个过短片段，剩余 {len(subs)} 个片段")
                    result.total_segments = len(subs)

                    if len(subs) == 0:
                        # 过滤后没有剩余片段 - 需要删除已创建的项目
                        db_manager.delete_project(project_id)
                        result.error_message = "过滤后没有剩余片段，无法继续导入"
                        return result
                elif user_choice == "keep_all":
                    # 保留所有片段（用户选择忽略风险）
                    self.log(f"用户确认保留所有片段（包含 {len(short_segments_info['indices'])} 个过短片段）")

            self.update_progress(40, 100, "分析视频关键帧...")
            
            # 启动关键帧分析（异步）
            keyframe_analysis_complete = threading.Event()
            keyframe_analysis_success = [False]  # 使用列表以便在闭包中修改
            
            def on_keyframe_progress(current, total, message):
                # 将关键帧分析进度映射到40-70%
                progress = 40 + (current / total) * 30
                self.update_progress(int(progress), 100, f"关键帧分析: {message}")
                
            def on_keyframe_complete(success, keyframes, error_msg):
                keyframe_analysis_success[0] = success
                if success:
                    self.log(f"关键帧分析完成: 找到 {len(keyframes)} 个关键帧")
                else:
                    self.log(f"关键帧分析失败: {error_msg}")
                keyframe_analysis_complete.set()
                
            # 启动关键帧分析
            keyframe_analyzer.analyze_video_keyframes(
                video_path,
                progress_callback=on_keyframe_progress,
                completion_callback=on_keyframe_complete
            )
            
            self.update_progress(70, 100, "储存字幕元数据...")
            
            # 储存字幕片段元数据
            stats = self._store_subtitle_metadata(project_id, video_path, subs)
            
            # 等待关键帧分析完成
            self.update_progress(90, 100, "等待关键帧分析完成...")
            keyframe_analysis_complete.wait(timeout=300)  # 最多等待5分钟
            
            if not keyframe_analysis_success[0]:
                self.log("警告：关键帧分析失败，但不影响基本功能")
                
            # 更新结果统计
            result.success = stats['success']
            result.video_success = 0  # 不切割视频
            result.video_failed = 0
            result.audio_success = 0  # 不切割音频
            result.audio_failed = 0
            result.subtitle_success = stats['subtitle_success']
            result.subtitle_failed = stats['subtitle_failed']
            result.duration = time.time() - start_time
            
            if result.success and not self.cancel_flag:
                self.log(f"项目导入完成：{original_video_name}")
                self.update_progress(100, 100, "导入完成")
            else:
                # 清理失败的项目
                db_manager.delete_project(project_id)
                result.error_message = "导入过程中出现错误或被取消"
                
            return result
            
        except Exception as e:
            self.log(f"导入失败：{e}")
            result.error_message = str(e)
            if result.project_id:
                db_manager.delete_project(result.project_id)
            return result
            
    def _parse_subtitle_file(self, subtitle_path: str) -> Optional[List]:
        """解析字幕文件，支持多种编码"""
        try:
            # 首先尝试使用utf-8-sig（自动处理BOM）
            try:
                subs = pysrt.open(subtitle_path, encoding="utf-8-sig")
                if subs:
                    self.log("使用UTF-8-sig编码解析字幕成功")
                    return self._filter_valid_subtitles(subs)
            except Exception:
                pass

            # 尝试使用utf-8
            try:
                subs = pysrt.open(subtitle_path, encoding="utf-8")
                if subs:
                    self.log("使用UTF-8编码解析字幕成功")
                    return self._filter_valid_subtitles(subs)
            except Exception:
                pass

            # 尝试使用gbk（中文字幕常用编码）
            try:
                subs = pysrt.open(subtitle_path, encoding="gbk")
                if subs:
                    self.log("使用GBK编码解析字幕成功")
                    return self._filter_valid_subtitles(subs)
            except Exception:
                pass

            # 尝试自动检测编码
            try:
                import chardet
                with open(subtitle_path, 'rb') as f:
                    raw_data = f.read()
                    encoding = chardet.detect(raw_data)['encoding']
                    if encoding:
                        subs = pysrt.open(subtitle_path, encoding=encoding)
                        if subs:
                            self.log(f"使用自动检测编码 {encoding} 解析字幕成功")
                            return self._filter_valid_subtitles(subs)
            except Exception:
                pass

            self.log("所有编码尝试失败，字幕解析失败")
            return None

        except Exception as e:
            self.log(f"字幕解析失败：{e}")
            return None

    def _clean_project_name(self, name: str) -> str:
        """清理项目名称，确保兼容数据库和文件系统"""
        if not name:
            return "untitled_project"

        # 保留原始名称的可读性，只替换真正有问题的字符
        # 替换数据库和文件系统不友好的字符
        replacements = {
            '"': "'",  # 双引号改为单引号
            '*': '_',  # 星号
            '?': '_',  # 问号
            '<': '(',  # 小于号
            '>': ')',  # 大于号
            '|': '_',  # 管道符
            ':': '-',  # 冒号
            '\\': '_', # 反斜杠
            '/': '_',  # 正斜杠
        }

        cleaned_name = name
        for old_char, new_char in replacements.items():
            cleaned_name = cleaned_name.replace(old_char, new_char)

        # 移除控制字符，但保留方括号等常见字符
        cleaned_name = ''.join(c for c in cleaned_name if ord(c) >= 32 or c in '\t\n\r')

        # 去除首尾空白
        cleaned_name = cleaned_name.strip()

        # 如果清理后为空，使用默认名称
        if not cleaned_name:
            cleaned_name = "untitled_project"

        # 限制长度
        if len(cleaned_name) > 200:
            cleaned_name = cleaned_name[:200].rstrip()

        return cleaned_name

    def _filter_valid_subtitles(self, subs) -> List:
        """过滤有效字幕"""
        valid_subs = []
        for sub in subs:
            if sub.text and sub.text.strip():
                valid_subs.append(sub)

        self.log(f"有效字幕片段：{len(valid_subs)}")
        return valid_subs

    def _detect_short_segments(self, subs: List) -> Optional[Dict[str, Any]]:
        """检测过短的字幕片段（<200ms）

        Args:
            subs: 字幕列表

        Returns:
            如果有过短片段，返回字典：
            {
                'count': 过短片段数量,
                'indices': 过短片段的索引列表（1-based）,
                'segments': 过短片段的详细信息列表
            }
            如果没有过短片段，返回 None
        """
        MIN_DURATION = 0.2  # 最小时长阈值（200ms）
        short_segments = []
        short_indices = []

        for i, sub in enumerate(subs, 1):
            start_time = sub.start.ordinal / 1000.0
            end_time = sub.end.ordinal / 1000.0
            duration = end_time - start_time

            if duration < MIN_DURATION:
                # 记录过短片段的详细信息
                short_segments.append({
                    'index': i,
                    'start_time': start_time,
                    'end_time': end_time,
                    'duration': duration,
                    'time_str': f"{sub.start} --> {sub.end}",
                    'text': sub.text.strip()
                })
                short_indices.append(i)

        if short_segments:
            self.log(f"检测到 {len(short_segments)} 个过短片段（时长 <200ms）")
            return {
                'count': len(short_segments),
                'indices': short_indices,
                'segments': short_segments
            }
        else:
            self.log("未检测到过短片段")
            return None

    def _handle_short_segments_confirmation(self, short_segments_info: Dict[str, Any], subs: List) -> str:
        """处理过短片段确认（通过回调函数）

        Args:
            short_segments_info: 过短片段信息
            subs: 完整字幕列表

        Returns:
            用户选择：'filter' / 'keep_all' / 'cancel'
        """
        # 在日志中显示所有过短片段的详细信息
        self.log("=" * 60)
        self.log("检测到过短的字幕片段（时长 <200ms）")
        self.log(f"总计：{short_segments_info['count']} 个过短片段")
        self.log("=" * 60)
        self.log(f"以下是所有 {short_segments_info['count']} 个过短片段的详细信息：")
        self.log("")

        # 显示所有过短片段（不限制数量）
        for i, seg_info in enumerate(short_segments_info['segments'], 1):
            self.log(f"--- 片段 #{i} (序号{seg_info['index']}, 时长{seg_info['duration']:.3f}秒) ---")
            self.log(f"{seg_info['index']}")
            self.log(f"{seg_info['time_str']}")
            # 显示字幕内容（可能包含多行）
            for line in seg_info['text'].split('\n'):
                self.log(line)
            self.log("")

        self.log("=" * 60)

        # 通过回调函数显示确认对话框（需要在UI线程中执行）
        # 如果没有回调函数，默认返回 'cancel'
        if not hasattr(self, 'short_segments_callback') or not self.short_segments_callback:
            self.log("警告：未设置过短片段确认回调函数，默认取消导入")
            return 'cancel'

        # 调用回调函数，返回用户选择
        user_choice = self.short_segments_callback(short_segments_info, len(subs))
        return user_choice

    def set_short_segments_callback(self, callback: Callable):
        """设置过短片段确认回调函数

        回调函数签名：callback(short_segments_info: Dict, total_count: int) -> str
        返回值：'filter' / 'keep_all' / 'cancel'
        """
        self.short_segments_callback = callback

    def _store_subtitle_metadata(self, project_id: int, video_path: str, subs: List) -> Dict[str, Any]:
        """储存字幕元数据到数据库"""
        stats = {
            'success': False,
            'subtitle_success': 0,
            'subtitle_failed': 0
        }
        
        try:
            total_segments = len(subs)
            
            for i, sub in enumerate(subs, 1):
                if self.cancel_flag:
                    self.log("操作已取消")
                    break
                    
                self.update_progress(
                    70 + int((i / total_segments) * 20), 
                    100, 
                    f"储存元数据 {i}/{total_segments}"
                )
                
                try:
                    # 时间转换
                    start_time = sub.start.ordinal / 1000.0
                    end_time = sub.end.ordinal / 1000.0
                    duration = end_time - start_time
                    
                    # 保留原始字幕文本（包含换行符）
                    text = sub.text.strip()

                    # 解析双语字幕
                    from core.video_processor import VideoProcessor
                    text_primary, text_secondary = VideoProcessor.parse_subtitle_text(text)

                    # 创建字幕片段记录（只储存元数据，不储存文件）
                    from database.models import SubtitleSegment
                    segment = SubtitleSegment(
                        project_id=project_id,
                        index_num=i,
                        start_time=start_time,
                        end_time=end_time,
                        text=text,
                        text_primary=text_primary,  # 原文（第一行）
                        text_secondary=text_secondary,  # 译文（第二行，可能为None）
                        video_file=None,  # 不储存切割后的视频文件
                        audio_file=None,  # 不储存切割后的音频文件
                        subtitle_file=None  # 不储存单独的字幕文件
                    )
                    segment_id = db_manager.create_segment(segment)
                    
                    if segment_id:
                        stats['subtitle_success'] += 1
                    else:
                        stats['subtitle_failed'] += 1
                        self.log(f"警告：片段 {i} 元数据储存失败")
                        
                except Exception as e:
                    stats['subtitle_failed'] += 1
                    self.log(f"错误：片段 {i} 处理失败：{e}")
                    
            stats['success'] = stats['subtitle_success'] > 0 and not self.cancel_flag
            
            self.log(f"元数据储存完成：成功 {stats['subtitle_success']} 个，失败 {stats['subtitle_failed']} 个")
            
        except Exception as e:
            self.log(f"储存元数据失败：{e}")
            stats['success'] = False
            
        return stats
        
    def get_video_info(self, video_path: str) -> Optional[Dict[str, Any]]:
        """获取视频信息"""
        try:
            import subprocess
            
            cmd = [
                'ffprobe', '-v', 'quiet',
                '-print_format', 'json',
                '-show_format', '-show_streams',
                video_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            if result.returncode == 0:
                import json
                info = json.loads(result.stdout)
                return info
            else:
                self.log(f"获取视频信息失败：{result.stderr}")
                return None
                
        except Exception as e:
            self.log(f"获取视频信息异常：{e}")
            return None


# 全局增强视频处理器实例
enhanced_video_processor = EnhancedVideoProcessor()
