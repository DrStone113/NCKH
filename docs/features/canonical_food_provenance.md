# Canonical ingredient catalog và provenance theo field

## Mục tiêu

Nền dữ liệu chỉ có một canonical nutrient record cho mỗi nguyên liệu tại một thời điểm. Nguồn sau không được cộng hoặc ghi đè ngầm lên nguồn trước: chúng chỉ là fallback/cross-check và chỉ được nhập sau khi food matching, license và quyền tái phân phối đã được duyệt.

Runtime hiện dùng 526 dòng của **Bảng thành phần thực phẩm Việt Nam** làm nguồn nutrient duy nhất. Catalog 300 món được enrich khi load, không sửa `vietnamese_foods.json` hoặc các snapshot món đã khóa cho nghiên cứu.

## Source hierarchy

Registry có máy đọc được nằm tại `apps/backend/data/food_source_registry_v1.json`.

| Priority | Source | Vai trò | Trạng thái runtime / license |
| --- | --- | --- | --- |
| 0 | Vietnam FCT | Primary Việt Nam | `ACTIVE`; cần xác nhận riêng quyền tái phân phối thương mại |
| 1 | FAO/INFOODS | Matching, recipe, QA | `METHODOLOGY_ONLY`, không cấp nutrient row |
| 2 | ASEANFOODS | Regional fallback | Chưa nhập; cần review license |
| 3 | USDA FoodData Central | Global fallback | Chưa nhập; dữ liệu CC0, attribution được đề nghị |
| 4 | Thai FCD | Regional fallback | Chưa nhập; dùng thương mại/tái phân phối cần xin phép INMU |
| 5 | MyFCD Malaysia | Regional fallback | Chưa nhập; cần review license |
| 6 | Japan MEXT | Asian cross-check | Chưa nhập; cho phép dùng lại khi ghi nguồn |
| 7 | Korea RDA | Asian cross-check | Chưa nhập; free access nhưng điều khoản tái phân phối cần review |
| 8 | Taiwan TFND | Asian cross-check | Chưa nhập; Open Government Data License 1.0 |
| 9 | Australia AFCD | Global cross-check | Chưa nhập; giấy phép dựa trên CC BY-SA 3.0 AU và có điều kiện bổ sung |

