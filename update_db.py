import sqlite3

# 连接到SQLite数据库
conn = sqlite3.connect('chat.db')
cursor = conn.cursor()

# 检查user表是否有avatar列
try:
    # 尝试查询avatar列
    cursor.execute("SELECT avatar FROM user LIMIT 1")
    print("Avatar列已存在")
except sqlite3.OperationalError:
    # 如果列不存在，添加它
    print("添加avatar列到user表...")
    cursor.execute("ALTER TABLE user ADD COLUMN avatar TEXT DEFAULT ''")
    conn.commit()
    print("Avatar列添加成功")

# 检查其他可能需要的列
try:
    # 检查last_login列
    cursor.execute("SELECT last_login FROM user LIMIT 1")
except sqlite3.OperationalError:
    print("添加last_login列到user表...")
    cursor.execute("ALTER TABLE user ADD COLUMN last_login TEXT")
    conn.commit()

# 关闭连接
conn.close()
print("数据库更新完成")