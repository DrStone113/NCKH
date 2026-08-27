# Gợi ý bài tập có cá nhân hóa và rào chắn an toàn

## Mục tiêu

`suggest_workout` tạo buổi tập từ catalog wger, giữ giới hạn 2–8 động tác và không vượt quá thời lượng người dùng yêu cầu. Phiên bản này cá nhân hóa liều tập theo mục tiêu, dùng cân nặng thật cho ước tính năng lượng và từ chối kê buổi tập khi có triệu chứng cảnh báo.

## Nguyên tắc bằng chứng

- [CDC – Adult Activity: An Overview](https://www.cdc.gov/physical-activity-basics/guidelines/adults.html): người lớn hướng tới ít nhất 150 phút aerobic cường độ vừa mỗi tuần và hoạt động tăng cơ từ 2 ngày, bao phủ các nhóm cơ chính.
- [Physical Activity Guidelines for Americans, 2nd edition](https://health.gov/paguidelines/second-edition/pdf/Physical_Activity_Guidelines_2nd_edition.pdf): người ít vận động nên tăng dần thời lượng và tần suất trước, sau đó mới tăng cường độ.
- [ACSM 2026 Resistance Training Guidelines](https://acsm.org/resistance-training-guidelines-update-2026/): tính đều đặn và cá nhân hóa theo mục tiêu quan trọng hơn một chương trình phức tạp; tập tại nhà, dây kháng lực và bodyweight đều có hiệu quả.
- [2024 Adult Compendium of Physical Activities](https://pacompendium.com/adult-compendium/): MET là giá trị chuẩn hóa của quần thể, phù hợp để ước tính chứ không phải phép đo tiêu hao chính xác của từng người.
- [American Heart Association – Physical Activity Plan](https://www.heart.org/en/health-topics/cardiac-rehab/getting-physically-active/develop-a-physical-activity-plan-for-you): đau ngực, chóng mặt/lú lẫn, mệt bất thường, khó thở bất thường hoặc nhịp tim nhanh/không đều là các dấu hiệu cần dừng hoạt động và được đánh giá y tế.
- [HHS Physical Activity Guidelines – Scientific Report](https://odphp.health.gov/sites/default/files/2019-09/PAG_Advisory_Committee_Report.pdf): bằng chứng ủng hộ tập các nhóm cơ chính 2–3 ngày không liên tiếp mỗi tuần; tăng dần tải giúp hạn chế nguy cơ chấn thương.
- [CDC – Children and Adolescents](https://www.cdc.gov/physical-activity-education/guidelines/index.html): 6–17 tuổi cần từ 60 phút hoạt động vừa-đến-mạnh mỗi ngày, có hoạt động tăng cơ và xương ít nhất 3 ngày/tuần.
- [CDC – Older Adults](https://www.cdc.gov/physical-activity-basics/adding-older-adults/what-counts.html): người từ 65 tuổi cần kết hợp aerobic, tăng cơ và hoạt động cân bằng.
- [CDC – Measuring Physical Activity Intensity](https://www.cdc.gov/physical-activity-basics/measuring/index.html): ở cường độ vừa, người tập nói chuyện được nhưng không hát được; ở cường độ mạnh chỉ nói được vài từ trước khi phải lấy hơi.

## Hành vi runtime

- `goal` nhận `general_fitness`, `strength`, `muscle_gain`, `endurance`, `weight_loss` hoặc `recovery`; tool thay đổi số hiệp, khoảng lặp và thời gian nghỉ, nhưng không tuyên bố một liều duy nhất là tối ưu cho mọi người.
- Dispatcher tự gắn `weight_kg` và chuyển `health_goal` trong hồ sơ sang mục tiêu buổi tập. Planner dài hạn cũng truyền hai giá trị này trực tiếp.
- Calo dùng công thức standard MET `MET × 3.5 × kg / 200 × phút`; payload luôn có `calories_estimated=true`, phương pháp và cân nặng đã dùng.
- `warning_symptoms` không rỗng làm tool trả `UNSAFE_TO_RECOMMEND_WORKOUT`; chatbot không được tự kê bài để lách rào chắn.
- Metadata dụng cụ wger bị thiếu được bổ sung bằng tên hiển thị rõ ràng. Danh sách rỗng không còn mặc định là bodyweight, tránh gợi ý cable curl, leg press, xe đạp hoặc treadmill khi người dùng chọn `equipment="none"`.

## Giới hạn

Catalog wger không có trường độ khó chuẩn cho mọi bài. `effective_level` là phân loại bảo thủ từ độ phức tạp động tác và dụng cụ, không thay thế đánh giá kỹ thuật trực tiếp. MET cũng không đại diện chính xác cho trao đổi chất cá nhân, thiết bị đeo hoặc kết quả phòng thí nghiệm.

## Kế hoạch nhiều tuần

- Lịch người lớn dùng 2 buổi full-body không liên tiếp cho giảm cân/duy trì và 3 buổi cho tăng cơ; như vậy mỗi nhóm cơ chính xuất hiện nhiều hơn một lần/tuần.
- Buổi `active_recovery` không còn là nhãn trống. Planner gọi `suggest_workout(mobility, goal=recovery, equipment=none)` để tạo 20–25 phút đi bộ, thở, giãn cơ và vận động khớp cường độ nhẹ.
- Người trưởng thành ít vận động bắt đầu với một buổi ít hơn trong giai đoạn thích nghi; planner thêm tần suất trước khi tăng cường độ.
- Chỉ tuần cuối của lộ trình từ 4 tuần mới được đánh dấu `is_deload_week`; các tuần củng cố trước đó không bị giảm tải hàng loạt.
- `weekly_activity_target` phân biệt 10–17, 18–64 và 65+; nhóm 65+ có nhắc hoạt động cân bằng, nhóm 10–17 không bị áp mục tiêu 150 phút của người lớn.
- Mỗi ngày lưu `session_type`, cường độ tương đối, thời lượng, quy tắc tiến triển và talk test. Mobile hiển thị tóm tắt kháng lực–aerobic–phục hồi–nghỉ của tuần.
- Thời lượng buổi có cấu trúc được chặn ở 40 phút để khớp đúng giới hạn tám khối 5 phút của payload hiện tại; app không ghi 45–50 phút khi danh sách bài chỉ cộng được 40 phút.

Kế hoạch có cấu trúc không tự tuyên bố đã đạt đủ 150 phút aerobic chỉ từ các buổi trong app. Phút đi bộ, di chuyển và hoạt động hằng ngày vẫn cần được cộng vào mục tiêu tuần.
