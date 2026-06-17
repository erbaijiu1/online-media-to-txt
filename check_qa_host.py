import pymysql
import json
import sys

try:
    conn = pymysql.connect(
        host='127.0.0.1', 
        port=3306, 
        user='root', 
        password='Gmcc@123', 
        database='xiaoe_db', 
        cursorclass=pymysql.cursors.DictCursor
    )
    with conn.cursor() as cursor:
        cursor.execute("SELECT raw_json FROM posts WHERE raw_json LIKE '%问答%' LIMIT 1")
        row = cursor.fetchone()
        if row:
            raw_data = json.loads(row['raw_json'])
            print(json.dumps(raw_data, indent=2, ensure_ascii=False))
        else:
            print("No QA posts found.")
except Exception as e:
    print(f"Error: {e}")
