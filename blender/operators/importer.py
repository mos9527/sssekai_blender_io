from bpy.app.translations import pgettext as T
import bpy, bpy.utils.previews, bpy_extras

from typing import List, Tuple
from UnityPy.classes import PPtr
from sssekai.unity.AnimationClip import (
    TransformType,
    read_animation,
)

from UnityPy.classes import (
    Mesh,
    Material,
    SkinnedMeshRenderer,
    MeshFilter,
    MeshRenderer,
)

from ..core.consts import *
from ..core.helpers import create_empty
from ..core.helpers import (
    ensure_sssekai_shader_blend,
    retrive_action,
    apply_action,
)

from ..core.asset import (
    import_fallback_material,
    import_sekai_eye_material,
    import_sekai_eyelight_material,
    import_sekai_character_material,
    import_sekai_character_face_sdf_material,
    import_sekai_stage_lightmap_material,
    import_sekai_stage_color_add_material,
    import_hierarchy_as_armature,
    import_mesh_data,
)
from ..core.animation import (
    load_armature_animation,
    load_camera_animation,
    load_keyshape_animation,
    import_articulation_animation,
)
from ..core.types import Hierarchy
from .. import register_class, register_wm_props, logger
from .. import sssekai_global


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
        root[KEY_SEKAI_CHARACTER_ROOT_STUB] = True
        root[KEY_SEKAI_CHARACTER_HEIGHT] = wm.sssekai_character_height

        rim_controller = bpy.data.objects["SekaiCharaRimLight"].copy()
        rim_controller.parent = root
        bpy.context.collection.objects.link(rim_controller)

        bpy.context.view_layer.objects.active = root
        return {"FINISHED"}


@register_class
class SSSekaiBlenderImportHierarchyOperator(bpy.types.Operator):
    bl_idname = "sssekai.import_op"
    bl_label = T("Import Hierarchy")
    bl_description = T("Import the selected Hierarchy from the selected asset bundle")

    # Here's where the magic happens^^
    def execute(self, context):
        global sssekai_global
        wm = context.window_manager
        ensure_sssekai_shader_blend()
        active_object = context.active_object

        container = wm.sssekai_selected_hierarchy_container
        selected = wm.sssekai_selected_hierarchy
        selected: bpy.types.EnumProperty
        hierarchy = sssekai_global.cotainers[container].hierarchies[int(selected)]
        logger.debug("Loading selected hierarchy: %s" % hierarchy.name)
        # Import the scene as an Armature
        armature, armature_obj = import_hierarchy_as_armature(hierarchy)
        # Import Skinned Meshes and Static Meshes
        # - Just like with Unity scene graph, everything is going to have a parent
        # - Once expressed as a Blender Armature, the direct translation of that is a Bone Parent
        #   Hence we'd always need an Armature to parent the meshes to
        # - Skinning works in Blender by matching bone names with vertex groups
        #   In that sense we only need to import the mesh and assign the modifier since parenting is already done
        imported_objects: List[Tuple[bpy.types.Object, List[PPtr[Material]], Mesh]] = []
        for path_id, node in hierarchy.nodes.items():
            game_object = node.game_object
            if game_object.m_SkinnedMeshRenderer:
                renderer = game_object.m_SkinnedMeshRenderer.read()
                renderer: SkinnedMeshRenderer
                mesh = renderer.m_Mesh.read()
                bone_names = [
                    hierarchy.nodes[pptr.m_PathID].name for pptr in renderer.m_Bones
                ]
                mesh_data, mesh_obj = import_mesh_data(
                    game_object.m_Name, mesh, bone_names
                )
                mesh_obj.parent = armature_obj
                mesh_obj.parent_type = "BONE"
                mesh_obj.parent_bone = node.name
                logger.debug("Imported Mesh (skinned) %s" % game_object.m_Name)
                imported_objects.append((mesh_obj, renderer.m_Materials, mesh))

            if game_object.m_MeshFilter:
                renderer = game_object.m_MeshRenderer.read()
                renderer: MeshRenderer
                mesh_filter = game_object.m_MeshFilter.read()
                mesh_filter: MeshFilter
                mesh = mesh_filter.m_Mesh.read()
                mesh_data, mesh_obj = import_mesh_data(game_object.m_Name, mesh)
                mesh_obj.parent = armature_obj
                mesh_obj.parent_type = "BONE"
                mesh_obj.parent_bone = node.name
                logger.debug("Imported Mesh (static) %s" % game_object.m_Name)
                imported_objects.append((mesh_obj, renderer.m_Materials, mesh))

        # Import Materials
        # - This is done in a seperate procedure since there'd be some permuations depending on
        # the user's preference (i.e. sssekai_hierarchy_import_mode)
        texture_cache = dict()
        material_cache = dict()

        # By principle this should be matched by their respective Shaders
        # But since there's no guarantee that the PathID would always match across versions therefore we'd pattern-match
        # the name and the properties to determine the correct importer
        def import_material_sekai_character(material: Material):
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
                    head_bone_target="Head",
                )
            rimlight = next(
                filter(
                    lambda o: o.name.startswith("SekaiCharaRimLight"),
                    active_object.children_recursive,
                ),
                None,
            )
            assert (
                rimlight
            ), "Rim Light controller not found on the active object's hierachy before Import!"
            return import_sekai_character_material(
                name, material, texture_cache, rimlight
            )

        def import_material_sekai_stage(material: Material):
            envs = dict(material.m_SavedProperties.m_TexEnvs)
            floats = dict(material.m_SavedProperties.m_Floats)
            name = material.m_Name
            if "_LightMapTex" in envs:
                if floats.get("_DstBlend", 0) == 10:  # StageLightMapReflection
                    return import_sekai_stage_lightmap_material(
                        name, material, texture_cache, has_reflection=True
                    )
                else:  # StageLightMap
                    return import_sekai_stage_lightmap_material(
                        name, material, texture_cache, has_reflection=False
                    )
            else:
                if floats.get("_DstBlend", 0) == 10:  # ColorMapAdd
                    return import_sekai_stage_color_add_material(
                        name, material, texture_cache
                    )
            # XXX: Some other permutations still exist
            return import_sekai_stage_lightmap_material(name, material, texture_cache)

        def import_material_fallback(material: Material):
            name = material.m_Name
            return import_fallback_material(name, material, texture_cache)

        for obj, materials, mesh in imported_objects:
            for ppmat in materials:
                if ppmat:
                    material: Material = ppmat.read()
                    if material.object_reader.path_id in material_cache:
                        imported = material_cache[material.object_reader.path_id]
                        obj.data.materials.append(imported)
                        continue
                    match wm.sssekai_hierarchy_import_mode:
                        case "SEKAI_CHARACTER":
                            imported = import_material_sekai_character(material)
                        case "SEKAI_STAGE":
                            imported = import_material_sekai_stage(material)
                        case "GENERIC":
                            imported = import_material_fallback(material)
                    obj.data.materials.append(imported)
                    material_cache[material.object_reader.path_id] = imported
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

        armature_obj.parent = active_object
        return {"FINISHED"}


class SSSekaiBlenderImportHierarchyAnimationOperaotr(bpy.types.Operator):
    bl_idname = "sssekai.import_hierarchy_animation_op"
    bl_label = T("Import Hierarchy Animation")
    bl_description = T(
        "Import the selected Animation into the selected Armature (Hierarchy)"
    )

    def execute(self, context):
        pass
