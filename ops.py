import bpy
from bpy.types import Operator
from mathutils import Vector

from . import overlay, solver, state
from .props import HANDLE_DEFAULTS, LINES


def tag_redraw(context):
    for win in context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def solve_camera(scene, cam):
    """Solve from the handles stored on cam.data.vpcm and write the camera. Returns (ok, message)."""
    cd = cam.data
    p = cd.vpcm
    a = solver.frame_aspect(scene)

    def pl(n):
        return solver.to_plane(getattr(p, n), a)

    try:
        lines = {g: tuple((pl(x), pl(y)) for x, y in pairs) for g, pairs in LINES.items()}
        f_known = solver.lens_to_f(cd, a) if p.mode == '1VP' else None
        ref = (pl("ref_0"), pl("ref_1"), p.ref_axis, p.ref_length) if p.use_reference else None
        r = solver.solve(p.mode, p.pp_mode, lines, p.vp1_axis, p.vp2_axis, f_known,
                         pl("origin"), ref, p.distance)
        lens = solver.f_to_lens(cd, a, r.f)
        if not 1.0 <= lens <= 5000.0:
            raise solver.SolveError(f"Focal length out of range ({lens:.1f} mm)")
    except solver.SolveError as e:
        p.status, p.status_ok = str(e), False
        return False, p.status

    cd.type = 'PERSP'
    if p.mode == '2VP':
        cd.lens = lens
    cd.shift_x, cd.shift_y = solver.pp_to_shift(cd, a, r.pp)
    cam.matrix_world = r.matrix

    p.res_focal, p.res_hfov, p.res_distance = cd.lens, solver.hfov_deg(r.f), r.distance
    p.status = f"{cd.lens:.2f} mm  |  hFOV {p.res_hfov:.2f}°  |  dist {r.distance:.3f}"
    p.status_ok = True
    if cam.parent is not None:
        p.status += "  |  camera is parented"
    return True, p.status


def _view3d_regions_under_mouse(context, event):
    """(region, rv3d) of a camera-view 3D viewport under the mouse, skipping overlapping side panels."""
    for area in context.window.screen.areas:
        if area.type != 'VIEW_3D':
            continue
        if not (area.x <= event.mouse_x < area.x + area.width and area.y <= event.mouse_y < area.y + area.height):
            continue
        win = None
        for region in area.regions:
            inside = (region.x <= event.mouse_x < region.x + region.width
                      and region.y <= event.mouse_y < region.y + region.height)
            if not inside:
                continue
            if region.type == 'WINDOW':
                win = region
            elif region.width > 1 and region.height > 1:
                return None  # over a header / toolbar / sidebar
        rv3d = area.spaces.active.region_3d
        if win and rv3d and rv3d.view_perspective == 'CAMERA':
            return win, rv3d
        return None
    return None


