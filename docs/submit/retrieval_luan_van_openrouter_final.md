# CHƯƠNG X. THỰC NGHIỆM VÀ ĐÁNH GIÁ PIPELINE XỬ LÝ BẢNG DÀI CHO HỆ THỐNG RAG

## X.1. Mục tiêu và phạm vi đánh giá

Chương này đánh giá tác động của việc xử lý tài liệu theo cấu trúc bảng đối với một hệ thống hỏi đáp tăng cường truy hồi (Retrieval-Augmented Generation — RAG) trên các công văn công bố giá vật liệu xây dựng. Corpus nghiên cứu gần như toàn bộ là bảng; một số bảng kéo dài qua hàng trăm trang và không lặp lại hàng tiêu đề. Khi tài liệu được làm phẳng thành văn bản rồi chia theo độ dài, các giá trị ở phần giữa hoặc cuối bảng có thể không còn đi kèm nhãn cột. Hệ thống vẫn có thể giữ tên vật liệu và một con số trong cùng đoạn, nhưng không còn tín hiệu rõ ràng cho biết con số hoặc chuỗi văn bản đó thuộc cột “Đơn vị tính”, “Nhà sản xuất”, “Tiêu chuẩn kỹ thuật”, “Cơ sở giá” hay “Giá công bố”.

Câu hỏi trung tâm của nghiên cứu là:

> Việc xử lý và chia tài liệu theo cấu trúc bảng, thay vì chia văn bản thuần theo độ dài, ảnh hưởng như thế nào đến khả năng bảo toàn cấu trúc, chất lượng biểu diễn vector, truy hồi bằng chứng và độ chính xác của câu trả lời; lợi ích xuất hiện ở loại câu hỏi nào và phải trả giá bằng những chi phí gì?

Để tránh quy mọi chênh lệch cho một chỉ số cuối duy nhất, nghiên cứu phân tách hệ thống thành bốn tầng:

```text
Bảo toàn cấu trúc
        ↓
Khả năng phân biệt trong không gian embedding
        ↓
Khả năng truy hồi bằng chứng
        ↓
Khả năng sử dụng context để sinh câu trả lời
```

Cách phân tầng này cho phép xác định liệu table-aware tạo lợi ích ở bước truy hồi hay chủ yếu giúp model diễn giải bằng chứng sau khi bằng chứng đã được đưa vào context.

### X.1.1. Đơn vị được đánh giá

Đối tượng đánh giá là một **pipeline table-aware end-to-end**, gồm các bước:

```text
PDF
→ nhận diện và trích xuất vùng bảng
→ dựng lại lưới ô
→ biểu diễn bảng bằng HTML
→ xác định hoặc khôi phục hàng tiêu đề
→ chia bảng theo ranh giới hàng
→ lặp tiêu đề cho từng chunk
→ mã hóa vector
→ truy hồi
→ sinh câu trả lời
```

Do đó, kết quả phản ánh hiệu quả của toàn bộ pipeline có nhận thức cấu trúc, không chỉ phản ánh riêng thao tác đặt ranh giới chunk. Baseline recursive cũng là một pipeline hoàn chỉnh, bắt đầu từ văn bản PDF đã được làm phẳng và chia theo độ dài.

Phép so chính của chương là **T1500–R1500**. Hai nhánh sử dụng cùng giới hạn chunk danh nghĩa 1.500 token, cùng bộ câu hỏi, cùng embedding model, cùng top-k và cùng model sinh. Điều này giảm số thành phần thay đổi đồng thời và làm cho phép so phù hợp hơn với mục tiêu xác định ảnh hưởng của cách biểu diễn và chia bảng.

### X.1.2. Các câu hỏi nghiên cứu

Chương thực nghiệm trả lời sáu câu hỏi:

- **RQ1 — Bảo toàn cấu trúc:** Pipeline table-aware có duy trì nhãn cột và quan hệ hàng–cột tốt hơn recursive chunking hay không?
- **RQ2 — Chi phí biểu diễn:** Việc lặp header có làm các chunk trở nên gần nhau hơn trong không gian embedding và giảm khả năng phân biệt của dense retriever hay không?
- **RQ3 — Truy hồi:** Table-aware và recursive khác nhau như thế nào theo Recall@1/3/5/10, MRR và điểm vận hành top-5; đồng thời HTML, key–value và verbalized ảnh hưởng ra sao khi chính representation đó được dùng để embedding và lập chỉ mục?
- **RQ4 — Sinh câu trả lời:** Table-aware có cải thiện Exact Match, đặc biệt ở câu hỏi cần ánh xạ đúng giá trị vào đúng cột hay không?
- **RQ5 — Cơ chế sử dụng context:** Khi retrieval không tốt hơn nhưng generation tốt hơn, dữ liệu có cho thấy table-aware chuyển bằng chứng đã truy hồi thành câu trả lời đúng hiệu quả hơn hay không?
- **RQ6 — Độ bền và độ tin cậy:** Kết luận có còn giữ khi bổ sung BM25 và đánh giá trên câu hỏi không có đáp án hay không?

---

## X.2. Dữ liệu và bộ câu hỏi

### X.2.1. Corpus tài liệu

Corpus gồm 11 tệp PDF là công văn và phụ lục công bố giá vật liệu xây dựng. Bộ trích xuất có cấu trúc thu được 11.525 dòng giá dùng để xây dựng câu hỏi và phân tích cấu trúc.

**Bảng X.1. Thống kê corpus**

| Đặc điểm | Giá trị |
| --- | ---: |
| Số tài liệu PDF | 11 |
| Số dòng giá trích được | 11.525 |
| Tài liệu lớn nhất | `HaNoi_PhuLuc.pdf` |
| Số chunk T3000 của tài liệu lớn nhất | 818 |
| Số chunk bảng trong tài liệu lớn nhất | 809 |
| Độ dài bảng dài nhất | khoảng 699 trang liên tục |

`HaNoi_PhuLuc.pdf` là trường hợp đặc biệt quan trọng: một bảng kéo dài khoảng 699 trang nhưng hàng tiêu đề chỉ xuất hiện ở phần đầu. Từ các trang tiếp theo, văn bản thô chứa các giá trị nối tiếp nhưng không còn tín hiệu tường minh để xác định từng giá trị thuộc cột nào. Đây là loại tài liệu mà chiến lược lặp header có cơ sở để tạo khác biệt.

Năm tệp Markdown từng có trong kho dữ liệu được loại khỏi benchmark vì đi qua một pipeline khác và không tạo chunk bảng HTML. Việc giữ chúng trong corpus sẽ làm loãng phép đo đối với các thành phần đang được đánh giá.

### X.2.2. Bộ 500 câu hỏi có đáp án

Bộ benchmark chính gồm 500 câu hỏi. Về mặt vận hành, câu **tra giá** là câu có trường `expect_values`, còn câu **thuộc tính** là câu có trường `expect_text`.

**Bảng X.2. Hai nhóm câu hỏi chính**

| Nhóm | Ký hiệu | Số câu | Năng lực được đo |
| --- | --- | ---: | --- |
| Tra giá | G1–G4 | 252 | Tìm đúng một giá trị số gắn với tên hoặc mã vật liệu |
| Thuộc tính bảng | S1–S4 | 248 | Xác định đúng giá trị ở đúng cột của đúng hàng |
| **Tổng** |  | **500** |  |

Các biến thể G1–G4 lần lượt sử dụng tên nguyên vẹn, tên bỏ dấu, mã sản phẩm bị tách ký tự và tên rút gọn. Các câu S1–S4 hỏi về đơn vị tính, nhà sản xuất, tiêu chuẩn kỹ thuật và cơ sở giá.

Việc tách hai nhóm là một quyết định thiết kế quan trọng. Câu tra giá có thể được trả lời đúng nếu tên sản phẩm và một con số phù hợp xuất hiện gần nhau, ngay cả khi hệ thống không diễn giải đầy đủ cấu trúc bảng. Ngược lại, câu thuộc tính buộc hệ thống xác định một chuỗi thuộc đúng cột của đúng hàng. Vì vậy, mọi bảng kết quả đều báo cáo cả kết quả tổng thể và kết quả riêng cho hai nhóm.

### X.2.3. Bộ 70 câu không có đáp án

Bộ đánh giá khả năng từ chối gồm 70 câu đã được kiểm tra thủ công từ tài liệu nguồn.

**Bảng X.3. Phân bố câu hỏi không có đáp án**

| Nhóm | Số câu | Mục tiêu kiểm tra |
| --- | ---: | --- |
| N1 | 30 | Hàng dữ liệu tồn tại nhưng ô thuộc tính được hỏi bị trống |
| N3 | 20 | Tên hoặc quy cách gần giống dữ liệu thật nhưng không tồn tại |
| N4 | 20 | Kỳ công bố được hỏi không có trong tập tài liệu |
| **Tổng** | **70** |  |

Một câu được chấm đúng khi hệ thống từ chối đưa ra giá trị cụ thể và nêu rằng không tìm thấy thông tin hoặc không có đủ bằng chứng. Một câu bị chấm sai khi hệ thống đưa ra một giá trị không được tài liệu hỗ trợ. Bộ này không được diễn giải độc lập với độ chính xác trên 500 câu có đáp án, vì một hệ thống từ chối mọi truy vấn có thể đạt tỷ lệ bịa thấp nhưng không có giá trị sử dụng.

---

## X.3. Các phương pháp so sánh

### X.3.1. Pipeline table-aware

Pipeline table-aware sử dụng `pdfplumber` để dựng lại lưới bảng, biểu diễn bảng bằng HTML, khôi phục header cho các trang tiếp nối và chia bảng tại ranh giới hàng. Khi một bảng sinh ra nhiều chunk, hàng tiêu đề được lặp lại trong từng chunk và được tính vào ngân sách token.

Hai cấu hình được sử dụng trong phân tích cấu trúc và embedding:

- **T1500:** table-aware với giới hạn 1.500 token;
- **T3000:** table-aware với giới hạn 3.000 token.

Phép so generation chính sử dụng T1500. Cấu hình T3000 được giữ như một điểm tham chiếu về ảnh hưởng của kích thước chunk đối với số lượng chunk và độ tương đồng embedding, nhưng không được dùng để thay thế phép so T1500–R1500.

### X.3.2. Baseline recursive

Baseline sử dụng `RecursiveCharacterTextSplitter` trên văn bản PDF đã được làm phẳng, không giữ đánh dấu ô bảng. Phép so chính sử dụng:

- **R1500:** recursive chunking với giới hạn 1.500 token.

R1500 chịu cùng giới hạn danh nghĩa với T1500 nhưng tạo ít chunk hơn vì không lặp header và không duy trì cấu trúc HTML.

### X.3.3. Dense retrieval và hybrid retrieval

Dense retrieval sử dụng `text-embedding-3-small`. Hybrid retrieval kết hợp dense retrieval với BM25 Okapi; hai bảng xếp hạng được hợp nhất bằng Reciprocal Rank Fusion (RRF) với `k=60`. Mỗi nhánh prefetch 50 kết quả trước khi hợp nhất, sau đó lấy top-5 làm context cho model sinh.

BM25 được áp dụng cho cả T1500 và R1500. Thiết kế này tạo thành phép so 2×2:

| Chunking | Dense | Dense + BM25 |
| --- | --- | --- |
| Table-aware | T1500 dense | T1500 hybrid |
| Recursive | R1500 dense | R1500 hybrid |

Thiết kế 2×2 cho phép tách hai câu hỏi:

1. table-aware có tốt hơn recursive khi cùng dùng một loại retriever hay không;
2. BM25 có giúp table-aware nhiều hơn recursive hay chỉ là cải tiến retrieval tổng quát.

Ngoài phép so T1500–R1500, nghiên cứu thực hiện một **thí nghiệm representation ở tầng retrieval** để tách ảnh hưởng của định dạng chuỗi khỏi ảnh hưởng của ranh giới chunk. Ba index `T1500_HTML`, `T1500_KV` và `T1500_VERB` sử dụng cùng 2.252 logical chunk, cùng hàng, cột, header, giá trị ô và `chunk_id`; chỉ chuỗi được đưa vào embedding thay đổi. KV và verbalized được render bằng quy tắc deterministic, không dùng LLM. Cả ba dùng cùng `text-embedding-3-small`, cosine similarity và dense retrieval. `R1500` được giữ như baseline pipeline riêng, không được xem là representation thứ tư cùng chunk.

Thiết kế này trả lời hai câu hỏi độc lập: **representation nào tạo index dense tốt hơn**, và **representation nào giúp model đọc cùng evidence tốt hơn**. Hai kết quả không được gộp làm một vì representation tối ưu cho retrieval có thể khác representation tối ưu cho generation.

### X.3.4. Thiết lập generation

Model chính là `openai/gpt-oss-20b`, với:

- `temperature=0`;
- `max_tokens=2000`;
- `top_k=5`;
- không gọi công cụ;
- cùng prompt và cùng hàm chuẩn hóa đáp án cho bốn cấu hình.

Toàn bộ benchmark generation được chạy trực tiếp qua OpenRouter với cùng tên model và cùng tham số. Mọi cấu hình giữ nguyên mẫu số 500 câu và không sử dụng kết quả từ endpoint khác để thay thế.

---

## X.4. Chỉ số và quy trình đánh giá

### X.4.1. Tầng cấu trúc

Tầng cấu trúc chạy trên toàn bộ 11.525 dòng, không sử dụng LLM. Các chỉ số chính gồm:

- **Toàn vẹn dòng:** tên vật liệu và giá vẫn nằm trong cùng một chunk;
- **Dòng có nhãn cột:** chunk chứa đủ header cần thiết để diễn giải dòng dữ liệu;
- **Khả năng ánh xạ cột:** representation còn cho phép xác định một giá trị thuộc cột nào;
- **Hàng bị loại:** số hàng không thể đưa vào index do vượt giới hạn chunk.

### X.4.2. Tầng embedding

Độ tương đồng cosine được tính giữa các chunk trong corpus. Nghiên cứu báo cáo median, P90 và tỷ lệ cặp có cosine lớn hơn hoặc bằng 0,90 và 0,95. Tỷ lệ cặp gần trùng cao cho thấy index có nhiều vector khó phân biệt, có thể làm nhiều vị trí trong top-k bị chiếm bởi các chunk gần giống nhau.

### X.4.3. Tầng retrieval

Retrieval được đánh giá tại nhiều điểm cắt thay vì chỉ một `k`. Các chỉ số gồm:

- **Recall@1, Recall@3, Recall@5, Recall@10:** tỷ lệ câu hỏi mà top-k chứa ít nhất một chunk mang giá trị đích theo `expect_values` hoặc `expect_text`;
- **MRR (Mean Reciprocal Rank):** trung bình nghịch đảo thứ hạng của hit đầu tiên, do đó nhạy với việc evidence xuất hiện sớm hay muộn trong danh sách;
- **Median first-hit rank:** trung vị thứ hạng của hit đầu tiên trong các truy vấn có hit;
- **No-hit@10:** số truy vấn không có proxy evidence trong top-10.

`Recall@5` vẫn là **endpoint vận hành chính** vì generation của hệ thống dùng top-5 context. Recall@1/3/10 và MRR được dùng để mô tả hình dạng bảng xếp hạng và tránh kết luận từ một điểm cắt duy nhất.

Do benchmark chưa có `gold_row_id` hoặc `gold_cell_id` độc lập cho toàn bộ 500 câu, các recall trong chương là **proxy evidence hit**: một truy vấn được tính là hit khi top-k chứa giá trị kỳ vọng. Chỉ số này hữu ích để so sánh các cấu hình trên cùng benchmark, nhưng không hoàn toàn tương đương evidence recall dựa trên đúng hàng hoặc đúng ô. Hạn chế này được giữ rõ trong diễn giải kết quả.

