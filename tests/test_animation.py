from tests import *
from sssekai.unity.AnimationClip import read_animation
from UnityPy.enums import ClassIDType


def test_animation():
    PATH = sample_file_path("animation", "pv001_character")
    with open(PATH, "rb") as f:
        env = load_assetbundle(f)
        for anim in filter(
            lambda obj: obj.type == ClassIDType.AnimationClip, env.objects
        ):
            clip = read_animation(anim.read())
            print("ok. animation was: %s" % clip.Name)


if __name__ == "__main__":
    test_animation()
