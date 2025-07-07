from bpy.app.translations import pgettext as T
import bpy, bpy.utils.previews, bpy_extras
import math, json, traceback

from typing import List, Tuple
from UnityPy.classes import PPtr

from UnityPy.classes import (
    Mesh,
    Material,
    SkinnedMeshRenderer,
    MeshFilter,
    MeshRenderer,
)
from sssekai.unity.AnimationClip import read_animation

from ..core.consts import *
from ..core.helpers import create_empty
from ..core.helpers import (
    ensure_sssekai_shader_blend,
    create_action,
    apply_action,
    editbone_children_recursive,
    armature_editbone_children_recursive,
    set_obj_bone_parent,
)

from ..core.asset import (
    import_all_material_inputs,
    make_material_value_node,
    import_sekai_eye_material,
    import_sekai_eyelight_material,
    import_sekai_character_material,
    import_sekai_character_face_sdf_material,
    import_sekai_stage_lightmap_material,
    import_sekai_stage_color_add_material,
    import_scene_hierarchy,
    import_mesh_data,
)
from ..core.animation import (
    load_armature_animation,
    load_sekai_camera_animation,
    load_sekai_keyshape_animation,
    load_sekai_ambient_light_animation,
    load_sekai_directional_light_animation,
    load_sekai_character_ambient_light_animation,
    load_sekai_character_rim_light_animation,
)
from ..core.types import Hierarchy
from ..core.math import blVector, blEuler
from .. import register_class, register_wm_props, logger
from .. import sssekai_global
from ..operators.material import (
    SSSekaiGenericMaterialSetModeOperator,
    set_generic_material_nodegroup,
)
from .utils import crc32
from tqdm import tqdm


@register_class
class SSSekaiBlenderUpdateCharacterControllerBodyPositionDriverOperator(
    bpy.types.Operator
):
    bl_idname = "sssekai.update_character_controller_body_position_driver_op"
    bl_label = T("Update Character Controller Driver")
    bl_description = T(
        "Update the driver for the Body object of the Character Controller"
    )

    def execute(self, context):
        wm = context.window_manager
        ensure_sssekai_shader_blend()
        active_obj = context.active_object
        assert active_obj and KEY_SEKAI_CHARACTER_ROOT in active_obj
        body = active_obj[KEY_SEKAI_CHARACTER_BODY_OBJ]
        assert body, "Body not found"
        body: bpy.types.Object
        bpy.context.view_layer.objects.active = body
        bpy.ops.object.mode_set(mode="POSE")
        bone = body.pose.bones.get("Position", None)
        if bone:
            bone.driver_remove("scale")
            for ch in bone.driver_add("scale"):
                ch.driver.type = "SCRIPTED"
                var = ch.driver.variables.new()
                var.name = "height"
                var.type = "SINGLE_PROP"
                var.targets[0].id = active_obj
                var.targets[0].data_path = f'["{KEY_SEKAI_CHARACTER_HEIGHT}"]'
                ch.driver.expression = "height"
        bpy.context.view_layer.objects.active = active_obj
        bpy.ops.object.mode_set(mode="OBJECT")
        return {"FINISHED"}


@register_class
class SSSekaiBlenderCreateCharacterControllerOperator(bpy.types.Operator):
    bl_idname = "sssekai.create_character_controller_op"
    bl_label = T("Create Character Controller")
    bl_description = T(
        "Create an Empty object with a Rim Light Controller that one can import Sekai Character armatures to"
    )

    def execute(self, context):
        wm = context.window_manager
        ensure_sssekai_shader_blend()

        root = create_empty("SekaiCharacterRoot")
        root[KEY_SEKAI_CHARACTER_ROOT] = True
        root[KEY_SEKAI_CHARACTER_HEIGHT] = wm.sssekai_character_height
        root[KEY_SEKAI_CHARACTER_BODY_OBJ] = None
        root[KEY_SEKAI_CHARACTER_FACE_OBJ] = None
        rim_controller = bpy.data.objects["SekaiCharaRimLight"].copy()
        rim_controller.parent = root
        root[KEY_SEKAI_CHARACTER_LIGHT_OBJ] = rim_controller
        bpy.context.collection.objects.link(rim_controller)

        bpy.context.view_layer.objects.active = root
        return {"FINISHED"}


