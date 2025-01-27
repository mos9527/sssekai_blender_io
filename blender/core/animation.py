import bpy
import logging, json, math
from typing import List
from sssekai.unity.AnimationClip import (
    Animation,
    Interpolation,
    Curve,
    kBindTransformEuler,
    kBindTransformPosition,
    kBindTransformRotation,
    kBindTransformScale,
)
from .math import (
    blEuler,
    blQuaternion,
    blVector,
    blMatrix,
    swizzle_euler,
    swizzle_quaternion,
    swizzle_vector,
    swizzle_vector_scale,
)
from .helpers import create_empty, time_to_frame, ensure_action, create_action
from .consts import *
from .. import logger

BEZIER_FREE = (
    bpy.types.Keyframe.bl_rna.properties["handle_left_type"].enum_items["FREE"].value
)


def interpolation_to_blender(ipo: Interpolation):
    return (
        bpy.types.Keyframe.bl_rna.properties["interpolation"]
        .enum_items[
            {
                Interpolation.Constant: "CONSTANT",
                Interpolation.Hermite: "LINEAR",
                Interpolation.HermiteOrLinear: "BEZIER",
                # Blender seem to use the left key value for the interpolation too
                Interpolation.Stepped: "CONSTANT",
            }[ipo]
        ]
        .value
    )


def import_curve(
    action: bpy.types.Action,
    data_path: str,
    curve: Curve,
    bl_values: List[float | blEuler | blVector],
    is_scale: bool = False,
):
    """Creates an arbitrary amount of FCurves for a sssekai Curve

    Args:
        action (bpy.types.Action): target action.
        data_path (str): data path
        curve (Curve): curve data
        bl_values (List[float | blEuler | blVector | blQuaternion]): values in Blender types
    """
    num_curves = 1
    bl_inSlopes = []
    bl_outSlopes = []
    # Slope values are in Blender's local space though should be unaffected
    # by the pose space transform since it's affine.
    # Only swizzling is needed since it's elementary matrix math which is not affine.
    # The same applies to translation and scale
    if type(bl_values[0]) == blEuler:
        num_curves = 3
        bl_inSlopes = [swizzle_euler(k.inSlope) for k in curve.Data]
        bl_outSlopes = [swizzle_euler(k.outSlope) for k in curve.Data]
    elif type(bl_values[0]) == blVector:
        num_curves = 3
        if not is_scale:
            bl_inSlopes = [swizzle_vector(k.inSlope) for k in curve.Data]
            bl_outSlopes = [swizzle_vector(k.outSlope) for k in curve.Data]
        else:
            bl_inSlopes = [swizzle_vector_scale(k.inSlope) for k in curve.Data]
            bl_outSlopes = [swizzle_vector_scale(k.outSlope) for k in curve.Data]
    elif type(bl_values[0]) == blQuaternion:
        num_curves = 4
        bl_inSlopes = [swizzle_quaternion(k.inSlope) for k in curve.Data]
        bl_outSlopes = [swizzle_quaternion(k.outSlope) for k in curve.Data]
    elif type(bl_values[0]) == float:
        num_curves = 1
        bl_inSlopes = [keyframe.inSlope for keyframe in curve.Data]
        bl_outSlopes = [keyframe.outSlope for keyframe in curve.Data]
    else:
        raise NotImplementedError("Unsupported value type")
    frames = [time_to_frame(keyframe.time) for keyframe in curve.Data]
    fcurve = [
        action.fcurves.new(data_path=data_path, index=i) for i in range(num_curves)
    ]

    for i in range(num_curves):
        curve_data = [0] * (len(frames) * 2)
        curve_data[::2] = frames
        curve_data[1::2] = [v[i] if num_curves > 1 else v for v in bl_values]

        fcurve[i].keyframe_points.clear()
        fcurve[i].keyframe_points.add(len(frames))
        fcurve[i].keyframe_points.foreach_set("co", curve_data)
        # Setup interpolation
        fcurve[i].keyframe_points.foreach_set(
            "interpolation",
            [
                interpolation_to_blender(
                    keyframe.interpolation_segment(keyframe, keyframe.next)[i]
                )
                for keyframe in curve.Data
            ],
        )
        # Setup Hermite to cubic Bezier CPs
        free_handles = [BEZIER_FREE] * len(frames)
        fcurve[i].keyframe_points.foreach_set("handle_left_type", free_handles)
        fcurve[i].keyframe_points.foreach_set("handle_right_type", free_handles)
        p1 = [0] * (len(frames) * 2)
        p2 = [0] * (len(frames) * 2)
        # Cubic Bezier H(t) = (1-t)^3 * P0 + 3(1-t)^2 * t * P1 + 3(1-t) * t^2 * P2 + t^3 * P3
        # H'(t) = 3(1-t)^2 * (P1 - P0) + 6(1-t) * t * (P2 - P1) + 3t^2 * (P3 - P2)
        # H'(0) = 3(P1 - P0) = m0 \therefore P1 = P0 + m0/3
        # H'(1) = 3(P3 - P2) = m1 \therefore P2 = P3 - m1/3
        # This is also where the rule of 1/3rd comes from
        delta_t_3 = lambda keyframe: (
            ((keyframe.next.time - keyframe.time) if keyframe.next else 0) / 3
        )
        p1[::2] = [time_to_frame(k.time + delta_t_3(k)) for k in curve.Data]
        p1[1::2] = [bl_values[i] + k * delta_t_3(k) for i, k in enumerate(bl_outSlopes)]
        p2[::2] = [time_to_frame(k.time - delta_t_3(k)) for k in curve.Data]
        p2[1::2] = [bl_values[i] - k * delta_t_3(k) for i, k in enumerate(bl_inSlopes)]
        fcurve[i].keyframe_points.foreach_set("handle_left", p2)
        fcurve[i].keyframe_points.foreach_set("handle_right", p1)
        fcurve[i].update()


