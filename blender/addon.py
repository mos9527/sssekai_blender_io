from typing import Set
from os import path
import zipfile

import UnityPy.classes
import UnityPy.classes
from . import *
from .asset import *
from .animation import *
from sssekai.unity.AnimationClip import Animation, Track
from sssekai.unity.AssetBundle import load_assetbundle

import bpy
import bpy.utils.previews
import mathutils
from bpy.types import Context, WindowManager
from bpy.props import (
    StringProperty,
    EnumProperty,
    BoolProperty,
    IntVectorProperty,
    IntProperty,
    FloatProperty
)
from bpy.app.translations import pgettext as T

def encode_asset_id(obj):
    prop = lambda x: '<%s %s>' % (x,getattr(obj,x,'<unk>'))
    return f"""{prop('name')},{prop('container')},{prop('path_id')},{prop('file_id')}"""
class SSSekaiGlobalEnvironment:
    current_dir : str = None
    current_enum_entries : list = None
    # --- SSSekai exclusive
    env : Environment
    articulations : Set[Armature]
    armatures : Set[Armature]
    animations : Set[Animation]
    # --- RLA exclusive
    rla_sekai_streaming_live_bundle_path : str = None
    rla_header : dict = dict()  
    rla_clip_data : dict = dict()   
    rla_selected_raw_clip : str = 0
    rla_raw_clips : dict = dict()  
    rla_animations : dict = dict()  # character ID -> Animation
    rla_clip_tick_range : tuple = (0,0)
    rla_clip_charas : set = set()
    rla_enum_entries : list = None
    rla_enum_bookmarks : list = []
    def rla_get_version(self):
        return tuple(map(int, sssekai_global.rla_header['version'].split('.'))) if 'version' in sssekai_global.rla_header else (0,0)
sssekai_global = SSSekaiGlobalEnvironment()

class SSSekaiBlenderUtilMiscRecalculateBoneHashTableOperator(bpy.types.Operator):
    bl_idname = "sssekai.util_misc_recalculate_bone_hash_table_op"
    bl_label = T("Recalculate Hash Table")
    bl_description = T("Recalculate the animation hash table for the selected armature/articulation. You should do this after renaming bones or changing the hierarchy.")
    def execute(self, context):
        assert context.mode == 'OBJECT', 'Please select an armature in Object Mode!'
        obj = bpy.context.active_object
        if obj.data and KEY_BONE_NAME_HASH_TBL in obj.data:
            bone_path_hash_tbl = dict()
            bone_path_tbl = dict()
            def dfs(bone):
                if bone.parent:
                    bone_path_tbl[bone.name] = bone_path_tbl[bone.parent.name] + '/' + bone.name
                else:
                    bone_path_tbl[bone.name] = bone.name
                bone_path_hash_tbl[str(get_name_hash(bone_path_tbl[bone.name]))] = bone.name
                for child in bone.children:
                    dfs(child)
            for bone in obj.data.bones:
                dfs(bone)        
            obj.data[KEY_BONE_NAME_HASH_TBL] = json.dumps(bone_path_hash_tbl,ensure_ascii=False)
        elif KEY_ARTICULATION_NAME_HASH_TBL in obj:
            joint_path_hash_tbl = dict()
            joint_path_tbl = dict()
            def dfs(joint):
                if not KEY_JOINT_BONE_NAME in joint: return
                joint_name = joint[KEY_JOINT_BONE_NAME]
                if joint.parent and KEY_JOINT_BONE_NAME in joint.parent:                    
                    joint_path_tbl[joint_name] = joint_path_tbl[joint.parent[KEY_JOINT_BONE_NAME]] + '/' + joint_name
                else:
                    joint_path_tbl[joint_name] = joint_name
                joint_path_hash_tbl[str(get_name_hash(joint_path_tbl[joint_name]))] = joint_name
                for child in joint.children:
                    dfs(child)
            for child in obj.children:
                dfs(child)
            obj[KEY_ARTICULATION_NAME_HASH_TBL] = json.dumps(joint_path_hash_tbl,ensure_ascii=False)
        else:
            assert False, 'Please select an armature/articulation imported by SSSekai first!'
        return {'FINISHED'}

class SSSekaiBlenderUtilMiscRemoveBoneHierarchyOperator(bpy.types.Operator):
    bl_idname = "sssekai.util_misc_remove_bone_hierarchy_op"
    bl_label = T("Remove Bone Hierarchy")
    bl_description = T("Remove the hierarchy from the selected bones in Edit Mode")
    def execute(self, context):
        assert context.mode == 'EDIT_ARMATURE', 'Please select bones in Edit Mode!'
        ebone = bpy.context.active_bone        
        for bone in ebone.children_recursive + [ebone]:
            bpy.context.active_object.data.edit_bones.remove(bone)
        return {'FINISHED'}

class SSSekaiBlenderUtilMiscRenameRemoveNumericSuffixOperator(bpy.types.Operator):
    bl_idname = "sssekai.util_misc_rename_remove_numeric_suffix_op"
    bl_label = T("Remove Numeric Suffix")
    bl_description = T("Remove the suffix from the selected objects and edit bones (i.e. xxx.001 -> xxx)")
    def execute(self, context):
        def rename_one(obj):
            names = obj.name.split('.')
            if len(names) > 1 and names[-1].isnumeric():
                obj.name = '.'.join(names[:-1])

        for pa in bpy.context.selected_objects:
            for obj in [pa] + pa.children_recursive:
                rename_one(obj)
  
        ebone = bpy.context.active_bone
        for bone in ebone.children_recursive + [ebone]:
            rename_one(bone)
        return {'FINISHED'}

