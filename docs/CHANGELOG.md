## [2026-08-27] — Nâng cấp kế hoạch tập luyện nhiều tuần
- **Weekly structure:** Thay split tăng cơ chỉ chạm mỗi nhóm cơ một lần bằng 3 buổi full-body không liên tiếp; giảm cân/duy trì dùng 2 buổi full-body, xen aerobic và phục hồi.
- **Actionable recovery:** Thêm `mobility` và goal `recovery` vào `suggest_workout`; ngày phục hồi nay sinh bài thật từ catalog thay vì chỉ mang nhãn trống.
- **Progression:** Người ít vận động có một buổi ít hơn trong giai đoạn thích nghi, giữ cường độ dễ khi mới tăng tần suất rồi mới lên intermediate; chỉ tuần cuối của lộ trình từ 4 tuần là deload.
- **Truthful duration:** Chặn buổi có cấu trúc ở 40 phút để thời lượng kế hoạch luôn khớp tối đa 8 bài × 5 phút mà tool thực sự trả về.
- **Age-aware:** Metadata tuần phân biệt mục tiêu CDC cho 10–17, 18–64 và 65+; người lớn tuổi có nhắc thêm hoạt động cân bằng.
- **Mobile:** Màn chi tiết kế hoạch hiển thị tóm tắt số buổi kháng lực, aerobic, phục hồi và ngày nghỉ của tuần.
- **Evidence:** Đối chiếu ACSM 2026, CDC/HHS Physical Activity Guidelines, talk test và hướng dẫn riêng cho thanh thiếu niên/người từ 65 tuổi.
- **Verified:** 564 backend tests passed (22 bộ phụ thuộc/môi trường được skip), 95 Flutter tests passed, `flutter analyze` sạch và validator catalog 300 món báo 0 lỗi.

## [2026-08-27] — Chatbot nhận 300 món và gợi ý bài tập theo bằng chứng
- **Verified integration:** Endpoint dinh dưỡng trả đủ 300 món, `suggest_dish` nạp đủ 300 record và tìm đúng món `normalized_reference_recipe` có ID >97; cả tool món và bài tập đều có trong registry chatbot.
- **Workout quality:** Không còn coi metadata dụng cụ wger bị rỗng là bodyweight; bổ sung suy luận bảo thủ cho cable, machine, xe đạp, treadmill, dây nhảy, box và các dụng cụ ghi rõ trong tên.
- **Personalization:** Thêm mục tiêu `general_fitness/strength/muscle_gain/endurance/weight_loss`, liều sets–reps–rest tương ứng và tự dùng cân nặng trong hồ sơ.
- **Energy honesty:** Thay quy tắc prompt cố định 5/8 kcal/phút bằng ước tính standard MET theo cân nặng; payload ghi rõ phương pháp và giới hạn ước tính.
- **Safety:** Tool từ chối gợi ý khi có triệu chứng cảnh báo tim mạch/hô hấp; prompt buộc chatbot truyền triệu chứng và không lách rào chắn.
- **Evidence:** Bám CDC Physical Activity Guidelines, ACSM 2026 Resistance Training Guidelines, 2024 Adult Compendium và cảnh báo từ American Heart Association.

## [2026-08-26] — Mở rộng catalog món Việt từ 97 lên 300
- **Data:** Thêm 203 `normalized_reference_recipe` từ ViFoodRec (PACLIC 2024), chỉ chọn công thức có nguồn Món Ngon Mỗi Ngày - Ajinomoto Việt Nam; snapshot được khóa bằng commit và SHA-256.
- **Nutrition:** Không sử dụng trực tiếp trường calo của website. Khối lượng được quy về một khẩu phần và năng lượng được tính lại từ Bảng thành phần thực phẩm Việt Nam; mỗi món giữ tên nguyên liệu nguồn, đạt ít nhất 2 nguyên liệu định lượng và độ phủ khối lượng từ 60%.
- **Quality tiers:** Giữ riêng 5 `verified_recipe`, 6 `verified_complete_meal` của Viện Dinh dưỡng và 203 món tham khảo đã chuẩn hóa, tránh đánh đồng mức độ bằng chứng.
- **API/Mobile:** Tăng giới hạn mặc định endpoint món lên 500 và mobile yêu cầu `limit=500`, khắc phục việc catalog lớn hơn nhưng giao diện chỉ nhận 100 món đầu.
- **Tooling:** Thêm pipeline dựng catalog tái lập, validator nguồn/commit/độ phủ/calo và test hồi quy tổng 300 món.
- **Verified:** Validator 0 lỗi; 554 test backend không phụ thuộc các bộ môi trường đã biết và 94 test Flutter đều pass; `flutter analyze` không có issue.

## [2026-08-26] — Catalog món Việt có nguồn kiểm chứng v1
- **Data:** Thêm overlay `vietnamese_dishes_curated_v1.json`; catalog runtime tăng từ 90 lên 97 món, gồm 5 công thức đã kiểm chứng và 6 suất ăn hoàn chỉnh đủ tinh bột–đạm–rau–quả.
- **Sources:** Công thức/khẩu phần lấy từ Viện Dinh dưỡng Quốc gia; thành phần dinh dưỡng nguyên liệu lấy từ Bảng thành phần thực phẩm Việt Nam; phép tính món hỗn hợp tuân theo phương pháp cộng thành phần của FAO/INFOODS.
- **Architecture:** Thêm loader merge có cache cho catalog live nhưng giữ nguyên `vietnamese_dishes.json` để không làm thay đổi corpus nghiên cứu offline đã đóng băng.
- **Safety:** Phân loại hải sản, thịt, trứng và sữa theo mã nhóm thực phẩm chính thức; kết quả `suggest_dish` của món đã kiểm chứng trả kèm provenance.
- **API:** Endpoint chi tiết món/thực phẩm dùng đúng ID số; `/api/nutrition/stats` báo thêm số công thức và suất ăn đã kiểm chứng.
- **Validation:** Thêm validator read-only và test hồi quy cho nguồn, exact food match, độ lệch calo ≤2%, nhóm thực phẩm, provenance, dị ứng và API ID.
- **Verified:** Validator 0 lỗi; 68/68 test trực tiếp và 570 test backend không phụ thuộc property-test/corpus đều pass; compileall pass.

## [2026-08-20] — Sửa lỗi điều hướng sau khi Đăng xuất và Đăng nhập lại
- **Fixed:** Sửa lỗi người dùng sau khi đăng xuất và đăng nhập lại bị đứng ở `AuthScreen` và phải reload/F5 trang mới vào được app.
- **Architecture:** Tách `AuthWrapper` thành module độc lập `auth_wrapper.dart`; chuẩn hóa các luồng đăng xuất trong `HomeScreen` và `AccountSettingsScreen` điều hướng quay về `AuthWrapper` thay vì đè `AuthScreen` trần lên navigation stack.
- **Improved:** Trạng thái xác thực `isAuthenticated` nay phản hồi tức thì: khi đăng nhập (Google, Email hoặc Demo), giao diện tự động chuyển thẳng vào `HomeScreen` mượt mà không cần tải lại trang.
- **Verified:** 70/70 Flutter tests pass; `flutter analyze` 0 issues.

## [2026-08-20] — Tối ưu hóa mượt mà và sửa lỗi mất hiển thị Carousel màn hình Đăng nhập
- **Fixed:** Sửa lỗi slide/carousel tính năng nổi bật trên màn hình đăng nhập (`AuthScreen`) bị mất hiển thị hoặc giật lag do vòng đời `PageController` không ổn định trong `didChangeDependencies`.
- **Improved:** Kích hoạt hỗ trợ kéo/vuốt cảm ứng và chuột (`PointerDeviceKind.mouse`, `touch`, `trackpad`) qua `ScrollConfiguration`, cho phép người dùng chủ động trượt slide mượt mà trên cả Web, Mobile và Desktop.
- **Changed:** Bỏ thẻ "Phân tích Giấc ngủ", tinh gọn danh sách tính năng thành 4 thẻ cốt lõi: Hoạt động, Luyện tập, Dinh dưỡng, Nước uống cùng 4 chấm chỉ báo tương ứng.
- **Improved:** Khởi tạo `PageController` chuẩn xác trong `initState` với `viewportFraction: 0.88` (hiệu ứng thẻ peek hiện đại hai bên) và cuộn vô hạn mượt mà.
- **Improved:** Tự động tạm dừng timer khi người dùng chạm vuốt và kích hoạt lại khi nhả tay; nâng cấp hiệu ứng hover mượt mà và chỉ báo dot chuyển động sắc nét.
- **Layout:** Tối ưu hóa khả năng co giãn linh hoạt của `FeatureCard` và `_FeatureGraphic` bằng `FittedBox(fit: BoxFit.scaleDown)`, loại bỏ nguy cơ tràn pixel (overflow) trên các thiết bị màn hình nhỏ.
- **Verified:** 70/70 Flutter tests pass; `flutter analyze` 0 issues.

