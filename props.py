import bpy
from bpy.props import (BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty,
                       IntProperty, StringProperty)
from bpy.types import PropertyGroup

# Handle positions are normalized frame coords: (0,0) bottom-left, (1,1) top-right.
HANDLE_DEFAULTS = {
    # VP1 (+X) converges right, VP2 (+Y) converges left -> +Z comes out up
    "vp1_a0": (0.55, 0.30), "vp1_a1": (0.85, 0.38),
    "vp1_b0": (0.55, 0.70), "vp1_b1": (0.85, 0.60),
    "vp2_a0": (0.45, 0.30), "vp2_a1": (0.15, 0.38),
    "vp2_b0": (0.45, 0.70), "vp2_b1": (0.15, 0.60),
    "vp3_a0": (0.33, 0.20), "vp3_a1": (0.36, 0.80),
    "vp3_b0": (0.67, 0.20), "vp3_b1": (0.64, 0.80),
    "hz_0": (0.20, 0.12), "hz_1": (0.80, 0.12),
    "origin": (0.50, 0.25),
    "ref_0": (0.56, 0.27), "ref_1": (0.56, 0.47),
}

LINES = {
    "vp1": (("vp1_a0", "vp1_a1"), ("vp1_b0", "vp1_b1")),
    "vp2": (("vp2_a0", "vp2_a1"), ("vp2_b0", "vp2_b1")),
    "vp3": (("vp3_a0", "vp3_a1"), ("vp3_b0", "vp3_b1")),
    "hz": (("hz_0", "hz_1"),),
    "ref": (("ref_0", "ref_1"),),
}


def active_groups(p):
    g = ["vp1"]
    if p.mode == '2VP':
        g.append("vp2")
        if p.pp_mode == 'VP3':
            g.append("vp3")
    else:
        g.append("hz")
    if p.use_reference:
        g.append("ref")
    return g


def active_handles(p):
    names = ["origin"]
    for g in active_groups(p):
        for a, b in LINES[g]:
            names += [a, b]
    return names


def _resolve(self, context):
    wm = context.window_manager
    if not (getattr(wm, "vpcm_running", False) and self.auto_solve):
        return
    cam = context.scene.camera
    if cam is not None and cam.data == self.id_data:
        from .ops import solve_camera
        solve_camera(context.scene, cam)
        from .ops import tag_redraw
        tag_redraw(context)


def _redraw(self, context):
    from .ops import tag_redraw
    tag_redraw(context)


AXIS_ITEMS = [
    ('POS_X', "+X", ""), ('NEG_X', "-X", ""),
    ('POS_Y', "+Y", ""), ('NEG_Y', "-Y", ""),
    ('POS_Z', "+Z", ""), ('NEG_Z', "-Z", ""),
]


def _build():
    ann = {n: FloatVectorProperty(size=2, default=d) for n, d in HANDLE_DEFAULTS.items()}
    ann.update(
        mode=EnumProperty(
            name="Mode",
            items=[('2VP', "2 VP", "Two vanishing points: solves focal length"),
                   ('1VP', "1 VP", "One vanishing point + horizon direction: needs a known focal length")],
            default='2VP', update=_resolve),
        pp_mode=EnumProperty(
            name="Principal Point",
            items=[('CENTER', "Image Center", "Assume the optical centre is the image centre (no lens shift)"),
                   ('VP3', "From VP3", "Solve the principal point (lens shift) from a third vanishing point")],
            default='CENTER', update=_resolve),
        vp1_axis=EnumProperty(name="VP1 Axis", items=AXIS_ITEMS, default='POS_X', update=_resolve,
                              description="World axis the VP1 lines run along (pointing toward VP1)"),
        vp2_axis=EnumProperty(name="VP2 Axis", items=AXIS_ITEMS, default='POS_Y', update=_resolve,
                              description="World axis the VP2 lines (or the horizon line in 1-VP mode) run along"),
        use_reference=BoolProperty(name="Reference Distance", default=False, update=_resolve,
                                   description="Set scene scale from a known length along an axis through the origin"),
        ref_axis=EnumProperty(name="Along", items=[('X', "X", ""), ('Y', "Y", ""), ('Z', "Z", "")],
                              default='Z', update=_resolve),
        ref_length=FloatProperty(name="Length", default=1.0, min=1e-4, subtype='DISTANCE', unit='LENGTH',
                                 update=_resolve),
        distance=FloatProperty(name="Camera Distance", default=10.0, min=1e-4, subtype='DISTANCE',
                               unit='LENGTH', update=_resolve,
                               description="Distance from camera to origin when no reference distance is used"),
        auto_solve=BoolProperty(name="Live Solve", default=True,
                                description="Update the camera while dragging handles"),
        show_grid=BoolProperty(name="Grid", default=True, update=_redraw),
        grid_plane=EnumProperty(name="Plane", items=[('XY', "XY", ""), ('XZ', "XZ", ""), ('YZ', "YZ", "")],
                                default='XY', update=_redraw),
        grid_size=FloatProperty(name="Spacing", default=1.0, min=1e-4, subtype='DISTANCE', unit='LENGTH',
                                update=_redraw),
        grid_count=IntProperty(name="Lines", default=10, min=1, max=100, update=_redraw),
        show_axes=BoolProperty(name="Axes", default=True, update=_redraw),
        show_horizon=BoolProperty(name="Horizon", default=True, update=_redraw),
        status=StringProperty(default="Not solved"),
        status_ok=BoolProperty(default=False),
        res_focal=FloatProperty(), res_hfov=FloatProperty(), res_distance=FloatProperty(),
    )
    return type("VPCM_Props", (PropertyGroup,), {"__annotations__": ann})


VPCM_Props = _build()
