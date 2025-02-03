from tests import *
from sssekai.unity.AssetBundle import load_assetbundle
from UnityPy.enums import ClassIDType
from UnityPy.export.Texture2DConverter import pillow
from PIL import Image


def test_dof():
    PATH = sample_file_path("lut", "camera_0181")
    with open(PATH, "rb") as f:
        env = load_assetbundle(f)
    monos = [
        obj.read()
        for obj in filter(
            lambda obj: obj.type == ClassIDType.MonoBehaviour, env.objects
        )
    ]
    monos = {obj.m_Name: obj for obj in monos}  # XXX: Same names
    lut = monos["Sekai Dof Track"]
    pass


if __name__ == "__main__":
    test_dof()