class VPCM_OT_match(Operator):
    bl_idname = "vpcm.match"
    bl_label = "Camera Match"
    bl_description = "Start / stop matching the active camera to its background image with vanishing points"

    @classmethod
    def poll(cls, context):
        cam = context.scene.camera
        return cam is not None and cam.type == 'CAMERA'

    def invoke(self, context, event):
        wm = context.window_manager
        if wm.vpcm_running:
            wm.vpcm_running = False
            tag_redraw(context)
            return {'FINISHED'}

        areas = [context.area] if context.area and context.area.type == 'VIEW_3D' else \
            [a for a in context.window.screen.areas if a.type == 'VIEW_3D'][:1]
        for area in areas:
            rv3d = area.spaces.active.region_3d
            if rv3d and rv3d.view_perspective != 'CAMERA':
                rv3d.view_perspective = 'CAMERA'

        state.cam_name = context.scene.camera.name
        state.hover = None
        self._drag = None
        overlay.ensure_handler()
        wm.vpcm_running = True
        wm.modal_handler_add(self)
        tag_redraw(context)
        return {'RUNNING_MODAL'}

    def _finish(self, context):
        context.window_manager.vpcm_running = False
        state.hover = None
        tag_redraw(context)
        return {'FINISHED'}

    def modal(self, context, event):
        wm = context.window_manager
        cam = bpy.data.objects.get(state.cam_name or "")
        if (not wm.vpcm_running or cam is None or cam.type != 'CAMERA'
                or context.scene.camera != cam):
            return self._finish(context)
        p = cam.data.vpcm

        # ---------------------------------------------------------------- dragging
        if self._drag:
            if event.type == 'MOUSEMOVE':
                rect = overlay.frame_rect(context.scene, cam, self._region, self._rv3d)
                if rect:
                    uv = overlay.px_to_uv(rect, event.mouse_x - self._region.x, event.mouse_y - self._region.y)
                    k = 0.2 if event.shift else 1.0
                    new = Vector(getattr(p, self._drag)) + (uv - self._last) * k
                    setattr(p, self._drag, (min(max(new.x, -2.0), 3.0), min(max(new.y, -2.0), 3.0)))
                    self._last = uv
                    if p.auto_solve:
                        solve_camera(context.scene, cam)
                    tag_redraw(context)
            elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                self._drag = None
                bpy.ops.ed.undo_push(message="Camera Match")
            elif event.type in {'RIGHTMOUSE', 'ESC'} and event.value == 'PRESS':
                setattr(p, self._drag, self._start)
                self._drag = None
                if p.auto_solve:
                    solve_camera(context.scene, cam)
                tag_redraw(context)
            return {'RUNNING_MODAL'}

        # ---------------------------------------------------------------- idle
        hit = _view3d_regions_under_mouse(context, event)
        if hit is None:
            if state.hover:
                state.hover = None
                tag_redraw(context)
            return {'PASS_THROUGH'}
        region, rv3d = hit

        if event.type in {'ESC', 'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            return self._finish(context)

        if event.type == 'MOUSEMOVE' or (event.type == 'LEFTMOUSE' and event.value == 'PRESS'):
            rect = overlay.frame_rect(context.scene, cam, region, rv3d)
            if rect is None:
                return {'PASS_THROUGH'}
            mx, my = event.mouse_x - region.x, event.mouse_y - region.y
            h = overlay.pick(p, rect, mx, my)
            if h != state.hover:
                state.hover = h
                tag_redraw(context)
            if event.type == 'LEFTMOUSE' and h:
                self._drag = h
                self._region, self._rv3d = region, rv3d
                self._start = tuple(getattr(p, h))
                self._last = overlay.px_to_uv(rect, mx, my)
                return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}


class VPCM_OT_solve(Operator):
    bl_idname = "vpcm.solve"
    bl_label = "Solve"
    bl_description = "Solve the active camera from the current handles"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        cam = context.scene.camera
        return cam is not None and cam.type == 'CAMERA'

    def execute(self, context):
        ok, msg = solve_camera(context.scene, context.scene.camera)
        tag_redraw(context)
        self.report({'INFO'} if ok else {'WARNING'}, msg)
        return {'FINISHED'} if ok else {'CANCELLED'}


class VPCM_OT_reset(Operator):
    bl_idname = "vpcm.reset_handles"
    bl_label = "Reset Handles"
    bl_description = "Move all handles back to their default positions"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        cam = context.scene.camera
        return cam is not None and cam.type == 'CAMERA'

    def execute(self, context):
        p = context.scene.camera.data.vpcm
        for n, d in HANDLE_DEFAULTS.items():
            setattr(p, n, d)
        p.status, p.status_ok = "Not solved", False
        tag_redraw(context)
        return {'FINISHED'}


class VPCM_OT_res_from_bg(Operator):
    bl_idname = "vpcm.resolution_from_background"
    bl_label = "Resolution from Background"
    bl_description = "Set the render resolution to the camera background image size (pixel aspect is kept)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        cam = context.scene.camera
        return cam is not None and cam.type == 'CAMERA' and any(
            b.image for b in cam.data.background_images)

    def execute(self, context):
        img = next(b.image for b in context.scene.camera.data.background_images if b.image)
        w, h = img.size[:]
        if w == 0 or h == 0:
            self.report({'WARNING'}, f"{img.name} has no pixel data loaded")
            return {'CANCELLED'}
        context.scene.render.resolution_x, context.scene.render.resolution_y = w, h
        self.report({'INFO'}, f"Resolution set to {w} x {h}")
        return {'FINISHED'}


classes = (VPCM_OT_match, VPCM_OT_solve, VPCM_OT_reset, VPCM_OT_res_from_bg)
