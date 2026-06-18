import sqlite3
import json
import re
from datetime import datetime
from typing import List, Optional, Tuple
from pathlib import Path

from database.models import Project, SubtitleSegment, ExportRecord
from config.settings import app_config

class DatabaseManager:
    """数据库管理器"""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or str(app_config.db_file)
        self.init_database()

    @staticmethod
    def _regexp(pattern, text):
        """SQLite REGEXP 函数实现"""
        if text is None:
            return False
        try:
            return re.search(pattern, text, re.IGNORECASE) is not None
        except:
            return False
    
    def init_database(self):
        """初始化数据库表"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 创建项目表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    video_path TEXT NOT NULL,
                    subtitle_path TEXT NOT NULL,
                    cache_dir TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 创建字幕片段表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS subtitle_segments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    index_num INTEGER NOT NULL,
                    start_time REAL NOT NULL,
                    end_time REAL NOT NULL,
                    text TEXT NOT NULL,
                    text_primary TEXT,
                    text_secondary TEXT,
                    video_file TEXT,
                    audio_file TEXT,
                    subtitle_file TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
                )
            ''')

            # 检查并添加双语字幕字段（兼容旧数据库）
            try:
                cursor.execute("SELECT text_primary FROM subtitle_segments LIMIT 1")
            except sqlite3.OperationalError:
                # 字段不存在，添加字段
                cursor.execute("ALTER TABLE subtitle_segments ADD COLUMN text_primary TEXT")
                cursor.execute("ALTER TABLE subtitle_segments ADD COLUMN text_secondary TEXT")
                # 迁移现有数据
                cursor.execute("UPDATE subtitle_segments SET text_primary = text WHERE text_primary IS NULL")

            # 创建导出记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS export_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    segment_ids TEXT NOT NULL,
                    export_type TEXT NOT NULL,
                    output_path TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
                )
            ''')
            
            # 创建索引
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_segments_project_id ON subtitle_segments(project_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_segments_text ON subtitle_segments(text)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_segments_text_primary ON subtitle_segments(text_primary)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_segments_text_secondary ON subtitle_segments(text_secondary)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_export_project_id ON export_records(project_id)')

            conn.commit()
    
    def create_project(self, project: Project) -> int:
        """创建项目"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO projects (name, video_path, subtitle_path, cache_dir, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                project.name,
                project.video_path,
                project.subtitle_path,
                project.cache_dir,
                datetime.now(),
                datetime.now()
            ))
            return cursor.lastrowid
    
    def get_project(self, project_id: int) -> Optional[Project]:
        """获取项目"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM projects WHERE id = ?', (project_id,))
            row = cursor.fetchone()
            if row:
                return Project(
                    id=row[0],
                    name=row[1],
                    video_path=row[2],
                    subtitle_path=row[3],
                    cache_dir=row[4],
                    created_at=datetime.fromisoformat(row[5]) if row[5] else None,
                    updated_at=datetime.fromisoformat(row[6]) if row[6] else None
                )
            return None
    
    def get_all_projects(self) -> List[Project]:
        """获取所有项目"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM projects ORDER BY updated_at DESC')
            rows = cursor.fetchall()
            projects = []
            for row in rows:
                projects.append(Project(
                    id=row[0],
                    name=row[1],
                    video_path=row[2],
                    subtitle_path=row[3],
                    cache_dir=row[4],
                    created_at=datetime.fromisoformat(row[5]) if row[5] else None,
                    updated_at=datetime.fromisoformat(row[6]) if row[6] else None
                ))
            return projects

    def get_projects(self) -> List[Project]:
        """获取所有项目（别名方法）"""
        return self.get_all_projects()

    def find_project_by_paths(self, video_path: str, subtitle_path: str) -> Optional[Project]:
        """根据视频和字幕路径查找项目

        Args:
            video_path: 视频文件路径
            subtitle_path: 字幕文件路径

        Returns:
            如果找到返回Project对象，否则返回None
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM projects
                WHERE video_path = ? AND subtitle_path = ?
            ''', (video_path, subtitle_path))
            row = cursor.fetchone()
            if row:
                return Project(
                    id=row[0],
                    name=row[1],
                    video_path=row[2],
                    subtitle_path=row[3],
                    cache_dir=row[4],
                    created_at=datetime.fromisoformat(row[5]) if row[5] else None,
                    updated_at=datetime.fromisoformat(row[6]) if row[6] else None
                )
            return None

    def update_project(self, project: Project):
        """更新项目"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE projects 
                SET name = ?, video_path = ?, subtitle_path = ?, cache_dir = ?, updated_at = ?
                WHERE id = ?
            ''', (
                project.name,
                project.video_path,
                project.subtitle_path,
                project.cache_dir,
                datetime.now(),
                project.id
            ))
    
    def delete_project(self, project_id: int):
        """删除项目及其相关数据"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM projects WHERE id = ?', (project_id,))
    
    def create_segment(self, segment: SubtitleSegment) -> int:
        """创建字幕片段"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO subtitle_segments
                (project_id, index_num, start_time, end_time, text, text_primary, text_secondary,
                 video_file, audio_file, subtitle_file, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                segment.project_id,
                segment.index_num,
                segment.start_time,
                segment.end_time,
                segment.text,
                segment.text_primary,
                segment.text_secondary,
                segment.video_file,
                segment.audio_file,
                segment.subtitle_file,
                datetime.now()
            ))
            return cursor.lastrowid

    def get_segments_by_project(self, project_id: int, offset: int = 0, limit: int = 50) -> List[SubtitleSegment]:
        """获取项目的字幕片段（分页）"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT s.id, s.project_id, s.index_num, s.start_time, s.end_time, s.text,
                       s.text_primary, s.text_secondary, s.video_file, s.audio_file, s.subtitle_file, s.created_at,
                       p.name as project_name
                FROM subtitle_segments s
                LEFT JOIN projects p ON s.project_id = p.id
                WHERE s.project_id = ?
                ORDER BY s.index_num
                LIMIT ? OFFSET ?
            ''', (project_id, limit, offset))
            rows = cursor.fetchall()
            segments = []
            for row in rows:
                segment = SubtitleSegment(
                    id=row[0],
                    project_id=row[1],
                    index_num=row[2],
                    start_time=row[3],
                    end_time=row[4],
                    text=row[5],
                    text_primary=row[6] or row[5],  # 如果text_primary为空，使用text
                    text_secondary=row[7],
                    video_file=row[8],
                    audio_file=row[9],
                    subtitle_file=row[10],
                    created_at=datetime.fromisoformat(row[11]) if row[11] else None
                )
                # 添加项目名称属性
                segment.project_name = row[12] or f"项目{row[1]}"
                segments.append(segment)
            return segments

    def get_segment_count(self, project_id: int) -> int:
        """获取项目的字幕片段总数"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM subtitle_segments WHERE project_id = ?', (project_id,))
            return cursor.fetchone()[0]

    def get_all_segments(self, offset: int = 0, limit: int = 50) -> List[SubtitleSegment]:
        """获取所有项目的字幕片段（分页）"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT s.id, s.project_id, s.index_num, s.start_time, s.end_time, s.text,
                       s.text_primary, s.text_secondary, s.video_file, s.audio_file, s.subtitle_file, s.created_at,
                       p.name as project_name
                FROM subtitle_segments s
                LEFT JOIN projects p ON s.project_id = p.id
                ORDER BY s.project_id, s.index_num
                LIMIT ? OFFSET ?
            ''', (limit, offset))
            rows = cursor.fetchall()
            segments = []
            for row in rows:
                segment = SubtitleSegment(
                    id=row[0],
                    project_id=row[1],
                    index_num=row[2],
                    start_time=row[3],
                    end_time=row[4],
                    text=row[5],
                    text_primary=row[6] or row[5],
                    text_secondary=row[7],
                    video_file=row[8],
                    audio_file=row[9],
                    subtitle_file=row[10],
                    created_at=datetime.fromisoformat(row[11]) if row[11] else None
                )
                # 添加项目名称属性
                segment.project_name = row[12] or f"项目{row[1]}"
                segments.append(segment)
            return segments

    def get_total_segment_count(self) -> int:
        """获取所有片段总数"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM subtitle_segments')
            return cursor.fetchone()[0]

    def search_segments(self, project_id: Optional[int], keyword: str, mode: str = "fuzzy",
                       offset: int = 0, limit: int = 50, context_before: int = 0, context_after: int = 0) -> List[SubtitleSegment]:
        """搜索字幕片段

        Args:
            project_id: 项目ID，None表示搜索所有项目
            keyword: 搜索关键词
            mode: 搜索模式 (fuzzy/exact/regex)
            offset: 偏移量
            limit: 限制数量
            context_before: 匹配行之前的上下文行数
            context_after: 匹配行之后的上下文行数
        """
        with sqlite3.connect(self.db_path) as conn:
            # 注册 REGEXP 函数
            conn.create_function("REGEXP", 2, self._regexp)
            cursor = conn.cursor()

            # 如果没有上下文扩展，使用原有逻辑
            if context_before == 0 and context_after == 0:
                return self._search_segments_basic(cursor, project_id, keyword, mode, offset, limit)

            # 有上下文扩展，需要分步处理
            # 第1步：先找到所有匹配的字幕行
            matched_segments = self._search_segments_basic(cursor, project_id, keyword, mode, 0, 999999)

            if not matched_segments:
                return []

            # 第2步：为每个匹配行扩展上下文，并合并重叠范围
            expanded_ranges = self._expand_and_merge_context(
                cursor, matched_segments, context_before, context_after
            )

            # 第3步：根据扩展后的范围查询所有字幕
            result_segments = self._fetch_segments_by_ranges(cursor, expanded_ranges)

            # 第4步：应用分页
            start_idx = offset
            end_idx = offset + limit
            return result_segments[start_idx:end_idx]

    def _search_segments_basic(self, cursor, project_id: Optional[int], keyword: str,
                               mode: str, offset: int, limit: int) -> List[SubtitleSegment]:
        """基础搜索（不含上下文扩展）"""
        # 构建查询（包含项目名称）
        query = '''
            SELECT s.id, s.project_id, s.index_num, s.start_time, s.end_time, s.text,
                   s.text_primary, s.text_secondary, s.video_file, s.audio_file, s.subtitle_file, s.created_at,
                   p.name as project_name
            FROM subtitle_segments s
            LEFT JOIN projects p ON s.project_id = p.id
            WHERE 1=1
        '''
        params = []

        # 项目过滤
        if project_id is not None:
            query += ' AND s.project_id = ?'
            params.append(project_id)

        # 搜索模式（搜索原文和译文）
        if mode == "exact":
            # 精确匹配（单词边界）
            keyword_pattern = f'\\b{re.escape(keyword)}\\b'
            query += ' AND (s.text REGEXP ? OR s.text_primary REGEXP ? OR s.text_secondary REGEXP ?)'
            params.extend([keyword_pattern, keyword_pattern, keyword_pattern])
        elif mode == "regex":
            # 正则匹配（用户自定义）
            query += ' AND (s.text REGEXP ? OR s.text_primary REGEXP ? OR s.text_secondary REGEXP ?)'
            params.extend([keyword, keyword, keyword])
        else:
            # 模糊匹配（默认）
            query += ' AND (s.text LIKE ? OR s.text_primary LIKE ? OR s.text_secondary LIKE ?)'
            keyword_pattern = f'%{keyword}%'
            params.extend([keyword_pattern, keyword_pattern, keyword_pattern])

        query += ' ORDER BY s.project_id, s.index_num LIMIT ? OFFSET ?'
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()
        segments = []
        for row in rows:
            segment = SubtitleSegment(
                id=row[0],
                project_id=row[1],
                index_num=row[2],
                start_time=row[3],
                end_time=row[4],
                text=row[5],
                text_primary=row[6] or row[5],
                text_secondary=row[7],
                video_file=row[8],
                audio_file=row[9],
                subtitle_file=row[10],
                created_at=datetime.fromisoformat(row[11]) if row[11] else None
            )
            # 添加项目名称属性
            segment.project_name = row[12] or f"项目{row[1]}"
            segments.append(segment)
        return segments

    def _expand_and_merge_context(self, cursor, matched_segments: List[SubtitleSegment],
                                  context_before: int, context_after: int) -> List[Tuple[int, int, int]]:
        """扩展上下文并合并重叠范围

        Returns:
            List of (project_id, start_index, end_index) tuples
        """
        # 按项目分组
        project_groups = {}
        for seg in matched_segments:
            if seg.project_id not in project_groups:
                project_groups[seg.project_id] = []
            project_groups[seg.project_id].append(seg.index_num)

        # 为每个项目扩展和合并范围
        merged_ranges = []
        for project_id, indices in project_groups.items():
            # 获取该项目的字幕总数（用于边界检查）
            cursor.execute(
                'SELECT MIN(index_num), MAX(index_num) FROM subtitle_segments WHERE project_id = ?',
                (project_id,)
            )
            min_idx, max_idx = cursor.fetchone()

            # 扩展每个匹配行的范围
            ranges = []
            for idx in indices:
                start = max(min_idx, idx - context_before)
                end = min(max_idx, idx + context_after)
                ranges.append((start, end))

            # 合并重叠范围
            ranges.sort()
            merged = []
            for start, end in ranges:
                if merged and start <= merged[-1][1] + 1:
                    # 重叠或相邻，合并
                    merged[-1] = (merged[-1][0], max(merged[-1][1], end))
                else:
                    # 不重叠，添加新范围
                    merged.append((start, end))

            # 添加到结果（包含 project_id）
            for start, end in merged:
                merged_ranges.append((project_id, start, end))

        return merged_ranges

    def _fetch_segments_by_ranges(self, cursor, ranges: List[Tuple[int, int, int]]) -> List[SubtitleSegment]:
        """根据范围查询字幕片段"""
        all_segments = []

        for project_id, start_idx, end_idx in ranges:
            query = '''
                SELECT s.id, s.project_id, s.index_num, s.start_time, s.end_time, s.text,
                       s.text_primary, s.text_secondary, s.video_file, s.audio_file, s.subtitle_file, s.created_at,
                       p.name as project_name
                FROM subtitle_segments s
                LEFT JOIN projects p ON s.project_id = p.id
                WHERE s.project_id = ? AND s.index_num >= ? AND s.index_num <= ?
                ORDER BY s.index_num
            '''
            cursor.execute(query, (project_id, start_idx, end_idx))
            rows = cursor.fetchall()

            for row in rows:
                segment = SubtitleSegment(
                    id=row[0],
                    project_id=row[1],
                    index_num=row[2],
                    start_time=row[3],
                    end_time=row[4],
                    text=row[5],
                    text_primary=row[6] or row[5],
                    text_secondary=row[7],
                    video_file=row[8],
                    audio_file=row[9],
                    subtitle_file=row[10],
                    created_at=datetime.fromisoformat(row[11]) if row[11] else None
                )
                segment.project_name = row[12] or f"项目{row[1]}"
                all_segments.append(segment)

        return all_segments

    def get_search_count(self, project_id: Optional[int], keyword: str, mode: str = "fuzzy",
                        context_before: int = 0, context_after: int = 0) -> int:
        """获取搜索结果总数

        Args:
            project_id: 项目ID
            keyword: 搜索关键词
            mode: 搜索模式
            context_before: 上文行数
            context_after: 下文行数

        Returns:
            结果总数（包含上下文扩展后的总行数）
        """
        with sqlite3.connect(self.db_path) as conn:
            # 注册 REGEXP 函数
            conn.create_function("REGEXP", 2, self._regexp)
            cursor = conn.cursor()

            # 如果没有上下文扩展，使用原有计数逻辑
            if context_before == 0 and context_after == 0:
                return self._get_search_count_basic(cursor, project_id, keyword, mode)

            # 有上下文扩展，需要计算扩展后的总数
            # 先获取所有匹配的字幕
            matched_segments = self._search_segments_basic(cursor, project_id, keyword, mode, 0, 999999)

            if not matched_segments:
                return 0

            # 扩展并合并范围
            expanded_ranges = self._expand_and_merge_context(
                cursor, matched_segments, context_before, context_after
            )

            # 计算扩展后的总行数
            total_count = 0
            for project_id, start_idx, end_idx in expanded_ranges:
                total_count += (end_idx - start_idx + 1)

            return total_count

    def _get_search_count_basic(self, cursor, project_id: Optional[int], keyword: str, mode: str) -> int:
        """基础计数（不含上下文扩展）"""
        query = 'SELECT COUNT(*) FROM subtitle_segments WHERE 1=1'
        params = []

        # 项目过滤
        if project_id is not None:
            query += ' AND project_id = ?'
            params.append(project_id)

        # 搜索模式（搜索原文和译文）
        if mode == "exact":
            # 精确匹配（单词边界）
            keyword_pattern = f'\\b{re.escape(keyword)}\\b'
            query += ' AND (text REGEXP ? OR text_primary REGEXP ? OR text_secondary REGEXP ?)'
            params.extend([keyword_pattern, keyword_pattern, keyword_pattern])
        elif mode == "regex":
            # 正则匹配（用户自定义）
            query += ' AND (text REGEXP ? OR text_primary REGEXP ? OR text_secondary REGEXP ?)'
            params.extend([keyword, keyword, keyword])
        else:
            # 模糊匹配（默认）
            keyword_pattern = f'%{keyword}%'
            query += ' AND (text LIKE ? OR text_primary LIKE ? OR text_secondary LIKE ?)'
            params.extend([keyword_pattern, keyword_pattern, keyword_pattern])

        cursor.execute(query, params)
        return cursor.fetchone()[0]

    def get_segments_in_time_range(self, project_id: Optional[int], start_time: float, end_time: float) -> List[SubtitleSegment]:
        """查询指定时间区间内的所有字幕片段

        Args:
            project_id: 项目ID，None表示查询所有项目
            start_time: 开始时间（秒）
            end_time: 结束时间（秒）

        Returns:
            该时间区间内的所有字幕片段列表
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # 构建查询（包含项目名称）
            query = '''
                SELECT s.id, s.project_id, s.index_num, s.start_time, s.end_time, s.text,
                       s.text_primary, s.text_secondary, s.video_file, s.audio_file, s.subtitle_file, s.created_at,
                       p.name as project_name
                FROM subtitle_segments s
                LEFT JOIN projects p ON s.project_id = p.id
                WHERE s.start_time >= ? AND s.end_time <= ?
            '''
            params = [start_time, end_time]

            # 项目过滤
            if project_id is not None:
                query += ' AND s.project_id = ?'
                params.append(project_id)

            query += ' ORDER BY s.project_id, s.index_num'

            cursor.execute(query, params)
            rows = cursor.fetchall()
            segments = []
            for row in rows:
                segment = SubtitleSegment(
                    id=row[0],
                    project_id=row[1],
                    index_num=row[2],
                    start_time=row[3],
                    end_time=row[4],
                    text=row[5],
                    text_primary=row[6] or row[5],
                    text_secondary=row[7],
                    video_file=row[8],
                    audio_file=row[9],
                    subtitle_file=row[10],
                    created_at=datetime.fromisoformat(row[11]) if row[11] else None
                )
                # 添加项目名称属性
                segment.project_name = row[12] or f"项目{row[1]}"
                segments.append(segment)
            return segments

    def delete_segments_by_project(self, project_id: int):
        """删除项目的所有字幕片段"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM subtitle_segments WHERE project_id = ?', (project_id,))

    def delete_segment(self, segment_id: int):
        """删除单个字幕片段"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM subtitle_segments WHERE id = ?', (segment_id,))

    def get_segments_by_ids(self, segment_ids: List[int]) -> List[SubtitleSegment]:
        """根据ID列表获取字幕片段"""
        if not segment_ids:
            return []

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(segment_ids))
            cursor.execute(f'''
                SELECT s.id, s.project_id, s.index_num, s.start_time, s.end_time, s.text,
                       s.text_primary, s.text_secondary, s.video_file, s.audio_file, s.subtitle_file, s.created_at,
                       p.name as project_name
                FROM subtitle_segments s
                LEFT JOIN projects p ON s.project_id = p.id
                WHERE s.id IN ({placeholders})
                ORDER BY s.index_num
            ''', segment_ids)
            rows = cursor.fetchall()
            segments = []
            for row in rows:
                segment = SubtitleSegment(
                    id=row[0],
                    project_id=row[1],
                    index_num=row[2],
                    start_time=row[3],
                    end_time=row[4],
                    text=row[5],
                    text_primary=row[6] or row[5],
                    text_secondary=row[7],
                    video_file=row[8],
                    audio_file=row[9],
                    subtitle_file=row[10],
                    created_at=datetime.fromisoformat(row[11]) if row[11] else None
                )
                # 添加项目名称属性
                segment.project_name = row[12] or f"项目{row[1]}"
                segments.append(segment)
            return segments

    def update_segment(self, segment: SubtitleSegment) -> bool:
        """更新字幕片段"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE subtitle_segments
                    SET text = ?, text_primary = ?, text_secondary = ?
                    WHERE id = ?
                ''', (
                    segment.text,
                    segment.text_primary,
                    segment.text_secondary,
                    segment.id
                ))
                return cursor.rowcount > 0
        except Exception as e:
            print(f"更新字幕片段失败: {e}")
            return False

    def update_segment_files(self, segment_id: int, video_file: str = None, audio_file: str = None, subtitle_file: str = None):
        """更新片段文件路径"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            updates = []
            params = []

            if video_file is not None:
                updates.append('video_file = ?')
                params.append(video_file)
            if audio_file is not None:
                updates.append('audio_file = ?')
                params.append(audio_file)
            if subtitle_file is not None:
                updates.append('subtitle_file = ?')
                params.append(subtitle_file)

            if updates:
                params.append(segment_id)
                cursor.execute(f'''
                    UPDATE subtitle_segments
                    SET {', '.join(updates)}
                    WHERE id = ?
                ''', params)

    def create_export_record(self, record: ExportRecord) -> int:
        """创建导出记录"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO export_records (project_id, segment_ids, export_type, output_path, created_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                record.project_id,
                record.segment_ids_json,
                record.export_type,
                record.output_path,
                datetime.now()
            ))
            return cursor.lastrowid

    def get_export_records(self, project_id: int) -> List[ExportRecord]:
        """获取导出记录"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM export_records
                WHERE project_id = ?
                ORDER BY created_at DESC
            ''', (project_id,))
            rows = cursor.fetchall()
            records = []
            for row in rows:
                record = ExportRecord(
                    id=row[0],
                    project_id=row[1],
                    export_type=row[3],
                    output_path=row[4],
                    created_at=datetime.fromisoformat(row[5]) if row[5] else None
                )
                record.segment_ids_json = row[2]
                records.append(record)
            return records

    def clear_all_data(self):
        """清空所有数据、重置ID序列并压缩数据库"""
        # [SEARCH] 获取清空前的数据库大小和统计信息
        db_size_before = Path(self.db_path).stat().st_size if Path(self.db_path).exists() else 0

        # 获取清空前的数据统计
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute('SELECT COUNT(*) FROM projects')
            projects_before = cursor.fetchone()[0]
            cursor.execute('SELECT COUNT(*) FROM subtitle_segments')
            segments_before = cursor.fetchone()[0]
            cursor.execute('SELECT COUNT(*) FROM export_records')
            exports_before = cursor.fetchone()[0]

            print(f"🗃️  清空前数据库状态:")
            print(f"   项目数量: {projects_before}")
            print(f"   片段数量: {segments_before}")
            print(f"   导出记录: {exports_before}")
            print(f"   数据库大小: {self._format_size(db_size_before)}")

            # 删除所有数据
            cursor.execute('DELETE FROM export_records')
            cursor.execute('DELETE FROM subtitle_segments')
            cursor.execute('DELETE FROM projects')

            # 重置自增ID序列，防止ID持续增长
            cursor.execute('DELETE FROM sqlite_sequence WHERE name="projects"')
            cursor.execute('DELETE FROM sqlite_sequence WHERE name="subtitle_segments"')
            cursor.execute('DELETE FROM sqlite_sequence WHERE name="export_records"')

            conn.commit()

        # [TOOL] 修复：VACUUM必须在事务外执行
        print("[REFRESH] 正在压缩数据库...")
        try:
            # 创建新的连接来执行VACUUM，不使用事务
            vacuum_conn = sqlite3.connect(self.db_path)
            vacuum_conn.execute('VACUUM')
            vacuum_conn.close()
            print("[OK] 数据库压缩成功")
        except Exception as e:
            print(f"[WARN]  数据库压缩失败: {e}")
            # 压缩失败不影响数据清空的成功

        # [SEARCH] 获取清空后的数据库大小
        db_size_after = Path(self.db_path).stat().st_size if Path(self.db_path).exists() else 0
        size_reduced = db_size_before - db_size_after

        print(f"[OK] 数据库清空完成:")
        print(f"   清空前大小: {self._format_size(db_size_before)}")
        print(f"   清空后大小: {self._format_size(db_size_after)}")
        print(f"   空间回收: {self._format_size(size_reduced)}")
        print(f"   压缩率: {(size_reduced/db_size_before*100):.1f}%" if db_size_before > 0 else "")

    def _format_size(self, size_bytes: int) -> str:
        """格式化文件大小显示"""
        if size_bytes == 0:
            return "0 B"

        # [TARGET] 优化：检查是否为空数据库（基于实际数据而非文件大小）
        try:
            # 检查是否有实际数据
            stats = self.get_database_stats()
            total_records = stats['projects'] + stats['segments'] + stats['exports']

            # 如果没有数据记录且文件大小小于100KB，显示为已清空
            if total_records == 0 and size_bytes <= 100000:
                return "已清空 (仅保留结构)"
        except:
            # 如果获取统计失败，回退到文件大小判断
            if size_bytes <= 50000:
                return "已清空 (仅保留结构)"

        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1

        return f"{size_bytes:.1f} {size_names[i]}"

    def delete_project_completely(self, project_id: int) -> bool:
        """完全删除单个项目及其所有相关数据（包括缓存文件）"""
        try:
            # 首先获取项目信息，用于删除缓存
            project = None
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM projects WHERE id = ?', (project_id,))
                row = cursor.fetchone()
                if row:
                    project = Project(
                        id=row[0],
                        name=row[1],
                        video_path=row[2],
                        subtitle_path=row[3],
                        cache_dir=row[4],
                        created_at=datetime.fromisoformat(row[5]) if row[5] else None
                    )

            if not project:
                print(f"项目 {project_id} 不存在")
                return False

            # 删除数据库记录
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # 删除导出记录
                cursor.execute('DELETE FROM export_records WHERE project_id = ?', (project_id,))

                # 删除字幕片段
                cursor.execute('DELETE FROM subtitle_segments WHERE project_id = ?', (project_id,))

                # 删除项目
                cursor.execute('DELETE FROM projects WHERE id = ?', (project_id,))

                conn.commit()

            # 删除项目缓存目录
            if project.cache_dir and Path(project.cache_dir).exists():
                import shutil
                try:
                    shutil.rmtree(project.cache_dir)
                    print(f"已删除项目缓存目录: {project.cache_dir}")
                except Exception as e:
                    print(f"删除缓存目录失败: {e}")
                    # 缓存删除失败不影响数据库删除的成功

            return True

        except Exception as e:
            print(f"删除项目失败：{e}")
            return False

    def update_segment_times(self, segment_id: int, start_time: float, end_time: float) -> bool:
        """更新字幕片段的时间轴

        Args:
            segment_id: 片段ID
            start_time: 新的开始时间
            end_time: 新的结束时间

        Returns:
            更新成功返回True，失败返回False
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE subtitle_segments
                    SET start_time = ?, end_time = ?
                    WHERE id = ?
                ''', (start_time, end_time, segment_id))
                return cursor.rowcount > 0
        except Exception as e:
            print(f"更新片段时间轴失败: {e}")
            return False

    def get_database_stats(self) -> dict:
        """获取数据库统计信息"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # 项目数量
            cursor.execute('SELECT COUNT(*) FROM projects')
            project_count = cursor.fetchone()[0]

            # 片段数量
            cursor.execute('SELECT COUNT(*) FROM subtitle_segments')
            segment_count = cursor.fetchone()[0]

            # 导出记录数量
            cursor.execute('SELECT COUNT(*) FROM export_records')
            export_count = cursor.fetchone()[0]

            # 数据库文件大小
            db_size = Path(self.db_path).stat().st_size if Path(self.db_path).exists() else 0

            return {
                'project_count': project_count,
                'segment_count': segment_count,
                'export_count': export_count,
                'db_size': db_size
            }

# 全局数据库管理器实例
db_manager = DatabaseManager()
