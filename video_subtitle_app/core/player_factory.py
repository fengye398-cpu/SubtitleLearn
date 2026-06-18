#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
播放器工厂
根据配置创建合适的播放器实例
"""

from typing import List, Tuple, Optional
from core.player_base import PlayerBase
from core.player_ffplay import FFplayPlayer
from core.player_mpv import MPVPlayer
from core.enhanced_player import EnhancedPlayer
# 暂时禁用enhanced_mpv_player以避免python-mpv库依赖问题
# from core.enhanced_mpv_player import EnhancedMPVPlayer
from config.settings import app_config


class PlayerFactory:
    """播放器工厂类"""
    
    @staticmethod
    def create_player() -> PlayerBase:
        """创建播放器实例（优先MPV，回退到FFplay）

        Returns:
            PlayerBase: 播放器实例
        """
        # 首先尝试MPV播放器
        try:
            print("检查MPV播放器可用性...")
            if MPVPlayer.is_available():
                print("使用 MPV 播放器")
                return MPVPlayer()
            else:
                print("MPV 不可用，尝试回退到 FFplay")
        except Exception as e:
            print(f"MPV 检查失败：{e}，尝试回退到 FFplay")

        # 回退到FFplay播放器
        try:
            print("检查FFplay播放器可用性...")
            if FFplayPlayer.is_available():
                print("使用 FFplay 播放器（回退）")
                return FFplayPlayer()
            else:
                print("FFplay 也不可用")
        except Exception as e:
            print(f"FFplay 检查失败：{e}")

        # 如果都不可用，抛出异常
        raise RuntimeError("没有可用的播放器！请确保已安装 MPV 或 FFmpeg。")
    
    @staticmethod
    def get_available_players() -> List[Tuple[str, str, str]]:
        """获取可用的播放器列表

        Returns:
            List[Tuple[str, str, str]]: 播放器列表，每项为 (类型, 名称, 描述)
        """
        players = []

        # 检查 MPV（优先）
        try:
            if MPVPlayer.is_available():
                players.append((
                    'mpv',
                    MPVPlayer.get_name(),
                    MPVPlayer.get_description()
                ))
        except Exception as e:
            print(f"检查 MPV 时出错：{e}")

        # 检查 FFplay（回退）
        try:
            if FFplayPlayer.is_available():
                players.append((
                    'ffplay',
                    FFplayPlayer.get_name(),
                    FFplayPlayer.get_description()
                ))
        except Exception as e:
            print(f"检查 FFplay 时出错：{e}")

        return players
    
    @staticmethod
    def get_current_player_info() -> Optional[Tuple[str, str, str]]:
        """获取当前配置的播放器信息

        Returns:
            Optional[Tuple[str, str, str]]: (类型, 名称, 描述) 或 None
        """
        # 优先返回MPV
        try:
            if MPVPlayer.is_available():
                return ('mpv', MPVPlayer.get_name(), MPVPlayer.get_description())
        except:
            pass

        # 回退到FFplay
        try:
            if FFplayPlayer.is_available():
                return ('ffplay', FFplayPlayer.get_name(), FFplayPlayer.get_description())
        except:
            pass

        return None
    



# 全局播放器实例
# 注意：这个实例会在导入时创建，如果需要切换播放器，需要重新创建
_player_instance: Optional[PlayerBase] = None


def get_player() -> PlayerBase:
    """获取全局播放器实例
    
    Returns:
        PlayerBase: 播放器实例
    """
    global _player_instance
    
    if _player_instance is None:
        _player_instance = PlayerFactory.create_player()
    
    return _player_instance


def reset_player() -> PlayerBase:
    """重置播放器实例（用于切换播放器）
    
    Returns:
        PlayerBase: 新的播放器实例
    """
    global _player_instance
    
    # 停止并清理旧播放器
    if _player_instance is not None:
        try:
            _player_instance.stop()
        except:
            pass
        _player_instance = None
    
    # 创建新播放器
    _player_instance = PlayerFactory.create_player()
    return _player_instance


# 为了兼容性，创建一个 player 变量（延迟初始化）
player = None

