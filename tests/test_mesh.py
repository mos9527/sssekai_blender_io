from tests import *
from blender.asset import search_env_meshes
from sssekai.unity.Mesh import read_mesh

from UnityPy.classes import MeshRenderer, UnityTexEnv, Texture2D


def test_mesh():
    PATH = sample_file_path("mesh", "face_31_0001")
    with open(PATH, "rb") as f:
        env = load_assetbundle(f)
        articulations, armatures = search_env_meshes(env)
        for arma in armatures:
            go = arma.skinnedMeshGameObject
            rnd: MeshRenderer = go.m_SkinnedMeshRenderer.read()
            mesh = rnd.m_Mesh.read()
            mesh = read_mesh(mesh)
            for mat in rnd.m_Materials:
                mmat = mat.read()
                texs = mmat.m_SavedProperties.m_TexEnvs

                def read_one(tex):
                    tex: UnityTexEnv
                    ttex = tex.m_Texture.read()
                    ttex: Texture2D
                    print(ttex)
                    ttex.image.save(os.path.join(TEMP_DIR, "sssekai_test_temp.tga"))

                for k, tex in texs:
                    try:
                        read_one(tex)
                        logger.info("tex %s pass" % k)
                    except Exception as e:
                        logger.warning("tex %s fail: %s" % (k, e))
            logger.info("ok. armature was: %s" % arma.name)


if __name__ == "__main__":
    test_mesh()