class SSSekaiBlenderUtilApplyModifersOperator(bpy.types.Operator):
    # From: https://github.com/przemir/ApplyModifierForObjectWithShapeKeys/blob/master/ApplyModifierForObjectWithShapeKeys.py
    # NOTE: Only a subset of the original features are implemented here
    bl_idname = "sssekai.util_apply_modifiers_op"
    bl_label = T("Apply Modifiers")
    bl_description = T("Apply all modifiers to the selected objects's meshes. Snippet from github.com/przemir/ApplyModifierForObjectWithShapeKeys")
    def execute(self, context):        
        PROPS = ["name", "interpolation", "mute", "slider_max", "slider_min", "value", "vertex_group"]

        context = bpy.context
        obj = context.object
        modifiers = obj.modifiers

        shapesCount = len(obj.data.shape_keys.key_blocks) if obj.data.shape_keys else 0
        if obj.data.shape_keys:
            shapesCount = len(obj.data.shape_keys.key_blocks)
        
        if(shapesCount == 0):
            for modifier in modifiers:
                bpy.ops.object.modifier_apply(modifier=modifier.name)
            return {'FINISHED'}
        
        # We want to preserve original object, so all shapes will be joined to it.
        originalObject = context.view_layer.objects.active
        bpy.ops.object.select_all(action='DESELECT')
        originalObject.select_set(True)
        
        # Copy object which will holds all shape keys.
        bpy.ops.object.duplicate_move(OBJECT_OT_duplicate={"linked":False, "mode":'TRANSLATION'}, TRANSFORM_OT_translate={"value":(0, 0, 0), "orient_type":'GLOBAL', "orient_matrix":((1, 0, 0), (0, 1, 0), (0, 0, 1)), "orient_matrix_type":'GLOBAL', "constraint_axis":(False, False, False), "mirror":True, "use_proportional_edit":False, "proportional_edit_falloff":'SMOOTH', "proportional_size":1, "use_proportional_connected":False, "use_proportional_projected":False, "snap":False, "snap_target":'CLOSEST', "snap_point":(0, 0, 0), "snap_align":False, "snap_normal":(0, 0, 0), "gpencil_strokes":False, "cursor_transform":False, "texture_space":False, "remove_on_cancel":False, "release_confirm":False, "use_accurate":False})
        copyObject = context.view_layer.objects.active
        copyObject.select_set(False)
        
        # Return selection to originalObject.
        context.view_layer.objects.active = originalObject
        originalObject.select_set(True)
        # Save key shape properties
        shapekey_props = [{p : getattr(originalObject.data.shape_keys.key_blocks[i],p,None) for p in PROPS} for i in range(shapesCount)]
        # Handle base shape in "originalObject"
        bpy.ops.object.shape_key_remove(all=True)
        for modifier in modifiers:
            bpy.ops.object.modifier_apply(modifier=modifier.name)
    
        bpy.ops.object.shape_key_add(from_mix=False)
        originalObject.select_set(False)
        
        # Handle other shape-keys: copy object, get right shape-key, apply modifiers and merge with originalObject.
        # We handle one object at time here.
        for i in range(1, shapesCount):
            context.view_layer.objects.active = copyObject
            copyObject.select_set(True)
            
            # Copy temp object.
            bpy.ops.object.duplicate_move(OBJECT_OT_duplicate={"linked":False, "mode":'TRANSLATION'}, TRANSFORM_OT_translate={"value":(0, 0, 0), "orient_type":'GLOBAL', "orient_matrix":((1, 0, 0), (0, 1, 0), (0, 0, 1)), "orient_matrix_type":'GLOBAL', "constraint_axis":(False, False, False), "mirror":True, "use_proportional_edit":False, "proportional_edit_falloff":'SMOOTH', "proportional_size":1, "use_proportional_connected":False, "use_proportional_projected":False, "snap":False, "snap_target":'CLOSEST', "snap_point":(0, 0, 0), "snap_align":False, "snap_normal":(0, 0, 0), "gpencil_strokes":False, "cursor_transform":False, "texture_space":False, "remove_on_cancel":False, "release_confirm":False, "use_accurate":False})
            tmpObject = context.view_layer.objects.active
            bpy.ops.object.shape_key_remove(all=True)
            copyObject.select_set(True)
            copyObject.active_shape_key_index = i
            
            # Get right shape-key.
            bpy.ops.object.shape_key_transfer()
            context.object.active_shape_key_index = 0
            bpy.ops.object.shape_key_remove()
            bpy.ops.object.shape_key_remove(all=True)
            
            # Time to apply modifiers.
            for modifier in modifiers:
                bpy.ops.object.modifier_apply(modifier=modifier.name)
            
            # Join with originalObject
            copyObject.select_set(False)
            context.view_layer.objects.active = originalObject
            originalObject.select_set(True)
            bpy.ops.object.join_shapes()
            originalObject.select_set(False)
            context.view_layer.objects.active = tmpObject
            
            # Remove tmpObject
            tmpMesh = tmpObject.data
            bpy.ops.object.delete(use_global=False)
            bpy.data.meshes.remove(tmpMesh)
        context.view_layer.objects.active = originalObject
        for i in range(shapesCount):
            for p in PROPS:
                setattr(originalObject.data.shape_keys.key_blocks[i],p,shapekey_props[i][p])
        # Remove copyObject.
        originalObject.select_set(False)
        context.view_layer.objects.active = copyObject
        copyObject.select_set(True)
        tmpMesh = copyObject.data
        bpy.ops.object.delete(use_global=False)
        bpy.data.meshes.remove(tmpMesh)
        
        # Select originalObject.
        context.view_layer.objects.active = originalObject
        context.view_layer.objects.active.select_set(True)
    
        return {'FINISHED'}

class SSSekaiBlenderUtilArmatureMergeOperator(bpy.types.Operator):
    bl_idname = "sssekai.util_armature_merge_op"
    bl_label = T("Merge Armatures")
    bl_description = T("Merge one armature into another, taking constraints & modifed rest poses into consideration.  With the active one as the newly merged armature.")
    def execute(self, context):
        scene = context.scene
        assert len(bpy.context.selected_objects) == 2, "Please select 2 and only 2 objects."        
        child_obj = bpy.context.selected_objects[1]   
        parent_obj = bpy.context.selected_objects[0]
        if child_obj == bpy.context.active_object:
            child_obj,parent_obj = parent_obj, child_obj            
        assert child_obj.type == 'ARMATURE' and parent_obj.type == 'ARMATURE', "Please select 2 Armatures."
        child_arma =  child_obj.data
        parent_arma = parent_obj.data
        # For the child armature, we:
        # - Apply the modifier so the mesh matches the new rest pose
        for child in child_obj.children:
            if child.type == 'MESH':
                bpy.context.view_layer.objects.active = child
                bpy.ops.sssekai.util_apply_modifiers_op()
        bpy.context.view_layer.objects.active = child_obj
        bpy.ops.object.mode_set(mode='POSE')
        # With the armature in pose mode, we:
        # - Apply all bone constraints
        for bone in child_obj.pose.bones:
            child_arma.bones.active = bone.bone
            for constraint in bone.constraints:
                bpy.ops.constraint.apply(constraint=constraint.name, owner='BONE')
        # - Set the pose to rest pose
        bpy.ops.pose.armature_apply(selected=False)                
        # For the parent armature, we:
        # - Merge the child armature with the parent armature
        # - Assign new modifers to the merged mesh
        bpy.ops.object.mode_set(mode='OBJECT')
        child_obj.select_set(True)
        parent_obj.select_set(True)
        bpy.context.view_layer.objects.active = parent_obj
        bpy.ops.object.join()
        for child in parent_obj.children:
            if child.type == 'MESH' and len(child.modifiers) == 0:
                child.modifiers.new('Armature', 'ARMATURE').object = parent_obj
        return {'FINISHED'}

class SSSekaiBlenderUtilMiscPanel(bpy.types.Panel):
    bl_idname = "OBJ_PT_sssekai_misc"
    bl_label = T("Misc")
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "SSSekai"

    def draw(self, context):
        layout = self.layout
        layout.label(text=T("Armature"))
        row = layout.row()
        row.operator(SSSekaiBlenderUtilMiscRenameRemoveNumericSuffixOperator.bl_idname,icon='TOOL_SETTINGS')
        row = layout.row()
        row.operator(SSSekaiBlenderUtilMiscRemoveBoneHierarchyOperator.bl_idname,icon='TOOL_SETTINGS')
        row = layout.row()
        row.operator(SSSekaiBlenderUtilMiscRecalculateBoneHashTableOperator.bl_idname,icon='TOOL_SETTINGS')
        row = layout.row()
        row.operator(SSSekaiBlenderUtilApplyModifersOperator.bl_idname,icon='TOOL_SETTINGS')
        row = layout.row()
        row.operator(SSSekaiBlenderUtilArmatureMergeOperator.bl_idname,icon='TOOL_SETTINGS')
        row = layout.row()
        row.operator(SSSekaiBlenderUtilArmatureSimplifyOperator.bl_idname,icon='TOOL_SETTINGS')

class SSSekaiBlenderUtilNeckAttachOperator(bpy.types.Operator):
    bl_idname = "sssekai.util_neck_attach_op"
    bl_label = T("Attach")
    bl_description = T("Attach the selected face armature to the selected body armature")
    def execute(self, context):
        scene = context.scene
        face_arma = scene.sssekai_util_neck_attach_obj_face
        body_arma = scene.sssekai_util_neck_attach_obj_body
        assert face_arma and body_arma, "Please select both face and body armatures"        
        face_obj = scene.objects.get(face_arma.name)
        body_obj = scene.objects.get(body_arma.name)
        bpy.context.view_layer.objects.active = face_obj
        bpy.ops.object.mode_set(mode='POSE')
        def add_constraint(name):
            bone = face_obj.pose.bones[name]
            constraint = bone.constraints.new('COPY_TRANSFORMS')
            constraint.target = body_obj
            constraint.subtarget = name
        add_constraint('Neck')
        add_constraint('Head')
        return {'FINISHED'}

