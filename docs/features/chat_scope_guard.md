# Chat scope guard

`CHAT_SCOPE_GUARD_MODE=strict` đặt Hybrid Domain-Scope Router trước toàn bộ
memory, RAG, tool router và model trả lời chính.

- Câu thuộc dinh dưỡng, vận động, giấc ngủ, cân nặng, sức khỏe hoặc thao tác
  trong ứng dụng được chuyển tiếp vào pipeline chatbot hiện có.
- Câu ngoài phạm vi rõ ràng như toán, thời tiết, lập trình, tài chính hoặc tin
  tức nhận câu từ chối cố định và không gọi model.
- Chào hỏi nhận câu trả lời cố định, không gọi model.
- Safety, lệnh lập trình rõ ràng, toán thuần và các yêu cầu OOS chắc chắn được
  rule xử lý trước. Rule dựa vào hành động và ngữ cảnh, không blacklist tên
  công nghệ. Vì vậy `Flutter app ... sai kcal` được chuyển tiếp, còn `viết code
  Flutter` bị chặn.
- Các fragment còn lại đi qua encoder local `SCOPE_ROUTER_MODEL`, phân loại
  `NUTRITION`, `WEIGHT_MANAGEMENT`, `MEAL_PLANNING`, `FITNESS`,
  `HEALTH_PROFILE`, `APP_HEALTH_DATA`, `GENERAL_WELLNESS`,
  `SAFETY_ESCALATION`, `AMBIGUOUS` hoặc `OUT_OF_SCOPE`.
- Prediction từ ngưỡng cao trở lên được dùng ngay. Vùng uncertainty hoặc bất
  đồng polarity với rule mới gọi `SCOPE_CLASSIFIER_MODEL` làm JSON scope judge.
  Dưới ngưỡng thấp được giữ `AMBIGUOUS`; rule sức khỏe rõ ràng vẫn là fallback
  khi encoder/judge không khả dụng để tránh false refusal do lỗi hạ tầng.
- JSON judge chỉ nhận fragment hiện tại, không nhận lịch sử/hồ sơ/RAG/tool và
  chỉ được xuất `{intent, scope, confidence, reason_code}`. Output sai schema,
  timeout hoặc confidence thấp không được quyền đi vào answer pipeline.
- Safety là trục riêng trên `ScopeDecision`. `đau ngực và khó thở` mang
  `URGENT_ESCALATION`; mục tiêu như `giảm 10kg trong 2 tuần` vẫn là
  `WEIGHT_MANAGEMENT` đúng phạm vi nhưng mang
  `POTENTIALLY_UNSAFE_WEIGHT_GOAL`. Ngưỡng cảnh báo trên 1kg/tuần là cổng thận
  trọng dựa trên khoảng giảm dần 0,5–1kg/tuần được
  [NHS](https://www.nhs.uk/conditions/overweight-and-obesity/) và
  [CDC](https://www.cdc.gov/healthy-weight-growth/losing-weight/index.html)
  khuyến nghị chung; đây không phải chẩn đoán hay mục tiêu cá nhân hóa.
- Câu hỗn hợp được tách theo ranh giới rõ như `tiện thể`, `nhân tiện`, `ngoài
  ra`, dấu chấm phẩy hoặc xuống dòng. Chỉ fragment sức khỏe đi tiếp; fragment
  ngoài phạm vi nhận câu từ chối cố định.
- Xác nhận ngắn như `có`, `không`, `lưu đi` vẫn đi tiếp để cơ chế pending
  action và lịch sử hội thoại xử lý đúng.

Phiên bản hiện tại dùng labelled Vietnamese, English và code-switch prototypes
trên multilingual MiniLM. Model được prewarm trước khi backend nhận traffic để
request đầu không rơi về rule/judge chỉ vì thời gian cold-start. Confidence là
routing score theo ba nhóm cân bằng `ALLOW_HEALTH`/`OUT_OF_SCOPE`/`AMBIGUOUS`,
kết hợp temperature scaling với độ mạnh cosine tuyệt đối để câu lạ không được
cho qua chỉ vì nhóm sức khỏe có nhiều intent hơn. Đây chưa phải xác suất
đã calibrate. Không được coi các ngưỡng mặc định là kết quả nghiên cứu hoặc bật
rollout production trước khi đánh giá trên holdout có nhãn.

Các khóa vận hành liên quan:

- `SCOPE_CLASSIFIER_TIMEOUT_SECONDS=2.5`
- `SCOPE_CLASSIFIER_CONFIDENCE=0.85`
- `SCOPE_ROUTER_LOW_CONFIDENCE=0.55`
- `SCOPE_ROUTER_HIGH_CONFIDENCE=0.85`
- `SCOPE_ROUTER_WARMUP_TIMEOUT_SECONDS=45`
- `SCOPE_ROUTER_FULL_CONFIDENCE_SIMILARITY=0.50`
- encoder và JSON judge không được fallback sang model trả lời chính/model nặng.

Có thể đặt `CHAT_SCOPE_GUARD_MODE=off` để rollback vận hành. Không nên dùng chế
độ này mặc định vì mọi câu sẽ quay lại pipeline LLM cũ.

## Evaluation harness

`scripts/evaluate_scope_router_v2.py` chạy độc lập bốn cấu hình `rule-only`,
`small-only`, `llm-only` và `hybrid`. Dataset JSONL phải tự khai báo
`SYNTHETIC_DEVELOPMENT` hoặc `HUMAN_LABELLED_HOLDOUT`; report không chứa lại
text đầu vào. Các metric gồm intent accuracy, OOS precision/recall/F1, false
refusal, OOS leakage, ambiguous accuracy, safety recall, p50/p95, số lần gọi
judge trên 1.000 câu và chi phí ước tính.

Ví dụ development không có lời gọi model ngoài:

```powershell
python scripts/evaluate_scope_router_v2.py `
  data/scope_router_v2_synthetic_development.jsonl `
  --mode rule-only
```

Kết quả từ fixture synthetic chỉ dùng để kiểm tra pipeline và không được báo
cáo như hiệu năng người dùng thật hoặc bằng chứng production.
