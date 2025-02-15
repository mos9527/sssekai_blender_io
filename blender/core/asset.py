import bpy, bmesh
import json, math
import tempfile, copy
from typing import Dict, Tuple, List, Set
from UnityPy.enums import ClassIDType
from UnityPy.helpers.MeshHelper import MeshHandler
from UnityPy.classes import (
    ColorRGBA,
    Texture2D,
    Material,
    Mesh,
    Transform,
    UnityTexEnv,
    SkinnedMeshRenderer,
)
from UnityPy import Environment
from .types import Hierarchy, HierarchyNode
from .utils import crc32, pprint
from .helpers import (
    create_empty,
    rgba_to_rgb_tuple,
    auto_connect_shader_nodes_by_name,
    auto_setup_shader_node_driver,
    apply_pose_matrix,
    set_obj_bone_parent,
)
from .math import (
    swizzle_matrix,
    swizzle_vector,
    swizzle_quaternion,
    swizzle_vector_scale,
    swizzle_vector3,
    blVector,
    blMatrix,
    uMatrix4x4,
    unity_to_blender,
)
from .consts import *
from .. import logger


def build_scene_hierarchy(env: Environment) -> List[Hierarchy]:
    """Build the scene hierarchy from the UnityPy Environment

    Formally, this function locates all the root Transform objects
    in the Environment (all scenes would then be included) and builds the hierarchy from there.

    With Unity's Scene Graph (Hierarchy), the root of the hierarchy belongs to the scene itself.
    This in effect eliminates the distinction between scene(s) and would allow a one-to-one
    representation of the scene in Blender's View Layer.
    """
    transform_roots = []
    for obj in filter(lambda obj: obj.type == ClassIDType.Transform, env.objects):
        data = obj.read()
        if hasattr(data, "m_Children") and not data.m_Father.path_id:
            transform_roots.append(data)
    hierarchies = []
    for transform in transform_roots:
        hierarchy = Hierarchy(transform.m_GameObject.read().m_Name)

        def dfs(root: Transform, parent: HierarchyNode = None):
            game_object = root.m_GameObject.read()
            name = game_object.m_Name
            node = HierarchyNode(
                name,
                root.object_reader.path_id,
                root.m_LocalPosition,
                root.m_LocalRotation,
                root.m_LocalScale,
                # ---
                parent=parent,
                game_object=game_object,
            )
            hierarchy.nodes[node.path_id] = node
            if not parent:
                # Effectively the bone for `transform`
                hierarchy.root = node
            else:
                parent.children.append(node)
                hierarchy.parents[node.path_id] = parent.path_id
            for child in root.m_Children:
                dfs(child.read(), node)

        dfs(transform)
        hierarchies.append(hierarchy)

    hierarchies = sorted(hierarchies, key=lambda x: x.name)
    return hierarchies