class SSSekaiBlenderUtilNeckMergeOperator(bpy.types.Operator):
    bl_idname = "sssekai.util_neck_merge_op"
    bl_label = T("Merge")
    bl_description = T("Merge the selected face armature with the selected body armature")
    def execute(self, context):
        scene = context.scene
        face_arma = scene.sssekai_util_neck_attach_obj_face
        body_arma = scene.sssekai_util_neck_attach_obj_body
        assert face_arma and body_arma, "Please select both face and body armatures"
        bpy.ops.sssekai.util_neck_attach_op() # Attach nontheless
        face_obj = scene.objects.get(face_arma.name)
        body_obj = scene.objects.get(body_arma.name)
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        face_obj.select_set(True)
        body_obj.select_set(True)
        bpy.context.view_layer.objects.active = body_obj         
        bpy.ops.sssekai.util_armature_merge_op()
        # Clean up bone hierarchy
        # We have made a lot of assumptions here...
        # Priori:
        # - The duped bones would be named as 'Bone.001', 'Bone.002', etc
        # - The face armature and body armature (if chosen correctly) would share some bones, up until the 'Neck' bone
        bpy.ops.object.mode_set(mode='EDIT')
        # - Changing the bone hierarchy in EDIT mode would not affect the mesh or the bone's armature space transforms
        # We will:
        # - Replace the subtree of the Neck bone of the body armature with the subtree of the Neck bone of the face armature
        # - Fix up the naming
        body_arma = body_obj.data
        for bone in body_arma.edit_bones['Head.001'].children:
            bone.parent = body_arma.edit_bones['Head']       
        # - Remove the now redundant bones
        body_arma.edit_bones.active = body_arma.edit_bones['Position.001']
        bpy.ops.sssekai.util_misc_remove_bone_hierarchy_op()
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"FINISHED"}

class SSSekaiBlenderUtilNeckAttach(bpy.types.Panel):
    bl_idname = "OBJ_PT_sssekai_util_neck_attach"
    bl_label = T("Attach Neck")
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "SSSekai"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        layout.label(text=T('Select Targets'))
        layout.prop(scene, 'sssekai_util_neck_attach_obj_face')
        layout.prop(scene, 'sssekai_util_neck_attach_obj_body')
        layout.operator(SSSekaiBlenderUtilNeckAttachOperator.bl_idname)       
        layout.operator(SSSekaiBlenderUtilNeckMergeOperator.bl_idname)

class SSSekaiBlenderUtilArmatureSimplifyOperator(bpy.types.Operator):
    bl_idname = "sssekai.util_armature_simplify_op"
    bl_label = T("Simplify Armature")
    bl_description = T("Simplify the bone hierachy of the selected armature. This operation is irreversible!")
    
    WHITELIST = {'Position', 'PositionOffset', 'Hip', 'Left_Thigh', 'Left_AssistHip', 'Left_Knee', 'Left_Ankle', 'Left_shw_back', 'Left_Toe', 'Left_shw_front', 'Right_Thigh', 'Right_AssistHip', 'Right_Knee', 'Right_Ankle', 'Right_shw_back', 'Right_Toe', 'Right_shw_front', 'Waist', 'Spine', 'Chest', 'Left_Shoulder', 'Left_Arm', 'Left_ArmRoll', 'Left_Elbow', 'Left_EllbowSupport', 'Left_EllbowSupport_End', 'Left_ForeArmRoll', 'Left_Wrist', 'Left_Hand_Attach', 'Left_Index_01', 'Left_Index_02', 'Left_Index_03', 'Left_Middle_01', 'Left_Middle_02', 'Left_Middle_03', 'Left_Pinky_01', 'Left_Pinky_02', 'Left_Pinky_03', 'Left_Ring_01', 'Left_Ring_02', 'Left_Ring_03', 'Left_Thumb_01', 'Left_Thumb_02', 'Left_Thumb_03', 'Neck', 'Head', 'Right_Shoulder', 'Right_Arm', 'Right_ArmRoll', 'Right_Elbow', 'Right_EllbowSupport', 'Right_EllbowSupport_End', 'Right_ForeArmRoll', 'Right_Wrist', 'Right_Hand_Attach', 'Right_Index_01', 'Right_Index_02', 'Right_Index_03', 'Right_Middle_01', 'Right_Middle_02', 'Right_Middle_03', 'Right_Pinky_01', 'Right_Pinky_02', 'Right_Pinky_03', 'Right_Ring_01', 'Right_Ring_02', 'Right_Ring_03', 'Right_Thumb_01', 'Right_Thumb_02', 'Right_Thumb_03', 'Chest_const', 'Thigh_Upv'}
    def execute(self, context):
        assert context.mode == 'EDIT_ARMATURE', 'Please select an armature in Edit Mode!'
        armature = bpy.context.active_object
        assert armature.type == 'ARMATURE', 'Please select an armature!'
        for bone in armature.data.edit_bones:
            if bone.name not in SSSekaiBlenderUtilArmatureSimplifyOperator.WHITELIST:
                print('* Removing bone', bone.name)
                armature.data.edit_bones.remove(bone)
        return {'FINISHED'}

