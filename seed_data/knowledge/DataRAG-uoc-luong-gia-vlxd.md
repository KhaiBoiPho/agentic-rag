---
title: "Ước lượng khối lượng và giá vật liệu xây dựng cho công trình - Data RAG"
language: "vi"
scope: "công trình dân dụng, công nghiệp quy mô thông dụng, hạ tầng kỹ thuật và giao thông ở mức nguyên tắc"
price_regions: ["Hà Nội", "Đà Nẵng", "TP. Hồ Chí Minh"]
price_source_type: "official-price-announcement-dispatch-with-pdf-annex"
price_source_format: "PDF; có thể gồm lớp văn bản, bản quét hoặc tài liệu lai"
primary_use: ["RAG", "bóc tách khối lượng", "lập ngân sách vật liệu", "kiểm tra dự toán", "so sánh phương án"]
---

# Ước lượng khối lượng và giá vật liệu xây dựng cho công trình

## Lời mở đầu

Tài liệu này là corpus kiến thức chuyên sâu phục vụ hệ thống RAG về cách ước lượng khối lượng và chi phí vật liệu xây dựng. Mục tiêu là giúp hệ thống không chỉ trả lời “một mét vuông nhà hết bao nhiêu tiền”, mà phải phân tích được công trình cần những vật liệu nào, số lượng được xác định từ đâu, đơn giá nào được phép dùng, giá đã bao gồm vận chuyển hay chưa, có bị cộng trùng hao hụt hay không và mức độ tin cậy của kết quả phụ thuộc vào giai đoạn thiết kế như thế nào.

Tài liệu được xây dựng để ghép với ba bộ PDF công văn công bố giá vật liệu xây dựng kèm phụ lục của Hà Nội, Đà Nẵng và Thành phố Hồ Chí Minh. Mỗi bộ nguồn phải được hiểu là một hồ sơ gồm phần công văn chứa metadata pháp lý, phạm vi và điều kiện áp dụng; cùng một hoặc nhiều phụ lục chứa các bảng đơn giá chi tiết. Các phụ lục là lớp dữ liệu đơn giá, còn phần công văn là lớp ngữ cảnh bắt buộc để diễn giải đúng đơn giá. Tài liệu này là lớp tri thức hướng dẫn trích xuất, chuẩn hóa, lựa chọn và sử dụng các dữ liệu đó. Giá vật liệu thay đổi theo kỳ công bố, quy cách, nguồn cung, điều kiện giao hàng và địa điểm công trình, vì vậy corpus không đóng cứng một bộ giá cụ thể.

Kết quả ước lượng trong tài liệu không thay thế dự toán được lập từ hồ sơ thiết kế đã phê duyệt, định mức hiện hành, báo giá hợp lệ, hợp đồng mua bán, chứng từ vận chuyển hoặc quyết định của người có thẩm quyền. Khi dùng cho dự án vốn nhà nước, hồ sơ thanh quyết toán, đấu thầu hoặc tranh chấp hợp đồng, phải áp dụng đúng hệ thống pháp luật và tài liệu chính thức tại thời điểm thực hiện.

<!-- chunk_id: rag-estimating-core-principle -->

## Nguyên tắc trung tâm

Chi phí vật liệu không được tính bằng cách lấy diện tích sàn nhân với một đơn giá vật liệu chung. Cách tính có kiểm soát phải đi qua chuỗi dữ liệu sau:

**Hồ sơ thiết kế hoặc giả định thiết kế → khối lượng công tác → hao phí vật liệu cho công tác → lượng vật liệu cần mua → giá vật liệu đến hiện trường → chi phí vật liệu → kiểm tra chéo và phân tích rủi ro.**

Một kết quả có nhiều chữ số không đồng nghĩa với chính xác. Độ chính xác phụ thuộc trước hết vào chất lượng dữ liệu đầu vào. Khi mới có diện tích sàn và loại công trình, chỉ có thể lập ước lượng sơ bộ. Khi có mặt bằng, mặt cắt, chi tiết cấu tạo và quy cách vật liệu, có thể bóc tách theo bộ phận. Khi có bản vẽ thi công, bảng thống kê thép, schedule cửa, chỉ dẫn kỹ thuật và tiến độ mua sắm, mới có thể lập lượng đặt hàng có độ tin cậy cao.

---

# Phần I. Khung pháp lý, nguồn dữ liệu và cấp độ tin cậy

<!-- chunk_id: legal-basis-cost-management -->

## 1. Hệ thống căn cứ cần tra cứu

Việc xác định và quản lý chi phí đầu tư xây dựng tại Việt Nam được đặt trong khung của Nghị định số 10/2021/NĐ-CP về quản lý chi phí đầu tư xây dựng. Các phương pháp xác định chi phí, giá xây dựng, giá vật liệu đến hiện trường, đo bóc khối lượng và định mức được hướng dẫn bởi các thông tư của Bộ Xây dựng và các văn bản sửa đổi, hợp nhất tương ứng.

Tại thời điểm cập nhật tài liệu này, nhóm văn bản trọng yếu gồm:

1. Nghị định số 10/2021/NĐ-CP của Chính phủ về quản lý chi phí đầu tư xây dựng.
2. Thông tư số 11/2021/TT-BXD và văn bản sửa đổi, bổ sung, hợp nhất về xác định và quản lý chi phí đầu tư xây dựng.
3. Thông tư số 12/2021/TT-BXD và các văn bản sửa đổi, bổ sung về định mức xây dựng.
4. Thông tư số 13/2021/TT-BXD, Thông tư số 01/2025/TT-BXD, Thông tư số 60/2025/TT-BXD và văn bản hợp nhất về phương pháp xác định chỉ tiêu kinh tế kỹ thuật và đo bóc khối lượng công trình.
5. Thông tư số 08/2025/TT-BXD sửa đổi, bổ sung một số định mức xây dựng; có hiệu lực từ ngày 15 tháng 7 năm 2025.
6. Thông tư số 60/2025/TT-BXD có hiệu lực từ ngày 15 tháng 2 năm 2026; trong đó bổ sung hướng dẫn khảo sát, thu thập và công bố giá vật liệu xây dựng.
7. Quyết định công bố suất vốn đầu tư xây dựng và giá xây dựng tổng hợp bộ phận kết cấu công trình của Bộ Xây dựng tại năm áp dụng; dữ liệu này chỉ dùng kiểm tra sơ bộ hoặc lập tổng mức đầu tư theo đúng phạm vi, không thay cho bóc tách chi tiết.
8. QCVN 16:2023/BXD và tiêu chuẩn sản phẩm tương ứng để kiểm soát quy cách, chất lượng, hợp quy của vật liệu thuộc phạm vi điều chỉnh.

Văn bản hợp nhất giúp đọc thuận tiện nhưng khi xử lý pháp lý vẫn cần nhận diện văn bản gốc, văn bản sửa đổi, ngày hiệu lực và quy định chuyển tiếp. Hệ thống RAG không được kết luận một văn bản “hiện hành” chỉ vì ngày tải file mới; phải đối chiếu nội dung và thông tin hiệu lực.

<!-- chunk_id: legal-price-announcement-meaning -->

## 2. Ý nghĩa đúng của giá vật liệu do địa phương công bố

Giá vật liệu do cơ quan địa phương công bố là nguồn tham khảo quan trọng, nhưng không mặc nhiên đồng nghĩa với giá giao đến công trường. Theo hướng dẫn được bổ sung năm 2025, thông tin giá công bố có thể là giá tại mỏ, nơi sản xuất, đại lý, nhà cung ứng hoặc giá bình quân trong một khu vực cụ thể. Vì vậy, mỗi dòng giá phải được đọc cùng thông tin về địa điểm giao nhận, điều kiện thương mại, thuế, cự ly vận chuyển và thời điểm công bố.

Một lỗi nghiêm trọng là lấy giá cát tại mỏ ở ngoại thành rồi dùng trực tiếp cho công trình trong nội đô mà không tính vận chuyển, bốc xếp, phí vào bãi, hao hụt và hạn chế giờ xe tải. Ngược lại, nếu bảng giá đã ghi “đến chân công trình” hoặc “giao tại địa bàn”, không được cộng lại toàn bộ chi phí vận chuyển lần thứ hai.

Giá công bố cũng không phải lúc nào phản ánh đầy đủ nhãn hiệu, chứng chỉ, cấp chất lượng, kích thước, màu sắc hoặc điều kiện mua số lượng nhỏ. Với vật liệu hoàn thiện, vật liệu độc quyền hoặc thiết bị gắn liền với công trình, báo giá nhà sản xuất và nhà cung cấp thường có vai trò lớn hơn giá bình quân công bố.

<!-- chunk_id: source-hierarchy -->

## 3. Thứ tự ưu tiên nguồn dữ liệu giá

Trong ước lượng vật liệu, nên tổ chức nguồn giá theo thứ tự ưu tiên có điều kiện, không theo một thứ tự tuyệt đối cho mọi trường hợp:

- Giá trúng thầu, hợp đồng hoặc báo giá ràng buộc đúng quy cách, đúng thời điểm, đúng khối lượng và đúng điều kiện giao hàng thường có giá trị cao nhất cho mua sắm thực tế.
- Báo giá trực tiếp từ nhà sản xuất hoặc đại lý được ủy quyền phù hợp khi vật liệu có thương hiệu, mã sản phẩm, màu, kích thước hoặc chứng nhận cụ thể.
- Công bố giá của Sở Xây dựng phù hợp để lập và kiểm soát chi phí, nhưng phải xử lý điều kiện giá và vận chuyển.
- Dữ liệu hóa đơn, đơn hàng gần nhất của cùng dự án hoặc dự án tương tự là nguồn kiểm chứng tốt nếu đã loại trừ yếu tố thời điểm và điều kiện thương mại khác nhau.
- Giá bán lẻ trên website hoặc sàn thương mại chỉ nên dùng tham khảo khi xác minh được sản phẩm, thuế, vận chuyển và tính đại diện.
- Suất vốn đầu tư, giá xây dựng tổng hợp hoặc tỷ lệ chi phí vật liệu chỉ dùng kiểm tra chéo ở giai đoạn sớm; không thay cho đơn giá vật liệu chi tiết.

Nếu nhiều nguồn mâu thuẫn, hệ thống phải nêu nguyên nhân có thể gây chênh lệch: khác thời điểm, khác thương hiệu, khác nguồn hàng, khác cấp chất lượng, khác địa điểm giao, khác mức thuế, khác khối lượng mua, khác điều khoản thanh toán hoặc khác phạm vi phụ kiện.

<!-- chunk_id: estimate-classification -->

## 4. Cấp độ ước lượng theo mức độ hoàn thiện thiết kế

### 4.1. Ước lượng ý tưởng

Đầu vào thường chỉ có loại công trình, diện tích, số tầng, cấp hoàn thiện và địa điểm. Phương pháp phù hợp là suất vốn đầu tư, giá theo mét vuông, tỷ lệ vật liệu trên tổng chi phí hoặc mô hình tham số. Kết quả dùng cho sàng lọc phương án, không dùng đặt hàng.

### 4.2. Ước lượng sơ bộ theo bộ phận

Đầu vào có mặt bằng, chiều cao tầng, hệ kết cấu, phương án móng, loại tường và mức hoàn thiện. Có thể tính khối lượng theo móng, khung, sàn, tường, mái, hoàn thiện và MEP. Kết quả dùng lập ngân sách, so sánh giải pháp và chuẩn bị kế hoạch cung ứng.

### 4.3. Dự toán chi tiết theo công tác

Đầu vào có bản vẽ thiết kế, chỉ dẫn kỹ thuật, danh mục công tác, định mức và giá. Khối lượng công tác được đo bóc; hao phí vật liệu được xác định theo định mức được áp dụng hoặc định mức dự án. Kết quả có thể dùng lập dự toán và kiểm soát chi phí theo quy định.

### 4.4. Khối lượng mua sắm

