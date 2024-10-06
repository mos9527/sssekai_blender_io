from tests import *
from blender.asset import search_env_meshes
from sssekai.unity.Mesh import read_mesh


def test_mesh():
    PATH = sample_file_path("mesh", "face_31_0001")
    with open(PATH, "rb") as f:
        env = load_assetbundle(f)
        articulations, armatures = search_env_meshes(env)
        for mesh in armatures:
            go = mesh.skinnedMeshGameObject
            rnd = go.m_SkinnedMeshRenderer.read()
            mesh = rnd.m_Mesh.read()
            mesh = read_mesh(mesh)
            logger.info("ok. mesh was: %s" % go.m_Name)


test_mesh()
