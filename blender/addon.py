from bpy.props import (
    StringProperty,
    EnumProperty,
    BoolProperty,
    IntVectorProperty,
    IntProperty,
    FloatProperty,
    FloatVectorProperty,
)
from bpy.app.translations import pgettext as T
import bpy, bpy.utils.previews

from sssekai.unity import sssekai_get_unity_version, sssekai_set_unity_version

from .core.consts import *
from .core.math import blVector
from . import register_wm_props, logger

from . import operators
from . import panels

register_wm_props(
    # sssekai_streaming_live_archive_bundle=StringProperty(
    #     name=T("RLA Bundle"),
    #     description=T(
    #         "The bundle file inside 'streaming_live/archive' directory.\nOr alternatively, a ZIP file containing 'sekai.rlh' (json) and respective 'sekai_xx_xxxxxx.rla' files. These files should have the extension '.rlh', '.rla'"
    #     ),
    #     subtype="FILE_PATH",
    # ),
    # sssekai_rla_selected=EnumProperty(
    #     name=T("RLA Clip"),
    #     description=T("Selected RLA Clip"),
    #     items=panels.rla.SSSekaiRLAImportPanel.enumerate_rla_assets,
    # ),
    # sssekai_rla_active_character=IntProperty(
    #     name=T("Character ID"), description=T("Active Character ID"), default=0
    # ),
    # sssekai_rla_active_character_height=FloatProperty(
    #     name=T("Height"), description=T("Active Character Height"), default=1.00
    # ),
    # sssekai_rla_single_pose_json=StringProperty(
    #     name=T("RLA Pose JSON"),
    #     description=T(
    #         "JSON of a single RLA pose (e.g. {'bodyPosition':...}) dumped by rla2json w/ sssekai"
    #     ),
    #     default="",
    # ),
    # sssekai_util_neck_attach_obj_face=bpy.props.PointerProperty(
    #     name=T("Face"), type=bpy.types.Armature
    # ),
    # sssekai_util_neck_attach_obj_body=bpy.props.PointerProperty(
    #     name=T("Body"), type=bpy.types.Armature
    # ),
    sssekai_unity_version_override=StringProperty(
        name=T("Unity Version"),
        description=T("Override Unity Version"),
        default=sssekai_get_unity_version(),
        update=lambda self, context: sssekai_set_unity_version(
            context.window_manager.sssekai_unity_version_override
        ),
    ),
)

logger.info("Addon reloaded")
