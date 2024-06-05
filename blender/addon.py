from typing import Set
from . import *
from .asset import *
from .animation import *

import bpy
import bpy.utils.previews
from bpy.types import Context, WindowManager
import bpy
from bpy.props import (
    StringProperty,
    EnumProperty,
    BoolProperty,
    IntProperty
)
def encode_name_and_container(name, container):
    return f'{name} | {container}'
preview_collections = dict()
class SSSekaiBlenderUtilNeckAttachOperator(bpy.types.Operator):
    bl_idname = "sssekai.util_neck_attach_op"
    bl_label = "Attach Selected"
    bl_description = "Attach the selected face armature to the selected body armature"
    def execute(self, context):
        scene = context.scene
        face_arma = scene.sssekai_util_neck_attach_obj_face
        body_arma = scene.sssekai_util_neck_attach_obj_body
        assert face_arma and body_arma, "Please select both face and body armatures"        
        face_obj = scene.objects.get(face_arma.name)
        body_obj = scene.objects.get(body_arma.name)
        bpy.context.view_layer.objects.active = face_obj
        bpy.ops.object.mode_set(mode='POSE')
        neck_bone = face_obj.pose.bones['Neck']
        constraint = neck_bone.constraints.new('COPY_TRANSFORMS')
        constraint.target = body_obj
        constraint.subtarget = 'Neck'
        return {'FINISHED'}

class SSSekaiBlenderUtilNeckAttach(bpy.types.Panel):
    bl_idname = "OBJ_PT_sssekai_util_neck_attach"
    bl_label = "Utility :: Neck Attach"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "SSSekai"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        layout.label(text='Select Targets')
        layout.prop(scene, 'sssekai_util_neck_attach_obj_face')
        layout.prop(scene, 'sssekai_util_neck_attach_obj_body')
        layout.operator(SSSekaiBlenderUtilNeckAttachOperator.bl_idname)       