def import_scene_hierarchy(
    hierarchy: Hierarchy,
    use_bindpose: bool = False,
    seperate_armatures: bool = True,
) -> List[Tuple[bpy.types.Object, Dict[int, str]]]:
    """Imports Scene Hierarchy data into Blender as an Armature object

    Args:
        arma (Armature): Armature as genereated by previous steps
        name (str): Armature Object name
        use_bindpose (bool): Whether to use the bindpose for the bones
        seperate_armatures (bool): Whether to create a new armature for each Skinned Mesh Renderer

    Note:
        In Unity Bindpose is generated in the asset import process (e.g. FBX)
        which may or may not be correct.
        * For example, in Project SEKAI's case bindpose for Face armatures are incorrect
            and is adjusted in post (Game) with a Transform parent which fixes the axis alignment.
            This is possibly due to a misconfigured FBX export on the dev's side.
            With that in mind, only use `use_bindpose` when:
        * The imported mesh does not align with the armature
            Could happen if the Hierarchy has some pose defined for it.
            With this enabled - the armature would be adjusted to the bindpose
            And the defined pose will be applied in Blender's Pose Mode (Pose Space)
        * Do note, however, that *any* animation imports overrides Blender's Pose Space which may
            or may not make this adjustment irrelavant.

    Returns:
        List[Tuple[bpy.types.Object (Armature Object), Dict[int, str] (Nodes belonging to the Armature's bones)]]
    """
    results = list()

    def bindpose_of(sm: SkinnedMeshRenderer):
        mesh = sm.m_Mesh.read()
        bindpose = {p.m_PathID: mesh.m_BindPose[i] for i, p in enumerate(sm.m_Bones)}
        return bindpose

    def build_armature(
        root_bone: HierarchyNode,
        bindpose: Dict[int, uMatrix4x4] = None,
        bone_ids: Set[int] = None,
        visited=set(),
    ) -> Tuple[bpy.types.Object, Dict[int, str]]:
        # Reserve bone_id nodes's names since they'd be used for vertex groups
        reserve_bonenames = dict()
        if bone_ids:
            for path_id in bone_ids:
                bone = hierarchy.nodes[path_id]
                reserve_bonenames[bone.name] = path_id
        # No scaling is ever applied here since otherwise scaling becomes
        # erroneouslly commutative which is *never* the case in any DCC software you'd use
        root_bone.update_global_transforms(scale=False)

        # Make an Armature with the hierarchy
        armature = bpy.data.armatures.new(root_bone.name)
        armature.display_type = "OCTAHEDRAL"
        armature.relation_line_position = "HEAD"
        obj = bpy.data.objects.new(armature.name, armature)
        bpy.context.collection.objects.link(obj)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode="EDIT")

        ebones = dict()
        pose_matrix = dict()
        pose_scales = dict()
        bone_names = dict()
        for parent, child, _ in root_bone.children_recursive(visited=visited):
            if child.name in reserve_bonenames:
                if child.path_id in bone_ids:
                    ebone = armature.edit_bones.new(child.name)
                else:
                    ebone = armature.edit_bones.new(child.name + "_Duped")
            else:
                ebone = armature.edit_bones.new(child.name)
            if not parent:
                ebone[KEY_HIERARCHY_BONE_ROOT] = True
            ebone[KEY_HIERARCHY_BONE_PATHID] = str(child.path_id)
            ebone[KEY_HIERARCHY_BONE_NAME] = str(child.name)
            ebone.use_local_location = True
            ebone.use_relative_parent = False
            ebone.use_connect = False
            ebone.use_deform = True
            # Cache the pose matrix for later
            # ebone name may not be unique in the hierarchy and importing it will
            # automatically add .001, .002, etc. suffixes to the bone name
            pose_scales[ebone.name] = child.scale
            bone_names[child.path_id] = ebone.name
            # Use bindposes for the subtree of the root bone
            # and apply the actual pose in Pose Bones later
            pose_matrix[ebone.name] = child.global_transform
            if bindpose:
                # Needs correction
                M_edit = child.global_transform
                M_bind = bindpose.get(child.path_id, None)
                if not M_bind:
                    logger.debug("No bindpose found for %s" % child.name)
                else:
                    M_bind = swizzle_matrix(M_bind)
                    # In armature space it's basically the inverse of the bindpose
                    # Identity = M_bind * M_pose
                    M_pose = M_bind.inverted()
                    M_pose = unity_to_blender(M_pose)
                    M_parent = root_bone.global_transform
                    # XXX: Assume no scaling in M_pose
                    M_edit = M_parent @ M_pose
            else:
                M_edit = child.global_transform
            # Treat the joints as extremely small bones
            # The same as https://github.com/KhronosGroup/glTF-Blender-IO/blob/2debd75ace303f3a3b00a43e9d7a9507af32f194/addons/io_scene_gltf2/blender/imp/gltf2_blender_node.py#L198
            # TODO: Alternative shapes for bones
            # TODO: Better bone size heuristic
            ebone.head = M_edit @ blVector((0, 0, 0))
            ebone.tail = M_edit @ blVector((0, 1, 0))
            ebone.length = DEFAULT_BONE_SIZE
            ebone.align_roll(M_edit @ blVector((0, 0, 1)) - ebone.head)
            if parent:
                ebone.parent = ebones.get(parent.path_id, None)
                if not ebone.parent:
                    logger.warning(
                        "Parent bone %s not found for %s" % (parent.name, child.name)
                    )
            ebones[child.path_id] = ebone
        bpy.ops.object.mode_set(mode="OBJECT")
        obj[KEY_HIERARCHY_BONE_PATHID] = str(root_bone.path_id)
        obj[KEY_HIERARCHY_BONE_NAME] = str(root_bone.name)
        # Pose space adjustment
        # Make Scene Hierachy transform the Pose Bones so the final pose is correct
        if pose_matrix:
            # https://docs.blender.org/api/current/info_gotcha.html#stale-data
            bpy.context.view_layer.update()
            apply_pose_matrix(obj, pose_matrix, edit_mode=False, clear_pose=False)
        # Scale adjustment
        bpy.context.view_layer.update()
        bpy.ops.object.mode_set(mode="POSE")
        for bone, scale in pose_scales.items():
            pbone = obj.pose.bones.get(bone, None)
            pbone.scale = swizzle_vector_scale(scale)
        return obj, bone_names

    sm_roots = list()
    for path_id, node in hierarchy.nodes.items():
        if node.game_object and node.game_object.m_SkinnedMeshRenderer:
            sm: SkinnedMeshRenderer = node.game_object.m_SkinnedMeshRenderer.read()
            root = sm.m_RootBone.path_id
            sm_roots.append((root, sm))
    sm_roots.sort(key=lambda x: x[0])

    if seperate_armatures:
        # Collect Skinned Meshes in the hierarchy
        # Their root bone's subtree is guaranteed to have AT LEAST one-to-one name to vertex group
        # mappings.
        # We'll cull these from the graph and import them separately
        sm_culled = {path_id for path_id, sm in sm_roots}
        bone_names_all = dict()
        root, bone_names = build_armature(hierarchy.root, visited=sm_culled)
        bone_names_all |= {k: (root, v) for k, v in bone_names.items()}
        results.append((root, bone_names))
        for sm_root, sm in sm_roots:
            child = hierarchy.nodes[sm_root]
            bones = {p.path_id for p in sm.m_Bones}
            if use_bindpose:
                bindpose = bindpose_of(sm)
                obj, child_bone_names = build_armature(
                    child,
                    bindpose=bindpose,
                    bone_ids=bones,
                    visited=sm_culled - {sm_root},
                )
            else:
                obj, child_bone_names = build_armature(
                    child, bone_ids=bones, visited=sm_culled - {sm_root}
                )
            results.append((obj, child_bone_names))
            bone_names_all |= {k: (obj, v) for k, v in child_bone_names.items()}
        for i, (obj, _) in enumerate(results[1:]):
            sm_root, sm = sm_roots[i]
            child = hierarchy.nodes[sm_root]
            bone_parent = hierarchy.parents.get(sm_root, None)
            pa_root, pa_name = bone_names_all.get(bone_parent, (None, None))
            if not pa_name:
                logger.warning("Parent not found for %s" % child.name)
            set_obj_bone_parent(obj, pa_name, pa_root)
    else:
        # Import the entire hierarchy as a single armature
        # Fails when:
        # - The root bones are reused for *different* bindposes
        # - The root bones are reused for *different* meshes with different weights
        # Otherwise for a single skinned mesh with a single bindpose this is fine
        bone_ids = set()
        for sm_root, sm in sm_roots:
            bone_ids |= {p.path_id for p in sm.m_Bones}
        if use_bindpose:
            # XXX: CHECK NOT ENFORCED
            # Sanity check - only allow this when the bindposes are the same
            bindpose = dict()
            for i in range(0, len(sm_roots) - 1):
                cur, next = sm_roots[i], sm_roots[i + 1]                
                if cur[0] == next[0]:
                    # Check matrices
                    lhs, rhs = bindpose_of(cur[1]), bindpose_of(next[1])
                    if lhs != rhs:
                        logger.warning(
                            "Bindposes are not the same. Seperation of armatures may be required!"
                        )
                bindpose |= bindpose_of(cur[1])
                bindpose |= bindpose_of(next[1])
            obj, bone_names = build_armature(
                hierarchy.root, bindpose=bindpose, bone_ids=bone_ids
            )
        else:
            obj, bone_names = build_armature(hierarchy.root, bone_ids=bone_ids)
        results.append((obj, bone_names))

    return results


