// Settings and reading progress, kept in this browser only.
const PREFIX = "tutruyen:";

function get(key, fallback) {
  try {
    const v = localStorage.getItem(PREFIX + key);
    return v ? JSON.parse(v) : fallback;
  } catch {
    return fallback;
  }
}

function set(key, value) {
  try {
    localStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch { /* private mode or storage full: settings just won't persist */ }
}

export const FONTS = {
  literata: '"Literata", Georgia, serif',
  noto: '"Noto Serif", Georgia, serif',
  vietnam: '"Be Vietnam Pro", system-ui, sans-serif',
  system: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
};
export const MARGINS = { narrow: 14, normal: 26, wide: 44 };

export function loadSettings() {
  const dark = window.matchMedia?.("(prefers-color-scheme: dark)").matches;
  const s = {
    theme: dark ? "dark" : "light", font: "literata", size: 18, lh: 1.6,
    margin: "normal", justify: true, anim: "curl", bilingual: false,
    ...get("settings", {}),
  };
  if (!(s.font in FONTS)) s.font = "literata";
  if (!(s.margin in MARGINS)) s.margin = "normal";
  if (!["curl", "bend", "slide", "none"].includes(s.anim)) s.anim = "curl";
  return s;
}

export const saveSettings = s => set("settings", s);
export const loadProgress = slug => get("progress:" + slug, null);
export const saveProgress = (slug, p) => set("progress:" + slug, p);
