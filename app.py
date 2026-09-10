import os
import io
import re
import pandas as pd
import pymysql
import math
from flask import Flask, render_template, request, redirect, url_for, session, flash, g, send_file
from flask_bcrypt import Bcrypt
from flask_wtf import FlaskForm
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from wtforms import StringField, PasswordField, SubmitField, TextAreaField, IntegerField, SelectField, DecimalField, BooleanField
from wtforms.validators import DataRequired, Length, Email, EqualTo, NumberRange, Optional
from datetime import date, datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a56858190e95526c81b9c7afabfa296b17401ef19a6e5923b7985a808d610c3e')
# Bật CSRF cho FlaskForm (form tay vẫn cần thêm token thủ công ở template nếu muốn)
app.config['WTF_CSRF_TIME_LIMIT'] = 3600

MYSQL_HOST = os.environ.get('MYSQL_HOST', '127.0.0.1')
MYSQL_PORT = int(os.environ.get('MYSQL_PORT', 3306))
MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
MYSQL_DB = os.environ.get('MYSQL_DB', 'fashion_shop')

ALLOWED_STATUSES = ['Chờ thanh toán', 'Chờ xác nhận', 'Đang giao', 'Hoàn thành', 'Đã hủy']
ALLOWED_PAYMENTS = ['COD', 'Chuyển khoản', 'Tiền mặt', 'ATM', 'Visa', 'Ví điện tử']
# Chuẩn hóa: 'Tiền mặt' (đơn cũ) tương đương COD khi xử lý
PAYMENT_ALIASES = {'Tiền mặt': 'COD'}

# Phase 1 — Biến thể quần áo: danh sách cố định, mở rộng bằng cách thêm 1 dòng ở đây
SIZES = ['S', 'M', 'L', 'XL', 'XXL', '28', '29', '30', '31', '32', 'Free-size']
COLORS = ['Mặc định', 'Đen', 'Trắng', 'Be', 'Xanh', 'Đỏ', 'Hồng', 'Vàng', 'Xám', 'Nâu']
DEFAULT_SIZE = 'M'
DEFAULT_COLOR = 'Mặc định'

# Phase 3 — Điểm thưởng: tích 1% đơn Hoàn thành, 1 điểm = 1000đ
POINTS_PER_VND = 100000
VND_PER_POINT = 1000

# Build Shop (chốt): freeship 500k / min order 0đ / đồng giá size / 1 đơn 1 quà / chỉ đổi size
FREESHIP_THRESHOLD_DEFAULT = 500000
MIN_ORDER_DEFAULT = 0
GIFT_MIN_DEFAULT = 500000
# Menu 2 tầng: mỗi nhóm cha là link thật (bấm luôn ra hàng), con trỏ category + từ khóa KHỚP TÊN HÀNG THẬT.
# Quy ước: con nào chưa có hàng khớp từ khóa thì để search='' (hiện cả nhóm cha) để không bao giờ ra trang trống.
CATEGORY_TREE = [
    {'label': 'Áo nam', 'category': 'Áo', 'search': '', 'children': [
        {'label': 'Thun', 'category': 'Áo', 'search': ''},
        {'label': 'Polo', 'category': 'Áo', 'search': 'polo'},
        {'label': 'Sơ mi', 'category': 'Áo', 'search': 'sơ mi'},
        {'label': 'Khoác', 'category': 'Áo khoác', 'search': ''},
    ]},
    {'label': 'Quần nam', 'category': 'Quần', 'search': '', 'children': [
        {'label': 'Tây', 'category': 'Quần', 'search': 'tây'},
        {'label': 'Kaki', 'category': 'Quần', 'search': ''},
        {'label': 'Jeans', 'category': 'Quần', 'search': 'jean'},
        {'label': 'Short', 'category': 'Quần', 'search': 'short'},
    ]},
    {'label': 'Áo nữ', 'category': 'Áo', 'search': 'nữ', 'children': [
        {'label': 'Thun', 'category': 'Áo', 'search': 'nữ'},
        {'label': 'Sơ mi', 'category': 'Áo', 'search': 'sơ mi'},
        {'label': 'Khoác', 'category': 'Áo khoác', 'search': 'nữ'},
    ]},
    {'label': 'Quần nữ', 'category': 'Quần', 'search': 'nữ', 'children': [
        {'label': 'Jeans', 'category': 'Quần', 'search': 'jean'},
        {'label': 'Short', 'category': 'Quần', 'search': 'short'},
    ]},
    {'label': 'Váy', 'category': 'Váy', 'search': '', 'children': [
        {'label': 'Hoa', 'category': 'Váy', 'search': 'hoa'},
        {'label': 'Đầm', 'category': 'Váy', 'search': 'đầm'},
    ]},
]
HOT_KEYWORDS = ['áo thun', 'polo', 'sơ mi', 'jeans', 'short', 'váy hoa', 'khoác', 'bigsize']
STATIC_PAGES = [
    ('gioi-thieu', 'Giới thiệu'), ('lien-he', 'Liên hệ'), ('thanh-toan', 'Thanh toán'),
    ('giao-hang', 'Giao hàng'), ('doi-hang', 'Đổi hàng'), ('tra-hang', 'Trả hàng'),
    ('bao-mat', 'Bảo mật'), ('mua-hang', 'Mua hàng'),
]
# Nhom full: thanh toan / van chuyen / combo / bao cao
SHIP_CARRIERS = [
    ('GHN', 'GHN', 0),
    ('GHTK', 'GHTK', 5000),
    ('ViettelPost', 'Viettel Post', 10000),
    ('TuGiao', 'Tự giao nội thành', 0),
]
SHIP_CARRIER_FEE = {code: fee for code, _, fee in SHIP_CARRIERS}
COMBO_TYPES = [('BUY_GET', 'Mua X tặng Y'), ('BUNDLE', 'Set bộ giá gói')]
REVIEW_STATUSES = ['Cho_duyet', 'Hien', 'An']


def get_setting(key, default=''):
    try:
        row = query_db('SELECT `value` FROM settings WHERE `key` = %s', [key], one=True)
        if row and row.get('value') not in (None, ''):
            return row.get('value')
    except Exception:
        pass
    return default


def get_int_setting(key, default=0):
    try:
        return int(float(str(get_setting(key, default))))
    except (ValueError, TypeError):
        return default


def set_setting(key, value):
    try:
        execute_db('INSERT INTO settings (`key`, `value`) VALUES (%s, %s) ON DUPLICATE KEY UPDATE `value` = VALUES(`value`)',
                   (key, str(value)))
    except Exception:
        pass


def ensure_extended_tables():
    """Tự tạo bảng/cột mới nếu chưa chạy migration SQL (an toàn chạy nhiều lần, không đụng data cũ)."""
    try:
        execute_db('''CREATE TABLE IF NOT EXISTS settings (`key` VARCHAR(50) NOT NULL PRIMARY KEY, `value` TEXT NULL)
                      ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''')
        execute_db('''CREATE TABLE IF NOT EXISTS pages (slug VARCHAR(50) NOT NULL PRIMARY KEY, title VARCHAR(255) NOT NULL,
                      content TEXT NOT NULL, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP)
                      ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''')
        execute_db('''CREATE TABLE IF NOT EXISTS stores (id INT AUTO_INCREMENT PRIMARY KEY, province VARCHAR(100) NOT NULL,
                      branch_name VARCHAR(255) NOT NULL, address VARCHAR(500) NOT NULL,
                      open_hours VARCHAR(255) NOT NULL DEFAULT '8:00 - 22:00', map_url VARCHAR(1000) NULL,
                      is_active TINYINT(1) NOT NULL DEFAULT 1, KEY idx_store_province (province))
                      ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''')
        execute_db('''CREATE TABLE IF NOT EXISTS gifts (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(255) NOT NULL,
                      stock INT NOT NULL DEFAULT 0, image VARCHAR(500) NULL,
                      min_order_amount DECIMAL(12,2) NOT NULL DEFAULT 500000,
                      is_active TINYINT(1) NOT NULL DEFAULT 1, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)
                      ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''')
        execute_db('''CREATE TABLE IF NOT EXISTS order_gifts (order_id INT NOT NULL PRIMARY KEY, gift_id INT NOT NULL,
                      qty INT NOT NULL DEFAULT 1, FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE)
                      ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''')
        execute_db('''CREATE TABLE IF NOT EXISTS subscribers (id INT AUTO_INCREMENT PRIMARY KEY,
                      email VARCHAR(255) NOT NULL UNIQUE, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)
                      ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''')
        execute_db('''CREATE TABLE IF NOT EXISTS contacts (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(100) NOT NULL,
                      phone VARCHAR(20) NOT NULL, message TEXT NOT NULL, reply TEXT NULL,
                      status VARCHAR(20) NOT NULL DEFAULT 'Moi', created_at DATETIME DEFAULT CURRENT_TIMESTAMP)
                      ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''')
        cols = query_db("SHOW COLUMNS FROM products LIKE 'has_gift'")
        if not cols:
            execute_db('ALTER TABLE products ADD COLUMN has_gift TINYINT(1) NOT NULL DEFAULT 0')
        execute_db('''CREATE TABLE IF NOT EXISTS product_images (id INT AUTO_INCREMENT PRIMARY KEY, product_id INT NOT NULL,
                      image_url VARCHAR(1000) NOT NULL, sort_order INT NOT NULL DEFAULT 0, KEY idx_pi_product (product_id),
                      FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''')
        execute_db('''CREATE TABLE IF NOT EXISTS product_faqs (id INT AUTO_INCREMENT PRIMARY KEY, product_id INT NOT NULL,
                      question VARCHAR(500) NOT NULL, answer TEXT NOT NULL, sort_order INT NOT NULL DEFAULT 0,
                      KEY idx_pf_product (product_id),
                      FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''')
        execute_db('''CREATE TABLE IF NOT EXISTS collections (id INT AUTO_INCREMENT PRIMARY KEY, slug VARCHAR(100) NOT NULL UNIQUE,
                      title VARCHAR(255) NOT NULL, description TEXT NULL, image VARCHAR(1000) NULL, season VARCHAR(50) NULL,
                      is_active TINYINT(1) NOT NULL DEFAULT 1, created_at DATETIME DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''')
        execute_db('''CREATE TABLE IF NOT EXISTS collection_products (collection_id INT NOT NULL, product_id INT NOT NULL,
                      PRIMARY KEY (collection_id, product_id),
                      FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE,
                      FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''')
        execute_db('''CREATE TABLE IF NOT EXISTS posts (id INT AUTO_INCREMENT PRIMARY KEY, slug VARCHAR(100) NOT NULL UNIQUE,
                      title VARCHAR(255) NOT NULL, content TEXT NOT NULL, image VARCHAR(1000) NULL, collection_id INT NULL,
                      is_active TINYINT(1) NOT NULL DEFAULT 1, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                      KEY idx_post_coll (collection_id),
                      FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE SET NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''')
        execute_db('''CREATE TABLE IF NOT EXISTS post_products (post_id INT NOT NULL, product_id INT NOT NULL,
                      PRIMARY KEY (post_id, product_id),
                      FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
                      FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''')
        execute_db('''CREATE TABLE IF NOT EXISTS jobs (id INT AUTO_INCREMENT PRIMARY KEY, title VARCHAR(255) NOT NULL,
                      location VARCHAR(255) NULL, salary VARCHAR(255) NULL, description TEXT NOT NULL,
                      is_active TINYINT(1) NOT NULL DEFAULT 1, created_at DATETIME DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''')
        execute_db('''CREATE TABLE IF NOT EXISTS applications (id INT AUTO_INCREMENT PRIMARY KEY, job_id INT NOT NULL,
                      name VARCHAR(100) NOT NULL, phone VARCHAR(20) NOT NULL, email VARCHAR(255) NULL, cv_text TEXT NOT NULL,
                      status VARCHAR(20) NOT NULL DEFAULT 'Moi', created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                      KEY idx_app_job (job_id),
                      FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4''')
        for _col, _ddl in [('brand', "ALTER TABLE products ADD COLUMN brand VARCHAR(100) NULL DEFAULT 'FashionShop'"),
                           ('video_url', 'ALTER TABLE products ADD COLUMN video_url VARCHAR(1000) NULL'),
                           ('material', 'ALTER TABLE products ADD COLUMN material VARCHAR(500) NULL'),
                           ('fit', 'ALTER TABLE products ADD COLUMN fit VARCHAR(255) NULL'),
                           ('size_note', 'ALTER TABLE products ADD COLUMN size_note VARCHAR(500) NULL')]:
            try:
                _has = query_db("SHOW COLUMNS FROM products LIKE %s", [_col])
                if not _has:
                    execute_db(_ddl)
            except Exception:
                pass
        # Nhom full: banner/combo/review-moderation/notify/stafflog + cot orders/order_items/reviews/users
        for _tbl, _ddl in [
            ('banners', '''CREATE TABLE IF NOT EXISTS banners (id INT AUTO_INCREMENT PRIMARY KEY, title VARCHAR(255) NULL,
                          image VARCHAR(1000) NOT NULL, link VARCHAR(1000) NULL, sort_order INT NOT NULL DEFAULT 0,
                          is_active TINYINT(1) NOT NULL DEFAULT 1, created_at DATETIME DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'''),
            ('combos', '''CREATE TABLE IF NOT EXISTS combos (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(255) NOT NULL,
                         combo_type VARCHAR(20) NOT NULL DEFAULT 'BUY_GET', trigger_product_id INT NULL, trigger_qty INT NOT NULL DEFAULT 1,
                         gift_product_id INT NULL, gift_qty INT NOT NULL DEFAULT 1, bundle_product_ids VARCHAR(500) NULL,
                         bundle_price DECIMAL(12,2) NULL, start_at DATETIME NULL, end_at DATETIME NULL,
                         is_active TINYINT(1) NOT NULL DEFAULT 1, created_at DATETIME DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'''),
            ('order_combos', '''CREATE TABLE IF NOT EXISTS order_combos (order_id INT NOT NULL, combo_id INT NOT NULL,
                               qty INT NOT NULL DEFAULT 1, discount DECIMAL(12,2) NOT NULL DEFAULT 0, PRIMARY KEY (order_id, combo_id),
                               FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'''),
            ('review_helpful', '''CREATE TABLE IF NOT EXISTS review_helpful (review_id INT NOT NULL, user_id INT NOT NULL,
                                 created_at DATETIME DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (review_id, user_id),
                                 FOREIGN KEY (review_id) REFERENCES reviews(id) ON DELETE CASCADE,
                                 FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'''),
            ('notifications', '''CREATE TABLE IF NOT EXISTS notifications (id INT AUTO_INCREMENT PRIMARY KEY, user_id INT NOT NULL,
                                title VARCHAR(500) NOT NULL, link VARCHAR(500) NULL, is_read TINYINT(1) NOT NULL DEFAULT 0,
                                created_at DATETIME DEFAULT CURRENT_TIMESTAMP, KEY idx_notif_user (user_id, is_read),
                                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'''),
            ('staff_logs', '''CREATE TABLE IF NOT EXISTS staff_logs (id INT AUTO_INCREMENT PRIMARY KEY, user_id INT NOT NULL,
                              action VARCHAR(100) NOT NULL, order_id INT NULL, detail VARCHAR(500) NULL,
                              created_at DATETIME DEFAULT CURRENT_TIMESTAMP, KEY idx_slog_user (user_id),
                              KEY idx_slog_order (order_id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'''),
        ]:
            try:
                execute_db(_ddl)
            except Exception:
                pass
        for _tbl, _col, _ddl in [
            ('orders', 'note', 'ALTER TABLE orders ADD COLUMN note TEXT NULL'),
            ('orders', 'dong_kiem', 'ALTER TABLE orders ADD COLUMN dong_kiem TINYINT(1) NOT NULL DEFAULT 0'),
            ('orders', 'ship_carrier', 'ALTER TABLE orders ADD COLUMN ship_carrier VARCHAR(50) NULL'),
            ('orders', 'channel', "ALTER TABLE orders ADD COLUMN channel VARCHAR(20) NOT NULL DEFAULT 'online'"),
            ('orders', 'store_id', 'ALTER TABLE orders ADD COLUMN store_id INT NULL'),
            ('order_items', 'is_gift', 'ALTER TABLE order_items ADD COLUMN is_gift TINYINT(1) NOT NULL DEFAULT 0'),
            ('reviews', 'status', "ALTER TABLE reviews ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'Hien'"),
            ('reviews', 'reply', 'ALTER TABLE reviews ADD COLUMN reply TEXT NULL'),
            ('reviews', 'helpful', 'ALTER TABLE reviews ADD COLUMN helpful INT NOT NULL DEFAULT 0'),
            ('users', 'email_verified', 'ALTER TABLE users ADD COLUMN email_verified TINYINT(1) NOT NULL DEFAULT 1'),
            ('return_requests', 'in_store', 'ALTER TABLE return_requests ADD COLUMN in_store TINYINT(1) NOT NULL DEFAULT 0'),
        ]:
            try:
                _has = query_db(f"SHOW COLUMNS FROM {_tbl} LIKE %s", [_col])
                if not _has:
                    execute_db(_ddl)
            except Exception:
                pass
        # Seed settings/pages/stores/gifts tối thiểu (INSERT IGNORE để không đè)
        for k, v in [('freeship_threshold', str(FREESHIP_THRESHOLD_DEFAULT)),
                     ('min_order_amount', str(MIN_ORDER_DEFAULT)),
                     ('gift_min_amount', str(GIFT_MIN_DEFAULT))]:
            try:
                execute_db('INSERT IGNORE INTO settings (`key`, `value`) VALUES (%s, %s)', (k, v))
            except Exception:
                pass
        for slug, title in STATIC_PAGES:
            try:
                execute_db('INSERT IGNORE INTO pages (slug, title, content) VALUES (%s, %s, %s)',
                           (slug, title, 'Dang cap nhat noi dung.'))
            except Exception:
                pass
        try:
            n = query_db('SELECT COUNT(*) AS c FROM stores', one=True)
            if n and int(n.get('c') or 0) == 0:
                execute_db("INSERT INTO stores (province, branch_name, address, open_hours, is_active) VALUES "
                           "(%s,%s,%s,%s,1)",
                           ('Da Nang', 'Chi nhanh Khue Trung', '39 Dao Cong Chinh, Khue Trung, Cam Le, Da Nang', '8:00 - 22:00'))
        except Exception:
            pass
        try:
            n = query_db('SELECT COUNT(*) AS c FROM gifts', one=True)
            if n and int(n.get('c') or 0) == 0:
                execute_db('INSERT INTO gifts (name, stock, min_order_amount, is_active) VALUES (%s,%s,%s,1),(%s,%s,%s,1)',
                           ('Tat co ban', 100, GIFT_MIN_DEFAULT, 'Voucher 20k don sau', 100, GIFT_MIN_DEFAULT))
        except Exception:
            pass
    except Exception:
        pass


def is_accessory_product(prod):
    try:
        cat = (prod.get('category') or '').strip().lower()
    except Exception:
        return False
    return cat in ('phụ kiện', 'phu kien', 'accessory', 'accessories')


def is_sale_product(prod):
    try:
        return effective_price(prod) < float(prod.get('price') or 0)
    except Exception:
        return False


def is_exchange_blocked(prod):
    """Sale + Phụ kiện tuyệt đối không đổi/trả. Trả về (blocked:bool, reason:str)."""
    if not prod:
        return True, 'Sản phẩm không tồn tại!'
    if is_accessory_product(prod):
        return True, 'Phụ kiện không áp dụng đổi/trả!'
    if is_sale_product(prod):
        return True, 'Hàng Sale không áp dụng đổi/trả!'
    return False, ''


def gift_eligible(cart_items, merch_total):
    """1 đơn 1 quà nếu tổng tiền đạt ngưỡng HOẶC giỏ có SP has_gift=1."""
    try:
        if float(merch_total or 0) >= float(get_int_setting('gift_min_amount', GIFT_MIN_DEFAULT)):
            return True
    except (ValueError, TypeError):
        pass
    for it in cart_items or []:
        try:
            if int(it.get('has_gift') or 0) == 1:
                return True
        except (ValueError, TypeError):
            continue
    return False


def get_available_gifts(merch_total):
    try:
        rows = query_db('SELECT * FROM gifts WHERE is_active = 1 AND stock > 0 AND min_order_amount <= %s ORDER BY id',
                        [float(merch_total or 0)])
        return rows or []
    except Exception:
        return []


def push_notification(user_id, title, link=None):
    try:
        if not user_id:
            return
        execute_db('INSERT INTO notifications (user_id, title, link) VALUES (%s, %s, %s)',
                   (int(user_id), (title or '')[:500], (link or '')[:500] or None))
    except Exception:
        pass


def staff_log(action, order_id=None, detail=''):
    try:
        if current_user.is_authenticated:
            execute_db('INSERT INTO staff_logs (user_id, action, order_id, detail) VALUES (%s, %s, %s, %s)',
                       (int(current_user.id), (action or '')[:100], order_id, (detail or '')[:500]))
    except Exception:
        pass


def verify_recaptcha(token):
    """reCAPTCHA v2: chưa cấu hình keys thì bỏ qua (không chặn form)."""
    try:
        secret = (get_setting('recaptcha_secret_key', '') or '').strip()
    except Exception:
        secret = ''
    if not secret or not (token or '').strip():
        return True if not secret else False
    try:
        import urllib.request
        import urllib.parse
        import json as _json
        data = urllib.parse.urlencode({'secret': secret, 'response': token}).encode()
        req = urllib.request.Request('https://www.google.com/recaptcha/api/siteverify', data=data)
        with urllib.request.urlopen(req, timeout=8) as resp:
            out = _json.loads(resp.read().decode('utf-8', 'ignore'))
        return bool(out.get('success'))
    except Exception:
        return False


def active_combos():
    try:
        return query_db("SELECT * FROM combos WHERE is_active = 1 AND (start_at IS NULL OR start_at <= NOW()) AND (end_at IS NULL OR end_at >= NOW()) ORDER BY id") or []
    except Exception:
        return []


def evaluate_combos(cart_map, eff_map):
    """cart_map {product_id: qty}, eff_map {product_id: unit_price}.
    Trả về (auto_gifts [(gift_pid, qty, combo)], bundle_discount, applied [(combo, qty, discount)])."""
    auto_gifts, applied = [], []
    bundle_discount = 0
    try:
        combos = active_combos()
    except Exception:
        return auto_gifts, 0, applied
    for cb in combos:
        try:
            ctype = (cb.get('combo_type') or 'BUY_GET').upper()
            if ctype == 'BUY_GET':
                tid = int(cb.get('trigger_product_id') or 0)
                tq = max(1, int(cb.get('trigger_qty') or 1))
                gid = int(cb.get('gift_product_id') or 0)
                gq = max(1, int(cb.get('gift_qty') or 1))
                if tid and gid and int(cart_map.get(tid) or 0) >= tq:
                    times = int(cart_map.get(tid) or 0) // tq
                    auto_gifts.append((gid, gq * times, cb))
                    applied.append((cb, times, 0))
            elif ctype == 'BUNDLE':
                ids = [int(x) for x in str(cb.get('bundle_product_ids') or '').replace(';', ',').split(',') if x.strip().isdigit()]
                try:
                    bprice = float(cb.get('bundle_price') or 0)
                except (ValueError, TypeError):
                    bprice = 0
                if len(ids) >= 2 and bprice > 0 and all(int(cart_map.get(i) or 0) >= 1 for i in ids):
                    sets = min(int(cart_map.get(i) or 0) for i in ids)
                    full = sum(float(eff_map.get(i) or 0) for i in ids)
                    if full > bprice:
                        disc = (full - bprice) * sets
                        bundle_discount += disc
                        applied.append((cb, sets, disc))
        except Exception:
            continue
    return auto_gifts, bundle_discount, applied


