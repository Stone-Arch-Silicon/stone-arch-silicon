"""Render real chip layouts (GDSII) as a slow 3D camera move.

make_hero.py uses this for shots with "kind": "gds". A shot names a GDS file
(a standard cell, a block, a whole chip in SKY130) and a camera path. Each
frame is drawn from the layout itself: every layer becomes metal or silicon
at its real height in the SKY130 stack (heights stretched so the stack reads
from far away), seen through a perspective camera.

How a frame is drawn. Each layer is rasterised once per shot into a sharp,
anti-aliased mask. Per frame, each layer's mask is projected as a plane at
the layer's top (a homography), swept toward its base for the side walls,
shaded (the reflection of a big soft studio light, which stays put while the
chip slides under it, and bevelled edges lit from the upper left), and laid
over the layers below, which also catch its shadow. A shallow depth of field,
a little bloom and a vignette finish the frame. Needs gdstk and numexpr.

Shot keys for "kind": "gds" (see hero_shots.json):

  "cell"      optional; the top cell by default
  "layers"    optional list of layer names to draw (default: all), e.g. to
              strip the upper metals off and show the transistors
  "z_scale"   how much to stretch heights (1 = true to scale)
  "landscape": {"from": CAM, "to": CAM}, "portrait": {"from": CAM, "to": CAM}
  CAM = {"at": [x, y], "width": w, "tilt": deg, "heading": deg}
        at       point the camera looks at, in microns of the layout
        width    microns across the frame at that point
        tilt     0 looks straight down; 60 is a low, raking view
        heading  compass direction the camera faces; 90 looks toward +y
  optional: "fov" (horizontal degrees, 28), "detail" (texels per pixel, 1.25),
  "dof" (0 = all sharp, 1), "exposure" (stops, 0)
"""
import math

import cv2
import numexpr as ne
import numpy as np

# SKY130 layers, bottom to top: (gds layer, datatype), base height and
# thickness in microns (the SKY130 metal stack), sRGB colour, kind.
# Colours follow the site: dark silicon, maroon polysilicon, brass local
# interconnect, silver aluminium, gold for the top metals.
LAYERS = [
    ('nwell', (64, 20), 0.000, 0.000, (0.070, 0.075, 0.090), 'base'),
    ('diff',  (65, 20), 0.000, 0.050, (0.230, 0.255, 0.245), 'base'),
    ('tap',   (65, 44), 0.000, 0.050, (0.180, 0.200, 0.200), 'base'),
    ('poly',  (66, 20), 0.330, 0.180, (0.470, 0.070, 0.125), 'poly'),
    ('licon', (66, 44), 0.330, 0.606, (0.700, 0.700, 0.690), 'via'),
    ('li1',   (67, 20), 0.936, 0.100, (0.640, 0.520, 0.330), 'li'),
    ('mcon',  (67, 44), 1.036, 0.340, (0.720, 0.720, 0.710), 'via'),
    ('met1',  (68, 20), 1.376, 0.360, (0.380, 0.420, 0.480), 'metal'),
    ('via',   (68, 44), 1.736, 0.270, (0.740, 0.740, 0.730), 'via'),
    ('met2',  (69, 20), 2.006, 0.360, (0.480, 0.490, 0.510), 'metal'),
    ('via2',  (69, 44), 2.366, 0.420, (0.750, 0.745, 0.730), 'via'),
    ('met3',  (70, 20), 2.786, 0.845, (0.540, 0.520, 0.490), 'metal'),
    ('via3',  (70, 44), 3.631, 0.390, (0.780, 0.760, 0.720), 'via'),
    ('met4',  (71, 20), 4.021, 0.845, (0.880, 0.610, 0.130), 'metal'),
    ('via4',  (71, 44), 4.866, 0.505, (0.900, 0.740, 0.420), 'via'),
    ('met5',  (72, 20), 5.371, 1.260, (0.920, 0.660, 0.190), 'metal'),
]
# how each kind of surface takes light: diffuse, specular (reflection of the
# studio light), edge highlight, and the side-wall shade at the top and base
MATERIAL = {
    'base':  dict(diffuse=1.00, spec=0.00, edge=0.0, wall=(0.0, 0.0)),
    'poly':  dict(diffuse=0.22, spec=1.10, edge=1.8, wall=(0.24, 0.07)),
    'li':    dict(diffuse=0.05, spec=2.40, edge=2.8, wall=(0.20, 0.045)),
    'metal': dict(diffuse=0.07, spec=2.60, edge=3.0, wall=(0.26, 0.05)),
    'via':   dict(diffuse=0.14, spec=0.80, edge=1.0, wall=(0.13, 0.035)),
}
LAYER_NAMES = [l[0] for l in LAYERS]

