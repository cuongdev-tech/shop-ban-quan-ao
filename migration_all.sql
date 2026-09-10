-- FashionShop: 1 file migration duy nhat. Chay tren phpMyAdmin tab SQL -> Go.
-- Chay 1 lan sau khi import schema_mysql.sql. An toan chay lai nhieu lan.
-- Chot: freeship 500k / min order 0d / dong gia size / 1 don 1 qua / chi doi size.

-- ================= PHAN 1 - Fix DB cu (role, bien the, sale, diem, doi size) =================
-- 1. users: thêm role nếu thiếu
SET @col_exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='fashion_shop' AND TABLE_NAME='users' AND COLUMN_NAME='role');
SET @sql := IF(@col_exists=0, 'ALTER TABLE `users` ADD COLUMN `role` VARCHAR(50) NOT NULL DEFAULT ''Khách hàng'' AFTER `is_admin`', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Đảm bảo cột password (werkzeug scrypt) tồn tại
SET @col_exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='fashion_shop' AND TABLE_NAME='users' AND COLUMN_NAME='password');
SET @sql := IF(@col_exists=0, 'ALTER TABLE `users` ADD COLUMN `password` VARCHAR(255) NULL AFTER `email`', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Chuẩn hóa role từ is_admin cho dòng cũ bị NULL/sai
UPDATE `users` SET `role`='Admin' WHERE `is_admin`=1 AND (`role` IS NULL OR `role`='' OR `role`='Khách hàng');
UPDATE `users` SET `role`='Khách hàng' WHERE (`role` IS NULL OR `role`='') AND (`is_admin`=0 OR `is_admin` IS NULL);
UPDATE `users` SET `is_admin`=1 WHERE `role`='Admin';
UPDATE `users` SET `is_admin`=0 WHERE `role` IN ('Khách hàng','Nhân viên') AND `is_admin` IS NULL;

-- QUAN TRỌNG: Admin đang lưu plaintext '123456' ở cột password -> phải reset tay:
-- Vào users > Sửa dòng admin@shop.com, đặt password = hash scrypt mới (dùng chức năng đổi MK trong web sau khi code mới chạy),
-- hoặc chạy: UPDATE users SET password='<hash-cua-123456-mới>' WHERE email='admin@shop.com';
-- Không để plaintext. Cột password_hash cũ (bcrypt) giữ lại để đối chiếu, không xóa vội.

-- 2. products: thêm is_active
SET @col_exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='fashion_shop' AND TABLE_NAME='products' AND COLUMN_NAME='is_active');
SET @sql := IF(@col_exists=0, 'ALTER TABLE `products` ADD COLUMN `is_active` TINYINT(1) NOT NULL DEFAULT 1', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
UPDATE `products` SET `is_active`=1 WHERE `is_active` IS NULL;

-- 3. orders: thêm user_id/status/payment_method/discount_amount nếu thiếu
SET @col_exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='fashion_shop' AND TABLE_NAME='orders' AND COLUMN_NAME='user_id');
SET @sql := IF(@col_exists=0, 'ALTER TABLE `orders` ADD COLUMN `user_id` INT NULL AFTER `id`, ADD INDEX (`user_id`)', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @col_exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='fashion_shop' AND TABLE_NAME='orders' AND COLUMN_NAME='status');
SET @sql := IF(@col_exists=0, 'ALTER TABLE `orders` ADD COLUMN `status` VARCHAR(50) NOT NULL DEFAULT ''Chờ thanh toán'' AFTER `phone`', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @col_exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='fashion_shop' AND TABLE_NAME='orders' AND COLUMN_NAME='payment_method');
SET @sql := IF(@col_exists=0, 'ALTER TABLE `orders` ADD COLUMN `payment_method` VARCHAR(50) NOT NULL DEFAULT ''COD'' AFTER `status`', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @col_exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='fashion_shop' AND TABLE_NAME='orders' AND COLUMN_NAME='discount_amount');
SET @sql := IF(@col_exists=0, 'ALTER TABLE `orders` ADD COLUMN `discount_amount` DECIMAL(12,2) NOT NULL DEFAULT 0 AFTER `total_amount`', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Chuẩn hóa payment cũ: 'Tiền mặt' -> 'COD'
UPDATE `orders` SET `payment_method`='COD' WHERE `payment_method`='Tiền mặt';
-- Backfill đơn 17 rỗng + đơn 1,2 NULL (sửa id/email theo thực tế của bạn)
-- UPDATE `orders` SET `fullname`='My', `email`='mytruong@gmail.com' WHERE `id`=17 AND (`fullname` IS NULL OR `fullname`='');
-- UPDATE `orders` SET `user_id`=2 WHERE `id` IN (1,2) AND `user_id` IS NULL;

-- Cho phép fullname/email NULL tạm để checkout mới không lỗi (vì code mới đã ghi đủ, dòng này chỉ phòng DB cũ NOT NULL)
-- Nếu cột đang NOT NULL mà bạn muốn giữ, bỏ qua 2 dòng dưới.
-- ALTER TABLE `orders` MODIFY `fullname` VARCHAR(255) NULL;
-- ALTER TABLE `orders` MODIFY `email` VARCHAR(255) NULL;

-- 4. reviews: thêm rating + order_id + unique chống spam
SET @col_exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='fashion_shop' AND TABLE_NAME='reviews' AND COLUMN_NAME='rating');
SET @sql := IF(@col_exists=0, 'ALTER TABLE `reviews` ADD COLUMN `rating` INT NOT NULL DEFAULT 5 AFTER `comment`', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @col_exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='fashion_shop' AND TABLE_NAME='reviews' AND COLUMN_NAME='order_id');
SET @sql := IF(@col_exists=0, 'ALTER TABLE `reviews` ADD COLUMN `order_id` INT NULL AFTER `rating`', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Xóa trùng (giữ 1 dòng nhỏ nhất) trước khi tạo UNIQUE
DELETE r1 FROM `reviews` r1 JOIN `reviews` r2
  ON r1.product_id=r2.product_id AND r1.name=r2.name AND r1.id > r2.id;

SET @idx_exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS WHERE TABLE_SCHEMA='fashion_shop' AND TABLE_NAME='reviews' AND INDEX_NAME='uniq_product_name');
SET @sql := IF(@idx_exists=0, 'ALTER TABLE `reviews` ADD UNIQUE KEY `uniq_product_name` (`product_id`,`name`)', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 5. cart/wishlist/vouchers/order_items: tạo nếu thiếu, thêm PK chống trùng
CREATE TABLE IF NOT EXISTS `cart` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `user_id` INT NOT NULL,
  `product_id` INT NOT NULL,
  `quantity` INT NOT NULL DEFAULT 1,
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY `uniq_cart_user_product` (`user_id`,`product_id`),
  KEY `idx_cart_user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `wishlist` (
  `user_id` INT NOT NULL,
  `product_id` INT NOT NULL,
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_id`,`product_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `vouchers` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `code` VARCHAR(50) NOT NULL UNIQUE,
  `discount_amount` DECIMAL(12,2) NOT NULL DEFAULT 0,
  `min_order_amount` DECIMAL(12,2) NOT NULL DEFAULT 0,
  `usage_limit` INT NOT NULL DEFAULT 0,
  `expires_at` DATE NULL,
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 6. orders.voucher_code (thống kê đơn nào dùng mã nào, NULL nếu không dùng)
SET @col_exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='fashion_shop' AND TABLE_NAME='orders' AND COLUMN_NAME='voucher_code');
SET @sql := IF(@col_exists=0, 'ALTER TABLE `orders` ADD COLUMN `voucher_code` VARCHAR(50) NULL AFTER `discount_amount`, ADD INDEX (`voucher_code`)', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 7. Phase 1: biến thể size/màu + tồn kho theo biến thể
CREATE TABLE IF NOT EXISTS `product_variants` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `product_id` INT NOT NULL,
  `size` VARCHAR(10) NOT NULL DEFAULT 'M',
  `color` VARCHAR(20) NOT NULL DEFAULT 'Mặc định',
  `stock` INT NOT NULL DEFAULT 0,
  `sku` VARCHAR(50) NULL,
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY `uniq_prod_size_color` (`product_id`,`size`,`color`),
  KEY `idx_variant_product` (`product_id`),
  FOREIGN KEY (`product_id`) REFERENCES `products`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
INSERT INTO product_variants (product_id, size, color, stock)
  SELECT p.id, 'M', 'Mặc định', p.stock FROM products p
  LEFT JOIN product_variants v ON v.product_id = p.id WHERE v.id IS NULL;
SET @col_exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='fashion_shop' AND TABLE_NAME='cart' AND COLUMN_NAME='variant_id');
SET @sql := IF(@col_exists=0, 'ALTER TABLE `cart` ADD COLUMN `variant_id` INT NULL AFTER `product_id`, ADD INDEX (`variant_id`)', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @col_exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='fashion_shop' AND TABLE_NAME='order_items' AND COLUMN_NAME='variant_id');
SET @sql := IF(@col_exists=0, 'ALTER TABLE `order_items` ADD COLUMN `variant_id` INT NULL AFTER `product_id`, ADD INDEX (`variant_id`)', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @col_exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='fashion_shop' AND TABLE_NAME='order_items' AND COLUMN_NAME='variant_size');
SET @sql := IF(@col_exists=0, 'ALTER TABLE `order_items` ADD COLUMN `variant_size` VARCHAR(10) NULL AFTER `variant_id`, ADD COLUMN `variant_color` VARCHAR(20) NULL AFTER `variant_size`', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 8. Phase 2: sale + voucher %/freeship + ship vùng
SET @col_exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='fashion_shop' AND TABLE_NAME='products' AND COLUMN_NAME='sale_price');
SET @sql := IF(@col_exists=0, 'ALTER TABLE `products` ADD COLUMN `sale_price` DECIMAL(12,2) NULL AFTER `price`, ADD COLUMN `sale_start` DATETIME NULL AFTER `sale_price`, ADD COLUMN `sale_end` DATETIME NULL AFTER `sale_start`', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @col_exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='fashion_shop' AND TABLE_NAME='vouchers' AND COLUMN_NAME='discount_type');
SET @sql := IF(@col_exists=0, 'ALTER TABLE `vouchers` ADD COLUMN `discount_type` VARCHAR(10) NOT NULL DEFAULT ''FIXED'' AFTER `discount_amount`, ADD COLUMN `max_discount` DECIMAL(12,2) NOT NULL DEFAULT 0 AFTER `discount_type`, ADD COLUMN `is_freeship` TINYINT(1) NOT NULL DEFAULT 0 AFTER `max_discount`', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @col_exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='fashion_shop' AND TABLE_NAME='orders' AND COLUMN_NAME='ship_zone');
SET @sql := IF(@col_exists=0, 'ALTER TABLE `orders` ADD COLUMN `ship_zone` VARCHAR(20) NULL AFTER `voucher_code`, ADD COLUMN `shipping_fee` DECIMAL(12,2) NOT NULL DEFAULT 0 AFTER `ship_zone`', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 9. Phase 3: đổi size + review ảnh + điểm thưởng
CREATE TABLE IF NOT EXISTS `return_requests` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `order_id` INT NOT NULL,
  `order_item_id` INT NOT NULL,
  `product_id` INT NOT NULL,
  `old_variant_id` INT NULL,
  `new_variant_id` INT NOT NULL,
  `reason` VARCHAR(255) NULL,
  `status` VARCHAR(20) NOT NULL DEFAULT 'Chờ duyệt',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  KEY `idx_ret_order` (`order_id`),
  KEY `idx_ret_item` (`order_item_id`),
  FOREIGN KEY (`order_id`) REFERENCES `orders`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
SET @col_exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='fashion_shop' AND TABLE_NAME='reviews' AND COLUMN_NAME='image_url');
SET @sql := IF(@col_exists=0, 'ALTER TABLE `reviews` ADD COLUMN `image_url` VARCHAR(500) NULL AFTER `rating`', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @col_exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='fashion_shop' AND TABLE_NAME='users' AND COLUMN_NAME='points');
SET @sql := IF(@col_exists=0, 'ALTER TABLE `users` ADD COLUMN `points` INT NOT NULL DEFAULT 0 AFTER `role`', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @col_exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='fashion_shop' AND TABLE_NAME='orders' AND COLUMN_NAME='points_used');
SET @sql := IF(@col_exists=0, 'ALTER TABLE `orders` ADD COLUMN `points_used` INT NOT NULL DEFAULT 0 AFTER `voucher_code`, ADD COLUMN `points_discount` DECIMAL(12,2) NOT NULL DEFAULT 0 AFTER `points_used`', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
CREATE TABLE IF NOT EXISTS `point_log` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `user_id` INT NOT NULL,
  `order_id` INT NULL,
  `points` INT NOT NULL,
  `type` VARCHAR(10) NOT NULL,
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
  KEY `idx_pl_user` (`user_id`),
  KEY `idx_pl_order` (`order_id`),
  FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 10. A1.4: SĐT khách để match đơn tại quầy + tích điểm
SET @col_exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='fashion_shop' AND TABLE_NAME='users' AND COLUMN_NAME='phone');
SET @sql := IF(@col_exists=0, 'ALTER TABLE `users` ADD COLUMN `phone` VARCHAR(15) NULL AFTER `email`, ADD INDEX (`phone`)', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ================= PHAN 2 - Trang tinh, cua hang, qua tang, subscribers, contacts =================
CREATE TABLE IF NOT EXISTS settings (
  `key` VARCHAR(50) NOT NULL PRIMARY KEY,
  `value` TEXT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO settings (`key`, `value`) VALUES
  ('freeship_threshold', '500000'),
  ('min_order_amount', '0'),
  ('gift_min_amount', '500000'),
  ('shop_hotline', '1900 8888'),
  ('shop_bank', 'Vietcombank 1234567890 - FashionShop - Chi nhanh Da Nang');

CREATE TABLE IF NOT EXISTS pages (
  slug VARCHAR(50) NOT NULL PRIMARY KEY,
  title VARCHAR(255) NOT NULL,
  content TEXT NOT NULL,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO pages (slug, title, content) VALUES
('gioi-thieu', 'Gioi thieu', 'FashionShop la cua hang thoi trang nam nu. Chung toi tap trung chat lieu cotton de mac, form basic de phoi, gia minh bach, cho kiem hang truoc khi nhan va doi size trong 14 ngay con tem mac.'),
('lien-he', 'Lien he', 'Hotline 1900 8888 (8:00-22:00). Dia chi: 39 Dao Cong Chinh, Khue Trung, Da Nang. Email support@fashionshop.vn. De lai loi nhan qua form lien he, shop phan hoi trong gio lam viec.'),
('thanh-toan', 'Thanh toan', 'Nhan COD va Chuyen khoan QR. Don Chuyen khoan duoc giu hang khi khach bam Da chuyen. Khach vui long ghi ma don vao noi dung chuyen khoan de shop doi soat nhanh.'),
('giao-hang', 'Giao hang', 'Noi thanh giao trong 24h sau xac nhan, ngoai thanh 3-4 ngay qua GHN, giao gio hanh chinh 8h-17h. Don tu 500000d duoc mien phi ship. Khach duoc kiem hang truoc khi nhan.'),
('doi-hang', 'Doi hang', 'Chi doi size ngang gia trong cung san pham, trong 14 ngay, con tem mac va hoa don. Hang Sale va Phu kien tuyet doi khong doi tra. COD chiu ship 2 chieu, loi shop shop chiu.'),
('tra-hang', 'Tra hang', 'Shop chi ho tro doi size ngang gia, khong ho tro tra hang hoan tien de giu ke toan don gian. Truong hop loi shop (sai mau, rach, thieu hang) lien he hotline de duoc xu ly rieng.'),
('bao-mat', 'Bao mat', 'Thong tin khach hang chi dung de giao hang va cham soc don. Shop khong ban hoac chia se du lieu cho ben thu ba. Mat khau duoc ma hoa mot chieu.'),
('mua-hang', 'Mua hang', 'Chon size mau -> Them vao gio hoac Mua ngay -> Nhap dia chi SDT -> Chon ship COD hoac Chuyen khoan -> Dat hang -> Theo doi o Don hang cua toi.');

CREATE TABLE IF NOT EXISTS stores (
  id INT AUTO_INCREMENT PRIMARY KEY,
  province VARCHAR(100) NOT NULL,
  branch_name VARCHAR(255) NOT NULL,
  address VARCHAR(500) NOT NULL,
  open_hours VARCHAR(255) NOT NULL DEFAULT '8:00 - 22:00',
  map_url VARCHAR(1000) NULL,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  KEY idx_store_province (province)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO stores (id, province, branch_name, address, open_hours, map_url, is_active) VALUES
(1, 'Da Nang', 'Chi nhanh Khue Trung', '39 Dao Cong Chinh, Khue Trung, Cam Le, Da Nang', '8:00 - 22:00', NULL, 1);

CREATE TABLE IF NOT EXISTS gifts (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  stock INT NOT NULL DEFAULT 0,
  image VARCHAR(500) NULL,
  min_order_amount DECIMAL(12,2) NOT NULL DEFAULT 500000,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO gifts (id, name, stock, image, min_order_amount, is_active) VALUES
(1, 'Tat co ban', 100, '', 500000, 1),
(2, 'Voucher 20k don sau', 100, '', 500000, 1);

CREATE TABLE IF NOT EXISTS order_gifts (
  order_id INT NOT NULL PRIMARY KEY,
  gift_id INT NOT NULL,
  qty INT NOT NULL DEFAULT 1,
  FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS subscribers (
  id INT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(255) NOT NULL UNIQUE,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS contacts (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  phone VARCHAR(20) NOT NULL,
  message TEXT NOT NULL,
  reply TEXT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'Moi',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Cot danh dau SP duoc tang qua (khong sua gia theo size: dong gia toan shop)
SET @has_col := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'products' AND COLUMN_NAME = 'has_gift');
SET @sql := IF(@has_col = 0, 'ALTER TABLE products ADD COLUMN has_gift TINYINT(1) NOT NULL DEFAULT 0', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ================= PHAN 3 - Gallery, FAQ, collection, bai viet, tuyen dung =================
CREATE TABLE IF NOT EXISTS product_images (id INT AUTO_INCREMENT PRIMARY KEY, product_id INT NOT NULL, image_url VARCHAR(1000) NOT NULL, sort_order INT NOT NULL DEFAULT 0, KEY idx_pi_product (product_id), FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS product_faqs (id INT AUTO_INCREMENT PRIMARY KEY, product_id INT NOT NULL, question VARCHAR(500) NOT NULL, answer TEXT NOT NULL, sort_order INT NOT NULL DEFAULT 0, KEY idx_pf_product (product_id), FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS collections (id INT AUTO_INCREMENT PRIMARY KEY, slug VARCHAR(100) NOT NULL UNIQUE, title VARCHAR(255) NOT NULL, description TEXT NULL, image VARCHAR(1000) NULL, season VARCHAR(50) NULL, is_active TINYINT(1) NOT NULL DEFAULT 1, created_at DATETIME DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS collection_products (collection_id INT NOT NULL, product_id INT NOT NULL, PRIMARY KEY (collection_id, product_id), FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE, FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS posts (id INT AUTO_INCREMENT PRIMARY KEY, slug VARCHAR(100) NOT NULL UNIQUE, title VARCHAR(255) NOT NULL, content TEXT NOT NULL, image VARCHAR(1000) NULL, collection_id INT NULL, is_active TINYINT(1) NOT NULL DEFAULT 1, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, KEY idx_post_coll (collection_id), FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE SET NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS post_products (post_id INT NOT NULL, product_id INT NOT NULL, PRIMARY KEY (post_id, product_id), FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE, FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS jobs (id INT AUTO_INCREMENT PRIMARY KEY, title VARCHAR(255) NOT NULL, location VARCHAR(255) NULL, salary VARCHAR(255) NULL, description TEXT NOT NULL, is_active TINYINT(1) NOT NULL DEFAULT 1, created_at DATETIME DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS applications (id INT AUTO_INCREMENT PRIMARY KEY, job_id INT NOT NULL, name VARCHAR(100) NOT NULL, phone VARCHAR(20) NOT NULL, email VARCHAR(255) NULL, cv_text TEXT NOT NULL, status VARCHAR(20) NOT NULL DEFAULT 'Moi', created_at DATETIME DEFAULT CURRENT_TIMESTAMP, KEY idx_app_job (job_id), FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
SET @has_brand := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'products' AND COLUMN_NAME = 'brand');
SET @sql := IF(@has_brand = 0, 'ALTER TABLE products ADD COLUMN brand VARCHAR(100) NULL DEFAULT ''FashionShop''', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @has_vid := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'products' AND COLUMN_NAME = 'video_url');
SET @sql := IF(@has_vid = 0, 'ALTER TABLE products ADD COLUMN video_url VARCHAR(1000) NULL', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @has_mat := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'products' AND COLUMN_NAME = 'material');
SET @sql := IF(@has_mat = 0, 'ALTER TABLE products ADD COLUMN material VARCHAR(500) NULL', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @has_fit := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'products' AND COLUMN_NAME = 'fit');
SET @sql := IF(@has_fit = 0, 'ALTER TABLE products ADD COLUMN fit VARCHAR(255) NULL', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @has_sn := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'products' AND COLUMN_NAME = 'size_note');
SET @sql := IF(@has_sn = 0, 'ALTER TABLE products ADD COLUMN size_note VARCHAR(500) NULL', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ================= PHAN 4 - Banner, combo, review, thong bao, Nhan vien, bao cao =================
CREATE TABLE IF NOT EXISTS banners (id INT AUTO_INCREMENT PRIMARY KEY, title VARCHAR(255) NULL, image VARCHAR(1000) NOT NULL, link VARCHAR(1000) NULL, sort_order INT NOT NULL DEFAULT 0, is_active TINYINT(1) NOT NULL DEFAULT 1, created_at DATETIME DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS combos (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(255) NOT NULL, combo_type VARCHAR(20) NOT NULL DEFAULT 'BUY_GET', trigger_product_id INT NULL, trigger_qty INT NOT NULL DEFAULT 1, gift_product_id INT NULL, gift_qty INT NOT NULL DEFAULT 1, bundle_product_ids VARCHAR(500) NULL, bundle_price DECIMAL(12,2) NULL, start_at DATETIME NULL, end_at DATETIME NULL, is_active TINYINT(1) NOT NULL DEFAULT 1, created_at DATETIME DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS order_combos (order_id INT NOT NULL, combo_id INT NOT NULL, qty INT NOT NULL DEFAULT 1, discount DECIMAL(12,2) NOT NULL DEFAULT 0, PRIMARY KEY (order_id, combo_id), FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS review_helpful (review_id INT NOT NULL, user_id INT NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (review_id, user_id), FOREIGN KEY (review_id) REFERENCES reviews(id) ON DELETE CASCADE, FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS notifications (id INT AUTO_INCREMENT PRIMARY KEY, user_id INT NOT NULL, title VARCHAR(500) NOT NULL, link VARCHAR(500) NULL, is_read TINYINT(1) NOT NULL DEFAULT 0, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, KEY idx_notif_user (user_id, is_read), FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS staff_logs (id INT AUTO_INCREMENT PRIMARY KEY, user_id INT NOT NULL, action VARCHAR(100) NOT NULL, order_id INT NULL, detail VARCHAR(500) NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, KEY idx_slog_user (user_id), KEY idx_slog_order (order_id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
SET @c := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'orders' AND COLUMN_NAME = 'note');
SET @s := IF(@c = 0, 'ALTER TABLE orders ADD COLUMN note TEXT NULL', 'SELECT 1'); PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
SET @c := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'orders' AND COLUMN_NAME = 'dong_kiem');
SET @s := IF(@c = 0, 'ALTER TABLE orders ADD COLUMN dong_kiem TINYINT(1) NOT NULL DEFAULT 0', 'SELECT 1'); PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
SET @c := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'orders' AND COLUMN_NAME = 'ship_carrier');
SET @s := IF(@c = 0, 'ALTER TABLE orders ADD COLUMN ship_carrier VARCHAR(50) NULL', 'SELECT 1'); PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
SET @c := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'orders' AND COLUMN_NAME = 'channel');
SET @s := IF(@c = 0, 'ALTER TABLE orders ADD COLUMN channel VARCHAR(20) NOT NULL DEFAULT ''online''', 'SELECT 1'); PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
SET @c := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'orders' AND COLUMN_NAME = 'store_id');
SET @s := IF(@c = 0, 'ALTER TABLE orders ADD COLUMN store_id INT NULL', 'SELECT 1'); PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
SET @c := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'order_items' AND COLUMN_NAME = 'is_gift');
SET @s := IF(@c = 0, 'ALTER TABLE order_items ADD COLUMN is_gift TINYINT(1) NOT NULL DEFAULT 0', 'SELECT 1'); PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
SET @c := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'reviews' AND COLUMN_NAME = 'status');
SET @s := IF(@c = 0, 'ALTER TABLE reviews ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT ''Hien''', 'SELECT 1'); PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
SET @c := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'reviews' AND COLUMN_NAME = 'reply');
SET @s := IF(@c = 0, 'ALTER TABLE reviews ADD COLUMN reply TEXT NULL', 'SELECT 1'); PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
SET @c := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'reviews' AND COLUMN_NAME = 'helpful');
SET @s := IF(@c = 0, 'ALTER TABLE reviews ADD COLUMN helpful INT NOT NULL DEFAULT 0', 'SELECT 1'); PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
SET @c := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'email_verified');
SET @s := IF(@c = 0, 'ALTER TABLE users ADD COLUMN email_verified TINYINT(1) NOT NULL DEFAULT 1', 'SELECT 1'); PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
SET @c := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'return_requests' AND COLUMN_NAME = 'in_store');
SET @s := IF(@c = 0, 'ALTER TABLE return_requests ADD COLUMN in_store TINYINT(1) NOT NULL DEFAULT 0', 'SELECT 1'); PREPARE st FROM @s; EXECUTE st; DEALLOCATE PREPARE st;
INSERT IGNORE INTO settings (`key`,`value`) VALUES ('commission_rate','2'),('recaptcha_site_key',''),('recaptcha_secret_key',''),('require_email_verify','1'),('shop_bank_accounts','Vietcombank 1234567890 - FashionShop - CN Da Nang\nMBBank 0987799353 - FashionShop');
INSERT IGNORE INTO banners (title,image,link,sort_order,is_active) VALUES ('Bo suu tap moi','https://images.unsplash.com/photo-1441986300917-64674bd600d8?auto=format&fit=crop&w=1200&q=80','/',0,1),('Sale thoi trang','https://images.unsplash.com/photo-1469334031218-e382a71b716b?auto=format&fit=crop&w=1200&q=80','/',1,1);
