# Cài đặt tài khoản và sức khỏe

Màn Cài đặt là trung tâm quản lý dữ liệu cá nhân của HealthApp, gồm bốn nhóm:

- **Hồ sơ sức khỏe:** chỉnh thông tin cá nhân, chỉ số cơ thể, cân nặng mục tiêu, mức vận động và mục tiêu sức khỏe. Các thay đổi cập nhật lại BMI, BMR, TDEE và lượng calo đề xuất qua `UserModel`.
- **Trợ lý & nhắc nhở:** mở Chatbot trực tiếp và cấu hình check-in trong ứng dụng cho uống nước, dinh dưỡng, vận động, tâm trạng.
- **Dữ liệu hội thoại:** xem danh sách session, mở lại lịch sử, xóa từng session hoặc xóa toàn bộ sau khi xác nhận.
- **Tài khoản:** xem thông tin phiên bản và đăng xuất.

## Lưu cài đặt check-in

`ProactiveProvider` giữ một bản cấu hình chuẩn hóa gồm `enable_proactive`, `water_checkin`, `nutrition_checkin`, `fitness_checkin`, `mood_checkin`. Mỗi giá trị được lưu bằng `SharedPreferences` với key chứa `userId`, tránh dùng chung cài đặt giữa các tài khoản trên một thiết bị.

Khi app tải check-in, provider đọc bản cục bộ và đồng bộ lại API `/checkin/settings`. Nếu backend tạm thời không hoạt động, lựa chọn vẫn được giữ trên thiết bị và sẽ được thử đồng bộ ở lần tải sau. Khi `enable_proactive = false`, client không gọi API lấy nudge.

## An toàn dữ liệu

Xóa lịch sử là thao tác không thể hoàn tác nên màn quản lý luôn yêu cầu xác nhận. Nếu xóa session đang mở, `AIChatProvider` tự tạo session mới để không giữ state trỏ tới dữ liệu đã xóa.
