from typing import Set
from . import *
from .asset import *
from .animation import *

import bpy
import bpy.utils.previews
from bpy.types import Context, WindowManager
from bpy.props import (
    StringProperty,
    EnumProperty,
    BoolProperty,
    IntProperty
)
preview_collections = dict()
class SSSekaiBlenderUtilNeckAttachOperator(bpy.types.Operator):
    bl_idname = "sssekai.util_neck_attach_op"
    bl_label = "Attach Selected"

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

    def execute(self, context):
        wm = context.window_manager
        print('* Loading from', wm.sssekai_assetbundle_file, 'for', wm.sssekai_assetbundle_preview)
        with open(wm.sssekai_assetbundle_file, 'rb') as f:
            env = load_assetbundle(f)
            static_mesh_gameobjects, armatures = search_env_meshes(env)

            def add_material(m_Materials : Material, obj : bpy.types.Object, materialParser = None):
                for ppmat in m_Materials:
                    material : Material = ppmat.read()
                    asset = materialParser(material.name, material)
                    obj.data.materials.append(asset)
                    print('* Imported Material', material.name)
            
            for mesh_go in static_mesh_gameobjects:
                mesh_rnd : MeshRenderer = mesh_go.m_MeshRenderer.read()
                mesh_filter : MeshFilter = mesh_go.m_MeshFilter.read()
                if getattr(mesh_filter,'m_Mesh',None):
                    mesh_data : Mesh = mesh_filter.m_Mesh.read()
                    if mesh_data.name == wm.sssekai_assetbundle_preview:
                        mesh, obj = import_mesh(mesh_go.name, mesh_data,False)
                        add_material(mesh_rnd.m_Materials, obj, import_scene_material)    
                        print('* Imported Static Mesh', mesh_data.name)
                        return {'FINISHED'}
            
            for armature in armatures:
                if armature.name == wm.sssekai_assetbundle_preview:
                    mesh_rnd : SkinnedMeshRenderer = armature.skinned_mesh_gameobject.m_SkinnedMeshRenderer.read()
                    if getattr(mesh_rnd,'m_Mesh',None):
                        mesh_data : Mesh = mesh_rnd.m_Mesh.read()
                        armInst, armObj = import_armature('%s_Armature' % armature.name ,armature)
                        mesh, obj = import_mesh(armature.name, mesh_data,True, armature.bone_path_hash_tbl)
                        obj.parent = armObj
                        obj.modifiers.new('Armature', 'ARMATURE').object = armObj
                        add_material(mesh_rnd.m_Materials, obj, import_character_material)    
                        print('* Imported Armature and Skinned Mesh', mesh_data.name)
                        return {'FINISHED'}

            animations = search_env_animations(env)    
            for animation in animations:
                if animation.name == wm.sssekai_assetbundle_preview:
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
                    print('* Duration', clip.Duration)
                    print('* Framerate', clip.Framerate)
                    print('* Frames', bpy.context.scene.frame_end)
                    print('* Blender FPS set to:', bpy.context.scene.render.fps)
                    if BLENDSHAPES_UNK_CRC in clip.FloatTracks:
                        print('* Importing Keyshape animation', animation.name)
                        check_is_active_armature()
                        arm_mesh_obj = bpy.context.active_object.children[0]
                        import_keyshape_animation(animation.name, clip, arm_mesh_obj, wm.sssekai_animation_import_offset, not wm.sssekai_animation_append_exisiting)
                        print('* Imported Keyshape animation', animation.name)
                    elif CAMERA_UNK_CRC in clip.TransformTracks[TransformType.Translation]:
                        print('* Importing Camera animation', animation.name)
                        check_is_active_camera()
                        import_camera_animation(animation.name, clip, bpy.context.active_object,  wm.sssekai_animation_import_offset, not wm.sssekai_animation_append_exisiting)
                        print('* Imported Camera animation', animation.name)
                    elif NULL_CRC in clip.FloatTracks and CAMERA_ADJ_UNK_CRC in clip.FloatTracks[NULL_CRC]:
                        # XXX not working yet. don't know what the values mean
                        print('* Importing Camera Parameter animation', animation.name)
                        check_is_active_camera()
                        import_camera_parameter_animation(animation.name, clip, bpy.context.active_object, wm.sssekai_animation_import_offset, not wm.sssekai_animation_append_exisiting)
                        print('* Imported Camera Parameter animation', animation.name)
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

    def execute(self, context):
        assert bpy.context.active_object and bpy.context.active_object.type == 'ARMATURE', "Please select an armature to import physics data to!"
        wm = context.window_manager
        print('* Loading physics data from', wm.sssekai_assetbundle_file, 'for', wm.sssekai_assetbundle_preview)
        with open(wm.sssekai_assetbundle_file, 'rb') as f:
            env = load_assetbundle(f)
            static_mesh_gameobjects, armatures = search_env_meshes(env)
            for armature in armatures:
                if armature.name == wm.sssekai_assetbundle_preview:
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
    def execute(self, context):
        assert bpy.context.active_object and bpy.context.active_object.type == 'ARMATURE', "Please select an armature to remove physics data from!"
        arma = bpy.context.active_object
        # Removes all rigidbodies, and, consequently, all constraints
        for child in get_rigidbodies_from_arma(arma):
            child.select_set(True)
            for cchild in child.children:
                cchild.select_set(True)
        arma.select_set(False)
        return bpy.ops.object.delete()
