from bpy.props import EnumProperty
from bpy.app.translations import pgettext as T
import bpy, bpy.utils.previews
import os

from sssekai.unity import sssekai_get_unity_version

import UnityPy
from UnityPy.enums import ClassIDType

from ..core.consts import *
from ..core.utils import encode_asset_id
from .. import register_class, logger

from ..core.asset import build_scene_hierarchy
from .. import sssekai_global

from ..operators.importer import (
    SSSekaiBlenderImportOperator,
    SSSekaiBlenderImportPhysicsOperator,
    SSSekaiBlenderExportAnimationTypeTree,
)


@register_class
class SSSekaiBlenderImportPanel(bpy.types.Panel):
    bl_idname = "OBJ_PT_sssekai_import"
    bl_label = T("Import")
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "SSSekai"

    @staticmethod
    def enumerate_hierarchy(self, context):
        global sssekai_global
        enum_items = []

        if context is None:
            return enum_items

        wm = context.window_manager
        dirname = wm.sssekai_assetbundle_file

        if dirname == sssekai_global.current_dir:
            return sssekai_global.current_enum_entries or [("NONE", "None", "", 0)]

        logger.debug("Loading index for %s" % dirname)

        if dirname and os.path.exists(dirname):
            index = 0
            UnityPy.config.FALLBACK_VERSION_WARNED = True
            UnityPy.config.FALLBACK_UNITY_VERSION = sssekai_get_unity_version()
            sssekai_global.env = UnityPy.load(dirname)
            sssekai_global.hierarchies = build_scene_hierarchy(sssekai_global.env)
            logger.debug(
                "Found %d Scene-level objects" % len(sssekai_global.hierarchies)
            )
            # See https://docs.blender.org/api/current/bpy.props.html#bpy.props.EnumProperty
            # enum_items = [(identifier, name, description, icon, number),...]
            # Note that `identifier` is the value that will be stored (and read) in the property
            for armature in sssekai_global.hierarchies:
                encoded = encode_asset_id(armature.root.game_object)
                enum_items.append(
                    (encoded, armature.name, encoded, "ARMATURE_DATA", index)
                )
                index += 1

            sssekai_global.animations = list(
                (
                    obj.read()
                    for obj in filter(
                        lambda obj: obj.type == ClassIDType.AnimationClip,
                        sssekai_global.env.objects,
                    )
                )
            )
            for animation in sssekai_global.animations:
                encoded = encode_asset_id(animation)
                enum_items.append(
                    (encoded, animation.m_Name, encoded, "ANIM_DATA", index)
                )
                index += 1

            enum_items.sort(key=lambda x: x[0])

        sssekai_global.current_enum_entries = enum_items
        sssekai_global.current_dir = dirname
        return sssekai_global.current_enum_entries

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        row = layout.row()
        row.label(
            text=T(
                "NOTE: Seek help/notices in the project README, Wiki, GH Issues (in that order) before submitting a new issue!"
            )
        )
        row = layout.row()
        row.label(
            text=T("README/Issues: https://github.com/mos9527/sssekai_blender_io")
        )
        row = layout.row()
        row.label(text=T("Wiki: https://github.com/mos9527/sssekai_blender_io/wiki"))
        row = layout.row()
        row.prop(wm, "sssekai_unity_version_override", icon="SETTINGS")
        row = layout.row()
        layout.label(text=T("Select Asset"))
        row = layout.row()
        row.prop(wm, "sssekai_assetbundle_file", icon="FILE_FOLDER")
        row = layout.row()
        row.prop(wm, "sssekai_hierarchy_selected", icon="SCENE_DATA")
        row = layout.row()
        row.operator(SSSekaiBlenderAssetSearchOperator.bl_idname, icon="VIEWZOOM")
        layout.separator()
        row = layout.row()
        row.label(text=T("Armature Options"))
        row = layout.row()
        row.operator(
            SSSekaiBlenderImportPhysicsOperator.bl_idname, icon="RIGID_BODY_CONSTRAINT"
        )
        row.prop(wm, "sssekai_armature_display_physics", toggle=True, icon="HIDE_OFF")
        row = layout.row()
        row.label(text=T("Animation Options"))
        row = layout.row()
        row.prop(wm, "sssekai_animation_import_offset", icon="TIME")
        row.prop(wm, "sssekai_animation_append_exisiting", icon="OVERLAY")
        row = layout.row()
        row.prop(wm, "sssekai_animation_import_camera_scaling", icon="CAMERA_DATA")
        row = layout.row()
        row.prop(wm, "sssekai_animation_import_camera_offset", icon="CAMERA_DATA")
        row = layout.row()
        row.prop(wm, "sssekai_animation_import_camera_fov_offset", icon="CAMERA_DATA")
        row = layout.row()
        row.label(text=T("NLA"))
        row = layout.row()
        row.prop(wm, "sssekai_animation_import_use_nla", icon="NLA")
        row.prop(
            wm, "sssekai_animation_import_nla_always_new_tracks", icon="NLA_PUSHDOWN"
        )
        row = layout.row()
        row.label(text=T("Export"))
        row = layout.row()
        row.operator(SSSekaiBlenderExportAnimationTypeTree.bl_idname, icon="EXPORT")
        row = layout.row()
        row.label(text=T("Import"))
        row = layout.row()
        row.prop(wm, "sssekai_asset_import_mode", expand=True)
        row = layout.row()
        row.operator(SSSekaiBlenderImportOperator.bl_idname, icon="APPEND_BLEND")


@register_class
class SSSekaiBlenderAssetSearchOperator(bpy.types.Operator):
    bl_idname = "sssekai.asset_search_op"
    bl_label = T("Search")
    bl_property = "selected"
    bl_description = T("Search for assets with their object name and/or container name")

    selected: EnumProperty(
        name="Asset",
        description="Selected Asset",
        items=SSSekaiBlenderImportPanel.enumerate_hierarchy,
    )  # type: ignore

    def execute(self, context):
        wm = context.window_manager
        wm.sssekai_hierarchy_selected = self.selected
        return {"FINISHED"}

    def invoke(self, context, event):
        wm = context.window_manager
        wm.invoke_search_popup(self)
        return {"FINISHED"}
