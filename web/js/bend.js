// Spine-hinged page turn ("bend"). The page is a sheet bound along its left edge, cut into
// vertical strips placed in 3D. First the paper arches up across its whole width, highest near
// the spine, its outer edge still resting on the page below; then the sheet swings over to the
// left, bending all the way out to its edge as the outer part trails behind and lands last.
// Units are stage pixels; z points towards the viewer.

const smooth = (a, b, x) => {
  const k = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return k * k * (3 - 2 * k);
};

const ARCH = 0.13;    // height of the opening arch, as a share of the page width
const TRAIL = 1.5;    // how far the outer edge lags mid-turn (radians)
const FLEX = 1.4;     // > 1 puts more of the bending towards the outer edge

/**
 * t: 0 = page flat, 1 = turned over onto the left. dir < 0 is a turn back (t runs 1 -> 0).
 * Returns, for each of n strips, the position of its spine-side edge (x, z) and its tilt phi
 * (0 = lying flat on the right, π = lying flat on the left).
 */
export function bendStrips(t, n, W, dir = 1) {
  // Turning back is the same motion mirrored across the spine and run from its own start: the sheet
  // arches as it lifts off the left-hand pages, and lands flat on the right with no bulge left over.
  if (dir < 0) return bendStrips(1 - t, n, W).map(({ x, z, phi }) => ({ x: -x, z, phi: Math.PI - phi }));
  const swing = Math.PI * smooth(0.12, 1, t);
  const arch = ARCH * (t < 0.25 ? smooth(0, 0.25, t) : 1 - smooth(0.25, 0.8, t));
  // Lag grows from nothing (so the outer edge never dips below the page underneath) and fades as the
  // sheet lands, smoothly: a min() of two curves here made the outer edge lurch mid-turn.
  const trail = TRAIL * Math.sin(swing) * (1 - Math.exp(-1.2 * swing));
  const sw = W / n, out = [];
  let x = 0, z = 0;
  for (let k = 0; k < n; k++) {
    const s = (k + 0.5) / n;
    // slope of the arch profile 27/4·s(1-s)²: steep at the spine, back down flat at the edge
    const slope = arch * 6.75 * (1 - s) * (1 - 3 * s);
    const phi = swing + Math.atan(slope) - trail * s ** FLEX;
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
