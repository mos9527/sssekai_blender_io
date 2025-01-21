import bpy
from bpy.app.translations import pgettext as T

from ..core.consts import *
from ..operators.utils import (
    SSSekaiBlenderUtilMiscRenameRemoveNumericSuffixOperator,
    SSSekaiBlenderUtilMiscRemoveBoneHierarchyOperator,
    SSSekaiBlenderUtilApplyModifersOperator,
    SSSekaiBlenderUtilArmatureMergeOperator,
    SSSekaiBlenderUtilCharacterArmatureSimplifyOperator,
    SSSekaiBlenderUtilCharacterHeelOffsetOperator,
    SSSekaiBlenderUtilCharacterNeckMergeOperator,
    SSSekaiBlenderUtilCharacterScalingMakeRootOperator,
    SSSekaiBlenderUtilMiscBatchAddArmatureModifier,
    SSSekaiBlenderUtilMiscRecalculateBoneHashTableOperator,
    SSSekaiBlenderUtilNeckAttachOperator,
)
from .. import register_class


@register_class
class SSSekaiBlenderUtilMiscPanel(bpy.types.Panel):
    bl_idname = "OBJ_PT_sssekai_misc"
    bl_label = T("Misc")
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "SSSekai"

    def draw(self, context):
        layout = self.layout
        layout.label(text=T("Armature"))
        row = layout.row()
        row.operator(
            SSSekaiBlenderUtilMiscRenameRemoveNumericSuffixOperator.bl_idname,
            icon="TOOL_SETTINGS",
        )
        row = layout.row()
        row.operator(
            SSSekaiBlenderUtilMiscRemoveBoneHierarchyOperator.bl_idname,
            icon="TOOL_SETTINGS",
        )
        row = layout.row()
        row.operator(
            SSSekaiBlenderUtilMiscRecalculateBoneHashTableOperator.bl_idname,
            icon="TOOL_SETTINGS",
        )
        row = layout.row()
        row.operator(
            SSSekaiBlenderUtilApplyModifersOperator.bl_idname, icon="TOOL_SETTINGS"
        )
        row = layout.row()
        row.operator(
            SSSekaiBlenderUtilArmatureMergeOperator.bl_idname, icon="TOOL_SETTINGS"
        )
        row = layout.row()
        row.operator(
            SSSekaiBlenderUtilCharacterArmatureSimplifyOperator.bl_idname,
            icon="TOOL_SETTINGS",
        )
        row = layout.row()
        row.prop(
            context.window_manager,
            "sssekai_util_batch_armature_mod_parent",
            icon_only=True,
        )
        row.operator(
            SSSekaiBlenderUtilMiscBatchAddArmatureModifier.bl_idname,
            icon="TOOL_SETTINGS",
        )
        row = layout.row()
        row.label(text=T("Danger Zone"))
        row = layout.row()
        row.operator(bpy.ops.script.reload.idname(), icon="FILE_SCRIPT")


@register_class
class SSSekaiBlenderUtilCharacterPanel(bpy.types.Panel):
    bl_idname = "OBJ_PT_sssekai_util_character"
    bl_label = T("Sekai Character")
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "SSSekai"

    def draw(self, context):
        active_obj = bpy.context.active_object
        layout = self.layout
        wm = context.window_manager
        row = layout.row()
        row.label(text=T("Neck Attach"))
        row = layout.row()
        row.label(text=T("Select Targets"))
        row = layout.row()
        row.prop(wm, "sssekai_util_neck_attach_obj_face")
        row.prop(wm, "sssekai_util_neck_attach_obj_body")
        row = layout.row()
        row.operator(SSSekaiBlenderUtilNeckAttachOperator.bl_idname)
        row.operator(SSSekaiBlenderUtilCharacterNeckMergeOperator.bl_idname)
        row = layout.row()
        row.label(text=T("Character Scaling"))
        row = layout.row()
        row.operator(SSSekaiBlenderUtilCharacterScalingMakeRootOperator.bl_idname)
        if active_obj and KEY_SEKAI_CHARACTER_HEIGHT in active_obj:
            row = layout.row()
            row.prop(
                active_obj,
                '["%s"]' % KEY_SEKAI_CHARACTER_HEIGHT,
                text=T("Character Height (in meters)"),
            )
            row = layout.row()
            row.prop(active_obj, "location", text=T("Use Heel Offset"))
            row = layout.row()
            row.operator(SSSekaiBlenderUtilCharacterHeelOffsetOperator.bl_idname)
