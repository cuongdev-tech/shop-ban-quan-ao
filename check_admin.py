"""Kiểm tra users dùng chung MySQL với app.py."""
import os
import pymysql

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
        try:
            cur.execute('SELECT id, name, email, is_admin, role FROM users')
            print(cur.fetchall())
        except Exception as e:
            print('error', e)
finally:
    con.close()
