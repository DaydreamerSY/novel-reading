// Paged reader. A chapter is laid out once in CSS columns, each column one page wide; a page is
// a window onto that flow, shifted by whole columns. Three page elements (previous, current,
// next) are recycled as the reader moves, so turning within a chapter only changes a transform.
import { bendStrips, shine } from "./bend.js";
import { curlGeometry } from "./curl.js";
import { FONTS, MARGINS, loadProgress, saveProgress, saveSettings } from "./store.js";

const MAX_W = 680;
const pad = n => String(n).padStart(4, "0");
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const easeOut = k => 1 - (1 - k) ** 3;
const easeInOut = k => (k < 0.5 ? 4 * k ** 3 : 1 - (-2 * k + 2) ** 3 / 2);
const polygon = pts => (pts.length < 3 ? "polygon(0 0, 0 0, 0 0)"
  : `polygon(${pts.map(([x, y]) => `${x.toFixed(1)}px ${y.toFixed(1)}px`).join(",")})`);
const div = cls => Object.assign(document.createElement("div"), { className: cls });

export async function fetchJSON(url, fresh = false) {
  const r = await fetch(url, fresh ? { cache: "no-cache" } : undefined);
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return r.json();
}

export function applyLook(s) {
  const root = document.documentElement;
  root.dataset.theme = s.theme;
  root.toggleAttribute("data-bilingual", s.bilingual);
  root.style.setProperty("--font", FONTS[s.font]);
  root.style.setProperty("--fs", `${s.size}px`);
  root.style.setProperty("--lh", s.lh);
  root.style.setProperty("--align", s.justify ? "justify" : "left");
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = getComputedStyle(root).getPropertyValue("--paper").trim();
}

// Wait (briefly) for the reading font so the first layout isn't done with a fallback.
function fontReady(s) {
  const family = FONTS[s.font].split(",")[0];
  if (!document.fonts?.load || !family.startsWith('"')) return Promise.resolve();
  const spec = `${s.size}px ${family}`;
  return Promise.race([
    Promise.all([document.fonts.load(spec, "Tiếng Việt"), document.fonts.load(`600 ${spec}`, "Chương")]).catch(() => {}),
    new Promise(r => setTimeout(r, 3000)),
  ]);
}

function chapterParts(d) {
  const m = /^(\D*?)\s*(\d+)\s*[:.\-–—]?\s*(.*)$/.exec(d.title);
  const head = m
    ? `<div class="kicker">${esc(m[1] || "Chương")}</div><div class="num">${m[2]}</div>${m[3] ? `<h2>${esc(m[3])}</h2>` : ""}`
    : `<h2>${esc(d.title)}</h2>`;
  const parts = d.vi.map((vi, i) => `<p class="vi">${esc(vi)}</p>${d.en?.[i] ? `<p class="en">${esc(d.en[i])}</p>` : ""}`);
  return { head: `<header class="chap-open">${head}</header>`, parts };
}

export class Reader {
  constructor(root, settings) {
    this.root = root;
    this.s = settings;
    this.$ = sel => root.querySelector(sel);
    this.stage = this.$("#stage");
    this.chapters = new Map();   // chapter number -> { n, title, head, parts, html, pages, starts, tops, key }
    this.loading = new Map();    // chapter number -> pending fetch
    this.pages = [this.makePage(), this.makePage(), this.makePage()];   // previous, current, next
    this.measurer = this.makePage("measure");
    this.backPage = this.makePage("back");
    this.underShade = div("shade under-shade");
    this.flap = div("flap");
    this.flapInner = div("flap-inner");
    this.flapShade = div("shade flap-shade");
    this.flapInner.append(this.backPage, this.flapShade);
    this.flap.append(this.flapInner);
    this.bend = div("bend");          // strips of the page turning around the spine
    this.bendShade = div("bend-shade");
    this.snap = this.makePage("snap");
    this.strips = [];
    this.stage.append(...this.pages, this.underShade, this.flap, this.bendShade, this.bend, this.measurer);

    this.book = null;
    this.pos = null;       // { ci: index into book.chapters, pg: page within that chapter }
    this.pinned = null;    // paragraph to keep in view across re-layouts, until the reader moves on
    this.near = {};        // neighbouring positions; null = edge of the book, undefined = not loaded yet
    this.flip = null;      // the page turn in progress
    this.g = null;         // the pointer gesture in progress
    this.gen = 0;
    this.lkey = "";
    this.wheelAt = 0;
    this.wheelSum = 0;
    this.bindInput();
    this.bindChrome();
    this.bindSettings();
  }

