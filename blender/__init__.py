# I swear *EVERY* globals ever used in the addon are here

import bpy, os
from logging import getLogger
from typing import List, Dict, DefaultDict
from dataclasses import dataclass, field
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
logger = getLogger("sssekai")


@dataclass
class SSSekaiClassRegistry:
    """Registers classes and WindowManager properties for the addon.

    This allows us to reload the addon without restarting Blender (in theory)
    XXX: Broken in a lot of cases.
    """

    classes: List[object] = field(default_factory=list)
    wm_props: Dict[str, object] = field(default_factory=dict)

    def add_register_class(self, clazz):
        self.classes.append(clazz)

    def register_all(self):
        for clazz in self.classes:
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

    def lookup_wm(self, key: str, default=None):
        props = bpy.types.WindowManager.bl_rna.properties
        return props.get(key, None)

    def reset(self):
        self.classes.clear()
        self.wm_props.clear()


registry = SSSekaiClassRegistry()


def register_class(clazz):
    registry.add_register_class(clazz)
    return clazz


def register_wm_props(**kw):
    registry.add_register_wm(**kw)


def lookup_wm_prop(key: str, default=None):
    return registry.lookup_wm(key, default)


# Evil(!!) global variables
# Copilot autocompleted this after 'evil' lmao
from UnityPy import Environment
from UnityPy.classes import AnimationClip, Animator
from .core.types import Hierarchy

from typing import Dict, List, Tuple
from dataclasses import dataclass, field


@dataclass
class SSSekaiEnvironmentContainerCachedEnums:
    hierarchies: List[Tuple[str, str, str, str, int]] = field(default_factory=list)
    animators: List[Tuple[str, str, str, str, int]] = field(default_factory=list)
    animations: List[Tuple[str, str, str, str, int]] = field(default_factory=list)


@dataclass
class SSSekaiEnvironmentContainer:
    # PathID to types
    hierarchies: Dict[int, Hierarchy] = field(default_factory=dict)
    animators: Dict[int, Animator] = field(default_factory=dict)
    animations: Dict[int, AnimationClip] = field(default_factory=dict)
    enums: SSSekaiEnvironmentContainerCachedEnums = field(
        default_factory=SSSekaiEnvironmentContainerCachedEnums
    )

    def update_enums(self):
        # [(identifier, name, description, icon, number), ...]
        self.enums.hierarchies = [
            (str(path_id), hierarchy.name, "", "ARMATURE_DATA", index)
            for index, (path_id, hierarchy) in enumerate(self.hierarchies.items())
        ]
        self.enums.hierarchies = sorted(self.enums.hierarchies, key=lambda x: x[1])
        self.enums.animators = [
            (
                str(path_id),
                animator.m_GameObject.read().m_Name,
                "",
                "DECORATE_ANIMATE",
                index,
            )
            for index, (path_id, animator) in enumerate(self.animators.items())
        ]
        self.enums.animators = sorted(self.enums.animators, key=lambda x: x[1])
        self.enums.animations = [
            (str(path_id), animation.m_Name, "", "ANIM_DATA", index)
            for index, (path_id, animation) in enumerate(self.animations.items())
        ]
        self.enums.animations = sorted(self.enums.animations, key=lambda x: x[1])


@dataclass
class SSSekaiGlobalEnvironment:
    # --- UnityPy
    env: Environment = None
    cotainers: DefaultDict[str, SSSekaiEnvironmentContainer] = field(
        default_factory=lambda: defaultdict(SSSekaiEnvironmentContainer)
    )
    container_enum: List[Tuple[str, str, str, str, int]] = field(default_factory=list)
    # --- RLA
    rla_sekai_streaming_live_bundle_path: str = None
    rla_header: dict = field(default_factory=dict)
    rla_clip_data: dict = field(default_factory=dict)
    rla_selected_raw_clip: str = None
    rla_raw_clips: dict = field(default_factory=dict)
    rla_animations: dict = field(default_factory=dict)  # character ID -> Animation
    rla_clip_tick_range: tuple = (0, 0)
    rla_clip_charas: set = field(default_factory=set)
    rla_enum_entries: list = None
    rla_enum_bookmarks: list = field(default_factory=list)

    def rla_get_version(self):
        return (
            tuple(map(int, sssekai_global.rla_header["version"].split(".")))
            if "version" in sssekai_global.rla_header
            else (0, 0)
        )


sssekai_global = SSSekaiGlobalEnvironment()
