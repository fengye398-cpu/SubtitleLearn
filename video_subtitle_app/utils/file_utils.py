import os
import shutil
import platform
import subprocess
from pathlib import Path
from typing import List, Tuple

class FileUtils:
    """文件工具类"""
    
    @staticmethod
    def ensure_dir(path: str):
        """确保目录存在"""
        Path(path).mkdir(parents=True, exist_ok=True)
    
    @staticmethod
    def get_file_size(path: str) -> int:
        """获取文件大小（字节）"""
        try:
            return Path(path).stat().st_size
        except (OSError, FileNotFoundError):
            return 0
    
    @staticmethod
    def get_directory_size(path: str) -> int:
        """获取目录大小（字节）"""
        total_size = 0
        try:
            for dirpath, dirnames, filenames in os.walk(path):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    try:
                        total_size += os.path.getsize(filepath)
                    except (OSError, FileNotFoundError):
                        continue
        except (OSError, FileNotFoundError):
            pass
        return total_size
    
    @staticmethod
    def format_size(size_bytes: int) -> str:
        """格式化文件大小"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        
        return f"{size_bytes:.1f} {size_names[i]}"
    
    @staticmethod
    def clean_filename(filename: str) -> str:
        """清理文件名，移除非法字符"""
        # Windows非法字符
        illegal_chars = '<>:"/\\|?*'
        for char in illegal_chars:
            filename = filename.replace(char, '_')
        
        # 移除控制字符
        filename = ''.join(c for c in filename if ord(c) >= 32)
        
        # 限制长度
        if len(filename) > 200:
            filename = filename[:200]
        
        return filename.strip()
    
    @staticmethod
    def get_video_extensions() -> List[str]:
        """获取支持的视频文件扩展名"""
        return ['.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.m4v', '.mpeg', '.mpg', '.ts', '.mts', '.m2ts']
    
    @staticmethod
    def get_audio_extensions() -> List[str]:
        """获取支持的音频文件扩展名"""
        return ['.mp3', '.wav', '.flac', '.aac', '.m4a', '.ogg', '.wma']
    
    @staticmethod
    def get_subtitle_extensions() -> List[str]:
        """获取支持的字幕文件扩展名"""
        return ['.srt', '.ass', '.ssa', '.vtt']
    
    @staticmethod
    def is_video_file(filepath: str) -> bool:
        """判断是否为视频文件"""
        ext = Path(filepath).suffix.lower()
        return ext in FileUtils.get_video_extensions()
    
    @staticmethod
    def is_audio_file(filepath: str) -> bool:
        """判断是否为音频文件"""
        ext = Path(filepath).suffix.lower()
        return ext in FileUtils.get_audio_extensions()
    
    @staticmethod
    def is_subtitle_file(filepath: str) -> bool:
        """判断是否为字幕文件"""
        ext = Path(filepath).suffix.lower()
        return ext in FileUtils.get_subtitle_extensions()
    
    @staticmethod
    def find_matching_subtitle(video_path: str) -> str:
        """查找匹配的字幕文件 - 增强对特殊符号路径的支持"""
        try:
            video_path = Path(video_path)
            base_name = video_path.stem
            parent_dir = video_path.parent

            # 确保父目录存在
            if not parent_dir.exists():
                return ""

            # 直接遍历目录文件，避免路径匹配问题
            try:
                for file in parent_dir.iterdir():
                    if file.is_file():
                        file_stem = file.stem
                        file_ext = file.suffix.lower()

                        # 检查文件名是否匹配且扩展名是字幕格式
                        if file_stem == base_name and file_ext in FileUtils.get_subtitle_extensions():
                            return str(file)
            except Exception as e:
                # 如果遍历失败，回退到原来的方法
                for ext in FileUtils.get_subtitle_extensions():
                    subtitle_path = parent_dir / f"{base_name}{ext}"
                    if subtitle_path.exists():
                        return str(subtitle_path)

            return ""
        except Exception:
            return ""
    
    @staticmethod
    def safe_remove(path: str):
        """安全删除文件或目录"""
        try:
            path_obj = Path(path)
            if path_obj.is_file():
                path_obj.unlink()
            elif path_obj.is_dir():
                shutil.rmtree(path)
        except (OSError, FileNotFoundError):
            pass
    
    @staticmethod
    def copy_file(src: str, dst: str):
        """复制文件"""
        try:
            FileUtils.ensure_dir(str(Path(dst).parent))
            shutil.copy2(src, dst)
            return True
        except Exception:
            return False
    
    @staticmethod
    def move_file(src: str, dst: str):
        """移动文件"""
        try:
            FileUtils.ensure_dir(str(Path(dst).parent))
            shutil.move(src, dst)
            return True
        except Exception:
            return False

    @staticmethod
    def open_directory(path: str):
        """跨平台打开目录

        Args:
            path: 目录路径
        """
        # 确保目录存在
        if not os.path.exists(path):
            FileUtils.ensure_dir(path)

        # 获取系统类型
        system = platform.system()

        try:
            if system == "Windows":
                # Windows: 使用 explorer
                os.startfile(path)
            elif system == "Darwin":
                # macOS: 使用 open
                subprocess.run(["open", path], check=True)
            else:
                # Linux: 使用 xdg-open
                subprocess.run(["xdg-open", path], check=True)
        except Exception as e:
            print(f"打开目录失败: {e}")