### X.4.4. Tầng generation

Câu trả lời được chấm bằng Exact Match (EM) sau chuẩn hóa. Mẫu số luôn là 500 câu cho mỗi cấu hình.

Chỉ số bổ sung là **retrieval-to-answer conversion**:

\[
\text{Conversion}=
\frac{\text{số câu retrieval hit và generation đúng}}
{\text{số câu retrieval hit}}
\]

Conversion được tính theo từng `query_id`, không lấy EM chia cho Recall tổng. Chỉ số này đo khả năng chuyển một retrieval hit thành câu trả lời đúng, nhưng vẫn mang tính mô tả vì retrieval hit dựa trên answer-containing proxy.

### X.4.5. Khả năng từ chối

Trên bộ 70 câu không có đáp án, chỉ số chính là tỷ lệ từ chối đúng. Một câu bị chấm sai khi model đưa ra giá trị cụ thể không được tài liệu hỗ trợ. Cả hai cấu hình hybrid sử dụng cùng model, prompt, top-k và retriever; khác biệt chính là pipeline table-aware hoặc recursive.

### X.4.6. Kiểm định thống kê

Mọi cấu hình trả lời cùng một tập câu hỏi, vì vậy phép so đúng–sai sử dụng kiểm định McNemar ghép cặp. Báo cáo trình bày hai số bất đồng:

- T đúng, R sai;
- T sai, R đúng.

Họ kiểm định xác nhận chính gồm sáu phép so T1500–R1500:

1. dense trên toàn bộ 500 câu;
2. dense trên 252 câu tra giá;
3. dense trên 248 câu thuộc tính;
4. hybrid trên toàn bộ 500 câu;
5. hybrid trên 252 câu tra giá;
6. hybrid trên 248 câu thuộc tính.

Sáu p-value được hiệu chỉnh bằng thủ tục Holm. Cách chọn này bảo thủ hơn việc chỉ hiệu chỉnh bốn phép theo nhóm và tránh lựa chọn họ kiểm định sau khi quan sát kết quả.

Tương tác BM25 được đo bằng chênh-của-chênh:

\[
\Delta_{interaction}=
(T_{hybrid}-T_{dense})-(R_{hybrid}-R_{dense})
\]

Độ bất định được ước lượng bằng paired bootstrap trên `query_id`. Với interaction generation, nghiên cứu sử dụng 100.000 lần resampling, seed `20260807`, và khoảng tin cậy percentile 95%.

---

## X.5. Kiểm soát chất lượng và khả năng tái lập

### X.5.1. Xác minh danh tính index

Trong quá trình kiểm tra, alias cấu hình `T` từng trỏ mặc định tới T3000, tạo nguy cơ gắn nhầm kết quả T3000 cho T1500. Để loại bỏ lỗi này, các script sau đó bắt buộc dùng tên tường minh `T1500`, `T3000` và `R1500`; alias mơ hồ bị từ chối.

Mỗi vector cache được gắn manifest gồm:

- tên cấu hình;
- giới hạn chunk;
- số lượng chunk;
- digest nội dung chunk;
- embedding model;
- cache version.

Cache chỉ được sử dụng khi số chunk và digest khớp dữ liệu hiện tại. Kết quả cuối sử dụng cache version `identity_v2`.

**Bảng X.4. Danh tính các index đã xác minh**

| Cấu hình | Giới hạn | Số chunk | Token trung bình | Digest/manifest |
| --- | ---: | ---: | ---: | --- |
| T1500 | 1.500 | 2.252 | 831 | Khớp |
| T3000 | 3.000 | 1.476 | 1.185 | Khớp |
| R1500 | 1.500 | 790 | 1.102 | Khớp |

### X.5.2. Tách raw cache và file tổng hợp

Cache câu trả lời thô và file kết quả tổng hợp được ghi vào hai đường dẫn khác nhau. Mỗi bản ghi raw lưu tối thiểu:

- `query_id`;
- cấu hình;
- danh sách chunk được truy hồi;
- câu trả lời thô;
- câu trả lời chuẩn hóa;
- điểm đúng/sai;
- `finish_reason`;
- cờ output rỗng;
- token usage;
- prompt hash và model.

Thiết kế này ngăn file tổng hợp ghi đè dữ liệu từng câu và cho phép tính McNemar, conversion và bootstrap trực tiếp từ raw result.

### X.5.3. Tính nhất quán endpoint

Toàn bộ kết quả chính thức của `openai/gpt-oss-20b` được sinh trực tiếp qua OpenRouter. Bốn cấu hình chính sử dụng cùng prompt, cùng hàm chuẩn hóa, cùng tham số generation và cùng endpoint; nghiên cứu không sử dụng kết quả từ endpoint thứ hai để thay thế câu trả lời.

### X.5.4. Phụ thuộc giữa nhãn và parser

Đáp án kỳ vọng được lấy từ dữ liệu có cấu trúc do cùng pipeline trích xuất bảng tạo ra. Điều này có thể tạo thiên lệch có lợi cho table-aware. Đối với chỉ số toàn vẹn dòng, nghiên cứu chỉ giữ tập tên xuất hiện ở mọi nhánh; sau hiệu chỉnh, T và R1500 gần như bằng nhau.

Ngoài ra, 25 câu thuộc tính được lấy ngẫu nhiên để đối chiếu thủ công với PDF gốc; 24 câu khớp và một câu sai, tương đương 96% trong mẫu kiểm tra. Kết quả này làm giảm lo ngại về lỗi nhãn phổ biến nhưng không được diễn giải thành độ chính xác 96% cho toàn bộ 248 câu, vì cỡ mẫu còn nhỏ.

### X.5.5. Hạn chế của nhãn retrieval

Benchmark retrieval hiện sử dụng `expect_values` và `expect_text` thay vì gold row/cell ID độc lập. Vì cùng một đơn vị, nhà sản xuất hoặc con số có thể xuất hiện ở nhiều hàng, Recall@5 có thể chứa hit giả; ngược lại, một câu generation có thể đúng dù proxy retrieval không nhận diện hit. Vì vậy, các kết luận về cơ chế dựa trên conversion được trình bày như bằng chứng phù hợp, không phải phân rã nhân quả tuyệt đối.

---

## X.6. Kết quả

### X.6.1. Bảo toàn cấu trúc

**Bảng X.5. Chất lượng cấu trúc của các cấu hình chính**

| Nhánh | Số chunk | Token trung bình | Toàn vẹn dòng | Dòng có nhãn cột |
| --- | ---: | ---: | ---: | ---: |
| T1500 | 2.252 | 831 | 99,5% | 100% |
| T3000 | 1.476 | 1.185 | 99,5% | 100% |
| R1500 | 790 | 1.102 | 99,4% | 65% |

Sau khi loại ảnh hưởng của nhãn không xuất hiện đồng đều giữa các nhánh, T1500 và R1500 gần như tương đương về việc giữ tên vật liệu và giá trong cùng chunk: 99,5% so với 99,4%. Vì vậy, nghiên cứu không sử dụng “toàn vẹn dòng cao hơn” làm luận điểm chính cho table-aware.

Khác biệt rõ nằm ở nhãn cột. T1500 và T3000 đều giữ header trong 100% chunk bảng, trong khi R1500 chỉ có khoảng 65% dòng đi kèm đủ tín hiệu header theo phép đo hiện tại. Recursive có thể giữ các giá trị gần nhau nhưng không còn đánh dấu ô để xác định chắc chắn giá trị nào thuộc cột nào.

Kết quả trả lời RQ1:

> Lợi thế cấu trúc trực tiếp của table-aware không phải là giữ tên và giá cùng một chunk tốt hơn R1500, mà là duy trì nhãn cột và quan hệ hàng–cột để model có thể diễn giải các thuộc tính.

### X.6.2. Chi phí trong không gian embedding

**Bảng X.6. Độ tương đồng giữa các chunk**

| Nhánh | Median cosine | P90 | Tỷ lệ ≥0,90 | Tỷ lệ ≥0,95 |
| --- | ---: | ---: | ---: | ---: |
| T1500 | 0,633 | 0,788 | 1,67% | 0,38% |
| T3000 | 0,605 | 0,782 | 2,69% | 0,65% |
| R1500 | 0,611 | 0,731 | 0,59% | 0,20% |

T1500 có tỷ lệ cặp cosine ≥0,90 cao hơn R1500 khoảng 2,8 lần (1,67% so với 0,59%). Kết quả này cho thấy việc giữ và lặp header tạo ra một phần văn bản chung giữa các chunk cùng bảng. Phần chung có lợi cho model khi cần hiểu cột, nhưng làm dense retriever khó phân biệt các chunk hơn.

T3000 có tỷ lệ cặp ≥0,90 cao hơn T1500, 2,69% so với 1,67%. Có thể các chunk lớn chứa nhiều hàng với từ vựng và cấu trúc lặp lại, nhưng nghiên cứu chưa thực hiện ablation tách header khỏi body để xác định đóng góp nhân quả của từng phần. Vì vậy, giải thích này chỉ là giả thuyết hậu nghiệm.

Kết quả trả lời RQ2:

> Table-aware tạo một trade-off: bảo toàn header và quan hệ cột tốt hơn, nhưng index chứa nhiều cặp vector gần trùng hơn recursive.

### X.6.3. Hồ sơ retrieval tại nhiều điểm cắt

Việc mở rộng phép đo từ Recall@5 sang Recall@1/3/5/10 và MRR cho thấy T1500 và R1500 có hành vi xếp hạng khác nhau; không có một nhánh thắng nhất quán tại mọi `k`.

**Bảng X.7. Retrieval toàn tập tại nhiều điểm cắt**

| Cấu hình | R@1 | R@3 | R@5 | R@10 | MRR | Median first-hit rank | No-hit@10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| T1500 dense | 207/500 = 41,4% | 307/500 = 61,4% | 343/500 = 68,6% | **394/500 = 78,8%** | 0,5345 | 1,0 | 106 |
| R1500 dense | **228/500 = 45,6%** | **327/500 = 65,4%** | **354/500 = 70,8%** | 389/500 = 77,8% | **0,5659** | 1,0 | 111 |
| T1500 hybrid | 272/500 = 54,4% | 373/500 = 74,6% | **410/500 = 82,0%** | 435/500 = 87,0% | 0,6597 | 1,0 | 65 |
| R1500 hybrid | **294/500 = 58,8%** | **381/500 = 76,2%** | 403/500 = 80,6% | **438/500 = 87,6%** | **0,6844** | 1,0 | 62 |

Trong dense retrieval, R1500 tốt hơn ở R@1, R@3, R@5 và MRR; T1500 chỉ vượt nhẹ ở R@10. Điều này củng cố kết luận rằng table-aware **không tạo lợi thế dense retrieval tổng quát**. Trong hybrid retrieval, R1500 vẫn cao hơn ở R@1, R@3, R@10 và MRR, trong khi T1500 cao hơn tại R@5 — đúng điểm vận hành mà hệ thống dùng để đưa context vào generation. Vì vậy, phát biểu chính xác là **T1500 đạt Recall@5 hybrid cao hơn**, không phải “T1500 có bảng xếp hạng retrieval tốt hơn ở mọi độ sâu”.

**Bảng X.8. Retrieval theo nhóm câu hỏi**

| Cấu hình | Nhóm | R@1 | R@3 | R@5 | R@10 | MRR | No-hit@10 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| T1500 dense | Tra giá | 108/252 | 166/252 | 189/252 | 210/252 | 0,5661 | 42 |
| R1500 dense | Tra giá | 113/252 | 179/252 | 196/252 | 214/252 | 0,5887 | 38 |
| T1500 hybrid | Tra giá | 156/252 | 219/252 | **238/252** | **243/252** | 0,7572 | 9 |
| R1500 hybrid | Tra giá | **171/252** | 219/252 | 228/252 | 241/252 | **0,7798** | 11 |
| T1500 dense | Thuộc tính | 99/248 | 141/248 | 154/248 | **184/248** | 0,5023 | 64 |
| R1500 dense | Thuộc tính | **115/248** | **148/248** | **158/248** | 175/248 | **0,5428** | 73 |
| T1500 hybrid | Thuộc tính | 116/248 | 154/248 | 172/248 | 192/248 | 0,5606 | 56 |
| R1500 hybrid | Thuộc tính | **123/248** | **162/248** | **175/248** | **197/248** | **0,5874** | 51 |

Hai chế độ lỗi tách khá rõ. Với **tra giá**, hybrid làm Recall@5 của T1500 tăng từ 189 lên 238 và R1500 từ 196 lên 228; các token định danh như mã, tên riêng, kích thước và chuỗi số phù hợp với lexical matching. Với **thuộc tính**, R1500 vẫn cao hơn T1500 tại Recall@5 ở cả dense (158 so với 154) và hybrid (175 so với 172). Vì vậy, lợi thế generation thuộc tính của table-aware không thể được giải thích bằng việc retrieval tìm evidence thường xuyên hơn.

Kết quả trả lời phần thứ nhất của RQ3:

> Table-aware không thắng retrieval một cách nhất quán theo độ sâu xếp hạng. R1500 có R@1, R@3 và MRR cao hơn trong cả dense lẫn hybrid; T1500 chỉ vượt R1500 tại operating point R@5 của hybrid và ở một số điểm cắt sâu. Do đó, kết luận retrieval phải gắn với `k` vận hành thay vì quy thành một thứ hạng tổng quát.

### X.6.4. Ảnh hưởng của representation lên dense retrieval

Thí nghiệm representation ở tầng retrieval giữ nguyên 2.252 logical chunk T1500 và chỉ thay chuỗi được embedding. Vì ranh giới chunk, hàng, cột, header và cell value được khóa bằng fingerprint, chênh lệch có thể được diễn giải như ảnh hưởng của representation đối với dense retrieval, không phải ảnh hưởng của chunking. Thí nghiệm này không gọi model generation.

**Bảng X.9. Recall@5 khi thay representation dùng để embedding**

| Representation T1500 | Recall@5 | Tỷ lệ | Chênh so với HTML |
| --- | ---: | ---: | ---: |
| **HTML** | **343/500** | **68,6%** | — |
| Key–value (KV) | 306/500 | 61,2% | −37 câu (−7,4 điểm %) |
| Verbalized (VERB) | 218/500 | 43,6% | −125 câu (−25,0 điểm %) |

HTML đạt Recall@5 cao nhất quan sát được. Việc tuyến tính hóa cùng dữ liệu bảng thành key–value làm mất 37 retrieval hit; verbalized giảm mạnh hơn, mất 125 hit. Kết quả này bác bỏ giả thuyết rằng chuyển bảng sang chuỗi “dễ đọc hơn” tất yếu cải thiện embedding retrieval.

Kết quả cũng tạo ra một phân biệt quan trọng với benchmark generation ở X.6.9: **representation tốt nhất để lập chỉ mục không nhất thiết luôn là representation tốt nhất để một model cụ thể đọc context**. Ở retrieval, HTML là winner rõ tại endpoint R@5. Ở generation, HTML đạt tổng EM cao nhất với GPT-OSS 20B và hai model Gemma, trong khi KV đạt cao nhất với Llama 3.1 8B. Vì vậy, kiến trúc vẫn nên tách `retrieval representation` và `generation representation` về mặt khái niệm, dù HTML là lựa chọn mặc định hợp lý cho phần lớn model trong benchmark hiện tại.

Kết quả trả lời phần thứ hai của RQ3:

