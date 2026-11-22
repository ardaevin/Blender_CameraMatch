"""Viewport overlay: handles, vanishing lines, horizon, solved grid/axes."""

from math import cos, sin, pi, hypot

import blf
import bpy
import gpu
from bpy_extras.view3d_utils import location_3d_to_region_2d
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from . import solver, state
from .props import LINES, active_groups, active_handles

# Line groups are told apart by hue AND a text label (no red-vs-green pairs).
COL = {
    "vp1": (1.00, 0.55, 0.10, 1.0),   # orange
    "vp2": (0.25, 0.65, 1.00, 1.0),   # blue
    "vp3": (0.85, 0.35, 1.00, 1.0),   # magenta
    "hz": (0.25, 0.65, 1.00, 1.0),
    "ref": (1.00, 0.95, 0.35, 1.0),   # yellow
    "origin": (1.0, 1.0, 1.0, 1.0),
}
LABEL = {"vp1": "1", "vp2": "2", "vp3": "3", "hz": "H", "ref": "R"}
AXIS_COL = {"X": (1.0, 0.35, 0.35, 1.0), "Y": (0.55, 0.9, 0.35, 1.0), "Z": (0.35, 0.6, 1.0, 1.0)}


# --------------------------------------------------------------------------- coordinate helpers

def frame_rect(scene, cam, region, rv3d):
    """Camera frame in region pixels: (x, y, w, h) or None."""
    mw = cam.matrix_world
    pts = [location_3d_to_region_2d(region, rv3d, mw @ v) for v in cam.data.view_frame(scene=scene)]
    if any(p is None for p in pts):
        return None
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    if w < 1 or h < 1:
        return None
    return min(xs), min(ys), w, h


def uv_to_px(rect, uv):
    return Vector((rect[0] + uv[0] * rect[2], rect[1] + uv[1] * rect[3]))


def px_to_uv(rect, x, y):
    return Vector(((x - rect[0]) / rect[2], (y - rect[1]) / rect[3]))


def handle_radius():
    return 7.0 * bpy.context.preferences.system.ui_scale


def pick(p, rect, mx, my):
    best, bd = None, handle_radius() * 1.8
    for n in active_handles(p):
        q = uv_to_px(rect, getattr(p, n))
        d = hypot(q.x - mx, q.y - my)
        if d < bd:
            best, bd = n, d
    return best


# --------------------------------------------------------------------------- primitive drawing

def _lines(coords, color, width=1.5):
    if not coords:
        return
    sh = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    b = batch_for_shader(sh, 'LINES', {"pos": [(c[0], c[1], 0.0) for c in coords]})
    vp = gpu.state.viewport_get()
    sh.bind()
    sh.uniform_float("viewportSize", (float(vp[2]), float(vp[3])))
    sh.uniform_float("lineWidth", width)
    sh.uniform_float("color", color)
    b.draw(sh)


def _disc(c, r, color, seg=16):
    tris = []
    for i in range(seg):
        a0, a1 = 2 * pi * i / seg, 2 * pi * (i + 1) / seg
        tris += [(c[0], c[1], 0.0), (c[0] + r * cos(a0), c[1] + r * sin(a0), 0.0),
                 (c[0] + r * cos(a1), c[1] + r * sin(a1), 0.0)]
    sh = gpu.shader.from_builtin('UNIFORM_COLOR')
    b = batch_for_shader(sh, 'TRIS', {"pos": tris})
    sh.bind()
    sh.uniform_float("color", color)
    b.draw(sh)


def _ring(c, r, color, width=1.5, seg=24):
    pts = []
    for i in range(seg):
        a0, a1 = 2 * pi * i / seg, 2 * pi * (i + 1) / seg
        pts += [(c[0] + r * cos(a0), c[1] + r * sin(a0)), (c[0] + r * cos(a1), c[1] + r * sin(a1))]
    _lines(pts, color, width)


def _text(x, y, s, color, size=13):
    fid = 0
    blf.size(fid, size * bpy.context.preferences.system.ui_scale)
    blf.color(fid, *color)
    blf.enable(fid, blf.SHADOW)
    blf.shadow(fid, 3, 0.0, 0.0, 0.0, 0.9)
    blf.position(fid, x, y, 0)
    blf.draw(fid, s)
    blf.disable(fid, blf.SHADOW)


def _with_alpha(c, a):
    return (c[0], c[1], c[2], a)


# --------------------------------------------------------------------------- 3D guides (from solved camera)

class _Projector:
    def __init__(self, region, rv3d, cam):
        self.region, self.rv3d = region, rv3d
        self.mw = cam.matrix_world
        self.inv = self.mw.inverted()
        self.near = max(cam.data.clip_start, 1e-4)

    def segment(self, p, q):
        a, b, n = self.inv @ p, self.inv @ q, self.near
        if a.z > -n and b.z > -n:
            return None
        if a.z > -n:
            a = b + (a - b) * ((-n - b.z) / (a.z - b.z))
        elif b.z > -n:
            b = a + (b - a) * ((-n - a.z) / (b.z - a.z))
        pa = location_3d_to_region_2d(self.region, self.rv3d, self.mw @ a)
        pb = location_3d_to_region_2d(self.region, self.rv3d, self.mw @ b)
        if pa is None or pb is None:
            return None
        return [pa, pb]


def _draw_grid(pr, p):
    s, n = p.grid_size, p.grid_count
    a1, a2 = {"XY": ("X", "Y"), "XZ": ("X", "Z"), "YZ": ("Y", "Z")}[p.grid_plane]
    u, v = solver.AXIS_VEC[a1] * s, solver.AXIS_VEC[a2] * s
    segs = []
    for i in range(-n, n + 1):
        for a, b in ((u * i - v * n, u * i + v * n), (v * i - u * n, v * i + u * n)):
            r = pr.segment(a, b)
            if r:
                segs += r
    _lines(segs, (1.0, 1.0, 1.0, 0.28), 1.0)