Đầu vào phải có bản vẽ thi công, biện pháp thi công, kế hoạch cắt, quy cách đóng gói, điều kiện kho bãi, tiến độ và tồn kho. Lượng mua sắm khác khối lượng thiết kế vì phải xét làm tròn lô, tối ưu cắt, hao hụt hợp lý, hàng dự phòng, hàng mẫu, thay thế và lượng tồn.

---

# Phần II. Mô hình dữ liệu đầu vào cho hệ thống RAG

<!-- chunk_id: input-required-fields -->

## 5. Bộ dữ liệu tối thiểu của một yêu cầu ước lượng

Một yêu cầu ước lượng đáng tin phải chứa hoặc phải truy xuất được các trường sau:

- Địa điểm công trình: tỉnh, thành phố, quận hoặc huyện, điều kiện tiếp cận.
- Thời điểm giá: tháng, quý, ngày báo giá hoặc mốc lập dự toán.
- Loại công trình và quy mô: diện tích, số tầng, chiều cao, công năng.
- Giai đoạn thiết kế: ý tưởng, thiết kế cơ sở, thiết kế kỹ thuật, bản vẽ thi công.
- Hệ kết cấu: bê tông cốt thép, thép, gỗ, kết cấu lắp ghép hoặc hỗn hợp.
- Phương án móng: móng đơn, móng băng, móng bè, cọc ép, cọc khoan nhồi hoặc khác.
- Vật liệu và cấp chất lượng: mác hoặc cấp bền bê tông, cấp thép, loại gạch, chiều dày tường, chủng loại kính, cấp hoàn thiện.
- Phạm vi chi phí: chỉ vật liệu hay gồm vận chuyển, bơm, bốc xếp, thí nghiệm, thuế và dự phòng.
- Nguồn giá ưu tiên: công bố giá địa phương, báo giá nhà cung cấp hay hợp đồng.
- Quy tắc hao hụt: theo định mức, theo kế hoạch cắt, theo dữ liệu lịch sử hay hệ số tạm tính.

Nếu thiếu dữ liệu quan trọng, hệ thống không được tự chọn một giả định duy nhất rồi trình bày như sự thật. Phải xuất bảng giả định, mức độ ảnh hưởng và khoảng kết quả.

<!-- chunk_id: material-master-schema -->

## 6. Schema chuẩn hóa danh mục vật liệu

Mỗi dòng vật liệu trong phụ lục của ba bộ công văn công bố giá nên được chuyển thành một bản ghi có cấu trúc như sau:

```yaml
material_id: "STEEL-REBAR-CB400V-D16"
material_group: "thep-cot-be-tong"
material_name_vi: "Thép thanh vằn CB400-V đường kính 16 mm"
specification:
  standard: "TCVN 1651-2 hoặc tiêu chuẩn được dự án chấp thuận"
  grade: "CB400-V"
  diameter_mm: 16
brand: null
origin: null
unit_original: "kg"
unit_normalized: "kg"
price_value: null
currency: "VND"
price_basis: "tai-dai-ly | tai-nha-may | tai-mo | giao-cong-trinh | binh-quan-khu-vuc"
vat_included: null
transport_included: null
loading_included: null
location_city: "Ha Noi | Da Nang | Ho Chi Minh"
location_detail: null
effective_date: "YYYY-MM-DD"
source_document_id: null
source_document_number: null
source_annex_id: null
source_table_title: null
source_row_number: null
source_page: null
source_raw_text: null
notes: null
confidence: "high | medium | low"
```

Tên vật liệu không đủ để ghép giá. “Thép D16”, “thép cây D16”, “thép CB400 D16” và “thép SD390 D16” có thể không phải cùng sản phẩm. Tương tự, “gạch 600 × 600” chưa nói được ceramic hay porcelain, độ hút nước, bề mặt, màu, thương hiệu, cấp loại và quy cách đóng hộp.

<!-- chunk_id: unit-normalization -->

## 7. Chuẩn hóa đơn vị

Đơn vị phải được chuyển đổi trước khi nhân giá. Các lỗi phổ biến gồm dùng tấn thay cho kilôgam, dùng mét khối rời thay cho mét khối đầm chặt, dùng viên thay cho mét vuông, dùng lít thay cho kilôgam hoặc dùng bao mà không biết khối lượng mỗi bao.

Công thức tổng quát:

$$
Q_{norm} = Q_{source} \times K_{unit}
$$

Trong đó $K_{unit}$ là hệ số chuyển đổi có nguồn gốc rõ ràng. Hệ số không được suy đoán từ tên thương mại.

Ví dụ:

- Tấn sang kilôgam: $1\,t = 1000\,kg$.
- Mét sang milimét: $1\,m = 1000\,mm$.
- Diện tích tấm sang số tấm: số tấm bằng diện tích cần phủ chia diện tích hữu ích của một tấm, sau đó làm tròn lên.
- Bao xi măng sang kilôgam: phải đọc đúng khối lượng tịnh ghi trên bao hoặc dữ liệu sản phẩm.
- Gạch hộp sang mét vuông: dùng diện tích thực đóng gói trên hộp, không chỉ nhân kích thước viên vì có thể có sai số và quy cách đóng gói khác nhau.

<!-- chunk_id: price-city-selection -->

## 8. Chọn bộ công văn công bố giá Hà Nội, Đà Nẵng hoặc TP.HCM

Địa điểm công trình quyết định bộ công văn công bố giá nền. Nếu công trình nằm trong một trong ba thành phố, ưu tiên đúng công văn và phụ lục tương ứng với địa bàn, kỳ công bố và nhóm vật liệu. Nếu công trình ở tỉnh khác, không được chọn thành phố “gần nhất” chỉ theo khoảng cách địa lý. Phải xác định nguồn cung thực tế, tuyến vận chuyển và thị trường vật liệu.

Vật liệu nặng, giá trị thấp theo khối lượng như cát, đá, đất đắp, gạch xây và bê tông thương phẩm nhạy cảm mạnh với cự ly vận chuyển. Vật liệu giá trị cao, khối lượng nhỏ như thiết bị, phụ kiện, hóa chất xây dựng hoặc vật liệu nhập khẩu có thể ít phụ thuộc hơn vào khoảng cách nhưng phụ thuộc vào hệ thống phân phối.

Khi so sánh ba thành phố, phải đưa giá về cùng điều kiện: cùng thời điểm, cùng quy cách, cùng thuế, cùng cơ sở giao hàng và cùng đơn vị. Chênh lệch chưa chuẩn hóa không phản ánh chênh lệch thị trường thật.

---

# Phần III. Từ khối lượng thiết kế đến lượng vật liệu cần mua

<!-- chunk_id: quantity-definitions -->

## 9. Bốn loại khối lượng cần phân biệt

### 9.1. Khối lượng hình học thuần

Đây là thể tích, diện tích, chiều dài hoặc số lượng được tính trực tiếp từ hình học thiết kế. Ví dụ, thể tích dầm bằng chiều rộng nhân chiều cao nhân chiều dài sau khi áp dụng quy tắc giao nhau được lựa chọn.

### 9.2. Khối lượng công tác

Đây là khối lượng dùng trong bảng tiên lượng hoặc dự toán, được đo bóc theo quy tắc của công tác. Khối lượng công tác có thể khác khối lượng hình học thuần do quy tắc trừ hoặc không trừ lỗ rỗng, phạm vi giao nhau, độ dốc, lớp cấu tạo và đơn vị định mức.

### 9.3. Hao phí vật liệu theo định mức

Mỗi đơn vị công tác cần một lượng vật liệu xác định theo định mức được áp dụng. Ví dụ, một mét khối công tác bê tông có hao phí xi măng, cát, đá, nước và phụ gia nếu trộn tại chỗ; hoặc hao phí bê tông thương phẩm nếu dùng bê tông mua sẵn.

### 9.4. Lượng đặt mua

Lượng đặt mua bằng lượng cần dùng sau khi xét đóng gói, tối ưu cắt, hao hụt chưa nằm trong định mức, hàng mẫu, dự phòng thay thế, điều kiện giao hàng và tồn kho. Đây là con số dùng cho procurement, không nhất thiết bằng khối lượng dự toán.

<!-- chunk_id: no-double-counting-waste -->

## 10. Quy tắc không cộng trùng hao hụt

Đây là nguyên tắc quan trọng nhất trong ước lượng vật liệu. Nếu hao phí vật liệu trong định mức đã bao gồm mức hao hụt thi công theo phạm vi định mức, không được nhân thêm một hệ số hao hụt chung lên toàn bộ vật liệu mà không có lý do.

Có ba cách tính hợp lệ, nhưng chỉ nên chọn một cơ sở chính:

### Cách A: Từ khối lượng công tác và định mức

$$
Q_i = \sum_j V_j \times h_{ij}
$$

Trong đó:

- $V_j$ là khối lượng công tác $j$;
- $h_{ij}$ là hao phí vật liệu $i$ cho một đơn vị công tác $j$;
- $Q_i$ là lượng vật liệu $i$ theo định mức.

Nếu định mức đã chứa hao hụt, $Q_i$ không được nhân thêm hệ số hao hụt thông thường.

### Cách B: Từ hình học thuần và hệ số mua sắm

$$
Q_{buy} = Q_{net} \times (1 + w) + Q_{special}
$$

Trong đó $w$ là hao hụt dự kiến chưa được tính ở nơi khác; $Q_{special}$ là hàng mẫu, hàng dự phòng, phần làm thử hoặc yêu cầu riêng.

### Cách C: Từ bảng cắt và tối ưu hóa

Đối với thép, kính, tấm, ống, cáp và vật liệu dạng thanh, lượng mua phải tính từ kế hoạch cắt. Phần dư được xác định từ tổ hợp chiều dài tiêu chuẩn và chiều dài chi tiết, không nên dùng một tỷ lệ chung khi đã có dữ liệu cắt.

Nếu dự toán tính theo định mức nhưng phòng mua hàng tính theo kế hoạch cắt, hai kết quả cần được trình bày song song và giải thích chênh lệch, không cộng chúng vào nhau.

<!-- chunk_id: packaging-rounding -->

## 11. Làm tròn theo quy cách đóng gói

Vật liệu đóng gói phải làm tròn lên theo quy cách bán:

$$
N_{pack} = \left\lceil \frac{Q_{required}}{Q_{per\_pack}} \right\rceil
$$

$$
Q_{ordered} = N_{pack} \times Q_{per\_pack}
$$

Áp dụng cho xi măng bao, gạch hộp, sơn thùng, vít hộp, tấm thạch cao, cuộn màng chống thấm, cuộn lưới, cuộn cáp và vật liệu tương tự. Phần dư sau làm tròn phải được ghi là tồn dự kiến, không gọi toàn bộ là hao hụt.

<!-- chunk_id: procurement-balance -->

## 12. Cân bằng vật tư trên công trường

Công thức kiểm soát:

$$
Q_{opening} + Q_{received} = Q_{installed} + Q_{waste} + Q_{returned} + Q_{closing}
$$

Trong đó:

- $Q_{opening}$: tồn đầu kỳ;
- $Q_{received}$: lượng nhận;
- $Q_{installed}$: lượng đã lắp đặt hoặc sử dụng;
- $Q_{waste}$: hao hụt, hư hỏng, cắt bỏ được xác nhận;
- $Q_{returned}$: trả nhà cung cấp hoặc chuyển công trình khác;
- $Q_{closing}$: tồn cuối kỳ.

Nếu phương trình không cân bằng, dữ liệu chưa đủ tin cậy để dùng làm hệ số hao hụt lịch sử.

---

# Phần IV. Công thức xác định giá vật liệu đến hiện trường

<!-- chunk_id: delivered-price-formula -->

## 13. Công thức tổng quát

Giá vật liệu đến hiện trường có thể biểu diễn theo mô hình:

$$
P_{site} = P_{source} + C_{transport} + C_{loading} + C_{unloading} + C_{transfer} + C_{site\_handling} + C_{loss} + C_{other}
$$

