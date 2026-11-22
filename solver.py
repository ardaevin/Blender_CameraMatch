"""Vanishing-point camera calibration math. Depends only on mathutils.

Image-plane convention ("plane coords"):
    origin = frame centre, +x right, +y up, 1 unit = frame WIDTH.
    A normalized frame coordinate (u, v) in 0..1 maps to
        x = u - 0.5,  y = (v - 0.5) / aspect
    where aspect = width / height (pixel aspect included).
Camera space follows Blender: the camera looks down -Z, +X right, +Y up.
"""

from math import sqrt, atan, degrees
from types import SimpleNamespace

from mathutils import Vector, Matrix


class SolveError(Exception):
    pass


AXIS_VEC = {"X": Vector((1.0, 0.0, 0.0)), "Y": Vector((0.0, 1.0, 0.0)), "Z": Vector((0.0, 0.0, 1.0))}
# third axis = a x b (right-handed, cyclic order)
_CROSS_FOR = {"X": ("Y", "Z"), "Y": ("Z", "X"), "Z": ("X", "Y")}


def parse_axis(ident):
    """'POS_X' -> ('X', 1.0), 'NEG_Y' -> ('Y', -1.0)"""
    return ident[-1], (-1.0 if ident.startswith("NEG") else 1.0)


# --------------------------------------------------------------------------- Blender camera helpers

def frame_aspect(scene):
    r = scene.render
    return (r.resolution_x * r.pixel_aspect_x) / (r.resolution_y * r.pixel_aspect_y)


def fit_is_horizontal(cd, aspect):
    if cd.sensor_fit == 'AUTO':
        return aspect >= 1.0
    return cd.sensor_fit == 'HORIZONTAL'


def _fit_sensor(cd):
    return cd.sensor_height if cd.sensor_fit == 'VERTICAL' else cd.sensor_width


def f_to_lens(cd, aspect, f):
    """focal in frame-width units -> lens mm for this camera's sensor settings"""
    s = _fit_sensor(cd)
    return f * s if fit_is_horizontal(cd, aspect) else f * aspect * s


def lens_to_f(cd, aspect):
    s = _fit_sensor(cd)
    return cd.lens / s if fit_is_horizontal(cd, aspect) else cd.lens / (aspect * s)


def pp_to_shift(cd, aspect, pp):
    """principal point (plane coords) -> Blender shift_x/y (units of the sensor-fit dimension)"""
    unit = 1.0 if fit_is_horizontal(cd, aspect) else 1.0 / aspect
    return -pp.x / unit, -pp.y / unit


def hfov_deg(f):
    return degrees(2.0 * atan(0.5 / f))


# --------------------------------------------------------------------------- 2D geometry

def to_plane(uv, aspect):
    return Vector((uv[0] - 0.5, (uv[1] - 0.5) / aspect))


def intersect(p0, p1, q0, q1):
    """Intersection of the infinite lines p0-p1 and q0-q1, or None if (near) parallel."""
    d1 = p1 - p0
    d2 = q1 - q0
    den = d1.x * d2.y - d1.y * d2.x
    if abs(den) < 1e-9 * max(d1.length * d2.length, 1e-12):
        return None
    t = ((q0.x - p0.x) * d2.y - (q0.y - p0.y) * d2.x) / den
    return p0 + d1 * t


def orthocenter(a, b, c):
    m = Matrix(((c.x - b.x, c.y - b.y), (c.x - a.x, c.y - a.y)))
    if abs(m.determinant()) < 1e-12:
        raise SolveError("Vanishing points are collinear - cannot find the principal point")
    return m.inverted() @ Vector((a.dot(c - b), b.dot(c - a)))


# --------------------------------------------------------------------------- solve

def _dir(p, pp, f):
    return Vector((p.x - pp.x, p.y - pp.y, -f)).normalized()


def _vp(pair, name):
    (a0, a1), (b0, b1) = pair
    v = intersect(a0, a1, b0, b1)
    if v is None:
        raise SolveError(f"{name} lines are parallel - no vanishing point")
    return v


