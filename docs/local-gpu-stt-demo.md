# Chạy lại STT qua GPU máy này cho demo (đã cài sẵn)

Máy này (`khai-D520MT`) đã cài xong `local-gpu-stt/` — không cần cài lại gì,
chỉ cần bật lại 2 tiến trình mỗi lần demo. Xem `local-gpu-stt/README.md`
nếu cần cài lại từ đầu trên máy khác.

## Điều quan trọng cần nhớ trước

**Ngrok free KHÔNG tồn tại vĩnh viễn.** URL chỉ sống trong lúc tiến trình
`ngrok http` đang chạy. Tắt terminal / tắt máy / restart máy → URL mất,
lần bật lại ra **URL random hoàn toàn khác**. Nghĩa là **mỗi lần demo**
(kể cả cùng ngày, chỉ là tắt bật lại) đều phải làm lại đủ 4 bước dưới đây,
không có cách nào "chạy 1 lần dùng mãi" trừ khi nâng cấp ngrok trả phí để
có static domain cố định (xem cuối file).

## Quy trình demo (mỗi lần)

### Terminal 1 — chạy server GPU

```bash
cd ~/Desktop/agentic-rag/local-gpu-stt
source .venv/bin/activate

export LD_LIBRARY_PATH="/home/khai06/miniconda3/envs/khai-env/lib/python3.11/site-packages/nvidia/cudnn/lib:$LD_LIBRARY_PATH"

WHISPER_MODEL_SIZE=phowhisper-base STT_SECRET=matkhau-tuychon python server.py
```

Đang dùng **PhoWhisper base** (fine-tune tiếng Việt của VinAI) thay vì
Whisper gốc — chính xác hơn cho tiếng Việt. Lần đầu chạy sẽ tự tải bản
CTranslate2 convert sẵn từ `quocphu/PhoWhisper-ct2-FasterWhisper` (vài
trăm MB), các lần sau dùng cache, không tải lại.

Đợi đến khi thấy dòng:
```
Model loaded — ready
```
(nếu model đã tải từ trước ở `~/.cache/huggingface`, bước này chỉ mất vài giây, không phải tải lại).

Kiểm tra nhanh (terminal khác, không tắt terminal 1):
```bash
curl http://localhost:8001/health
```

### Terminal 2 — chạy ngrok

```bash
ngrok http 8001
```

Copy dòng `Forwarding` — dạng:
```
https://xxxx-xx-xx-xx-xx.ngrok-free.app -> http://localhost:8001
```

### Cập nhật Railway (mỗi lần URL đổi)

Vào Railway → service `agentic-rag` (backend) → tab **Variables** → sửa:
```
STT_BACKEND=http
STT_HTTP_URL=https://xxxx-xx-xx-xx-xx.ngrok-free.app   ← URL vừa copy
STT_HTTP_SECRET=matkhau-tuychon                         ← phải khớp STT_SECRET ở Terminal 1
```
Save → backend tự redeploy (mất khoảng 30-60s).

### Test

Vào link frontend Railway → bấm mic 🎙️ trong ô chat → nói thử → thả ra →
xem có tự chuyển thành text và gửi không.

## Sau khi demo xong

`Ctrl+C` ở cả 2 terminal để tắt server + ngrok — không bắt buộc (không tốn
gì nếu để chạy), nhưng nếu tắt thì lần sau nhớ làm lại từ đầu quy trình ở
trên (kể cả không restart máy, chỉ cần tắt 2 tiến trình này là đã mất URL).

## Nếu muốn URL cố định, không phải sửa Railway mỗi lần

Nâng cấp gói ngrok trả phí (~$8-10/tháng bản rẻ nhất có static domain) →
đặt 1 domain cố định, ví dụ `myproject.ngrok-free.app` hoặc domain riêng →
chạy `ngrok http --domain=<domain-cố-định> 8001` → domain không đổi giữa
các lần chạy → chỉ cần set `STT_HTTP_URL` trên Railway **đúng 1 lần duy
nhất**, không cần sửa lại nữa (server ở Terminal 1 vẫn phải bật mỗi lần
demo, chỉ URL là cố định).
