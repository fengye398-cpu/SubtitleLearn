#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查数据库中所有项目的媒体类型（包含可能删除的项目）"""

import sys
import os

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(__file__))

from database.manager import db_manager
from utils.file_utils import FileUtils

def check_all_project_types():
    """检查所有项目的媒体类型"""
    print("=" * 80)
    print("Complete Project Type Check")
    print("=" * 80)

    # 获取所有项目
    projects = db_manager.get_all_projects()

    if not projects:
        print("No projects found in database")
        return

    print(f"Found {len(projects)} projects:\n")

    audio_projects = []
    video_projects = []
    unknown_projects = []

    for project in projects:
        # 提取文件扩展名
        file_path = project.video_path
        file_ext = os.path.splitext(file_path)[1].lower()

        # 判断文件类型
        is_audio = FileUtils.is_audio_file(file_path)
        is_video = FileUtils.is_video_file(file_path)

        # 分类项目
        if is_audio:
            media_type = "Audio"
            audio_projects.append(project)
        elif is_video:
            media_type = "Video"
            video_projects.append(project)
        else:
            media_type = "Unknown"
            unknown_projects.append(project)

        # 显示项目信息
        print(f"Project ID: {project.id}")
        print(f"  Name: {project.name}")
        print(f"  Media Path: {file_path}")
        print(f"  File Extension: {file_ext}")
        print(f"  File Type: {media_type}")
        print(f"  Display Label: [{media_type}] {project.name}")
        print()

    print("=" * 80)
    print("Statistics:")
    print(f"  Audio Projects: {len(audio_projects)}")
    print(f"  Video Projects: {len(video_projects)}")
    print(f"  Unknown Type: {len(unknown_projects)}")
    print(f"  Total Projects: {len(projects)}")
    print("=" * 80)

    # 显示音频项目详情
    if audio_projects:
        print("\nAudio Projects:")
        for project in audio_projects:
            file_ext = os.path.splitext(project.video_path)[1].lower()
            print(f"  ID {project.id}: {project.name} ({file_ext})")

    # 显示视频项目详情
    if video_projects:
        print(f"\nVideo Projects (showing first 5):")
        for project in video_projects[:5]:
            file_ext = os.path.splitext(project.video_path)[1].lower()
            print(f"  ID {project.id}: {project.name} ({file_ext})")
        if len(video_projects) > 5:
            print(f"  ... and {len(video_projects) - 5} more video projects")

    print("=" * 80)

if __name__ == "__main__":
    try:
        check_all_project_types()
    except Exception as e:
        print(f"Check failed: {e}")
        import traceback
        traceback.print_exc()
