# Đề xuất điều chỉnh glossary (dựa trên toàn bộ ch1–971, bản novelight)

> Mình chưa sửa gì trong `glossary.yaml` ngoài các mục bạn đã duyệt hôm 2026-10-06:
> - bỏ Hercules, Pantemonium;
> - thêm Gathering Wind, WizerView, One Flash.
>
> Bạn duyệt rồi báo mục nào đồng ý, mình sẽ áp dụng bằng script (có bản sao lưu), hoặc bạn tự sửa trong `python novel.py edit`.
> **Số chương theo novelight.** Đổi từ số novellunar cũ:
> - 1–510 giữ nguyên;
> - 511–754 thì trừ 1;
> - 755–828 ≈ 754–792 (`data/novellunar/map.json`).
>
> Ký hiệu: 🔴 nên sửa ngay (gây dịch sai) · 🟡 nên sửa · ⚪ tuỳ khẩu vị · 🆕 mới thêm từ phần ch754–971.
> Tên viết khác của người dịch mới (Atjie, Ospreet, Ridwi…) đã xử lý bằng `aliases.yaml`, không cần thêm vào glossary.

## A. Mục đang sai, thiếu hoặc gây hại

| | Mục | Hiện tại | Đề xuất | Lý do |
|---|---|---|---|---|
| 🔴 | `I-I'm` (nhan_vat) | "Tôi" | **Xoá** | Chữ nói lắp, không phải nhân vật |
| 🔴 | `Imperial` (to_chuc) | "Triều Đình Hoàng Gia" | **Xoá** | Là tính từ, khớp cả "Imperial Palace", "Imperial Knights" |
| 🔴 | `Being` (thuat_ngu) | "Sự tồn tại" | **Xoá** | Khớp mọi câu bắt đầu bằng "Being…" |
| 🔴 | `Divine` (thuat_ngu) | "Thánh Lực" | **Xoá** | Là tính từ |
| 🔴 | `Fron` (nhan_vat) | vi "Frondier" | vi **"Fron"** | Đang xoá mất biệt danh thân mật |
| 🔴 | `Mjölnir` | *thiếu* (≈280 lần) | Thêm vào vu_khi: "Mjölnir", ghi chú "búa của thần Thor" | Dạng viết "Mjolnir" của bản mới đã được gộp về Mjölnir |
| 🔴 | `Black Lotus` (vat_pham) | "Hắc Lệ" | **"Hắc Liên"** (hoặc "Sen Đen") | "Lệ" là nước mắt; sen là "Liên" |
| 🔴 🆕 | `Ecleksis` | *thiếu* (190 lần) | Thêm vào thuat_ngu: "Ecleksis", ghi chú "tên thật của sức mạnh trước đây bị coi là 'sức mạnh của quỷ'" | Khái niệm trung tâm của phần cuối |
| 🔴 🆕 | `Golden Apple` | *thiếu* (87) | Thêm vào vat_pham: "Táo Vàng" | Vật phẩm then chốt (Ahop, Aphrodite, giao kèo với Belphegor) |
| 🔴 🆕 | `Seven Deadly Sins` | *thiếu* (155) | "Bảy Tội Lỗi" hoặc "Thất Đại Tội" (mục D) | Hay gặp |
| 🔴 🆕 | `72 Demons` | *thiếu* (129) | "72 Quỷ" (ghi chú: 72 quỷ của Solomon) | Hay gặp |
| 🔴 🆕 | `King of Demons` / `Demon King` | *thiếu* (55) | "Vua Quỷ" hoặc "Ma Vương" (mục D) | Frondier tự xưng ở ch867 |
| 🔴 🆕 | `Paladin` / `Paladins` | *thiếu* (124) | "Paladin" hoặc "Thánh Kỵ Sĩ" (mục D) | Hiệp sĩ của vương quốc Palma |
| 🟡 🆕 | Địa danh và vật thần thoại mới | *thiếu* | Thêm, đa số giữ nguyên tên: Yggdrasil, Olympus, Asgard, Nastrond, Tartarus, Niflheim, Gleipnir, Naglfar, Bifrost, Aegis, Goetia, Astrape, Edrium, Palma, Ahop, "Nine", Machia | Bước `terms` đang lọc lại toàn bộ, sẽ có trong editor |
| 🟡 | `Pro` (thuat_ngu) | "Chuyên nghiệp giả" | **"Pro"** (ghi chú: người hành nghề diệt quái chuyên nghiệp) | "giả" dễ bị đọc thành "giả mạo" |
| 🟡 | `Pros` (nhan_vat, nam) | – | Chuyển sang thuat_ngu, vi "các Pro", bỏ giới tính | Là tên nghề |
| 🟡 | `Wordsmith` (danh_hieu) | "Ngôn ngữ giả" | Kiểm tra lại ngữ cảnh; tạm đề xuất "Bậc thầy ngôn từ" | Dễ đọc thành "giả mạo" |
| 🟡 | `Khryselakatos` (nhan_vat) | – | Chuyển sang **vu_khi** | Là vũ khí (bản mới viết 3 kiểu, đã gộp) |
| 🟡 | `Cassian` (nhan_vat, nam) | – | ghichu **"con ngựa thông minh (của Sybil)"**, ngoi3 **"nó"** | Là ngựa |
| 🟡 | `Kraken` (nhan_vat, nam) | – | ghichu "quái vật/linh hồn biển sâu, thành viên Indus", ngoi3 "hắn" | Không phải người |
| 🟡 | `Roach` (to_chuc) | vi "nhà Roach", gioitinh "nam" | vi **"Roach"**, bỏ gioitinh, giữ ghi chú gia tộc | Hay dùng làm họ → báo nhầm "thiếu thuật ngữ" |
| 🟡 | `Bartello` ghichu | "Bartello Tert, quốc vương" | **"Bartello Terst, Hoàng đế Đế quốc Terst, chồng Philly, cha Elysia, Sale, Aten"** | Là Hoàng đế (sai chính tả "Tert") |
| 🟡 | `Majesty the Empress` | "Nữ Hoàng Bệ Hạ" | **"Hoàng hậu Bệ hạ"** | Philly là hoàng hậu |
| 🟡 | `King` (danh_hieu) | "Quốc vương" | Giữ "Quốc vương" (vua Palma là vua thật); ghi chú Bartello: "bản Anh đôi khi gọi King, vẫn dịch Hoàng đế" | |
| 🟡 | `Shroud Knight Order` | "Đội Hiệp Sĩ Shround" | "Đội Hiệp Sĩ Shroud" | Lỗi chính tả |
| 🟡 | `Shepherds` và 3 mục cùng nhóm | "Lãnh đao" / "Lãnh đạo Manggot" | **"Người Chăn Cừu (Manggot)"** – cần bạn xác nhận | "Lãnh đao" sai chính tả |
| 🟡 | `Poseidon` (chung_toc) | "Poseidon (Thần Poseidon)" | Chuyển sang **nhan_vat**, vi "Poseidon", gioitinh nam | Là nhân vật; hiện cả chuỗi bị ép vào bản dịch |
| 🟡 | `Medusa` | "Mê Du Sa" | **"Medusa"** | Các tên thần thoại khác đều giữ nguyên |
| 🟡 | `Achaea` (dia_danh) | "Achaea" | Chuyển sang **to_chuc** (gia tộc), ghi chú "gia tộc của Aias; phu nhân là Eriboia" | Là gia tộc |
| 🟡 🆕 | `Isiah`, `Ayas`, `Pierrot`, `Akaia`, `Gather Wind`, `Gathering Wind Arrow` | – | Có thể **xoá** | Cách viết riêng của bản novellunar, không còn xuất hiện trong nguồn novelight |
| 🟡 | `Sylvania` | *thiếu* | Thêm vào dia_danh, ghi chú "thủ đô Đế quốc (có chỗ gọi Silvester)" | Cảnh trục xuất (ch741) |
| ⚪ | `Lady of the Lake` | "Quý cô hồ nước" | "Bà Chúa Hồ" hoặc "Nữ thần Hồ" | Tự nhiên hơn; xuất hiện lại khi Aster chém Zeus (ch877) |
| ⚪ | `Iron Wall` / `Iron Wall of the North` | "Thiết Vách (Phương Bắc)" | "Thiết Bích (Phương Bắc)" hoặc "Tường Thép (Phương Bắc)" | Danh hiệu của Enfer |
| ⚪ | `Human Sloth` | "Con-lười-người" | "Con Lười Hình Người" | Gạch nối đọc gượng |
| ⚪ | `Sloth` (chung_toc) | "Sloth (Sự Lười Biếng)" | vi "Sloth", ghi chú "biệt danh của Frondier và tội Lười Biếng của Belphegor/Astaroth" | Hiện cả chuỗi bị ép vào bản dịch |
| ⚪ | `Weaving` | "Sao chép" | Giữ nếu bạn muốn khớp tên truyện; nghĩa gốc là "Dệt" | Phần cuối nói nhiều về Weaving, Loki và "xưởng dệt" của Moirai, nên nghĩa "dệt" có vai trò |

