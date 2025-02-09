import bpy
import logging, json, math
from typing import List, Dict, Tuple
from sssekai.unity.AnimationClip import (
    Animation,
    Interpolation,
    Curve,
    KeyFrame,
    kBindTransformEuler,
    kBindTransformPosition,
    kBindTransformRotation,
    kBindTransformScale,
)
from .math import (
    uVector3,
    blEuler,
    blQuaternion,
    blVector,
    blMatrix,
    swizzle_euler,
    swizzle_euler_slope,
    swizzle_euler_ipo,
    swizzle_quaternion,
    swizzle_quaternion_slope,
    swizzle_quaternion_ipo,
    swizzle_vector,
    swizzle_vector_slope,
    swizzle_vector_scale,
    swizzle_vector_ipo,
)
from .helpers import create_empty, time_to_frame, create_action
from .utils import crc32
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
                Interpolation.Hermite: "BEZIER",
                Interpolation.Linear: "LINEAR",
                # Blender seem to use the left key value for the interpolation too
                Interpolation.Stepped: "CONSTANT",
            }[ipo]
        ]
        .value
    )


def load_fcurves(
    action: bpy.types.Action,
    data_path: str,
    curve: Curve,
    bl_values: List[float | blEuler | blVector | blQuaternion],
    swizzle_slope_func: callable = None,
    swizzle_ipo_func: callable = None,
    always_lerp: bool = False,
    override_data_index: int = 0,
):
    """Creates an arbitrary amount of FCurves for a sssekai Curve

    Args:
        action (bpy.types.Action): target action.
        data_path (str): data path
        curve (Curve): curve data. used to access slope values
        bl_values (List[float | blEuler | blVector | blQuaternion]): values in Blender types
        swizzle_slope_func (callable, optional): swizzle function applied on the slope values. Read the note below
        swizzle_ipo_func (callable, optional): swizzle function applied on the interpolation order with multiple values (e.g. XYZ). Defaults to None.
        always_lerp (bool, optional): always use linear interpolation. Defaults to False.
        override_data_index (int, optional): override the data index. only used when value type is float. Defaults to 0.

    Notes on swizzle_slope_func, swizzle_ipo_func:
        Swizzling `g(x) = kx` would be STRICTLY linear and `f(x), f'(x)` are known, this implies that:
        `F(x) = g(f(x))`->`F'(x) = g'(f(x)) * f'(x) = k * f'(x) = g(f'(x))`

        Meaning swizzling the slope values would make them correct.

        Affine transform (non-Scale, Shear) in 3D space only needs the swizzling on the slope values since
        affine transforms don't affect slopes.

        If your value transform isn't linear (e.g. FOV to Lens) - you should probably consider using a Driver instead
    """
    num_curves = 1
    bl_inSlopes = []
    bl_outSlopes = []

    if type(bl_values[0]) == blEuler:
        num_curves = 3
        swizzle_slope_func = swizzle_slope_func or swizzle_euler_slope
        swizzle_ipo_func = swizzle_ipo_func or swizzle_euler_ipo
    elif type(bl_values[0]) == blVector:
        num_curves = 3
        swizzle_slope_func = swizzle_slope_func or swizzle_vector_slope
        swizzle_ipo_func = swizzle_ipo_func or swizzle_vector_ipo
    elif type(bl_values[0]) == blQuaternion:
        num_curves = 4
        swizzle_slope_func = swizzle_slope_func or swizzle_quaternion_slope
        swizzle_ipo_func = swizzle_ipo_func or swizzle_quaternion_ipo
    elif type(bl_values[0]) == float:
        num_curves = 1
        swizzle_slope_func = swizzle_slope_func or (lambda x: x)
        swizzle_ipo_func = swizzle_ipo_func or (lambda x: x)
    else:
        raise NotImplementedError("Unsupported value type")
    bl_inSlopes = [swizzle_slope_func(k.inSlope) for k in curve.Data]
    bl_outSlopes = [swizzle_slope_func(k.outSlope) for k in curve.Data]
    finite = lambda x: (
        x if math.isfinite(x) and abs(x) < 1e18 else 0
    )  # XXX: Arbitrary value
    frames = [finite(time_to_frame(keyframe.time)) for keyframe in curve.Data]
    if num_curves > 1:
        fcurve = [
            action.fcurves.new(data_path=data_path, index=i) for i in range(num_curves)
        ]
    else:
        fcurve = [action.fcurves.new(data_path=data_path, index=override_data_index)]
    for index in range(num_curves):
        curve_data = [0] * (len(frames) * 2)
        curve_data[::2] = frames
        curve_data[1::2] = [
            finite(v[index] if num_curves > 1 else v) for v in bl_values
        ]

        fcurve[index].keyframe_points.clear()
        fcurve[index].keyframe_points.add(len(frames))
        fcurve[index].keyframe_points.foreach_set("co", curve_data)
        # Setup interpolation
        fcurve[index].keyframe_points.foreach_set(
            "interpolation",
            [
                interpolation_to_blender(
                    swizzle_ipo_func(
                        keyframe.interpolation_segment(keyframe, keyframe.next)
                    )[index]
                    if not always_lerp
                    else Interpolation.Linear
                )
                for keyframe in curve.Data
            ],
        )
        # Setup Hermite to cubic Bezier CPs
        # For non-Bezier segments the would not have any effect
        free_handles = [BEZIER_FREE] * len(frames)
        fcurve[index].keyframe_points.foreach_set("handle_left_type", free_handles)
        fcurve[index].keyframe_points.foreach_set("handle_right_type", free_handles)
        p1 = [0] * (len(frames) * 2)
        p2 = [0] * (len(frames) * 2)
        # Cubic Bezier H(t) = (1-t)^3 * P0 + 3(1-t)^2 * t * P1 + 3(1-t) * t^2 * P2 + t^3 * P3
        # H'(t) = 3(1-t)^2 * (P1 - P0) + 6(1-t) * t * (P2 - P1) + 3t^2 * (P3 - P2)
        # H'(0) = 3(P1 - P0) = m0 \therefore P1 = P0 + m0/3
        # H'(1) = 3(P3 - P2) = m1 \therefore P2 = P3 - m1/3
        # This is also where the rule of 1/3rd comes from
        delta_t_3 = lambda i: (
            (curve.Data[i + 1].time - curve.Data[i].time) / 3
            if i + 1 < len(curve.Data)
            else 0.1  # Arbitrary value
        )
        # XXX: Somehow stepped keys with IPO set to Constant
        # can still affect neighboring keys.
        p1[::2] = [
            finite(time_to_frame(k.time + delta_t_3(i)))
            for i, k in enumerate(curve.Data)
        ]
        p1[1::2] = [
            finite(
                (bl_values[i][index] if num_curves > 1 else bl_values[i])
                + finite((k[index] if num_curves > 1 else k) * delta_t_3(i))
            )
            for i, k in enumerate(bl_outSlopes)
        ]
        p2[::2] = [
            finite(time_to_frame(k.time - delta_t_3(i)))
            for i, k in enumerate(curve.Data)
        ]
        p2[1::2] = [
            finite(
                (bl_values[i][index] if num_curves > 1 else bl_values[i])
                - finite((k[index] if num_curves > 1 else k) * delta_t_3(i))
            )
            for i, k in enumerate(bl_inSlopes)
        ]
        fcurve[index].keyframe_points.foreach_set("handle_left", p2)
        fcurve[index].keyframe_points.foreach_set("handle_right", p1)
        fcurve[index].update()