def _draw_axes(pr, p):
    length = p.grid_size * 2.0
    o = Vector((0.0, 0.0, 0.0))
    for name, vec in solver.AXIS_VEC.items():
        r = pr.segment(o, vec * length)
        if r:
            _lines(r, AXIS_COL[name], 2.5)
            _text(r[1].x + 4, r[1].y + 4, name, AXIS_COL[name], 14)


# --------------------------------------------------------------------------- main draw

def _draw_group(px, g, region_size):
    color = COL[g]
    pairs = [(px[a], px[b]) for a, b in LINES[g]]
    segs = [q for pair in pairs for q in pair]
    _lines(segs, color, 2.0)
    for a, b in pairs:
        m = (a + b) * 0.5
        _text(m.x + 6, m.y + 6, LABEL[g], color, 14)
    if len(pairs) != 2:
        return None
    vp = solver.intersect(pairs[0][0], pairs[0][1], pairs[1][0], pairs[1][1])
    if vp is None:
        return None
    centre = Vector((region_size[0] * 0.5, region_size[1] * 0.5))
    if (vp - centre).length > 40.0 * max(region_size):
        return vp
    ext = []
    for a, b in pairs:
        near = a if (a - vp).length < (b - vp).length else b
        ext += [near, vp]
    _lines(ext, _with_alpha(color, 0.45), 1.0)
    if 0 <= vp.x <= region_size[0] and 0 <= vp.y <= region_size[1]:
        k = 8
        _lines([(vp.x - k, vp.y), (vp.x + k, vp.y), (vp.x, vp.y - k), (vp.x, vp.y + k)], color, 1.5)
        _text(vp.x + 6, vp.y - 16, "VP" + LABEL[g], color, 12)
    return vp


def _long_line(a, b, size):
    d = b - a
    if d.length < 1e-6:
        return []
    d = d.normalized() * (4.0 * max(size))
    return [a - d, b + d]


def draw():
    ctx = bpy.context
    wm = ctx.window_manager
    if not getattr(wm, "vpcm_running", False):
        return
    region, rv3d, scene = ctx.region, ctx.region_data, ctx.scene
    if region is None or rv3d is None or rv3d.view_perspective != 'CAMERA':
        return
    cam = scene.camera
    if cam is None or cam.type != 'CAMERA' or cam.name != state.cam_name:
        return
    rect = frame_rect(scene, cam, region, rv3d)
    if rect is None:
        return
    p = cam.data.vpcm
    size = (region.width, region.height)

    gpu.state.blend_set('ALPHA')
    try:
        # solved-camera guides (only meaningful after a successful solve)
        if p.status_ok:
            pr = _Projector(region, rv3d, cam)
            if p.show_grid:
                _draw_grid(pr, p)
            if p.use_reference:
                av = solver.AXIS_VEC[p.ref_axis] * (p.res_distance * 20.0 + p.ref_length)
                r = pr.segment(-av, av)
                if r:
                    _lines(r, _with_alpha(COL["ref"], 0.35), 1.0)
            if p.show_axes:
                _draw_axes(pr, p)

        px = {n: uv_to_px(rect, getattr(p, n)) for n in active_handles(p)}
        vps = {}
        for g in active_groups(p):
            vps[g] = _draw_group(px, g, size)

        if p.show_horizon:
            hz_col = (1.0, 1.0, 1.0, 0.5)
            if p.mode == '2VP' and vps.get("vp1") is not None and vps.get("vp2") is not None:
                _lines(_long_line(vps["vp1"], vps["vp2"], size), hz_col, 1.0)
            elif p.mode == '1VP':
                a, b = px["hz_0"], px["hz_1"]
                if vps.get("vp1") is not None:  # horizon runs through VP1, parallel to the H line
                    d = b - a
                    _lines(_long_line(vps["vp1"], vps["vp1"] + d, size), hz_col, 1.0)

        # origin
        o = px["origin"]
        k = 12
        _lines([(o.x - k, o.y), (o.x + k, o.y), (o.x, o.y - k), (o.x, o.y + k)], COL["origin"], 1.5)
        _text(o.x + 8, o.y + 8, "O", COL["origin"], 14)

        # handles
        r = handle_radius()
        for n, q in px.items():
            g = "origin" if n == "origin" else next(gg for gg, pairs in LINES.items()
                                                     if any(n in pr_ for pr_ in pairs))
            color = COL[g]
            if n == state.hover:
                _disc(q, r * 1.25, _with_alpha(color, 0.35))
                _ring(q, r * 1.25, (1.0, 1.0, 1.0, 1.0), 2.0)
            else:
                _ring(q, r, color, 1.5)
            _disc(q, 1.6, (1.0, 1.0, 1.0, 1.0), 8)

        # status line
        msg = ("Camera Match  |  drag handles, Shift = precise, Esc/Enter = finish  |  "
               + (p.status if p.status else ""))
        _text(rect[0], rect[1] - 22, msg, (1.0, 1.0, 1.0, 0.9) if p.status_ok else (1.0, 0.75, 0.3, 1.0), 12)
    finally:
        gpu.state.blend_set('NONE')


def ensure_handler():
    if state.draw_handle is None:
        state.draw_handle = bpy.types.SpaceView3D.draw_handler_add(draw, (), 'WINDOW', 'POST_PIXEL')


def remove_handler():
    if state.draw_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(state.draw_handle, 'WINDOW')
        state.draw_handle = None