def import_mesh_data(
    name: str,
    data: Mesh,
    vertex_groups: List[str] = None,
):
    """Imports the mesh data into blender.

    Takes care of the following:
    - Vertices (Position + Normal) and indices (Trig Faces)
    - UV Map

    Additonally, for Skinned meshes:
    - Bone Indices + Bone Weights
    - Blend Shape / Shape Keys

    Args:
        name (str): Name for the created Blender object
        data (Mesh): Source UnityPy Mesh data
        vertex_groups (List[str], optional): List of bone names for vertex groups, must be in order. Defaults to None.

    Returns:
        Tuple[bpy.types.Mesh, bpy.types.Object]: Created mesh and its parent object
    """
    mesh = bpy.data.meshes.new(name=data.m_Name)
    handler = MeshHandler(data)
    handler.process()

    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bm = bmesh.new()
    # Bone Indices + Bone Weights
    deform_layer = None
    if vertex_groups:
        for boneName in vertex_groups:
            obj.vertex_groups.new(name=boneName)
        deform_layer = bm.verts.layers.deform.new()
    # Vertex position & vertex normal (pre-assign)
    for vtx in range(0, handler.m_VertexCount):
        vert = bm.verts.new(swizzle_vector3(*handler.m_Vertices[vtx]))
        # Blender always generates normals automatically
        # Custom normals needs a bit more work
        # See below for normals_split... calls
        if handler.m_Normals:
            vert.normal = swizzle_vector3(*handler.m_Normals[vtx])
        if deform_layer:
            boneIndex = handler.m_BoneIndices[vtx]
            if handler.m_BoneWeights:
                boneWeight = handler.m_BoneWeights[vtx]
            else:
                # Default to 1 otherwise the bone would not make any effect
                # XXX: This is purly emprical to handle some edge cases.
                boneWeight = [1.0 / len(boneIndex)] * len(boneIndex)
            for i in range(len(boneIndex)):
                vertex_group_index = boneIndex[i]
                if not vertex_group_index in vert[deform_layer]:
                    vert[deform_layer][vertex_group_index] = boneWeight[i]
                vert[deform_layer][vertex_group_index] = max(
                    vert[deform_layer][vertex_group_index], boneWeight[i]
                )
    bm.verts.ensure_lookup_table()
    # Indices
    trigs = handler.get_triangles()
    for submesh in trigs:
        for idx, trig in enumerate(submesh):
            try:
                face = bm.faces.new(
                    [bm.verts[i] for i in reversed(trig)]
                )  # UV rewinding
                face.smooth = True
            except ValueError as e:
                logger.warning("Invalid face index %d (%s) - discarded." % (idx, e))
    bm.to_mesh(mesh)

    # UV Map
    def try_add_uv_map(name, set_active=False):
        src_layer = getattr(handler, "m_" + name)
        if src_layer:
            uv_layer = mesh.uv_layers.new()
            uv_layer.name = name
            if set_active:
                mesh.uv_layers.active = uv_layer
            for face in mesh.polygons:
                for vtx, loop in zip(face.vertices, face.loop_indices):
                    uv_layer.data[loop].uv = src_layer[vtx]

    try_add_uv_map("UV0", set_active=True)
    for i in range(1, 8):
        # Unity supports up to 8 UV maps
        try_add_uv_map("UV" + str(i))

    # Vertex Color
    if handler.m_Colors:
        vertex_color = mesh.color_attributes.new(
            name="Vertex Color", type="FLOAT_COLOR", domain="POINT"
        )
        for vtx in range(0, handler.m_VertexCount):
            vertex_color.data[vtx].color = handler.m_Colors[vtx]
    # Assign vertex normals
    try:
        mesh.create_normals_split()
        mesh.use_auto_smooth = True
    except:
        pass  # 4.2.0 Alpha removed these somehow
    normals = [(0, 0, 0) for l in mesh.loops]
    for i, loop in enumerate(mesh.loops):
        normal = bm.verts[loop.vertex_index].normal
        normal.normalize()
        normals[i] = normal
    mesh.normals_split_custom_set(normals)
    # Blend Shape / Shape Keys
    if data.m_Shapes.channels:
        obj.shape_key_add(name="Basis")
        keyshape_hash_tbl = dict()
        for channel in data.m_Shapes.channels:
            shape_key = obj.shape_key_add(name=channel.name)
            keyshape_hash_tbl[channel.nameHash] = channel.name
            for frameIndex in range(
                channel.frameIndex, channel.frameIndex + channel.frameCount
            ):
                # fullWeight = mesh_data.m_Shapes.fullWeights[frameIndex]
                shape = data.m_Shapes.shapes[frameIndex]
                for morphedVtxIndex in range(
                    shape.firstVertex, shape.firstVertex + shape.vertexCount
                ):
                    morpedVtx = data.m_Shapes.vertices[morphedVtxIndex]
                    targetVtx: bpy.types.ShapeKeyPoint = shape_key.data[morpedVtx.index]
                    targetVtx.co += swizzle_vector(morpedVtx.vertex)
        # Like boneHash, do the same thing with blend shapes
        mesh[KEY_SHAPEKEY_HASH_TABEL] = json.dumps(
            keyshape_hash_tbl, ensure_ascii=False
        )
    bm.free()
    return mesh, obj