class SSSekaiBlenderImportOperator(bpy.types.Operator):
    bl_idname = "sssekai.import_op"
    bl_label = T("Import Selected")
    bl_description = T("Import the selected asset from the selected asset bundle")
    def execute(self, context):
        global sssekai_global
        wm = context.window_manager        
        articulations, armatures, animations = sssekai_global.articulations, sssekai_global.armatures, sssekai_global.animations
        
        print('* Loading selected asset:', wm.sssekai_assetbundle_selected)
        texture_cache = dict()
        material_cache = dict()
        def add_mesh(gameObject, name : str = None, parent_obj = None, bone_hash_tbl : dict = None):
            name = name or gameObject.name
            if getattr(gameObject,'m_SkinnedMeshRenderer',None):
                print('* Found Skinned Mesh at', gameObject.name)
                mesh_rnd : SkinnedMeshRenderer = gameObject.m_SkinnedMeshRenderer.read()
                bone_order  = [b.read().m_GameObject.read().name for b in mesh_rnd.m_Bones]
                if getattr(mesh_rnd,'m_Mesh',None):
                    mesh_data : Mesh = mesh_rnd.m_Mesh.read(return_typetree_on_error=False)                            
                    mesh, obj = import_mesh(name, mesh_data,True, bone_hash_tbl, bone_order)
                    if parent_obj:
                        obj.parent = parent_obj
                    add_material(mesh_rnd.m_Materials, obj, mesh_data, import_character_material)    
                    print('* Imported Skinned Mesh', mesh_data.name)
                    return obj
            elif getattr(gameObject,'m_MeshFilter',None):
                print('* Found Static Mesh at', gameObject.name)
                mesh_filter : MeshFilter = gameObject.m_MeshFilter.read()
                mesh_rnd : MeshRenderer = gameObject.m_MeshRenderer.read()
                mesh_data = mesh_filter.m_Mesh.read(return_typetree_on_error=False)
                mesh, obj = import_mesh(mesh_data.name, mesh_data, False)
                if parent_obj:
                    obj.parent = parent_obj
                add_material(mesh_rnd.m_Materials, obj, mesh_data, import_scene_material)    
                print('* Imported Static Mesh', mesh_data.name)
                return obj
            return None
        
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
        
        def add_articulation(articulation : Armature):
            joint_map, parent_object = import_articulation(articulation)
            for bone_name, joint in joint_map.items():
                bone = articulation.get_bone_by_name(bone_name)
                mesh = add_mesh(bone.gameObject, bone_name, joint)             
            print('* Imported Articulation', articulation.name)        
        
        def add_armature(armature : Armature):
            armInst, armObj = import_armature(armature)
            for parent,bone,depth in armature.root.dfs_generator():
                mesh = add_mesh(bone.gameObject, bone.name, armObj, armature.bone_path_hash_tbl)
                if mesh:                    
                    mesh.modifiers.new('Armature', 'ARMATURE').object = armObj                        
            print('* Imported Armature', armature.name)
    
        for articulation in articulations:            
            if encode_asset_id(articulation.root.gameObject) == wm.sssekai_assetbundle_selected:
                add_articulation(articulation)
                return {'FINISHED'}
        
        for armature in armatures:
            if encode_asset_id(armature.root.gameObject) == wm.sssekai_assetbundle_selected:
                if wm.sssekai_armatures_as_articulations:
                    add_articulation(armature)
                    return {'FINISHED'}
                else:
                    add_armature(armature)
                    return {'FINISHED'}
        
        for animation in animations:
            if encode_asset_id(animation) == wm.sssekai_assetbundle_selected:
                print('* Reading AnimationClip:', animation.name)
                print('* Byte size:',animation.byte_size)
                print('* Loading...')
                clip = read_animation(animation)  
                print('* Importing...')
                # Set the fps. Otherwise keys may get lost!
                bpy.context.scene.render.fps = int(clip.Framerate)
                bpy.context.scene.frame_end = max(bpy.context.scene.frame_end,int(clip.Framerate * clip.Duration + 0.5 + wm.sssekai_animation_import_offset))
                if bpy.context.scene.rigidbody_world:
                    bpy.context.scene.rigidbody_world.point_cache.frame_end = max(bpy.context.scene.rigidbody_world.point_cache.frame_end, bpy.context.scene.frame_end)
                print('* Duration', clip.Duration)
                print('* Framerate', clip.Framerate)
                print('* Frames', bpy.context.scene.frame_end)
                print('* Blender FPS set to:', bpy.context.scene.render.fps)
                active_type = bpy.context.active_object.type
                if active_type == 'CAMERA' or KEY_CAMERA_RIG in bpy.context.active_object:
                    camera_obj = bpy.context.active_object
                    if KEY_CAMERA_RIG in bpy.context.active_object:
                        camera_obj = camera_obj.children[0]                    
                    track = clip.TransformTracks[TransformType.Translation]
                    if CAMERA_TRANS_ROT_CRC_MAIN in track or CAMERA_TRANS_SCALE_EXTRA_CRC_EXTRA in track:
                        print('* Importing Camera animation', animation.name)                        
                        import_camera_animation(animation.name, clip, camera_obj,  wm.sssekai_animation_import_offset, not wm.sssekai_animation_append_exisiting, wm.sssekai_animation_import_camera_scaling)
                        print('* Imported Camera animation', animation.name)
                elif active_type == 'ARMATURE':
                    if BLENDSHAPES_CRC in clip.FloatTracks:
                        print('* Importing Keyshape animation', animation.name)
                        mesh_obj = None
                        for obj in bpy.context.active_object.children:
                            if KEY_SHAPEKEY_NAME_HASH_TBL in obj.data:
                                mesh_obj = obj
                                break
                        assert mesh_obj, "KEY_SHAPEKEY_NAME_HASH_TBL not found in any of the sub meshes!" 
                        print("* Importing into", mesh_obj.name)
                        import_keyshape_animation(animation.name, clip, mesh_obj, wm.sssekai_animation_import_offset, not wm.sssekai_animation_append_exisiting)
                        print('* Imported Keyshape animation', animation.name)
                    if clip.TransformTracks[TransformType.Translation] or clip.TransformTracks[TransformType.Rotation] or clip.TransformTracks[TransformType.EulerRotation] or clip.TransformTracks[TransformType.Scaling]:
                        print('* Importing Armature animation', animation.name)
                        import_armature_animation(animation.name, clip, bpy.context.active_object, wm.sssekai_animation_import_offset, not wm.sssekai_animation_append_exisiting)
                        print('* Imported Armature animation', animation.name)
                elif active_type == 'EMPTY':
                    if clip.TransformTracks[TransformType.Translation] or clip.TransformTracks[TransformType.Rotation] or clip.TransformTracks[TransformType.EulerRotation] or clip.TransformTracks[TransformType.Scaling]:
                        print('* Importing Articulation animation', animation.name)
                        import_articulation_animation(animation.name, clip, bpy.context.active_object, wm.sssekai_animation_import_offset, not wm.sssekai_animation_append_exisiting)
                        print('* Imported Articulation animation', animation.name)

                return {'FINISHED'}
        return {'CANCELLED'}

class SSSekaiBlenderImportPhysicsOperator(bpy.types.Operator):
    bl_idname = "sssekai.import_physics_op"
    bl_label = T("Import Physics")
    bl_description = T("Import physics data from the selected asset bundle. NOTE: This operation is irreversible!")
    def execute(self, context):
        global sssekai_global
        assert bpy.context.active_object and bpy.context.active_object.type == 'ARMATURE', "Please select an armature to import physics data to!"
        wm = context.window_manager        
        articulations, armatures = sssekai_global.articulations, sssekai_global.armatures
        for armature in armatures:
            if encode_asset_id(armature.root.gameObject) == wm.sssekai_assetbundle_selected:
                bpy.context.scene.frame_current = 0
                import_armature_physics_constraints(bpy.context.active_object, armature)
                return {'FINISHED'}
        return {'CANCELLED'}

class SSSekaiBlenderPhysicsDisplayOperator(bpy.types.Operator):
    bl_idname = "sssekai.display_physics_op"
    bl_label = T("Show Physics Objects")
    bl_description = T("Show or hide physics objects")
    def execute(self, context):
        assert bpy.context.active_object and bpy.context.active_object.type == 'ARMATURE', "Please select an armature!"
        arma = bpy.context.active_object
        wm = context.window_manager
        display = not wm.sssekai_armature_display_physics
        for child in (child for child in arma.children if '_rigidbody' in child.name):
            child.hide_set(display)
            child.hide_render = display
            for cchild in child.children_recursive:
                cchild.hide_set(display)
                cchild.hide_render = display
        return {'FINISHED'}
    
class SSSekaiBlenderApplyOutlineOperator(bpy.types.Operator):
    bl_idname = "sssekai.apply_outline_op"
    bl_label = T("Add Outline to Selected")
    bl_description = T("Add outline to selected objects")
    def execute(self, context):
        ensure_sssekai_shader_blend()
        outline_material = bpy.data.materials["SekaiShaderOutline"].copy()
        for pa in bpy.context.selected_objects:
            for obj in [pa] + pa.children_recursive:
                if obj.type == 'MESH' and obj.hide_get() == False:                    
                    bpy.context.view_layer.objects.active = obj
                    bpy.ops.object.mode_set(mode='OBJECT')
                    obj.data.materials.append(outline_material)
                    modifier = obj.modifiers.new(name="SekaiShellOutline", type='NODES')
                    modifier.node_group = bpy.data.node_groups["SekaiShellOutline"].copy()
                    index = len(obj.data.materials) - 1
                    modifier['Socket_4'] = index # XXX: Any other way to assign this attribute?
        return {'FINISHED'}

