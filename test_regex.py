import sqlite3
import re
from pathlib import Path

# 数据库路径
db_path = Path.home() / ".video_subtitle_app" / "app.db"

print(f"数据库路径: {db_path}")
print(f"数据库是否存在: {db_path.exists()}")
print()

if not db_path.exists():
    print("数据库文件不存在！请先运行应用并导入字幕。")
    exit(1)

# 连接数据库
conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

# 查询包含 "too" 的字幕
cursor.execute("""
    SELECT id, text, text_primary, text_secondary
    FROM subtitle_segments
    WHERE text LIKE '%too%' OR text_primary LIKE '%too%' OR text_secondary LIKE '%too%'
    LIMIT 5
""")

rows = cursor.fetchall()

print(f"找到 {len(rows)} 条包含 'too' 的字幕记录\n")
print("=" * 80)

for row in rows:
    seg_id, text, text_primary, text_secondary = row
    print(f"\nID: {seg_id}")
    print(f"text 字段: {repr(text)}")
    print(f"text_primary 字段: {repr(text_primary)}")
    print(f"text_secondary 字段: {repr(text_secondary)}")
    print()

    # 测试正则表达式
    print("正则测试:")

    # 测试 text 字段
    if text:
        print(f"  text 字段测试:")
        print(f"    'too$' (无标志): {bool(re.search('too$', text))}")
        print(f"    'too$' (MULTILINE): {bool(re.search('too$', text, re.MULTILINE))}")
        print(f"    'too$' (IGNORECASE|MULTILINE): {bool(re.search('too$', text, re.IGNORECASE | re.MULTILINE))}")

    # 测试 text_primary 字段
    if text_primary:
        print(f"  text_primary 字段测试:")
        print(f"    'too$' (无标志): {bool(re.search('too$', text_primary))}")
        print(f"    'too$' (MULTILINE): {bool(re.search('too$', text_primary, re.MULTILINE))}")
        print(f"    'too$' (IGNORECASE|MULTILINE): {bool(re.search('too$', text_primary, re.IGNORECASE | re.MULTILINE))}")

    print("-" * 80)

conn.close()