def import_texture(name: str, data: Texture2D):
    """Imports Texture2D assets into blender.

    Args:
        name (str): asset name
        data (Texture2D): source texture

    Note:
        An intermediate PNG file is created to import the texture into Blender.

    Returns:
        bpy.types.Image: Created image
    """
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp:
        image = data.image
        image.save(temp)
        temp.close()
        img = bpy.data.images.load(temp.name, check_existing=True)
        img.name = name
        img.pack()
        logger.debug("Packed Texture %s" % name)
        temp.delete = True
    return img


def make_material_texture_node(
    material: bpy.types.Material,
    ppTexture: UnityTexEnv,
    texture_cache: dict = None,
    uv_layer: str = "UV0",
    uv_remap_override_node: bpy.types.Node = None,
    uv_remap_postprocess_node: bpy.types.Node = None,
):
    image = None
    try:
        texture: Texture2D = ppTexture.m_Texture.read()
        if texture_cache:
            if not texture.m_Name in texture_cache:
                texture_cache[texture.m_Name] = import_texture(texture.m_Name, texture)
            image = texture_cache[texture.m_Name]
        else:
            image = import_texture(texture.m_Name, texture)
    except Exception as e:
        logger.error("Failed to load texture - %s. Discarding." % e)
        return None
    uvMap = material.node_tree.nodes.new("ShaderNodeUVMap")
    uvMap.uv_map = uv_layer
    if uv_remap_override_node:
        uvRemap = uv_remap_override_node
    else:
        uvRemap = material.node_tree.nodes.new("ShaderNodeMapping")
        uvRemap.inputs[1].default_value[0] = ppTexture.m_Offset.x
        uvRemap.inputs[1].default_value[1] = ppTexture.m_Offset.y
        uvRemap.inputs[3].default_value[0] = ppTexture.m_Scale.x
        uvRemap.inputs[3].default_value[1] = ppTexture.m_Scale.y
    texNode = material.node_tree.nodes.new("ShaderNodeTexImage")
    texNode.image = image
    material.node_tree.links.new(uvMap.outputs["UV"], uvRemap.inputs[0])
    if uv_remap_postprocess_node:
        material.node_tree.links.new(
            uvRemap.outputs[0], uv_remap_postprocess_node.inputs[0]
        )
        material.node_tree.links.new(
            uv_remap_postprocess_node.outputs[0], texNode.inputs["Vector"]
        )
    else:
        material.node_tree.links.new(uvRemap.outputs[0], texNode.inputs["Vector"])
    return texNode


