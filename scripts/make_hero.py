#!/usr/bin/env python3
"""Render the home-page hero film.

Reads a shot list (scripts/hero_shots.json), moves a slow virtual camera across
each shot's source, grades it toward the site's black, white and gold look, and
crossfades the shots into a seamless loop. A source is either a procedural scene
drawn by scripts/hero_scenes.py (the digital design flow: RTL, simulation,
place and route, the finished die) or a photo or video to download. Writes:

  assets/hero-1080.mp4            1920x1080 H.264 High 4.1 (matches index.html)
  assets/hero-720.webm            1280x720 VP9
  assets/hero-mobile.mp4          720x1280 H.264 for portrait screens
  assets/hero-poster.jpg          first frame, 1920x1080
  assets/hero-poster-mobile.jpg   first frame, 720x1280
  assets/hero-credits.txt         where each shot came from, and its license

The file names stay the same, so index.html and site.css need no edits.

Run it from GitHub Actions ("Build hero video" in the Actions tab), or
locally with python3, ffmpeg, and pip install numpy opencv-python-headless
pillow fonttools brotli:

  python3 scripts/make_hero.py scripts/hero_shots.json
  python3 scripts/make_hero.py scripts/hero_shots.json --preview   # fast, small

Shot list format (all coordinates are fractions of the source image):

  {
    "fps": 30,
    "crossfade": 1.4,                  seconds of dissolve between shots
    "grade": {...},                    see GRADE_DEFAULTS below
    "poster": {"shot": 1, "time": 3},  optional: the still for the posters, as
                                       shot number (from 1) and seconds into it;
                                       without it the posters are the first frame
    "posters": [{"name": "hero-poster-about", "shot": 2, "time": 1.6}, ...]
                                       optional: more stills, for the inner pages'
                                       heroes; each writes NAME.jpg and NAME-mobile.jpg
    "shots": [{
      "kind": "scene",                 a drawing from scripts/hero_scenes.py ...
      "scene": "route",                ... by name: rtl, waves, route or die
      "params": {...},                 optional settings for that scene
    }, {
      "src": "https://...jpg",         or a photo, or a video (set "kind": "video")
      "page": "https://...",           the page it came from, for the credits
      "credit": "What it is. Photo: Name",
      "license": "CC0 1.0",
      "duration": 6.5,                 seconds this shot owns in the loop
      "landscape": {"from": [cx, cy, w], "to": [cx, cy, w]},
      "portrait":  {"from": [cx, cy, w], "to": [cx, cy, w]}
    }]
  }

  cx, cy is the centre of the view and w is its width, all as fractions of the
  source. The camera moves in a straight line from "from" to "to" over the
  shot (zoom changes at a constant rate). Optional per shot: "rot": [a, b] in
  degrees, "start" and "speed" for video sources, "grade" overrides.

  Scenes also take, per shot or inside "landscape"/"portrait":
    "tilt":  [rx, ry]                   degrees; swings the camera for perspective
    "dof":   {"focus": [x, y], "radius": r, "feather": f, "blur": px}
                                        soft focus away from a point (fractions of
                                        the frame); add "normal": [nx, ny] to focus
                                        along a line instead
    "bloom": {"threshold": t, "sigma": px, "strength": k}   glow on bright gold
"""
import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hero_scenes  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(tempfile.gettempdir(), 'sasi-hero-sources')   # downloads, kept out of the repo
UA = 'SASi-hero-builder/1.0 (+https://github.com/Stone-Arch-Silicon/stone-arch-silicon)'

GRADE_DEFAULTS = {
    'exposure': 0.0,      # stops
    'contrast': 1.0,      # S-curve strength around mid grey, 1 = none
    'saturation': 1.0,    # 0 = black and white
    'tint': [1.0, 1.0, 1.0],   # RGB multiplier applied to the highlights
    'black': 0.0,         # lifts (+) or crushes (-) the blacks
    'soften': 0.0,        # gaussian sigma in output pixels; tames shimmer on fine detail
}

