import os
import sqlite3

# 数据库路径
db_path = os.path.join('data', 'database.db')

print(f"Checking database: {db_path}")
print(f"Database exists: {os.path.exists(db_path)}")

if os.path.exists(db_path):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 查询所有项目
        cursor.execute('SELECT id, name, video_path FROM projects ORDER BY id')
        rows = cursor.fetchall()

        print(f"\nFound {len(rows)} projects:")
        for row in rows:
            file_ext = os.path.splitext(row[2])[1].lower()
            print(f"ID: {row[0]:2d}, Name: {row[1]:<30}, Extension: {file_ext}")

        conn.close()
    except Exception as e:
        print(f"Error querying database: {e}")
else:
    print("Database file not found")