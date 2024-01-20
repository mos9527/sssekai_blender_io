from . import *

def search_env_meshes(env : Environment):
    '''(Partially) Loads the UnityPy Environment for further Mesh processing

    Args:
        env (Environment): UnityPy Environment

    Returns:
        Tuple[List[GameObject], Dict[str,Armature]]: Static Mesh GameObjects and Armatures
    '''
    # Collect all static meshes and skinned meshes's *root transform* object
    # UnityPy does not construct the Bone Hierarchy so we have to do it ourselves
    static_mesh_gameobjects : List[GameObject] = list() # No extra care needed
    transform_roots = []
    for obj in env.objects:
        data = obj.read()
        if obj.type == ClassIDType.GameObject and getattr(data,'m_MeshRenderer',None):
            static_mesh_gameobjects.append(data)
        if obj.type == ClassIDType.Transform:
            if hasattr(data,'m_Children') and not data.m_Father.path_id:
                transform_roots.append(data)
    # Collect all skinned meshes as Armature[s]
    # Note that Mesh maybe reused across Armatures, but we don't care...for now
    armatures = []
    for root in transform_roots:
        armature = Armature(root.m_GameObject.read().m_Name)
        armature.bone_path_hash_tbl = dict()
        armature.bone_name_tbl = dict()
        path_id_tbl = dict() # Only used locally
        def dfs(root : Transform, parent : Bone = None):            
            gameObject = root.m_GameObject.read()
            name = gameObject.m_Name
            # Addtional properties
            # Skinned Mesh Renderer
            if getattr(gameObject,'m_SkinnedMeshRenderer',None):
                armature.skinned_mesh_gameobject = gameObject
            # Complete path. Used for CRC hash later on
            path_from_root = ''
            if parent and parent.global_path:
                path_from_root = parent.global_path + '/' + name
            elif parent:
                path_from_root = name
            # Physics Rb + Collider
            # XXX: Some properties are not implemented yet
            bonePhysics = None
            for component in gameObject.m_Components:
                if component.type == ClassIDType.MonoBehaviour:
                    component = component.read()
                    if component.m_Script:
                        physicsScript = component.m_Script.read()
                        physics = component.read_typetree()
                        phy_type = None                        
                        if physicsScript.name == 'SpringSphereCollider':
                            phy_type = BonePhysicsType.SphereCollider
                        if physicsScript.name == 'SpringCapsuleCollider':
                            phy_type = BonePhysicsType.CapsuleCollider
                        if physicsScript.name == 'SekaiSpringBone':
                            phy_type = BonePhysicsType.SpringBone
                        if physicsScript.name == 'SpringManager':
                            phy_type = BonePhysicsType.SpringManager
                        if phy_type != None:
                            bonePhysics = BonePhysics.from_dict(physics)                            
                            bonePhysics.type = phy_type
                            if 'pivotNode' in physics:
                                bonePhysics.pivot = path_id_tbl[physics['pivotNode']['m_PathID']].name
            bone = Bone(
                name,
                root.m_LocalPosition,
                root.m_LocalRotation,
                root.m_LocalScale,
                parent,
                list(),
                path_from_root,
                None,
                bonePhysics
            )
            path_id_tbl[root.path_id] = bone
            armature.bone_name_tbl[name] = bone
            armature.bone_path_hash_tbl[get_name_hash(path_from_root)] = bone
            if not parent:
                armature.root = bone
            else:
                parent.children.append(bone)
            for child in root.m_Children:
                dfs(child.read(), bone)
        dfs(root)    
        if armature.skinned_mesh_gameobject:
            armatures.append(armature)
    return static_mesh_gameobjects, armatures

def search_env_animations(env : Environment):
    '''Searches the Environment for AnimationClips

    Args:
        env (Environment): UnityPy Environment

    Returns:
        List[AnimationClip]: AnimationClips
    '''
    animations = []
    for asset in env.assets:
        for obj in asset.get_objects():
            data = obj.read()
            if obj.type == ClassIDType.AnimationClip:
                animations.append(data)
    return animations

