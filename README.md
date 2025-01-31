# sssekai_blender_io
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Blender asset importer for Project SEKAI (JP: プロジェクトセカイ カラフルステージ！ feat.初音ミク) asset bundles.

## Documentation
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
  **PLEASE NOTE:**
  The updater is still a W.I.P and has bugs! Please report them in the [issues](https://github.com/mos9527/sssekai_blender_io/issues) tab if you encounter one.
  
- Make sure you have [Git](https://git-scm.com/downloads) installed on your system.
- Download the addon [Bootstrapper](https://github.com/mos9527/sssekai_blender_io/blob/master/bootstrap.py)
- Install the Bootstrapper in Blender by going to `Edit > Preferences > Add-ons > Install...` and selecting the Bootstrapper, which is a `.py` file.
- Enable the Bootstrapper in Blender by checking the box next to it.
- Follow the instructions in the Bootstrapper to install or update the addon.
- Once done, search for `SSSekai` and enable `SSSekai Blender IO` - which is the main addon.
- You can come back to the Bootstrapper to update the addon at any time.

The addon will be accessible in the sidebar (`N` key) in the `SSSekai` tab.

### Roadmap
#### Asset
- ~~Handle Skinned Mesh with non-Identity Bind Pose~~
  - Done. Also applies to generic Unity assets
- ~~Handle Skinned Mesh with non-Identity Rest Pose~~
  - Done. Also applies to generic Unity assets
- Custom `Animator` for animation import
  - Path CRC32 table can now be done through `m_Avatar`
  - TODO: Implement Animator bindpose
#### Lighting
NOTE: Mostly done
- 1-to-1 approximation of the game's lighting system
  - ~~Face light (SDF for v2, simple $N \cdot L$ for legacy)~~
    - ~~*NOTE*: Current SDF implementation does not handle relative light directions~~
    - Fixed. See also https://mos9527.com/en/posts/pjsk/shading-reverse-part-3/
  - ~~Directional Light (`SekaiCharacterDirectionalLight`)~~
    - ~~Not specialized at all and does not support colors as of now~~
    - Fixed. See also https://mos9527.com/posts/pjsk/shading-reverse-part-2/
  - ~~Rim Light (`SekaiCharacterRimLight`)~~
  - ~~Ambient Light (`SekaiAmbientLight`, `SekaiCharacterAmbientLight`)~~
  - ...
#### Effects
- Post processing
  - See also https://mos9527.com/posts/pjsk/shading-reverse-part-1/
- Sub-cameras (off-screen cameras)
- Blob shadows
- Particles
#### Animation
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