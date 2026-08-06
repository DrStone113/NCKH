# Hướng dẫn Thiết lập Firebase & Cấu trúc Database

Dưới đây là hướng dẫn từng bước để tạo dự án Firebase, kết nối với ứng dụng Flutter của bạn và cách thiết kế cấu trúc database NoSQL (Firestore) dựa trên sơ đồ DBML bạn vừa cung cấp.

---

## Phần 1: Tạo và Kết nối Firebase

### Bước 1: Tạo Project Firebase
1. Truy cập [Firebase Console](https://console.firebase.google.com/).
2. Bấm **Add project** (Thêm dự án).
3. Đặt tên là `HealthApp` (hoặc tên tùy ý) và tiếp tục.
4. Tắt Google Analytics (để đơn giản hóa lúc đầu) và đợi dự án khởi tạo xong.

### Bước 2: Bật Authentication (Đăng nhập)
1. Trong menu bên trái, chọn **Build** -> **Authentication**.
2. Bấm **Get started**.
3. Tab **Sign-in method**, bật 2 phương thức:
   - **Email/Password**: Bật công tắc Enable và Save.
   - **Google**: Bật công tắc Enable, chọn mội Project support email (email của bạn) và Save.

### Bước 3: Bật Cloud Firestore (Database)
1. Trong menu bên trái, chọn **Build** -> **Firestore Database**.
2. Bấm **Create database**.
3. Chọn Location (Nên chọn `asia-southeast1` - Singapore cho gần Việt Nam).
4. Chọn **Start in Test mode** (Cho phép đọc/ghi thoải mái trong quá trình dev) và bấm Enable.

### Bước 4: Kết nối với Flutter bằng FlutterFire CLI
Để app Flutter hiểu được Firebase, bạn cần thiết lập cấu hình. Mở Terminal trong VSCode (hoặc PowerShell tại thư mục `C:\Project\Chatbot\apps\mobile`) và chạy:

1. Cài đặt Firebase CLI (nếu chưa có):
```bash
npm install -g firebase-tools
firebase login
```
2. Cài đặt FlutterFire CLI:
```bash
dart pub global activate flutterfire_cli
```
3. Cấu hình Firebase cho Project:
```bash
flutterfire configure
```
*Giao diện dòng lệnh sẽ hiện ra, bạn dùng phím mũi tên chọn project `HealthApp` vừa tạo, sau đó ấn Enter để chọn nền tảng (Android, iOS, Web). CLI sẽ tự động tải file `google-services.json` và tạo file `firebase_options.dart`.*

---

## Phần 2: Chuyển đổi DBML sang Cấu trúc NoSQL (Firestore)

Vì Firestore là cơ sở dữ liệu NoSQL (lưu dạng Document thay vì Table), ta cần chuyển đổi các Table DBML của bạn thành các **Collections** (Tập hợp) và **Documents** (Tài liệu). Dưới đây là sơ đồ mapping tối ưu:

### 1. Tập hợp (Collection): `users`
*(Thay thế bảng `nguoi_dung`)*
- `id` (Document ID mặc định của Firebase Auth)
- `ho_ten`: String
- `email`: String
- `gioi_tinh`: String ("nam", "nu", "khac")
- `ngay_sinh`: Timestamp
- `chieu_cao`: Number (cm)
- `can_nang_muc_tieu`: Number (kg)
- `muc_do_van_dong`: String ("it", "nhe", "vua", "nhieu", "rat_nhieu")
- `ngay_tao`: Timestamp

### 2. Tập hợp (Collection): `body_metrics`
*(Thay thế bảng `chi_so_co_the`)*
Khuyên dùng: Tạo root collection `body_metrics` để dễ truy vấn theo ngày.
- `id` (Auto-generated Document ID)
- `userId`: String (Tham chiếu tới Document ID của `users`)
- `can_nang`: Number (kg)
- `bmi`: Number
- `ngay_ghi_nhan`: Timestamp

### 3. Tập hợp (Collection): `foods`
*(Thay thế bảng `mon_an`)*
- `id` (Auto-generated Document ID)
- `userId`: String (Gán `"system"` nếu là món do hệ thống cung cấp)
- `ten_mon`: String
- `calo_tren_100g`: Number
- `protein_tren_100g`: Number
- `chat_beo_tren_100g`: Number
- `carbs_tren_100g`: Number
- `vi_chat_dinh_duong`: Map (Object)
- `danh_muc`: String
- `la_mon_he_thong`: Boolean

### 4. Tập hợp (Collection): `menus` & `menu_details`
*(Thay thế bảng `thuc_don` và `chi_tiet_thuc_don`)*
Vì Firestore hỗ trợ lưu Array of Objects, ta kết hợp 2 bảng này vào một Document.
**Collection `menus`**:
- `id` (Auto-generated)
- `userId`: String (hoặc null/"system")
- `ten_thuc_don`: String
- `loai_muc_tieu`: String ("giam_can", "duy_tri", "tang_co", "tuy_chinh")
- `mo_ta`: String
- `cong_khai`: Boolean
- `mon_an_chi_tiet`: Array of Maps (Mảng chứa các Map)
  - `[0]`: `{ mon_an_id: "id_mon1", luong_gram: 200, bua_an: "sang" }`
  - `[1]`: `{ mon_an_id: "id_mon2", luong_gram: 150, bua_an: "trua" }`

### 5. Tập hợp (Collection): `meal_logs`
*(Thay thế bảng `nhat_ky_an_uong`)*
- `id` (Auto-generated)
- `userId`: String
- `mon_an_id`: String
- `khoi_luong_an`: Number
- `loai_bua_an`: String ("sang", "trua", "toi", "phu")
- `ngay_ghi_nhan`: Timestamp

### 6. Tập hợp (Collection): `exercises` & `exercise_logs`
*(Thay thế bảng `bai_tap` và `nhat_ky_tap_luyen`)*
**Collection `exercises`**:
- `id` (Auto)
- `ten_bai_tap`: String
- `chi_so_met`: Number
- `mo_ta`: String

**Collection `exercise_logs`**:
- `id` (Auto)
- `userId`: String
- `bai_tap_id`: String
- `thoi_gian_phut`: Number
- `calo_tieu_thu`: Number
- `ngay_ghi_nhan`: Timestamp

### 7. Nhóm Chatbot & Triệu chứng
Với bảng DBML `trieu_chung`, `thieu_hut_vi_chat`, `ban_do_trieu_chung`, `thuc_pham_bo_sung`:
Vì nội dung này ít khi thay đổi (kiến thức y khoa cố định), **cách tốt nhất để tối ưu chi phí Firebase (tránh tốn lượt đọc)** là hardcode database này thành các class Dart trong file `providers/chat_provider.dart` (như cách ứng dụng hiện tại đang làm).
Nếu bạn vẫn muốn lưu trên Firebase để sau này admin tự thêm bớt không cần update app, hãy tạo collection `chatbot_knowledge`, trong đó mỗi Document ứng với một "Triệu Chứng" (gộp mô tả, thiếu hụt, cách bổ sung thành 1 array).