Trong đó:

- $P_{source}$: giá tại mỏ, nhà máy, kho hoặc đại lý theo nguồn;
- $C_{transport}$: chi phí vận chuyển chính;
- $C_{loading}$ và $C_{unloading}$: bốc, xếp, dỡ nếu chưa nằm trong giá;
- $C_{transfer}$: trung chuyển do xe lớn không vào được công trường;
- $C_{site\_handling}$: vận chuyển nội bộ đến vị trí sử dụng nếu phạm vi dự toán yêu cầu;
- $C_{loss}$: hao hụt vận chuyển hợp lý chưa nằm trong giá hoặc định mức;
- $C_{other}$: phí đường, phà, bãi, che phủ, bảo quản đặc biệt, kiểm định hoặc chi phí liên quan.

Thuế giá trị gia tăng phải được quản lý bằng trường riêng. Không được cộng thuế nếu giá nguồn đã bao gồm thuế. Không được giả định mọi bảng giá công bố đều cùng trạng thái thuế.

<!-- chunk_id: transport-cost-model -->

## 14. Chi phí vận chuyển

### 14.1. Tính theo chuyến

$$
C_{transport,unit} = \frac{C_{trip}}{Q_{effective}}
$$

Trong đó $Q_{effective}$ là lượng hàng thực tế phân bổ cho chuyến, không vượt tải trọng hợp pháp và phải xét khả năng quay đầu, hạn chế tải trọng cầu đường, giờ cấm và tỷ lệ xe chạy rỗng.

### 14.2. Tính theo tấn-kilômét

$$
C_{transport} = Q_{ton} \times D_{km} \times R_{ton.km}
$$

Phương pháp này chỉ phù hợp nếu đơn giá tấn-kilômét đã phản ánh loại đường, loại xe, cự ly, chiều hàng, chiều rỗng và điều kiện vận hành. Không được áp một đơn giá duy nhất cho mọi cự ly.

### 14.3. Vật liệu tính theo mét khối

Khi nhà vận chuyển báo theo tấn nhưng vật liệu mua theo mét khối, phải dùng khối lượng thể tích ở đúng trạng thái giao hàng:

$$
Q_{ton} = Q_{m^3} \times \rho_{bulk}
$$

Cát ẩm, đất ướt, đá dăm rời và vật liệu đầm chặt có khối lượng thể tích khác nhau. Không dùng một giá trị mặc định không có nguồn kiểm chứng.

<!-- chunk_id: delivery-basis-checklist -->

## 15. Checklist điều kiện giá

Trước khi sử dụng một đơn giá, phải trả lời:

1. Giá tại đâu: mỏ, nhà máy, kho, đại lý, cổng công trình hay vị trí thi công?
2. Giá áp dụng cho khối lượng mua bao nhiêu?
3. Giá có VAT hay chưa?
4. Giá có bốc lên xe, dỡ xuống, pallet, bao bì, hoàn trả pallet hay chưa?
5. Giá có bơm bê tông, phụ phí chờ, phụ phí ca đêm, phụ phí đường cấm hay chưa?
6. Thời hạn hiệu lực của báo giá?
7. Điều kiện thanh toán và chiết khấu?
8. Thương hiệu, nguồn gốc, tiêu chuẩn, cấp loại, màu và kích thước có đúng không?
9. Có chứng chỉ xuất xưởng, hợp quy, thí nghiệm hoặc bảo hành không?
10. Khối lượng tối thiểu và số chuyến tối thiểu?

Nếu chưa trả lời được, đơn giá phải có trạng thái “chưa chuẩn hóa” và không nên dùng làm kết quả cuối.

---

# Phần V. Đo bóc và ước lượng theo nhóm công tác

# Chương 16. Công tác bê tông

<!-- chunk_id: concrete-volume -->

## 16.1. Khối lượng bê tông theo hình học

Khối lượng bê tông của cấu kiện được tính từ hình học thực của cấu kiện sau khi xác định quy tắc giao nhau và phần lỗ rỗng. Công thức cơ bản:

$$
V = L \times B \times H
$$

Đối với sàn:

$$
V_{slab} = A_{slab} \times t_{slab} - V_{openings}
$$

Đối với cột:

$$
V_{column} = \sum A_{section} \times H_{clear\ or\ rule}
$$

Đối với dầm:

$$
V_{beam} = \sum B \times H \times L
$$

Cần thống nhất dầm được tính toàn tiết diện hay trừ phần nằm trong sàn; cột tính đến đáy dầm, mặt sàn hay theo chiều cao tầng. Không được tính dầm và sàn theo hai quy tắc khác nhau gây trùng thể tích.

<!-- chunk_id: ready-mix-vs-site-mix -->

## 16.2. Bê tông thương phẩm và bê tông trộn tại chỗ

Nếu dùng bê tông thương phẩm, vật liệu mua chính là bê tông theo mét khối với cấp độ bền, độ sụt, loại xi măng, cỡ hạt, yêu cầu chống thấm, phụ gia và thời gian vận chuyển. Không bóc riêng xi măng, cát, đá cho cùng khối lượng bê tông, trừ khi phân tích giá hoặc có phần trộn tại chỗ riêng.

Nếu trộn tại chỗ, hao phí xi măng, cát, đá, nước và phụ gia phải lấy từ thiết kế cấp phối được chấp thuận hoặc định mức áp dụng. Không dùng tỷ lệ thể tích dân gian cho kết cấu chịu lực khi hồ sơ yêu cầu cấp phối thiết kế.

<!-- chunk_id: concrete-order-quantity -->

## 16.3. Lượng đặt bê tông

Lượng đặt theo đợt đổ:

$$
V_{order} = V_{geometric} + V_{construction\ allowance} - V_{available\ stock}
$$

Phần dự phòng phải xét độ chính xác cốp pha, bê tông còn trong ống bơm, bề mặt nền không phẳng, khối lượng kết thúc mẻ và khả năng điều phối xe. Không nên áp cùng một tỷ lệ cho móng, sàn, cột và cấu kiện nhỏ.

Các yếu tố làm tăng chi phí bê tông thương phẩm gồm cự ly trạm trộn, bơm cần hoặc bơm tĩnh, chiều cao bơm, thời gian chờ, đường kính ống, phụ gia kéo dài ninh kết, phụ gia chống thấm, ca đêm, khối lượng chuyến nhỏ và yêu cầu kiểm tra mẫu.

<!-- chunk_id: concrete-quality-price-match -->

## 16.4. Ghép đúng giá bê tông

Không ghép giá chỉ theo “mác 250” hoặc “B20” mà bỏ qua độ sụt, cỡ đá, yêu cầu bơm, loại xi măng, môi trường xâm thực và phụ gia. Hai bê tông cùng cấp độ bền có thể có giá khác do yêu cầu công nghệ và độ bền lâu.

---

# Chương 17. Cốt thép

<!-- chunk_id: rebar-unit-weight -->

## 17.1. Khối lượng lý thuyết của thép tròn

Khối lượng một mét thép tròn được suy ra từ diện tích tiết diện và khối lượng riêng thép:

$$
w = \rho \times \frac{\pi d^2}{4}
$$

Với $d$ tính bằng mét và $\rho$ khoảng $7850\,kg/m^3$. Dạng gần đúng thường dùng khi $d$ tính bằng milimét:

$$
w \approx \frac{d^2}{162}\quad kg/m
$$

Công thức này dùng kiểm tra và bóc sơ bộ. Khi mua hàng và nghiệm thu phải theo tiêu chuẩn sản phẩm, dung sai khối lượng và chứng từ lô thép.

<!-- chunk_id: rebar-bbs -->

## 17.2. Tính từ bảng thống kê thép

Phương pháp ưu tiên khi có bản vẽ thi công:

$$
Q_{steel} = \sum N_i \times L_i \times w_i
$$

Trong đó:

- $N_i$: số thanh của mã thép $i$;
- $L_i$: chiều dài cắt của một thanh, đã gồm móc, neo, uốn và nối theo bản vẽ;
- $w_i$: khối lượng đơn vị theo đường kính.

Không được cộng thêm chiều dài neo nếu chiều dài trong bảng thống kê đã bao gồm. Không được tính chồng phần nối cơ khí và nối chồng. Với lưới thép hàn, phải dùng khối lượng tấm hoặc khối lượng trên mét vuông đúng quy cách.

<!-- chunk_id: rebar-purchase-optimization -->

## 17.3. Từ khối lượng thiết kế đến lượng mua

Thép thanh được bán theo chiều dài thương mại. Lượng mua phụ thuộc kế hoạch cắt:

$$
Waste = \sum L_{stock} - \sum L_{used} - \sum L_{reusable\ offcut}
$$

Phần thép thừa đủ chiều dài để dùng cho cấu kiện khác không được tính là phế liệu. Hệ thống tối ưu cắt nên nhóm theo đường kính, cấp thép và chiều dài thanh. Không được trộn CB300-V và CB400-V chỉ vì cùng đường kính.

### Dải kiểm tra sơ bộ, không phải định mức pháp lý

Trong giai đoạn chưa có bảng cắt, nhiều dự án dùng dải dự phòng nội bộ khoảng vài phần trăm cho thép thanh. Dải này phụ thuộc mạnh vào hình học, chiều dài thương mại, mức độ lặp lại và khả năng tái sử dụng đầu thừa. RAG chỉ được đề xuất dải sau khi cảnh báo rằng phải thay bằng bảng cắt hoặc dữ liệu lịch sử của nhà thầu.

<!-- chunk_id: rebar-price-normalization -->

## 17.4. Giá thép

Giá thép phải chuẩn hóa theo:

- Chủng loại: thép trơn, thép vằn, thép cuộn, thép hình, lưới hàn.
- Cấp thép và tiêu chuẩn.
- Đường kính hoặc quy cách hình học.
- Thương hiệu và nguồn gốc nếu hồ sơ quy định.
- Đơn vị kg hoặc tấn.
- Giá giao tại nhà máy, đại lý hay công trình.
- Chi phí gia công cắt uốn, coupler, hàn, buộc và vận chuyển có nằm trong giá hay không.

Giá thép gia công sẵn không được so trực tiếp với giá thép nguyên liệu nếu chưa tách phí gia công và hao hụt cắt.

---

# Chương 18. Cốp pha và hệ chống đỡ

<!-- chunk_id: formwork-contact-area -->

## 18.1. Diện tích cốp pha

Cốp pha thường được đo theo diện tích bề mặt bê tông tiếp xúc với ván khuôn. Ví dụ:

- Cột chữ nhật: chu vi tiết diện nhân chiều cao.
- Dầm: hai mặt bên cộng mặt đáy; mặt trên thường không có cốp pha.
- Sàn: diện tích mặt đáy, trừ hoặc xử lý lỗ mở theo quy tắc đo bóc.
- Móng: các mặt bên cần ván khuôn; mặt tiếp xúc đất hoặc bê tông lót có thể không tính như cốp pha.

Vật liệu cốp pha mua không bằng diện tích cốp pha thi công vì tấm có thể luân chuyển nhiều lần. Lượng mua phụ thuộc sơ đồ chia khu, chu kỳ tầng, số bộ luân chuyển, tỷ lệ hỏng và kích thước tấm.

<!-- chunk_id: formwork-purchase -->

## 18.2. Tính lượng tấm

$$
A_{purchase} = \frac{A_{peak\ simultaneous}}{N_{reuse\ effective}} \times K_{cut} + A_{special}
$$

Trong đó:

- $A_{peak\ simultaneous}$ là diện tích cần lắp đồng thời;
- $N_{reuse\ effective}$ là số vòng sử dụng hiệu quả trong tiến độ;
- $K_{cut}$ phản ánh cắt ghép, nhưng phải dựa trên layout tấm;
- $A_{special}$ là tấm tạo hình, đầu dầm, góc, cổ cột hoặc khu vực không tái sử dụng.

