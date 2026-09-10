"""Script tạo admin dùng chung MySQL với app.py (đã bỏ sqlite store.db cũ)."""
import os
import pymysql
from werkzeug.security import generate_password_hash

MYSQL_HOST = os.environ.get('MYSQL_HOST', '127.0.0.1')
MYSQL_PORT = int(os.environ.get('MYSQL_PORT', 3306))
MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
MYSQL_DB = os.environ.get('MYSQL_DB', 'fashion_shop')

con = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER,
                      password=MYSQL_PASSWORD, database=MYSQL_DB,
                      cursorclass=pymysql.cursors.DictCursor, autocommit=True)
try:
    with con.cursor() as cur:
        cur.execute('SELECT id FROM users WHERE email = %s', ('admin@shop.com',))
        if cur.fetchone():
            print('admin already exists')
        else:
            pw = generate_password_hash('admin123')
            cur.execute('INSERT INTO users (name, email, password, is_admin, role) VALUES (%s, %s, %s, %s, %s)',
                        ('Admin Shop', 'admin@shop.com', pw, 1, 'Admin'))
            print('admin created')
finally:
    con.close()