## [2026-08-20] — Xử lý dứt điểm cơ chế xóa món cũ khi đổi món trong kế hoạch thực đơn
- **Fixed:** Cải tiến `addMeal(meal, replacePendingSlot: true)` trong `NutritionProvider`: Tự động tìm và xóa sạch món dự kiến chưa ăn (`isCompleted == false`) của cùng bữa ăn (Sáng/Trưa/Tối) khi đổi món mới, không còn tình trạng xuất hiện cả 2 món cùng lúc.
- **Fixed:** Lưu danh sách `_deletedPlanItemIds` vào `SharedPreferences` và chặn `_syncMealsFromBackendPlan` nạp lại món từ backend nếu slot bữa ăn đã có món mới được người dùng/AI cập nhật.
- **Added:** Bổ sung phương thức `replaceMeal(oldMealId, newMeal)` cho phép thay thế trực tiếp món ăn trong ngày.
- **Verified:** 70/70 Flutter tests passed; Flutter Web release build thành công (`build/web`).

## [2026-08-20] — Chuẩn hóa tính Calo Đã Ăn và bổ sung cơ chế đối chiếu thực đơn & xác nhận đổi món
- **Fixed:** Tách biệt hoàn toàn `consumedCalories` (chỉ tính các bữa thực tế đã hoàn thành) và `plannedCalories` (tổng calo kế hoạch cả ngày) trong `NutritionProvider`. Giao diện màn Dinh dưỡng & Trang chủ không còn hiển thị nhầm calo kế hoạch thành calo "Đã ăn".
- **Fixed:** Chatbot chỉ nhận `consumedCalories` thực tế đã nạp, không còn hiểu nhầm là người dùng đã ăn hết calo cả ngày khi các bữa vẫn ở trạng thái "sắp ăn".
- **Added:** Bổ sung cơ chế **"Menu Awareness & Meal Replacement"** vào `system_prompt.py`: Chatbot luôn kiểm tra danh sách món ăn đã lên lịch trong ngày; nếu bữa ăn đã có món trong kế hoạch (ví dụ Bữa tối có *Cơm đùi gà nấu nấm*), AI sẽ thông báo món hiện có, đề xuất món mới và hỏi xác nhận người dùng có muốn đổi món hay không trước khi ghi nhật ký.
- **Verified:** 485/485 backend tests passed; 70/70 Flutter tests passed; live test trên Vilao AI Gateway với model `rk/llms/qwen-3.7-plus` xác nhận phản hồi chính xác 100%.

## [2026-08-20] — Cập nhật cấu hình mô hình Vilao AI và API Key mới
- **Changed:** Chuyển đổi toàn bộ cấu hình AI Provider sang máy chủ Vilao AI (`https://api.vilao.ai/v1`) với API Key mới.
- **Changed:** Cập nhật mô hình chính (`LLM_MODEL`) sang `rk/llms/qwen-3.7-plus` cho các tác vụ trò chuyện, trích xuất dữ liệu và tool calling trực tiếp.
- **Changed:** Cập nhật mô hình suy luận sâu / fallback (`HEAVY_LLM_MODEL`) sang `spd/deepseek-v4-pro` cho các tác vụ phân tích sức khỏe phức tạp và dự phòng tự động khi mô hình chính quá tải.
- **Updated:** Đồng bộ cấu hình trong `apps/backend/.env`, `apps/backend/config.py`, `.env` (gốc), `apps/backend/.env.docker`, `apps/backend/.env.example` và `services/experiment/config.py`.
- **Verified:** Kiểm thử trực tiếp kết nối live API thành công: Health check OK, streaming token OK, non-streaming heavy inference OK, và tool calling detection chính xác.

## [2026-08-14] — Sửa kế hoạch báo thành công nhưng không có món ăn/bài tập
- **Fixed:** `PlannerAgent` không còn dùng chuỗi ghép `planUUID-day-meal` làm `plan_items.id`; mọi item nay dùng UUID v5 hợp lệ và ổn định theo plan/ngày/loại mục.
- **Fixed:** `create_plan` và `append_plan_items` không còn nuốt lỗi PostgreSQL rồi ghi log thành công. Lỗi ghi dữ liệu được truyền ngược lên planner để rollback plan dang dở và để chatbot thông báo thất bại trung thực.
- **Added:** Trước khi trả thành công, planner truy vấn hậu điều kiện trong PostgreSQL: phải đủ toàn bộ ngày và đúng ba bữa ăn mỗi ngày; thiếu dữ liệu sẽ báo `PLAN_INCOMPLETE`, rollback plan mới và không hủy plan active cũ.
- **Security:** `append_plan_items` không còn rơi về plan active mới nhất toàn hệ thống khi `plan_id` sai hoặc không tồn tại, tránh nguy cơ gắn dữ liệu vào plan của người dùng khác.
- **Data repair:** Plan 7 ngày rỗng `10f7ed25…` đã được giữ lại ở trạng thái `cancelled`; plan thay thế `1b1ea25d…` đang active với đủ 21 bữa ăn, 4 buổi tập và đủ Ngày 1–7.
- **Verified:** 456/456 backend tests passed; chạy thật qua PostgreSQL và REST `/plans/{user_id}/active/detail` trả 25 item trên đủ 7 ngày; hậu điều kiện database cũng được chạy end-to-end và dữ liệu chẩn đoán tạm đã được xóa.

## [2026-08-14] — Chia lộ trình dài hạn theo nhịp sinh hoạt tuần
- **Fixed:** Kế hoạch dài hạn không còn là danh sách ngày phẳng dùng cùng một mục tiêu và xoay bài tập theo số thứ tự; 60 ngày nay được hiểu đúng là 8 tuần trọn vẹn + 4 ngày của Tuần 9.
- **Added:** Planner phân toàn bộ lộ trình thành 4 giai đoạn theo tỷ lệ thời lượng: thích nghi, xây nền, tăng tiến và củng cố; mục tiêu calo, protein, cường độ và thời lượng tập thay đổi theo giai đoạn.
- **Added:** Lịch tập bám thứ thật trong tuần, có buổi chính, ngày phục hồi chủ động và Chủ Nhật nghỉ hoàn toàn; giai đoạn chống chững của mục tiêu giảm cân có ngày nạp lại được kiểm soát.
- **Added:** Mỗi plan item lưu metadata tuần/giai đoạn/ngày sinh hoạt để client không phải suy đoán lại quy tắc planner.
- **Changed:** Màn chi tiết hiển thị “60 ngày • 8 tuần + 4 ngày”, đánh dấu tuần cuối chỉ có 4 ngày, đồng thời cho biết thứ/ngày tháng, loại ngày và mục tiêu riêng của từng ngày.
- **Verified:** 452/452 backend tests và 70/70 Flutter tests passed; `flutter analyze` sạch; Flutter Web release build thành công.

