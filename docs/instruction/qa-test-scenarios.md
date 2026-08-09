# QA Test Scenarios — Full System Audit

Bộ kịch bản để kiểm tra thủ công (hoặc bán tự động qua `curl`/script) toàn bộ
hành vi chat: nhận diện ý định, RAG/citation, chống bịa số, tính ngân sách,
search/research, và các vấn đề đã tìm/sửa trong quá trình rebuild frontend.

**Cách dùng:** với mỗi kịch bản, gõ đúng câu hỏi mẫu vào UI (hoặc gọi
`POST /api/v1/chat/stream`), rồi đối chiếu với "Kỳ vọng". Cột "Vì sao" giải
thích lỗi cụ thể nếu sai — tra cứu nhanh khi có regression.

## Kết quả lần chạy gần nhất (toàn bộ §1–§4, §7–§8, có gọi LLM thật)

24 case chạy tự động qua script (`urllib` + SSE parser), 1 bug thật tìm thấy
và đã sửa ngay trong lần chạy:

| Nhóm | Kết quả |
|---|---|
| §1 Chống bịa số (4 case) | 4/4 PASS |
| §2 RAG grounding (3 case) | 3/3 PASS (2 case ban đầu máy đánh dấu REVIEW, đọc full text xác nhận đúng — model honest về việc data không khớp region/thiếu chi tiết, không phải lỗi) |
| §3 Intent detection (11 case) | 11/11 PASS |
| §4 Tính ngân sách (3 case) | ban đầu 4.2 **FAIL thật** — xem bên dưới; sau khi sửa: 3/3 PASS |
| §7 Tìm kiếm web (2 case) | 2/2 PASS |
| §8 Nghiên cứu sâu (1 case) | 1/1 PASS (~38s, đủ 8 bước pipeline) |

**Bug nghiêm trọng tìm thấy & đã sửa (`rag_context` thiếu ở nhánh chat chính):**
Badge "RAG · <tên KB>" trên frontend chưa từng hiện đúng cho luồng chat
thường (mode="rag", KB/project active) — kể cả khi retrieval thật sự thành
công với citation điểm số tốt. Nguyên nhân: `app/api/v1/chat.py`'s nhánh RAG
chính chỉ gửi `sources` trong SSE event cuối, **thiếu hẳn field
`rag_context`** — field này trước giờ CHỈ được set ở nhánh `form_submission`
(dự toán chi phí). Badge luôn hạ về "Chat thường" bất kể retrieval có tốt
hay không, vì frontend cần `rag_context` khác null mới hiện badge RAG.

