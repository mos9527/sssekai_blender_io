# sssekai_blender_io
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Blender importer for Project SEKAI (JP: プロジェクトセカイ カラフルステージ！ feat.初音ミク), and generic Unity AssetBundle files.

Supports Blender 3.x and up.

## Documentation
**ATTENTION:** The Wiki is undergoing revisions and is not up-to-date. Please wait for further notice.

Read the [wiki page](https://github.com/mos9527/sssekai_blender_io/wiki) for more!

## Supported Languages
PRs are welcome for additions. 
- You can find the translation file [here](https://github.com/mos9527/sssekai_blender_io/tree/master/translations.py).
- The script used to generate the translation file is [here](https://github.com/mos9527/sssekai_blender_io/tree/master/translations_codegen.py). Run this in the root of this repo, with any Python 3.8+ interpreter to update the translation file. Existing translations will be preserved.

You can find your language code by entering `bpy.app.translations.locale` in the Blender Python console.

Currently supported languages and maintainers:
- English (en_US, mos9527, @Rypie109)
- 简体中文 (zh_HANS, mos9527)

## Installing & Updating
`sssekai_blender_io` depends on [`sssekai`](https://github.com/mos9527/sssekai), which in turn uses [`UnityPy`](https://github.com/K0lb3/UnityPy) for Unity asset IO.

For this reason, do NOT download the repo as zip and install as you won't be able to manage dependencies, or run at all without manual setup.

The following methods are recommended for consuming the addon.
### With Addon Bundle
Prebuilt bundles are not provided for binary ABI compatibility reasons. 

[The Bundle Script](https://github.com/mos9527/sssekai_blender_io/blob/master/bundle.py) is provided to build a self-contained addon bundle for your Blender version. Please follow the instructions in the script to build the bundle.

### With the Bootstrapper
You can semi-automatically update the addon using the [Bootstrapper](https://github.com/mos9527/sssekai_blender_io/blob/master/bootstrap.py).

**Portable** version of Blender is highly recommended when using the Bootstrapper. 

#### Attention
**To Windows 11 Users** 
- If you'd specify the addon source directory - which in turns creates a symlink - you'll have to enable Developer Mode in Windows 11 otherwise it's **not going to work**.

**To ones who have installed Blender to Program Files**
- This would be the case if you'd install Blender through the offical MSI installer, or in some cases when Blender is installed through Steam - whilst using the default Steam Library location
- Using a non-portable Blender installation makes the updater unable to modify addon files.
- Either:
  1. Download and use the portable version of Blender instead
  2. Or run Blender as Administrator when using the Bootstrapper.
    - You don't have to run Blender as Administrator when using the addon normally, only when updating the addon through the Bootstrapper.
  3. Setup file permissions for the Blender installation directory to allow the updater to modify files.
    - This is not recommended as it can be a security risk.
#### To use the Bootstrapper
- Make sure you have [Git](https://git-scm.com/downloads) installed on your system.
- Download the addon [Bootstrapper](https://github.com/mos9527/sssekai_blender_io/blob/master/bootstrap.py)
- Install the Bootstrapper in Blender by going to `Edit > Preferences > Add-ons > Install...` and selecting the Bootstrapper, which is a `.py` file.
- Enable the Bootstrapper in Blender by checking the box next to it.
- Follow the instructions in the Bootstrapper to install or update the addon.
- Once done, search for `SSSekai` and enable `SSSekai Blender IO` - which is the main addon.
- You can come back to the Bootstrapper to update the addon at any time.

The addon will be accessible in the sidebar (`N` key) in the `SSSekai` tab.

### Known Issues
- ~~Doesn't handle scenes with multiple objects of the same name.~~

### Roadmap
#### Asset
- ~~Handle Skinned Mesh with non-Identity Bind Pose~~
  - Done. Also applies to generic Unity assets
- ~~Handle Skinned Mesh with non-Identity Rest Pose~~
  - Done. Also applies to generic Unity assets
- Custom `Animator` for animation import
  - Path CRC32 table can now be done through `m_Avatar`
- ~~Implement Animator bindpose~~
  - Done. Usually not a requirement however.
#### Rendering
- One-key Outline Modifier(s) for Sekai characters (World-space, normal offset + stencil masking)
  - See also https://mos9527.com/posts/pjsk/shading-reverse-part-2/
- Accurate reproduction of the game's lighting
  - ~~Face light (SDF for v2, simple $N \cdot L$ for legacy)~~
    - ~~*NOTE*: Current SDF implementation does not handle relative light directions~~
    - Fixed. See also https://mos9527.com/en/posts/pjsk/shading-reverse-part-3/
  - ~~Directional Light (`SekaiCharacterDirectionalLight`)~~
    - ~~Not specialized at all and does not support colors as of now~~
    - Fixed. See also https://mos9527.com/posts/pjsk/shading-reverse-part-2/
  - ~~Rim Light (`SekaiCharacterRimLight`)~~
  - ~~Ambient Light (`SekaiAmbientLight`, `SekaiCharacterAmbientLight`)~~
  
#### Effects
- Post processing (PostEffectV2)
  - LUT. https://github.com/mos9527/blender-image-lut
  - Bloom from Rim lights
  - Depth of Field
  - Vignette
  - Solarization
  - Saturation
  - See also https://mos9527.com/posts/pjsk/shading-reverse-part-1/
- Sub-cameras (off-screen cameras)
  - Animations can be imported
- Blob shadows
- Particles?
  - Most probably WONTFIX.
#### Animation
- ~~Light animation~~
  - Done. Applies to directional lights, rim lights and ambient lights
  - **XXX:** Implementation shows severe performance regression with animated lights in Blender 4.0+
- Effect animation
  - Articulated (GameObject animations) ones work OOTB.
  - Particles not at all supported.
- Approximate Unity's IK system
  - Since [My Sekai](https://pjsekai.sega.jp/news/archive/index.html?hash=ecca5cb23ea530edb669fc0d2ae302fd0f374a4b) is a thing now and the chibi models are rigged with Unity's IK system.  
  - Also would be nice since all Unity games with humanoid characters use this system.
  - This would also make retargeting trivial.
#### QoL
- ~~An actual updater~~
  - Use the [Bootstrapper](https://github.com/mos9527/sssekai_blender_io/blob/master/bootstrap.py)
- ~~**Cleanup** temp files after importing.~~
  - Done. Images will be cleaned up after import and packed into the blend file.
## License
MIT

## References
- https://github.com/K0lb3/UnityPy
- https://github.com/KhronosGroup/glTF-Blender-IO
- https://github.com/theturboturnip/yk_gmd_io
- https://github.com/SutandoTsukai181/yakuza-gmt-blender
- https://github.com/UuuNyaa/blender_mmd_tools
- https://github.com/Pauan/blender-rigid-body-bones
- https://zhuanlan.zhihu.com/p/411188212
- https://zhuanlan.zhihu.com/p/337944099
- https://zhuanlan.zhihu.com/p/670837192
- https://github.com/przemir/ApplyModifierForObjectWithShapeKeys
- https://www.academia.edu/9781223/Matrix_Form_for_Cubic_B%C3%A9zier_Curves_Converting_Between_Cubic_Spline_Types
- https://pomax.github.io/bezierinfo/#catmullconv