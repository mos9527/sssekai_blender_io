from enum import IntEnum
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Generator
from .utils import dataclass_from_dict
from .math import (
    swizzle_vector,
    swizzle_quaternion,
    swizzle_vector_scale,
    uVector3,
    uQuaternion,
    blMatrix,
)
from UnityPy.classes import GameObject


@dataclass
class HierarchyNode:
    name: str
    path_id: int

    # Transform (in Local Space, Unity coordinates)
    position: uVector3
    rotation: uQuaternion
    scale: uVector3

    # Graph relations
    parent: object = None  # HierarchyNode
    children: List[object] = field(default_factory=list)  # HierarchyNode

    # Cached global attributes
    """Global transform in Blender coordinates. NOTE: You will need to update this manually with `update_global_transforms`"""
    global_transform: blMatrix = blMatrix.Identity(4)

    # Unity-specific
    game_object: GameObject = None

    def __hash__(self):
        return self.path_id

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

    def children_recursive(
        self, root=None
    ) -> Generator[Tuple[object, object, int], None, None]:
        """Yields a tuple of (parent, child, depth) for each bone in the hierarchy.

        The tree is traversed in depth-first order and from top to bottom.
        """

        def dfs(bone: HierarchyNode, parent: HierarchyNode = None, depth=0):
            yield parent, bone, depth
            for child in bone.children:
                yield from dfs(child, bone, depth + 1)

        yield from dfs(root or self)

    def update_global_transforms(self):
        """Calculates global transforms for this bone and all its children recursively."""
        for parent, child, _ in self.children_recursive():
            if parent:
                child.global_transform = parent.global_transform @ child.to_trs_matrix()
            else:
                child.global_transform = child.to_trs_matrix()


@dataclass
class Hierarchy:
    name: str

    # Graph relations
    root: HierarchyNode = None
    nodes: Dict[int, HierarchyNode] = field(default_factory=dict)
    named_nodes: Dict[str, HierarchyNode] = field(default_factory=dict)

    @property
    def path_id(self):
        return self.root.path_id
