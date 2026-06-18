#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import pysrt
from pathlib import Path
from typing import List, Callable, Optional
from glob import glob

from database.manager import db_manager
from database.models import Project
from core.video_processor import VideoProcessor
from utils.file_utils import FileUtils

class BatchProcessor:
    """批量处理器"""
    
    def __init__(self):
        self.progress_callback: Optional[Callable] = None
        self.log_callback: Optional[Callable] = None
        self.cancel_flag = False
    
    def set_progress_callback(self, callback: Callable):
        """设置进度回调"""
        self.progress_callback = callback
    
    def set_log_callback(self, callback: Callable):
        """设置日志回调"""
        self.log_callback = callback
    
    def log(self, message: str):
        """记录日志"""
        if self.log_callback:
            self.log_callback(message)
        print(message)
    
    def update_progress(self, current: int, total: int, message: str = ""):
        """更新进度"""
        if self.progress_callback:
            progress = int((current / total) * 100) if total > 0 else 0
            self.progress_callback(progress, message)
    
    def batch_process(self, input_folder: str, output_folder: str, preset: str, crf: str, naming_mode: str) -> int:
        """批量处理视频和字幕文件"""
        try:
            self.log(f"开始批量处理：{input_folder}")
            
            # 查找所有视频文件
            video_files = self._find_video_files(input_folder)
            if not video_files:
                self.log("没有找到视频文件")
                return 0
            
            self.log(f"找到 {len(video_files)} 个视频文件")
            
            success_count = 0
            total_files = len(video_files)
            
            for i, video_file in enumerate(video_files, 1):
                if self.cancel_flag:
                    self.log("批量处理已取消")
                    break
                
                self.update_progress(i, total_files, f"处理文件 {i}/{total_files}: {Path(video_file).name}")
                
                # 查找对应的字幕文件
                subtitle_file = self._find_subtitle_file(video_file)
                if not subtitle_file:
                    self.log(f"跳过 {Path(video_file).name}：未找到对应的字幕文件")
                    continue
                
                # 处理单个文件
                if self._process_single_file(video_file, subtitle_file, output_folder, preset, crf, naming_mode):
                    success_count += 1
                    self.log(f"成功处理：{Path(video_file).name}")
                else:
                    self.log(f"处理失败：{Path(video_file).name}")
            
            self.log(f"批量处理完成，成功处理 {success_count}/{total_files} 个文件")
            return success_count
            
        except Exception as e:
            self.log(f"批量处理失败：{e}")
            return 0
    
    def _find_video_files(self, folder: str) -> List[str]:
        """查找视频文件"""
        video_extensions = FileUtils.get_video_extensions() + FileUtils.get_audio_extensions()
        video_files = []
        
        for ext in video_extensions:
            # 查找当前扩展名的文件（不区分大小写）
            pattern = os.path.join(folder, f"*{ext}")
            video_files.extend(glob(pattern))
            # 也查找大写扩展名
            pattern = os.path.join(folder, f"*{ext.upper()}")
            video_files.extend(glob(pattern))
        
        return sorted(list(set(video_files)))  # 去重并排序
    
    def _find_subtitle_file(self, video_file: str) -> Optional[str]:
        """查找对应的字幕文件"""
        video_path = Path(video_file)
        video_name = video_path.stem
        video_dir = video_path.parent

        # 查找同名的srt文件
        subtitle_extensions = ['.srt', '.SRT']

        for ext in subtitle_extensions:
            subtitle_file = video_dir / f"{video_name}{ext}"
            if subtitle_file.exists():
                return str(subtitle_file)

        return None
    
    def _process_single_file(self, video_file: str, subtitle_file: str, output_folder: str, 
                           preset: str, crf: str, naming_mode: str) -> bool:
        """处理单个文件"""
        try:
            # 创建视频处理器
            processor = VideoProcessor()
            
            # 设置回调（传递给子处理器）
            if self.progress_callback:
                processor.set_progress_callback(self.progress_callback)
            if self.log_callback:
                processor.set_log_callback(self.log_callback)
            
            # 导入到数据库
            project_id = processor.import_video_subtitle(video_file, subtitle_file, preset, crf)
            
            if not project_id:
                return False
            
            # 如果指定了输出文件夹，还需要导出文件
            if output_folder:
                return self._export_segments(project_id, video_file, output_folder, naming_mode)
            
            return True
            
        except Exception as e:
            self.log(f"处理文件失败 {Path(video_file).name}：{e}")
            return False
    
    def _export_segments(self, project_id: int, video_file: str, output_folder: str, naming_mode: str) -> bool:
        """导出片段到指定文件夹"""
        try:
            # 获取项目信息
            project = db_manager.get_project(project_id)
            if not project:
                return False
            
            # 创建输出子文件夹
            video_name = Path(video_file).stem
            project_output_dir = Path(output_folder) / video_name
            project_output_dir.mkdir(parents=True, exist_ok=True)
            
            # 获取所有片段
            segments = db_manager.get_segments_by_project(project_id)
            if not segments:
                return False
            
            # 复制片段文件到输出文件夹
            for segment in segments:
                try:
                    # 确定文件名
                    if naming_mode == "subtitle":
                        # 按序号+字幕内容命名
                        clean_text = FileUtils.clean_filename(segment.text[:20])
                        base_name = f"{segment.index_num:03d}_{clean_text}"
                    else:
                        # 按序号命名
                        base_name = f"{segment.index_num:03d}"
                    
                    # 复制视频文件
                    if segment.video_file and os.path.exists(segment.video_file):
                        src_video = Path(segment.video_file)
                        dst_video = project_output_dir / f"{base_name}{src_video.suffix}"
                        import shutil
                        shutil.copy2(segment.video_file, dst_video)
                    
                    # 复制音频文件
                    if segment.audio_file and os.path.exists(segment.audio_file):
                        src_audio = Path(segment.audio_file)
                        dst_audio = project_output_dir / f"{base_name}{src_audio.suffix}"
                        import shutil
                        shutil.copy2(segment.audio_file, dst_audio)
                    
                    # 复制字幕文件
                    if segment.subtitle_file and os.path.exists(segment.subtitle_file):
                        src_subtitle = Path(segment.subtitle_file)
                        dst_subtitle = project_output_dir / f"{base_name}{src_subtitle.suffix}"
                        import shutil
                        shutil.copy2(segment.subtitle_file, dst_subtitle)
                
                except Exception as e:
                    self.log(f"复制片段文件失败 {segment.index_num}：{e}")
                    continue
            
            self.log(f"片段文件已导出到：{project_output_dir}")
            return True
            
        except Exception as e:
            self.log(f"导出片段失败：{e}")
            return False
    
    def cancel(self):
        """取消处理"""
        self.cancel_flag = True
