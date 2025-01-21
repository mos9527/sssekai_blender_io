from bpy.app.translations import pgettext as T
import bpy, bpy.utils.previews
import json

from ..core.consts import *
from ..core.utils import get_name_hash
from ..core.helpers import create_empty
from .. import register_class, logger


@register_class
class SSSekaiBlenderUtilMiscRecalculateBoneHashTableOperator(bpy.types.Operator):
    bl_idname = "sssekai.util_misc_recalculate_bone_hash_table_op"
    bl_label = T("Recalculate Hash Table")
    bl_description = T(
        "Recalculate the animation hash table for the selected armature/articulation. You should do this after renaming bones or changing the hierarchy."
    )

    def execute(self, context):
        assert context.mode == "OBJECT", "Please select an armature in Object Mode!"
        obj = bpy.context.active_object
        if obj.data and KEY_BONE_NAME_HASH_TBL in obj.data:
            global_path_hash_table = dict()
            bone_path_tbl = dict()

            def dfs(bone):
                if bone.parent:
                    bone_path_tbl[bone.name] = (
                        bone_path_tbl[bone.parent.name] + "/" + bone.name
                    )
                else:
                    bone_path_tbl[bone.name] = bone.name
                global_path_hash_table[str(get_name_hash(bone_path_tbl[bone.name]))] = (
                    bone.name
                )
                for child in bone.children:
                    dfs(child)

            for bone in obj.data.bones:
                dfs(bone)
            obj.data[KEY_BONE_NAME_HASH_TBL] = json.dumps(
                global_path_hash_table, ensure_ascii=False
            )
        elif KEY_ARTICULATION_NAME_HASH_TBL in obj:
            joint_path_hash_tbl = dict()
            joint_path_tbl = dict()

            def dfs(joint):
                if not KEY_JOINT_BONE_NAME in joint:
                    return
                joint_name = joint[KEY_JOINT_BONE_NAME]
                if joint.parent and KEY_JOINT_BONE_NAME in joint.parent:
                    joint_path_tbl[joint_name] = (
                        joint_path_tbl[joint.parent[KEY_JOINT_BONE_NAME]]
                        + "/"
                        + joint_name
                    )
                else:
                    joint_path_tbl[joint_name] = joint_name
                joint_path_hash_tbl[str(get_name_hash(joint_path_tbl[joint_name]))] = (
                    joint_name
                )
                for child in joint.children:
                    dfs(child)

            for child in obj.children:
                dfs(child)
            obj[KEY_ARTICULATION_NAME_HASH_TBL] = json.dumps(
                joint_path_hash_tbl, ensure_ascii=False
            )
        else:
            assert (
                False
            ), "Please select an armature/articulation imported by SSSekai first!"
        return {"FINISHED"}


@register_class
class SSSekaiBlenderUtilMiscRemoveBoneHierarchyOperator(bpy.types.Operator):
    bl_idname = "sssekai.util_misc_remove_bone_hierarchy_op"
    bl_label = T("Remove Bone Hierarchy")
    bl_description = T("Remove the hierarchy from the selected bones in Edit Mode")

    def execute(self, context):
        assert context.mode == "EDIT_ARMATURE", "Please select bones in Edit Mode!"
        ebone = bpy.context.active_bone
        for bone in ebone.children_recursive + [ebone]:
            bpy.context.active_object.data.edit_bones.remove(bone)
        return {"FINISHED"}


@register_class
class SSSekaiBlenderUtilMiscRenameRemoveNumericSuffixOperator(bpy.types.Operator):
    bl_idname = "sssekai.util_misc_rename_remove_numeric_suffix_op"
    bl_label = T("Remove Numeric Suffix")
    bl_description = T(
        "Remove the suffix from the selected objects and edit bones (i.e. xxx.001 -> xxx)"
    )

    def execute(self, context):
        def rename_one(obj):
            names = obj.name.split(".")
            if len(names) > 1 and names[-1].isnumeric():
                obj.name = ".".join(names[:-1])

        for pa in bpy.context.selected_objects:
            for obj in [pa] + pa.children_recursive:
                rename_one(obj)

        ebone = bpy.context.active_bone
        for bone in ebone.children_recursive + [ebone]:
            rename_one(bone)
        return {"FINISHED"}


