import bpy
from .. import register_class
from bpy.app.translations import pgettext as T


@register_class
class SSSekaiBlenderRendererApplyRecommendedSettingsOperator(bpy.types.Operator):
    bl_idname = "sssekai.renderer_apply_recommended_settings"
    bl_label = T("Apply Recommended Settings")
    bl_description = T("Apply recommended settings for rendering PJSK assets")

    def execute(self, context):
        wm = context.window_manager
        if context.scene.render.engine == "BLENDER_EEVEE_NEXT":
            context.scene.eevee.use_raytracing = True
            context.scene.view_settings.view_transform = "Standard"
        elif context.scene.render.engine == "BLENDER_EEVEE":
            context.scene.eevee.use_ssr = True
            context.scene.view_settings.view_transform = "Standard"
        return {"FINISHED"}