def earn_points_for_order(order_id, user_id, total_amount):
    """Tích điểm khi đơn Hoàn thành (chống tích 2 lần). Chỉ acc Khách hàng. Trả về số điểm đã tích."""
    if not user_id:
        return 0
    owner = query_db("SELECT role FROM users WHERE id = %s", [user_id], one=True)
    if not owner or (owner.get('role') != 'Khách hàng'):
        return 0
    try:
        earn = int(float(total_amount or 0) // POINTS_PER_VND)
    except (ValueError, TypeError):
        earn = 0
    if earn <= 0:
        return 0
    dup = query_db("SELECT id FROM point_log WHERE order_id = %s AND type = 'EARN'", [order_id], one=True)
    if dup:
        return 0
    execute_db('UPDATE users SET points = points + %s WHERE id = %s', (earn, user_id))
    execute_db("INSERT INTO point_log (user_id, order_id, points, type) VALUES (%s, %s, %s, 'EARN')", (user_id, order_id, earn))
    return earn


def refund_points_for_cancel(order_id, user_id):
    """Hủy đơn: hoàn điểm đã dùng (REFUND) + thu hồi điểm đã tích (REVOKE)."""
    if not user_id:
        return
    spent = query_db("SELECT COALESCE(SUM(points),0) AS s FROM point_log WHERE order_id = %s AND type = 'SPEND'", [order_id], one=True)
    spent = int((spent or {}).get('s') or 0)
    if spent > 0:
        already = query_db("SELECT id FROM point_log WHERE order_id = %s AND type = 'REFUND'", [order_id], one=True)
        if not already:
            execute_db('UPDATE users SET points = points + %s WHERE id = %s', (spent, user_id))
            execute_db("INSERT INTO point_log (user_id, order_id, points, type) VALUES (%s, %s, %s, 'REFUND')", (user_id, order_id, spent))
    earned = query_db("SELECT COALESCE(SUM(points),0) AS s FROM point_log WHERE order_id = %s AND type = 'EARN'", [order_id], one=True)
    earned = int((earned or {}).get('s') or 0)
    if earned > 0:
        already = query_db("SELECT id FROM point_log WHERE order_id = %s AND type = 'REVOKE'", [order_id], one=True)
        if not already:
            execute_db('UPDATE users SET points = GREATEST(0, points - %s) WHERE id = %s', (earned, user_id))
            execute_db("INSERT INTO point_log (user_id, order_id, points, type) VALUES (%s, %s, %s, 'REVOKE')", (user_id, order_id, earned))

# Phase 2 — Giá sale: biểu thức SQL dùng chung (alias bảng truyền vào)
def eff_price_sql(alias='p'):
    return (f"(CASE WHEN {alias}.sale_price IS NOT NULL AND {alias}.sale_price >= 0 "
            f"AND {alias}.sale_price < {alias}.price "
            f"AND ({alias}.sale_start IS NULL OR {alias}.sale_start <= NOW()) "
            f"AND ({alias}.sale_end IS NULL OR {alias}.sale_end >= NOW()) "
            f"THEN {alias}.sale_price ELSE {alias}.price END)")


def effective_price(row):
    """Giá bán thực tế của 1 dict product (có price/sale_price/sale_start/sale_end)."""
    try:
        base = float(row.get('price') or 0)
    except (ValueError, TypeError):
        base = 0
    sp = row.get('sale_price')
    if sp is None:
        return base
    try:
        sp = float(sp)
    except (ValueError, TypeError):
        return base
    if sp < 0 or sp >= base:
        return base
    now = datetime.now()
    st, en = row.get('sale_start'), row.get('sale_end')
    for v in (st, en):
        if isinstance(v, date) and not isinstance(v, datetime):
            pass  # DATE so sánh được với datetime? chuẩn hóa bên dưới
    try:
        if st:
            std = st if isinstance(st, datetime) else datetime.combine(st, datetime.min.time()) if isinstance(st, date) else datetime.strptime(str(st)[:19], '%Y-%m-%d %H:%M:%S' if len(str(st)) > 10 else '%Y-%m-%d')
            if std > now:
                return base
        if en:
            end = en if isinstance(en, datetime) else datetime.combine(en, datetime.max.time()) if isinstance(en, date) else datetime.strptime(str(en)[:19], '%Y-%m-%d %H:%M:%S' if len(str(en)) > 10 else '%Y-%m-%d')
            if end < now:
                return base
    except (ValueError, TypeError):
        return base
    return sp


def apply_pricing(rows):
    """Gắn eff_price/on_sale/discount_pct cho list dict product. Trả về chính list đó."""
    for r in rows or []:
        try:
            base = float(r.get('price') or 0)
        except (ValueError, TypeError):
            base = 0
        eff = effective_price(r)
        r['eff_price'] = eff
        r['on_sale'] = eff < base
        r['discount_pct'] = int(round((base - eff) * 100 / base)) if base > 0 and eff < base else 0
    return rows    

bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Vui lòng đăng nhập để sử dụng tính năng này.'
login_manager.login_message_category = 'warning'
class User(UserMixin):
    def __init__(self, id, name, email, is_admin, role):
        self.id = id
        self.name = name
        self.email = email
        self.is_admin = is_admin
        self.role = role

    def get_id(self):
        return str(self.id)

@login_manager.user_loader
def load_user(user_id):
    try:
        user_id_int = int(user_id)
    except (ValueError, TypeError):
        return None
    user = query_db('SELECT id, name, email, is_admin, role FROM users WHERE id = %s', [user_id_int], one=True)
    if user:
        return User(user['id'], user['name'], user['email'], user.get('is_admin', 0), user.get('role', 'Khách hàng'))
    return None


def _get_stored_password(user_row):
    """Ưu tiên cột `password` (werkzeug scrypt), fallback `password_hash` (bcrypt cũ)."""
    if not user_row:
        return None
    pw = user_row.get('password')
    if pw:
        return pw
    return user_row.get('password_hash')


def verify_password(stored_hash, plain_password):
    """Verify hỗ trợ cả werkzeug (scrypt/pbkdf2) và bcrypt cũ. Không bao giờ so sánh plaintext."""
    if not stored_hash or not plain_password:
        return False
    # Plaintext trong DB (bug cũ, vd Admin/123456) -> coi như sai, bắt buộc reset qua migration
    if len(stored_hash) < 20 or ('$' not in stored_hash and ':' not in stored_hash):
        return False
    try:
        if check_password_hash(stored_hash, plain_password):
            return True
    except Exception:
        pass
    try:
        # Fallback bcrypt cũ ($2b$...) qua Flask-Bcrypt
        if stored_hash.startswith('$2'):
            return bcrypt.check_password_hash(stored_hash, plain_password)
    except Exception:
        pass
    return False


def is_admin_user():
    try:
        return current_user.is_authenticated and (int(current_user.is_admin or 0) == 1)
    except Exception:
        return False


def is_staff_user():
    """Admin hoặc Nhân viên được vào khu quản lý đơn/doanh thu."""
    try:
        if not current_user.is_authenticated:
            return False
        if int(current_user.is_admin or 0) == 1:
            return True
        return (current_user.role == 'Nhân viên')
    except Exception:
        return False


def normalize_payment(method):
    m = (method or 'COD').strip()
    m = PAYMENT_ALIASES.get(m, m)
    if m not in ALLOWED_PAYMENTS and m != 'COD':
        # Map 'Tiền mặt' cũ -> COD, còn lại default COD
        return 'COD'
    if m == 'Tiền mặt':
        return 'COD'
    return m


def get_variants(product_id):
    """Danh sách biến thể còn/không còn hàng của 1 SP (sắp xếp size theo thứ tự chuẩn)."""
    rows = query_db('SELECT * FROM product_variants WHERE product_id = %s', [product_id])
    order = {s: i for i, s in enumerate(SIZES)}
    return sorted(rows or [], key=lambda r: (order.get(r.get('size'), 99), r.get('color') or ''))


def resync_product_stock(product_id):
    """Chốt tổng products.stock = SUM(variants) để chống lệch. Trả về tổng mới."""
    row = query_db('SELECT COALESCE(SUM(stock),0) AS s FROM product_variants WHERE product_id = %s', [product_id], one=True)
    total = int((row or {}).get('s') or 0)
    execute_db('UPDATE products SET stock = %s WHERE id = %s', (total, product_id))
    return total


def resync_all_stock():
    """Đồng bộ toàn bộ SP. Trả về số SP bị lệch đã sửa."""
    prods = query_db('SELECT id, stock FROM products')
    fixed = 0
    for p in prods or []:
        row = query_db('SELECT COALESCE(SUM(stock),0) AS s FROM product_variants WHERE product_id = %s', [p['id']], one=True)
        total = int((row or {}).get('s') or 0)
        if total != int(p.get('stock') or 0):
            execute_db('UPDATE products SET stock = %s WHERE id = %s', (total, p['id']))
            fixed += 1
    return fixed


def resolve_variant(product_id, size=None, color=None):
    """Tìm biến thể theo size/màu; thiếu param → biến thể default; không khớp → None."""
    size = (size or '').strip() or DEFAULT_SIZE
    color = (color or '').strip() or DEFAULT_COLOR
    if size not in SIZES or color not in COLORS:
        return None
    return query_db('SELECT * FROM product_variants WHERE product_id = %s AND size = %s AND color = %s',
                    [product_id, size, color], one=True)


def parse_variant_lines(text):
    """Parse textarea admin: mỗi dòng 'Size | Màu | SL'. Trả về (errors, [(size,color,qty)])."""
    errors, out, seen = [], [], set()
    for ln, raw in enumerate((text or '').splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split('|')]
        if len(parts) != 3:
            errors.append(f'Dòng {ln}: phải đúng dạng Size | Màu | SL!')
            continue
        size, color, qty_raw = parts
        if size not in SIZES:
            errors.append(f'Dòng {ln}: size "{size}" không trong danh sách {"/".join(SIZES)}!')
            continue
        if color not in COLORS:
            errors.append(f'Dòng {ln}: màu "{color}" không trong danh sách {"/".join(COLORS)}!')
            continue
        try:
            qty = int(qty_raw)
        except (ValueError, TypeError):
            errors.append(f'Dòng {ln}: SL phải là số nguyên!')
            continue
        if qty < 0 or qty > 99999:
            errors.append(f'Dòng {ln}: SL phải 0–99999!')
            continue
        if (size, color) in seen:
            errors.append(f'Dòng {ln}: trùng biến thể {size}/{color}!')
            continue
        seen.add((size, color))
        out.append((size, color, qty))
    return errors, out

class RegistrationForm(FlaskForm):
    name = StringField('Họ và tên', validators=[DataRequired(), Length(min=2, max=50)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Mật khẩu', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Xác nhận mật khẩu', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Đăng ký')
class AdminAddUserForm(FlaskForm):
    role = SelectField('Vị trí công tác', choices=[('Nhân viên', 'Nhân viên bán hàng'), ('Admin', 'Quản trị viên')])
    name = StringField('Họ và tên', validators=[DataRequired(), Length(min=2, max=50)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Mật khẩu', validators=[DataRequired(), Length(min=6)])
    submit = SubmitField('Thêm nhân sự')
class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Mật khẩu', validators=[DataRequired()])
    submit = SubmitField('Đăng nhập')

class ProductForm(FlaskForm):
    name = StringField('Tên sản phẩm', validators=[DataRequired(), Length(min=3, max=100)])
    price = DecimalField('Giá (đ)', validators=[DataRequired(), NumberRange(min=0)])
    stock = IntegerField('Số lượng (chỉ dùng khi không nhập biến thể)', validators=[Optional(), NumberRange(min=0)])
    category = StringField('Danh mục', validators=[DataRequired(), Length(min=2, max=50)])
    description = TextAreaField('Mô tả', validators=[DataRequired(), Length(min=5, max=500)])
    image = StringField('Ảnh (URL)', validators=[DataRequired(), Length(min=5, max=500)])
    variants = TextAreaField('Biến thể: mỗi dòng Size | Màu | SL (vd: M | Đen | 20). Bỏ trống = 1 biến thể mặc định.')
    sale_price = DecimalField('Giá sale (để trống = không sale)', validators=[Optional(), NumberRange(min=0)])
    sale_start = StringField('Sale từ ngày (YYYY-MM-DD, để trống = luôn)', validators=[Optional(), Length(max=10)])
    sale_end = StringField('Sale đến ngày (YYYY-MM-DD, để trống = luôn)', validators=[Optional(), Length(max=10)])
    is_featured = BooleanField('Nổi bật')
    has_gift = BooleanField('Có quà tặng kèm (1 đơn 1 quà)')
    brand = StringField('Thương hiệu', validators=[Optional(), Length(max=100)])
    video_url = StringField('Video mặc thử (URL mp4/youtube embed)', validators=[Optional(), Length(max=1000)])
    material = StringField('Chất liệu', validators=[Optional(), Length(max=500)])
    fit = StringField('Form dáng', validators=[Optional(), Length(max=255)])
    size_note = StringField('Ghi chú size', validators=[Optional(), Length(max=500)])
    gallery = TextAreaField('Gallery: mỗi dòng 1 URL ảnh (ngoài ảnh chính)')
    faqs = TextAreaField('FAQ riêng: mỗi dòng Câu hỏi || Trả lời')
    submit = SubmitField('Lưu')


def slugify(text):
    import unicodedata
    text = (text or '').strip().lower()
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    text = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    return text[:100] or 'item'


def parse_gallery_lines(text):
    out, seen = [], set()
    for raw in (text or '').splitlines():
        u = raw.strip()[:1000]
        if not u or u in seen:
            continue
        if not (u.startswith('http://') or u.startswith('https://')):
            continue
        seen.add(u)
        out.append(u)
    return out[:10]


def parse_faq_lines(text):
    errors, out = [], []
    for ln, raw in enumerate((text or '').splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if '||' not in line:
            errors.append(f'FAQ dòng {ln}: phải dạng Câu hỏi || Trả lời!')
            continue
        q, a = line.split('||', 1)
        q, a = q.strip()[:500], a.strip()
        if len(q) < 3 or len(a) < 3:
            errors.append(f'FAQ dòng {ln}: quá ngắn!')
            continue
        out.append((q, a))
        if len(out) >= 10:
            break
    return errors, out


def get_product_images(product_id):
    try:
        return query_db('SELECT * FROM product_images WHERE product_id = %s ORDER BY sort_order, id', [product_id]) or []
    except Exception:
        return []


def get_product_faqs(product_id):
    try:
        return query_db('SELECT * FROM product_faqs WHERE product_id = %s ORDER BY sort_order, id', [product_id]) or []
    except Exception:
        return []


def parse_sale(price_val, sale_raw, start_raw, end_raw):
    """Validate giá sale. Trả về (errors, sale_price|None, sale_start|None, sale_end|None)."""
    errors = []
    if sale_raw in (None, ''):
        return errors, None, None, None
    try:
        sp = float(sale_raw)
    except (ValueError, TypeError):
        return ['Giá sale không hợp lệ!'], None, None, None
    if sp < 0 or sp >= float(price_val):
        errors.append('Giá sale phải >= 0 và nhỏ hơn giá gốc!')
    def _d(raw, label):
        raw = (raw or '').strip()
        if not raw:
            return None
        try:
            return datetime.strptime(raw[:10], '%Y-%m-%d')
        except (ValueError, TypeError):
            errors.append(f'{label} phải dạng YYYY-MM-DD!')
            return None
    st = _d(start_raw, 'Ngày bắt đầu')
    en = _d(end_raw, 'Ngày kết thúc')
    if st and en and st > en:
        errors.append('Ngày bắt đầu phải trước ngày kết thúc!')
    if errors:
        return errors, None, None, None
    return [], sp, st, en

class CheckoutForm(FlaskForm):
    fullname = StringField('Họ tên', validators=[DataRequired(), Length(min=3, max=100)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    phone = StringField('SĐT', validators=[DataRequired(), Length(min=9, max=15)])
    address = TextAreaField('Địa chỉ', validators=[Length(max=200)])
    submit = SubmitField('Đặt hàng')

class ReviewForm(FlaskForm):
    name = StringField('Tên', validators=[DataRequired(), Length(min=2, max=50)])
    comment = TextAreaField('Đánh giá', validators=[DataRequired(), Length(min=3, max=300)])
    rating = IntegerField('Sao', validators=[DataRequired(), NumberRange(min=1, max=5)])
    submit = SubmitField('Gửi')

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER, password=MYSQL_PASSWORD, database=MYSQL_DB, cursorclass=pymysql.cursors.DictCursor, autocommit=True)
        g._database = db
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def query_db(query, args=(), one=False):
    db = get_db()
    query = query.replace('?', '%s') 
    with db.cursor() as cur:
        cur.execute(query, args)
        rv = cur.fetchall()
    return (rv[0] if rv else None) if one else rv

def execute_db(query, args=(), lastrowid=False):
    db = get_db()
    query = query.replace('?', '%s')
    with db.cursor() as cur:
        cur.execute(query, args)
        rowid = cur.lastrowid if lastrowid else None
    return rowid

@app.before_request
def _auto_migrate_extended():
    if not getattr(g, '_ext_migrated', False):
        g._ext_migrated = True
        try:
            ensure_extended_tables()
        except Exception:
            pass


@app.context_processor
def inject_globals():
    try:
        ensure_extended_tables()
    except Exception:
        pass
    try:
        categories = query_db('SELECT DISTINCT category FROM products WHERE is_active = 1')
    except Exception:
        categories = []
    ...
    
    # 1. Khởi tạo biến
    cart_quantity = 0
    wishlist_count = 0
    
    if current_user.is_authenticated:
        try:
            # 2. ĐẾM GIỎ HÀNG TỪ DATABASE (KHÔNG DÙNG SESSION NỮA)
            cart_res = query_db('SELECT SUM(quantity) as total FROM cart WHERE user_id = %s', [current_user.id], one=True)
            if cart_res and cart_res['total']:
                cart_quantity = int(cart_res['total'] or 0)
        except Exception:
            cart_quantity = 0
        try:
            # 3. Đếm Yêu thích
            res = query_db('SELECT COUNT(*) as cnt FROM wishlist WHERE user_id = %s', [current_user.id], one=True)
            if res and res.get('cnt'):
                wishlist_count = int(res['cnt'] or 0)
        except Exception:
            wishlist_count = 0
        
    try:
        _freeship = get_int_setting('freeship_threshold', FREESHIP_THRESHOLD_DEFAULT)
    except Exception:
        _freeship = FREESHIP_THRESHOLD_DEFAULT
    notif_count = 0
    expiring_vouchers = []
    if current_user.is_authenticated:
        try:
            _n = query_db('SELECT COUNT(*) AS c FROM notifications WHERE user_id = %s AND is_read = 0', [current_user.id], one=True)
            notif_count = int((_n or {}).get('c') or 0)
        except Exception:
            notif_count = 0
        try:
            expiring_vouchers = query_db('SELECT code, expires_at FROM vouchers WHERE usage_limit > 0 AND expires_at IS NOT NULL AND expires_at >= CURDATE() AND expires_at <= DATE_ADD(CURDATE(), INTERVAL 3 DAY) ORDER BY expires_at LIMIT 5') or []
        except Exception:
            expiring_vouchers = []
    return {
        'categories': [row['category'] for row in categories] if categories else [],
        'cart_quantity': cart_quantity,
        'wishlist_count': wishlist_count,
        'menu_tree': CATEGORY_TREE,
        'hot_keywords': HOT_KEYWORDS,
        'static_pages': STATIC_PAGES,
        'freeship_threshold': _freeship,
        'notif_count': notif_count,
        'expiring_vouchers': expiring_vouchers,
        'recaptcha_site_key': get_setting('recaptcha_site_key', ''),
    }

# ==========================================
# CÁC ROUTE KHÁCH HÀNG & MUA SẮM
# ==========================================
@app.route('/')
def index():
    search = request.args.get('search', '').strip()
    category = request.args.get('category', '').strip()
    fsize = request.args.get('size', '').strip()
    fcolor = request.args.get('color', '').strip()
    sort = request.args.get('sort', '').strip()
    try:
        page = int(request.args.get('page', 1))
    except (ValueError, TypeError):
        page = 1
    if page < 1:
        page = 1
    try:
        fmin = float(request.args.get('min_price') or '')
        if fmin < 0:
            fmin = None
    except (ValueError, TypeError):
        fmin = None
    try:
        fmax = float(request.args.get('max_price') or '')
        if fmax < 0:
            fmax = None
    except (ValueError, TypeError):
        fmax = None
    if fsize not in SIZES:
        fsize = ''
    if fcolor not in COLORS or fcolor == 'Mặc định':
        fcolor = ''
    if sort not in ('newest', 'price_asc', 'price_desc', 'best'):
        sort = ''
    sale_only = request.args.get('sale', '').strip() == '1'
    per_page = 10
    EP = eff_price_sql('products')

    # LUÔN PHẢI CÓ ĐIỀU KIỆN is_active = 1 CHO KHÁCH HÀNG
    where_clause = "is_active = 1"
    params = []

    if search:
        where_clause += " AND (products.name LIKE %s OR products.category LIKE %s)"
        params.extend([f'%{search}%', f'%{search}%'])
    if category and category != 'Tất cả':
        where_clause += " AND products.category = %s"
        params.append(category)
    if fsize:
        where_clause += " AND EXISTS (SELECT 1 FROM product_variants v WHERE v.product_id = products.id AND v.size = %s AND v.stock > 0)"
        params.append(fsize)
    if fcolor:
        where_clause += " AND EXISTS (SELECT 1 FROM product_variants v WHERE v.product_id = products.id AND v.color = %s AND v.stock > 0)"
        params.append(fcolor)
    if fmin is not None:
        where_clause += f" AND ({EP}) >= %s"
        params.append(fmin)
    if fmax is not None:
        where_clause += f" AND ({EP}) <= %s"
        params.append(fmax)
    if sale_only:
        where_clause += (" AND products.sale_price IS NOT NULL AND products.sale_price >= 0 "
                         "AND products.sale_price < products.price "
                         "AND (products.sale_start IS NULL OR products.sale_start <= NOW()) "
                         "AND (products.sale_end IS NULL OR products.sale_end >= NOW())")

    if sort == 'best':
        # Bán chạy: chỉ tính đơn Hoàn thành, ẩn SP chưa bán được cái nào
        sold_expr = "COALESCE(SUM(CASE WHEN o.status = %s THEN oi.quantity ELSE 0 END), 0)"
        best_from = ("FROM products LEFT JOIN order_items oi ON oi.product_id = products.id "
                     "LEFT JOIN orders o ON o.id = oi.order_id AND o.status = %s "
                     f"WHERE {where_clause} GROUP BY products.id HAVING {sold_expr} > 0")
        cnt_row = query_db(f'SELECT COUNT(*) as cnt FROM (SELECT products.id {best_from}) t',
                           ['Hoàn thành'] + params + ['Hoàn thành'], one=True)
    else:
        cnt_row = query_db(f'SELECT COUNT(id) as cnt FROM products WHERE {where_clause}', params, one=True)
    total_products = cnt_row['cnt'] if cnt_row and cnt_row.get('cnt') else 0
    total_pages = max(1, math.ceil(total_products / per_page)) if total_products > 0 else 1
    if page > total_pages:
        page = total_pages
    offset = (page - 1) * per_page

    if sort == 'price_asc':
        order_by = f'({EP}) ASC, products.id DESC'
    elif sort == 'price_desc':
        order_by = f'({EP}) DESC, products.id DESC'
    elif sort == 'newest':
        order_by = 'products.id DESC'
    elif sort == 'best':
        order_by = 'COALESCE(SUM(CASE WHEN o.status = %s THEN oi.quantity ELSE 0 END), 0) DESC, products.id DESC'
    else:
        order_by = 'products.is_featured DESC, products.id DESC'

    if sort == 'best':
        query = (f'SELECT products.*, {sold_expr} AS sold {best_from} '
                 f'ORDER BY {sold_expr} DESC, products.id DESC LIMIT %s OFFSET %s')
        products = query_db(query, ['Hoàn thành', 'Hoàn thành'] + params + ['Hoàn thành', 'Hoàn thành', per_page, offset])
    else:
        query = f'SELECT *, ({EP}) AS eff_sql FROM products WHERE {where_clause} ORDER BY {order_by} LIMIT %s OFFSET %s'
        products = query_db(query, params + [per_page, offset])
    apply_pricing(products)

    featured = query_db('SELECT * FROM products WHERE is_featured = 1 AND is_active = 1 LIMIT 4')
    apply_pricing(featured)

    categories_data = query_db('SELECT DISTINCT category FROM products WHERE category IS NOT NULL AND is_active = 1')
    categories = [row['category'] for row in categories_data]
    try:
        banners = query_db('SELECT * FROM banners WHERE is_active = 1 ORDER BY sort_order, id') or []
    except Exception:
        banners = []

    return render_template('index.html', products=products, featured=featured, search=search, category=category,
                           page=page, total_pages=total_pages, total_products=total_products, categories=categories,
                           fsize=fsize, fcolor=fcolor, fmin=request.args.get('min_price', ''),
                           fmax=request.args.get('max_price', ''), sort=sort, sale=sale_only, sizes=SIZES, colors=COLORS,
                           banners=banners)

@app.route('/product/<int:product_id>', methods=['GET', 'POST'])
def product_detail(product_id):
    # Lấy thông tin sản phẩm hiện tại
    product = query_db('SELECT * FROM products WHERE id = %s AND is_active = 1', [product_id], one=True)
    if not product: return redirect(url_for('index'))
    
    # Kiểm tra xem user đã đánh giá sản phẩm này chưa (theo tên chuẩn hóa, chống spoof)
    user_has_reviewed = False
    has_purchased = False
    if current_user.is_authenticated:
        reviewed = query_db('SELECT id FROM reviews WHERE product_id = %s AND name = %s', [product_id, (current_user.name or '').strip()], one=True)
        if reviewed:
            user_has_reviewed = True
        # Đã mua và hoàn thành thì mới được review (đơn online theo acc + đơn tại quầy match SĐT)
        bought = query_db('''SELECT oi.id FROM order_items oi JOIN orders o ON oi.order_id = o.id
                             WHERE o.user_id = %s AND oi.product_id = %s AND o.status = 'Hoàn thành' LIMIT 1''',
                          [current_user.id, product_id], one=True)
        if not bought:
            me_phone = query_db('SELECT phone FROM users WHERE id = %s', [current_user.id], one=True)
            my_digits = re.sub(r'\D', '', ((me_phone or {}).get('phone') or ''))
            if my_digits:
                bought = query_db('''SELECT oi.id FROM order_items oi JOIN orders o ON oi.order_id = o.id
                                     WHERE REPLACE(REPLACE(REPLACE(o.phone, ' ', ''), '+', ''), '-', '') = %s
                                     AND oi.product_id = %s AND o.status = 'Hoàn thành' LIMIT 1''',
                                  [my_digits, product_id], one=True)
        has_purchased = bool(bought)

    form = ReviewForm()
    if form.validate_on_submit():
        if not current_user.is_authenticated:
            flash('Vui lòng đăng nhập để đánh giá!', 'warning')
            return redirect(url_for('login'))
        if is_admin_user() or (current_user.is_authenticated and current_user.role == 'Nhân viên'):
            flash('Tài khoản quản trị/nhân viên không thể đánh giá!', 'danger')
            return redirect(url_for('product_detail', product_id=product_id))
        if user_has_reviewed:
            flash('Bạn đã đánh giá sản phẩm này rồi!', 'danger')
        elif not has_purchased:
            flash('Bạn cần mua và nhận hàng thành công mới được đánh giá!', 'warning')
        else:
            # Luôn dùng tên thật từ DB, bỏ qua field client để chống mạo danh
            safe_name = (current_user.name or '').strip()[:50]
            try:
                rating_val = int(form.rating.data)
            except (ValueError, TypeError):
                rating_val = 0
            if rating_val < 1 or rating_val > 5:
                flash('Số sao không hợp lệ!', 'danger')
                return redirect(url_for('product_detail', product_id=product_id))
            img_url = (request.form.get('image_url') or '').strip()[:500]
            if img_url and not (img_url.startswith('http://') or img_url.startswith('https://')):
                flash('Link ảnh đánh giá phải bắt đầu bằng http(s)!', 'danger')
                return redirect(url_for('product_detail', product_id=product_id))
            if not verify_recaptcha(request.form.get('g-recaptcha-response', '')):
                flash('Xác minh chống spam thất bại, thử lại!', 'danger')
                return redirect(url_for('product_detail', product_id=product_id))
            try:
                execute_db("INSERT INTO reviews (product_id, name, comment, rating, image_url, status, helpful) VALUES (%s, %s, %s, %s, %s, 'Cho_duyet', 0)",
                           (product_id, safe_name, (form.comment.data or '').strip(), rating_val, img_url or None))
                flash('Cảm ơn bạn đã đánh giá! Nhận xét sẽ hiện sau khi shop duyệt.', 'success')
            except Exception as e:
                # Trùng UNIQUE(product_id,name) do race
                if 'Duplicate' in str(e):
                    flash('Bạn đã đánh giá sản phẩm này rồi!', 'danger')
                else:
                    flash('Không thể gửi đánh giá lúc này!', 'danger')
        return redirect(url_for('product_detail', product_id=product_id))
        
    voted_ids = set()
    if current_user.is_authenticated:
        try:
            _v = query_db('SELECT review_id FROM review_helpful WHERE user_id = %s', [current_user.id]) or []
            voted_ids = {r['review_id'] for r in _v}
        except Exception:
            voted_ids = set()
    reviews = query_db("SELECT * FROM reviews WHERE product_id = %s AND status = 'Hien' ORDER BY helpful DESC, created_at DESC", [product_id])
    # Lọc theo sao (?star=5..1)
    try:
        star = int(request.args.get('star') or 0)
    except (ValueError, TypeError):
        star = 0
    if star not in (1, 2, 3, 4, 5):
        star = 0
    if star:
        reviews = query_db("SELECT * FROM reviews WHERE product_id = %s AND status = 'Hien' AND rating = %s ORDER BY helpful DESC, created_at DESC", [product_id, star])

    avg_rating_row = query_db("SELECT AVG(rating) as avg_rating, COUNT(id) as total_reviews FROM reviews WHERE product_id = %s AND status = 'Hien'", [product_id], one=True)
    avg_rating = round(avg_rating_row['avg_rating'], 1) if avg_rating_row['avg_rating'] else 0
    total_reviews = avg_rating_row['total_reviews']
    
    # ==========================================
    # LẤY 4 SẢN PHẨM LIÊN QUAN (Cùng danh mục, ngẫu nhiên)
    # ==========================================
    related_products = query_db(
        'SELECT * FROM products WHERE category = %s AND id != %s AND is_active = 1 ORDER BY RAND() LIMIT 4',
        [product['category'], product_id]
    )
    apply_pricing([product])
    apply_pricing(related_products)

    gallery = get_product_images(product_id)
    faqs = get_product_faqs(product_id)

    return render_template('product.html', product=product, form=form, reviews=reviews,
                         avg_rating=avg_rating, total_reviews=total_reviews, star=star,
                         user_has_reviewed=user_has_reviewed, has_purchased=has_purchased, related_products=related_products,
                         variants=get_variants(product_id), sizes=SIZES, colors=COLORS,
                         gallery=gallery, faqs=faqs, voted_ids=voted_ids)

@app.route('/add-to-cart/<int:product_id>', methods=['POST', 'GET'])
@login_required
def add_to_cart(product_id):
    # Hỗ trợ cả form POST và link GET (mặc định qty=1), validate chặt
    raw_qty = request.form.get('quantity', request.args.get('quantity', 1))
    try:
        quantity = int(raw_qty)
    except (ValueError, TypeError):
        flash('Số lượng không hợp lệ!', 'error')
        return redirect(request.referrer or url_for('index'))
    if quantity < 1:
        flash('Số lượng phải từ 1 trở lên!', 'error')
        return redirect(request.referrer or url_for('index'))
    if quantity > 999:
        quantity = 999

    # Chặn thêm hàng đã ẩn/xóa
    product = query_db('SELECT id, stock, name FROM products WHERE id = %s AND is_active = 1', [product_id], one=True)
    if not product:
        flash('Sản phẩm không tồn tại!', 'error')
        return redirect(request.referrer or url_for('index'))
    # Biến thể: trang chi tiết gửi size/color (hoặc variant "Size|Màu"); thêm nhanh → biến thể default còn hàng
    size = request.form.get('size', request.args.get('size'))
    color = request.form.get('color', request.args.get('color'))
    combo = request.form.get('variant', request.args.get('variant'))
    if combo and '|' in combo:
        _s, _c = combo.split('|', 1)
        size, color = _s.strip(), _c.strip()
    if size or color:
        variant = resolve_variant(product_id, size, color)
        if not variant:
            flash('Size/màu không hợp lệ!', 'error')
            return redirect(request.referrer or url_for('index'))
    else:
        variant = resolve_variant(product_id, DEFAULT_SIZE, DEFAULT_COLOR)
        if not variant or variant['stock'] < 1:
            variant = query_db('SELECT * FROM product_variants WHERE product_id = %s AND stock > 0 ORDER BY stock DESC LIMIT 1',
                               [product_id], one=True)
        if not variant:
            flash('Sản phẩm đã hết hàng!', 'error')
            return redirect(request.referrer or url_for('index'))
    if variant['stock'] < 1 or variant['stock'] < quantity:
        flash(f'Phân loại {variant["size"]}/{variant["color"]} chỉ còn {variant["stock"]} cái!', 'error')
        return redirect(request.referrer or url_for('index'))

    existing_item = query_db('SELECT id, quantity FROM cart WHERE user_id = %s AND product_id = %s AND variant_id = %s',
                             [current_user.id, product_id, variant['id']], one=True)

    if existing_item:
        new_quantity = existing_item['quantity'] + quantity
        if new_quantity > variant['stock']:
            flash(f'Không thể thêm! Phân loại {variant["size"]}/{variant["color"]} chỉ còn {variant["stock"]} cái.', 'error')
        else:
            execute_db('UPDATE cart SET quantity = %s WHERE id = %s AND user_id = %s', (new_quantity, existing_item['id'], current_user.id))
            flash(f'Đã cập nhật số lượng {product["name"]} ({variant["size"]}/{variant["color"]}) trong giỏ hàng.', 'success')
    else:
        try:
            execute_db('INSERT INTO cart (user_id, product_id, variant_id, quantity) VALUES (%s, %s, %s, %s)',
                       (current_user.id, product_id, variant['id'], quantity))
        except Exception as e:
            if 'Duplicate' in str(e):
                execute_db('UPDATE cart SET quantity = LEAST(quantity + %s, (SELECT stock FROM product_variants WHERE id = %s)) WHERE user_id = %s AND product_id = %s AND variant_id = %s',
                           (quantity, variant['id'], current_user.id, product_id, variant['id']))
            else:
                raise
        flash(f'Đã thêm {product["name"]} ({variant["size"]}/{variant["color"]}) vào giỏ hàng.', 'success')

    return redirect(request.referrer or url_for('index'))

@app.route('/cart')
@login_required
def cart():
    # Khách hàng/Admin đều vào được giỏ hàng

    # 1. Truy vấn lấy danh sách sản phẩm trong giỏ của user đang đăng nhập (kèm biến thể + sale)
    cart_items = query_db('''
        SELECT c.id, c.quantity, c.variant_id, p.id as product_id, p.name, p.price, p.image,
               p.sale_price, p.sale_start, p.sale_end, p.has_gift,
               v.size AS vsize, v.color AS vcolor, v.stock AS vstock
        FROM cart c
        JOIN products p ON c.product_id = p.id
        LEFT JOIN product_variants v ON v.id = c.variant_id
        WHERE c.user_id = %s
    ''', [current_user.id])
    for it in cart_items or []:
        it['stock'] = it.pop('vstock') if it.get('vstock') is not None else 0
    apply_pricing(cart_items)

    # Lấy tổng số lượng trên icon
    total_qty_query = query_db('SELECT SUM(quantity) as total FROM cart WHERE user_id = %s', [current_user.id], one=True)
    cart_quantity = total_qty_query['total'] if total_qty_query['total'] else 0

    points_balance = 0
    if not is_staff_user():
        brow = query_db('SELECT points FROM users WHERE id = %s', [current_user.id], one=True)
        points_balance = int((brow or {}).get('points') or 0)

    freeship_threshold = get_int_setting('freeship_threshold', FREESHIP_THRESHOLD_DEFAULT)
    cart_subtotal = sum(float(it.get('eff_price') or 0) * int(it.get('quantity') or 0) for it in (cart_items or []))
    show_gift = gift_eligible(cart_items, cart_subtotal)
    gifts = get_available_gifts(cart_subtotal) if show_gift else []
    _cmap, _emap = {}, {}
    for it in (cart_items or []):
        try:
            _pid = int(it['product_id'])
        except (ValueError, TypeError):
            continue
        _cmap[_pid] = int(_cmap.get(_pid) or 0) + int(it.get('quantity') or 0)
        _emap[_pid] = float(it.get('eff_price') or 0)
    _ag, _bd, _ap = evaluate_combos(_cmap, _emap)
    try:
        stores = query_db('SELECT id, branch_name, province FROM stores WHERE is_active = 1 ORDER BY province, branch_name') or []
    except Exception:
        stores = []

    return render_template('cart.html', cart_items=cart_items, cart_quantity=cart_quantity,
                           points_balance=points_balance, freeship_threshold=freeship_threshold,
                           cart_subtotal=cart_subtotal, gifts=gifts, show_gift=show_gift,
                           combo_gifts=_ag, combo_discount=_bd, applied_combos=_ap,
                           ship_carriers=SHIP_CARRIERS, stores=stores)
@app.route('/update-cart/<int:item_id>', methods=['POST'])
@login_required
def update_cart(item_id):
    try:
        quantity = int(request.form.get('quantity', 1))
    except (ValueError, TypeError):
        flash('Số lượng không hợp lệ!', 'error')
        return redirect(url_for('cart'))
    if quantity < 1:
        quantity = 1 # Vá lỗi người dùng nhập số 0
    if quantity > 999:
        quantity = 999
        
    item = query_db('''
        SELECT c.id, c.product_id, c.variant_id, COALESCE(v.stock, 0) AS stock,
               v.size AS vsize, v.color AS vcolor
        FROM cart c JOIN products p ON c.product_id = p.id
        LEFT JOIN product_variants v ON v.id = c.variant_id
        WHERE c.id = %s AND c.user_id = %s
    ''', [item_id, current_user.id], one=True)

    if item:
        if quantity > item['stock']:
            label = f" ({item['vsize']}/{item['vcolor']})" if item.get('vsize') else ''
            flash(f'Phân loại{label} chỉ còn {item["stock"]} cái trong kho!', 'error')
        else:
            execute_db('UPDATE cart SET quantity = %s WHERE id = %s AND user_id = %s', (quantity, item_id, current_user.id))

    return redirect(url_for('cart'))

@app.route('/admin/order/<int:order_id>/update', methods=['POST'])
@login_required
def update_order_status(order_id):
    if not is_staff_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))

    new_status = (request.form.get('status') or '').strip()
    if new_status not in ALLOWED_STATUSES:
        flash('Trạng thái không hợp lệ!', 'error')
        return redirect(url_for('admin_orders'))
    
    order = query_db('SELECT status, user_id, total_amount FROM orders WHERE id = %s', [order_id], one=True)
    if not order:
        flash('Không tìm thấy đơn hàng!', 'error')
        return redirect(url_for('admin_orders'))
        
    old_status = order['status']

    # ==========================================
    # CHỐT CHẶN BẢO MẬT: Nếu đơn cũ ĐÃ HỦY/HOÀN THÀNH thì khóa
    # ==========================================
    if old_status == 'Đã hủy':
        flash('Đơn hàng này đã bị hủy và bị khóa, không thể thay đổi trạng thái!', 'error')
        return redirect(url_for('admin_orders'))
    if old_status == 'Hoàn thành' and new_status == 'Đã hủy':
        flash('Đơn đã hoàn thành, không thể hủy! Hãy tạo đơn hoàn trả riêng.', 'error')
        return redirect(url_for('admin_orders'))

    # Cập nhật trạng thái mới vào database
    execute_db('UPDATE orders SET status = %s WHERE id = %s', (new_status, order_id))

    # Xử lý cộng trả lại kho nếu chuyển sang Đã hủy (biến thể + tổng SP)
    if new_status == 'Đã hủy' and old_status != 'Đã hủy':
        order_items = query_db('SELECT product_id, variant_id, quantity FROM order_items WHERE order_id = %s', [order_id])
        for item in order_items:
            if item.get('variant_id'):
                execute_db('UPDATE product_variants SET stock = stock + %s WHERE id = %s',
                           (item['quantity'], item['variant_id']))
            execute_db('UPDATE products SET stock = stock + %s WHERE id = %s',
                       (item['quantity'], item['product_id']))
        refund_points_for_cancel(order_id, order.get('user_id'))
        flash('Đã cập nhật HỦY ĐƠN. Số lượng sản phẩm đã được tự động hoàn trả vào kho!', 'success')
    else:
        if new_status == 'Hoàn thành' and old_status != 'Hoàn thành':
            earned = earn_points_for_order(order_id, order.get('user_id'), order.get('total_amount'))
            if earned:
                flash(f'Đã cập nhật thành "Hoàn thành"! Khách được tích {earned} điểm.', 'success')
            else:
                flash('Đã cập nhật trạng thái đơn hàng thành "Hoàn thành"!', 'success')
        else:
            flash(f'Đã cập nhật trạng thái đơn hàng thành "{new_status}"!', 'success')

    try:
        push_notification(order.get('user_id'), f"Đơn #ORD-{order_id} chuyển sang: {new_status}.", "/my-orders")
        staff_log(f'Doi trang thai {old_status}->{new_status}', order_id, f"Tong {'{:,.0f}'.format(float(order.get('total_amount') or 0))}d")
    except Exception:
        pass
    return redirect(url_for('admin_orders'))
@app.route('/remove-from-cart/<int:item_id>', methods=['POST', 'GET'])
@login_required
def remove_from_cart(item_id):
    execute_db('DELETE FROM cart WHERE id = %s AND user_id = %s', (item_id, current_user.id))
    flash('Đã xóa sản phẩm khỏi giỏ hàng.', 'success')
    return redirect(request.referrer or url_for('cart'))

@app.route('/checkout', methods=['POST'])
@login_required
def checkout():
    # Phân biệt bán tại quầy (staff/admin) vs khách online — logic khách giữ nguyên 100%
    staff_sale = is_staff_user()
    # Validate cơ bản
    address = (request.form.get('address') or '').strip()
    phone = (request.form.get('phone') or '').strip()
    if staff_sale and not address:
        address = 'Mua tại cửa hàng'
    if not address or len(address) < 5 or len(address) > 255:
        flash('Vui lòng nhập địa chỉ giao hàng đầy đủ (5-255 ký tự)!', 'error')
        return redirect(url_for('cart'))
    if not phone or len(phone) < 9 or len(phone) > 15 or not phone.replace('+', '').replace(' ', '').isdigit():
        flash('Số điện thoại không hợp lệ!', 'error')
        return redirect(url_for('cart'))
    payment_method = normalize_payment(request.form.get('payment_method', 'COD'))
    if payment_method not in ALLOWED_PAYMENTS:
        payment_method = 'COD'

    # Lấy user info để backfill fullname/email (orders.fullname/email NOT NULL ở DB cũ)
    me = query_db('SELECT name, email FROM users WHERE id = %s', [current_user.id], one=True)
    fullname = (me['name'] if me and me.get('name') else current_user.name or '').strip()[:255]
    email = (me['email'] if me and me.get('email') else current_user.email or '').strip()[:255]
    # BÁN TẠI QUẦY: ưu tiên tên khách nhập tay, bỏ trống = giữ tên acc NV như cũ
    order_owner_id = current_user.id
    if staff_sale:
        typed_name = (request.form.get('customer_name') or '').strip()[:255]
        if typed_name:
            if len(typed_name) < 2:
                flash('Tên khách phải từ 2 ký tự!', 'error')
                return redirect(url_for('cart'))
            fullname = typed_name
        # SĐT khớp acc khách quen → đơn thuộc về khách (khách thấy đơn + được tích điểm)
        digits = re.sub(r'\D', '', phone or '')
        if digits:
            cust = query_db("SELECT id, name, email FROM users WHERE phone = %s AND role = 'Khách hàng' LIMIT 1", [digits], one=True)
            if cust:
                order_owner_id = cust['id']
                if not typed_name:
                    fullname = (cust.get('name') or fullname).strip()[:255]
                email = (cust.get('email') or email).strip()[:255]
    if not fullname:
        fullname = f'User #{current_user.id}'
    if not email:
        email = f'user{current_user.id}@noemail.local'

    cart_items = query_db('''
        SELECT c.*, p.price, p.sale_price, p.sale_start, p.sale_end, p.name, p.has_gift,
               v.size AS vsize, v.color AS vcolor, COALESCE(v.stock, 0) AS stock
        FROM cart c
        JOIN products p ON c.product_id = p.id
        LEFT JOIN product_variants v ON v.id = c.variant_id
        WHERE c.user_id = %s AND p.is_active = 1
    ''', [current_user.id])

    if not cart_items:
        flash('Giỏ hàng của bạn đang trống!', 'error')
        return redirect(url_for('cart'))

    # Giỏ cũ thiếu variant (legacy) → gắn biến thể default để checkout được
    for item in cart_items:
        if not item.get('variant_id'):
            dv = resolve_variant(item['product_id'], DEFAULT_SIZE, DEFAULT_COLOR)
            if dv:
                execute_db('UPDATE cart SET variant_id = %s WHERE id = %s AND user_id = %s',
                           (dv['id'], item['id'], current_user.id))
                item['variant_id'] = dv['id']
                item['vsize'], item['vcolor'], item['stock'] = dv['size'], dv['color'], dv['stock']

    total_amount = 0
    for item in cart_items:
        item['eff_price'] = effective_price(item)
        try:
            qty = int(item['quantity'])
        except (ValueError, TypeError):
            qty = 0
        if qty < 1 or qty > (item['stock'] or 0):
            label = f" ({item.get('vsize')}/{item.get('vcolor')})" if item.get('vsize') else ''
            flash(f'Lỗi: Sản phẩm "{item["name"]}"{label} hiện chỉ còn {item["stock"]} cái. Vui lòng giảm số lượng!', 'error')
            return redirect(url_for('cart'))
        total_amount += qty * float(item['eff_price'])
        
    # ==========================================
    # XỬ LÝ LOGIC MÃ GIẢM GIÁ (VOUCHER)
    # ==========================================
    voucher_code = (request.form.get('voucher_code') or '').strip().upper()
    discount_applied = 0
    voucher_id = None
    freeship = False
    
    if voucher_code:
        voucher = query_db('SELECT * FROM vouchers WHERE code = %s', [voucher_code], one=True)
        if not voucher:
            flash('Mã giảm giá không tồn tại!', 'error')
            return redirect(url_for('cart'))
        # Hạn sử dụng: hỗ trợ DATE/DATETIME/string/None
        try:
            exp = voucher.get('expires_at')
            if exp is None:
                raise ValueError('missing expiry')
            if isinstance(exp, datetime):
                exp_date = exp.date()
            elif isinstance(exp, date):
                exp_date = exp
            else:
                exp_date = datetime.strptime(str(exp)[:10], '%Y-%m-%d').date()
            if exp_date < date.today():
                flash('Mã giảm giá đã hết hạn sử dụng!', 'error')
                return redirect(url_for('cart'))
        except ValueError:
            flash('Mã giảm giá lỗi hạn sử dụng, liên hệ shop!', 'error')
            return redirect(url_for('cart'))
        try:
            usage_left = int(voucher.get('usage_limit') or 0)
        except (ValueError, TypeError):
            usage_left = 0
        if usage_left <= 0:
            flash('Mã giảm giá đã hết lượt sử dụng!', 'error')
            return redirect(url_for('cart'))
        try:
            min_order = float(voucher.get('min_order_amount') or 0)
        except (ValueError, TypeError):
            min_order = 0
        if total_amount < min_order:
            formatted_min = '{:,.0f}'.format(min_order)
            flash(f'Đơn hàng tối thiểu phải từ {formatted_min} đ mới được áp dụng mã này!', 'error')
            return redirect(url_for('cart'))
        try:
            discount_raw = float(voucher.get('discount_amount') or 0)
        except (ValueError, TypeError):
            discount_raw = 0
        vtype = (voucher.get('discount_type') or 'FIXED').upper()
        if vtype not in ('FIXED', 'PERCENT'):
            vtype = 'FIXED'  # type lạ (sửa tay trong DB) → coi như giảm tiền cố định cho an toàn
        if vtype == 'PERCENT':
            if discount_raw <= 0 or discount_raw > 100:
                flash('Mã giảm giá % không hợp lệ!', 'error')
                return redirect(url_for('cart'))
            discount_applied = total_amount * discount_raw / 100
            try:
                cap = float(voucher.get('max_discount') or 0)
            except (ValueError, TypeError):
                cap = 0
            if cap > 0 and discount_applied > cap:
                discount_applied = cap
        else:
            discount_applied = discount_raw
        if discount_applied <= 0:
            flash('Mã giảm giá không hợp lệ!', 'error')
            return redirect(url_for('cart'))
        # Chống abuse đơn 0đ: giảm tối đa total-1000đ
        max_discount = max(0, total_amount - 1000)
        if discount_applied > max_discount:
            discount_applied = max_discount
        voucher_id = voucher['id']
        freeship = int(voucher.get('is_freeship') or 0) == 1

    # ---- Phí ship theo vùng + hãng + ngưỡng freeship 500k (chốt: min order 0đ) ----
    ship_zone = None
    shipping_fee = 0
    ship_carrier = None
    if not staff_sale:
        ship_carrier = (request.form.get('ship_carrier') or 'GHN').strip()
        if ship_carrier not in SHIP_CARRIER_FEE:
            ship_carrier = 'GHN'
    freeship_threshold = get_int_setting('freeship_threshold', FREESHIP_THRESHOLD_DEFAULT)
    min_order_amount = get_int_setting('min_order_amount', MIN_ORDER_DEFAULT)
    note = (request.form.get('note') or '').strip()[:1000] or None
    dong_kiem = 1 if request.form.get('dong_kiem') else 0
    channel = 'tai_quay' if staff_sale else 'online'
    try:
        store_id = int(request.form.get('store_id') or 0) or None
    except (ValueError, TypeError):
        store_id = None
    if not staff_sale:
        ship_zone = (request.form.get('ship_zone') or '').strip()
        if ship_zone not in ('noi_thanh', 'ngoai_thanh'):
            flash('Vui lòng chọn khu vực giao hàng!', 'error')
            return redirect(url_for('cart'))
        # merch_total tạm để xét freeship (chưa có ship)
        _tmp_merch = (total_amount - discount_applied)
        # points sẽ trừ sau, nhưng freeship xét trên merch sau giảm voucher/điểm -> tính sau; ở đây xét sơ bộ
        shipping_fee = 0 if ship_zone == 'noi_thanh' else 30000
        shipping_fee += SHIP_CARRIER_FEE.get(ship_carrier, 0)
        if freeship:
            shipping_fee = 0

    # ---- Điểm thưởng: chỉ đơn online (tại quầy không tích/dùng để khỏi lẫn điểm NV) ----
    use_points = 0
    points_discount = 0
    if not staff_sale:
        try:
            use_points = int(request.form.get('use_points') or 0)
        except (ValueError, TypeError):
            use_points = 0
        if use_points < 0:
            flash('Điểm dùng không hợp lệ!', 'error')
            return redirect(url_for('cart'))
        if use_points > 0:
            bal_row = query_db('SELECT points FROM users WHERE id = %s', [current_user.id], one=True)
            balance = int((bal_row or {}).get('points') or 0)
            if use_points > balance:
                flash(f'Bạn chỉ có {balance} điểm!', 'error')
                return redirect(url_for('cart'))
            points_discount = use_points * VND_PER_POINT
            cap_points = max(0, (total_amount - discount_applied) - 1000)
            if points_discount > cap_points:
                points_discount = cap_points
                use_points = int(points_discount // VND_PER_POINT)
                points_discount = use_points * VND_PER_POINT

    # Chốt: 0đ vẫn đặt được -> merch floor 0, min_order đọc từ settings (mặc định 0)
    merch_total = max(0, total_amount - discount_applied - points_discount) if total_amount > 0 else 0
    # ---- Combo tự động (không cần nhập tay): Mua X tặng Y + Set bộ giá gói (có hẹn giờ) ----
    cart_map, eff_map = {}, {}
    for it in cart_items:
        try:
            pid = int(it['product_id'])
        except (ValueError, TypeError):
            continue
        cart_map[pid] = int(cart_map.get(pid) or 0) + int(it.get('quantity') or 0)
        eff_map[pid] = float(it.get('eff_price') or 0)
    auto_gifts, bundle_discount, applied_combos = evaluate_combos(cart_map, eff_map)
    if bundle_discount > 0:
        bundle_discount = min(bundle_discount, merch_total)
        merch_total = max(0, merch_total - bundle_discount)
    if merch_total < min_order_amount:
        flash(f"Đơn tối thiểu {'{:,.0f}'.format(min_order_amount)}đ mới đặt được!", 'error')
        return redirect(url_for('cart'))
    # Freeship từ 500k: override phí zone + phí hãng
    if not staff_sale and merch_total >= freeship_threshold:
        shipping_fee = 0
    final_amount = merch_total + shipping_fee

    # ---- Quà 1 đơn 1 quà ----
    gift_id = None
    try:
        _g = (request.form.get('gift_id') or '').strip()
        gift_id = int(_g) if _g else None
    except (ValueError, TypeError):
        gift_id = None
    if gift_id is not None:
        if not gift_eligible(cart_items, merch_total):
            flash('Đơn chưa đạt điều kiện nhận quà (500k hoặc SP có quà)!', 'error')
            return redirect(url_for('cart'))
        _gift = query_db('SELECT * FROM gifts WHERE id = %s AND is_active = 1', [gift_id], one=True)
        if not _gift or int(_gift.get('stock') or 0) <= 0:
            flash('Quà đã hết!', 'error')
            return redirect(url_for('cart'))
        # Nếu quà có ngưỡng riêng cao hơn merch thì chặn
        try:
            if float(_gift.get('min_order_amount') or 0) > float(merch_total or 0):
                # Ngoại lệ: giỏ có SP has_gift thì vẫn cho lấy
                has_flag = any(int(x.get('has_gift') or 0) == 1 for x in cart_items)
                if not has_flag:
                    flash('Quà này yêu cầu đơn cao hơn!', 'error')
                    return redirect(url_for('cart'))
        except (ValueError, TypeError):
            pass
    
    # Transaction: lock voucher + trừ kho nguyên tử
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute('START TRANSACTION')
            # Lock + re-check voucher
            if voucher_id:
                cur.execute('SELECT usage_limit FROM vouchers WHERE id = %s FOR UPDATE', [voucher_id])
                vrow = cur.fetchone()
                if not vrow or int(vrow.get('usage_limit') or 0) <= 0:
                    db.rollback()
                    flash('Mã giảm giá vừa hết lượt!', 'error')
                    return redirect(url_for('cart'))
            # Lock + re-check stock từng biến thể, trừ kho nguyên tử (variant + tổng SP)
            for item in cart_items:
                if not item.get('variant_id'):
                    db.rollback()
                    flash(f'Sản phẩm "{item["name"]}" thiếu phân loại, vui lòng thêm lại vào giỏ!', 'error')
                    return redirect(url_for('cart'))
                cur.execute('SELECT stock, size, color FROM product_variants WHERE id = %s FOR UPDATE', [item['variant_id']])
                vrow = cur.fetchone()
                if not vrow or int(vrow.get('stock') or 0) < int(item['quantity']):
                    db.rollback()
                    flash(f'Phân loại {vrow.get("size") if vrow else "?"}/{vrow.get("color") if vrow else "?"} của "{item["name"]}" vừa hết hàng!', 'error')
                    return redirect(url_for('cart'))
            # Tạo đơn (ghi đủ fullname/email/discount/voucher/ship/điểm để tương thích DB cũ + thống kê)
            cur.execute('''
                INSERT INTO orders (user_id, fullname, email, total_amount, discount_amount, voucher_code, points_used, points_discount, ship_zone, shipping_fee, ship_carrier, channel, store_id, note, dong_kiem, payment_method, address, phone, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'Chờ thanh toán', NOW())
            ''', [order_owner_id, fullname, email, final_amount, discount_applied + bundle_discount, (voucher_code or None) if voucher_id else None, use_points, points_discount, ship_zone, shipping_fee, ship_carrier, channel, store_id, note, dong_kiem, payment_method, address, phone])
            order_id = cur.lastrowid
            for item in cart_items:
                cur.execute('INSERT INTO order_items (order_id, product_id, variant_id, variant_size, variant_color, quantity, unit_price, is_gift) VALUES (%s, %s, %s, %s, %s, %s, %s, 0)',
                            (order_id, item['product_id'], item['variant_id'], item.get('vsize'), item.get('vcolor'), item['quantity'], float(item['eff_price'])))
                affected = cur.execute('UPDATE product_variants SET stock = stock - %s WHERE id = %s AND stock >= %s',
                                       (item['quantity'], item['variant_id'], item['quantity']))
                if affected == 0:
                    db.rollback()
                    flash(f'Sản phẩm "{item["name"]}" vừa hết hàng!', 'error')
                    return redirect(url_for('cart'))
                cur.execute('UPDATE products SET stock = stock - %s WHERE id = %s', (item['quantity'], item['product_id']))
            if voucher_id:
                cur.execute('UPDATE vouchers SET usage_limit = usage_limit - 1 WHERE id = %s AND usage_limit > 0', [voucher_id])
                if cur.rowcount == 0:
                    db.rollback()
                    flash('Mã giảm giá vừa hết lượt!', 'error')
                    return redirect(url_for('cart'))
            if use_points > 0:
                cur.execute('SELECT points FROM users WHERE id = %s FOR UPDATE', [current_user.id])
                urow = cur.fetchone()
                if not urow or int(urow.get('points') or 0) < use_points:
                    db.rollback()
                    flash('Điểm của bạn không đủ!', 'error')
                    return redirect(url_for('cart'))
                cur.execute('UPDATE users SET points = points - %s WHERE id = %s AND points >= %s', [use_points, current_user.id, use_points])
                if cur.rowcount == 0:
                    db.rollback()
                    flash('Điểm của bạn không đủ!', 'error')
                    return redirect(url_for('cart'))
            # Quà 1 đơn 1 quà: lock + trừ kho quà
            if gift_id is not None:
                cur.execute('SELECT stock FROM gifts WHERE id = %s FOR UPDATE', [gift_id])
                grow = cur.fetchone()
                if not grow or int(grow.get('stock') or 0) <= 0:
                    db.rollback()
                    flash('Quà vừa hết hàng!', 'error')
                    return redirect(url_for('cart'))
                cur.execute('UPDATE gifts SET stock = stock - 1 WHERE id = %s AND stock > 0', [gift_id])
                if cur.rowcount == 0:
                    db.rollback()
                    flash('Quà vừa hết hàng!', 'error')
                    return redirect(url_for('cart'))
                cur.execute('INSERT INTO order_gifts (order_id, gift_id, qty) VALUES (%s, %s, 1)', [order_id, gift_id])
            # Combo tặng SP: trừ kho biến thể còn hàng nhất + ghi dòng quà 0đ
            for _gpid, _gqty, _cb in (auto_gifts or []):
                cur.execute('SELECT id, size, color FROM product_variants WHERE product_id = %s AND stock >= %s ORDER BY stock DESC LIMIT 1',
                            [_gpid, _gqty])
                _gv = cur.fetchone()
                if not _gv:
                    continue
                cur.execute('INSERT INTO order_items (order_id, product_id, variant_id, variant_size, variant_color, quantity, unit_price, is_gift) VALUES (%s,%s,%s,%s,%s,%s,0,1)',
                            (order_id, _gpid, _gv['id'], _gv.get('size'), _gv.get('color'), _gqty))
                cur.execute('UPDATE product_variants SET stock = stock - %s WHERE id = %s AND stock >= %s', [_gqty, _gv['id'], _gqty])
                cur.execute('UPDATE products SET stock = stock - %s WHERE id = %s', [_gqty, _gpid])
            for _cb, _times, _disc in (applied_combos or []):
                try:
                    cur.execute('INSERT INTO order_combos (order_id, combo_id, qty, discount) VALUES (%s,%s,%s,%s)',
                                [order_id, int(_cb.get('id')), int(_times), float(_disc or 0)])
                except Exception:
                    continue
            cur.execute('DELETE FROM cart WHERE user_id = %s', [current_user.id])
            db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        flash('Đặt hàng thất bại, vui lòng thử lại!', 'error')
        return redirect(url_for('cart'))

    # Ghi log SPEND sau commit (điểm đã trừ nguyên tử trong transaction)
    if use_points > 0:
        try:
            execute_db("INSERT INTO point_log (user_id, order_id, points, type) VALUES (%s, %s, %s, 'SPEND')",
                       (current_user.id, order_id, use_points))
        except Exception:
            pass
    try:
        push_notification(order_owner_id, f"Đơn #ORD-{order_id} đã đặt, chờ thanh toán.", f"/my-orders")
        if staff_sale:
            staff_log('Tao don tai quay', order_id, f"Tong {'{:,.0f}'.format(final_amount)}d")
    except Exception:
        pass

    flash('Đặt hàng thành công! Cảm ơn bạn đã mua sắm.', 'success')
    if staff_sale:
        if normalize_payment(payment_method) == 'Chuyển khoản':
            return redirect(url_for('admin_order_qr', order_id=order_id))
        return redirect(url_for('admin_order_detail', order_id=order_id))
    return redirect(url_for('my_orders'))
# Route mới để hiển thị QR
@app.route('/order/<int:order_id>/bill')
@login_required
def order_bill(order_id):
    """Hóa đơn in: chủ đơn hoặc staff/admin đều xem được (staff in cho khách tại quầy)."""
    order = query_db('SELECT * FROM orders WHERE id = %s', [order_id], one=True)
    if not order:
        flash('Không tìm thấy đơn hàng!', 'danger')
        return redirect(url_for('my_orders') if not is_staff_user() else url_for('admin_orders'))
    if not is_staff_user() and order.get('user_id') != int(current_user.id):
        flash('Không tìm thấy đơn hàng!', 'danger')
        return redirect(url_for('my_orders'))
    items = query_db(
        'SELECT order_items.product_id, products.name, order_items.quantity, order_items.unit_price, '
        'order_items.variant_size, order_items.variant_color, order_items.is_gift '
        'FROM order_items JOIN products ON products.id = order_items.product_id WHERE order_items.order_id = %s',
        [order_id])
    seller = query_db('SELECT name, role FROM users WHERE id = %s', [order.get('user_id')], one=True) if order.get('user_id') else None
    subtotal = sum(float(i['unit_price']) * int(i['quantity']) for i in items) if items else float(order.get('total_amount') or 0)
    try:
        combos = query_db('SELECT oc.*, c.name FROM order_combos oc JOIN combos c ON c.id = oc.combo_id WHERE oc.order_id = %s', [order_id]) or []
    except Exception:
        combos = []
    try:
        store = query_db('SELECT branch_name, province FROM stores WHERE id = %s', [order.get('store_id')], one=True) if order.get('store_id') else None
    except Exception:
        store = None
    exchanges = query_db('''SELECT r.created_at, ov.size AS osize, ov.color AS ocolor, nv.size AS nsize, nv.color AS ncolor
                            FROM return_requests r
                            LEFT JOIN product_variants ov ON ov.id = r.old_variant_id
                            LEFT JOIN product_variants nv ON nv.id = r.new_variant_id
                            WHERE r.order_id = %s AND r.status = 'Hoàn thành' ORDER BY r.created_at''', [order_id])
    try:
        gift = query_db('SELECT g.name FROM order_gifts og JOIN gifts g ON g.id = og.gift_id WHERE og.order_id = %s', [order_id], one=True)
    except Exception:
        gift = None
    return render_template('order_bill.html', order=order, items=items or [], seller=seller,
                           subtotal=subtotal, today=date.today().strftime('%d/%m/%Y'), exchanges=exchanges or [],
                           gift=(gift or {}).get('name'), combos=combos, store=store)
@app.route('/payment-info/<int:order_id>')
@login_required
def payment_info(order_id):
    order = query_db('SELECT * FROM orders WHERE id = %s AND user_id = %s', [order_id, current_user.id], one=True)
    if not order:
        flash('Không tìm thấy đơn hàng!', 'danger')
        return redirect(url_for('my_orders'))
    pm = normalize_payment(order.get('payment_method'))
    if pm != 'Chuyển khoản' or order.get('status') != 'Chờ thanh toán':
        flash('Đơn này không cần thanh toán QR!', 'warning')
        return redirect(url_for('my_orders'))
    return render_template('payment_info.html', order=order, bank_accounts=get_setting('shop_bank_accounts', ''))


@app.route('/admin/order/<int:order_id>/qr')
@login_required
def admin_order_qr(order_id):
    """QR thu ngân tại quầy: staff cho khách quét sau khi lên đơn Chuyển khoản."""
    if not is_staff_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    order = query_db('SELECT * FROM orders WHERE id = %s', [order_id], one=True)
    if not order:
        flash('Không tìm thấy đơn hàng!', 'danger')
        return redirect(url_for('admin_orders'))
    if order.get('status') != 'Chờ thanh toán' or normalize_payment(order.get('payment_method')) != 'Chuyển khoản':
        flash('Đơn này không ở trạng thái chờ quét QR!', 'warning')
        return redirect(url_for('admin_order_detail', order_id=order_id))
    items = query_db(
        'SELECT order_items.quantity, order_items.unit_price, products.name '
        'FROM order_items JOIN products ON products.id = order_items.product_id WHERE order_items.order_id = %s',
        [order_id])
    return render_template('admin_order_qr.html', order=order, items=items or [],
                           bank_accounts=get_setting('shop_bank_accounts', ''))


@app.route('/admin/order/<int:order_id>/complete', methods=['POST'])
@login_required
def admin_order_complete(order_id):
    """Thu ngân bấm sau khi khách đã quét QR: chốt đơn Hoàn thành ngay."""
    if not is_staff_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    order = query_db('SELECT user_id, status, payment_method, total_amount FROM orders WHERE id = %s', [order_id], one=True)
    if not order:
        flash('Không tìm thấy đơn hàng!', 'danger')
        return redirect(url_for('admin_orders'))
    if order.get('status') != 'Chờ thanh toán' or normalize_payment(order.get('payment_method')) != 'Chuyển khoản':
        flash('Đơn này không ở trạng thái chờ quét QR!', 'warning')
        return redirect(url_for('admin_order_detail', order_id=order_id))
    db = get_db()
    try:
        with db.cursor() as cur:
            affected = cur.execute("UPDATE orders SET status = 'Hoàn thành' WHERE id = %s AND status = 'Chờ thanh toán'", [order_id])
    except Exception:
        affected = 0
    if not affected:
        flash('Đơn vừa được xử lý ở nơi khác!', 'warning')
        return redirect(url_for('admin_order_detail', order_id=order_id))
    try:
        earned = earn_points_for_order(order_id, order.get('user_id'), order.get('total_amount'))
    except Exception:
        earned = 0
    try:
        push_notification(order.get('user_id'), f"Đơn #ORD-{order_id} đã thanh toán và hoàn thành. Cảm ơn bạn!", "/my-orders")
        staff_log('Thu QR hoan thanh', order_id, f"Tong {'{:,.0f}'.format(float(order.get('total_amount') or 0))}d")
    except Exception:
        pass
    if earned:
        flash(f'Đã thu tiền và hoàn thành đơn! Khách được tích {earned} điểm.', 'success')
    else:
        flash('Đã thu tiền và hoàn thành đơn!', 'success')
    return redirect(url_for('admin_order_detail', order_id=order_id))

@app.route('/confirm-payment/<int:order_id>', methods=['POST'])
@login_required
def confirm_payment(order_id):
    # Chỉ chủ đơn, đúng trạng thái Chờ thanh toán + Chuyển khoản mới được xác nhận
    order = query_db('SELECT user_id, status, payment_method FROM orders WHERE id = %s', [order_id], one=True)
    if not order or order.get('user_id') != int(current_user.id):
        flash('Không tìm thấy đơn hàng!', 'error')
        return redirect(url_for('my_orders'))
    if order.get('status') != 'Chờ thanh toán' or normalize_payment(order.get('payment_method')) != 'Chuyển khoản':
        flash('Đơn này không ở trạng thái chờ thanh toán!', 'warning')
        return redirect(url_for('my_orders'))
    execute_db('UPDATE orders SET status = %s WHERE id = %s AND status = %s', ('Chờ xác nhận', order_id, 'Chờ thanh toán'))
    try:
        push_notification(order.get('user_id'), f"Đơn #ORD-{order_id} đã báo chuyển khoản, chờ shop xác nhận.", "/my-orders")
    except Exception:
        pass
    flash('Đã xác nhận chuyển khoản! Shop sẽ kiểm tra và xác nhận đơn hàng sớm nhất.', 'success')
    return redirect(url_for('my_orders'))

@app.route('/my-orders')
@login_required
def my_orders():
    try:
        page = int(request.args.get('page', 1))
    except (ValueError, TypeError):
        page = 1
    if page < 1:
        page = 1
    selected_date = request.args.get('date', '').strip()
    per_page = 5  
    
    where_clause = "user_id = %s"
    params = [current_user.id]
    
    if selected_date:
        where_clause += " AND DATE(created_at) = %s"
        params.append(selected_date)
        
    cnt_row = query_db(f'SELECT COUNT(id) as cnt FROM orders WHERE {where_clause}', params, one=True)
    total_orders = cnt_row['cnt'] if cnt_row and cnt_row.get('cnt') else 0
    total_pages = max(1, math.ceil(total_orders / per_page)) if total_orders > 0 else 1
    if page > total_pages:
        page = total_pages
    offset = (page - 1) * per_page
    
    orders = query_db(f'SELECT * FROM orders WHERE {where_clause} ORDER BY created_at DESC LIMIT %s OFFSET %s', params + [per_page, offset])
    
    for order in orders:
        items = query_db(
            'SELECT order_items.id AS line_id, order_items.product_id, products.name, products.image, order_items.quantity, order_items.unit_price, '
            'order_items.variant_id, order_items.variant_size, order_items.variant_color, order_items.is_gift '
            'FROM order_items JOIN products ON products.id = order_items.product_id WHERE order_items.order_id = %s',
            [order['id']]
        )
        # Map yêu cầu đổi size đang chờ của các dòng trong đơn này
        pend = query_db("SELECT order_item_id, status FROM return_requests WHERE order_id = %s AND status = 'Chờ duyệt'", [order['id']])
        pend_map = {p['order_item_id']: p['status'] for p in (pend or [])}
        
        # Kiểm tra xem user hiện tại đã đánh giá sản phẩm này chưa
        for item in items:
            reviewed = query_db('SELECT id FROM reviews WHERE product_id = %s AND name = %s', [item['product_id'], (current_user.name or '').strip()], one=True)
            item['has_reviewed'] = True if reviewed else False
            item['exchange_pending'] = item.get('line_id') in pend_map
            # Chặn đổi Sale/Phụ kiện ngay ở list đơn
            _p = query_db('SELECT price, sale_price, sale_start, sale_end, category FROM products WHERE id = %s', [item['product_id']], one=True)
            _blocked, _ = is_exchange_blocked(_p) if _p else (False, '')
            item['exchange_blocked'] = _blocked

        try:
            _g = query_db('SELECT g.name FROM order_gifts og JOIN gifts g ON g.id = og.gift_id WHERE og.order_id = %s', [order['id']], one=True)
            order['gift_name'] = (_g or {}).get('name')
        except Exception:
            order['gift_name'] = None
        try:
            order['combos'] = query_db('SELECT oc.*, c.name FROM order_combos oc JOIN combos c ON c.id = oc.combo_id WHERE oc.order_id = %s', [order['id']]) or []
        except Exception:
            order['combos'] = []
        order['order_items'] = items
        
    return render_template('my_orders.html', orders=orders, page=page, total_pages=total_pages, selected_date=selected_date)

# ==========================================
# Phase 4 — BẢNG SIZE + GỢI Ý SIZE (public, rule đơn giản)
# ==========================================
SIZE_GUIDE = [
    {'size': 'S', 'chest': '84-88', 'waist': '66-70', 'weight': '< 45kg', 'height': '< 158cm'},
    {'size': 'M', 'chest': '88-92', 'waist': '70-74', 'weight': '45-55kg', 'height': '158-165cm'},
    {'size': 'L', 'chest': '92-96', 'waist': '74-78', 'weight': '55-65kg', 'height': '165-172cm'},
    {'size': 'XL', 'chest': '96-100', 'waist': '78-84', 'weight': '65-75kg', 'height': '172-178cm'},
    {'size': 'XXL', 'chest': '100-106', 'waist': '84-90', 'weight': '> 75kg', 'height': '> 178cm'},
]

def suggest_size(height_cm, weight_kg):
    """Map chiều cao/cân nặng về size S-XXL. Rule minh bạch, chỉ tham khảo."""
    try:
        h, w = float(height_cm), float(weight_kg)
    except (ValueError, TypeError):
        return None
    if h <= 0 or w <= 0 or h > 250 or w > 300:
        return None
    if w < 45:
        base = 0
    elif w < 55:
        base = 1
    elif w < 65:
        base = 2
    elif w < 75:
        base = 3
    else:
        base = 4
    if h >= 170 and w < 60 and base < 4:
        base += 1  # cao + nhẹ cân: tăng 1 size lấy độ dài
    elif h < 155 and base > 0:
        base -= 1
    order = ['S', 'M', 'L', 'XL', 'XXL']
    return order[base]


@app.route('/size-guide')
def size_guide():
    height = (request.args.get('height') or '').strip()
    weight = (request.args.get('weight') or '').strip()
    suggested = suggest_size(height, weight) if height and weight else None
    tried = bool(height or weight)
    return render_template('size_guide.html', guide=SIZE_GUIDE, height=height, weight=weight,
                           suggested=suggested, tried=tried)

# ==========================================
# Phase 4 — BÁO CÁO TỒN/BÁN CHẠY THEO SIZE-MÀU (chỉ admin)
# ==========================================
@app.route('/admin/stock-report')
@login_required
def admin_stock_report():
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    # Bán chạy theo size/màu (chỉ đơn Hoàn thành)
    by_size = query_db('''SELECT oi.variant_size AS label, SUM(oi.quantity) AS sold
                          FROM order_items oi JOIN orders o ON o.id = oi.order_id
                          WHERE o.status = 'Hoàn thành' AND oi.variant_size IS NOT NULL
                          GROUP BY oi.variant_size ORDER BY sold DESC''')
    by_color = query_db('''SELECT oi.variant_color AS label, SUM(oi.quantity) AS sold
                           FROM order_items oi JOIN orders o ON o.id = oi.order_id
                           WHERE o.status = 'Hoàn thành' AND oi.variant_color IS NOT NULL
                           GROUP BY oi.variant_color ORDER BY sold DESC''')
    # Tồn kho theo biến thể + lần bán gần nhất
    stock_rows = query_db('''SELECT v.id, v.product_id, v.size, v.color, v.stock, p.name,
                             (SELECT MAX(o.created_at) FROM order_items oi JOIN orders o ON o.id = oi.order_id
                              WHERE oi.variant_id = v.id AND o.status = 'Hoàn thành') AS last_sold,
                             (SELECT COALESCE(SUM(oi.quantity),0) FROM order_items oi JOIN orders o ON o.id = oi.order_id
                              WHERE oi.variant_id = v.id AND o.status = 'Hoàn thành'
                              AND o.created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)) AS sold_30d
                             FROM product_variants v JOIN products p ON p.id = v.product_id
                             WHERE p.is_active = 1 ORDER BY v.stock DESC''')
    from datetime import timedelta
    cutoff = datetime.now() - timedelta(days=90)
    for r in stock_rows or []:
        sold30 = int(r.get('sold_30d') or 0)
        stock = int(r.get('stock') or 0)
        last = r.get('last_sold')
        if stock <= 0 and sold30 > 0:
            r['tip'], r['tip_class'] = 'Cháy hàng — nhập thêm ngay', 'danger'
        elif stock > 0 and sold30 >= stock and sold30 > 0:
            r['tip'], r['tip_class'] = 'Bán nhanh — sắp hết, nhập thêm', 'warning'
        elif stock >= 20 and sold30 == 0 and (not last or last < cutoff):
            r['tip'], r['tip_class'] = 'Tồn chết (>90 ngày không bán) — đưa vào sale', 'secondary'
        elif stock > 0 and sold30 == 0:
            r['tip'], r['tip_class'] = 'Chưa bán 30 ngày qua — theo dõi', 'info'
        else:
            r['tip'], r['tip_class'] = 'Ổn định', 'success'
    return render_template('admin_stock_report.html', by_size=by_size or [], by_color=by_color or [],
                           stock_rows=stock_rows or [])

# ==========================================
# AUTH
# ==========================================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        if not verify_recaptcha(request.form.get('g-recaptcha-response', '')):
            flash('Xác minh chống spam thất bại, thử lại!', 'danger')
            return render_template('register.html', form=form)
        email_norm = (form.email.data or '').strip().lower()
        name_norm = (form.name.data or '').strip()
        if not name_norm or len(name_norm) < 2:
            flash('Họ tên không hợp lệ!', 'danger')
            return render_template('register.html', form=form)
        existing_user = query_db('SELECT id FROM users WHERE email = %s', [email_norm], one=True)
        if existing_user:
            flash('Email này đã được sử dụng!', 'danger')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(form.password.data)
        need_verify = (get_setting('require_email_verify', '1') or '1').strip() == '1'
        try:
            uid = execute_db(
                'INSERT INTO users (name, email, password, is_admin, role, email_verified) VALUES (%s, %s, %s, %s, %s, %s)',
                (name_norm, email_norm, hashed_password, 0, 'Khách hàng', 0 if need_verify else 1),
                lastrowid=True,
            )
        except Exception as e:
            # Race trùng email (UNIQUE)
            if 'Duplicate' in str(e):
                flash('Email này đã được sử dụng!', 'danger')
                return redirect(url_for('register'))
            flash('Đăng ký thất bại, thử lại!', 'danger')
            return render_template('register.html', form=form)
        if need_verify:
            try:
                token = _verify_serializer().dumps(email_norm)
                link = url_for('verify_email', token=token, _external=False)
                flash('Đăng ký thành công! Vui lòng xác thực email trước khi đăng nhập.', 'success')
                return render_template('register.html', form=form, verify_link=link)
            except Exception:
                pass
        flash('Đăng ký thành công! Hãy đăng nhập.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html', form=form, verify_link=None)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    form = LoginForm()
    if form.validate_on_submit():
        email_norm = (form.email.data or '').strip().lower()
        user = query_db('SELECT * FROM users WHERE email = %s', [email_norm], one=True)
        stored = _get_stored_password(user) if user else None
        if user and int(user.get('email_verified', 1) or 0) == 0 and (user.get('role') == 'Khách hàng'):
            flash('Email chưa xác thực! Vui lòng bấm link xác thực đã nhận khi đăng ký.', 'warning')
            return render_template('login.html', form=form)
        if user and verify_password(stored, form.password.data):
            user_obj = User(user['id'], user['name'], user['email'], user.get('is_admin', 0), user.get('role', 'Khách hàng'))
            login_user(user_obj)
            flash('Đăng nhập thành công!', 'success')
            nxt = request.args.get('next')
            # Chống open-redirect
            if nxt and nxt.startswith('/') and not nxt.startswith('//'):
                return redirect(nxt)
            return redirect(url_for('index'))
        else:
            flash('Email hoặc mật khẩu không chính xác!', 'danger')
            
    return render_template('login.html', form=form)

@app.route('/logout', methods=['POST', 'GET'])
@login_required
def logout():
    logout_user()
    flash('Đã đăng xuất!', 'info')
    return redirect(url_for('index'))

def _reset_serializer():
    from itsdangerous import URLSafeTimedSerializer
    return URLSafeTimedSerializer(app.config['SECRET_KEY'], salt='pw-reset-v1')


def _verify_serializer():
    from itsdangerous import URLSafeTimedSerializer
    return URLSafeTimedSerializer(app.config['SECRET_KEY'], salt='email-verify-v1')


@app.route('/verify/<token>')
def verify_email(token):
    from itsdangerous import BadSignature, SignatureExpired
    try:
        email_norm = _verify_serializer().loads(token, max_age=86400)
    except SignatureExpired:
        flash('Link xác thực hết hạn (24h)! Hãy đăng ký lại hoặc liên hệ shop.', 'danger')
        return redirect(url_for('register'))
    except BadSignature:
        flash('Link xác thực không hợp lệ!', 'danger')
        return redirect(url_for('register'))
    execute_db('UPDATE users SET email_verified = 1 WHERE email = %s', [email_norm])
    flash('Xác thực email thành công! Hãy đăng nhập.', 'success')
    return redirect(url_for('login'))

@app.route('/forgot', methods=['GET', 'POST'])
def forgot():
    """Quên mật khẩu (khu khách): nhập email → nhận link reset. Không đụng logic admin/NV."""
    if current_user.is_authenticated:
        return redirect(url_for('profile'))
    reset_link = None
    if request.method == 'POST':
        email_norm = (request.form.get('email') or '').strip().lower()
        if not email_norm or '@' not in email_norm:
            flash('Vui lòng nhập email hợp lệ!', 'danger')
            return render_template('forgot.html', reset_link=None)
        user = query_db('SELECT id, email FROM users WHERE email = %s', [email_norm], one=True)
        # Luôn báo chung để chống dò email, nhưng demo chưa có SMTP nên hiện link ngay khi email tồn tại
        if user:
            token = _reset_serializer().dumps(email_norm)
            reset_link = url_for('reset_password', token=token, _external=False)
            app.logger.info('RESET-LINK for %s: %s', email_norm, reset_link)
        flash('Nếu email tồn tại trong hệ thống, link đặt lại mật khẩu đã được tạo (hiệu lực 1 giờ).', 'info')
        return render_template('forgot.html', reset_link=reset_link)
    return render_template('forgot.html', reset_link=None)

@app.route('/reset/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Đặt MK mới từ token (hiệu lực 1 giờ)."""
    if current_user.is_authenticated:
        return redirect(url_for('profile'))
    from itsdangerous import BadSignature, SignatureExpired
    try:
        email_norm = _reset_serializer().loads(token, max_age=3600)
    except SignatureExpired:
        flash('Link đã hết hạn (quá 1 giờ)! Vui lòng tạo link mới.', 'danger')
        return redirect(url_for('forgot'))
    except BadSignature:
        flash('Link không hợp lệ!', 'danger')
        return redirect(url_for('forgot'))
    if request.method == 'POST':
        pw1 = request.form.get('new_password') or ''
        pw2 = request.form.get('confirm_password') or ''
        if pw1 != pw2:
            flash('Mật khẩu nhập lại không khớp!', 'danger')
            return render_template('reset.html', token=token)
        if len(pw1) < 6:
            flash('Mật khẩu phải từ 6 ký tự!', 'danger')
            return render_template('reset.html', token=token)
        user = query_db('SELECT id FROM users WHERE email = %s', [email_norm], one=True)
        if not user:
            flash('Tài khoản không còn tồn tại!', 'danger')
            return redirect(url_for('forgot'))
        execute_db('UPDATE users SET password = %s WHERE email = %s', (generate_password_hash(pw1), email_norm))
        flash('Đổi mật khẩu thành công! Hãy đăng nhập.', 'success')
        return redirect(url_for('login'))
    return render_template('reset.html', token=token)

@app.route('/wishlist')
@login_required
def wishlist():
    # Wishlist là mua cho mình → staff/admin dùng trang bán tại quầy thay vì wishlist
    if is_staff_user():
        flash('Tài khoản bán hàng không dùng danh sách yêu thích!', 'warning')
        return redirect(url_for('admin_dashboard'))
    products = query_db('SELECT p.* FROM products p JOIN wishlist w ON p.id = w.product_id WHERE w.user_id = %s ORDER BY w.created_at DESC', [current_user.id])
    apply_pricing(products)
    return render_template('wishlist.html', products=products)

@app.route('/wishlist/toggle/<int:product_id>', methods=['POST'])
@login_required
def toggle_wishlist(product_id):
    if is_staff_user():
        flash('Tài khoản bán hàng không dùng danh sách yêu thích!', 'warning')
        return redirect(request.referrer or url_for('admin_dashboard'))
    # Chặn wishlist hàng ẩn
    prod = query_db('SELECT id FROM products WHERE id = %s AND is_active = 1', [product_id], one=True)
    if not prod:
        flash('Sản phẩm không tồn tại!', 'error')
        return redirect(request.referrer or url_for('index'))
    exists = query_db('SELECT * FROM wishlist WHERE user_id = %s AND product_id = %s', [current_user.id, product_id], one=True)
    if exists:
        execute_db('DELETE FROM wishlist WHERE user_id = %s AND product_id = %s', (current_user.id, product_id))
        flash('Đã gỡ khỏi danh sách yêu thích.', 'info')
    else:
        try:
            execute_db('INSERT INTO wishlist (user_id, product_id) VALUES (%s, %s)', (current_user.id, product_id))
            flash('Đã lưu vào danh sách yêu thích!', 'success')
        except Exception as e:
            if 'Duplicate' in str(e):
                flash('Đã có trong danh sách yêu thích!', 'info')
            else:
                raise
    return redirect(request.referrer or url_for('index'))


# QUẢN TRỊ (ADMIN)

@app.route('/admin')
@login_required
def admin_dashboard():
    if not is_staff_user(): 
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    
    current_month = request.args.get('month_num', date.today().strftime('%m'))
    current_year = request.args.get('year_num', date.today().strftime('%Y'))
    # Validate tháng/năm
    if current_month not in [f'{m:02d}' for m in range(1, 13)]:
        current_month = date.today().strftime('%m')
    if current_year not in ['2024', '2025', '2026', '2027']:
        current_year = date.today().strftime('%Y')
    
    monthly_stats = query_db("SELECT COUNT(id) as total_completed, SUM(total_amount) as total_revenue FROM orders WHERE YEAR(created_at) = %s AND MONTH(created_at) = %s AND status = 'Hoàn thành'", [current_year, current_month], one=True)
    total_monthly_orders = query_db("SELECT COUNT(id) as total_all FROM orders WHERE YEAR(created_at) = %s AND MONTH(created_at) = %s", [current_year, current_month], one=True)
    
    monthly_revenue = monthly_stats['total_revenue'] if monthly_stats and monthly_stats['total_revenue'] else 0
    monthly_orders_count = monthly_stats['total_completed'] if monthly_stats and monthly_stats['total_completed'] else 0
    total_all = total_monthly_orders['total_all'] if total_monthly_orders and total_monthly_orders['total_all'] else 0
    
    efficiency_rate = (monthly_orders_count / total_all) * 100 if total_all > 0 else 0
    
    # Chỉ đếm hàng đang bán
    products = query_db('SELECT id FROM products WHERE is_active = 1 ORDER BY id DESC')
    # GIỚI HẠN CHỈ LẤY 6 ĐƠN MỚI NHẤT
    orders = query_db('SELECT * FROM orders ORDER BY created_at DESC LIMIT 6') 
    low_stock = query_db('SELECT * FROM products WHERE is_active = 1 AND stock <= 5 ORDER BY stock ASC')

    # Dữ liệu thật cho biểu đồ: doanh thu theo category + theo tháng
    try:
        cat_rows = query_db('''SELECT p.category AS cat, SUM(oi.quantity * oi.unit_price) AS rev
                               FROM order_items oi JOIN products p ON p.id = oi.product_id
                               JOIN orders o ON o.id = oi.order_id
                               WHERE o.status = 'Hoàn thành' AND YEAR(o.created_at)=%s AND MONTH(o.created_at)=%s
                               GROUP BY p.category''', [current_year, current_month])
    except Exception:
        cat_rows = []
    try:
        trend_rows = query_db('''SELECT MONTH(created_at) AS m, SUM(total_amount) AS rev FROM orders
                                 WHERE status='Hoàn thành' AND YEAR(created_at)=%s GROUP BY MONTH(created_at) ORDER BY m''', [current_year])
    except Exception:
        trend_rows = []
    
    return render_template('admin.html', products=products, orders=orders, low_stock=low_stock, monthly_revenue=monthly_revenue, monthly_orders_count=monthly_orders_count, efficiency_rate=efficiency_rate, current_month=current_month, current_year=current_year, cat_rows=cat_rows or [], trend_rows=trend_rows or [])

@app.route('/admin/users', methods=['GET', 'POST'])
@login_required
def admin_users():
    
    if not is_admin_user():
        flash('Bạn không có quyền truy cập trang này!', 'danger')
        return redirect(url_for('index'))
        
    form = AdminAddUserForm()
    if form.validate_on_submit():
        email_norm = (form.email.data or '').strip().lower()
        existing_user = query_db('SELECT id FROM users WHERE email = %s', [email_norm], one=True)
        if existing_user:
            flash('Email này đã tồn tại trong hệ thống!', 'danger')
            users = query_db('SELECT id, name, email, is_admin, role, created_at FROM users ORDER BY id DESC')
            return render_template('admin_users.html', form=form, users=users, show_modal=True)
            
        hashed_password = generate_password_hash(form.password.data)
        role = form.role.data # 'Nhân viên' hoặc 'Admin'
        if role not in ('Nhân viên', 'Admin'):
            flash('Vai trò không hợp lệ!', 'danger')
            return redirect(url_for('admin_users'))
        is_admin = 1 if role == 'Admin' else 0
        
        try:
            execute_db(
                'INSERT INTO users (name, email, password, is_admin, role) VALUES (%s, %s, %s, %s, %s)',
                ((form.name.data or '').strip(), email_norm, hashed_password, is_admin, role)
            )
        except Exception as e:
            if 'Duplicate' in str(e):
                flash('Email này đã tồn tại trong hệ thống!', 'danger')
                users = query_db('SELECT id, name, email, is_admin, role, created_at FROM users ORDER BY id DESC')
                return render_template('admin_users.html', form=form, users=users, show_modal=True)
            raise
        flash(f'Đã thêm tài khoản {role} thành công!', 'success')
        return redirect(url_for('admin_users'))

    users = query_db('SELECT id, name, email, is_admin, role, created_at FROM users ORDER BY id DESC')
    show_modal = request.method == 'POST' and bool(form.errors)
    return render_template('admin_users.html', form=form, users=users, show_modal=show_modal)
@app.route('/admin/customers')
@login_required
def admin_customers():
    if not is_admin_user(): 
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    # FIX double-count: tổng tiền phải SUM DISTINCT theo order, không JOIN trực tiếp
    customers = query_db('''SELECT o.phone, MAX(o.fullname) AS fullname, MAX(o.email) AS email,
        COUNT(DISTINCT o.id) AS order_count,
        (SELECT SUM(oi2.quantity) FROM order_items oi2 JOIN orders o2 ON oi2.order_id=o2.id WHERE o2.phone=o.phone) AS total_items,
        SUM(o.total_amount) AS total_spent
        FROM orders o GROUP BY o.phone ORDER BY total_spent DESC''')
    return render_template('admin_customers.html', customers=customers)

@app.route('/admin/customer/<phone>')
@login_required
def admin_customer_detail(phone):
    if not is_admin_user(): 
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    phone = (phone or '').strip()[:20]
    customer = query_db('''SELECT o.phone, MAX(o.fullname) AS fullname, MAX(o.email) AS email,
        COUNT(DISTINCT o.id) AS order_count,
        (SELECT SUM(oi2.quantity) FROM order_items oi2 JOIN orders o2 ON oi2.order_id=o2.id WHERE o2.phone=%s) AS total_items,
        SUM(o.total_amount) AS total_spent FROM orders o WHERE o.phone = %s GROUP BY o.phone''', [phone, phone], one=True)
    if not customer:
        flash('Không tìm thấy khách hàng!', 'warning')
        return redirect(url_for('admin_customers'))
    orders = query_db('SELECT id, fullname, email, phone, address, total_amount, created_at, status FROM orders WHERE phone = %s ORDER BY created_at DESC', [phone])
    for order in orders:
        order['order_details'] = query_db('SELECT products.name, order_items.quantity, order_items.unit_price, order_items.variant_size, order_items.variant_color FROM order_items JOIN products ON products.id = order_items.product_id WHERE order_items.order_id = %s', [order['id']])
    return render_template('admin_customer_detail.html', customer=customer, orders=orders)

# CHI TIẾT 1 ĐƠN (staff/admin): xem item + khách + voucher + người bán. Bảng list giữ nguyên, chỉ thêm link vào.
@app.route('/admin/order/<int:order_id>')
@login_required
def admin_order_detail(order_id):
    if not is_staff_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    order = query_db('SELECT * FROM orders WHERE id = %s', [order_id], one=True)
    if not order:
        flash('Không tìm thấy đơn hàng!', 'danger')
        return redirect(url_for('admin_orders'))
    items = query_db(
        'SELECT order_items.product_id, products.name, products.image, order_items.quantity, order_items.unit_price, '
        'order_items.variant_size, order_items.variant_color, order_items.is_gift '
        'FROM order_items JOIN products ON products.id = order_items.product_id WHERE order_items.order_id = %s',
        [order_id])
    seller = query_db('SELECT name, email, role FROM users WHERE id = %s', [order.get('user_id')], one=True) if order.get('user_id') else None
    voucher = query_db('SELECT * FROM vouchers WHERE code = %s', [order.get('voucher_code')], one=True) if order.get('voucher_code') else None
    subtotal = sum(float(i['unit_price']) * int(i['quantity']) for i in items) if items else float(order.get('total_amount') or 0)
    exchanges = query_db('''SELECT r.id, r.created_at, r.status, ov.size AS osize, ov.color AS ocolor,
                            nv.size AS nsize, nv.color AS ncolor
                            FROM return_requests r
                            LEFT JOIN product_variants ov ON ov.id = r.old_variant_id
                            LEFT JOIN product_variants nv ON nv.id = r.new_variant_id
                            WHERE r.order_id = %s ORDER BY r.created_at''', [order_id])
    # Đơn khác cùng SĐT khách (để đối chiếu lịch sử mua)
    same_phone = []
    if order.get('phone'):
        same_phone = query_db('SELECT id, total_amount, status, created_at FROM orders WHERE phone = %s AND id != %s ORDER BY created_at DESC LIMIT 5',
                              [order['phone'], order_id])
    try:
        gift = query_db('SELECT g.name FROM order_gifts og JOIN gifts g ON g.id = og.gift_id WHERE og.order_id = %s', [order_id], one=True)
    except Exception:
        gift = None
    try:
        combos = query_db('SELECT oc.*, c.name FROM order_combos oc JOIN combos c ON c.id = oc.combo_id WHERE oc.order_id = %s', [order_id]) or []
    except Exception:
        combos = []
    try:
        store = query_db('SELECT branch_name, province FROM stores WHERE id = %s', [order.get('store_id')], one=True) if order.get('store_id') else None
    except Exception:
        store = None
    try:
        logs = query_db('SELECT l.*, u.name AS uname FROM staff_logs l JOIN users u ON u.id = l.user_id WHERE l.order_id = %s ORDER BY l.id DESC LIMIT 10', [order_id]) or []
    except Exception:
        logs = []
    return render_template('admin_order_detail.html', order=order, items=items or [], seller=seller,
                           voucher=voucher, subtotal=subtotal, same_phone=same_phone or [], exchanges=exchanges or [],
                           gift=(gift or {}).get('name'), combos=combos, store=store, logs=logs)

# QUẢN LÝ ĐƠN HÀNG (Lọc theo ngày + Phân trang 10 dòng, default xem TẤT CẢ)
@app.route('/admin/orders')
@login_required
def admin_orders():
    if not is_staff_user(): 
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
        
    try:
        page = int(request.args.get('page', 1))
    except (ValueError, TypeError):
        page = 1
    if page < 1:
        page = 1
    # Không default today nữa: rỗng = xem tất cả, fix bug nút X không clear được
    selected_date = (request.args.get('date') or '').strip()
    per_page = 10
    
    where_clause = "1=1"
    params = []
    
    if selected_date:
        where_clause = "DATE(created_at) = %s"
        params.append(selected_date)
        
    cnt_row = query_db(f'SELECT COUNT(id) as cnt FROM orders WHERE {where_clause}', params, one=True)
    total_orders = cnt_row['cnt'] if cnt_row and cnt_row.get('cnt') else 0
    total_pages = max(1, math.ceil(total_orders / per_page)) if total_orders > 0 else 1
    if page > total_pages:
        page = total_pages
    offset = (page - 1) * per_page
    
    orders = query_db(f'SELECT * FROM orders WHERE {where_clause} ORDER BY created_at DESC LIMIT %s OFFSET %s', params + [per_page, offset])
    
    orders_data = []
    for o in orders:
        cnt = query_db('SELECT SUM(quantity) as total_qty FROM order_items WHERE order_id = %s', [o['id']], one=True)
        item_cnt = cnt['total_qty'] if cnt and cnt.get('total_qty') else 0
        orders_data.append({'order': o, 'item_count': item_cnt})

    return render_template('admin_orders.html', orders_data=orders_data, page=page, total_pages=total_pages, selected_date=selected_date)


@app.route('/admin/products')
@login_required
def admin_products():
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    tab = (request.args.get('tab') or 'active').strip()
    if tab not in ('active', 'hidden', 'all'):
        tab = 'active'
    if tab == 'active':
        products = query_db('SELECT * FROM products WHERE is_active = 1 ORDER BY id DESC')
    elif tab == 'hidden':
        products = query_db('SELECT * FROM products WHERE is_active = 0 ORDER BY id DESC')
    else:
        products = query_db('SELECT * FROM products ORDER BY id DESC')
    counts = {
        'active': query_db('SELECT COUNT(id) AS c FROM products WHERE is_active = 1', [], one=True)['c'] or 0,
        'hidden': query_db('SELECT COUNT(id) AS c FROM products WHERE is_active = 0', [], one=True)['c'] or 0,
    }
    return render_template('admin_products.html', products=products, tab=tab, counts=counts)

@app.route('/admin/product/add', methods=['GET', 'POST'])
@login_required
def admin_add_product():
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    form = ProductForm()
    if form.validate_on_submit():
        try:
            price_val = float(form.price.data)
        except (ValueError, TypeError):
            flash('Giá không hợp lệ!', 'danger')
            return render_template('admin_product_form.html', form=form, action='Thêm Sản Phẩm', sizes=SIZES, colors=COLORS)
        if price_val < 0:
            flash('Giá không được âm!', 'danger')
            return render_template('admin_product_form.html', form=form, action='Thêm Sản Phẩm', sizes=SIZES, colors=COLORS)
        serrs, sale_price, sale_start, sale_end = parse_sale(price_val, form.sale_price.data, form.sale_start.data, form.sale_end.data)
        if serrs:
            for e in serrs:
                flash(e, 'danger')
            return render_template('admin_product_form.html', form=form, action='Thêm Sản Phẩm', sizes=SIZES, colors=COLORS)
        verrs, variants = parse_variant_lines(form.variants.data)
        if verrs:
            for e in verrs:
                flash(e, 'danger')
            return render_template('admin_product_form.html', form=form, action='Thêm Sản Phẩm', sizes=SIZES, colors=COLORS)
        if not variants:
            # Không nhập biến thể → 1 biến thể mặc định, SL lấy từ ô số lượng
            try:
                stock_val = int(form.stock.data or 0)
            except (ValueError, TypeError):
                stock_val = 0
            if stock_val < 0:
                flash('Số lượng không được âm!', 'danger')
                return render_template('admin_product_form.html', form=form, action='Thêm Sản Phẩm', sizes=SIZES, colors=COLORS)
            variants = [(DEFAULT_SIZE, DEFAULT_COLOR, stock_val)]
        ferrs, faqs = parse_faq_lines(form.faqs.data)
        if ferrs:
            for e in ferrs:
                flash(e, 'danger')
            return render_template('admin_product_form.html', form=form, action='Thêm Sản Phẩm', sizes=SIZES, colors=COLORS)
        gallery = parse_gallery_lines(form.gallery.data)
        video_url = (form.video_url.data or '').strip()[:1000] or None
        if video_url and not (video_url.startswith('http://') or video_url.startswith('https://')):
            flash('Link video phải bắt đầu bằng http(s)!', 'danger')
            return render_template('admin_product_form.html', form=form, action='Thêm Sản Phẩm', sizes=SIZES, colors=COLORS)
        total_stock = sum(q for _, _, q in variants)
        has_gift_flag = 1 if form.has_gift.data else 0
        pid = execute_db('INSERT INTO products (name, price, sale_price, sale_start, sale_end, stock, category, description, image, is_featured, has_gift, brand, video_url, material, fit, size_note, is_active) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1)',
                         ((form.name.data or '').strip(), price_val, sale_price, sale_start, sale_end, total_stock, (form.category.data or '').strip(), (form.description.data or '').strip(), (form.image.data or '').strip(), 1 if form.is_featured.data else 0, has_gift_flag,
                          (form.brand.data or 'FashionShop').strip()[:100] or 'FashionShop', video_url,
                          (form.material.data or '').strip()[:500] or None, (form.fit.data or '').strip()[:255] or None,
                          (form.size_note.data or '').strip()[:500] or None),
                         lastrowid=True)
        for size, color, qty in variants:
            execute_db('INSERT INTO product_variants (product_id, size, color, stock) VALUES (%s, %s, %s, %s)', (pid, size, color, qty))
        for i, u in enumerate(gallery):
            execute_db('INSERT INTO product_images (product_id, image_url, sort_order) VALUES (%s, %s, %s)', (pid, u, i))
        for i, (q, a) in enumerate(faqs):
            execute_db('INSERT INTO product_faqs (product_id, question, answer, sort_order) VALUES (%s, %s, %s, %s)', (pid, q, a, i))
        flash('Thêm sản phẩm thành công.', 'success')
        return redirect(url_for('admin_products'))
    return render_template('admin_product_form.html', form=form, action='Thêm Sản Phẩm', sizes=SIZES, colors=COLORS)

@app.route('/admin/product/edit/<int:product_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_product(product_id):
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    product = query_db('SELECT * FROM products WHERE id = %s', [product_id], one=True)
    if not product:
        flash('Không tìm thấy sản phẩm!', 'danger')
        return redirect(url_for('admin_products'))
    if request.method == 'GET':
        form = ProductForm(data=product)
        cur_vars = get_variants(product_id)
        form.variants.data = '\n'.join(f"{v['size']} | {v['color']} | {v['stock']}" for v in cur_vars)
        form.stock.data = product.get('stock', 0)
        try:
            form.has_gift.data = int(product.get('has_gift') or 0) == 1
        except (ValueError, TypeError):
            form.has_gift.data = False
        form.gallery.data = '\n'.join(r['image_url'] for r in get_product_images(product_id))
        _faqs = get_product_faqs(product_id)
        form.faqs.data = '\n'.join(f"{r['question']} || {r['answer']}" for r in _faqs)
        form.sale_price.data = product.get('sale_price')
        try:
            form.sale_start.data = product.get('sale_start').strftime('%Y-%m-%d') if product.get('sale_start') else ''
        except AttributeError:
            form.sale_start.data = str(product.get('sale_start') or '')[:10]
        try:
            form.sale_end.data = product.get('sale_end').strftime('%Y-%m-%d') if product.get('sale_end') else ''
        except AttributeError:
            form.sale_end.data = str(product.get('sale_end') or '')[:10]
    else:
        form = ProductForm()
    if form.validate_on_submit():
        try:
            price_val = float(form.price.data)
        except (ValueError, TypeError):
            flash('Giá không hợp lệ!', 'danger')
            return render_template('admin_product_form.html', form=form, action='Chỉnh Sửa Sản Phẩm', sizes=SIZES, colors=COLORS)
        if price_val < 0:
            flash('Giá không được âm!', 'danger')
            return render_template('admin_product_form.html', form=form, action='Chỉnh Sửa Sản Phẩm', sizes=SIZES, colors=COLORS)
        serrs, sale_price, sale_start, sale_end = parse_sale(price_val, form.sale_price.data, form.sale_start.data, form.sale_end.data)
        if serrs:
            for e in serrs:
                flash(e, 'danger')
            return render_template('admin_product_form.html', form=form, action='Chỉnh Sửa Sản Phẩm', sizes=SIZES, colors=COLORS)
        verrs, variants = parse_variant_lines(form.variants.data)
        if verrs:
            for e in verrs:
                flash(e, 'danger')
            return render_template('admin_product_form.html', form=form, action='Chỉnh Sửa Sản Phẩm', sizes=SIZES, colors=COLORS)
        if not variants:
            try:
                stock_val = int(form.stock.data or product.get('stock', 0))
            except (ValueError, TypeError):
                stock_val = product.get('stock', 0)
            variants = [(DEFAULT_SIZE, DEFAULT_COLOR, max(0, stock_val))]
        # Đồng bộ biến thể: update/insert theo (size,color); chỉ xóa biến thể chưa từng bán
        existing = { (v['size'], v['color']): v for v in get_variants(product_id) }
        for size, color, qty in variants:
            if (size, color) in existing:
                execute_db('UPDATE product_variants SET stock = %s WHERE id = %s', (qty, existing[(size, color)]['id']))
            else:
                execute_db('INSERT INTO product_variants (product_id, size, color, stock) VALUES (%s, %s, %s, %s)', (product_id, size, color, qty))
        for key, v in existing.items():
            if key not in [(s, c) for s, c, _ in variants]:
                used = query_db('SELECT id FROM order_items WHERE variant_id = %s LIMIT 1', [v['id']], one=True)
                in_cart = query_db('SELECT id FROM cart WHERE variant_id = %s LIMIT 1', [v['id']], one=True)
                if used or in_cart:
                    flash(f'Giữ lại {key[0]}/{key[1]} (đã có đơn/giỏ, SL giữ {v["stock"]}) — muốn bỏ bán hãy để SL 0.', 'warning')
                else:
                    execute_db('DELETE FROM product_variants WHERE id = %s', [v['id']])
        ferrs, faqs = parse_faq_lines(form.faqs.data)
        if ferrs:
            for e in ferrs:
                flash(e, 'danger')
            return render_template('admin_product_form.html', form=form, action='Chỉnh Sửa Sản Phẩm', sizes=SIZES, colors=COLORS)
        gallery = parse_gallery_lines(form.gallery.data)
        video_url = (form.video_url.data or '').strip()[:1000] or None
        if video_url and not (video_url.startswith('http://') or video_url.startswith('https://')):
            flash('Link video phải bắt đầu bằng http(s)!', 'danger')
            return render_template('admin_product_form.html', form=form, action='Chỉnh Sửa Sản Phẩm', sizes=SIZES, colors=COLORS)
        total = query_db('SELECT SUM(stock) AS s FROM product_variants WHERE product_id = %s', [product_id], one=True)
        total_stock = int(total['s'] or 0) if total else 0
        has_gift_flag = 1 if form.has_gift.data else 0
        execute_db('UPDATE products SET name=%s, price=%s, sale_price=%s, sale_start=%s, sale_end=%s, stock=%s, category=%s, description=%s, image=%s, is_featured=%s, has_gift=%s, brand=%s, video_url=%s, material=%s, fit=%s, size_note=%s WHERE id=%s', ((form.name.data or '').strip(), price_val, sale_price, sale_start, sale_end, total_stock, (form.category.data or '').strip(), (form.description.data or '').strip(), (form.image.data or '').strip(), 1 if form.is_featured.data else 0, has_gift_flag,
                   (form.brand.data or 'FashionShop').strip()[:100] or 'FashionShop', video_url,
                   (form.material.data or '').strip()[:500] or None, (form.fit.data or '').strip()[:255] or None,
                   (form.size_note.data or '').strip()[:500] or None, product_id))
        execute_db('DELETE FROM product_images WHERE product_id = %s', [product_id])
        for i, u in enumerate(gallery):
            execute_db('INSERT INTO product_images (product_id, image_url, sort_order) VALUES (%s, %s, %s)', (product_id, u, i))
        execute_db('DELETE FROM product_faqs WHERE product_id = %s', [product_id])
        for i, (q, a) in enumerate(faqs):
            execute_db('INSERT INTO product_faqs (product_id, question, answer, sort_order) VALUES (%s, %s, %s, %s)', (product_id, q, a, i))
        flash('Cập nhật thành công.', 'success')
        return redirect(url_for('admin_products'))
    return render_template('admin_product_form.html', form=form, action='Chỉnh Sửa Sản Phẩm', sizes=SIZES, colors=COLORS)
@app.route('/admin/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_user(user_id):
    if not is_admin_user():
        flash('Bạn không có quyền truy cập!', 'danger')
        return redirect(url_for('index'))
        
    user = query_db('SELECT * FROM users WHERE id = %s', [user_id], one=True)
    if not user:
        flash('Không tìm thấy tài khoản!', 'danger')
        return redirect(url_for('admin_users'))
        
    
    if user.get('role') == 'Khách hàng':
        flash('Không được phép chỉnh sửa tài khoản khách hàng!', 'danger')
        return redirect(url_for('admin_users'))
        
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        role = (request.form.get('role') or '').strip()
        new_password = request.form.get('password') or ''
        if not name or len(name) < 2 or len(name) > 50:
            flash('Họ tên không hợp lệ!', 'danger')
            return render_template('admin_edit_user.html', user=user)
        if role not in ('Nhân viên', 'Admin'):
            flash('Vai trò không hợp lệ!', 'danger')
            return render_template('admin_edit_user.html', user=user)
        # Chống tự hạ quyền chính mình
        if int(user_id) == int(current_user.id) and role != 'Admin':
            flash('Không thể tự hạ quyền chính mình!', 'danger')
            return render_template('admin_edit_user.html', user=user)
        is_admin = 1 if role == 'Admin' else 0
        
        if new_password:
            if len(new_password) < 6:
                flash('Mật khẩu mới phải từ 6 ký tự!', 'danger')
                return render_template('admin_edit_user.html', user=user)
            hashed_pw = generate_password_hash(new_password)
            execute_db('UPDATE users SET name = %s, role = %s, is_admin = %s, password = %s WHERE id = %s', 
                       (name, role, is_admin, hashed_pw, user_id))
        else:
            execute_db('UPDATE users SET name = %s, role = %s, is_admin = %s WHERE id = %s', 
                       (name, role, is_admin, user_id))
                       
        flash('Cập nhật tài khoản thành công!', 'success')
        return redirect(url_for('admin_users'))
        
    return render_template('admin_edit_user.html', user=user)
@app.route('/admin/product/delete/<int:product_id>', methods=['POST'])
@login_required
def admin_delete_product(product_id):
    if not is_admin_user(): 
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    execute_db('UPDATE products SET is_active = 0 WHERE id = %s', [product_id])
    flash('Đã ẩn sản phẩm thành công (Bảo toàn lịch sử đơn hàng cũ).', 'success')
    return redirect(url_for('admin_products'))

@app.route('/admin/product/restore/<int:product_id>', methods=['POST'])
@login_required
def admin_restore_product(product_id):
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    execute_db('UPDATE products SET is_active = 1 WHERE id = %s', [product_id])
    flash('Đã khôi phục sản phẩm!', 'success')
    return redirect(url_for('admin_products'))

@app.route('/admin/products/resync', methods=['POST'])
@login_required
def admin_resync_stock():
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    fixed = resync_all_stock()
    if fixed:
        flash(f'Đã đồng bộ kho: sửa {fixed} sản phẩm bị lệch tổng!', 'success')
    else:
        flash('Kho tổng khớp hết với biến thể, không có gì để sửa!', 'info')
    return redirect(url_for('admin_products', tab=request.args.get('tab', 'active')))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = query_db('SELECT * FROM users WHERE id = %s', [current_user.id], one=True)
    point_history = query_db("SELECT * FROM point_log WHERE user_id = %s ORDER BY created_at DESC LIMIT 20", [current_user.id])
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'update_info':
            name = (request.form.get('name') or '').strip()
            if not name or len(name) < 2 or len(name) > 50:
                flash('Họ tên phải từ 2-50 ký tự!', 'danger')
                return redirect(url_for('profile'))
            phone_raw = (request.form.get('phone') or '').strip()
            digits = re.sub(r'\D', '', phone_raw)
            if phone_raw:
                if len(digits) < 9 or len(digits) > 15:
                    flash('Số điện thoại không hợp lệ!', 'danger')
                    return redirect(url_for('profile'))
                dup = query_db('SELECT id FROM users WHERE phone = %s AND id != %s', [digits, current_user.id], one=True)
                if dup:
                    flash('Số điện thoại này đã dùng cho tài khoản khác!', 'danger')
                    return redirect(url_for('profile'))
                execute_db('UPDATE users SET name = %s, phone = %s WHERE id = %s', (name, digits, current_user.id))
            else:
                execute_db('UPDATE users SET name = %s WHERE id = %s', (name, current_user.id))
            flash('Cập nhật thông tin cá nhân thành công!', 'success')
            return redirect(url_for('profile'))
            
        elif action == 'change_password':
            old_password = request.form.get('old_password') or ''
            new_password = request.form.get('new_password') or ''
            confirm_password = request.form.get('confirm_password') or ''
            stored = _get_stored_password(user)
            if not verify_password(stored, old_password):
                flash('Mật khẩu hiện tại không chính xác!', 'danger')
            elif new_password != confirm_password:
                flash('Mật khẩu mới và xác nhận mật khẩu không khớp!', 'danger')
            elif len(new_password) < 6:
                flash('Mật khẩu mới phải có ít nhất 6 ký tự!', 'danger')
            else:
                hashed_pw = generate_password_hash(new_password)
                execute_db('UPDATE users SET password = %s WHERE id = %s', (hashed_pw, current_user.id))
                flash('Đổi mật khẩu thành công!', 'success')
            return redirect(url_for('profile'))
            
    return render_template('profile.html', user=user, point_history=point_history or [])
@app.route('/admin/transactions')
@login_required
def admin_transactions():
    if not is_staff_user(): 
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
        
    try:
        page = int(request.args.get('page', 1))
    except (ValueError, TypeError):
        page = 1
    if page < 1:
        page = 1
    # Default rỗng = xem tất cả, fix bug luôn lọc hôm nay
    selected_date = (request.args.get('date') or '').strip()
    per_page = 10
    
    where_clause = "status = 'Hoàn thành'"
    params = []
    
    if selected_date:
        where_clause += " AND DATE(created_at) = %s"
        params.append(selected_date)
        
    if selected_date:
        summary_query = """
            SELECT COUNT(o.id) as total_orders, SUM(o.total_amount) as total_revenue,
                   SUM(o.total_amount - COALESCE(o.shipping_fee, 0)) as merch_revenue,
                   (SELECT SUM(oi.quantity) FROM order_items oi JOIN orders ord ON oi.order_id = ord.id WHERE ord.status = 'Hoàn thành' AND DATE(ord.created_at) = %s) as total_products
            FROM orders o WHERE status = 'Hoàn thành' AND DATE(o.created_at) = %s
        """
        summary = query_db(summary_query, [selected_date, selected_date], one=True)
    else:
        summary = query_db("""
            SELECT COUNT(o.id) as total_orders, SUM(o.total_amount) as total_revenue,
                   SUM(o.total_amount - COALESCE(o.shipping_fee, 0)) as merch_revenue,
                   (SELECT SUM(oi.quantity) FROM order_items oi JOIN orders ord ON oi.order_id = ord.id WHERE ord.status = 'Hoàn thành') as total_products
            FROM orders o WHERE o.status = 'Hoàn thành'
        """, [], one=True)

    total_revenue = summary['total_revenue'] if summary and summary['total_revenue'] else 0
    merch_revenue = summary['merch_revenue'] if summary and summary.get('merch_revenue') else 0
    total_orders_count = summary['total_orders'] if summary and summary['total_orders'] else 0
    total_products_sold = summary['total_products'] if summary and summary['total_products'] else 0

    cnt_row = query_db(f'SELECT COUNT(id) as cnt FROM orders WHERE {where_clause}', params, one=True)
    total_tx = cnt_row['cnt'] if cnt_row and cnt_row.get('cnt') else 0
    total_pages = max(1, math.ceil(total_tx / per_page)) if total_tx > 0 else 1
    if page > total_pages:
        page = total_pages
    offset = (page - 1) * per_page
    
    transactions = query_db(f'SELECT * FROM orders WHERE {where_clause} ORDER BY created_at DESC LIMIT %s OFFSET %s', params + [per_page, offset])
    
    return render_template('admin_transactions.html', 
                           transactions=transactions, 
                           page=page, 
                           total_pages=total_pages, 
                           selected_date=selected_date,
                           total_revenue=total_revenue,
                           merch_revenue=merch_revenue,
                           total_orders_count=total_orders_count,
                           total_products_sold=total_products_sold)
@app.route('/cancel-order/<int:order_id>', methods=['POST'])
@login_required
def cancel_order(order_id):
    order = query_db('SELECT status FROM orders WHERE id = %s AND user_id = %s', [order_id, current_user.id], one=True)
    
    if not order:
        flash('Không tìm thấy đơn hàng hoặc bạn không có quyền hủy đơn này!', 'error')
        return redirect(url_for('my_orders'))
        
    
    if order['status'] not in ['Chờ thanh toán', 'Chờ xác nhận']:
        flash('Đơn hàng đã được xử lý hoặc đang giao, không thể tự hủy. Vui lòng liên hệ Hotline!', 'error')
        return redirect(url_for('my_orders'))
        
    # Transaction chống double-hủy: chỉ update khi còn ở 2 trạng thái cho phép
    affected = 0
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute('START TRANSACTION')
            cur.execute("UPDATE orders SET status='Đã hủy' WHERE id=%s AND user_id=%s AND status IN ('Chờ thanh toán','Chờ xác nhận')",
                        [order_id, current_user.id])
            affected = cur.rowcount
            if affected == 0:
                db.rollback()
                flash('Đơn đã được xử lý, không thể hủy!', 'error')
                return redirect(url_for('my_orders'))
            cur.execute('SELECT product_id, variant_id, quantity FROM order_items WHERE order_id=%s', [order_id])
            items = cur.fetchall()
            for item in items:
                if item.get('variant_id'):
                    cur.execute('UPDATE product_variants SET stock = stock + %s WHERE id = %s', [item['quantity'], item['variant_id']])
                cur.execute('UPDATE products SET stock = stock + %s WHERE id = %s', [item['quantity'], item['product_id']])
            db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        flash('Hủy đơn thất bại, thử lại!', 'error')
        return redirect(url_for('my_orders'))

    refund_points_for_cancel(order_id, current_user.id)
    try:
        push_notification(current_user.id, f"Đơn #ORD-{order_id} đã hủy, kho/điểm đã hoàn.", "/my-orders")
    except Exception:
        pass
    flash('Bạn đã hủy đơn hàng thành công!', 'success')
    return redirect(url_for('my_orders'))
@app.route('/admin/vouchers')
@login_required
def admin_vouchers():
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    vouchers = query_db('SELECT * FROM vouchers ORDER BY expires_at DESC, id DESC')
    today = date.today()
    for v in vouchers:
        used_row = query_db('SELECT COUNT(id) AS cnt FROM orders WHERE voucher_code = %s', [v['code']], one=True)
        v['used_count'] = used_row['cnt'] if used_row and used_row.get('cnt') else 0
        # Trạng thái hiển thị
        try:
            exp = v.get('expires_at')
            if isinstance(exp, datetime):
                exp_date = exp.date()
            elif isinstance(exp, date):
                exp_date = exp
            else:
                exp_date = datetime.strptime(str(exp)[:10], '%Y-%m-%d').date() if exp else None
        except (ValueError, TypeError):
            exp_date = None
        v['exp_date'] = exp_date
        if exp_date and exp_date < today:
            v['state'] = 'expired'
        elif int(v.get('usage_limit') or 0) <= 0:
            v['state'] = 'out'
        else:
            v['state'] = 'active'
    return render_template('admin_vouchers.html', vouchers=vouchers, today=today)


def _validate_voucher_input(code, discount, min_order, usage, expires_str, ignore_id=None, dtype='FIXED', max_disc=0, freeship=False):
    """Trả về (errors:list, cleaned:dict). Code chuẩn hóa UPPER. dtype FIXED|PERCENT."""
    errors = []
    code = (code or '').strip().upper()
    if not re.fullmatch(r'[A-Z0-9]{3,20}', code):
        errors.append('Mã phải 3-20 ký tự chữ/số (A-Z, 0-9)!')
    dtype = (dtype or 'FIXED').upper()
    if dtype not in ('FIXED', 'PERCENT'):
        errors.append('Loại giảm không hợp lệ!')
        dtype = 'FIXED'
    try:
        discount = float(discount)
    except (ValueError, TypeError):
        discount = -1
    if dtype == 'PERCENT':
        if discount <= 0 or discount > 100:
            errors.append('Giảm % phải từ 1–100!')
    elif discount <= 0:
        errors.append('Tiền giảm phải lớn hơn 0!')
    try:
        max_disc = float(max_disc or 0)
    except (ValueError, TypeError):
        max_disc = -1
    if max_disc < 0:
        errors.append('Trần giảm không được âm!')
    try:
        min_order = float(min_order or 0)
    except (ValueError, TypeError):
        min_order = -1
    if min_order < 0:
        errors.append('Đơn tối thiểu không được âm!')
    try:
        usage = int(usage)
    except (ValueError, TypeError):
        usage = -1
    if usage < 0:
        errors.append('Lượt dùng không được âm!')
    try:
        exp_date = datetime.strptime((expires_str or '').strip()[:10], '%Y-%m-%d').date()
    except (ValueError, TypeError):
        exp_date = None
        errors.append('Hạn sử dụng phải đúng định dạng YYYY-MM-DD!')
    if exp_date and exp_date < date.today():
        errors.append('Hạn sử dụng phải từ hôm nay trở đi!')
    if code and not errors:
        dup = query_db('SELECT id FROM vouchers WHERE code = %s', [code], one=True)
        if dup and (ignore_id is None or int(dup['id']) != int(ignore_id)):
            errors.append('Mã này đã tồn tại!')
    return errors, {'code': code, 'discount': discount, 'min_order': min_order, 'usage': usage,
                    'exp_date': exp_date, 'dtype': dtype, 'max_disc': max_disc, 'freeship': 1 if freeship else 0}


@app.route('/admin/voucher/add', methods=['GET', 'POST'])
@login_required
def admin_add_voucher():
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    if request.method == 'POST':
        errors, c = _validate_voucher_input(request.form.get('code'), request.form.get('discount_amount'),
                                            request.form.get('min_order_amount'), request.form.get('usage_limit'),
                                            request.form.get('expires_at'), dtype=request.form.get('discount_type'),
                                            max_disc=request.form.get('max_discount'),
                                            freeship=request.form.get('is_freeship'))
        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('admin_voucher_form.html', action='Thêm mã giảm giá', v=request.form)
        try:
            execute_db('INSERT INTO vouchers (code, discount_amount, discount_type, max_discount, is_freeship, min_order_amount, usage_limit, expires_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
                       (c['code'], c['discount'], c['dtype'], c['max_disc'], c['freeship'], c['min_order'], c['usage'], c['exp_date'].strftime('%Y-%m-%d')))
        except Exception as e:
            if 'Duplicate' in str(e):
                flash('Mã này đã tồn tại!', 'danger')
                return render_template('admin_voucher_form.html', action='Thêm mã giảm giá', v=request.form)
            raise
        flash(f'Đã tạo mã {c["code"]}!', 'success')
        return redirect(url_for('admin_vouchers'))
    return render_template('admin_voucher_form.html', action='Thêm mã giảm giá', v={})


@app.route('/admin/voucher/edit/<int:voucher_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_voucher(voucher_id):
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    v = query_db('SELECT * FROM vouchers WHERE id = %s', [voucher_id], one=True)
    if not v:
        flash('Không tìm thấy mã!', 'danger')
        return redirect(url_for('admin_vouchers'))
    used_row = query_db('SELECT COUNT(id) AS cnt FROM orders WHERE voucher_code = %s', [v['code']], one=True)
    used = used_row['cnt'] if used_row and used_row.get('cnt') else 0
    if request.method == 'POST':
        errors, c = _validate_voucher_input(request.form.get('code'), request.form.get('discount_amount'),
                                            request.form.get('min_order_amount'), request.form.get('usage_limit'),
                                            request.form.get('expires_at'), ignore_id=voucher_id,
                                            dtype=request.form.get('discount_type'),
                                            max_disc=request.form.get('max_discount'),
                                            freeship=request.form.get('is_freeship'))
        # Mã đã có đơn dùng thì khóa code + discount (+ loại)
        if used > 0 and (c['code'] != v['code'] or float(c['discount']) != float(v['discount_amount']) or c['dtype'] != (v.get('discount_type') or 'FIXED')):
            flash(f'Mã đã có {used} đơn dùng, không được đổi mã/loại/tiền giảm (chỉ sửa hạn/lượt/đơn tối thiểu/trần)!', 'danger')
            return render_template('admin_voucher_form.html', action='Sửa mã giảm giá', v=request.form, voucher=v, used=used, locked=True)
        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('admin_voucher_form.html', action='Sửa mã giảm giá', v=request.form, voucher=v, used=used, locked=used > 0)
        execute_db('UPDATE vouchers SET code=%s, discount_amount=%s, discount_type=%s, max_discount=%s, is_freeship=%s, min_order_amount=%s, usage_limit=%s, expires_at=%s WHERE id=%s',
                   (c['code'], c['discount'], c['dtype'], c['max_disc'], c['freeship'], c['min_order'], c['usage'], c['exp_date'].strftime('%Y-%m-%d'), voucher_id))
        # Đồng bộ voucher_code trên đơn cũ nếu đổi code khi chưa ai dùng (used==0, an toàn)
        flash(f'Đã cập nhật mã {c["code"]}!', 'success')
        return redirect(url_for('admin_vouchers'))
    return render_template('admin_voucher_form.html', action='Sửa mã giảm giá', v=v, voucher=v, used=used, locked=used > 0)


@app.route('/admin/voucher/delete/<int:voucher_id>', methods=['POST'])
@login_required
def admin_delete_voucher(voucher_id):
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    v = query_db('SELECT * FROM vouchers WHERE id = %s', [voucher_id], one=True)
    if not v:
        flash('Không tìm thấy mã!', 'danger')
        return redirect(url_for('admin_vouchers'))
    used_row = query_db('SELECT COUNT(id) AS cnt FROM orders WHERE voucher_code = %s', [v['code']], one=True)
    used = used_row['cnt'] if used_row and used_row.get('cnt') else 0
    if used > 0:
        # Không xóa cứng để giữ lịch sử → khóa
        execute_db('UPDATE vouchers SET usage_limit = 0 WHERE id = %s', [voucher_id])
        flash(f'Mã {v["code"]} đã có {used} đơn dùng nên chuyển thành KHÓA (hết lượt) thay vì xóa!', 'warning')
    else:
        execute_db('DELETE FROM vouchers WHERE id = %s', [voucher_id])
        flash(f'Đã xóa mã {v["code"]}!', 'success')
    return redirect(url_for('admin_vouchers'))

# ==========================================
# Phase 3 — ĐỔI SIZE NGANG GIÁ (khách yêu cầu, shop duyệt)
# ==========================================
RETURN_STATUSES = ['Chờ duyệt', 'Hoàn thành', 'Từ chối']

@app.route('/exchange/<int:line_id>', methods=['GET', 'POST'])
@login_required
def exchange_request(line_id):
    """Khách yêu cầu đổi size/màu trong cùng SP (đơn phải Hoàn thành, ngang giá)."""
    if is_staff_user():
        flash('Tài khoản bán hàng không cần đổi size!', 'warning')
        return redirect(url_for('index'))
    line = query_db('''SELECT oi.*, o.user_id, o.status FROM order_items oi
                       JOIN orders o ON o.id = oi.order_id WHERE oi.id = %s''', [line_id], one=True)
    if not line or int(line.get('user_id') or 0) != int(current_user.id):
        flash('Không tìm thấy món hàng!', 'danger')
        return redirect(url_for('my_orders'))
    if line.get('status') != 'Hoàn thành':
        flash('Chỉ đổi size cho đơn đã hoàn thành!', 'warning')
        return redirect(url_for('my_orders'))
    pending = query_db("SELECT id FROM return_requests WHERE order_item_id = %s AND status = 'Chờ duyệt'", [line_id], one=True)
    if pending:
        flash('Món này đang có yêu cầu chờ duyệt rồi!', 'info')
        return redirect(url_for('my_orders'))
    prod = query_db('SELECT * FROM products WHERE id = %s', [line['product_id']], one=True)
    blocked, reason = is_exchange_blocked(prod)
    if blocked:
        flash(reason + ' Vui lòng liên hệ hotline nếu hàng lỗi!', 'warning')
        return redirect(url_for('my_orders'))
    options = [v for v in get_variants(line['product_id']) if v['stock'] > 0 and v['id'] != line.get('variant_id')]
    if request.method == 'POST':
        try:
            new_vid = int(request.form.get('new_variant_id') or 0)
        except (ValueError, TypeError):
            new_vid = 0
        reason = (request.form.get('reason') or '').strip()[:255]
        nv = query_db('SELECT * FROM product_variants WHERE id = %s AND product_id = %s', [new_vid, line['product_id']], one=True)
        if not nv:
            flash('Phân loại mới không hợp lệ (phải cùng sản phẩm)!', 'danger')
            return redirect(url_for('exchange_request', line_id=line_id))
        if int(nv.get('stock') or 0) < int(line['quantity']):
            flash(f'Phân loại {nv["size"]}/{nv["color"]} chỉ còn {nv["stock"]} cái!', 'danger')
            return redirect(url_for('exchange_request', line_id=line_id))
        # Ngang giá: giá theo SP nên cùng SP là ngang giá; chốt thêm check unit_price khớp giá hiện tại
        execute_db('INSERT INTO return_requests (order_id, order_item_id, product_id, old_variant_id, new_variant_id, reason, status) VALUES (%s, %s, %s, %s, %s, %s, %s)',
                   (line['order_id'], line_id, line['product_id'], line.get('variant_id'), new_vid, reason, 'Chờ duyệt'))
        flash('Đã gửi yêu cầu đổi size! Shop sẽ duyệt sớm.', 'success')
        return redirect(url_for('my_orders'))
    return render_template('exchange.html', line=line, product=prod, options=options)

@app.route('/admin/returns')
@login_required
def admin_returns():
    if not is_staff_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    status = (request.args.get('status') or '').strip()
    where = "1=1"
    params = []
    if status in RETURN_STATUSES:
        where = "r.status = %s"
        params.append(status)
    rows = query_db(f'''SELECT r.*, o.fullname, o.phone, o.status AS order_status, p.name AS pname,
                        ov.size AS osize, ov.color AS ocolor, nv.size AS nsize, nv.color AS ncolor,
                        oi.quantity, oi.unit_price
                        FROM return_requests r
                        JOIN orders o ON o.id = r.order_id
                        JOIN products p ON p.id = r.product_id
                        JOIN order_items oi ON oi.id = r.order_item_id
                        LEFT JOIN product_variants ov ON ov.id = r.old_variant_id
                        LEFT JOIN product_variants nv ON nv.id = r.new_variant_id
                        WHERE {where} ORDER BY r.created_at DESC''', params)
    counts = {}
    for s in RETURN_STATUSES:
        c = query_db('SELECT COUNT(id) AS cnt FROM return_requests WHERE status = %s', [s], one=True)
        counts[s] = c['cnt'] if c and c.get('cnt') else 0
    return render_template('admin_returns.html', rows=rows or [], counts=counts, status=status)

@app.route('/admin/return/<int:req_id>/approve', methods=['POST'])
@login_required
def admin_approve_return(req_id):
    if not is_staff_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute('START TRANSACTION')
            cur.execute("SELECT * FROM return_requests WHERE id = %s FOR UPDATE", [req_id])
            req = cur.fetchone()
            if not req or req.get('status') != 'Chờ duyệt':
                db.rollback()
                flash('Yêu cầu không ở trạng thái chờ duyệt!', 'error')
                return redirect(url_for('admin_returns'))
            cur.execute('SELECT * FROM order_items WHERE id = %s FOR UPDATE', [req['order_item_id']])
            line = cur.fetchone()
            if not line:
                db.rollback()
                flash('Dòng đơn không còn tồn tại!', 'error')
                return redirect(url_for('admin_returns'))
            # Chốt ngang giá: variant mới phải cùng SP với dòng đơn
            cur.execute('SELECT * FROM product_variants WHERE id = %s FOR UPDATE', [req['new_variant_id']])
            nv = cur.fetchone()
            if not nv or int(nv['product_id']) != int(line['product_id']):
                db.rollback()
                flash('Phân loại mới không cùng sản phẩm (lệch giá) — từ chối!', 'error')
                return redirect(url_for('admin_returns'))
            # Chốt: Sale + Phụ kiện tuyệt đối không đổi (kể cả đơn cũ lọt qua)
            cur.execute('SELECT * FROM products WHERE id = %s', [line['product_id']])
            _prod = cur.fetchone()
            if _prod:
                _blocked = False
                try:
                    _cat = (_prod.get('category') or '').strip().lower()
                    if _cat in ('phụ kiện', 'phu kien', 'accessory', 'accessories'):
                        _blocked = True
                except Exception:
                    pass
                if not _blocked:
                    try:
                        base = float(_prod.get('price') or 0)
                        sp = _prod.get('sale_price')
                        if sp is not None and float(sp) >= 0 and float(sp) < base:
                            _blocked = True
                    except (ValueError, TypeError):
                        pass
                if _blocked:
                    db.rollback()
                    flash('Hàng Sale/Phụ kiện không được đổi — đã chặn duyệt!', 'error')
                    return redirect(url_for('admin_returns'))
            qty = int(line['quantity'])
            if int(nv.get('stock') or 0) < qty:
                db.rollback()
                flash(f'Phân loại mới chỉ còn {nv.get("stock")} cái, không đủ đổi!', 'error')
                return redirect(url_for('admin_returns'))
            # Đổi kho: hoàn cũ, trừ mới (tổng products.stock không đổi vì cùng SP)
            if req.get('old_variant_id'):
                cur.execute('UPDATE product_variants SET stock = stock + %s WHERE id = %s', [qty, req['old_variant_id']])
            cur.execute('UPDATE product_variants SET stock = stock - %s WHERE id = %s AND stock >= %s', [qty, req['new_variant_id'], qty])
            if cur.rowcount == 0:
                db.rollback()
                flash('Phân loại mới vừa hết hàng!', 'error')
                return redirect(url_for('admin_returns'))
            cur.execute('UPDATE order_items SET variant_id = %s, variant_size = %s, variant_color = %s WHERE id = %s',
                        [req['new_variant_id'], nv['size'], nv['color'], req['order_item_id']])
            cur.execute("UPDATE return_requests SET status = 'Hoàn thành' WHERE id = %s", [req_id])
            db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        flash('Duyệt thất bại, thử lại!', 'error')
        return redirect(url_for('admin_returns'))
    try:
        _o = query_db('SELECT user_id, order_id FROM return_requests WHERE id = %s', [req_id], one=True)
        if _o:
            push_notification(_o.get('user_id'), f"Yêu cầu đổi size đơn #ORD-{_o.get('order_id')} đã duyệt.", "/my-orders")
        staff_log('Duyet doi size', (_o or {}).get('order_id'), f"Yeu cau #{req_id}")
    except Exception:
        pass
    flash('Đã duyệt đổi size!', 'success')
    return redirect(url_for('admin_returns'))

@app.route('/admin/return/<int:req_id>/reject', methods=['POST'])
@login_required
def admin_reject_return(req_id):
    if not is_staff_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    execute_db("UPDATE return_requests SET status = 'Từ chối' WHERE id = %s AND status = 'Chờ duyệt'", [req_id])
    try:
        _o = query_db('SELECT user_id, order_id FROM return_requests WHERE id = %s', [req_id], one=True)
        if _o:
            push_notification(_o.get('user_id'), f"Yêu cầu đổi size đơn #ORD-{_o.get('order_id')} bị từ chối.", "/my-orders")
        staff_log('Tu choi doi size', (_o or {}).get('order_id'), f"Yeu cau #{req_id}")
    except Exception:
        pass
    flash('Đã từ chối yêu cầu!', 'info')
    return redirect(url_for('admin_returns'))

# ==========================================
# Build Shop: trang tĩnh + cửa hàng + quà + mua ngay + subscribers + contacts + settings
# ==========================================
@app.route('/p/<slug>')
def static_page(slug):
    slug = (slug or '').strip()[:50]
    page = query_db('SELECT * FROM pages WHERE slug = %s', [slug], one=True)
    if not page:
        flash('Trang không tồn tại!', 'warning')
        return redirect(url_for('index'))
    return render_template('page.html', page=page)


@app.route('/admin/pages')
@login_required
def admin_pages():
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    rows = query_db('SELECT * FROM pages ORDER BY slug')
    return render_template('admin_pages.html', rows=rows or [])


@app.route('/admin/page/<slug>', methods=['GET', 'POST'])
@login_required
def admin_page_edit(slug):
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    page = query_db('SELECT * FROM pages WHERE slug = %s', [slug], one=True)
    if not page:
        flash('Không tìm thấy trang!', 'danger')
        return redirect(url_for('admin_pages'))
    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()[:255]
        content = (request.form.get('content') or '').strip()
        if len(title) < 2 or len(content) < 5:
            flash('Tiêu đề/nội dung quá ngắn!', 'danger')
            return render_template('admin_page_form.html', page=page)
        execute_db('UPDATE pages SET title = %s, content = %s WHERE slug = %s', (title, content, slug))
        flash('Đã cập nhật trang!', 'success')
        return redirect(url_for('admin_pages'))
    return render_template('admin_page_form.html', page=page)


@app.route('/cua-hang')
def store_list():
    provinces = query_db('SELECT DISTINCT province FROM stores WHERE is_active = 1 ORDER BY province') or []
    prov = (request.args.get('province') or '').strip()
    if prov:
        stores = query_db('SELECT * FROM stores WHERE is_active = 1 AND province = %s ORDER BY branch_name', [prov])
    else:
        stores = query_db('SELECT * FROM stores WHERE is_active = 1 ORDER BY province, branch_name')
    return render_template('stores.html', provinces=[p['province'] for p in provinces],
                           stores=stores or [], prov=prov)


@app.route('/admin/stores')
@login_required
def admin_stores():
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    rows = query_db('SELECT * FROM stores ORDER BY province, branch_name')
    return render_template('admin_stores.html', rows=rows or [])


@app.route('/admin/store/add', methods=['GET', 'POST'])
@login_required
def admin_store_add():
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    if request.method == 'POST':
        province = (request.form.get('province') or '').strip()[:100]
        branch = (request.form.get('branch_name') or '').strip()[:255]
        address = (request.form.get('address') or '').strip()[:500]
        hours = (request.form.get('open_hours') or '8:00 - 22:00').strip()[:255]
        map_url = (request.form.get('map_url') or '').strip()[:1000] or None
        if len(province) < 2 or len(branch) < 2 or len(address) < 5:
            flash('Vui lòng nhập đủ tỉnh/chi nhánh/địa chỉ!', 'danger')
            return render_template('admin_store_form.html', action='Thêm cửa hàng', s=request.form)
        execute_db('INSERT INTO stores (province, branch_name, address, open_hours, map_url, is_active) VALUES (%s,%s,%s,%s,%s,1)',
                   (province, branch, address, hours, map_url))
        flash('Đã thêm cửa hàng!', 'success')
        return redirect(url_for('admin_stores'))
    return render_template('admin_store_form.html', action='Thêm cửa hàng', s={})


@app.route('/admin/store/edit/<int:sid>', methods=['GET', 'POST'])
@login_required
def admin_store_edit(sid):
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    s = query_db('SELECT * FROM stores WHERE id = %s', [sid], one=True)
    if not s:
        flash('Không tìm thấy cửa hàng!', 'danger')
        return redirect(url_for('admin_stores'))
    if request.method == 'POST':
        province = (request.form.get('province') or '').strip()[:100]
        branch = (request.form.get('branch_name') or '').strip()[:255]
        address = (request.form.get('address') or '').strip()[:500]
        hours = (request.form.get('open_hours') or '8:00 - 22:00').strip()[:255]
        map_url = (request.form.get('map_url') or '').strip()[:1000] or None
        active = 1 if request.form.get('is_active') else 0
        if len(province) < 2 or len(branch) < 2 or len(address) < 5:
            flash('Vui lòng nhập đủ tỉnh/chi nhánh/địa chỉ!', 'danger')
            return render_template('admin_store_form.html', action='Sửa cửa hàng', s=request.form)
        execute_db('UPDATE stores SET province=%s, branch_name=%s, address=%s, open_hours=%s, map_url=%s, is_active=%s WHERE id=%s',
                   (province, branch, address, hours, map_url, active, sid))
        flash('Đã cập nhật cửa hàng!', 'success')
        return redirect(url_for('admin_stores'))
    return render_template('admin_store_form.html', action='Sửa cửa hàng', s=s)


@app.route('/admin/store/delete/<int:sid>', methods=['POST'])
@login_required
def admin_store_delete(sid):
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    execute_db('DELETE FROM stores WHERE id = %s', [sid])
    flash('Đã xóa cửa hàng!', 'success')
    return redirect(url_for('admin_stores'))


@app.route('/admin/gifts')
@login_required
def admin_gifts():
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    rows = query_db('SELECT * FROM gifts ORDER BY id DESC')
    return render_template('admin_gifts.html', rows=rows or [])


@app.route('/admin/gift/add', methods=['GET', 'POST'])
@login_required
def admin_gift_add():
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()[:255]
        try:
            stock = int(request.form.get('stock') or 0)
        except (ValueError, TypeError):
            stock = -1
        try:
            min_amt = float(request.form.get('min_order_amount') or GIFT_MIN_DEFAULT)
        except (ValueError, TypeError):
            min_amt = -1
        image = (request.form.get('image') or '').strip()[:500] or None
        active = 1 if request.form.get('is_active') else 0
        if len(name) < 2 or stock < 0 or min_amt < 0:
            flash('Tên/stock/ngưỡng không hợp lệ!', 'danger')
            return render_template('admin_gift_form.html', action='Thêm quà', g=request.form)
        execute_db('INSERT INTO gifts (name, stock, image, min_order_amount, is_active) VALUES (%s,%s,%s,%s,%s)',
                   (name, stock, image, min_amt, active))
        flash('Đã thêm quà!', 'success')
        return redirect(url_for('admin_gifts'))
    return render_template('admin_gift_form.html', action='Thêm quà', g={})


@app.route('/admin/gift/edit/<int:gid>', methods=['GET', 'POST'])
@login_required
def admin_gift_edit(gid):
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    g = query_db('SELECT * FROM gifts WHERE id = %s', [gid], one=True)
    if not g:
        flash('Không tìm thấy quà!', 'danger')
        return redirect(url_for('admin_gifts'))
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()[:255]
        try:
            stock = int(request.form.get('stock') or 0)
        except (ValueError, TypeError):
            stock = -1
        try:
            min_amt = float(request.form.get('min_order_amount') or 0)
        except (ValueError, TypeError):
            min_amt = -1
        image = (request.form.get('image') or '').strip()[:500] or None
        active = 1 if request.form.get('is_active') else 0
        if len(name) < 2 or stock < 0 or min_amt < 0:
            flash('Tên/stock/ngưỡng không hợp lệ!', 'danger')
            return render_template('admin_gift_form.html', action='Sửa quà', g=request.form)
        execute_db('UPDATE gifts SET name=%s, stock=%s, image=%s, min_order_amount=%s, is_active=%s WHERE id=%s',
                   (name, stock, image, min_amt, active, gid))
        flash('Đã cập nhật quà!', 'success')
        return redirect(url_for('admin_gifts'))
    return render_template('admin_gift_form.html', action='Sửa quà', g=g)


@app.route('/admin/gift/delete/<int:gid>', methods=['POST'])
@login_required
def admin_gift_delete(gid):
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    used = query_db('SELECT order_id FROM order_gifts WHERE gift_id = %s LIMIT 1', [gid], one=True)
    if used:
        execute_db('UPDATE gifts SET is_active = 0, stock = 0 WHERE id = %s', [gid])
        flash('Quà đã có đơn dùng nên chuyển thành ẨN thay vì xóa!', 'warning')
    else:
        execute_db('DELETE FROM gifts WHERE id = %s', [gid])
        flash('Đã xóa quà!', 'success')
    return redirect(url_for('admin_gifts'))


def _validate_buy_now(product_id, variant_val, qty_raw):
    try:
        qty = int(qty_raw or 1)
    except (ValueError, TypeError):
        return None, 'Số lượng không hợp lệ!'
    if qty < 1 or qty > 999:
        return None, 'Số lượng 1-999!'
    prod = query_db('SELECT * FROM products WHERE id = %s AND is_active = 1', [product_id], one=True)
    if not prod:
        return None, 'Sản phẩm không tồn tại!'
    size, color = DEFAULT_SIZE, DEFAULT_COLOR
    if variant_val and '|' in variant_val:
        _s, _c = variant_val.split('|', 1)
        size, color = _s.strip(), _c.strip()
    variant = resolve_variant(product_id, size, color)
    if not variant:
        return None, 'Size/màu không hợp lệ!'
    if int(variant.get('stock') or 0) < qty:
        return None, f"Phân loại {variant['size']}/{variant['color']} chỉ còn {variant['stock']} cái!"
    apply_pricing([prod])
    return {'product': prod, 'variant': variant, 'qty': qty,
            'unit_price': float(prod.get('eff_price') or 0)}, ''


@app.route('/buy-now/<int:product_id>', methods=['POST'])
@login_required
def buy_now(product_id):
    variant_val = request.form.get('variant') or request.form.get('size')
    # form chi tiết gửi select variant "Size|Màu"
    data, err = _validate_buy_now(product_id, variant_val, request.form.get('quantity', 1))
    if err:
        flash(err, 'error')
        return redirect(request.referrer or url_for('product_detail', product_id=product_id))
    session['buy_now'] = {'product_id': product_id, 'variant_id': int(data['variant']['id']),
                          'qty': int(data['qty'])}
    return redirect(url_for('checkout_direct'))


@app.route('/buy-now-qty', methods=['POST'])
@login_required
def buy_now_qty():
    """Đổi số lượng món Mua ngay (kẹp theo tồn kho), trả JSON để trang tự cập nhật tiền."""
    from flask import jsonify
    bn = session.get('buy_now')
    if not bn:
        return jsonify({'ok': False})
    variant = query_db('SELECT stock FROM product_variants WHERE id = %s', [bn.get('variant_id')], one=True)
    max_q = int((variant or {}).get('stock') or 1)
    if max_q < 1:
        max_q = 1
    try:
        q = int(request.form.get('qty') or 1)
    except (ValueError, TypeError):
        q = 1
    q = max(1, min(q, min(max_q, 999)))
    bn['qty'] = q
    session['buy_now'] = bn
    return jsonify({'ok': True, 'qty': q, 'max': max_q})


@app.route('/checkout-direct', methods=['GET', 'POST'])
@login_required
def checkout_direct():
    bn = session.get('buy_now')
    if not bn:
        flash('Chưa chọn món mua ngay!', 'warning')
        return redirect(url_for('index'))
    data, err = _validate_buy_now(bn.get('product_id'), None, bn.get('qty'))
    # resolve lại variant theo id đã lưu (tránh lệch size/màu)
    variant = query_db('SELECT * FROM product_variants WHERE id = %s', [bn.get('variant_id')], one=True)
    prod = query_db('SELECT * FROM products WHERE id = %s AND is_active = 1', [bn.get('product_id')], one=True)
    if not prod or not variant or int(variant.get('product_id') or 0) != int(prod.get('id')):
        session.pop('buy_now', None)
        flash('Món mua ngay không còn hợp lệ!', 'error')
        return redirect(url_for('index'))
    apply_pricing([prod])
    try:
        qty = int(bn.get('qty') or 1)
    except (ValueError, TypeError):
        qty = 1
    if int(variant.get('stock') or 0) < qty:
        flash(f"Phân loại {variant['size']}/{variant['color']} chỉ còn {variant['stock']} cái!", 'error')
        return redirect(url_for('product_detail', product_id=prod['id']))
    unit_price = float(prod.get('eff_price') or 0)
    total_amount = unit_price * qty
    freeship_threshold = get_int_setting('freeship_threshold', FREESHIP_THRESHOLD_DEFAULT)
    gifts = get_available_gifts(total_amount)
    show_gift = gift_eligible([{'has_gift': prod.get('has_gift')}], total_amount)
    if not show_gift:
        gifts = []
    if request.method == 'GET':
        points_balance = 0
        if not is_staff_user():
            brow = query_db('SELECT points FROM users WHERE id = %s', [current_user.id], one=True)
            points_balance = int((brow or {}).get('points') or 0)
        try:
            stores = query_db('SELECT id, branch_name, province FROM stores WHERE is_active = 1 ORDER BY province, branch_name') or []
        except Exception:
            stores = []
        return render_template('checkout_direct.html', prod=prod, variant=variant, qty=qty,
                               unit_price=unit_price, total_amount=total_amount,
                               freeship_threshold=freeship_threshold, gifts=gifts,
                               show_gift=show_gift, points_balance=points_balance,
                               ship_carriers=SHIP_CARRIERS, stores=stores)
    # POST: tạo đơn thẳng, bỏ qua giỏ
    staff_sale = is_staff_user()
    address = (request.form.get('address') or '').strip()
    phone = (request.form.get('phone') or '').strip()
    if staff_sale and not address:
        address = 'Mua tại cửa hàng'
    if not address or len(address) < 5 or len(address) > 255:
        flash('Vui lòng nhập địa chỉ đầy đủ!', 'error')
        return redirect(url_for('checkout_direct'))
    if not phone or len(phone) < 9 or len(phone) > 15 or not phone.replace('+', '').replace(' ', '').isdigit():
        flash('Số điện thoại không hợp lệ!', 'error')
        return redirect(url_for('checkout_direct'))
    payment_method = normalize_payment(request.form.get('payment_method', 'COD'))
    me = query_db('SELECT name, email FROM users WHERE id = %s', [current_user.id], one=True)
    fullname = ((me or {}).get('name') or current_user.name or '').strip()[:255] or f'User #{current_user.id}'
    email = ((me or {}).get('email') or current_user.email or '').strip()[:255] or f'user{current_user.id}@noemail.local'
    order_owner_id = current_user.id
    if staff_sale:
        typed_name = (request.form.get('customer_name') or '').strip()[:255]
        if typed_name:
            if len(typed_name) < 2:
                flash('Tên khách phải từ 2 ký tự!', 'error')
                return redirect(url_for('checkout_direct'))
            fullname = typed_name
    ship_zone, shipping_fee, discount_applied, voucher_id, voucher_code = None, 0, 0, None, ''
    use_points, points_discount, freeship = 0, 0, False
    ship_carrier = None
    if not staff_sale:
        ship_carrier = (request.form.get('ship_carrier') or 'GHN').strip()
        if ship_carrier not in SHIP_CARRIER_FEE:
            ship_carrier = 'GHN'
    note = (request.form.get('note') or '').strip()[:1000] or None
    dong_kiem = 1 if request.form.get('dong_kiem') else 0
    channel = 'tai_quay' if staff_sale else 'online'
    try:
        store_id = int(request.form.get('store_id') or 0) or None
    except (ValueError, TypeError):
        store_id = None
    if not staff_sale:
        voucher_code = (request.form.get('voucher_code') or '').strip().upper()
        if voucher_code:
            voucher = query_db('SELECT * FROM vouchers WHERE code = %s', [voucher_code], one=True)
            if not voucher or int(voucher.get('usage_limit') or 0) <= 0:
                flash('Mã giảm giá không hợp lệ/hết lượt!', 'error')
                return redirect(url_for('checkout_direct'))
            try:
                exp = voucher.get('expires_at')
                exp_date = exp.date() if isinstance(exp, datetime) else exp if isinstance(exp, date) else datetime.strptime(str(exp)[:10], '%Y-%m-%d').date() if exp else None
                if exp_date and exp_date < date.today():
                    flash('Mã đã hết hạn!', 'error')
                    return redirect(url_for('checkout_direct'))
            except (ValueError, TypeError):
                pass
            try:
                min_o = float(voucher.get('min_order_amount') or 0)
            except (ValueError, TypeError):
                min_o = 0
            if total_amount < min_o:
                flash('Chưa đạt đơn tối thiểu của mã!', 'error')
                return redirect(url_for('checkout_direct'))
            try:
                dra = float(voucher.get('discount_amount') or 0)
            except (ValueError, TypeError):
                dra = 0
            vtype = (voucher.get('discount_type') or 'FIXED').upper()
            if vtype == 'PERCENT':
                discount_applied = total_amount * dra / 100
                try:
                    cap = float(voucher.get('max_discount') or 0)
                except (ValueError, TypeError):
                    cap = 0
                if cap > 0 and discount_applied > cap:
                    discount_applied = cap
            else:
                discount_applied = dra
            discount_applied = max(0, min(discount_applied, max(0, total_amount)))
            voucher_id = voucher['id']
            freeship = int(voucher.get('is_freeship') or 0) == 1
        ship_zone = (request.form.get('ship_zone') or '').strip()
        if ship_zone not in ('noi_thanh', 'ngoai_thanh'):
            flash('Vui lòng chọn khu vực giao hàng!', 'error')
            return redirect(url_for('checkout_direct'))
        shipping_fee = 0 if ship_zone == 'noi_thanh' else 30000
        shipping_fee += SHIP_CARRIER_FEE.get(ship_carrier, 0)
        if freeship:
            shipping_fee = 0
    _ag, _bd, _ap = evaluate_combos({int(prod['id']): qty}, {int(prod['id']): unit_price})
    merch_total = max(0, total_amount - discount_applied - _bd)
    if not staff_sale and merch_total >= freeship_threshold:
        shipping_fee = 0
    final_amount = merch_total + shipping_fee
    gift_id = None
    try:
        _g = (request.form.get('gift_id') or '').strip()
        gift_id = int(_g) if _g else None
    except (ValueError, TypeError):
        gift_id = None
    if gift_id is not None:
        if not gift_eligible([{'has_gift': prod.get('has_gift')}], merch_total):
            flash('Đơn chưa đạt điều kiện nhận quà!', 'error')
            return redirect(url_for('checkout_direct'))
        _gift = query_db('SELECT * FROM gifts WHERE id = %s AND is_active = 1', [gift_id], one=True)
        if not _gift or int(_gift.get('stock') or 0) <= 0:
            flash('Quà đã hết!', 'error')
            return redirect(url_for('checkout_direct'))
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute('START TRANSACTION')
            if voucher_id:
                cur.execute('SELECT usage_limit FROM vouchers WHERE id = %s FOR UPDATE', [voucher_id])
                vrow = cur.fetchone()
                if not vrow or int(vrow.get('usage_limit') or 0) <= 0:
                    db.rollback()
                    flash('Mã vừa hết lượt!', 'error')
                    return redirect(url_for('checkout_direct'))
            cur.execute('SELECT stock FROM product_variants WHERE id = %s FOR UPDATE', [variant['id']])
            vrow = cur.fetchone()
            if not vrow or int(vrow.get('stock') or 0) < qty:
                db.rollback()
                flash('Món vừa hết hàng!', 'error')
                return redirect(url_for('checkout_direct'))
            cur.execute('''INSERT INTO orders (user_id, fullname, email, total_amount, discount_amount, voucher_code,
                         points_used, points_discount, ship_zone, shipping_fee, ship_carrier, channel, store_id, note, dong_kiem, payment_method, address, phone, status, created_at)
                         VALUES (%s,%s,%s,%s,%s,%s,0,0,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'Chờ thanh toán',NOW())''',
                        [order_owner_id, fullname, email, final_amount, discount_applied + _bd,
                         (voucher_code or None) if voucher_id else None, ship_zone, shipping_fee, ship_carrier, channel, store_id, note, dong_kiem,
                         payment_method, address, phone])
            order_id = cur.lastrowid
            cur.execute('INSERT INTO order_items (order_id, product_id, variant_id, variant_size, variant_color, quantity, unit_price, is_gift) VALUES (%s,%s,%s,%s,%s,%s,%s,0)',
                        (order_id, prod['id'], variant['id'], variant.get('size'), variant.get('color'), qty, unit_price))
            for _gpid, _gqty, _cb in (_ag or []):
                cur.execute('SELECT id, size, color FROM product_variants WHERE product_id = %s AND stock >= %s ORDER BY stock DESC LIMIT 1', [_gpid, _gqty])
                _gv = cur.fetchone()
                if not _gv:
                    continue
                cur.execute('INSERT INTO order_items (order_id, product_id, variant_id, variant_size, variant_color, quantity, unit_price, is_gift) VALUES (%s,%s,%s,%s,%s,%s,0,1)',
                            (order_id, _gpid, _gv['id'], _gv.get('size'), _gv.get('color'), _gqty))
                cur.execute('UPDATE product_variants SET stock = stock - %s WHERE id = %s AND stock >= %s', [_gqty, _gv['id'], _gqty])
                cur.execute('UPDATE products SET stock = stock - %s WHERE id = %s', [_gqty, _gpid])
            for _cb, _times, _disc in (_ap or []):
                try:
                    cur.execute('INSERT INTO order_combos (order_id, combo_id, qty, discount) VALUES (%s,%s,%s,%s)',
                                [order_id, int(_cb.get('id')), int(_times), float(_disc or 0)])
                except Exception:
                    continue
            cur.execute('UPDATE product_variants SET stock = stock - %s WHERE id = %s AND stock >= %s', [qty, variant['id'], qty])
            cur.execute('UPDATE products SET stock = stock - %s WHERE id = %s', [qty, prod['id']])
            if voucher_id:
                cur.execute('UPDATE vouchers SET usage_limit = usage_limit - 1 WHERE id = %s AND usage_limit > 0', [voucher_id])
            if gift_id is not None:
                cur.execute('SELECT stock FROM gifts WHERE id = %s FOR UPDATE', [gift_id])
                grow = cur.fetchone()
                if not grow or int(grow.get('stock') or 0) <= 0:
                    db.rollback()
                    flash('Quà vừa hết!', 'error')
                    return redirect(url_for('checkout_direct'))
                cur.execute('UPDATE gifts SET stock = stock - 1 WHERE id = %s AND stock > 0', [gift_id])
                cur.execute('INSERT INTO order_gifts (order_id, gift_id, qty) VALUES (%s,%s,1)', [order_id, gift_id])
            db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        flash('Đặt hàng thất bại, thử lại!', 'error')
        return redirect(url_for('checkout_direct'))
    session.pop('buy_now', None)
    try:
        push_notification(order_owner_id, f"Đơn #ORD-{order_id} đã đặt, chờ thanh toán.", "/my-orders")
    except Exception:
        pass
    flash('Mua ngay thành công! Cảm ơn bạn đã mua sắm.', 'success')
    if staff_sale:
        if normalize_payment(payment_method) == 'Chuyển khoản':
            return redirect(url_for('admin_order_qr', order_id=order_id))
        return redirect(url_for('admin_order_detail', order_id=order_id))
    return redirect(url_for('my_orders'))


@app.route('/subscribe', methods=['POST'])
def subscribe():
    email = (request.form.get('email') or '').strip().lower()[:255]
    if not email or '@' not in email or '.' not in email:
        flash('Email nhận tin không hợp lệ!', 'danger')
        return redirect(request.referrer or url_for('index'))
    try:
        execute_db('INSERT INTO subscribers (email) VALUES (%s)', [email])
        flash('Đã đăng ký nhận tin! Cảm ơn bạn.', 'success')
    except Exception as e:
        if 'Duplicate' in str(e):
            flash('Email này đã đăng ký rồi!', 'info')
        else:
            flash('Không đăng ký được lúc này!', 'danger')
    return redirect(request.referrer or url_for('index'))


@app.route('/admin/subscribers')
@login_required
def admin_subscribers():
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    rows = query_db('SELECT * FROM subscribers ORDER BY id DESC')
    return render_template('admin_subscribers.html', rows=rows or [])


@app.route('/admin/subscriber/delete/<int:sid>', methods=['POST'])
@login_required
def admin_subscriber_delete(sid):
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    execute_db('DELETE FROM subscribers WHERE id = %s', [sid])
    flash('Đã xóa email!', 'success')
    return redirect(url_for('admin_subscribers'))


@app.route('/contact', methods=['POST'])
def contact_post():
    if not verify_recaptcha(request.form.get('g-recaptcha-response', '')):
        flash('Xác minh chống spam thất bại, thử lại!', 'danger')
        return redirect(request.referrer or url_for('index'))
    name = (request.form.get('name') or '').strip()[:100]
    phone = (request.form.get('phone') or '').strip()[:20]
    message = (request.form.get('message') or '').strip()
    if len(name) < 2 or len(re.sub(r'\D', '', phone or '')) < 9 or len(message) < 5 or len(message) > 1000:
        flash('Vui lòng nhập tên/SĐT/lời nhắn hợp lệ!', 'danger')
        return redirect(request.referrer or url_for('index'))
    execute_db('INSERT INTO contacts (name, phone, message, status) VALUES (%s,%s,%s,%s)',
               (name, phone, message, 'Moi'))
    flash('Đã gửi lời nhắn! Shop sẽ liên hệ sớm.', 'success')
    return redirect(request.referrer or url_for('index'))


@app.route('/admin/contacts')
@login_required
def admin_contacts():
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    status = (request.args.get('status') or '').strip()
    if status in ('Moi', 'Da_tra_loi', 'Dong'):
        rows = query_db('SELECT * FROM contacts WHERE status = %s ORDER BY id DESC', [status])
    else:
        rows = query_db('SELECT * FROM contacts ORDER BY id DESC')
        status = ''
    counts = {}
    for s in ('Moi', 'Da_tra_loi', 'Dong'):
        c = query_db('SELECT COUNT(id) AS cnt FROM contacts WHERE status = %s', [s], one=True)
        counts[s] = int((c or {}).get('cnt') or 0)
    return render_template('admin_contacts.html', rows=rows or [], counts=counts, status=status)


@app.route('/admin/contact/<int:cid>/reply', methods=['POST'])
@login_required
def admin_contact_reply(cid):
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    reply = (request.form.get('reply') or '').strip()
    if len(reply) < 2 or len(reply) > 2000:
        flash('Nội dung trả lời quá ngắn/dài!', 'danger')
        return redirect(url_for('admin_contacts'))
    execute_db("UPDATE contacts SET reply = %s, status = 'Da_tra_loi' WHERE id = %s", (reply, cid))
    flash('Đã trả lời tin nhắn!', 'success')
    return redirect(url_for('admin_contacts'))


@app.route('/admin/contact/<int:cid>/close', methods=['POST'])
@login_required
def admin_contact_close(cid):
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    execute_db("UPDATE contacts SET status = 'Dong' WHERE id = %s", [cid])
    flash('Đã đóng tin nhắn!', 'info')
    return redirect(url_for('admin_contacts'))


@app.route('/admin/settings', methods=['GET', 'POST'])
@login_required
def admin_settings():
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    if request.method == 'POST':
        try:
            ft = int(request.form.get('freeship_threshold') or FREESHIP_THRESHOLD_DEFAULT)
        except (ValueError, TypeError):
            ft = -1
        try:
            mo = int(request.form.get('min_order_amount') or 0)
        except (ValueError, TypeError):
            mo = -1
        try:
            gm = int(request.form.get('gift_min_amount') or GIFT_MIN_DEFAULT)
        except (ValueError, TypeError):
            gm = -1
        try:
            rate = float(request.form.get('commission_rate') or 2)
        except (ValueError, TypeError):
            rate = -1
        if ft < 0 or mo < 0 or gm < 0 or rate < 0 or rate > 50:
            flash('Ngưỡng/hoa hồng không hợp lệ (hoa hồng 0-50%)!', 'danger')
            return redirect(url_for('admin_settings'))
        set_setting('freeship_threshold', ft)
        set_setting('min_order_amount', mo)
        set_setting('gift_min_amount', gm)
        set_setting('commission_rate', rate)
        set_setting('recaptcha_site_key', (request.form.get('recaptcha_site_key') or '').strip())
        set_setting('recaptcha_secret_key', (request.form.get('recaptcha_secret_key') or '').strip())
        set_setting('require_email_verify', '1' if request.form.get('require_email_verify') else '0')
        set_setting('shop_bank_accounts', (request.form.get('shop_bank_accounts') or '').strip())
        flash(f'Đã lưu cấu hình!', 'success')
        return redirect(url_for('admin_settings'))
    cur = {'freeship_threshold': get_int_setting('freeship_threshold', FREESHIP_THRESHOLD_DEFAULT),
           'min_order_amount': get_int_setting('min_order_amount', MIN_ORDER_DEFAULT),
           'gift_min_amount': get_int_setting('gift_min_amount', GIFT_MIN_DEFAULT),
           'commission_rate': get_setting('commission_rate', '2'),
           'recaptcha_site_key': get_setting('recaptcha_site_key', ''),
           'recaptcha_secret_key': get_setting('recaptcha_secret_key', ''),
           'require_email_verify': get_setting('require_email_verify', '1'),
           'shop_bank_accounts': get_setting('shop_bank_accounts', '')}
    counts = {'subs': 0, 'contacts': 0, 'stores': 0, 'gifts': 0}
    try:
        for k, tbl in [('subs', 'subscribers'), ('contacts', 'contacts'), ('stores', 'stores'), ('gifts', 'gifts')]:
            r = query_db(f'SELECT COUNT(*) AS c FROM {tbl}', one=True)
            counts[k] = int((r or {}).get('c') or 0)
    except Exception:
        pass
    return render_template('admin_settings.html', cur=cur, counts=counts)


# ==========================================
# Nhóm Sản phẩm + nội dung: Collection + Bài viết + Tuyển dụng
# ==========================================
@app.route('/collections')
def collection_list():
    rows = query_db('SELECT * FROM collections WHERE is_active = 1 ORDER BY id DESC') or []
    for c in rows:
        cnt = query_db('SELECT COUNT(*) AS n FROM collection_products WHERE collection_id = %s', [c['id']], one=True)
        c['count'] = int((cnt or {}).get('n') or 0)
    return render_template('collections.html', rows=rows)


@app.route('/collections/<slug>')
def collection_detail(slug):
    c = query_db('SELECT * FROM collections WHERE slug = %s AND is_active = 1', [(slug or '').strip()[:100]], one=True)
    if not c:
        flash('Bộ sưu tập không tồn tại!', 'warning')
        return redirect(url_for('collection_list'))
    prods = query_db('''SELECT p.* FROM products p JOIN collection_products cp ON cp.product_id = p.id
                        WHERE cp.collection_id = %s AND p.is_active = 1 ORDER BY p.id DESC''', [c['id']])
    apply_pricing(prods)
    posts = query_db('SELECT * FROM posts WHERE collection_id = %s AND is_active = 1 ORDER BY id DESC LIMIT 6', [c['id']])
    return render_template('collection_detail.html', c=c, prods=prods or [], posts=posts or [])


@app.route('/bai-viet')
def post_list():
    rows = query_db('SELECT p.*, c.title AS ctitle FROM posts p LEFT JOIN collections c ON c.id = p.collection_id WHERE p.is_active = 1 ORDER BY p.id DESC') or []
    return render_template('posts.html', rows=rows)


@app.route('/bai-viet/<slug>')
def post_detail(slug):
    p = query_db('SELECT p.*, c.title AS ctitle FROM posts p LEFT JOIN collections c ON c.id = p.collection_id WHERE p.slug = %s AND p.is_active = 1', [(slug or '').strip()[:100]], one=True)
    if not p:
        flash('Bài viết không tồn tại!', 'warning')
        return redirect(url_for('post_list'))
    prods = query_db('''SELECT p.* FROM products p JOIN post_products pp ON pp.product_id = p.id
                        WHERE pp.post_id = %s AND p.is_active = 1 ORDER BY p.id DESC''', [p['id']])
    apply_pricing(prods)
    others = query_db('SELECT id, slug, title, image FROM posts WHERE is_active = 1 AND id != %s ORDER BY id DESC LIMIT 4', [p['id']])
    return render_template('post_detail.html', p=p, prods=prods or [], others=others or [])


@app.route('/tuyen-dung', methods=['GET', 'POST'])
def job_list():
    jobs = query_db('SELECT * FROM jobs WHERE is_active = 1 ORDER BY id DESC') or []
    if request.method == 'POST':
        if current_user.is_authenticated and (int(current_user.is_admin or 0) == 1 or current_user.role == 'Nhân viên'):
            flash('Tài khoản bán hàng không cần ứng tuyển!', 'warning')
            return redirect(url_for('job_list'))
        if not verify_recaptcha(request.form.get('g-recaptcha-response', '')):
            flash('Xác minh chống spam thất bại, thử lại!', 'danger')
            return render_template('jobs.html', jobs=jobs)
        try:
            job_id = int(request.form.get('job_id') or 0)
        except (ValueError, TypeError):
            job_id = 0
        name = (request.form.get('name') or '').strip()[:100]
        phone = (request.form.get('phone') or '').strip()[:20]
        email = (request.form.get('email') or '').strip().lower()[:255] or None
        cv_text = (request.form.get('cv_text') or '').strip()
        job = query_db('SELECT id FROM jobs WHERE id = %s AND is_active = 1', [job_id], one=True)
        import re as _re
        if not job:
            flash('Vị trí ứng tuyển không hợp lệ!', 'danger')
        elif len(name) < 2 or len(_re.sub(r'\D', '', phone or '')) < 9 or len(cv_text) < 10 or len(cv_text) > 5000:
            flash('Vui lòng nhập tên/SĐT/giới thiệu hợp lệ (giới thiệu 10-5000 ký tự)!', 'danger')
        elif email and ('@' not in email or '.' not in email):
            flash('Email không hợp lệ!', 'danger')
        else:
            execute_db('INSERT INTO applications (job_id, name, phone, email, cv_text, status) VALUES (%s,%s,%s,%s,%s,%s)',
                       (job_id, name, phone, email, cv_text, 'Moi'))
            flash('Đã gửi hồ sơ ứng tuyển! Shop sẽ liên hệ sớm.', 'success')
            return redirect(url_for('job_list'))
    return render_template('jobs.html', jobs=jobs)


def _require_admin():
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return False
    return True


@app.route('/admin/collections')
@login_required
def admin_collections():
    if not _require_admin():
        return redirect(url_for('index'))
    rows = query_db('SELECT * FROM collections ORDER BY id DESC') or []
    for c in rows:
        cnt = query_db('SELECT COUNT(*) AS n FROM collection_products WHERE collection_id = %s', [c['id']], one=True)
        c['count'] = int((cnt or {}).get('n') or 0)
    return render_template('admin_collections.html', rows=rows)


@app.route('/admin/collection/add', methods=['GET', 'POST'])
@login_required
def admin_collection_add():
    if not _require_admin():
        return redirect(url_for('index'))
    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()[:255]
        season = (request.form.get('season') or '').strip()[:50] or None
        desc = (request.form.get('description') or '').strip() or None
        image = (request.form.get('image') or '').strip()[:1000] or None
        active = 1 if request.form.get('is_active') else 0
        pids = request.form.getlist('product_ids')
        if len(title) < 3:
            flash('Tiêu đề quá ngắn!', 'danger')
            return render_template('admin_collection_form.html', action='Thêm collection', c=request.form.to_dict(), prods=query_db('SELECT id, name FROM products WHERE is_active=1 ORDER BY id DESC') or [], picked=set(pids))
        slug = slugify(title)
        base, i = slug, 1
        while query_db('SELECT id FROM collections WHERE slug = %s', [slug], one=True):
            i += 1
            slug = f'{base}-{i}'
        cid = execute_db('INSERT INTO collections (slug, title, description, image, season, is_active) VALUES (%s,%s,%s,%s,%s,%s)',
                         (slug, title, desc, image, season, active), lastrowid=True)
        for pid in pids:
            try:
                execute_db('INSERT IGNORE INTO collection_products (collection_id, product_id) VALUES (%s,%s)', (cid, int(pid)))
            except (ValueError, TypeError):
                continue
        flash('Đã thêm collection!', 'success')
        return redirect(url_for('admin_collections'))
    prods = query_db('SELECT id, name FROM products WHERE is_active = 1 ORDER BY id DESC') or []
    return render_template('admin_collection_form.html', action='Thêm collection', c={}, prods=prods, picked=set())


@app.route('/admin/collection/edit/<int:cid>', methods=['GET', 'POST'])
@login_required
def admin_collection_edit(cid):
    if not _require_admin():
        return redirect(url_for('index'))
    c = query_db('SELECT * FROM collections WHERE id = %s', [cid], one=True)
    if not c:
        flash('Không tìm thấy collection!', 'danger')
        return redirect(url_for('admin_collections'))
    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()[:255]
        season = (request.form.get('season') or '').strip()[:50] or None
        desc = (request.form.get('description') or '').strip() or None
        image = (request.form.get('image') or '').strip()[:1000] or None
        active = 1 if request.form.get('is_active') else 0
        pids = request.form.getlist('product_ids')
        if len(title) < 3:
            flash('Tiêu đề quá ngắn!', 'danger')
            return redirect(url_for('admin_collection_edit', cid=cid))
        execute_db('UPDATE collections SET title=%s, description=%s, image=%s, season=%s, is_active=%s WHERE id=%s',
                   (title, desc, image, season, active, cid))
        execute_db('DELETE FROM collection_products WHERE collection_id = %s', [cid])
        for pid in pids:
            try:
                execute_db('INSERT IGNORE INTO collection_products (collection_id, product_id) VALUES (%s,%s)', (cid, int(pid)))
            except (ValueError, TypeError):
                continue
        flash('Đã cập nhật collection!', 'success')
        return redirect(url_for('admin_collections'))
    prods = query_db('SELECT id, name FROM products WHERE is_active = 1 ORDER BY id DESC') or []
    picked = {str(r['product_id']) for r in (query_db('SELECT product_id FROM collection_products WHERE collection_id = %s', [cid]) or [])}
    return render_template('admin_collection_form.html', action='Sửa collection', c=c, prods=prods, picked=picked)


@app.route('/admin/collection/delete/<int:cid>', methods=['POST'])
@login_required
def admin_collection_delete(cid):
    if not _require_admin():
        return redirect(url_for('index'))
    execute_db('DELETE FROM collections WHERE id = %s', [cid])
    flash('Đã xóa collection!', 'success')
    return redirect(url_for('admin_collections'))


@app.route('/admin/posts')
@login_required
def admin_posts():
    if not _require_admin():
        return redirect(url_for('index'))
    rows = query_db('SELECT p.*, c.title AS ctitle FROM posts p LEFT JOIN collections c ON c.id = p.collection_id ORDER BY p.id DESC') or []
    return render_template('admin_posts.html', rows=rows)


@app.route('/admin/post/add', methods=['GET', 'POST'])
@login_required
def admin_post_add():
    if not _require_admin():
        return redirect(url_for('index'))
    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()[:255]
        content = (request.form.get('content') or '').strip()
        image = (request.form.get('image') or '').strip()[:1000] or None
        try:
            coll = int(request.form.get('collection_id') or 0) or None
        except (ValueError, TypeError):
            coll = None
        active = 1 if request.form.get('is_active') else 0
        pids = request.form.getlist('product_ids')
        if len(title) < 3 or len(content) < 10:
            flash('Tiêu đề/nội dung quá ngắn!', 'danger')
            return redirect(url_for('admin_post_add'))
        slug = slugify(title)
        base, i = slug, 1
        while query_db('SELECT id FROM posts WHERE slug = %s', [slug], one=True):
            i += 1
            slug = f'{base}-{i}'
        pid = execute_db('INSERT INTO posts (slug, title, content, image, collection_id, is_active) VALUES (%s,%s,%s,%s,%s,%s)',
                         (slug, title, content, image, coll, active), lastrowid=True)
        for pr in pids:
            try:
                execute_db('INSERT IGNORE INTO post_products (post_id, product_id) VALUES (%s,%s)', (pid, int(pr)))
            except (ValueError, TypeError):
                continue
        flash('Đã thêm bài viết!', 'success')
        return redirect(url_for('admin_posts'))
    prods = query_db('SELECT id, name FROM products WHERE is_active = 1 ORDER BY id DESC') or []
    colls = query_db('SELECT id, title FROM collections ORDER BY id DESC') or []
    return render_template('admin_post_form.html', action='Thêm bài viết', p={}, prods=prods, colls=colls, picked=set())


@app.route('/admin/post/edit/<int:pid>', methods=['GET', 'POST'])
@login_required
def admin_post_edit(pid):
    if not _require_admin():
        return redirect(url_for('index'))
    p = query_db('SELECT * FROM posts WHERE id = %s', [pid], one=True)
    if not p:
        flash('Không tìm thấy bài viết!', 'danger')
        return redirect(url_for('admin_posts'))
    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()[:255]
        content = (request.form.get('content') or '').strip()
        image = (request.form.get('image') or '').strip()[:1000] or None
        try:
            coll = int(request.form.get('collection_id') or 0) or None
        except (ValueError, TypeError):
            coll = None
        active = 1 if request.form.get('is_active') else 0
        pids = request.form.getlist('product_ids')
        if len(title) < 3 or len(content) < 10:
            flash('Tiêu đề/nội dung quá ngắn!', 'danger')
            return redirect(url_for('admin_post_edit', pid=pid))
        execute_db('UPDATE posts SET title=%s, content=%s, image=%s, collection_id=%s, is_active=%s WHERE id=%s',
                   (title, content, image, coll, active, pid))
        execute_db('DELETE FROM post_products WHERE post_id = %s', [pid])
        for pr in pids:
            try:
                execute_db('INSERT IGNORE INTO post_products (post_id, product_id) VALUES (%s,%s)', (pid, int(pr)))
            except (ValueError, TypeError):
                continue
        flash('Đã cập nhật bài viết!', 'success')
        return redirect(url_for('admin_posts'))
    prods = query_db('SELECT id, name FROM products WHERE is_active = 1 ORDER BY id DESC') or []
    colls = query_db('SELECT id, title FROM collections ORDER BY id DESC') or []
    picked = {str(r['product_id']) for r in (query_db('SELECT product_id FROM post_products WHERE post_id = %s', [pid]) or [])}
    return render_template('admin_post_form.html', action='Sửa bài viết', p=p, prods=prods, colls=colls, picked=picked)


@app.route('/admin/post/delete/<int:pid>', methods=['POST'])
@login_required
def admin_post_delete(pid):
    if not _require_admin():
        return redirect(url_for('index'))
    execute_db('DELETE FROM posts WHERE id = %s', [pid])
    flash('Đã xóa bài viết!', 'success')
    return redirect(url_for('admin_posts'))


@app.route('/admin/jobs')
@login_required
def admin_jobs():
    if not _require_admin():
        return redirect(url_for('index'))
    rows = query_db('SELECT j.*, (SELECT COUNT(*) FROM applications a WHERE a.job_id = j.id) AS apps FROM jobs j ORDER BY j.id DESC') or []
    return render_template('admin_jobs.html', rows=rows)


@app.route('/admin/job/add', methods=['GET', 'POST'])
@login_required
def admin_job_add():
    if not _require_admin():
        return redirect(url_for('index'))
    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()[:255]
        loc = (request.form.get('location') or '').strip()[:255] or None
        salary = (request.form.get('salary') or '').strip()[:255] or None
        desc = (request.form.get('description') or '').strip()
        active = 1 if request.form.get('is_active') else 0
        if len(title) < 3 or len(desc) < 10:
            flash('Tiêu đề/mô tả quá ngắn!', 'danger')
            return render_template('admin_job_form.html', action='Thêm tin tuyển dụng', j=request.form.to_dict())
        execute_db('INSERT INTO jobs (title, location, salary, description, is_active) VALUES (%s,%s,%s,%s,%s)',
                   (title, loc, salary, desc, active))
        flash('Đã thêm tin tuyển dụng!', 'success')
        return redirect(url_for('admin_jobs'))
    return render_template('admin_job_form.html', action='Thêm tin tuyển dụng', j={})


@app.route('/admin/job/edit/<int:jid>', methods=['GET', 'POST'])
@login_required
def admin_job_edit(jid):
    if not _require_admin():
        return redirect(url_for('index'))
    j = query_db('SELECT * FROM jobs WHERE id = %s', [jid], one=True)
    if not j:
        flash('Không tìm thấy tin!', 'danger')
        return redirect(url_for('admin_jobs'))
    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()[:255]
        loc = (request.form.get('location') or '').strip()[:255] or None
        salary = (request.form.get('salary') or '').strip()[:255] or None
        desc = (request.form.get('description') or '').strip()
        active = 1 if request.form.get('is_active') else 0
        if len(title) < 3 or len(desc) < 10:
            flash('Tiêu đề/mô tả quá ngắn!', 'danger')
            return render_template('admin_job_form.html', action='Sửa tin tuyển dụng', j=request.form.to_dict())
        execute_db('UPDATE jobs SET title=%s, location=%s, salary=%s, description=%s, is_active=%s WHERE id=%s',
                   (title, loc, salary, desc, active, jid))
        flash('Đã cập nhật!', 'success')
        return redirect(url_for('admin_jobs'))
    return render_template('admin_job_form.html', action='Sửa tin tuyển dụng', j=j)


@app.route('/admin/job/delete/<int:jid>', methods=['POST'])
@login_required
def admin_job_delete(jid):
    if not _require_admin():
        return redirect(url_for('index'))
    execute_db('DELETE FROM jobs WHERE id = %s', [jid])
    flash('Đã xóa tin tuyển dụng!', 'success')
    return redirect(url_for('admin_jobs'))


@app.route('/admin/applications')
@login_required
def admin_applications():
    if not _require_admin():
        return redirect(url_for('index'))
    status = (request.args.get('status') or '').strip()
    if status in ('Moi', 'Da_xem', 'Dat', 'Loai'):
        rows = query_db('''SELECT a.*, j.title AS jtitle FROM applications a JOIN jobs j ON j.id = a.job_id
                           WHERE a.status = %s ORDER BY a.id DESC''', [status])
    else:
        rows = query_db('SELECT a.*, j.title AS jtitle FROM applications a JOIN jobs j ON j.id = a.job_id ORDER BY a.id DESC')
        status = ''
    counts = {}
    for s in ('Moi', 'Da_xem', 'Dat', 'Loai'):
        c = query_db('SELECT COUNT(id) AS cnt FROM applications WHERE status = %s', [s], one=True)
        counts[s] = int((c or {}).get('cnt') or 0)
    return render_template('admin_applications.html', rows=rows or [], counts=counts, status=status)


@app.route('/admin/application/<int:aid>/status', methods=['POST'])
@login_required
def admin_application_status(aid):
    if not _require_admin():
        return redirect(url_for('index'))
    st = (request.form.get('status') or '').strip()
    if st not in ('Moi', 'Da_xem', 'Dat', 'Loai'):
        flash('Trạng thái không hợp lệ!', 'danger')
        return redirect(url_for('admin_applications'))
    execute_db('UPDATE applications SET status = %s WHERE id = %s', (st, aid))
    flash('Đã cập nhật hồ sơ!', 'success')
    return redirect(url_for('admin_applications'))


# ==========================================
# Nhom full: suggest/review-moderate/instore/notify/banner/combo/report/stafflog/bank
# ==========================================
@app.route('/search-suggest')
def search_suggest():
    from flask import jsonify
    q = (request.args.get('q') or '').strip()
    if len(q) < 2:
        return jsonify([])
    try:
        EP = eff_price_sql('p')
        rows = query_db(f"SELECT p.id, p.name, p.image, p.category, ({EP}) AS eff FROM products p WHERE p.is_active = 1 AND (p.name LIKE %s OR p.category LIKE %s) ORDER BY p.is_featured DESC, p.id DESC LIMIT 8",
                        [f'%{q}%', f'%{q}%']) or []
        out = [{'id': r['id'], 'name': r['name'], 'image': r.get('image'),
                'price': float(r.get('eff') or 0), 'url': url_for('product_detail', product_id=r['id'])} for r in rows]
        return jsonify(out)
    except Exception:
        return jsonify([])


@app.route('/review/<int:rid>/helpful', methods=['POST'])
@login_required
def review_helpful(rid):
    rv = query_db('SELECT id, product_id FROM reviews WHERE id = %s', [rid], one=True)
    if not rv:
        flash('Không tìm thấy đánh giá!', 'warning')
        return redirect(request.referrer or url_for('index'))
    try:
        execute_db('INSERT INTO review_helpful (review_id, user_id) VALUES (%s, %s)', [rid, current_user.id])
        execute_db('UPDATE reviews SET helpful = helpful + 1 WHERE id = %s', [rid])
        flash('Đã vote hữu ích!', 'success')
    except Exception as e:
        if 'Duplicate' in str(e):
            flash('Bạn đã vote rồi!', 'info')
        else:
            flash('Không vote được lúc này!', 'danger')
    return redirect(request.referrer or url_for('product_detail', product_id=rv['product_id']))


@app.route('/admin/reviews')
@login_required
def admin_reviews():
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    status = (request.args.get('status') or '').strip()
    if status in REVIEW_STATUSES:
        rows = query_db('SELECT r.*, p.name AS pname FROM reviews r JOIN products p ON p.id = r.product_id WHERE r.status = %s ORDER BY r.created_at DESC', [status])
    else:
        rows = query_db('SELECT r.*, p.name AS pname FROM reviews r JOIN products p ON p.id = r.product_id ORDER BY r.created_at DESC')
        status = ''
    counts = {}
    for s in REVIEW_STATUSES:
        c = query_db('SELECT COUNT(id) AS cnt FROM reviews WHERE status = %s', [s], one=True)
        counts[s] = int((c or {}).get('cnt') or 0)
    return render_template('admin_reviews.html', rows=rows or [], counts=counts, status=status)


@app.route('/admin/review/<int:rid>/moderate', methods=['POST'])
@login_required
def admin_review_moderate(rid):
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    action = (request.form.get('action') or '').strip()
    rv = query_db('SELECT * FROM reviews WHERE id = %s', [rid], one=True)
    if not rv:
        flash('Không tìm thấy đánh giá!', 'danger')
        return redirect(url_for('admin_reviews'))
    if action in ('Hien', 'An', 'Cho_duyet'):
        execute_db('UPDATE reviews SET status = %s WHERE id = %s', (action, rid))
        flash(f'Đã chuyển đánh giá sang {action}!', 'success')
    elif action == 'reply':
        reply = (request.form.get('reply') or '').strip()[:2000]
        if len(reply) < 2:
            flash('Trả lời quá ngắn!', 'danger')
        else:
            execute_db('UPDATE reviews SET reply = %s WHERE id = %s', (reply, rid))
            flash('Đã trả lời đánh giá!', 'success')
    elif action == 'delete':
        execute_db('DELETE FROM reviews WHERE id = %s', [rid])
        flash('Đã xóa đánh giá!', 'success')
    else:
        flash('Thao tác không hợp lệ!', 'danger')
    try:
        staff_log(f'Review {action}', None, f"Review #{rid} SP {rv.get('product_id')}")
    except Exception:
        pass
    return redirect(url_for('admin_reviews', status=request.args.get('status', '')))


@app.route('/admin/exchange-instore', methods=['GET', 'POST'])
@login_required
def admin_exchange_instore():
    """Đổi trực tiếp tại cửa hàng: NV nhập mã đơn/SĐT -> đổi ngay, không ship 2 chiều."""
    if not is_staff_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    order, lines, msg = None, [], ''
    q = (request.values.get('q') or '').strip()[:50]
    if q:
        if q.isdigit():
            order = query_db('SELECT * FROM orders WHERE id = %s', [int(q)], one=True)
        if not order:
            order = query_db('SELECT * FROM orders WHERE phone = %s ORDER BY created_at DESC LIMIT 1', [q], one=True)
        if not order:
            msg = 'Không tìm thấy đơn theo mã/SĐT!'
        else:
            lines = query_db('''SELECT oi.id AS line_id, oi.product_id, oi.quantity, oi.variant_id, oi.variant_size, oi.variant_color,
                                p.name, p.price, p.sale_price, p.sale_start, p.sale_end, p.category
                                FROM order_items oi JOIN products p ON p.id = oi.product_id WHERE oi.order_id = %s''', [order['id']]) or []
    if request.method == 'POST' and request.form.get('do_exchange'):
        try:
            line_id = int(request.form.get('line_id') or 0)
            new_vid = int(request.form.get('new_variant_id') or 0)
        except (ValueError, TypeError):
            flash('Dữ liệu không hợp lệ!', 'danger')
            return redirect(url_for('admin_exchange_instore'))
        line = query_db('SELECT * FROM order_items WHERE id = %s', [line_id], one=True)
        od = query_db('SELECT * FROM orders WHERE id = %s', [line['order_id'] if line else 0], one=True)
        if not line or not od:
            flash('Dòng đơn không tồn tại!', 'danger')
            return redirect(url_for('admin_exchange_instore'))
        prod = query_db('SELECT * FROM products WHERE id = %s', [line['product_id']], one=True)
        blocked, reason = is_exchange_blocked(prod)
        if blocked:
            flash(reason, 'danger')
            return redirect(url_for('admin_exchange_instore') + f'?q={od["id"]}')
        nv = query_db('SELECT * FROM product_variants WHERE id = %s AND product_id = %s', [new_vid, line['product_id']], one=True)
        if not nv or int(nv.get('stock') or 0) < int(line['quantity']):
            flash('Phân loại mới không đủ hàng!', 'danger')
            return redirect(url_for('admin_exchange_instore') + f'?q={od["id"]}')
        db = get_db()
        try:
            with db.cursor() as cur:
                cur.execute('START TRANSACTION')
                cur.execute('SELECT stock FROM product_variants WHERE id = %s FOR UPDATE', [new_vid])
                if int((cur.fetchone() or {}).get('stock') or 0) < int(line['quantity']):
                    db.rollback()
                    flash('Phân loại mới vừa hết!', 'danger')
                    return redirect(url_for('admin_exchange_instore') + f'?q={od["id"]}')
                if line.get('variant_id'):
                    cur.execute('UPDATE product_variants SET stock = stock + %s WHERE id = %s', [line['quantity'], line['variant_id']])
                cur.execute('UPDATE product_variants SET stock = stock - %s WHERE id = %s AND stock >= %s', [line['quantity'], new_vid, line['quantity']])
                cur.execute('UPDATE order_items SET variant_id=%s, variant_size=%s, variant_color=%s WHERE id=%s',
                            [new_vid, nv['size'], nv['color'], line_id])
                cur.execute("INSERT INTO return_requests (order_id, order_item_id, product_id, old_variant_id, new_variant_id, reason, status, in_store) VALUES (%s,%s,%s,%s,%s,%s,'Hoàn thành',1)",
                            [od['id'], line_id, line['product_id'], line.get('variant_id'), new_vid, 'Doi tai quay'])
                db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
            flash('Đổi tại quầy thất bại!', 'danger')
            return redirect(url_for('admin_exchange_instore') + f'?q={od["id"]}')
        try:
            push_notification(od.get('user_id'), f"Đơn #ORD-{od['id']} đã đổi size tại cửa hàng.", "/my-orders")
            staff_log('Doi tai quay', od['id'], f"Line {line_id} -> variant {new_vid}")
        except Exception:
            pass
        flash('Đã đổi tại quầy thành công!', 'success')
        return redirect(url_for('admin_exchange_instore') + f'?q={od["id"]}')
    options_map = {}
    if order:
        for ln in lines:
            options_map[ln['line_id']] = [v for v in get_variants(ln['product_id']) if v['stock'] >= ln['quantity'] and v['id'] != ln.get('variant_id')]
    return render_template('admin_exchange_instore.html', order=order, lines=lines, options_map=options_map, q=q, msg=msg)


@app.route('/notifications')
@login_required
def notifications():
    rows = query_db('SELECT * FROM notifications WHERE user_id = %s ORDER BY id DESC LIMIT 30', [current_user.id]) or []
    return render_template('notifications.html', rows=rows)


@app.route('/notifications/read/<int:nid>', methods=['POST'])
@login_required
def notification_read(nid):
    execute_db('UPDATE notifications SET is_read = 1 WHERE id = %s AND user_id = %s', (nid, current_user.id))
    return redirect(request.referrer or url_for('notifications'))


@app.route('/notifications/read-all', methods=['POST'])
@login_required
def notifications_read_all():
    execute_db('UPDATE notifications SET is_read = 1 WHERE user_id = %s', [current_user.id])
    return redirect(request.referrer or url_for('notifications'))


@app.route('/huong-dan-chuyen-khoan')
def bank_guide():
    accounts = (get_setting('shop_bank_accounts', '') or '').strip()
    return render_template('bank_guide.html', accounts=accounts)


@app.route('/admin/banners')
@login_required
def admin_banners():
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    rows = query_db('SELECT * FROM banners ORDER BY sort_order, id') or []
    return render_template('admin_banners.html', rows=rows)


@app.route('/admin/banner/add', methods=['GET', 'POST'])
@login_required
def admin_banner_add():
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()[:255] or None
        image = (request.form.get('image') or '').strip()[:1000]
        link = (request.form.get('link') or '').strip()[:1000] or None
        try:
            sort = int(request.form.get('sort_order') or 0)
        except (ValueError, TypeError):
            sort = 0
        active = 1 if request.form.get('is_active') else 0
        if not image or not (image.startswith('http://') or image.startswith('https://')):
            flash('Ảnh banner phải là URL http(s)!', 'danger')
            return render_template('admin_banner_form.html', action='Thêm banner', b=request.form.to_dict())
        execute_db('INSERT INTO banners (title, image, link, sort_order, is_active) VALUES (%s,%s,%s,%s,%s)',
                   (title, image, link, sort, active))
        flash('Đã thêm banner!', 'success')
        return redirect(url_for('admin_banners'))
    return render_template('admin_banner_form.html', action='Thêm banner', b={})


@app.route('/admin/banner/edit/<int:bid>', methods=['GET', 'POST'])
@login_required
def admin_banner_edit(bid):
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    b = query_db('SELECT * FROM banners WHERE id = %s', [bid], one=True)
    if not b:
        flash('Không tìm thấy banner!', 'danger')
        return redirect(url_for('admin_banners'))
    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()[:255] or None
        image = (request.form.get('image') or '').strip()[:1000]
        link = (request.form.get('link') or '').strip()[:1000] or None
        try:
            sort = int(request.form.get('sort_order') or 0)
        except (ValueError, TypeError):
            sort = 0
        active = 1 if request.form.get('is_active') else 0
        if not image or not (image.startswith('http://') or image.startswith('https://')):
            flash('Ảnh banner phải là URL http(s)!', 'danger')
            return render_template('admin_banner_form.html', action='Sửa banner', b=request.form.to_dict())
        execute_db('UPDATE banners SET title=%s, image=%s, link=%s, sort_order=%s, is_active=%s WHERE id=%s',
                   (title, image, link, sort, active, bid))
        flash('Đã cập nhật banner!', 'success')
        return redirect(url_for('admin_banners'))
    return render_template('admin_banner_form.html', action='Sửa banner', b=b)


@app.route('/admin/banner/delete/<int:bid>', methods=['POST'])
@login_required
def admin_banner_delete(bid):
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    execute_db('DELETE FROM banners WHERE id = %s', [bid])
    flash('Đã xóa banner!', 'success')
    return redirect(url_for('admin_banners'))


def _parse_combo_form(form):
    errors = []
    name = (form.get('name') or '').strip()[:255]
    ctype = (form.get('combo_type') or 'BUY_GET').upper()
    if not name or len(name) < 3:
        errors.append('Tên combo quá ngắn!')
    if ctype not in ('BUY_GET', 'BUNDLE'):
        errors.append('Loại combo không hợp lệ!')
        ctype = 'BUY_GET'
    try:
        tid = int(form.get('trigger_product_id') or 0) or None
    except (ValueError, TypeError):
        tid, errors = None, errors + ['SP kích hoạt không hợp lệ!']
    try:
        tq = int(form.get('trigger_qty') or 1)
    except (ValueError, TypeError):
        tq = 0
    try:
        gid = int(form.get('gift_product_id') or 0) or None
    except (ValueError, TypeError):
        gid, errors = None, errors + ['SP tặng không hợp lệ!']
    try:
        gq = int(form.get('gift_qty') or 1)
    except (ValueError, TypeError):
        gq = 0
    bundle_ids = (form.get('bundle_product_ids') or '').strip()[:500] or None
    try:
        bprice_raw = (form.get('bundle_price') or '').strip()
        bprice = float(bprice_raw) if bprice_raw else None
    except (ValueError, TypeError):
        bprice, errors = None, errors + ['Giá gói không hợp lệ!']
    def _dt(raw):
        raw = (raw or '').strip()
        if not raw:
            return None
        for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
            try:
                return datetime.strptime(raw[:16], fmt)
            except (ValueError, TypeError):
                continue
        errors.append(f'Mốc giờ "{raw}" phải dạng YYYY-MM-DD HH:MM!')
        return None
    start = _dt(form.get('start_at'))
    end = _dt(form.get('end_at'))
    if start and end and start > end:
        errors.append('Bắt đầu phải trước kết thúc!')
    if ctype == 'BUY_GET':
        if not tid or not gid or tq < 1 or gq < 1:
            errors.append('Mua X tặng Y cần đủ SP kích hoạt/tặng + SL >= 1!')
    else:
        ids = [x for x in (bundle_ids or '').replace(';', ',').split(',') if x.strip().isdigit()]
        if len(ids) < 2 or not bprice or bprice <= 0:
            errors.append('Set bộ cần >= 2 SP + giá gói > 0!')
    active = 1 if form.get('is_active') else 0
    cleaned = {'name': name, 'combo_type': ctype, 'trigger_product_id': tid, 'trigger_qty': tq,
               'gift_product_id': gid, 'gift_qty': gq, 'bundle_product_ids': bundle_ids,
               'bundle_price': bprice, 'start_at': start, 'end_at': end, 'is_active': active}
    return errors, cleaned


@app.route('/admin/combos')
@login_required
def admin_combos():
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    rows = query_db('SELECT * FROM combos ORDER BY id DESC') or []
    for r in rows:
        try:
            r['running'] = r.get('is_active') == 1 and (not r.get('start_at') or r.get('start_at') <= datetime.now()) and (not r.get('end_at') or r.get('end_at') >= datetime.now())
        except Exception:
            r['running'] = bool(r.get('is_active'))
    return render_template('admin_combos.html', rows=rows)


@app.route('/admin/combo/add', methods=['GET', 'POST'])
@login_required
def admin_combo_add():
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    if request.method == 'POST':
        errors, c = _parse_combo_form(request.form)
        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('admin_combo_form.html', action='Thêm combo', c=request.form.to_dict(), prods=query_db('SELECT id, name FROM products WHERE is_active=1 ORDER BY id DESC') or [])
        execute_db('''INSERT INTO combos (name, combo_type, trigger_product_id, trigger_qty, gift_product_id, gift_qty,
                      bundle_product_ids, bundle_price, start_at, end_at, is_active)
                      VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                   (c['name'], c['combo_type'], c['trigger_product_id'], c['trigger_qty'], c['gift_product_id'],
                    c['gift_qty'], c['bundle_product_ids'], c['bundle_price'], c['start_at'], c['end_at'], c['is_active']))
        flash('Đã thêm combo!', 'success')
        return redirect(url_for('admin_combos'))
    return render_template('admin_combo_form.html', action='Thêm combo', c={}, prods=query_db('SELECT id, name FROM products WHERE is_active=1 ORDER BY id DESC') or [])


@app.route('/admin/combo/edit/<int:cid>', methods=['GET', 'POST'])
@login_required
def admin_combo_edit(cid):
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    c0 = query_db('SELECT * FROM combos WHERE id = %s', [cid], one=True)
    if not c0:
        flash('Không tìm thấy combo!', 'danger')
        return redirect(url_for('admin_combos'))
    if request.method == 'POST':
        errors, c = _parse_combo_form(request.form)
        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('admin_combo_form.html', action='Sửa combo', c=request.form.to_dict(), prods=query_db('SELECT id, name FROM products WHERE is_active=1 ORDER BY id DESC') or [])
        execute_db('''UPDATE combos SET name=%s, combo_type=%s, trigger_product_id=%s, trigger_qty=%s, gift_product_id=%s,
                      gift_qty=%s, bundle_product_ids=%s, bundle_price=%s, start_at=%s, end_at=%s, is_active=%s WHERE id=%s''',
                   (c['name'], c['combo_type'], c['trigger_product_id'], c['trigger_qty'], c['gift_product_id'],
                    c['gift_qty'], c['bundle_product_ids'], c['bundle_price'], c['start_at'], c['end_at'], c['is_active'], cid))
        flash('Đã cập nhật combo!', 'success')
        return redirect(url_for('admin_combos'))
    return render_template('admin_combo_form.html', action='Sửa combo', c=c0, prods=query_db('SELECT id, name FROM products WHERE is_active=1 ORDER BY id DESC') or [])


@app.route('/admin/combo/delete/<int:cid>', methods=['POST'])
@login_required
def admin_combo_delete(cid):
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    used = query_db('SELECT order_id FROM order_combos WHERE combo_id = %s LIMIT 1', [cid], one=True)
    if used:
        execute_db('UPDATE combos SET is_active = 0 WHERE id = %s', [cid])
        flash('Combo đã có đơn dùng nên chuyển thành TẮT thay vì xóa!', 'warning')
    else:
        execute_db('DELETE FROM combos WHERE id = %s', [cid])
        flash('Đã xóa combo!', 'success')
    return redirect(url_for('admin_combos'))


@app.route('/admin/report-channel')
@login_required
def admin_report_channel():
    if not is_staff_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    month = (request.args.get('month_num') or date.today().strftime('%m')).strip()
    year = (request.args.get('year_num') or date.today().strftime('%Y')).strip()
    if month not in [f'{m:02d}' for m in range(1, 13)]:
        month = date.today().strftime('%m')
    if year not in ['2024', '2025', '2026', '2027']:
        year = date.today().strftime('%Y')
    by_channel = query_db('''SELECT COALESCE(channel,'online') AS ch, COUNT(id) AS orders, SUM(total_amount) AS rev
                             FROM orders WHERE status='Hoàn thành' AND YEAR(created_at)=%s AND MONTH(created_at)=%s
                             GROUP BY ch''', [year, month]) or []
    by_store = query_db('''SELECT COALESCE(s.branch_name, 'Online/Không chi nhánh') AS store, COUNT(o.id) AS orders, SUM(o.total_amount) AS rev
                           FROM orders o LEFT JOIN stores s ON s.id = o.store_id
                           WHERE o.status='Hoàn thành' AND YEAR(o.created_at)=%s AND MONTH(o.created_at)=%s
                           GROUP BY store ORDER BY rev DESC''', [year, month]) or []
    try:
        stock_val = query_db('SELECT SUM(stock * price) AS v, SUM(stock) AS q FROM products WHERE is_active = 1', one=True) or {}
        stock_by_cat = query_db('SELECT category, SUM(stock * price) AS v, SUM(stock) AS q FROM products WHERE is_active = 1 GROUP BY category ORDER BY v DESC') or []
    except Exception:
        stock_val, stock_by_cat = {}, []
    return render_template('admin_report_channel.html', by_channel=by_channel, by_store=by_store,
                           stock_val=stock_val, stock_by_cat=stock_by_cat, month=month, year=year)


@app.route('/admin/staff-logs')
@login_required
def admin_staff_logs():
    if not is_admin_user():
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    try:
        rate = float(get_setting('commission_rate', '2') or 2)
    except (ValueError, TypeError):
        rate = 2
    month = (request.args.get('month_num') or date.today().strftime('%m')).strip()
    year = (request.args.get('year_num') or date.today().strftime('%Y')).strip()
    if month not in [f'{m:02d}' for m in range(1, 13)]:
        month = date.today().strftime('%m')
    if year not in ['2024', '2025', '2026', '2027']:
        year = date.today().strftime('%Y')
    logs = query_db('''SELECT l.*, u.name AS uname FROM staff_logs l JOIN users u ON u.id = l.user_id
                       WHERE YEAR(l.created_at)=%s AND MONTH(l.created_at)=%s ORDER BY l.id DESC LIMIT 200''', [year, month]) or []
    comm = query_db('''SELECT u.name AS uname, COUNT(DISTINCT l.order_id) AS orders, SUM(o.total_amount) AS rev
                       FROM staff_logs l JOIN users u ON u.id = l.user_id LEFT JOIN orders o ON o.id = l.order_id AND o.status='Hoàn thành'
                       WHERE YEAR(l.created_at)=%s AND MONTH(l.created_at)=%s AND l.action LIKE %s
                       GROUP BY u.name ORDER BY rev DESC''', [year, month, '%Hoàn thành%']) or []
    for r in comm:
        try:
            r['commission'] = float(r.get('rev') or 0) * rate / 100
        except (ValueError, TypeError):
            r['commission'] = 0
    return render_template('admin_staff_logs.html', logs=logs, comm=comm, rate=rate, month=month, year=year)


@app.route('/admin/export/excel')
@login_required
def export_excel():
    if not is_admin_user(): 
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    orders = query_db('SELECT id, COALESCE(fullname, CONCAT("User #", user_id)) AS fullname, phone, total_amount, status, created_at FROM orders ORDER BY created_at DESC')
    if not orders:
        df = pd.DataFrame(columns=['Mã Đơn', 'Khách hàng', 'SĐT', 'Tổng Tiền (đ)', 'Trạng thái', 'Ngày Đặt'])
    else:
        df = pd.DataFrame(orders)
        # Map đúng cột dù query có đổi thứ tự
        try:
            df = df[['id', 'fullname', 'phone', 'total_amount', 'status', 'created_at']]
        except KeyError:
            pass
        df.columns = ['Mã Đơn', 'Khách hàng', 'SĐT', 'Tổng Tiền (đ)', 'Trạng thái', 'Ngày Đặt'][:len(df.columns)]
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer: df.to_excel(writer, index=False)
    output.seek(0)
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name='DoanhThu.xlsx')

@app.route('/admin/export/pdf')
@login_required
def export_pdf():
    if not is_admin_user(): 
        flash('Bạn không có quyền!', 'danger')
        return redirect(url_for('index'))
    return render_template('admin_print_report.html', orders=query_db('SELECT * FROM orders ORDER BY created_at DESC'), namespace_today=date.today().strftime('%d/%m/%Y'))

if __name__ == '__main__':
    app.run(debug=False, port=5000)