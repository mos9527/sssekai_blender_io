import os, sys

try:
    import bpy
    import bpy_extras
    import bmesh
    from mathutils import (
        Matrix as blMatrix,
        Quaternion as blQuaternion,
        Vector as blVector,
        Euler as blEuler,
    )

    BLENDER = True
except ImportError:
    # Stubs for debugging outside blender's python
    # pip install fake-bpy-module
    class blMatrix:
        pass

    class blQuaternion:
        pass

    class blVector:
        pass

    class blEuler:
        pass

    BLENDER = False

import math
import zlib
from typing import List, Dict, Set
from dataclasses import dataclass
from enum import IntEnum

# UnityPy deps
import UnityPy
from UnityPy import Environment
from UnityPy.enums import ClassIDType
from UnityPy.classes import (
    Mesh,
    SkinnedMeshRenderer,
    MeshRenderer,
    MeshFilter,
    GameObject,
    Transform,
    Texture2D,
    Material,
)
from UnityPy.classes.math import Vector3f as uVector3, Quaternionf as uQuaternion

# SSSekai deps
from sssekai.unity.AnimationClip import (
    Animation,
    TransformType,
    KeyFrame,
)
from sssekai.unity import sssekai_get_unity_version, sssekai_set_unity_version


# Coordinate System | Forward |  Up  |  Left
# Unity:   LH, Y Up |   Z     |   Y  |  -X
# Blender: RH, Z Up |  -Y     |   Z  |   X
def swizzle_vector_scale(vec: uVector3):
    return blVector((vec.x, vec.z, vec.y))


def swizzle_vector3(X, Y, Z):
    return blVector((-X, -Z, Y))


def swizzle_vector(vec: uVector3):
    return swizzle_vector3(vec.x, vec.y, vec.z)


def swizzle_euler3(X, Y, Z):
    return blEuler((X, Z, -Y), "YXZ")


def swizzle_euler(euler: uVector3, isDegrees=True):
    """mode -> YXZ on the objects that support it. see euler3_to_quat_swizzled"""
    if isDegrees:
        return swizzle_euler3(
            math.radians(euler.x), math.radians(euler.y), math.radians(euler.z)
        )
    else:
        return swizzle_euler3(euler.x, euler.y, euler.z)


def swizzle_quaternion4(X, Y, Z, W):
    return blQuaternion((W, X, Z, -Y))  # conjugate (W,-X,-Z,Y)


def swizzle_quaternion(quat: uQuaternion):
    return swizzle_quaternion4(quat.x, quat.y, quat.z, quat.w)


# See swizzle_quaternion4. This is the inverse of that since we're reproducing Unity's quaternion
def euler3_to_quat_swizzled(x, y, z):
    # See https://docs.unity3d.com/ScriptReference/Quaternion.Euler.html
    # Unity uses ZXY rotation order
    quat = (
        blQuaternion((0, 0, 1), -y)
        @ blQuaternion((1, 0, 0), x)
        @ blQuaternion((0, 1, 0), z)
    )  # Left multiplication
    return uQuaternion(quat.x, -quat.z, quat.y, quat.w)


# Used for bone path (boneName) and blend shape name inverse hashing
def get_name_hash(name: str):
    return zlib.crc32(name.encode("utf-8"))


# The tables stored in the mesh's Custom Properties. Used by the animation importer.
KEY_BONE_NAME_HASH_TBL = "sssekai_bone_name_hash_tbl"  # Bone *full path hash* to bone name (Vertex Group name in blender lingo)
KEY_ARTICULATION_NAME_HASH_TBL = "sssekai_articulation_name_hash_tbl"  # GameObject hierarchy path hash to parent GameObject name
KEY_SHAPEKEY_NAME_HASH_TBL = (
    "sssekai_shapekey_name_hash_tbl"  # ShapeKey name hash to ShapeKey names
)
KEY_JOINT_BONE_NAME = "sssekai_joint_bone_name"  # Bone name of the joint
KEY_CAMERA_RIG = "sssekai_camera_rig"  # Camera rig data

# --- BEGIN Sekai specific values
# Plugin table names
KEY_SEKAI_CHARACTER_HEIGHT = "sssekai_sekai_character_height"
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
BLENDSHAPES_CRC = 2770785369
# Camera rigs
CAMERA_TRANS_ROT_CRC_MAIN = 3326594866  # Euler, Position in transform tracks
CAMERA_TRANS_SCALE_EXTRA_CRC_EXTRA = (
    3283970054  # Position, Scale(??) in transform tracks, FOV in the last float track
)
# --- END Sekai specific values

# Utilities
from .. import SCRIPT_DIR
from sssekai.abcache import fromdict as dataclass_from_dict


def get_addon_relative_path(*args):
    return os.path.join(SCRIPT_DIR, *args)


def create_empty(name: str, parent=None):
    joint = bpy.data.objects.new(name, None)
    joint.empty_display_size = 0.1
    joint.empty_display_type = "ARROWS"
    joint.parent = parent
    bpy.context.collection.objects.link(joint)
    return joint


def clamp(value, mmin, mmax):
    return max(min(value, mmax), mmin)


def encode_asset_id(obj):
    prop = lambda x: "<%s %s>" % (x, getattr(obj, x, "<unk>"))
    obj_prop = lambda x: "<%s %s>" % (
        x,
        (
            getattr(obj.object_reader, x, "<unk>")
            if hasattr(obj, "object_reader")
            else "<unk>"
        ),
    )
    return f"""{prop('m_Name')},{obj_prop('container')},{obj_prop('path_id')}"""


