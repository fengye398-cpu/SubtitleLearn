"""
预加载器：后台提取视频关键帧和音频头，加速播放启动
"""
import os
import subprocess
import threading
from pathlib import Path
from typing import Optional, Dict
from config.settings import app_config

class Preloader:
    """视频/音频预加载器"""
    
    def __init__(self):
        self.cache = {}  # {file_path: {'thumbnail': path, 'audio_header': path}}
        self.preload_dir = app_config.cache_dir / "preload"
        self.preload_dir.mkdir(parents=True, exist_ok=True)
        self.enabled = app_config.get('player.preload_enabled', True)
    
    def set_enabled(self, enabled: bool):
        """开关预加载"""
        self.enabled = enabled
        app_config.set('player.preload_enabled', enabled)
    
    def preload_segment(self, file_path: str, force: bool = False):
        """
        预加载单个片段：提取首帧缩略图 + 音频头（前3秒）
        force=True 强制重新提取
        """
        if not self.enabled and not force:
            return
        
        if not file_path or not os.path.exists(file_path):
            return
        
        # 已缓存且未强制刷新
        if file_path in self.cache and not force:
            return
        
        # 后台线程提取
        threading.Thread(target=self._extract_preview, args=(file_path,), daemon=True).start()
    
    def _extract_preview(self, file_path: str):
        """提取预览数据（缩略图 + 音频头）"""
        try:
            base_name = Path(file_path).stem
            thumb_path = self.preload_dir / f"{base_name}_thumb.jpg"
            audio_path = self.preload_dir / f"{base_name}_audio.mp3"
            
            # 提取首帧缩略图（320x240，快速）
            if not thumb_path.exists():
                cmd_thumb = [
                    "ffmpeg", "-y", "-i", file_path,
                    "-vf", "scale=320:240:force_original_aspect_ratio=decrease",
                    "-vframes", "1", "-q:v", "5",
                    str(thumb_path)
                ]
                subprocess.run(cmd_thumb, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              creationflags=subprocess.CREATE_NO_WINDOW, timeout=5)
            
            # 提取音频头（前3秒，用于快速音频预览）
            if not audio_path.exists():
                cmd_audio = [
                    "ffmpeg", "-y", "-i", file_path,
                    "-t", "3", "-vn", "-acodec", "libmp3lame", "-ab", "64k",
                    str(audio_path)
                ]
                subprocess.run(cmd_audio, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              creationflags=subprocess.CREATE_NO_WINDOW, timeout=5)
            
            # 缓存路径
            self.cache[file_path] = {
                'thumbnail': str(thumb_path) if thumb_path.exists() else None,
                'audio_header': str(audio_path) if audio_path.exists() else None
            }
        except Exception:
            pass
    
    def get_thumbnail(self, file_path: str) -> Optional[str]:
        """获取缩略图路径"""
        if file_path in self.cache:
            return self.cache[file_path].get('thumbnail')
        return None
    
    def clear_cache(self):
        """清理预加载缓存"""
        try:
            import shutil
            if self.preload_dir.exists():
                shutil.rmtree(self.preload_dir)
                self.preload_dir.mkdir(parents=True, exist_ok=True)
            self.cache.clear()
        except Exception:
            pass

# 全局预加载器实例
preloader = Preloader()