class SSSekaiBlenderExportAnimationTypeTree(bpy.types.Operator, bpy_extras.io_utils.ExportHelper):
    bl_idname = "sssekai.export_typetree_op"
    bl_label = T("Export Animation TypeTree")
    bl_description = T("Export the TypeTree of the selected animation")

    filename_ext = ".anim"
    filter_glob: bpy.props.StringProperty(default='*.anim;', options={'HIDDEN'})

    def execute(self, context):
        global sssekai_global
        wm = context.window_manager
        articulations, armatures, animations = sssekai_global.articulations, sssekai_global.armatures, sssekai_global.animations
        from UnityPy.classes import GameObject
        def export_typetree(gameObject : GameObject):
            assert gameObject.type == ClassIDType.AnimationClip, "Only AnimationClip is supported for exporting TypeTree"
            filename = self.filepath
            import yaml
            with open(filename, 'w', encoding='utf-8') as f:
                print('* Exporting TypeTree to', filename)
                f.write('''%YAML 1.1
%TAG !u! tag:unity3d.com,2011:
--- !u!74 &7400000
''') 
                yaml.dump({'AnimationClip':gameObject.read_typetree()}, f, indent=4, ensure_ascii=False)
                print('* Exported TypeTree to', filename)                
        for articulation in articulations:
            if encode_asset_id(articulation.root.gameObject) == wm.sssekai_assetbundle_selected:
                export_typetree(articulation.root.gameObject)
                return {'FINISHED'}
        for armature in armatures:
            if encode_asset_id(armature.root.gameObject) == wm.sssekai_assetbundle_selected:
                export_typetree(armature.root.gameObject)
                return {'FINISHED'}
        for animation in animations:
            if encode_asset_id(animation) == wm.sssekai_assetbundle_selected:
                export_typetree(animation)
                return {'FINISHED'}
        return {'CANCELLED'}

def enumerate_assets(self, context):
    global sssekai_global
    enum_items = []

    if context is None:
        return enum_items

    wm = context.window_manager
    dirname = wm.sssekai_assetbundle_file

    if dirname == sssekai_global.current_dir:
        return sssekai_global.current_enum_entries or [("NONE", "None", "", 0)]

    print("* Loading index for %s" % dirname)

    if dirname and os.path.exists(dirname):
        index = 0        
        UnityPy.config.FALLBACK_VERSION_WARNED = True
        UnityPy.config.FALLBACK_UNITY_VERSION = sssekai_get_unity_version()         
        sssekai_global.env = UnityPy.load(dirname)
        sssekai_global.articulations, sssekai_global.armatures = search_env_meshes(sssekai_global.env)
        print('* Found %d articulations and %d armatures' % (len(sssekai_global.articulations), len(sssekai_global.armatures)))
        # See https://docs.blender.org/api/current/bpy.props.html#bpy.props.EnumProperty
        # enum_items = [(identifier, name, description, icon, number),...]
        # Note that `identifier` is the value that will be stored (and read) in the property
        for articulation in sssekai_global.articulations:
            encoded = encode_asset_id(articulation.root.gameObject)
            enum_items.append((encoded,articulation.name,encoded,'MESH_DATA', index))
            index+=1

        for armature in sssekai_global.armatures:
            encoded = encode_asset_id(armature.root.gameObject)
            enum_items.append((encoded,armature.name,encoded,'ARMATURE_DATA',index))
            index+=1

        sssekai_global.animations = search_env_animations(sssekai_global.env)    
        for animation in sssekai_global.animations:            
            encoded = encode_asset_id(animation)
            enum_items.append((encoded,animation.name,encoded,'ANIM_DATA',index))
            index+=1

        enum_items.sort(key=lambda x: x[0])

    sssekai_global.current_enum_entries = enum_items
    sssekai_global.current_dir = dirname
    return sssekai_global.current_enum_entries

class SSSekaiBlenderAssetSearchOperator(bpy.types.Operator):
    bl_idname = "sssekai.asset_search_op"
    bl_label = T("Search")
    bl_property = "selected"
    bl_description = T("Search for assets with their object name and/or container name")

    selected: EnumProperty(name="Asset",description="Selected Asset",items=enumerate_assets)
    def execute(self, context):
        wm = context.window_manager
        wm.sssekai_assetbundle_selected = self.selected
        return {'FINISHED'}

    def invoke(self, context, event):
        wm = context.window_manager
        wm.invoke_search_popup(self)
        return {'FINISHED'}    

class SSSekaiBlenderImportRLASinglePoseOperator(bpy.types.Operator):
    bl_idname = "sssekai.rla_import_armature_pose_op"
    bl_label = T("Import RLA Pose")
    bl_description = T("Import RLA Pose (armature/shapekey) for the selected object from a JSON, into the offset frame set in Animation Options. NOTE: The face/body armature must be pre-processed with the Merge option!")
    def execute(self, context):
        arma_obj = bpy.context.active_object
        assert arma_obj.type == 'ARMATURE', "Please select an armature to import the animation to!"
        mesh_obj = None
        for child in bpy.context.active_object.children:
            if KEY_SHAPEKEY_NAME_HASH_TBL in child.data:
                mesh_obj = child
                break
        assert mesh_obj, "KEY_SHAPEKEY_NAME_HASH_TBL not found in any of the sub meshes!"

        wm = context.window_manager
        pose = json.loads(wm.sssekai_rla_single_pose_json)       
        
        inv_bone_hash_table = arma_obj.data[KEY_BONE_NAME_HASH_TBL]
        inv_bone_hash_table = json.loads(inv_bone_hash_table)
        inv_bone_hash_table = {v:k for k,v in inv_bone_hash_table.items()}

        inv_shape_table = mesh_obj.data[KEY_SHAPEKEY_NAME_HASH_TBL]
        inv_shape_table = json.loads(inv_shape_table)
        inv_shape_table = {v:k for k,v in inv_shape_table.items()}    

        anim = Animation()
        if pose['boneDatas']:
            for bone in RLA_VALID_BONES: anim.TransformTracks[TransformType.Rotation][inv_bone_hash_table[bone]] = Track()
        else:
            anim.TransformTracks[TransformType.Rotation][inv_bone_hash_table[RLA_ROOT_BONE]] = Track()
        anim.TransformTracks[TransformType.Translation][inv_bone_hash_table[RLA_ROOT_BONE]] = Track()

        if pose['shapeDatas']:
            anim.FloatTracks[BLENDSHAPES_CRC] = dict()   
            for shape in RLA_VALID_BLENDSHAPES:
                anim.FloatTracks[BLENDSHAPES_CRC][inv_shape_table[shape]] = Track()     
        
        for idx, boneEuler in enumerate(pose['boneDatas']):
            if RLA_VALID_BONES[idx] != RLA_ROOT_BONE:
                anim.TransformTracks[TransformType.Rotation][inv_bone_hash_table[RLA_VALID_BONES[idx]]].add_keyframe(
                    KeyFrame(0, euler3_to_quat_swizzled(*boneEuler), UnityQuaternion(), UnityQuaternion(), 0)
                )
        anim.TransformTracks[TransformType.Translation][inv_bone_hash_table[RLA_ROOT_BONE]].add_keyframe(
            KeyFrame(0, Vector3(*pose['bodyPosition']), Vector3(), Vector3(), 0)
        )
        anim.TransformTracks[TransformType.Rotation][inv_bone_hash_table[RLA_ROOT_BONE]].add_keyframe(
            KeyFrame(0, euler3_to_quat_swizzled(*pose['bodyRotation']), UnityQuaternion(), UnityQuaternion(), 0)
        )

        for idx, value in enumerate(pose['shapeDatas']):
                anim.FloatTracks[BLENDSHAPES_CRC][inv_shape_table[RLA_VALID_BLENDSHAPES[idx]]].add_keyframe(
                    KeyFrame(0, value, 0, 0, 0)
                )
        
        import_armature_animation('RLAPose', anim, arma_obj, wm.sssekai_animation_import_offset, False)
        if pose['shapeDatas']:
            import_keyshape_animation('RLAPose', anim, mesh_obj, 0, False)
        bpy.context.scene.frame_end = max(bpy.context.scene.frame_end, wm.sssekai_animation_import_offset)
        bpy.context.scene.frame_current = wm.sssekai_animation_import_offset
        return {'FINISHED'}

