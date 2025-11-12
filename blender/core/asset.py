import bpy, bmesh
import json, math
import tempfile, copy, traceback
from typing import Dict, Tuple, List, Set
from UnityPy.enums import ClassIDType
from UnityPy.helpers.MeshHelper import MeshHandler
from UnityPy.classes import (
    ColorRGBA,
    Texture2D,
    Material,
    Mesh,
    Transform,
    RectTransform,
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
    UNITY_TO_BLENDER_BASIS,
    BLENDER_TO_UNITY_BASIS,
)
from .consts import *
from .. import logger
from tqdm import tqdm


def build_scene_hierarchy(env: Environment) -> List[Hierarchy]:
    """Build the scene hierarchy from the UnityPy Environment

    Formally, this function locates all the root Transform objects
    in the Environment (all scenes would then be included) and builds the hierarchy from there.

    With Unity's Scene Graph (Hierarchy), the root of the hierarchy belongs to the scene itself.
    This in effect eliminates the distinction between scene(s) and would allow a one-to-one
    representation of the scene in Blender's View Layer.
    """
    transform_roots = []
    for obj in filter(
        lambda obj: obj.type in {ClassIDType.Transform, ClassIDType.RectTransform},
        env.objects,
    ):
        data = obj.read()
        if hasattr(data, "m_Children") and not data.m_Father.path_id:
            transform_roots.append(data)
    hierarchies = []
    for transform in transform_roots:
        hierarchy = Hierarchy(transform.m_GameObject.read().m_Name)

        def dfs(root: Transform | RectTransform, parent: HierarchyNode = None):
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
    seperate_armatures: bool = False,
) -> List[Tuple[bpy.types.Object, Dict[int, str], int]]:
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
        List[Tuple[bpy.types.Object, Dict[int, str], int]]:
            List of tuples containing the created Armature, a dictionary of bone IDs, the path ID of the Skinned Mesh Renderer
            The SMR path ID can be 0 - in which case the armature is used for all Skinned Mesh Renderers in the hierarchy.
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
        keep_only_bone_ids: bool = False,
    ) -> Tuple[bpy.types.Object, Dict[int, str]]:
        # Reserve bone_id nodes's names since they'd be used for vertex groups
        reserve_bonenames = dict()
        if bone_ids:
            for path_id in bone_ids:
                if not path_id in hierarchy.nodes:
                    logger.warning(
                        "Bone ID %d not found in hierarchy nodes, skipping." % path_id
                    )
                    continue
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

        bone_ids_keep = set()
        if keep_only_bone_ids:
            # Find the only path that leads to the bone_ids set
            # i.e. ones that contributes to the final global transform, with or without bindpose
            def dfs(bone: HierarchyNode):
                if bone.path_id in bone_ids:
                    return True
                res = False
                for child in bone.children:
                    res |= dfs(child)
                if res:
                    bone_ids_keep.add(bone.path_id)
                return res

            dfs(root_bone)
            for ch_root in bone_ids:
                bone_ids_keep.add(ch_root)
                for parent, child, _ in hierarchy.nodes[ch_root].children_recursive():
                    # Add all children of the bone_ids to the keep set
                    bone_ids_keep.add(child.path_id)

        for parent, child, _ in root_bone.children_recursive(visited=visited):
            if keep_only_bone_ids and child.path_id not in bone_ids_keep:
                # Skip bones that are not in the bone_ids set with this flag
                continue
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
                    # logger.debug("No bindpose found for %s" % child.name)
                    pass
                else:
                    M_bind = swizzle_matrix(M_bind)
                    # In armature space it's basically the inverse of the bindpose
                    # Identity = M_bind * M_pose
                    M_pose = M_bind.inverted()
                    M_pose = UNITY_TO_BLENDER_BASIS @ M_pose @ BLENDER_TO_UNITY_BASIS
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

    sm_renderers = list()
    # Skinned Mesh Roots
    # SkinnedMesh's RootBone doesn't have to be the root of the hierarchy
    # Nor does it influence the skinning in any way
    # This is only used to determine skinned meshes in the hierarchy
    for path_id, node in hierarchy.nodes.items():
        if node.game_object and node.game_object.m_SkinnedMeshRenderer:
            sm: SkinnedMeshRenderer = node.game_object.m_SkinnedMeshRenderer.read()
            if sm.m_Mesh:
                sm_renderers.append(sm)

    if seperate_armatures:
        # Create new armatures for each Skinned Mesh Renderer
        # This is useful when the Skinned Meshes have different bindposes
        # and cannot be combined into a single armature
        # NOTE: The hierarchy that influences the skinning is replicated for each Skinned Mesh Renderer
        logger.info(
            f"Importing {len(sm_renderers)} Skinned Mesh Renderers as separate armatures"
        )
        for sm in tqdm(sm_renderers):
            bones = {p.path_id for p in sm.m_Bones}
            parent = hierarchy.root
            if use_bindpose:
                bindpose = bindpose_of(sm)
                obj, child_bone_names = build_armature(
                    parent, bindpose=bindpose, bone_ids=bones, keep_only_bone_ids=True
                )
            else:
                obj, child_bone_names = build_armature(
                    parent, bone_ids=bones, keep_only_bone_ids=True
                )
            results.append((obj, child_bone_names, sm.object_reader.path_id))
    else:
        # Import the entire hierarchy as a single armature
        # Fails when:
        # - The root bones are reused for *different* bindposes
        # - The root bones are reused for *different* meshes with different weights
        # Otherwise for a single skinned mesh with a single bindpose this is fine
        bone_ids = set()
        for sm in sm_renderers:
            bone_ids |= {p.path_id for p in sm.m_Bones}
        if use_bindpose:
            bindpose = dict()
            for i in range(0, len(sm_renderers) - 1):
                cur, next = sm_renderers[i], sm_renderers[i + 1]
                bindpose |= bindpose_of(cur)
                bindpose |= bindpose_of(next)
            if len(sm_renderers) == 1:
                bindpose |= bindpose_of(sm_renderers[0])
            obj, bone_names = build_armature(
                hierarchy.root, bindpose=bindpose, bone_ids=bone_ids
            )
        else:
            obj, bone_names = build_armature(hierarchy.root, bone_ids=bone_ids)
        results.append((obj, bone_names, 0))

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
        vert = bm.verts.new(swizzle_vector3(*handler.m_Vertices[vtx][:3]))
        # Blender always generates normals automatically
        # Custom normals needs a bit more work
        # See below for normals_split... calls
        if handler.m_Normals:
            vert.normal = swizzle_vector3(*handler.m_Normals[vtx][:3])
        if deform_layer:
            boneIndex = handler.m_BoneIndices[vtx]
            if handler.m_BoneWeights:
                boneWeight = handler.m_BoneWeights[vtx]
            else:
                # Default to 1 otherwise the bone would not have any effect on the skinning
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
                # logger.warning("Invalid face index %d (%s) - discarded." % (idx, e))
                pass
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
                    # XXX: UVs with >2 components HOW?
                    uv_layer.data[loop].uv = src_layer[vtx][:2]

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
    # Reset Shape Key values to 0 (Blender 5.0.0+ quirk)
    if obj.data.shape_keys:
        for key_block in obj.data.shape_keys.key_blocks:
            if key_block.name != "Basis":
                key_block.value = 0.0
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
        if ppTexture.m_Texture:
            texture: Texture2D = ppTexture.m_Texture.read()
            if texture_cache:
                if not texture.object_reader.path_id in texture_cache:
                    texture_cache[texture.object_reader.path_id] = import_texture(
                        texture.m_Name, texture
                    )
                image = texture_cache[texture.object_reader.path_id]
            else:
                image = import_texture(texture.m_Name, texture)
        else:
            return None
    except Exception as e:
        traceback.print_exc()
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


