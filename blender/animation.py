from . import *

def time_to_frame(time : float, frame_offset : int):
    return int(time * bpy.context.scene.render.fps) + 1 + frame_offset

def retrive_action(object : bpy.types.Object):
    '''Retrieves the action bound to an object, if any'''
    return object.animation_data.action if object.animation_data else None

def ensure_action(object, name : str, always_create_new : bool):
    '''Creates (or retrieves) an action for an object, whilst ensuring that the action is bound to animation_data'''
    existing_action = retrive_action(object)
    if always_create_new or not existing_action:
        object.animation_data_clear()
        object.animation_data_create()
        action = bpy.data.actions.new(name)
        object.animation_data.action = action
        return action
    else:
        return object.animation_data.action

def create_action(name : str):
    action = bpy.data.actions.new(name)
    return action

def apply_action(action : bpy.types.Action, object : bpy.types.Object, use_nla : bool = False):    
    '''Applies an action to an object'''
    if not use_nla:
        object.animation_data_clear()
        object.animation_data_create()
        object.animation_data.action = action
    else:
        nla_track = object.animation_data.nla_tracks.new()
        nla_track.name = action.name
        nla_track.strips.new(action.name, 0, action)        

def import_fcurve(action : bpy.types.Action, data_path : str , values : list, frames : list, num_curves : int = 1, interpolation : str = 'BEZIER', tangents_in : list = [], tangents_out : list = []):
    '''Imports an Fcurve into an action

    Args:
        action (bpy.types.Action): target action. keyframes will be merged into this action.
        data_path (str): data path
        values (list): values. size must be that of frames
        frames (list): frame indices. size must be that of values
        num_curves (int, optional): number of curves. e.g. with translation (X,Y,Z) you'd want 3. Defaults to 1.
        interpolation (str, optional): interpolation type. Defaults to 'BEZIER'.
        tagents_in (list, optional): in tangents (i.e. inSlope). Defaults to [].
        tagents_out (list, optional): out tangents (i.e. outSlope). Defaults to [].
    '''
    valueIterable = type(values[0])
    valueIterable = valueIterable != float and valueIterable != int
    assert valueIterable or (not valueIterable and num_curves == 1), "Cannot import multiple curves for non-iterable values"
    fcurve = [action.fcurves.find(data_path=data_path, index=i) or action.fcurves.new(data_path=data_path, index=i) for i in range(num_curves)]
    for i in range(num_curves):
        curve_data = [0] * (len(frames) * 2)
        curve_data[::2] = frames
        curve_data[1::2] = [v[i] if valueIterable else v for v in values]
        if len(fcurve[i].keyframe_points) > 0:
            # Has existing data. Always append them
            existing_data = [0] * (len(fcurve[i].keyframe_points) * 2)
            fcurve[i].keyframe_points.foreach_get('co', existing_data)
            curve_data = existing_data + curve_data
        fcurve[i].keyframe_points.clear()
        fcurve[i].keyframe_points.add(len(curve_data) // 2)
        fcurve[i].keyframe_points.foreach_set('co', curve_data)        
        ipo = bpy.types.Keyframe.bl_rna.properties['interpolation'].enum_items[interpolation].value
        fcurve[i].keyframe_points.foreach_set('interpolation', [ipo] * len(fcurve[i].keyframe_points))
        if tangents_in or tangents_out:
            free_handle = bpy.types.Keyframe.bl_rna.properties['handle_left_type'].enum_items['FREE'].value
            free_handles = [free_handle] * len(fcurve[i].keyframe_points)
            handle_data = [0] * (len(frames) * 2)            
            if tangents_in:
                fcurve[i].keyframe_points.foreach_set('handle_left_type', free_handles)
                handle_data[::2] = [f - 1 for f in frames] 
                # Fixed 1 unit on the curve for now since that's what Unity does
                handle_data[1::2] = [v[i] if valueIterable else v for v in tangents_in]
                fcurve[i].keyframe_points.foreach_set('handle_left', handle_data)
            if tangents_out:
                fcurve[i].keyframe_points.foreach_set('handle_right_type', free_handles)
                handle_data[::2] = [f + 1 for f in frames]
                handle_data[1::2] = [v[i] if valueIterable else v for v in tangents_out]
                fcurve[i].keyframe_points.foreach_set('handle_right', handle_data)
        fcurve[i].update()
    return fcurve

def import_fcurve_quatnerion(action : bpy.types.Action, data_path : str , values : List[BlenderQuaternion], frames : list, interpolation : str = 'LINEAR'):
    '''Imports an Fcurve into an action, specialized for quaternions    

    Args:
        action (bpy.types.Action): target action. keyframes will be merged into this action.
        data_path (str): data path
        values (List[BlenderQuaternion]): values. size must be that of frames
        frames (list): frame indices. size must be that of values
        interpolation (str, optional): interpolation type. Defaults to 'LINEAR'.
    
    Note:
        * The import function ensures that the quaternions in the curve are compatible with each other 
            (i.e. lerping between them will not cause flips and the shortest path will always be taken).
        * Note it's *LERP* not *SLERP*. Blender fcurves does not specialize in quaternion interpolation.
        * Hence, with `interpolation`, you should always use `LINEAR` for the most accurate results.
    '''
    fcurve = [action.fcurves.find(data_path=data_path, index=i) or action.fcurves.new(data_path=data_path, index=i) for i in range(4)]
    curve_datas = list()
    for i in range(4):
        curve_data = [0] * (len(frames) * 2)
        curve_data[::2] = frames
        curve_data[1::2] = [v[i] for v in values]
        if len(fcurve[i].keyframe_points) > 0:
            # Has existing data. Always append them
            existing_data = [0] * (len(fcurve[i].keyframe_points) * 2)
            fcurve[i].keyframe_points.foreach_get('co', existing_data)
            curve_data = existing_data + curve_data
        curve_datas.append(curve_data)
    curve_quats = [BlenderQuaternion((curve_datas[0][i],curve_datas[1][i],curve_datas[2][i],curve_datas[3][i])) for i in range(1, len(curve_datas[i]), 2)]
    for i in range(1,len(curve_quats)):
        curve_quats[i].make_compatible(curve_quats[i-1])
    for i in range(4):
        curve_datas[i][1::2] = [v[i] for v in curve_quats]
    for i in range(4):
        fcurve[i].keyframe_points.clear()
        fcurve[i].keyframe_points.add(len(curve_datas[i]) // 2)
        fcurve[i].keyframe_points.foreach_set('co', curve_datas[i])
        ipo = bpy.types.Keyframe.bl_rna.properties['interpolation'].enum_items[interpolation].value
        fcurve[i].keyframe_points.foreach_set('interpolation', [ipo] * len(fcurve[i].keyframe_points))
        fcurve[i].update()
    return fcurve


def load_armature_animation(name : str, data : Animation, dest_arma : bpy.types.Object, frame_offset : int, action : bpy.types.Action = None):
    '''Converts an Animation object into Blender Action **without** applying it to the armature

    Args:
        name (str): name of the action
        data (Animation): animation data
        dest_arma (bpy.types.Object): target armature object
        frame_offset (int): frame offset
        action (bpy.types.Action, optional): existing action to append to. Defaults

    Returns:
        bpy.types.Action: the created action
    '''
    bone_table = json.loads(dest_arma.data[KEY_BONE_NAME_HASH_TBL])
    bpy.ops.object.mode_set(mode='EDIT')
    # Collect bone space <-> local space transforms
    local_space_trans_rot = dict() # i.e. parent space
    for bone in dest_arma.data.edit_bones: # Must be done in edit mode        
        local_mat = (bone.parent.matrix.inverted() @ bone.matrix) if bone.parent else Matrix()
        local_space_trans_rot[bone.name] = (local_mat.to_translation(), local_mat.to_quaternion())
    # from glTF-Blender-IO:
    # ---
    # We have the final TRS of the bone in values. We need to give
    # the TRS of the pose bone though, which is relative to the edit
    # bone.
    #
    #     Final = EditBone * PoseBone
    #   where
    #     Final =    Trans[ft] Rot[fr] Scale[fs]
    #     EditBone = Trans[et] Rot[er]
    #     PoseBone = Trans[pt] Rot[pr] Scale[ps]
    #
    # Solving for PoseBone gives
    #
    #     pt = Rot[er^{-1}] (ft - et)
    #     pr = er^{-1} fr
    #     ps = fs 
    # ---
    def to_pose_quaternion(name, quat : BlenderQuaternion):
        etrans, erot = local_space_trans_rot[name]
        erot_inv = erot.conjugated()
        return erot_inv @ quat
    def to_pose_translation(name : bpy.types.PoseBone, vec : Vector):
        etrans, erot = local_space_trans_rot[name]
        erot_inv = erot.conjugated()
        return erot_inv @ (vec - etrans)
    def to_pose_euler(name : bpy.types.PoseBone, euler : Euler):
        etrans, erot = local_space_trans_rot[name]
        erot_inv = erot.conjugated()
        result = erot_inv @ euler.to_quaternion()
        result = result.to_euler('XYZ')
        return result
    # Reset the pose 
    bpy.ops.object.mode_set(mode='POSE')
    bpy.ops.pose.select_all(action='SELECT')
    bpy.ops.pose.transforms_clear()
    bpy.ops.pose.select_all(action='DESELECT')
    # Setup actions
    action = action or create_action(name)
    for bone_hash, track in data.TransformTracks[TransformType.Rotation].items():
        # Quaternion rotations
        if str(bone_hash) in bone_table:
            bone_name = bone_table[str(bone_hash)]            
            bone = dest_arma.pose.bones.get(bone_name,None)
            if not bone: 
                print("* WARNING: [Rotation] Bone %s not found in pose bones" % bone_name)
                continue
            bone.rotation_mode = 'QUATERNION'       
            values = [to_pose_quaternion(bone_name, swizzle_quaternion(keyframe.value)) for keyframe in track.Curve]
            frames = [time_to_frame(keyframe.time, frame_offset) for keyframe in track.Curve]
            import_fcurve_quatnerion(action,'pose.bones["%s"].rotation_quaternion' % bone_name, values, frames)
        else:
            print("* WARNING: [Rotation] Bone hash %s not found in bone table" % bone_hash)
    for bone_hash, track in data.TransformTracks[TransformType.EulerRotation].items():
        # Euler rotations
        if str(bone_hash) in bone_table:
            bone_name = bone_table[str(bone_hash)]
            bone = dest_arma.pose.bones.get(bone_name,None)
            if not bone: 
                print("* WARNING: [Rotation Euler] Bone %s not found in pose bones" % bone_name)
                continue
            bone.rotation_mode = 'YXZ'
            values = [to_pose_euler(bone_name, swizzle_euler(keyframe.value)) for keyframe in track.Curve]
            frames = [time_to_frame(keyframe.time, frame_offset) for keyframe in track.Curve]
            import_fcurve(action,'pose.bones["%s"].rotation_euler' % bone_name, values, frames, 3)            
        else:
            print("* WARNING: [Rotation Euler] Bone hash %s not found in bone table" % bone_hash)
    for bone_hash, track in data.TransformTracks[TransformType.Translation].items():
        # Translations
        if str(bone_hash) in bone_table:
            bone_name = bone_table[str(bone_hash)]
            bone = dest_arma.pose.bones.get(bone_name,None)
            if not bone: 
                print("* WARNING: [Translation] Bone %s not found in pose bones" % bone_name)
                continue
            values = [to_pose_translation(bone_name, swizzle_vector(keyframe.value)) for keyframe in track.Curve]
            frames = [time_to_frame(keyframe.time, frame_offset) for keyframe in track.Curve]
            import_fcurve(action,'pose.bones["%s"].location' % bone_name, values, frames, 3)
        else:
            print("* WARNING: [Translation] Bone hash %s not found in bone table" % bone_hash)
    for bone_hash, track in data.TransformTracks[TransformType.Scaling].items():
        # Scale
        if str(bone_hash) in bone_table:
            bone_name = bone_table[str(bone_hash)]
            bone = dest_arma.pose.bones.get(bone_name,None)
            if not bone: 
                print("* WARNING: [Scale] Bone %s not found in pose bones" % bone_name)
                continue
            values = [swizzle_vector_scale(keyframe.value) for keyframe in track.Curve]
            frames = [time_to_frame(keyframe.time, frame_offset) for keyframe in track.Curve]
            import_fcurve(action,'pose.bones["%s"].scale' % bone_name, values, frames, 3)        
        else:
            print("* WARNING: [Scale] Bone hash %s not found in bone table" % bone_hash)
    return action

def load_keyshape_animation(name : str, data : Animation, dest_mesh : bpy.types.Object, frame_offset : int, action : bpy.types.Action = None):
    '''Converts an Animation object into Blender Action **without** applying it to the mesh
    
    Args:
        name (str): name of the action
        data (Animation): animation data
        dest_mesh (bpy.types.Object): target mesh object
        frame_offset (int): frame offset
        action (bpy.types.Action, optional): existing action to append to. Defaults to None

    Returns:
        bpy.types.Action: the created action
    
    Note:
        KeyShape value range [0,100]
    '''
    mesh = dest_mesh.data
    assert KEY_SHAPEKEY_NAME_HASH_TBL in mesh, "Shape Key table not found. You can only import blend shape animations on meshes with blend shapes!"
    assert BLENDSHAPES_CRC in data.FloatTracks, "No blend shape animation found!"
    keyshape_table = json.loads(mesh[KEY_SHAPEKEY_NAME_HASH_TBL])
    action = create_action(name)
    for attrCRC, track in data.FloatTracks[BLENDSHAPES_CRC].items():
        bsName = keyshape_table[str(attrCRC)]
        import_fcurve(action,'key_blocks["%s"].value' % bsName, [keyframe.value / 100.0 for keyframe in track.Curve], [time_to_frame(keyframe.time, frame_offset) for keyframe in track.Curve])
    return action

def prepare_camera_rig(camera : bpy.types.Object):
    if not camera.parent or not KEY_CAMERA_RIG in camera.parent:
        # The 'rig' Offsets the camera's look-at direction w/o modifying the Euler angles themselves, which
        # would otherwise cause interpolation issues.
        # This is simliar to how mmd_tools handles camera animations.
        #
        # We also store the FOV in the X scale of the parent object so that it's easy to interpolate
        # and we'd only need one action for the entire animation.        
        rig = create_empty('Camera Rig', camera.parent)
        rig[KEY_CAMERA_RIG] = "<marker>"
        camera.parent = rig
        camera.location = Vector((0,0,0))
        camera.rotation_euler = Euler((math.radians(90),0,math.radians(180)))
        camera.rotation_mode = 'XYZ'
        camera.scale = Vector((1,1,1))
        # Driver for FOV
        driver = camera.data.driver_add('lens')
        driver.type = 'SCRIPTED'
        var_scale = driver.variables.new()
        var_scale.name = 'fov'
        var_scale.type = 'TRANSFORMS'
        var_scale.targets[0].id = rig
        var_scale.targets[0].transform_space = 'WORLD_SPACE'
        var_scale.targets[0].transform_type = 'SCALE_X'
        driver.expression = 'fov'
        print('* Created Camera Rig for camera',camera.name)    
        return rig
    return camera.parent

def load_camera_animation(name : str, data : Animation, camera : bpy.types.Object, frame_offset : int, scaling_factor : Vector, scaling_offset : Vector, fov_offset : float, action : bpy.types.Action = None): 
    '''Converts an Animation object into Blender Action **without** applying it to the camera

    Args:
        name (str): name of the action
        data (Animation): animation data
        camera (bpy.types.Object): target camera object
        frame_offset (int): frame offset        
        scaling_factor (Vector): scale factor
        scaling_offset (Vector): scale offset
        fov_offset (float): offset to the FOV
        action (bpy.types.Action, optional): existing action to append to. Defaults to None

    Returns:
        bpy.types.Action: the created action
    '''
    rig = prepare_camera_rig(camera)
    rig.rotation_mode = 'YXZ'
    action = action or create_action(name)
    def swizzle_translation_camera(vector : Vector):
        result = swizzle_vector(vector)
        result *= Vector(scaling_factor)
        result += Vector(scaling_offset)        
        return result    
    def swizzle_euler_camera(euler : Euler):
        result = swizzle_euler(euler)
        result.y *= -1 # Invert Y (Unity's Roll)      
        return result
    def fov_to_focal_length(fov : float):
        # FOV = 2 arctan [sensorSize/(2*focalLength)] 
        # focalLength = sensorSize / (2 * tan(FOV/2))        
        # fov -> Vertical FOV, which is the default in Unity
        fov += fov_offset
        return camera.data.sensor_height / (2 * math.tan(math.radians(fov) / 2))
    if CAMERA_TRANS_ROT_CRC_MAIN in data.TransformTracks[TransformType.EulerRotation]:
        print('* Found Camera Rotation track')
        curve = data.TransformTracks[TransformType.EulerRotation][CAMERA_TRANS_ROT_CRC_MAIN].Curve
        import_fcurve(
            action,'rotation_euler', 
            [swizzle_euler_camera(keyframe.value) for keyframe in curve], 
            [time_to_frame(keyframe.time,frame_offset) for keyframe in curve], 
            3, 'BEZIER',                         
            # [swizzle_euler(keyframe.inSlope) for keyframe in curve], 
            # [swizzle_euler(keyframe.outSlope) for keyframe in curve]
        )        
    if CAMERA_TRANS_ROT_CRC_MAIN in data.TransformTracks[TransformType.Translation]:
        print('* Found Camera Translation track, scaling=',scaling_factor)
        curve = data.TransformTracks[TransformType.Translation][CAMERA_TRANS_ROT_CRC_MAIN].Curve
        import_fcurve(
            action,'location', 
            [swizzle_translation_camera(keyframe.value) for keyframe in curve], 
            [time_to_frame(keyframe.time,frame_offset) for keyframe in curve],
            3, 'BEZIER',
            # [swizzle_translation_camera(keyframe.inSlope) for keyframe in curve],
            # [swizzle_translation_camera(keyframe.outSlope) for keyframe in curve]
        )
    if CAMERA_TRANS_SCALE_EXTRA_CRC_EXTRA in data.TransformTracks[TransformType.Translation]:
        print('* Found Camera FOV track')
        camera.data.lens_unit = 'MILLIMETERS'        
        curve = data.TransformTracks[TransformType.Translation][CAMERA_TRANS_SCALE_EXTRA_CRC_EXTRA].Curve        
        import_fcurve(
            action,'scale', # FOV on the X scale
            [(fov_to_focal_length(keyframe.value.Z * 100),1,1) for keyframe in curve],
            [time_to_frame(keyframe.time, frame_offset) for keyframe in curve], 
            3, 'BEZIER',
            # [fov_to_focal_length(keyframe.inSlope.Z * 100) for keyframe in curve],
            # [fov_to_focal_length(keyframe.outSlope.Z * 100) for keyframe in curve]
        )

def import_articulation_animation(name : str, data : Animation, dest_arma : bpy.types.Object, frame_offset : int, always_create_new : bool):
    '''Converts an Animation object into Blender Action(s), **whilst applying it to the articulation hierarchy**
       
    In this case there would be seperate actions for **each** joint in the hierarchy.

    Support for exportable Actions (for usage with NLA Clips, for example) is not planned due to this approach.

    Args:
        name (str): name of the action
        data (Animation): animation data
        dest_arma (bpy.types.Object): target joint (Empty) hierarchy's top-most parent object
        frame_offset (int): frame offset
        always_create_new (bool): whether to always create a new action
    '''
    joint_table = json.loads(dest_arma[KEY_ARTICULATION_NAME_HASH_TBL])
    joint_obj = {obj[KEY_JOINT_BONE_NAME]:obj for obj in dest_arma.children_recursive if obj.type == 'EMPTY' and KEY_JOINT_BONE_NAME in obj}
    for bone_hash, track in data.TransformTracks[TransformType.Rotation].items():
        bone_name = joint_table.get(str(bone_hash),None)
        obj = joint_obj.get(bone_name,None)
        if obj:
            action = ensure_action(obj, name, always_create_new)
            obj.rotation_mode = 'QUATERNION'
            values = [swizzle_quaternion(keyframe.value) for keyframe in track.Curve]                    
            frames = [time_to_frame(keyframe.time, frame_offset) for keyframe in track.Curve]
            import_fcurve_quatnerion(action,'rotation_quaternion', values, frames)
        else:
            print("* WARNING: [Rotation] Bone hash %s not found in joint table" % bone_hash)
    for bone_hash, track in data.TransformTracks[TransformType.EulerRotation].items():
        bone_name = joint_table.get(str(bone_hash),None)
        obj = joint_obj.get(bone_name,None)
        if obj:
            action = ensure_action(obj, name, always_create_new)
            obj.rotation_mode = 'YXZ'
            values = [swizzle_euler(keyframe.value) for keyframe in track.Curve]
            frames = [time_to_frame(keyframe.time, frame_offset) for keyframe in track.Curve]
            import_fcurve(action,'rotation_euler', values, frames, 3)
        else:
            print("* WARNING: [Rotation Euler] Bone hash %s not found in joint table" % bone_hash)
    for bone_hash, track in data.TransformTracks[TransformType.Translation].items():
        bone_name = joint_table.get(str(bone_hash),None)
        obj = joint_obj.get(bone_name,None)
        if obj:
            action = ensure_action(obj, name, always_create_new)
            values = [swizzle_vector(keyframe.value) for keyframe in track.Curve]
            frames = [time_to_frame(keyframe.time, frame_offset) for keyframe in track.Curve]
            import_fcurve(action,'location', values, frames, 3)
        else:
            print("* WARNING: [Translation] Bone hash %s not found in joint table" % bone_hash)
    for bone_hash, track in data.TransformTracks[TransformType.Scaling].items():
        bone_name = joint_table.get(str(bone_hash),None)
        obj = joint_obj.get(bone_name,None)
        if obj:
            action = ensure_action(obj, name, always_create_new)
            values = [swizzle_vector_scale(keyframe.value) for keyframe in track.Curve]
            frames = [time_to_frame(keyframe.time, frame_offset) for keyframe in track.Curve]
            import_fcurve(action,'scale', values, frames, 3)
        else:
            print("* WARNING: [Scale] Bone hash %s not found in joint table" % bone_hash)
    return action