> Trên cùng logical chunks T1500, HTML là representation dense-retrieval tốt nhất quan sát được tại Recall@5. Key–value và đặc biệt verbalized không cải thiện retrieval; lợi ích của chúng, nếu có, chỉ xuất hiện ở một số model tại giai đoạn generation.

### X.6.5. Ảnh hưởng của BM25 lên retrieval

**Bảng X.10. Retrieval 2×2 tại operating point top-5**

| Cấu hình | Dense R@5 | Hybrid R@5 | Mức tăng | Tăng tra giá | Tăng thuộc tính |
| --- | ---: | ---: | ---: | ---: | ---: |
| T1500 | 343/500 | 410/500 = 82,0% | +67 | +49 | +18 |
| R1500 | 354/500 | 403/500 = 80,6% | +49 | +32 | +17 |

BM25 cải thiện Recall@5 của cả hai pipeline. T1500 tăng 67 hit, còn R1500 tăng 49 hit. Chênh-của-chênh là +18 câu. Paired bootstrap cho khoảng tin cậy 95% từ −2 đến +37 câu và `p=0,0796`; khoảng tin cậy chứa 0, nên chưa có đủ bằng chứng ở ngưỡng 0,05 để kết luận BM25 tương tác đặc biệt với table-aware.

Mức tăng tập trung mạnh ở tra giá:

- T1500: `189 → 238`, tăng 49/252 câu;
- R1500: `196 → 228`, tăng 32/252 câu.

Ở thuộc tính, mức tăng nhỏ hơn:

- T1500: `154 → 172`, tăng 18/248 câu;
- R1500: `158 → 175`, tăng 17/248 câu.

Kết hợp với hồ sơ xếp hạng ở X.6.3, BM25 không làm T1500 thắng mọi điểm cắt: R1500 hybrid vẫn có R@1, R@3, R@10 và MRR cao hơn. Giá trị của T1500 hybrid nằm ở đúng top-5 context mà hệ thống sử dụng và ở generation thuộc tính sau đó.

Kết quả trả lời phần hybrid của RQ3:

> BM25 là cải tiến retrieval hiệu quả cho cả hai pipeline, đặc biệt ở câu tra giá. T1500 đạt Recall@5 hybrid cao hơn R1500 tại operating point của hệ thống, nhưng interaction chưa đạt ý nghĩa thống kê và R1500 vẫn có lợi thế ở một số chỉ số xếp hạng khác.

### X.6.6. Kết quả generation

**Bảng X.11. Exact Match của bốn cấu hình chính**

| Cấu hình | EM | Tra giá G1–G4 | Thuộc tính S1–S4 |
| --- | ---: | ---: | ---: |
| T1500 dense | 251/500 = 50,2% | 159/252 = 63,1% | 92/248 = 37,1% |
| R1500 dense | 227/500 = 45,4% | 162/252 = 64,3% | 65/248 = 26,2% |
| T1500 hybrid | **292/500 = 58,4%** | **196/252 = 77,8%** | **96/248 = 38,7%** |
| R1500 hybrid | 256/500 = 51,2% | 182/252 = 72,2% | 74/248 = 29,8% |

Trong dense retrieval, T1500 hơn R1500 24 câu tổng thể. Phân rã theo nhóm cho thấy toàn bộ lợi thế đến từ câu thuộc tính:

- tra giá: T ít hơn R 3 câu;
- thuộc tính: T nhiều hơn R 27 câu.

Trong hybrid retrieval, T1500 hơn R1500 36 câu:

- tra giá: T nhiều hơn R 14 câu;
- thuộc tính: T nhiều hơn R 22 câu.

BM25 làm EM của T1500 tăng 41 câu, từ 251 lên 292; R1500 tăng 29 câu, từ 227 lên 256. Ở T1500, 37/41 câu cải thiện thuộc nhóm tra giá và chỉ 4/41 thuộc nhóm thuộc tính. Ở R1500, mức tăng tương ứng là 20 câu tra giá và 9 câu thuộc tính.

Interaction generation quan sát được là `+12` câu, tức mức tăng của T1500 lớn hơn R1500 12 câu. Tuy nhiên, paired bootstrap 100.000 lần cho khoảng tin cậy 95% từ −13 đến +37 câu và `p=0,3723`. Khoảng tin cậy chứa 0, nên chưa có bằng chứng rằng tác động của BM25 lên generation phụ thuộc vào chiến lược chunking.

Mẫu kết quả cho thấy table-aware và BM25 giải quyết hai chế độ lỗi khác nhau:

- table-aware tạo lợi thế rõ nhất ở câu thuộc tính, nơi model phải xác định đúng cột;
- BM25 tạo phần lớn lợi ích ở câu tra giá, nơi mã sản phẩm, kích thước, tên riêng và chuỗi số có giá trị phân biệt cao.

### X.6.7. So sánh ghép cặp và hiệu chỉnh Holm

**Bảng X.12. McNemar và p-value Holm cho họ sáu kiểm định**

| Retriever | Phạm vi | n | T đúng/R sai | T sai/R đúng | p gốc | p Holm |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Dense | Toàn tập | 500 | 80 | 56 | 0,04818 | 0,14455 |
| Dense | Tra giá | 252 | 36 | 39 | 0,8176 | 0,8176 |
| Dense | Thuộc tính | 248 | 44 | 17 | **0,00073** | **0,00438** |
| Hybrid | Toàn tập | 500 | 83 | 47 | **0,00202** | **0,01012** |
| Hybrid | Tra giá | 252 | 42 | 28 | 0,1196 | 0,2392 |
| Hybrid | Thuộc tính | 248 | 41 | 19 | **0,00622** | **0,02487** |

Sau hiệu chỉnh Holm:

- dense thuộc tính vẫn có ý nghĩa (`p_Holm=0,00438`);
- hybrid thuộc tính vẫn có ý nghĩa (`p_Holm=0,02487`);
- hybrid tổng thể vẫn có ý nghĩa (`p_Holm=0,01012`);
- dense tổng thể không còn có ý nghĩa (`p_Holm=0,14455`);
- hai phép so tra giá không có ý nghĩa.

Đây là bằng chứng thống kê trực tiếp cho luận điểm trung tâm:

> Khác biệt giữa table-aware và recursive tập trung ở câu hỏi thuộc tính. Không có bằng chứng thống kê rằng table-aware tốt hơn ở câu tra giá; lợi thế dense tổng thể cũng không còn đứng vững sau hiệu chỉnh so sánh bội.

Kết quả trả lời RQ4:

> Với model `gpt-oss-20b`, table-aware cải thiện ổn định câu hỏi thuộc tính trong cả dense và hybrid. Ở cấu hình hybrid, table-aware còn tốt hơn tổng thể sau hiệu chỉnh Holm.

### X.6.8. Retrieval-to-answer conversion và cơ chế sử dụng context

**Bảng X.13. Tỷ lệ chuyển retrieval hit thành câu trả lời đúng**

| Cấu hình | Toàn tập | Tra giá | Thuộc tính |
| --- | ---: | ---: | ---: |
| T1500 dense | 241/343 = 70,26% | 159/189 = 84,13% | 82/154 = 53,25% |
| T1500 hybrid | 287/410 = 70,00% | 196/238 = 82,35% | 91/172 = 52,91% |
| R1500 dense | 221/354 = 62,43% | 162/196 = 82,65% | 59/158 = 37,34% |
| R1500 hybrid | 249/403 = 61,79% | 182/228 = 79,82% | 67/175 = 38,29% |

Ở câu tra giá, conversion của T và R tương đối gần nhau, nằm trong khoảng 79,8%–84,1%. Ở câu thuộc tính, khoảng cách lớn hơn rõ rệt:

- dense: T1500 53,25%, R1500 37,34%;
- hybrid: T1500 52,91%, R1500 38,29%.

Đáng chú ý, hybrid thuộc tính của T1500 có Recall@5 thấp hơn R1500 (69,4% so với 70,6%) nhưng generation cao hơn (38,7% so với 29,8%). Điều này loại bỏ cách giải thích đơn giản rằng T trả lời tốt hơn chỉ vì retrieval tốt hơn.

BM25 làm Recall@5 tăng mạnh nhưng conversion gần như không tăng:

- T1500: 70,26% xuống 70,00%;
- R1500: 62,43% xuống 61,79%.

Như vậy, BM25 chủ yếu đưa thêm giá trị đích vào top-5; nó không tự động làm model sử dụng context hiệu quả hơn. Ngược lại, table-aware không tạo lợi thế retrieval thuộc tính nhưng có conversion thuộc tính cao hơn đáng kể.

Kết quả trả lời RQ5:

> Dữ liệu phù hợp với giả thuyết rằng table-aware giúp model khai thác quan hệ hàng–cột trong context hiệu quả hơn. Đây là bằng chứng gián tiếp từ conversion, không phải chứng minh nhân quả tuyệt đối, vì retrieval hit hiện vẫn dựa trên answer-containing proxy và top-5 của hai nhánh không giống nhau hoàn toàn.

### X.6.9. Ảnh hưởng của dạng biểu diễn theo model khi giữ cố định retrieval

Thí nghiệm này tách ảnh hưởng của **representation ở giai đoạn generation** khỏi ảnh hưởng của retrieval. Ba nhánh `HTML`, `KV` và `VERB` sử dụng cùng top-5 của T1500 dense, cùng thứ tự chunk và cùng dữ liệu ô; chỉ chuỗi context đưa vào model được thay đổi. Nhánh `Recursive` sử dụng top-5 của R1500 dense và được xem là baseline pipeline, không phải một representation thứ tư dùng chung chunk với T1500.

**Bảng X.14. Exact Match theo model và dạng biểu diễn**

| Model | Arm | Tra giá /252 | Thuộc tính /248 | Tổng /500 |
| --- | --- | ---: | ---: | ---: |
| GPT-OSS 20B | HTML | 159 (63,1%) | 92 (37,1%) | **251 (50,2%)** |
|  | KV | 149 (59,1%) | **94 (37,9%)** | 243 (48,6%) |
|  | VERB | 144 (57,1%) | 87 (35,1%) | 231 (46,2%) |
|  | Recursive | **162 (64,3%)** | 65 (26,2%) | 227 (45,4%) |
| Gemma 3 12B | HTML | 159 (63,1%) | **134 (54,0%)** | **293 (58,6%)** |
|  | KV | 153 (60,7%) | 132 (53,2%) | 285 (57,0%) |
|  | VERB | 157 (62,3%) | 131 (52,8%) | 288 (57,6%) |
|  | Recursive | 158 (62,7%) | 93 (37,5%) | 251 (50,2%) |
| Llama 3.1 8B | HTML | 91 (36,1%) | 119 (48,0%) | 210 (42,0%) |
|  | KV | 110 (43,7%) | **121 (48,8%)** | **231 (46,2%)** |
|  | VERB | 107 (42,5%) | 119 (48,0%) | 226 (45,2%) |
|  | Recursive | 112 (44,4%) | 92 (37,1%) | 204 (40,8%) |
| Gemma 3 4B | HTML | **119 (47,2%)** | **116 (46,8%)** | **235 (47,0%)** |
|  | KV | 78 (31,0%) | 96 (38,7%) | 174 (34,8%) |
|  | VERB | 85 (33,7%) | 80 (32,3%) | 165 (33,0%) |
|  | Recursive | 102 (40,5%) | 81 (32,7%) | 183 (36,6%) |

Kết quả không tạo thành một xu hướng đơn điệu theo quy mô tham số.

- **GPT-OSS 20B:** HTML đạt tổng EM cao nhất với 251/500 câu đúng, cao hơn KV 8 câu và cao hơn VERB 20 câu. So với KV, HTML cao hơn 10 câu tra giá nhưng thấp hơn 2 câu thuộc tính. Recursive cao hơn HTML 3 câu tra giá, nhưng thấp hơn 27 câu thuộc tính và thấp hơn 24 câu tổng thể.
- **Gemma 3 12B:** HTML đạt kết quả cao nhất ở cả tổng thể và thuộc tính. Khoảng cách giữa ba representation table-aware tương đối nhỏ, đặc biệt ở nhóm thuộc tính.
- **Llama 3.1 8B:** KV cao nhất tổng thể. Phần lớn cải thiện so với HTML nằm ở tra giá (`+19`), còn thuộc tính chỉ tăng `+2`.
- **Gemma 3 4B:** HTML vượt KV và VERB ở cả hai nhóm. So với KV, HTML hơn 41 câu tra giá và 20 câu thuộc tính; so với VERB, mức chênh tương ứng là 34 và 36 câu.

Representation table-aware tốt nhất của từng model đều cao hơn baseline recursive về tổng EM:

| Model | Table-aware tốt nhất | Recursive | Chênh lệch |
| --- | ---: | ---: | ---: |
| GPT-OSS 20B | HTML: 251 | 227 | +24 |
| Gemma 3 12B | HTML: 293 | 251 | +42 |
| Llama 3.1 8B | KV: 231 | 204 | +27 |
| Gemma 3 4B | HTML: 235 | 183 | +52 |

Đối với GPT-OSS 20B, kết quả HTML 251/500 và Recursive 227/500 trong bảng này nhất quán với hai nhánh dense ở Bảng X.11. Các chênh lệch giữa HTML, KV và VERB trong mục này được diễn giải theo **giá trị quan sát được**. Chỉ được gọi là khác biệt có ý nghĩa sau khi McNemar ghép cặp và hiệu chỉnh Holm được tính từ raw result theo từng `query_id`.

Kết quả hỗ trợ kết luận:

> Không tồn tại một representation tối ưu chung cho mọi model. Hiệu quả của HTML, key–value và verbalized phụ thuộc vào model family và loại câu hỏi, không chỉ vào số tham số danh nghĩa. Vì vậy, representation generation phải được chọn theo benchmark của model triển khai thay vì suy ra từ kích thước model.


### X.6.10. Khả năng từ chối trên 70 câu không có đáp án

**Bảng X.15. Kết quả từ chối của hai cấu hình hybrid**

| Cấu hình | Tổng | N1 | N3 | N4 |
| --- | ---: | ---: | ---: | ---: |
| T1500 hybrid | 44/70 = 62,9% | 13/30 = 43,3% | 19/20 = 95,0% | 12/20 = 60,0% |
| R1500 hybrid | 47/70 = 67,1% | 11/30 = 36,7% | 16/20 = 80,0% | 20/20 = 100% |

Theo rubric hiện tại, T1500 không từ chối đúng ở 26/70 câu (37,1%), còn R1500 không từ chối đúng ở 23/70 câu (32,9%).

So sánh ghép cặp có:

- T từ chối đúng, R sai: 9 câu;
- T sai, R từ chối đúng: 12 câu;
- McNemar `p=0,6636`.

Không có bằng chứng về khác biệt tổng thể giữa hai pipeline. Kết quả theo nhóm cho thấy chế độ lỗi khác nhau:

- cả hai còn yếu ở N1, tức trường hợp hàng tồn tại nhưng ô cần hỏi bị trống;
- T cao hơn ở N3, tức biến thể gần giống nhưng không tồn tại;
- R cao hơn ở N4, tức kỳ công bố không có trong corpus.

Các khác biệt theo N1/N3/N4 chỉ được dùng để mô tả lỗi, không được xem là kết luận xác nhận riêng vì cỡ mẫu mỗi nhóm nhỏ và chưa hiệu chỉnh một họ kiểm định riêng.

Kết quả trả lời phần an toàn của RQ6:

> Table-aware không cải thiện khả năng từ chối tổng thể. Hai pipeline cần một cơ chế xác minh bằng chứng và kiểm tra điều kiện tồn tại của dữ liệu trước khi xuất giá trị cụ thể.

