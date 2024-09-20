bl_info = {
    "name": "SSSekai Blender IO",
    "author": "mos9527",
    "version": (0, 0, 1),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > SSSekai",
    "description": "Project SEKAI Asset Importer for Blender 4.0+",
    "warning": "",
    "wiki_url": "https://github.com/mos9527/sssekai_blender_io/wiki",
    "tracker_url": "https://github.com/mos9527/sssekai_blender_io",
    "category": "Import-Export",
}
# Dependencies
try:
    import UnityPy
    import sssekai
except ImportError as e:
    raise Exception('Dependencies incomplete. Refer to README.md for installation instructions.')

import importlib, bpy, logging
from logging import getLogger

logger = getLogger(__name__)
def register():
    from .blender import registry, SCRIPT_DIR
    from coloredlogs import install       
    install(level='DEBUG', fmt='sssekai | %(levelname)s | %(module)s | %(message)s')

    ADDONS = ['addon']
    logger.debug('*** SSSekai Blender IO ***')
    logger.debug('Script directory: %s', SCRIPT_DIR)
    logger.debug('Blender version: %s', bpy.app.version_string)
    logger.info('Registering addon.')
    modules = []
    for addon in ADDONS:
        modules.append(importlib.import_module('.blender.' + addon , __name__))
    registry.reset()
    for module in modules:
        importlib.reload(module) # Ensure that the latest code is loaded everytime
    registry.register_all()   
    registry.register_all_wm()

    from .translations import translations_dict
    bpy.app.translations.register(__package__, translations_dict)

def unregister():
    logger.info('Unregistering addon.')
    from .blender import registry

    registry.unregister_all()
    registry.unregister_all_wm()
    bpy.app.translations.unregister(__package__)

if __name__ == "__main__":
    register()