@register_class
class SSSekaiBlenderCreateCameraRigControllerOperator(bpy.types.Operator):
    bl_idname = "sssekai.create_camera_rig_controller_op"
    bl_label = T("Create Camera Rig Controller")
    bl_description = T(
        "Create an Empty object with a Camera Rig Controller that one can import Sekai Camera animations to"
    )

    def execute(self, context):
        wm = context.window_manager
        ensure_sssekai_shader_blend()
        camera = context.active_object
        assert camera.type == "CAMERA", "Active object must be a Camera"

        rig = create_empty("SekaiCameraRig")
        rig[KEY_SEKAI_CAMERA_RIG] = "<marker>"
        rig.rotation_mode = "XZY"
        # NOTE: Not YXZ since there's a 90 degree Y offset at the root of the in game camera
        # Can be done in anim import stage but that messes up the slopes. Eulers are weird...
        rig.scale.y = 60  # Arbitrary default - FOV
        rig[KEY_SEKAI_CAMERA_RIG_SENSOR_HEIGHT] = (
            24  # Arbitrary default - Sensor Height (mm)
        )
        camera.parent = rig
        camera.data.lens_unit = "MILLIMETERS"
        camera.location = blVector((0, 0, 0))
        camera.rotation_euler = blEuler((math.radians(90), 0, math.radians(180)))
        camera.rotation_mode = "YXZ"
        camera.scale = blVector((1, 1, 1))
        camera.data.sensor_fit = "VERTICAL"
        camera.data.dof.aperture_fstop = 6.5

        height = camera.data.driver_add("sensor_height")
        height.driver.type = "SCRIPTED"
        var = height.driver.variables.new()
        var.name = "height"
        var.type = "SINGLE_PROP"
        var.targets[0].id = rig
        var.targets[0].data_path = f'["{KEY_SEKAI_CAMERA_RIG_SENSOR_HEIGHT}"]'
        height.driver.expression = "height"

        # Driver for FOV
        driver = camera.data.driver_add("lens")
        driver.driver.type = "SCRIPTED"

        var_sensor = driver.driver.variables.new()
        var_sensor.name = "sensor_height"
        var_sensor.type = "SINGLE_PROP"
        var_sensor.targets[0].id = rig
        var_sensor.targets[0].data_path = f'["{KEY_SEKAI_CAMERA_RIG_SENSOR_HEIGHT}"]'

        var_scale = driver.driver.variables.new()
        var_scale.name = "fov"
        var_scale.type = "TRANSFORMS"
        var_scale.targets[0].id = rig
        var_scale.targets[0].transform_space = "WORLD_SPACE"
        var_scale.targets[0].transform_type = "SCALE_Z"

        driver.driver.expression = "sensor_height / (2 * tan(radians(fov * 100) / 2))"

        # Driver for Focal Distance
        camera.data.dof.use_dof = True
        driver = camera.data.driver_add("dof.focus_distance")
        driver.driver.type = "SCRIPTED"

        var_distance = driver.driver.variables.new()
        var_distance.name = "distance"
        var_distance.type = "SINGLE_PROP"
        var_distance.targets[0].id = rig
        var_distance.targets[0].data_path = "delta_scale.x"

        driver.driver.expression = "distance"

        bpy.context.view_layer.objects.active = rig
        return {"FINISHED"}


