#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查数据库中所有项目的媒体类型"""

import sys
import os

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(__file__))

from database.manager import db_manager
from utils.file_utils import FileUtils

def check_project_types():
    """检查所有项目的媒体类型"""
    print("=" * 80)
    print("项目媒体类型检查")
    print("=" * 80)

    # 获取所有项目
    projects = db_manager.get_all_projects()

    if not projects:
        print("数据库中没有项目")
        return

    print(f"找到 {len(projects)} 个项目:\n")

    audio_count = 0
    video_count = 0

    for project in projects:
        # 提取文件扩展名
        file_path = project.video_path
        file_ext = os.path.splitext(file_path)[1].lower()

        # 判断文件类型
        is_audio = FileUtils.is_audio_file(file_path)
        is_video = FileUtils.is_video_file(file_path)

        # 统计
        if is_audio:
            media_type = "音频"
            audio_count += 1
        elif is_video:
            media_type = "视频"
            video_count += 1
        else:
            media_type = "未知"

        # 显示项目信息
        print(f"项目ID: {project.id}")
        print(f"  项目名称: {project.name}")
        print(f"  媒体路径: {file_path}")
        print(f"  文件扩展名: {file_ext}")
        print(f"  文件类型: {media_type}")
        print(f"  显示标签: [{media_type}] {project.name}")
        print()

    print("=" * 80)
    print("统计结果:")
    print(f"  音频项目: {audio_count} 个")
    print(f"  视频项目: {video_count} 个")
    print(f"  未知类型: {len(projects) - audio_count - video_count} 个")
    print(f"  总项目数: {len(projects)} 个")
    print("=" * 80)

if __name__ == "__main__":
    try:
        check_project_types()
    except Exception as e:
        print(f"检查失败: {e}")
        import traceback
        traceback.print_exc()