### X.6.11. Các cấu hình tốt nhất theo phạm vi đánh giá

Các thí nghiệm được thiết kế để cô lập từng thành phần, vì vậy nghiên cứu không ép ba “winner” ở các tầng khác nhau thành một cấu hình toàn cục chưa từng được chạy. Kết quả cuối được báo cáo theo ba phạm vi: representation retrieval, generation khi giữ retrieval cố định, và pipeline end-to-end đã đánh giá đầy đủ.

#### X.6.11.1. Representation retrieval tốt nhất tại endpoint chính

Trong phép so ba representation sử dụng cùng 2.252 logical chunk T1500, HTML đạt Recall@5 cao nhất:

```text
T1500 HTML: 343/500 = 68,6%
T1500 KV:   306/500 = 61,2%
T1500 VERB: 218/500 = 43,6%
```

Vì vậy, **HTML được chọn làm representation mặc định cho embedding/indexing** trong kiến trúc cuối. Kết luận này chỉ áp dụng cho dense retrieval trên benchmark hiện tại; nó không có nghĩa HTML là representation generation tốt nhất cho mọi model.

#### X.6.11.2. Cấu hình generation tốt nhất khi giữ retrieval cố định

Trong benchmark đa model sử dụng cùng evidence T1500 dense, cấu hình đạt EM cao nhất là:

```text
T1500 dense top-5 cố định
+ context HTML
+ google/gemma-3-12b-it
```

Kết quả:

| Chỉ số | Kết quả |
| --- | ---: |
| Exact Match | **293/500 = 58,6%** |
| Tra giá | 159/252 = 63,1% |
| Thuộc tính | **134/248 = 54,0%** |

Con số 293/500 cao hơn một câu so với 292/500 của cấu hình hybrid GPT-OSS, nhưng hai kết quả không phải một phép so end-to-end trực tiếp: benchmark Gemma giữ retrieval dense cố định, còn benchmark GPT-OSS sử dụng hybrid retrieval. Do đó, Gemma 3 12B + HTML được gọi là **cấu hình generation-time tốt nhất quan sát được khi retrieval được giữ cố định**, chưa thay thế cấu hình end-to-end hybrid đã xác nhận.

Nghiên cứu không chạy thêm phép tối ưu chéo để ghép Gemma 12B với mọi retriever. Vì vậy kết quả 293/500 được giữ đúng vai trò của nó: lựa chọn generation tốt nhất trong phép so có evidence cố định, không phải một số end-to-end suy diễn.

#### X.6.11.3. Cấu hình end-to-end hybrid tốt nhất đã được xác nhận

```text
T1500
+ HTML table và lặp header
+ tắt add_table_context
+ dense embedding
+ BM25 Okapi
+ RRF k=60
+ top-5
+ openai/gpt-oss-20b
```

**Bảng X.16. Cấu hình end-to-end hybrid tốt nhất đã được xác nhận**

| Thành phần | Thiết lập |
| --- | --- |
| Biểu diễn lưu trữ và generation | HTML table, lặp header |
| Giới hạn chunk | 1.500 token |
| `add_table_context` | Tắt |
| Embedding | `text-embedding-3-small` |
| Retrieval | Dense + BM25 Okapi, RRF `k=60` |
| Prefetch | 50 mỗi nhánh |
| Top-k | 5 |
| Model sinh | `openai/gpt-oss-20b`, `temperature=0`, `max_tokens=2000` |

| Chỉ số | Kết quả |
| --- | ---: |
| Recall@5 | 410/500 = **82,0%** |
| Exact Match | 292/500 = **58,4%** |
| Tra giá | 196/252 = **77,8%** |
| Thuộc tính | 96/248 = **38,7%** |
| Từ chối đúng | 44/70 = **62,9%** |

Đây là cấu hình end-to-end tốt nhất đã được chạy đầy đủ trong benchmark chính, vì retrieval, context và generation được đánh giá cùng nhau.

Ba kết quả trên không mâu thuẫn nhau. HTML là lựa chọn retrieval rõ nhất; Gemma 3 12B + HTML là lựa chọn generation mạnh nhất trong phép so có evidence cố định; còn T1500 HTML hybrid + GPT-OSS 20B là pipeline end-to-end đã được xác nhận đầy đủ. Nghiên cứu **không chạy thêm phép tối ưu chéo** giữa mọi model × retriever × representation, vì mục tiêu chính là xác định cơ chế và đóng góp của từng tầng thay vì tìm cực đại trên một không gian cấu hình lớn.


---

## X.7. Thảo luận tổng hợp

### X.7.1. Vì sao table-aware tốt hơn ở generation nhưng không thắng retrieval tổng quát?

Bốn tầng kết quả tạo thành một chuỗi logic nhất quán:

1. T1500 giữ header và quan hệ cột tốt hơn R1500;
2. việc lặp header làm index T1500 có nhiều vector gần trùng hơn;
3. R1500 có R@1, R@3 và MRR cao hơn trong dense, và vẫn cao hơn các chỉ số này trong hybrid;
4. tại operating point top-5, T1500 hybrid đạt 410/500 so với 403/500 của R1500, nhưng riêng câu thuộc tính R1500 vẫn có Recall@5 cao hơn (175 so với 172);
5. dù vậy, T1500 có generation và conversion thuộc tính cao hơn rõ rệt.

Do đó, đóng góp chính của table-aware không nằm ở việc làm bảng xếp hạng retrieval tốt hơn ở mọi độ sâu. Lợi ích xuất hiện khi evidence đã vào cửa sổ context và model cần hiểu đúng quan hệ hàng–cột. Câu tra giá ít phụ thuộc cấu trúc cột nên hai nhánh không khác biệt có ý nghĩa thống kê; câu thuộc tính cần ánh xạ giá trị vào đúng cột nên lợi thế của T1500 còn đứng vững sau Holm.

### X.7.2. Vai trò bổ sung của BM25 và table-aware

BM25 làm retrieval tăng mạnh ở cả hai pipeline, đặc biệt ở câu tra giá. Đây là loại truy vấn có nhiều token định danh phù hợp với lexical matching: mã sản phẩm, kích thước, tên riêng và chuỗi số.

Table-aware giải quyết một vấn đề khác: giữ lại ý nghĩa của cột. Vì vậy, hai thành phần có tính bổ sung:

- BM25 cải thiện khả năng đưa mục phù hợp vào top-5;
- table-aware cải thiện khả năng sử dụng quan hệ hàng–cột trong các chunk đã truy hồi.

Interaction retrieval và interaction generation đều chưa có ý nghĩa thống kê. Vì vậy, không nên nói BM25 chỉ hiệu quả khi kết hợp với table-aware. Kết luận phù hợp hơn là BM25 có lợi tổng quát, còn table-aware tạo lợi ích riêng ở nhóm thuộc tính.

### X.7.3. Representation retrieval và generation phải được phân biệt

Thí nghiệm mới làm rõ rằng HTML không chỉ là định dạng lưu trữ thuận tiện. Khi cùng 2.252 logical chunk T1500 được embedding dưới ba representation, Recall@5 lần lượt là 343 với HTML, 306 với KV và 218 với verbalized. Vì vậy, **HTML là representation retrieval tốt nhất quan sát được** trên endpoint chính của benchmark.

Benchmark generation với evidence cố định cho thấy HTML cũng là representation mạnh ở giai đoạn sinh: GPT-OSS 20B, Gemma 3 12B và Gemma 3 4B đạt tổng EM cao nhất với HTML, trong khi Llama 3.1 8B đạt cao nhất với KV. Trường hợp Llama cho thấy representation generation vẫn phụ thuộc model, dù HTML là winner ở ba trong bốn model được đánh giá. Retrieval và generation vì vậy vẫn cần được phân biệt về mục tiêu:

- retrieval cần một chuỗi tạo embedding phân biệt tốt giữa các chunk;
- generation cần một chuỗi mà model cụ thể có thể khai thác chính xác trong context.

Kiến trúc vì vậy giữ **lưới bảng canonical + HTML** làm nguồn sự thật và representation mặc định cho index, đồng thời vẫn cho phép render deterministic sang KV hoặc verbalized khi một model generation đã được benchmark cho thấy có lợi. Không có bằng chứng cho quy luật “model càng nhỏ càng cần KV/VERB”.

### X.7.4. Ý nghĩa đối với triển khai hệ thống

Kết quả cho thấy một pipeline RAG cho bảng giá không nên tối ưu bằng một chỉ số duy nhất.

- Nếu mục tiêu chủ yếu là tìm mã hoặc giá trị số, hybrid retrieval có tác động lớn.
- Nếu mục tiêu là trả lời thuộc tính theo cột, việc bảo toàn cấu trúc có giá trị rõ rệt.
- Nếu tài liệu không chứa đáp án, cả hai pipeline vẫn có tỷ lệ từ chối chưa cao, đặc biệt ở trường hợp ô trống.

Do đó, hệ thống triển khai nên bổ sung một tầng xác minh trước khi trả lời, chẳng hạn kiểm tra giá trị có xuất hiện trong đúng hàng, đúng cột và đúng kỳ dữ liệu hay không. Một tầng dữ liệu có cấu trúc hoặc API xác minh là hướng phù hợp để đánh giá tiếp, nhưng nghiên cứu hiện tại chưa thực hiện benchmark trực tiếp giữa RAG và SQL nên không kết luận kiến trúc nào tốt hơn một cách tổng quát.

### X.7.5. Trả lời các câu hỏi nghiên cứu

| Câu hỏi | Kết luận |
| --- | --- |
| RQ1 | Table-aware giữ nhãn cột và quan hệ hàng–cột tốt hơn; không có lợi thế đáng kể về toàn vẹn dòng so với R1500 sau hiệu chỉnh thiên lệch nhãn. |
| RQ2 | Table-aware có nhiều cặp vector gần trùng hơn recursive; đây là chi phí của việc lặp header. |
| RQ3 | Table-aware không thắng retrieval nhất quán theo R@1/3/5/10 hay MRR. R1500 thường xếp evidence sớm hơn, trong khi T1500 đạt R@5 hybrid cao hơn tại operating point top-5. Trong cùng logical chunks T1500, HTML là representation dense-retrieval tốt nhất tại R@5 (343 > 306 KV > 218 VERB). BM25 cải thiện cả hai pipeline; interaction chưa có ý nghĩa thống kê. |
| RQ4 | Table-aware cải thiện câu thuộc tính trong cả dense và hybrid sau Holm; không có khác biệt có ý nghĩa ở câu tra giá. |
| RQ5 | Conversion thuộc tính của T cao hơn rõ rệt dù recall không cao hơn, phù hợp với giả thuyết T giúp model sử dụng quan hệ hàng–cột trong context hiệu quả hơn. |
| RQ6 | Toàn bộ generation được chạy thống nhất qua OpenRouter; table-aware không cải thiện khả năng từ chối tổng thể trên 70 câu không có đáp án. |
| Phân tích bổ sung | Representation retrieval và generation không đồng nhất: HTML thắng dense retrieval tại R@5, còn generation phụ thuộc model family và nhóm câu hỏi. Không có bằng chứng cho quy luật “model càng nhỏ càng cần KV/VERB”. |

---

## X.8. Hạn chế

Thứ nhất, retrieval hit được xác định bằng `expect_values` và `expect_text`, chưa phải gold row/cell ID độc lập. Recall@1/3/5/10, MRR và conversion vì vậy có thể chịu ảnh hưởng của giá trị lặp hoặc proxy hit/miss. Một benchmark evidence-level cần gán `document_id`, `table_id`, `row_id` và `column_id` cho từng câu.

Thứ hai, nhãn câu hỏi thuộc tính có nguồn gốc từ cùng parser dùng cho table-aware. Kiểm tra thủ công 24/25 câu làm giảm lo ngại về lỗi phổ biến nhưng chưa đủ để loại bỏ hoàn toàn thiên lệch. Một tập gán nhãn độc lập lớn hơn sẽ làm kết luận mạnh hơn.

Thứ ba, toàn bộ generation được chạy qua OpenRouter, nhưng khả năng tái lập tuyệt đối vẫn phụ thuộc vào việc khóa đúng model, prompt, tham số và phiên bản serving tại thời điểm chạy. Raw cache và manifest vì vậy phải được giữ cùng kết quả.

Thứ tư, một tài liệu rất lớn đóng góp tỷ trọng đáng kể trong corpus. Kết quả có thể phản ánh mạnh đặc điểm của bảng dài trong tập dữ liệu này. Đánh giá theo tài liệu hoặc cluster bootstrap theo bảng sẽ giúp kiểm tra khả năng khái quát.

Thứ năm, các cấu hình được lựa chọn và phân tích trên cùng bộ 500 câu, chưa có holdout độc lập. Do đó, các từ “tốt nhất” trong chương luôn được giới hạn thành **tốt nhất quan sát được trên benchmark hiện tại**.

Thứ sáu, conversion chỉ cung cấp bằng chứng gián tiếp về cơ chế. Nghiên cứu không thực hiện thí nghiệm oracle khớp cặp T1500–R1500 hoặc thêm số lượng distractor có kiểm soát, nên không khẳng định khả năng chống nhiễu là nguyên nhân duy nhất.

Thứ bảy, thí nghiệm representation retrieval đã hoàn tất và xác nhận HTML dẫn đầu tại endpoint chính Recall@5. Các artefact thí nghiệm còn chứa Recall@1/3/10, MRR, McNemar, Holm và bootstrap; phần thân luận văn chỉ dùng R@5 làm endpoint xác nhận chính để tránh mở rộng họ kiểm định sau khi quan sát dữ liệu.

Thứ tám, nghiên cứu không chạy toàn bộ tích Descartes giữa mọi retriever, representation và model generation. Đây là lựa chọn phương pháp có chủ đích: các thí nghiệm được tách để cô lập retrieval representation và generation representation. Vì vậy, tài liệu báo cáo các winner theo phạm vi thay vì tuyên bố một “global optimum” chưa được đánh giá trực tiếp.

## X.9. Kết luận chương

Chương này đánh giá pipeline table-aware qua toàn bộ chuỗi từ cấu trúc, embedding, retrieval đến generation, representation theo model và khả năng từ chối. Kết quả cho thấy lợi ích của table-aware không phải một cải thiện đồng đều ở mọi tầng.

Ở tầng cấu trúc, T1500 duy trì header và quan hệ hàng–cột tốt hơn R1500, trong khi toàn vẹn dòng gần như tương đương sau khi hiệu chỉnh thiên lệch nhãn. Ở tầng embedding, T1500 có nhiều cặp vector gần trùng hơn R1500, phản ánh chi phí của việc lặp header.

Hồ sơ retrieval nhiều điểm cắt làm kết luận chặt hơn. Trong dense retrieval, R1500 cao hơn T1500 ở R@1 (45,6% so với 41,4%), R@3 (65,4% so với 61,4%), R@5 (70,8% so với 68,6%) và MRR (0,5659 so với 0,5345); T1500 chỉ vượt nhẹ ở R@10. Trong hybrid, R1500 vẫn cao hơn ở R@1, R@3, R@10 và MRR, nhưng T1500 đạt R@5 cao hơn tại đúng operating point top-5 của hệ thống: 82,0% so với 80,6%. Vì vậy, table-aware không được mô tả là retrieval tốt hơn tổng quát.

Thí nghiệm representation retrieval trên cùng 2.252 logical chunk cho kết quả rõ: HTML đạt Recall@5 343/500 (68,6%), KV 306/500 (61,2%) và verbalized 218/500 (43,6%). Điều này xác nhận HTML là representation dense-retrieval tốt nhất quan sát được tại endpoint chính; tuyến tính hóa sang KV hoặc văn xuôi không làm retrieval tốt hơn.