@register_class
class SSSekaiBlenderImportHierarchyOperator(bpy.types.Operator):
    bl_idname = "sssekai.import_op"
    bl_label = T("Import Hierarchy")
    bl_description = T("Import the selected Hierarchy from the selected asset bundle")

    def execute(self, context):
        global sssekai_global
        wm = context.window_manager
        ensure_sssekai_shader_blend()
        active_obj = context.active_object

        container = wm.sssekai_selected_hierarchy_container
        selected = wm.sssekai_selected_hierarchy
        selected: bpy.types.EnumProperty
        hierarchy = sssekai_global.containers[container].hierarchies[int(selected)]
        logger.debug("Loading selected hierarchy: %s" % hierarchy.name)
        # Import the scene as an Armature
        scene = import_scene_hierarchy(
            hierarchy,
            wm.sssekai_hierarchy_import_bindpose,
            wm.sssekai_hierarchy_import_seperate_armatures,
        )
        if wm.sssekai_hierarchy_import_mode == "SEKAI_CHARACTER":
            assert (
                KEY_SEKAI_CHARACTER_ROOT in active_obj
            ), "Active object is not a Character Controller"
            match wm.sssekai_character_type:
                case "HEAD":
                    assert not active_obj[
                        KEY_SEKAI_CHARACTER_FACE_OBJ
                    ], "Face already imported"
                    active_obj[KEY_SEKAI_CHARACTER_FACE_OBJ] = scene[0][0]
                case "BODY":
                    assert not active_obj[
                        KEY_SEKAI_CHARACTER_BODY_OBJ
                    ], "Body already imported"
                    active_obj[KEY_SEKAI_CHARACTER_BODY_OBJ] = scene[0][0]
                    bpy.context.view_layer.objects.active = active_obj
                    bpy.ops.sssekai.update_character_controller_body_position_driver_op()
        # Import Skinned Meshes and Static Meshes
        # - Just like with Unity scene graph, everything is going to have a parent
        # - Once expressed as a Blender Armature, the direct translation of that is a Bone Parent
        #   Hence we'd always need an Armature to parent the meshes to
        # - Skinning works in Blender by matching bone names with vertex groups
        #   In that sense we only need to import the mesh and assign the modifier since parenting is already done
        imported_objects: List[Tuple[bpy.types.Object, List[PPtr[Material]], Mesh]] = []
        # Skinned Meshes
        sm_mapping = {
            sm_pathid: (armature_obj, bone_names)
            for armature_obj, bone_names, sm_pathid in scene
        }
        for node in tqdm(hierarchy.nodes.values(), desc="Importing Skinned Meshes"):
            game_object = node.game_object
            if game_object.m_SkinnedMeshRenderer:
                # bool ModelImporter::ImportSkinnedMesh
                try:
                    sm = game_object.m_SkinnedMeshRenderer.read()
                    sm: SkinnedMeshRenderer
                    if not sm.m_Mesh:
                        continue
                    mesh = sm.m_Mesh.read()
                    bone_names = [
                        hierarchy.nodes[pptr.m_PathID].name for pptr in sm.m_Bones
                    ]
                    mesh_data, mesh_obj = import_mesh_data(
                        game_object.m_Name, mesh, bone_names
                    )
                    armature_obj, _mapping = sm_mapping.get(
                        sm.object_reader.path_id, (None, None)
                    )
                    if not armature_obj:
                        armature_obj, _mapping = sm_mapping.get(0, (None, None))
                        assert armature_obj, "no armature found"
                    # Already in parent space
                    mesh_obj.parent = armature_obj
                    if wm.sssekai_hierarchy_import_seperate_armatures:
                        # Otherwise armature only has an identity transform on its object
                        # Will introduce issues with the mesh's parent space so we set it manually
                        armature_bone = armature_obj.data.bones[0].name
                        set_obj_bone_parent(mesh_obj, armature_bone, armature_obj)
                        bpy.context.view_layer.update()
                        # Keep the transform but parent to the armature w/o the bone
                        M_world = mesh_obj.matrix_world.copy()
                        mesh_obj.parent = armature_obj
                        mesh_obj.parent_type = "OBJECT"
                        mesh_obj.matrix_world = M_world
                    # Add an armature modifier
                    mesh_obj.modifiers.new("Armature", "ARMATURE").object = armature_obj
                    imported_objects.append((mesh_obj, sm.m_Materials, mesh))
                except Exception as e:
                    traceback.print_exc()
                    logger.error(
                        "Failed to import Skinned Mesh at %s: %s. Skipping."
                        % (game_object.m_Name, str(e))
                    )
        # Static Meshes
        for armature_obj, nodes, _ in tqdm(scene, desc="Importing Static Meshes"):
            if wm.sssekai_hierarchy_import_mode == "SEKAI_CHARACTER":
                armature_obj.parent = active_obj
            for path_id, bone_name in nodes.items():
                node = hierarchy.nodes[path_id]
                game_object = node.game_object
                if game_object.m_MeshFilter:
                    try:
                        m = game_object.m_MeshRenderer.read()
                        m: MeshRenderer
                        mf = game_object.m_MeshFilter.read()
                        mf: MeshFilter
                        if not mf.m_Mesh:
                            continue
                        mesh = mf.m_Mesh.read()
                        mesh_data, mesh_obj = import_mesh_data(game_object.m_Name, mesh)
                        set_obj_bone_parent(mesh_obj, bone_name, armature_obj)
                        imported_objects.append((mesh_obj, m.m_Materials, mesh))
                    except Exception as e:
                        traceback.print_exc()
                        logger.error(
                            "Failed to import Static Mesh at %s: %s. Skipping."
                            % (bone_name, str(e))
                        )
        # Import Materials
        # - This is done in a seperate procedure since there'd be some permuations depending on
        # the user's preference (i.e. sssekai_hierarchy_import_mode)
        texture_cache = dict()
        material_cache = dict()

        # By principle this should be matched by their respective Shaders
        # But since there's no guarantee that the PathID would always match across versions therefore we'd pattern-match
        # the name and the properties to determine the correct importer
        def import_material_sekai_character(material: Material):
            controller = next(
                filter(
                    lambda o: o.name.startswith("SekaiCharaRimLight"),
                    active_obj.children_recursive,
                ),
                None,
            )
            envs = dict(material.m_SavedProperties.m_TexEnvs)
            floats = dict(material.m_SavedProperties.m_Floats)
            name = material.m_Name
            if "_eye" in name:  # CharacterEyeBase
                return import_sekai_eye_material(name, material, texture_cache)
            if "_ehl_" in name:  # CharacterEyeLight
                return import_sekai_eyelight_material(name, material, texture_cache)
            if "_FaceShadowTex" in envs and floats.get(
                "_UseFaceSDF", 0
            ):  # CharacterToonV3
                return import_sekai_character_face_sdf_material(
                    name,
                    material,
                    texture_cache,
                    armature_obj=armature_obj,
                    rim_light_controller=controller,
                    head_bone_target="Head",
                )

            assert (
                controller
            ), "Rim Light controller not found on the active object's hierachy before Import!"
            return import_sekai_character_material(
                name, material, texture_cache, controller
            )

        def import_material_sekai_stage(material: Material):
            envs = dict(material.m_SavedProperties.m_TexEnvs)
            floats = dict(material.m_SavedProperties.m_Floats)
            name = material.m_Name
            if "_LightMapTex" in envs:
                if "Reflection_" in name:
                    return import_sekai_stage_lightmap_material(
                        name, material, texture_cache, has_reflection=True
                    )
                else:
                    return import_sekai_stage_lightmap_material(
                        name, material, texture_cache, has_reflection=False
                    )
            elif "_Color_Add" in name:
                return import_sekai_stage_color_add_material(
                    name, material, texture_cache
                )
            else:
                # XXX: Some other permutations still exist
                return import_all_material_inputs(name, material, texture_cache)

        def import_material_fallback(material: Material, mode_override: str = ""):
            name = material.m_Name
            mat = import_all_material_inputs(name, material, texture_cache)
            set_generic_material_nodegroup(
                mat, mode_override or wm.sssekai_generic_material_import_mode
            )
            return mat

        def import_material(material: Material):
            imported = None
            name = material.m_Name
            envs = dict(material.m_SavedProperties.m_TexEnvs)
            floats = dict(material.m_SavedProperties.m_Floats)
            match wm.sssekai_hierarchy_import_mode:
                case "SEKAI_CHARACTER":
                    if wm.sssekai_sekai_material_mode == "GENERIC":
                        # Some hardcoded modes for this kind of blending
                        if "_ehl_" in name:
                            imported = import_material_fallback(
                                material, mode_override="COLORADD"
                            )
                        elif "_FaceShadowTex" in envs and floats.get("_UseFaceSDF", 0):
                            imported = import_material_fallback(
                                material, mode_override="EMISSIVE"
                            )
                        else:
                            imported = import_material_fallback(material)
                    else:
                        imported = import_material_sekai_character(material)
                case "SEKAI_STAGE":
                    if wm.sssekai_sekai_material_mode == "GENERIC":
                        if "_Color_Add" in name:
                            imported = import_material_fallback(
                                material, mode_override="COLORADD"
                            )
                        else:
                            imported = import_material_fallback(material)
                    else:
                        imported = import_material_sekai_stage(material)
                case "GENERIC":
                    if wm.sssekai_generic_material_import_mode == "SKIP":
                        return None
                    imported = import_material_fallback(material)
            return imported

        for obj, materials, mesh in tqdm(imported_objects, desc="Importing Materials"):
            for ppmat in materials:
                if ppmat:
                    try:
                        material: Material = ppmat.read()
                        imported = None
                        if material.object_reader.path_id in material_cache:
                            imported = material_cache[material.object_reader.path_id]
                            obj.data.materials.append(imported)
                            continue
                        imported = import_material(material)
                        if imported:
                            obj.data.materials.append(imported)
                            material_cache[material.object_reader.path_id] = imported
                    except Exception as e:
                        traceback.print_exc()
                        logger.error(
                            "Failed to import Material %s: %s. Skipping."
                            % (material.m_Name, str(e))
                        )
            # Set material indices afterwards
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.mode_set(mode="OBJECT")
            for index, sub in enumerate(mesh.m_SubMeshes):
                start, count = sub.firstVertex, sub.vertexCount
                for i in range(start, start + count):
                    obj.data.vertices[i].select = True
                bpy.ops.object.mode_set(mode="EDIT")
                bpy.context.object.active_material_index = index
                bpy.ops.object.material_slot_assign()
                bpy.ops.mesh.select_all(action="DESELECT")
                bpy.ops.object.mode_set(mode="OBJECT")  # Deselects all vertices

        # Restore
        if active_obj:
            bpy.context.view_layer.objects.active = active_obj
            bpy.ops.object.mode_set(mode="OBJECT")
        return {"FINISHED"}


