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
    blVector,
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

    def to_tr_matrix(self):
        return blMatrix.LocRotScale(
            swizzle_vector(self.position),
            swizzle_quaternion(self.rotation),
            blVector((1, 1, 1)),
        )

    def to_trs_matrix(self):
        return blMatrix.LocRotScale(
            swizzle_vector(self.position),
            swizzle_quaternion(self.rotation),
            swizzle_vector_scale(self.scale),
        )

    def children_recursive(
        self, root=None
    ) -> Generator[Tuple["HierarchyNode", "HierarchyNode", int], None, None]:
        """Yields a tuple of (parent, child, depth) for each bone in the hierarchy.

        The tree is traversed in depth-first order and from top to bottom.
        """

        def dfs(bone: HierarchyNode, parent: HierarchyNode = None, depth=0):
            yield parent, bone, depth
            for child in bone.children:
                yield from dfs(child, bone, depth + 1)

        yield from dfs(root or self)

    def update_global_transforms(self, scale=False):
        """Calculates global transforms for this bone and all its children recursively."""
        for parent, child, _ in self.children_recursive():
            transform = child.to_trs_matrix() if scale else child.to_tr_matrix()
            if parent:
                child.global_transform = parent.global_transform @ transform
            else:
                child.global_transform = transform


@dataclass
class Hierarchy:
    name: str

    # Graph relations
    root: HierarchyNode = None
    # PathID:Node
    nodes: Dict[int, HierarchyNode] = field(default_factory=dict)
    # PathID:PathID
    parents: Dict[int, int] = field(default_factory=dict)

    @property
    def path_id(self):
        return self.root.path_id

    @staticmethod
    def from_node(node: HierarchyNode):
        """Create the hierarchy from a single node, with it as the new root"""
        hierarchy = Hierarchy(node.name, node)
        for parent, child, _ in node.children_recursive():
            hierarchy.nodes[child.path_id] = child
            hierarchy.parents[child.path_id] = parent.path_id
        return hierarchy
