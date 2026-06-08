import sqlite3
import os

db_path = 'inspection.db'
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(import_batches)")
    columns = [col[1] for col in cursor.fetchall()]

    needed_columns = ['is_revoked', 'revoked_at', 'revoked_by', 'revocation_reason']
    for col in needed_columns:
        if col not in columns:
            print(f'添加列: {col}')
            if col == 'is_revoked':
                cursor.execute('ALTER TABLE import_batches ADD COLUMN is_revoked INTEGER DEFAULT 0')
            elif col == 'revoked_at':
                cursor.execute('ALTER TABLE import_batches ADD COLUMN revoked_at DATETIME')
            elif col == 'revoked_by':
                cursor.execute('ALTER TABLE import_batches ADD COLUMN revoked_by VARCHAR(100)')
            elif col == 'revocation_reason':
                cursor.execute('ALTER TABLE import_batches ADD COLUMN revocation_reason VARCHAR(500)')

    cursor.execute("PRAGMA table_info(import_batches)")
    columns = [col[1] for col in cursor.fetchall()]
    print('当前列:', columns)

    conn.commit()
    conn.close()
    print('数据库迁移完成')
else:
    print('数据库不存在，将自动创建')
