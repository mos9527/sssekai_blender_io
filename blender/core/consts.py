# Plugin custom attribute keys
KEY_SHAPEKEY_HASH_TABEL = "sssekai_shapekey_name_hash_tbl"

KEY_SEKAI_CAMERA_RIG = "sssekai_camera_rig"
KEY_SEKAI_CHARACTER_ROOT_STUB = "sssekai_sekai_character_root_stub"
KEY_SEKAI_CHARACTER_HEIGHT = "sssekai_sekai_character_height"
KEY_SEKAI_CHARACTER_BODY_OBJ = "sssekai_sekai_character_body_obj"
KEY_SEKAI_CHARACTER_FACE_OBJ = "sssekai_sekai_character_face_obj"
# Hardcoded orders for RLA import
RLA_VALID_BONES = [
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
RLA_VALID_BLENDSHAPES = [
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
RLA_ROOT_BONE = "Hip"
RLA_TIME_MAGNITUDE = 1e7  # 1e7 = 1 second
# CRC Constants
# XXX: Find the corresponding source strings for these!
BLENDSHAPES_CRC = 2770785369
# Camera rigs
CAMERA_TRANS_ROT_CRC_MAIN = 3326594866  # Euler, Position in transform tracks
CAMERA_TRANS_SCALE_EXTRA_CRC_EXTRA = (
    3283970054  # Position, Scale(??) in transform tracks, FOV in the last float track
)