from .utils import crc32

DEFAULT_BONE_SIZE = 0.01
# Plugin custom attribute keys
KEY_HIERARCHY_PATHID = "sssekai_hierarchy_pathid"
KEY_HIERARCHY_BONE_PATHID = "sssekai_bone_hierarchy_pathid"
KEY_HIERARCHY_BONE_NAME = "sssekai_bone_hierarchy_bonename"
# Hashes of names prefixed `blendShape.`
KEY_SHAPEKEY_HASH_TABEL = "sssekai_shapekey_name_hash_tbl"

# region Unity Specific
# AnimatorController::BuildAsset()
UNITY_MECANIM_RESERVED_TOS = {
    crc32(x): x
    for x in [
        "T",
        "Q",
        "S",
        "A",
        "B",
        "C",
        "D",
        "E",
        "X",
        "Y",
        "Z",
        "W",
        "Result",
        "Min",
        "Max",
        "Value",
        "MinMin",
        "MinMax",
        "MaxMin",
        "MaxMax",
        "In",
        "Out",
        "RangeA",
        "RangeB",
        "RangeC",
        "RangeD",
        "RangeE",
        "WeightA",
        "WeightB",
        "WeightC",
        "WeightD",
        "WeightE",
        "OutA",
        "OutB",
        "OutC",
        "OutD",
        "OutE",
        "Num",
        "Den",
        "Rem",
        "DampTime",
        "DeltaTime",
        "PreviousValue",
        "GravityWeight",
        "SrcRefX",
        "DstRefX",
        "SrcPivotX",
        "DstPivotX",
        "RefWeight",
        "PivotWeight",
        "XI",
        "XO",
        "Condition",
        "StateTime",
        "StateSpeed",
        "StateExitTime",
        "DoTransition",
        "NextStateStartTime",
        "TransitionDuration",
        "TransitionOffset",
        "TransitionStartTime",
        "StateMachineWeight",
        "TransitionTime",
        "BlendWeight",
        "StateWeight",
        "StabilizeFeet",
        "RootX",
        "LeftFoot.WeightT",
        "LeftFoot.WeightR",
        "RightFoot.WeightT",
        "RightFoot.WeightR",
        "ComputeSource",
        "LookAt",
        "LeftFootX",
        "RightFootX",
        "LeftFootSpeedT",
        "LeftFootSpeedQ",
        "RightFootSpeedT",
        "RightFootSpeedQ",
        "LeftFootStableT",
        "LeftFootStableQ",
        "RightFootStableT",
        "RightFootStableQ",
        "RootSpeedT",
        "RootSpeedQ",
        "RootStableT",
        "RootStableQ",
        "LeftFootProjX",
        "RightFootProjX",
        "PlantFeet",
        "LeftFootSafeX",
        "RightFootSafeX);",
        "PositionX",
        "PositionY",
        "PositionZ",
        "QuaternionX",
        "QuaternionY",
        "QuaternionZ",
        "QuaternionW",
        "ScaleX",
        "ScaleY",
        "ScaleZ",
        "DynamicCurve",
    ]
}
# endregion
# region Sekai Specific
DEFAULT_SPRINGBONE_RADIUS_SCALE = 0.8
DEFAULT_SPRINGBONE_SIZE = 0.01
DEFAULT_SPRINGBONE_PIVOT_SIZE = 0.01
DEFAULT_SPRINGBONE_CONSTRAINT_OBJ_SIZE = 0.1
KEY_SEKAI_CAMERA_RIG = "sssekai_sekai_camera_rig"
KEY_SEKAI_CAMERA_RIG_SENSOR_HEIGHT = "sssekai_sekai_camera_rig_sensor_height"
KEY_SEKAI_CHARACTER_ROOT = "sssekai_sekai_character_root_stub"
KEY_SEKAI_CHARACTER_HEIGHT = "sssekai_sekai_character_height"
KEY_SEKAI_CHARACTER_LIGHT_OBJ = "sssekai_sekai_character_light_obj"
KEY_SEKAI_CHARACTER_BODY_OBJ = "sssekai_sekai_character_body_obj"
KEY_SEKAI_CHARACTER_FACE_OBJ = "sssekai_sekai_character_face_obj"
# Hardcoded orders for RLA import
SEKAI_RLA_VALID_BONES = [
    "Hip",
    "Waist",
    "Spine",
    "Chest",
    "Neck",
    "Head",
    "Left_Shoulder",
    "Left_Arm",
    "Left_Elbow",
    "Left_Wrist",
    "Left_Thumb_01",
    "Left_Thumb_02",
    "Left_Thumb_03",
    "Left_Index_01",
    "Left_Index_02",
    "Left_Index_03",
    "Left_Middle_01",
    "Left_Middle_02",
    "Left_Middle_03",
    "Left_Ring_01",
    "Left_Ring_02",
    "Left_Ring_03",
    "Left_Pinky_01",
    "Left_Pinky_02",
    "Left_Pinky_03",
    "Left_ForeArmRoll",
    "Left_ArmRoll",
    "Left_Pectoralis_01",
    "Right_Pectoralis_01",
    "Right_Shoulder",
    "Right_Arm",
    "Right_Elbow",
    "Right_Wrist",
    "Right_Thumb_01",
    "Right_Thumb_02",
    "Right_Thumb_03",
    "Right_Index_01",
    "Right_Index_02",
    "Right_Index_03",
    "Right_Middle_01",
    "Right_Middle_02",
    "Right_Middle_03",
    "Right_Ring_01",
    "Right_Ring_02",
    "Right_Ring_03",
    "Right_Pinky_01",
    "Right_Pinky_02",
    "Right_Pinky_03",
    "Right_ForeArmRoll",
    "Right_ArmRoll",
    "Left_Thigh",
    "Left_Knee",
    "Left_Ankle",
    "Left_Toe",
    "Left_AssistHip",
    "Right_Thigh",
    "Right_Knee",
    "Right_Ankle",
    "Right_Toe",
    "Right_AssistHip",
]
SEKAI_RLA_VALID_BLENDSHAPES = [
    "BS_look.look_up",
    "BS_look.look_down",
    "BS_look.look_left",
    "BS_look.look_right",
    "BS_mouth.mouth_a",
    "BS_mouth.mouth_i",
    "BS_mouth.mouth_u",
    "BS_mouth.mouth_e",
    "BS_mouth.mouth_o",
    "BS_mouth.mouth_a2",
    "BS_mouth.mouth_i2",
    "BS_mouth.mouth_u2",
    "BS_mouth.mouth_e2",
    "BS_mouth.mouth_o2",
    "BS_mouth.mouth_sad",
    "BS_mouth.mouth_kime",
    "BS_mouth.mouth_happy",
    "BS_eye.eye_happy",
    "BS_eye.eye_sad",
    "BS_eye.eye_close",
    "BS_eye.eye_wink_L",
    "BS_eye.eye_wink_R",
    "BS_eyeblow.eyeblow_happy",
    "BS_eyeblow.eyeblow_sad",
    "BS_eyeblow.eyeblow_kime",
    "BS_eyeblow.eyeblow_smile",
]
SEKAI_RLA_ROOT_BONE = "Hip"
SEKAI_RLA_TIME_MAGNITUDE = 1e7  # 1e7 = 1 second
# Hardcoded names for Sekai
SEKAI_BLENDSHAPE_NAME = "BS_"  # XXX: Incorrect!!
SEKAI_BLENDSHAPE_CRC = 2770785369
SEKAI_CAMERA_MAIN_NAME = "mainCam"
SEKAI_CAMERA_PARAM_NAME = "mainCam/CamParam"

