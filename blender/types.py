from enum import IntEnum
from dataclasses import dataclass, field
from typing import Dict, List
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


class SekaiBonePhysicsType(IntEnum):
    NoPhysics = 0x00

    Bone = 0x10
    SpringBone = 0x11

    Collider = 0x20
    SphereCollider = 0x21
    CapsuleCollider = 0x22

    Manager = 0x30
    SpringManager = 0x30


@dataclass
class SekaiBoneAngularLimit:
    active: bool = 0
    # In degrees
    min: float = 0
    max: float = 0


@dataclass
class SekaiBonePhysics:
    type: SekaiBonePhysicsType = SekaiBonePhysicsType.NoPhysics

    radius: float = 0
    height: float = 0

    # SpringBones only
    pivot: str = ""  # Bone name. Could be None
    springForce: float = 0
    dragForce: float = 0
    angularStiffness: float = 0
    yAngleLimits: SekaiBoneAngularLimit = None
    zAngleLimits: SekaiBoneAngularLimit = None

    @staticmethod
    def from_dict(data: dict):
        phy = dataclass_from_dict(SekaiBonePhysics, data, warn_missing_fields=False)
        return phy


@dataclass
class HierarchyNode:
    name: str

    # Transform (in Local Space)
    position: uVector3
    rotation: uQuaternion
    scale: uVector3
    # Graph relations
    parent: object = None  # HierarchyNode
    children: List[object] = field(default_factory=list)  # HierarchyNode
    # Cached global attributes
    global_path: List[str] = field(default_factory=list)
    global_transform: blMatrix = blMatrix.Identity(4)
    # Attributes
    game_object: GameObject = None
    # Sekai Specific
    sekai_physics: SekaiBonePhysics = None

    # Helpers
    def get_blender_local_position(self):
        return swizzle_vector(self.position)

    def get_blender_local_rotation(self):
        return swizzle_quaternion(self.rotation)

    def to_translation_matrix(self):
        return blMatrix.Translation(swizzle_vector(self.position))

    def to_trs_matrix(self):
        return blMatrix.LocRotScale(
            swizzle_vector(self.position),
            swizzle_quaternion(self.rotation),
            swizzle_vector_scale(self.scale),
        )

    def dfs_generator(self, root=None):
        def dfs(bone: HierarchyNode, parent: HierarchyNode = None, depth=0):
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
class Hierarchy:
    name: str

    root: HierarchyNode = None
    nodes: Dict[str, HierarchyNode] = None

    # Tables
    # CRC32 hash table of global path concatenated with / (e.g. Position/Body/Neck/Head)
    global_path_hash_table: Dict[int, HierarchyNode] = None

    # Helpers
    def get_bone_by_path(self, path: str):
        return self.global_path_hash_table[get_name_hash(path)]

    def get_bone_by_name(self, name: str):
        return self.nodes[name]