class SSSekaiBlenderImportOperator(bpy.types.Operator):
    bl_idname = "sssekai.import_op"
    bl_label = "Import Selected"
    bl_description = "Import the selected asset from the selected asset bundle"
    def execute(self, context):
        wm = context.window_manager
        print('* Loading from', wm.sssekai_assetbundle_file, 'for', wm.sssekai_assetbundle_preview)
        env = UnityPy.load(wm.sssekai_assetbundle_file)
        articulations, armatures = search_env_meshes(env)
        print('* Found %d articulations and %d armatures' % (len(articulations), len(armatures)))
        texture_cache = dict()
        material_cache = dict()
        def add_material(m_Materials : Material, obj : bpy.types.Object, meshData : Mesh, defaultParser = None): 
            for ppmat in m_Materials:
                if ppmat:                    
                    material : Material = ppmat.read()
                    parser = defaultParser                    
                    # Override parser by name when not using blender's Principled BSDF
                    # These are introduced by v2 meshes     
                    if not wm.sssekai_materials_use_principled_bsdf:                   
                        if '_eye' in material.name:
                            parser = import_eye_material
                        if '_ehl_' in material.name: 
                            parser = import_eyelight_material
                        if 'mtl_chr_00' in material.name and '_FaceShadowTex' in material.m_SavedProperties.m_TexEnvs:   
                            setup_sdfValue_driver(obj)
                            parser = import_chara_face_v2_material
                    if material.name in material_cache:
                        asset = material_cache[material.name]
                        print('* Reusing Material', material.name)
                    else:
                        asset = parser(
                            material.name, 
                            material, 
                            use_principled_bsdf=wm.sssekai_materials_use_principled_bsdf,
                            texture_cache=texture_cache
                        )
                        material_cache[material.name] = asset
                        print('* Imported new Material', material.name)
                    obj.data.materials.append(asset)
            
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.mode_set(mode='OBJECT')
            mesh = obj.data
            for index,sub in enumerate(meshData.m_SubMeshes):
                start, count = sub.firstVertex, sub.vertexCount
                for i in range(start, start + count):
                    mesh.vertices[i].select = True
                bpy.ops.object.mode_set(mode='EDIT')
                bpy.context.object.active_material_index = index
                bpy.ops.object.material_slot_assign()
                bpy.ops.mesh.select_all(action='DESELECT')
                bpy.ops.object.mode_set(mode='OBJECT')
        
        def add_articulation(articulation):                
            joint_map = dict()
            for parent,bone,depth in articulation.root.dfs_generator():
                joint = bpy.data.objects.new(bone.name, None)
                joint.empty_display_size = 0.1
                joint.empty_display_type = 'ARROWS'     
                joint_map[bone.name] = joint         
                bpy.context.collection.objects.link(joint)
                # Make the artiulation
                joint.parent = joint_map[parent.name] if parent else None
                joint.location = swizzle_vector(bone.localPosition)
                joint.rotation_mode = 'QUATERNION'
                joint.rotation_quaternion = swizzle_quaternion(bone.localRotation)
                joint.scale = swizzle_vector_scale(bone.localScale)
                # Add the meshes, if any
                if bone.gameObject and getattr(bone.gameObject,'m_MeshFilter',None):
                    print('* Found Static Mesh at', bone.name)
                    mesh_filter : MeshFilter = bone.gameObject.m_MeshFilter.read()
                    mesh_rnd : MeshRenderer = bone.gameObject.m_MeshRenderer.read()
                    mesh_data = mesh_filter.m_Mesh.read(return_typetree_on_error=False)
                    mesh, obj = import_mesh(mesh_data.name, mesh_data, False)
                    try:
                        add_material(mesh_rnd.m_Materials, obj, mesh_data, import_scene_material)    
                    except Exception:
                        pass
                    obj.parent = joint
                    print('* Imported Static Mesh', mesh_data.name)
            print('* Imported Static Mesh Articulation', articulation.name)        

        for articulation in articulations:
            container = articulation.root.gameObject.container
            if encode_name_and_container(articulation.name, container) == wm.sssekai_assetbundle_preview:
                add_articulation(articulation)
                return {'FINISHED'}
        
        # XXX: Skinned meshes are expected to have identity transforms 
        # maybe this would change in the future but for now, it's a safe assumption
        def add_armature(armature : Armature):
            armInst, armObj = import_armature('%s_Armature' % armature.name ,armature)
            for parent,bone,depth in armature.root.dfs_generator():
                if bone.gameObject and getattr(bone.gameObject,'m_SkinnedMeshRenderer',None):
                    print('* Found Skinned Mesh at', bone.name)
                    mesh_rnd : SkinnedMeshRenderer = bone.gameObject.m_SkinnedMeshRenderer.read()
                    bone_order  = [b.read().m_GameObject.read().name for b in mesh_rnd.m_Bones]
                    if getattr(mesh_rnd,'m_Mesh',None):
                        mesh_data : Mesh = mesh_rnd.m_Mesh.read(return_typetree_on_error=False)                            
                        mesh, obj = import_mesh(bone.name, mesh_data,True, armature.bone_path_hash_tbl,bone_order)
                        obj.parent = armObj
                        obj.modifiers.new('Armature', 'ARMATURE').object = armObj
                        add_material(mesh_rnd.m_Materials, obj, mesh_data, import_character_material)    
                        print('* Imported Skinned Mesh', mesh_data.name)
            print('* Imported Armature', armature.name)

        for armature in armatures:
            container = armature.root.gameObject.container
            if encode_name_and_container(armature.name, container) == wm.sssekai_assetbundle_preview:
                if wm.sssekai_armatures_as_articulations:
                    add_articulation(armature)
                    return {'FINISHED'}
                else:
                    add_armature(armature)
                    return {'FINISHED'}

        animations = search_env_animations(env)    
        for animation in animations:
            container = animation.container
            if encode_name_and_container(animation.name, container) == wm.sssekai_assetbundle_preview:
                def check_is_active_armature():
                    assert bpy.context.active_object and bpy.context.active_object.type == 'ARMATURE', "Please select an armature for this animation!"
                def check_is_active_camera():
                    assert bpy.context.active_object and bpy.context.active_object.type == 'CAMERA', "Please select a camera for this animation!"
                print('* Reading AnimationClip:', animation.name)
                print('* Byte size:',animation.byte_size)
                print('* Loading...')
                clip = read_animation(animation)  
                print('* Importing...')
                # Set the fps. Otherwise keys may get lost!
                bpy.context.scene.render.fps = int(clip.Framerate)
                bpy.context.scene.frame_end = max(bpy.context.scene.frame_end,int(clip.Framerate * clip.Duration + 0.5 + wm.sssekai_animation_import_offset))
                bpy.context.scene.rigidbody_world.point_cache.frame_end = max(bpy.context.scene.rigidbody_world.point_cache.frame_end, bpy.context.scene.frame_end)
                print('* Duration', clip.Duration)
                print('* Framerate', clip.Framerate)
                print('* Frames', bpy.context.scene.frame_end)
                print('* Blender FPS set to:', bpy.context.scene.render.fps)
                if BLENDSHAPES_UNK_CRC in clip.FloatTracks:
                    print('* Importing Keyshape animation', animation.name)
                    check_is_active_armature()
                    mesh_obj = None
                    for obj in bpy.context.active_object.children:
                        if KEY_SHAPEKEY_NAME_HASH_TBL in obj.data:
                            mesh_obj = obj
                            break
                    assert mesh_obj, "KEY_SHAPEKEY_NAME_HASH_TBL not found in any of the sub meshes! Invalid armature!" 
                    print("* Importing into", mesh_obj.name)
                    import_keyshape_animation(animation.name, clip, mesh_obj, wm.sssekai_animation_import_offset, not wm.sssekai_animation_append_exisiting)
                    print('* Imported Keyshape animation', animation.name)
                elif CAMERA_UNK_CRC in clip.TransformTracks[TransformType.Translation]:
                    print('* Importing Camera animation', animation.name)
                    check_is_active_camera()
                    import_camera_animation(animation.name, clip, bpy.context.active_object,  wm.sssekai_animation_import_offset, not wm.sssekai_animation_append_exisiting)
                    print('* Imported Camera animation', animation.name)
                elif CAMERA_DOF_UNK_CRC in clip.FloatTracks and CAMERA_DOF_FOV_UNK_CRC in clip.FloatTracks[CAMERA_DOF_UNK_CRC]:
                    # depth_of_field animations
                    # Don't know why FOV is here though...but it is!
                    print('* Importing Camera FOV animation', animation.name)
                    check_is_active_camera()
                    import_camera_fov_animation(animation.name, clip.FloatTracks[CAMERA_DOF_UNK_CRC][CAMERA_DOF_FOV_UNK_CRC].Curve, bpy.context.active_object, wm.sssekai_animation_import_offset, not wm.sssekai_animation_append_exisiting)
                    print('* Imported Camera FOV animation', animation.name)
                else:
                    print('* Importing Armature animation', animation.name)
                    check_is_active_armature()
                    import_armature_animation(animation.name, clip, bpy.context.active_object, wm.sssekai_animation_import_offset, not wm.sssekai_animation_append_exisiting)
                    print('* Imported Armature animation', animation.name)
                return {'FINISHED'}
        return {'CANCELLED'}
