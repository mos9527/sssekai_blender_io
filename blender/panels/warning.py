import bpy
from .. import register_class
from bpy.app.translations import pgettext as T

# fmt: off
WARNING_TEXT = """!This is a Work in Progress
All functions are subject to change without notice
and does not represent the final state of the addon
?Generic Unity assets besides Project SEKAI ones
are supported with "Generic"-titled options.
?In doubt, please refer to the wiki or the issues page
*Links are available here""".split("\n")

ICONS = {
    '!':'INFO',
    '?':'QUESTION',
    '*':'PINNED'
}
@register_class
class SSSekaiWarningPanel(bpy.types.Panel):
    bl_idname = "OBJ_PT_sssekai_warning"
    bl_label = T("Warning")
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "SSSekai"

    def draw(self, context):
        layout = self.layout
        for i, line in enumerate(WARNING_TEXT):
            row = layout.row()
            icon = ICONS.get(line[0],None) if line else None
            kw = {'icon':icon} if icon else {}
            row.label(text=line[1 if icon else 0:],**kw)
        row = layout.row()
        row.operator("wm.url_open", text=T("Repo"), icon="URL").url = "https://github.com/mos9527/sssekai_blender_io"
        row.operator("wm.url_open", text=T("Issues"), icon="ERROR").url = "https://github.com/mos9527/sssekai_blender_io/issues"
        row.operator("wm.url_open", text=T("Wiki"), icon="BOOKMARKS").url = "https://github.com/mos9527/sssekai_blender_io/wiki"