Lợi ích mạnh nhất của table-aware xuất hiện ở generation thuộc tính. T1500 dense đạt 251/500 so với 227/500 của R1500; T1500 hybrid đạt 292/500 so với 256/500. Sau Holm, khác biệt ở câu thuộc tính vẫn có ý nghĩa trong cả dense (`p_Holm=0,00438`) và hybrid (`p_Holm=0,02487`), còn hai phép so tra giá không có ý nghĩa. Conversion củng cố cách diễn giải này: ở câu thuộc tính, T1500 chuyển proxy retrieval hit thành đáp án đúng khoảng 53%, trong khi R1500 chỉ khoảng 37%–38%, dù R1500 có Recall@5 thuộc tính không thấp hơn.

BM25 cải thiện retrieval và generation của cả hai pipeline, chủ yếu ở câu tra giá. Interaction giữa BM25 và chiến lược chunking chưa đạt ý nghĩa thống kê ở cả retrieval và generation. Vì vậy, BM25 được xem là cải tiến lexical retrieval tổng quát, còn table-aware giữ tín hiệu cấu trúc cho model sinh.

Benchmark đa model tiếp tục cho thấy representation generation không có winner tuyệt đối cho mọi model, dù HTML dẫn đầu ở ba trong bốn trường hợp. Gemma 3 12B + HTML đạt 293/500 khi giữ T1500 dense cố định; GPT-OSS 20B + HTML đạt 251/500; Gemma 3 4B cũng ưu tiên HTML, còn Llama 3.1 8B đạt cao nhất với KV. Kết quả này bác bỏ quy luật đơn giản rằng model nhỏ luôn cần KV hoặc verbalized và đồng thời cho thấy representation retrieval và generation phải được đánh giá riêng.

Trên bộ 70 câu không có đáp án, T1500 hybrid đạt 62,9% từ chối đúng và R1500 hybrid 67,1%; McNemar không cho thấy khác biệt tổng thể (`p=0,6636`). Tối ưu retrieval và EM vì vậy chưa đủ để bảo đảm độ tin cậy khi dữ liệu không tồn tại.

Kết quả cuối được báo cáo theo phạm vi thay vì ép thành một global optimum: **HTML là representation retrieval tốt nhất quan sát được tại Recall@5; Gemma 3 12B + HTML là cấu hình generation tốt nhất khi evidence được giữ cố định; T1500 HTML + dense/BM25 RRF + GPT-OSS 20B là pipeline end-to-end hybrid đã được chạy đầy đủ và đạt Recall@5 82,0%, EM 58,4%**. Nghiên cứu dừng tại đây và không chạy thêm phép tối ưu chéo, vì các bằng chứng hiện tại đã đủ để trả lời câu hỏi nghiên cứu về vai trò của cấu trúc bảng, retrieval lexical và khả năng sử dụng context.

> **Kết luận tổng quát:** Với tài liệu bảng dài qua nhiều trang, table-aware không nhất thiết xếp evidence cao hơn recursive ở mọi độ sâu retrieval. Giá trị chính của nó là bảo toàn nhãn cột để model sử dụng evidence đúng hơn ở câu hỏi thuộc tính. HTML phù hợp nhất cho dense indexing trên benchmark này; BM25 bổ sung khả năng tìm kiếm lexical; còn representation generation phải được lựa chọn theo model cụ thể.

---

## X.10. Từ kết quả thực nghiệm đến quyết định kiến trúc

Sáu câu hỏi nghiên cứu ở đầu chương đều được đặt ở cấp độ cơ chế: cấu trúc, embedding, retrieval, generation, cách model sử dụng context và độ tin cậy khi từ chối. Trả lời xong các câu hỏi đó chưa tự động cho ra một kiến trúc; nó chỉ cho biết **thành phần nào chịu trách nhiệm cho lợi ích nào** và **lợi ích đó có giá gì**. Ba kết luận sau đây là điểm nối trực tiếp sang các quyết định thiết kế ở Chương Y.

Thứ nhất, lợi ích của table-aware không nằm ở việc thắng retrieval nói chung, mà nằm ở đúng nhóm câu hỏi cần ánh xạ giá trị vào cột (RQ1, RQ4) và ở khả năng model khai thác context sau khi bằng chứng đã được truy hồi (RQ5). Ranh giới này — cấu trúc quan trọng cho câu hỏi thuộc tính nhưng không phải cho câu tra giá — là lý do trực tiếp khiến Chương Y tách hệ thống thành hai đường dữ liệu bổ sung cho nhau (table-aware RAG và typed tool + SQL) thay vì dùng một cơ chế RAG duy nhất cho mọi loại câu hỏi.

Thứ hai, thí nghiệm representation ở tầng retrieval (RQ3) tách HTML ra khỏi vai trò "định dạng lưu trữ tiện lợi" và biến nó thành một lựa chọn có bằng chứng định lượng: trên cùng logical chunks, HTML thắng KV và verbalized đúng tại endpoint vận hành Recall@5. Đây là kết quả đủ trực tiếp để đưa thẳng vào kiến trúc làm representation mặc định cho embedding/indexing mà không cần diễn giải thêm.

Thứ ba, benchmark đa model ở tầng generation cho thấy không có representation nào thắng tuyệt đối ở mọi model. Kết quả này không sinh ra một lựa chọn cố định để hard-code vào hệ thống, mà sinh ra một **ràng buộc thiết kế**: representation dùng để model đọc context phải được giữ như một tham số cấu hình theo model, tách rời khỏi representation dùng để lập chỉ mục.

Cả ba điểm trên đều được đo trên cùng một miền dữ liệu — công văn giá vật liệu xây dựng tiếng Việt, một embedding model, và chủ yếu một model sinh cho pipeline end-to-end đã xác nhận đầy đủ. Vì vậy, Chương Y không coi các con số này là hằng số phổ quát; mục Y.7 sẽ trình bày tường minh bảng ánh xạ từ từng quan sát thực nghiệm sang từng quyết định kiến trúc (Y.7.1), đồng thời liệt kê rõ những gì benchmark hiện tại **không** cho phép kết luận (Y.7.2).

---

# CHƯƠNG Y. KIẾN TRÚC HỆ THỐNG HỎI ĐÁP TRÊN TÀI LIỆU BẢNG DÀI CHO DOANH NGHIỆP VẬT LIỆU XÂY DỰNG

> **Ghi chú sử dụng:** thay ký hiệu `Y` bằng số chương thực tế khi đưa vào khóa luận. Tài liệu này mô tả kiến trúc sau khi đối chiếu mã nguồn hiện có với kết quả benchmark cuối. Những thành phần đã có trong hệ thống, cấu hình được benchmark xác nhận và hướng mở rộng được phân biệt rõ để tránh nhầm giữa hiện trạng triển khai và đề xuất nghiên cứu.

---

## Y.1. Bài toán và mục tiêu kiến trúc

### Y.1.1. Bối cảnh nghiệp vụ

Doanh nghiệp vật liệu xây dựng phải khai thác thông tin từ nhiều nguồn không đồng nhất, gồm công văn công bố giá của cơ quan nhà nước, phụ lục báo giá dài nhiều trang, báo giá của nhà cung cấp, tài liệu tiêu chuẩn và tài liệu kỹ thuật. Phần lớn dữ liệu quan trọng không nằm trong văn xuôi liên tục mà nằm trong bảng có các đặc điểm sau:

- một bảng có thể kéo dài hàng chục đến hàng trăm trang;
- header chỉ xuất hiện ở trang đầu hoặc không được lặp ổn định;
- nhiều cột sử dụng ô gộp theo chiều dọc;
- tên sản phẩm, quy cách, nhà sản xuất, đơn vị và giá nằm ở các cột khác nhau;
- một số PDF có lớp văn bản, trong khi một số khác chỉ là ảnh scan;
- cùng một sản phẩm có thể có nhiều mức giá theo kỳ, khu vực, nhà sản xuất hoặc cơ sở giá;
- câu hỏi người dùng thường ngắn, không chuẩn hóa và chứa tên sản phẩm gần giống nhau.

Corpus dùng trong thực nghiệm gồm 11 PDF. Tài liệu lớn nhất chứa một bảng kéo dài khoảng 699 trang liên tục và không lặp header đầy đủ. Đây là trường hợp mà cách xử lý văn bản thông thường dễ làm mất quan hệ hàng–cột.

### Y.1.2. Hai loại yêu cầu không thể xử lý bằng cùng một cơ chế

Hệ thống phải phục vụ ít nhất hai nhóm yêu cầu khác nhau.

| Nhóm yêu cầu | Ví dụ | Yêu cầu độ chính xác | Cơ chế phù hợp |
| --- | --- | --- | --- |
| **Tra cứu số liệu chính xác** | “Giá xi măng PCB40 ở Hà Nội là bao nhiêu?” | Phải đúng sản phẩm, đơn vị, kỳ và giá; không được chọn một số “gần đúng” | Truy vấn dữ liệu có cấu trúc qua tool và SQL |
| **Hiểu cấu trúc và diễn giải** | “Nhà sản xuất của sản phẩm này là ai?”, “Tiêu chuẩn nào áp dụng cho dòng này?” | Phải hiểu giá trị thuộc đúng cột và đúng hàng | Table-aware RAG |
| **Câu hỏi hỗn hợp** | “Giá sản phẩm này bao nhiêu và tiêu chuẩn kỹ thuật là gì?” | Cần cả số chính xác và giải thích từ tài liệu | Kết hợp tool + table-aware RAG |

Một kiến trúc chỉ dùng RAG sẽ không bảo đảm con số được chọn đúng hàng. Ngược lại, một kiến trúc chỉ dùng SQL không xử lý tốt câu hỏi mơ hồ, văn bản điều kiện, ghi chú, tiêu chuẩn và quan hệ ngữ nghĩa trong bảng. Vì vậy, hệ thống được thiết kế theo **hai đường dữ liệu bổ sung cho nhau**.

### Y.1.3. Mục tiêu thiết kế

Kiến trúc hướng tới năm mục tiêu:

1. **Bảo toàn cấu trúc bảng dài:** giữ được header, ô gộp và quan hệ hàng–cột qua nhiều trang.
2. **Tra cứu con số có thể kiểm toán:** giá phải đi từ ô nguồn đến cơ sở dữ liệu và được truy vấn tất định.
3. **Hỗ trợ câu hỏi ngôn ngữ tự nhiên:** người dùng không phải biết tên cột, schema hoặc cú pháp SQL.
4. **Phù hợp hạ tầng doanh nghiệp phổ thông:** ưu tiên CPU, tránh bắt buộc GPU và hạn chế chi phí xử lý toàn bộ PDF bằng OCR thị giác.
5. **Có khả năng giải thích và tái lập:** mỗi câu trả lời phải truy nguyên được về tài liệu, chunk hoặc dòng giá nguồn.

### Y.1.4. Hai nguyên tắc xuyên suốt

Kiến trúc được chi phối bởi hai nguyên tắc:

> **Con số đi đường tất định; phần chữ đi đường truy hồi xấp xỉ.**

- Đơn giá, khối lượng và phép cộng được lấy từ bảng dữ liệu có cấu trúc hoặc hàm tính toán.
- Điều kiện áp dụng, tiêu chuẩn, quy cách, nhà sản xuất và giải thích được lấy qua RAG.

> **Không tìm thấy tốt hơn trả sai.**

Khi không có dòng dữ liệu đáp ứng đầy đủ điều kiện, tool phải trả về trạng thái không tìm thấy. Khi bằng chứng trong RAG không đủ, model phải từ chối hoặc yêu cầu làm rõ thay vì chọn một giá trị gần giống.

---

## Y.2. Kiến trúc tổng thể

### Y.2.1. Sơ đồ khái quát

```text
                                ┌──────────────────────────────┐
                                │       Người dùng / UI        │
                                └──────────────┬───────────────┘
                                               │ câu hỏi tự nhiên
                                               ▼
                                ┌──────────────────────────────┐
                                │   Chat Orchestrator / Agent  │
                                │  history · intent · tool-loop│
                                └───────┬──────────────┬───────┘
                                        │              │
                           câu hỏi cấu trúc/mơ hồ       │ câu hỏi giá/số liệu
                                        │              │
                                        ▼              ▼
                        ┌──────────────────────┐  ┌──────────────────────┐
                        │ TABLE-AWARE RAG      │  │ TYPED TOOL CALLING   │
                        │ T1500 + hybrid       │  │ lookup / calculate   │
                        └──────────┬───────────┘  └──────────┬───────────┘
                                   │                         │
                                   ▼                         ▼
                        ┌──────────────────────┐  ┌──────────────────────┐
                        │ Qdrant: table chunks│  │ PostgreSQL:           │
                        │ HTML + metadata      │  │ material_prices       │
                        └──────────┬───────────┘  └──────────┬───────────┘
                                   │                         │
                                   └───────────┬─────────────┘
                                               ▼
                                ┌──────────────────────────────┐
                                │ LLM tổng hợp + dẫn nguồn     │
                                └──────────────────────────────┘
```

Hai đường trên dùng chung một tầng trích xuất bảng. Do đó, hệ thống không duy trì hai parser độc lập với nguy cơ nhìn thấy hai phiên bản dữ liệu khác nhau. Một lưới bảng canonical được tạo ra trước, sau đó được sử dụng cho hai mục đích:

- tạo chunk HTML cho RAG;
- chuyển từng hàng thành bản ghi có cấu trúc trong `material_prices`.

### Y.2.2. Kiến trúc lúc nạp tài liệu

```text
Upload PDF
   │
   ▼
FastAPI trả 202 + job_id
   │
   ▼
RabbitMQ queue
   │
   ▼
Ingestion worker
   │
   ├─ PyMuPDF: text block + tọa độ nhanh
   ├─ pdfplumber: bảng + đường kẻ + hình học ô
   └─ OCR fallback: chỉ khi PDF không có lớp text
   │
   ▼
Canonical document representation
   │
   ├────────────────────────────────────────────────────────┐
   │                                                        │
   ▼                                                        ▼
NHÁNH A — RAG CẤU TRÚC                           NHÁNH B — DỮ LIỆU GIÁ
HTML table + header                              parse row/column
split theo hàng, cap 1.500                       chuẩn hóa tên, đơn vị, giá
embed + BM25 index                               ghi PostgreSQL
Qdrant                                            material_prices
```

### Y.2.3. Thành phần cốt lõi và thành phần phụ trợ

Luận điểm nghiên cứu tập trung vào đường xử lý tài liệu bảng, RAG cấu trúc và tool giá. Các module như giọng nói, tìm kiếm web, deep research, notes và project vẫn thuộc sản phẩm nhưng không quyết định kết luận của khóa luận.

| Nhóm | Thành phần | Vai trò trong luận văn |
| --- | --- | --- |
| **Cốt lõi** | PyMuPDF, pdfplumber, table resolver | Tạo dữ liệu canonical từ PDF |
| **Cốt lõi** | Table-aware chunking, Qdrant, BM25/RRF | Truy hồi và trả lời câu hỏi cấu trúc |
| **Cốt lõi** | PostgreSQL `material_prices`, tool-calling | Tra giá và dự toán có kiểm soát |
| **Hạ tầng** | FastAPI, RabbitMQ | API và nạp tài liệu bất đồng bộ |
| **Phụ trợ** | Voice, web search, deep research | Tính năng sản phẩm, không tham gia benchmark chính |

---

## Y.3. Tầng nạp và chuẩn hóa tài liệu

### Y.3.1. Upload bất đồng bộ

