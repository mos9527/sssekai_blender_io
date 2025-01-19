# I swear *EVERY* globals ever used in the addon are here

import bpy, os
from logging import getLogger
from typing import List

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
logger = getLogger("sssekai")


class SSSekaiClassRegistry:
    """Registers classes and WindowManager properties for the addon.

    This allows us to reload the addon without restarting Blender (in theory)
    XXX: Broken in a lot of cases.
    """

    classes = list()
    wm_props = dict()

    def add_register_class(self, clazz):
        self.classes.append(clazz)

    def register_all(self):
        for clazz in self.classes[::-1]:
            bpy.utils.register_class(clazz)

    def unregister_all(self):
        for clazz in self.classes:
            bpy.utils.unregister_class(clazz)
        self.classes.clear()

    def add_register_wm(self, **kw):
        self.wm_props.update(kw)

    def register_all_wm(self):
        for k, v in self.wm_props.items():
            setattr(bpy.types.WindowManager, k, v)

    def unregister_all_wm(self):
        for k, v in self.wm_props.items():
            setattr(bpy.types.WindowManager, k, None)
        self.wm_props.clear()

    def reset(self):
        self.classes.clear()
        self.wm_props.clear()


registry = SSSekaiClassRegistry()


def register_class(clazz):
    registry.add_register_class(clazz)
    return clazz


def register_wm_props(**kw):
    registry.add_register_wm(**kw)


# Evil(!!) global variables
# Copilot autocompleted this after 'evil' lmao
from typing import Set
from UnityPy import Environment
from UnityPy.classes import AnimationClip
from .types import Hierarchy


class SSSekaiGlobalEnvironment:
    current_dir: str = None
    current_enum_entries: list = None
    # --- SSSekai exclusive
    env: Environment
    articulations: List[Hierarchy]
    armatures: List[Hierarchy]
    animations: List[AnimationClip]
    # --- RLA exclusive
    rla_sekai_streaming_live_bundle_path: str = None
    rla_header: dict = dict()
    rla_clip_data: dict = dict()
    rla_selected_raw_clip: str = 0
    rla_raw_clips: dict = dict()
    rla_animations: dict = dict()  # character ID -> Animation
    rla_clip_tick_range: tuple = (0, 0)
    rla_clip_charas: set = set()
    rla_enum_entries: list = None
    rla_enum_bookmarks: list = []

    def rla_get_version(self):
        return (
            tuple(map(int, sssekai_global.rla_header["version"].split(".")))
            if "version" in sssekai_global.rla_header
            else (0, 0)
        )


sssekai_global = SSSekaiGlobalEnvironment()
