import bpy
from .. import register_class, bl_info
from bpy.app.translations import pgettext as T


@register_class
class SSSekaiInfoPanel(bpy.types.Panel):
    bl_idname = "OBJ_PT_sssekai_info"
    bl_label = T("Info")
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "SSSekai"

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.label(text=T("sssekai_blender_io %d.%d.%d by mos9527") % bl_info["version"])
        row = layout.row()
        row.label(text=T("When in doubt, visit the links below:"))
        row = layout.row()
        row.operator("wm.url_open", text=T("Repo"), icon="URL").url = "https://github.com/mos9527/sssekai_blender_io"
        row.operator("wm.url_open", text=T("Issues"), icon="ERROR").url = "https://github.com/mos9527/sssekai_blender_io/issues"
        row.operator("wm.url_open", text=T("Wiki"), icon="BOOKMARKS").url = "https://github.com/mos9527/sssekai_blender_io/wiki"