class SSSekaiBlenderImportRLAArmatureAnimationOperator(bpy.types.Operator):
    bl_idname = "sssekai.rla_import_armature_animation_op"
    bl_label = T("Import Armature Animation")
    bl_description = T("Import Armature Animation for the selected character")
    def execute(self, context):        
        obj = bpy.context.active_object
        assert obj.type == 'ARMATURE', "Please select an armature to import the animation to!"

        wm = context.window_manager
        active_chara = wm.sssekai_rla_active_character
        chara_segments = list()
        has_boneData = False
        for tick, data in sssekai_global.rla_clip_data.items():
            m_data = data.get('MotionCaptureData', None)
            if m_data:                
                for data in m_data:                    
                    for pose in data['data']:
                        if pose['id'] == active_chara:
                            chara_segments.append(pose)
                            if pose['pose']['boneDatas']:
                                has_boneData = True
        print('* Found %d segments for character %d' % (len(chara_segments), active_chara))
        if not has_boneData:
            print('! No bone data found in the segments.')
        inv_hash_table = obj.data[KEY_BONE_NAME_HASH_TBL]
        inv_hash_table = json.loads(inv_hash_table)
        inv_hash_table = {v:k for k,v in inv_hash_table.items()}

        anim = Animation()
        if has_boneData:
            for bone in RLA_VALID_BONES: anim.TransformTracks[TransformType.Rotation][inv_hash_table[bone]] = Track()
        else:
            anim.TransformTracks[TransformType.Rotation][inv_hash_table[RLA_ROOT_BONE]] = Track()
        anim.TransformTracks[TransformType.Translation][inv_hash_table[RLA_ROOT_BONE]] = Track()
        base_tick = sssekai_global.rla_header['baseTicks']
        tick_min, tick_max = 1e18, 0
        for segment in chara_segments:            
            timestamp = (segment['timestamp'] - base_tick) / RLA_TIME_MAGNITUDE       
            tick_min = min(tick_min, timestamp)
            tick_max = max(tick_max, timestamp)     
            for idx, boneEuler in enumerate(segment['pose']['boneDatas']):
                if RLA_VALID_BONES[idx] != RLA_ROOT_BONE:
                    anim.TransformTracks[TransformType.Rotation][inv_hash_table[RLA_VALID_BONES[idx]]].add_keyframe(
                        KeyFrame(timestamp, euler3_to_quat_swizzled(*boneEuler), UnityQuaternion(), UnityQuaternion(), 0)
                    )
            anim.TransformTracks[TransformType.Translation][inv_hash_table[RLA_ROOT_BONE]].add_keyframe(
                KeyFrame(timestamp, Vector3(*segment['pose']['bodyPosition']), Vector3(), Vector3(), 0)
            )
            anim.TransformTracks[TransformType.Rotation][inv_hash_table[RLA_ROOT_BONE]].add_keyframe(
                KeyFrame(timestamp, euler3_to_quat_swizzled(*segment['pose']['bodyRotation']), UnityQuaternion(), UnityQuaternion(), 0)
            )
        import_armature_animation('RLA', anim, obj, 0, False)
        # TODO: Figure out why the frame_end is not being set correctly sometimes
        try:
            bpy.context.scene.frame_end = max(bpy.context.scene.frame_end, int(tick_max * bpy.context.scene.render.fps))
            bpy.context.scene.frame_current = int(tick_min * bpy.context.scene.render.fps) 
        except Exception as e:
            print('* Failed to set frame range:', e, 'range=', (tick_min, tick_max))
        return {'FINISHED'}

class SSSekaiBlenderImportRLAShapekeyAnimationOperator(bpy.types.Operator):
    bl_idname = "sssekai.rla_import_shapekey_animation_op"
    bl_label = T("Import Shapekey Animation")
    bl_description = T("Import Shapekey Animation for the selected character")
    def execute(self, context):        
        obj = bpy.context.active_object
        wm = context.window_manager
        active_chara = wm.sssekai_rla_active_character

        assert obj.type == 'ARMATURE', "Please select an armature to import the animation to!"
        mesh_obj = None
        for child in bpy.context.active_object.children:
            if KEY_SHAPEKEY_NAME_HASH_TBL in child.data:
                mesh_obj = child
                break
        assert mesh_obj, "KEY_SHAPEKEY_NAME_HASH_TBL not found in any of the sub meshes!"
        
        shapekey_segments = list()
        for tick, data in sssekai_global.rla_clip_data.items():
            m_data = data.get('MotionCaptureData', None)
            if m_data:                
                for data in m_data:
                    for pose in data['data']:
                        if pose['id'] == active_chara:   
                            shapeData = pose['pose']['shapeDatas']                     
                            if shapeData:
                                shapekey_segments.append((pose['timestamp'], shapeData))
        
        inv_hash_table = mesh_obj.data[KEY_SHAPEKEY_NAME_HASH_TBL]
        inv_hash_table = json.loads(inv_hash_table)
        inv_hash_table = {v:k for k,v in inv_hash_table.items()}        
        anim = Animation()
        base_tick = sssekai_global.rla_header['baseTicks']
        anim.FloatTracks[BLENDSHAPES_CRC] = dict()
        if shapekey_segments:
            for shape in RLA_VALID_BLENDSHAPES:
                anim.FloatTracks[BLENDSHAPES_CRC][inv_hash_table[shape]] = Track()
        tick_min, tick_max = 1e18, 0
        for timestamp, segment in shapekey_segments:
            timestamp = (timestamp - base_tick) / RLA_TIME_MAGNITUDE
            tick_min = min(tick_min, timestamp)
            tick_max = max(tick_max, timestamp)
            for idx, value in enumerate(segment):
                anim.FloatTracks[BLENDSHAPES_CRC][inv_hash_table[RLA_VALID_BLENDSHAPES[idx]]].add_keyframe(
                    KeyFrame(timestamp, value, 0, 0, 0)
                )
        import_keyshape_animation('RLA', anim, mesh_obj, 0, False)
        try:
            bpy.context.scene.frame_end = max(bpy.context.scene.frame_end, int(tick_max * bpy.context.scene.render.fps))
            bpy.context.scene.frame_current = int(tick_min * bpy.context.scene.render.fps) 
        except Exception as e:
            print('* Failed to set frame range:', e, 'range=', (tick_min, tick_max))
        return {'FINISHED'}

class SSSekaiBlenderImportRLABatchOperator(bpy.types.Operator):
    bl_idname = "sssekai.rla_import_batch_op"
    bl_label = T("Batch Import (slow!)")
    bl_description = T("Import RLA clips (Armature/KeyShape) from the selected range for the selected character")
    def execute(self, context):
        wm = context.window_manager
        rla_range = wm.sssekai_rla_import_range
        entries = list(sssekai_global.rla_raw_clips)
        entries = entries[rla_range[0]:rla_range[1]]
        for entry in entries:
            sssekai_global.rla_selected_raw_clip = entry        
            update_selected_rla_asset(entry)
            try:
                bpy.ops.sssekai.rla_import_armature_animation_op()
            except Exception as e:
                print('* Failed to import armature animation:', e)
            try:
                bpy.ops.sssekai.rla_import_shapekey_animation_op()
            except Exception as e:
                print('* Failed to import shapekey animation:', e)                
        return {'FINISHED'}         
   
