from enum import IntEnum
from dataclasses import dataclass
from typing import Dict
from .utils import dataclass_from_dict, get_name_hash
from .math import (
    swizzle_vector,
    swizzle_quaternion,
    swizzle_vector_scale,
    uVector3,
    uQuaternion,
    blMatrix,
)
from UnityPy.classes import GameObject


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
