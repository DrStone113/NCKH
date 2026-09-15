# Thứ tự chọn món trong adaptive shadow

Candidate → xác thực ID/nguồn → lọc dị ứng, restriction và safety →
yêu cầu hiện tại → sở thích đã học → chống lặp/đa dạng → chọn món.

`CandidateEligibilityGate` kiểm tra nguồn, ingredient mapping và dinh dưỡng
canonical trước khi `RecommendationRankerV2` tính sở thích. `CurrentRequest`
lọc tập món hợp lệ; sở thích và bước chống lặp chỉ được làm việc trong tập này.
Nếu không có món thỏa yêu cầu hiện tại, trả trạng thái
`NO_ELIGIBLE_CANDIDATE_FOR_EXPLICIT_REQUEST`, không tự đổi sang món khác.

Khi người dùng chỉ định món muốn ăn lại, lịch sử hiển thị/ăn món đó không được
trừ điểm lặp hoặc độ mới. Với yêu cầu chung, bước cuối vẫn ưu tiên món chưa
hiển thị, rồi món được hiển thị lâu nhất; sở thích quyết định thứ tự trong
cùng nhóm lịch sử. Đây là chống lặp sau khi đã lọc yêu cầu hiện tại.

Nguyên nhân phát hiện ngày 2026-09-08:

- Miễn điểm lặp chỉ đọc `stated_dish_intent` và so sánh nguyên văn tên món,
  trong khi bước lọc và luân phiên đọc `CurrentRequest` đã chuẩn hóa. Yêu cầu
  có cấu trúc hoặc câu “tôi muốn ăn lại …” vì thế nhận điểm không nhất quán.
  Cách sửa: dùng cùng yêu cầu đã chuẩn hóa cho lọc và miễn điểm lặp/độ mới.
- Nhãn do ingredient mapper suy ra có cả `contains_allergen:FISH` và
  `contains_allergen:fish`; bản chiếu catalog chỉ có mã viết hoa. So sánh nhãn
  phân biệt hoa/thường từ chối nhầm món cá hợp lệ. Cách sửa: chuẩn hóa chữ khi
  đối chiếu nhãn, vẫn kiểm tra nguyên vẹn ID dị nguyên và thành phần canonical.

Kiểm tra tập trung dùng `suggest_dish` và catalog hiện có, đưa kết quả qua
`canonical_catalog_reference`, cổng xác thực và ranker. Dữ liệu sở thích/lịch
sử kiểm thử chỉ tồn tại trong bộ nhớ. Lệnh từ `apps/backend`:

```text
python -m pytest tests/test_recommendation_selection_order.py -q
```

Kết quả ngày 2026-09-08: trước sửa `6 failed, 8 passed`; sau sửa
`14 passed in 3.70s`. Bao phủ nguồn/ID sai, nutrient không hợp lệ, nhãn dị
nguyên canonical, thiếu metadata an toàn, dị ứng/restriction, yêu cầu hiện tại
ở ba dạng nhập, tránh thực phẩm, sở thích đã học và luân phiên món. Chính sách
xếp hạng được ghi phiên bản `RECOMMENDATION_RANKER_V2_N3_3R_SEMANTICS_V2`.
Đây là kiểm tra tích hợp catalog và domain trong tiến trình, không phải kết
quả live PostgreSQL, API/Flutter E2E hay đóng toàn bộ N3.3R.

Phạm vi: development/shadow. Không thay đổi catalog, dữ liệu nghiên cứu,
artifact đánh giá lịch sử, công thức nutrient, SQL hay bật adaptive production.
