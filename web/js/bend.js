// Spine-hinged page turn ("bend"). The page is a sheet bound along its left edge, cut into
// vertical strips placed in 3D: first the paper bulges up near the spine, then the whole sheet
// swings over to the left while its outer part trails behind. Units are stage pixels; z points
// towards the viewer.

const smooth = (a, b, x) => {
  const k = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return k * k * (3 - 2 * k);
};

const HUMP = 0.11;    // bulge height, as a share of the page width
const SPAN = 0.45;    // the bulge covers this share of the page, from the spine
const TRAIL = 0.7;    // how far the outer part lags mid-turn (radians across the page)

/**
 * t: 0 = page flat, 1 = turned over onto the left. Returns, for each of n strips, the position
 * of its left edge (x, z) and its tilt phi (0 = lying flat, π = turned over).
 */
export function bendStrips(t, n, W) {
  const swing = Math.PI * smooth(0.12, 1, t);
  const hump = HUMP * (t < 0.25 ? smooth(0, 0.25, t) : 1 - smooth(0.25, 0.85, t));
  const trail = TRAIL * Math.sin(swing);
  const sw = W / n, out = [];
  let x = 0, z = 0;
  for (let k = 0; k < n; k++) {
    const s = (k + 0.5) / n, u = s / SPAN;
    // slope of the bulge profile 27/4·u(1-u)²: steep at the spine, back down flat at u = 1
    const slope = u < 1 ? (hump * 6.75 * (1 - u) * (1 - 3 * u)) / SPAN : 0;
    const phi = swing + Math.atan(slope) - trail * s;
    out.push({ x, z, phi });
    x += sw * Math.cos(phi);
    z += sw * Math.sin(phi);
  }
  return out;
}

// Light from the front-left: how much brighter (+) or darker (-) a strip tilted by phi looks
// than the flat page. Past 90° the back of the paper faces the viewer.
const LX = -0.5 / Math.hypot(0.5, 1), LZ = 1 / Math.hypot(0.5, 1);
export function shine(phi) {
  const nx = -Math.sin(phi), nz = Math.cos(phi), side = nz >= 0 ? 1 : -1;
  return side * (nx * LX + nz * LZ) - LZ;
}