Với cốp pha nhôm, thép hoặc hệ định hình, giá có thể là thuê, mua hoặc khấu hao. Không tính toàn bộ giá mua hệ cốp pha vào một lần nếu phương pháp chi phí yêu cầu phân bổ theo số lần sử dụng.

---

# Chương 19. Tường xây và gạch block

<!-- chunk_id: masonry-wall-volume -->

## 19.1. Diện tích và thể tích tường

Diện tích tường thuần:

$$
A_{wall,net} = \sum L \times H - \sum A_{openings} + A_{returns\ and\ details}
$$

Thể tích tường:

$$
V_{wall} = A_{wall,net} \times t
$$

Phải phân loại riêng tường 100, 150, 200 mm hoặc chiều dày khác; tường gạch đất sét nung, block bê tông, AAC và tấm tường có hao phí khác nhau.

<!-- chunk_id: brick-count-modular -->

## 19.2. Số viên theo mô đun xây

Nếu viên gạch có kích thước $l \times b \times h$ và mạch vữa thiết kế là $j$, số viên trên đơn vị diện tích có thể ước lượng từ kích thước mô đun:

$$
n = \frac{1}{(l+j)(h+j)}
$$

Công thức chỉ phù hợp khi hướng đặt viên và chiều dày tường đã xác định. Với tường nhiều hàng, block rỗng, gạch có ngàm, viên góc hoặc cách xây đặc biệt, phải dùng layout hoặc định mức tương ứng.

Số viên mua:

$$
N_{buy} = \left\lceil N_{net} + N_{cut\ break} + N_{special} - N_{stock} \right\rceil
$$

Hao hụt gạch phụ thuộc độ giòn, vận chuyển, độ phẳng tường, số lượng góc, kích thước lỗ mở, cắt điện nước và chất lượng bảo quản. Không dùng một tỷ lệ chung cho gạch nung và block AAC.

<!-- chunk_id: masonry-mortar -->

## 19.3. Vữa xây

Vữa xây có thể tính theo định mức công tác hoặc từ chênh lệch thể tích giữa khối xây và thể tích viên. Phương pháp hình học:

$$
V_{mortar,wet} = V_{wall} - N_{brick} \times V_{brick}
$$

Kết quả hình học phải hiệu chỉnh theo lỗ rỗng, vữa lọt lỗ, độ dày mạch, co ngót và điều kiện thi công. Với mục đích dự toán chính thức, ưu tiên định mức áp dụng. Với vữa khô trộn sẵn, dùng định mức tiêu hao của nhà sản xuất theo chiều dày và loại nền, sau đó kiểm chứng tại công trường.

---

# Chương 20. Trát, láng và cán nền

<!-- chunk_id: plaster-area -->

## 20.1. Diện tích trát

Diện tích trát tính theo diện tích bề mặt thực cần hoàn thiện. Hai mặt tường là hai khối lượng riêng. Phần cột, dầm, gờ, hốc, cạnh cửa và ô kỹ thuật cần được xác định theo phạm vi công tác.

$$
A_{plaster} = A_{walls} + A_{columns} + A_{beams} + A_{soffits} + A_{reveals} - A_{excluded}
$$

Thể tích vữa ướt sơ bộ:

$$
V_{wet} = A_{plaster} \times t_{average}
$$

Chiều dày trung bình phải phản ánh độ phẳng nền. Nếu tường xây sai lệch lớn, lượng vữa thực tế có thể vượt đáng kể lượng tính theo chiều dày danh nghĩa.

<!-- chunk_id: dry-mortar-consumption -->

## 20.2. Vữa khô trộn sẵn

Lượng vữa khô:

$$
M_{dry} = A \times c_{manufacturer}(t, substrate)
$$

Trong đó $c_{manufacturer}$ là định mức tiêu hao do nhà sản xuất công bố cho chiều dày và nền cụ thể. Nếu tài liệu kỹ thuật ghi tiêu hao theo mm chiều dày, phải nhân đúng số mm. Không dùng dữ liệu của vữa trát cho keo dán gạch hoặc vữa tự san.

<!-- chunk_id: screed-volume -->

## 20.3. Cán nền, láng sàn

$$
V_{screed} = \sum A_i \times t_i
$$

Phải phân khu theo chiều dày; sàn tạo dốc không được lấy một chiều dày duy nhất nếu chênh lệch lớn. Chiều dày trung bình của lớp tạo dốc tuyến tính có thể lấy trung bình hai đầu nếu hình học đều:

$$
t_{avg} = \frac{t_{min}+t_{max}}{2}
$$

---

# Chương 21. Gạch ốp lát và đá hoàn thiện

<!-- chunk_id: tile-net-area -->

## 21.1. Diện tích thuần

Diện tích lát sàn bằng diện tích mặt bằng hoàn thiện, trừ lỗ mở và phần không lát. Diện tích ốp tường tính theo chu vi, chiều cao ốp và các mảng thiết kế.

Lượng mua phải xét layout:

$$
A_{buy} = A_{net} + A_{cut} + A_{breakage} + A_{future\ replacement}
$$

Tỷ lệ cắt tăng khi lát chéo, hoa văn ghép, viên lớn, nhiều góc, phòng nhỏ, kích thước phòng không phù hợp mô đun và yêu cầu đối vân. Đá tự nhiên cần xét lựa vân, sai màu, nứt vi mô và cắt theo slab.

<!-- chunk_id: tile-box-rounding -->

## 21.2. Làm tròn theo hộp

$$
N_{box} = \left\lceil \frac{A_{buy}}{A_{box}} \right\rceil
$$

Phải lưu mã lô màu và caliber. Gạch cùng tên nhưng khác lô có thể lệch màu hoặc kích thước. Phần dự phòng thay thế nên cùng lô nếu công trình yêu cầu đồng nhất.

<!-- chunk_id: tile-adhesive-grout -->

## 21.3. Keo dán và keo chà ron

Lượng keo dán phụ thuộc kích thước răng bay, độ phẳng nền, kích thước viên, phương pháp dán một mặt hay hai mặt và tỷ lệ phủ sau viên. Không được tính chỉ theo diện tích mà bỏ qua chiều dày lớp keo.

Lượng chà ron phụ thuộc chiều rộng, chiều sâu mạch và kích thước viên. Công thức hình học có thể dùng kiểm tra, nhưng dữ liệu tiêu hao của nhà sản xuất thường chính xác hơn cho sản phẩm cụ thể.

---

# Chương 22. Sơn và bả

<!-- chunk_id: paint-area -->

## 22.1. Diện tích sơn

Diện tích sơn phải tính theo bề mặt thực, tách trần, tường trong, tường ngoài, kim loại và gỗ. Không lấy diện tích sàn nhân một hệ số cố định khi đã có bản vẽ.

$$
A_{paint} = A_{substrate} - A_{excluded} + A_{reveals} + A_{details}
$$

<!-- chunk_id: paint-consumption -->

## 22.2. Lượng sơn lý thuyết và thực tế

Nếu độ phủ lý thuyết của sản phẩm là $R$ mét vuông trên lít cho một lớp:

$$
Q_{theoretical} = \frac{A \times N_{coats}}{R}
$$

Lượng thực tế:

$$
Q_{actual} = Q_{theoretical} \times K_{surface} \times K_{application} \times K_{color}
$$

Trong đó:

- $K_{surface}$ phản ánh độ hút và độ nhám của nền;
- $K_{application}$ phản ánh lăn, quét, phun và tổn thất thiết bị;
- $K_{color}$ phản ánh đổi màu mạnh, màu đậm hoặc độ che phủ.

Không được dùng độ phủ quảng cáo nếu chưa đọc điều kiện chiều dày màng khô và bề mặt thử. Hệ sơn phải tách bột bả, sơn lót kháng kiềm, sơn phủ, sơn chống thấm và lớp xử lý nền.

<!-- chunk_id: paint-packaging -->

## 22.3. Làm tròn thùng sơn

Nên tối ưu phối hợp nhiều cỡ thùng để giảm dư. Dùng thuật toán chọn tổ hợp thùng thay vì chỉ làm tròn theo thùng lớn nhất. Phần sơn pha màu thường khó trả lại, do đó lượng dự phòng phải cân bằng với rủi ro thiếu cùng lô màu.

---

# Chương 23. Chống thấm

<!-- chunk_id: waterproofing-area -->

## 23.1. Phạm vi diện tích

Diện tích chống thấm không chỉ là diện tích mặt sàn. Phải cộng phần vén chân tường, cổ ống, hộp kỹ thuật, rãnh, khe co giãn, góc âm dương và chi tiết xuyên sàn.

$$
A_{waterproof} = A_{horizontal} + A_{upturn} + A_{details}
$$

<!-- chunk_id: membrane-overlap -->

## 23.2. Màng cuộn

Lượng màng cuộn phải tính theo kích thước hữu ích sau chồng mí:

$$
A_{effective\ roll} = (W-o_w)(L-o_l)
$$

Trong đó $o_w$ và $o_l$ là phần chồng mí theo chiều rộng và chiều dài. Số cuộn:

$$
N_{roll} = \left\lceil \frac{A_{layout}}{A_{effective\ roll}} \right\rceil
$$

Cần cộng màng gia cường tại góc, cổ ống và khe nếu hệ thống yêu cầu.

<!-- chunk_id: liquid-waterproofing -->

## 23.3. Chống thấm dạng lỏng

Lượng vật liệu dựa trên định mức kg/m² cho tổng hệ lớp hoặc mỗi lớp, phụ thuộc chiều dày màng khô. Không được giảm số lớp bằng cách thi công một lớp quá dày nếu tài liệu kỹ thuật không cho phép.

---

# Chương 24. Mái

<!-- chunk_id: roof-slope-area -->

## 24.1. Diện tích mái dốc

Nếu biết diện tích chiếu bằng $A_p$ và góc dốc $\alpha$:

$$
A_{slope} = \frac{A_p}{\cos \alpha}
$$

Hoặc tính trực tiếp từ chiều dài mái dốc. Phải cộng phần đua mái, úp nóc, diềm, khe mái, máng xối và chi tiết giao mái.

<!-- chunk_id: roofing-effective-coverage -->

## 24.2. Tấm lợp và ngói

Số tấm hoặc số viên phải dùng diện tích phủ hữu ích sau chồng mí, không dùng kích thước danh nghĩa. Với tôn, chiều dài tấm ảnh hưởng số mối nối và khả năng vận chuyển. Với ngói, dùng số viên trên mét vuông của hệ sản phẩm và độ dốc cho phép.

---

# Chương 25. Trần, vách thạch cao và tấm nhẹ

<!-- chunk_id: drywall-board-layout -->

## 25.1. Tấm

Số tấm phải tính theo layout kích thước tấm và hướng lắp:

$$
N_{board} = \left\lceil \frac{A_{net} \times K_{layout}}{A_{board}} \right\rceil
$$

$K_{layout}$ không nên là một hệ số tùy ý nếu có thể mô phỏng cắt tấm. Vách hai mặt, hai lớp phải nhân đúng số lớp. Tấm chống ẩm, chống cháy và tiêu âm phải tách mã vật liệu.

<!-- chunk_id: drywall-framing -->

## 25.2. Khung xương và phụ kiện

Khối lượng thanh đứng phụ thuộc bước khung, chiều cao vách và vị trí cửa. Thanh ngang, viền, tăng cường, ty treo, vít, băng xử lý mối nối, bột xử lý và bông cách âm phải được bóc riêng. Không dùng đơn giá “vách thạch cao trọn bộ” để suy ngược vật liệu nếu phạm vi hệ không rõ.

---

# Chương 26. Cửa, kính và mặt dựng

<!-- chunk_id: door-window-schedule -->

## 26.1. Schedule cửa

Phương pháp tốt nhất là lập schedule gồm mã cửa, kích thước ô chờ, kích thước sản xuất, số lượng, vật liệu khung, loại kính, phụ kiện, hoàn thiện bề mặt và yêu cầu chống cháy hoặc cách âm.

Diện tích sơ bộ:

$$
A_{opening} = W \times H \times N
$$