def import_fallback_material(
    name: str, data: Material, texture_cache=None, slot_name: str = "_MainTex", **kwargs
):
    """Imports Material assets into blender.
    This is a generic material importer that only imports all texture maps
    with the nth_slot as the input to a Principled BSDF shader's Base Color (Diffuse) and an Alpha input

    Args:
        name (str): material name
        data (Material): UnityPy Material
        slot_name (str, optional): Texture slot to import.

    Returns:
        bpy.types.Material: Created material
    """
    textures = dict(data.m_SavedProperties.m_TexEnvs)
    material = bpy.data.materials["SekaiDefaultFallbackMaterial"].copy()
    material.name = name
    sekaiShader = material.node_tree.nodes["SekaiDefaultFallbackShader"]

    def link_tex(tex: bpy.types.Node):
        material.node_tree.links.new(
            tex.outputs["Color"],
            sekaiShader.inputs["Color"],
        )
        material.node_tree.links.new(tex.outputs["Alpha"], sekaiShader.inputs["Alpha"])

    logger.debug("Material %s" % name)
    imported = dict()
    for i, (env_name, env) in enumerate(textures.items()):
        logger.debug("- Tex#%2d: %s" % (i, env_name))
        tex = make_material_texture_node(material, env, texture_cache)
        if tex:
            tex.label = env_name
            imported[env_name] = tex
    if slot_name in imported:
        link_tex(imported[slot_name])
    else:
        logger.warning("Slot %s not found" % slot_name)
    return material


