import bpy
from .. import register_class
from bpy.app.translations import pgettext as T

from ..operators.renderer import SSSekaiBlenderRendererApplyRecommendedSettingsOperator


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
                "Generally EEVEE is recommended for previewing assets (available before 4.2) for better performance."
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
        if context.scene.render.engine == "BLENDER_EEVEE":
            row.label(
                text=T(
                    "Screen Space Reflections (SSR) is required for reflective surfaces to work."
                ),
            )
            row = layout.row()
            row.prop(context.scene.eevee, "use_ssr")
            row = layout.row()
        elif context.scene.render.engine == "BLENDER_EEVEE_NEXT":
            row.prop(context.scene.eevee, "use_raytracing")
            row = layout.row()
            if not context.scene.eevee.use_raytracing:
                row.label(
                    text=T(
                        "Raytracing enables SSR (Screen Space Reflections) which is required for reflective surfaces to work."
                    ),
                    icon="INFO",
                )
                row = layout.row()
        row.prop(context.scene.view_settings, "view_transform")
        row = layout.row()
        if not context.scene.view_settings.view_transform == "Standard":
            row.label(
                text=T(
                    "View Transform should be set to Standard since the assets are authored in SRGB space."
                ),
                icon="INFO",
            )
        row = layout.row()
        row.operator(SSSekaiBlenderRendererApplyRecommendedSettingsOperator.bl_idname)
