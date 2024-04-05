# sssekai_blender_io
Blender I/O for the game's assets. (actually it's imports only)

Tested on Blender `4.0.3`, `4.2.0 Alpha`

Currently supports:  
  * Textures
  * Character Toon Material (via [SekaiShaderStandalone](https://github.com/mos9527/sssekai_blender_io/blob/master/assets/SekaiShaderStandalone.blend))
  * Static Mesh
  * Skinned Mesh
  * Armatures (built through GameObject hierarchy)
  * Physics (Rigidbodies, Colliders, Spring Bones)
  * Animations (Skeletal, BlendShape, Camera)

## Installation:
- Install depedencies in your Blender Python
    - Navigate to your Blender installation path, and find the Python interperter of your version. (e.g. `C:\Program Files (x86)\Steam\steamapps\common\Blender\4.0\python\bin\python.exe`)
    - Run the following
```bash
python -m ensurepip
python -m pip install sssekai
```
- Download [this repo as zip](https://codeload.github.com/mos9527/sssekai_blender_io/zip/refs/heads/master)
- In Blender, go to `Edit > Preferences > Add-ons > Install...` and select the zip file you just downloaded.
- The addon should appear in the 3D Viewport sidebar (N key) under the tab `SSSekai`

## Usage
TODO

## References
https://github.com/KhronosGroup/glTF-Blender-IO

https://github.com/theturboturnip/yk_gmd_io

https://github.com/SutandoTsukai181/yakuza-gmt-blender

https://github.com/UuuNyaa/blender_mmd_tools

https://github.com/Pauan/blender-rigid-body-bones

https://zhuanlan.zhihu.com/p/411188212

https://zhuanlan.zhihu.com/p/337944099

https://zhuanlan.zhihu.com/p/670837192