## [2026-08-14] — Tạo kế hoạch dài hạn trọn gói, không hỏi vòng vo từng ngày
- **Fixed:** Chatbot không còn tự điều phối `create_plan` → nhiều lượt `suggest_dish`/`suggest_workout` → `append_plan_items` rồi hết ngân sách agent ở Ngày 1–2 và hỏi người dùng tiếp tục nhiều lần.
- **Added:** Tool server `create_long_term_plan` gọi `PlannerAgent` một lần để tính mục tiêu, tạo plan và điền đủ thực đơn + bài tập cho toàn bộ số ngày được yêu cầu; profile hiện có được backend tự gắn vào tool call trước validation.
- **Fixed:** `PlannerAgent` nay gọi được implementation thật nằm trong `ToolRegistry`, bao gồm đúng calling convention dạng một profile-dict của `calculate_tdee`; REST `/plans` và quick action vì vậy dùng chung luồng planner hoàn chỉnh.
- **Changed:** Quick action 7/14/30 ngày không gửi lại câu “Hãy tạo kế hoạch...” vào chatbot sau khi REST đã tạo xong, tránh tạo trùng và tránh một vòng hội thoại xác nhận không cần thiết.
- **Changed:** Reasoning hiển thị cho người dùng được yêu cầu viết ngắn gọn, không kể tên tool, JSON, giới hạn vòng lặp hay kế hoạch điều phối nội bộ.
- **Verified:** 450/450 backend tests và 66/66 Flutter tests passed; `flutter analyze` sạch; kiểm thử end-to-end bằng catalog production tạo đủ 12 mục cho 3/3 ngày; Flutter Web release build thành công.

## [2026-08-14] — Hiệu ứng typewriter cho quá trình suy nghĩ của AI
- **Fixed:** Token `thought`/reasoning nay đi qua hàng đợi typewriter riêng thay vì nối thẳng toàn bộ vào `AIChatMessage`, nên panel “AI đang suy nghĩ...” vẫn nhả chữ mượt khi upstream trả hàng trăm chunk cùng lúc.
- **Changed:** Token câu trả lời cuối được giữ lại cho tới khi backlog suy nghĩ đã hiển thị hết; giao diện không còn chuyển sang câu trả lời và làm ẩn panel reasoning quá sớm.
- **Performance:** Reasoning dùng cùng nhịp 18 ms nhưng hệ số batch nhanh gấp đôi câu trả lời, giữ hiệu ứng dễ quan sát mà không kéo dài quá mức với nội dung suy nghĩ lớn.
- **Lifecycle:** Cả hai hàng đợi và phần câu trả lời đang chờ đều được dọn khi bắt đầu lượt mới, ngắt kết nối, gặp lỗi hoặc dispose provider.
- **Verified:** `flutter analyze` sạch, 66/66 Flutter tests passed và Flutter Web release build thành công.

## [2026-08-14] — Hiển thị đầy đủ các ngày trong lịch trình kế hoạch
- **Fixed:** Màn chi tiết kế hoạch nay luôn dựng đủ ngày trong tuần được chọn, thay vì chỉ render các `day_index` đã có `plan_items`.
- **Added:** Ngày chưa có dữ liệu hiển thị trạng thái rõ ràng và nút “Bổ sung” để yêu cầu AI tạo thực đơn/lịch tập cho ngày đó.
- **Changed:** Chỉ số tiến độ tách số ngày đã có lịch khỏi số mục đã hoàn thành, tránh trường hợp kế hoạch 7 ngày nhưng `3/3 xong` làm người dùng tưởng toàn bộ tuần đã đủ.
- **Verified:** `flutter analyze` sạch, 65/65 Flutter tests passed và Flutter Web release build thành công.

## [2026-08-14] — Làm mượt chữ trả lời Chatbot khi upstream trả dồn
- **Added:** Thêm bộ đệm typewriter phía Flutter để phát dần nội dung câu trả lời thay vì render toàn bộ ngay khi nhà cung cấp xả nhiều SSE chunk cùng lúc.
- **Changed:** Sự kiện WebSocket `done` nay chờ typewriter tiêu thụ hết backlog rồi mới chuyển message sang hoàn tất và hiển thị card/gợi ý.
- **Performance:** Nhịp typewriter tự tăng kích thước batch với câu trả lời dài, giữ hiệu ứng đọc tự nhiên nhưng không kéo dài thời gian chờ quá mức.
- **Unicode:** Pacing theo grapheme cluster bằng package `characters`, tránh cắt đôi emoji ghép hoặc ký tự Unicode.
- **Verified:** `flutter analyze` sạch, 64/64 Flutter tests passed và Flutter Web release build thành công.

## [2026-08-14] — Gỡ nút Thêm bài tập nổi khỏi màn Vận động
- **Changed:** Loại bỏ `FloatingActionButton.extended` “Thêm bài tập” đang đè lên thẻ lịch tập và nút AI ở thanh điều hướng.
- **Compatibility:** Luồng thêm bài tập vẫn giữ nguyên qua nút “Thêm bài tập ngay” trong trạng thái trống và các danh mục bài tập.
- **Verified:** `flutter analyze` sạch, 61/61 Flutter tests passed và Flutter Web release build thành công.

## [2026-08-14] — Hoàn thiện màn Cài đặt và quản lý dữ liệu cá nhân
- **Changed:** Thiết kế lại màn Cài đặt thành các nhóm chức năng rõ ràng: hồ sơ sức khỏe, mục tiêu, trợ lý & nhắc nhở, dữ liệu hội thoại và tài khoản.
- **Added:** Form chỉnh họ tên, tuổi, giới tính, chiều cao, cân nặng, cân nặng mục tiêu và mức độ vận động với kiểm tra dữ liệu trước khi lưu.
- **Added:** Giao diện bật/tắt check-in chủ động theo từng nhóm uống nước, dinh dưỡng, vận động và tâm trạng; lựa chọn được lưu theo user trên thiết bị và đồng bộ lại backend.
- **Added:** Màn quản lý lịch sử hội thoại hỗ trợ tải lại, mở phiên cũ, xóa từng phiên và xóa toàn bộ với hộp thoại xác nhận.
- **Fixed:** Hồ sơ tài khoản demo nay cập nhật state cục bộ thay vì gọi Firestore chưa được khởi tạo; nút Trợ lý AI mở màn chat thật thay vì chỉ hiện snackbar.
- **Privacy:** API danh sách lịch sử chỉ trả session thuộc đúng `user_id`; chế độ anonymous không còn bị ghép vào lịch sử của mọi tài khoản.
- **Verified:** `flutter analyze` sạch, 61/61 Flutter tests và 445/445 backend tests passed; Flutter Web release build thành công.

## [2026-08-14] — Đồng nhất giao diện Chatbot khi xem lại lịch sử
- **Fixed:** Backend nay gom và lưu toàn bộ token `thought` của lượt trả lời vào `chat_messages.thoughts`, thay vì chỉ truyền tạm thời qua WebSocket rồi làm mất khi kết thúc phiên.
- **Changed:** API `GET /chat/sessions/{session_id}/messages` trả lại `thoughts`; `AIChatProvider.loadExistingSession` khôi phục trường này để dùng đúng `AIThoughtsPanel` như tin nhắn vừa chat.
- **Changed:** Panel reasoning đã hoàn tất và panel được nạp từ lịch sử mặc định giữ trạng thái mở như lúc đang chat; người dùng vẫn có thể thu gọn bằng nút mũi tên.
- **Database:** Thêm migration `004_chat_message_thoughts.sql`; dữ liệu lịch sử cũ không có reasoning vì trước đây chưa từng được lưu, còn các lượt chat mới sẽ được khôi phục đầy đủ.

## [2026-08-14] — Đồng nhất card món ăn giữa chat trực tiếp và lịch sử
- **Fixed:** Card món ăn mở lại từ lịch sử nay dùng đúng `StructuredResponse` đã hiển thị lúc chat trực tiếp, giữ nguyên tên món, danh sách nguyên liệu, khối lượng và toàn bộ macro.
- **Changed:** Client tool gửi thêm `ui_message` tách biệt khỏi dữ liệu dành cho LLM; backend lưu payload này vào `chat_messages.structured_data` và API lịch sử trả lại qua trường `structured`.
- **Compatibility:** Các session cũ chưa có payload cấu trúc vẫn dùng bộ khôi phục legacy để không mất hoàn toàn card.
- **Verified:** 444/444 backend tests và 59/59 Flutter tests passed; `flutter analyze` sạch; Flutter Web release build thành công.