class SSSekaiBlenderImportPhysicsOperator(bpy.types.Operator):
    bl_idname = "sssekai.import_physics_op"
    bl_label = "Import Physics"
    bl_description = "Import physics data from the selected asset bundle. NOTE: This operation is irreversible!"
    def execute(self, context):
        assert bpy.context.active_object and bpy.context.active_object.type == 'ARMATURE', "Please select an armature to import physics data to!"
        wm = context.window_manager
        env = UnityPy.load(wm.sssekai_assetbundle_file)
        articulations, armatures = search_env_meshes(env)
        for armature in armatures:
            container = armature.root.gameObject.container
            if encode_name_and_container(armature.name, container) == wm.sssekai_assetbundle_preview:
                bpy.context.scene.frame_current = 0
                import_armature_physics_constraints(bpy.context.active_object, armature)
                return {'FINISHED'}
        return {'CANCELLED'}

def get_rigidbodies_from_arma(arma : bpy.types.Object):
    for child in arma.children:
        if '_rigidbody' in child.name:
            yield child
class SSSekaiBlenderRemovePhysicsOperator(bpy.types.Operator):
    bl_idname = "sssekai.remove_physics_op"
    bl_label = "Remove Physics"
    bl_description = "Remove physics data from the selected armature. NOTE: This operation is irreversible!"
    def execute(self, context):
        assert bpy.context.active_object and bpy.context.active_object.type == 'ARMATURE', "Please select an armature to remove physics data from!"
        arma = bpy.context.active_object
        # Removes all rigidbodies, and, consequently, all constraints
        for child in get_rigidbodies_from_arma(arma):
            child.select_set(True)            
            for cchild in child.children_recursive:
                cchild.select_set(True)
        arma.select_set(False)
        bpy.ops.object.delete()
        # For all bones, restore the original hierarchy and transform
        bpy.ops.object.mode_set(mode='EDIT')
        for bone in arma.data.edit_bones:
            if KEY_ORIGINAL_PARENT in bone:
                bone.parent = arma.data.edit_bones[bone[KEY_ORIGINAL_PARENT]]
                del bone[KEY_ORIGINAL_PARENT]
        for bone in arma.data.edit_bones:        
            if KEY_ORIGINAL_WORLD_MATRIX in bone:
                bone.matrix = unpack_matrix(bone[KEY_ORIGINAL_WORLD_MATRIX])
                del bone[KEY_ORIGINAL_WORLD_MATRIX]
        return {'FINISHED'}