def make_material_value_node(
    name: str, material: bpy.types.Material, value: float | int | ColorRGBA
):
    node = None
    if type(value) == ColorRGBA:
        node = material.node_tree.nodes.new("ShaderNodeCombineXYZ")
        node.inputs[0].default_value = value.r
        node.inputs[1].default_value = value.g
        node.inputs[2].default_value = value.b
        alpha = make_material_value_node(name + " Alpha", material, value.a)
    else:
        node = material.node_tree.nodes.new("ShaderNodeValue")
        node.outputs[0].default_value = value
    if node:
        node.name = node.label = name
    return node


def import_all_material_inputs(name: str, data: Material, texture_cache=None, **kwargs):
    """Imports Material assets into blender.
    This imports all texture slots into the material w/o actually linking them.

    Args:
        name (str): material name
        data (Material): UnityPy Material

    Returns:
        bpy.types.Material: Created material
    """
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    for node in material.node_tree.nodes:
        material.node_tree.nodes.remove(node)
    output = material.node_tree.nodes.new("ShaderNodeOutputMaterial")
    output.name = "Material Output"
    for env_name, env in data.m_SavedProperties.m_TexEnvs or []:
        tex = make_material_texture_node(material, env, texture_cache)
        if tex:
            tex.name = tex.label = env_name
        else:
            logger.warning("Texture map not found on %s" % env_name)
    for env_name, env in (
        (data.m_SavedProperties.m_Floats or [])
        + (data.m_SavedProperties.m_Colors or [])
        + (data.m_SavedProperties.m_Ints or [])
    ):
        node = make_material_value_node(env_name, material, env)

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
