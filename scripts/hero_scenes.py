"""Procedural scenes for the home-page hero film.

The hero shows the digital design flow, drawn from scratch: SystemVerilog being
written, a simulation running, a clock tree being routed across standard cells,
and the finished die. Nothing in it is fab equipment, and every frame is the
club's own work, so there are no outside credits or licenses to track.

make_hero.py moves its camera across a scene exactly as it does across a photo.
A shot in scripts/hero_shots.json picks a scene with "kind": "scene" and
"scene": one of SCENES below, plus optional "params" for that scene.

Each scene is drawn once at a fixed size in pixels and reused for both the
landscape and the portrait film. Drawing needs numpy, OpenCV, Pillow and
fontTools (with brotli, to read the site's woff2 fonts).
"""
import math
import os
import tempfile

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _rgb(hexstr):
    return np.array([int(hexstr[i:i + 2], 16) for i in (1, 3, 5)], np.float32) / 255.0


# the site's palette (assets/site.css)
BG = _rgb('#060607')
GOLD = _rgb('#e3a81b')
WHITE = _rgb('#f4f4f2')


def grey(v):
    return np.array([v, v, v], np.float32)


def col(c):
    """cv2 drawing colour from an RGB float array."""
    return tuple(float(x) for x in c)


# ---------------------------------------------------------------- fonts
_FONTS = {}


def font(size, weight=400, family='GeistMono'):
    """The site's own Geist fonts, instanced from the variable woff2 files."""
    path = os.path.join(tempfile.gettempdir(), 'sasi-{}-{}.ttf'.format(family, weight))
    if not os.path.exists(path):
        from fontTools.ttLib import TTFont
        from fontTools.varLib import instancer
        f = TTFont(os.path.join(ROOT, 'assets', family + '-Variable.woff2'))
        f = instancer.instantiateVariableFont(f, {'wght': weight})
        f.flavor = None
        f.save(path)
    key = (path, int(round(size)))
    if key not in _FONTS:
        _FONTS[key] = ImageFont.truetype(path, int(round(size)))
    return _FONTS[key]


def text_mask(w, h, items):
    """items: (x, y, text, font[, anchor]). Returns a float32 coverage mask."""
    im = Image.new('L', (w, h), 0)
    d = ImageDraw.Draw(im)
    for it in items:
        x, y, s, f = it[:4]
        d.text((x, y), s, font=f, fill=255, anchor=it[4] if len(it) > 4 else 'ls')
    return np.asarray(im, np.float32) / 255.0


def paint(img, mask, colour, alpha=1.0):
    """Blend a colour into img wherever mask (0..1) is set."""
    a = mask[..., None] * alpha
    img *= 1.0 - a
    img += a * colour


# ---------------------------------------------------------------- camera
def camera_matrix(src_w, src_h, cx, cy, wfrac, rot_deg, tilt, out_w, out_h):
    """3x3 map from output pixels to source pixels. tilt = [rx, ry] in degrees
    swings the camera about the frame's centre for a perspective view."""
    sx = wfrac * src_w / out_w
    th = math.radians(rot_deg)
    c, n = math.cos(th) * sx, math.sin(th) * sx
    ox, oy = out_w / 2.0, out_h / 2.0
    ccx, ccy = cx * src_w, cy * src_h
    A = np.array([[c, -n, ccx - c * ox + n * oy],
                  [n, c, ccy - n * ox - c * oy],
                  [0, 0, 1]], np.float64)
    if tilt and (tilt[0] or tilt[1]):
        rx, ry = math.radians(tilt[0]), math.radians(tilt[1])
        f = 1.1 * math.hypot(out_w, out_h)
        K = np.array([[f, 0, ox], [0, f, oy], [0, 0, 1]])
        Rx = np.array([[1, 0, 0], [0, math.cos(rx), -math.sin(rx)], [0, math.sin(rx), math.cos(rx)]])
        Ry = np.array([[math.cos(ry), 0, math.sin(ry)], [0, 1, 0], [-math.sin(ry), 0, math.cos(ry)]])
        H = K @ Ry @ Rx @ np.linalg.inv(K)
        p = H @ np.array([ox, oy, 1.0])
        p /= p[2]
        H = np.array([[1, 0, ox - p[0]], [0, 1, oy - p[1]], [0, 0, 1]]) @ H
        A = A @ np.linalg.inv(H)
    return A


def _apply(M, x, y):
    p = M @ np.array([x, y, 1.0])
    return p[0] / p[2], p[1] / p[2]


def source_scale(M, out_w, out_h):
    """Source pixels per output pixel at the centre of the frame."""
    x, y = out_w / 2.0, out_h / 2.0
    a = _apply(M, x, y)
    b = _apply(M, x + 1, y)
    c = _apply(M, x, y + 1)
    det = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return math.sqrt(abs(det))


