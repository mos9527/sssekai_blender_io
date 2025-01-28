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
class SSSekaiBlenderUtilArmatureMergeOperator(bpy.types.Operator):
    bl_idname = "sssekai.util_armature_merge_op"
    bl_label = T("Merge Armatures")
    bl_description = T(
        "Merge one armature into another, taking constraints & modifed rest poses into consideration.  With the active one as the newly merged armature."
    )

    def execute(self, context):
        scene = context.scene
        assert (
            len(bpy.context.selected_objects) == 2
        ), "Please select 2 and only 2 objects."
        child_obj = bpy.context.selected_objects[1]
        parent_obj = bpy.context.selected_objects[0]
        if child_obj == bpy.context.active_object:
            child_obj, parent_obj = parent_obj, child_obj
        assert (
            child_obj.type == "ARMATURE" and parent_obj.type == "ARMATURE"
        ), "Please select 2 Armatures."
        child_arma = child_obj.data
        parent_arma = parent_obj.data
        # For the child armature, we:
        # - Apply the modifier so the mesh matches the new rest pose
        for child in child_obj.children:
            if child.type == "MESH":
                bpy.context.view_layer.objects.active = child
                bpy.ops.sssekai.util_apply_modifiers_op()
        bpy.context.view_layer.objects.active = child_obj
        bpy.ops.object.mode_set(mode="POSE")
        # With the armature in pose mode, we:
        # - Apply all bone constraints
        for bone in child_obj.pose.bones:
            child_arma.bones.active = bone.bone
            for constraint in bone.constraints:
                bpy.ops.constraint.apply(constraint=constraint.name, owner="BONE")
        # - Set the pose to rest pose
        bpy.ops.pose.armature_apply(selected=False)
        # For the parent armature, we:
        # - Merge the child armature with the parent armature
        # - Assign new modifers to the merged mesh
        bpy.ops.object.mode_set(mode="OBJECT")
        child_obj.select_set(True)
        parent_obj.select_set(True)
        bpy.context.view_layer.objects.active = parent_obj
        bpy.ops.object.join()
        for child in parent_obj.children:
            if child.type == "MESH" and len(child.modifiers) == 0:
                child.modifiers.new("Armature", "ARMATURE").object = parent_obj
        return {"FINISHED"}


@register_class
class SSSekaiBlenderUtilNeckAttachOperator(bpy.types.Operator):
    bl_idname = "sssekai.util_neck_attach_op"
    bl_label = T("Attach")
    bl_description = T(
        "Attach the selected face armature to the selected body armature"
    )

    def execute(self, context):
        scene = context.scene
        wm = context.window_manager
        face_arma = wm.sssekai_util_neck_attach_obj_face
        body_arma = wm.sssekai_util_neck_attach_obj_body
        assert face_arma and body_arma, "Please select both face and body armatures"
        face_obj = scene.objects.get(face_arma.name)
        body_obj = scene.objects.get(body_arma.name)
        bpy.context.view_layer.objects.active = face_obj
        bpy.ops.object.mode_set(mode="POSE")

        def add_constraint(name):
            bone = face_obj.pose.bones[name]
            constraint = bone.constraints.new("COPY_TRANSFORMS")
            constraint.target = body_obj
            constraint.subtarget = name

        add_constraint("Neck")
        add_constraint("Head")
        return {"FINISHED"}
