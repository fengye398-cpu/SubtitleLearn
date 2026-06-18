#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
导出配置管理器 - 管理默认导出配置
"""

import os
import json
from pathlib import Path
from typing import Optional, Dict, Any


class ExportConfigManager:
    """导出配置管理器 - 保存和加载默认导出配置"""

    # 配置文件路径 - 使用用户主目录，支持EXE打包后使用
    @staticmethod
    def _get_config_dir():
        """获取配置目录（支持开发环境和打包后的EXE）"""
        # 优先使用用户主目录下的配置目录
        user_home = Path.home()
        config_dir = user_home / ".video_subtitle_cut"

        # 如果目录不存在，创建它
        config_dir.mkdir(parents=True, exist_ok=True)

        return config_dir

    @classmethod
    def _get_config_file(cls):
        """获取配置文件路径"""
        return cls._get_config_dir() / "export_default_config.json"

    # 系统默认配置
    SYSTEM_DEFAULT_CONFIG = {
        "output_dir": "",                      # 输出目录（空表示未设置）
        "naming_mode": "index",                # 命名方式: index / subtitle
        "fast_copy_mode": True,                # 导出模式: True=标准模式, False=重新编码
        "continuous_cut_mode": False,          # 是否连续切割
        "encoding_preset": "veryfast",         # FFmpeg预设
        "crf": "24",                           # CRF质量
        "target_resolution": "1920x1080",      # 目标分辨率
        "target_fps": "25",                    # 目标帧率
        "smart_validation": True,              # 智能校验
        "auto_fix_deviation": True,            # 自动修正偏差
    }

    @classmethod
    def save_config(cls, config: Dict[str, Any]) -> bool:
        """保存默认配置

        Args:
            config: 配置字典

        Returns:
            是否保存成功
        """
        try:
            # 获取配置文件路径
            config_file = cls._get_config_file()

            # 写入配置文件
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)

            print(f"[配置管理器] 默认配置已保存: {config_file}")
            return True

        except Exception as e:
            print(f"[配置管理器] 保存配置失败: {e}")
            return False

    @classmethod
    def load_config(cls) -> Optional[Dict[str, Any]]:
        """加载默认配置

        Returns:
            配置字典，如果不存在则返回None
        """
        try:
            config_file = cls._get_config_file()
            if not config_file.exists():
                print(f"[配置管理器] 配置文件不存在: {config_file}")
                return None

            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)

            print(f"[配置管理器] 已加载默认配置")
            return config

        except Exception as e:
            print(f"[配置管理器] 加载配置失败: {e}")
            return None

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        """获取默认配置

        如果用户已保存配置则返回用户配置，否则返回系统默认配置

        Returns:
            配置字典
        """
        user_config = cls.load_config()
        if user_config is not None:
            # 合并用户配置和系统默认配置（防止缺少字段）
            config = cls.SYSTEM_DEFAULT_CONFIG.copy()
            config.update(user_config)
            return config
        else:
            return cls.SYSTEM_DEFAULT_CONFIG.copy()

    @classmethod
    def has_user_config(cls) -> bool:
        """检查是否存在用户配置

        Returns:
            是否存在用户配置
        """
        return cls._get_config_file().exists()

    @classmethod
    def delete_config(cls) -> bool:
        """删除用户配置

        Returns:
            是否删除成功
        """
        try:
            config_file = cls._get_config_file()
            if config_file.exists():
                config_file.unlink()
                print(f"[配置管理器] 已删除用户配置")
                return True
            return False
        except Exception as e:
            print(f"[配置管理器] 删除配置失败: {e}")
            return False


# 便捷函数
def save_export_config(config: Dict[str, Any]) -> bool:
    """保存默认导出配置"""
    return ExportConfigManager.save_config(config)


def load_export_config() -> Optional[Dict[str, Any]]:
    """加载默认导出配置"""
    return ExportConfigManager.load_config()


def get_default_export_config() -> Dict[str, Any]:
    """获取默认导出配置"""
    return ExportConfigManager.get_default_config()


def has_export_config() -> bool:
    """检查是否存在用户配置"""
    return ExportConfigManager.has_user_config()