Nhưng chi phí cửa không tỷ lệ hoàn toàn với diện tích vì phụ kiện, số cánh, kiểu mở, chia đố và yêu cầu thử nghiệm tạo ra chi phí cố định trên mỗi bộ.

<!-- chunk_id: glass-cutting -->

## 26.2. Kính

Kính phải tính từ kích thước cắt, chiều dày, loại xử lý và sơ đồ tối ưu tấm jumbo. Không dùng diện tích ô kính thuần nhân hệ số hao hụt chung khi dự án lớn và có thể nesting. Kính cường lực sau gia công không thể cắt lại, nên sai số kích thước có rủi ro chi phí cao.

---

# Chương 27. Kết cấu thép

<!-- chunk_id: structural-steel-weight -->

## 27.1. Khối lượng thép hình và thép tấm

Khối lượng thép hình tính theo chiều dài nhân khối lượng đơn vị trong catalogue hoặc tiêu chuẩn. Thép tấm:

$$
M = L \times B \times t \times \rho
$$

Phải cộng bản mã, sườn tăng cường, bu lông, thanh giằng, tai cẩu và chi tiết liên kết. Sơn bảo vệ, mạ kẽm, chống cháy và gia công không phải khối lượng thép nhưng ảnh hưởng mạnh đến giá.

<!-- chunk_id: structural-steel-fabrication -->

## 27.2. Giá kết cấu thép

Cần phân biệt:

- Giá thép nguyên liệu.
- Giá gia công tại xưởng.
- Giá sơn hoặc mạ.
- Vận chuyển cấu kiện quá khổ.
- Cẩu lắp và liên kết tại công trường.
- Kiểm tra mối hàn và hồ sơ chất lượng.

Không so sánh giá “đồng/kg kết cấu hoàn thiện” với giá thép tấm hoặc thép hình nguyên liệu.

---

# Chương 28. Hệ thống MEP

<!-- chunk_id: mep-length-takeoff -->

## 28.1. Ống, cáp và máng

Chiều dài tuyến phải tính theo đường đi thực tế, cao độ, đoạn đứng, đoạn chuyển hướng, dự phòng đấu nối và bán kính uốn. Không lấy khoảng cách thẳng giữa hai thiết bị.

$$
L_{order} = L_{route} + L_{vertical} + L_{connection} + L_{service\ loop} + L_{waste\ not\ included}
$$

Phụ kiện ống như co, tê, măng sông, mặt bích, van, giá đỡ và vật tư treo phải bóc theo số lượng hoặc định mức hệ thống. Giá ống không đại diện cho toàn bộ chi phí vật liệu đường ống.

<!-- chunk_id: cable-drum-optimization -->

## 28.2. Cáp điện

Cáp được cung cấp theo cuộn hoặc drum; phải phân bổ tuyến theo chiều dài drum để giảm đầu thừa. Không được nối cáp tại vị trí không cho phép chỉ để tận dụng vật tư. Tiết diện, số lõi, cấp điện áp, chống cháy và thương hiệu phải khớp hoàn toàn với giá.

---

# Chương 29. Công trình giao thông và hạ tầng

<!-- chunk_id: road-material-quantities -->

## 29.1. Đất, cấp phối và lớp móng

Khối lượng lớp vật liệu sau đầm chặt:

$$
V_{compacted} = A \times t_{compacted}
$$

Lượng vật liệu rời cần vận chuyển:

$$
V_{loose} = V_{compacted} \times K_{conversion}
$$

$K_{conversion}$ phải lấy từ thí nghiệm, chỉ dẫn kỹ thuật, định mức hoặc dữ liệu mỏ; không được dùng một hệ số chung cho mọi loại đất và cấp phối. Độ ẩm tối ưu, khối lượng thể tích khô lớn nhất và độ chặt yêu cầu ảnh hưởng trực tiếp đến lượng và số chuyến.

<!-- chunk_id: asphalt-quantity -->

## 29.2. Bê tông nhựa

Khối lượng hỗn hợp:

$$
M_{asphalt} = A \times t \times \rho_{compacted}
$$

Khối lượng thể tích phải phù hợp thiết kế cấp phối và kết quả thí nghiệm. Giá hỗn hợp tại trạm chưa bao gồm vận chuyển, rải, lu lèn và hao hụt nhiệt. Cự ly từ trạm, thời gian vận chuyển và nhiệt độ thi công có thể quyết định tính khả thi của nguồn cung.

<!-- chunk_id: pipe-trench-material -->

## 29.3. Hạ tầng đường ống

Phải bóc riêng ống, phụ kiện, cát đệm, vật liệu lấp, bê tông móng hoặc gối, hố ga, nắp, gioăng, vật liệu cảnh báo và vật tư đấu nối. Khối lượng đào không đồng nghĩa với khối lượng vật liệu lấp vì có thể tái sử dụng đất đào hoặc thay bằng vật liệu chọn lọc.

---

# Phần VI. Hệ số hao hụt và dự phòng

<!-- chunk_id: waste-taxonomy -->

## 30. Phân loại hao hụt

Hao hụt cần được tách theo nguyên nhân:

1. Hao hụt công nghệ đã nằm trong định mức công tác.
2. Hao hụt vận chuyển từ nguồn đến công trường.
3. Hao hụt bốc xếp và lưu kho.
4. Hao hụt cắt ghép theo layout.
5. Hư hỏng do điều kiện thời tiết, bảo quản hoặc thi công lại.
6. Dư do đóng gói và lượng đặt hàng tối thiểu.
7. Hàng mẫu, mock-up, thử nghiệm và phê duyệt.
8. Dự phòng thay thế trong vận hành.
9. Mất mát bất thường hoặc quản lý yếu; không nên mặc nhiên đưa vào định mức hợp lý.

Hệ thống RAG phải hỏi “hao hụt này đã được tính ở đâu?” trước khi cộng.

<!-- chunk_id: planning-waste-ranges -->

## 31. Dải tham khảo nội bộ ở giai đoạn sớm

Các dải dưới đây chỉ dùng làm cảnh báo và kiểm tra sơ bộ khi chưa có định mức, bảng cắt hoặc dữ liệu nhà thầu. Chúng không phải định mức pháp lý và không được áp tự động:

| Nhóm vật liệu | Dải dự phòng sơ bộ thường gặp | Yếu tố làm thay đổi mạnh |
|---|---:|---|
| Bê tông thương phẩm | khoảng 0,5% đến 2% | loại cấu kiện, độ chính xác cốp pha, bơm, mẻ cuối |
| Thép thanh | khoảng 2% đến 5% | chiều dài thương mại, layout, nối, khả năng dùng đầu thừa |
| Gạch xây | khoảng 2% đến 7% | loại gạch, vận chuyển, số góc và lỗ mở, cắt MEP |
| Gạch ốp lát | khoảng 5% đến 10%; cao hơn khi lát chéo hoặc ghép vân | layout, kích thước viên, số góc, yêu cầu dự phòng cùng lô |
| Đá tự nhiên | khoảng 8% đến 20% hoặc tính theo nesting slab | lựa vân, nứt, ghép vân, kích thước slab |
| Sơn | khoảng 3% đến 8% ngoài lượng lý thuyết | độ hút nền, phương pháp thi công, màu và tay nghề |
| Màng chống thấm | khoảng 5% đến 12% | chồng mí, vén chân, chi tiết góc và cổ ống |
| Tấm thạch cao hoặc tấm nhẹ | khoảng 5% đến 12% | layout, hình dạng phòng, nhiều lớp, lỗ kỹ thuật |
| Ống và cáp | theo layout và quy cách cuộn; sơ bộ thường vài phần trăm | tuyến, đầu nối, cuộn hoặc drum, bán kính uốn |

Khi có dữ liệu dự án, phải thay dải tham khảo bằng một trong các nguồn: định mức hiện hành, kế hoạch cắt, chỉ dẫn nhà sản xuất, biện pháp thi công được duyệt hoặc dữ liệu tiêu hao lịch sử đã cân bằng vật tư.

<!-- chunk_id: contingency-vs-waste -->

## 32. Phân biệt hao hụt với dự phòng giá và dự phòng khối lượng

- Hao hụt vật liệu là phần vật chất không trở thành sản phẩm hoàn thành nhưng hợp lý trong quá trình cung ứng và thi công.
- Dự phòng khối lượng là phần cho phạm vi chưa xác định hoặc thay đổi thiết kế.
- Dự phòng giá là phần cho biến động giá theo thời gian.
- Dư đóng gói là phần còn tồn do quy cách bán.

Không được gộp tất cả vào một hệ số “10% dự phòng vật liệu” vì không thể truy vết và dễ cộng trùng.

---

# Phần VII. Tính chi phí vật liệu

<!-- chunk_id: material-cost-equation -->

## 33. Chi phí vật liệu cơ bản

$$
C_M = \sum_i Q_{i,buy} \times P_{i,site}
$$

Nếu giá chưa gồm thuế:

$$
C_{M,total} = C_M + Tax(C_M)
$$

Thuế phải là tham số theo quy định và thời điểm áp dụng, không đóng cứng trong corpus.

<!-- chunk_id: cost-comparison-city -->

## 34. So sánh ba thành phố

Đối với cùng danh mục vật liệu:

$$
C_{city} = \sum_i Q_i \times P_{i,city,normalized}
$$

Chênh lệch:

$$
\Delta C_{A-B} = C_A - C_B
$$

Tỷ lệ chênh:

$$
\Delta \% = \frac{C_A-C_B}{C_B}\times 100\%
$$

Chỉ so sánh khi $P_{i,city,normalized}$ đã cùng điều kiện. Nếu một thành phố công bố giá tại nguồn và thành phố khác công bố giá giao đến công trình, kết quả phải được đánh dấu không so sánh trực tiếp.

<!-- chunk_id: price-escalation -->

## 35. Biến động giá

Đối với ước lượng kéo dài nhiều tháng, nên lập tối thiểu ba kịch bản:

- Kịch bản cơ sở: giá tại thời điểm lập.
- Kịch bản thấp: giảm hoặc ổn định theo giả định có căn cứ.
- Kịch bản cao: tăng theo nhóm vật liệu nhạy cảm.

Dạng mô hình:

$$
P_{future,i} = P_{base,i} \times I_i
$$

Trong đó $I_i$ là hệ số biến động của nhóm vật liệu. Không dùng một chỉ số chung cho thép, cát, xi măng, kính và thiết bị nếu biến động khác nhau.

Nếu áp dụng chỉ số giá xây dựng hoặc điều chỉnh hợp đồng, phải tuân thủ phương pháp và điều kiện hợp đồng hiện hành; tài liệu này không thay thế công thức điều chỉnh giá được phê duyệt.

<!-- chunk_id: sensitivity-analysis -->

## 36. Phân tích độ nhạy

Mức ảnh hưởng của vật liệu $i$ khi giá thay đổi $r_i$:

$$
Impact_i = C_i \times r_i
$$

Nên ưu tiên kiểm soát các vật liệu có tích số “giá trị × độ biến động” lớn. Thép, bê tông, cát đá, nhôm kính và vật liệu hoàn thiện cao cấp thường là nhóm cần theo dõi, nhưng danh sách thực tế phụ thuộc dự án.

---

# Phần VIII. Ví dụ tính toán có cấu trúc

# Chương 37. Ví dụ tường xây

<!-- chunk_id: example-masonry-wall -->

## 37.1. Dữ liệu giả định

Một bức tường dài 10 m, cao 3,3 m, dày 100 mm. Có một cửa đi 0,9 × 2,2 m và hai cửa sổ 1,2 × 1,4 m. Ví dụ chỉ minh họa quy trình, không thay định mức.

Diện tích thô:

$$
A_{gross} = 10 \times 3.3 = 33\,m^2
$$

Diện tích lỗ mở:

$$
A_{open} = 0.9\times2.2 + 2\times1.2\times1.4 = 5.34\,m^2
$$

Diện tích tường thuần:

$$
A_{net} = 33 - 5.34 = 27.66\,m^2
$$

Thể tích tường:

$$
V_{wall} = 27.66 \times 0.1 = 2.766\,m^3
$$

Bước tiếp theo không được tự chọn số viên trên mét vuông nếu chưa biết loại gạch và mạch vữa. Hệ thống phải truy xuất định mức hoặc dữ liệu sản phẩm. Nếu dùng định mức $h_{brick}$ viên/m² và $h_{mortar}$ m³/m²:

$$
N_{brick} = 27.66 \times h_{brick}
$$

$$
V_{mortar} = 27.66 \times h_{mortar}
$$

Sau đó ghép giá gạch và thành phần vữa từ file giá thành phố tương ứng.

# Chương 38. Ví dụ bê tông sàn

<!-- chunk_id: example-concrete-slab -->

## 38.1. Dữ liệu giả định

Sàn 8 × 12 m, dày 120 mm, có lỗ thang 2 × 3 m.

$$
A_{net} = 8\times12 - 2\times3 = 90\,m^2
$$

$$
V_{slab} = 90 \times 0.12 = 10.8\,m^3
$$

Nếu dùng bê tông thương phẩm, lượng đặt phải xét biện pháp đổ và dự phòng thi công. Giá vật liệu là giá bê tông đúng cấp độ bền và yêu cầu công nghệ đến công trường, cộng phí bơm nếu chưa gồm.

Nếu dùng bê tông trộn tại chỗ, hệ thống phải lấy cấp phối hoặc định mức để tính xi măng, cát, đá, nước và phụ gia; không được đồng thời tính giá bê tông thương phẩm.

# Chương 39. Ví dụ cốt thép

<!-- chunk_id: example-rebar -->

## 39.1. Một mã thép D16

Giả sử có 80 thanh, chiều dài cắt mỗi thanh 5,8 m.

Khối lượng đơn vị gần đúng:

$$
w = \frac{16^2}{162} \approx 1.58\,kg/m
$$

Khối lượng thiết kế:

$$
Q = 80 \times 5.8 \times 1.58 \approx 733.1\,kg
$$

Lượng mua không được kết luận bằng cách cộng ngay 5%. Phải xem thanh thương mại dài bao nhiêu và mỗi thanh cắt được bao nhiêu đoạn 5,8 m. Nếu thanh thương mại 11,7 m, có thể cắt hai đoạn 5,8 m với phần dư nhỏ; lượng hao hụt thực tế thấp hơn trường hợp chiều dài cắt 6,1 m.

# Chương 40. Ví dụ gạch lát

<!-- chunk_id: example-tile -->

## 40.1. Phòng 4,2 × 5,6 m

Diện tích thuần:

$$
A = 4.2 \times 5.6 = 23.52\,m^2
$$

Nếu lát thẳng bằng gạch 600 × 600 mm, cần lập layout theo hai chiều. Tính diện tích nhân 1,05 chỉ là cách sơ bộ. Cách tốt hơn là tính số viên theo hàng, số viên cắt biên và khả năng dùng phần cắt cho phía đối diện. Sau đó làm tròn theo số mét vuông mỗi hộp.

Giá phải ghép đúng mã gạch; giá “gạch 600 × 600” trung bình không đủ để lập ngân sách hoàn thiện chính xác.

# Chương 41. Ví dụ giá cát đến công trường

<!-- chunk_id: example-sand-delivered-price -->

## 41.1. Dữ liệu giả định

- Giá tại mỏ: $P_m$ đồng/m³.
- Cự ly: $D$ km.
- Xe chở hiệu quả: $Q_t$ m³/chuyến.
- Giá một chuyến: $C_t$ đồng.
- Bốc dỡ và phí khác: $C_o$ đồng/m³.

Chi phí vận chuyển phân bổ:

$$
C_{transport} = \frac{C_t}{Q_t}
$$

Giá đến công trường:

$$
P_{site} = P_m + \frac{C_t}{Q_t} + C_o
$$

Nếu bảng giá địa phương đã công bố giá giao tại khu vực công trình, không dùng lại công thức trên trừ khi bảng giá loại trừ một thành phần cụ thể.

---

# Phần IX. Kiểm tra chéo và phát hiện sai số

<!-- chunk_id: validation-checks -->

## 42. Kiểm tra hình học

- Tổng diện tích phòng phải phù hợp diện tích sàn và phạm vi tường.
- Tổng thể tích bê tông theo cấu kiện phải khớp mô hình hoặc bản vẽ.
- Diện tích cốp pha không được nhỏ hơn bất hợp lý so với bề mặt cấu kiện.
- Diện tích sơn, trát phải phân biệt số mặt.
- Lỗ mở phải được trừ hoặc không trừ nhất quán theo quy tắc đo bóc.

<!-- chunk_id: validation-units -->

## 43. Kiểm tra đơn vị

Các cảnh báo tự động nên gồm:

- Giá thép tính đồng/tấn nhưng khối lượng tính kg.
- Giá bê tông tính đồng/m³ nhưng khối lượng nhập lít.
- Sơn báo kg nhưng tiêu hao theo lít, chưa có khối lượng riêng.
- Gạch báo đồng/viên nhưng lượng bóc m².
- Cát báo m³ rời nhưng lượng yêu cầu m³ đầm chặt.
- Kính báo m² nhưng chi phí tối thiểu theo tấm hoặc bộ.

<!-- chunk_id: validation-price-date -->

## 44. Kiểm tra thời điểm

Nếu ngày giá cách ngày ước lượng quá xa hoặc thị trường biến động mạnh, kết quả phải có cảnh báo. Không được trộn giá thép tháng hiện tại với giá cát của năm trước mà không điều chỉnh hoặc giải thích.

<!-- chunk_id: validation-spec -->

## 45. Kiểm tra quy cách

Mỗi ghép giá nên có điểm tương đồng:

```text
match_score = specification + unit + grade + dimensions + brand + delivery_basis + date + location
```

Nếu thiếu cấp thép, cấp bê tông, chiều dày kính, loại gạch, loại xi măng hoặc điều kiện giao hàng, điểm tin cậy phải giảm.

<!-- chunk_id: validation-outliers -->

## 46. Phát hiện ngoại lệ giá

Với nhiều báo giá cùng quy cách, có thể dùng trung vị thay vì trung bình khi có giá ngoại lệ:

$$
P_{median} = median(P_1, P_2, ..., P_n)
$$

Kiểm tra độ phân tán:

$$
CV = \frac{\sigma}{\mu}
$$

Hệ số biến thiên cao cho thấy dữ liệu không đồng nhất hoặc thị trường biến động. Trước khi loại ngoại lệ, phải kiểm tra giá thấp có thiếu vận chuyển hoặc thuế, giá cao có bao gồm phụ kiện hoặc dịch vụ hay không.

<!-- chunk_id: benchmark-ratios -->

## 47. Kiểm tra theo suất và tỷ lệ

Sau khi bóc chi tiết, có thể quy đổi:

- kg thép/m² sàn;
- m³ bê tông/m² sàn;
- viên gạch/m² tường;
- lít sơn/m² bề mặt;
- chi phí vật liệu/m² sàn;
- tỷ trọng nhóm vật liệu trong tổng vật liệu.

Các tỷ lệ chỉ dùng phát hiện bất thường. Không tự động sửa kết quả để ép về “mức phổ biến”, vì hệ kết cấu và kiến trúc có thể khác biệt thực sự.

---

# Phần X. Quy trình vận hành với ba bộ PDF công văn và phụ lục công bố giá

<!-- chunk_id: official-pdf-source-model -->

## 48. Cấu trúc nguồn: công văn và phụ lục PDF

Ba bộ dữ liệu giá của Hà Nội, Đà Nẵng và TP.HCM không được coi là ba bảng giá phẳng. Mỗi bộ phải được mô hình hóa thành ít nhất hai tầng liên kết:

1. **Tầng văn bản công văn**: số và ký hiệu văn bản, cơ quan ban hành, ngày ban hành, kỳ công bố, phạm vi địa bàn, mục đích sử dụng, nguyên tắc tham khảo, quy định về thuế, vận chuyển, chất lượng, điều kiện áp dụng, trách nhiệm của chủ thể sử dụng và các lưu ý pháp lý.
2. **Tầng phụ lục bảng giá**: nhóm vật liệu, tên vật liệu, tiêu chuẩn hoặc quy cách, đơn vị tính, nhà sản xuất hoặc nhà cung cấp, địa chỉ nguồn hàng, giá trị giá, địa bàn áp dụng, ghi chú và số trang.

Không được tách phụ lục khỏi công văn khi lập chỉ mục RAG. Một dòng giá chỉ có ý nghĩa đầy đủ khi truy ngược được về công văn chứa điều kiện sử dụng của nó. Nếu công văn nêu rằng giá chưa gồm VAT, chưa gồm vận chuyển, chỉ áp dụng tại nơi sản xuất hoặc chỉ mang tính tham khảo, tất cả bản ghi giá thuộc phụ lục phải kế thừa metadata đó trừ khi bảng có ghi chú riêng khác đi.

### 48.1. Mô hình hồ sơ nguồn

```yaml
source_package_id: "HN-YYYY-MM-OFFICIAL-VLXD"
city: "Ha Noi | Da Nang | Ho Chi Minh"
source_type: "official_price_announcement"
dispatch:
  document_number: null
  document_symbol: null
  issuing_authority: null
  signer: null
  issue_date: "YYYY-MM-DD"
  effective_period_from: null
  effective_period_to: null
  publication_period_label: null
  applicable_area: []
  purpose_and_scope: null
  legal_notes: []
  vat_default: "included | excluded | mixed | unknown"
  transport_default: "included | excluded | mixed | unknown"
  price_basis_default: "tai-mo | tai-nha-may | tai-dai-ly | den-cong-trinh | binh-quan-khu-vuc | mixed | unknown"
annexes:
  - annex_id: "PL-01"
    annex_title: null
    page_from: null
    page_to: null
    material_groups: []
file_provenance:
  filename: null
  file_hash_sha256: null
  page_count: null
  has_text_layer: null
  extraction_method: "native-text | table-parser | manual-review | ocr-last-resort"
  reviewed: false
```

### 48.2. Những nội dung bắt buộc phải đọc ở phần công văn

Trước khi trích giá từ phụ lục, hệ thống phải nhận diện và lưu riêng các nội dung sau:

- Số, ký hiệu và ngày công văn.
- Cơ quan ban hành và đơn vị đầu mối công bố.
- Kỳ giá: theo tháng, quý, thời điểm khảo sát hoặc khoảng thời gian cụ thể.
- Địa bàn áp dụng: toàn thành phố, từng quận/huyện, khu vực hoặc vị trí nguồn cung.
- Mục đích công bố và mức độ ràng buộc của thông tin giá.
- Giá đã hay chưa gồm thuế giá trị gia tăng.
- Giá đã hay chưa gồm vận chuyển, bốc xếp, lưu kho, hao hụt hoặc chi phí khác.
- Giá tại mỏ, nhà máy, đại lý, nơi bán hay đến chân công trình.
- Quy định xử lý vật liệu không có trong công bố giá.
- Khuyến cáo về khảo sát giá thị trường, báo giá nhà cung cấp hoặc trách nhiệm của đơn vị lập dự toán.
- Các chú thích áp dụng chung cho toàn bộ phụ lục.

Nếu một trường không được nêu rõ, phải lưu `unknown`; không được suy luận thành `included` hoặc `excluded` chỉ dựa vào thông lệ.

<!-- chunk_id: three-city-etl -->

## 49. Quy trình ETL dữ liệu từ PDF công văn kèm phụ lục

### Bước 1. Phân loại chất lượng PDF

Xác định PDF có lớp văn bản thật, bảng vector, ảnh quét hay dạng lai. Ưu tiên trích xuất trực tiếp từ lớp văn bản và cấu trúc bảng. Chỉ dùng OCR khi trang không có lớp văn bản sử dụng được; mọi kết quả OCR về số tiền, đơn vị và kích thước phải được kiểm tra thủ công hoặc bằng quy tắc đối chiếu.