## [2026-08-14] — Chỉ hiển thị quá trình suy nghĩ thực tế của Chatbot
- **Changed:** Loại bỏ bong bóng trạng thái trung gian như “Đang tải ngữ cảnh…”, “Đang lập kế hoạch…”, “Đang suy nghĩ câu trả lời…” và “Đang chạy công cụ…”.
- **Changed:** Trong lúc chờ phản hồi, giao diện chỉ render `AIThoughtsPanel` sau khi nhận được token `thought`/reasoning thật từ backend; nếu chưa có reasoning thì không tạo placeholder giả.
- **Changed:** Sự kiện WebSocket `status` vẫn được dùng ngầm làm heartbeat để gia hạn timeout, nhưng không còn được lưu vào `AIChatMessage` hay kích hoạt rebuild giao diện.
- **Verified:** `flutter analyze` không phát hiện vấn đề, toàn bộ 57 Flutter tests passed và `flutter build web --release --no-tree-shake-icons` hoàn tất thành công.

## [2026-08-14] — Tự động build lại Flutter Web khi khởi động
- **Changed:** `start-all.bat` nay tính dấu vân tay SHA-256 của toàn bộ đầu vào build web (`lib/`, `web/`, `assets/`, `pubspec.yaml`, `pubspec.lock`) trước khi mở Web Server.
- **Changed:** Nếu chưa có `build/web`, hoặc dấu vân tay khác lần build thành công gần nhất, script tự chạy `flutter build web --release --no-tree-shake-icons`; nếu không có thay đổi, script dùng lại bản build hiện tại để khởi động nhanh hơn.
- **Safety:** Dấu vân tay chỉ được ghi vào `build/web/.source_hash` sau khi Flutter build thành công. Build lỗi sẽ dừng luồng khởi động Web Server và được thử lại ở lần chạy kế tiếp.
- **Verified:** Fingerprint ổn định qua nhiều lần tính, nhánh không thay đổi nhận đúng `SkipBuild=True`, và `flutter build web --release --no-tree-shake-icons` hoàn tất thành công trong 63,4 giây.

