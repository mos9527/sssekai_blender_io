import bpy, bmesh
import json, math
import tempfile, copy
from typing import Dict, Tuple, List
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


def import_hierarchy_as_armature(
    hierarchy: Hierarchy, name: str = None, use_bindpose: bool = False
):
    """Imports Hierarchy data into Blender as an Armature object

    Args:
        arma (Armature): Armature as genereated by previous steps
        name (str): Armature Object name

    Returns:
        Tuple[bpy.types.Armature, bpy.types.Object]: Created armature and its parent object
    """
    name = name or hierarchy.name
    armature = bpy.data.armatures.new(name)
    armature.display_type = "OCTAHEDRAL"
    armature.relation_line_position = "HEAD"
    obj = bpy.data.objects.new(name, armature)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    root_meshes: Dict[int, int] = dict()
    for path_id, node in hierarchy.nodes.items():
        if node.game_object and node.game_object.m_SkinnedMeshRenderer:
            root_meshes[path_id] = node
    # Adjust SkinnedMesh Root bones by the meshes' bindpose
    root_bindposes: Dict[int, Dict[int, blMatrix]] = dict()
    bindposes_pa: Dict[int, int] = dict()
    if use_bindpose:
        for path_id, node in hierarchy.nodes.items():
            if node.game_object and node.game_object.m_SkinnedMeshRenderer:
                renderer = node.game_object.m_SkinnedMeshRenderer.read()
                renderer: SkinnedMeshRenderer
                root_bone = renderer.m_RootBone.m_PathID
                if not renderer.m_Mesh:
                    continue
                mesh = renderer.m_Mesh.read()
                mesh: Mesh
                bindposes = {
                    p.m_PathID: swizzle_matrix(mesh.m_BindPose[i])
                    for i, p in enumerate(renderer.m_Bones)
                }
                for p in renderer.m_Bones:
                    bindposes_pa[p.m_PathID] = root_bone
                if root_bone in root_bindposes:
                    # Sanity check - only allow this when the bindposes are the same
                    dirty = False
                    for p, bp in root_bindposes[root_bone].items():
                        # Matrix eq. is done within epsilon
                        if not p in bindposes or bindposes[p] != bp:
                            dirty = True
                            break
                    if dirty:
                        logger.warning(
                            "Impossible! Root bone %s has different bindposes!"
                            % hierarchy.nodes[root_bone].name
                        )
                        continue
                root_bindposes[root_bone] = bindposes
            pass
    # Build bone hierarchy in blender
    # Obivously the won't work when leaf bones aren't named uniquely
    # However the assumption should hold true since...well, Blender doesn't allow it -_-||
    # XXX: Figure out if we'd ever need to support multiple bones with the same name
    #
    # Final = EditBone * PoseBone
    ebones = dict()
    root_bone = hierarchy.root
    # Build EditBones.
    # No scaling is ever applied here since otherwise this messes up bind pose calculations
    hierarchy.root.update_global_transforms(scale=False)
    for parent, child, _ in root_bone.children_recursive():
        parent: HierarchyNode
        child: HierarchyNode
        if child.name != root_bone.name:
            ebone = armature.edit_bones.new(child.name)
            ebone.use_local_location = True
            ebone.use_relative_parent = False
            ebone.use_connect = False
            ebone.use_deform = True
            M_edit = child.global_transform
            # Use bindposes for the subtree of the root bone
            # and apply the actual pose in Pose Bones later
            if use_bindpose and child.path_id in bindposes_pa:
                # Needs correction
                bparent = bindposes_pa[child.path_id]
                bbind = root_bindposes[bparent][child.path_id]
                # In armature space it's basically the inverse of the bindpose
                # Identity = M_bind * M_pose
                M_pose = bbind.inverted()
                M_pose = unity_to_blender(M_pose)
                # Bindposes are in the _Root's Parent's_ space (2 levels up)
                brparent = hierarchy.parents[bparent]
                M_parent = hierarchy.nodes[brparent].global_transform
                # XXX: Assume no scaling in M_pose
                M_edit = M_parent @ M_pose
            # Treat the joints as extremely small bones
            # The same as https://github.com/KhronosGroup/glTF-Blender-IO/blob/2debd75ace303f3a3b00a43e9d7a9507af32f194/addons/io_scene_gltf2/blender/imp/gltf2_blender_node.py#L198
            # TODO: Alternative shapes for bones
            ebone.head = M_edit @ blVector((0, 0, 0))
            ebone.tail = M_edit @ blVector((0, 1, 0))
            ebone.length = DEFAULT_BONE_SIZE
            ebone.align_roll(M_edit @ blVector((0, 0, 1)) - ebone.head)
            ebone.parent = (
                ebones[parent.name]
                if parent and parent.name != root_bone.name
                else None
            )
            ebone[KEY_HIERARCHY_BONE_PATHID] = str(child.path_id)
            ebones[child.name] = ebone
    # Pose space adjustment
    # Make Scene Hierachy transform the Pose Bones so the final pose is correct
    if use_bindpose:
        # i hate this
        # https://docs.blender.org/api/current/info_gotcha.html#stale-data
        bpy.context.view_layer.update()
        pose_matrix = {
            node.name: node.global_transform for node in hierarchy.nodes.values()
        }
        apply_pose_matrix(obj, pose_matrix, edit_mode=False)
    # Scale adjustment
    bpy.ops.object.mode_set(mode="POSE")
    for node in hierarchy.nodes.values():
        if node.path_id in root_meshes:
            continue
        pbone = obj.pose.bones.get(node.name, None)
        if pbone:
            pbone.scale = swizzle_vector_scale(node.scale)
    bpy.ops.object.mode_set(mode="OBJECT")
    obj[KEY_HIERARCHY_PATHID] = str(hierarchy.path_id)
    return armature, obj


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
    """Imports Texture2D assets into blender

    Args:
        name (str): asset name
        data (Texture2D): source texture

    Returns:
        bpy.types.Image: Created image
    """
    with tempfile.NamedTemporaryFile(suffix=".tga", delete=False) as temp:
        logger.debug("Saving Texture %s->%s" % (data.m_Name, temp.name))
        image = data.image
        image.save(temp)
        temp.close()
        img = bpy.data.images.load(temp.name, check_existing=True)
        img.name = name
        logger.debug("Imported Texture %s" % name)
        return img


