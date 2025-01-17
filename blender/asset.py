import logging, json
import tempfile
import copy

from UnityPy.helpers.MeshHelper import MeshHandler
from . import *

logger = logging.getLogger(__name__)


def search_env_meshes(env: Environment):
    """(Partially) Loads the UnityPy Environment for further Mesh processing

    Args:
        env (Environment): UnityPy Environment

    Returns:
        Tuple[List[GameObject], Dict[str,Armature]]: Static Mesh GameObjects and Armatures
    """
    # Collect all static meshes and skinned meshes's *root transform* object
    # UnityPy does not construct the Bone Hierarchy so we have to do it ourselves
    transform_roots = []
    for obj in env.objects:
        if obj.type == ClassIDType.Transform:
            data = obj.read()
            if hasattr(data, "m_Children") and not data.m_Father.path_id:
                transform_roots.append(data)
    # Collect all skinned meshes as Armature[s], otherwise build articulations for
    # Note that Mesh maybe reused across Armatures, but we don't care...for now
    articulations = []
    armatures = []
    for root in transform_roots:
        armature = Armature(root.m_GameObject.read().m_Name)
        armature.bone_path_hash_tbl = dict()
        armature.bone_name_tbl = dict()
        path_id_tbl = dict()  # Only used locally

        def dfs(root: Transform, parent: Bone = None):
            gameObject = root.m_GameObject.read()
            name = gameObject.m_Name
            # Addtional properties
            # Skinned Mesh Renderer
            if getattr(gameObject, "m_SkinnedMeshRenderer", None):
                armature.skinnedMeshGameObject = gameObject
            # Complete path. Used for CRC hash later on
            if parent:
                if parent.global_path:
                    path_from_root = parent.global_path + "/" + name
                else:
                    path_from_root = name
            else:
                path_from_root = ""
            # Reads:
            # - Physics Rb + Collider
            # XXX: Some properties are not implemented yet
            bonePhysics = None
            for component in gameObject.m_Components:
                if component.type == ClassIDType.MonoBehaviour:
                    component = component.deref().read(check_read=False)
                    if component.m_Script:
                        physicsScript = component.m_Script.read()
                        physics = component.__dict__  # .read_typetree()
                        phy_type = None
                        if physicsScript.m_Name == "SpringSphereCollider":
                            phy_type = BonePhysicsType.SphereCollider
                        if physicsScript.m_Name == "SpringCapsuleCollider":
                            phy_type = BonePhysicsType.CapsuleCollider
                        if physicsScript.m_Name == "SekaiSpringBone":
                            phy_type = BonePhysicsType.SpringBone
                        if physicsScript.m_Name == "SpringManager":
                            phy_type = BonePhysicsType.SpringManager
                        if phy_type != None:
                            bonePhysics = BonePhysics.from_dict(physics)
                            bonePhysics.type = phy_type
                            if "pivotNode" in physics:
                                bonePhysics.pivot = path_id_tbl.get(
                                    physics["pivotNode"].m_PathID, None
                                )
                                bonePhysics.pivot = getattr(
                                    bonePhysics.pivot, "name", None
                                )
            bone = Bone(
                name,
                root.m_LocalPosition,
                root.m_LocalRotation,
                root.m_LocalScale,
                parent,
                list(),
                path_from_root,
                None,
                bonePhysics,
                gameObject,
            )
            path_id_tbl[root.m_GameObject.m_PathID] = bone
            armature.bone_name_tbl[name] = bone
            if not parent:
                armature.root = bone
            else:
                armature.bone_path_hash_tbl[get_name_hash(path_from_root)] = bone
                parent.children.append(bone)
            for child in root.m_Children:
                dfs(child.read(), bone)

        dfs(root)
        if armature.skinnedMeshGameObject:
            armature.is_articulation = False
            armatures.append(armature)
        else:
            armature.is_articulation = True
            articulations.append(armature)
    articulations = sorted(articulations, key=lambda x: x.name)
    armatures = sorted(armatures, key=lambda x: x.name)
    return articulations, armatures