## B. Ghi chú đề xuất cho nhân vật
Mỗi ghi chú ngắn, chỉ ghi điều giúp chọn giọng và xưng hô.

| Nhân vật | Ghi chú đề xuất |
|---|---|
| Frondier | nhân vật chính, người kể chuyện (xưng "tôi"), con thứ nhà Roach; bị gọi "Sloth"; giáo viên ở Atlas từ ch761; 🆕 tự xưng Vua Quỷ (ch867), hoá thành quỷ qua giao kèo với Belphegor (ch908); 🆕 ở ch950–952 gặp linh hồn "Frondier thật" (chủ cũ của thân xác) |
| Selena | tên thật Jei, cựu sát thủ Manggot; tùy tùng rồi đồng hành của Frondier; 🆕 Belphegor gọi cô là "Jei" |
| Aster | Aster Evans, nhân vật chính gốc của game; em trai Ellen; kỹ thuật One Flash; 🆕 chém Zeus (ch877), giáo viên tạm ở Atlas (ch882) |
| Azier 🆕 | Azier de Roach, anh trai Frondier; chết ở ch900, linh hồn ở Tartarus, được giải thoát ở ch970 |
| Sybil | bạn cùng lớp Frondier; năng lực may mắn/số phận; con gái Daud Forte; 🆕 á thần, mẹ ruột là nữ thần Idun (ch921), tự nhận là bạn gái Frondier (ch858) |
| Quinie | khoá trên của Frondier; điều hành thương hội Viet, chỉ huy đội tàu |
| Renzo | "Glutton of Chaos", kẻ thù rồi đồng minh bất đắc dĩ; 🆕 mang Ares trong người nhưng chống lại Ares, hạ Tyr (ch966) |
| Elysia | công chúa cả; từng làm hầu gái của Frondier (ch623–687); chỉ huy Shadow Unit từ ch688 |
| Lily | = Ria Lis, Zodiac, năng lực Charm; gọi Frondier là "chủ nhân" từ ch687 |
| Ria Lis | = Lily (cùng một người) |
| Sale | công chúa; bị Odin chiếm thân xác (ch731–733) |
| Marco / Marchosias | cùng một quỷ thuộc 72 quỷ; bị Frondier bắt giữ |
| Baal | quỷ mạnh nhất trong 72 quỷ; quy phục Frondier (ch679); 🆕 theo Frondier khi anh xưng Vua Quỷ (ch868) |
| Belphegor 🆕 | quỷ, tội Lười Biếng (Bảy Tội Lỗi); kẻ thù cũ thời Manggot; giao kèo với Frondier (ch907), giọng trịch thượng, trêu chọc |
| Lunia | Lunia Fricell, bạn cùng khoá, thân với Aster |
| Cain | **nữ, cháu gái Heldre, có năng lực bản sao/nhện; học sinh năm nhất Constel từ ch707** (để không lẫn với Esther) |
| Esther | **nữ, cai ngục nhà tù Morion, có năng lực tạo bản sao** (để không lẫn với Cain); 🆕 bắt Renzo (ch966) |
| Pielott | Pielott von Ribanche, đàn em của Frondier, nóng nảy; ở Atlas là học sinh; 🆕 được Hypnos ban sức mạnh |
| Dier | Dier Aiger, đàn em của Frondier, đầu óc chiến lược; 🆕 chỉ huy chiến lược trong đại chiến |
| Osprey | hiệu trưởng Constel, Zodiac, pháp sư cực mạnh; 🆕 cầm chân Zeus |
| Jane | giáo viên Constel, Zodiac |
| Ludwig | Ludwig von Urfa, lãnh chúa Tyburn, Zodiac; cha của Hector |
| Hector 🆕 | Hector von Urfa, giáo viên ở Atlas dưới tên "Hector Dutoit"; con của Ludwig |
| Ludovic | Zodiac; 🆕 mang Apollo trong người; dạy thay ở Atlas (ch915) |
| Monty | Monty Morgan, Zodiac; sư phụ của Frondier (từ ch695) |
| Arald | Arald Lemer, quỷ cổ (từng thấy Ragnarok), chủ tịch Hitchcock; theo Frondier sang Agoris |
| Gregory | cựu Indus, biến được thành quạ; đưa tin cho Frondier, liên hệ với Malia |
| Carla | Carla Ilse, hiệu trưởng Atlas; thực chất là Medusa; 🆕 từ khoảng ch845 có Athena trú trong thân xác |
| Giotto | giáo viên Atlas, bị Carla tống tiền để nghe lén |
| Basileo | học sinh Atlas, theo Frondier học phép thuật, gọi anh là "thầy"; 🆕 tạo ra Hellfire |
| Aias | học sinh Atlas, có thần lực, dùng giáo; con nhà Achaea; 🆕 đấu Hermes |
| Eriboia 🆕 | nữ, phu nhân nhà Achaea, mẹ Aias; quý tộc thù địch với Carla |
| Glaukos 🆕 | nam, học sinh năm nhất Atlas, sức mạnh vượt trội |
| Zenita | Zenita di Sandri, nữ sinh Atlas, thông minh, thích cá cược |
| Liberto | Liberto di Sandri, gia chủ nhà Sandri, cha Zenita |
| Antero | Paladin của Palma; kiêu ngạo, dựa vào cổ vật; bị quỷ Bune chiếm xác |
| Bune 🆕 | quỷ thuộc 72 quỷ; giao kèo với Antero qua sách Goetia |
| Charon 🆕 | Paladin của Palma; nhận thần lực từ "Poseidon" giả, giao kèo với Baal |
| Colin 🆕 | thương nhân bí mật ở thủ đô Palma, thuộc mạng lưới "Nine" |
| Evelina 🆕 | nữ, thủ lĩnh Ahop, đeo mặt nạ; dâng Táo Vàng |
| Heracles 🆕 | bán thần ở Agoris, mạnh khủng khiếp, nói chuyện cộc cằn; con trai là Telephos |
| Athena | nữ thần trí tuệ; trú trong thân xác Carla |
| Poseidon | thần biển (Poseidon thật bị giam ở biển; có kẻ giả danh Poseidon) |
| Aphrodite, Hera 🆕 | hai nữ thần đứng sau cuộc bầu chọn sắc đẹp ở Palma (người được chọn: Lupina, Bruna) |
| Zeus, Hermes, Apollo, Ares 🆕 | thần Olympus thù địch; Apollo trong Ludovic, Ares trong Renzo |
| Hestia 🆕 | nữ thần đứng về phía nhân loại, cứu Frondier ở Olympus |
| Vishnu, Rudra 🆕 | thần Ấn Độ; Vishnu nhập vào Elodie (ch844–847), Rudra can thiệp |
| Hypnos 🆕 | thần giấc ngủ, nói chuyện với Pielott trong mơ |
| Moirai 🆕 | ba nữ thần định mệnh, bị Frondier giết (ch940–944) |
| Loki, Idun, Jormungandr, Fenrir, Hela, Thor, Odin, Tyr, Baldur 🆕 | thần và quái vật Bắc Âu. Jormungandr được Sybil gọi thân là "Yor" |
| Sigurd, Arthur, Jeanne, Merlin 🆕 | anh hùng xưa (bị gọi là "người khổng lồ") đã lên kế hoạch triệu hồi người từ thế giới khác |
| Astaroth, Lazor, Paride, Purpur 🆕 | quỷ phe Satan/Astaroth (Lazor là thuộc hạ của Astaroth) |
| Durga | nữ thần (gioitinh: nữ), có giao kèo với Monty |
| Slevb | hồn ma (nữ) trong ngục tối đầu tiên |