def load_float_fcurve(
    action: bpy.types.Action,
    data_path: str,
    curve: Curve,
    bl_values: List[float] = None,
    always_lerp: bool = False,
    override_data_index: int = 0,
):
    """Helper function that creates an FCurve for a sssekai Float Curve

    Args:
        action (bpy.types.Action): target action.
        data_path (str): data path
        curve (Curve): curve data
        bl_values (List[float], optional): values in Blender types. will be extracted from curve if not provided. Defaults to None.
        always_lerp (bool, optional): always use linear interpolation. Defaults to False.
        override_data_index (int, optional): override the data index. Defaults to 0.

    """
    bl_values = bl_values or [k.value for k in curve.Data]
    return load_fcurves(
        action,
        data_path,
        curve,
        bl_values,
        always_lerp=always_lerp,
        override_data_index=override_data_index,
    )


def load_quatnerion_fcurves(
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
        interpolation (str, optional): interpolation type. Defaults to "LINEAR".

    Note:
        * The import function ensures that the quaternions in the curve are compatible with each other
            (i.e. lerping between them will not cause flips and the shortest path will always be taken).
        * Note it's *LERP* not *SLERP*. Blender fcurves does not specialize in quaternion interpolation.
        * Hence, with `interpolation`, you should always use `LINEAR` for the most accurate results.
        * The curve's tangents are NOT used for this reason.
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
    name: str,
    anim: Animation,
    target: bpy.types.Object,
    tos_leaf: dict,
    always_lerp: bool = False,
):
    """Converts an Animation object into Blender Action WITHOUT applying it to the armature

    To apply the animation, you must call `apply_action` with the returned action.

    Args:
        name (str): name of the action
        anim (Animation): animation data
        target (bpy.types.Object): target armature object
        tos_leaf (dict): TOS. Animation *FULL* path CRC32 to *LEAF* bone name table
        always_lerp (bool, optional): always use linear interpolation. Defaults to False.

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
        # XXX: Guess what...animators would wrap around the euler values
        # and do animations in ranges like 0~69420 so it 'effectively' spins a lot
        # Transforming euler w/ matrices - then converting to euler again would normalize it
        # to -180~180 range.
        # assume \theta = 2k\pi + \phi. we'd just add 2k\pi to the euler value
        etrans, erot = local_space_TR[name]
        erot: blQuaternion
        erot_inv = erot.conjugated()
        TWOPI = 2 * math.pi
        result = euler.copy()
        if euler.x:
            result.x %= math.copysign(TWOPI, euler.x)
        if euler.y:
            result.y %= math.copysign(TWOPI, euler.y)
        if euler.z:
            result.z %= math.copysign(TWOPI, euler.z)
        x, y, z = euler.x - result.x, euler.y - result.y, euler.z - result.z
        result = erot_inv @ result.to_quaternion()
        result = result.to_euler("XYZ")
        result.x += x
        result.y += y
        result.z += z
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
        bone = tos_leaf.get(path, None)
        if not bone:
            logger.warning("Quaternion: Failed to bind CRC32 %s to bone" % path)
            continue
        values = [
            to_pose_quaternion(bone, swizzle_quaternion(keyframe.value))
            for keyframe in curve.Data
        ]
        load_quatnerion_fcurves(
            action, 'pose.bones["%s"].rotation_quaternion' % bone, curve, values
        )
    # Euler Rotations
    for path, curve in anim.Curves[kBindTransformEuler].items():
        bone = tos_leaf.get(path, None)
        if not bone:
            logger.warning("Euler: Failed to bind CRC32 %s to bone" % path)
            continue
        pose_bone = target.pose.bones.get(bone)
        pose_bone.rotation_mode = "YXZ"  # see swizzle_euler
        values = [
            to_pose_euler(bone, swizzle_euler(keyframe.value))
            for keyframe in curve.Data
        ]
        load_fcurves(
            action,
            'pose.bones["%s"].rotation_euler' % bone,
            curve,
            values,
            always_lerp=always_lerp,
        )
    # Translations
    for path, curve in anim.Curves[kBindTransformPosition].items():
        bone = tos_leaf.get(path, None)
        if not bone:
            logger.warning("Translation: Failed to bind CRC32 %s to bone" % path)
            continue
        values = [
            to_pose_translation(bone, swizzle_vector(keyframe.value))
            for keyframe in curve.Data
        ]
        load_fcurves(
            action,
            'pose.bones["%s"].location' % bone,
            curve,
            values,
            always_lerp=always_lerp,
        )
    # Scale
    for path, curve in anim.Curves[kBindTransformScale].items():
        bone = tos_leaf.get(path, None)
        if not bone:
            logger.warning("Scale: Failed to bind CRC32 %s to bone" % path)
            continue
        values = [swizzle_vector_scale(keyframe.value) for keyframe in curve.Data]
        load_fcurves(
            action,
            'pose.bones["%s"].scale' % bone,
            curve,
            values,
            swizzle_slope_func=swizzle_vector_scale,
            always_lerp=always_lerp,
        )
    return action


# region Sekai Specific


def load_sekai_keyshape_animation(
    name: str,
    data: Animation,
    crc_keyshape_table: dict,
    always_lerp: bool = False,
):
    """Converts an Animation object into Blender Action WITHOUT applying it to any mesh

    To apply the animation, you must call `apply_action` with the returned action.

    Args:
        name (str): name of the action
        data (Animation): animation data
        crc_keyshape_table (dict): Animation path CRC32 value to Blend Shape name table
        frame_offset (int): frame offset
        action (bpy.types.Action, optional): existing action to append to. Defaults to None
        always_lerp (bool, optional): always use linear interpolation. Defaults to False.

    Returns:
        bpy.types.Action: the created action

    Note:
        KeyShape value range [0,100]
    """
    action = create_action(name)
    for attr, curve in data.CurvesT[SEKAI_BLENDSHAPE_CRC].items():
        bsName = crc_keyshape_table[str(attr)]
        load_fcurves(
            action,
            'key_blocks["%s"].value' % bsName,
            curve,
            [keyframe.value / 100.0 for keyframe in curve.Data],
            swizzle_slope_func=lambda x: x / 100.0,
            always_lerp=always_lerp,
        )
    return action


def load_sekai_camera_animation(
    name: str,
    data: Animation,
    always_lerp: bool = False,
    is_sub_camera: bool = False,
):
    """Converts an Animation object into Blender Action WITHOUT applying it to the camera rig

    The Action MUST be applied to a SekaiCameraRig object.

    Args:
        name (str): name of the action
        data (Animation): animation data
        always_lerp (bool, optional): always use linear interpolation. Defaults to False.

    Returns:
        bpy.types.Action: the created action
    """
    action = create_action(name)

    def swizzle_param_camera(param: blVector):
        return blVector((-param.x, param.y, param.z))

    if is_sub_camera:
        mainCam = data.CurvesT.get(
            crc32(SEKAI_CAMERA_SUB_NAME), None
        )  # Euler, Position in transform tracks
        camParam = data.CurvesT.get(
            crc32(SEKAI_CAMERA_SUB_PARAM_NAME), None
        )  # Position, Scale(??) in transform tracks, FOV in the last float track
        target = data.CurvesT.get(crc32(SEKAI_CAMERA_SUB_TARGET_NAME), None)
        # XXX: Need sample.
    else:
        mainCam = data.CurvesT.get(
            crc32(SEKAI_CAMERA_MAIN_NAME), None
        )  # Euler, Position in transform tracks
        camParam = data.CurvesT.get(
            crc32(SEKAI_CAMERA_PARAM_NAME), None
        )  # Position, Scale(??) in transform tracks, FOV in the last float track
    if mainCam:
        if kBindTransformEuler in mainCam:
            curve = mainCam[kBindTransformEuler]
            load_fcurves(
                action,
                "rotation_euler",
                curve,
                [swizzle_euler(keyframe.value) for keyframe in curve.Data],
                always_lerp=always_lerp,
            )
        if kBindTransformPosition in mainCam:
            curve = mainCam[kBindTransformPosition]
            load_fcurves(
                action,
                "location",
                curve,
                [swizzle_vector(keyframe.value) for keyframe in curve.Data],
                always_lerp=always_lerp,
            )
    else:
        logger.warning(
            "Main Camera Transform not found. Camera Motion will be unavailable"
        )
    if camParam:
        if kBindTransformPosition in camParam:
            curve = camParam[kBindTransformPosition]
            load_fcurves(
                action,
                "scale",
                curve,
                [swizzle_param_camera(keyframe.value) for keyframe in curve.Data],
                swizzle_slope_func=swizzle_param_camera,
                always_lerp=always_lerp,
            )
    else:
        logger.warning(
            "Camera Param Transform not found. Camera FOV curve will be unavailable"
        )
    return action


def swizzle_euler_light(euler: uVector3, flipY=False):
    euler = swizzle_euler(euler)
    euler.x *= -1
    if flipY:
        euler.y += math.radians(180)
    return euler


def swizzle_euler_light_slope(euler: uVector3):
    euler = swizzle_euler_slope(euler)
    euler.x *= -1
    return euler


def load_sekai_ambient_light_animation(
    name: str,
    data: Animation,
    always_lerp: bool = False,
):
    """
    AmbientLight
        --- Ambient Intensity
        3920803986	intensity
        --- Ambient Color
        3163355018	ambientColor.r
        3511751521	ambientColor.g
        2705057774	ambientColor.b
        -- unk
        942847572	NOT FOUND
        190802317	NOT FOUND
    """
    # fmt: off
    action = create_action(name)
    curves = data.CurvesT[0]
    curve = curves.get(crc32(SEKAI_LIGHT_INTENSITY), None)
    if curve:
        load_float_fcurve(
            action, '["Ambient Intensity"]', curve, always_lerp=always_lerp
        )
    curve = curves.get(crc32(SEKAI_LIGHT_AMBIENT_COLOR_R), None)
    if curve:
        load_float_fcurve(action, '["Ambient Color"]', curve, always_lerp=always_lerp, override_data_index=0)
    curve = curves.get(crc32(SEKAI_LIGHT_AMBIENT_COLOR_G), None)
    if curve:
        load_float_fcurve(action, '["Ambient Color"]', curve, always_lerp=always_lerp, override_data_index=1)
    curve = curves.get(crc32(SEKAI_LIGHT_AMBIENT_COLOR_B), None)
    if curve:
        load_float_fcurve(action, '["Ambient Color"]', curve, always_lerp=always_lerp, override_data_index=2)
    # fmt: on
    return action


def load_sekai_directional_light_animation(
    name: str,
    data: Animation,
    always_lerp: bool = False,
) -> Tuple[bpy.types.Action, bpy.types.Action]:
    """
    DirectionalLight
        --- rotation_euler
        4	        Euler
        --- Shadow Color
        464682304	shadowColor.r
        1987025323	shadowColor.g
        101018916	shadowColor.b
        --- unk
        2668379294	NOT FOUND
        3305885265	NOT FOUND
        --- (not used for now. still broken in-game)
        2309651703	faceShadowLimitRange
        2381373797	useFaceShadowLimiter

    Returns:
        Tuple[bpy.types.Action, bpy.types.Action]: (Global Action, Directional Light Action)
    """
    # fmt: off
    curves = data.CurvesT[0]
    curve = curves.get(kBindTransformEuler, None)
    action = create_action(name)
    if curve:
        load_fcurves(
            action, 'rotation_euler', curve, 
            [swizzle_euler_light(keyframe.value) for keyframe in curve.Data], 
            swizzle_slope_func=swizzle_euler_light_slope,
            always_lerp=always_lerp
        )
    directional_light_action = action

    action = create_action(name)
    curve = curves.get(crc32(SEKAI_LIGHT_SHADOW_COLOR_R), None)
    if curve:
        load_float_fcurve(action, '["Shadow Color"]', curve, always_lerp=always_lerp, override_data_index=0)
    curve = curves.get(crc32(SEKAI_LIGHT_SHADOW_COLOR_G), None)
    if curve:
        load_float_fcurve(action, '["Shadow Color"]', curve, always_lerp=always_lerp, override_data_index=1)
    curve = curves.get(crc32(SEKAI_LIGHT_SHADOW_COLOR_B), None)
    if curve:
        load_float_fcurve(action, '["Shadow Color"]', curve, always_lerp=always_lerp, override_data_index=2)
    # fmt: on
    return action, directional_light_action


def load_sekai_character_ambient_light_animation(
    name: str,
    data: Animation,
    always_lerp: bool = False,
):
    """
    character_ambient_0474_02
        --- Ambient Color
        3163355018	ambientColor.r
        3511751521	ambientColor.g
        2705057774	ambientColor.b
        942847572	NOT FOUND
        --- Ambient Intensity
        3920803986	intensity
        --- XXX outline
        2706170584	outlineColor.r
        3432056371	outlineColor.g
        3170628284	outlineColor.b
        636658438	NOT FOUND
        2290131282	outlineBlending
    """
    # fmt: off
    action = create_action(name)
    curves = data.CurvesT[0]
    curve = curves.get(crc32(SEKAI_LIGHT_INTENSITY), None)
    if curve:
        load_float_fcurve(
            action, '["Character Ambient Intensity"]', curve, always_lerp=always_lerp
        )
    curve = curves.get(crc32(SEKAI_LIGHT_AMBIENT_COLOR_R), None)
    if curve:
        load_float_fcurve(action, '["Character Ambient Color"]', curve, always_lerp=always_lerp, override_data_index=0)
    curve = curves.get(crc32(SEKAI_LIGHT_AMBIENT_COLOR_G), None)
    if curve:
        load_float_fcurve(action, '["Character Ambient Color"]', curve, always_lerp=always_lerp, override_data_index=1)
    curve = curves.get(crc32(SEKAI_LIGHT_AMBIENT_COLOR_B), None)
    if curve:
        load_float_fcurve(action, '["Character Ambient Color"]', curve, always_lerp=always_lerp, override_data_index=2)
    # TODO: Outlines
    # ---
    # fmt: on
    return action


def load_sekai_character_rim_light_animation(
    name: str,
    data: Animation,
    always_lerp: bool = False,
) -> Tuple[bpy.types.Action, bpy.types.Action]:
    """
    character_rim_0474_01
        --- rotation_euler
        4	Euler
        --- not implemented
        4028783860	emission
        1031701497	isUseShadowColor
        2600596049	lightInfluence
        2475121225	range
        --- Rim Color
        4222072118	rimColor.r
        2524598749	rimColor.g
        3859850578	rimColor.b
        2132407528	NOT FOUND
        --- Rim Color (Shadowing)
        2459267540	shadowRimColor.r
        4282946879	shadowRimColor.g
        2401395120	shadowRimColor.b
        371929098	NOT FOUND
        --- not implemented
        3526214719	shadowSharpness
        2163651078	edgeSmoothness

    """
    # fmt: off
    curves = data.CurvesT[0]
    curve = curves.get(kBindTransformEuler, None)
    action = create_action(name)
    if curve:
        load_fcurves(
            action, 'rotation_euler', curve, 
            [swizzle_euler_light(keyframe.value, flipY=True) for keyframe in curve.Data],
            swizzle_slope_func=swizzle_euler_light_slope,
            always_lerp=always_lerp
        )
    
    curve = curves.get(crc32(SEKAI_LIGHT_RIM_COLOR_R), None)
    if curve:
        load_float_fcurve(action, '["Rim Color"]', curve, always_lerp=always_lerp, override_data_index=0)
    curve = curves.get(crc32(SEKAI_LIGHT_RIM_COLOR_G), None)
    if curve:
        load_float_fcurve(action, '["Rim Color"]', curve, always_lerp=always_lerp, override_data_index=1)
    curve = curves.get(crc32(SEKAI_LIGHT_RIM_COLOR_B), None)
    if curve:
        load_float_fcurve(action, '["Rim Color"]', curve, always_lerp=always_lerp, override_data_index=2)
    curve = curves.get(crc32(SEKAI_LIGHT_SHADOW_COLOR_R), None)
    if curve:
        load_float_fcurve(action, '["Rim Shadow Color"]', curve, always_lerp=always_lerp, override_data_index=0)
    curve = curves.get(crc32(SEKAI_LIGHT_SHADOW_COLOR_G), None)
    if curve:
        load_float_fcurve(action, '["Rim Shadow Color"]', curve, always_lerp=always_lerp, override_data_index=1)
    curve = curves.get(crc32(SEKAI_LIGHT_SHADOW_COLOR_B), None)
    if curve:
        load_float_fcurve(action, '["Rim Shadow Color"]', curve, always_lerp=always_lerp, override_data_index=2)
    # fmt: on
    return action


# endregion