# Import helpers
class _registry:
    classes = list()
    wm_props = dict()

    def add_register_class(self, clazz):
        self.classes.append(clazz)

    def register_all(self):
        for clazz in self.classes[::-1]:
            bpy.utils.register_class(clazz)

    def unregister_all(self):
        for clazz in self.classes:
            bpy.utils.unregister_class(clazz)
        self.classes.clear()

    # ---
    def add_register_wm(self, **kw):
        self.wm_props.update(kw)

    def register_all_wm(self):
        for k, v in self.wm_props.items():
            setattr(bpy.types.WindowManager, k, v)

    def unregister_all_wm(self):
        for k, v in self.wm_props.items():
            setattr(bpy.types.WindowManager, k, None)
        self.wm_props.clear()

    # ---
    def reset(self):
        self.classes.clear()
        self.wm_props.clear()


registry = _registry()


def register_class(clazz):
    registry.add_register_class(clazz)
    return clazz


def register_wm_props(**kw):
    registry.add_register_wm(**kw)


# Data Types
class BonePhysicsType(IntEnum):
    NoPhysics = 0x00

    Bone = 0x10
    SpringBone = 0x11

    Collider = 0x20
    SphereCollider = 0x21
    CapsuleCollider = 0x22

    Manager = 0x30
    SpringManager = 0x30


@dataclass
class BoneAngularLimit:
    active: bool = 0
    # In degrees
    min: float = 0
    max: float = 0


@dataclass
class BonePhysics:
    type: BonePhysicsType = BonePhysicsType.NoPhysics

    radius: float = 0
    height: float = 0

    # SpringBones only
    pivot: str = ""  # Bone name. Could be None
    springForce: float = 0
    dragForce: float = 0
    angularStiffness: float = 0
    yAngleLimits: BoneAngularLimit = None
    zAngleLimits: BoneAngularLimit = None

    @staticmethod
    def from_dict(data: dict):
        phy = dataclass_from_dict(BonePhysics, data, warn_missing_fields=False)
        return phy


@dataclass
class Bone:
    name: str
    localPosition: uVector3
    localRotation: uQuaternion
    localScale: uVector3
    # Hierarchy. Built after asset import
    parent: object  # Bone
    children: list  # Bone
    global_path: str
    global_transform: blMatrix = None
    # Physics
    physics: BonePhysics = None
    gameObject: object = None  # Unity GameObject

    # Helpers
    def get_blender_local_position(self):
        return swizzle_vector(self.localPosition)

    def get_blender_local_rotation(self):
        return swizzle_quaternion(self.localRotation)

    def to_translation_matrix(self):
        return blMatrix.Translation(swizzle_vector(self.localPosition))

    def to_trs_matrix(self):
        return blMatrix.LocRotScale(
            swizzle_vector(self.localPosition),
            swizzle_quaternion(self.localRotation),
            swizzle_vector_scale(self.localScale),
        )

    def dfs_generator(self, root=None):
        def dfs(bone: Bone, parent: Bone = None, depth=0):
            yield parent, bone, depth
            for child in bone.children:
                yield from dfs(child, bone, depth + 1)

        yield from dfs(root or self)

    def calculate_global_transforms(self):
        """Calculates global transforms for this bone and all its children recursively."""
        if not self.global_transform:
            self.global_transform = blMatrix.Identity(4)
        for parent, child, _ in self.dfs_generator():
            if parent:
                child.global_transform = parent.global_transform @ child.to_trs_matrix()
            else:
                child.global_transform = child.to_trs_matrix()

    def recursive_search(self, predicate=lambda x: True):
        """Searches for a bone that matches the predicate, recursively."""
        for parent, child, _ in self.dfs_generator():
            if predicate(child):
                yield child

    def recursive_locate_by_name(self, name):
        try:
            return next(self.recursive_search(lambda x: x.name == name))
        except StopIteration:
            return None

    # Extra
    edit_bone: object = None  # Blender EditBone


@dataclass
class Armature:
    name: str
    is_articulation: bool = False
    skinnedMeshGameObject: GameObject = None
    root: Bone = None
    # Tables
    bone_path_hash_tbl: Dict[int, Bone] = None
    bone_name_tbl: Dict[str, Bone] = None

    # Helpers
    def get_bone_by_path(self, path: str):
        return self.bone_path_hash_tbl[get_name_hash(path)]

    def get_bone_by_name(self, name: str):
        return self.bone_name_tbl[name]


# Evil(!!) global variables
# Copilot autocompleted this after 'evil' lmao
class SSSekaiGlobalEnvironment:
    current_dir: str = None
    current_enum_entries: list = None
    # --- SSSekai exclusive
    env: Environment
    articulations: Set[Armature]
    armatures: Set[Armature]
    animations: Set[Animation]
    # --- RLA exclusive
    rla_sekai_streaming_live_bundle_path: str = None
    rla_header: dict = dict()
    rla_clip_data: dict = dict()
    rla_selected_raw_clip: str = 0
    rla_raw_clips: dict = dict()
    rla_animations: dict = dict()  # character ID -> Animation
    rla_clip_tick_range: tuple = (0, 0)
    rla_clip_charas: set = set()
    rla_enum_entries: list = None
    rla_enum_bookmarks: list = []

    def rla_get_version(self):
        return (
            tuple(map(int, sssekai_global.rla_header["version"].split(".")))
            if "version" in sssekai_global.rla_header
            else (0, 0)
        )


sssekai_global = SSSekaiGlobalEnvironment()