### Bước 2. Tách phần công văn và phần phụ lục

Xác định ranh giới trang của công văn, từng phụ lục và từng bảng. Giữ liên kết `source_package_id → dispatch → annex → table → row`. Không gộp tiêu đề bảng với dòng vật liệu và không bỏ các chú thích cuối trang.

### Bước 3. Trích xuất metadata công văn

Đọc số văn bản, ngày ban hành, kỳ công bố, cơ quan ban hành, địa bàn, điều kiện thuế, vận chuyển, cơ sở giao hàng và các cảnh báo áp dụng. Metadata này được truyền xuống mọi dòng giá thuộc phụ lục, trừ khi dòng hoặc bảng có ghi chú riêng.

### Bước 4. Trích xuất từng bảng phụ lục

Đọc từng bảng giá, giữ nguyên tên vật liệu, đơn vị, giá, ghi chú, địa điểm, thời điểm, nhà sản xuất hoặc nhà cung cấp, tiêu chuẩn/quy cách, số thứ tự dòng, tên bảng và trang nguồn.

### Bước 5. Làm sạch

- Chuẩn hóa Unicode và dấu thập phân.
- Tách giá trị số khỏi đơn vị.
- Không tự điền ô trống bằng giá dòng trước nếu cấu trúc bảng không chứng minh.
- Nhận diện giá “từ... đến...” và lưu min/max.
- Giữ ghi chú “chưa VAT”, “tại mỏ”, “đến công trình”, “giá tham khảo”.

### Bước 6. Ánh xạ danh mục

Ghép mỗi dòng với `material_id`. Nếu chưa đủ quy cách, tạo bản ghi `unresolved` thay vì ép ghép.

### Bước 7. Chuẩn hóa điều kiện giá

Chuyển về cùng cơ sở giao hàng và thuế khi so sánh. Lưu cả giá gốc và giá chuẩn hóa để truy vết.

### Bước 8. Kiểm tra và đối soát

So sánh với báo giá nhà cung cấp, dữ liệu tháng trước và phạm vi hợp lý. Cảnh báo biến động lớn.

### Bước 9. Lập chỉ mục RAG

Chunk theo nhóm vật liệu, thành phố và thời điểm. Không gộp ba thành phố vào một đoạn quá dài vì có thể truy xuất nhầm địa bàn.

<!-- chunk_id: price-record-example -->

## 50. Bản ghi giá đề xuất cho một dòng phụ lục

```json
{
  "price_id": "HCM-2026-06-STEEL-CB400V-D16-001",
  "material_id": "STEEL-REBAR-CB400V-D16",
  "city": "TP. Ho Chi Minh",
  "effective_period": "2026-06",
  "price_original": 0,
  "unit_original": "dong/kg",
  "price_basis": "tai-dai-ly",
  "vat_included": false,
  "transport_included": false,
  "normalized_price_site": null,
  "source_package_id": "HCM-2026-06-OFFICIAL-VLXD",
  "source_document_number": null,
  "source_annex_id": "PL-01",
  "source_table_title": null,
  "source_row_number": null,
  "source_file": "cong-van-cong-bo-gia-va-phu-luc.pdf",
  "source_page": 12,
  "source_raw_text": null,
  "confidence": "medium",
  "notes": "Can tinh van chuyen den dia diem cong trinh"
}
```

<!-- chunk_id: retrieval-routing -->

## 51. Logic truy xuất

Khi người dùng hỏi “giá vật liệu cho công trình ở Hà Nội”, bộ truy xuất nên ưu tiên:

1. Đoạn kiến thức về phương pháp tính loại vật liệu.
2. Bản ghi giá Hà Nội đúng thời điểm.
3. Đoạn về vận chuyển và điều kiện giá nếu giá chưa đến công trường.
4. Định mức hoặc dữ liệu tiêu hao đúng công tác.
5. Đoạn kiểm tra sai số và hao hụt.

Không chỉ truy xuất dòng giá. Giá không có ngữ cảnh có thể làm câu trả lời sai dù con số được đọc đúng.

---

# Phần XI. Mẫu thuật toán và pseudo-code

<!-- chunk_id: calculation-pipeline -->

## 52. Pipeline tính chi phí

```python
for work_item in project.work_items:
    work_quantity = measure(work_item.geometry, work_item.measurement_rule)

    for consumption in get_consumptions(work_item.norm_id):
        material = material_master[consumption.material_id]
        required_qty = work_quantity * consumption.quantity_per_unit

        # Chỉ cộng hao hụt bổ sung nếu chưa nằm trong định mức.
        if not consumption.includes_waste:
            required_qty *= 1 + project.extra_waste_rate(material)

        ordered_qty = round_to_package_or_stock_length(
            required_qty,
            material.packaging,
            material.stock_length,
            project.cutting_plan
        )

        source_price = select_price(
            material_id=material.id,
            city=project.city,
            date=project.price_date,
            specification=material.specification
        )

        site_price = normalize_to_site_price(
            source_price,
            project.delivery_conditions,
            tax_mode=project.tax_mode
        )

        cost = ordered_qty * site_price
        add_to_cost_plan(material.id, ordered_qty, site_price, cost)
```

<!-- chunk_id: price-selection-score -->

## 53. Chấm điểm dòng giá

```text
score = 0
+ 30 nếu material_id khớp hoàn toàn
+ 15 nếu cấp chất lượng khớp
+ 10 nếu kích thước khớp
+ 10 nếu đơn vị khớp hoặc chuyển đổi chắc chắn
+ 10 nếu thành phố khớp
+ 10 nếu thời điểm nằm trong kỳ yêu cầu
+ 10 nếu điều kiện giao hàng rõ
+ 5 nếu thuế rõ
- 20 nếu dùng giá thay thế khác thương hiệu bắt buộc
- 30 nếu thiếu thông số kỹ thuật trọng yếu
- 40 nếu không rõ giá tại nguồn hay tại công trường
```

Điểm số chỉ hỗ trợ kiểm tra, không thay đánh giá chuyên môn.

<!-- chunk_id: uncertainty-output -->

## 54. Xuất kết quả có độ không chắc chắn

```json
{
  "estimate_level": "preliminary",
  "location": "Da Nang",
  "price_date": "2026-06",
  "material_cost_base": 0,
  "material_cost_low": 0,
  "material_cost_high": 0,
  "currency": "VND",
  "includes_vat": false,
  "includes_transport": true,
  "assumptions": [],
  "exclusions": [],
  "major_risks": [],
  "source_records": [],
  "confidence": "medium"
}
```

---

# Phần XII. Câu trả lời mẫu cho hệ thống RAG

<!-- chunk_id: answer-template -->

## 55. Cấu trúc câu trả lời bắt buộc

Một câu trả lời tốt nên có các phần:

1. Phạm vi và mức độ ước lượng.
2. Dữ liệu đầu vào và giả định.
3. Công thức hoặc phương pháp bóc khối lượng.
4. Lượng vật liệu thuần, lượng theo định mức và lượng mua nếu khác nhau.
5. Nguồn giá, thời điểm, thành phố và điều kiện giá.
6. Chi phí vật liệu đến hiện trường.
7. Thuế và chi phí chưa bao gồm.
8. Kiểm tra chéo.
9. Rủi ro và dữ liệu cần bổ sung.

<!-- chunk_id: answer-refusal-conditions -->

## 56. Trường hợp không nên đưa một con số duy nhất

Không nên trả một con số duy nhất khi:

- Chỉ có diện tích sàn nhưng không biết số tầng hoặc hệ kết cấu.
- Không biết địa điểm và thời điểm giá.
- Không biết vật liệu hoàn thiện.
- Không rõ giá có vận chuyển và VAT.
- Khối lượng lấy từ ảnh hoặc bản vẽ không đủ tỷ lệ.
- Quy cách vật liệu trong file giá không khớp thiết kế.
- Công trình có điều kiện đặc biệt như tầng hầm sâu, ven biển, đường hẹp, thi công ban đêm hoặc yêu cầu chứng nhận cao.

Trong trường hợp này, hệ thống nên đưa khoảng giá, giả định và độ nhạy thay vì khẳng định tuyệt đối.

---

# Phần XIII. Các lỗi thường gặp

<!-- chunk_id: common-errors -->

## 57. Danh sách lỗi nghiêm trọng

1. Nhân diện tích sàn với kg thép/m² mà không biết hệ kết cấu.
2. Tính bê tông thương phẩm rồi cộng thêm xi măng, cát, đá cho cùng cấu kiện.
3. Dùng định mức đã có hao hụt rồi cộng thêm 5% hoặc 10% toàn bộ vật liệu.
4. Lấy giá tại mỏ làm giá tại công trường.
5. Cộng vận chuyển hai lần.
6. Trộn giá có VAT và chưa VAT.
7. Ghép vật liệu khác quy cách vì tên gần giống.
8. Không làm tròn theo bao, hộp, cuộn, thanh hoặc chuyến xe.
9. Gọi phần dư đóng gói là hao hụt thi công.
10. Dùng giá của tháng cũ cho thị trường biến động mà không cảnh báo.
11. Không trừ tồn kho và vật tư thu hồi.
12. Dùng hệ số quy đổi cát, đất, đá mà không xác định trạng thái rời, ẩm hoặc đầm chặt.
13. Không tính phụ kiện của hệ vật liệu.
14. Không tách vật liệu theo thương hiệu hoặc cấp chất lượng bắt buộc.
15. Dùng suất vốn đầu tư để đặt hàng vật liệu.

---

# Phần XIV. Từ điển thuật ngữ

<!-- chunk_id: glossary -->

## 58. Thuật ngữ chính

**Bóc tách khối lượng:** xác định số lượng công tác hoặc cấu kiện từ hồ sơ thiết kế theo quy tắc đo bóc.

**Định mức xây dựng:** mức hao phí vật liệu, nhân công, máy hoặc chi phí cần thiết để hoàn thành một đơn vị công tác trong điều kiện xác định.

**Hao phí vật liệu:** lượng vật liệu cần cho một đơn vị công tác, có thể đã bao gồm hao hụt trong phạm vi định mức.

**Giá vật liệu tại nguồn:** giá tại mỏ, nhà máy, kho hoặc đại lý trước các chi phí đưa đến công trường nếu chưa bao gồm.

**Giá vật liệu đến hiện trường:** giá sau khi cộng các chi phí hợp lý để vật liệu đến địa điểm công trình theo phạm vi quy định.

**Khối lượng thuần:** lượng vật liệu hoặc cấu kiện theo hình học thiết kế, chưa xét hao hụt và đóng gói.

**Lượng mua:** lượng đặt hàng thực tế sau tối ưu cắt, làm tròn đóng gói, dự phòng hợp lý và trừ tồn kho.

**Suất vốn đầu tư:** chỉ tiêu chi phí bình quân cho một đơn vị công suất hoặc diện tích, dùng cho ước lượng ở giai đoạn phù hợp.

**Bảng tiên lượng:** danh sách công tác và khối lượng đo bóc.

**BBS, Bar Bending Schedule:** bảng thống kê và gia công cốt thép.

**Price basis:** cơ sở hình thành giá, ví dụ tại mỏ, tại đại lý hoặc giao đến công trường.

**Nesting:** tối ưu sắp xếp chi tiết cắt trên tấm, thanh hoặc cuộn để giảm phế liệu.

---

# Phần XV. Danh mục nguồn tham khảo chính thức

<!-- chunk_id: official-sources -->

## 59. Nguồn pháp lý và kỹ thuật

1. Chính phủ, Nghị định số 10/2021/NĐ-CP về quản lý chi phí đầu tư xây dựng:  
   https://vanban.chinhphu.vn/?docid=202663&pageid=27160