## [2026-08-13] — Comprehensive Exercise Module Overhaul, 3-Phase Routines & Animated Simulation Player
- **Added:** Hệ thống **Luyện tập Tương tác, Mô phỏng Động tác Thể thao & Cải tổ Toàn diện Toàn bộ Giao diện Bài tập**:
  - **Màn hình Vận động Chính ([`exercise_screen.dart`](file:///c:/Project/Chatbot/apps/mobile/lib/features/exercise/screens/exercise_screen.dart)):**
    - Thiết kế lại toàn bộ giao diện: Banner AI Huấn luyện viên thể thao, thẻ thống kê Calo & Thời gian tập luyện với gradient sống động, lưới danh mục bài tập tương tác.
    - Danh sách "Lịch tập hôm nay": Mỗi thẻ bài tập tích hợp trực tiếp nút **▶ Tập ngay** (Quick Play) khởi chạy trình mô phỏng tương tác chỉ với 1 chạm.
    - Modal chi tiết `_ExerciseLiveDetailModal`: Nhúng trực tiếp **Canvas Hoạt ảnh Chuyển động (`WorkoutSimulationWidget`)** ngay tại header, phân tách chuẩn 3 giai đoạn (Khởi động 4p ➔ Thân bài ➔ Giãn cơ 4p), hướng dẫn kỹ thuật từng bước, nhịp thở hít/thở, và nút CTA lớn **🚀 "Bắt đầu luyện tập"**.
  - **Màn hình Chi tiết Bài tập ([`exercise_detail_screen.dart`](file:///c:/Project/Chatbot/apps/mobile/lib/features/exercise/screens/exercise_detail_screen.dart)):**
    - Nhúng khung hoạt ảnh mô phỏng chuyển động `WorkoutSimulationWidget` theo thời gian thực.
    - Bổ sung nút CTA **🚀 "Bắt đầu luyện tập"** kết nối trực tiếp với `WorkoutSimulationScreen`.
  - **Trình duyệt Bài tập ([`exercise_browser_screen.dart`](file:///c:/Project/Chatbot/apps/mobile/lib/features/exercise/screens/exercise_browser_screen.dart)):**
    - Mỗi thẻ bài tập wger được bổ sung nút **▶ Luyện tập ngay** khởi động trình phát đếm giờ và mô phỏng tức thì.
  - **Bộ Chọn Nhóm cơ Thông minh ([`smart_exercise_picker.dart`](file:///c:/Project/Chatbot/apps/mobile/lib/widgets/smart_exercise_picker.dart)):**
    - Bổ sung tùy chọn "Luyện tập ngay" khi chọn bài tập từ bản đồ cơ bắp.
  - **Trình Phát & Mô Phỏng Luyện Tập Tương Tác ([`workout_simulation_screen.dart`](file:///c:/Project/Chatbot/apps/mobile/lib/features/exercise/screens/workout_simulation_screen.dart)):**
    - Đồng hồ đếm giờ tương tác (Circular Countdown Timer) cho bài tập theo thời gian.
    - Đếm hiệp và số lần (Set / Rep Counter) với nút hoàn thành nhanh.
    - Chế độ nghỉ ngơi giữa các hiệp (Rest Interval Timer) đếm ngược 45s kèm hướng dẫn thả lỏng.
    - Thanh theo dõi tiến độ thời gian thực (% hoàn thành, calo ước tính, thời gian tập).
    - Màn hình chúc mừng hoàn thành và lưu thành tích vào nhật ký vận động (`ExerciseProvider`).
  - **Thẻ Hành Động Chatbot ([`action_card_widget.dart`](file:///c:/Project/Chatbot/apps/mobile/lib/widgets/action_card_widget.dart) & [`detail_bottom_sheet.dart`](file:///c:/Project/Chatbot/apps/mobile/lib/widgets/detail_bottom_sheet.dart)):**
    - Badge số lượng bài tập (`X bài tập · 3 giai đoạn`) và modal xem chi tiết 3 giai đoạn.
  - **Sửa Lỗi Tag HTML & Hiệu Chuẩn Chỉ Số Calo Tiêu Thụ ([`exercise_provider.dart`](file:///c:/Project/Chatbot/apps/mobile/lib/providers/exercise_provider.dart)):**
    - `cleanHtml`: Loại bỏ sạch sẽ các thẻ HTML thô (`<p>`, `</p>`, `&nbsp;`, `<br/>`) trên toàn bộ danh mục và modal bài tập.
    - `estimateMETForExercise`: Hiệu chuẩn chính xác chỉ số chuyển hóa MET theo từng động tác thực tế (Nước rút 11.5 MET, Nhảy dây 10.0 MET, Chạy bộ 8.5 MET, Zone 2 7.0 MET, Elliptical 6.0 MET, TRX 5.5 MET, Yoga 3.0 MET...) thay vì gán đồng loạt 8.0 MET gây trùng lặp 284 kcal/30p.
- **Verified:** `flutter analyze` (0 issues), 31/31 tests passed 100% (`flutter test`).

## [2026-08-13] — Multi-Week Phased Health Plan Roadmap & Week-by-Week Architecture
- **Added:** Kiến trúc **Lộ trình Kế hoạch Sức khỏe Đa Giai đoạn theo Tuần (Phased Multi-week Roadmap)** hỗ trợ các kế hoạch dài hạn (60 ngày / 2 tháng, 30 ngày, 90 ngày):
  - **Flutter UI ([`plan_detail_bottom_sheet.dart`](file:///c:/Project/Chatbot/apps/mobile/lib/widgets/plan_detail_bottom_sheet.dart)):**
    - Bổ sung thanh chọn tuần dạng cuộn ngang (**Week Selector Tabs: Tuần 1, Tuần 2, ..., Tuần N**) kèm chỉ báo trạng thái (*Hiện tại*, *Đã qua*, *Sắp tới*).
    - Hiển thị thẻ tổng quan giai đoạn khoa học (**Phase Milestone Card**): Giai đoạn 1 (Tuần 1-2 Thích nghi), Giai đoạn 2 (Tuần 3-4 Tăng tốc đốt mỡ), Giai đoạn 3 (Tuần 5-6 Đột phá & Chống chững), Giai đoạn 4 (Tuần 7-8+ Siết nét & Duy trì).
    - Tự động lọc và nhóm danh sách thực đơn & bài tập theo tuần được chọn (`day_index` tương ứng), kèm checkbox hoàn thành mục tiêu.
    - Bổ sung hộp thoại **Check-in cân nặng tuần** tích hợp trực tiếp với API `/plans/checkins`.
    - Trạng thái rỗng thông minh cho tuần mới kèm nút kích hoạt AI sinh thực đơn/bài tập cuốn chiếu.
  - **Backend API ([`backend_api_service.dart`](file:///c:/Project/Chatbot/apps/mobile/lib/services/backend_api_service.dart)):** Bổ sung phương thức `createPlanCheckin` gửi dữ liệu check-in cân nặng và cảm nhận về máy chủ.
  - **AI Agent System Prompt ([`system_prompt.py`](file:///c:/Project/Chatbot/apps/backend/services/agent/system_prompt.py)):** Bổ sung chỉ dẫn xây dựng lộ trình 4 giai đoạn theo tuần và sinh chi tiết thực đơn/bài tập cuốn chiếu cho tuần hiện tại khi người dùng yêu cầu kế hoạch 60 ngày.
- **Verified:** 40/40 tests `test_planner.py` và `test_plan_tools.py` passed 100%, `flutter analyze` 0 issues.

## [2026-08-13] — Compile and Linter Fixes in Flutter App
- **Fixed:** Khắc phục lỗi biên dịch nghiêm trọng do thiếu từ khóa `async` trong hàm xử lý Tool Call của `AIChatProvider` khiến trình biên dịch Dart không thể nhận diện từ khóa `await` và gây ra chuỗi lỗi cú pháp liên quan.
- **Fixed:** Dọn dẹp các cảnh báo phân tích linter trong dự án Flutter:
  - Loại bỏ hàm private không sử dụng `_preFetchNearbyDates` trong [nutrition_provider.dart](file:///c:/Project/Chatbot/apps/mobile/lib/providers/nutrition_provider.dart).
  - Xóa trường `_error` không sử dụng trong [plan_detail_bottom_sheet.dart](file:///c:/Project/Chatbot/apps/mobile/lib/widgets/plan_detail_bottom_sheet.dart) và tối ưu hóa widget `Row` thành `const Row(...)`.
  - Thay thế 22 lời gọi `.withOpacity()` đã bị deprecated bằng `.withValues(alpha: ...)` trong [main.dart](file:///c:/Project/Chatbot/apps/mobile/lib/main.dart).
  - Thêm ignore rules cho các cảnh báo sử dụng `dart:html` trong [location_helper_web.dart](file:///c:/Project/Chatbot/apps/mobile/lib/utils/location_helper_web.dart).
- **Verified:** Chạy `flutter analyze` cho kết quả thành công tuyệt đối: `No issues found!`.

## [2026-08-13] — Dynamic System Prompt & Personalization Engine theo Thể Trạng, Mục Tiêu và Dữ Liệu App
- **Added:** Kiến trúc **Dynamic System Prompt** tự động biến đổi linh hoạt theo từng người dùng dựa trên dữ liệu thời gian thực trong ứng dụng.
  - **Thể trạng & Chỉ số nhân trắc học:** Tự động tính toán và nhúng các thông số khoa học: **BMI** & Phân loại thể trạng người Việt (Gầy / Bình thường / Thừa cân / Béo phì), **BMR** (Mifflin-St Jeor), **TDEE** (Năng lượng tiêu thụ hàng ngày), **Nhu cầu nước** ($kg \times 0.033$), Mức độ vận động, Cân nặng mục tiêu.
  - **Mục tiêu sức khỏe & Chiến lược tư vấn động:** Tự động áp dụng các nguyên tắc chuyên biệt theo mục tiêu (`lose_weight` - thâm hụt calo an toàn, giữ cơ no lâu; `gain_muscle` - thặng dư calo, đẩy mạnh đạm 1.6-2.2g/kg, quá tải lũy tiến; `maintain` - cân bằng năng lượng quanh TDEE) và thể trạng (bài tập an toàn cho khớp với người thừa cân/béo phì; tăng cân bền vững cho người gầy).
  - **Đồng bộ dữ liệu nhật ký thực tế trong ngày:** Nhúng calo đã nạp (`today_calories_consumed`), calo đã đốt (`today_calories_burned`), calo còn lại (`remaining_calories`), danh sách các bữa ăn và bài tập đã ghi nhận trong ngày để AI căn chỉnh khẩu phần gợi ý tiếp theo chính xác.
  - **Đồng bộ Data Pipeline:** Nâng cấp [ai_chat_provider.dart](file:///c:/Project/Chatbot/apps/mobile/lib/providers/ai_chat_provider.dart) gửi kèm `user_context` phong phú qua WebSocket; cập nhật [chat_gateway.py](file:///c:/Project/Chatbot/apps/backend/services/agent/chat_gateway.py) và [orchestrator.py](file:///c:/Project/Chatbot/apps/backend/services/agent/orchestrator.py) nạp trực tiếp bối cảnh người dùng vào System Prompt ngay từ lượt đầu tiên.
- **Added:** Bổ sung test suite [test_dynamic_system_prompt.py](file:///c:/Project/Chatbot/apps/backend/tests/test_dynamic_system_prompt.py) kiểm tra tính toán BMI/BMR/TDEE, nguyên tắc mục tiêu và tích hợp orchestrator.
- **Verified:** Vượt qua **433/433 bài kiểm thử unit tests** backend (100% passed).

## [2026-08-13] — Live AI Reasoning / Chain-of-Thought Streaming cho Chatbot
- **Added:** Tính năng truyền và hiển thị luồng suy nghĩ thực tế của Chatbot theo thời gian thực (Live AI Reasoning / Chain of Thought Stream).
  - Khai thông luồng token tư duy (`reasoning_content` và `<think>...</think>`) từ LLM Backend qua WebSocket tới giao diện Chatbot Mobile.
  - Bổ sung chỉ dẫn hệ thống `_REASONING` vào [system_prompt.py](file:///c:/Project/Chatbot/apps/backend/services/agent/system_prompt.py) yêu cầu AI phân tích logic, cân nhắc calo/macro và công cụ trước khi đưa ra phản hồi hoặc gọi tool.
  - Nâng cấp component `AIThoughtsPanel` trong [chatbot_screen.dart](file:///c:/Project/Chatbot/apps/mobile/lib/features/chat/screens/chatbot_screen.dart) với biểu tượng bộ não phát sáng, live spinner, định dạng Markdown rõ ràng, tự động mở rộng theo thời gian thực và cho phép đóng/mở linh hoạt khi hoàn tất.
- **Fixed:**
  - Loại bỏ hoàn toàn kỹ thuật `prefill = " "` và các quy tắc cấm suy nghĩ cũ trong [orchestrator.py](file:///c:/Project/Chatbot/apps/backend/services/agent/orchestrator.py), khắc phục triệt để việc mô hình bị chặn không xuất ra token tư duy.
  - Cập nhật [llm_client.py](file:///c:/Project/Chatbot/apps/backend/services/agent/llm_client.py) để lưu trữ an toàn `reasoning_content` trong buffer đầu và không nuốt stream khi chuẩn bị gọi tool.
  - Cập nhật tên mô hình chính xác `LLM_MODEL=ds/qwen3.5-397b-a17b` trong `config.py` và `.env`.
- **Verified:** 428/428 bài kiểm thử backend unit tests passed 100%, kiểm thử luồng suy nghĩ trực tiếp thành công.

## [2026-08-09] — LM Studio Local LLM Integration & Fast/Reasoning Modes
- **Changed:** Cấu hình hệ thống sử dụng mô hình ngôn ngữ lớn chạy cục bộ (Local LLM) qua LM Studio.
  - Cập nhật [apps/backend/.env](file:///c:/Project/Chatbot/apps/backend/.env) để sử dụng `OPENAI_BASE_URL=http://localhost:1234/v1` và đặt tên mô hình `LLM_MODEL` và `HEAVY_LLM_MODEL` là `qwen/qwen3-8b` (đã được nạp và hoạt động trong LM Studio).
  - Cập nhật [.env](file:///c:/Project/Chatbot/.env) ở thư mục gốc thành `OPENAI_BASE_URL=http://host.docker.internal:1234/v1` để tương thích với môi trường Docker Compose.
- **Added:** Tích hợp tính năng tự động chuyển đổi thông minh giữa **Fast Mode** (Thinking OFF) và **Reasoning Mode** (Thinking ON) dựa trên độ phức tạp của câu hỏi (phân loại qua [turn_router.py](file:///c:/Project/Chatbot/apps/backend/services/agent/turn_router.py)):
  - **Fast Mode (Thinking OFF):** Sử dụng kỹ thuật **Response Prefilling** (gửi tin nhắn mở đầu của assistant dưới dạng một dấu cách `" "`) để ép mô hình Qwen3/R1 bỏ qua quá trình suy nghĩ dài dòng khi xử lý các câu hỏi đơn giản (tra cứu calo, định nghĩa dinh dưỡng, chào hỏi). Giúp phản hồi cực kỳ nhanh chóng.
  - **XML Tool Call Fallback:** Khi chạy Fast Mode, bổ sung chỉ dẫn hệ thống yêu cầu mô hình xuất lệnh gọi tool dưới dạng JSON bọc trong thẻ `<tool_call>...</tool_call>` để tương thích với bộ phân tích cú pháp của hệ thống, giúp gọi tool (ghi chép nhật ký, gợi ý thực đơn) vẫn hoạt động 100% chính xác mà không cần qua bước suy nghĩ.
  - **Tối ưu trải nghiệm trực quan:** Tự động ẩn trạng thái "Đang suy nghĩ câu trả lời..." trên giao diện chat khi ở chế độ Fast Mode để tạo cảm giác phản hồi tức thì.
  - **Reasoning Mode (Thinking ON):** Giữ nguyên hành vi suy nghĩ sâu (Chain-of-Thought) cho các tác vụ phức tạp (lên thực đơn 7 ngày, tính macro dinh dưỡng nâng cao, phân tích RAG chéo).
- **Fixed:** Khắc phục mâu thuẫn trong gợi ý bài tập và tính toán calo tiêu thụ:
  - Cập nhật quy định chặt chẽ và bổ sung ví dụ Few-Shot vào [system_prompt.py](file:///c:/Project/Chatbot/apps/backend/services/agent/system_prompt.py) để bắt buộc mô hình phải gọi `suggest_workout` khi người dùng yêu cầu gợi ý bài tập (ví dụ: "tập tay"), cấm tuyệt đối việc tự nghĩ ra tên bài tập hay tự hướng dẫn bằng chữ.
  - Xóa bỏ việc mô hình tự phát ngôn sai lệch rằng "tập kháng lực/tập tay không tính calo đốt", làm rõ quy định calo hệ thống (sức bền/tạ tính 5 kcal/phút, cardio tính 8 kcal/phút).
  - Hướng dẫn mô hình map chính xác tiêu đề buổi tập được đề xuất từ tool (ví dụ: `Arms workout (beginner)`) vào lệnh gọi `log_exercise` thay vì ghi nhận chung chung là "tập tay" khi lưu kế hoạch gợi ý.
  - Cập nhật công cụ `log_exercise` trong [__init__.py](file:///c:/Project/Chatbot/apps/backend/services/agent/tools/__init__.py) hỗ trợ truyền tham số mô tả `description` chứa danh sách chi tiết các động tác được gợi ý.
  - Cập nhật [ai_chat_provider.dart](file:///c:/Project/Chatbot/apps/mobile/lib/providers/ai_chat_provider.dart) và [detail_bottom_sheet.dart](file:///c:/Project/Chatbot/apps/mobile/lib/widgets/detail_bottom_sheet.dart) trên app Flutter để tự động hiển thị danh sách các động tác con được mô tả từ `description`, đồng thời nhận diện chuỗi bài tập kết hợp để hiển thị thông báo phù hợp (*'Đây là chuỗi bài tập kết hợp. Chi tiết thông tin được cung cấp bởi AI.'*) thay vì hiển thị cảnh báo lỗi/bịa bài tập (*'Bài tập này chưa có trong cơ sở dữ liệu wger...'*).
  - Khắc phục lỗi mất thẻ bài tập/dinh dưỡng trực quan (Structured Card) khi tải lại lịch sử hội thoại: Nâng cấp hàm `loadExistingSession` trong [ai_chat_provider.dart](file:///c:/Project/Chatbot/apps/mobile/lib/providers/ai_chat_provider.dart) để tự động phân tích nội dung văn bản của tin nhắn xác nhận từ quá khứ nhằm tái tạo lại cấu trúc thẻ; đồng thời cập nhật [chatbot_screen.dart](file:///c:/Project/Chatbot/apps/mobile/lib/features/chat/screens/chatbot_screen.dart) để tự động ẩn nút "Lưu vào nhật ký" trùng lặp trên các thẻ bài tập/dinh dưỡng đã được lưu thành công trong lịch sử.
  - Loại bỏ việc lưu trữ tin nhắn lỗi (`LLM_UNAVAILABLE` hoặc `LLM_ERROR`) vào database khi LLM gặp sự cố: Cập nhật cơ chế xử lý lỗi trong [orchestrator.py](file:///c:/Project/Chatbot/apps/backend/services/agent/orchestrator.py) để re-raise các lỗi ngoại lệ kết nối/phản hồi lỗi, kích hoạt rollback giao dịch tự động của router để không lưu trữ cả tin nhắn của người dùng lẫn tin nhắn lỗi của hệ thống khi không có câu trả lời thực tế thành công.
- **Verified:** Chạy thử nghiệm thành công trên LM Studio và vượt qua toàn bộ **423/423 bài kiểm thử unit tests** của backend.

## [2026-08-06]
- **Changed:** **Tái cấu trúc cây thư mục theo chuẩn monorepo.** Phẳng hoá `Chatbot/NCKH/` → `Chatbot/` (bỏ 1 tầng lồng thừa); `HealthApp/health_app/` → `apps/mobile/`; `HealthApp/ai_backend/backend/` → `apps/backend/` (bỏ 2 tầng lồng thừa). Thư mục `HealthApp/` bị loại bỏ hoàn toàn.
- **Changed:** `Dataset/` tách thành `data/raw/` (CSV, JSON, PDF nguồn) và `data/scripts/` (script parse/convert). Đổi tên `Cook book Vietnamese of Twin cooker_final.pdf` → `cookbook_vietnamese_twin_cooker.pdf` (bỏ khoảng trắng trong tên file).
- **Changed:** Sắp xếp lại `docs/` thành `architecture/`, `features/`, `guides/`, `archive/`, `thesis/`. Gộp tài liệu backend rải rác (`QUICK_START.md`, `GPU_SETUP.md`, `PGVECTOR_GUIDE.md`, `DOCKER_README.md`, `setup_firebase_guide.md`) vào `docs/guides/`; chuyển nhật ký task đã hoàn thành vào `docs/archive/`.
- **Fixed:** Xoá `HealthApp/.gitignore` — đây là `.gitignore` của **repo Flutter SDK** bị đặt nhầm, không liên quan tới ứng dụng. Xoá `HealthApp/.gitattributes` và `HealthApp/.vscode/settings.json` trùng lặp với bản ở gốc.
- **Fixed:** Gộp 3 bản `pyrightconfig.json` trùng lặp (gốc workspace, `NCKH/`, `backend/`) còn 1 bản ở gốc trỏ đúng `apps/backend`. Cập nhật `.vscode/settings.json` với interpreter, pytest args và `dart.flutterSdkPath`.
- **Fixed:** Gộp 2 bản `AGENTS.md` trùng lặp, giữ bản superset (có mục "ZERO-REPEAT DEFECT MANDATE"), lưu UTF-8 không BOM.
- **Security:** Gỡ `firebase_options.dart` (chứa API keys) khỏi git index bằng `git rm --cached` — file vẫn còn trên đĩa và đã có rule trong `.gitignore`. Chỉ `firebase_options.dart.example` được track.
- **Fixed:** Cập nhật đường dẫn theo cấu trúc mới trong `docker-compose.yml`, `start-all.bat`, và các script Python (`convert_vn_foods.py`, `fix_uw.py`, `parse_pdf_full.py`, `parse_dinhduong.py`, `convert_to_dart.py`) — thay đường dẫn tương đối dễ vỡ bằng `Path(__file__).resolve().parents[n]`.
- **Fixed:** Xoá `analysis_options.yaml` ở gốc (loại trừ `flutter/**` không còn tồn tại); `apps/mobile` đã có bản riêng. Bỏ thuộc tính `version` lỗi thời trong `docker-compose.yml`.
- **Changed:** Thêm `/rules/` và `/.continue/` (config riêng của từng AI IDE) vào `.gitignore`.
- **Verified:** `flutter analyze` 22 info / 0 error, `flutter test` 23/23 passed, `flutter build web` thành công, `pytest` backend **399/399 passed**, `docker compose config` hợp lệ.

## [2026-08-06] — Môi trường Flutter
- **Changed:** Flutter SDK 3.44.8 (Dart 3.12.2) được cài đặt ngoài workspace tại `C:\flutter` và thêm `C:\flutter\bin` vào biến môi trường `PATH` hệ thống. Toàn bộ tài liệu chuyển từ đường dẫn tương đối (`..\..\flutter\bin\flutter.bat`, `../../../flutter/bin/...`) sang gọi lệnh `flutter` / `dart` trực tiếp.
- **Changed:** Cập nhật đường dẫn thư mục dự án trong `docs/RUN_GUIDE_LDPLAYER.md` và `docs/05_run_guide.md` từ `C:\Users\ADMIN\Downloads\Project\Chatbot-NCKH\NCKH\NCKH` sang `C:\Project\Chatbot`; thay các link `file:///` tuyệt đối bằng đường dẫn tương đối trong `docs/04_troubleshooting.md`.
- **Added:** Bổ sung mục "Môi Trường Đã Xác Minh" và "Lệnh Kiểm Thử" vào `docs/05_run_guide.md`, ghi nhận kết quả: `flutter pub get` OK, `flutter analyze` 22 info / 0 error / 0 warning, `flutter test` 23/23 passed, `flutter build web --release --no-tree-shake-icons` thành công.
- **Changed:** Ghi chú máy phát triển chưa cài Chrome — tài liệu chuyển sang dùng device `edge` hoặc `web-server` cho Flutter Web; Visual Studio C++ chưa cài nên chưa build được Windows desktop; Android SDK 36.0.0 cần chạy `flutter doctor --android-licenses`.
- **Changed:** Cập nhật `HUONG_DAN_CAI_DAT.md` bỏ tham chiếu `setup.bat` / `run.bat` (không tồn tại trong `health_app`) và thư mục SDK nhúng `flutter/`.

## [2026-08-01]
- **Added:** Thiết lập bộ unit test đánh giá khả năng tự học thích ứng (Adaptive Learning Evaluation) của AI tại [test_adaptive_learning.py](../apps/backend/tests/test_adaptive_learning.py) gồm 6 ca kiểm thử chi tiết hóa dưới dạng Ma trận chuyển đổi trạng thái (State Transition Matrix).
- **Added:** Thiết lập bộ unit test an toàn sức khỏe y tế mở rộng tại [test_health_safety_eval.py](../apps/backend/tests/test_health_safety_eval.py) kiểm thử các tình huống gợi ý món ăn nâng cao (tìm kiếm có dấu/không dấu, bộ lọc không hải sản, món chay), mâu thuẫn ràng buộc cực đoan, ánh xạ lỗi và tuân thủ ranh giới y tế trong system prompt.
- **Fixed:** Khắc phục lỗi chatbot gợi ý món ăn không đúng ý đồ người dùng (ví dụ: gợi ý Mì xào hải sản khi được yêu cầu Cơm) bằng cách bổ sung tham số tìm kiếm `query` tùy chọn vào schema và hàm xử lý của công cụ gợi ý món ăn `suggest_dish` cùng thuật toán so khớp không dấu tiếng Việt `_remove_accents`.
- **Added:** Tích hợp tính năng hiển thị quá trình suy nghĩ thời gian thực (Real-time Thinking Process). Hỗ trợ tách biệt và stream tokens suy nghĩ (`reasoning_content` của DeepSeek / thẻ `<think>...</think>`) cùng các thông báo trạng thái xử lý trung gian (`send_status` như RAG query, tool call execution) lên giao diện người dùng.
- **Added:** Thiết kế widget `AIThoughtsPanel` collapsible (có thể thu gọn/mở rộng với hiệu ứng) trên Flutter để hiển thị nội dung suy nghĩ của chatbot một cách chuyên nghiệp.
- **Fixed:** Khắc phục lỗi chatbot trả lời hành động ảo (khẳng định đã ghi món/bài tập nhưng không gọi tool) bằng cách cập nhật quy tắc `_TOOL_RULES` và thêm ví dụ Few-Shot chi tiết về gọi công cụ (`tool_calls`) cho các trường hợp người dùng đồng ý/xác nhận lưu gợi ý thực đơn/bài tập vào `system_prompt.py`.
- **Fixed:** Ẩn hoàn toàn nút "Lưu vào nhật ký" thừa thãi và tối ưu chiều rộng nút "Xem chi tiết" trên các thẻ gợi ý món ăn/bài tập có cấu trúc khi chatbot đã tự động lưu thành công các món/bài tập này.
- **Fixed:** Thay thế các biểu tượng Material Icons dạng Rounded/Outline Rounded và các icon không được hỗ trợ trên bản build Web bằng các phiên bản tiêu chuẩn ổn định hơn (Icons.person, Icons.person_outlined, Icons.monitor_weight, Icons.height, Icons.analytics, Icons.local_fire_department, Icons.bolt, Icons.directions_run, Icons.dashboard, Icons.flag, Icons.logout, Icons.edit, Icons.smart_toy...), giải quyết triệt để vấn đề mất icon và đồng bộ hóa hiển thị trên tab bar của giao diện Web.
- **Fixed:** Chỉ tạo cuộc hội thoại trong cơ sở dữ liệu khi người dùng gửi tin nhắn trò chuyện đầu tiên thay vì tạo cuộc hội thoại trống ngay khi kết nối WebSocket bằng cách trì hoãn lệnh gọi `_ensure_session_exists` từ hàm `authenticate()` sang phần nhận tin nhắn của `chat_gateway.py`.
- **Added:** Upgraded chatbot memory architecture to support **Adaptive Memory State Updates** (`add`, `update`, `remove` actions) to automatically deactivate conflicting or outdated user facts, preventing prompt pollution and conflicting instructions.
- **Added:** Implemented **Contextual Window Memory Retrieval** using PostgreSQL full-text search combined with window functions (`ROW_NUMBER()`) to pull matching dialogue snippets along with their surrounding 2 preceding and 2 succeeding turns, merging overlapping exchanges automatically.
- **Fixed:** Prevented irrelevant RAG vector database queries on short conversational responses (e.g. "có", "không", "ừ", "ok") by expanding the `is_simple_greeting_or_chitchat` helper in `memory_service.py` to match short affirmative/negative responses, resolving chatbot prompt confusion.
- **Fixed:** Resolved FastAPI type checking errors in `memory_service.py` by casting row values to correct schemas (`FactCategoryLiteral`, `FactStatusLiteral`, `ChatRoleLiteral`).
- **Fixed:** Eliminated Python 3.12+ deprecation warnings by replacing `datetime.utcnow()` with timezone-aware `datetime.now(timezone.utc)` in `memory_service.py` and `session_store.py`.
- **Fixed:** Removed unused import `app_theme.dart` in `account_settings_screen.dart` to resolve Flutter analyzer warning.
- **Added:** Created Flutter Web Mobile Simulator layout (`_WebPhoneWrapper` in `main.dart`) to constrain the app within a realistic smartphone frame on desktop browsers with switchable aspect ratios (16:9, 19.5:9, 21:9) and themes (Midnight Black, Neon Glow, Glassmorphic).
- **Added:** Added detailed startup instructions to `docs/05_run_guide.md` for both automated and manual service startup.

## [2026-07-29]
- **Fixed:** Resolved browser font blocking issues by creating a custom python server `serve_web.py` to correctly map `.otf` and `.ttf` files to `font/otf` and `font/ttf` MIME types instead of `application/octet-stream` causing missing icons.
- **Fixed:** Resolved `Null check operator used on a null value` runtime crash in `FormattedMarkdownText` by safe-unpacking regex match groups using null-coalescing fallback operators (`?? ''`).
- **Fixed:** Fixed missing filled icons (e.g., `Icons.person_rounded` on active BottomNavigationBar, and badges like `Icons.health_and_safety_rounded`, `Icons.smart_toy_rounded`, `Icons.directions_run_rounded` on `AccountSettingsScreen`) on Flutter Web by building the web app with `--no-tree-shake-icons`.
- **Added:** Implemented complete 2-way data synchronization between AI Chatbot and Flutter HealthApp (`get_active_plan`, `mark_plan_item_complete`, `get_weight_history`, `log_*`).
- **Added:** Integrated `getActivePlanDetail` in `BackendApiService` and connected active plan retrieval with FastAPI backend PostgreSQL database.
- **Added:** Floating AI Assistant (FAB) enabled across all 5 navigation screens with draggable bottom sheet chat interface.
- **Added:** AI Health Nudge Card on Dashboard screen with real-time missing indicator checks (hydration, missing meals, exercise).
- **Added:** Structured documentation system in `docs/` (`01_architecture.md`, `02_database_schema.md`, `03_features/chatbot_integration.md`, `04_troubleshooting.md`).
- **Fixed:** Resolved `ChatbotScreen.initState()` overwriting provider references by passing all 4 providers (`Exercise`, `Nutrition`, `Lifestyle`, `Health`) to `AIChatProvider.setProviders()`.
- **Fixed:** Added null-safe checks in `AIChatProvider.setProviders()` to prevent resetting existing provider references when optional arguments are omitted.
- **Fixed:** Resolved `get_active_plan` returning empty mock data by querying backend endpoints with 404 safety fallback.
- **Fixed:** Fixed null safety dereference in `proactive_checkin_card.dart` and aligned water intake getter to `todayWaterIntake`.
- **Optimized:** Implemented mandatory Parallel Tool Calling prompt directive in `system_prompt.py` forcing LLM to dispatch all context tools in a single turn.
- **Optimized:** Reduced `max_agent_steps` from 6 to 3 and `tool_timeout_ms` from 15000 to 5000 in `config.py`.
- **Optimized:** Applied 1.0-second `asyncio.wait_for` timeout for `queryRag` vector searches in `memory_service.py` to prevent vector embeddings from delaying response generation.
- **Fixed:** Applied Ultra High Contrast typography across `AccountSettingsScreen`: pure white/sky-blue text on dark slate profile cards (`#0F172A`), deep dark slate titles (`#0F172A`), and bold black values (`#0F172A`) on tinted biometric cards (`#1D4ED8`, `#047857`, `#C2410C`).
- **Added:** Added HealthApp Brand Logo badges across the Settings screen header, profile avatar notch, goal/activity item boxes, and app brand footer.
- **Lessons Learned (Anti-Repetition):** Always pass all active providers to `setProviders()` in screen initializers, enforce parallel tool execution via system prompt rules, and place strict timeouts on RAG embeddings searches.

## [2026-07-25]
- **Added:** Implemented **3-Module Modular Architecture** (Module 1: Dinh dưỡng, Module 2: Thể chất, Module 3: Sức khỏe Tinh thần & Lifestyle).
- **Added:** Created `lifestyle_model.dart`, `lifestyle_provider.dart`, and `lifestyle_screen.dart` for Module 3 management in Flutter.
- **Added:** Registered client tools `get_lifestyle_logs`, `log_lifestyle`, `set_lifestyle_reminder` in FastAPI backend `tools/__init__.py` and mapped domain modules via `DOMAIN_MODULE_MAP`.
- **Added:** Updated `system_prompt.py` to instruct LLM on modular domain routing and lifestyle tool invocation strategies.
- **Added:** Created scientific research design document `docs/MODULAR_ARCHITECTURE_DESIGN.md` for NCKH paper publishing.
- **Fixed:** Fixed parameter structure mismatch in `wger_food_search_widget.dart` by properly nesting `MealItem` within `MealModel.items`.
- **Lessons Learned (Anti-Repetition):** Always construct domain models (e.g. `MealModel`) with their exact expected parameters (`items: [MealItem]`) rather than passing raw item properties directly to top-level model constructors.

## [2026-06-30]
- **Added:** Real-time token streaming to Flutter UI (word-by-word rendering).
- **Added:** Locked input TextField and disabled send button when AI chatbot is streaming responses.
- **Added:** Optimistic UI updates for `log_meal` and `log_exercise` client-side tool calls in Flutter.
- **Added:** Local keyword-based nutrition macro lookup inside client `ActionItem` models.
- **Added:** Bún Riêu to backend `nutrition.json` dataset and re-loaded into PostgreSQL vector database (RAG).
- **Added:** Compound recipe splitting in frontend `wger_models.dart` and `ai_chat_provider.dart` to automatically expand compound dishes (such as Bún riêu, Phở bò, Phở gà, Bún chả, Bánh mì kẹp, Cơm tấm) into constituent ingredients for accurate local macro calculations.
- **Optimized:** Truncated context history window to 6 turns in the orchestrator to decrease LLM response latency.
- **Optimized:** Stripped `calories` and `calories_burned` calculation requirements from LLM system prompts and tool schemas.
- **Fixed:** Chatbot message bubble displays stream content on token arrival instead of hiding it in the thinking indicator.
- **Fixed:** Public accessibility of `lookupFoodNutrition` static helper across Dart libraries.
- **Fixed:** Resolved `InterfaceError: another operation is in progress` database crash by removing redundant concurrent `commit()` calls from the WebSocket `tool_result` event handler.
- **Lessons Learned (Anti-Repetition):** Ensure that `notifyListeners()` is triggered on real-time stream token updates to notify widgets. Avoid library-private prefixes (`_`) for static model helpers that need to be accessed by providers across library boundaries. Do not run database commits (`commit()`) concurrently on a single shared async SQLAlchemy session when other asynchronous tasks are actively executing queries/updates.
## [2026-06-25]
- **Added:** System Prompt instructions for generating `StructuredResponse` JSON to enable Flutter action cards (Food/Exercise UI).
- **Added:** System Prompt rules enforcing strict Medical Decorum (no diagnosis).
- **Added:** Backend `orchestrator.py` now parses `{"type": "structured", ...}` JSON from LLM's text stream and routes it via WebSocket.
- **Fixed (AI Hallucination):** The AI fabricated an excuse ("hệ thống hồ sơ đang tạm thời không phản hồi") to ask the user for profile data manually when asked to create a plan. The system prompt was updated to aggressively enforce calling `get_user_profile` for ALL tasks and strictly forbade it from making excuses or asking the user for profile data.
- **Lessons Learned (Anti-Repetition):** Always check if the application is running via Docker or natively. When running via Docker, verify if the files being edited are mounted via volumes or baked into the image. If baked in, a full `docker-compose up --build` is required. Also, for LLMs with strong chat instincts (like DeepSeek), ensure stream parsing handles late-arriving tool calls.
# Development D1 — State correctness and observability (2026-08-23)

- Added production-gated development `ContextTrace` logging.
- Added typed state freshness/conflict and write-result semantics.
- Fixed consumed meal logging and persistence verification.
- Added authoritative chatbot reads and explicit stale snapshot metadata.
- Removed synthesized lifestyle observations.
- Added canonical weight precedence/conflict reporting and post-log profile sync.
- Separated water target, canonical consumed water, and legacy lifestyle water.
- Split active-plan not-found from read failures.
- Added synthetic D1 regression scenarios and D2 calculator dependency map.
