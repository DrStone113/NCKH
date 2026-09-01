# Catalog món Việt có nguồn kiểm chứng

## Mục tiêu

Catalog runtime phải phân biệt rõ dữ liệu legacy ước lượng và công thức đã đối chiếu nguồn. Một món được gắn `verified_recipe` hoặc `verified_complete_meal` chỉ khi toàn bộ nguyên liệu khớp chính xác một dòng trong Bảng thành phần thực phẩm Việt Nam và phép tính năng lượng vượt qua validator.

## Nguồn dữ liệu

- **Viện Dinh dưỡng Quốc gia, Bộ Y tế:** [Bảng thành phần thực phẩm Việt Nam](https://chuyentrang.viendinhduong.vn/viewfilenew/vi/thu-vien-sach-chuyen-nganh/189/1.html).
- **Viện Dinh dưỡng Quốc gia:** [Danh mục 500 món ăn thông dụng](https://chuyentrang.viendinhduong.vn/vi/dinh-duong-va-benh-khong-lay-nhiem/dinh-duong-va-benh-khong-lay-nhiem.html), gồm các PDF công thức theo nhóm món.
- **Viện Dinh dưỡng Quốc gia:** [Thực đơn tham khảo 1600 kcal](https://chuyentrang.viendinhduong.vn/vi/-395/che-do-an-du-phong-va-dieu-tri-nguoi-bi-benh-gout.html), được dùng làm nguồn định lượng cho các suất ăn hoàn chỉnh; đây là nguồn công thức tham khảo, không biến catalog thành chỉ định điều trị.
- **FAO/INFOODS:** [Recommendations on recipe calculation](https://www.fao.org/infoods/infoods/recipes/en/) và [Food matching guidelines](https://www.fao.org/fileadmin/templates/food_composition/documents/upload/INFOODSGuidelinesforFoodMatching_version_1_2.pdf).
- **ViFoodRec (PACLIC 2024):** [A New Dataset and Empirical Evaluation for Vietnamese Food Recommendation System](https://aclanthology.org/2024.paclic-1.4/), tập dữ liệu 5.509 món do nhóm Đại học Công nghệ Thông tin - ĐHQG TP.HCM công bố. Catalog chỉ nhập các bản ghi có ảnh nguồn từ website chính thức Món Ngon Mỗi Ngày của Ajinomoto Việt Nam.

## Kiến trúc dữ liệu

- `vietnamese_dishes.json`: catalog legacy 90 món và input bất biến của corpus nghiên cứu `offline-v1-636`.
- `vietnamese_dishes_curated_v1.json`: overlay có phiên bản gồm `overrides` và `additions`, provenance và trạng thái kiểm chứng.
- `vietnamese_dishes_reference_v1.json`: 203 công thức tham khảo được chuẩn hóa từ snapshot ViFoodRec đã khóa commit/SHA-256; chỉ lưu tên món, nguyên liệu định lượng đã đối chiếu và provenance, không sao chép mô tả hay hướng dẫn chế biến.
- `scripts/build_reference_dish_catalog.py`: pipeline tái lập để tải/đọc snapshot, lọc nguồn Món Ngon Mỗi Ngày, quy đổi theo số người ăn, chọn bản ghi đạt ngưỡng chất lượng và tính lại năng lượng từ bảng thực phẩm Việt Nam.
- `modules/nutrition/catalog.py`: merge ba nguồn theo ID, từ chối override không tồn tại, addition trùng ID và tên món trùng.
- Nutrition API và `suggest_dish` cùng đọc catalog merged; do đó giao diện thêm món thủ công và chatbot không còn lệch catalog.

## Quy tắc kiểm định

1. Mọi tên nguyên liệu curated phải khớp chính xác `vietnamese_foods.json`; không thay cá này bằng cá khác hoặc một loại củ bằng loại củ khác.
2. `estimated_calories` phải nằm trong ±2% của tổng `energy_kcal × grams / 100`.
3. `verified_complete_meal` phải có ít nhất các nhóm `carb`, `protein`, `veggie`, `fruit` và tối thiểu 7 thành phần.
4. Provenance phải thuộc miền Viện Dinh dưỡng hoặc FAO.
5. Nước dùng/gia vị không có dòng dinh dưỡng tương ứng không được bịa số; phần bỏ qua phải thể hiện trong phương pháp của overlay.
6. Bộ lọc dị ứng dùng mã nhóm thực phẩm của bảng chính thức và vẫn giữ danh sách tên làm lớp bảo vệ bổ sung.
7. `normalized_reference_recipe` là tầng độ phủ, không được trình bày như công thức đã kiểm chứng trực tiếp bởi Viện Dinh dưỡng. Mỗi bản ghi phải có ít nhất 2 nguyên liệu định lượng, độ phủ tối thiểu 60% tổng khối lượng định lượng, giữ lại tên nguyên liệu nguồn để audit và tính lại calo từ bảng chính thức.
8. Số calo của website/ViFoodRec không được dùng làm chân lý; nước và gia vị không có định lượng bị bỏ khỏi phép tính và giới hạn này được ghi trong metadata của từng món.
9. Bài báo ghi dữ liệu được mở miễn phí cho cộng đồng nghiên cứu, nhưng repository không kèm giấy phép tái phân phối rõ ràng. Catalog chỉ lưu dữ kiện tối thiểu và attribution; phải kiểm tra lại điều khoản nguồn trước khi phân phối thương mại.

Chạy kiểm định:

```powershell
cd apps/backend
python scripts/validate_dish_catalog.py
pytest -q tests/test_curated_dish_catalog.py
```

## Trạng thái v2

- Catalog live: 300 món; API/mobile tải toàn bộ thay vì bị giới hạn ngầm ở 100.
- Công thức `verified_recipe`: 5.
- Suất ăn `verified_complete_meal`: 6.
- Công thức phủ rộng `normalized_reference_recipe`: 203.
- Catalog legacy vẫn được phục vụ để bảo toàn độ phủ; các batch tiếp theo cần lần lượt thay thế hoặc ngừng phục vụ những món có mapping sai đã biết.

## Canonical ingredient layer v3

Từ 2026-08-30, catalog được enrich qua `canonical_foods.py`: 526 thực phẩm có stable `food_id`, provenance tới từng nutrient, food state, allergen taxonomy và energy QA. Mọi ingredient của 300 món live hiện resolve `EXACT` tới Vietnam FCT; source hierarchy có 10 nguồn nhưng chỉ `VIETNAM_FCT` được phép cấp nutrient values tại runtime.

Xem thiết kế, license gates và số liệu audit tại [Canonical ingredient catalog và provenance theo field](canonical_food_provenance.md).