def import_mesh(name : str, data: Mesh, skinned : bool = False, bone_path_tbl : Dict[str,Bone] = None):
    '''Imports the mesh data into blender.

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
    '''
    print('* Importing Mesh', data.name, 'Skinned=', skinned)
    mesh = bpy.data.meshes.new(name=data.name)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bm = bmesh.new()
    vtxFloats = int(len(data.m_Vertices) / data.m_VertexCount)
    normalFloats = int(len(data.m_Normals) / data.m_VertexCount)
    uvFloats = int(len(data.m_UV0) / data.m_VertexCount)
    colorFloats = int(len(data.m_Colors) / data.m_VertexCount)
    # Bone Indices + Bone Weights
    deform_layer = None
    if skinned:
        for boneHash in data.m_BoneNameHashes:
            # boneHash is the CRC32 hash of the full bone path
            # i.e Position/Hips/Spine/Spine1/Spine2/Neck/Head
            group_name = bone_path_tbl[boneHash].name   
            obj.vertex_groups.new(name=group_name)
        deform_layer = bm.verts.layers.deform.new()
        # Animations uses the hash to identify the bone
        # so this has to be stored in the metadata as well
        mesh[KEY_BONE_NAME_HASH_TBL] = json.dumps({k:v.name for k,v in bone_path_tbl.items()},ensure_ascii=False)
    # Vertex position & vertex normal (pre-assign)
    for vtx in range(0, data.m_VertexCount):        
        vert = bm.verts.new(swizzle_vector3(
            data.m_Vertices[vtx * vtxFloats], # x,y,z
            data.m_Vertices[vtx * vtxFloats + 1],
            data.m_Vertices[vtx * vtxFloats + 2]            
        ))
        # Blender always generates normals automatically
        # Custom normals needs a bit more work
        # See below for normals_split... calls
        # XXX why is this flipped?
        vert.normal = swizzle_vector3(
            -1 * data.m_Normals[vtx * normalFloats],
            -1 * data.m_Normals[vtx * normalFloats + 1],
            -1 * data.m_Normals[vtx * normalFloats + 2]
        )
        if deform_layer:
            for i in range(4):
                skin = data.m_Skin[vtx]
                if skin.weight[i] <= 0:
                    continue
                vertex_group_index = skin.boneIndex[i]                
                vert[deform_layer][vertex_group_index] = skin.weight[i]
    bm.verts.ensure_lookup_table()
    # Indices
    for idx in range(0, len(data.m_Indices), 3):
        face = bm.faces.new([bm.verts[data.m_Indices[idx + j]] for j in range(3)])
        face.smooth = True
    bm.to_mesh(mesh)
    # UV Map
    uv_layer = mesh.uv_layers.new()
    mesh.uv_layers.active = uv_layer
    for face in mesh.polygons:
        for vtx, loop in zip(face.vertices, face.loop_indices):
            uv_layer.data[loop].uv = (
                data.m_UV0[vtx * uvFloats], 
                data.m_UV0[vtx * uvFloats + 1]
            )
    # Vertex Color
    if colorFloats:
        vertex_color = mesh.color_attributes.new(name='Vertex Color',type='FLOAT_COLOR',domain='POINT')
        for vtx in range(0, data.m_VertexCount):
            color = [data.m_Colors[vtx * colorFloats + i] for i in range(colorFloats)]
            vertex_color.data[vtx].color = color
    # Assign vertex normals
    mesh.create_normals_split()
    normals = [(0,0,0) for l in mesh.loops]
    for i, loop in enumerate(mesh.loops):
        normal = bm.verts[loop.vertex_index].normal
        normal.normalize()
        normals[i] = normal
    mesh.normals_split_custom_set(normals)
    mesh.use_auto_smooth = True   
    # Blend Shape / Shape Keys
    if data.m_Shapes.channels:
        obj.shape_key_add(name="Basis")
        keyshape_hash_tbl = dict()
        for channel in data.m_Shapes.channels:
            shape_key = obj.shape_key_add(name=channel.name)
            keyshape_hash_tbl[channel.nameHash] = channel.name
            for frameIndex in range(channel.frameIndex, channel.frameIndex + channel.frameCount):
                # fullWeight = mesh_data.m_Shapes.fullWeights[frameIndex]
                shape = data.m_Shapes.shapes[frameIndex]
                for morphedVtxIndex in range(shape.firstVertex,shape.firstVertex + shape.vertexCount):
                    morpedVtx = data.m_Shapes.vertices[morphedVtxIndex]
                    targetVtx : bpy.types.ShapeKeyPoint = shape_key.data[morpedVtx.index]
                    targetVtx.co += swizzle_vector(morpedVtx.vertex)                    
        # Like boneHash, do the same thing with blend shapes
        mesh[KEY_SHAPEKEY_NAME_HASH_TBL] = json.dumps(keyshape_hash_tbl,ensure_ascii=False)
    bm.free()      
    return mesh, obj