class SSSekaiBlenderPhysicsDisplayOperator(bpy.types.Operator):
    bl_idname = "sssekai.display_physics_op"
    bl_label = "Show Physics Objects"
    bl_description = "Show or hide physics objects"          
    def execute(self, context):
        assert bpy.context.active_object and bpy.context.active_object.type == 'ARMATURE', "Please select an armature!"
        arma = bpy.context.active_object
        wm = context.window_manager
        display = not wm.sssekai_armature_display_physics
        for child in get_rigidbodies_from_arma(arma):
            child.hide_set(display)
            child.hide_render = display
            for cchild in child.children_recursive:
                cchild.hide_set(display)
                cchild.hide_render = display
        return {'FINISHED'}
    
class SSSekaiBlenderApplyOutlineOperator(bpy.types.Operator):
    bl_idname = "sssekai.apply_outline_op"
    bl_label = "Add Outline to Selected"
    bl_description = "Add outline to the selected object"
    def execute(self, context):
        ensure_sssekai_shader_blend()
        outline_material = bpy.data.materials["SekaiShaderOutline"].copy()
        for pa in bpy.context.selected_objects:
            for obj in [pa] + pa.children_recursive:
                if obj.type == 'MESH':                    
                    bpy.context.view_layer.objects.active = obj
                    bpy.ops.object.mode_set(mode='OBJECT')
                    obj.data.materials.append(outline_material)
                    modifier = obj.modifiers.new(name="SekaiShellOutline", type='NODES')
                    modifier.node_group = bpy.data.node_groups["SekaiShellOutline"].copy()
                    index = len(obj.data.materials) - 1
                    modifier['Socket_4'] = index # XXX: Any other way to assign this attribute?
        return {'FINISHED'}

class SSSekaiBlenderImportPanel(bpy.types.Panel):
    bl_idname = "OBJ_PT_sssekai_import"
    bl_label = "Importer"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "SSSekai"

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        layout.prop(wm, "sssekai_unity_version_override")
        row = layout.row()
        layout.label(text="Select Asset")
        row = layout.row()
        row.prop(wm, "sssekai_assetbundle_file")
        row = layout.row()
        row.prop(wm, "sssekai_assetbundle_preview")
        layout.separator()
        row = layout.row()
        row.label(text="Material Options")
        row = layout.row()
        row.prop(wm, "sssekai_materials_use_principled_bsdf")
        row = layout.row()
        row.operator(SSSekaiBlenderApplyOutlineOperator.bl_idname)
        row = layout.row()
        row.label(text="Armature Options")
        row = layout.row()
        row.prop(wm, "sssekai_armatures_as_articulations")
        row = layout.row()
        row.operator(SSSekaiBlenderImportPhysicsOperator.bl_idname)
        row = layout.row()
        row.operator(SSSekaiBlenderRemovePhysicsOperator.bl_idname)
        row = layout.row()
        row.prop(wm, "sssekai_armature_display_physics", toggle=True)
        row = layout.row()
        row.label(text="Animation Options")
        row = layout.row()
        row.prop(wm, "sssekai_animation_import_offset")
        row.prop(wm, "sssekai_animation_append_exisiting")
        row = layout.row()
        row.operator(SSSekaiBlenderImportOperator.bl_idname)

def enumerate_assets(self, context):
    """EnumProperty callback"""
    enum_items = []

    if context is None:
        return enum_items

    wm = context.window_manager
    fname = wm.sssekai_assetbundle_file

    # Get the preview collection (defined in register func).
    pcoll = preview_collections["main"]

    if fname == pcoll.sssekai_assetbundle_file:
        return pcoll.sssekai_assetbundle_preview

    print("* Loading index for %s" % fname)

    if fname and os.path.exists(fname):
        index = 0        
        UnityPy.config.FALLBACK_VERSION_WARNED = True
        UnityPy.config.FALLBACK_UNITY_VERSION = sssekai_get_unity_version() 
        env = UnityPy.load(fname)
        articulations, armatures = search_env_meshes(env)
        for articulation in articulations:
            container = articulation.root.gameObject.container
            encoded = encode_name_and_container(articulation.name, container)
            enum_items.append((encoded, encoded,articulation.name, 'MESH_DATA', index))
            index+=1

        for armature in armatures:
            container = armature.root.gameObject.container
            encoded = encode_name_and_container(armature.name, container)
            enum_items.append((encoded,encoded,armature.name, 'ARMATURE_DATA',index))
            index+=1

        animations = search_env_animations(env)    
        for animation in animations:
            container = animation.container
            encoded = encode_name_and_container(animation.name, container)
            enum_items.append((encoded,encoded,animation.name, 'ANIM_DATA',index))
            index+=1

    pcoll.sssekai_assetbundle_preview = enum_items
    pcoll.sssekai_assetbundle_file = fname
    return pcoll.sssekai_assetbundle_preview

