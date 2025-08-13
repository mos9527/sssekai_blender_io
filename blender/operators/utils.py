from bpy.app.translations import pgettext as T
import bpy, bpy.utils.previews
import json

from ..core.consts import *
from ..core.utils import crc32
from ..core.helpers import create_empty
from .. import register_class, logger


@register_class
class SSSekaiBlenderUtilApplyModifersOperator(bpy.types.Operator):
    # From: https://github.com/przemir/ApplyModifierForObjectWithShapeKeys/blob/master/ApplyModifierForObjectWithShapeKeys.py
    # NOTE: Only a subset of the original features are implemented here
    bl_idname = "sssekai.util_apply_modifiers_op"
    bl_label = T("Apply Modifiers")
    bl_description = T(
        "Apply all modifiers to the selected objects's meshes. Snippet from github.com/przemir/ApplyModifierForObjectWithShapeKeys"
    )

    def execute(self, context):
        PROPS = [
            "name",
            "interpolation",
            "mute",
            "slider_max",
            "slider_min",
            "value",
            "vertex_group",
        ]

        context = bpy.context
        obj = context.object
        modifiers = obj.modifiers

        shapesCount = len(obj.data.shape_keys.key_blocks) if obj.data.shape_keys else 0
        if obj.data.shape_keys:
            shapesCount = len(obj.data.shape_keys.key_blocks)

        if shapesCount == 0:
            for modifier in modifiers:
                bpy.ops.object.modifier_apply(modifier=modifier.name)
            return {"FINISHED"}

        # We want to preserve original object, so all shapes will be joined to it.
        originalObject = context.view_layer.objects.active
        bpy.ops.object.select_all(action="DESELECT")
        originalObject.select_set(True)

        # Copy object which will holds all shape keys.
        bpy.ops.object.duplicate_move(
            OBJECT_OT_duplicate={"linked": False, "mode": "TRANSLATION"},
            TRANSFORM_OT_translate={
                "value": (0, 0, 0),
                "orient_type": "GLOBAL",
                "orient_matrix": ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
                "orient_matrix_type": "GLOBAL",
                "constraint_axis": (False, False, False),
                "mirror": True,
                "use_proportional_edit": False,
                "proportional_edit_falloff": "SMOOTH",
                "proportional_size": 1,
                "use_proportional_connected": False,
                "use_proportional_projected": False,
                "snap": False,
                "snap_target": "CLOSEST",
                "snap_point": (0, 0, 0),
                "snap_align": False,
                "snap_normal": (0, 0, 0),
                "gpencil_strokes": False,
                "cursor_transform": False,
                "texture_space": False,
                "remove_on_cancel": False,
                "release_confirm": False,
                "use_accurate": False,
            },
        )
        copyObject = context.view_layer.objects.active
        copyObject.select_set(False)

        # Return selection to originalObject.
        context.view_layer.objects.active = originalObject
        originalObject.select_set(True)
        # Save key shape properties
        shapekey_props = [
            {
                p: getattr(originalObject.data.shape_keys.key_blocks[i], p, None)
                for p in PROPS
            }
            for i in range(shapesCount)
        ]
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
            bpy.ops.object.duplicate_move(
                OBJECT_OT_duplicate={"linked": False, "mode": "TRANSLATION"},
                TRANSFORM_OT_translate={
                    "value": (0, 0, 0),
                    "orient_type": "GLOBAL",
                    "orient_matrix": ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
                    "orient_matrix_type": "GLOBAL",
                    "constraint_axis": (False, False, False),
                    "mirror": True,
                    "use_proportional_edit": False,
                    "proportional_edit_falloff": "SMOOTH",
                    "proportional_size": 1,
                    "use_proportional_connected": False,
                    "use_proportional_projected": False,
                    "snap": False,
                    "snap_target": "CLOSEST",
                    "snap_point": (0, 0, 0),
                    "snap_align": False,
                    "snap_normal": (0, 0, 0),
                    "gpencil_strokes": False,
                    "cursor_transform": False,
                    "texture_space": False,
                    "remove_on_cancel": False,
                    "release_confirm": False,
                    "use_accurate": False,
                },
            )
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
                setattr(
                    originalObject.data.shape_keys.key_blocks[i],
                    p,
                    shapekey_props[i][p],
                )
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

        return {"FINISHED"}