  makePage(extra) {
    const el = div(extra ? `page ${extra}` : "page");
    el.innerHTML = '<div class="page-head"></div><div class="page-body"><div class="flow"></div></div><div class="page-foot"></div>';
    el.head = el.firstChild;
    el.flow = el.querySelector(".flow");
    el.foot = el.lastChild;
    return el;
  }

  // ---------- opening a book ----------

  async open(slug, n) {
    this.close();
    const token = (this.token = Symbol());
    this.root.hidden = false;
    this.busy(true);
    try {
      const book = await fetchJSON(`books/${encodeURIComponent(slug)}/book.json`, true);
      if (this.token !== token) return;
      if (!book.chapters?.length) throw new Error(`${slug}: chưa có chương nào`);
      book.slug = slug;
      this.book = book;
      document.title = book.title;
      this.$("#r-book").textContent = book.title;
      this.$('#settings [data-set="bilingual"]').closest(".row").hidden = book.bilingual === false;
      this.buildToc();

      const saved = loadProgress(slug);
      const want = n ?? saved?.n ?? book.chapters[0].n;
      let ci = book.chapters.findIndex(c => c.n >= want);
      if (ci < 0) ci = book.chapters.length - 1;
      const anchor = saved?.n === book.chapters[ci].n ? saved.i : 0;

      await fontReady(this.s);
      if (this.token !== token) return;
      this.resize();
      const ch = await this.load(ci);
      if (this.token !== token || !ch) return;
      this.pos = { ci, pg: this.pageOf(ch, anchor) };
      this.pinned = anchor;
      this.settle();
    } finally {
      if (this.token === token) this.busy(false);
    }
  }

  close() {
    this.token = null;
    this.abortFlip();
    this.closePanel();
    this.chrome(false);
    this.root.hidden = true;
    this.book = null;
    this.pos = null;
    this.pinned = null;
    this.near = {};
    this.chapters.clear();
    this.loading.clear();
    for (const el of [...this.pages, this.backPage]) {
      el.chap = el.pos = null;
      el.flow.textContent = "";
    }
  }

  load(ci) {
    const book = this.book, n = book.chapters[ci].n;
    if (!this.chapters.has(n) && !this.loading.has(n)) {
      const p = fetchJSON(`books/${encodeURIComponent(book.slug)}/c/${pad(n)}.json`)
        .then(d => {
          if (this.book !== book) return;
          const { head, parts } = chapterParts(d);
          this.chapters.set(n, { n, title: d.title, head, parts, html: head + parts.join("") });
        })
        .finally(() => { if (this.loading.get(n) === p) this.loading.delete(n); });
      this.loading.set(n, p);
    }
    return Promise.resolve(this.loading.get(n)).then(() => (this.book === book ? this.chap(ci) : null));
  }

  // ---------- layout ----------

  // A loaded chapter, measured for the current layout; null if not loaded yet.
  chap(ci) {
    const ch = this.book && this.chapters.get(this.book.chapters[ci]?.n);
    if (!ch) return null;
    if (ch.key !== this.lkey) this.measure(ch);
    return ch;
  }

  // Count the chapter's pages and note where each paragraph starts: page, and height within it.
  measure(ch) {
    const flow = this.measurer.flow;
    flow.innerHTML = ch.html;
    const { left, top } = flow.getBoundingClientRect();
    const col = x => Math.max(0, Math.floor((x - left + 1) / this.stepX));
    const firsts = Array.from(flow.querySelectorAll("p.vi"), p => p.getClientRects()[0]);
    ch.starts = firsts.map(r => col(r?.left ?? left));
    ch.tops = firsts.map(r => (r ? r.top - top : 0));
    let last = flow.lastElementChild;
    while (last && !last.getClientRects().length) last = last.previousElementSibling;
    const rects = last ? last.getClientRects() : [];
    ch.pages = rects.length ? col(rects[rects.length - 1].left) + 1 : 1;
    ch.key = this.lkey;
    flow.textContent = "";
  }

