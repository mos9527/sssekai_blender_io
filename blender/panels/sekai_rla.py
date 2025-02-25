from bpy.types import Context
from bpy.app.translations import pgettext as T
import bpy, bpy.utils.previews
import zipfile, json, os

from sssekai.unity.AssetBundle import load_assetbundle

from UnityPy.enums import ClassIDType
from bpy.props import StringProperty, EnumProperty, IntProperty, IntVectorProperty
from ..core.consts import *
from .. import register_class, register_wm_props, logger
from .. import sssekai_global

from ..operators.sekai_rla import (
    SSSekaiBlenderImportRLASegmentOperator,
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
            # Support ZIP archives as well
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
                logger.debug("RLA version: %s" % header["version"])
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
        row.prop(bpy.context.scene.render, "fps", icon="TIME")
        row = layout.row()
        row.label(
            text=T("Effective RLA clip range: %d - %d")
            % (0, len(sssekai_global.rla_raw_clips))
        )
        row = layout.row()
        selected = list(sssekai_global.rla_raw_clips or [])[
            wm.sssekai_rla_import_range[0] : wm.sssekai_rla_import_range[1] + 1
        ]
        row.label(text=T("Selected Clip: %s") % ",".join(selected))
        row = layout.row()
        row.prop(wm, "sssekai_rla_import_range", icon="FILE_FOLDER")
        row = layout.row()
        active_obj = bpy.context.active_object
        if active_obj and KEY_SEKAI_CHARACTER_BODY_OBJ in active_obj:
            row.label(
                text=T(
                    "Don't forget to *correctly* configure the Height of the character in the Import tab first"
                ),
                icon="INFO",
            )
            row = layout.row()
            row.label(
                text=T(
                    "NLA tracks will be used and NO new tracks will be automatically created regardless of the option specified!"
                ),
                icon="INFO",
            )
            row = layout.row()
            row.operator(
                SSSekaiBlenderImportRLASegmentOperator.bl_idname,
                icon="ARMATURE_DATA",
            )
            row = layout.row()
            row.operator(
                SSSekaiBlenderImportRLABatchOperator.bl_idname, icon="FILE_FOLDER"
            )
        else:
            row.label(
                text=T("Please select a SekaiCharacterRoot with a Body armature first")
            )


register_wm_props(
    sssekai_streaming_live_archive_bundle=StringProperty(
        name=T("RLA Bundle"),
        description=T(
            "The bundle file inside 'streaming_live/archive' directory.\nOr alternatively, a ZIP file containing 'sekai.rlh' (json) and respective 'sekai_xx_xxxxxx.rla' files. These files should have the extension '.rlh', '.rla'"
        ),
        subtype="FILE_PATH",
    ),
    sssekai_rla_selected=EnumProperty(
        name=T("RLA Clip"),
        description=T("Selected RLA Clip"),
        items=SSSekaiRLAImportPanel.enumerate_rla_assets,
    ),
    sssekai_rla_import_range=IntVectorProperty(
        name=T("Import Range"),
        description=T("Import clips from this range, order is as shown in the list"),
        size=2,
        default=[0, 0],
    ),
    sssekai_rla_active_character=IntProperty(
        name=T("Character ID"), description=T("Active Character ID"), default=0
    ),
    sssekai_util_neck_attach_obj_face=bpy.props.PointerProperty(
        name=T("Face"), type=bpy.types.Armature
    ),
    sssekai_util_neck_attach_obj_body=bpy.props.PointerProperty(
        name=T("Body"), type=bpy.types.Armature
    ),
)