# region Sekai Specific
def import_sekai_eyelight_material(
    name: str, data: Material, texture_cache=None, **kwargs
):
    """Imports Material assets for V2 Mesh Eye Highlight into blender.

    Args:
        name (str): material name
        data (Material): UnityPy Material

    Returns:
        bpy.types.Material: Created material
    """
    textures = dict(data.m_SavedProperties.m_TexEnvs)
    material = bpy.data.materials["SekaiShaderEyelightMaterial"].copy()
    material.name = name
    sekaiShader = material.node_tree.nodes["SekaiEyelightShader"]
    if "_MainTex" in textures:
        mainTex = make_material_texture_node(
            material,
            textures["_MainTex"],
            texture_cache,
            "UV0",
            None,
            material.node_tree.nodes["SekaiEyelightShaderDistortion"],
        )
        if mainTex:
            material.node_tree.links.new(
                mainTex.outputs["Color"], sekaiShader.inputs["Sekai C"]
            )
    return material


def import_sekai_eye_material(name: str, data: Material, texture_cache=None, **kwargs):
    """Imports Material assets for V2 Mesh Eye into blender.

    Args:
        name (str): material name
        data (Material): UnityPy Material

    Returns:
        bpy.types.Material: Created material
    """
    textures = dict(data.m_SavedProperties.m_TexEnvs)
    material = bpy.data.materials["SekaiShaderEyeMaterial"].copy()
    material.name = name
    sekaiShader = material.node_tree.nodes["SekaiEyeShader"]
    if "_MainTex" in textures:
        mainTex = make_material_texture_node(
            material, textures["_MainTex"], texture_cache
        )
        if mainTex:
            material.node_tree.links.new(
                mainTex.outputs["Color"], sekaiShader.inputs["Sekai C"]
            )
    return material