  resize() {
    const vw = window.innerWidth, W = Math.min(vw, MAX_W), H = window.innerHeight;
    const mx = MARGINS[this.s.margin] + (W >= 560 ? 24 : 0);
    Object.assign(this.stage.style, { width: `${W}px`, height: `${H}px`, left: `${Math.floor((vw - W) / 2)}px` });
    this.root.classList.toggle("framed", W < vw);
    this.root.style.setProperty("--mx", `${mx}px`);
    const body = this.measurer.flow.getBoundingClientRect();
    this.W = W;
    this.H = H;
    this.stepX = body.width + 2 * mx;
    this.root.style.setProperty("--cw", `${body.width}px`);
    this.root.style.setProperty("--gap", `${2 * mx}px`);
    this.root.style.setProperty("--diag", `${2 * Math.hypot(W, H)}px`);
    this.persp = Math.max(1400, 2.5 * W);
    this.bend.style.perspective = `${this.persp}px`;
    if (this.stripsFor !== W) this.buildStrips(W);
    const s = this.s;
    this.lkey = [this.gen, W, H, body.width, body.height, s.font, s.size, s.lh, s.justify, s.bilingual].join("|");
  }

  // Re-paginate (window size, font, settings) while staying on the same paragraph. The anchor is
  // pinned so that, say, A+ then A- comes back to the same page instead of drifting.
  relayout() {
    if (!this.book) return;
    this.abortFlip();
    const anchor = this.pos && (this.pinned ??= this.anchorOf(this.pos));
    this.gen++;
    this.resize();
    if (!this.pos) return;
    this.pos = { ci: this.pos.ci, pg: this.pageOf(this.chap(this.pos.ci), anchor) };
    this.settle();
  }

  pageOf(ch, anchor) {
    return clamp(ch.starts[anchor] ?? 0, 0, ch.pages - 1);
  }

  // The paragraph that starts on this page, or else the one running onto it from before.
  anchorOf(pos) {
    const starts = this.chap(pos.ci).starts;
    let best = 0;
    for (let i = 0; i < starts.length; i++) {
      if (starts[i] === pos.pg) return i;
      if (starts[i] > pos.pg) break;
      best = i;
    }
    return best;
  }

  step(pos, dir) {
    const pg = pos.pg + dir;
    if (pg >= 0 && pg < this.chap(pos.ci).pages) return { ci: pos.ci, pg };
    const ci = pos.ci + dir;
    if (ci < 0 || ci >= this.book.chapters.length) return null;
    const ch = this.chap(ci);
    return ch ? { ci, pg: dir > 0 ? 0 : ch.pages - 1 } : undefined;
  }

  paint(el, pos) {
    el.pos = pos || null;
    if (!pos) return;
    const ch = this.chap(pos.ci);
    if (el.chap !== ch) {
      el.chap = ch;
      el.flow.innerHTML = ch.html;
      el.head.textContent = ch.title;
    }
    el.flow.style.transform = `translateX(${-pos.pg * this.stepX}px)`;
    el.head.classList.toggle("off", pos.pg === 0);
    el.foot.textContent = `${pos.pg + 1} / ${ch.pages}`;
  }

  // The page with only its own text (and the paragraph running onto it), laid out in the same
  // columns as the whole chapter: a spacer stands in for everything above that paragraph.
  // Cheap enough to copy into every strip of a bend turn.
  fillSnap(pos) {
    const ch = this.chap(pos.ci), { starts, tops } = ch, pg = pos.pg, el = this.snap;
    const first = starts.findIndex(s => s >= pg), after = starts.findIndex(s => s > pg);
    const a = Math.max(0, (first < 0 ? starts.length : first) - 1);
    const b = (after < 0 ? starts.length : after) - 1;
    const lead = a === 0 ? ch.head : `<div style="height:${tops[a]}px"></div>`;
    el.flow.innerHTML = lead + ch.parts.slice(a, b + 1).join("");
    el.flow.style.transform = `translateX(${-(pg - (a === 0 ? 0 : starts[a])) * this.stepX}px)`;
    el.head.textContent = ch.title;
    el.head.classList.toggle("off", pg === 0);
    el.foot.textContent = `${pg + 1} / ${ch.pages}`;
  }