Tái hiện bằng cách tạo 1 KB mới, upload PDF thật, hỏi 1 câu có match tốt
(0.6 score) — response có 5 sources thật, nội dung đúng, nhưng
`rag_context: None`. Sửa: thêm field `rag_scope_name` (tra tên KB qua
`KnowledgeBaseRepository.get_by_id()` — method mới, không giới hạn quyền sở
hữu vì chỉ dùng để hiển thị tên, hoặc tên project nếu dùng `project_id`),
build `rag_ctx` giống hệt logic đã có ở nhánh form_submission (chỉ set khi
`sources` không rỗng — giữ đúng quy tắc "không credit RAG khi không có
citation thật"). Đã verify lại cả KB user tự tạo lẫn KB hệ thống — badge
hiện đúng `{"kind":"kb","name":"..."}` sau fix.

**Bug tìm thấy & đã sửa (4.2):** submit form KHÔNG kèm `target_budget_vnd`
(hoặc =0) vẫn khiến câu trả lời tự nhắc "Với ngân sách mục tiêu của bạn,
diện tích khả thi ước tính khoảng 100 m²" — dù backend chưa từng đưa mục
ngân sách vào dữ liệu gửi cho LLM. Nguyên nhân: `COST_PRESENT_PROMPT` chỉ
nói "NẾU có mục ngân sách..." mà không nói rõ phải làm gì khi KHÔNG có —
model tự suy diễn/áp khung ngân sách dù không có dữ liệu, dựa trên việc
prompt CÓ NHẮC tới khái niệm này. Sửa: thêm rule tường minh cho nhánh phủ
định ("NẾU KHÔNG có... TUYỆT ĐỐI KHÔNG nhắc tới từ 'ngân sách'") trong
`app/core/mcp/tools/cost_tool.py::COST_PRESENT_PROMPT`. Đã retest 3 lần
(có ngân sách / không / =0 tường minh) — đều đúng sau fix.

---

## 1. Chống bịa số (hallucination guard) — KHÔNG có KB active

Badge phải là **"Chat thường — không dùng RAG"**, KHÔNG có chip trích dẫn.

| # | Prompt | Kỳ vọng | Vì sao sai nếu không đạt |
|---|---|---|---|
| 1.1 | `cho tôi giá vật liệu xây dựng tham khảo` | Hỏi lại vật liệu/khu vực cụ thể, gợi ý chọn KB "Dự toán giá nhà" — **không** đưa số cụ thể | Đã fix ngày hôm nay (`_DEFAULT_SYSTEM` trong `chat.py`) — nếu tái phát, LLM đang bịa lại |
| 1.2 | `giá thép hôm nay bao nhiêu` | Tương tự — hỏi lại/gợi ý KB, không đưa số VNĐ cụ thể | |
| 1.3 | `1kg xi măng giá bao nhiêu` | Tương tự | |
| 1.4 | `giá xây nhà 1m2 bao nhiêu tiền` (không đủ diện tích để trigger form) | Không đưa số cụ thể; có thể gợi ý cung cấp diện tích thật | Kiểm tra ranh giới giữa "đủ info để trigger form" và "không đủ" |

> Lưu ý: nếu **cùng 1 hội thoại** trước đó đã có lượt RAG thật (badge "RAG · ...")
> và sau đó hỏi lại chung chung không kèm KB, model CÓ THỂ lặp lại số liệu thật
> đã thấy trong lịch sử 10 tin nhắn gần nhất — đây là hành vi "nhớ lại", không
> phải bịa, nhưng lượt trả lời sau **không có citation mới** dù số liệu là thật.
> Không coi đây là hallucination nếu số khớp với 1 lượt RAG thật trước đó
> trong cùng hội thoại — kiểm tra kỹ trước khi báo bug.

---

## 2. RAG grounding & citation accuracy — CÓ KB "Dự toán giá nhà" active

Badge phải là **"RAG · Dự toán giá nhà"** CHỈ KHI có ít nhất 1 citation thật.

| # | Prompt | Kỳ vọng |
|---|---|---|
| 2.1 | `giá thép Hòa Phát ở Hà Nội` | RAG badge + chip trích dẫn tên file PDF thật + % score |
| 2.2 | `giá xi măng PCB40 Đà Nẵng` | Tương tự, vùng DN |
| 2.3 | Hỏi 1 câu hoàn toàn ngoài chủ đề (vd `hôm nay trời thế nào`) trong khi KB active | Badge hạ về **"Chat thường"** dù KB đang active — vì không có citation nào đạt `score_threshold=0.5` |
| 2.4 | So khớp: điểm % hiển thị trên chip có nhất quán với nội dung câu trả lời không (không có chip 30-40% bị hiển thị như nguồn chắc chắn) | |

**Kiểm tra dữ liệu (đã phát hiện, ghi nhận là known issue — xem §6):** hỏi cụ
thể `giá tấm đan thoát nước Hà Nội` — nếu câu trả lời hiện material_name chỉ
là số đo (`"0,6 x1 x0,07"`) không có tên vật liệu, đó là data quality bug đã
biết trong `material_prices`, không phải bug retrieval.

**Known limitation (không phải bug, là giới hạn kiến trúc):** Qdrant/RAG
semantic search KHÔNG phải kênh đáng tin cho giá vật liệu chính xác — bảng
`material_prices` (SQL, tra cứu chính xác) mới là nguồn đúng, nhưng công cụ
`lookup_material_price` chỉ reachable qua `mode="agent"`, mà **frontend hiện
tại luôn gửi `mode="rag"`**, không bao giờ `"agent"`. Nên câu hỏi giá cụ thể
(vd `giá thép Hòa Phát ở Hà Nội`) qua chat thường có thể bị từ chối trả lời
dù nghe "rất cụ thể", nếu Qdrant không có chunk nào thật sự khớp mạnh (dưới
threshold 0.5 hoặc chỉ khớp yếu ~0.50-0.52, thậm chí sai vùng) — đây là hành
vi ĐÚNG sau khi thêm 2 chỉ dẫn chống bịa/chống lệch pha ở §1, KHÔNG PHẢI lỗi
mới. Muốn có câu trả lời chính xác cho giá 1 vật liệu cụ thể, cách đáng tin
cậy nhất hiện tại là qua form dự toán (`dự toán giá nhà`) — chat tự do vẫn
phụ thuộc chất lượng match ngữ nghĩa của Qdrant. Nếu muốn nâng cấp (vd mặc
định `mode="agent"` để chat thường cũng dùng được `lookup_material_price`
SQL chính xác), đây là quyết định sản phẩm cần bàn riêng, không tự ý đổi.

---

## 3. Nhận diện ý định → form dự toán (`app/core/chat/intent.py`)

Phải trigger `form_request` (không gọi LLM) cho MỌI câu dưới đây:

| # | Prompt | Trigger form? |
|---|---|---|
| 3.1 | `dự toán giá nhà 100m2` | ✅ (fix hôm nay — thiếu "dự toán" trong nhóm từ khoá) |
| 3.2 | `dự toán giá nhà 100m2 ở hà nội` | ✅ |
| 3.3 | `giá xây 1 căn nhà 100m2 ở hà nội` | ✅ |
| 3.4 | `dự toán giá nhà xây dựng 100m2 ở hà nội` | ✅ |
| 3.5 | `tính chi phí xây nhà 100m2` | ✅ |
| 3.6 | `chi phí làm nhà 100m2` | ✅ |
| 3.7 | `dự toán chi phí xây dựng nhà 100m2` | ✅ |
| 3.8 | `dự toán xây nhà` (không diện tích) | ✅ (form hiện, field diện tích để trống) |

Phải **KHÔNG** trigger (tránh false positive):

| # | Prompt | Trigger form? |
|---|---|---|
| 3.9 | `giá nhà đất hà nội` | ❌ — bất động sản, không phải xây dựng |
| 3.10 | `nhà tôi đẹp quá` | ❌ — chat phiếm |
| 3.11 | `giá xây dựng` (không có "nhà") | ❌ — quá chung chung, không đủ ngữ cảnh |

**Prefill:** với 3.2–3.4, kiểm tra `area_per_floor_m2=100` và `region=HN` được
điền sẵn đúng trong form.

---

## 4. Tính ngược từ ngân sách (mới thêm hôm nay)

| # | Prompt | Kỳ vọng |
|---|---|---|
| 4.1 | `tôi có 1 căn nhà 1000m2 tính toán chi phí tối ưu nhất khoảng 200 triệu để xây 1 căn nhà 1 tầng` | Form prefill `area=1000, target_budget_vnd=200000000`. Sau submit: câu trả lời trả lời THẲNG "~200 triệu xây được khoảng X m²" trước, rồi mới nêu chi phí cho 1000m² để đối chiếu + nói rõ vượt ngân sách |
| 4.2 | Submit form KHÔNG điền ngân sách (để trống) | Trả lời như cũ — bảng giá trực tiếp, KHÔNG có đoạn "ngân sách mục tiêu" |
| 4.3 | Submit form với ngân sách hợp lý (vd diện tích 50m², ngân sách 500 triệu — dư dả) | Câu trả lời nên phản ánh đúng: diện tích khả thi > diện tích đã nhập, không nói "vượt ngân sách" |

**Kiểm chứng toán học:** diện tích khả thi ≈ ngân sách ÷ (tổng chi phí vật
liệu ở mức trung bình ÷ diện tích đã submit). Sai lệch >5% là bug tính toán.

---

## 5. Continuity & UI state (các bug đã sửa — hồi quy)

| # | Kịch bản | Kỳ vọng |
|---|---|---|
| 5.1 | Gửi 1 câu hỏi, đợi trả lời xong, chuyển sang chat khác, quay lại | Lịch sử đầy đủ, không mất tin nhắn |
| 5.2 | Gửi câu hỏi, **ngay khi đang stream** (chưa xong), chuyển ngay sang trang khác (vd Cài đặt), đợi ~10s, quay lại | Câu trả lời đầy đủ phải xuất hiện (có thể có độ trễ ngắn do polling catch-up, không phải typewriter reveal) |
| 5.3 | Gửi câu hỏi trigger form (`dự toán giá nhà 100m2`), **CHƯA submit**, chuyển sang trang khác, quay lại | Form vẫn còn nguyên, có thể điền/submit bình thường — KHÔNG bị mất, KHÔNG hiện "đang suy nghĩ" vô tận |
| 5.4 | Ghim 1 cuộc trò chuyện trong sidebar, tải lại trang (F5) | Vẫn nằm trong mục "Đã ghim" |
| 5.5 | Ghim/xoá 1 tin nhắn trong khung chat (hover vào bubble) | Hoạt động, có badge "Đã ghim" khi ghim |
| 5.6 | Sidebar có nhiều mục Kho tri thức + Dự án + Đã ghim + Gần đây (đủ dài để tràn) | Chỉ vùng danh sách cuộn, logo/nút mới/nav và avatar dưới cùng đứng yên |

---

## 6. Data quality — known issues (không phải bug UI, ghi nhận để theo dõi)

Kiểm tra trực tiếp DB (`docker exec agentic-postgres psql -U agentic -d
agentic_rag`) nếu nghi ngờ số liệu lạ xuất hiện trong câu trả lời:

```sql
-- Đếm số dòng material_name chỉ là số đo (không có tên vật liệu thật)
SELECT COUNT(*) FROM material_prices WHERE material_name ~ '^[0-9]';
-- 1016/10010 dòng tại thời điểm viết tài liệu này (~10%)

-- Đếm số dòng material_category là tên công ty thay vì loại vật liệu
SELECT COUNT(*) FROM material_prices WHERE material_category ~ 'CÔNG TY|C\.TY|CTY';
-- 873/10010 dòng
```

**Nguồn gốc:** `app/core/ingestion/price_extractor.py` — heuristic nhận diện
header/forward-fill category không bắt được tên vật liệu thật khi nó chỉ xuất
hiện 1 lần ở dòng tiêu đề nhóm phía trên 1 bảng con chỉ có kích thước+giá (vd
bảng "Tấm đan thoát nước" của Công ty Thoát nước Hà Nội). Đây là việc sửa
riêng ở tầng ETL, chưa nằm trong phạm vi rebuild frontend — cần xem lại
heuristic ở `price_extractor.py` §3 (`docs/construction-pricing-pipeline.md`)
với các file PDF thực tế bị ảnh hưởng trước khi sửa, để tránh vá nhầm sang
false-positive ở các bảng đang parse đúng.

---

## 7. Tìm kiếm web (`mode="search"`)

| # | Prompt | Kỳ vọng |
|---|---|---|
| 7.1 | Chuyển composer sang "Tìm kiếm", hỏi `giá thép hôm nay trên thị trường` | Badge "Tìm kiếm web" (globe icon), có `[n]` trích dẫn nội dòng + danh sách "Nguồn" cuối câu trả lời |
| 7.2 | Hỏi tiếp `còn ở Đà Nẵng thì sao` (follow-up, không nêu lại chủ đề) | Trả lời đúng ngữ cảnh giá thép — kiểm tra cơ chế "context" 6 tin nhắn gần nhất có hoạt động |

## 8. Nghiên cứu sâu (`mode="research"`)

| # | Prompt | Kỳ vọng |
|---|---|---|
| 8.1 | Chuyển sang "Nghiên cứu", hỏi 1 câu cần tổng hợp nhiều nguồn (vd `xu hướng giá vật liệu xây dựng 2026`) | Panel các bước (Mở rộng câu hỏi → Tìm kiếm → Tổng hợp → Kiểm tra chất lượng → Trả lời) chạy tuần tự, progress bar tăng dần, câu trả lời cuối stream token-by-token có trích dẫn |

## 9. Giọng nói (voice) — chỉ test thủ công qua UI thật, không script được

| # | Kịch bản | Kỳ vọng |
|---|---|---|
| 9.1 | Bấm mic, nói 1 câu hỏi ngắn | STT chuyển thành text đúng, tự động gửi, badge "Giọng nói" hiện trên bubble user |
| 9.2 | Sau khi có trả lời từ câu hỏi voice | Tự động phát audio, có indicator "Đang đọc trả lời…" |

## 10. Đa ngôn ngữ (VI/EN)

| # | Kịch bản | Kỳ vọng |
|---|---|---|
| 10.1 | Bấm nút VI/EN ở TopBar | Toàn bộ UI (nav, badge, composer, placeholder...) đổi ngôn ngữ ngay, không cần reload |
| 10.2 | Đổi sang EN, gửi câu hỏi bằng tiếng Việt | Backend vẫn trả lời tiếng Việt (system prompt: "trừ khi người dùng chủ động dùng ngôn ngữ khác") — UI chrome là EN nhưng nội dung chat theo ngôn ngữ người dùng gõ, đây là hành vi ĐÚNG, không phải bug |

---

## Ghi chú khi chạy test có API cost thật

Các mục §1–§4, §7–§9 gọi LLM/OpenRouter thật (tốn phí). Khi test hàng loạt,
ưu tiên §3 (intent detection, không gọi LLM — free) và §5 (state, không cần
gọi API — free) trước; chỉ chạy §1/§2/§4 khi cần xác nhận sau khi đổi
`_DEFAULT_SYSTEM`/`cost_tool.py`/`intent.py`.
