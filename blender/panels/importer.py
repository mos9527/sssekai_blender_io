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

from ..core.helpers import register_serachable_enum, get_enum_search_op_name
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
    SSSekaiBlenderUtilArmatureBakeIdentityPoseOperator,
    SSSekaiBlenderUtilArmatureBoneParentToWeightOperator,
)

from ..operators.sekai_rigidbody import (
    SSSekaiBlenderHierarchyAddSekaiRigidBodiesOperator,
)

from ..operators.material import SSSekaiGenericMaterialSetModeOperator

EMPTY_OPT = ("<no assest selected!>", "Not Available", "", "ERROR", 0)
EMPTY_CONTAINER = "<default>"
ALL_CONTAINER = "<all>"


def update_environment(path: str, aux_path: str):
    global sssekai_global

    if path and os.path.exists(path):
        if sssekai_global.env_path == path and sssekai_global.env_aux_path == aux_path:
            return
        logger.debug("Loading environment: %s" % path)
        UnityPy.config.SERIALIZED_FILE_PARSE_TYPETREE = False
        UnityPy.config.FALLBACK_UNITY_VERSION = sssekai_get_unity_version()
        sssekai_global.reset_env()
        sssekai_global.env = UnityPy.load(path)
        sssekai_global.env_path = path
        sssekai_global.env_aux_path = aux_path
        logger.debug("Building scene hierarchy")
        hierarchies = build_scene_hierarchy(sssekai_global.env)
        if os.path.exists(aux_path):
            logger.debug("Loading auxiliary environment: %s" % aux_path)
            sssekai_global.env.load_folder(aux_path)
        for hierarchy in hierarchies:
            root = hierarchy.root.game_object
            container = root.object_reader.container or EMPTY_CONTAINER
            sssekai_global.containers[container].hierarchies[
                hierarchy.path_id
            ] = hierarchy
        logger.debug("Updating enums")
        for reader in filter(
            lambda obj: obj.type == ClassIDType.AnimationClip,
            sssekai_global.env.objects,
        ):
            container = reader.container or EMPTY_CONTAINER
            sssekai_global.containers[container].animations[reader.path_id] = reader

        for reader in filter(
            lambda obj: obj.type == ClassIDType.Animator, sssekai_global.env.objects
        ):
            container = reader.container or EMPTY_CONTAINER
            sssekai_global.containers[container].animators[reader.path_id] = reader

        for container in sssekai_global.containers.values():
            container.update_enums()

        sssekai_global.container_enum = [
            (container, container, "", "FILE_FOLDER", index)
            for index, container in enumerate(sssekai_global.containers)
        ]
        sssekai_global.container_enum = sorted(
            sssekai_global.container_enum, key=lambda x: x[1]
        )
    else:
        sssekai_global.container_enum.clear()


def enumerate_containers(obj: bpy.types.Object, context: bpy.types.Context):
    global sssekai_global

    wm = context.window_manager
    try:
        update_environment(
            wm.sssekai_selected_assetbundle_file,
            wm.sssekai_selected_assetbundle_file_aux,
        )
    except Exception as e:
        wm.sssekai_selected_assetbundle_file = ""
        raise e
    return sssekai_global.container_enum or [EMPTY_OPT]


def enumerate_prop(container_selection_key: str, prop: str):
    global sssekai_global

    def inner(obj: bpy.types.Object, context: bpy.types.Context):
        wm = context.window_manager
        container = getattr(wm, container_selection_key)
        return getattr(sssekai_global.containers[container].enums, prop) or [EMPTY_OPT]

    return inner


