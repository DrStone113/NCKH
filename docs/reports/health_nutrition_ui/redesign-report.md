# HEALTH & NUTRITION UI REDESIGN REPORT

Ngày hoàn tất: 2026-09-09

## Screens Audited

Đã kiểm tra luồng hiện có trước khi sửa: `AuthWrapper`, `ProfileCompletionNotice`,
`ProfileSettingsScreen`, `WorkoutAccountIntakeScreen`, `NutritionScreen`,
`PlannedDayPlanSection`, thư viện và chi tiết Plan V2, sheet thêm bữa ăn,
`MealSummaryCard`, thẻ gợi ý trong chat và `RecommendationFeedbackBar`.

Ứng dụng đang dùng `MaterialPageRoute`, tab Dinh dưỡng hiện hữu và các entry point
Plan hiện hữu; không thêm route hoặc bottom-nav tab trùng lặp. Nguồn trạng thái được
giữ nguyên: `UserProvider`, `NutritionProvider`, `PlanHistoryRepository`,
`PlanHistoryResolver`, HealthProfile V2 và các API model/service hiện có.

Danh mục backend có 90 món nhưng không có trường ảnh món khả dụng. Vì vậy UI dùng
placeholder vector theo nhóm món, không tải ảnh tùy ý từ Internet.

## Design System Changes

Giữ màu thương hiệu slate hiện hữu (`#111827`) và nền off-white (`#F8FAFC`). Các
surface dùng nền trắng, bo 24 px, viền nhạt và shadow nhẹ. Nút chính cao tối thiểu
52 px, nút viền tối thiểu 48 px, bo 18 px. Màu macro giữ hệ thống sẵn có: đỏ cho
protein, amber cho carb, xanh cho fat và coral cho năng lượng.

Các widget dùng lại được đã được tách thành `HealthSurface`, `ProfileStepHeader`,
`ProfileOptionCard`, `ProfileSummaryCard`, `NutritionHeroCard`,
`MacroProgressCard`, `DailyDateStrip`, `MealPlanCard`, `MealSlotSection`,
`NutritionEmptyState`, `NutritionSkeleton` và `MealDetailContent`.

## Profile Onboarding

Tài khoản mới thấy màn hình chào “Hồ sơ sức khỏe của bạn”, minh họa sức khỏe dạng
vector, lời giải thích vì sao chatbot cần dữ liệu và CTA “Bắt đầu”. Luồng không tạo
giá trị mặc định giả và vẫn tuân theo cổng hoàn thiện hồ sơ hiện hữu.

## Health Profile Wizard

Form dài được chia thành sáu bước theo ranh giới lưu hiện hữu: thông tin cơ bản,
mục tiêu, sức khỏe/dinh dưỡng, ưu tiên hỗ trợ và dinh dưỡng chi tiết, tập luyện/an
toàn, xác nhận. Tiến độ phân đoạn luôn cho biết bước hiện tại. Trường tên, tuổi,
giới tính, chiều cao và cân nặng có vùng chạm lớn, đơn vị rõ ràng; mục tiêu dùng thẻ
chọn lớn. Dị ứng, hạn chế ăn và sở thích vẫn là các khái niệm riêng.

Tất cả widget bước giữ state trong khi đi tới/lùi. Giá trị `UNKNOWN`/chưa cung cấp
được hiển thị riêng, không bị biến thành `false` hoặc câu trả lời đã xác nhận. Hai
pha lưu hiện hữu được giữ nguyên để không thay đổi HealthProfile V2 semantics.

## Confirmation

Màn hình xác nhận gom thành các card riêng cho thông tin cơ bản, mục tiêu, dị ứng,
hạn chế ăn, sở thích, tập luyện, an toàn tập luyện và an toàn dinh dưỡng. Mỗi nhóm
có hành động sửa đưa người dùng về đúng form; dữ liệu đã nhập không cần nhập lại.
CTA “Hoàn tất” dùng đúng phương thức lưu của provider và giữ các trạng thái loading,
lỗi, thành công hiện hữu.

## Nutrition Today

Màn Dinh dưỡng trả lời theo thứ tự: ngày đang chọn, năng lượng, macro, kế hoạch dự
kiến và nhật ký đã ăn. Date strip chuyển ngày tại chỗ. Nhật ký chỉ cộng các bữa đã
xác nhận; bữa chờ được đặt ở nhóm riêng. Khi hồ sơ hoặc summary không đủ, UI giữ
dữ liệu đã biết và dùng dấu gạch cho phần không biết, không tạo số 0 giả.

## Calories/Macros

Hero card dùng trực tiếp `CanonicalNutritionState` và `DailyNutritionSummary`.
Vòng tiến độ, “Đã ăn / Mục tiêu / Còn lại” và trạng thái vượt mục tiêu đều dùng số
đã được domain cung cấp và hàm làm tròn hiển thị hiện hữu. “Còn lại” chỉ xuất hiện
khi mục tiêu authoritative có mặt. Protein dùng planning target hiện hữu; carb/fat
giữ nguyên khoảng khuyến nghị, không tự lấy trung điểm.

## Today Meal Plan

“Kế hoạch ăn hôm nay” đọc exact Plan V2 snapshot theo domain và ngày. Các món dự
kiến dùng card viền trung tính, icon đồng hồ và nhãn “Dự kiến · chưa ghi nhận”. Việc
mở kế hoạch hoặc xem món không gọi thao tác ghi nhận. Nhật ký actual dùng viền xanh,
check icon và nhãn “Đã ăn · đã ghi nhận”.