def import_armature(name : str, data : Armature):
    '''Imports the Armature data generated into blender

    NOTE: Unused bones will not be imported since they have identity transforms and thus
    cannot have their own head-tail vectors. It's worth noting though that they won't affect
    the mesh anyway.

    Args:
        name (str): Armature Object name
        data (Armature): Armature as genereated by previous steps
    
    Returns:
        Tuple[bpy.types.Armature, bpy.types.Object]: Created armature and its parent object
    '''
    armature = bpy.data.armatures.new(name)
    armature.display_type = 'OCTAHEDRAL'
    armature.relation_line_position = 'HEAD'

    obj = bpy.data.objects.new(name, armature)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    # HACK: *Seems like* the only useful root bone is 'Position' (which is the root of the actual skeleton)
    bone = data.root.recursive_locate_by_name('Position')
    if bone:
        # Build global transforms           
        bone.calculate_global_transforms()
        # Build bone hierarchy in blender
        for parent, child, _ in bone.dfs_generator():
            ebone = armature.edit_bones.new(child.name)
            ebone.use_local_location = True
            ebone.use_relative_parent = False                
            ebone.use_connect = False
            ebone.use_deform = True
            ebone[KEY_BINDPOSE_TRANS] = [v for v in child.get_blender_local_position()]
            ebone[KEY_BINDPOSE_QUAT] = [v for v in child.get_blender_local_rotation()]
            child.edit_bone = ebone
            # Treat the joints as extremely small bones
            # The same as https://github.com/KhronosGroup/glTF-Blender-IO/blob/2debd75ace303f3a3b00a43e9d7a9507af32f194/addons/io_scene_gltf2/blender/imp/gltf2_blender_node.py#L198
            # TODO: Alternative shapes for bones                                                
            ebone.head = child.global_transform @ Vector((0,0,0))
            ebone.tail = child.global_transform @ Vector((0,1,0))
            ebone.length = 0.01
            ebone.align_roll(child.global_transform @ Vector((0,0,1)) - ebone.head)
            if parent:
                ebone.parent = parent.edit_bone

    return armature, obj

