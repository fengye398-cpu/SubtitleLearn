from datetime import datetime, timedelta
from typing import Union, Optional

class FormatUtils:
    """格式化工具类"""
    
    @staticmethod
    def format_time(seconds: float) -> str:
        """格式化时间（秒）为 HH:MM:SS 格式"""
        if seconds < 0:
            return "00:00:00"
        
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    @staticmethod
    def format_time_with_ms(seconds: float) -> str:
        """格式化时间（秒）为 HH:MM:SS,mmm 格式"""
        if seconds < 0:
            return "00:00:00,000"

        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        milliseconds = int((seconds % 1) * 1000)

        return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"
    
    @staticmethod
    def format_time_with_brackets(seconds: float) -> str:
        """格式化时间（秒）为 [HH:MM:SS.mmm] 格式"""
        if seconds < 0:
            return "[00:00:00.000]"

        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        milliseconds = int((seconds % 1) * 1000)

        return f"[{hours:02d}:{minutes:02d}:{secs:02d}.{milliseconds:03d}]"

    @staticmethod
    def format_srt_time(seconds: float) -> str:
        """格式化时间为SRT字幕格式 HH:MM:SS,mmm"""
        if seconds < 0:
            return "00:00:00,000"
        
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        milliseconds = int((seconds % 1) * 1000)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"
    
    @staticmethod
    def parse_srt_time(time_str: str) -> float:
        """解析SRT时间格式为秒数"""
        try:
            # 格式: HH:MM:SS,mmm
            time_part, ms_part = time_str.split(',')
            hours, minutes, seconds = map(int, time_part.split(':'))
            milliseconds = int(ms_part)
            
            total_seconds = hours * 3600 + minutes * 60 + seconds + milliseconds / 1000.0
            return total_seconds
        except (ValueError, IndexError):
            return 0.0
    
    @staticmethod
    def format_duration(start_time: float, end_time: float) -> str:
        """格式化时长"""
        duration = end_time - start_time
        return FormatUtils.format_time(duration)
    
    @staticmethod
    def format_datetime(dt: Union[datetime, str]) -> str:
        """格式化日期时间"""
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt)
            except ValueError:
                return dt
        
        if isinstance(dt, datetime):
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        
        return str(dt)
    
    @staticmethod
    def format_relative_time(dt: Union[datetime, str]) -> str:
        """格式化相对时间（如：2小时前）"""
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt)
            except ValueError:
                return dt
        
        if not isinstance(dt, datetime):
            return str(dt)
        
        now = datetime.now()
        diff = now - dt
        
        if diff.days > 0:
            return f"{diff.days}天前"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours}小时前"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes}分钟前"
        else:
            return "刚刚"
    
    @staticmethod
    def format_progress(current: int, total: int) -> str:
        """格式化进度"""
        if total == 0:
            return "0%"
        
        percentage = (current / total) * 100
        return f"{percentage:.1f}%"
    
    @staticmethod
    def format_speed(items_per_second: float) -> str:
        """格式化处理速度"""
        if items_per_second < 1:
            return f"{items_per_second:.2f} 项/秒"
        else:
            return f"{items_per_second:.1f} 项/秒"
    
    @staticmethod
    def format_eta(seconds_remaining: float) -> str:
        """格式化预计剩余时间"""
        if seconds_remaining <= 0:
            return "即将完成"
        
        if seconds_remaining < 60:
            return f"{int(seconds_remaining)}秒"
        elif seconds_remaining < 3600:
            minutes = int(seconds_remaining // 60)
            return f"{minutes}分钟"
        else:
            hours = int(seconds_remaining // 3600)
            minutes = int((seconds_remaining % 3600) // 60)
            return f"{hours}小时{minutes}分钟"
    
    @staticmethod
    def truncate_text(text: str, max_length: int = 50, suffix: str = "...") -> str:
        """截断文本"""
        if len(text) <= max_length:
            return text
        
        return text[:max_length - len(suffix)] + suffix
    
    @staticmethod
    def parse_time(time_str: str) -> Optional[float]:
        """解析时间字符串为秒数

        支持格式：
        - HH:MM:SS
        - HH:MM:SS.mmm
        - MM:SS
        - MM:SS.mmm
        - SS
        - SS.mmm
        """
        try:
            if not time_str or not isinstance(time_str, str):
                return None

            time_str = time_str.strip()

            # 尝试不同的分隔符
            if '.' in time_str:
                time_part, ms_part = time_str.split('.')
                milliseconds = float('.' + ms_part) * 1000 / 1000  # 转换为秒的小数部分
            elif ',' in time_str:
                time_part, ms_part = time_str.split(',')
                milliseconds = float('.' + ms_part) * 1000 / 1000
            else:
                time_part = time_str
                milliseconds = 0.0

            # 分割时间部分
            parts = time_part.split(':')

            if len(parts) == 3:  # HH:MM:SS
                hours, minutes, seconds = map(float, parts)
                total_seconds = hours * 3600 + minutes * 60 + seconds + milliseconds
            elif len(parts) == 2:  # MM:SS
                minutes, seconds = map(float, parts)
                total_seconds = minutes * 60 + seconds + milliseconds
            elif len(parts) == 1:  # SS
                seconds = float(parts[0])
                total_seconds = seconds + milliseconds
            else:
                return None

            return total_seconds

        except (ValueError, IndexError, AttributeError):
            return None

    @staticmethod
    def format_file_count(count: int, item_name: str = "项") -> str:
        """格式化文件数量"""
        if count == 0:
            return f"无{item_name}"
        elif count == 1:
            return f"1个{item_name}"
        else:
            return f"{count}个{item_name}"
