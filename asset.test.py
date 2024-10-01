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
from UnityPy.math import Vector3, Quaternion as UnityQuaternion
from sssekai.unity import sssekai_get_unity_version

UnityPy.config.FALLBACK_VERSION_WARNED = True
UnityPy.config.FALLBACK_UNITY_VERSION = sssekai_get_unity_version()
from blender.asset import search_env_meshes

env = UnityPy.load(r"C:\Users\mos9527\.sssekai\bundles")
articulations, armatures = search_env_meshes(env)
for armature in armatures:
    if "v2/face/31/9001" in armature.root.gameObject.container:
        for parent, bone, depth in armature.root.dfs_generator():
            if bone.gameObject and getattr(
                bone.gameObject, "m_SkinnedMeshRenderer", None
            ):
                print("* Found Skinned Mesh at", bone.name)
                mesh_rnd: SkinnedMeshRenderer = (
                    bone.gameObject.m_SkinnedMeshRenderer.read()
                )
                if getattr(mesh_rnd, "m_Mesh", None):
                    mesh_data: Mesh = mesh_rnd.m_Mesh.read()
                    pass
        pass
pass
