// Routes: #/ = library, #/read/<slug> = continue reading, #/read/<slug>/<chapter> = open a chapter.
import { Reader, applyLook, fetchJSON } from "./reader.js";
import { loadProgress, loadSettings } from "./store.js";

const settings = loadSettings();
applyLook(settings);
const reader = new Reader(document.getElementById("reader"), settings);
const library = document.getElementById("library");
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const pct = p => Math.round(p.pct * 100);

function hue(s) {
  let h = 0;
  for (const c of s) h = (h * 31 + c.codePointAt(0)) % 360;
  return h;
}

const cover = b => `<div class="cover" style="--h:${hue(b.slug)}">
  <div class="cover-title">${esc(b.title)}</div><div class="cover-author">${esc(b.author || "")}</div></div>`;

const meter = p => `<div class="meter"><i style="width:${(p.pct * 100).toFixed(1)}%"></i></div>`;

async function showLibrary() {
  reader.close();
  document.title = "Tủ Truyện";
  library.hidden = false;
  let books = [];
  try {
    books = (await fetchJSON("books/index.json", true)).books;
  } catch { /* no books exported yet */ }
  if (library.hidden) return;   // the reader was opened meanwhile

  const shelf = document.getElementById("shelf"), cont = document.getElementById("continue");
  if (!books.length) {
    cont.innerHTML = "";
    shelf.innerHTML = `<p class="empty">Chưa có truyện nào. Xuất các chương đã dịch bằng
      <code>python novel.py web</code> rồi tải lại trang.</p>`;
    return;
  }
  const items = books.map(b => ({ b, p: loadProgress(b.slug) }));
  shelf.innerHTML = items.map(({ b, p }) => `
    <a class="book" href="#/read/${encodeURIComponent(b.slug)}">
      ${cover(b)}
      <div class="book-title">${esc(b.title)}</div>
      <div class="book-meta">${b.count} chương${p ? ` · đã đọc ${pct(p)}%` : ""}</div>
      ${p ? meter(p) : ""}
    </a>`).join("");

  const last = items.filter(x => x.p).sort((a, b) => b.p.ts - a.p.ts)[0];
  cont.innerHTML = last ? `
    <a class="cont" href="#/read/${encodeURIComponent(last.b.slug)}">
      ${cover(last.b)}
      <div class="cont-body">
        <div class="cont-kicker">Đọc tiếp</div>
        <div class="cont-title">${esc(last.b.title)}</div>
        <div class="cont-sub">${esc(last.p.title)} · đã đọc ${pct(last.p)}%</div>
        ${meter(last.p)}
        <span class="btn">Tiếp tục đọc</span>
      </div>
    </a>` : "";
}

function route() {
  const [, view, slug, n] = location.hash.split("/");
  if (view === "read" && slug) {
    library.hidden = true;
    const chapter = Number(n);
    reader.open(decodeURIComponent(slug), n && Number.isFinite(chapter) ? chapter : undefined).catch(err => {
      console.error(err);
      location.hash = "#/";
    });
  } else {
    showLibrary();
  }
}

window.addEventListener("hashchange", route);
route();
