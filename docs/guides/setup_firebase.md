# Thiết lập Firebase cho Health App

Firebase của dự án này chỉ chịu trách nhiệm xác thực, hồ sơ người dùng và một
số nhật ký cá nhân đang được Flutter truy cập trực tiếp. PostgreSQL/backend vẫn
là nguồn dữ liệu chính cho Plan V2, chat, RAG, catalog và dữ liệu nghiên cứu.
Không tạo các collection Firestore để sao chép các hệ thống đó.

Thiết kế và ma trận ownership đầy đủ nằm tại
[`docs/firebase/firebase_architecture.md`](../firebase/firebase_architecture.md).

## Công cụ đã chuẩn hóa

- Firebase CLI: `15.30.0`
- FlutterFire CLI: `1.4.1`
- Flutter/Dart của dự án: `.fvmrc`, Flutter `3.44.8`, Dart `3.12.2`
- Firebase Emulator: JDK 21 qua biến user `FIREBASE_JAVA_HOME`
- Android/Gradle: tiếp tục dùng JDK 17 qua `JAVA_HOME`

Firebase Emulator tooling hỗ trợ Node 20, 22 hoặc 24. Node 26 hiện chạy được bộ
test nhưng không phải phiên bản được khai báo hỗ trợ; nên dùng Node 24 LTS cho
CI hoặc trước khi coi toolchain là production-ready.

## Cấu hình cố định

- Firebase project dự kiến: `healthcare-191d8`
- Android package: `com.example.app`
- Debug SHA-1: `DC:60:5D:E3:F6:70:EF:D5:BA:32:B8:1F:F0:91:B1:2F:FB:5B:E9:80`
- Debug SHA-256: `01:78:8F:DF:20:A3:C5:B8:40:53:EC:38:51:64:2E:6C:BC:15:94:70:17:5B:0E:35:26:CA:27:00:8C:A0:71:82`

Fingerprint phải được lấy lại bằng `android\gradlew.bat signingReport` nếu
debug keystore thay đổi.

## Chạy kiểm tra local

Từ thư mục gốc repository:

```powershell
.\scripts\firebase\run-emulator-tests.ps1
```

Lệnh này dùng project giả `demo-healthcare-f1`, khởi động Firestore Emulator,
chạy rule tests rồi tự tắt. Nó không thể ghi vào production.

Để chạy app Flutter với Auth và Firestore Emulator:

```powershell
firebase emulators:start --only auth,firestore --project demo-healthcare-f1
cd apps\mobile
.\.fvm\flutter_sdk\bin\flutter.bat run `
  --dart-define=USE_FIREBASE_EMULATORS=true
```

Trên Android emulator/LDPlayer, app dùng `10.0.2.2` để truy cập emulator trên
máy host. Web dùng `127.0.0.1`. Nếu không truyền dart-define, production Firebase
là mặc định.

## Audit cloud trước khi thay đổi

Đăng nhập bằng tài khoản có quyền với project hiện hữu:

```powershell
firebase login
.\scripts\firebase\bootstrap.ps1
```

Bootstrap mặc định là `AUDIT_ONLY`: xác minh project, Android app, SHA và
Firestore nhưng không tạo/deploy gì.

## Áp dụng cloud có kiểm soát

Không chạy tất cả cờ cùng lúc khi chưa đọc output audit. Ví dụ, nếu Android app
đã tồn tại nhưng thiếu SHA/config:

```powershell
.\scripts\firebase\bootstrap.ps1 `
  -ApplyCloud `
  -RegisterSha `
  -DownloadGoogleServices `
  -ConfigureFlutterFire
```

Chỉ tạo Android app nếu audit xác nhận app `com.example.app` chưa tồn tại:

```powershell
.\scripts\firebase\bootstrap.ps1 `
  -ApplyCloud `
  -CreateMissingAndroidApp `
  -RegisterSha `
  -DownloadGoogleServices `
  -ConfigureFlutterFire
```

Deploy Firestore chỉ sau khi rule tests pass:

```powershell
.\scripts\firebase\bootstrap.ps1 -ApplyCloud -DeployFirestore
```

Deploy Email/Password và Google Sign-In cần email hỗ trợ thuộc quyền sở hữu của
người quản trị OAuth:

```powershell
.\scripts\firebase\bootstrap.ps1 `
  -ApplyCloud `
  -DeployAuth `
  -SupportEmail 'owner@example.com'
```

Script sinh config Auth tạm trong thư mục đã ignore và chỉ deploy `auth`. Không
lưu support email vào source nếu không cần.

## File cấu hình Android

`apps/mobile/android/app/google-services.json` phải được tải từ Firebase bằng
CLI hoặc Console sau khi Android app và SHA hợp lệ. File được Git ignore và
không được tạo giả. Sau khi có file, Gradle tự bật plugin Google Services.

Không tạo Firestore ở Test mode. Rules production phải đến từ
`firebase/firestore.rules`, đã qua Emulator, rồi deploy scoped.