@register_class
class SSSekaiBlenderUtilMiscBatchAddArmatureModifier(bpy.types.Operator):
    bl_idname = "sssekai.util_misc_add_armature_modifer_batch_op"
    bl_label = T("Add Armature Modifier")
    bl_description = T(
        "Add an Armature modifier to the selected objects, with the active object as the target armature"
    )

    def execute(self, context):
        arma = context.window_manager.sssekai_util_batch_armature_mod_parent
        assert arma, "Please select an armature as the target"
        arma = context.scene.objects.get(arma.name)
        for pa in bpy.context.selected_objects:
            for obj in [pa] + pa.children_recursive:
                if obj.type == "MESH":
                    mod = [mod for mod in obj.modifiers if mod.type == "ARMATURE"]
                    if mod:
                        mod = mod[-1]
                        mod.object = arma
                        logger.debug("Updated Armature modifier for %s" % obj.name)
                    else:
                        mod = (
                            obj.modifiers.new("Armature", "ARMATURE")
                            if not mod
                            else mod[-1]
                        )
                        mod.object = arma
                        logger.debug("Added Armature modifier to %s" % obj.name)
        return {"FINISHED"}


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


@register_class
class SSSekaiBlenderUtilCharacterScalingMakeRootOperator(bpy.types.Operator):
    bl_idname = "sssekai.util_character_scaling_make_root_op"
    bl_label = T("Make/Update Root Height Scale")
    bl_description = T(
        """Appends the selected object to an Empty object (that can be configured with a height value), with the Empty object as the new root.
If a root object is in the selection as well, this would become the root instead.
NOTE: This only affects the FINAL visual of the pose. The armature itself isn't affected.
      If otherwise needed, enter Object Mode, scale the armature, and then Apply Scale to the entire armature."""
    )

    def execute(self, context):
        scene = context.scene
        objs = context.selected_objects
        root = None
        for obj in objs:
            pred = (
                lambda obj: obj
                and obj.type == "EMPTY"
                and KEY_SEKAI_CHARACTER_HEIGHT in obj
            )
            if pred(obj):
                root = obj
                break
            if pred(obj.parent):
                root = obj.parent
                break
        if not root:
            root = create_empty("Character Root")
            root[KEY_SEKAI_CHARACTER_HEIGHT] = 1.0
        else:
            logger.debug("Using root %s" % root.name)
        # Set up drivers for the scaling
        for obj in objs:
            # Collect `Position` pose bones that we can apply the scaling to
            if obj.type == "ARMATURE":
                for bone in obj.pose.bones:
                    if bone.name == "Position":
                        bone.driver_remove("scale")
                        for ch in bone.driver_add("scale"):
                            ch.driver.type = "SCRIPTED"
                            var = ch.driver.variables.new()
                            var.name = "height"
                            var.type = "SINGLE_PROP"
                            var.targets[0].id = root
                            var.targets[0].data_path = (
                                f'["{KEY_SEKAI_CHARACTER_HEIGHT}"]'
                            )
                            ch.driver.expression = "height"
                        logger.debug("Applied Height driver for %s" % obj.name)
        for obj in objs:
            if obj != root:
                obj.parent = root
        return {"FINISHED"}


@register_class
class SSSekaiBlenderUtilCharacterNeckMergeOperator(bpy.types.Operator):
    bl_idname = "sssekai.util_neck_merge_op"
    bl_label = T("Merge")
    bl_description = T(
        "Merge the selected face armature with the selected body armature"
    )

    def execute(self, context):
        scene = context.scene
        wm = context.window_manager
        face_arma = wm.sssekai_util_neck_attach_obj_face
        body_arma = wm.sssekai_util_neck_attach_obj_body
        assert face_arma and body_arma, "Please select both face and body armatures"
        bpy.ops.sssekai.util_neck_attach_op()  # Attach nontheless
        face_obj = scene.objects.get(face_arma.name)
        body_obj = scene.objects.get(body_arma.name)
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        face_obj.select_set(True)
        body_obj.select_set(True)
        bpy.context.view_layer.objects.active = body_obj
        bpy.ops.sssekai.util_armature_merge_op()
        # Clean up bone hierarchy
        # We have made a lot of assumptions here...
        # Priori:
        # - The duped bones would be named as 'Bone.001', 'Bone.002', etc
        # - The face armature and body armature (if chosen correctly) would share some bones, up until the 'Neck' bone
        bpy.ops.object.mode_set(mode="EDIT")
        # - Changing the bone hierarchy in EDIT mode would not affect the mesh or the bone's armature space transforms
        # We will:
        # - Replace the subtree of the Neck bone of the body armature with the subtree of the Neck bone of the face armature
        # - Fix up the naming
        body_arma = body_obj.data
        for bone in body_arma.edit_bones["Head.001"].children:
            bone.parent = body_arma.edit_bones["Head"]
        # - Remove the now redundant bones
        body_arma.edit_bones.active = body_arma.edit_bones["Position.001"]
        bpy.ops.sssekai.util_misc_remove_bone_hierarchy_op()
        bpy.ops.object.mode_set(mode="OBJECT")
        return {"FINISHED"}