def update_selected_rla_asset(entry):
    global sssekai_global
    from sssekai.fmt.rla import read_rla
    from io import BytesIO
    print('* Loading RLA index', entry)
    version = sssekai_global.rla_get_version()            
    sssekai_global.rla_clip_data = read_rla(BytesIO(sssekai_global.rla_raw_clips[entry]), version, strict=False)
    sssekai_global.rla_selected_raw_clip = entry
    min_tick, max_tick = 1e18, 0
    sssekai_global.rla_clip_charas.clear()
    for tick, data in sssekai_global.rla_clip_data.items():
        m_data = data.get('MotionCaptureData', None)
        if m_data:
            min_tick = min(min_tick, tick)
            max_tick = max(max_tick, tick)
            for data in m_data:
                for pose in data['data']:
                    sssekai_global.rla_clip_charas.add(pose['id'])
    base_tick = sssekai_global.rla_header['baseTicks']            
    sssekai_global.rla_clip_tick_range = ((min_tick - base_tick) / RLA_TIME_MAGNITUDE, (max_tick - base_tick) / RLA_TIME_MAGNITUDE)
       
def enumerate_rla_assets(self, context):
    global sssekai_global

    if context is None:
        return []
    
    wm = context.window_manager

    filename = wm.sssekai_streaming_live_archive_bundle
    if not path.isfile(filename) or filename == sssekai_global.rla_sekai_streaming_live_bundle_path:
        return sssekai_global.rla_enum_entries or [("NONE", "None", "", 0)]

    try:
        with open(filename, 'rb') as f:
            datas = dict()
            if f.read(2) == b'PK':
                f.seek(0)
                print('* Loaded RLA ZIP archive:', filename)
                with zipfile.ZipFile(f, 'r') as z:
                    for name in z.namelist():
                        with z.open(name) as zf:
                            datas[name] = zf.read()
            else:
                f.seek(0)
                rla_env = load_assetbundle(f)
                print('* Loaded RLA Unity bundle:', filename)
                for obj in rla_env.objects:
                    if obj.type in {ClassIDType.TextAsset}:
                        data = obj.read()
                        datas[data.name] = data.script.tobytes()
            header = sssekai_global.rla_header = json.loads(datas['sekai.rlh'].decode('utf-8'))   
            seconds = header['splitSeconds']
            sssekai_global.rla_raw_clips.clear()
            for sid in header['splitFileIds']:
                sname = 'sekai_%02d_%08d' % (seconds, sid)
                data = datas[sname + '.rla']
                sssekai_global.rla_raw_clips[sname] = data
            sssekai_global.rla_sekai_streaming_live_bundle_path = filename
            sssekai_global.rla_enum_entries = [(sname, sname, '', 'ANIM_DATA', index) for index, sname in enumerate(sssekai_global.rla_raw_clips.keys())]
    except Exception as e:
        print('* Failed to load RLA bundle:', e)       
    return sssekai_global.rla_enum_entries

class SSSekaiRLAImportPanel(bpy.types.Panel):
    bl_idname = "OBJ_PT_sssekai_rla_import"
    bl_label = T("RLA Import")
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "SSSekai"
    
    @classmethod
    def poll(self, context):
        wm = context.window_manager
        entry = wm.sssekai_rla_selected
        if entry and entry != sssekai_global.rla_selected_raw_clip and entry in sssekai_global.rla_raw_clips and sssekai_global.rla_raw_clips[entry]:            
            update_selected_rla_asset(entry)
        return True

    def draw(self, context: Context):
        layout = self.layout
        wm = context.window_manager
        row = layout.row()
        row.label(text=T('Statistics'))
        row = layout.row()
        row.label(text=T('Version: %d.%d') % sssekai_global.rla_get_version())
        row = layout.row()
        row.label(text=T('Time %.2fs - %.2fs') % sssekai_global.rla_clip_tick_range)
        row = layout.row()
        row.label(text=T('Character IDs: %s') % ','.join(str(x) for x in sssekai_global.rla_clip_charas))
        row = layout.row()
        row.label(text=T('Number of segments: %d') % len(sssekai_global.rla_clip_data))
        row = layout.row()
        layout.prop(wm, "sssekai_streaming_live_archive_bundle", icon='FILE_FOLDER')
        row = layout.row()
        row.prop(wm, "sssekai_rla_selected", icon='SCENE_DATA')
        row = layout.row()
        row.prop(wm, "sssekai_rla_active_character", icon='ARMATURE_DATA')
        row = layout.row()
        row.prop(bpy.context.scene.render, "fps", icon='TIME')
        row = layout.row()
        row.operator(SSSekaiBlenderImportRLAArmatureAnimationOperator.bl_idname, icon='ARMATURE_DATA')
        row.operator(SSSekaiBlenderImportRLAShapekeyAnimationOperator.bl_idname, icon='SHAPEKEY_DATA')
        row = layout.row()
        row.prop(wm, "sssekai_rla_single_pose_json", icon='SHAPEKEY_DATA')
        row = layout.row()
        row.operator(SSSekaiBlenderImportRLASinglePoseOperator.bl_idname, icon='ARMATURE_DATA')
        row = layout.row()
        row.label(text=T('Effective RLA clip range: %d - %d') % (0, len(sssekai_global.rla_raw_clips)))
        row = layout.row()
        selected = list(sssekai_global.rla_raw_clips or [])[wm.sssekai_rla_import_range[0]:wm.sssekai_rla_import_range[1]]
        row.label(text=T('Selected Clip: %s') % ','.join(selected))
        row = layout.row()
        row.prop(wm, "sssekai_rla_import_range", icon='FILE_FOLDER')
        row = layout.row()
        row.operator(SSSekaiBlenderImportRLABatchOperator.bl_idname, icon='FILE_FOLDER')
class SSSekaiBlenderImportPanel(bpy.types.Panel):
    bl_idname = "OBJ_PT_sssekai_import"
    bl_label = T("Import")
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "SSSekai"

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        layout.prop(wm, "sssekai_unity_version_override",icon='SETTINGS')
        row = layout.row()
        layout.label(text=T("Select Asset"))
        row = layout.row()
        row.prop(wm, "sssekai_assetbundle_file",icon='FILE_FOLDER')
        row = layout.row()
        row.prop(wm, "sssekai_assetbundle_selected",icon='SCENE_DATA')
        row = layout.row()
        row.operator(SSSekaiBlenderAssetSearchOperator.bl_idname,icon='VIEWZOOM')
        layout.separator()
        row = layout.row()
        row.label(text=T("Material Options"))
        row = layout.row()
        row.prop(wm, "sssekai_materials_use_principled_bsdf",icon='MATERIAL')
        row = layout.row()
        row.operator(SSSekaiBlenderApplyOutlineOperator.bl_idname,icon='META_CUBE')
        row = layout.row()
        row.label(text=T("Armature Options"))
        row = layout.row()
        row.prop(wm, "sssekai_armatures_as_articulations", icon='OUTLINER_OB_EMPTY')
        row = layout.row()
        row.operator(SSSekaiBlenderImportPhysicsOperator.bl_idname, icon='RIGID_BODY_CONSTRAINT')
        row = layout.row()
        row.prop(wm, "sssekai_armature_display_physics", toggle=True, icon='HIDE_OFF')
        row = layout.row()
        row.label(text=T("Animation Options"))
        row = layout.row()
        row.prop(wm, "sssekai_animation_import_offset",icon='TIME')
        row.prop(wm, "sssekai_animation_append_exisiting",icon='OVERLAY')
        row = layout.row()
        row.prop(wm, "sssekai_animation_import_camera_scaling",icon='CAMERA_DATA')
        row = layout.row()
        row.operator(SSSekaiBlenderExportAnimationTypeTree.bl_idname,icon='EXPORT')
        row = layout.row()        
        row.label(text=T("Import"))
        row = layout.row()
        row.operator(SSSekaiBlenderImportOperator.bl_idname,icon='APPEND_BLEND')        