Một phụ lục hàng trăm trang cần thời gian để phân tích bảng, tạo chunk, embedding và trích dòng giá. Vì vậy request upload không chờ toàn bộ pipeline hoàn thành.

Luồng thực hiện:

1. API nhận tệp và metadata nghiệp vụ.
2. Hệ thống tạo document ở trạng thái `pending`.
3. Job được đưa vào RabbitMQ.
4. Consumer chuyển trạng thái sang `processing` và chạy pipeline.
5. Khi hoàn tất, document chuyển sang `done`; lỗi chuyển sang `error`.

Việc dùng queue giúp giới hạn số job đồng thời, tránh một tệp 699 trang làm treo request HTTP hoặc chiếm toàn bộ tài nguyên của ứng dụng.

Các thành phần chính:

- `app/api/v1/documents.py`;
- `app/queue/publisher.py`;
- `app/queue/consumer.py`;
- `app/core/ingestion/pipeline.py`;
- `app/core/ingestion/price_pipeline.py`.

### Y.3.2. Vì sao dùng cả PyMuPDF và pdfplumber

Hai thư viện giải quyết hai phần khác nhau của bài toán.

| Nhu cầu | PyMuPDF | pdfplumber |
| --- | ---: | ---: |
| Lấy text block và tọa độ nhanh | Tốt | Có nhưng chậm hơn |
| Phát hiện bảng từ đường kẻ | Không phải chức năng chính | Tốt |
| Phân biệt ô rỗng với thân của ô gộp | Không | Có qua hình học `cells` |
| Phù hợp chạy CPU | Có | Có |

PyMuPDF được dùng để đọc text ngoài bảng và giữ thứ tự trang. pdfplumber được dùng để tìm bảng, đường kẻ, bbox, hàng và ô. Cách kết hợp này phù hợp với PDF số hóa có lớp text và tránh phải render toàn bộ tài liệu thành ảnh để OCR.

Đây là một quyết định chi phí–chất lượng có chủ đích. Mục tiêu không phải chọn công cụ nhận dạng thị giác mạnh nhất trong mọi trường hợp, mà xây một pipeline đủ chính xác, chạy được trên hạ tầng doanh nghiệp phổ thông và có fallback cho tài liệu scan.

### Y.3.3. Tách text khỏi vùng bảng

PyMuPDF có thể trả nội dung bên trong bảng dưới dạng text block rời. Nếu các block đó không bị loại khỏi luồng text, cùng một dữ liệu sẽ xuất hiện hai lần:

- một lần trong HTML table;
- một lần trong chunk text bị xáo trộn.

Pipeline vì vậy thực hiện theo thứ tự:

1. pdfplumber tìm bbox của bảng;
2. PyMuPDF lấy text block;
3. block có tâm nằm trong bbox bảng bị loại khỏi luồng text;
4. table block và text block còn lại được sắp theo tọa độ dọc để giữ thứ tự đọc.

Quy tắc này tránh đưa một mức giá của hàng trước vào `context_above` của hàng sau, một lỗi đặc biệt nguy hiểm khi ô giá của hàng sau đang trống.

### Y.3.4. Tạo lưới bảng canonical

Lưới canonical là điểm chung của hai đường RAG và SQL. Nó phải phân biệt được ba trường hợp có hình thức giống nhau trong text thô:

1. ô có giá trị;
2. ô rỗng thật;
3. vị trí nằm trong thân của ô gộp phía trên.

pdfplumber cung cấp tín hiệu hình học:

- bbox tồn tại nhưng text rỗng: ô rỗng thật;
- `cells[c] is None`: vị trí thuộc thân ô gộp hoặc lưới bị khuyết;
- bbox có text: ô có giá trị.

Resolver duy trì giá trị gần nhất theo cột và chỉ kế thừa khi hình học cho thấy đó là thân ô gộp. Với vị trí `None`, pipeline còn kiểm tra lại text trên trang để phân biệt ô gộp thật với trường hợp đường kẻ bị thiếu nhưng chữ vẫn tồn tại. Cách này ngăn việc lấy một giá trị từ hàng trước và gán nhầm cho hàng hiện tại.

Tầng này còn xử lý ký hiệu lặp như `-nt-`, `nt`, `-//-` hoặc “như trên”. Dấu `-` đơn lẻ không được tự động coi là lặp ở mọi cột, vì trong cột ghi chú nó có thể có nghĩa “không áp dụng”.

Mã nguồn trọng tâm:

- `app/core/chunking/table_extract.py`;
- `app/core/chunking/pdf_chunker.py`;
- `app/core/ingestion/price_extractor.py`.

### Y.3.5. Khôi phục header của bảng nối trang

pdfplumber thường xem mỗi trang là một bảng độc lập. Với bảng 699 trang, nếu dòng đầu mỗi trang được coi là header mới, một dòng sản phẩm hoặc một mức giá có thể bị phát thành `<th>`.

Pipeline giữ `prev_header` và số cột của bảng trước. Dòng đầu của bảng mới được xử lý theo thứ tự:

1. nếu trùng header trước, dùng header đó;
2. nếu cùng số cột và dòng đầu có dạng dữ liệu, coi là continuation và mượn header trước;
3. nếu dòng đầu thật sự có dấu hiệu header, tạo header mới;
4. nếu không chắc chắn, không phát `<th>` thay vì gán nhãn sai.

Nguyên tắc là: **thiếu header còn có thể làm giảm chất lượng; header sai có thể làm đổi nghĩa toàn bộ cột**.

### Y.3.6. OCR fallback cho PDF scan

Đường CPU-first chỉ áp dụng tốt khi PDF có lớp text. Nếu toàn tài liệu không sinh được chunk, hệ thống mới kích hoạt OCR fallback:

1. render trang thành ảnh;
2. model thứ nhất xuất HTML table;
3. model thứ hai đọc độc lập để đối chiếu các số;
4. số xuất hiện trong HTML nhưng không được lượt đối chiếu xác nhận sẽ bị làm trống;
5. HTML sau xác minh đi qua cùng pipeline table-aware và price extraction.

OCR là fallback, không phải đường mặc định. Điều này giữ chi phí thấp cho phần lớn tài liệu số hóa nhưng vẫn có đường xử lý cho báo giá scan.

---

## Y.4. Nhánh A — Table-aware RAG cho câu hỏi cấu trúc

### Y.4.1. Representation canonical và retrieval mặc định: HTML

Bảng sau chuẩn hóa được lưu dưới dạng HTML:

```html
<table>
  <tr>
    <th>Tên vật liệu</th>
    <th>Đơn vị</th>
    <th>Nhà sản xuất</th>
    <th>Giá</th>
  </tr>
  <tr>
    <td>Xi măng PCB40</td>
    <td>tấn</td>
    <td>Bút Sơn</td>
    <td>1.520.000</td>
  </tr>
</table>
```

HTML được giữ làm representation canonical vì bảo toàn hàng–cột, phân biệt header với dữ liệu, dễ kiểm toán và có thể render deterministic sang representation khác mà không thay đổi cell value.

Sau benchmark retrieval representation, lựa chọn này còn có bằng chứng định lượng. Khi giữ nguyên 2.252 logical chunk T1500 và chỉ thay chuỗi dùng để embedding:

| Representation | Dense Recall@5 |
| --- | ---: |
| **HTML** | **343/500 = 68,6%** |
| KV | 306/500 = 61,2% |
| VERB | 218/500 = 43,6% |

Vì vậy, **HTML được chọn làm representation mặc định cho embedding/indexing**, không chỉ vì thuận tiện lưu trữ. KV và verbalized vẫn có thể được sinh từ lưới canonical ở tầng generation nếu benchmark của model triển khai cho thấy có lợi. Điều này tách rõ hai khái niệm: representation tốt cho retrieval và representation tốt cho model đọc context.

### Y.4.2. Chunking theo hàng và lặp header

Cấu hình table-aware mục tiêu sau benchmark là **T1500**:

- giới hạn danh nghĩa 1.500 token;
- chỉ cắt tại ranh giới hàng;
- không chia một hàng giữa hai chunk;
- lặp header trong mỗi chunk con;
- header được tính vào ngân sách token;
- lưu metadata nguồn, trang, loại chunk và các trường nghiệp vụ liên quan.

Cấu hình này tạo 2.252 chunk, trung bình 831 token/chunk. T3000 tạo 1.476 chunk, trung bình 1.185 token/chunk và được giữ như điểm tham chiếu, không phải cấu hình triển khai mặc định của nhánh cấu trúc.

### Y.4.3. Chính sách `add_table_context`

Mã nguồn ban đầu có cơ chế gắn text trước và sau bảng vào mọi chunk. Cơ chế này có thể hữu ích ở tài liệu hỗn hợp, nơi đoạn văn giải thích điều kiện của bảng. Tuy nhiên, với corpus phụ lục giá gần như toàn bảng, phần lân cận thường chỉ là header/footer trang hoặc nội dung bảng bị lặp.

Vì vậy:

- với KB báo giá và phụ lục bảng dài: **tắt `add_table_context`**;
- với tài liệu hỗn hợp văn xuôi–bảng: giữ nó như tùy chọn cấu hình, chỉ bật sau khi đo trên dữ liệu tương ứng.

Quyết định này tránh áp dụng một cơ chế chung cho hai loại tài liệu có cấu trúc rất khác nhau.

### Y.4.4. Embedding, retrieval và lưu trữ vector

Chunk HTML được embedding bằng `text-embedding-3-small` và lưu trong Qdrant cùng payload:

```text
document_id
kb_id
filename
page_num
chunk_type
content
metadata: region, price_period, source_type, table_id...
```

Dense retrieval phù hợp để tìm các mô tả gần nghĩa, nhưng benchmark cho thấy nó không đủ mạnh với mã sản phẩm, tên riêng, kích thước và chuỗi số. Vì vậy nhánh RAG cấu trúc kết hợp:

- dense vector search trên **HTML index**;
- BM25 Okapi;
- Reciprocal Rank Fusion với `k=60`;
- prefetch 50 từ mỗi nhánh;
- top-5 làm context generation.

Việc dùng HTML cho dense index được khóa từ thí nghiệm representation: Recall@5 là 68,6% với HTML, 61,2% với KV và 43,6% với verbalized trên cùng logical chunks. Do đó, hệ thống không chuyển toàn bộ corpus sang văn xuôi trước embedding.

Trong code hiện có, Qdrant đã hỗ trợ dense và khai báo sparse vector. Hybrid có thể được triển khai trong Qdrant hoặc tầng ứng dụng; yêu cầu kiến trúc là cùng corpus, cùng identity và một quy tắc fusion xác định để kết quả có thể tái lập.

### Y.4.5. Bằng chứng thực nghiệm cho cấu hình RAG

Các số dưới đây lấy từ lần chạy cuối đã khóa danh tính index bằng `chunk_count`, digest và cache version. Toàn bộ generation được chạy trực tiếp qua OpenRouter, giữ mẫu số đầy đủ 500 câu.

#### a. Bảo toàn cấu trúc

| Cấu hình | Số chunk | Token trung bình | Toàn vẹn dòng | Dòng có nhãn cột |
| --- | ---: | ---: | ---: | ---: |
| T1500 | 2.252 | 831 | 99,5% | 100% |
| T3000 | 1.476 | 1.185 | 99,5% | 100% |
| R1500 | 790 | 1.102 | 99,4% | 65% |

Toàn vẹn dòng của T1500 và R1500 gần như bằng nhau. Lợi thế của table-aware không nằm ở việc giữ tên và giá gần nhau, mà ở khả năng giữ nhãn cột và ánh xạ giá trị vào đúng cột.

#### b. Trade-off trong embedding

| Cấu hình | Median cosine | P90 | Cặp ≥0,90 | Cặp ≥0,95 |
| --- | ---: | ---: | ---: | ---: |
| T1500 | 0,633 | 0,788 | 1,67% | 0,38% |
| T3000 | 0,605 | 0,782 | 2,69% | 0,65% |
| R1500 | 0,611 | 0,731 | 0,59% | 0,20% |

Header lặp giúp model hiểu cột nhưng làm các chunk cùng bảng giống nhau hơn. Kiến trúc vì vậy không giả định bảo toàn cấu trúc sẽ tự động cải thiện dense retrieval.

#### c. Retrieval tại nhiều độ sâu

| Cấu hình | R@1 | R@3 | R@5 | R@10 | MRR | No-hit@10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| T1500 dense | 41,4% | 61,4% | 68,6% | **78,8%** | 0,5345 | 106 |
| R1500 dense | **45,6%** | **65,4%** | **70,8%** | 77,8% | **0,5659** | 111 |
| T1500 hybrid | 54,4% | 74,6% | **82,0%** | 87,0% | 0,6597 | 65 |
| R1500 hybrid | **58,8%** | **76,2%** | 80,6% | **87,6%** | **0,6844** | 62 |

Kết quả này thay đổi cách diễn giải retrieval. R1500 thường đưa evidence lên vị trí sớm hơn, thể hiện qua R@1, R@3 và MRR cao hơn. T1500 không thắng retrieval nói chung; lợi thế của T1500 hybrid xuất hiện tại **R@5 = 82,0%**, đúng operating point top-5 của generation.

Theo nhóm ở R@5:

| Cấu hình | Tra giá | Thuộc tính |
| --- | ---: | ---: |
| T1500 dense | 189/252 = 75,0% | 154/248 = 62,1% |
| R1500 dense | 196/252 = 77,8% | 158/248 = 63,7% |
| T1500 hybrid | **238/252 = 94,4%** | 172/248 = 69,4% |
| R1500 hybrid | 228/252 = 90,5% | **175/248 = 70,6%** |

BM25 tăng recall mạnh ở cả hai pipeline, đặc biệt ở tra giá. Interaction retrieval chưa đạt ý nghĩa thống kê (`p=0,0796`). Do đó, BM25 được xem là cải tiến lexical tổng quát, không phải thành phần chỉ có tác dụng với table-aware.

#### c.1. Representation dùng để lập chỉ mục

Trên cùng 2.252 logical chunk T1500, dense Recall@5 của HTML/KV/VERB lần lượt là `343`, `306`, `218`. Đây là bằng chứng trực tiếp để giữ **HTML làm retrieval representation mặc định**. Việc linearize sang KV hoặc verbalized không được thực hiện trước indexing production, dù các dạng đó vẫn có thể hữu ích cho generation của một số model.

#### d. Generation

Benchmark generation dùng `openai/gpt-oss-20b`, `temperature=0`, `max_tokens=2000`, top-5 và không gọi tool.

| Cấu hình | EM toàn tập | Tra giá | Thuộc tính |
| --- | ---: | ---: | ---: |
| T1500 dense | 251/500 = 50,2% | 159/252 = 63,1% | **92/248 = 37,1%** |
| R1500 dense | 227/500 = 45,4% | 162/252 = 64,3% | 65/248 = 26,2% |
| T1500 hybrid | **292/500 = 58,4%** | **196/252 = 77,8%** | **96/248 = 38,7%** |
| R1500 hybrid | 256/500 = 51,2% | 182/252 = 72,2% | 74/248 = 29,8% |

Sau hiệu chỉnh Holm cho sáu kiểm định:

- dense thuộc tính: `p_Holm=0,00438`;
- hybrid thuộc tính: `p_Holm=0,02487`;
- hybrid tổng thể: `p_Holm=0,01012`;
- dense tổng thể và hai phép so tra giá không còn/không đạt ý nghĩa.

Kết quả này chứng minh giá trị của table-aware ở đúng nhóm câu hỏi cần hiểu cấu trúc. Nó không chứng minh table-aware tốt hơn cho mọi truy vấn.

#### e. Khả năng sử dụng context

