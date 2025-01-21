from bpy.types import Context
from bpy.app.translations import pgettext as T
import bpy, bpy.utils.previews
import zipfile, json, os

from sssekai.unity.AssetBundle import load_assetbundle

from UnityPy.enums import ClassIDType

from ..core.consts import *
from .. import register_class, logger
from .. import sssekai_global

from ..operators.rla import (
    SSSekaiBlenderImportRLAArmatureAnimationOperator,
    SSSekaiBlenderImportRLAShapekeyAnimationOperator,
    SSSekaiBlenderImportRLASinglePoseOperator,
    SSSekaiBlenderImportRLABatchOperator,
)


@register_class
class SSSekaiRLAImportPanel(bpy.types.Panel):
    bl_idname = "OBJ_PT_sssekai_rla_import"
    bl_label = T("RLA Import")
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "SSSekai"

    @staticmethod
    def enumerate_rla_assets(self, context):
        global sssekai_global

        if context is None:
            return []

        wm = context.window_manager

        filename = wm.sssekai_streaming_live_archive_bundle
        if (
            not os.path.isfile(filename)
            or filename == sssekai_global.rla_sekai_streaming_live_bundle_path
        ):
            return sssekai_global.rla_enum_entries or [("NONE", "None", "", 0)]

        try:
            with open(filename, "rb") as f:
                datas = dict()
                if f.read(2) == b"PK":
                    f.seek(0)
                    logger.debug("Loaded RLA ZIP archive: %s" % filename)
                    with zipfile.ZipFile(f, "r") as z:
                        for name in z.namelist():
                            with z.open(name) as zf:
                                datas[name] = zf.read()
                else:
                    f.seek(0)
                    rla_env = load_assetbundle(f)
                    logger.debug("Loaded RLA Unity bundle: %s" % filename)
                    for obj in rla_env.objects:
                        if obj.type in {ClassIDType.TextAsset}:
                            data = obj.read()
                            datas[data.m_Name] = data.m_Script.encode(
                                "utf-8", "surrogateescape"
                            )
                header = sssekai_global.rla_header = json.loads(
                    datas["sekai.rlh"].decode("utf-8")
                )
                seconds = header["splitSeconds"]
                sssekai_global.rla_raw_clips.clear()
                for sid in header["splitFileIds"]:
                    sname = "sekai_%02d_%08d" % (seconds, sid)
                    data = datas[sname + ".rla"]
                    sssekai_global.rla_raw_clips[sname] = data
                sssekai_global.rla_sekai_streaming_live_bundle_path = filename
                sssekai_global.rla_enum_entries = [
                    (sname, sname, "", "ANIM_DATA", index)
                    for index, sname in enumerate(sssekai_global.rla_raw_clips.keys())
                ]
        except Exception as e:
            logger.error("Failed to load RLA bundle: %s" % e)
        return sssekai_global.rla_enum_entries

    @classmethod
    def poll(self, context):
        wm = context.window_manager
        entry = wm.sssekai_rla_selected
        if (
            entry
            and entry != sssekai_global.rla_selected_raw_clip
            and entry in sssekai_global.rla_raw_clips
            and sssekai_global.rla_raw_clips[entry]
        ):
            SSSekaiBlenderImportRLABatchOperator.update_selected_rla_asset(entry)
        return True

    def draw(self, context: Context):
        layout = self.layout
        wm = context.window_manager
        row = layout.row()
        row.label(text=T("Statistics"))
        row = layout.row()
        row.label(text=T("Version: %d.%d") % sssekai_global.rla_get_version())
        row = layout.row()
        row.label(text=T("Time %.2fs - %.2fs") % sssekai_global.rla_clip_tick_range)
        row = layout.row()
        row.label(
            text=T("Character IDs: %s")
            % ",".join(str(x) for x in sssekai_global.rla_clip_charas)
        )
        row = layout.row()
        row.label(text=T("Number of segments: %d") % len(sssekai_global.rla_clip_data))
        row = layout.row()
        layout.prop(wm, "sssekai_streaming_live_archive_bundle", icon="FILE_FOLDER")
        row = layout.row()
        row.prop(wm, "sssekai_rla_selected", icon="SCENE_DATA")
        row = layout.row()
        row.prop(wm, "sssekai_rla_active_character", icon="ARMATURE_DATA")
        row = layout.row()
        row.prop(wm, "sssekai_rla_active_character_height", icon="ARMATURE_DATA")
        row = layout.row()
        row.prop(bpy.context.scene.render, "fps", icon="TIME")
        row = layout.row()
        row.label(text=T("NLA"))
        row = layout.row()
        row.prop(wm, "sssekai_animation_import_use_nla", icon="NLA")
        row.prop(
            wm, "sssekai_animation_import_nla_always_new_tracks", icon="NLA_PUSHDOWN"
        )
        row = layout.row()
        row.label(text=T("Import"))
        row = layout.row()
        row.operator(
            SSSekaiBlenderImportRLAArmatureAnimationOperator.bl_idname,
            icon="ARMATURE_DATA",
        )
        row.operator(
            SSSekaiBlenderImportRLAShapekeyAnimationOperator.bl_idname,
            icon="SHAPEKEY_DATA",
        )
        row = layout.row()
        row.prop(wm, "sssekai_rla_single_pose_json", icon="SHAPEKEY_DATA")
        row = layout.row()
        row.operator(
            SSSekaiBlenderImportRLASinglePoseOperator.bl_idname, icon="ARMATURE_DATA"
        )
        row = layout.row()
        row.label(
            text=T("Effective RLA clip range: %d - %d")
            % (0, len(sssekai_global.rla_raw_clips))
        )
        row = layout.row()
        selected = list(sssekai_global.rla_raw_clips or [])[
            wm.sssekai_rla_import_range[0] : wm.sssekai_rla_import_range[1]
        ]
        row.label(text=T("Selected Clip: %s") % ",".join(selected))
        row = layout.row()
        row.prop(wm, "sssekai_rla_import_range", icon="FILE_FOLDER")
        row = layout.row()
        row.operator(SSSekaiBlenderImportRLABatchOperator.bl_idname, icon="FILE_FOLDER")
