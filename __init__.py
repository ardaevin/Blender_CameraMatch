"""Camera Match - fSpy-style camera calibration from vanishing points, inside Blender's camera view."""

import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, PointerProperty

from . import ops, overlay, props, state, ui

_classes = (props.VPCM_Props,) + ops.classes + ui.classes


@persistent
def _on_load(_dummy):
    wm = bpy.context.window_manager
    if wm is not None:
        wm.vpcm_running = False
    state.hover = None


def register():
    for c in _classes:
        bpy.utils.register_class(c)
    bpy.types.Camera.vpcm = PointerProperty(type=props.VPCM_Props)
    bpy.types.WindowManager.vpcm_running = BoolProperty(default=False)
    bpy.app.handlers.load_post.append(_on_load)


def unregister():
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
    try:
        bpy.context.window_manager.vpcm_running = False
    except Exception:
        pass
    overlay.remove_handler()
    del bpy.types.WindowManager.vpcm_running
    del bpy.types.Camera.vpcm
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)