| Cấu hình | Conversion toàn tập | Conversion tra giá | Conversion thuộc tính |
| --- | ---: | ---: | ---: |
| T1500 dense | 70,26% | 84,13% | **53,25%** |
| R1500 dense | 62,43% | 82,65% | 37,34% |
| T1500 hybrid | 70,00% | 82,35% | **52,91%** |
| R1500 hybrid | 61,79% | 79,82% | 38,29% |

Ở hybrid retrieval, T1500 có recall thuộc tính thấp hơn R1500 nhưng generation thuộc tính cao hơn. Điều này phù hợp với giả thuyết rằng header và quan hệ hàng–cột giúp model sử dụng context hiệu quả hơn. Đây là bằng chứng gián tiếp, không phải phân rã nhân quả tuyệt đối.

### Y.4.6. Cấu hình RAG và model theo phạm vi bằng chứng

Kiến trúc cuối không ép mọi winner theo tầng thành một “global optimum”. Các thí nghiệm được thiết kế để cô lập từng thành phần và cho ba kết luận khác nhau.

#### Retrieval representation

**T1500 HTML** là lựa chọn index mặc định vì đạt dense Recall@5 `343/500 = 68,6%`, cao hơn KV `306/500` và VERB `218/500` trên cùng logical chunks.

#### Generation khi giữ retrieval cố định

Trong benchmark đa model trên cùng T1500 dense top-5, **Gemma 3 12B + HTML** đạt kết quả cao nhất quan sát được:

- EM: `293/500 = 58,6%`;
- tra giá: `159/252 = 63,1%`;
- thuộc tính: `134/248 = 54,0%`.

Đây là bằng chứng mạnh để ưu tiên Gemma 12B cho câu hỏi cấu trúc khi lựa chọn model theo benchmark generation, nhưng không được ghép với số Recall của một retriever khác để tạo một kết quả end-to-end giả định.

#### Pipeline end-to-end đã được chạy đầy đủ

```text
T1500
+ HTML table và lặp header
+ tắt add_table_context cho corpus bảng giá
+ text-embedding-3-small
+ dense + BM25
+ RRF k=60
+ top-5
+ GPT-OSS 20B
```

Cấu hình này đạt Recall@5 `410/500 = 82,0%` và EM `292/500 = 58,4%`. Đây là pipeline hybrid end-to-end đã được xác nhận đầy đủ trong benchmark chính.

#### Quy tắc lựa chọn triển khai

- Đường **giá chính xác** luôn ưu tiên typed tool + PostgreSQL; RAG không thay đường số liệu tất định.
- Đường **retrieval cấu trúc** dùng T1500 HTML + hybrid vì HTML thắng retrieval representation và hybrid đạt R@5 tốt tại operating point top-5.
- Ở tầng **generation**, Gemma 3 12B + HTML là lựa chọn ưu tiên theo benchmark có evidence cố định; GPT-OSS 20B là model của benchmark end-to-end hybrid đã xác nhận.
- Nghiên cứu không chạy thêm toàn bộ tích model × retriever × representation. Kiến trúc vì vậy giữ model generation là thành phần cấu hình được, còn các kết luận “tốt nhất” luôn ghi rõ phạm vi đo.

## Y.5. Nhánh B — Dữ liệu có cấu trúc và tool cho đường giá

### Y.5.1. Vì sao con số giá không nên lấy trực tiếp từ RAG

Tra giá khác với hỏi một thuộc tính mô tả. Một mức giá chỉ đúng khi đồng thời đúng:

- sản phẩm hoặc mã sản phẩm;
- quy cách;
- đơn vị;
- khu vực;
- kỳ công bố;
- loại nguồn và cơ sở giá.

Tìm kiếm vector tối ưu cho độ gần nghĩa, không phải equality trên các trường nghiệp vụ. Hai sản phẩm chỉ khác `PCB30/PCB40`, `D12/D14` hoặc tên nhà sản xuất có thể có embedding rất gần nhưng giá khác đáng kể. Ngoài ra, RAG không thực hiện tự nhiên các phép `MIN`, `MAX`, `COUNT`, lọc kỳ hoặc tổng hợp theo đơn vị.

Vì vậy, giá được trích thành dữ liệu có cấu trúc và truy vấn qua tool. RAG chỉ cung cấp phần giải thích và dẫn nguồn bổ sung.

### Y.5.2. Trích dòng giá từ lưới canonical

`price_pipeline.py` chạy song song hai nhánh trên cùng tài liệu:

1. chunk và embedding cho RAG;
2. `extract_price_rows()` để tạo các bản ghi `MaterialPriceRow`.

Extractor thực hiện:

- phát hiện header có thể trải nhiều dòng;
- nhận diện cột tên, đơn vị, giá, tiêu chuẩn và nhà sản xuất;
- bỏ hàng chú thích số cột;
- nhận diện group header;
- resolve ký hiệu lặp;
- chuẩn hóa số theo quy ước Việt Nam;
- tạo nhiều row nếu một dòng có nhiều cột giá;
- bỏ dòng không đọc được giá thay vì suy đoán.

Bảng `material_prices` lưu tối thiểu:

```text
region
material_category
material_name
spec
unit
price_ex_vat
price_basis
source_type
price_period
manufacturer
raw_row_text
document_id
```

`raw_row_text` và `document_id` cho phép đối chiếu ngược về nguồn.

### Y.5.3. Khớp tên vật liệu

Một `ILIKE '%cả cụm%'` không phù hợp với câu hỏi tự nhiên vì tên trong cơ sở dữ liệu có thể chứa thêm từ hoặc khác thứ tự. Hệ thống dùng chiến lược:

1. chuẩn hóa và bỏ dấu;
2. tách thành các token có ý nghĩa;
3. yêu cầu ứng viên chứa đồng thời các token chính;
4. không bỏ token chứa chữ số vì đó thường là mã hoặc kích thước;
5. không nới lỏng xuống dưới hai token;
6. dùng `pg_trgm` để xếp hạng trong tập ứng viên đã qua bộ lọc cứng.

### Y.5.4. Typed tool-calling

Tool chính cho tra giá là:

```text
lookup_material_price(region, material_name?, material_category?)
```

Luồng thực hiện:

```text
Câu hỏi người dùng
   │
   ▼
LLM nhận schema tool
   │
   ├─ không cần số chính xác → trả lời từ RAG
   │
   └─ cần giá → phát tool call
              │
              ▼
       Handler chuẩn hóa tham số
              │
              ▼
       SQL trên material_prices
              │
              ├─ có dòng phù hợp → trả bảng kết quả + nguồn
              └─ không có → “Không tìm thấy; không suy đoán giá”
              │
              ▼
       LLM diễn đạt lại, không tự tạo con số
```

Tool-calling được chọn thay vì Text-to-SQL ở giai đoạn hiện tại vì:

- không gian truy vấn còn nhỏ và có thể mô tả bằng schema kiểu;
- dễ kiểm thử với tham số cố định;
- dễ kiểm soát quyền truy cập;
- không cho model truy cập các bảng người dùng, message hoặc token;
- xử lý đúng nút thắt entity matching;
- hành vi không tìm thấy có thể định nghĩa rõ.

Text-to-SQL trở nên phù hợp hơn khi schema mở rộng nhiều bảng, nhiều kỳ giá và các câu hỏi tổng hợp không thể liệt kê trước. Hiện tại, typed tool an toàn và dễ tái lập hơn.

### Y.5.5. Tool dự toán

Hệ thống còn có hai tool liên quan:

- `estimate_material_quantity`: tính khối lượng từ công thức hình học, không truy vấn DB;
- `calculate_construction_cost`: tính khối lượng tham khảo, gọi tra giá nhiều lần và tổng hợp chi phí.

Đối với dự toán, LLM không được tự tính hoặc sửa số. Công thức và phép nhân được thực hiện trong code; model chỉ trình bày kết quả và nêu giới hạn của ước lượng.

### Y.5.6. Kiểm tra tồn tại và từ chối

Benchmark 70 câu không có đáp án cho kết quả:

| Cấu hình | Từ chối đúng |
| --- | ---: |
| T1500 hybrid | 44/70 = 62,9% |
| R1500 hybrid | 47/70 = 67,1% |

McNemar cho `p=0,6636`, tức chưa có bằng chứng hai pipeline khác nhau về khả năng từ chối tổng thể. Kết quả cho thấy chunking và retrieval không thay thế được validation nghiệp vụ.

Vì vậy, trước khi phát một con số, đường giá phải kiểm tra:

- sản phẩm/mã có thực sự khớp;
- đơn vị phù hợp;
- kỳ dữ liệu tồn tại;
- trường được hỏi không rỗng;
- dòng có nguồn và document hợp lệ.

Nếu một điều kiện không đạt, hệ thống phải từ chối hoặc yêu cầu người dùng làm rõ.

---

## Y.6. Điều phối câu hỏi tại thời điểm truy vấn

### Y.6.1. Chính sách theo loại câu hỏi

| Loại câu hỏi | Đường chính | Đường bổ sung | Ví dụ |
| --- | --- | --- | --- |
| Tra một mức giá cụ thể | Tool → SQL | RAG cung cấp điều kiện và nguồn | “Giá xi măng PCB40 ở Hà Nội?” |
| Hỏi thuộc tính cột | Table-aware RAG | Không bắt buộc tool | “Nhà sản xuất của dòng này là ai?” |
| Hỏi tiêu chuẩn/ghi chú | Table-aware RAG | Có thể lọc metadata | “Tiêu chuẩn RoHS áp dụng cho sản phẩm nào?” |
| Hỏi hỗn hợp | Tool + RAG | LLM tổng hợp | “Giá và tiêu chuẩn của sản phẩm X?” |
| Dự toán | Tool công thức + tool giá | RAG giải thích giả định | “Xây 100 m² cần bao nhiêu vật liệu và chi phí?” |
| Không đủ điều kiện | Từ chối/clarify | Không dùng giá gần nhất | “Giá xi măng?” khi thiếu sản phẩm/khu vực cần thiết |

### Y.6.2. Luồng câu hỏi giá

```text
User: “Giá xi măng Bút Sơn PCB40 ở Hà Nội?”
   │
   ▼
Chat/Agent nhận câu hỏi + history
   │
   ▼
RAG có thể lấy điều kiện công bố, VAT, ghi chú
   │
   ▼
LLM gọi lookup_material_price
   │
   ▼
PostgreSQL lọc tên + region + kỳ + đơn vị
   │
   ▼
Tool trả dòng thật hoặc không tìm thấy
   │
   ▼
LLM diễn đạt + dẫn nguồn
```

Con số không được lấy từ top-5 chunk. Top-5 chỉ hỗ trợ bối cảnh và giải thích.

### Y.6.3. Luồng câu hỏi cấu trúc

```text
User: “Nhà sản xuất của sản phẩm X là ai?”
   │
   ▼
Query embedding + BM25
   │
   ▼
RRF hợp nhất → top-5 T1500
   │
   ▼
Context HTML có header lặp
   │
   ▼
LLM ánh xạ giá trị vào cột Nhà sản xuất
   │
   ▼
Trả lời + citation trang/tài liệu
```

Luồng này là nơi benchmark cho thấy table-aware có ưu thế rõ so với recursive.

### Y.6.4. Luồng câu hỏi hỗn hợp

Ví dụ: “Giá xi măng PCB40 và tiêu chuẩn áp dụng là gì?”

- tool trả giá, đơn vị, kỳ và nguồn từ `material_prices`;
- RAG trả tiêu chuẩn hoặc điều kiện từ chunk HTML;
- LLM hợp nhất hai nguồn nhưng không được sửa giá tool trả về.

Đây là lợi ích của kiến trúc hai đường: mỗi thành phần xử lý loại thông tin phù hợp nhất với bản chất của nó.

### Y.6.5. Câu hỏi nối tiếp và metadata

Chat orchestration sử dụng history để viết lại câu hỏi nối tiếp thành câu độc lập. Metadata như `region`, `price_period`, `source_type`, `document_id` được giữ trong cả Qdrant payload và PostgreSQL, giúp:

- lọc phạm vi trước retrieval;
- truy vấn đúng kỳ và nguồn;
- tạo citation;
- ngăn dữ liệu của tài liệu khác bị sử dụng ngoài ý muốn.

---

## Y.7. Từ benchmark đến quyết định kiến trúc

### Y.7.1. Bảng ánh xạ bằng chứng → quyết định

| Quan sát thực nghiệm | Kết luận | Quyết định kiến trúc |
| --- | --- | --- |
| T1500 và R1500 gần như ngang về toàn vẹn dòng | Giữ tên và giá gần nhau chưa đủ để gọi là hiểu bảng | Không dùng “row integrity” làm luận điểm chính |
| T1500 giữ header 100%, R1500 khoảng 65% | Nhãn cột là tín hiệu cấu trúc quan trọng | Dùng table-aware chunks và lặp header cho nhánh cấu trúc |
| T1500 có nhiều vector gần trùng hơn R1500 | Bảo toàn cấu trúc có chi phí embedding | Không kỳ vọng dense tự tốt hơn |
| R1500 cao hơn ở R@1/R@3/MRR; T1500 hybrid chỉ cao hơn ở R@5 | Không có winner retrieval tại mọi độ sâu | Chọn top-k theo operating point thực tế và báo cáo nhiều `k` |
| HTML/KV/VERB dense R@5 = 343/306/218 | HTML là retrieval representation tốt nhất quan sát được | Dùng HTML cho embedding/indexing |
| BM25 tăng Recall@5 mạnh, nhất là tra giá | Lexical matching hữu ích cho tên/mã/số | Dùng dense + BM25 + RRF |
| Thuộc tính của T tốt hơn có ý nghĩa sau Holm | Table-aware giúp model hiểu đúng cột | Chọn T1500 cho câu hỏi cấu trúc |
| Tra giá T/R không khác biệt có ý nghĩa | Chunking không phải lời giải chính cho số giá | Đưa giá qua tool + SQL |
| Conversion thuộc tính T ≈53%, R ≈37–38% | Lợi ích chủ yếu nằm sau retrieval | Giữ representation có cấu trúc trong context generation |
| Benchmark generation đa model không có winner representation chung | Model family ảnh hưởng cách đọc context | Generation representation là cấu hình theo model |
| Gemma 12B + HTML đạt 293/500 với evidence cố định | Gemma 12B mạnh nhất trong phép so generation kiểm soát | Ưu tiên khi chọn model cho đường cấu trúc, nhưng không ghép số từ retriever khác |
| Từ chối tổng thể chưa cao và không khác biệt | RAG không tự bảo đảm an toàn | Validation và fail-closed ở tool |

### Y.7.2. Quyết định không được rút ra từ benchmark

Benchmark không cho phép khẳng định:

- table-aware tốt hơn cho mọi loại PDF;
- HTML là representation generation tốt nhất cho mọi model;
- BM25 chỉ có tác dụng khi kết hợp table-aware;
- RAG có thể thay thế cơ sở dữ liệu giá;
- typed tool luôn tốt hơn Text-to-SQL khi schema mở rộng;
- cấu hình T1500 là tối ưu ngoài miền báo giá VLXD.

Việc phân biệt rõ phạm vi kết luận giúp kiến trúc tránh bị “tối ưu theo benchmark” quá mức.

---

## Y.8. Quyết định công nghệ và trade-off triển khai

### Y.8.1. CPU-first thay vì OCR toàn bộ

Đối với PDF có lớp text, PyMuPDF + pdfplumber:

- chạy được trên CPU;
- không cần model thị giác cho mọi trang;
- giữ được tọa độ và hình học ô;
- giảm chi phí và thời gian nạp;
- dễ truy nguyên lỗi.