def import_armature_physics_constraints(armature, data : Armature):
    '''Imports the rigid body constraints for the armature

    Args:
        armature (bpy.types.Object): Armature object
        data (Armature): Armature data
    '''
    PIVOT_SIZE = 0.004
    SPHERE_RADIUS_FACTOR = 1
    CAPSULE_RADIUS_FACTOR = 1
    CAPSULE_HEIGHT_FACTOR = 1
    SPRINGBONE_RADIUS_FACTOR = 1
    BBONE_SEGMENTS = 4
    bpy.context.view_layer.objects.active = armature    
    bone = data.root.recursive_locate_by_name('Position')

    target_rigid_bodies = dict()

    if bone:
        # Connect all spring bones
        # SpringBones are observed to be never animated. 
        # Connecting them will make our lives a lot eaiser
        bpy.ops.object.mode_set(mode='EDIT')
        class SpringBoneChain:
            begin : object = None
            end : object = None
        springbone_chains : Dict[str,SpringBoneChain] = dict()
        armature.data.display_type = 'BBONE'
        for parent, child, _ in bone.dfs_generator():
            if child.name in armature.data.edit_bones:
                ebone = armature.data.edit_bones[child.name]
                ebone.bbone_x = ebone.bbone_z = PIVOT_SIZE
        def connect_spring_bones(bone : Bone, parent = None):
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
                    if '_offset' in parent_bone.name and not bone.name in springbone_chains: # Keep the fisrt bone's parent. The rest are connected
                        armature.data.edit_bones.remove(armature.data.edit_bones[parent_bone.name])   
                        ebone.parent = armature.data.edit_bones[parent_bone.parent.name]
                    ebone.use_connect = True
                    scaled_segments = BBONE_SEGMENTS if ebone.length > 0.03 else 1 # XXX: Is there a better way to do this?
                    ebone.bbone_segments = scaled_segments
                    if bone.physics:
                        ebone.bbone_x = ebone.bbone_z = bone.physics.radius * SPRINGBONE_RADIUS_FACTOR
                    elif bone.parent.physics:
                        ebone.bbone_x = ebone.bbone_z = bone.parent.physics.radius * SPRINGBONE_RADIUS_FACTOR
                if not bone.children:
                    springbone_chains[parent.name].end = bone
            for child in bone.children:
                connect_spring_bones(child, parent)
        connect_spring_bones(bone)
        # XXX: PoC. Using two rigid bodies to simulate the whole chain
        # Works if...the bendy bone chain is not too long.
        # e.g. a banana (huh?)
        # Here's the link BTW https://www.youtube.com/watch?v=_QY12thfOPc&ab_channel=SouthernShotty    
        # NOTE: https://github.com/Pauan/blender-rigid-body-bones produced quite visually pleasing results
        # with the prep work done previously here.
        # I'll try to implement it later on...
        if False:
            def ensure_bone_rigidbody(name : str, is_pivot : bool, radius : float):
                bpy.ops.mesh.primitive_uv_sphere_add(radius=radius)
                obj = bpy.context.object
                obj.name = name + '_rigidbody'
                bpy.ops.rigidbody.object_add()
                obj.rigid_body.collision_shape = 'SPHERE'                            
                obj.rigid_body.type = 'ACTIVE'       
                obj.parent = armature
                if is_pivot:
                    obj.rigid_body.collision_collections[0] = False # Does not collide with anything
                    obj.rigid_body.kinematic = True
                else:                                
                    obj.rigid_body.collision_collections[0] = True # Collides with selected RBs. see below..
                    obj.rigid_body.kinematic = False
                return obj  
            def set_bone_parent(object : bpy.types.Object, bone_name : str):
                object.parent = armature
                object.parent_type = 'BONE'
                object.parent_bone = bone_name
            def set_bone_constraint(bone_name : str, target):
                pbone : bpy.types.PoseBone = armature.pose.bones[bone_name] 
                ct = pbone.constraints.new('CHILD_OF')                       
                ct.target = target
                bpy.context.active_object.data.bones.active = pbone.bone
                context_override = bpy.context.copy()
                with bpy.context.temp_override(**context_override):
                    bpy.ops.constraint.childof_set_inverse(constraint=ct.name, owner='BONE')

            for chain in springbone_chains.values():  
                bpy.ops.object.mode_set(mode='EDIT')
                ebone_begin : bpy.types.EditBone = armature.data.edit_bones[chain.begin.name]
                ebone_end : bpy.types.EditBone = armature.data.edit_bones[chain.end.name]

                pre_name = chain.begin.parent.name
                begin_name = chain.begin.name
                end_name = chain.end.name
                begin_radius = ebone_begin.bbone_x
                end_radius = ebone_end.bbone_x
                end_matrix = ebone_end.matrix
                bpy.ops.object.mode_set(mode='OBJECT')
                print('! Connecting SpringBone Chain', begin_name,end_name)
                # Create rigidbodies at the beginning and the end
                rb_begin = ensure_bone_rigidbody(begin_name, True, begin_radius)
                rb_end = ensure_bone_rigidbody(end_name, False, end_radius)
                # Both are connected to the armature. So assign arm space matrix
                set_bone_parent(rb_begin, begin_name)
                rb_end.matrix_world = end_matrix
                # Spring Constraint
                joint = bpy.data.objects.new("SpringBoneJoint", None)
                joint.empty_display_size = 0.1
                joint.empty_display_type = 'ARROWS'
                # Joint follows the pivot
                bpy.context.collection.objects.link(joint)
                set_bone_parent(joint, begin_name)
                bpy.context.view_layer.objects.active = joint    
                # Add the constraint
                bpy.ops.rigidbody.constraint_add(type='GENERIC_SPRING')
                ct = joint.rigid_body_constraint
                # Spring damping effect
                # XXX: These are not going to be accurate
                ct.use_spring_ang_x = True
                ct.use_spring_ang_y = True
                ct.use_spring_ang_z = True                        
                # Link the objects!
                joint.rigid_body_constraint.object1 = rb_begin
                joint.rigid_body_constraint.object2 = rb_end
                # Point Constraint
                joint = bpy.data.objects.new("PointBoneJoint", None)
                joint.empty_display_size = 0.1
                joint.empty_display_type = 'ARROWS'
                # Joint follows the pivot
                bpy.context.collection.objects.link(joint)
                set_bone_parent(joint, begin_name)
                bpy.context.view_layer.objects.active = joint    
                # Add the constraint
                bpy.ops.rigidbody.constraint_add(type='POINT')
                ct = joint.rigid_body_constraint            
                # Link the objects!
                joint.rigid_body_constraint.object1 = rb_begin
                joint.rigid_body_constraint.object2 = rb_end
                # Add constraints to the bones
                bpy.context.view_layer.objects.active = armature
                bpy.ops.object.mode_set(mode='POSE')
                set_bone_constraint(begin_name, rb_begin)
                set_bone_constraint(end_name, rb_end)
        
        bpy.ops.object.mode_set(mode='OBJECT')
        for parent, child, _ in bone.dfs_generator():            
            if child.physics:
                if child.physics.type & BonePhysicsType.Collider:
                    # Add colliders
                    obj = None
                    if child.physics.type == BonePhysicsType.SphereCollider:
                        bpy.ops.mesh.primitive_uv_sphere_add(radius=child.physics.radius * SPHERE_RADIUS_FACTOR)
                        obj = bpy.context.object
                        obj.name = child.name + '_rigidbody'
                        bpy.ops.rigidbody.object_add()
                        obj.rigid_body.type = 'PASSIVE'
                        obj.rigid_body.collision_shape = 'SPHERE'
                    if child.physics.type == BonePhysicsType.CapsuleCollider:
                        bpy.ops.mesh.primitive_cylinder_add(radius=child.physics.radius * CAPSULE_RADIUS_FACTOR,depth=child.physics.height * CAPSULE_HEIGHT_FACTOR)
                        obj = bpy.context.object
                        obj.name = child.name + '_rigidbody'
                        bpy.ops.rigidbody.object_add()
                        obj.rigid_body.type = 'PASSIVE'
                        obj.rigid_body.collision_shape = 'CAPSULE'
                    if obj:
                        obj.rigid_body.kinematic = True
                        obj.parent = armature
                        obj.parent_bone = child.name
                        obj.parent_type = 'BONE'             