register_serachable_enum(
    "sssekai_selected_hierarchy_container",
    name=T("Container"),
    description=T("Selected Container"),
    items=enumerate_containers,
)
register_serachable_enum(
    "sssekai_selected_hierarchy",
    name=T("Hierarchy"),
    description=T("Selected Hierarchy"),
    items=enumerate_prop("sssekai_selected_hierarchy_container", "hierarchies"),
)
register_serachable_enum(
    "sssekai_selected_animation_container",
    name=T("Container"),
    description=T("Selected Container"),
    items=enumerate_containers,
)
register_serachable_enum(
    "sssekai_selected_animation",
    name=T("Animation"),
    description=T("Selected Animation"),
    items=enumerate_prop("sssekai_selected_animation_container", "animations"),
)
register_serachable_enum(
    "sssekai_selected_animator_container",
    name=T("Container"),
    description=T("Selected Container"),
    items=enumerate_containers,
)
register_serachable_enum(
    "sssekai_selected_animator",
    name=T("Animator"),
    description=T("Selected Animator"),
    items=enumerate_prop("sssekai_selected_animator_container", "animators"),
)
register_wm_props(
    sssekai_selected_assetbundle_file=StringProperty(
        name=T("Directory"),
        description=T(
            "Where the asset bundle(s) are located. Every AssetBundle in this directory will be loaded (if possible)"
        ),
        subtype="DIR_PATH",
    ),
    sssekai_selected_assetbundle_file_aux=StringProperty(
        name=T("Aux. Directory"),
        description=T(
            "Where the auxiliary asset bundle(s) are located. Useful for assets with dependencies that's stored elsewhere\n"
            "NOTE: These files will NOT show up in the Asset Browser, but will be used by the addon if needed."
        ),
        subtype="DIR_PATH",
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
            "Use the selected Animator to import the Animation, instead of building the relations in runtime."
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
    sssekai_animation_import_use_scene_fps=BoolProperty(
        name=T("Use Scene FPS"),
        description=T(
            "Use a custom FPS value for the imported animation, instead of the FPS of the imported animation itself"
        ),
        default=True,
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
            "Correct the hierarchy to match the bind pose of the Skinned Meshes that might be imported. ONLY use this if the pose is incorrect"
        ),
        default=False,
    ),
    sssekai_hierarchy_import_seperate_armatures=BoolProperty(
        name=T("Seperate Armatures"),
        description=T(
            "Import Skinned Meshes into different armatures. MUST be used IF your hierarchy has multiple Skinned Meshes and has different bind poses. ONLY use this if the pose is incorrect"
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
                T("(Project SEKAI) Import the selected animation as a character motion"),
                "ARMATURE_DATA",
                1,
            ),
            (
                "SEKAI_FACE",
                T("Sekai Face"),
                T("(Project SEKAI) Import the selected animation as a character facial (Shapekey) animation"),
                "SHAPEKEY_DATA",
                2,
            ),
            (
                "SEKAI_CAMERA",
                T("Sekai Camera"),
                T("(Project SEKAI) Import the selected animation as a camera animation"),
                "CAMERA_DATA",
                3,
            ),
            (
                "SEKAI_LIGHT",
                T("Sekai Light"),
                T("(Project SEKAI) Import the selected animation as a light animation"),
                "LIGHT_DATA",
                4,
            ),
            (
                "GENERIC",
                T("Generic"),
                T(
                    "Import the selected animation as generic animation data applied on any imported Hierarchy"
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
    sssekai_generic_material_import_mode=EnumProperty(
        name=T("Generic Material Mode"),
        description=T("Method to import the selected material"),
        items=[
            (
                "BASIC_TOON",
                T("Toon"),
                T(
                    "Import the materials as a basic toon material w/ simple NPR techniques"
                ),
                "MATERIAL",
                1,
            ),
            (
                "UNITY_PBR_STANDARD",
                T("PBR Std."),
                T(
                    "Import the materials as a Unity Universal Render Pipeline (URP) Standard Material"
                ),
                "MATERIAL",
                2,
            ),
            (
                "BASIC",
                T("Basic"),
                T(
                    "Import the materials with only the diffuse map"
                ),
                "MATERIAL",
                3,
            ),
            (
                "EMISSIVE",
                T("Emissive"),
                T("Import the materials as an Emissive material, ignoring lighting"),
                "MATERIAL",
                4,
            ),
            (
                "COLORADD",
                T("Color Add"),
                T("Import the materials effectively as Color Add overlays"),
                "MATERIAL",
                5,
            ),
            ("SKIP", T("Skip"), T("Skip importing the material"), "CANCEL", 6),
            (
                "CUSTOM",
                T("Custom"),
                T("Use a custom material node group.\nNOTE: Check the Wiki on how to make custom node groups for any assets"),
                "MODIFIER",
                7,
            ),
        ],
    ),
    sssekai_generic_material_import_mode_custom_group=StringProperty(
        name=T("Custom Material Node Group"),
        description=T("Name of the custom material node group to use"),
        default="",
    ),
    sssekai_sekai_material_mode=EnumProperty(
        name=T("Material Mode"),
        description=T("Method to import the selected material"),
        items=[
            (
                "SEKAI",
                T("SEKAI Auto"),
                T(
                    "Import the selected material as a Project SEKAI Material with auto setup.\n" \
                    "NOTE: Can be VERY slow due to Nodetree + Driver issues in Blender"
                ),
                "MATERIAL",
                1,
            ),
            (
                "GENERIC",
                T("Generic"),
                T("Import the selected material as a generic material"),
                "MATERIAL",
                2,
            ),
        ],
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
        row.prop(wm, "sssekai_selected_assetbundle_file_aux", icon="FILE_FOLDER")
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
                row.operator(
                    get_enum_search_op_name("sssekai_selected_animation_container"),
                    icon="VIEWZOOM",
                )
                row = layout.row()
                row.prop(wm, "sssekai_selected_animation")
                row.operator(
                    get_enum_search_op_name("sssekai_selected_animation"),
                    icon="VIEWZOOM",
                )
                row = layout.row()
                row.prop(
                    wm,
                    "sssekai_selected_animator_container",
                    text=T("Container"),
                    icon="DECORATE_ANIMATE",
                )
                row.operator(
                    get_enum_search_op_name("sssekai_selected_animator_container"),
                    icon="VIEWZOOM",
                )
                row = layout.row()
                row.prop(wm, "sssekai_selected_animator")
                row.operator(
                    get_enum_search_op_name("sssekai_selected_animator"),
                    icon="VIEWZOOM",
                )
                row = layout.row()
            case "IMPORT_HIERARCHY":
                row.prop(
                    wm,
                    "sssekai_selected_hierarchy_container",
                    text=T("Container"),
                    icon="OUTLINER_OB_ARMATURE",
                )
                row.operator(
                    get_enum_search_op_name("sssekai_selected_hierarchy_container"),
                    icon="VIEWZOOM",
                )
                row = layout.row()
                row.prop(wm, "sssekai_selected_hierarchy")
                row.operator(
                    get_enum_search_op_name("sssekai_selected_hierarchy"),
                    icon="VIEWZOOM",
                )
                row = layout.row()
        row.label(text=T("Import Options"), icon="OPTIONS")
        row = layout.row()
        match import_type:
            case "IMPORT_ANIMATION":
                row.label(text=T("Animation Options"), icon="ANIM_DATA")
                row = layout.row()
                row.prop(wm, "sssekai_animation_import_use_scene_fps", icon="TIME")
                if wm.sssekai_animation_import_use_scene_fps:
                    row.prop(bpy.context.scene.render, "fps", text=T("Scene FPS"))
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

                def __draw_generic_material_options(row):
                    row.prop(wm, "sssekai_generic_material_import_mode", expand=True)
                    row = layout.row()
                    if wm.sssekai_generic_material_import_mode == "CUSTOM":
                        row.prop(
                            wm, "sssekai_generic_material_import_mode_custom_group"
                        )
                        row = layout.row()
                    row.operator(SSSekaiGenericMaterialSetModeOperator.bl_idname)
                    row = layout.row()

                match import_mode:
                    case "SEKAI_CHARACTER":
                        row.label(
                            text=T("Project SEKAI Character Options"),
                            icon="OUTLINER_OB_ARMATURE",
                        )
                        row = layout.row()
                        row.label(text=T("Material Options"))
                        row = layout.row()
                        row.prop(wm, "sssekai_sekai_material_mode", expand=True)
                        if wm.sssekai_sekai_material_mode == "GENERIC":
                            row = layout.row()
                            __draw_generic_material_options(row)
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
                                icon="CONSTRAINT",
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
                        row.label(text=T("Material Options"))
                        row = layout.row()
                        row.prop(wm, "sssekai_sekai_material_mode", expand=True)
                        if wm.sssekai_sekai_material_mode == "GENERIC":
                            row = layout.row()
                            __draw_generic_material_options(row)
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
                        row.label(text=T("Material Options"))
                        row = layout.row()
                        wm.sssekai_sekai_material_mode = "GENERIC"
                        __draw_generic_material_options(row)
                        row = layout.row()
                        row.operator(
                            SSSekaiBlenderImportHierarchyOperator.bl_idname,
                            icon="APPEND_BLEND",
                        )
                        row = layout.row()
                        row.label(text=T("Common Fixes"))
                        row = layout.row()
                        row.operator(
                            SSSekaiBlenderUtilArmatureBakeIdentityPoseOperator.bl_idname,
                            icon="CONSTRAINT_BONE",
                        )
                        row = layout.row()
                        row.operator(
                            SSSekaiBlenderUtilArmatureBoneParentToWeightOperator.bl_idname,
                            icon="GROUP_VERTEX",
                        )

        row = layout.row()
        row.label(text=T("Debug Options"), icon="SCRIPT")
        row = layout.row()
        row.prop(wm, "sssekai_debug_link_shaders", icon="SCRIPT", expand=True)