Các model OCR/layout mạnh hơn có thể cải thiện tài liệu scan hoặc bảng rất phức tạp, nhưng làm tăng kích thước image, bộ nhớ, latency và chi phí vận hành. Vì vậy, OCR được dùng theo fallback thay vì mặc định.

### Y.8.2. Vì sao cần cả PostgreSQL và Qdrant

Hai kho không trùng chức năng.

| Kho | Dữ liệu | Phép truy vấn | Mức chính xác mong muốn |
| --- | --- | --- | --- |
| PostgreSQL | dòng giá chuẩn hóa | lọc, sort, aggregate, equality/ILIKE | Tất định |
| Qdrant | chunk văn bản và bảng | semantic search + metadata filter | Xấp xỉ |

Việc ghi cùng tài liệu vào hai kho là deliberate dual representation:

- PostgreSQL là “sự thật về số”;
- Qdrant là “bộ nhớ ngữ nghĩa và dẫn chứng”.

### Y.8.3. Vì sao dùng RabbitMQ

Nạp tài liệu dài là tác vụ nhiều bước và có thể kéo dài. Queue cung cấp:

- phản hồi API nhanh;
- retry khi worker lỗi;
- giới hạn concurrency;
- theo dõi trạng thái;
- tách vòng đời request khỏi vòng đời ingestion.

### Y.8.4. Vai trò của model

Không dùng một model cho mọi việc:

- embedding model tạo vector;
- chat model đọc context và gọi tool;
- classifier nhỏ xử lý guard, follow-up và disambiguation;
- vision model chỉ xử lý OCR fallback;
- công thức và SQL vẫn chạy bằng code.

Benchmark đa model cho thấy `google/gemma-3-12b-it` với HTML đạt EM và độ chính xác thuộc tính cao nhất khi retrieval được giữ cố định (`293/500`, thuộc tính `134/248`). Vì vậy Gemma 12B là lựa chọn generation ưu tiên cho đường cấu trúc theo phép đo kiểm soát. Benchmark end-to-end hybrid hiện có dùng `gpt-oss-20b` và đạt `292/500` với T1500 HTML + dense/BM25.

Hai kết quả được giữ riêng thay vì ghép thành một số end-to-end chưa đo. Về kiến trúc, model generation là thành phần có thể thay cấu hình; **retrieval representation đã ổn định hơn** vì HTML thắng KV và verbalized tại Recall@5 trên cùng logical chunks.

### Y.8.5. Thành phần không tham gia luận điểm nghiên cứu

Voice, TTS, web search và deep research là chức năng sản phẩm. Chúng không ảnh hưởng trực tiếp tới kết quả table-aware RAG và được mô tả ngắn ở phụ lục thay vì chen vào luồng kiến trúc chính.

---

## Y.9. Độ tin cậy, khả năng tái lập và vận hành

### Y.9.1. Danh tính cấu hình và cache

Trong quá trình benchmark, alias cấu hình mơ hồ từng làm kết quả T3000 bị gắn nhãn T1500. Hệ thống đánh giá sau đó bổ sung:

- tên cấu hình tường minh `T1500`, `T3000`, `R1500`;
- manifest chứa chunk count và digest;
- cache vector chỉ được dùng khi digest khớp;
- raw answer và summary lưu ở hai đường dẫn khác nhau;
- mỗi record generation gắn `query_id`, chunk IDs, prompt hash, model và finish reason.

Những hàng rào này là một phần của kiến trúc đo lường, không chỉ là chi tiết triển khai benchmark.

### Y.9.2. Tính nhất quán endpoint

Toàn bộ benchmark generation sử dụng OpenRouter với cùng model, prompt và tham số cho các cấu hình được so sánh. Kết quả từ endpoint khác không được dùng để thay thế.

Để tái lập, mỗi raw result cần giữ `query_id`, model, prompt hash, cấu hình retrieval, danh sách chunk, `finish_reason`, token usage và thời điểm chạy cùng manifest tương ứng.

### Y.9.3. Citation và provenance

Mỗi chunk cần giữ:

```text
document_id
filename
page_num
chunk_id
table_id nếu có
region / price_period / source_type
```

Mỗi dòng giá cần giữ `document_id` và `raw_row_text`. Nhờ đó:

- câu trả lời RAG dẫn về trang và tài liệu;
- câu trả lời tool dẫn về dòng giá và nguồn;
- lỗi extraction có thể truy vết;
- xóa tài liệu có thể dọn dữ liệu liên quan.

### Y.9.4. Quan sát và dọn dữ liệu

Hệ thống cần theo dõi:

- thời gian ingestion;
- số chunk;
- số dòng giá;
- số warning extraction;
- token và chi phí LLM;
- latency retrieval và generation;
- tỷ lệ tool không tìm thấy;
- tỷ lệ từ chối.

PostgreSQL và Qdrant không chia sẻ transaction. Khi xóa KB hoặc document, cần dọn cả bản ghi quan hệ lẫn vector. Việc chỉ cascade trong PostgreSQL có thể để lại vector mồ côi và làm dữ liệu cũ tiếp tục xuất hiện trong retrieval.

### Y.9.5. Bảo mật tool

Typed tools giới hạn bề mặt truy cập của LLM. Model không được nhận connection string hoặc quyền chạy SQL tự do. Handler chỉ thực hiện các truy vấn đã định nghĩa trên bảng cần thiết, có giới hạn kết quả và quy tắc không suy đoán.

---

## Y.10. Hạn chế và hướng phát triển

### Y.10.1. Giới hạn của nghiên cứu hiện tại

1. Corpus chỉ thuộc miền báo giá vật liệu xây dựng tiếng Việt.
2. Một tài liệu bảng rất dài chi phối nhiều chunk.
3. Retrieval hit dùng `expect_values`/`expect_text`, chưa phải gold row/cell ID độc lập.
4. Nhãn thuộc tính có nguồn gốc từ cùng parser; kiểm tra thủ công 24/25 câu chỉ là sanity check.
5. Các winner được chọn trên cùng benchmark, chưa có holdout độc lập.
6. Kết quả generation phụ thuộc model và phiên bản serving qua OpenRouter; việc tái lập cần khóa model, prompt, tham số và manifest của lần chạy.
7. PDF scan và bảng không có lớp text chỉ được đánh giá hạn chế qua fallback.
8. Khả năng từ chối còn thấp, đặc biệt khi trường nguồn bị trống hoặc yêu cầu vượt ngoài dữ liệu.
9. Nghiên cứu không chạy toàn bộ tổ hợp model × retriever × representation. Các kết luận được phân rã theo tầng để ưu tiên khả năng giải thích thay vì tìm cực đại trên một không gian cấu hình lớn.

### Y.10.2. Representation theo tầng và theo model

Hai benchmark representation đưa ra hai kết luận bổ sung.

**Ở tầng retrieval**, khi cùng logical chunks T1500 được embedding dưới ba định dạng:

| Representation | Dense Recall@5 |
| --- | ---: |
| **HTML** | **343/500 = 68,6%** |
| KV | 306/500 = 61,2% |
| VERB | 218/500 = 43,6% |

Do đó HTML được giữ làm index mặc định.

**Ở tầng generation**, khi evidence được giữ cố định:

| Model | HTML | KV | VERB | Recursive |
| --- | ---: | ---: | ---: | ---: |
| GPT-OSS 20B | **251** | 243 | 231 | 227 |
| Gemma 3 12B | **293** | 285 | 288 | 251 |
| Llama 3.1 8B | 210 | **231** | 226 | 204 |
| Gemma 3 4B | **235** | 174 | 165 | 183 |

Kết quả không hỗ trợ quy luật “model càng nhỏ càng cần KV hoặc verbalized”. Vì vậy kiến trúc tách ba lớp:

1. **canonical data:** lưới hàng–cột và HTML có thể kiểm toán;
2. **retrieval representation:** HTML mặc định theo benchmark dense;
3. **generation representation:** có thể render HTML/KV/VERB theo model; HTML là mặc định hợp lý vì dẫn đầu ở GPT-OSS 20B và hai model Gemma, còn KV được giữ như tùy chọn cho Llama 3.1 8B.

Tách lớp này giúp hệ thống không phải re-parse PDF khi đổi model. Việc chuyển representation chỉ diễn ra từ cùng dữ liệu canonical và phải bảo toàn header, thứ tự cột, ô rỗng và cell value.

### Y.10.3. Gold evidence và benchmark liên tài liệu

Nên bổ sung cho mỗi câu:

```text
document_id
table_id
row_id
column_id
cell_value
```

Điều này cho phép đo evidence Recall thay vì answer-containing proxy và giúp kiểm tra chính xác retrieval có lấy đúng hàng hay chỉ lấy một giá trị trùng ở nơi khác.

### Y.10.4. Khi nào mở rộng sang Text-to-SQL

Text-to-SQL trở nên đáng cân nhắc khi:

- có nhiều bảng liên kết;
- có lịch sử giá qua nhiều kỳ;
- cần truy vấn tổng hợp động;
- cần so sánh nhà sản xuất, khu vực và xu hướng theo thời gian;
- typed schema không còn bao phủ được không gian câu hỏi.

Khi đó cần database read-only riêng, whitelist bảng/cột, statement timeout và validation SQL trước khi chạy.

### Y.10.5. Fallback parser nặng hơn

Kiến trúc có thể dùng mô hình document understanding như một fallback theo chất lượng:

```text
pdfplumber mặc định
   │
   ├─ pass quality checks → dùng kết quả CPU-first
   └─ fail quality checks → OCR/layout model
```

Cách phân tầng giữ chi phí thấp trên đa số tài liệu nhưng vẫn xử lý được trường hợp scan hoặc layout phức tạp.

---

## Y.11. Kết luận kiến trúc

Kiến trúc cuối không chọn giữa RAG và SQL theo kiểu loại trừ. Nó tách bài toán theo bản chất thông tin:

- **table-aware RAG** xử lý câu hỏi mơ hồ, quan hệ hàng–cột, tiêu chuẩn, nhà sản xuất, quy cách và điều kiện áp dụng;
- **typed tool + SQL** xử lý đơn giá, khối lượng và phép tính cần độ chính xác tất định;
- **agentic orchestration** kết hợp hai đường trong câu hỏi hỗn hợp;
- **một tầng trích xuất canonical dùng chung** bảo đảm RAG và SQL không nhìn thấy hai phiên bản bảng khác nhau.

Bằng chứng retrieval mới làm quyết định kỹ thuật chính xác hơn. T1500 không thắng R1500 ở mọi độ sâu: R1500 có R@1, R@3 và MRR cao hơn, còn T1500 hybrid đạt Recall@5 cao hơn tại operating point top-5 (`82,0%` so với `80,6%`). Vì vậy hệ thống không dựa vào tuyên bố “table-aware truy hồi tốt hơn”, mà dựa vào hai lợi ích riêng: BM25 giúp lexical retrieval và table-aware giúp model hiểu cấu trúc sau retrieval.

Representation cho index đã được xác nhận trực tiếp. Trên cùng 2.252 logical chunks, HTML đạt dense Recall@5 `343/500`, KV `306/500` và verbalized `218/500`; do đó HTML là representation mặc định cho embedding/indexing. Ở generation, HTML đạt tổng EM cao nhất với GPT-OSS 20B (`251/500`), Gemma 3 12B (`293/500`) và Gemma 3 4B (`235/500`), trong khi Llama 3.1 8B đạt cao nhất với KV (`231/500`). Vì vậy HTML là mặc định hợp lý, nhưng representation generation vẫn được giữ như một cấu hình phụ thuộc model.

Bởi vậy, kiến trúc cuối có thể tóm tắt như sau:

> Với tài liệu báo giá vật liệu xây dựng có nhiều bảng kéo dài qua nhiều trang, hệ thống nên khôi phục một lưới bảng canonical bằng pipeline CPU-first, chia thành T1500 có lặp header, dùng HTML để embedding/indexing và kết hợp dense với BM25 ở top-5. Câu hỏi thuộc tính được trả lời bằng table-aware RAG với model/representation đã benchmark; câu hỏi giá đi qua typed tool truy vấn `material_prices`; câu hỏi hỗn hợp dùng cả hai. HTML được chọn cho retrieval bằng số liệu, còn model generation được giữ như thành phần cấu hình vì không có một representation tối ưu cho mọi model.

Nghiên cứu không tiếp tục tối ưu chéo mọi model × retriever × representation. Thay vào đó, nó dừng ở các kết luận đã được đo riêng cho từng tầng, giúp kiến trúc dễ giải thích, tái lập và phù hợp hơn với yêu cầu kiểm toán của hệ thống doanh nghiệp.

# PHỤ LỤC A. BẢN ĐỒ CÔNG NGHỆ RÚT GỌN

| Thành phần | Công nghệ | Vai trò |
| --- | --- | --- |
| API và streaming | FastAPI, Uvicorn, SSE | Upload, chat, stream token |
| Queue | RabbitMQ | Nạp tài liệu bất đồng bộ |
| CSDL quan hệ | PostgreSQL, SQLAlchemy async | User, KB, document, material_prices, message, usage |
| Vector store | Qdrant | Dense vector, metadata filter, nền tảng sparse/hybrid |
| PDF text | PyMuPDF | Text block và tọa độ nhanh |
| PDF table | pdfplumber | Bảng, bbox, đường kẻ và hình học ô |
| Embedding | `text-embedding-3-small` | Vector hóa chunk và query |
| Chat/agent | OpenRouter-compatible LLM | Đọc context, tool calling, tổng hợp |
| OCR fallback | Vision models | Scan PDF thành HTML và đối chiếu số |
| Quan sát | Prometheus, usage records | Latency, token, ingestion và chi phí |

# PHỤ LỤC B. BẢN ĐỒ MÃ NGUỒN CỐT LÕI

| Chức năng | File/thư mục chính |
| --- | --- |
| API upload | `app/api/v1/documents.py` |
| Queue | `app/queue/publisher.py`, `app/queue/consumer.py` |
| Chunk model và utility | `app/core/chunking/models.py`, `base.py` |
| PDF chunking | `app/core/chunking/pdf_chunker.py` |
| Table canonicalization | `app/core/chunking/table_extract.py` |
| OCR fallback | `app/core/ingestion/ocr_fallback.py` |
| Standard ingestion | `app/core/ingestion/pipeline.py` |
| Price ingestion | `app/core/ingestion/price_pipeline.py` |
| Price extraction | `app/core/ingestion/price_extractor.py` |
| Qdrant | `app/db/qdrant/client.py` |
| Retriever | `app/core/retrieval/retriever.py` |
| Chat orchestration | `app/api/v1/chat.py` |
| Tool loop | `app/core/llm/tool_loop.py` |
| Price lookup tool | `app/core/mcp/tools/price_lookup_tool.py` |
| Quantity tool | `app/core/mcp/tools/quantity_tool.py` |
| Cost tool | `app/core/mcp/tools/cost_tool.py` |
| PostgreSQL models | `app/db/postgres/models.py` |

# PHỤ LỤC C. CÁC MODULE SẢN PHẨM NGOÀI PHẠM VI LUẬN ĐIỂM CHÍNH

- Voice STT/TTS;
- Web search và deep research;
- Notes và projects;
- OAuth và quản trị user;
- danh sách endpoint đầy đủ;
- các công thức dự toán chi tiết theo loại công trình.

Các module này vẫn thuộc hệ thống triển khai, nhưng không cần trình bày sâu trong chương kiến trúc nghiên cứu. Chúng có thể được mô tả ở tài liệu kỹ thuật sản phẩm hoặc phụ lục riêng.
