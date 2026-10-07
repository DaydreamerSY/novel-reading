"""Dịch truyện offline: tải bản tiếng Anh → dịch bằng model local (Ollama) → xuất EPUB/TXT.

  python novel.py scrape                 tải tiếp các chương còn thiếu đến hết truyện
  python novel.py scrape --source novelight  tải các chương miễn phí từ novelight.net (đa luồng)
  python novel.py source                 dựng data/en từ bản novelight (đổi tên theo aliases.yaml)
  python novel.py terms                  liệt kê tên riêng + model phân loại → glossary_draft.yaml
  python novel.py edit                   công cụ chỉnh glossary trên trình duyệt (gom mục trùng)
  python novel.py analyze                đọc trước toàn truyện: tóm tắt, bối cảnh, quan hệ → story/tom_tat/
  python novel.py translate 1-5          dịch các chương 1..5 (bỏ qua chương đã dịch)
  python novel.py compare 1 --models a,b so sánh bản dịch của nhiều model (HTML)
  python novel.py merge 610-612          ghép bản dịch của 2 model, model thứ ba phân xử đoạn khác nhau
  python novel.py polish 610-612         model lớn chỉ sửa xưng hô / đại từ trên bản dịch có sẵn
  python novel.py audit 610-612 --models a,b  soát xưng hô của các bản dịch theo glossary và ngu_canh.yaml
  python novel.py status                 tiến độ và các chương cần xem lại
  python novel.py export --format epub   xuất sách
  python novel.py web                    xuất cho app đọc truyện trên web (../web)
"""
import argparse
import itertools

from common import Paths, available, chapter_path, fmt_duration, load_config, parse_range, read_json, utf8_console


def cmd_scrape(cfg, paths, args):
    if args.source == "novelight":
        from novelight import scrape as scrape_novelight
        scrape_novelight(cfg, paths, parse_range(args.range, []) if args.range else None, args.workers, args.force)
        return
    from scraper import scrape
    if args.range:
        scrape(cfg, paths, parse_range(args.range, []), open_ended=False, force=args.force)
    else:
        scrape(cfg, paths, itertools.count(1), open_ended=True, force=args.force)


def cmd_source(cfg, paths, args):
    from novelight import build_source
    build_source(cfg, paths)


def cmd_terms(cfg, paths, args):
    from entities import build_draft
    chapters = parse_range(args.range, available(paths.en))
    build_draft(cfg, paths, chapters, args.model or cfg["llm"]["model"], args.min, not args.no_llm)


def cmd_analyze(cfg, paths, args):
    from analyzer import report, run
    if args.report:
        report(cfg, paths)
    else:
        run(cfg, paths, parse_range(args.range, available(paths.en)), args.model or cfg["llm"]["model"], args.force)


def cmd_edit(cfg, paths, args):
    from editor import serve
    serve(args.port, not args.no_browser)


def cmd_translate(cfg, paths, args):
    from translator import run
    model = args.model or cfg["llm"]["model"]
    workers = args.workers or int(cfg["llm"].get("workers", 1))
    run(cfg, paths, parse_range(args.range, available(paths.en)), model, workers, args.force, args.no_cache)


def cmd_merge(cfg, paths, args):
    from selector import run
    models = [m.strip() for m in args.models.split(",")] if args.models else None
    run(cfg, paths, parse_range(args.range, available(paths.en)), models, args.judge, args.name,
        False if args.no_reasons else None)


def cmd_polish(cfg, paths, args):
    from polish import run
    run(cfg, paths, parse_range(args.range, available(paths.en)), args.model, args.source, args.name)


def cmd_audit(cfg, paths, args):
    from audit import run
    run(cfg, paths, parse_range(args.range, []), [m.strip() for m in args.models.split(",") if m.strip()])


def cmd_compare(cfg, paths, args):
    from exporter import compare
    compare(paths, int(args.chapter), [m.strip() for m in args.models.split(",") if m.strip()])


def cmd_status(cfg, paths, args):
    model = args.model or cfg["llm"]["model"]
    en, vi = available(paths.en), available(paths.vi(model))
    print(f"Bản tiếng Anh: {len(en)} chương" + (f" ({en[0]}-{en[-1]})" if en else ""))
    print(f"Đã dịch bằng {model}: {len(vi)} chương")
    flagged, secs = [], []
    for n in vi:
        ch = read_json(chapter_path(paths.vi(model), n))
        k = sum(1 for p in ch["paragraphs"] if p.get("flags"))
        if k:
            flagged.append((n, k))
        if ch["stats"]["llm_calls"]:
            secs.append(ch["stats"]["seconds"])
    left = len(set(en) - set(vi))
    if secs and left:
        print(f"Trung bình {sum(secs) / len(secs):.0f}s/chương → còn {left} chương ≈ "
              f"{fmt_duration(sum(secs) / len(secs) * left)} (1 luồng)")
    if flagged:
        print(f"{len(flagged)} chương có đoạn cần xem lại (chương: số đoạn):")
        print("  " + ", ".join(f"{n}: {k}" for n, k in flagged[:60]) + (" ..." if len(flagged) > 60 else ""))
        print("  Xem chi tiết bằng: python novel.py compare <chương> --models " + model)


def cmd_export(cfg, paths, args):
    from exporter import export
    model = args.model or cfg["llm"]["model"]
    chapters = parse_range(args.range, []) if args.range else None
    export(cfg, paths, model, chapters, args.format, args.bilingual)


def cmd_web(cfg, paths, args):
    from webexport import export_web
    model = args.model or cfg["llm"]["model"]
    export_web(cfg, paths, model, parse_range(args.range, []) if args.range else None)