def import_float_curve(
    action: bpy.types.Action,
    data_path: str,
    curve: Curve,
):
    bl_values = [k.value for k in curve.Data]
    return import_curve(action, data_path, curve, bl_values)


def import_curve_quatnerion(
    action: bpy.types.Action,
    data_path: str,
    curve: Curve,
    bl_values: List[blQuaternion],
    interpolation: str = "LINEAR",
):
    """Creates 4 FCurves (x,y,z,w) for a sssekai Quaternion Curve

    Args:
        action (bpy.types.Action): target action.
        data_path (str): data path
        curve (Curve): curve data
        bl_values (List[blQuaternion]): blQuaternion values in pose space

    Note:
        * The import function ensures that the quaternions in the curve are compatible with each other
            (i.e. lerping between them will not cause flips and the shortest path will always be taken).
        * Note it's *LERP* not *SLERP*. Blender fcurves does not specialize in quaternion interpolation.
        * Hence, with `interpolation`, you should always use `LINEAR` for the most accurate results.
    """
    assert (
        type(bl_values[0]) == blQuaternion
    ), "Values must be in Blender Quaternion type"
    frames = [time_to_frame(keyframe.time) for keyframe in curve.Data]
    fcurve = [action.fcurves.new(data_path=data_path, index=i) for i in range(4)]
    curve_datas = list()
    for i in range(4):
        curve_data = [0] * (len(frames) * 2)
        curve_data[::2] = frames
        curve_data[1::2] = [v[i] for v in bl_values]
        curve_datas.append(curve_data)
    curve_quats = [
        blQuaternion(
            (curve_datas[0][i], curve_datas[1][i], curve_datas[2][i], curve_datas[3][i])
        )
        for i in range(1, len(curve_datas[i]), 2)
    ]
    for i in range(1, len(curve_quats)):
        curve_quats[i].make_compatible(curve_quats[i - 1])
    for i in range(4):
        curve_datas[i][1::2] = [v[i] for v in curve_quats]
    for i in range(4):
        fcurve[i].keyframe_points.clear()
        fcurve[i].keyframe_points.add(len(curve_datas[i]) // 2)
        fcurve[i].keyframe_points.foreach_set("co", curve_datas[i])
        ipo = (
            bpy.types.Keyframe.bl_rna.properties["interpolation"]
            .enum_items[interpolation]
            .value
        )
        fcurve[i].keyframe_points.foreach_set(
            "interpolation", [ipo] * len(fcurve[i].keyframe_points)
        )
        fcurve[i].update()
    return fcurve


def load_armature_animation(
    name: str, anim: Animation, target: bpy.types.Object, crc_bone_table: dict
):
    """Converts an Animation object into Blender Action WITHOUT applying it to the armature

    To apply the animation, you must call `apply_action` with the returned action.

    Args:
        name (str): name of the action
        anim (Animation): animation data
        target (bpy.types.Object): target armature object
        crc_bone_table (dict): Animation path CRC32 value to Bone name table

    Returns:
        bpy.types.Action: the created action
    """
    bpy.ops.object.mode_set(mode="EDIT")
    # Collect Local Space matrices
    # In Blender we animate bones in Pose Space (explained below)
    local_space_TR = dict()
    for bone in target.data.edit_bones:  # Must be accessed in edit mode
        local_mat = (
            (
                bone.parent.matrix.inverted() @ bone.matrix
            )  # In armature space / world space
            if bone.parent
            else blMatrix.Identity(4)
        )
        local_space_TR[bone.name] = (
            local_mat.to_translation(),
            local_mat.to_quaternion(),
        )

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
    def to_pose_quaternion(name: str, quat: blQuaternion):
        etrans, erot = local_space_TR[name]
        erot_inv = erot.conjugated()
        return erot_inv @ quat

    def to_pose_translation(name: str, vec: blVector):
        etrans, erot = local_space_TR[name]
        erot_inv = erot.conjugated()
        return erot_inv @ (vec - etrans)

    def to_pose_euler(name: str, euler: blEuler):
        etrans, erot = local_space_TR[name]
        erot_inv = erot.conjugated()
        result = erot_inv @ euler.to_quaternion()
        result = result.to_euler("XYZ")
        return result

    # Reset the pose
    bpy.ops.object.mode_set(mode="POSE")
    bpy.ops.pose.select_all(action="SELECT")
    bpy.ops.pose.transforms_clear()
    bpy.ops.pose.select_all(action="DESELECT")
    # Setup actions
    action = create_action(name)
    # Quaternions
    for path, curve in anim.Curves[kBindTransformRotation].items():
        bone = crc_bone_table.get(path, None)
        if not bone:
            logger.warning("Quaternion: Failed to bind CRC32 %s to bone" % path)
            continue
        frames = [time_to_frame(keyframe.time, 0) for keyframe in curve.Data]
        values = [
            to_pose_quaternion(bone, swizzle_quaternion(keyframe.value))
            for keyframe in curve.Data
        ]
        import_curve_quatnerion(
            action, 'pose.bones["%s"].rotation_quaternion' % bone, frames, values
        )
    # Euler Rotations
    for path, curve in anim.Curves[kBindTransformEuler].items():
        bone = crc_bone_table.get(path, None)
        if not bone:
            logger.warning("Euler: Failed to bind CRC32 %s to bone" % path)
            continue
        pose_bone = target.pose.bones.get(bone)
        pose_bone.rotation_mode = "YXZ"  # see swizzle_euler
        frames = [time_to_frame(keyframe.time, 0) for keyframe in curve.Data]
        values = [
            to_pose_euler(bone, swizzle_euler(keyframe.value))
            for keyframe in curve.Data
        ]
        import_curve(
            action, 'pose.bones["%s"].rotation_euler' % bone, curve, frames, values
        )
    # Translations
    for path, curve in anim.Curves[kBindTransformPosition].items():
        bone = crc_bone_table.get(path, None)
        if not bone:
            logger.warning("Translation: Failed to bind CRC32 %s to bone" % path)
            continue
        frames = [time_to_frame(keyframe.time, 0) for keyframe in curve.Data]
        values = [
            to_pose_translation(bone, swizzle_vector(keyframe.value))
            for keyframe in curve.Data
        ]
        import_curve(action, 'pose.bones["%s"].location' % bone, curve, frames, values)
    # Scale
    for path, curve in anim.Curves[kBindTransformScale].items():
        bone = crc_bone_table.get(path, None)
        if not bone:
            logger.warning("Scale: Failed to bind CRC32 %s to bone" % path)
            continue
        frames = [time_to_frame(keyframe.time, 0) for keyframe in curve.Data]
        values = [swizzle_vector_scale(keyframe.value) for keyframe in curve.Data]
        import_curve(
            action,
            'pose.bones["%s"].scale' % bone,
            curve,
            frames,
            values,
            is_scale=True,
        )
    return action


def load_keyshape_animation(
    name: str,
    data: Animation,
    crc_keyshape_table: dict,
    frame_offset: int = 0,
    action: bpy.types.Action = None,
):
    """Converts an Animation object into Blender Action WITHOUT applying it to any mesh

    To apply the animation, you must call `apply_action` with the returned action.

    Args:
        name (str): name of the action
        data (Animation): animation data
        crc_keyshape_table (dict): Animation path CRC32 value to Blend Shape name table
        frame_offset (int): frame offset
        action (bpy.types.Action, optional): existing action to append to. Defaults to None

    Returns:
        bpy.types.Action: the created action

    Note:
        KeyShape value range [0,100]
    """
    action = create_action(name)
    for attrCRC, track in data.FloatTracks[BLENDSHAPES_CRC].items():
        bsName = crc_keyshape_table[str(attrCRC)]
        import_curve(
            action,
            'key_blocks["%s"].value' % bsName,
            [keyframe.value / 100.0 for keyframe in track.Curve],
            [time_to_frame(keyframe.time, frame_offset) for keyframe in track.Curve],
        )
    return action


def prepare_camera_rig(camera: bpy.types.Object):
    if not camera.parent or not KEY_SEKAI_CAMERA_RIG in camera.parent:
        # The 'rig' Offsets the camera's look-at direction w/o modifying the Euler angles themselves, which
        # would otherwise cause interpolation issues.
        # This is simliar to how mmd_tools handles camera animations.
        #
        # We also store the FOV in the X scale of the parent object so that it's easy to interpolate
        # and we'd only need one action for the entire animation.
        rig = create_empty("Camera Rig", camera.parent)
        rig[KEY_SEKAI_CAMERA_RIG] = "<marker>"
        camera.parent = rig
        camera.location = blVector((0, 0, 0))
        camera.rotation_euler = blEuler((math.radians(90), 0, math.radians(180)))
        camera.rotation_mode = "XYZ"
        camera.scale = blVector((1, 1, 1))
        # Driver for FOV
        driver = camera.data.driver_add("lens")
        driver.driver.type = "SCRIPTED"
        var_scale = driver.driver.variables.new()
        var_scale.name = "fov"
        var_scale.type = "TRANSFORMS"
        var_scale.targets[0].id = rig
        var_scale.targets[0].transform_space = "WORLD_SPACE"
        var_scale.targets[0].transform_type = "SCALE_X"
        driver.driver.expression = "fov"
        logger.debug("Created Camera Rig for camera %s" % camera.name)
        return rig
    return camera.parent


def load_camera_animation(
    name: str,
    data: Animation,
    camera: bpy.types.Object,
    frame_offset: int,
    scaling_factor: blVector,
    scaling_offset: blVector,
    fov_offset: float,
    action: bpy.types.Action = None,
):
    """Converts an Animation object into Blender Action WITHOUT applying it to the camera

    To apply the animation, you must call `apply_action` with the returned action.

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
    """
    rig = prepare_camera_rig(camera)
    rig.rotation_mode = "YXZ"
    action = action or create_action(name)

    def swizzle_translation_camera(vector: blVector):
        result = swizzle_vector(vector)
        result *= blVector(scaling_factor)
        result += blVector(scaling_offset)
        return result

    def swizzle_euler_camera(euler: blEuler):
        result = swizzle_euler(euler)
        result.y *= -1  # Invert Y (Unity's Roll)
        return result

    def fov_to_focal_length(fov: float):
        # FOV = 2 arctan [sensorSize/(2*focalLength)]
        # focalLength = sensorSize / (2 * tan(FOV/2))
        # fov -> Vertical FOV, which is the default in Unity
        fov += fov_offset
        return camera.data.sensor_height / (2 * math.tan(math.radians(fov) / 2))

    if CAMERA_TRANS_ROT_CRC_MAIN in data.TransformTracks[TransformType.EulerRotation]:
        logger.debug("Found Camera Rotation track")
        curve = data.TransformTracks[TransformType.EulerRotation][
            CAMERA_TRANS_ROT_CRC_MAIN
        ].Curve
        import_curve(
            action,
            "rotation_euler",
            [swizzle_euler_camera(keyframe.value) for keyframe in curve],
            [time_to_frame(keyframe.time, frame_offset) for keyframe in curve],
            3,
            "BEZIER",
            # [swizzle_euler(keyframe.inSlope) for keyframe in curve],
            # [swizzle_euler(keyframe.outSlope) for keyframe in curve]
        )
    if CAMERA_TRANS_ROT_CRC_MAIN in data.TransformTracks[TransformType.Translation]:
        logger.debug("Found Camera Translation track, scaling=%s" % scaling_factor)
        curve = data.TransformTracks[TransformType.Translation][
            CAMERA_TRANS_ROT_CRC_MAIN
        ].Curve
        import_curve(
            action,
            "location",
            [swizzle_translation_camera(keyframe.value) for keyframe in curve],
            [time_to_frame(keyframe.time, frame_offset) for keyframe in curve],
            3,
            "BEZIER",
            # [swizzle_translation_camera(keyframe.inSlope) for keyframe in curve],
            # [swizzle_translation_camera(keyframe.outSlope) for keyframe in curve]
        )
    if (
        CAMERA_TRANS_SCALE_EXTRA_CRC_EXTRA
        in data.TransformTracks[TransformType.Translation]
    ):
        logger.debug("Found Camera FOV track")
        camera.data.lens_unit = "MILLIMETERS"
        curve = data.TransformTracks[TransformType.Translation][
            CAMERA_TRANS_SCALE_EXTRA_CRC_EXTRA
        ].Curve
        import_curve(
            action,
            "scale",  # FOV on the X scale
            [(fov_to_focal_length(keyframe.value.z * 100), 1, 1) for keyframe in curve],
            [time_to_frame(keyframe.time, frame_offset) for keyframe in curve],
            3,
            "BEZIER",
            # [fov_to_focal_length(keyframe.inSlope.Z * 100) for keyframe in curve],
            # [fov_to_focal_length(keyframe.outSlope.Z * 100) for keyframe in curve]
        )
    return action
