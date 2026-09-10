# FashionShop — Nền tảng bán quần áo trực tuyến

FashionShop là web bán thời trang gồm mua sắm online tính ship theo khu vực/hãng, tích điểm và quà tặng, theo dõi đơn kèm đổi size, báo cáo doanh thu và bộ công cụ quản trị.

## 1. Tính năng chi tiết

Web có **3 giao diện riêng theo vai trò**: khách hàng (mua sắm), nhân viên (bán tại quầy), admin (quản trị).

**Khách hàng:** mua sắm theo menu Áo/Quần nam–nữ (tìm kiếm gợi ý, lọc size/màu/giá), xem chi tiết SP (gallery, video, tồn theo biến thể, FAQ, đánh giá), giỏ hàng + Mua ngay, thanh toán COD/QR/ATM/Visa/Ví (freeship 500k, voucher, combo tự động, điểm, quà tặng, ship GHN/GHTK/Viettel, đồng kiểm), theo dõi đơn + hóa đơn, đổi size 14 ngày (trừ Sale/Phụ kiện), Collection/bài phối đồ, bảng size, cửa hàng Đà Nẵng, tuyển dụng, nhận tin KM, chuông thông báo, đăng ký xác thực email.

**Nhân viên:** menu bán hàng gọn; bán tại quầy (không ship), trang QR thu ngân (khách quét → bấm hoàn thành đơn), quản lý đơn, duyệt đổi size, đổi tại quầy.

**Admin:** thêm toàn bộ của NV + quản lý SP/voucher/combo/quà/banner/collection/bài viết/trang tĩnh/cửa hàng/tuyển dụng/tin nhắn/đánh giá/khách hàng/tài khoản; báo cáo doanh thu, kênh, chi nhánh, tồn kho, nhật ký NV + hoa hồng; xuất Excel/PDF; cấu hình ở `/admin/settings`.

## 2. Công nghệ sử dụng

| Tầng | Công nghệ |
|---|---|
| Backend | Python, Flask, PyMySQL |
| Xác thực | Flask-Login, bcrypt |
| Tiện ích | openpyxl, Jinja2 |
| Frontend | Bootstrap 5, JS thuần |
| Database | MySQL (phpMyAdmin) |

## 3. Yêu cầu môi trường

Python 3.11 trở lên. MySQL/MariaDB (khuyên dùng XAMPP để có phpMyAdmin). Khuyên dùng 1 terminal riêng cho Flask sau khi DB sẵn sàng.

## 4. Chạy local

**Bước 1 — Chuẩn bị database**
Tạo database `fashion_shop` trong phpMyAdmin, import `schema_mysql.sql`, rồi chạy file `migration_all.sql` ở tab SQL (app cũng tự tạo bảng/cột thiếu khi khởi động, không mất dữ liệu cũ).

**Bước 2 — Cài dependencies**
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**Bước 3 — Seed dữ liệu mẫu (tùy chọn nhưng nên làm)**
Thêm SP ở `/admin/products` sau khi có tài khoản admin. Các script tiện ích: `add_admin.py` (tạo admin), `check_admin.py` (kiểm tra users), `show_products.py` (liệt kê SP).

**Bước 4 — Chạy app**
```
python app.py
```

| Dịch vụ | Địa chỉ |
|---|---|
| Giao diện + Admin | http://127.0.0.1:5000 |
| phpMyAdmin | http://localhost/phpmyadmin |

Tạo tài khoản admin bằng `add_admin.py`, rồi đăng nhập phân vai trong trang Quản lý Tài khoản.

**Các script hay dùng**

| Script | Tác dụng |
|---|---|
| `python app.py` | Chạy web (port 5000) |
| `python add_admin.py` | Tạo tài khoản admin |
| `python check_admin.py` | Kiểm tra users trong DB |
| `python show_products.py` | Liệt kê sản phẩm |
| `python insert_products_mysql.py` | Chèn bộ SP mẫu cũ |

## 5. Kiểm thử

Hiện kiểm thử thủ công theo checklist: đăng ký → xác thực email → đăng nhập 3 vai trò; thêm giỏ/mua ngay → checkout COD + Chuyển khoản; staff lên đơn quầy → trang QR → hoàn thành; đổi size online + tại quầy (Sale/Phụ kiện bị chặn); voucher/combo/quà/điểm trừ kho đúng; bấm hết link menu (20/20 có hàng); render các trang admin và template không lỗi.

## 6. Chạy bằng Docker

Chưa có — đang chạy trực tiếp Flask + MySQL local qua XAMPP. Có thể bổ sung `Dockerfile` + `docker-compose.yml` khi cần.

## 7. Cấu trúc thư mục

```
├── app.py                  # Toàn bộ route, helper, transaction
├── templates/              # Giao diện theo vai (layout chung)
├── static/css/style.css    # Theme + menu 2 tầng + submenu
├── schema_mysql.sql        # Schema gốc
├── migration_*.sql         # 4 migration theo đợt (chạy lại an toàn)
├── backup_fashion_shop_A3.sql
├── requirements.txt
├── add_admin.py / check_admin.py / show_products.py / insert_products_mysql.py
```

## 8. API tổng quan

App dùng form POST truyền thống (không có REST JSON riêng) ngoài `GET /search-suggest?q=` (gợi ý live) và `POST /buy-now-qty` (đổi số lượng mua ngay). Mọi route quản trị đều yêu cầu đăng nhập + đúng vai trò ở backend, giao diện chỉ ẩn link chứ backend mới là lớp bảo vệ quyết định.

## 9. Biến môi trường

| Biến | Bắt buộc | Mô tả |
|---|---|---|
| `MYSQL_HOST/PORT/USER/PASSWORD/DB` | Không | Kết nối DB (mặc định `127.0.0.1:3306/root/fashion_shop`) |
| `SECRET_KEY` | Không | Khóa session/token (mặc định trong `app.py`, đổi ở production) |

Cấu hình nghiệp vụ (freeship 500k, đơn tối thiểu 0đ, ngưỡng quà, hoa hồng %, keys reCAPTCHA, STK shop, bật/tắt verify email) nằm trong bảng `settings`, sửa ở `/admin/settings`, không cần đụng code.

