import bpy
from .. import register_class
from bpy.app.translations import pgettext as T

@register_class
class SSSekaiRendererPanel(bpy.types.Panel):
    bl_idname = "OBJ_PT_sssekai_renderer"
    bl_label = T("Renderer")
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "SSSekai"

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.label(
            text=T(
                "EEVEE is the recommended for Unity assets, and would be the only option for Toon shaders."
            ),
            icon="INFO",
        )
        row = layout.row()
        row.label(
            text=T(
                "If you're seeing severe performance issues, try switching to an older version of Blender (e.g. 3.6)."
            ),
            icon="INFO",
        )
        row = layout.row()
        row.prop(context.scene.render, "engine")
        row = layout.row()
        row.prop(context.scene.view_settings, "view_transform")
        row = layout.row()
        if not context.scene.view_settings.view_transform == "Standard":
            row.label(
                text=T(
                    "For NPR assets, 'Standard' view transform is always recommended."
                ),
                icon="INFO",
            )