# crf sets the quality; maxrate (kbit/s) caps it so fine detail can't balloon the file
LANDSCAPE = {
    'hero-1080.mp4': dict(size=(1920, 1080), codec='h264', crf=23, maxrate=2800),
    'hero-720.webm': dict(size=(1280, 720), codec='vp9', crf=34, maxrate=1300),
}
PORTRAIT = {
    'hero-mobile.mp4': dict(size=(720, 1280), codec='h264', crf=24, maxrate=1500),
}


def log(*a):
    print(*a, flush=True)


# ---------------------------------------------------------------- sources
def fetch(url):
    """Download once into the temp folder and return the local path."""
    if os.path.exists(url):
        return url
    os.makedirs(CACHE, exist_ok=True)
    ext = os.path.splitext(url.split('?')[0])[1][:6] or '.bin'
    path = os.path.join(CACHE, hashlib.sha1(url.encode()).hexdigest()[:16] + ext)
    if not os.path.exists(path):
        log('  downloading', url)
        part = path + '.part'
        if shutil.which('curl'):
            # retries, and gives up on a stalled transfer instead of hanging the build
            subprocess.run(['curl', '-fsSL', '--retry', '4', '--retry-all-errors', '--connect-timeout', '20',
                            '--speed-limit', '100000', '--speed-time', '30', '--max-time', '600',
                            '-A', UA, '-o', part, url], check=True)
        else:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=60) as r, open(part, 'wb') as f:
                shutil.copyfileobj(r, f)
        os.replace(part, path)
        log('    {:.1f} MB'.format(os.path.getsize(path) / 1e6))
    return path


class Still:
    """A photo. shrink() pre-scales it once (area averaging) so the per-frame
    camera never has to shrink fine detail by much, which is what causes
    shimmer and moire on die shots."""

    def __init__(self, path):
        img = cv2.imread(path, cv2.IMREAD_COLOR)
        if img is None:
            sys.exit('Could not read image: ' + path)
        self.full = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        self.h, self.w = self.full.shape[:2]
        self.img, self.factor = self.full, 1.0

    def shrink(self, factor):
        self.factor = max(1.0, factor)
        if self.factor > 1.0:
            size = (max(1, round(self.w / self.factor)), max(1, round(self.h / self.factor)))
            self.img = cv2.resize(self.full, size, interpolation=cv2.INTER_AREA)
        self.full = None   # 9000 px originals are big; keep only the copy we draw from


