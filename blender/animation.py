from . import *

def time_to_frame(time : float, frame_offset : int):
    return int(time * bpy.context.scene.render.fps) + 1 + frame_offset

def ensure_action(object, name : str, always_create_new : bool):
    if always_create_new or not object.animation_data or not object.animation_data.action:
        object.animation_data_clear()
        object.animation_data_create()
        action = bpy.data.actions.new(name)
        object.animation_data.action = action
        return action
    else:
        return object.animation_data.action

def import_fcurve(action : bpy.types.Action, data_path : str , values : list, frames : list, num_curves : int = 1):
    '''Imports an Fcurve into an action

    Args:
        action (bpy.types.Action): target action
        data_path (str): data path
        values (list): values. size must be that of frames
        frames (list): frame indices. size must be that of values
        num_curves (int, optional): number of curves. e.g. with quaternion (W,X,Y,Z) you'd want 4. Defaults to 1.
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
        fcurve[i].update()

def import_armature_animation(name : str, data : Animation, dest_arma : bpy.types.Object, frame_offset : int, always_create_new : bool):
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
    action = ensure_action(dest_arma, name, always_create_new)
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
            # Ensure minimum rotation path (i.e. neighboring quats dots >= 0)
            for i in range(0,len(values) - 1):
                if values[i].dot(values[i+1]) < 0:
                    values[i+1] = -values[i+1]
            frames = [time_to_frame(keyframe.time, frame_offset) for keyframe in track.Curve]
            import_fcurve(action,'pose.bones["%s"].rotation_quaternion' % bone_name, values, frames, 4)
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
            bone.rotation_mode = 'XZY'
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

def import_articulation_animation(name : str, data : Animation, dest_arma : bpy.types.Object, frame_offset : int, always_create_new : bool):
    joint_table = json.loads(dest_arma[KEY_ARTICULATION_NAME_HASH_TBL])
    joint_obj = {obj[KEY_JOINT_BONE_NAME]:obj for obj in dest_arma.children_recursive if obj.type == 'EMPTY' and KEY_JOINT_BONE_NAME in obj}
    if always_create_new:
        for obj in joint_obj.values():
            obj.animation_data_clear()
            obj.animation_data_create()
    for bone_hash, track in data.TransformTracks[TransformType.Rotation].items():
        bone_name = joint_table.get(str(bone_hash),None)
        obj = joint_obj.get(bone_name,None)
        if obj:
            action = ensure_action(obj, name, False)
            obj.rotation_mode = 'QUATERNION'
            values = [swizzle_quaternion(keyframe.value) for keyframe in track.Curve]      
            frames = [time_to_frame(keyframe.time, frame_offset) for keyframe in track.Curve]
            import_fcurve(action,'rotation_quaternion', values, frames, 4)
        else:
            print("* WARNING: [Rotation] Bone hash %s not found in joint table" % bone_hash)
    for bone_hash, track in data.TransformTracks[TransformType.EulerRotation].items():
        bone_name = joint_table.get(str(bone_hash),None)
        obj = joint_obj.get(bone_name,None)
        if obj:
            action = ensure_action(obj, name, False)
            obj.rotation_mode = 'XZY'
            values = [swizzle_euler(keyframe.value) for keyframe in track.Curve]
            frames = [time_to_frame(keyframe.time, frame_offset) for keyframe in track.Curve]
            import_fcurve(action,'rotation_euler', values, frames, 3)
        else:
            print("* WARNING: [Rotation Euler] Bone hash %s not found in joint table" % bone_hash)
    for bone_hash, track in data.TransformTracks[TransformType.Translation].items():
        bone_name = joint_table.get(str(bone_hash),None)
        obj = joint_obj.get(bone_name,None)
        if obj:
            action = ensure_action(obj, name, False)
            values = [swizzle_vector(keyframe.value) for keyframe in track.Curve]
            frames = [time_to_frame(keyframe.time, frame_offset) for keyframe in track.Curve]
            import_fcurve(action,'location', values, frames, 3)
        else:
            print("* WARNING: [Translation] Bone hash %s not found in joint table" % bone_hash)
    for bone_hash, track in data.TransformTracks[TransformType.Scaling].items():
        bone_name = joint_table.get(str(bone_hash),None)
        obj = joint_obj.get(joint_table[str(bone_hash)],None)
        if obj:
            action = ensure_action(obj, name, False)
            values = [swizzle_vector_scale(keyframe.value) for keyframe in track.Curve]
            frames = [time_to_frame(keyframe.time, frame_offset) for keyframe in track.Curve]
            import_fcurve(action,'scale', values, frames, 3)
        else:
            print("* WARNING: [Scale] Bone hash %s not found in joint table" % bone_hash)

def import_keyshape_animation(name : str, data : Animation, dest_mesh : bpy.types.Object, frame_offset : int, always_create_new : bool):
    mesh = dest_mesh.data
    assert KEY_SHAPEKEY_NAME_HASH_TBL in mesh, "Shape Key table not found. You can only import blend shape animations on meshes with blend shapes!"
    assert BLENDSHAPES_UNK_CRC in data.FloatTracks, "No blend shape animation found!"
    keyshape_table = json.loads(mesh[KEY_SHAPEKEY_NAME_HASH_TBL])
    action = ensure_action(mesh.shape_keys, name, always_create_new)
    for attrCRC, track in data.FloatTracks[BLENDSHAPES_UNK_CRC].items():
        bsName = keyshape_table[str(attrCRC)]
        import_fcurve(action,'key_blocks["%s"].value' % bsName, [keyframe.value / 100.0 for keyframe in track.Curve], [time_to_frame(keyframe.time, frame_offset) for keyframe in track.Curve])

def import_camera_animation(name : str, data : Animation, camera : bpy.types.Object, frame_offset : int, always_create_new : bool):
    action = ensure_action(camera, name, always_create_new)
    camera.rotation_mode = 'XZY'
    def swizzle_euler_camera(euler : Euler):
        # Unity camera resets by viewing at Z+, which is the front direction
        # Blenders looks at -Z, which is its down direction
        offset = Euler((math.radians(90),0,math.radians(180)),'XZY')
        euler = Euler(swizzle_euler(euler),'XZY')
        offset.rotate(euler)
        return offset
    def swizzer_translation_camera(vector : Vector):
        result = swizzle_vector(vector)
        return result
    if CAMERA_UNK_CRC in data.TransformTracks[TransformType.EulerRotation]:
        curve = data.TransformTracks[TransformType.EulerRotation][CAMERA_UNK_CRC].Curve
        import_fcurve(action,'rotation_euler', [swizzle_euler_camera(keyframe.value) for keyframe in curve], [time_to_frame(keyframe.time,frame_offset) for keyframe in curve], 3)        
    
    if CAMERA_UNK_CRC in data.TransformTracks[TransformType.Translation]:
        curve = data.TransformTracks[TransformType.Translation][CAMERA_UNK_CRC].Curve
        import_fcurve(action,'location', [swizzer_translation_camera(keyframe.value) for keyframe in curve], [time_to_frame(keyframe.time,frame_offset) for keyframe in curve], 3)     

def import_camera_fov_animation(name : str, curve : List[KeyFrame], camera : bpy.types.Object, frame_offset : int, always_create_new : bool):
    action = ensure_action(camera, name, always_create_new)
    camera.data.lens_unit = 'MILLIMETERS'
    def fov_to_focal_length(fov : float):
        # FOV = 2 arctan [sensorSize/(2*focalLength)] 
        # focalLength = sensorSize / (2 * tan(FOV/2))
        print(fov)
        return camera.data.sensor_width / (2 * math.tan(math.radians(fov) / 2))
    # FOV
    import_fcurve(action,'data.lens',[fov_to_focal_length(keyframe.value) for keyframe in curve],[time_to_frame(keyframe.time, frame_offset) for keyframe in curve], 1)