# ---------------------------------------------------------------- base
class Scene:
    """A drawing the camera moves over. image(tau) is the full canvas at local
    time tau (seconds into the shot), float32 sRGB in [0, 1]."""
    static = False

    def __init__(self, params):
        self.params = params
        self._pyr = None
        self._pyr_key = None

    def image(self, tau):
        raise NotImplementedError

    def _pyramid(self, tau, levels):
        key = 'static' if self.static else tau
        if self._pyr_key != key:
            self._pyr = [self.image(tau)]
            self._pyr_key = key
        while len(self._pyr) <= levels:
            p = self._pyr[-1]
            self._pyr.append(cv2.resize(p, (max(1, p.shape[1] // 2), max(1, p.shape[0] // 2)),
                                        interpolation=cv2.INTER_AREA))
        return self._pyr

    def view(self, tau, cx, cy, wfrac, rot, tilt, out_w, out_h):
        """Render the camera's view. Uses a mip pyramid when the camera pulls back
        so fine layout detail averages out instead of shimmering."""
        M = camera_matrix(self.w, self.h, cx, cy, wfrac, rot, tilt, out_w, out_h)
        scale = source_scale(M, out_w, out_h)
        lv = max(0.0, math.log2(scale)) if scale > 1.0 else 0.0
        l0 = int(math.floor(lv))
        frac = lv - l0
        pyr = self._pyramid(tau, l0 + (1 if frac > 0.02 else 0))
        out = self._warp(pyr[l0], M, l0, out_w, out_h)
        if frac > 0.02:
            out = out * (1 - frac) + self._warp(pyr[l0 + 1], M, l0 + 1, out_w, out_h) * frac
        return np.clip(out, 0.0, 1.0)

    @staticmethod
    def _warp(img, M, level, out_w, out_h):
        k = 1.0 / (2 ** level)
        S = np.array([[k, 0, 0.5 * k - 0.5], [0, k, 0.5 * k - 0.5], [0, 0, 1]])
        return cv2.warpPerspective(img, S @ M, (out_w, out_h), flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP,
                                   borderMode=cv2.BORDER_CONSTANT, borderValue=col(BG))


def canvas(w, h, colour=BG):
    img = np.empty((h, w, 3), np.float32)
    img[:] = colour
    return img


# ================================================================ RTL
RTL = r"""// systolic_pe.sv : one processing element of a systolic matrix multiplier
// Stone Arch Silicon, RTL subteam

module systolic_pe #(
  parameter int W   = 8,
  parameter int ACC = 2*W + 4
) (
  input  logic           clk,
  input  logic           rst_n,
  input  logic           en,
  input  logic [W-1:0]   a_in,    // from the west
  input  logic [W-1:0]   b_in,    // from the north
  output logic [W-1:0]   a_out,   // to the east
  output logic [W-1:0]   b_out,   // to the south
  output logic [ACC-1:0] acc
);

  logic [2*W-1:0] prod;
  assign prod = a_in * b_in;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      a_out <= '0;
      b_out <= '0;
      acc   <= '0;
    end else if (en) begin
      a_out <= a_in;
      b_out <= b_in;
      acc   <= acc + ACC'(prod);
    end
  end

endmodule
"""

KEYWORDS = {'module', 'endmodule', 'parameter', 'input', 'output', 'logic', 'int', 'assign',
            'always_ff', 'posedge', 'negedge', 'or', 'begin', 'end', 'if', 'else'}


def tokenize_sv(line):
    """Split a line of SystemVerilog into (text, kind) runs."""
    out, i = [], 0
    while i < len(line):
        ch = line[i]
        if line.startswith('//', i):
            out.append((line[i:], 'comment'))
            break
        if ch.isalpha() or ch == '_':
            j = i
            while j < len(line) and (line[j].isalnum() or line[j] in '_$'):
                j += 1
            word = line[i:j]
            if j < len(line) and line[j] == "'":          # sized cast, like ACC'(x)
                out.append((word + "'", 'number'))
                i = j + 1
                continue
            out.append((word, 'keyword' if word in KEYWORDS else 'ident'))
            i = j
        elif ch.isdigit() or (ch == "'" and i + 1 < len(line) and line[i + 1] in '0123456789bhd'):
            j = i + 1
            while j < len(line) and (line[j].isalnum() or line[j] == "'"):
                j += 1
            out.append((line[i:j], 'number'))
            i = j
        elif ch == ' ':
            j = i
            while j < len(line) and line[j] == ' ':
                j += 1
            out.append((line[i:j], 'space'))
            i = j
        else:
            out.append((ch, 'punct'))
            i += 1
    return out


class RTLScene(Scene):
    """SystemVerilog in the site's mono font, typed out with a gold cursor."""
    COLOURS = {
        'keyword': WHITE * 0.97,
        'ident': grey(0.68),
        'number': GOLD,
        'punct': grey(0.44),
        'comment': grey(0.34),
    }

    def __init__(self, params):
        super().__init__(params)
        self.w, self.h = params.get('size', [2600, 1800])
        size = params.get('font', 31)
        self.lh = int(round(size * 1.6))
        f = font(size, 400)
        self.adv = f.getlength('M')
        x_code, x_num, y0 = 330, 270, 130
        lines = RTL.rstrip('\n').split('\n')
        type_from = params.get('type_from', 26)          # 1-based line where typing starts
        cps = params.get('cps', 30.0)
        t = params.get('type_start', 0.5)
        rng = np.random.default_rng(params.get('seed', 3))

        masks = {k: [] for k in self.COLOURS}
        nums, nums_hi = [], []
        self.tmap = np.full((self.h, self.w), -1e9, np.float32)
        self.cursor = []      # (time, x, y, line): where the cursor sits from that time on
        ascent = f.getmetrics()[0]
        for li, line in enumerate(lines):
            y = y0 + li * self.lh
            base = y + ascent
            (nums_hi if li + 1 >= type_from else nums).append((x_num, base, str(li + 1), f, 'rs'))
            col_i = 0
            typing = li + 1 >= type_from
            if typing and li + 1 > type_from:
                t += 0.16                                   # newline, then auto-indent
            lead = len(line) - len(line.lstrip(' '))
            if typing:
                self.cursor.append((t, x_code + lead * self.adv, y, li))
            for text, kind in tokenize_sv(line):
                for ch in text:
                    x = x_code + col_i * self.adv
                    if kind != 'space':
                        masks[kind].append((x, base, ch, f))
                    if typing and col_i >= lead:
                        x0, x1 = int(x), int(math.ceil(x + self.adv))
                        self.tmap[y - 4:y + self.lh - 4, x0:x1] = t
                        self.cursor.append((t, x + self.adv, y, li))
                        t += (1.0 / cps) * rng.uniform(0.6, 1.4)
                    col_i += 1
        self.cursor.sort()
        self.text = canvas(self.w, self.h)
        for kind, items in masks.items():
            if items:
                paint(self.text, text_mask(self.w, self.h, items), self.COLOURS[kind])
        self.gutter = canvas(self.w, self.h, np.zeros(3, np.float32))
        paint(self.gutter, text_mask(self.w, self.h, nums), grey(0.24))
        self.gutter_hi = text_mask(self.w, self.h, nums_hi)
        # a hairline down the gutter, like an editor
        self.text[:, x_num + 22:x_num + 23] = grey(0.11)
        self.x_code = x_code

    def image(self, tau):
        img = np.where((self.tmap <= tau)[..., None], self.text, BG[None, None, :])
        img = img + self.gutter
        cur = None
        for c in self.cursor:
            if c[0] <= tau:
                cur = c
        if cur is None:
            cur = self.cursor[0]
        _, x, y, li = cur
        # current line: a faint band and a brighter line number; lines below it don't exist yet
        a, b = y - 6, y + self.lh - 6
        img[a:b, self.x_code - 50:] += 0.028
        paint(img[:a], self.gutter_hi[:a], grey(0.24))
        paint(img[a:b], self.gutter_hi[a:b], grey(0.72))
        # gold block cursor; it blinks only while idle
        idle = tau - cur[0]
        if idle < 0.35 or (idle % 1.0) < 0.55:
            x0 = int(round(x)) + 1
            img[y + 2:y + self.lh - 12, x0:x0 + 3] = GOLD
        return img


# ================================================================ waveforms
class WaveScene(Scene):
    """A simulation running: a timing diagram of the systolic PE, with values that
    actually follow from the RTL (prod = a*b, acc accumulates, a_out lags a_in)."""

    def __init__(self, params):
        super().__init__(params)
        self.w, self.h = params.get('size', [2800, 1500])
        rng = np.random.default_rng(params.get('seed', 11))
        P = params.get('period', 66)
        x0 = 640
        ncyc = (self.w - 40 - x0) // P
        x1 = x0 + ncyc * P
        self.x0, self.x1, self.P = x0, x1, P
        self.head = params.get('head', [1500, 2600])
        self.ns = params.get('ns_per_cycle', 10)

        # ---- signal values per cycle
        state = []
        for k in range(ncyc):
            state.append('IDLE' if k < 2 else 'LOAD' if k < 4 else 'RUN' if k < ncyc - 5 else 'DRAIN' if k < ncyc - 2 else 'IDLE')
        run = [s == 'RUN' for s in state]
        a = [int(rng.integers(1, 256)) if r else 0 for r in run]
        b = [int(rng.integers(1, 256)) if r else 0 for r in run]
        prod = [x * y for x, y in zip(a, b)]
        acc, s_ = [], 0
        for k in range(ncyc):
            acc.append(s_)
            if run[k]:
                s_ = (s_ + prod[k]) & 0xFFFFF
        a_out = [0] + a[:-1]
        b_out = [0] + b[:-1]
        ready = [1 if state[k] in ('IDLE', 'RUN') and k >= 2 else 0 for k in range(ncyc)]
        rst = [0 if k < 2 else 1 for k in range(ncyc)]
        en = [1 if r else 0 for r in run]
        valid = [1 if state[k] == 'DRAIN' else 0 for k in range(ncyc)]
        rows = [
            ('clk', '', 'clk', None),
            ('rst_n', '', 'bit', rst),
            ('en', '', 'bit', en),
            ('state', '[1:0]', 'bus', state),
            ('acc', '[19:0]', 'bus', ['{:05X}'.format(v) for v in acc]),
            ('a_in', '[7:0]', 'bus', ['{:02X}'.format(v) for v in a]),
            ('b_in', '[7:0]', 'bus', ['{:02X}'.format(v) for v in b]),
            ('prod', '[15:0]', 'bus', ['{:04X}'.format(v) for v in prod]),
            ('a_out', '[7:0]', 'bus', ['{:02X}'.format(v) for v in a_out]),
            ('b_out', '[7:0]', 'bus', ['{:02X}'.format(v) for v in b_out]),
            ('ready', '', 'bit', ready),
            ('valid', '', 'bit', valid),
        ]

        top, pitch, amp = 222, 96, 32
        self.names = canvas(self.w, self.h)
        self.waves = canvas(self.w, self.h)
        fn, fw, fv, fr = font(23, 400), font(23, 400), font(18, 400), font(18, 400)

        # names column
        items, dim = [], []
        for i, (name, width, _, _) in enumerate(rows):
            y = top + i * pitch + 8
            items.append((150, y, name, fn))
            dim.append((150 + fn.getlength(name) + 6, y, width, fw))
        paint(self.names, text_mask(self.w, self.h, items), grey(0.66))
        paint(self.names, text_mask(self.w, self.h, dim), grey(0.32))
        self.names[150:self.h - 40, x0 - 40:x0 - 39] = grey(0.13)

        # ruler, revealed with the waves
        w = self.waves
        cv2.line(w, (x0, 128), (x1, 128), col(grey(0.2)), 1, cv2.LINE_AA)
        labels = []
        for k in range(ncyc + 1):
            x = x0 + k * P
            cv2.line(w, (x, 128), (x, 128 - (14 if k % 4 == 0 else 7)), col(grey(0.3)), 1, cv2.LINE_AA)
            if k % 4 == 0:
                labels.append((x + 6, 120, '{} ns'.format(k * self.ns), fr))
            cv2.line(w, (x, 150), (x, self.h - 40), col(grey(0.055)), 1)
        paint(w, text_mask(self.w, self.h, labels), grey(0.4))

        vals = []
        sh = 4    # shift for sub-pixel AA drawing
        S = 1 << sh

        def pts(seq):
            return (np.array(seq, np.float64) * S).round().astype(np.int32).reshape(-1, 1, 2)

        for i, (name, width, kind, v) in enumerate(rows):
            mid = top + i * pitch
            hi, lo = mid - amp / 2, mid + amp / 2
            line_c = grey(0.82) if name != 'clk' else grey(0.5)
            if name == 'acc':
                line_c = GOLD
            if kind in ('clk', 'bit'):
                seq = []
                if kind == 'clk':
                    for k in range(ncyc):
                        xa = x0 + k * P
                        seq += [(xa, lo), (xa, hi), (xa + P / 2, hi), (xa + P / 2, lo)]
                    seq.append((x1, lo))
                else:
                    level = v[0]
                    seq.append((x0, hi if level else lo))
                    for k in range(1, ncyc):
                        if v[k] != level:
                            xk = x0 + k * P
                            seq += [(xk, hi if level else lo), (xk + 3, hi if v[k] else lo)]
                            level = v[k]
                    seq.append((x1, hi if level else lo))
                cv2.polylines(w, [pts(seq)], False, col(line_c), 2, cv2.LINE_AA, sh)
            else:
                k = 0
                fill = np.zeros((self.h, self.w), np.float32)
                while k < ncyc:
                    j = k
                    while j + 1 < ncyc and v[j + 1] == v[k]:
                        j += 1
                    xa, xb = x0 + k * P, x0 + (j + 1) * P
                    e = 7
                    poly = [(xa, mid), (xa + e, hi), (xb - e, hi), (xb, mid), (xb - e, lo), (xa + e, lo)]
                    cv2.fillPoly(fill, [pts(poly)], 1.0, cv2.LINE_AA, sh)
                    cv2.polylines(w, [pts(poly)], True, col(line_c), 2, cv2.LINE_AA, sh)
                    label = v[k]
                    if fv.getlength(label) + 9 < xb - xa:
                        vals.append(((xa + xb) / 2, mid + 7, label, fv, 'ms', name == 'acc'))
                    k = j + 1
                paint(w, fill, GOLD if name == 'acc' else WHITE, 0.07 if name == 'acc' else 0.045)
        paint(w, text_mask(self.w, self.h, [x[:5] for x in vals if not x[5]]), grey(0.86))
        paint(w, text_mask(self.w, self.h, [x[:5] for x in vals if x[5]]), GOLD)
        self.top = 96
        self.flab = font(20, 500)

    def head_x(self, tau):
        T = self.params.get('span', 4.6)
        u = min(max(tau / T, 0.0), 1.0)
        return self.head[0] + (self.head[1] - self.head[0]) * u

    def image(self, tau):
        hx = self.head_x(tau)
        h = int(hx)
        img = self.names.copy()
        img[:, self.x0 - 2:h] = self.waves[:, self.x0 - 2:h]
        # a soft glow trailing the simulation front
        g = 90
        a = max(0, h - g)
        ramp = np.linspace(0.0, 1.0, h - a, dtype=np.float32) ** 2
        img[140:self.h - 40, a:h] += (GOLD * 0.05)[None, None, :] * ramp[None, :, None]
        # gold time cursor and its readout
        img[self.top + 34:self.h - 40, h:h + 2] = GOLD
        ns = (hx - self.x0) / self.P * self.ns
        label = '{:.1f} ns'.format(ns)
        tw = int(self.flab.getlength(label)) + 22
        x0, y0 = h - tw // 2, self.top - 30
        img[y0:y0 + 34, x0:x0 + tw] = GOLD
        m = text_mask(tw, 34, [(tw / 2, 24, label, self.flab, 'ms')])
        sub = img[y0:y0 + 34, x0:x0 + tw]
        paint(sub, m, BG)
        return img


# ================================================================ place and route
class PlaceRouteScene(Scene):
    """Rows of standard cells. Signal routes fill in on two metal layers while a
    gold H-tree clock net grows out from its root, buffer by buffer."""

    def __init__(self, params):
        super().__init__(params)
        self.w, self.h = W, H = params.get('size', [2600, 1500])
        rng = np.random.default_rng(params.get('seed', 5))
        RH, SITE = 32, 5
        base = canvas(W, H, grey(0.022))
        pins = []
        poly_c, diff_c, cell_c, edge_c, pin_c = grey(0.105), grey(0.068), grey(0.044), grey(0.10), grey(0.21)
        for r in range(H // RH + 1):
            y = r * RH
            flip = r % 2
            x = int(rng.integers(0, 40))
            while x < W:
                if rng.random() < 0.07:                                  # filler gap
                    x += SITE * int(rng.integers(1, 4))
                    continue
                flop = rng.random() < 0.12
                ws = int(rng.integers(16, 23)) if flop else int(rng.choice([3, 4, 4, 5, 6, 6, 8, 9, 12]))
                cw = ws * SITE
                x0, x1 = x + 1, x + cw - 1
                cv2.rectangle(base, (x0, y + 3), (x1, y + RH - 3), col(cell_c if not flop else grey(0.055)), -1)
                pa, pb = (y + 6, y + 12) if not flip else (y + RH - 12, y + RH - 6)
                na, nb = (y + RH - 12, y + RH - 6) if not flip else (y + 6, y + 12)
                cv2.rectangle(base, (x0 + 2, pa), (x1 - 2, pb), col(diff_c), -1)
                cv2.rectangle(base, (x0 + 2, na), (x1 - 2, nb), col(diff_c * 0.9), -1)
                for k in range(1, ws, 2 if not flop else 3):
                    xp = x + k * SITE
                    cv2.line(base, (xp, y + 4), (xp, y + RH - 4), col(poly_c), 1)
                cv2.rectangle(base, (x0, y + 3), (x1, y + RH - 3), col(edge_c), 1)
                for _ in range(int(rng.integers(1, 4 if not flop else 5))):
                    xp = x + SITE * int(rng.integers(1, ws)) - 1
                    cv2.rectangle(base, (xp, y + 11), (xp + 2, y + RH - 11), col(pin_c), -1)
                    pins.append((xp + 1, y + RH // 2))
                x += cw
            cv2.line(base, (0, y), (W, y), col(grey(0.13)), 3)             # VDD / VSS rails
        self.base = base

        # ---- signal routing: M2 vertical, M3 horizontal, on a 10 px track grid
        T = params.get('span', 4.6)
        self.layers = []
        m2t = np.full((H, W), np.inf, np.float32)
        m3t = np.full((H, W), np.inf, np.float32)
        vt = np.full((H, W), np.inf, np.float32)
        nets = []
        pins = np.array(pins)
        for _ in range(params.get('nets', 760)):
            ax, ay = (int(v) for v in pins[rng.integers(len(pins))])
            dx = int(rng.normal(0, 260))
            dy = int(rng.normal(0, 130))
            bx = int(np.clip(ax + dx, 5, W - 5)) // 10 * 10 + 5
            by = int(np.clip(ay + dy, 16, H - 16)) // RH * RH + RH // 2
            ax = ax // 10 * 10 + 5
            if abs(bx - ax) + abs(by - ay) < 50:
                continue
            yt = int(ay + rng.uniform(0.2, 0.8) * (by - ay)) // 10 * 10
            t0 = rng.uniform(-3.0, 0.0) if rng.random() < 0.5 else rng.uniform(0.0, T * 0.9)
            nets.append((t0, [(ax, ay), (ax, yt), (bx, yt), (bx, by)], rng.uniform(700, 1300)))
        nets.sort(key=lambda n: -n[0])       # earliest drawn last so it wins overlaps
        for t0, path, v in nets:
            t = t0
            layers = (m2t, m3t, m2t)
            for (pa, pb), tm in zip(zip(path[:-1], path[1:]), layers):
                t = self._seg(tm, pa, pb, t, v, 3)
            for p, tv in ((path[0], t0), (path[-1], t)):
                cv2.rectangle(vt, (p[0] - 2, p[1] - 2), (p[0] + 2, p[1] + 2), float(tv), -1)
        self.layers += [(m2t, np.array([0.21, 0.24, 0.29], np.float32), 0.85, 'signal'),
                        (m3t, grey(0.45), 0.85, 'signal'),
                        (vt, grey(0.62), 1.0, 'signal')]

        # ---- clock tree: an H-tree on top metal, grown at a constant speed
        ct = np.full((H, W), np.inf, np.float32)
        bt = np.full((H, W), np.inf, np.float32)
        root = params.get('root', [0.56, 0.5])
        size0 = params.get('htree', 660)
        levels = params.get('levels', 4)
        v = params.get('clock_speed', 300.0)
        t_start = params.get('clock_start', -1.2)
        self.clock_period = params.get('clock_period', 1.25)

        def htree(cx, cy, size, t, lev):
            half = size / 2.0
            wdt = max(4, 8 - lev)
            for ex in (cx - half, cx + half):
                self._seg(ct, (cx, cy), (ex, cy), t, v, wdt)
            t1 = t + half / v
            for ex in (cx - half, cx + half):
                for ey in (cy - half, cy + half):
                    self._seg(ct, (ex, cy), (ex, ey), t1, v, wdt)
                    t2 = t1 + half / v
                    b = 7 if lev < levels - 1 else 5
                    cv2.rectangle(bt, (int(ex - b), int(ey - b)), (int(ex + b), int(ey + b)), float(t2), -1)
                    if lev + 1 < levels:
                        htree(ex, ey, half, t2, lev + 1)
        htree(root[0] * W, root[1] * H, size0, t_start, 0)
        cv2.rectangle(bt, (int(root[0] * W) - 10, int(root[1] * H) - 10),
                      (int(root[0] * W) + 10, int(root[1] * H) + 10), float(t_start), -1)
        self.layers += [(ct, GOLD * 0.92, 1.0, 'clock'), (bt, GOLD, 1.0, 'clock')]

    @staticmethod
    def _seg(tm, pa, pb, t, v, width, step=5.0):
        """Draw a wire into a time map, each part stamped with when it gets routed."""
        ax, ay = pa
        bx, by = pb
        L = math.hypot(bx - ax, by - ay)
        n = max(1, int(L / step))
        for k in range(n):
            u0, u1 = k / n, (k + 1) / n
            p0 = (int(round(ax + (bx - ax) * u0)), int(round(ay + (by - ay) * u0)))
            p1 = (int(round(ax + (bx - ax) * u1)), int(round(ay + (by - ay) * u1)))
            cv2.line(tm, p0, p1, float(t + L * u0 / v), width)
        return t + L / v

    def image(self, tau):
        img = self.base.copy()
        hot = np.array([1.0, 0.88, 0.56], np.float32)
        for tm, c, a, kind in self.layers:
            on = tm <= tau
            if not on.any():
                continue
            img[on] = img[on] * (1 - a) + c * a
            if kind == 'clock':
                # clock edges leave the root every period and ripple out to the leaves;
                # the first edge is the tree growing
                age = np.mod(tau - tm[on], self.clock_period)
                k = np.exp(-age / 0.09)[:, None] * 0.7
                img[on] = img[on] * (1 - k) + hot * k
            else:
                front = on & (tm > tau - 0.1)
                img[front] = img[front] * 0.4 + grey(0.85) * 0.6
        return img


# ================================================================ the die
def stdcell_sea(img, x0, y0, x1, y1, rng, rh=10, lo=0.05, hi=0.11):
    """Fill a region with rows of tiny standard cells (vectorised)."""
    W = x1 - x0
    for y in range(y0, y1 - rh + 1, rh):
        widths = rng.integers(2, 13, size=W // 2 + 2)
        edges = np.cumsum(widths)
        edges = edges[edges < W]
        shades = rng.uniform(lo, hi, size=len(edges) + 1).astype(np.float32)
        row = np.repeat(shades, np.diff(np.concatenate([[0], edges, [W]])))
        img[y + 1:y + rh - 1, x0:x1, :] = row[None, :, None]
        img[y + 1:y + rh - 1, x0 + edges, :] *= 0.5
        img[y, x0:x1, :] = 0.15


def route_texture(img, x0, y0, x1, y1, rng, density=1.0):
    """Short M2/M3 wire segments over a region, like dense local routing."""
    W, H = x1 - x0, y1 - y0
    mh = np.zeros((H, W), np.float32)
    mv = np.zeros((H, W), np.float32)
    n = int(W * H / 900 * density)
    xs = rng.integers(0, W, n)
    ys = rng.integers(0, H, n) // 4 * 4
    ls = rng.integers(16, 160, n)
    for x, y, l in zip(xs, ys, ls):
        cv2.line(mh, (int(x), int(y)), (int(x + l), int(y)), 1.0, 2)
    xs = rng.integers(0, W, n) // 4 * 4 + 2
    ys = rng.integers(0, H, n)
    ls = rng.integers(16, 120, n)
    for x, y, l in zip(xs, ys, ls):
        cv2.line(mv, (int(x), int(y)), (int(x), int(y + l)), 1.0, 1)
    sub = img[y0:y1, x0:x1]
    paint(sub, mv, np.array([0.30, 0.34, 0.40], np.float32), 0.35)
    paint(sub, mh, grey(0.46), 0.26)


class DieScene(Scene):
    """The finished chip: pad ring, power ring and grid, two SRAM macros, an 8x8
    systolic array with its gold data buses, standard-cell logic, and the club's
    name in top metal, the way designers sign their dies."""
    static = True

    def __init__(self, params):
        super().__init__(params)
        D = params.get('size', 4096)
        self.w = self.h = D
        s = D / 4096.0

        def u(v):
            return int(round(v * s))

        rng = np.random.default_rng(params.get('seed', 9))
        img = canvas(D, D, grey(0.032))

        # ---- seal ring
        cv2.rectangle(img, (u(26), u(26)), (D - u(26), D - u(26)), col(grey(0.24)), max(2, u(12)))
        cv2.rectangle(img, (u(50), u(50)), (D - u(50), D - u(50)), col(grey(0.15)), max(1, u(4)))

        # ---- pad ring
        n_pads, p0, p1 = 20, u(420), D - u(420)
        pitch = (p1 - p0) / n_pads
        pw, depth = int(pitch * 0.72), u(250)
        for side in range(4):
            for k in range(n_pads):
                a = int(p0 + (k + 0.5) * pitch - pw / 2)
                pad = np.zeros((depth, pw, 3), np.float32)
                pad[:] = grey(0.1)
                cv2.rectangle(pad, (0, 0), (pw - 1, depth - 1), col(grey(0.32)), max(1, u(3)))
                bo = int(pw * 0.78)
                bx = (pw - bo) // 2
                cv2.rectangle(pad, (bx, bx), (bx + bo, bx + bo), col(grey(0.2)), -1)
                cv2.rectangle(pad, (bx, bx), (bx + bo, bx + bo), col(grey(0.36)), max(1, u(3)))
                for f in range(9):                                   # ESD fingers
                    xf = int(pw * (0.12 + 0.76 * f / 8))
                    cv2.line(pad, (xf, bx + bo + u(18)), (xf, depth - u(14)), col(grey(0.24)), max(1, u(4)))
                pad = np.rot90(pad, k=side)
                off = u(80)
                if side == 0:
                    img[off:off + depth, a:a + pw] = pad
                elif side == 1:
                    img[a:a + pw, off:off + depth] = pad
                elif side == 2:
                    img[D - off - depth:D - off, a:a + pw] = pad
                else:
                    img[a:a + pw, D - off - depth:D - off] = pad
        for k in range(5):                                              # IO ring rails
            r = u(352 + k * 9)
            cv2.rectangle(img, (r, r), (D - r, D - r), col(grey(0.17 if k % 2 else 0.24)), max(1, u(3)))

        # ---- power ring
        c0, c1 = u(450), D - u(450)
        cv2.rectangle(img, (c0 + u(14), c0 + u(14)), (c1 - u(14), c1 - u(14)), col(GOLD * 0.55), u(26))
        cv2.rectangle(img, (c0 + u(54), c0 + u(54)), (c1 - u(54), c1 - u(54)), col(grey(0.36)), u(26))
        k0, k1 = u(600), D - u(600)

        # ---- floorplan
        sram = [(k0, k0, u(1540), u(1500)), (k0, u(1580), u(1540), u(2470))]
        sa = (u(1660), k0, k1, k0 + (k1 - u(1660)))          # square systolic array, top right
        sea = (k0, u(2560), k1, k1)
        logo = (u(2740), u(3080), k1 - u(20), k1 - u(20))

        stdcell_sea(img, *sea, rng, rh=max(4, u(10)))
        route_texture(img, *sea, rng)
        for x0, y0, x1, y1 in sram:
            self._sram(img, x0, y0, x1, y1, u, rng)
        self._systolic(img, sa, u, rng)

        # global routes in the channels between blocks
        for _ in range(140):
            y = int(rng.integers(k0, k1)) // u(6) * u(6)
            x = int(rng.integers(k0, k1 - u(300)))
            cv2.line(img, (x, y), (x + int(rng.integers(u(100), u(900))), y), col(grey(0.3)), max(1, u(2)))

        # ---- keep-out around the logo, with dummy metal fill
        lx0, ly0, lx1, ly1 = logo
        img[ly0:ly1, lx0:lx1] = grey(0.03)
        step, b = max(3, u(14)), max(1, u(4))
        for y in range(ly0 + step, ly1 - step, step):
            for x in range(lx0 + step, lx1 - step, step):
                img[y:y + b, x:x + b] = grey(0.09)
        cv2.rectangle(img, (lx0, ly0), (lx1, ly1), col(grey(0.22)), max(1, u(3)))
        self._logo(img, logo, u)

        # ---- power grid on the top metals, over everything in the core
        g = np.zeros((D, D), np.float32)
        for x in range(k0, k1, u(112)):
            g[k0:k1, x:x + u(10)] = 1.0
        paint(img, g, GOLD * 0.9, 0.17)
        g[:] = 0
        for y in range(k0, k1, u(112)):
            g[y:y + u(10), k0:k1] = 1.0
        paint(img, g, WHITE, 0.07)
        self.img = img

    @staticmethod
    def _sram(img, x0, y0, x1, y1, u, rng):
        img[y0:y1, x0:x1] = grey(0.05)
        dec = u(120)
        amp = u(120)
        # bit cell array, in four banks
        motif = np.full((max(3, u(6)), max(4, u(8))), 0.085, np.float32)
        motif[0, :] = 0.17
        motif[:, 0] = 0.14
        motif[motif.shape[0] // 3: 2 * motif.shape[0] // 3 + 1, motif.shape[1] // 3: 2 * motif.shape[1] // 3 + 1] = 0.23
        ax0, ay0, ax1, ay1 = x0 + dec + u(20), y0 + u(20), x1 - u(20), y1 - amp - u(20)
        bw, bh = (ax1 - ax0 - u(30)) // 2, (ay1 - ay0 - u(30)) // 2
        for i in range(2):
            for j in range(2):
                bx, by = ax0 + i * (bw + u(30)), ay0 + j * (bh + u(30))
                reps = (bh // motif.shape[0] + 1, bw // motif.shape[1] + 1)
                img[by:by + bh, bx:bx + bw] = np.tile(motif, reps)[:bh, :bw, None]
        # row decoder and sense amplifiers
        stdcell_sea(img, x0 + u(10), y0 + u(20), x0 + dec, y1 - amp - u(20), rng, rh=max(3, u(6)), lo=0.07, hi=0.13)
        for x in range(ax0, ax1, max(4, u(8))):
            img[y1 - amp:y1 - u(16), x:x + max(1, u(3))] = grey(0.17)
        stdcell_sea(img, x0 + u(10), y1 - amp, x0 + dec, y1 - u(10), rng, rh=max(3, u(8)))
        cv2.rectangle(img, (x0, y0), (x1, y1), col(grey(0.32)), max(1, u(4)))

    @staticmethod
    def _systolic(img, sa, u, rng):
        x0, y0, x1, y1 = sa
        n, gap = 8, u(30)
        tile = (x1 - x0 - (n + 1) * gap) // n
        img[y0:y1, x0:x1] = grey(0.035)
        bus = np.zeros(img.shape[:2], np.float32)
        for i in range(n):
            for j in range(n):
                tx, ty = x0 + gap + j * (tile + gap), y0 + gap + i * (tile + gap)
                stdcell_sea(img, tx, ty, tx + tile, ty + tile, rng, rh=max(3, u(8)), lo=0.055, hi=0.12)
                m = tile // 3
                mx, my = tx + (tile - m) // 2, ty + (tile - m) // 2      # the multiplier
                step = max(2, u(5))
                blk = img[my:my + m, mx:mx + m]
                blk[:] = grey(0.07)
                blk[::step] = grey(0.16)
                blk[:, ::step] = np.maximum(blk[:, ::step], grey(0.13))
                cv2.rectangle(img, (mx, my), (mx + m, my + m), col(grey(0.3)), max(1, u(2)))
                cv2.rectangle(img, (tx, ty), (tx + tile, ty + tile), col(grey(0.27)), max(1, u(3)))
                # data buses: a flows east, b flows south
                for k in range(6):
                    yy = ty + tile // 2 - u(25) + k * u(10)
                    xa = tx - gap if j > 0 else x0 - u(60)
                    cv2.line(bus, (xa, yy), (tx + u(6), yy), 1.0, max(1, u(3)))
                    xx = tx + tile // 2 - u(25) + k * u(10)
                    ya = ty - gap if i > 0 else y0 - u(60)
                    cv2.line(bus, (xx, ya), (xx, ty + u(6)), 1.0, max(1, u(3)))
        paint(img, bus, GOLD, 0.9)
        cv2.rectangle(img, (x0, y0), (x1, y1), col(grey(0.3)), max(1, u(4)))

    @staticmethod
    def _logo(img, box, u):
        """The club's name drawn as top-metal squares, like real die art."""
        x0, y0, x1, y1 = box
        W, H = x1 - x0, y1 - y0
        sq = np.zeros((H, W), np.float32)
        for text, f, yb, cell in (('SASi', font(u(250), 600, 'Geist'), 0.56, max(3, u(9))),
                                  ('STONE ARCH SILICON', font(u(50), 600, 'Geist'), 0.79, max(2, u(4)))):
            m = text_mask(W, H, [(W / 2, H * yb, text, f, 'ms')])
            gh, gw = H // cell, W // cell
            cov = cv2.resize(m[:gh * cell, :gw * cell], (gw, gh), interpolation=cv2.INTER_AREA)
            g = max(1, cell // 6) if cell > 3 else 0
            for r, c in np.argwhere(cov > 0.45):
                sq[r * cell + g:(r + 1) * cell - g, c * cell + g:(c + 1) * cell - g] = 1.0
        paint(img[y0:y1, x0:x1], sq, GOLD, 0.95)
        lab = font(u(28), 400, 'GeistMono')
        paint(img[y0:y1, x0:x1], text_mask(W, H, [(W / 2, H - u(26), 'UMN  ·  2026', lab, 'ms')]), grey(0.42))

    def image(self, tau):
        return self.img


SCENES = {
    'rtl': RTLScene,
    'waves': WaveScene,
    'route': PlaceRouteScene,
    'die': DieScene,
}

_BUILT = {}


def get(name, params):
    """Build a scene once and share it between the landscape and portrait renders."""
    key = (name, repr(sorted(params.items())))
    if key not in _BUILT:
        if name not in SCENES:
            raise SystemExit('Unknown scene "{}". Choose from: {}'.format(name, ', '.join(SCENES)))
        _BUILT[key] = SCENES[name](params)
    return _BUILT[key]