class Footage:
    """A video source, decoded sequentially by ffmpeg at the output frame rate."""

    def __init__(self, path, start, speed, fps):
        probe = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
             'stream=width,height', '-of', 'csv=p=0', path],
            capture_output=True, text=True, check=True).stdout.strip().split(',')
        self.w, self.h = int(probe[0]), int(probe[1])
        self.dw, self.dh = self.w, self.h          # decoded size, after shrink()
        self.path, self.start, self.speed, self.fps = path, start, speed, fps
        self.proc, self.pos, self.last = None, -1, None
        self.factor = 1.0

    def shrink(self, factor):
        self.factor = max(1.0, factor)
        self.dw = 2 * round(self.w / self.factor / 2)
        self.dh = 2 * round(self.h / self.factor / 2)

    def _open(self):
        vf = 'setpts=PTS/{},fps={},scale={}:{}:flags=lanczos'.format(self.speed, self.fps, self.dw, self.dh)
        self.proc = subprocess.Popen(
            ['ffmpeg', '-v', 'fatal', '-ss', str(self.start), '-i', self.path, '-an',
             '-vf', vf, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
            stdout=subprocess.PIPE)
        self.pos = -1

    def close(self):
        if self.proc:
            self.proc.kill()
            self.proc.wait()
            self.proc = None

    def frame_at(self, index):
        if self.proc is None or index < self.pos:
            self.close()
            self._open()
        n = self.dw * self.dh * 3
        while self.pos < index:
            buf = self.proc.stdout.read(n)
            if len(buf) < n:     # ran out of footage: hold the last frame
                break
            self.last = np.frombuffer(buf, np.uint8).reshape(self.dh, self.dw, 3)
            self.pos += 1
        if self.last is None:
            sys.exit('No frames decoded from ' + self.path)
        return self.last


# ---------------------------------------------------------------- camera
def camera(path, u):
    """Interpolate [cx, cy, w] along a path at u in [0, 1]; zoom is geometric."""
    a, b = path['from'], path['to']
    cx = a[0] + (b[0] - a[0]) * u
    cy = a[1] + (b[1] - a[1]) * u
    w = a[2] * (b[2] / a[2]) ** u
    return cx, cy, w


def warp(img, cx, cy, wfrac, rot_deg, out_w, out_h):
    """Render the view centred on (cx, cy) with width wfrac of the image.
    Sub-pixel accurate, so slow moves glide instead of stepping."""
    ih, iw = img.shape[:2]
    sx = wfrac * iw / out_w                    # image pixels per output pixel
    th = math.radians(rot_deg)
    c, n = math.cos(th) * sx, math.sin(th) * sx
    ccx, ccy = cx * iw, cy * ih
    # dst (x, y) -> src: centre-relative, rotated, scaled
    ox, oy = out_w / 2.0, out_h / 2.0
    M = np.array([[c, -n, ccx - c * ox + n * oy],
                  [n, c, ccy - n * ox - c * oy]], dtype=np.float64)
    return cv2.warpAffine(img, M, (out_w, out_h), flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP,
                          borderMode=cv2.BORDER_REFLECT_101)


def check_bounds(name, path, aspect, src_w, src_h, rot):
    """Warn when a view would run past the edge of the source."""
    for u in (0.0, 0.5, 1.0):
        cx, cy, w = camera(path, u)
        vw = w * src_w
        vh = vw / aspect
        if rot:
            r = math.radians(max(abs(rot[0]), abs(rot[1])))
            vw, vh = vw * math.cos(r) + vh * math.sin(r), vw * math.sin(r) + vh * math.cos(r)
        x0, x1 = cx * src_w - vw / 2, cx * src_w + vw / 2
        y0, y1 = cy * src_h - vh / 2, cy * src_h + vh / 2
        if x0 < -1 or y0 < -1 or x1 > src_w + 1 or y1 > src_h + 1:
            log('  warning: {} leaves the source at u={} ({:.0f},{:.0f})-({:.0f},{:.0f} of {}x{})'
                .format(name, u, x0, y0, x1, y1, src_w, src_h))


# ---------------------------------------------------------------- grade
_LUT_N = 4096
_grid = np.linspace(0.0, 1.0, _LUT_N, dtype=np.float64)
_TO_LIN = np.where(_grid <= 0.04045, _grid / 12.92, ((_grid + 0.055) / 1.055) ** 2.4).astype(np.float32)
_TO_SRGB = np.where(_grid <= 0.0031308, _grid * 12.92, 1.055 * _grid ** (1 / 2.4) - 0.055).astype(np.float32)


def _lut(x, table):
    idx = np.clip(x * (_LUT_N - 1) + 0.5, 0, _LUT_N - 1).astype(np.int32)
    return table[idx]


def to_linear(x):
    return _lut(x, _TO_LIN)


def to_srgb(x):
    return _lut(x, _TO_SRGB)


def grade(rgb, g):
    """rgb: float32 sRGB in [0, 1]. Returns graded float32 sRGB."""
    x = rgb
    if g['exposure']:
        x = to_srgb(to_linear(x) * (2.0 ** g['exposure']))
    if g['saturation'] != 1.0:
        luma = x @ np.array([0.2126, 0.7152, 0.0722], np.float32)
        x = luma[..., None] + (x - luma[..., None]) * g['saturation']
    if g['contrast'] != 1.0:
        k = g['contrast']
        x = np.clip(x, 0.0, 1.0)
        x = np.where(x < 0.5, 0.5 * (2 * x) ** k, 1 - 0.5 * (2 * (1 - x)) ** k)
    tint = np.array(g['tint'], np.float32)
    if not np.allclose(tint, 1.0):
        x = x * (1.0 + (tint - 1.0) * np.clip(x, 0, 1))   # tint grows toward the highlights
    if g['black']:
        x = g['black'] + x * (1.0 - g['black'])
    return np.clip(x, 0.0, 1.0)


def smoothstep(a):
    return a * a * (3 - 2 * a)


# ---------------------------------------------------------------- render
class Renderer:
    def __init__(self, spec, orient, out_w, out_h):
        self.spec, self.orient = spec, orient
        self.out_w, self.out_h = out_w, out_h
        self.fps = spec['fps']
        self.xf = spec['crossfade']
        self.shots = spec['shots']
        self.durs = [float(s['duration']) for s in self.shots]
        if min(self.durs) < self.xf:
            sys.exit('Every shot must last at least as long as the crossfade.')
        self.starts = np.cumsum([0.0] + self.durs[:-1]).tolist()
        self.total = sum(self.durs)
        self.sources = []
        for s in self.shots:
            if s.get('kind') == 'scene':
                log('  drawing scene', s['scene'])
                self.sources.append(hero_scenes.get(s['scene'], s.get('params', {})))
                continue
            path = fetch(s['src'])
            if s.get('kind') == 'video':
                self.sources.append(Footage(path, float(s.get('start', 0)), float(s.get('speed', 1.0)), self.fps))
            else:
                self.sources.append(Still(path))
        aspect = out_w / out_h
        self._masks = {}
        for i, (s, src) in enumerate(zip(self.shots, self.sources)):
            if isinstance(src, hero_scenes.Scene):
                continue      # scenes are drawn at full size and mip-mapped instead
            path = s[orient]
            check_bounds('shot {} ({})'.format(i + 1, orient), path, aspect, src.w, src.h, s.get('rot'))
            # one pre-shrink per shot, from its tightest framing, so sharpness never pops
            s_min = min(path['from'][2], path['to'][2]) * src.w / out_w
            src.shrink(s_min / 1.15)

    def shot_frame(self, i, tau):
        """Shot i at local time tau in [0, duration + crossfade)."""
        s, src = self.shots[i], self.sources[i]
        length = self.durs[i] + self.xf
        u = min(max(tau / length, 0.0), 1.0)
        path = s[self.orient]
        cx, cy, w = camera(path, u)
        rot = s.get('rot')
        angle = rot[0] + (rot[1] - rot[0]) * u if rot else 0.0
        if isinstance(src, hero_scenes.Scene):
            tilt = path.get('tilt', s.get('tilt'))
            x = src.view(tau, cx, cy, w, angle, tilt, self.out_w, self.out_h)
        else:
            img = src.frame_at(int(round(tau * self.fps))) if isinstance(src, Footage) else src.img
            x = warp(img, cx, cy, w, angle, self.out_w, self.out_h).astype(np.float32) / 255.0
        g = dict(GRADE_DEFAULTS, **self.spec.get('grade', {}))
        g.update(s.get('grade', {}))
        if g['soften'] > 0:
            x = cv2.GaussianBlur(x, (0, 0), g['soften'])
        dof = path.get('dof', s.get('dof'))
        if dof:
            m = self.dof_mask(i, dof)
            k = self.out_w / 1920.0 if self.out_w > self.out_h else self.out_h / 1920.0
            soft = cv2.GaussianBlur(x, (0, 0), dof.get('blur', 4.0) * k)
            x = x + (soft - x) * m[..., None]
        x = grade(x, g)
        bloom = path.get('bloom', s.get('bloom'))
        if bloom:
            x = self.add_bloom(x, bloom)
        return x

    def dof_mask(self, i, dof):
        """0 where the shot is in focus, rising to 1 where it is fully soft."""
        key = (i, json.dumps(dof, sort_keys=True))
        if key not in self._masks:
            h, w = self.out_h, self.out_w
            ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
            fx, fy = dof.get('focus', [0.5, 0.5])
            dx, dy = (xs / w - fx) * (w / h), ys / h - fy        # in frame heights
            if 'normal' in dof:
                nx, ny = dof['normal']
                n = math.hypot(nx, ny)
                d = np.abs(dx * nx / n + dy * ny / n)
            else:
                d = np.sqrt(dx * dx + dy * dy)
            m = np.clip((d - dof.get('radius', 0.3)) / dof.get('feather', 0.4), 0.0, 1.0)
            self._masks[key] = smoothstep(m).astype(np.float32)
        return self._masks[key]

    def add_bloom(self, x, b):
        """A soft glow around the brightest parts of the frame (the gold clock net)."""
        k = self.out_w / 1920.0 if self.out_w > self.out_h else self.out_h / 1920.0
        hot = np.clip(x - b.get('threshold', 0.55), 0.0, None)
        glow = cv2.GaussianBlur(hot, (0, 0), b.get('sigma', 14) * k) + \
            0.5 * cv2.GaussianBlur(hot, (0, 0), b.get('sigma', 14) * k * 3)
        return np.clip(x + glow * b.get('strength', 0.8), 0.0, 1.0)

    def frame(self, n):
        """Output frame n. The film starts as shot 1 becomes fully visible and
        ends inside the dissolve from the last shot back into shot 1, so it loops."""
        g = (n / self.fps + self.xf) % self.total
        # which shot owns g, and is the previous one still dissolving out?
        i = max(k for k, st in enumerate(self.starts) if st <= g + 1e-9)
        tau = g - self.starts[i]
        cur = self.shot_frame(i, tau)
        if tau < self.xf:
            prev = (i - 1) % len(self.shots)
            prev_tau = self.durs[prev] + tau
            a = smoothstep(tau / self.xf)
            # dissolve in linear light so the midpoint doesn't dip
            out = to_srgb(to_linear(self.shot_frame(prev, prev_tau)) * (1 - a) + to_linear(cur) * a)
        else:
            out = cur
        return (out * 255.0 + 0.5).astype(np.uint8)

    def count(self):
        return int(round(self.total * self.fps))


def encoder_args(name, opts, fps, preview):
    w, h = opts['size']
    color = ['-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709']
    vf = 'scale={}:{}:flags=lanczos:out_color_matrix=bt709:out_range=tv,format=yuv420p'.format(w, h)
    gop = str(int(fps * 2))
    if opts['codec'] == 'h264':
        rate = opts['maxrate'] // (2 if preview else 1)
        args = ['-vf', vf, '-c:v', 'libx264', '-profile:v', 'high', '-level:v', '4.1',
                '-preset', 'veryfast' if preview else 'slow', '-crf', str(opts['crf']),
                '-maxrate', '{}k'.format(rate), '-bufsize', '{}k'.format(rate * 2),
                '-g', gop, '-bf', '2', '-movflags', '+faststart']
    else:
        rate = opts['maxrate'] // (2 if preview else 1)
        args = ['-vf', vf, '-c:v', 'libvpx-vp9', '-crf', str(opts['crf']), '-b:v', '{}k'.format(rate),
                '-row-mt', '1', '-deadline', 'good', '-cpu-used', '5' if preview else '3',
                '-g', gop]
    return args + color + ['-an']


def render(spec, orient, outputs, outdir, preview):
    base_w, base_h = max(o['size'] for o in outputs.values())
    if preview:
        base_w, base_h = base_w // 2, base_h // 2
    r = Renderer(spec, orient, base_w, base_h)
    total = r.count()
    tmp = {name: os.path.join(outdir, '.tmp-' + name) for name in outputs}
    cmd = ['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
           '-s', '{}x{}'.format(base_w, base_h), '-r', str(spec['fps']), '-i', '-']
    for name, opts in outputs.items():
        o = dict(opts)
        if preview:
            o['size'] = (o['size'][0] // 2, o['size'][1] // 2)
        cmd += encoder_args(name, o, spec['fps'], preview) + [tmp[name]]
    log('  {} frames at {}x{} -> {}'.format(total, base_w, base_h, ', '.join(outputs)))
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    first = None
    for n in range(total):
        f = r.frame(n)
        if n == 0:
            first = f
        enc.stdin.write(f.tobytes())
        if n % (spec['fps'] * 2) == 0:
            log('    {:5.1f}s / {:.1f}s'.format(n / spec['fps'], r.total))
    enc.stdin.close()
    for src in r.sources:
        if isinstance(src, Footage):
            src.close()
    if enc.wait() != 0:
        sys.exit('ffmpeg failed')
    for name in outputs:          # only replace the real files once ffmpeg has finished cleanly
        os.replace(tmp[name], os.path.join(outdir, name))
    poster = spec.get('poster')
    if poster:
        # the still shown before the film loads, and instead of it when motion is off
        first = (r.shot_frame(int(poster['shot']) - 1, float(poster['time'])) * 255.0 + 0.5).astype(np.uint8)
    return first


def save_poster(frame, size, path):
    img = cv2.resize(frame, size, interpolation=cv2.INTER_AREA)
    img = cv2.GaussianBlur(img, (0, 0), 0.6)    # the finest layout detail costs bytes nobody sees under the shade
    cv2.imwrite(path, cv2.cvtColor(img, cv2.COLOR_RGB2BGR),
                [cv2.IMWRITE_JPEG_QUALITY, 80, cv2.IMWRITE_JPEG_PROGRESSIVE, 1])


def extra_posters(spec, outdir, preview, only):
    """Stills for the inner pages' heroes. Each page plays the same film from its
    poster's moment (data-start in the HTML), so the still and the film line up."""
    jobs = [('landscape', (1920, 1080), ''), ('portrait', (720, 1280), '-mobile')]
    for orient, size, suffix in jobs:
        if only and only != orient or not spec.get('posters'):
            continue
        w, h = (size[0] // 2, size[1] // 2) if preview else size
        r = Renderer(spec, orient, w, h)
        for p in spec['posters']:
            frame = (r.shot_frame(int(p['shot']) - 1, float(p['time'])) * 255.0 + 0.5).astype(np.uint8)
            save_poster(frame, (w, h), os.path.join(outdir, p['name'] + suffix + '.jpg'))
            start = (sum(float(x['duration']) for x in spec['shots'][:int(p['shot']) - 1])
                     + float(p['time']) - spec['crossfade']) % sum(float(x['duration']) for x in spec['shots'])
            if orient == 'landscape' or only == 'portrait':
                log('  {}.jpg  (film time {:.2f}s, use data-start="{:.1f}")'.format(p['name'], start, start))


def write_credits(spec, path):
    lines = ['Home-page hero film. Built by scripts/make_hero.py from scripts/hero_shots.json.', '']
    for i, s in enumerate(spec['shots'], 1):
        lines.append('Shot {}: {}'.format(i, s.get('credit', 'unknown')))
        if s.get('kind') == 'scene':
            lines.append('  License: {}'.format(s.get('license', 'Original work by Stone Arch Silicon')))
            lines.append('  Source: drawn by scripts/hero_scenes.py (scene "{}")'.format(s['scene']))
            continue
        lines.append('  License: {}'.format(s.get('license', 'unknown')))
        lines.append('  Source: {}'.format(s.get('page', s['src'])))
    if any('DVIDS' in s.get('license', '') for s in spec['shots']):
        lines += ['', 'The appearance of U.S. Department of Defense (DoD) visual information does not',
                  'imply or constitute DoD endorsement.']
    with open(path, 'w') as f:
        f.write('\n'.join(lines) + '\n')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('spec', help='shot list JSON')
    ap.add_argument('--out', default=os.path.join(ROOT, 'assets'), help='output folder')
    ap.add_argument('--preview', action='store_true', help='half size, fast encode')
    ap.add_argument('--only', choices=['landscape', 'portrait'], help='render one orientation')
    args = ap.parse_args()
    with open(args.spec) as f:
        spec = json.load(f)
    spec.setdefault('fps', 30)
    spec.setdefault('crossfade', 1.4)
    os.makedirs(args.out, exist_ok=True)

    if args.only != 'portrait':
        log('landscape')
        first = render(spec, 'landscape', LANDSCAPE, args.out, args.preview)
        save_poster(first, (1920, 1080) if not args.preview else (960, 540),
                    os.path.join(args.out, 'hero-poster.jpg'))
    if args.only != 'landscape':
        log('portrait')
        first = render(spec, 'portrait', PORTRAIT, args.out, args.preview)
        save_poster(first, (720, 1280) if not args.preview else (360, 640),
                    os.path.join(args.out, 'hero-poster-mobile.jpg'))
    extra_posters(spec, args.out, args.preview, args.only)
    write_credits(spec, os.path.join(args.out, 'hero-credits.txt'))
    for name in list(LANDSCAPE) + list(PORTRAIT) + ['hero-poster.jpg', 'hero-poster-mobile.jpg']:
        p = os.path.join(args.out, name)
        if os.path.exists(p):
            log('  {:28s} {:8.0f} KB'.format(name, os.path.getsize(p) / 1024))


if __name__ == '__main__':
    main()