@register_class
class SSSekaiBlenderImportHierarchyAnimationOperaotr(bpy.types.Operator):
    bl_idname = "sssekai.import_hierarchy_animation_op"
    bl_label = T("Import Hierarchy Animation")
    bl_description = T(
        "Import the selected Animation into the selected Armature (Hierarchy). ATTENTION: Split armatures won't work yet!"
    )

    def execute(self, context):
        global sssekai_global
        wm = context.window_manager
        ensure_sssekai_shader_blend()
        active_obj = context.active_object
        assert active_obj.type == "ARMATURE", "Active object must be an Armature"
        assert (
            KEY_HIERARCHY_BONE_PATHID in active_obj
        ), "Active object must be a Hierarchy imported by the addon itself"
        # Build TOS
        # XXX: Does TOS mean To String? Unity uses this nomenclature internally
        tos_leaf = dict()
        if wm.sssekai_animation_use_animator:
            animator = sssekai_global.containers[
                wm.sssekai_selected_animator_container
            ].animators[int(wm.sssekai_selected_animator)]
            animator = animator.read()
            avatar = animator.m_Avatar.read()
            # Only take the leaf bone names for the same reason as stated in `import_hierarchy_as_armature`
            tos_leaf = {k: v.split("/")[-1] for k, v in avatar.m_TOS}
            if len(set(tos_leaf.values())) != len(tos_leaf):
                logger.warning(
                    "Animator has multiple bones with the same name. Expect issues"
                )
        else:
            # Again, this is only accessable in edit mode
            bpy.ops.object.mode_set(mode="EDIT")
            dfngen = None
            if wm.sssekai_animation_root_bone:
                ebone = active_obj.data.edit_bones.get(
                    wm.sssekai_animation_root_bone, None
                )
                assert ebone, "Selected root bone not found in the Armature"
                dfngen = editbone_children_recursive(ebone)
            else:
                dfngen = armature_editbone_children_recursive(active_obj.data)
            for parent, child, depth in dfngen:
                if (
                    not wm.sssekai_animation_root_bone
                    and KEY_HIERARCHY_BONE_ROOT in child
                ):
                    # Stub. Ignore this when a root bone is selected
                    continue
                pa_path = tos_leaf.get(parent.name, "") if parent else ""
                if pa_path:
                    pa_path += "/"
                leaf = child[KEY_HIERARCHY_BONE_NAME]
                tos_leaf[leaf] = pa_path + leaf
            tos_leaf = {crc32(v): k for k, v in tos_leaf.items()}
            bpy.ops.object.mode_set(mode="OBJECT")
        # Load Animation
        anim = sssekai_global.containers[
            wm.sssekai_selected_animation_container
        ].animations[int(wm.sssekai_selected_animation)]
        logger.info("Loading Animation %s" % anim.m_Name)
        anim = anim.read()
        anim = read_animation(anim)
        bpy.context.scene.render.fps = int(anim.SampleRate)
        logger.info("Sample Rate: %d FPS" % anim.SampleRate)
        action = load_armature_animation(
            anim.Name, anim, active_obj, tos_leaf, wm.sssekai_animation_always_lerp
        )
        # Set frame range
        bpy.context.scene.frame_end = max(
            bpy.context.scene.frame_end, int(action.curve_frame_range[1])
        )
        if bpy.context.scene.rigidbody_world:
            bpy.context.scene.rigidbody_world.point_cache.frame_end = max(
                bpy.context.scene.rigidbody_world.point_cache.frame_end,
                bpy.context.scene.frame_end,
            )
        apply_action(
            active_obj,
            action,
            wm.sssekai_animation_import_use_nla,
            wm.sssekai_animation_import_nla_always_new_track,
        )
        self.report({"INFO"}, T("Hierarchy Animation %s Imported") % anim.Name)
        # Restore
        bpy.context.view_layer.objects.active = active_obj
        bpy.ops.object.mode_set(mode="OBJECT")
        return {"FINISHED"}