SUBSTRATE = (0.014, 0.016, 0.020)    # sRGB, the silicon between shapes
LIGHT = np.array([-0.60, -0.80])      # screen direction the key light comes from (upper left)


def srgb_to_lin(c):
    c = np.asarray(c, np.float32)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4).astype(np.float32)


_K = {k: np.float32(v) for k, v in dict(t=0.0031308, a=12.92, b=1.055, c=0.055, e=1 / 2.4, z=0.0, o=1.0).items()}


def lin_to_srgb(x):
    return ne.evaluate('where(x <= t, where(x < z, z, x) * a, b * where(x > o, o, x) ** e - c)',
                       local_dict=dict(_K, x=x))


# ---------------------------------------------------------------- layout
_LOADED = {}


def load(path, cell=None):
    """Parse a GDS file once, however many shots use it."""
    key = (path, cell)
    if key not in _LOADED:
        _LOADED[key] = Layout(path, cell)
    return _LOADED[key]


class Layout:
    """Flattened polygons of one cell, grouped by layer."""

    def __init__(self, path, cell=None):
        import gdstk   # only needed for gds shots
        lib = gdstk.read_gds(path)
        if cell:
            found = [c for c in lib.cells if c.name == cell]
            if not found:
                raise SystemExit('No cell named {} in {}'.format(cell, path))
            top = found[0]
        else:
            top = max(lib.top_level(), key=lambda c: _area(c.bounding_box()))
        self.name = top.name
        (x0, y0), (x1, y1) = top.bounding_box()
        self.bbox = (x0, y0, x1, y1)
        self.polys = {}
        for name, (layer, dt), *_ in LAYERS:
            ps = top.get_polygons(layer=layer, datatype=dt)
            if not ps:
                continue
            pts = [p.points for p in ps]
            bb = np.array([[q[:, 0].min(), q[:, 1].min(), q[:, 0].max(), q[:, 1].max()] for q in pts])
            self.polys[name] = (pts, bb)

    def raster(self, name, roi, texel):
        """Anti-aliased uint8 mask of one layer over roi = (x0, y0, x1, y1) microns."""
        x0, y0, x1, y1 = roi
        w = int(math.ceil((x1 - x0) / texel))
        h = int(math.ceil((y1 - y0) / texel))
        mask = np.zeros((h, w), np.uint8)
        if name not in self.polys:
            return mask
        pts, bb = self.polys[name]
        keep = np.nonzero((bb[:, 2] >= x0) & (bb[:, 0] <= x1) & (bb[:, 3] >= y0) & (bb[:, 1] <= y1))[0]
        k = 16.0 / texel    # cv2 fixed point with 4 fractional bits
        batch = []
        for i in keep:
            q = pts[i]
            a = np.empty((len(q), 2), np.int32)
            a[:, 0] = np.round((q[:, 0] - x0) * k - 8)   # texel centres sit on whole numbers
            a[:, 1] = np.round((y1 - q[:, 1]) * k - 8)
            batch.append(a)
            if len(batch) >= 20000:
                cv2.fillPoly(mask, batch, 255, lineType=cv2.LINE_AA, shift=4)
                batch = []
        if batch:
            cv2.fillPoly(mask, batch, 255, lineType=cv2.LINE_AA, shift=4)
        return mask


def _area(bb):
    if bb is None:
        return 0
    (x0, y0), (x1, y1) = bb
    return (x1 - x0) * (y1 - y0)