def import_texture(name : str, data : Texture2D):
    '''Imports Texture2D assets into blender

    Args:
        name (str): asset name
        data (Texture2D): source texture

    Returns:
        bpy.types.Image: Created image
    '''
    with tempfile.NamedTemporaryFile(suffix='.bmp',delete=False) as temp:
        print('* Saving Texture', name, 'to', temp.name)
        data.image.save(temp)
        temp.close()
        img = bpy.data.images.load(temp.name, check_existing=True)        
        img.name = name
        print('* Imported Texture', name)
        return img

def load_sssekai_shader_blend():
    if not 'SekaiShaderChara' in bpy.data.materials or not 'SekaiShaderScene' in bpy.data.materials:
        print('! SekaiShader not loaded. Importing from source.')
        with bpy.data.libraries.load(SHADER_BLEND_FILE, link=False) as (data_from, data_to):
            data_to.materials = data_from.materials
            print('! Loaded shader blend file.')

def make_material_texture_node(material , ppTexture):
    texCoord = material.node_tree.nodes.new('ShaderNodeTexCoord')
    uvRemap = material.node_tree.nodes.new('ShaderNodeMapping')
    uvRemap.inputs[1].default_value[0] = ppTexture.m_Offset.X
    uvRemap.inputs[1].default_value[1] = ppTexture.m_Offset.Y
    uvRemap.inputs[3].default_value[0] = ppTexture.m_Scale.X
    uvRemap.inputs[3].default_value[1] = ppTexture.m_Scale.Y
    texture : Texture2D = ppTexture.m_Texture.read()
    texNode = material.node_tree.nodes.new('ShaderNodeTexImage')
    texNode.image = import_texture(texture.name, texture)
    material.node_tree.links.new(texCoord.outputs['UV'], uvRemap.inputs['Vector'])
    material.node_tree.links.new(uvRemap.outputs['Vector'], texNode.inputs['Vector'])
    return texNode

