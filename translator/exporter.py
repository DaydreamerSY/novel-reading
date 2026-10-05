"""Export translated chapters to EPUB / TXT, and side-by-side HTML to compare models."""
import html
import uuid
import zipfile
from datetime import datetime, timezone

from common import available, chapter_path, read_json, safe_name

CSS = """body { font-family: serif; line-height: 1.6; margin: 0 4%; }
h2 { text-align: center; margin: 1.5em 0 1em; }
p { margin: 0 0 0.8em; text-indent: 0; }
p.en { color: #777; font-size: 0.85em; font-style: italic; margin-top: -0.5em; }
p.flag { border-left: 3px solid #d9822b; padding-left: 0.5em; }
"""


def _x(s):
    return html.escape(s, quote=True)


def load_chapters(folder, chapters):
    return [read_json(chapter_path(folder, n)) for n in chapters if chapter_path(folder, n).exists()]


def _chapter_xhtml(ch, bilingual):
    body = []
    for p in ch["paragraphs"]:
        cls = ' class="flag"' if p.get("flags") and bilingual else ""
        body.append(f"<p{cls}>{_x(p['vi'])}</p>")
        if bilingual:
            body.append(f'<p class="en">{_x(p["en"])}</p>')
    return (f'<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
            f'<html xmlns="http://www.w3.org/1999/xhtml" lang="vi" xml:lang="vi">\n'
            f'<head><meta charset="utf-8"/><title>{_x(ch["title_vi"])}</title>'
            f'<link rel="stylesheet" type="text/css" href="style.css"/></head>\n'
            f'<body>\n<h2>{_x(ch["title_vi"])}</h2>\n' + "\n".join(body) + "\n</body>\n</html>\n")


def write_epub(path, title, author, chapters, bilingual):
    uid = f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, title)}"
    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ids = [f"c{ch['number']:04d}" for ch in chapters]

    manifest = "\n".join(f'  <item id="{i}" href="{i}.xhtml" media-type="application/xhtml+xml"/>' for i in ids)
    spine = "\n".join(f'  <itemref idref="{i}"/>' for i in ids)
    opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="vi">
 <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:identifier id="bookid">{uid}</dc:identifier>
  <dc:title>{_x(title)}</dc:title>
  <dc:creator>{_x(author)}</dc:creator>
  <dc:language>vi</dc:language>
  <meta property="dcterms:modified">{modified}</meta>
 </metadata>
 <manifest>
  <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
  <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
  <item id="css" href="style.css" media-type="text/css"/>
{manifest}
 </manifest>
 <spine toc="ncx">
{spine}
 </spine>
</package>
"""
    nav_items = "\n".join(f'<li><a href="{i}.xhtml">{_x(ch["title_vi"])}</a></li>' for i, ch in zip(ids, chapters))
    nav = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="vi" xml:lang="vi">
<head><meta charset="utf-8"/><title>Mục lục</title></head>
<body><nav epub:type="toc" id="toc"><h1>Mục lục</h1><ol>
{nav_items}
</ol></nav></body></html>
"""
    points = "\n".join(
        f'  <navPoint id="n{k}" playOrder="{k}"><navLabel><text>{_x(ch["title_vi"])}</text></navLabel>'
        f'<content src="{i}.xhtml"/></navPoint>'
        for k, (i, ch) in enumerate(zip(ids, chapters), 1))
    ncx = f"""<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
 <head><meta name="dtb:uid" content="{uid}"/></head>
 <docTitle><text>{_x(title)}</text></docTitle>
 <navMap>
{points}
 </navMap>
</ncx>
"""
    container = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
 <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)  # must be first
        z.writestr("META-INF/container.xml", container)
        z.writestr("OEBPS/content.opf", opf)
        z.writestr("OEBPS/nav.xhtml", nav)
        z.writestr("OEBPS/toc.ncx", ncx)
        z.writestr("OEBPS/style.css", CSS)
        for i, ch in zip(ids, chapters):
            z.writestr(f"OEBPS/{i}.xhtml", _chapter_xhtml(ch, bilingual))