  buildStrips(W) {
    const n = W > 500 ? 28 : 20;
    this.stripsFor = W;
    this.stripW = W / n;
    this.bend.textContent = "";
    this.strips = Array.from({ length: n }, () => {
      const strip = div("strip"), front = div("face"), back = div("face back");
      strip.style.width = `${this.stripW + 1}px`;   // overlap hides seams between neighbours
      front.append(div("lit"));
      back.append(div("lit"));
      strip.append(front, back);
      this.bend.append(strip);
      return { strip, front, lits: [front.firstChild, back.firstChild] };
    });
  }

  // Show this.pos and get its neighbours ready.
  settle() {
    const [prev, cur, next] = this.pages;
    this.paint(cur, this.pos);
    this.near = { prev: this.step(this.pos, -1), next: this.step(this.pos, 1) };
    this.paint(prev, this.near.prev);
    this.paint(next, this.near.next);
    this.restack();
    this.updateChrome();
    this.remember();
    // Fetch the chapters on either side ahead of time so crossing into them is instant.
    for (const ci of [this.pos.ci + 1, this.pos.ci - 1]) {
      if (ci < 0 || ci >= this.book.chapters.length || this.chapters.has(this.book.chapters[ci].n)) continue;
      this.load(ci).then(() => {
        if (this.pos && !this.flip && (this.near.next === undefined || this.near.prev === undefined)) this.settle();
      }, () => {});
    }
  }

  restack() {
    this.pages.forEach((el, i) => {
      el.style.cssText = "";
      el.classList.toggle("on", i === 1);
    });
    this.flap.classList.remove("on");
    this.underShade.classList.remove("on");
    this.bend.classList.remove("on");
    this.bendShade.classList.remove("on");
  }

  // ---------- turning pages ----------

  // Start turning: dir 1 lifts the current page off the next one, -1 brings the previous page back.
  begin(dir, bottom, lift) {
    const to = dir > 0 ? this.near.next : this.near.prev;
    if (!to) return false;
    const [prev, cur, next] = this.pages;
    const f = {
      dir, to, bottom, lift, yOff: 0, t: dir > 0 ? 0 : 1, target: null, mode: this.s.anim,
      turning: dir > 0 ? cur : prev, under: dir > 0 ? next : cur,
    };
    f.under.style.cssText = "visibility:visible;z-index:1";
    f.turning.style.cssText = "visibility:visible;z-index:2";
    if (f.mode === "curl") {
      this.paint(this.backPage, f.turning.pos);
      this.flap.classList.add("on");
      this.underShade.classList.add("on");
    } else if (f.mode === "bend") {
      this.fillSnap(f.turning.pos);
      this.strips.forEach(({ front }, k) => {
        const page = this.snap.cloneNode(true);
        page.style.cssText = `left:${-k * this.stripW}px;width:${this.W}px`;
        if (front.firstChild.classList.contains("page")) front.firstChild.replaceWith(page);
        else front.prepend(page);
      });
      f.turning.style.visibility = "hidden";
      this.bend.classList.add("on");
      this.bendShade.classList.add("on");
    } else {
      f.turning.style.boxShadow = "0 0 28px rgba(0,0,0,.28)";
    }
    this.flip = f;
    this.chrome(false);
    this.draw();
    return true;
  }

  draw() {
    const f = this.flip, { W, H } = this;
    if (f.mode === "bend") return this.drawBend(f);
    if (f.mode !== "curl") {
      f.turning.style.transform = `translate3d(${(-f.t * W).toFixed(1)}px,0,0)`;
      return;
    }
    const g = curlGeometry(W, H, f.t, f.bottom, f.yOff, f.lift);
    this.flap.style.visibility = this.underShade.style.visibility = g ? "" : "hidden";
    if (!g) {
      f.turning.style.clipPath = "";
      return;
    }
    f.turning.style.clipPath = polygon(g.front);
    this.flapInner.style.clipPath = polygon(g.back);
    this.flap.style.transform = `matrix(${g.matrix.map(v => v.toFixed(5)).join(",")})`;
    // Both shades start at the fold and fade towards the grabbed corner; the flap's one is
    // drawn before the reflection, so it lands on the folded-over side.
    const along = `translate(${g.M[0].toFixed(1)}px,${g.M[1].toFixed(1)}px) rotate(${g.angle.toFixed(5)}rad) translateY(-50%)`;
    this.flapShade.style.transform = this.underShade.style.transform = along;
    this.flapShade.style.width = `${g.len / 2}px`;
    this.underShade.style.width = `${Math.min(g.len / 2, W * 0.5)}px`;
    this.underShade.style.opacity = Math.min(1, (1 - f.t) * 3);
  }

