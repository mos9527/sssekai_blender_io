# sssekai_blender_io
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Blender asset importer for Project SEKAI (JP: プロジェクトセカイ カラフルステージ！ feat.初音ミク) asset bundles.

# Features
## Asset Types
- Character (legacy and 'v2') armatures and stage objects (with hierarchy) from asset bundles are generally supported.
- Animations from asset bundles (and [RLA/RTVL packets](https://github.com/mos9527/sssekai/wiki#streaming-live-rla-segments)) for characters and stage objects are generally supported
- Hair/Cloth physics are approximated with the game's own definition, and implemented as rigid body simulations.
## Shading
NPR toon shading is approximated with [SekaiShaderStandalone](https://github.com/mos9527/sssekai_blender_io/blob/master/assets/SekaiShaderStandalone.blend), which supports
- Customized diffuse/shadow textures
- Artist-authored outline strength
- SDF face shadows from 'v2' assets
## Documentation
Read the [wiki page](https://github.com/mos9527/sssekai_blender_io/wiki) for more!

# Supported Languages
PRs are welcome for additions. 
- You can find the translation file [here](https://github.com/mos9527/sssekai_blender_io/tree/master/translations.py).
- The script used to generate the translation file is [here](https://github.com/mos9527/sssekai_blender_io/tree/master/translations_codegen.py). Run this in the root of this repo, with any Python 3.8+ interpreter to update the translation file. Existing translations will be preserved.

You can find your language code by entering `bpy.app.translations.locale` in the Blender Python console.

Currently supported languages and maintainers:
- English (en_US, mos9527, @Rypie109)
- 简体中文 (zh_HANS, mos9527)

# Installing & Updating
## As A User
### 1. Dependencies
`sssekai_blender_io` requires `sssekai` to function. Ensure `sssekai` is installed **correctly** before attempting to install the addon itself.
#### Method A. Package the dependencies into the addon ZIP
This is the **recommended** method for most users as it is the least intrusive or error-prone.
- Download [this repo as zip](https://codeload.github.com/mos9527/sssekai_blender_io/zip/refs/heads/master), and unzip it.
  - Or preferably, clone this repo.
- Locate your Blender's Python interpreter (as stated in [Method B](#method-b-manage-dependencies-with-blender-pythons-pip))
- Run `<path_to_blender_python> make_addon_zip.py <output_zip_name WITHOUT the zip extension>`
  - e.g. `/Applications/Blender.app/Contents/Resources/4.3/python/bin/python3.11 make_addon_zip.py sssekai_blender_io-master`
- Install the *packaged* addon zip like any other Blender addon. (e.g. `sssekai_blender_io-master.zip` in the example).
- You can now skip the rest and jump to the [Install The Addon](#2-install-the-addon) section for help.

#### Method B. Manage dependencies with Blender Python's `pip`
It's only recommended if you're interested in debugging/developing the addon yourself. This method is platform-dependent.

**ATTENTION**: This method **only** works when you can freely write to the Blender installation directory on your system.
  - Navigate to your Blender installation path, and find the Python interpreter of your version. 
    - e.g. `C:\Program Files (x86)\Steam\steamapps\common\Blender\4.0\python\bin\python.exe`
      - ...and no, managing your Blender installation with Steam isn't recommended.
    - (For Windows, Linux) It is recommended to use the portable ZIP package instead of other versions to avoid permission issues
      - i.e. MSI installer for Windows, Snap Store for some Linux distros
    - (For macOS) Make sure that you can write to Blender's application path (e.g. `/Applications/Blender.app/`). The details shall be omitted here for the sake of sanity. <sigh>
      - Giving whichever terminal app you're using Full Disk Access in System Preferences > Security & Privacy > Privacy > Full Disk Access* worked for me
  - Install the dependencies with `pip` in-built with Blender's Python.
  ```bash
  <blender_python_path> -m ensurepip
  <blender_python_path> -m pip install --no-user -U sssekai 
  ```
  - **Make sure** the scripts are deployed to your **Blender** instance.
    - `--no-user` is an undocumented flag introduced in https://github.com/pypa/pip/commit/17e0d115e82fd195513b3a41736a13d122a5730b
      - This is **strictly** required as it prevents the dependencies from installing into the User directory - Blender **cannot** read those. 
      - If this happens, check if you can write to Blender's directory and start over.
  - Download [this repo as zip](https://codeload.github.com/mos9527/sssekai_blender_io/zip/refs/heads/master) and jump to the [next section](#2-install-the-addon)

### 2. Install the addon
- In Blender, go to `Edit > Preferences > Add-ons > Install...` and select the zip file you just prepared/downloaded.
- The addon should appear in the 3D Viewport sidebar (N key) under the tab `SSSekai`

## TODO
### QoL
- An actual updater
- **Cleanup** temp files after importing.
### Lighting
- 1-to-1 approximation of the game's lighting system
  - Face light (SDF for v2, simple $N \cdot L$ for legacy) [?]
    - *NOTE*: Current SDF implementation does not handle relative light directions
  - Directional Light (`SekaiCharacterDirectionalLight`) [?]
    - Not specialized at all and does not support colors as of now
  - Rim Light (`SekaiCharacterRimLight`) []
  - Ambient Light (`SekaiAmbientLight`, `SekaiCharacterAmbientLight`) []
  - ...
### Effects
- Approximate the game's particle system []
  - Some are observed to be implemented with simple articulated objects  
### Animation
- Approximate Unity's IK system []
  - Since [My Sekai](https://pjsekai.sega.jp/news/archive/index.html?hash=ecca5cb23ea530edb669fc0d2ae302fd0f374a4b) is a thing now and the chibi models are rigged with Unity's IK system.  
  - Also would be nice since all Unity games with humanoid characters use this system.
  - This would also make retargeting trivial.
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