## C. Xưng hô

### C1. Chỉnh quy tắc bạn đã có
| Cặp | Đề xuất | Lý do |
|---|---|---|
| Lily ↔ Frondier | **ch1–686** giữ như bạn đặt (`ta / cậu` · `tôi / cô`) · **ch687–** Lily: `tôi / chủ nhân`, Frondier: `tôi / cô` | Từ ch687 Lily gọi Frondier là "chủ nhân" |
| (nhân đôi cho `Ria Lis`) | Như trên | Quy tắc chỉ áp dụng khi tên đó xuất hiện |
| Azier ↔ Frondier 🆕 | Giữ `anh / em`; ghi chú cho model: ở ch900–970 Azier đã chết / là linh hồn | Không cần đổi xưng hô |

### C2. Cặp đề xuất thêm
Gợi ý dựa trên quan hệ và cách gọi mà lượt phân tích ghi nhận; giọng điệu là lựa chọn của bạn.

| Cặp | Đề xuất | Căn cứ |
|---|---|---|
| Frondier ↔ Philly | `tôi / Hoàng hậu` · `ta / cậu` | Frondier gọi "Your Majesty" |
| Frondier ↔ Bartello | `thần / Bệ hạ` · `ta / ngươi` | Bartello lạnh nhạt, ra lệnh |
| Frondier ↔ Elysia **ch1–609** | Frondier: `tôi / công chúa` · Elysia: `ta / ngươi` | Công chúa, đối địch |
| Frondier ↔ Elysia **ch610–687** | Frondier: `tôi / cô` · Elysia: `tôi / anh` | Thường dân, rồi hầu gái |
| Frondier ↔ Elysia **ch688–** | Frondier: `tôi / công chúa` · Elysia: `tôi / anh` | Trở lại làm công chúa nhưng đã thân hơn |
| Pielott → Frondier | **ch386–396** `tôi / anh` · **ch397–** `tôi / tiền bối` (xem D5) | Đầu gọi "Sloth" thô lỗ, sau gọi "senior" |
| Frondier → Pielott, Frondier → Dier | `tôi / cậu` | Khoá trên – khoá dưới |
| Dier → Frondier | `em / tiền bối` | Gọi "Senior" |
| Học sinh Atlas → Frondier (Basileo, Aias, Zenita, Glaukos) | `em / thầy` · Frondier: `thầy / em` | Basileo gọi "Teacher"; Frondier là giáo viên từ ch761 |
| Học sinh Atlas ↔ Elodie | `em / cô` · Elodie: `cô / em` | Elodie là giáo viên |
| 🆕 Học sinh Atlas ↔ Aster (ch882–) | `em / thầy` · Aster: `thầy / em` | Aster dạy thay |
| 🆕 Pielott ↔ Aias | `tôi / cậu` (hai chiều) | Bạn học, đối thủ |
| Frondier ↔ Carla | Frondier: `tôi / hiệu trưởng` · Carla: `tôi / anh` | Frondier gọi "Principal"; ghi chú: từ khoảng ch845 lời Carla có thể là Athena |
| Frondier ↔ Giotto | `tôi / anh` (hai chiều) | Đồng nghiệp; Giotto gọi "Professor" |
| Frondier ↔ Liberto | Frondier: `tôi / ngài` · Liberto: `ta / cậu` | Gia chủ quý tộc |
| Frondier ↔ Eriboia | Frondier: `tôi / phu nhân` · Eriboia: `ta / ngươi` | Quý tộc thù địch |
| Frondier ↔ Antero | Frondier: `tôi / anh` · Antero: `ta / ngươi` | Paladin kiêu ngạo, thô lỗ |
| 🆕 Frondier ↔ Charon | Frondier: `tôi / anh` · Charon: `ta / ngươi` | Paladin thù địch |
| 🆕 Frondier ↔ Belphegor | Frondier: `tôi / ông` · Belphegor: `ta / ngươi` | Đối tác giao kèo, Belphegor trịch thượng |
| 🆕 Belphegor ↔ Selena | Belphegor: `ta / ngươi` · Selena: `tôi / ông` | |
| Frondier ↔ Baal | **ch1–866** Frondier: `tôi / ông` · Baal: `ta / ngươi` · 🆕 **ch868–** Baal: `tôi / ngài` | Từ ch868 Baal theo "Vua Quỷ" |
| 🆕 Quỷ thuộc hạ → Frondier (ch867–) | `thần / bệ hạ` hoặc `tôi / ngài` (mục D) | Frondier xưng Vua Quỷ |
| Frondier ↔ Marco | Frondier: `tôi / anh` · Marco: `tôi / cậu` | Bị bắt giữ, dè chừng |
| 🆕 Frondier ↔ Heracles | Frondier: `tôi / ngài` · Heracles: `ta / ngươi` | Frondier gọi "Lord Heracles"; Heracles cộc cằn |
| Frondier ↔ Poseidon | Frondier: `tôi / ngài` · Poseidon: `ta / ngươi` | Thần với người phàm |
| Frondier ↔ Athena | Frondier: `tôi / cô` · Athena: `ta / ngươi` | Hai bên ngang hàng, không kiêng nể |
| 🆕 Frondier ↔ Aphrodite, Hestia | Frondier: `tôi / ngài` · nữ thần: `ta / ngươi` (Hestia: `ta / con`?) | Hestia hiền từ, che chở |
| 🆕 Frondier ↔ thần thù địch (Thor, Zeus, Moirai, Hela, Satan) | `ta / ngươi` (hai chiều) | Đối đầu; Frondier có lúc gọi Moirai là "mụ già" |
| 🆕 Sybil ↔ Jormungandr | Sybil: `tôi / ông` · Jormungandr: `ta / cô` | Sybil gọi "Mr. Jormungandr" |
| 🆕 Aster ↔ Ludovic | Aster: `tôi / ngài` · Ludovic: `ta / cậu` | Zodiac – Aster |
| 🆕 Aster ↔ Renzo, Renzo ↔ Ares/Tyr | `ta / ngươi` (hai chiều) | Thù địch, khiêu khích |
| 🆕 Osprey ↔ Elodie | Osprey: `ta / em` · Elodie: `em / thầy` | Hiệu trưởng – học trò cũ |
| 🆕 Vishnu → Elodie | `ta / ngươi` | Thần chiếm xác, trịch thượng |
| Aster ↔ Lunia | `tớ / cậu` (hai chiều) | Bạn thân cùng khoá |
| Frondier ↔ Sylvain | Frondier: `tôi / chỉ huy` · Sylvain: `tôi / cậu` | Lễ phép hai chiều |
| Frondier ↔ Renzo | `ta / ngươi` (hai chiều) | Thù địch, khiêu khích |
| Frondier ↔ Mei | Frondier: `anh / em` · Mei: `em / anh` | Frondier dạy dỗ, che chở |
| Frondier ↔ Gregory | Frondier: `tôi / ông` · Gregory: `tôi / cậu` | |
| Frondier ↔ Esther | Frondier: `tôi / cô` · Esther: `tôi / cậu` | |
| Frondier ↔ Cain | Frondier: `tôi / cô` · Cain: `tôi / anh` (hoặc `tôi / tiền bối` từ ch707) | |
| Frondier ↔ Laurie | Frondier: `tôi / cô` · Laurie: `tôi / cậu` | |
| Frondier ↔ Binkis, Frondier ↔ Jane | Frondier: `em / cô` · Binkis, Jane: `cô / em` | Thầy trò |
| Frondier ↔ Ludwig | Frondier: `tôi / ngài` · Ludwig: `ta / cậu` | |
| Frondier ↔ Monty | Frondier: `tôi / ngài` (hoặc `con / sư phụ` từ ch695) · Monty: `ta / cậu` | Thầy – đệ tử |
| Frondier ↔ Arald | Frondier: `tôi / ông` · Arald: `tôi / cậu` | Arald lễ phép với Frondier |
| Frondier ↔ Kora, Eden, Hagley, Ameline | như bản trước (Kora `tôi / cậu`·`tôi / anh`; Eden, Hagley `tôi / ông`·`ta / cậu`; Ameline `tôi / tiểu thư`·`tôi / ngài`) | |
| Selena → Hagley | **ch1–541** `tôi / ngài` · **ch542–** `tôi / ông` | |
| Hagley → Selena | `ta / con` | Cha nuôi/thầy |
| Gia đình | Aster–Ellen `em / chị`; Elodie–Revet `em / anh`; Aten–Elysia, Sale `em / chị`; Philly–các con `mẹ / con`; Enfer–Malia `anh / em`; Malia–Azier `mẹ / con` | |
| Philly ↔ Bartello | Philly: `thiếp / Bệ hạ` (hoặc `em / anh`) · Bartello: `ta / nàng` | Tuỳ giọng (D2) |

## D. Còn chờ bạn quyết
1. Cách dịch "Shepherds" của Manggot.
2. Giọng xưng hô trong hoàng tộc: kiểu cổ (`trẫm / khanh`, `thiếp`) hay hiện đại hơn (`ta / ngươi`, `em / anh`).
3. Có dịch "Zodiac" hay giữ nguyên.
4. "Medusa": giữ nguyên hay "Mê Du Sa"; tương tự với các tên thần thoại khác.
5. Pielott ở Atlas (từ ch761) là học sinh của Frondier: giữ `tôi / tiền bối` hay đổi sang `em / thầy`.
6. 🆕 "King of Demons / Demon King": **"Vua Quỷ"** hay **"Ma Vương"**; quỷ thuộc hạ gọi Frondier là `bệ hạ` hay `ngài`.
7. 🆕 "Seven Deadly Sins": "Bảy Tội Lỗi" hay "Thất Đại Tội". "Paladin": giữ nguyên hay "Thánh Kỵ Sĩ".
8. 🆕 Các tên còn chờ trong `aliases.yaml`:
   - "Nakjang": kỹ thuật của Azier, gộp với "Falling" hay "Fallen Spear"?
   - "Aetius": đổi thành "Etius" (cùng tên game) hay giữ?
