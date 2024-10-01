from tests import *
from blender.asset import search_env_meshes


def test_mesh():
    PATH = sample_file_path("model", "ladies_s")
    with open(PATH, "rb") as f:
        env = load_assetbundle(f)
        r = search_env_meshes(env)


test_mesh()
logger.info("all passed")