@register_class
class SSSekaiBlenderUtilCharaNeckMergeOperator(bpy.types.Operator):
    bl_idname = "sssekai.util_chara_root_armature_merge_op"
    bl_label = T("Merge")
    bl_description = T(
        "Merge character Face and Body meshes,taking constraints & modifed rest poses into consideration."
    )

    def execute(self, context):
        active_obj = context.active_object
        assert (
            active_obj and KEY_SEKAI_CHARACTER_ROOT in active_obj
        ), "Please select a Character Root"
        face = active_obj[KEY_SEKAI_CHARACTER_FACE_OBJ]
        body = active_obj[KEY_SEKAI_CHARACTER_BODY_OBJ]
        face: bpy.types.Object
        body: bpy.types.Object
        if face and not body:
            active_obj[KEY_SEKAI_CHARACTER_BODY_OBJ] = face
            return {"FINISHED"}
        elif body and not face:
            active_obj[KEY_SEKAI_CHARACTER_FACE_OBJ] = body
            return {"FINISHED"}
        elif not face and not body:
            raise ValueError("Face and Body must be set")
        # Always try to attach first
        bpy.ops.sssekai.util_chara_root_armature_attach_op()
        # For the child armature, we:
        # - Apply the modifier so the mesh matches the new rest pose
        for child in face.children:
            if child.type == "MESH":
                bpy.context.view_layer.objects.active = child
                bpy.ops.sssekai.util_apply_modifiers_op()
        bpy.context.view_layer.objects.active = face
        bpy.ops.object.mode_set(mode="POSE")
        # With the armature in pose mode, we:
        # - Apply all bone constraints
        for bone in face.pose.bones:
            face.data.bones.active = bone.bone
            for constraint in bone.constraints:
                bpy.ops.constraint.apply(constraint=constraint.name, owner="BONE")
        # - Set the pose to rest pose
        bpy.ops.pose.armature_apply(selected=False)
        # For the parent armature, we:
        # - Merge the child armature with the parent armature
        # - Assign new modifers to the merged mesh
        bpy.ops.object.mode_set(mode="OBJECT")
        face.select_set(True)
        body.select_set(True)
        bpy.context.view_layer.objects.active = body
        bpy.ops.object.join()
        for child in body.children:
            if child.type == "MESH" and len(child.modifiers) == 0:
                child.modifiers.new("Armature", "ARMATURE").object = body
        active_obj[KEY_SEKAI_CHARACTER_FACE_OBJ] = body
        # In Edit Mode clean up dupe bones and reparent to the main armature
        bpy.ops.object.mode_set(mode="EDIT")
        to_remove = set()
        for bone in body.data.edit_bones:
            if bone.parent:
                if bone.parent.name.endswith(".001"):
                    to_remove.add(bone.parent.name)
                    bone.parent = body.data.edit_bones[bone.parent.name[:-4]]
        for bone in to_remove:
            body.data.edit_bones.remove(body.data.edit_bones[bone])
        bpy.ops.object.mode_set(mode="OBJECT")
        return {"FINISHED"}


@register_class
class SSSekaiBlenderUtilCharaNeckAttachOperator(bpy.types.Operator):
    bl_idname = "sssekai.util_chara_root_armature_attach_op"
    bl_label = T("Attach")
    bl_description = T(
        "Attach the selected character Face armature to the selected Body armature by binding Neck and Head bones."
    )

    def execute(self, context):
        scene = context.scene
        wm = context.window_manager
        active_obj = context.active_object
        assert (
            active_obj and KEY_SEKAI_CHARACTER_ROOT in active_obj
        ), "Please select a Character Root"
        face = active_obj[KEY_SEKAI_CHARACTER_FACE_OBJ]
        body = active_obj[KEY_SEKAI_CHARACTER_BODY_OBJ]
        face: bpy.types.Object
        body: bpy.types.Object
        assert face and body, "Face and Body must be set"
        assert face != body, "Face and Body must be different."
        bpy.context.view_layer.objects.active = face
        bpy.ops.object.mode_set(mode="POSE")

        def add_constraint(name):
            bone = face.pose.bones[name]
            constraint = bone.constraints.new("COPY_TRANSFORMS")
            constraint.target = body
            constraint.subtarget = name

        add_constraint("Neck")
        add_constraint("Head")
        add_constraint("Position")
        return {"FINISHED"}


@register_class
class SSSekaiBlenderUtilArmatureBakeIdentityPoseOperator(bpy.types.Operator):
    bl_idname = "sssekai.util_armature_set_identity_pose_op"
    bl_label = T("Bake Identity Pose")
    bl_description = T(
        "Bakes the current visual transform (e.g. Scaling, Modifiers) into the armature's Mesh data and sets current pose as the new rest pose. This in effect would result in all new bone transforms to be identity transforms."
    )

    def execute(self, context):
        active_obj = context.active_object
        assert active_obj and active_obj.type == "ARMATURE", "Please select an armature"
        # All mesh children - bake their visual transforms into the mesh data
        children = []
        for child in active_obj.children:
            if child.type == "MESH":
                bpy.context.view_layer.objects.active = child
                children.append(child)
                bpy.ops.object.mode_set(mode="OBJECT")
                bpy.ops.sssekai.util_apply_modifiers_op()
                bpy.context.view_layer.objects.active = active_obj
                bpy.ops.object.mode_set(mode="POSE")
        # Re-add armature modifier to all children
        for child in children:
            child.modifiers.new("Armature", "ARMATURE").object = active_obj
        # Set the armature to pose mode and apply all constraints
        bpy.ops.object.mode_set(mode="POSE")
        bpy.ops.pose.armature_apply(selected=False)
        bpy.ops.object.mode_set(mode="OBJECT")
        return {"FINISHED"}


@register_class
class SSSekaiBlenderUtilArmatureBoneParentToWeightOperator(bpy.types.Operator):
    bl_idname = "sssekai.util_armature_bone_parent_to_weight_op"
    bl_label = T("Bone Parent to Weight")
    bl_description = T(
        "Transforms bone parent relationships into vertex group weight. NOTE: This only applies to meshes without pre-existing vertex groups."
    )

    def execute(self, context):
        active_obj = context.active_object
        assert active_obj and active_obj.type == "ARMATURE", "Please select an armature"
        children = []
        # Deselect all objects
        bpy.ops.object.select_all(action="DESELECT")
        for child in active_obj.children:
            if child.type == "MESH":
                # Only add ones w/o vertex groups
                if not child.vertex_groups and child.parent_bone:
                    children.append((child, child.parent_bone))
                    child.select_set(True)
        bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        for child, bone in children:
            child: bpy.types.Object
            data: bpy.types.Mesh = child.data
            # Create vertex group with the name of the bone
            vgroup = child.vertex_groups.new(name=bone)
            # Assign weight 1.0 to all vertices
            for i, v in enumerate(data.vertices):
                vgroup.add([i], 1.0, "ADD")
            # Set the parent to the armature
            child.parent = active_obj
            child.parent_type = "OBJECT"
            child.parent_bone = bone
            child.modifiers.new("Armature", "ARMATURE").object = active_obj
            # Add Modifier

        return {"FINISHED"}