def register():
    WindowManager.sssekai_assetbundle_file = StringProperty(
        name="Bundle Directory",
        description="Where the asset bundle(s) is located. Every AssetBundle in this directory will be loaded (if possible).",
        subtype='DIR_PATH',
    )
    WindowManager.sssekai_assetbundle_preview = EnumProperty(
        name="Asset",
        description="Asset",
        items=enumerate_assets,
    )
    WindowManager.sssekai_armatures_as_articulations = BoolProperty(
        name="Armatures as Articulations",
        description="Treating armatures as articulations instead of skinned meshes. This is useful for importing stages.",
        default=False        
    )        
    WindowManager.sssekai_materials_use_principled_bsdf = BoolProperty(
        name="Use Principled BSDF",
        description="Use Principled BSDF instead of SekaiShader for imported materials",
        default=False        
    )    
    WindowManager.sssekai_armature_display_physics = BoolProperty(
        name="Display Physics",
        description="Display Physics Objects",
        default=True,
        update=SSSekaiBlenderPhysicsDisplayOperator.execute
    )
    WindowManager.sssekai_animation_append_exisiting = BoolProperty(
        name="Append",
        description="Append Animations to the existing Action, instead of overwriting it",
        default=False
    )
    WindowManager.sssekai_animation_import_offset = IntProperty(
        name="Offset",
        description="Animation Offset in frames",
        default=0
    )
    def sssekai_on_unity_version_change(self, context):
        sssekai_set_unity_version(context.window_manager.sssekai_unity_version_override)
    WindowManager.sssekai_unity_version_override = StringProperty(
        name="Unity Version",
        description="Override Unity Version",
        default=sssekai_get_unity_version(),
        update=sssekai_on_unity_version_change
    )
    pcoll = bpy.utils.previews.new()
    pcoll.sssekai_assetbundle_file = ""
    pcoll.sssekai_assetbundle_preview = ()
    
    preview_collections["main"] = pcoll
    bpy.utils.register_class(SSSekaiBlenderImportOperator)
    bpy.utils.register_class(SSSekaiBlenderImportPanel)

    bpy.types.Scene.sssekai_util_neck_attach_obj_face = bpy.props.PointerProperty(name="Face",type=bpy.types.Armature)
    bpy.types.Scene.sssekai_util_neck_attach_obj_body = bpy.props.PointerProperty(name="Body",type=bpy.types.Armature)
    bpy.utils.register_class(SSSekaiBlenderUtilNeckAttachOperator)
    bpy.utils.register_class(SSSekaiBlenderUtilNeckAttach)
    bpy.utils.register_class(SSSekaiBlenderApplyOutlineOperator)
    bpy.utils.register_class(SSSekaiBlenderImportPhysicsOperator)
    bpy.utils.register_class(SSSekaiBlenderRemovePhysicsOperator)
    bpy.utils.register_class(SSSekaiBlenderPhysicsDisplayOperator)


def unregister():
    del WindowManager.sssekai_assetbundle_preview

    for pcoll in preview_collections.values():
        bpy.utils.previews.remove(pcoll)
    preview_collections.clear()
    bpy.utils.unregister_class(SSSekaiBlenderImportOperator)
    bpy.utils.unregister_class(SSSekaiBlenderImportPanel)
    bpy.utils.unregister_class(SSSekaiBlenderUtilNeckAttachOperator)
    bpy.utils.unregister_class(SSSekaiBlenderUtilNeckAttach)
    bpy.utils.unregister_class(SSSekaiBlenderApplyOutlineOperator)
    bpy.utils.unregister_class(SSSekaiBlenderImportPhysicsOperator)
    bpy.utils.unregister_class(SSSekaiBlenderRemovePhysicsOperator)
    bpy.utils.unregister_class(SSSekaiBlenderPhysicsDisplayOperator)