def import_sekai_character_material(
    name: str, data: Material, texture_cache=None, rim_light_controller=None, **kwargs
):
    """Imports Material assets for Characters into blender.

    Args:
        name (str): material name
        data (Material): UnityPy Material

    Returns:
        bpy.types.Material: Created material
    """
    textures = dict(data.m_SavedProperties.m_TexEnvs)
    material = bpy.data.materials["SekaiShaderCharaMaterial"].copy()
    material.name = name
    sekaiShader = material.node_tree.nodes["SekaiCharaShader"]
    if "_MainTex" in textures:
        mainTex = make_material_texture_node(
            material, textures["_MainTex"], texture_cache
        )
        if mainTex:
            material.node_tree.links.new(
                mainTex.outputs["Color"], sekaiShader.inputs["Sekai C"]
            )
    if "_ShadowTex" in textures:
        shadowTex = make_material_texture_node(
            material, textures["_ShadowTex"], texture_cache
        )
        if shadowTex:
            material.node_tree.links.new(
                shadowTex.outputs["Color"], sekaiShader.inputs["Sekai S"]
            )
    if "_ValueTex" in textures:
        valueTex = make_material_texture_node(
            material, textures["_ValueTex"], texture_cache
        )
        if valueTex:
            material.node_tree.links.new(
                valueTex.outputs["Color"], sekaiShader.inputs["Sekai H"]
            )
            material.node_tree.links.new(
                valueTex.outputs["Alpha"], sekaiShader.inputs["Sekai H Alpha"]
            )
    properties = dict(data.m_SavedProperties.m_Floats)
    sekaiShader.inputs["Specular Power"].default_value = (
        1 if properties.get("_SpecularPower", 1) > 0 else 0
    )
    sekaiShader.inputs["Rim Threshold"].default_value = properties.get(
        "_SpecularStrength", 0
    )
    properties = dict(data.m_SavedProperties.m_Colors)
    sekaiShader.inputs["Skin Color Default"].default_value = rgba_to_rgb_tuple(
        properties.get("_SkinColorDefault", ColorRGBA(0, 0, 0, 0))
    )
    sekaiShader.inputs["Skin Color 1"].default_value = rgba_to_rgb_tuple(
        properties.get("_Shadow1SkinColor", ColorRGBA(0, 0, 0, 0))
    )
    sekaiShader.inputs["Skin Color 2"].default_value = rgba_to_rgb_tuple(
        properties.get("_Shadow2SkinColor", ColorRGBA(0, 0, 0, 0))
    )

    if rim_light_controller:
        rimController = material.node_tree.nodes.new("ShaderNodeGroup")
        rimController.node_tree = bpy.data.node_groups["SekaiShaderRimDriver"].copy()
        auto_setup_shader_node_driver(rimController.node_tree, rim_light_controller)
        auto_connect_shader_nodes_by_name(
            material.node_tree, rimController, sekaiShader
        )
    else:
        logger.warning(
            "Trying to import character material without Rim Light Controller. This is probably not what you want."
        )
    return material


