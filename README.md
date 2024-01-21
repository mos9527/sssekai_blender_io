# sssekai_blender_io
Blender I/O for the game's assets. (actually it's imports only)

Currently supports:  
  * Textures
  * Character NPR Material (via [SekaiShaderStandalone](https://github.com/mos9527/sssekai_blender_io/blob/master/assets/SekaiShaderStandalone.blend))
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
- The addon show appear in the 3D Viewport sidebar (N key) under the tab `SSSekai`

## Usage
Refer to the Wiki!
https://github.com/mos9527/sssekai_blender_io/wiki （附带简中）

## References
https://github.com/KhronosGroup/glTF-Blender-IO

https://github.com/theturboturnip/yk_gmd_io

https://github.com/SutandoTsukai181/yakuza-gmt-blender

https://github.com/UuuNyaa/blender_mmd_tools

https://github.com/Pauan/blender-rigid-body-bones