def register():
    WindowManager.sssekai_assetbundle_file = StringProperty(
        name=T("Directory"),
        description=T("Where the asset bundle(s) are located. Every AssetBundle in this directory will be loaded (if possible)"),
        subtype='DIR_PATH',
    )
    WindowManager.sssekai_assetbundle_selected = EnumProperty(
        name=T("Asset"),
        description=T("Selected Asset"),
        items=enumerate_assets,
    )
    WindowManager.sssekai_streaming_live_archive_bundle = StringProperty(
        name=T("RLA Bundle"),
        description=T("The bundle file inside 'streaming_live/archive' directory.\nOr alternatively, a ZIP file containing 'sekai.rlh' (json) and respective 'sekai_xx_xxxxxx.rla' files. These files should have the extension '.rlh', '.rla'"),
        subtype='FILE_PATH',
    )
    WindowManager.sssekai_rla_selected = EnumProperty(
        name=T("RLA Clip"),
        description=T("Selected RLA Clip"),
        items=enumerate_rla_assets,
    )    
    WindowManager.sssekai_rla_active_character = IntProperty(
        name=T("Character ID"),
        description=T("Active Character ID"),
        default=0
    )
    WindowManager.sssekai_rla_single_pose_json = StringProperty(
        name=T("RLA Pose JSON"),
        description=T("JSON of a single RLA pose (e.g. {'bodyPosition':...}) dumped by rla2json w/ sssekai"),
        default=""
    )
    WindowManager.sssekai_rla_import_range = IntVectorProperty(
        name=T("Import Range"),
        description=T("Import clips from this range, order is as shown in the list"),
        size=2,
        default=[0,0]
    )
    WindowManager.sssekai_armatures_as_articulations = BoolProperty(
        name=T("Armatures as Articulations"),
        description=T("Treating armatures as articulations instead of skinned meshes. Useful for importing stages, etc"),
        default=False        
    )        
    WindowManager.sssekai_materials_use_principled_bsdf = BoolProperty(
        name=T("Use Principled BSDF"),
        description=T("Use Principled BSDF instead of SekaiShader for imported materials"),
        default=False        
    )    
    WindowManager.sssekai_armature_display_physics = BoolProperty(
        name=T("Display Physics"),
        description=T("Display Physics Objects"),
        default=True,
        update=SSSekaiBlenderPhysicsDisplayOperator.execute
    )
    WindowManager.sssekai_animation_append_exisiting = BoolProperty(
        name=T("Append"),
        description=T("Append Animations to the existing Action, instead of overwriting it"),
        default=False
    )
    WindowManager.sssekai_animation_import_offset = IntProperty(
        name=T("Offset"),
        description=T("Animation Offset in frames"),
        default=0
    )
    WindowManager.sssekai_animation_import_camera_scaling = FloatProperty(
        name=T("Camera Scaling"),
        description=T("Scaling used when importing camera animations"),
        default=1
    )
    def sssekai_on_unity_version_change(self, context):
        sssekai_set_unity_version(context.window_manager.sssekai_unity_version_override)
    WindowManager.sssekai_unity_version_override = StringProperty(
        name=T("Unity"),
        description=T("Override Unity Version"),
        default=sssekai_get_unity_version(),
        update=sssekai_on_unity_version_change
    )

    bpy.utils.register_class(SSSekaiBlenderImportOperator)
    bpy.utils.register_class(SSSekaiBlenderImportPanel)
    bpy.utils.register_class(SSSekaiRLAImportPanel)
    bpy.utils.register_class(SSSekaiBlenderAssetSearchOperator)
    bpy.types.Scene.sssekai_util_neck_attach_obj_face = bpy.props.PointerProperty(name=T("Face"),type=bpy.types.Armature)
    bpy.types.Scene.sssekai_util_neck_attach_obj_body = bpy.props.PointerProperty(name=T("Body"),type=bpy.types.Armature)
    bpy.utils.register_class(SSSekaiBlenderUtilNeckAttachOperator)
    bpy.utils.register_class(SSSekaiBlenderUtilNeckAttach)
    bpy.utils.register_class(SSSekaiBlenderApplyOutlineOperator)
    bpy.utils.register_class(SSSekaiBlenderImportPhysicsOperator)
    bpy.utils.register_class(SSSekaiBlenderPhysicsDisplayOperator)
    bpy.utils.register_class(SSSekaiBlenderUtilMiscPanel)
    bpy.utils.register_class(SSSekaiBlenderUtilMiscRenameRemoveNumericSuffixOperator)
    bpy.utils.register_class(SSSekaiBlenderUtilMiscRemoveBoneHierarchyOperator)
    bpy.utils.register_class(SSSekaiBlenderUtilMiscRecalculateBoneHashTableOperator)
    bpy.utils.register_class(SSSekaiBlenderUtilApplyModifersOperator)
    bpy.utils.register_class(SSSekaiBlenderUtilArmatureMergeOperator)
    bpy.utils.register_class(SSSekaiBlenderUtilNeckMergeOperator)
    bpy.utils.register_class(SSSekaiBlenderUtilArmatureSimplifyOperator)
    bpy.utils.register_class(SSSekaiBlenderExportAnimationTypeTree)
    bpy.utils.register_class(SSSekaiBlenderImportRLAArmatureAnimationOperator)
    bpy.utils.register_class(SSSekaiBlenderImportRLAShapekeyAnimationOperator)
    bpy.utils.register_class(SSSekaiBlenderImportRLASinglePoseOperator)
    bpy.utils.register_class(SSSekaiBlenderImportRLABatchOperator)
def unregister():    
    bpy.utils.unregister_class(SSSekaiBlenderAssetSearchOperator)
    bpy.utils.unregister_class(SSSekaiBlenderImportOperator)
    bpy.utils.unregister_class(SSSekaiBlenderImportPanel)
    bpy.utils.unregister_class(SSSekaiRLAImportPanel)
    bpy.utils.unregister_class(SSSekaiBlenderUtilNeckAttachOperator)
    bpy.utils.unregister_class(SSSekaiBlenderUtilNeckAttach)
    bpy.utils.unregister_class(SSSekaiBlenderApplyOutlineOperator)
    bpy.utils.unregister_class(SSSekaiBlenderImportPhysicsOperator)
    bpy.utils.unregister_class(SSSekaiBlenderPhysicsDisplayOperator)
    bpy.utils.unregister_class(SSSekaiBlenderUtilMiscPanel)
    bpy.utils.unregister_class(SSSekaiBlenderUtilMiscRenameRemoveNumericSuffixOperator)
    bpy.utils.unregister_class(SSSekaiBlenderUtilMiscRemoveBoneHierarchyOperator)
    bpy.utils.unregister_class(SSSekaiBlenderUtilMiscRecalculateBoneHashTableOperator)
    bpy.utils.unregister_class(SSSekaiBlenderUtilApplyModifersOperator)
    bpy.utils.unregister_class(SSSekaiBlenderUtilArmatureMergeOperator)
    bpy.utils.unregister_class(SSSekaiBlenderUtilNeckMergeOperator)
    bpy.utils.unregister_class(SSSekaiBlenderUtilArmatureSimplifyOperator)
    bpy.utils.unregister_class(SSSekaiBlenderExportAnimationTypeTree)
    bpy.utils.unregister_class(SSSekaiBlenderImportRLAArmatureAnimationOperator)
    bpy.utils.unregister_class(SSSekaiBlenderImportRLAShapekeyAnimationOperator)
    bpy.utils.unregister_class(SSSekaiBlenderImportRLASinglePoseOperator)
    bpy.utils.unregister_class(SSSekaiBlenderImportRLABatchOperator)
