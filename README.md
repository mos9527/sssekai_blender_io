# sssekai_blender_io
Blender asset importer for Project SEKAI (JP: プロジェクトセカイ カラフルステージ！ feat.初音ミク) asset bundles.

Tested on Blender `4.0.3`, `4.2.0 Alpha`, `4.2.0 LTS`, `4.3.0 Alpha`

# Importer Features
  * Textures
  * Character Toon Material (via [SekaiShaderStandalone](https://github.com/mos9527/sssekai_blender_io/blob/master/assets/SekaiShaderStandalone.blend))
  * Static/Skinned Meshes
  * Armatures
  * Articulations (Scene rebuilt with Empty object and static meshes)
  * Physics (WIP. Limited support for Rigidbodies, Colliders, and Spring Bones)
  * Animations (Armatures, Articulations, BlendShape, Camera. From `live_pv` and `streaming_live` assets)

# Supported Languages
PRs are welcome for additions. 
- You can find the translation file [here](https://github.com/mos9527/sssekai_blender_io/tree/master/translations.py).
- The script used to generate the translation file is [here](https://github.com/mos9527/sssekai_blender_io/tree/master/translations_codegen.py). Run this anywhere to update the translation file. Exisiting translations will be preserved.

You can find your language code by entering `bpy.app.translations.locale` in the Blender Python console.

Currently supported languages and maintainers:
- English (en_US, mos9527)
- 简体中文 (zh_HANS, mos9527)

# Installing & Updating
- Install/Update depedencies in your Blender Python
    - Navigate to your Blender installation path, and find the Python interperter of your version. (e.g. `C:\Program Files (x86)\Steam\steamapps\common\Blender\4.0\python\bin\python.exe`)
    - In its working directory (i.e. `...\python\bin`), run the following (**in a command prompt**. In Windows you can press Shift+Mouse Right Click to open up a new Terminal/Powershell Prompt)
```bash
.\python -m ensurepip
.\python -m pip install -U sssekai
```
- Download [this repo as zip](https://codeload.github.com/mos9527/sssekai_blender_io/zip/refs/heads/master)
- In Blender, go to `Edit > Preferences > Add-ons > Install...` and select the zip file you just downloaded.
- The addon should appear in the 3D Viewport sidebar (N key) under the tab `SSSekai`

# Documentation
See the [wiki page!](https://github.com/mos9527/sssekai_blender_io/wiki)

# Notes
The plugin is observed to work with other Unity games as well. But such compatibility is not guaranteed, and WILL NOT receive support from the author in full capacity.

# License
MIT

# References
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
