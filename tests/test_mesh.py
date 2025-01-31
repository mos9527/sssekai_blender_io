from tests import *

from UnityPy.classes import MeshRenderer, UnityTexEnv, Texture2D
from UnityPy.helpers import MeshHelper
from UnityPy.enums import ClassIDType


def test_mesh():
    PATH = sample_file_path("mesh", "face_31_0001")
    with open(PATH, "rb") as f:
        env = load_assetbundle(f)
        for rnd in filter(
            lambda obj: obj.type == ClassIDType.MeshRenderer, env.objects
        ):
            rnd = rnd.read()
            mesh = rnd.m_Mesh.read()
            mesh = MeshHelper.MeshHandler(mesh)
            mesh.process()
            for mat in rnd.m_Materials:
                mmat = mat.read()
                texs = mmat.m_SavedProperties.m_TexEnvs

                def read_one(tex):
                    tex: UnityTexEnv
                    ttex = tex.m_Texture.read()
                    ttex: Texture2D
                    image = ttex.image
                    image.save(os.path.join(TEMP_DIR, "sssekai_test_temp.tga"))

                for k, tex in texs:
                    try:
                        read_one(tex)
                        logger.info("tex %s pass" % k)
                    except Exception as e:
                        logger.warning("tex %s fail: %s" % (k, e))
            logger.info("ok. mesh was: %s" % rnd.m_GameObject.m_Name)


if __name__ == "__main__":
    test_mesh()
