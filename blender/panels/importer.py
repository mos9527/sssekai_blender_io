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
from .. import register_class, register_wm_props, logger

from ..core.asset import build_scene_hierarchy
from .. import sssekai_global, SSSekaiEnvironmentContainer

from ..operators.importer import (
    SSSekaiBlenderCreateCameraRigControllerOperator,
    SSSekaiBlenderImportHierarchyOperator,
    SSSekaiBlenderImportHierarchyAnimationOperaotr,
    SSSekaiBlenderImportSekaiCameraAnimationOperator,
    SSSekaiBlenderCreateCharacterControllerOperator,
    SSSekaiBlenderImportSekaiCharacterMotionOperator,
    SSSekaiBlenderImportSekaiCharacterFaceMotionOperator,
    SSSekaiBlenderImportGlobalLightAnimationOperator,
    SSSekaiBlenderImportCharacterLightAnimationOperator,
)

from ..operators.utils import (
    SSSekaiBlenderUtilCharaNeckAttachOperator,
    SSSekaiBlenderUtilCharaNeckMergeOperator,
)

from ..operators.sekai_rigidbody import (
    SSSekaiBlenderHierarchyAddSekaiRigidBodiesOperator,
)

EMPTY_OPT = ("<no assest selected!>", "Not Available", "", "ERROR", 0)
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
                hierarchy.path_id
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
        sssekai_global.container_enum = sorted(
            sssekai_global.container_enum, key=lambda x: x[1]
        )
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
            "Use the selected Animator to import the Animation, instead of building the relations in runtime. NOTE: Does not restore bind pose yet!"
        ),
        default=False,
    ),
    sssekai_animation_root_bone=StringProperty(
        name=T("Root Bone"),
        description=T(
            "Root bone of the animation. Leave empty to use the armature root(s)"
        ),
        default="",
    ),
    sssekai_animation_import_offset=IntProperty(
        name=T("Offset"), description=T("Animation Offset in frames"), default=0
    ),
    sssekai_animation_always_lerp=BoolProperty(
        name=T("Always Lerp"),
        description=T(
            "Always interpolate keyframes linearly. Useful for densely packed keyframes"
        ),
        default=False,
    ),
    sssekai_animation_import_use_nla=BoolProperty(
        name=T("Use NLA"),
        description=T(
            "Import as NLA Track. Otherwise, the imported animation overwrites the exisiting one."
        ),
        default=True,
    ),
    sssekai_animation_import_nla_always_new_track=BoolProperty(
        name=T("Always New Track"),
        description=T("Always create a new NLA Track"),
        default=True,
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
    sssekai_hierarchy_import_bindpose=BoolProperty(
        name=T("Bind Pose"),
        description=T(
            "Correct the hierarchy to match the bind pose of the Skinned Meshes that might be imported. Only use this if the pose is incorrect"
        ),
        default=False,
    ),
    sssekai_hierarchy_import_seperate_armatures=BoolProperty(
        name=T("Seperate Armatures"),
        description=T(
            "Import Skinned Meshes into different armatures. MUST be used IF your armature comes with duped bones"
        ),
        default=False,
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
                "GENERIC",
                T("Generic"),
                T(
                    "Import the selected hierarchy as a generic armature, with no additional setup"
                ),
                "ARMATURE_DATA",
                3,
            ),
        ],
    ),
    sssekai_character_height=FloatProperty(
        name=T("Character Height"),
        description=T("Height of the character in meters"),
        default=1.00,
    ),
    sssekai_character_type=EnumProperty(
        name=T("Character Type"),
        description=T("Type of character mesh to import."),
        items=[
            (
                "HEAD",
                T("Face"),
                T("Hierachy is a Face object"),
                "SHAPEKEY_DATA",
                1,
            ),
            (
                "BODY",
                T("Body"),
                T("Hierachy is a Body object"),
                "CON_ARMATURE",
                2,
            ),
        ],
    ),
    sssekai_animation_import_mode=EnumProperty(
        name=T("Animation Import Mode"),
        description=T("Method to import the selected animation"),
        items=[
            (
                "SEKAI_MOTION",
                T("Sekai Motion"),
                T("Import the selected animation as a Project SEKAI Motion"),
                "ARMATURE_DATA",
                1,
            ),
            (
                "SEKAI_FACE",
                T("Sekai Face"),
                T("Import the selected animation as a Project SEKAI Face Animation"),
                "SHAPEKEY_DATA",
                2,
            ),
            (
                "SEKAI_CAMERA",
                T("Sekai Camera"),
                T("Import the selected animation as a Project SEKAI Camera Animation"),
                "CAMERA_DATA",
                3,
            ),
            (
                "SEKAI_LIGHT",
                T("Sekai Light"),
                T("Import the selected animation as a Project SEKAI Light Animation"),
                "LIGHT_DATA",
                4,
            ),
            (
                "GENERIC",
                T("Generic Transform"),
                T(
                    "Import the selected animation as generic animation data applied on Transforms"
                ),
                "ANIM_DATA",
                5,
            ),
        ],
    ),
    sssekai_animation_light_type=EnumProperty(
        name=T("Light Animation Type"),
        description=T("Type of light animation to import."),
        items=[
            (
                "DIRECTIONAL",
                T("Directional"),
                T("Directional Light"),
                "LIGHT_SUN",
                1,
            ),
            (
                "AMBIENT",
                T("Ambient"),
                T("Ambient Light"),
                "LIGHT_HEMI",
                2,
            ),
            (
                "CHARACTER_RIM",
                T("Chara Rim"),
                T("Character Rim Light"),
                "LIGHT_POINT",
                3,
            ),
            (
                "CHARACTER_AMBIENT",
                T("Chara Ambient"),
                T("Character Ambient Light"),
                "LIGHT_HEMI",
                4,
            ),
        ],
    ),
    sssekai_camera_import_is_sub_camera=BoolProperty(
        name=T("Sub Camera"),
        description=T("Import the camera as a sub camera"),
        default=False,
    ),
    sssekai_generic_material_import_slot=StringProperty(
        name=T("Material Slot"),
        description=T(
            "Material Slot to use as the diffuse map. Check the System Console during import for slot info. NOTE: All texture maps will be imported regardless which one is picked"
        ),
        default="_MainTex",
    ),
    sssekai_generic_material_import_skip=BoolProperty(
        name=T("Skip Materials"),
        description=T("Skip importing materials"),
        default=False,
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
        active_obj = context.active_object

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
        match import_type:
            case "IMPORT_ANIMATION":
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
            case "IMPORT_HIERARCHY":
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
        match import_type:
            case "IMPORT_ANIMATION":
                row.label(text=T("Animation Options"), icon="ANIM_DATA")
                row = layout.row()
                row.prop(wm, "sssekai_animation_import_offset", icon="TIME")
                row.prop(wm, "sssekai_animation_always_lerp", icon="IPO_LINEAR")
                row = layout.row()
                row.prop(wm, "sssekai_animation_import_use_nla", icon="NLA")
                row.prop(
                    wm, "sssekai_animation_import_nla_always_new_track", icon="NLA"
                )
                row = layout.row()
                row.prop(wm, "sssekai_animation_import_mode", expand=True)
                row = layout.row()
                import_mode = wm.sssekai_animation_import_mode
                match import_mode:
                    case "SEKAI_MOTION":
                        if active_obj and KEY_SEKAI_CHARACTER_BODY_OBJ in active_obj:
                            row.operator(
                                SSSekaiBlenderImportSekaiCharacterMotionOperator.bl_idname
                            )
                            row = layout.row()
                        else:
                            row.label(
                                text=T(
                                    "Please select a SekaiCharacterRoot with a Body armature first"
                                )
                            )
                            row = layout.row()
                    case "SEKAI_FACE":
                        if active_obj and KEY_SEKAI_CHARACTER_FACE_OBJ in active_obj:
                            row.operator(
                                SSSekaiBlenderImportSekaiCharacterFaceMotionOperator.bl_idname
                            )
                            row = layout.row()
                        else:
                            row.label(
                                text=T(
                                    "Please select a SekaiCharacterRoot with a Face armature first"
                                )
                            )
                            row = layout.row()
                    case "SEKAI_CAMERA":
                        if active_obj and KEY_SEKAI_CAMERA_RIG in active_obj:
                            row.prop(wm, "sssekai_camera_import_is_sub_camera")
                            row = layout.row()
                            row.operator(
                                SSSekaiBlenderImportSekaiCameraAnimationOperator.bl_idname
                            )
                            row = layout.row()
                        else:
                            row.label(
                                text=T(
                                    "Please select a SekaiCameraRig with a Camera armature first"
                                )
                            )
                            row = layout.row()
                            row.label(
                                text=T(
                                    "You can create one by selecting a Camera first."
                                )
                            )
                            row = layout.row()
                            if active_obj and active_obj.type == "CAMERA":
                                row.operator(
                                    SSSekaiBlenderCreateCameraRigControllerOperator.bl_idname,
                                    icon="OUTLINER_OB_ARMATURE",
                                )
                    case "SEKAI_LIGHT":
                        row.prop(wm, "sssekai_animation_light_type", expand=True)
                        row = layout.row()
                        row.label(
                            text="NOTE: Some animation settings are enforced with this import mode"
                        )
                        row = layout.row()
                        wm.sssekai_animation_import_use_nla = True
                        wm.sssekai_animation_import_nla_always_new_track = True
                        match wm.sssekai_animation_light_type:
                            case "DIRECTIONAL":
                                row.operator(
                                    SSSekaiBlenderImportGlobalLightAnimationOperator.bl_idname
                                )
                                row = layout.row()
                            case "AMBIENT":
                                row.operator(
                                    SSSekaiBlenderImportGlobalLightAnimationOperator.bl_idname
                                )
                                row = layout.row()
                            case "CHARACTER_RIM":
                                if (
                                    active_obj
                                    and KEY_SEKAI_CHARACTER_LIGHT_OBJ in active_obj
                                ):
                                    row.operator(
                                        SSSekaiBlenderImportCharacterLightAnimationOperator.bl_idname
                                    )
                                else:
                                    row.label(
                                        text=T(
                                            "Please select a SekaiCharacterRoot first"
                                        )
                                    )
                                row = layout.row()
                            case "CHARACTER_AMBIENT":
                                if (
                                    active_obj
                                    and KEY_SEKAI_CHARACTER_LIGHT_OBJ in active_obj
                                ):
                                    row.operator(
                                        SSSekaiBlenderImportCharacterLightAnimationOperator.bl_idname
                                    )
                                else:
                                    row.label(
                                        text=T(
                                            "Please select a SekaiCharacterRoot first"
                                        )
                                    )
                                row = layout.row()
                    case "GENERIC":
                        if active_obj and KEY_HIERARCHY_BONE_PATHID in active_obj:
                            row.prop(
                                wm,
                                "sssekai_animation_use_animator",
                                icon="DECORATE_ANIMATE",
                            )
                            row = layout.row()
                            if not wm.sssekai_animation_use_animator:
                                row.prop(
                                    wm, "sssekai_animation_root_bone", icon="BONE_DATA"
                                )
                                row = layout.row()
                            row.operator(
                                SSSekaiBlenderImportHierarchyAnimationOperaotr.bl_idname
                            )
                        else:
                            row.label(
                                text=T("Please select an armature created by the addon")
                            )
                row = layout.row()
            case "IMPORT_HIERARCHY":
                row.label(text=T("Hierarchy Options"), icon="OUTLINER_OB_ARMATURE")
                row = layout.row()
                row.prop(wm, "sssekai_hierarchy_import_mode", expand=True)
                row = layout.row()
                row.label(text=T("Import Options"), icon="OPTIONS")
                row = layout.row()
                row.label(
                    text=T(
                        "NOTE: Some settings are enforced with different import modes"
                    )
                )
                row = layout.row()
                row.prop(
                    wm,
                    "sssekai_hierarchy_import_bindpose",
                    icon="OUTLINER_DATA_ARMATURE",
                )
                row.prop(
                    wm,
                    "sssekai_hierarchy_import_seperate_armatures",
                    icon="BONE_DATA",
                )
                row = layout.row()
                import_mode = wm.sssekai_hierarchy_import_mode
                match import_mode:
                    case "SEKAI_CHARACTER":
                        row.label(
                            text=T("Project SEKAI Character Options"),
                            icon="OUTLINER_OB_ARMATURE",
                        )
                        wm.sssekai_hierarchy_import_bindpose = False
                        wm.sssekai_hierarchy_import_seperate_armatures = False
                        if active_obj and KEY_HIERARCHY_BONE_PATHID in active_obj:
                            row = layout.row()
                            row.operator(
                                SSSekaiBlenderHierarchyAddSekaiRigidBodiesOperator.bl_idname,
                                icon="CONSTRAINT_BONE",
                            )
                        if not (active_obj and KEY_SEKAI_CHARACTER_ROOT in active_obj):
                            row = layout.row()
                            row.label(
                                text=T("NOTE: To import a Project SEKAI Armature")
                            )
                            row = layout.row()
                            row.label(
                                text=T(
                                    "You'll need to create an instance of SekaiCharacterRoot, or have one selected"
                                )
                            )
                            row = layout.row()
                            row.label(text=T("Click the button below to create one"))
                            row = layout.row()
                            row.operator(
                                SSSekaiBlenderCreateCharacterControllerOperator.bl_idname,
                                icon="OUTLINER_OB_ARMATURE",
                            )
                        else:
                            row = layout.row()
                            row.label(text=T("Character Height"))
                            row = layout.row()
                            row.prop(
                                active_obj,
                                '["%s"]' % KEY_SEKAI_CHARACTER_HEIGHT,
                                text=T("Character Height (in meters)"),
                            )
                            row = layout.row()
                            row.prop(
                                active_obj,
                                '["%s"]' % KEY_SEKAI_CHARACTER_FACE_OBJ,
                                text=T("Face"),
                            )
                            row.prop(
                                active_obj,
                                '["%s"]' % KEY_SEKAI_CHARACTER_BODY_OBJ,
                                text=T("Body"),
                            )
                            row = layout.row()
                            row.operator(
                                SSSekaiBlenderUtilCharaNeckAttachOperator.bl_idname,
                                icon="CONSTRAINT_BONE",
                            )
                            row.operator(
                                SSSekaiBlenderUtilCharaNeckMergeOperator.bl_idname,
                                icon="AREA_JOIN",
                            )
                            row = layout.row()
                            row.label(text=T("Mesh Type"))
                            row = layout.row()
                            row.prop(wm, "sssekai_character_type", expand=True)
                            row = layout.row()
                            row.operator(
                                SSSekaiBlenderImportHierarchyOperator.bl_idname,
                                icon="APPEND_BLEND",
                            )
                    case "SEKAI_STAGE":
                        row.label(
                            text=T("Project SEKAI Stage Options"),
                            icon="OUTLINER_OB_EMPTY",
                        )
                        row = layout.row()
                        wm.sssekai_hierarchy_import_bindpose = True
                        wm.sssekai_hierarchy_import_seperate_armatures = False
                        row.operator(
                            SSSekaiBlenderImportHierarchyOperator.bl_idname,
                            icon="APPEND_BLEND",
                        )
                    case "GENERIC":
                        row.label(text=T("Generic Options"), icon="ARMATURE_DATA")
                        row = layout.row()
                        row.prop(wm, "sssekai_generic_material_import_slot")
                        row.prop(
                            wm, "sssekai_generic_material_import_skip", icon="CANCEL"
                        )
                        row = layout.row()
                        row.operator(
                            SSSekaiBlenderImportHierarchyOperator.bl_idname,
                            icon="APPEND_BLEND",
                        )
