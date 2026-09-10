-- Schema chuẩn đồng bộ từ DB thật fashion_shop (2026-09-09)
-- Đã bao gồm fix: users.role, products.is_active, orders.user_id/status/payment_method/discount_amount,
-- reviews.rating, cart/wishlist/vouchers. Giữ dữ liệu khi chạy lại nhờ IF NOT EXISTS.
-- Lưu ý: chạy file migration_fix_phpmyadmin.sql trước nếu DB cũ chưa có các cột này.

CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT,
  name VARCHAR(100) NOT NULL,
  email VARCHAR(255) NOT NULL,
  phone VARCHAR(15) NULL COMMENT 'SĐT khách (A1.4): match đơn tại quầy + tích điểm',
  password_hash VARCHAR(255) NULL,
  password VARCHAR(255) NULL COMMENT 'werkzeug scrypt, cột chính app đang dùng',
  is_admin TINYINT(1) NOT NULL DEFAULT 0,
  role VARCHAR(50) NOT NULL DEFAULT 'Khách hàng',
  points INT NOT NULL DEFAULT 0 COMMENT 'điểm thưởng (Phase 3): 1đ = 1000đ',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY email (email),
  KEY idx_phone (phone)
);

CREATE TABLE IF NOT EXISTS products (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  price DECIMAL(12,2) NOT NULL,
  sale_price DECIMAL(12,2) NULL COMMENT 'giá sale (Phase 2), NULL = không sale',
  sale_start DATETIME NULL,
  sale_end DATETIME NULL,
  stock INT NOT NULL,
  category VARCHAR(100) NOT NULL,
  description TEXT NOT NULL,
  image VARCHAR(500) NOT NULL,
  is_featured TINYINT(1) NOT NULL DEFAULT 0,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS orders (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NULL,
  fullname VARCHAR(255) NOT NULL,
  email VARCHAR(255) NOT NULL,
  phone VARCHAR(50) NOT NULL,
  address TEXT NOT NULL,
  total_amount DECIMAL(12,2) NOT NULL,
  discount_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
  voucher_code VARCHAR(50) NULL COMMENT 'mã voucher đã dùng, NULL nếu không dùng',
  points_used INT NOT NULL DEFAULT 0 COMMENT 'điểm đã dùng (Phase 3)',
  points_discount DECIMAL(12,2) NOT NULL DEFAULT 0 COMMENT 'tiền trừ từ điểm (Phase 3)',
  ship_zone VARCHAR(20) NULL COMMENT 'noi_thanh/ngoai_thanh (Phase 2)',
  shipping_fee DECIMAL(12,2) NOT NULL DEFAULT 0,
  status VARCHAR(50) NOT NULL DEFAULT 'Chờ thanh toán',
  payment_method VARCHAR(50) NOT NULL DEFAULT 'COD',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX (user_id)
);

CREATE TABLE IF NOT EXISTS order_items (
  id INT AUTO_INCREMENT PRIMARY KEY,
  order_id INT NOT NULL,
  product_id INT NOT NULL,
  variant_id INT NULL COMMENT 'biến thể lúc mua (Phase 1)',
  variant_size VARCHAR(10) NULL COMMENT 'snapshot size để giữ lịch sử',
  variant_color VARCHAR(20) NULL COMMENT 'snapshot màu để giữ lịch sử',
  quantity INT NOT NULL,
  unit_price DECIMAL(12,2) NOT NULL,
  FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
  FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS product_variants (
  id INT AUTO_INCREMENT PRIMARY KEY,
  product_id INT NOT NULL,
  size VARCHAR(10) NOT NULL DEFAULT 'M',
  color VARCHAR(20) NOT NULL DEFAULT 'Mặc định',
  stock INT NOT NULL DEFAULT 0,
  sku VARCHAR(50) NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uniq_prod_size_color (product_id, size, color),
  KEY idx_variant_product (product_id),
  FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reviews (
  id INT AUTO_INCREMENT PRIMARY KEY,
  product_id INT NOT NULL,
  name VARCHAR(100) NOT NULL,
  comment TEXT NOT NULL,
  rating INT NOT NULL DEFAULT 5,
  image_url VARCHAR(500) NULL COMMENT 'ảnh thật KH (Phase 3)',
  order_id INT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uniq_product_name (product_id, name),
  FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cart (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  product_id INT NOT NULL,
  variant_id INT NULL COMMENT 'biến thể size/màu (Phase 1)',
  quantity INT NOT NULL DEFAULT 1,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uniq_cart_user_product (user_id, product_id),
  UNIQUE KEY uniq_cart_upv (user_id, product_id, variant_id),
  KEY idx_cart_user (user_id),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS wishlist (
  user_id INT NOT NULL,
  product_id INT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, product_id)
);

CREATE TABLE IF NOT EXISTS vouchers (
  id INT AUTO_INCREMENT PRIMARY KEY,
  code VARCHAR(50) NOT NULL UNIQUE,
  discount_amount DECIMAL(12,2) NOT NULL DEFAULT 0 COMMENT 'số tiền hoặc % (theo discount_type)',
  discount_type VARCHAR(10) NOT NULL DEFAULT 'FIXED' COMMENT 'FIXED|PERCENT (Phase 2)',
  max_discount DECIMAL(12,2) NOT NULL DEFAULT 0 COMMENT 'trần giảm cho loại % (Phase 2)',
  is_freeship TINYINT(1) NOT NULL DEFAULT 0 COMMENT '1 = miễn ship (Phase 2)',
  min_order_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
  usage_limit INT NOT NULL DEFAULT 0,
  expires_at DATE NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS return_requests (
  id INT AUTO_INCREMENT PRIMARY KEY,
  order_id INT NOT NULL,
  order_item_id INT NOT NULL COMMENT 'dòng món xin đổi (Phase 3)',
  product_id INT NOT NULL,
  old_variant_id INT NULL,
  new_variant_id INT NOT NULL,
  reason VARCHAR(255) NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'Chờ duyệt',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  KEY idx_ret_order (order_id),
  KEY idx_ret_item (order_item_id),
  FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS point_log (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  order_id INT NULL,
  points INT NOT NULL,
  type VARCHAR(10) NOT NULL COMMENT 'EARN/SPEND/REFUND/REVOKE (Phase 3)',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  KEY idx_pl_user (user_id),
  KEY idx_pl_order (order_id),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
