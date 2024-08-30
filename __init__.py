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

try:
    import bpy
    from .blender.addon import register, unregister, SSSekaiBlenderImportPanel
    from .translations import translations_dict
    BLENDER = True
    bpy.app.translations.register(__package__, translations_dict)
except Exception as e:
    print('* Running outside of Blender:',e)
    BLENDER = False

if BLENDER and __name__ == "__main__":
    register()
