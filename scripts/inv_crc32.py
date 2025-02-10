# Simple script to reverse crc32 to find the name of the attribute
# that's used in the animation clips
# ---
# A CSV file will be printed to stdout. collect with
# `python inv_crc32.py > inv_crc32.csv`
# Pass `nocsv` to disable the CSV output
# `python inv_crc32.py nocsv`
# ---
from sssekai.unity.AnimationClip import (
    read_animation,
    Animation,
    kBindTransformEuler,
    kBindTransformPosition,
    kBindTransformScale,
    kBindTransformRotation,
)
from sssekai.unity.AssetBundle import load_assetbundle
from UnityPy.enums import ClassIDType
from zlib import crc32
import colorama as Col
import sys

Col.init()
logprint = lambda *a, **k: print(*a, **k, file=sys.stderr, sep="")
pvid = "0133"
f = open(
    f"/Volumes/mos9527弄丢的盘/Reverse/proseka_reverse/assets/live_pv/timeline/{pvid}/camera",
    "rb",
)
aux_kws = ["r", "g", "b"] + ["x", "y", "z", "w"] + ["postProcess"]
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
    # PostEffectV2
    "PostEffectV2",
    "quality",
    "enableSekaiDof",
    "focusDistance",
    "transitionRange",
    "focalRegion",
    "aperture",
    "focalLength",
    "disableForeBokeh",
    "intensity",
    "scatter",
    "newBloomBlend",
    "brightColor",
    "darkColor",
    "brightPosition",
    "darkPosition",
    "incidentLightType",
    "incidentLightColor",
    "incidentLightPosition",
    "incidentLightLength",
    "sat",
    "satAlpha",
    "saturationModule",
    "directionalBlurParamType",
    "directionalBlurStrength",
    "directionalBlurDirection",
    "radialBlurCenterPosition",
    "solarization",
    "fadeOut",
    "fadeOutLerp",
    "fadeOutBeforeProp",
    "fadeOutBeforePropLerp",
    "frontLut",
    "backLut",
    "frontLutBlend",
    "backLutBlend",
    "frontLutPoint",
    "frontNonLutPoint",
    "backLutPoint",
    "backNonLutPoint",
    "antialiasingMode",
]
kws = kws + [f"{attr}.{aux}" for attr in kws for aux in aux_kws]
kws = {crc32(k.encode()): k for k in kws}
kws = kws | {
    kBindTransformEuler: "Euler",
    kBindTransformPosition: "Position",
    kBindTransformScale: "Scale",
    kBindTransformRotation: "Quaternion",
}
env = load_assetbundle(f)
valid_kws, missing_kws = set(), set()
for anim in filter(lambda obj: obj.type == ClassIDType.AnimationClip, env.objects):
    data = anim.read()
    anim: Animation = read_animation(data)
    if not anim.Name.startswith("depth_of_field"):
        continue
    logprint(Col.Fore.WHITE, Col.Style.BRIGHT, data.m_Name, Col.Style.RESET_ALL)
    for path in anim.CurvesT:
        if path in kws:
            logprint("\t", Col.Fore.WHITE, path, "\t", Col.Fore.GREEN, kws[path])
            valid_kws.add(path)
        else:
            logprint("\t", Col.Fore.RED, path, "\tNOT FOUND")
            missing_kws.add(path)
        for attr in anim.CurvesT[path]:
            if attr in kws:
                logprint("\t\t", Col.Fore.WHITE, attr, "\t", Col.Fore.GREEN, kws[attr])
                valid_kws.add(attr)
            else:
                logprint("\t\t", Col.Fore.RED, attr, "\tNOT FOUND")
                missing_kws.add(attr)
    pass
logprint(
    Col.Style.RESET_ALL,
    len(missing_kws),
    " missing attribute(s): ",
    ",".join((str(k) for k in sorted(missing_kws))),
)
if sys.argv[-1] != "nocsv":
    print("hash", "name", sep=",")
    for k in valid_kws:
        print(k, kws[k], sep=",")