# ---------------------------------------------------------------- camera
class Camera:
    """Pinhole camera looking at a point on the chip. Lengths in microns."""

    def __init__(self, cam, out_w, out_h, fov=28.0):
        tx, ty = cam['at']
        tilt = math.radians(cam.get('tilt', 40.0))
        heading = math.radians(cam.get('heading', 90.0))
        half = math.radians(fov) / 2
        f = (out_w / 2.0) / math.tan(half)
        dist = cam['width'] / (2 * math.tan(half))
        st, ct = math.sin(tilt), math.cos(tilt)
        sp, cp = math.sin(heading), math.cos(heading)
        fwd = np.array([st * cp, st * sp, -ct])
        right = np.array([sp, -cp, 0.0])
        up = np.cross(right, fwd)
        self.R = np.stack([right, -up, fwd])          # world -> camera: x right, y down, z forward
        self.C = np.array([tx, ty, 0.0]) - dist * fwd
        self.K = np.array([[f, 0, out_w / 2.0], [0, f, out_h / 2.0], [0, 0, 1]])
        self.w, self.h = out_w, out_h

    def plane(self, z):
        """Homography from (x, y, 1) on the plane at height z to pixels."""
        t = -self.R @ self.C
        return self.K @ np.column_stack([self.R[:, 0], self.R[:, 1], self.R[:, 2] * z + t])

    def project(self, x, y, z):
        p = self.K @ (self.R @ (np.array([x, y, z]) - self.C))
        return p[:2] / p[2]

    def footprint(self, z=0.0, margin=0.12):
        """Bounding box, in microns, of what the frame sees on the plane at height z."""
        Hinv = np.linalg.inv(self.plane(z))
        mx, my = self.w * margin, self.h * margin
        pts = np.array([[-mx, -my, 1], [self.w + mx, -my, 1], [-mx, self.h + my, 1],
                        [self.w + mx, self.h + my, 1]], float).T
        p = Hinv @ pts
        p[2] = np.where(p[2] <= 1e-9, 1e-9, p[2])    # frame top past the horizon
        xy = p[:2] / p[2]
        return xy[0].min(), xy[1].min(), xy[0].max(), xy[1].max()


def lerp_cam(a, b, u):
    """Straight-line move; width (zoom) changes geometrically."""
    out = {'at': [a['at'][0] + (b['at'][0] - a['at'][0]) * u, a['at'][1] + (b['at'][1] - a['at'][1]) * u],
           'width': a['width'] * (b['width'] / a['width']) ** u}
    for k, d in (('tilt', 40.0), ('heading', 90.0)):
        va, vb = a.get(k, d), b.get(k, d)
        out[k] = va + (vb - va) * u
    return out


def _shift(img, dx, dy):
    """img moved by whole pixels (dx, dy), zeros shifted in."""
    h, w = img.shape[:2]
    out = np.zeros_like(img)
    if abs(dx) >= w or abs(dy) >= h:
        return out
    xs, xd = (0, dx) if dx >= 0 else (-dx, 0)
    ys, yd = (0, dy) if dy >= 0 else (-dy, 0)
    out[yd:h - ys if ys else h, xd:w - xs if xs else w] = img[ys:h - yd if yd else h, xs:w - xd if xd else w]
    return out