def main():
    utf8_console()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scrape", help="tải chương tiếng Anh")
    s.add_argument("range", nargs="?", help="vd 1-50; bỏ trống = tải tiếp đến hết truyện")
    s.add_argument("--force", action="store_true",
                   help="tải lại cả chương đã có (novelight: dựng lại từ data/cache/novelight, không tải lại)")
    s.add_argument("--source", choices=["novellunar", "novelight"], default="novellunar",
                   help="novelight: lưu vào data/en_novelight, đánh số theo thứ tự đọc (0001 = Prologue)")
    s.add_argument("--workers", type=int, help="số luồng tải song song (novelight; mặc định trong config.yaml)")
    s.set_defaults(fn=cmd_scrape)

    s = sub.add_parser("source", help="dựng data/en từ data/en_novelight, đổi tên theo aliases.yaml")
    s.set_defaults(fn=cmd_source)

    s = sub.add_parser("terms", help="liệt kê tên riêng, model phân loại → glossary_draft.yaml")
    s.add_argument("range", nargs="?", help="vd 1-50; mặc định tất cả chương đã tải")
    s.add_argument("--min", type=int, default=3, help="số lần xuất hiện tối thiểu (mặc định 3)")
    s.add_argument("--model", help="model phân loại; mặc định llm.model trong config.yaml")
    s.add_argument("--no-llm", action="store_true", help="chỉ dùng script, không phân loại bằng model")
    s.set_defaults(fn=cmd_terms)

    s = sub.add_parser("analyze", help="đọc từng chương, ghi tóm tắt / bối cảnh / quan hệ → story/tom_tat/*.md")
    s.add_argument("range", nargs="?", help="vd 288-308; mặc định tất cả chương đã tải")
    s.add_argument("--model", help="ghi đè llm.model trong config.yaml")
    s.add_argument("--force", action="store_true", help="phân tích lại cả chương đã có")
    s.add_argument("--report", action="store_true", help="chỉ tạo lại các file .md từ kết quả đã có, không gọi model")
    s.set_defaults(fn=cmd_analyze)

    s = sub.add_parser("edit", help="mở công cụ chỉnh glossary trên trình duyệt")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--no-browser", action="store_true", help="không tự mở trình duyệt")
    s.set_defaults(fn=cmd_edit)

    s = sub.add_parser("translate", help="dịch hàng loạt")
    s.add_argument("range", nargs="?", help="vd 1-50,60; mặc định tất cả chương đã tải")
    s.add_argument("--model", help="ghi đè llm.model trong config.yaml")
    s.add_argument("--workers", type=int, help="số chương dịch song song")
    s.add_argument("--force", action="store_true", help="dịch lại chương đã có (vẫn dùng cache nếu prompt không đổi)")
    s.add_argument("--no-cache", action="store_true", help="bỏ qua cache, gọi model lại từ đầu")
    s.set_defaults(fn=cmd_translate)

    s = sub.add_parser("merge", help="ghép 2 bản dịch: tự kiểm tra trước, model phân xử phần khác nhau")
    s.add_argument("range", nargs="?", help="vd 610-612; mặc định mọi chương đã có đủ 2 bản dịch")
    s.add_argument("--models", help="2 model đã dịch, vd gemma3:12b,translategemma:12b (mặc định trong config.yaml)")
    s.add_argument("--judge", help="model phân xử, vd qwen3:8b (mặc định trong config.yaml)")
    s.add_argument("--name", help="tên thư mục kết quả (mặc định merge.name trong config.yaml)")
    s.add_argument("--no-reasons", action="store_true", help="không yêu cầu lý do (nhanh hơn với model chậm như 27B)")
    s.set_defaults(fn=cmd_merge)

    s = sub.add_parser("polish", help="model lớn chỉ sửa xưng hô / đại từ trên bản dịch có sẵn")
    s.add_argument("range", nargs="?", help="vd 610-612; mặc định mọi chương đã có bản nguồn")
    s.add_argument("--model", help="model chỉnh (mặc định polish.model trong config.yaml)")
    s.add_argument("--source", help="bản dịch đem chỉnh, vd gemma3:12b hoặc tuyen-chon")
    s.add_argument("--name", help="tên thư mục kết quả (mặc định polish.name)")
    s.set_defaults(fn=cmd_polish)

    s = sub.add_parser("audit", help="soát xưng hô của các bản dịch (không cần model)")
    s.add_argument("range", help="vd 610-612")
    s.add_argument("--models", required=True, help="vd gemma3:12b,gemma3:27b-it-qat,translategemma:12b")
    s.set_defaults(fn=cmd_audit)

    s = sub.add_parser("compare", help="HTML so sánh bản dịch của nhiều model")
    s.add_argument("chapter")
    s.add_argument("--models", required=True, help="vd qwen3:8b,gemma3:12b")
    s.set_defaults(fn=cmd_compare)

    s = sub.add_parser("status", help="tiến độ dịch")
    s.add_argument("--model")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("export", help="xuất EPUB/TXT")
    s.add_argument("range", nargs="?", help="vd 1-100; mặc định tất cả chương đã dịch")
    s.add_argument("--model")
    s.add_argument("--format", choices=["md", "epub", "txt"], default="epub",
                   help="md: mỗi chương 1 file để duyệt; epub/txt: gộp thành sách")
    s.add_argument("--bilingual", action="store_true", help="kèm câu tiếng Anh dưới mỗi đoạn")
    s.set_defaults(fn=cmd_export)

    s = sub.add_parser("web", help="xuất cho app đọc truyện trên web (../web)")
    s.add_argument("range", nargs="?", help="vd 1-100; mặc định tất cả chương đã dịch")
    s.add_argument("--model")
    s.set_defaults(fn=cmd_web)

    args = p.parse_args()
    args.fn(load_config(), Paths(), args)


if __name__ == "__main__":
    main()
