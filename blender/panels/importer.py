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
import os

from sssekai.unity import sssekai_get_unity_version

import UnityPy
from UnityPy.enums import ClassIDType
from UnityPy.classes import AnimationClip, Animator

from ..core.consts import *
from ..core.utils import encode_asset_id
from .. import register_class, register_wm_props, logger

from ..core.asset import build_scene_hierarchy
from .. import sssekai_global, SSSekaiEnvironmentContainer

from ..operators.importer import (
    SSSekaiBlenderImportOperator,
    SSSekaiBlenderImportPhysicsOperator,
    SSSekaiBlenderExportAnimationTypeTree,
)

EMPTY_OPT = ("--", "Not Available", "", "ERROR", 0)
EMPTY_CONTAINER = "<default>"
ALL_CONTAINER = "<all>"


def update_environment(path: str):
    global sssekai_global

    if path and os.path.exists(path):
        if sssekai_global.env and sssekai_global.env.path == path:
            return
        logger.debug("Loading environment: %s" % path)
        UnityPy.config.FALLBACK_VERSION_WARNED = True
        UnityPy.config.FALLBACK_UNITY_VERSION = sssekai_get_unity_version()
        sssekai_global.env = UnityPy.load(path)
        sssekai_global.cotainers.clear()

        hierarchies = build_scene_hierarchy(sssekai_global.env)
        for hierarchy in hierarchies:
            root = hierarchy.root.game_object
            container = root.object_reader.container or EMPTY_CONTAINER
            sssekai_global.cotainers[container].hierarchies[
                root.object_reader.path_id
            ] = hierarchy

        predicate = lambda obj: obj.type == ClassIDType.AnimationClip
        for animation in (
            obj.read() for obj in filter(predicate, sssekai_global.env.objects)
        ):
            animation: AnimationClip
            container = animation.object_reader.container or EMPTY_CONTAINER
            sssekai_global.cotainers[container].animations[
                animation.object_reader.path_id
            ] = animation

        predicate = lambda obj: obj.type == ClassIDType.Animator
        for animator in (
            obj.read() for obj in filter(predicate, sssekai_global.env.objects)
        ):
            animator: Animator
            container = (
                animator.m_GameObject.read().object_reader.container or EMPTY_CONTAINER
            )
            sssekai_global.cotainers[container].animators[
                animator.object_reader.path_id
            ] = animator

        for container in sssekai_global.cotainers.values():
            container.update_enums()

        sssekai_global.container_enum = [
            (container, container, "", "FILE_FOLDER", index)
            for index, container in enumerate(sssekai_global.cotainers)
        ]
    else:
        sssekai_global.container_enum.clear()


def enumerate_containers(obj: bpy.types.Object, context: bpy.types.Context):
    global sssekai_global

    wm = context.window_manager
    path = wm.sssekai_selected_assetbundle_file
    update_environment(path)
    return sssekai_global.container_enum or [EMPTY_OPT]


def enumerate_prop(container_selection_key: str, prop: str):
    global sssekai_global

    def inner(obj: bpy.types.Object, context: bpy.types.Context):
        wm = context.window_manager
        container = getattr(wm, container_selection_key)
        return getattr(sssekai_global.cotainers[container].enums, prop) or [EMPTY_OPT]

    return inner


register_wm_props(
    sssekai_selected_assetbundle_file=StringProperty(
        name=T("Directory"),
        description=T(
            "Where the asset bundle(s) are located. Every AssetBundle in this directory will be loaded (if possible)"
        ),
        subtype="DIR_PATH",
    ),
    sssekai_selected_hierarchy_container=EnumProperty(
        name=T("Container"),
        description=T("Selected Container"),
        items=enumerate_containers,
    ),
    sssekai_selected_hierarchy=EnumProperty(
        name=T("Hierarchy"),
        description=T("Selected Hierarchy"),
        items=enumerate_prop("sssekai_selected_hierarchy_container", "hierarchies"),
    ),
    sssekai_selected_animation_container=EnumProperty(
        name=T("Container"),
        description=T("Selected Container"),
        items=enumerate_containers,
    ),
    sssekai_selected_animation=EnumProperty(
        name=T("Animation"),
        description=T("Selected Animation"),
        items=enumerate_prop("sssekai_selected_animation_container", "animations"),
    ),
    sssekai_selected_animator_container=EnumProperty(
        name=T("Container"),
        description=T("Selected Container"),
        items=enumerate_containers,
    ),
    sssekai_selected_animator=EnumProperty(
        name=T("Animator"),
        description=T("Selected Animator"),
        items=enumerate_prop("sssekai_selected_animator_container", "animators"),
    ),
    sssekai_animation_append_exisiting=BoolProperty(
        name=T("Append"),
        description=T(
            "Append Animations to the existing Action, instead of overwriting it"
        ),
        default=False,
    ),
    sssekai_animation_use_animator=BoolProperty(
        name=T("Use Animator"),
        description=T(
            "Use the selected Animator to import the Animation, instead of building the relations in runtime"
        ),
        default=False,
    ),
    sssekai_animation_import_offset=IntProperty(
        name=T("Offset"), description=T("Animation Offset in frames"), default=0
    ),
    sssekai_animation_import_use_nla=BoolProperty(
        name=T("Use NLA"), description=T("Import as NLA Track"), default=False
    ),
    sssekai_animation_import_nla_always_new_tracks=BoolProperty(
        name=T("Create new NLA tracks"),
        description=T("Always create new NLA tracks"),
        default=False,
    ),
    sssekai_import_type=EnumProperty(
        name=T("Import Type"),
        description=T("Type of import to perform"),
        items=[
            (
                "IMPORT_HIERARCHY",
                T("Hierarchy"),
                T("Import the selected hierarchy"),
                "OUTLINER_OB_ARMATURE",
                1,
            ),
            (
                "IMPORT_ANIMATION",
                T("Animation"),
                T("Import the selected animation"),
                "ANIM_DATA",
                2,
            ),
        ],
    ),
    sssekai_hierarchy_import_mode=EnumProperty(
        name=T("Hierarchy Import Mode"),
        description=T("Method to import the selected hierarchy"),
        items=[
            # [(identifier, name, description, icon, number),...]
            (
                "SEKAI_CHARACTER",
                T("Sekai Character"),
                T(
                    "(Project SEKAI) Import the selected hierarchy as a Project SEKAI Character, with the necessary setup for material, lighting and so on"
                ),
                "OUTLINER_OB_ARMATURE",
                1,
            ),
            (
                "SEKAI_STAGE",
                T("Sekai Stage"),
                T(
                    "(Project SEKAI) Import the selected hierarchy as a Project SEKAI Stage, with the necessary setup for material, lighting and so on"
                ),
                "OUTLINER_OB_EMPTY",
                2,
            ),
            (
                "GENERIC_ARMATURE",
                T("Generic Armature"),
                T(
                    "Import the selected hierarchy as a generic armature, with no additional setup"
                ),
                "ARMATURE_DATA",
                3,
            ),
            (
                "GENERIC_ARTICULATION",
                T("Generic Articulation"),
                T(
                    "Import the selected hierarchy as a generic articulation (built with joint hierarchy), with no additional setup"
                ),
                "OUTLINER_DATA_EMPTY",
                4,
            ),
        ],
    ),
    sssekai_character_height=FloatProperty(
        name=T("Character Height"),
        description=T("Height of the character in meters"),
        default=1.00,
    ),
)