  drawBend(f) {
    const { W } = this, sw = this.stripW, geo = bendStrips(f.t, this.strips.length, W);
    // Shade each strip with a gradient between the tilts at its two edges, so the light runs
    // smoothly across the sheet instead of in bands.
    const tone = phi => {
      const v = shine(phi);
      return v > 0 ? `rgba(255,255,255,${Math.min(0.3, v * 1.2).toFixed(3)})` : `rgba(0,0,0,${Math.min(0.45, -v * 0.75).toFixed(3)})`;
    };
    const edges = geo.map((g, k) => tone(k ? (geo[k - 1].phi + g.phi) / 2 : g.phi));
    edges.push(tone(geo[geo.length - 1].phi));
    let high = 0;
    geo.forEach(({ x, z, phi }, k) => {
      const { strip, lits } = this.strips[k];
      strip.style.transform = `translate3d(${x.toFixed(2)}px,0,${z.toFixed(2)}px) rotateY(${(-phi).toFixed(4)}rad)`;
      lits[0].style.background = lits[1].style.background = `linear-gradient(90deg,${edges[k]},${edges[k + 1]})`;
      high = Math.max(high, z);
    });
    // The lifted sheet shades the page below, up to where its outer edge appears on screen.
    const last = geo[geo.length - 1];
    const ex = last.x + sw * Math.cos(last.phi), ez = last.z + sw * Math.sin(last.phi);
    const edge = Math.max(0, W / 2 + ((ex - W / 2) * this.persp) / (this.persp - ez));
    const a = (0.32 * Math.min(1, high / (W * 0.2))).toFixed(3);
    this.bendShade.style.background = `linear-gradient(90deg, rgba(0,0,0,${a}) ${edge.toFixed(1)}px, transparent ${(edge + 56).toFixed(1)}px)`;
  }

  animate(target, ms, ease) {
    const f = this.flip, t0 = f.t, y0 = f.yOff, start = performance.now();
    f.target = target;
    cancelAnimationFrame(this.raf);
    const tick = now => {
      if (this.flip !== f) return;
      const k = Math.min(1, (now - start) / ms), e = ease(k);
      f.t = t0 + (target - t0) * e;
      f.yOff = y0 * (1 - e);
      this.draw();
      if (k < 1) this.raf = requestAnimationFrame(tick);
      else this.end();
    };
    this.raf = requestAnimationFrame(tick);
  }

  end() {
    const f = this.flip;
    if (!f) return;
    cancelAnimationFrame(this.raf);
    this.flip = null;
    if (f.dir > 0 ? f.t >= 1 : f.t <= 0) {
      const [p, c, n] = this.pages;
      this.pages = f.dir > 0 ? [c, n, p] : [n, p, c];
      this.pos = f.to;
      this.pinned = null;
    }
    this.settle();
  }

  // Jump an animating turn to its end, so rapid taps never queue up.
  finish() {
    if (this.flip?.target != null) {
      this.flip.t = this.flip.target;
      this.end();
    }
  }

  // Also drop a turn that's still under the finger.
  abortFlip() {
    const f = this.flip;
    this.g = null;
    if (!f) return;
    f.t = f.target ?? (f.dir > 0 ? 0 : 1);
    this.end();
  }

  turn(dir) {
    if (!this.pos) return;
    if (this.flip) {
      if (this.flip.target == null) return;   // a finger is still holding a page
      this.finish();
    }
    const to = dir > 0 ? this.near.next : this.near.prev;
    if (to === null) return this.toast(dir > 0 ? "Hết phần đã dịch" : "Đây là trang đầu");
    if (to === undefined) return this.waitFor(this.pos.ci + dir, () => this.turn(dir));
    if (this.s.anim === "none") {
      this.chrome(false);
      this.pos = to;
      this.pinned = null;
      this.settle();
      return;
    }
    this.begin(dir, true, Math.min(this.W, this.H) * 0.3);
    const [ms, ease] = { curl: [600, easeInOut], bend: [850, easeInOut], slide: [320, easeOut] }[this.s.anim];
    this.animate(dir > 0 ? 1 : 0, ms, ease);
  }