2. Bộ Xây dựng, Văn bản hợp nhất số 35/VBHN-BXD năm 2026 về hướng dẫn một số nội dung xác định và quản lý chi phí đầu tư xây dựng, gồm phương pháp xác định giá vật liệu đến hiện trường:  
   https://moc.gov.vn/Images/FileVanBan/BXD_35-VBHN-BXD_15062026.pdf

3. Bộ Xây dựng, Phụ lục của Văn bản hợp nhất số 35/VBHN-BXD:  
   https://moc.gov.vn/Images/FileVanBan/BXD_35-VBHN-BXD_15062026_Phuluc%281%29.pdf

4. Bộ Xây dựng, Văn bản hợp nhất số 37/VBHN-BXD năm 2026 về phương pháp xác định các chỉ tiêu kinh tế kỹ thuật và đo bóc khối lượng công trình:  
   https://moc.gov.vn/vn/Pages/ChiTietVanBan.aspx?TypeVB=2&vID=4989

5. Bộ Xây dựng, Thông tư số 01/2025/TT-BXD sửa đổi, bổ sung quy định về đo bóc khối lượng và quản lý chi phí:  
   https://vanban.chinhphu.vn/?classid=1&docid=212647&pageid=27160&typegroupid=6

6. Bộ Xây dựng, Thông tư số 08/2025/TT-BXD sửa đổi, bổ sung một số định mức xây dựng:  
   https://moc.gov.vn/vn/tin-tuc/1176/85737/sua-doi--bo-sung-mot-so-dinh-muc-xay-dung-ban-hanh-tai-thong-tu-so-122021tt-bxd-ngay-3182021-cua-bo-truong-bo-xay-dung.aspx

7. Bộ Xây dựng, Thông tư số 60/2025/TT-BXD, có hiệu lực từ ngày 15/02/2026; bổ sung hướng dẫn khảo sát, thu thập và công bố giá vật liệu xây dựng:  
   https://moc.gov.vn/pl/pages/ChiTietVanBan.aspx?vID=576

8. Bộ Xây dựng, Quyết định số 425/QĐ-BXD năm 2026 và phụ lục công bố suất vốn đầu tư xây dựng, giá xây dựng tổng hợp bộ phận kết cấu công trình:  
   https://moc.gov.vn/Images/FileVanBan/BXD_425-QD-BXD_30032026_Phuluc.pdf

9. Bộ Xây dựng, QCVN 16:2023/BXD về sản phẩm, hàng hóa vật liệu xây dựng:  
   https://moc.gov.vn/Images/editor/files/Quy%20Chu%E1%BA%A9n/QCVN%2016-2023.pdf

## 60. Nguyên tắc sử dụng nguồn

Nguồn pháp lý được dùng để xác định phương pháp, trách nhiệm công bố giá, đo bóc và định mức. Ba bộ PDF công văn công bố giá kèm phụ lục của Hà Nội, Đà Nẵng và TP.HCM được dùng làm dữ liệu đơn giá tại thời điểm cụ thể; phần công văn cung cấp ngữ cảnh pháp lý và điều kiện áp dụng, còn phụ lục cung cấp dòng giá. Chỉ dẫn kỹ thuật và catalogue nhà sản xuất được dùng cho tiêu hao sản phẩm chuyên dụng như sơn, keo, vữa khô, chống thấm, tấm, phụ kiện và hệ hoàn thiện.

Khi có xung đột, phải ưu tiên hồ sơ thiết kế và chỉ dẫn kỹ thuật được phê duyệt, văn bản pháp luật hiện hành, điều kiện hợp đồng và nguồn giá phù hợp với phạm vi dự án. Tài liệu RAG chỉ hỗ trợ truy xuất và giải thích; không tự thay đổi yêu cầu thiết kế hoặc hợp đồng.

---

# Phụ lục A. Mẫu bảng tính vật liệu

<!-- chunk_id: boq-template -->

| STT | Mã công tác | Công tác | Khối lượng | Đơn vị | Mã vật liệu | Hao phí/đơn vị | Lượng theo định mức | Điều chỉnh mua sắm | Lượng đặt mua | Đơn giá tại nguồn | Vận chuyển và phí | Giá đến công trường | Thành tiền | Nguồn |
|---:|---|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | | | | | | | | | | | | | | |

# Phụ lục B. Mẫu bảng giả định

<!-- chunk_id: assumption-register -->

| ID | Giả định | Cơ sở | Ảnh hưởng nếu sai | Người xác nhận | Trạng thái |
|---|---|---|---|---|---|
| A-01 | | | Thấp/Trung bình/Cao | | Mở/Đã xác nhận |

# Phụ lục C. Mẫu bảng kiểm tra nguồn giá

<!-- chunk_id: price-source-checklist-table -->

| Trường | Giá trị |
|---|---|
| Tên vật liệu gốc | |
| Mã vật liệu chuẩn | |
| Quy cách | |
| Đơn vị | |
| Giá | |
| Thành phố/khu vực | |
| Thời điểm | |
| VAT | Có/Không/Không rõ |
| Vận chuyển | Có/Không/Không rõ |
| Cơ sở giá | Mỏ/Nhà máy/Đại lý/Công trường/Bình quân |
| Nguồn và trang | |
| Mức tin cậy | Cao/Trung bình/Thấp |
| Ghi chú | |


# Phụ lục D. Mẫu bảng metadata công văn công bố giá

<!-- chunk_id: official-dispatch-metadata-template -->

| Trường | Giá trị | Trang nguồn | Mức tin cậy |
|---|---|---:|---|
| Thành phố | | | |
| Số/ký hiệu công văn | | | |
| Cơ quan ban hành | | | |
| Ngày ban hành | | | |
| Kỳ công bố giá | | | |
| Phạm vi địa bàn | | | |
| VAT mặc định | Có/Không/Hỗn hợp/Không rõ | | |
| Vận chuyển mặc định | Có/Không/Hỗn hợp/Không rõ | | |
| Cơ sở giá mặc định | Mỏ/Nhà máy/Đại lý/Công trường/Bình quân/Hỗn hợp/Không rõ | | |
| Điều kiện áp dụng | | | |
| Cảnh báo pháp lý | | | |
| Số phụ lục | | | |
| Trang công văn | | | |
| Trang phụ lục | | | |

# Phụ lục E. Mẫu ánh xạ một dòng phụ lục PDF

<!-- chunk_id: official-annex-row-template -->

| Trường | Giá trị |
|---|---|
| `source_package_id` | |
| `source_document_number` | |
| `source_annex_id` | |
| `source_table_title` | |
| `source_page` | |
| `source_row_number` | |
| `material_name_raw` | |
| `material_id_normalized` | |
| `specification_raw` | |
| `unit_original` | |
| `price_original` | |
| `price_min` / `price_max` | |
| `supplier_or_producer` | |
| `source_location` | |
| `vat_included` | |
| `transport_included` | |
| `price_basis` | |
| `row_notes` | |
| `source_raw_text` | |
| `extraction_confidence` | |
| `review_status` | |

# Phụ lục F. Kiểm tra lỗi trích xuất PDF

<!-- chunk_id: pdf-extraction-validation -->

- Đối chiếu tổng số dòng trích xuất với số thứ tự dòng trong từng bảng.
- Kiểm tra các giá có số 0 bất thường do OCR nhầm `0`, `6`, `8`, dấu chấm hoặc dấu phẩy.
- Kiểm tra ô giá bị trôi sang dòng kế tiếp do ô nhiều dòng hoặc ô gộp.
- Kiểm tra đơn vị `kg`, `tấn`, `m³`, `m²`, `m`, `viên`, `bộ`, `cái`, `lít`, `bao` và các ký hiệu có chỉ số trên.
- Không kế thừa tên nhà sản xuất, địa bàn hoặc cơ sở giá từ dòng trước nếu bảng không thể hiện cấu trúc ô gộp rõ ràng.
- Lưu cả văn bản thô và giá trị chuẩn hóa để có thể truy ngược.
- Với bảng có nhiều cột địa bàn, mỗi ô giá phải trở thành một bản ghi riêng hoặc một mảng giá gắn đúng địa bàn.
- Với giá dạng khoảng, lưu `price_min` và `price_max`; không tự lấy trung bình nếu chưa có quy tắc nghiệp vụ.
- Với dấu gạch ngang, ô trống hoặc ký hiệu đặc biệt, phân biệt `không có giá`, `không áp dụng`, `chưa khảo sát` và `giá bằng 0`.
- Các dòng có độ tin cậy thấp phải đi vào hàng đợi kiểm tra, không được dùng tự động để tính chi phí.

# Phụ lục G. Mẫu cảnh báo tự động cho RAG

<!-- chunk_id: rag-warnings -->

- `WARNING_PRICE_BASIS_UNKNOWN`: chưa rõ giá tại nguồn hay tại công trường.
- `WARNING_VAT_UNKNOWN`: chưa rõ trạng thái thuế.
- `WARNING_SPEC_MISMATCH`: quy cách giá không khớp quy cách thiết kế.
- `WARNING_DATE_STALE`: dữ liệu giá quá cũ so với thời điểm ước lượng.
- `WARNING_WASTE_DOUBLE_COUNT`: nguy cơ cộng trùng hao hụt.
- `WARNING_UNIT_MISMATCH`: đơn vị khối lượng và đơn vị giá không khớp.
- `WARNING_PACKAGE_ROUNDING`: chưa làm tròn theo quy cách bán.
- `WARNING_TRANSPORT_DUPLICATED`: giá đã gồm vận chuyển nhưng vẫn cộng vận chuyển.
- `WARNING_TRANSPORT_MISSING`: giá tại nguồn chưa cộng vận chuyển.
- `WARNING_ESTIMATE_LEVEL_LOW`: dữ liệu thiết kế chưa đủ để đưa kết quả chi tiết.
- `WARNING_NO_STOCK_DEDUCTION`: chưa trừ tồn kho hoặc vật tư thu hồi.
- `WARNING_NO_ACCESS_CONDITION`: chưa xét điều kiện xe và bốc dỡ tại công trường.
- `WARNING_DISPATCH_METADATA_MISSING`: chưa trích được số công văn, kỳ giá hoặc cơ quan ban hành.
- `WARNING_ANNEX_ORPHAN_ROW`: dòng giá không liên kết được với phụ lục và công văn nguồn.
- `WARNING_PDF_OCR_LOW_CONFIDENCE`: giá hoặc quy cách được OCR với độ tin cậy thấp.
- `WARNING_FOOTNOTE_NOT_APPLIED`: chưa áp dụng chú thích chung của bảng hoặc cuối trang.
- `WARNING_MERGED_CELL_INHERITANCE`: giá trị kế thừa từ ô gộp chưa được xác minh.
- `WARNING_PRICE_RANGE_COLLAPSED`: giá dạng khoảng đã bị ép thành một giá duy nhất.
- `WARNING_PAGE_TRACE_MISSING`: bản ghi chưa có trang nguồn để truy vết.

# Kết luận

Ước lượng giá vật liệu đáng tin không bắt đầu từ bảng giá mà bắt đầu từ việc hiểu đúng cấu tạo công trình và phạm vi công tác. Bảng giá chỉ trở thành dữ liệu hữu ích sau khi được ghép đúng vật liệu, đúng quy cách, đúng thời điểm, đúng địa điểm và đúng điều kiện giao hàng. Khối lượng vật liệu chỉ trở thành lượng mua khi đã xử lý định mức, hao hụt, kế hoạch cắt, đóng gói, tồn kho và tiến độ.

Một hệ thống RAG chuyên sâu phải luôn giữ khả năng truy vết: con số khối lượng đến từ bản vẽ nào, hao phí từ định mức hoặc tài liệu nào, đơn giá từ công văn nào, phụ lục nào, bảng nào, dòng nào và trang nào; vận chuyển tính ra sao và giả định nào đang mở. Khi thiếu một mắt xích, hệ thống phải giảm mức tin cậy và yêu cầu dữ liệu bổ sung thay vì tạo ra một con số có vẻ chính xác nhưng không kiểm chứng được.
