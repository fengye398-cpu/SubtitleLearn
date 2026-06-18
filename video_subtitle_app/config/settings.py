import os
import json
from pathlib import Path

class AppConfig:
    """应用配置管理类"""
    
    def __init__(self):
        self.app_dir = Path.home() / ".video_subtitle_app"
        self.config_file = self.app_dir / "config.json"
        self.cache_dir = self.app_dir / "cache"
        self.db_file = self.app_dir / "app.db"
        
        # 确保目录存在
        self.app_dir.mkdir(exist_ok=True)
        self.cache_dir.mkdir(exist_ok=True)
        
        # 默认配置
        self.default_config = {
            "window": {
                "width": 1200,
                "height": 800,
                "x": 100,
                "y": 100
            },
            "player": {
                "type": "ffplay",  # 播放器类型：ffplay 或 mpv
                "volume": 100,  # 提高默认音量到100%
                "auto_play": False,
                "loop": False,
                "repeat_count": 1,
                "window_width": 800,
                "window_height": 600
            },
            "export": {
                "preset": "veryfast",
                "crf": "24",
                "default_format": "mp4"
            },
            "pagination": {
                "items_per_page": 30,
                "max_items_per_page": 500
            },
            "cache": {
                "max_size_gb": 10,
                "auto_cleanup": True,
                "cleanup_days": 30
            },
            "timeline_editor": {
                "default_adjust_step": 0.1,
                "remember_adjust_step": True,
                "last_adjust_step": 0.1
            }
        }
        
        self.config = self.load_config()
    
    def load_config(self):
        """加载配置文件"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                # 合并默认配置
                return self._merge_config(self.default_config, config)
            except Exception as e:
                print(f"加载配置文件失败: {e}")
                return self.default_config.copy()
        else:
            return self.default_config.copy()
    
    def save_config(self):
        """保存配置文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"保存配置文件失败: {e}")
    
    def _merge_config(self, default, user):
        """合并配置，保留用户配置，补充默认配置"""
        result = default.copy()
        for key, value in user.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_config(result[key], value)
            else:
                result[key] = value
        return result
    
    def get(self, key_path, default=None):
        """获取配置值，支持点分隔的路径"""
        keys = key_path.split('.')
        value = self.config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value
    
    def set(self, key_path, value):
        """设置配置值，支持点分隔的路径"""
        keys = key_path.split('.')
        config = self.config
        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            config = config[key]
        config[keys[-1]] = value
        self.save_config()

    def get_column_widths(self) -> dict:
        """获取列宽配置"""
        return self.config.get('ui', {}).get('column_widths', {})

    def save_column_widths(self, widths: dict):
        """保存列宽配置"""
        if 'ui' not in self.config:
            self.config['ui'] = {}
        self.config['ui']['column_widths'] = widths
        self.save_config()

    def get_window_geometry(self) -> dict:
        """获取窗口几何信息"""
        return self.config.get('window', {})

    def save_window_geometry(self, width: int, height: int, x: int, y: int):
        """保存窗口几何信息"""
        if 'window' not in self.config:
            self.config['window'] = {}
        self.config['window'].update({
            'width': width,
            'height': height,
            'x': x,
            'y': y
        })
        self.save_config()

# 全局配置实例
app_config = AppConfig()