  waitFor(ci, then) {
    this.busy(true);
    this.load(ci).then(ch => {
      this.busy(false);
      if (ch && this.pos) {
        this.settle();
        then();
      }
    }, () => {
      this.busy(false);
      this.toast("Không tải được chương");
    });
  }

  goTo(ci, anchor = 0) {
    if (!this.book) return;
    this.abortFlip();
    this.busy(true);
    this.load(ci).then(ch => {
      this.busy(false);
      if (!ch) return;
      this.pos = { ci, pg: this.pageOf(ch, anchor) };
      this.pinned = anchor;
      this.settle();
    }, () => {
      this.busy(false);
      this.toast("Không tải được chương");
    });
  }

  // ---------- input ----------

  bindInput() {
    const r = this.root;
    r.addEventListener("pointerdown", e => this.down(e));
    r.addEventListener("pointermove", e => this.move(e));
    r.addEventListener("pointerup", e => this.up(e, false));
    r.addEventListener("pointercancel", e => this.up(e, true));
    r.addEventListener("wheel", e => this.wheel(e), { passive: false });
    document.addEventListener("keydown", e => this.key(e));
    let timer;
    const later = ms => {
      clearTimeout(timer);
      timer = setTimeout(() => this.relayout(), ms);
    };
    window.addEventListener("resize", () => later(150));
    document.fonts?.addEventListener?.("loadingdone", () => later(50));
  }

  onChrome(e) {
    return e.target.closest(".bar, .drawer, .sheet, .toast");
  }

  down(e) {
    if (e.button > 0 || this.onChrome(e) || !this.pos) return;
    if (this.panel) return this.closePanel();
    const r = this.stage.getBoundingClientRect();
    this.g = { id: e.pointerId, r, x0: e.clientX - r.left, y0: e.clientY - r.top, t0: performance.now(), dir: 0, live: false, moved: false, hist: [] };
    this.track(e);
  }

  track(e) {
    const g = this.g, now = performance.now();
    g.x = e.clientX - g.r.left;
    g.y = e.clientY - g.r.top;
    g.hist.push([now, g.x]);
    while (g.hist.length > 2 && now - g.hist[0][0] > 100) g.hist.shift();
  }

  move(e) {
    const g = this.g;
    if (!g || e.pointerId !== g.id) return;
    this.track(e);
    const dx = g.x - g.x0, dy = g.y - g.y0;
    if (!g.dir) {
      if (Math.hypot(dx, dy) > 10) g.moved = true;
      if (Math.abs(dx) < 12 || Math.abs(dx) < Math.abs(dy)) return;
      g.dir = dx < 0 ? 1 : -1;
      try { this.root.setPointerCapture(e.pointerId); } catch { /* pointer already gone */ }
      if (this.flip) {
        if (this.flip.target == null) return;
        this.finish();
      }
      g.live = this.s.anim !== "none" && this.begin(g.dir, g.y0 > this.H / 2, this.H * 0.05);
    }
    const f = this.flip;
    if (!g.live || !f || f.target != null) return;
    if (f.mode === "curl") {
      // Forward: the corner follows the finger, whatever point of the page was grabbed.
      // Back: the incoming page's edge follows the finger.
      f.t = f.dir > 0 ? clamp(-dx / Math.max(g.x0, 80) * 0.6, 0, 1) : clamp(1 - dx / Math.max(this.W - g.x0, 80), 0, 1);
      f.yOff = dy * 0.5;
    } else {
      f.t = clamp((f.dir > 0 ? 0 : 1) - dx / (this.W * (f.mode === "bend" ? 0.8 : 1)), 0, 1);
    }
    this.draw();
  }