def make_material_texture_node(
    material: bpy.types.Material,
    ppTexture: UnityTexEnv,
    texture_cache: dict = None,
    uv_layer: str = "UV0",
    uv_remap_override_node: bpy.types.Node = None,
    uv_remap_postprocess_node: bpy.types.Node = None,
):
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
    try:
        texture: Texture2D = ppTexture.m_Texture.read()
        if texture_cache:
            if not texture.m_Name in texture_cache:
                texture_cache[texture.m_Name] = import_texture(texture.m_Name, texture)
            texNode.image = texture_cache[texture.m_Name]
        else:
            texNode.image = import_texture(texture.m_Name, texture)
    except Exception as e:
        logger.error("Failed to load texture - %s. Discarding." % e)
        return None
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


def import_fallback_material(name: str, data: Material, texture_cache=None, **kwargs):
    """Imports Material assets into blender.
    This is a generic material importer that only imports the main texture,
    as the input to a Principled BSDF shader's Base Color (Diffuse) and an Alpha input

    Args:
        name (str): material name
        data (Material): UnityPy Material

    Returns:
        bpy.types.Material: Created material
    """
    textures = dict(data.m_SavedProperties.m_TexEnvs)
    material = bpy.data.materials["SekaiDefaultFallbackMaterial"].copy()
    material.name = name
    sekaiShader = material.node_tree.nodes["SekaiDefaultFallbackShader"]
    if "_MainTex" in textures:
        mainTex = make_material_texture_node(
            material, textures["_MainTex"], texture_cache
        )
        if mainTex:
            material.node_tree.links.new(
                mainTex.outputs["Color"],
                sekaiShader.inputs["Color"],
            )
            material.node_tree.links.new(
                mainTex.outputs["Alpha"], sekaiShader.inputs["Alpha"]
            )
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