@register_class
class SSSekaiBlenderImportSekaiCharacterMotionOperator(bpy.types.Operator):
    bl_idname = "sssekai.import_sekai_character_motion_op"
    bl_label = T("Import Sekai Character Motion")
    bl_description = T("Import the selected Sekai Character Motion")

    def execute(self, context):
        global sssekai_global
        wm = context.window_manager
        ensure_sssekai_shader_blend()
        active_obj = context.active_object
        assert (
            active_obj and KEY_SEKAI_CHARACTER_ROOT in active_obj
        ), "Active object must be a Character Controller"
        body = active_obj[KEY_SEKAI_CHARACTER_BODY_OBJ]
        assert body, "Body not found"
        # Set active object to the body
        bpy.context.view_layer.objects.active = body
        bpy.ops.sssekai.import_hierarchy_animation_op()
        # Restore
        bpy.context.view_layer.objects.active = active_obj
        bpy.ops.object.mode_set(mode="OBJECT")
        # Drivers get removed post animation import so fix it here too
        bpy.ops.sssekai.update_character_controller_body_position_driver_op()
        return {"FINISHED"}


@register_class
class SSSekaiBlenderImportSekaiCharacterFaceMotionOperator(bpy.types.Operator):
    bl_idname = "sssekai.import_sekai_character_face_motion_op"
    bl_label = T("Import Sekai Character Face Motion")
    bl_description = T("Import the selected Sekai Character Face Motion")

    def execute(self, context):
        global sssekai_global
        wm = context.window_manager
        ensure_sssekai_shader_blend()
        active_obj = context.active_object
        assert (
            active_obj and KEY_SEKAI_CHARACTER_ROOT in active_obj
        ), "Active object must be a Character Controller"
        face = active_obj[KEY_SEKAI_CHARACTER_FACE_OBJ]
        face: bpy.types.Object
        assert face, "Face not found"
        # Find the shapekey name hashtable
        # hash is simply crc32("blendShape." + Shape key name). This is baked in.
        morphs = list(
            filter(
                lambda obj: obj.type == "MESH" and KEY_SHAPEKEY_HASH_TABEL in obj.data,
                face.children_recursive,
            )
        )
        assert morphs, "No meshes with shapekey found"
        assert (
            len(morphs) == 1
        ), "Multiple meshes with shapekeys found. Please keep only one"
        # XXX: Generalize this for generic Unity stuff
        morph = morphs[0]
        crc_table = json.loads(morph.data[KEY_SHAPEKEY_HASH_TABEL])
        # Set active object to the face
        bpy.context.view_layer.objects.active = face
        # Load Animation
        anim = sssekai_global.containers[
            wm.sssekai_selected_animation_container
        ].animations[int(wm.sssekai_selected_animation)]
        logger.info("Loading Animation %s" % anim.m_Name)
        anim = anim.read()
        anim = read_animation(anim)
        action = load_sekai_keyshape_animation(
            anim.Name, anim, crc_table, wm.sssekai_animation_always_lerp
        )
        apply_action(
            morph.data.shape_keys,
            action,
            wm.sssekai_animation_import_use_nla,
            wm.sssekai_animation_import_nla_always_new_track,
        )
        self.report({"INFO"}, T("Sekai Shapekey Animation %s Imported") % anim.Name)
        bpy.context.view_layer.objects.active = active_obj
        bpy.ops.object.mode_set(mode="OBJECT")
        return {"FINISHED"}