def _axis_param(c, w, a):
    """Parameter t of the point on the axis line (t * a, through the world origin)
    closest to the camera ray c + s * w."""
    b = w.dot(a)
    den = 1.0 - b * b
    if den < 1e-9:
        raise SolveError("Reference ray is parallel to the reference axis")
    return (a.dot(c) - b * w.dot(c)) / den


def solve(mode, pp_mode, lines, axis1, axis2, f_known, origin, ref, distance):
    """
    mode     '2VP' | '1VP'
    pp_mode  'CENTER' | 'VP3'  (2VP only)
    lines    {'vp1': ((a0,a1),(b0,b1)), 'vp2': ..., 'vp3': ..., 'hz': ((h0,h1),)}  plane coords
    axis1/2  'POS_X' ... 'NEG_Z'  world axis that VP1 / VP2 (or the horizon line) points along
    f_known  focal in width units (1VP)
    origin   plane coords of the world origin
    ref      None or (p0, p1, 'X'|'Y'|'Z', length)
    distance camera->origin distance used when ref is None
    """
    ax1, s1 = parse_axis(axis1)
    ax2, s2 = parse_axis(axis2)
    if ax1 == ax2:
        raise SolveError("The two axes must be different")

    pp = Vector((0.0, 0.0))
    v1 = _vp(lines["vp1"], "VP1")
    v2 = v3 = None

    if mode == '2VP':
        v2 = _vp(lines["vp2"], "VP2")
        if pp_mode == 'VP3':
            v3 = _vp(lines["vp3"], "VP3")
            pp = orthocenter(v1, v2, v3)
        f2 = -(v1 - pp).dot(v2 - pp)
        if f2 <= 1e-12:
            raise SolveError("Vanishing points don't fit a real camera (they must lie on opposite sides of the principal point)")
        f = sqrt(f2)
        d1 = _dir(v1, pp, f)
        d2 = _dir(v2, pp, f)
    else:
        if not f_known or f_known <= 0.0:
            raise SolveError("Set a focal length for 1-VP mode")
        f = f_known
        d1 = _dir(v1, pp, f)
        h = lines["hz"][0][1] - lines["hz"][0][0]
        if h.length < 1e-9:
            raise SolveError("Horizon line is too short")
        n = d1.cross(Vector((h.x, h.y, 0.0)))
        if n.length < 1e-9:
            raise SolveError("Horizon line points straight at VP1")
        d2 = n.cross(d1).normalized()
        if Vector((d2.x, d2.y)).dot(h) < 0.0:
            d2.negate()

    # columns = world axes expressed in camera space
    cols = {ax1: d1 * s1}
    c2 = d2 * s2
    cols[ax2] = (c2 - cols[ax1] * cols[ax1].dot(c2)).normalized()
    third = ({"X", "Y", "Z"} - {ax1, ax2}).pop()
    a, b = _CROSS_FOR[third]
    cols[third] = cols[a].cross(cols[b]).normalized()

    cam_from_world = Matrix((cols["X"], cols["Y"], cols["Z"])).transposed()
    world_from_cam = cam_from_world.transposed()

    c_unit = -(world_from_cam @ _dir(origin, pp, f))  # camera position at distance 1 from origin

    if ref is not None:
        p0, p1, axis, length = ref
        av = AXIS_VEC[axis]
        t0 = _axis_param(c_unit, world_from_cam @ _dir(p0, pp, f), av)
        t1 = _axis_param(c_unit, world_from_cam @ _dir(p1, pp, f), av)
        meas = abs(t1 - t0)
        if meas < 1e-9:
            raise SolveError("Reference points land on the same spot of the axis")
        dist = length / meas
    else:
        dist = distance

    mat = world_from_cam.to_4x4()
    mat.translation = c_unit * dist
    return SimpleNamespace(f=f, pp=pp, matrix=mat, distance=dist, vp1=v1, vp2=v2, vp3=v3)
