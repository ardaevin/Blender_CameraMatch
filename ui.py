from bpy.types import Panel


def _bg_mismatch(scene, cd):
    for b in cd.background_images:
        if b.image and b.image.size[0] and b.image.size[1]:
            ia = b.image.size[0] / b.image.size[1]
            ra = scene.render.resolution_x / scene.render.resolution_y
            return abs(ia / ra - 1.0) > 0.005
    return False


class VPCM_PT_main(Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Camera Match"
    bl_label = "Camera Match"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        cam = scene.camera
        if cam is None or cam.type != 'CAMERA':
            layout.label(text="Scene has no active camera", icon='ERROR')
            return
        cd = cam.data
        p = cd.vpcm
        running = context.window_manager.vpcm_running

        layout.label(text=cam.name, icon='CAMERA_DATA')
        row = layout.row()
        row.scale_y = 1.4
        row.operator("vpcm.match", text="Stop Matching" if running else "Start Matching",
                     icon='PAUSE' if running else 'PLAY', depress=running)

        if not any(b.image for b in cd.background_images):
            layout.label(text="Camera has no background image", icon='INFO')
        elif _bg_mismatch(scene, cd):
            col = layout.column(align=True)
            col.alert = True
            col.label(text="Image aspect ≠ render aspect", icon='ERROR')
            col.operator("vpcm.resolution_from_background", icon='IMAGE_DATA')

        box = layout.box()
        box.row().prop(p, "mode", expand=True)
        col = box.column(align=True)
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(p, "vp1_axis", text="VP1 Axis")
        col.prop(p, "vp2_axis", text="VP2 Axis" if p.mode == '2VP' else "Horizon Axis")
        if p.mode == '2VP':
            box.label(text="Principal Point")
            box.row().prop(p, "pp_mode", expand=True)
        else:
            col = box.column()
            col.use_property_split = True
            col.prop(cd, "lens", text="Focal Length")

        box = layout.box()
        box.label(text="Origin & Scale", icon='EMPTY_AXIS')
        box.prop(p, "use_reference")
        col = box.column(align=True)
        col.use_property_split = True
        col.use_property_decorate = False
        if p.use_reference:
            col.prop(p, "ref_axis")
            col.prop(p, "ref_length")
            box.label(text="R handles sit on the axis through O", icon='INFO')
        else:
            col.prop(p, "distance")

        box = layout.box()
        row = box.row(align=True)
        row.prop(p, "show_grid", toggle=True)
        row.prop(p, "show_axes", toggle=True)
        row.prop(p, "show_horizon", toggle=True)
        if p.show_grid:
            col = box.column(align=True)
            col.use_property_split = True
            col.use_property_decorate = False
            col.row().prop(p, "grid_plane", expand=True)
            col.prop(p, "grid_size")
            col.prop(p, "grid_count")

        row = layout.row(align=True)
        row.prop(p, "auto_solve", toggle=True, icon='FILE_REFRESH')
        row.operator("vpcm.solve", icon='CON_CAMERASOLVER')
        layout.operator("vpcm.reset_handles", icon='LOOP_BACK')

        box = layout.box()
        if p.status_ok:
            col = box.column(align=True)
            col.label(text=f"Focal: {p.res_focal:.2f} mm  (sensor {cd.sensor_width:.2f})")
            col.label(text=f"H FOV: {p.res_hfov:.2f}°")
            col.label(text=f"Distance: {p.res_distance:.3f}")
            col.label(text=f"Shift: {cd.shift_x:.4f}, {cd.shift_y:.4f}")
        else:
            box.alert = True
            box.label(text=p.status, icon='ERROR' if p.status != "Not solved" else 'INFO')


classes = (VPCM_PT_main,)
