from tests import *
from sssekai.unity.AssetBundle import load_assetbundle
from UnityPy.enums import ClassIDType
from UnityPy.export.Texture2DConverter import pillow
from PIL import Image


def test_lut():
    PATH = sample_file_path("lut", "camera_0181")
    with open(PATH, "rb") as f:
        env = load_assetbundle(f)
    monos = [
        obj.read()
        for obj in filter(
            lambda obj: obj.type == ClassIDType.MonoBehaviour, env.objects
        )
    ]
    monos = {obj.m_Name: obj for obj in monos}
    lut = monos["Lut Track"]
    for clip in lut.m_Clips:
        asset = clip.m_Asset
        asset = asset.read()
        lutbehaviour = asset.template
        texture3d = lutbehaviour.texture3D.read()
        """
        Texels are layed out as follows.
        for z in Depth:
            for y in Height:
                for x in Width:
                    texel [i = x + y * W + z * W * D] at (x, y, z)
        """
        lut2D = pillow(
            texture3d.image_data,
            texture3d.m_Width * texture3d.m_Depth,
            texture3d.m_Height,
            "RGBA",
            "raw",
            "RGBA",
            swap=(0, 2, 1, 3),  # RBGA??
        )
        """
        LUT[r,g,b] = LUT_2D[r + b * W, g]
        """
        save = os.path.join(TEMP_DIR, clip.m_DisplayName + ".png")
        lut2D.save(save)
        print("LUT@%.3fs\t%s" % (clip.m_Start, save))
        pass
    pass


if __name__ == "__main__":
    test_lut()
