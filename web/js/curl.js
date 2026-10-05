// Page-curl geometry. The spine is the page's left edge; the free corner C0 (top-right or
// bottom-right) is pulled to P and the page folds along the perpendicular bisector of C0→P.
// Everything is in stage pixels with the origin at the page's top-left.

// Keep the part of a convex polygon on one side of the line through M with normal n:
// sign = 1 keeps (X - M)·n <= 0, sign = -1 keeps the other side.
function clip(poly, M, n, sign) {
  const side = ([x, y]) => sign * ((x - M[0]) * n[0] + (y - M[1]) * n[1]);
  const out = [];
  for (let i = 0; i < poly.length; i++) {
    const a = poly[i], b = poly[(i + 1) % poly.length], da = side(a), db = side(b);
    if (da <= 0) out.push(a);
    if ((da < 0 && db > 0) || (da > 0 && db < 0)) {
      const k = da / (da - db);
      out.push([a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k]);
    }
  }
  return out;
}

function within(P, C, r) {
  const dx = P[0] - C[0], dy = P[1] - C[1], d = Math.hypot(dx, dy);
  return d <= r ? P : [C[0] + dx / d * r, C[1] + dy / d * r];
}

/**
 * t: 0 = page flat, 1 = turned all the way over to the left.
 * bottom: grab the bottom-right corner (else top-right).
 * yOff: extra vertical pull from the finger; lift: how far the corner rises mid-turn.
 * Returns null while the page is flat.
 */
export function curlGeometry(W, H, t, bottom, yOff = 0, lift = 0) {
  const C0 = [W, bottom ? H : 0];
  let P = [W - 2 * W * t, C0[1] + (bottom ? -1 : 1) * lift * Math.sin(Math.PI * t) + yOff];
  // Paper doesn't stretch: the grabbed corner stays within reach of both spine corners.
  P = within(P, [0, C0[1]], W);
  P = within(P, [0, H - C0[1]], Math.hypot(W, H));

  const dx = C0[0] - P[0], dy = C0[1] - P[1], len = Math.hypot(dx, dy);
  if (len < 0.5) return null;
  const n = [dx / len, dy / len];                         // fold normal, pointing at the corner
  const M = [(C0[0] + P[0]) / 2, (C0[1] + P[1]) / 2];     // a point on the fold
  const rect = [[0, 0], [W, 0], [W, H], [0, H]];
  const k = 2 * (M[0] * n[0] + M[1] * n[1]);
  return {
    M, n, len,
    angle: Math.atan2(n[1], n[0]),
    front: clip(rect, M, n, 1),    // still lying flat
    back: clip(rect, M, n, -1),    // folded over (before reflection)
    // reflection across the fold: x' = x - 2((x - M)·n)n, as a CSS matrix(a, b, c, d, e, f)
    matrix: [1 - 2 * n[0] * n[0], -2 * n[0] * n[1], -2 * n[0] * n[1], 1 - 2 * n[1] * n[1], k * n[0], k * n[1]],
  };
}
