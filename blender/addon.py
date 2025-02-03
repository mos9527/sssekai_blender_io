from bpy.props import (
    StringProperty,
)
from bpy.app.translations import pgettext as T
import bpy, bpy.utils.previews

from sssekai.unity import sssekai_get_unity_version, sssekai_set_unity_version

from .core.consts import *
from . import register_wm_props, logger

from . import operators
from . import panels

register_wm_props(
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
