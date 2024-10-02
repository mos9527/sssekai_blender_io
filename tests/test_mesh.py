from tests import *
from blender.asset import search_env_meshes


def test_mesh():
    PATH = sample_file_path("model", "ladies_s")
    with open(PATH, "rb") as f:
        env = load_assetbundle(f)
        articulations, armatures = search_env_meshes(env)
        for mesh in armatures:
            go = mesh.skinnedMeshGameObject
            rnd = go.m_SkinnedMeshRenderer
            pass
        pass


test_mesh()
logger.info("all passed")