  up(e, cancelled) {
    const g = this.g;
    if (!g || e.pointerId !== g.id) return;
    this.g = null;
    const f = this.flip;
    if (g.live && f && f.target == null) {
      const h = g.hist, dt = h[h.length - 1][0] - h[0][0];
      const v = dt > 0 ? (h[h.length - 1][1] - h[0][1]) / dt : 0;   // px/ms, positive = rightwards
      const fwd = f.dir > 0;
      const go = !cancelled && (fwd ? v < -0.3 || (v < 0.3 && f.t > 0.15) : v > 0.3 || (v > -0.3 && f.t < 0.85));
      const target = fwd === go ? 1 : 0;
      this.animate(target, 140 + (f.mode === "bend" ? 560 : 380) * Math.abs(target - f.t), easeOut);
    } else if (g.dir && !g.live) {
      if (!cancelled && Math.abs(g.x - g.x0) > 40) this.turn(g.dir);
    } else if (!g.dir && !g.moved && !cancelled && performance.now() - g.t0 < 600) {
      this.tap(g.x);
    }
  }

  tap(x) {
    if (this.root.classList.contains("chrome")) return this.chrome(false);
    if (x < this.W * 0.3) this.turn(-1);
    else if (x > this.W * 0.7) this.turn(1);
    else this.chrome(true);
  }

  // One page per wheel gesture: further events are ignored until the wheel rests for a moment.
  wheel(e) {
    if (this.onChrome(e) || this.panel || !this.pos) return;
    e.preventDefault();
    const now = performance.now();
    const d = Math.abs(e.deltaY) >= Math.abs(e.deltaX) ? e.deltaY : e.deltaX;
    if (now - this.wheelAt > 200) {
      this.wheelSum = 0;
      this.wheelLock = false;
    }
    this.wheelAt = now;
    this.wheelSum += d;
    if (!this.wheelLock && Math.abs(this.wheelSum) > 40) {
      this.wheelLock = true;
      this.turn(Math.sign(this.wheelSum));
    }
  }

  key(e) {
    if (this.root.hidden || !this.pos || e.altKey || e.ctrlKey || e.metaKey) return;
    if (e.key === "Escape") {
      if (this.panel) this.closePanel();
      else this.chrome(!this.root.classList.contains("chrome"));
      return;
    }
    if (this.panel || e.target.closest?.("input, button")) return;
    let dir = 0;
    if (["ArrowRight", "ArrowDown", "PageDown"].includes(e.key) || (e.key === " " && !e.shiftKey)) dir = 1;
    else if (["ArrowLeft", "ArrowUp", "PageUp"].includes(e.key) || (e.key === " " && e.shiftKey)) dir = -1;
    if (dir) {
      e.preventDefault();
      this.turn(dir);
    }
  }

  // ---------- chrome: bars, table of contents, settings ----------

  bindChrome() {
    this.root.addEventListener("click", e => {
      const act = e.target.closest("[data-act]")?.dataset.act;
      if (!act || !this.book) return;
      if (act === "back") location.hash = "#/";
      else if (act === "toc") this.openPanel("#toc");
      else if (act === "settings") this.openPanel("#settings");
      else if (act === "close") this.closePanel();
      else if (act === "prev-chap" || act === "next-chap") {
        const ci = this.pos.ci + (act === "next-chap" ? 1 : -1);
        if (ci >= 0 && ci < this.book.chapters.length) this.goTo(ci);
      }
    });
    const slider = this.$("#r-slider"), label = this.$("#r-scrub-label");
    slider.addEventListener("input", () => {
      label.innerHTML = `<span>${esc(this.book.chapters[slider.value].title)}</span>`;
    });
    slider.addEventListener("change", () => {
      label.textContent = "";
      if (Number(slider.value) !== this.pos.ci) this.goTo(Number(slider.value));
    });
    this.$("#toc-list").addEventListener("click", e => {
      const li = e.target.closest("[data-ci]");
      if (!li) return;
      this.closePanel();
      this.goTo(Number(li.dataset.ci));
    });
    this.$("#toc-filter").addEventListener("input", e => this.filterToc(e.target.value));
  }