def import_sekai_character_face_sdf_material(
    name: str,
    data: Material,
    texture_cache=None,
    armature_obj=None,
    head_bone_target=None,
    rim_light_controller=None,
    **kwargs,
):
    """Imports Material assets for V2 Face SDF into blender.

    Args:
        name (str): material name
        data (Material): UnityPy Material

    Returns:
        bpy.types.Material: Created material
    """
    textures = dict(data.m_SavedProperties.m_TexEnvs)
    material = bpy.data.materials["SekaiShaderCharaFaceSDFMaterial"].copy()
    material.name = name
    sekaiShader = material.node_tree.nodes["SekaiShaderCharaFaceSDF"]
    if "_MainTex" in textures:
        mainTex = make_material_texture_node(
            material, textures["_MainTex"], texture_cache
        )
        if mainTex:
            material.node_tree.links.new(
                mainTex.outputs["Color"], sekaiShader.inputs["Sekai C"]
            )
    if "_ShadowTex" in textures:
        shadowTex = make_material_texture_node(
            material, textures["_ShadowTex"], texture_cache
        )
        if shadowTex:
            material.node_tree.links.new(
                shadowTex.outputs["Color"], sekaiShader.inputs["Sekai S"]
            )

    if armature_obj and head_bone_target:
        boneDriver = material.node_tree.nodes.new("ShaderNodeGroup")
        boneDriver.node_tree = bpy.data.node_groups["SekaiBoneBasisDriver"].copy()
        auto_setup_shader_node_driver(
            boneDriver.node_tree, armature_obj, head_bone_target
        )
        auto_connect_shader_nodes_by_name(
            material.node_tree,
            boneDriver,
            material.node_tree.nodes["SekaiShaderCharaFaceSDFHelper"],
        )
        if "_FaceShadowTex" in textures:
            faceShadowTex = make_material_texture_node(
                material,
                textures["_FaceShadowTex"],
                texture_cache,
                "UV1",
                None,
                material.node_tree.nodes["SekaiShaderTextureHelper"],
            )
            if faceShadowTex:
                material.node_tree.links.new(
                    faceShadowTex.outputs["Color"], sekaiShader.inputs["Sekai SDF"]
                )
    else:
        logger.warning(
            "Face SDF material imported without bone target. Face shadows will NOT work"
        )
    if rim_light_controller:
        rimController = material.node_tree.nodes.new("ShaderNodeGroup")
        rimController.node_tree = bpy.data.node_groups["SekaiShaderRimDriver"].copy()
        auto_setup_shader_node_driver(rimController.node_tree, rim_light_controller)
        auto_connect_shader_nodes_by_name(
            material.node_tree, rimController, sekaiShader
        )
    else:
        logger.warning(
            "Trying to import character material without Rim Light Controller. This is probably not what you want."
        )
    return material


def import_sekai_stage_lightmap_material(
    name: str, data: Material, texture_cache=None, has_reflection=False, **kwargs
):
    """Imports Material assets for stage (w/ baked lightmap) into blender.

    Args:
        name (str): material name
        data (Material): UnityPy Material

    Returns:
        bpy.types.Material: Created material
    """
    textures = dict(data.m_SavedProperties.m_TexEnvs)
    if not has_reflection:
        material = bpy.data.materials["SekaiShaderStageLightmapMaterial"].copy()
        sekaiShader = material.node_tree.nodes["SekaiStageLightmapShader"]
    else:
        material = bpy.data.materials[
            "SekaiShaderStageLightmapReflectionMaterial"
        ].copy()
        sekaiShader = material.node_tree.nodes[
            "SekaiShaderStageLightmapReflectionShader"
        ]
    material.name = name
    if "_MainTex" in textures:
        mainTex = make_material_texture_node(
            material, textures["_MainTex"], texture_cache
        )
        if mainTex:
            material.node_tree.links.new(
                mainTex.outputs["Color"], sekaiShader.inputs["Sekai C"]
            )
            material.node_tree.links.new(
                mainTex.outputs["Alpha"], sekaiShader.inputs["Alpha"]
            )
    if "_LightMapTex" in textures:
        lightMapTex = make_material_texture_node(
            material, textures["_LightMapTex"], texture_cache, "UV1"
        )
        if lightMapTex:
            material.node_tree.links.new(
                lightMapTex.outputs["Color"], sekaiShader.inputs["Sekai Lightmap"]
            )
    return material


def import_sekai_stage_color_add_material(
    name: str, data: Material, texture_cache=None, **kwargs
):
    """Imports Material assets for stage Color Add type (e.g. flares) into Blender

    Args:
        name (str): material name
        data (Material): UnityPy Material

    Returns:
        bpy.types.Material: Created material
    """
    textures = dict(data.m_SavedProperties.m_TexEnvs)
    material = bpy.data.materials["SekaiShaderStageColorAddMaterial"].copy()
    material.name = name
    sekaiShader = material.node_tree.nodes["SekaiShaderStageColorAddShader"]
    if "_MainTex" in textures:
        mainTex = make_material_texture_node(
            material, textures["_MainTex"], texture_cache
        )
        if mainTex:
            material.node_tree.links.new(
                mainTex.outputs["Color"], sekaiShader.inputs["Sekai C"]
            )
    return material


# endregion