Nguồn chính thức: [Vietnam FCT](https://chuyentrang.viendinhduong.vn/viewfilenew/vi/thu-vien-sach-chuyen-nganh/189/1.html), [FAO/INFOODS standards](https://www.fao.org/infoods/infoods/standards-guidelines/en/), [USDA FDC API/licensing](https://fdc.nal.usda.gov/api-guide/), [Thai FCD](https://inmu.mahidol.ac.th/thaifcd/home), [MyFCD](https://myfcd.moh.gov.my/), [Japan MEXT](https://www.mext.go.jp/a_menu/syokuhinseibun/), [Korea RDA](https://www.nics.go.kr/food/eng/fctFoodSrchEng/main), [Taiwan open data](https://data.gov.tw/en/datasets/8543), [Australia AFCD](https://www.foodstandards.gov.au/science-data/food-nutrient-databases/afcd/data-files) và [FSANZ data licence](https://www.foodstandards.gov.au/science-data/monitoringnutrients/afcd/datauserlicenceagreement).

## Canonical food record

`modules/nutrition/canonical_foods.py` thêm vào mỗi source row:

- `food_id`: ID ổn định như `VN_FCT_08042`;
- `canonical_key`: giữ tên, state, processing và source record ID;
- `canonical_description`: food/type/part/processing/cooking/state; trạng thái suy từ tên luôn ghi `SOURCE_NAME_PARSER` và không được dùng để biến một match gần đúng thành exact;
- `nutrients_per_100g`: mỗi nutrient mang `value`, `unit`, `basis`, `data_status`, `source_id`, `source_record_id`; field source không công bố giữ `MISSING/null`, tuyệt đối không đổi thành 0;
- `source`: dataset, edition, URL, ngày truy xuất và `match_quality`;
- `allergen_ids`, `objective_tags`, `verification.energy_qa`.

Một dòng thiếu tên Việt nhưng có tên Anh được giữ lại với `canonical_name_language="en"`; không phát sinh tên bằng LLM.

## Food matching và publish gate

Năm mức được hỗ trợ:

```text
EXACT
CLOSE_VARIANT
GENERIC_PARENT
SUBSTITUTED_WITH_JUSTIFICATION
UNRESOLVED
```

Từ D4.1, chỉ `EXACT` có thể tự động publish cho phép tính. Mọi mức còn lại cần reviewer và quyết định có tài liệu; khác biệt species, trạng thái, cut/part, processing hoặc cooking phải được phê duyệt riêng. Runtime hiện chỉ thực hiện exact match với Vietnam FCT. Không tìm thấy tên sẽ tạo `UNRESOLVED + DATA_REVIEW_REQUIRED`; không thay cá basa bằng cá khác, không đổi mollusc thành crustacean và không chọn generic parent ngầm.

[FAO/INFOODS Food Matching Guidelines](https://www.fao.org/fileadmin/templates/food_composition/documents/upload/INFOODSGuidelinesforFoodMatching_version_1_2.pdf) nhấn mạnh chất lượng match, trạng thái chế biến và việc dùng yield/retention khi tính món chín. Vì catalog hiện chưa có metadata cooking đã review, payload ghi rõ `yield_factor_applied=false` và `retention_factor_applied=false`; hệ thống không giả vờ đã hiệu chỉnh nấu nướng.

## Dish quality và serving provenance

Mỗi món live có:

- `ingredients[].food_id`, `match`, `food_state`, `allergen_ids`;
- `nutrition.method=RECIPE_CALCULATED` và tổng macro/năng lượng từ canonical ingredients;
- `serving.serving_weight_g` chỉ là tổng phần nguyên liệu đã định lượng; `recipe_total_weight_g` và `number_of_servings` để `null` khi nguồn không đủ;
- `quality.ingredient_match_complete`, `publishable_for_nutrition_calculation`, `nutrition_consistency`, `catalog_energy_alignment`;
- `dietary_tags.objective` tách khỏi `heuristic`;
- `region_metadata` chỉ có vùng khi kèm official cultural source và confidence; món chưa có nguồn là `Unknown`, không tự coi là nationwide.

Chatbot không còn nhân hệ số kcal của từng nguyên liệu để ép tổng recipe bằng `estimated_calories` legacy. `catalog_energy_alignment` giữ chênh lệch đó làm audit signal; 70 món legacy hiện mang `LEGACY_SERVING_REVIEW_REQUIRED`, trong khi công thức đã chuẩn hóa vẫn dùng được.

## Energy QA và allergen taxonomy

QA dùng `4P + 4C + 9F`:

```text
delta <= 10%  -> PASS
10–20%        -> REVIEW
> 20%         -> FAIL
```

Đây là tín hiệu kiểm định, không thay source energy vì chất xơ, acid hữu cơ, alcohol và quy ước database có thể tạo khác biệt. Validator chặn món có macro-energy `FAIL`, nhưng giữ source row và gắn review để điều tra.

Allergen IDs được derive từ mã nhóm Vietnam FCT kết hợp exact-name taxonomy: `PEANUT`, `TREE_NUT`, `MILK`, `EGG`, `FISH`, `CRUSTACEAN`, `MOLLUSC`, `SOY`, `WHEAT_GLUTEN`, `SESAME`. Tool hỗ trợ các restriction tương ứng và không nhờ LLM tự phán đoán món an toàn.

## Kiểm định

```powershell
cd apps/backend
py -3.10 scripts/validate_dish_catalog.py
py -3.10 -m pytest -q tests/test_canonical_food_provenance.py
```

Validator bắt source priority bị đổi, fallback chưa duyệt được kích hoạt, duplicate canonical ID, nutrient mất field provenance, match không đủ chất lượng, region thiếu nguồn, macro-energy fail và catalog serving cần review.