@register_class
class SSSekaiBlenderImportPanel(bpy.types.Panel):
    bl_idname = "OBJ_PT_sssekai_import"
    bl_label = T("Import")
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "SSSekai"

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        row = layout.row()
        row.prop(wm, "sssekai_unity_version_override", icon="SETTINGS")
        row = layout.row()
        layout.label(text=T("Select Directory"), icon="SETTINGS")
        row = layout.row()
        row.prop(wm, "sssekai_selected_assetbundle_file", icon="FILE_FOLDER")
        row = layout.row()

        row.label(text=T("Import Type"), icon="IMPORT")
        row = layout.row()
        row.prop(wm, "sssekai_import_type", expand=True)
        row = layout.row()

        layout.label(text=T("Select Asset"), icon="SCENE_DATA")
        row = layout.row()
        import_type = wm.sssekai_import_type
        if import_type == "IMPORT_ANIMATION":
            row.prop(
                wm,
                "sssekai_selected_animation_container",
                text=T("Container"),
                icon="ANIM_DATA",
            )
            row = layout.row()
            row.prop(wm, "sssekai_selected_animation")
            row = layout.row()
            row.prop(
                wm,
                "sssekai_selected_animator_container",
                text=T("Container"),
                icon="DECORATE_ANIMATE",
            )
            row = layout.row()
            row.prop(wm, "sssekai_selected_animator")
            row = layout.row()
        elif import_type == "IMPORT_HIERARCHY":
            row.prop(
                wm,
                "sssekai_selected_hierarchy_container",
                text=T("Container"),
                icon="OUTLINER_OB_ARMATURE",
            )
            row = layout.row()
            row.prop(wm, "sssekai_selected_hierarchy")
            row = layout.row()

        row.label(text=T("Import Options"), icon="OPTIONS")
        row = layout.row()
        if import_type == "IMPORT_ANIMATION":
            row.label(text=T("Animation Options"), icon="ANIM_DATA")
            row = layout.row()
            row.prop(wm, "sssekai_animation_import_offset", icon="TIME")
            row = layout.row()
            row.prop(wm, "sssekai_animation_import_use_nla", icon="NLA")
            row.prop(
                wm,
                "sssekai_animation_import_nla_always_new_tracks",
                icon="NLA_PUSHDOWN",
            )
            row = layout.row()
            row.prop(wm, "sssekai_animation_use_animator", icon="DECORATE_ANIMATE")
            row.prop(wm, "sssekai_animation_append_exisiting", icon="OVERLAY")
            row = layout.row()
        elif import_type == "IMPORT_HIERARCHY":
            row.label(text=T("Hierarchy Options"), icon="OUTLINER_OB_ARMATURE")
            row = layout.row()
            row.prop(wm, "sssekai_hierarchy_import_mode", expand=True)
            row = layout.row()
            import_mode = wm.sssekai_hierarchy_import_mode
            if import_mode == "SEKAI_CHARACTER":
                row.label(
                    text=T("Project SEKAI Character Options"),
                    icon="OUTLINER_OB_ARMATURE",
                )
                row = layout.row()
                row.label(
                    text=T(
                        "NOTE: To import a Project SEKAI Armature, you'll have to create a Character Controller first. Click the operator below to make one."
                    )
                )
                row = layout.row()
                row.operator(
                    "sssekai.create_character_controller_op",
                    icon="OUTLINER_OB_ARMATURE",
                )
        row = layout.row()
        row.operator(SSSekaiBlenderImportOperator.bl_idname, icon="APPEND_BLEND")
