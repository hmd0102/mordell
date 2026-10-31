# mordell — S-box động từ đường cong Mordell & mã hóa ảnh

Sinh S-box động từ đường cong Mordell trên GF(2⁸), dùng S-box đó trong AES-256 để
mã hóa ảnh (CBC/ECB), kèm bộ đánh giá chất lượng S-box và ảnh mã hóa. Có cả CLI và
giao diện PyQt6.

## Cài đặt

Yêu cầu Python ≥ 3.9 (numpy, pillow, pyqt6, matplotlib):

```
pip install -r requirements.txt
```

## Lệnh chính

| Việc | Lệnh |
|---|---|
| Kiểm thử (25 test) | `python main.py selftest` |
| Mã hóa ảnh | `python main.py encrypt data/images/lena.png lena_enc.png --key "khoa-bi-mat"` |
| Giải mã ảnh | `python main.py decrypt lena_enc.png lena_dec.png --key "khoa-bi-mat"` |
| In bảng S-box từ khóa | `python main.py sbox --key "khoa-A"` |
| S-box theo đa thức | `python main.py sbox --poly 283` |
| Đánh giá một S-box | `python main.py eval-sbox --key "khoa-bi-mat"` |
| So sánh với 3 S-box tham chiếu | `python main.py compare` |
| Đánh giá một ảnh | `python main.py eval-image data/images/lena.png` |
| Thực nghiệm chương 3 | `python -m experiments.chapter3` |
| Mở giao diện | `python ui.py` |

Giải mã đọc `cipher_mode` từ tệp `.meta` đi kèm (tệp cũ mặc định CBC). ECB không dùng
IV và làm lộ cấu trúc ảnh nên chỉ dùng để minh họa.

## Giao diện

5 tab: **Trang chủ** · **Mã hóa & Giải mã ảnh** · **Đánh giá S-box** ·
**So sánh S-box** · **Đánh giá ảnh mã hóa**.

- Mã hóa/giải mã với CBC hoặc ECB, xem trước ảnh, tự đối chiếu ảnh gốc sau khi giải mã.
- Đánh giá S-box: bảng 16×16 (hex/thập phân), sao chép TSV; so sánh 4 S-box kèm biểu đồ.
- Đánh giá ảnh: entropy, tương quan (ngang/dọc/chéo), GLCM, NPCR/UACI, histogram,
  ECB vs CBC, độ nhạy.
- Tác vụ nặng chạy nền (QThread) với thanh tiến trình và nút Huỷ.
- Xuất báo cáo TXT/CSV/JSON, nút Mở thư mục; giao diện mở maximized.
- Phím tắt: `F11` toàn màn hình, `Esc` thu nhỏ, `F1` danh sách phím tắt, `Ctrl+H` Trang chủ.
- Logo/banner tab Trang chủ: đặt `gui/assets/logo_truong.png` và `gui/assets/banner.png`;
  thông tin đề tài sửa trong `gui/tabs/home_tab.py`.

## Cấu trúc

```
main.py             CLI
ui.py               điểm vào GUI
gui/                giao diện PyQt6 (tabs, widgets, theme, export, workers)
core/               GF(2⁸), Mordell, S-box, AES-256, CBC/ECB, mã hóa ảnh
metrics/            NL, SAC, BIC, LAP, DAP; entropy, NPCR, UACI, PSNR...
reference/          3 S-box tham chiếu (AES, Weierstrass, hỗn loạn)
experiments/        ví dụ chương 2, thực nghiệm chương 3
tests/              kiểm thử tự động (unittest)
data/images/        ảnh thử (lena, baboon)
```

## Kết quả & kiểm thử

- `python -m experiments.chapter3` sinh số liệu JSON và 8 hình vào `results/chapter3/`
  (thư mục này nằm trong `.gitignore`).
- `python main.py selftest` hoặc `python -m unittest discover -s tests`: 25 test.
