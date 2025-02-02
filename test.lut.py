from sssekai.unity.AssetBundle import load_assetbundle
from sssekai.unity.AnimationClip import read_animation, vec3_quat_as_floats
from UnityPy.enums import ClassIDType, TextureFormat
from UnityPy.export.Texture2DConverter import pillow
import UnityPy
from matplotlib import pyplot as plt
from numpy import arange

# Not going in the auto tests yet
UnityPy.config.FALLBACK_VERSION_WARNED = True
UnityPy.config.FALLBACK_UNITY_VERSION = "2022.3.21f1"
env = UnityPy.load(f"tests/lut/camera_0181")
monos = [
    obj.read()
    for obj in filter(lambda obj: obj.type == ClassIDType.MonoBehaviour, env.objects)
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
    lut2D.save("test." + clip.m_DisplayName + ".png")
    pass
pass