@register_class
class SSSekaiBlenderImportSekaiCameraAnimationOperator(bpy.types.Operator):
    bl_idname = "sssekai.import_sekai_camera_animation_op"
    bl_label = T("Import Sekai Camera Animation")
    bl_description = T("Import the selected Sekai Camera Animation")

    def execute(self, context):
        global sssekai_global
        wm = context.window_manager
        ensure_sssekai_shader_blend()
        active_obj = context.active_object
        assert KEY_SEKAI_CAMERA_RIG in active_obj, "Active object must be a Camera Rig"
        # Load Animation
        anim = sssekai_global.containers[
            wm.sssekai_selected_animation_container
        ].animations[int(wm.sssekai_selected_animation)]
        logger.info("Loading Animation %s" % anim.m_Name)
        anim = anim.read()
        anim = read_animation(anim)
        bpy.context.scene.render.fps = int(anim.SampleRate)
        logger.info("Sample Rate: %d FPS" % anim.SampleRate)
        action = load_sekai_camera_animation(
            anim.Name,
            anim,
            wm.sssekai_animation_always_lerp,
            wm.sssekai_camera_import_is_sub_camera,
        )
        # Set frame range
        bpy.context.scene.frame_end = max(
            bpy.context.scene.frame_end, int(action.curve_frame_range[1])
        )
        apply_action(
            active_obj,
            action,
            wm.sssekai_animation_import_use_nla,
            wm.sssekai_animation_import_nla_always_new_track,
        )
        self.report({"INFO"}, T("Sekai Camera Animation %s Imported") % anim.Name)
        bpy.context.view_layer.objects.active = active_obj
        bpy.ops.object.mode_set(mode="OBJECT")
        return {"FINISHED"}


