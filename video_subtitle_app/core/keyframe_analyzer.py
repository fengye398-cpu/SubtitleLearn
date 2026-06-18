#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
关键帧分析器
用于分析视频关键帧，建立时间索引，替代视频切割储存机制
"""

import os
import subprocess
import threading
import json
import time
from pathlib import Path
from typing import List, Optional, Callable, Dict, Any
from bisect import bisect_left

from config.settings import app_config
from utils.file_utils import FileUtils


class KeyframeAnalyzer:
    """关键帧分析器"""
    
    def __init__(self):
        self.keyframes_cache: Dict[str, List[float]] = {}
        self.analysis_threads: Dict[str, threading.Thread] = {}
        self.progress_callbacks: Dict[str, Callable] = {}
        self.completion_callbacks: Dict[str, Callable] = {}
        
    def analyze_video_keyframes(self, video_path: str, 
                               progress_callback: Optional[Callable] = None,
                               completion_callback: Optional[Callable] = None) -> bool:
        """
        分析视频关键帧
        
        Args:
            video_path: 视频文件路径
            progress_callback: 进度回调函数 (current, total, message)
            completion_callback: 完成回调函数 (success, keyframes, error_msg)
            
        Returns:
            bool: 是否成功启动分析
        """
        if not os.path.exists(video_path):
            if completion_callback:
                completion_callback(False, [], "视频文件不存在")
            return False
            
        # 检查是否已有缓存
        cache_key = self._get_cache_key(video_path)
        if cache_key in self.keyframes_cache:
            if completion_callback:
                completion_callback(True, self.keyframes_cache[cache_key], "")
            return True
            
        # 检查是否正在分析
        if cache_key in self.analysis_threads and self.analysis_threads[cache_key].is_alive():
            return True
            
        # 保存回调函数
        if progress_callback:
            self.progress_callbacks[cache_key] = progress_callback
        if completion_callback:
            self.completion_callbacks[cache_key] = completion_callback
            
        # 启动分析线程
        thread = threading.Thread(
            target=self._analyze_worker,
            args=(video_path, cache_key),
            daemon=True
        )
        thread.start()
        self.analysis_threads[cache_key] = thread
        
        return True
        
    def _analyze_worker(self, video_path: str, cache_key: str):
        """关键帧分析工作线程"""
        try:
            progress_callback = self.progress_callbacks.get(cache_key)
            completion_callback = self.completion_callbacks.get(cache_key)
            
            if progress_callback:
                progress_callback(0, 100, "开始分析关键帧...")
                
            # 使用ffprobe获取关键帧信息
            cmd = [
                'ffprobe', '-v', 'quiet',
                '-select_streams', 'v:0',
                '-show_entries', 'packet=pts_time,flags',
                '-of', 'csv=p=0',
                video_path
            ]
            
            if progress_callback:
                progress_callback(20, 100, "执行ffprobe分析...")
                
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=120,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            if result.returncode != 0:
                error_msg = f"ffprobe执行失败: {result.stderr}"
                if completion_callback:
                    completion_callback(False, [], error_msg)
                return
                
            if progress_callback:
                progress_callback(60, 100, "解析关键帧数据...")
                
            # 解析关键帧时间点
            keyframes = []
            lines = result.stdout.strip().split('\n')
            
            for i, line in enumerate(lines):
                if 'K' in line:  # 关键帧标记
                    parts = line.split(',')
                    if len(parts) >= 2:
                        try:
                            pts_time = float(parts[0])
                            keyframes.append(pts_time)
                        except ValueError:
                            continue
                            
                # 更新进度
                if progress_callback and i % 1000 == 0:
                    progress = 60 + (i / len(lines)) * 30
                    progress_callback(int(progress), 100, f"解析关键帧: {len(keyframes)} 个")
                    
            # 排序并缓存
            keyframes = sorted(keyframes)
            self.keyframes_cache[cache_key] = keyframes
            
            if progress_callback:
                progress_callback(100, 100, f"分析完成: 找到 {len(keyframes)} 个关键帧")
                
            # 保存到磁盘缓存
            self._save_keyframes_cache(video_path, keyframes)
            
            if completion_callback:
                completion_callback(True, keyframes, "")
                
        except subprocess.TimeoutExpired:
            error_msg = "关键帧分析超时"
            if completion_callback:
                completion_callback(False, [], error_msg)
        except Exception as e:
            error_msg = f"关键帧分析失败: {e}"
            if completion_callback:
                completion_callback(False, [], error_msg)
        finally:
            # 清理回调
            self.progress_callbacks.pop(cache_key, None)
            self.completion_callbacks.pop(cache_key, None)
            
    def get_keyframes(self, video_path: str) -> Optional[List[float]]:
        """获取视频的关键帧列表"""
        cache_key = self._get_cache_key(video_path)
        
        # 先检查内存缓存
        if cache_key in self.keyframes_cache:
            return self.keyframes_cache[cache_key]
            
        # 尝试从磁盘缓存加载
        keyframes = self._load_keyframes_cache(video_path)
        if keyframes:
            self.keyframes_cache[cache_key] = keyframes
            return keyframes
            
        return None
        
    def find_nearest_keyframe(self, video_path: str, target_time: float) -> Optional[float]:
        """找到离目标时间最近的关键帧"""
        keyframes = self.get_keyframes(video_path)
        if not keyframes:
            return None
            
        pos = bisect_left(keyframes, target_time)
        
        if pos == 0:
            return keyframes[0]
        elif pos == len(keyframes):
            return keyframes[-1]
        else:
            before = keyframes[pos - 1]
            after = keyframes[pos]
            
            if abs(before - target_time) < abs(after - target_time):
                return before
            else:
                return after
                
    def _get_cache_key(self, video_path: str) -> str:
        """生成缓存键"""
        # 使用文件路径和修改时间作为缓存键
        try:
            stat = os.stat(video_path)
            return f"{video_path}_{stat.st_mtime}_{stat.st_size}"
        except:
            return video_path
            
    def _get_cache_file_path(self, video_path: str) -> str:
        """获取关键帧缓存文件路径"""
        cache_dir = app_config.cache_dir / "keyframes"
        cache_dir.mkdir(exist_ok=True)
        
        # 使用视频文件名和哈希作为缓存文件名
        video_name = Path(video_path).stem
        cache_key = self._get_cache_key(video_path)
        cache_hash = str(hash(cache_key))[-8:]  # 取哈希的后8位
        
        return str(cache_dir / f"{video_name}_{cache_hash}.json")
        
    def _save_keyframes_cache(self, video_path: str, keyframes: List[float]):
        """保存关键帧缓存到磁盘"""
        try:
            cache_file = self._get_cache_file_path(video_path)
            cache_data = {
                'video_path': video_path,
                'keyframes': keyframes,
                'created_time': time.time(),
                'video_stat': {
                    'mtime': os.path.getmtime(video_path),
                    'size': os.path.getsize(video_path)
                }
            }
            
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2)
                
        except Exception as e:
            print(f"保存关键帧缓存失败: {e}")
            
    def _load_keyframes_cache(self, video_path: str) -> Optional[List[float]]:
        """从磁盘加载关键帧缓存"""
        try:
            cache_file = self._get_cache_file_path(video_path)
            if not os.path.exists(cache_file):
                return None
                
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
                
            # 验证缓存是否有效
            if cache_data.get('video_path') != video_path:
                return None
                
            video_stat = cache_data.get('video_stat', {})
            current_mtime = os.path.getmtime(video_path)
            current_size = os.path.getsize(video_path)
            
            if (video_stat.get('mtime') != current_mtime or 
                video_stat.get('size') != current_size):
                # 视频文件已修改，缓存无效
                os.remove(cache_file)
                return None
                
            return cache_data.get('keyframes', [])
            
        except Exception as e:
            print(f"加载关键帧缓存失败: {e}")
            return None
            
    def clear_cache(self, video_path: Optional[str] = None):
        """清理缓存"""
        if video_path:
            # 清理指定视频的缓存
            cache_key = self._get_cache_key(video_path)
            self.keyframes_cache.pop(cache_key, None)
            
            try:
                cache_file = self._get_cache_file_path(video_path)
                if os.path.exists(cache_file):
                    os.remove(cache_file)
            except Exception as e:
                print(f"删除缓存文件失败: {e}")
        else:
            # 清理所有缓存
            self.keyframes_cache.clear()
            
            try:
                cache_dir = app_config.cache_dir / "keyframes"
                if cache_dir.exists():
                    for cache_file in cache_dir.glob("*.json"):
                        cache_file.unlink()
            except Exception as e:
                print(f"清理缓存目录失败: {e}")


# 全局关键帧分析器实例
keyframe_analyzer = KeyframeAnalyzer()