def search_env_animations(env: Environment):
    """Searches the Environment for AnimationClips

    Args:
        env (Environment): UnityPy Environment

    Returns:
        List[AnimationClip]: AnimationClips
    """
    animations = []
    for asset in env.assets:
        for obj in asset.get_objects():
            if obj.type == ClassIDType.AnimationClip:
                data = obj.read()
                animations.append(data)
    return animations


def import_mesh(
    name: str,
    data: Mesh,
    skinned: bool = False,
    bone_path_tbl: Dict[str, Bone] = None,
    bone_order: list[str] = None,
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
        skinned (bool, optional): Whether the Mesh has skinning data, i.e. attached to SkinnedMeshRenderer. Defaults to False.

    Returns:
        Tuple[bpy.types.Mesh, bpy.types.Object]: Created mesh and its parent object
    """
    logger.debug("Importing Mesh %s, Skinned=%s" % (data.m_Name, skinned))
    mesh = bpy.data.meshes.new(name=data.m_Name)
    handler = MeshHandler(data)
    handler.process()

    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bm = bmesh.new()
    # Bone Indices + Bone Weights
    deform_layer = None
    if skinned:
        if not bone_order:
            for boneHash in data.m_BoneNameHashes:
                # boneHash is the CRC32 hash of the full bone path
                # i.e Position/Hips/Spine/Spine1/Spine2/Neck/Head
                group_name = bone_path_tbl[boneHash].name
                obj.vertex_groups.new(name=group_name)
        else:
            for boneName in bone_order:
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
                boneWeight = [1.0] * len(boneIndex)
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
    # TODO: Figure out all uses cases for UV1 maps
    # Discoveries so far:
    # - Lightmaps for stage pre-baked lighting
    # - Facial SDF shadows. See Reference section in the README
    try_add_uv_map("UV1")
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
        mesh[KEY_SHAPEKEY_NAME_HASH_TBL] = json.dumps(
            keyshape_hash_tbl, ensure_ascii=False
        )
    bm.free()
    return mesh, obj


def import_articulation(arma: Armature, name: str = None):
    """Imports the Articulation hierarchy described by the Armature data into Blender as a set of Empty objects

    Args:
        arma (Armature): Armature as genereated by previous steps
        arma_parent (object, optional): Parent of the generated Empty hierachry. Defaults to None.

    Returns:
        Tuple[Dict[str,bpy.types.Object], bpy.types.Object]: Created Empty objects and its parent object
    """
    name = name or arma.name
    joint_map = dict()
    parent_joint = None
    for parent, bone, depth in arma.root.dfs_generator():
        joint = create_empty(
            bone.name, joint_map[parent.name] if parent else parent_joint
        )
        # Set the global transform
        joint.location = swizzle_vector(bone.localPosition)
        joint.rotation_mode = "QUATERNION"
        joint.rotation_quaternion = swizzle_quaternion(bone.localRotation)
        joint.scale = swizzle_vector_scale(bone.localScale)
        joint_map[bone.name] = joint
        if parent:
            joint[KEY_JOINT_BONE_NAME] = bone.name
        else:
            parent_joint = joint
            joint.name = name
            joint[KEY_ARTICULATION_NAME_HASH_TBL] = json.dumps(
                {k: v.name for k, v in arma.bone_path_hash_tbl.items()},
                ensure_ascii=False,
            )
    return joint_map, parent_joint


def import_armature(arma: Armature, name: str = None):
    """Imports the Armature hierarcht described by the Armature data into Blender as an Armature object

    Args:
        arma (Armature): Armature as genereated by previous steps
        name (str): Armature Object name

    Returns:
        Tuple[bpy.types.Armature, bpy.types.Object]: Created armature and its parent object
    """
    name = name or arma.name
    armature = bpy.data.armatures.new(name)
    armature.display_type = "OCTAHEDRAL"
    armature.relation_line_position = "HEAD"
    armature[KEY_BONE_NAME_HASH_TBL] = json.dumps(
        {k: v.name for k, v in arma.bone_path_hash_tbl.items()}, ensure_ascii=False
    )
    obj = bpy.data.objects.new(name, armature)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    root = arma.root
    # Build global transforms
    root.calculate_global_transforms()
    # Build bone hierarchy in blender
    for parent, child, _ in root.dfs_generator():
        if child.name != root.name:
            ebone = armature.edit_bones.new(child.name)
            ebone.use_local_location = True
            ebone.use_relative_parent = False
            ebone.use_connect = False
            ebone.use_deform = True
            child.edit_bone = ebone
            # Treat the joints as extremely small bones
            # The same as https://github.com/KhronosGroup/glTF-Blender-IO/blob/2debd75ace303f3a3b00a43e9d7a9507af32f194/addons/io_scene_gltf2/blender/imp/gltf2_blender_node.py#L198
            # TODO: Alternative shapes for bones
            ebone.head = child.global_transform @ blVector((0, 0, 0))
            ebone.tail = child.global_transform @ blVector((0, 1, 0))
            ebone.length = 0.01
            ebone.align_roll(child.global_transform @ blVector((0, 0, 1)) - ebone.head)
            if (
                parent and parent.name != root.name
            ):  # Let the root be the armature itself
                ebone.parent = parent.edit_bone

    return armature, obj


# XXX: This is irrevesible. Armature hierarchy will be simplified and there is not way to go back
#      Also, the workflow of animation import will require strict order of operations
#      One should import all physics constraints before importing animations
#      Since the import only works on rest pose for some reason?
#      Maybe this is enough for now..
def import_armature_physics_constraints(armature, data: Armature):
    """Imports the rigid body constraints for the armature

    Args:
        armature (bpy.types.Object): Armature object
        data (Armature): Armature data
    """
    PIVOT_SIZE = 0.004
    SPHERE_RADIUS_FACTOR = 1
    CAPSULE_RADIUS_FACTOR = 1
    CAPSULE_HEIGHT_FACTOR = 1
    SPRINGBONE_RADIUS_FACTOR = 0.15
    # These are totally empirical
    bpy.context.view_layer.objects.active = armature
    root_bone = data.root.recursive_locate_by_name("Position")

    if root_bone:
        # Connect all spring bones
        # SpringBones are observed to be never animated.
        # Connecting them will make our lives a lot eaiser
        bpy.ops.object.mode_set(mode="EDIT")

        class SpringBoneChain:
            begin: Bone = None
            end: Bone = None

        springbone_chains: Dict[str, SpringBoneChain] = dict()

        def connect_spring_bones(bone: Bone, parent=None):
            if not parent:
                if bone.physics and bone.physics.type == BonePhysicsType.SpringBone:
                    parent = bone
                if parent:
                    # First Physics bone in the chain
                    springbone_chains[parent.name] = SpringBoneChain()
                    springbone_chains[parent.name].begin = parent
            if parent:
                ebone = armature.data.edit_bones[bone.name]
                # EX (Physics) bone always has a parent Offset bone with them
                # We don't need them as they do not contribute to the mesh
                parent_bone = bone.parent
                if parent_bone.name in armature.data.edit_bones:
                    if (
                        "_offset" in parent_bone.name
                        and not bone.name in springbone_chains
                    ):  # Keep the fisrt bone's parent. The rest are connected
                        armature.data.edit_bones.remove(
                            armature.data.edit_bones[parent_bone.name]
                        )
                        ebone.parent = armature.data.edit_bones[parent_bone.parent.name]
                    # ebone.use_connect = True
                if not bone.children:
                    springbone_chains[parent.name].end = bone
            for child in bone.children:
                if not "_end" in child.name:
                    connect_spring_bones(child, parent)
                else:
                    # _end bones have no weight in the mesh. We'll merge them with the parent
                    ebone = armature.data.edit_bones[child.name]
                    parent = ebone.parent
                    parent.tail = ebone.head
                    armature.data.edit_bones.remove(
                        armature.data.edit_bones[child.name]
                    )

        connect_spring_bones(root_bone)

        # The following strategy is inspired by https://github.com/Pauan/blender-rigid-body-bones
        # TL;DR
        # * Isolate physics bones from the hierarchy
        # * Make rigidbodies for each of them
        # * Also, make a rigidbody for the parent bone of the chain
        # * By using Empty object with the same hierarchy of the bones, connect the rigidbodies with constraints, building the hierarchy again
        # * Apply physical constraints to the rigidbodies
        # * Disable self-collisions for the active rigidbodies
        # * Apply constraints to the bones
        # * Profit(?) lmao copilot added this
        def create_bone_rigidbody(
            name: str, radius: float, passive=False, has_collison=True, length=-1
        ):
            bpy.ops.mesh.primitive_cylinder_add(
                radius=radius, depth=length if length > 0 else radius * 2
            )
            obj = bpy.context.object
            obj.name = name + "_rigidbody"
            # Align the cylinder to the bone
            obj.rotation_euler.rotate_axis("X", math.radians(-90))
            obj.location += blVector((0, length / 2, 0))
            bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
            bpy.ops.rigidbody.object_add()
            obj.rigid_body.collision_shape = "CONVEX_HULL"
            obj.rigid_body.type = "PASSIVE" if passive else "ACTIVE"
            obj.rigid_body.kinematic = True if passive else False
            obj.rigid_body.collision_collections[0] = has_collison
            obj.display_type = "BOUNDS"
            return obj

        def set_bone_parent(object: bpy.types.Object, bone_name: str):
            object.parent = armature
            object.parent_type = "BONE"
            object.parent_bone = bone_name

        def set_bone_constraint(bone_name: str, target):
            pbone: bpy.types.PoseBone = armature.pose.bones[bone_name]
            ct = pbone.constraints.new("COPY_TRANSFORMS")
            ct.target = target
            # ct.use_scale_x = ct.use_scale_y = ct.use_scale_z = False
            # bpy.context.active_object.data.bones.active = pbone.bone
            # context_override = bpy.context.copy()
            # with bpy.context.temp_override(**context_override):
            #     bpy.ops.constraint.childof_set_inverse(constraint=ct.name, owner='BONE')

        def unparent_bone(bone_name):
            bpy.ops.object.mode_set(mode="EDIT")
            ebone = armature.data.edit_bones[bone_name]
            arma_matrix = ebone.matrix
            ebone.parent = None
            ebone.matrix = arma_matrix

        def set_no_collision(obj, parent_obj):
            # Joint follows the pivot
            joint = create_empty(obj.name + "_nc_joint", parent_obj)
            bpy.context.view_layer.objects.active = joint
            bpy.ops.rigidbody.constraint_add(type="GENERIC")
            # Without limits. This acts as a dummy constraint
            # to disable collisions between the two objects
            ct = joint.rigid_body_constraint
            ct.disable_collisions = True
            ct.object1 = obj
            ct.object2 = parent_obj

        for chain in springbone_chains.values():
            bpy.context.view_layer.objects.active = armature
            bpy.ops.object.mode_set(mode="EDIT")
            ebone_begin: bpy.types.EditBone = armature.data.edit_bones[chain.begin.name]
            chain_all = [ebone_begin] + ebone_begin.children_recursive
            parent_all = {
                bone.name: bone.parent.name for bone in chain_all if bone.parent
            }
            bonesize_all = {bone.name: bone.length for bone in chain_all}
            # Read this later on in pose mode since constraits/animations are not available in edit mode
            world_all = {
                bone.name: bone.matrix
                for bone in chain_all
                + [bone.parent for bone in chain_all if bone.parent]
            }
            chain_all = [bone.name for bone in chain_all]
            bpy.ops.object.mode_set(mode="POSE")
            for bone in chain_all:
                unparent_bone(bone)
            bpy.ops.object.mode_set(mode="OBJECT")
            pivot_bone_name = chain.begin.parent.name  # chain.begin.physics.pivot
            # 'pivot' is not used since 'connect_spring_bones' process already connected the bones
            # and the parent of the beginning of the chain would be the only usable pivot
            joints = dict()
            rigidbodies = dict()
            prev_radius = PIVOT_SIZE
            for bone_name in [pivot_bone_name] + chain_all:
                parent = parent_all.get(bone_name, None)
                joint = create_empty(bone_name + "joint")
                joints[bone_name] = joint
                if parent:
                    joint.parent = joints[parent]
                    joint.matrix_local = (
                        world_all[parent].inverted() @ world_all[bone_name]
                    )

                    phys_data = data.bone_name_tbl[bone_name].physics
                    if phys_data:
                        prev_radius = phys_data.radius
                    target = create_bone_rigidbody(
                        bone_name + "_target",
                        (phys_data.radius if phys_data else prev_radius)
                        * SPRINGBONE_RADIUS_FACTOR,
                        passive=False,
                        has_collison=True,
                        length=bonesize_all[bone_name],
                    )
                    target.parent = joint
                    target.matrix_local = blMatrix.Identity(4)

                    rigidbodies[bone_name] = target
                    parent = rigidbodies[parent_all[bone_name]]

                    # Add constraint for the rbs
                    bpy.context.view_layer.objects.active = joint
                    # Add the constraint
                    bpy.ops.rigidbody.constraint_add(type="GENERIC_SPRING")
                    ct = joint.rigid_body_constraint
                    ct.use_limit_lin_x = True
                    ct.use_limit_lin_y = True
                    ct.use_limit_lin_z = True
                    # No linear movement
                    ct.limit_lin_x_lower = 0
                    ct.limit_lin_x_upper = 0
                    ct.limit_lin_y_lower = 0
                    ct.limit_lin_y_upper = 0
                    ct.limit_lin_z_lower = 0
                    ct.limit_lin_z_upper = 0
                    # Angular movement per physics data
                    # Note that the axis are swapped
                    ct.use_limit_ang_x = True
                    ct.use_limit_ang_y = True
                    ct.use_limit_ang_z = True
                    if phys_data:
                        ct.limit_ang_x_lower = 0
                        ct.limit_ang_x_upper = 0
                        ct.limit_ang_y_lower = (
                            math.radians(phys_data.zAngleLimits.min) / 2
                        )
                        ct.limit_ang_y_upper = (
                            math.radians(phys_data.zAngleLimits.max) / 2
                        )
                        ct.limit_ang_z_lower = (
                            math.radians(phys_data.yAngleLimits.min) / 2
                        )
                        ct.limit_ang_z_upper = (
                            math.radians(phys_data.yAngleLimits.max) / 2
                        )
                    # Spring damping effect
                    # XXX: These are not going to be accurate
                    ct.use_spring_ang_x = True
                    ct.use_spring_ang_y = True
                    ct.use_spring_ang_z = True
                    if phys_data:
                        ct.spring_stiffness_ang_x = ct.spring_stiffness_ang_y = (
                            ct.spring_stiffness_ang_z
                        ) = phys_data.angularStiffness
                        ct.spring_damping_x = ct.spring_damping_y = (
                            ct.spring_damping_z
                        ) = phys_data.dragForce
                    # Link the objects!
                    joint.rigid_body_constraint.object1 = parent
                    joint.rigid_body_constraint.object2 = target
                    # Constraints back to the bones
                    bpy.context.view_layer.objects.active = armature
                    bpy.ops.object.mode_set(mode="POSE")
                    set_bone_constraint(bone_name, target)
                else:
                    pivot = create_bone_rigidbody(
                        pivot_bone_name + "_pivot",
                        PIVOT_SIZE,
                        passive=True,
                        has_collison=False,
                    )
                    set_bone_parent(pivot, pivot_bone_name)
                    rigidbodies[pivot_bone_name] = pivot

                    joint.parent = pivot
                    joint.matrix_local = blMatrix.Identity(4)
        bpy.ops.object.mode_set(mode="OBJECT")
        rbs = list(rigidbodies.values())
        for i in range(len(rbs)):
            for j in range(i + 1, len(rbs)):
                set_no_collision(rbs[i], rbs[j])
        for parent, child, _ in root_bone.dfs_generator():
            if child.physics:
                if child.physics.type & BonePhysicsType.Collider:
                    # Add colliders
                    obj = None
                    if child.physics.type == BonePhysicsType.SphereCollider:
                        bpy.ops.mesh.primitive_uv_sphere_add(
                            radius=child.physics.radius * SPHERE_RADIUS_FACTOR
                        )
                        obj = bpy.context.object
                        obj.name = child.name + "_rigidbody"
                        bpy.ops.rigidbody.object_add()
                        obj.rigid_body.type = "PASSIVE"
                        obj.rigid_body.collision_shape = "SPHERE"
                    if child.physics.type == BonePhysicsType.CapsuleCollider:
                        bpy.ops.mesh.primitive_cylinder_add(
                            radius=child.physics.radius * CAPSULE_RADIUS_FACTOR,
                            depth=child.physics.height * CAPSULE_HEIGHT_FACTOR,
                        )
                        obj = bpy.context.object
                        obj.name = child.name + "_rigidbody"
                        bpy.ops.rigidbody.object_add()
                        obj.rigid_body.type = "PASSIVE"
                        obj.rigid_body.collision_shape = "CAPSULE"
                    if obj:
                        obj.rigid_body.kinematic = True
                        obj.parent = armature
                        obj.parent_bone = child.name
                        obj.parent_type = "BONE"
                        obj.display_type = "BOUNDS"
                        bpy.ops.object.parent_clear(type="CLEAR_INVERSE")


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


def ensure_sssekai_shader_blend():
    SHADER_BLEND_FILE = get_addon_relative_path("assets", "SekaiShaderStandalone.blend")
    if not "SSSekaiWasHere" in bpy.data.materials:
        logger.warning("SekaiShader not loaded. Importing from %s" % SHADER_BLEND_FILE)
        with bpy.data.libraries.load(SHADER_BLEND_FILE, link=False) as (
            data_from,
            data_to,
        ):
            data_to.materials = data_from.materials
            data_to.node_groups = data_from.node_groups
            data_to.collections = data_from.collections
            logger.debug("Loaded shader blend file.")
        bpy.context.scene.collection.children.link(
            bpy.data.collections["SekaiShaderBase"]
        )


def make_material_texture_node(
    material,
    ppTexture,
    texture_cache=None,
    uv_layer="UV0",
    uv_remap_override_node=None,
    uv_remap_postprocess_node=None,
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


def auto_connect_shader_nodes_by_name(node_tree, lhs, rhs):
    outputs = {k.name: i for i, k in enumerate(lhs.outputs)}
    inputs = {k.name: i for i, k in enumerate(rhs.inputs)}
    for output in outputs:
        if output in inputs:
            node_tree.links.new(
                lhs.outputs[outputs[output]], rhs.inputs[inputs[output]]
            )


def auto_setup_shader_node_driver(node_group, target_obj):
    def fcurves_for_input(node, input_path):
        node.inputs[input_path].driver_remove("default_value")
        return node.inputs[input_path].driver_add("default_value")

    def fcurves_for_output(node, input_path):
        node.outputs[input_path].driver_remove("default_value")
        return node.outputs[input_path].driver_add("default_value")

    def drivers_setup(fcurves, paths):
        for fcurve, path in zip(fcurves, paths):
            driver = fcurve.driver
            driver.type = "SCRIPTED"
            driver.expression = "var"
            var = driver.variables.new()
            var.name = "var"
            var.targets[0].id = target_obj
            var.targets[0].data_path = path

    for node in node_group.nodes:
        if node.type == "VECTOR_ROTATE":
            fcurves = fcurves_for_input(node, "Rotation")
            drivers_setup(
                fcurves,
                ["rotation_euler.x", "rotation_euler.y", "rotation_euler.z"],
            )
        elif node.name in target_obj:
            if node.type == "VECT_MATH":
                fcurves = fcurves_for_input(node, 0)
                drivers_setup(
                    fcurves,
                    [
                        f'["{node.name}"][0]',
                        f'["{node.name}"][1]',
                        f'["{node.name}"][2]',
                    ],
                )
            if node.type == "VALUE":
                fcurves = fcurves_for_output(node, 0)
                drivers_setup([fcurves], [f'["{node.name}"]'])
    pass


def create_principled_bsdf_material(name: str):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    material.use_backface_culling = True
    # material.blend_method = ("BLEND")
    # Alpha blending is always costly. This should be opt-in when there's alpha channel in the texture
    # TODO: Can we know in advance if the texture has alpha?
    return material


def import_eyelight_material(name: str, data: Material, texture_cache=None, **kwargs):
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


def import_eye_material(name: str, data: Material, texture_cache=None, **kwargs):
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


def import_character_material(
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
