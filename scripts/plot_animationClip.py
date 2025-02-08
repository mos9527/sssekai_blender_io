from sssekai.unity.AssetBundle import load_assetbundle
from sssekai.unity.AnimationClip import (
    read_animation,
    vec3_quat_as_floats,
    kBindTransformEuler,
)
from UnityPy.enums import ClassIDType
import UnityPy
from matplotlib import pyplot as plt
from numpy import arange
from zlib import crc32

# Not going in the auto tests yet
UnityPy.config.FALLBACK_VERSION_WARNED = True
UnityPy.config.FALLBACK_UNITY_VERSION = "2022.3.21f1"
path = b"Stage_joint/LS_laser_light_01/LS_laser_light_01_02/LS_laser_light_01_03/LS_laser_light_01_04_02"
env = UnityPy.load(r"tests/animation/pv095_stage")
for anim in filter(lambda obj: obj.type == ClassIDType.AnimationClip, env.objects):
    anim = anim.read()
    anim = read_animation(anim)
    if anim.Name.endswith("0095_01"):
        print("Time", "Value", "InSlope", "OutSlope", "Interpolation", sep="\t")
        t = arange(0, anim.Duration, 0.01)
        curve = anim.CurvesT[crc32(path)][kBindTransformEuler]
        for key in curve.Data:
            print(
                "%.2f" % key.time,
                key.value,
                key.inSlope,
                key.outSlope,
                key.interpolation_segment(key, key.next),
                sep="\t",
            )
            c = [vec3_quat_as_floats(curve.evaluate(x)) for x in t]
            plt.plot(t, c, label=curve.Path)
        plt.legend()
        plt.show()

        break