@register_class
class SSSekaiBlenderImportGlobalLightAnimationOperator(bpy.types.Operator):
    bl_idname = "sssekai.import_global_light_animation_op"
    bl_label = T("Import Global Light Animation")
    bl_description = T("Import the selected Light Animation to the Global Light")

    def execute(self, context):
        global sssekai_global
        wm = context.window_manager
        ensure_sssekai_shader_blend()
        # Load Animation
        anim = sssekai_global.containers[
            wm.sssekai_selected_animation_container
        ].animations[int(wm.sssekai_selected_animation)]
        logger.info("Loading Animation %s" % anim.m_Name)
        anim = anim.read()
        anim = read_animation(anim)
        bpy.context.scene.render.fps = int(anim.SampleRate)
        logger.info("Sample Rate: %d FPS" % anim.SampleRate)
        global_obj = bpy.data.objects["SekaiShaderGlobals"]
        dir_light_obj = bpy.data.objects["SekaiDirectionalLight"]
        match wm.sssekai_animation_light_type:
            case "AMBIENT":
                action = load_sekai_ambient_light_animation(
                    anim.Name, anim, wm.sssekai_animation_always_lerp
                )
                apply_action(
                    global_obj,
                    action,
                    wm.sssekai_animation_import_use_nla,
                    wm.sssekai_animation_import_nla_always_new_track,
                )
            case "DIRECTIONAL":
                global_action, directional_light_action = (
                    load_sekai_directional_light_animation(
                        anim.Name, anim, wm.sssekai_animation_always_lerp
                    )
                )
                apply_action(
                    global_obj,
                    global_action,
                    wm.sssekai_animation_import_use_nla,
                    wm.sssekai_animation_import_nla_always_new_track,
                )
                apply_action(
                    dir_light_obj,
                    directional_light_action,
                    wm.sssekai_animation_import_use_nla,
                    wm.sssekai_animation_import_nla_always_new_track,
                )

        return {"FINISHED"}


