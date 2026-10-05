# Dịch truyện offline

Tải bản tiếng Anh, dịch sang tiếng Việt bằng model chạy trên máy (Ollama), rồi xuất EPUB/TXT.
Ngoài việc tải trang truyện, không có gì được gửi ra ngoài.

## Cần có
- Python 3.11+ với `requests`, `beautifulsoup4`, `lxml`, `pyyaml` (máy hiện tại đã có đủ).
- Ollama đang chạy và đã tải model. Model mặc định là `gemma3:12b` (`ollama pull gemma3:12b`).

## Quy trình

1. **Tải truyện**: `python novel.py scrape`
   Tải tiếp các chương còn thiếu đến hết truyện. Chạy lại khi truyện ra chương mới.
2. **Làm glossary**
   - `python novel.py terms` tạo `glossary_draft.yaml`. Script tìm mọi tên riêng (cụm viết hoa giữa câu, cụm trong `[ ]`),
     rồi model phân loại thành nhân vật / địa danh / tổ chức / vũ khí / kỹ năng / vật phẩm / chủng tộc / danh hiệu / thuật ngữ.
     Với nhân vật, model đoán thêm giới tính dựa vào đại từ he/she đứng sau tên. Mỗi mục có gợi ý bản dịch và mô tả ngắn.
   - Cuối file nháp là danh sách các cặp nhân vật hay đối thoại với nhau, để bạn điền xưng hô.
   - Kết quả phân loại được cache. Chạy lại sau khi tải thêm chương thì chỉ những tên mới được phân loại.
     Thêm `--no-llm` nếu chỉ cần danh sách thô, `--min 5` để bỏ các tên hiếm.
   - **Duyệt bằng công cụ**: `python novel.py edit` mở trang chỉnh sửa trên trình duyệt (Ctrl+C trong terminal để tắt).
     Các cách viết khác nhau của cùng một thứ được gom vào một nhóm (Empire / Terst Empire, Shadow Transfer / Shadow Transference,
     Ameline / Amelie...). Tab "Xưng hô" có danh sách cặp nhân vật để bấm thêm quy tắc. Lưu (Ctrl+S) sẽ ghi đè `glossary.yaml`,
     bản trước được giữ ở `glossary.yaml.bak`. Cũng có thể sửa tay `glossary.yaml`, hướng dẫn nằm ở đầu file.
   - Sửa `style.md` để chỉnh văn phong và ngôi kể.
3. **Dịch thử** vài chương để kiểm tra glossary đã có tác dụng chưa: `python novel.py translate 1-10 --force`.
   Muốn so sánh với model khác thì dịch cùng chương bằng `--model <tên>`, rồi chạy
   `python novel.py compare 1 --models gemma3:12b,<tên>` và mở `output/so-sanh_chuong-0001.html` để đọc song song.
4. **Dịch toàn bộ**: `python novel.py translate`
   Có thể dừng bất cứ lúc nào bằng Ctrl+C. Chạy lại lệnh thì chương nào xong rồi sẽ được bỏ qua.
5. **Kiểm tra**: `python novel.py status`
   Lệnh này liệt kê các chương có đoạn cần xem lại, tức đoạn chưa dịch hoặc thiếu thuật ngữ.
   Lý do model phải thử lại được ghi ở `data/vi/<model>/_log.txt`.
6. **Xuất sách**: `python novel.py export --format epub`
   Thêm `--bilingual` để kèm câu gốc tiếng Anh dưới mỗi đoạn. Có thể giới hạn chương, ví dụ `export 1-100`.

## Đọc trên web (`../web`)
App đọc truyện dạng trang tĩnh, lật trang kiểu Google Play Books, không cần build.
1. `python novel.py web` chép các chương đã dịch sang `../web/books/<slug>/`. Chạy lại mỗi khi dịch thêm chương.
   Chương nào dịch từ bản tải cũ có dấu `"`/`]` bị tách thành đoạn riêng thì được gộp lại khi xuất.
2. Xem thử trên máy: `python -m http.server 8080 --directory web` (chạy ở thư mục gốc), rồi mở `http://localhost:8080`.
   Phải mở qua server: mở thẳng file `index.html` thì trình duyệt sẽ chặn việc tải chương.
3. Đưa lên GitHub Pages: đẩy nội dung thư mục `web/` lên một repo, vào Settings → Pages, chọn nhánh và thư mục gốc.
   Lưu ý: trang GitHub Pages là công khai, ai có link cũng đọc được.

Cách dùng: chạm mép phải/trái hoặc vuốt để lật trang, chạm giữa để hiện thanh công cụ (mục lục, tuỳ chỉnh chữ, giao diện,
kiểu lật trang, song ngữ). Trên máy tính dùng phím mũi tên, Space hoặc con lăn chuột.
Vị trí đọc và tuỳ chỉnh được lưu trong trình duyệt của từng máy.