def import_character_material(name : str,data : Material):
    '''Imports Material assets for Characters into blender. 
    
    Args:
        name (str): material name
        data (Material): UnityPy Material

    Returns:
        bpy.types.Material: Created material        
    '''
    load_sssekai_shader_blend()
    material = bpy.data.materials["SekaiShaderChara"].copy()
    material.name = name
    sekaiShader = material.node_tree.nodes['Group']
    textures = data.m_SavedProperties.m_TexEnvs
    if '_MainTex' in textures:
        mainTex = make_material_texture_node(material, textures['_MainTex'])
        material.node_tree.links.new(mainTex.outputs['Color'], sekaiShader.inputs[0])
    if '_ShadowTex' in textures:
        shadowTex = make_material_texture_node(material, textures['_ShadowTex'])
        material.node_tree.links.new(shadowTex.outputs['Color'], sekaiShader.inputs[1])
    if '_ValueTex' in textures:
        valueTex = make_material_texture_node(material, textures['_ValueTex'])
        material.node_tree.links.new(valueTex.outputs['Color'], sekaiShader.inputs[2])
    return material

def import_scene_material(name : str,data : Material):
    '''Imports Material assets for Non-Character (i.e. Stage) into blender. 
    
    Args:
        name (str): material name
        data (Material): UnityPy Material

    Returns:
        bpy.types.Material: Created material        
    '''
    load_sssekai_shader_blend()
    material = bpy.data.materials["SekaiShaderScene"].copy()
    material.name = name
    sekaiShader = material.node_tree.nodes['Group']
    textures = data.m_SavedProperties.m_TexEnvs
    if '_MainTex' in textures:
        mainTex = make_material_texture_node(material, textures['_MainTex'])
        material.node_tree.links.new(mainTex.outputs['Color'], sekaiShader.inputs[0])
    if '_LightMapTex' in textures:
        lightMapTex = make_material_texture_node(material, textures['_LightMapTex'])
        material.node_tree.links.new(lightMapTex.outputs['Color'], sekaiShader.inputs[1])
    return material