class SSSekaiBlenderPhysicsDisplayOperator(bpy.types.Operator):
    bl_idname = "sssekai.display_physics_op"
    bl_label = "Show Physics Objects"                
    def execute(self, context):
        assert bpy.context.active_object and bpy.context.active_object.type == 'ARMATURE', "Please select an armature!"
        arma = bpy.context.active_object
        wm = context.window_manager
        display = not wm.sssekai_armature_display_physics
        for child in get_rigidbodies_from_arma(arma):
            child.hide_set(display)
            for cchild in child.children:
                cchild.hide_set(display)
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
        layout.label(text="Select Asset")
        row = layout.row()
        row.prop(wm, "sssekai_assetbundle_file")

        row = layout.row()
        row.prop(wm, "sssekai_assetbundle_preview")
        layout.separator()
        row = layout.row()
        row.label(text="Armature Options")
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
        with open(fname, 'rb') as f:
            env = load_assetbundle(f)
            static_mesh_gameobjects, armatures = search_env_meshes(env)
            for mesh_go in static_mesh_gameobjects:
                mesh_filter : MeshFilter = mesh_go.m_MeshFilter.read()
                if getattr(mesh_filter,'m_Mesh',None):
                    mesh_data : Mesh = mesh_filter.m_Mesh.read()    
                    enum_items.append((mesh_data.name,mesh_data.name,'Static Mesh %s' % mesh_data.name, 'MESH_DATA', index))
                    index+=1

            for armature in armatures:
                enum_items.append((armature.name,armature.name,'Armature %s' % armature.name, 'ARMATURE_DATA',index))
                index+=1

            animations = search_env_animations(env)    
            for animation in animations:
                enum_items.append((animation.name,animation.name,'Animation %s' % animation.name, 'ANIM_DATA',index))
                index+=1

    pcoll.sssekai_assetbundle_preview = enum_items
    pcoll.sssekai_assetbundle_file = fname
    return pcoll.sssekai_assetbundle_preview

def register():
    WindowManager.sssekai_assetbundle_file = StringProperty(
        name="File",
        description="File",
        subtype='FILE_PATH',
    )
    WindowManager.sssekai_assetbundle_preview = EnumProperty(
        name="Asset",
        description="Asset",
        items=enumerate_assets,
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
    bpy.utils.unregister_class(SSSekaiBlenderImportPhysicsOperator)
    bpy.utils.unregister_class(SSSekaiBlenderRemovePhysicsOperator)
    bpy.utils.unregister_class(SSSekaiBlenderPhysicsDisplayOperator)