## Kính ngữ, chức danh và mục trùng
- **Kính ngữ** (Lord, Miss, Senior, -nim, -ssi, -sunbae...) nằm ở mục `kinh_ngu`, tách khỏi tên: "Senior Ellen" được tính
  cho "Senior" và "Ellen", "Frondier-nim" cho "-nim" và "Frondier". Khi dịch, chúng được gửi kèm như *hướng dẫn cách gọi*,
  nên có thể ghi nhiều lựa chọn, ví dụ `ngài / anh / chị (tùy quan hệ)`; model chọn theo quan hệ hoặc lược bỏ.
- **Chức danh** (Professor, Teacher, Librarian, Zodiac...) nằm ở `danh_hieu` với một bản dịch cố định để thống nhất cả bộ.
  Chức danh riêng của truyện khai báo trong `config.yaml` → `terms.extra_titles`, để "Zodiac Monty" được tách thành "Zodiac" + "Monty".
- **Mục trùng** (Empire / Terst Empire, Shadow Unit / Empire Shadow Unit): giữ cả hai nếu cả hai thật sự xuất hiện,
  nhưng dịch thống nhất (Đế quốc / Đế quốc Terst). Bản viết sai chính tả của bản dịch Anh (Amelie, Mizonus...) thì cho cùng
  bản dịch với tên đúng hoặc bỏ tick.

## Xưng hô thay đổi theo ngữ cảnh
Quy tắc xưng hô là cách gọi **mặc định**, không bắt buộc. Model được đổi khi cảnh rõ ràng cần (riêng tư thân mật,
gọi biệt danh, giận dữ, nơi trang trọng) và giữ nhất quán trong cảnh đó. Muốn model nhận ra sự thân mật thì:
- ghi quan hệ vào `ghichu` của nhân vật (vd "bạn từ thuở nhỏ của Frondier");
- thêm biệt danh vào glossary với ghi chú, vd `Fron` → "biệt danh thân mật của Frondier".

Cặp nào quá thất thường thì xoá quy tắc, model sẽ tự chọn từng cảnh (đổi lại có thể thiếu nhất quán giữa các chương).

## Model biết gì khi dịch một khối
Model không có trí nhớ giữa các lần gọi. Mỗi lần nó chỉ thấy những gì được gửi kèm:
- **Khối đang dịch**: tối đa 60 đoạn, thường là trọn một cảnh. Trong khối, model tự theo dõi được ai nói với ai
  nhờ lời dẫn ("she said") và đại từ he/she của bản tiếng Anh.
- **Ngữ cảnh ngay trước**: vài đoạn cuối của khối trước, gồm cả câu gốc lẫn bản đã dịch, để giữ cách xưng hô đã chọn.
  Khối đầu chương thì nhận vài đoạn cuối của chương trước.
- **Glossary**: các nhân vật có mặt trong chương (kèm giới tính, ngôi thứ 3, ghi chú) và quy tắc xưng hô
  cho những cặp cùng xuất hiện. Đây là phần "trí nhớ dài hạn" duy nhất của model.
  Một nhân vật nữ mà không có trong glossary thì ở cảnh không có "she", model chỉ đoán được giới tính.

## Sửa glossary khi đã dịch một phần
Sửa `glossary.yaml` hoặc `style.md`, rồi chạy `python novel.py translate 1-200 --force`.
Mỗi khối đoạn được cache theo đúng prompt đã gửi. Khối nào có prompt không đổi sẽ lấy lại từ cache ngay,
chỉ những khối chứa thuật ngữ vừa sửa mới bị dịch lại.
Riêng `style.md` và các nhân vật chính (xuất hiện ở mọi chương) thì nằm trong mọi prompt, nên sửa chúng sẽ phải dịch lại gần hết.
Vì vậy nên chốt hai phần này trước khi dịch toàn bộ.

## Thư mục
| Đường dẫn | Nội dung |
|---|---|
| `data/en/0001.json` | bản tiếng Anh, mỗi chương một file |
| `data/vi/<model>/0001.json` | bản dịch; mỗi đoạn có cả `en` và `vi`, nên app Godot đọc thẳng được |
| `data/cache/` | cache từng khối; giữ lại để dịch lại cho nhanh |
| `output/` | EPUB, TXT, HTML so sánh |
| `../web/` | app đọc truyện trên web; `books/` do lệnh `web` tạo ra |

Thư mục này có file `.gdignore` để Godot không import hàng nghìn file JSON.
App Godot muốn đọc bản dịch thì dùng `FileAccess` với đường dẫn tuyệt đối, hoặc copy `data/vi/<model>/` vào project.

## Tham số đáng chỉnh (`config.yaml`)
- `translate.chunk_chars` / `chunk_paragraphs`: khối to thì ít lượt gọi, ngữ cảnh rộng hơn, nhưng model nhỏ dễ gộp hoặc bỏ đoạn hơn.
  Khối bị lỗi sẽ tự chia đôi rồi dịch lại.
- `llm.temperature`: 0.2–0.4 cho bản dịch ổn định.
- `llm.workers`: chỉ có tác dụng khi Ollama được chạy với biến môi trường `OLLAMA_NUM_PARALLEL` ≥ số này.
  Với cấu hình mặc định, các yêu cầu được xử lý lần lượt.