SEKAI_CAMERA_SUB_NAME = "subCam"
SEKAI_CAMERA_SUB_TARGET_NAME = "subCam/target"
SEKAI_CAMERA_SUB_PARAM_NAME = "subCam/CamParam"

SEKAI_LIGHT_INTENSITY = "intensity"
SEKAI_LIGHT_EDGE_SMOOTHNESS = "edgeSmoothness"
SEKAI_LIGHT_SHADOW_SHARPNESS = "shadowSharpness"

SEKAI_LIGHT_AMBIENT_COLOR_R = "ambientColor.r"
SEKAI_LIGHT_AMBIENT_COLOR_G = "ambientColor.g"
SEKAI_LIGHT_AMBIENT_COLOR_B = "ambientColor.b"

SEKAI_LIGHT_SHADOW_COLOR_R = "shadowColor.r"
SEKAI_LIGHT_SHADOW_COLOR_G = "shadowColor.g"
SEKAI_LIGHT_SHADOW_COLOR_B = "shadowColor.b"

SEKAI_LIGHT_SHADOW_RIM_COLOR_R = "shadowRimColor.r"
SEKAI_LIGHT_SHADOW_RIM_COLOR_G = "shadowRimColor.g"
SEKAI_LIGHT_SHADOW_RIM_COLOR_B = "shadowRimColor.b"

SEKAI_LIGHT_OUTLINE_BLENDING = "outlineBlending"
SEKAI_LIGHT_OUTLINE_COLOR_R = "outlineColor.r"
SEKAI_LIGHT_OUTLINE_COLOR_G = "outlineColor.g"
SEKAI_LIGHT_OUTLINE_COLOR_B = "outlineColor.b"

SEKAI_LIGHT_RIM_COLOR_R = "rimColor.r"
SEKAI_LIGHT_RIM_COLOR_G = "rimColor.g"
SEKAI_LIGHT_RIM_COLOR_B = "rimColor.b"

SEKAI_LIGHT_RANGE = "range"
SEKAI_LIGHT_INFLUENCE = "lightInfluence"
SEKAI_LIGHT_USE_FACE_SHADOW_LIMITER = "useFaceShadowLimiter"
SEKAI_LIGHT_EMISSION = "emission"
SEKAI_LIGHT_FACE_SHADOW_LIMIT_RANGE = "faceShadowLimitRange"
SEKAI_LIGHT_IS_USE_SHADOW_COLOR = "isUseShadowColor"
# endregion
