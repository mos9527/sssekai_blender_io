bl_info = {
    "name": "SSSekai Blender IO",
    "author": "mos9527",
    "version": (0, 1, 2),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > SSSekai",
    "description": "Project SEKAI / Generic Unity Game Asset Importer for Blender",
    "warning": "",
    "wiki_url": "https://github.com/mos9527/sssekai_blender_io/wiki",
    "tracker_url": "https://github.com/mos9527/sssekai_blender_io",
    "category": "Import-Export",
}

import sys, os

REQUIRED_SSSEKAI_MIN_VERSION = (0, 7, 58)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    # Dependencies
    print("* Script directory:", SCRIPT_DIR)
    sys.path.append(
        SCRIPT_DIR
    )  # Enables us to load dependencies from the addon folder directly
    print("* SSSekai: Blender Python Version:", sys.version)
    print("* SSSekai: Blender Python Interperter Path:", sys.executable)

    import UnityPy
    import sssekai

    print("* SSSekai: SSSekai Source Path:", sssekai.__file__)
    assert (
        sssekai.__VERSION_MAJOR__,
        sssekai.__VERSION_MINOR__,
        sssekai.__VERSION_PATCH__,
    ) >= REQUIRED_SSSEKAI_MIN_VERSION, "SSSekai version must be %d.%d.%d or higher. (installed=%s)" % (
        *REQUIRED_SSSEKAI_MIN_VERSION,
        sssekai.__version__,
    )
except ImportError as e:
    raise Exception(
        "Dependencies requirements not met. Refer to README.md for installation instructions. (error=%s)"
        % e
    )

import importlib, bpy, logging
from logging import getLogger

logger = getLogger("init")


def register():
    from . import blender
    from coloredlogs import install

    from .translations import translations_dict

    bpy.app.translations.register(__package__, translations_dict)

    install(
        level="DEBUG",
        fmt="%(asctime)s %(name)s\t%(levelname).1s %(message)s",
        datefmt="%H:%M:%S.%f",
        millisecond=True,
        level_styles=dict(
            spam=dict(color="green", faint=True),
            debug=dict(color="green"),
            verbose=dict(color="blue"),
            info=dict(),
            notice=dict(color="magenta"),
            warning=dict(color="yellow"),
            success=dict(color="green", bold=True),
            error=dict(color="red"),
            critical=dict(color="red", bold=True),
        ),
    )

    ADDONS = ["addon"]
    logger.debug("Blender version: %s", bpy.app.version_string)
    logger.debug("SSSekai version: %s", sssekai.__version__)
    logger.debug("UnityPy version: %s", UnityPy.__version__)
    logger.info("Registering addon.")

    blender.registry.reset()
    modules = []
    for addon in ADDONS:
        modules.append(importlib.import_module(".blender." + addon, __name__))
    for module in modules:
        importlib.reload(module)  # Ensure that the latest code is loaded everytime
    blender.registry.register_all()
    blender.registry.register_all_wm()


def unregister():
    logger.info("Unregistering addon.")
    from .blender import registry

    registry.unregister_all()
    registry.unregister_all_wm()
    bpy.app.translations.unregister(__package__)


if __name__ == "__main__":
    register()