def chapter_md(ch, bilingual=False):
    """One chapter as markdown; flagged paragraphs are listed at the end with their English source."""
    lines = [f"# {ch['title_vi']}", ""]
    for p in ch["paragraphs"]:
        lines += [p["vi"], ""]
        if bilingual:
            lines += [f"> {p['en']}", ""]
    flagged = [(i, p) for i, p in enumerate(ch["paragraphs"], 1) if p.get("flags")]
    if flagged:
        lines += ["---", "", "## Cần xem lại", ""]
        for i, p in flagged:
            lines += [f"- **Đoạn {i}** ({'; '.join(p['flags'])})", f"  - EN: {p['en']}", f"  - VI: {p['vi']}"]
        lines.append("")
    return "\n".join(lines)


def write_md(paths, model, chapters, bilingual=False):
    folder = paths.output / "md" / safe_name(model)
    folder.mkdir(parents=True, exist_ok=True)
    for ch in chapters:
        (folder / f"{ch['number']:04d}.md").write_text(chapter_md(ch, bilingual), encoding="utf-8")
    return folder


def write_txt(path, chapters, bilingual):
    parts = []
    for ch in chapters:
        lines = [ch["title_vi"], ""]
        for p in ch["paragraphs"]:
            lines.append(p["vi"])
            if bilingual:
                lines.append(f"    ({p['en']})")
            lines.append("")
        parts.append("\n".join(lines))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n\n".join(parts), encoding="utf-8")


def export(cfg, paths, model, chapters, fmt, bilingual):
    folder = paths.vi(model)
    chapters = load_chapters(folder, chapters or available(folder))
    if not chapters:
        print(f"Chưa có chương nào đã dịch bằng {model}.")
        return
    first, last = chapters[0]["number"], chapters[-1]["number"]
    if fmt == "md":
        folder = write_md(paths, model, chapters, bilingual)
        print(f"{len(chapters)} chương → {folder}")
        return
    title = cfg["book"]["title"]
    stem = f"{safe_name(title)}_{first:04d}-{last:04d}{'_song-ngu' if bilingual else ''}"
    if fmt == "epub":
        path = paths.output / f"{stem}.epub"
        write_epub(path, f"{title} ({first}-{last})", cfg["book"]["author"], chapters, bilingual)
    else:
        path = paths.output / f"{stem}.txt"
        write_txt(path, chapters, bilingual)
    print(f"{len(chapters)} chương → {path}")


def compare(paths, n, models):
    """One HTML table: English | model A | model B ... for a single chapter."""
    en = read_json(chapter_path(paths.en, n))
    runs = []
    for m in models:
        p = chapter_path(paths.vi(m), n)
        if p.exists():
            runs.append((m, read_json(p)))
        else:
            print(f"Bỏ qua {m}: chưa dịch chương {n}.")
    if not runs:
        return
    head = "".join(f"<th>{_x(m)}</th>" for m, _ in runs)
    rows = [f"<tr><td class=en>{_x(en['title'])}</td>"
            + "".join(f"<td><b>{_x(ch['title_vi'])}</b></td>" for _, ch in runs) + "</tr>"]
    for i, para in enumerate(en["paragraphs"]):
        cells = []
        for _, ch in runs:
            p = ch["paragraphs"][i] if i < len(ch["paragraphs"]) else {"vi": ""}
            flag = f'<div class=flag>{_x("; ".join(p["flags"]))}</div>' if p.get("flags") else ""
            cells.append(f"<td>{_x(p['vi'])}{flag}</td>")
        rows.append(f"<tr><td class=en>{_x(para)}</td>{''.join(cells)}</tr>")
    page = f"""<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>So sánh chương {n}</title>
<style>
:root {{ color-scheme: light dark; --line: #8884; --muted: #888; --flag: #d9822b; }}
body {{ font: 15px/1.55 system-ui, sans-serif; margin: 16px; background: Canvas; color: CanvasText; }}
table {{ border-collapse: collapse; width: 100%; table-layout: fixed; }}
th {{ position: sticky; top: 0; background: Canvas; text-align: left; padding: 8px; border-bottom: 2px solid var(--line); }}
td {{ vertical-align: top; padding: 6px 8px; border-bottom: 1px solid var(--line); overflow-wrap: anywhere; }}
td.en {{ color: var(--muted); }}
.flag {{ color: var(--flag); font-size: 12px; margin-top: 4px; }}
</style></head><body>
<h1>Chương {n}</h1>
<table><thead><tr><th>English</th>{head}</tr></thead><tbody>
{chr(10).join(rows)}
</tbody></table></body></html>"""
    path = paths.output / f"so-sanh_chuong-{n:04d}.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")
    print(f"→ {path}")