# ---------------------------------------------------------------- shot
class LayoutShot:
    """One gds shot at one output size. render(u) draws the frame at u in [0, 1]."""

    def __init__(self, layout, shot, orient, out_w, out_h):
        self.path = shot[orient]
        self.w, self.h = out_w, out_h
        self.fov = float(shot.get('fov', 28.0))
        self.dof = float(shot.get('dof', 1.0))
        self.zs = float(shot.get('z_scale', 4.0))
        self.gain = 2.0 ** float(shot.get('exposure', 0.0))
        wanted = shot.get('layers') or LAYER_NAMES
        unknown = set(wanted) - set(LAYER_NAMES)
        if unknown:
            raise SystemExit('Unknown layers: ' + ', '.join(sorted(unknown)))
        self.layers = [l for l in LAYERS if l[0] in wanted and l[0] in layout.polys]
        # rasterise what the camera sees over the whole move, clipped to the layout
        cams = [Camera(lerp_cam(self.path['from'], self.path['to'], u), out_w, out_h, self.fov)
                for u in (0.0, 0.25, 0.5, 0.75, 1.0)]
        ztop = max(z + t for _, _, z, t, _, _ in self.layers) * self.zs
        boxes = np.array([c.footprint(0.0) for c in cams] + [c.footprint(ztop) for c in cams])
        lx0, ly0, lx1, ly1 = layout.bbox
        pad = 1.0
        roi = (max(boxes[:, 0].min(), lx0 - pad), max(boxes[:, 1].min(), ly0 - pad),
               min(boxes[:, 2].max(), lx1 + pad), min(boxes[:, 3].max(), ly1 + pad))
        # about `detail` texels per output pixel at the frame centre, at the closest point of the move
        texel = min(self.path['from']['width'], self.path['to']['width']) / out_w / float(shot.get('detail', 1.25))
        texel = max(texel, max(roi[2] - roi[0], roi[3] - roi[1]) / 14000.0)   # memory cap
        self.roi, self.texel = roi, texel
        self.tex = {}
        for name, *_ in self.layers:
            m = layout.raster(name, roi, texel)
            pyr = [m]
            while min(pyr[-1].shape) > 64 and len(pyr) < 7:
                pyr.append(cv2.resize(pyr[-1], (pyr[-1].shape[1] // 2, pyr[-1].shape[0] // 2),
                                      interpolation=cv2.INTER_AREA))
            self.tex[name] = pyr
        self.layers = [l for l in self.layers if self.tex[l[0]][0].any()]

        self.base = srgb_to_lin(SUBSTRATE)
        yy, xx = np.mgrid[0:out_h, 0:out_w].astype(np.float32)
        xx /= out_w
        yy /= out_h
        # what flat metal reflects: a large soft studio light up and to the right
        # (fixed in the frame, so highlights slide along the chip as it moves),
        # over a dim gradient that brightens toward the far edge
        sx, sy = xx - 0.74, yy - 0.26
        box = np.exp(-(sx * sx / 0.055 + sy * sy / 0.022))
        self.env = (0.03 + 0.07 * (1.0 - yy) + 1.0 * box).astype(np.float32)
        r2 = ((xx - 0.5) * 1.05) ** 2 + ((yy - 0.52) * 0.95) ** 2
        self.vignette = (1.0 - 0.6 * np.clip(r2, 0, 1)).astype(np.float32)
        d = np.abs(yy - 0.52) * 2.0                 # 0 in the focus band, 1 at the top and bottom
        w1 = np.clip(d * 2.2 - 0.35, 0, 1)
        w2 = np.clip(d * 2.0 - 1.0, 0, 1)
        # weights of the sharp, slightly blurred and more blurred frames
        self.dof_w = tuple(np.ascontiguousarray(w, np.float32) for w in (1 - w1, w1 * (1 - w2), w1 * w2))

    def _tex_to_world(self, level):
        x0, y0, x1, y1 = self.roi
        s = self.texel
        k = 2 ** level
        off = (k - 1) / 2.0
        S = np.array([[s, 0, x0], [0, -s, y1], [0, 0, 1]], float)
        return S @ np.array([[k, 0, off], [0, k, off], [0, 0, 1]], float)

    def _level(self, M0):
        """Mip level from how much the texture shrinks at the frame centre."""
        p = np.linalg.inv(M0) @ np.array([self.w / 2, self.h / 2, 1.0])
        p = p / p[2]
        q0, q1, q2 = M0 @ p, M0 @ (p + [1, 0, 0]), M0 @ (p + [0, 1, 0])
        a = q1[:2] / q1[2] - q0[:2] / q0[2]
        b = q2[:2] / q2[2] - q0[:2] / q0[2]
        scale = math.sqrt(max(abs(a[0] * b[1] - a[1] * b[0]), 1e-12))   # pixels per texel (area)
        return max(0, int(round(math.log2(1.0 / scale) - 0.25))) if scale < 1 else 0

    def render(self, u):
        # numexpr reads the local variables named in each expression string
        cam = Camera(lerp_cam(self.path['from'], self.path['to'], u), self.w, self.h, self.fov)
        W, H, zs = self.w, self.h, self.zs
        f32 = np.float32
        one, inv255, k_sh = f32(1), f32(1.0 / 255.0), f32(0.62)
        lo_f, hi_f = f32(-0.25), f32(0.6)
        # the frame is kept as three planes (R, G, B): numexpr is fastest on contiguous arrays
        acc = [np.full((H, W), self.base[c], np.float32) for c in range(3)]
        env = self.env
        # where the frame centre's ground point appears for a height z: gives the wall sweep
        g = np.linalg.inv(cam.plane(0.0)) @ np.array([W / 2, H / 2, 1.0])
        gx, gy = g[0] / g[2], g[1] / g[2]
        lightdir = LIGHT / np.linalg.norm(LIGHT)
        nlx, nly = f32(-0.25 * lightdir[0]), f32(-0.25 * lightdir[1])   # Sobel scale folded in
        small = (max(1, W // 2), max(1, H // 2))

        for name, gds, z, t, col, kind in self.layers:
            zb, zt = z * zs, (z + t) * zs
            pyr = self.tex[name]
            M0 = cam.plane(zt) @ self._tex_to_world(0)
            lv = min(self._level(M0), len(pyr) - 1)
            M = cam.plane(zt) @ self._tex_to_world(lv)
            top = cv2.warpPerspective(pyr[lv], M, (W, H), flags=cv2.INTER_LINEAR, borderValue=0)
            if not cv2.countNonZero(top):
                continue
            mt = top.astype(np.float32)
            mt *= inv255
            colour = (srgb_to_lin(col) * self.gain).astype(np.float32)
            mat = MATERIAL[kind]
            dif, spc, edg = f32(mat['diffuse']), f32(mat['spec']), f32(mat['edge'])

            # top face: diffuse plus the reflected studio light, with lit and shaded bevels
            if kind == 'base':
                q = ne.evaluate('dif * mt')
                keep = ne.evaluate('one - mt')
            else:
                b = cv2.GaussianBlur(mt, (0, 0), 0.9)
                ex = cv2.Sobel(b, cv2.CV_32F, 1, 0, ksize=3)
                ey = cv2.Sobel(b, cv2.CV_32F, 0, 1, ksize=3)
                fc = ne.evaluate('ex * nlx + ey * nly')                 # > 0 on edges that face the light
                shade = ne.evaluate('(dif + spc * env) * (one + edg * where(fc < lo_f, lo_f, where(fc > hi_f, hi_f, fc)))')

                # shadow on everything below, cast away from the light, soft
                off = -lightdir * (1.2 + 0.45 * math.hypot(*(cam.project(gx, gy, zt) - cam.project(gx, gy, 0.0))))
                ms = cv2.resize(mt, small, interpolation=cv2.INTER_AREA)
                ms = cv2.warpAffine(ms, np.float32([[1, 0, off[0] / 2], [0, 1, off[1] / 2]]), small, borderValue=0)
                ms = cv2.GaussianBlur(ms, (0, 0), 0.8 + 0.25 * math.hypot(*off))
                sh = cv2.resize(ms, (W, H), interpolation=cv2.INTER_LINEAR)

                # side walls: the top face swept, pixel by pixel, toward where its base appears;
                # lvl keeps how close to the top edge the visible wall point is
                d = cam.project(gx, gy, zb) - cam.project(gx, gy, zt)
                steps = int(min(24, math.floor(math.hypot(*d))))
                if steps >= 1:
                    cov = np.zeros_like(top)
                    lvl = np.zeros_like(top)
                    for k in range(steps, 0, -1):
                        s = _shift(top, int(round(d[0] * k / steps)), int(round(d[1] * k / steps)))
                        cv2.max(cov, s, dst=cov)
                        _, tk = cv2.threshold(s, 96, steps - k + 1, cv2.THRESH_BINARY)
                        cv2.max(lvl, tk, dst=lvl)
                    wa = cov.astype(np.float32)
                    wa *= inv255
                    wl = lvl.astype(np.float32)
                    hi, lo = f32(mat['wall'][0]), f32(mat['wall'][1])
                    ist = f32(1.0 / steps)
                    keep = ne.evaluate('(one - (mt + wa * (one - mt))) * (one - k_sh * sh)')
                    q = ne.evaluate('shade * mt + (lo + (hi - lo) * (wl * ist)) * wa * (one - mt)')
                else:
                    keep = ne.evaluate('(one - mt) * (one - k_sh * sh)')
                    q = ne.evaluate('shade * mt')
            for c in range(3):
                a, cc = acc[c], colour[c]
                ne.evaluate('a * keep + q * cc', out=a)

        # finish: depth of field toward the top and bottom, bloom, vignette
        if self.dof > 0:
            c0, c1, c2 = self.dof_w
            for c in range(3):
                a = acc[c]
                b1 = cv2.GaussianBlur(a, (0, 0), 1.1 * self.dof)
                b2 = cv2.GaussianBlur(a, (0, 0), 3.2 * self.dof)
                acc[c] = ne.evaluate('a * c0 + b1 * c1 + b2 * c2')
        r_, g_, b_ = acc
        lum = ne.evaluate('0.2126 * r_ + 0.7152 * g_ + 0.0722 * b_').astype(np.float32)
        glow = cv2.GaussianBlur(cv2.resize(cv2.max(lum - 0.42, 0.0), small, interpolation=cv2.INTER_AREA), (0, 0), 7)
        glow = cv2.resize(glow, (W, H), interpolation=cv2.INTER_LINEAR)
        vig = self.vignette
        out = []
        for c, tint in enumerate((0.50, 0.40, 0.26)):
            a, tc = acc[c], f32(tint)
            out.append(lin_to_srgb(ne.evaluate('(a + glow * tc) * vig')))
        return cv2.merge(out)
