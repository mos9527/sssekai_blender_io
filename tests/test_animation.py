from tests import *
from blender.asset import search_env_animations
from sssekai.unity.AnimationClip import read_animation


def test_mesh():
    PATH = sample_file_path("animation", "pv001_character")
    with open(PATH, "rb") as f:
        env = load_assetbundle(f)
        anims = search_env_animations(env)
        for anim in anims:
            clip = read_animation(anim)
            print("ok. animation was: %s" % anim.m_Name)


test_mesh()