@register_class
class SSSekaiBlenderUtilCharacterHeelOffsetOperator(bpy.types.Operator):
    bl_idname = "sssekai.util_character_heel_offset_op"
    bl_label = T("Calibrate Heel Offset")
    bl_description = T(
        "Set the Z offset of the selected character by its OffsetValue bone. Do this when the character's feet are not at the origin, or when you changed the character's height."
    )

    def execute(self, context):
        obj = context.active_object
        assert (
            obj and KEY_SEKAI_CHARACTER_HEIGHT in obj
        ), "Please select an Character Root!"
        # Search for armature that has the OffsetValue bone
        ebone = None
        for child in obj.children:
            if child.type == "ARMATURE":
                bpy.context.view_layer.objects.active = child
                bpy.ops.object.mode_set(mode="EDIT")
                ebone = child.data.edit_bones.get("OffsetValue")
                bpy.ops.object.mode_set(mode="OBJECT")
                if ebone:
                    logger.debug("Found OffsetValue bone in %s" % child.name)
                    break
        assert ebone, "OffsetValue bone not found"
        loc_xyz = ebone.head
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode="OBJECT")
        obj.location.z = loc_xyz.z * obj[KEY_SEKAI_CHARACTER_HEIGHT]
        return {"FINISHED"}


@register_class
class SSSekaiBlenderUtilCharacterArmatureSimplifyOperator(bpy.types.Operator):
    bl_idname = "sssekai.util_armature_simplify_op"
    bl_label = T("Simplify Armature")
    bl_description = T(
        "Simplify the bone hierachy of the selected armature. This operation is irreversible!"
    )

    WHITELIST = {
        "Position",
        "PositionOffset",
        "Hip",
        "Left_Thigh",
        "Left_AssistHip",
        "Left_Knee",
        "Left_Ankle",
        "Left_shw_back",
        "Left_Toe",
        "Left_shw_front",
        "Right_Thigh",
        "Right_AssistHip",
        "Right_Knee",
        "Right_Ankle",
        "Right_shw_back",
        "Right_Toe",
        "Right_shw_front",
        "Waist",
        "Spine",
        "Chest",
        "Left_Shoulder",
        "Left_Arm",
        "Left_ArmRoll",
        "Left_Elbow",
        "Left_EllbowSupport",
        "Left_EllbowSupport_End",
        "Left_ForeArmRoll",
        "Left_Wrist",
        "Left_Hand_Attach",
        "Left_Index_01",
        "Left_Index_02",
        "Left_Index_03",
        "Left_Middle_01",
        "Left_Middle_02",
        "Left_Middle_03",
        "Left_Pinky_01",
        "Left_Pinky_02",
        "Left_Pinky_03",
        "Left_Ring_01",
        "Left_Ring_02",
        "Left_Ring_03",
        "Left_Thumb_01",
        "Left_Thumb_02",
        "Left_Thumb_03",
        "Neck",
        "Head",
        "Right_Shoulder",
        "Right_Arm",
        "Right_ArmRoll",
        "Right_Elbow",
        "Right_EllbowSupport",
        "Right_EllbowSupport_End",
        "Right_ForeArmRoll",
        "Right_Wrist",
        "Right_Hand_Attach",
        "Right_Index_01",
        "Right_Index_02",
        "Right_Index_03",
        "Right_Middle_01",
        "Right_Middle_02",
        "Right_Middle_03",
        "Right_Pinky_01",
        "Right_Pinky_02",
        "Right_Pinky_03",
        "Right_Ring_01",
        "Right_Ring_02",
        "Right_Ring_03",
        "Right_Thumb_01",
        "Right_Thumb_02",
        "Right_Thumb_03",
        "Chest_const",
        "Thigh_Upv",
    }

    def execute(self, context):
        assert (
            context.mode == "EDIT_ARMATURE"
        ), "Please select an armature in Edit Mode!"
        armature = bpy.context.active_object
        assert armature.type == "ARMATURE", "Please select an armature!"
        for bone in armature.data.edit_bones:
            if (
                bone.name
                not in SSSekaiBlenderUtilCharacterArmatureSimplifyOperator.WHITELIST
            ):
                logger.debug("Removing bone %s" % bone.name)
                armature.data.edit_bones.remove(bone)
        return {"FINISHED"}
