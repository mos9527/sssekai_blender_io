# Simple script to reverse crc32 to find the name of the attribute
# that's used in the animation clips
# ---
# A CSV file will be printed to stdout. collect with
# `python inv_crc32.py > inv_crc32.csv`
from sssekai.unity.AnimationClip import read_animation, Animation
from sssekai.unity.AssetBundle import load_assetbundle
from UnityPy.enums import ClassIDType
from zlib import crc32
import colorama as Col
import sys

Col.init()
logprint = lambda *a, **k: print(*a, **k, file=sys.stderr, sep="")
pvid = "0474"
f = open(
    f"/Volumes/mos9527弄丢的盘/Reverse/proseka_reverse/assets/live_pv/timeline/{pvid}/light",
    "rb",
)
aux_kws = ["r", "g", "b"] + ["x", "y", "z", "w"]
kws = [
    # SekaiCharacterAmbientLight
    "ambientColor",
    "intensity",
    "specularColor",
    "outlineColor",
    "outlineBlending",
    # SekaiDirectionalLight
    "shadowColor",
    "shadowThreshold",
    # SekaiCharacterDirectionalLight
    "useFaceShadowLimiter",
    "faceShadowLimitRange",
    "shadowTexWeight",
    # SekaiCharacterRimLight
    "rimColor",
    "range",
    "edgeSmoothness",
    "emission",
    "directionMode",
    "rimDirectionVector",
    "lightInfluence",
    "isUseShadowColor",
    "shadowRimColor",
    "shadowSharpness",
    # SekaiGlobalSettings
    "fogColor",
    "fogStart",
    "fogEnd",
    "quality",
]
kws = kws + [f"{attr}.{aux}" for attr in kws for aux in aux_kws]
kws = {crc32(k.encode()): k for k in kws} | {0: "<transform>"}
env = load_assetbundle(f)
valid_kws, missing_kws = set(), set()
for anim in filter(lambda obj: obj.type == ClassIDType.AnimationClip, env.objects):
    data = anim.read()
    anim: Animation = read_animation(data)
    logprint(Col.Fore.WHITE, Col.Style.BRIGHT, data.m_Name, Col.Style.RESET_ALL)
    for attr in anim.FloatTracks.get(0, {}):
        if attr in kws:
            logprint("\t", Col.Fore.WHITE, attr, "\t", Col.Fore.GREEN, kws[attr])
            valid_kws.add(attr)
        else:
            logprint("\t", Col.Fore.RED, attr, "\tNOT FOUND")
            missing_kws.add(attr)
    pass
logprint(
    Col.Style.RESET_ALL,
    len(missing_kws),
    " missing attribute(s): ",
    ",".join((str(k) for k in sorted(missing_kws))),
)
print("hash", "name", sep=",")
for k in valid_kws:
    print(k, kws[k], sep=",")
