from bpy.props import StringProperty, BoolProperty
from bpy.app.translations import pgettext as T
import bpy, bpy.utils.previews

from sssekai.unity import sssekai_get_unity_version, sssekai_set_unity_version

from .core.consts import *
from . import register_wm_props, logger, sssekai_global

from . import operators
from . import panels


def __set_debug_link_shaders(self, context):
    sssekai_global.debug_link_shaders = (
        context.window_manager.sssekai_debug_link_shaders
    )


register_wm_props(
    sssekai_unity_version_override=StringProperty(
        name=T("Unity Version"),
        description=T("Override Unity Version"),
        default=sssekai_get_unity_version(),
        update=lambda self, context: sssekai_set_unity_version(
            context.window_manager.sssekai_unity_version_override
        ),
    ),
    sssekai_debug_link_shaders=BoolProperty(
        name=T("Link Shaders"),
        description=T("Link Shader .blend file instead of copying"),
        default=sssekai_global.debug_link_shaders,
        update=__set_debug_link_shaders,
    ),
)

logger.info("Addon reloaded")