  buildToc() {
    let html = "", prev = null;
    this.book.chapters.forEach((c, i) => {
      if (prev != null && c.n > prev + 1) {
        html += `<li class="gap">${c.n - prev > 2 ? `Chương ${prev + 1}–${c.n - 1}` : `Chương ${prev + 1}`} chưa có</li>`;
      }
      const rest = c.title.replace(/^\D*?\d+\s*[:.\-–—]?\s*/, "");
      html += `<li data-ci="${i}"><button>${rest ? `<span class="n">${c.n}</span><span>${esc(rest)}</span>` : `<span>${esc(c.title)}</span>`}</button></li>`;
      prev = c.n;
    });
    this.$("#toc-list").innerHTML = html;
    this.$("#toc-filter").value = "";
  }

  filterToc(q) {
    q = q.trim().toLowerCase();
    const numeric = /^\d+$/.test(q);
    for (const li of this.$("#toc-list").children) {
      if (!li.dataset.ci) {
        li.hidden = !!q;
        continue;
      }
      const c = this.book.chapters[li.dataset.ci];
      li.hidden = !!q && !(numeric ? String(c.n).startsWith(q) : c.title.toLowerCase().includes(q));
    }
  }

  openPanel(sel) {
    this.closePanel();
    this.panel = this.$(sel);
    this.panel.classList.add("open");
    this.$(".scrim").classList.add("open");
    if (sel === "#toc") this.$("#toc-list .cur")?.scrollIntoView({ block: "center" });
    if (sel === "#settings") this.syncSettings();
  }

  closePanel() {
    if (!this.panel) return;
    this.panel.classList.remove("open");
    this.$(".scrim").classList.remove("open");
    this.panel = null;
  }

  chrome(on) {
    this.root.classList.toggle("chrome", on);
  }

  busy(on) {
    this.root.classList.toggle("busy", on);
  }

  toast(msg) {
    const t = this.$(".toast");
    t.textContent = msg;
    t.classList.add("show");
    clearTimeout(this.toastTimer);
    this.toastTimer = setTimeout(() => t.classList.remove("show"), 1800);
  }

  progress() {
    const { ci, pg } = this.pos;
    return (ci + (pg + 1) / this.chap(ci).pages) / this.book.chapters.length;
  }

  updateChrome() {
    const { ci, pg } = this.pos, ch = this.chap(ci), total = this.book.chapters.length;
    this.$("#r-chap").textContent = ch.title;
    this.$("#r-info").textContent = `Trang ${pg + 1}/${ch.pages}`;
    this.$("#r-pct").textContent = `${ci + 1}/${total} chương · ${Math.round(this.progress() * 100)}%`;
    const slider = this.$("#r-slider");
    slider.max = total - 1;
    slider.value = ci;
    const list = this.$("#toc-list");
    list.querySelector(".cur")?.classList.remove("cur");
    list.querySelector(`[data-ci="${ci}"]`)?.classList.add("cur");
  }

  remember() {
    const ch = this.chap(this.pos.ci);
    saveProgress(this.book.slug, { n: ch.n, i: this.pinned ?? this.anchorOf(this.pos), pct: this.progress(), title: ch.title, ts: Date.now() });
    const hash = `#/read/${encodeURIComponent(this.book.slug)}/${ch.n}`;
    if (location.hash !== hash) history.replaceState(null, "", hash);
  }

  bindSettings() {
    this.$("#settings").addEventListener("click", e => {
      const b = e.target.closest("button"), group = b?.closest("[data-set]");
      if (!group) return;
      const key = group.dataset.set;
      let v;
      if (b.dataset.d) {
        const step = Number(group.dataset.step);
        v = clamp(this.s[key] + Number(b.dataset.d) * step, Number(group.dataset.min), Number(group.dataset.max));
        v = Number(v.toFixed(2));
      } else {
        v = b.dataset.v === "true" ? true : b.dataset.v === "false" ? false : b.dataset.v;
      }
      if (v === this.s[key]) return;
      this.s[key] = v;
      saveSettings(this.s);
      applyLook(this.s);
      this.syncSettings();
      if (key !== "theme" && key !== "anim") this.relayout();
    });
  }

  syncSettings() {
    for (const group of this.$("#settings").querySelectorAll("[data-set]")) {
      const v = this.s[group.dataset.set];
      const out = group.querySelector("output");
      if (out) out.textContent = group.dataset.set === "lh" ? v.toFixed(1) : v;
      for (const b of group.querySelectorAll("[data-v]")) b.setAttribute("aria-pressed", String(b.dataset.v === String(v)));
    }
  }
}