## Daily Meal Plan

Màn “Kế hoạch ăn theo ngày” có ngày chọn, mục tiêu hiện có, năng lượng/macro và danh
sách món theo thứ tự bữa sáng, trưa, tối, phụ. Nếu Plan không có giờ chính xác, UI
chỉ hiển thị meal slot. Exact plan/revision metadata được giữ trong mục mở rộng để
không lấn át nội dung người dùng.

## Weekly Plan

Plan nhiều ngày có tổng quan nhẹ với ngày, số bữa, trạng thái dự kiến và tổng kcal
chỉ khi mọi món đều có kcal. Chạm ngày đổi ngày đang xem. Đây là phép tổng hợp trình
bày từ snapshot, không phải planning engine mới.

## Meal Selection

Sheet chọn món có heading lớn, tìm kiếm và các tab hiện được backend hỗ trợ: món
Việt, món đã lưu và nguyên liệu. Card hiển thị placeholder đúng nhóm, tên, kcal khi
có, cùng hai hành động “Xem” và “Chọn”. Callback nhận lại nguyên `Map` món nên ID và
payload không bị dựng lại. Khi catalog trống, skeleton chuyển thành empty state có
“Thử lại”, thay cho trạng thái tải vô hạn.

## Meal Detail

Bottom sheet chi tiết có hero artwork, tên món, khẩu phần, kcal, macro, thành phần
và trạng thái. Dữ liệu không có được ghi “Chưa có”. Banner điều chỉnh khẩu phần chỉ
hiện khi metadata thực sự là `ADAPTED_RECIPE_VARIANT`; không ngụ ý dữ liệu canonical
đã bị sửa.

## Recommendation Feedback

Các nút Thích, Không hợp, Lưu lại và Đổi món có vùng chạm 48 px, giữ callback và
reason code công khai hiện hữu. Feedback nằm trong phần chi tiết/gợi ý và không dùng
chung hành động “Ghi nhận đã ăn”; test xác nhận feedback không mutate nhật ký.

## Loading / Empty / Error States

Plan và catalog dùng skeleton card để ổn định layout. Ngày không có Plan có card
“Bạn chưa có kế hoạch ăn cho ngày này.” cùng entry point Plan hiện hữu. Lỗi tải Plan
có retry inline; dữ liệu canonical không bị thay bằng zero. Nhật ký trống và mục
tiêu chưa khả dụng có thông điệp riêng.

## Accessibility

Đã thêm semantic label cho ngày, tiến độ, trạng thái chọn và năng lượng. Các trạng
thái planned/actual dùng cả chữ, icon và đường viền thay vì chỉ màu. Nút và lựa chọn
chính đạt vùng chạm khoảng 48 px; màu chữ phụ và surface tuân hệ tương phản sẵn có.

## Responsive Layout

Các form và dashboard dùng `SafeArea`, scroll view, constraint linh hoạt và chiều
cao tối thiểu thay vì khóa chiều cao màn hình. Đã render native ở 360x640, 390x844
và 430x932; kiểm tra thêm bàn phím 250 px, nhãn tiếng Việt dài, bottom sheet và nội
dung cuộn. Ảnh kiểm tra nằm trong `apps/mobile/build/ui_redesign/`.

## Tests

Lượt cuối: 94/94 Flutter test đạt. Phạm vi gồm HealthProfile V2/model serialization,
profile readiness, canonical nutrition integration/parity, Plan snapshot/history,
workout profile memory và widget tests cho toàn bộ UI liên quan. Các test mới kiểm
tra draft khi quay lại, UNKNOWN, confirmation, planned/actual, nhóm bữa, macro,
exact ID/map callback, feedback không ghi nhật ký, loading/empty/error/retry và ba
cỡ điện thoại.

Flutter analyzer trên 14 tệp UI/test thay đổi: không có issue. Kiểm tra SHA-256 sau
cùng: 425/425 tệp backend, mobile models/providers/services và assets giữ nguyên so
với baseline trước redesign. Không chạy Playwright, không sửa research artifact,
không commit hoặc push.

## Remaining UX Limitations

Không có ảnh tham chiếu đính kèm trong workspace/message để đối chiếu trực tiếp;
thiết kế bám mô tả và brand hiện hữu. Catalog hiện không mang ảnh món nên dùng
placeholder vector. Plan chưa có giờ sẽ không hiện timeline giờ; UI không bịa giờ.
Các action thay món hoặc ghi nhận trực tiếp từ Plan chỉ xuất hiện khi domain hiện
hỗ trợ; hiện tại Plan detail là read-only và ghi nhận nằm ở nhật ký. Draft giữ khi
đi tới/lùi trong phiên form; draft chưa submit không được ghi bền qua lần tắt app.
Ảnh review dùng Flutter native test với font hệ thống thay thế, không phải build có
Firebase/backend live.

PROFILE_ONBOARDING_REDESIGN_READY = YES

PROFILE_WIZARD_REDESIGN_READY = YES

NUTRITION_TODAY_REDESIGN_READY = YES

TODAY_MEAL_PLAN_REDESIGN_READY = YES

DAILY_MEAL_PLAN_REDESIGN_READY = YES

MEAL_SELECTION_REDESIGN_READY = YES

MEAL_DETAIL_REDESIGN_READY = YES

PLANNED_ACTUAL_VISUALLY_DISTINCT = YES

FLUTTER_UI_TESTS_READY = YES

NO_DOMAIN_LOGIC_REGRESSION = YES
