import os
# Force app to use MySQL for this run
os.environ['DB_TYPE'] = 'mysql'
os.environ.setdefault('MYSQL_HOST', '127.0.0.1')
os.environ.setdefault('MYSQL_PORT', '3306')
os.environ.setdefault('MYSQL_USER', 'root')
os.environ.setdefault('MYSQL_PASSWORD', '')
os.environ.setdefault('MYSQL_DB', 'fashion_shop')

from app import execute_db, app

products = [
    ('Áo sơ mi nam công sở dài tay', 350000, 100, 'Áo', 'Áo sơ mi chất liệu bamboo cao cấp, chống nhăn, thoáng khí, form dáng slim-fit tôn dáng lịch lãm.', 'https://example.com/ao-so-mi-nam.jpg', 1),
    ('Quần tây âu nữ dáng suông ống rộng', 280000, 80, 'Quần', 'Quần tây dáng suông lưng cao, chất vải tuyết mưa dày dặn, thích hợp đi làm, đi chơi.', 'https://example.com/quan-tay-nu.jpg', 0),
    ('Váy hoa nhí dáng dài cổ chữ V', 420000, 45, 'Váy', 'Váy voan tơ mềm mại có lót trong, họa tiết hoa nhí vintage ngọt ngào, bo eo nhẹ nhàng.', 'https://example.com/vay-hoa-nhi.jpg', 1),
    ('Áo khoác Bomber nỉ ngoại unisex', 390000, 60, 'Áo khoác', 'Áo khoác kiểu dáng bomber năng động, chất nỉ dày dặn, tay phối màu hot trend cho nam nữ.', 'https://example.com/ao-bomber.jpg', 1),
    ('Quần short jeans nam rách gối nhẹ', 220000, 120, 'Quần', 'Chất denim co giãn nhẹ, màu xanh bạc cá tính, dễ dàng phối cùng áo thun, áo polo.', 'https://example.com/short-jeans-nam.jpg', 0),
    ('Áo hoodie nỉ bông form rộng oversized', 290000, 150, 'Áo', 'Áo hoodie có mũ trùm dày dặn, lót nỉ bông ấm áp, thích hợp cho thời tiết thu đông.', 'https://example.com/ao-hoodie.jpg', 1),
    ('Chân váy tennis xếp ly ngắn có quần trong', 180000, 95, 'Váy', 'Chân váy ngắn xếp ly đều đặn, chất tuyết mưa đứng form, có sẵn quần bảo hộ bên trong tiện lợi.', 'https://example.com/chan-vay-tennis.jpg', 0),
    ('Áo polo nam cotton cá sấu phối sọc', 260000, 110, 'Áo', 'Chất vải cá sấu co giãn 4 chiều, thấm hút mồ hôi tốt, cổ bẻ thanh lịch phù hợp mọi hoàn cảnh.', 'https://example.com/ao-polo-nam.jpg', 1),
    ('Quần jogger thun nam nữ dáng thể thao', 195000, 200, 'Quần', 'Thiết kế bo gấu năng động, chất thun cotton dày dặn, có túi khóa zip hai bên tiện lợi.', 'https://example.com/quan-jogger.jpg', 0),
    ('Đầm dạ hội trễ vai dáng ôm quyến rũ', 650000, 20, 'Váy', 'Thiết kế trễ vai sang trọng, xẻ tà đùi cao, chất vải satin bóng nhẹ tôn dáng tối đa cho các buổi tiệc.', 'https://example.com/dam-da-hoi.jpg', 1),
    ('Áo len nữ cổ lọ dệt kim basic', 240000, 70, 'Áo', 'Chất len dệt kim mềm mịn, co giãn ôm sát cơ thể giữ ấm tốt, không bị xù lông khi giặt.', 'https://example.com/ao-len-co-lo.jpg', 0),
    ('Quần jean baggy nữ cạp cao rách gối', 310000, 85, 'Quần', 'Form quần baggy thoải mái, che khuyết điểm chân tốt, chất bò dày dặn không phai màu.', 'https://example.com/jean-baggy-nu.jpg', 1),
    ('Bộ đồ ngủ Pijama lụa satin họa tiết dài tay', 250000, 130, 'Đồ ngủ', 'Chất lụa satin cao cấp bóng mượt, mát lịm, đường may tỉ mỉ, họa tiết dễ thương sắc nét.', 'https://example.com/pijama-lua.jpg', 0),
    ('Áo khoác Blazer nữ 2 lớp dáng rộng', 450000, 40, 'Áo khoác', 'Áo blazer thiết kế có đệm vai nhẹ, bên trong lót lụa mềm mại, dễ phối đồ theo phong cách hiện đại.', 'https://example.com/blazer-nu.jpg', 1),
    ('Quần short đũi nam dây rút lưng thun', 160000, 140, 'Quần', 'Vải đũi xước tự nhiên siêu nhẹ và mát, thích hợp mặc ở nhà, đi biển hoặc dạo phố ngày hè.', 'https://example.com/quan-doi-nam.jpg', 0),
]

query = 'INSERT INTO products (name, price, stock, category, description, image, is_featured, is_active) VALUES (%s, %s, %s, %s, %s, %s, %s, 1)'

try:
    with app.app_context():
        for p in products:
            execute_db(query, p)
    print(f'Đã chèn {len(products)} sản phẩm vào MySQL ({os.environ.get("MYSQL_DB")} ).')
except Exception as e:
    print('Lỗi khi chèn vào MySQL:', e)