@register_class
class SSSekaiBlenderImportCharacterLightAnimationOperator(bpy.types.Operator):
    bl_idname = "sssekai.import_character_light_animation_op"
    bl_label = T("Import Character Light Animation")
    bl_description = T("Import the selected Light Animation to the Character Light")

    def execute(self, context):
        global sssekai_global
        wm = context.window_manager
        ensure_sssekai_shader_blend()
        active_obj = context.active_object
        assert (
            active_obj and KEY_SEKAI_CHARACTER_ROOT in active_obj
        ), "Active object must be a Character Controller"
        controler = active_obj[KEY_SEKAI_CHARACTER_LIGHT_OBJ]
        # Load Animation
        anim = sssekai_global.containers[
            wm.sssekai_selected_animation_container
        ].animations[int(wm.sssekai_selected_animation)]
        logger.info("Loading Animation %s" % anim.m_Name)
        anim = anim.read()
        anim = read_animation(anim)
        bpy.context.scene.render.fps = int(anim.SampleRate)
        logger.info("Sample Rate: %d FPS" % anim.SampleRate)
        match wm.sssekai_animation_light_type:
            case "CHARACTER_RIM":
                action = load_sekai_character_rim_light_animation(
                    anim.Name, anim, wm.sssekai_animation_always_lerp
                )
                apply_action(
                    controler,
                    action,
                    wm.sssekai_animation_import_use_nla,
                    wm.sssekai_animation_import_nla_always_new_track,
                )
            case "CHARACTER_AMBIENT":
                action = load_sekai_character_ambient_light_animation(
                    anim.Name, anim, wm.sssekai_animation_always_lerp
                )
                apply_action(
                    controler,
                    action,
                    wm.sssekai_animation_import_use_nla,
                    wm.sssekai_animation_import_nla_always_new_track,
                )
        return {"FINISHED"}
