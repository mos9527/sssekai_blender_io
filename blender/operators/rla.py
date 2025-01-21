from bpy.app.translations import pgettext as T
import bpy, bpy.utils.previews
import json

from sssekai.unity.AnimationClip import Animation, Track, TransformType, KeyFrame
from sssekai.unity.AssetBundle import load_assetbundle
from UnityPy.enums import ClassIDType

from ..core.consts import *
from ..core.helpers import (
    retrive_action,
    apply_action,
)
from ..core.math import uVector3, uQuaternion
from ..core.math import euler3_to_quat_swizzled
from .. import register_class, logger

from ..core.animation import (
    load_armature_animation,
    load_keyshape_animation,
)
from .. import sssekai_global


@register_class
class SSSekaiBlenderImportRLASinglePoseOperator(bpy.types.Operator):
    bl_idname = "sssekai.rla_import_armature_pose_op"
    bl_label = T("Import RLA Pose")
    bl_description = T(
        "Import RLA Pose (armature/shapekey) for the selected object from a JSON, into the offset frame set in Animation Options. NOTE: The face/body armature must be pre-processed with the Merge option!"
    )

    def execute(self, context):
        arma_obj = bpy.context.active_object
        assert (
            arma_obj.type == "ARMATURE"
        ), "Please select an armature to import the animation to!"
        mesh_obj = None
        for child in bpy.context.active_object.children:
            if KEY_SHAPEKEY_NAME_HASH_TBL in child.data:
                mesh_obj = child
                break
        assert (
            mesh_obj
        ), "KEY_SHAPEKEY_NAME_HASH_TBL not found in any of the sub meshes!"

        wm = context.window_manager
        pose = json.loads(wm.sssekai_rla_single_pose_json)

        inv_bone_hash_table = arma_obj.data[KEY_BONE_NAME_HASH_TBL]
        inv_bone_hash_table = json.loads(inv_bone_hash_table)
        inv_bone_hash_table = {v: k for k, v in inv_bone_hash_table.items()}

        inv_shape_table = mesh_obj.data[KEY_SHAPEKEY_NAME_HASH_TBL]
        inv_shape_table = json.loads(inv_shape_table)
        inv_shape_table = {v: k for k, v in inv_shape_table.items()}

        anim = Animation()
        if pose["boneDatas"]:
            for bone in RLA_VALID_BONES:
                anim.TransformTracks[TransformType.Rotation][
                    inv_bone_hash_table[bone]
                ] = Track()
        else:
            anim.TransformTracks[TransformType.Rotation][
                inv_bone_hash_table[RLA_ROOT_BONE]
            ] = Track()
        anim.TransformTracks[TransformType.Translation][
            inv_bone_hash_table[RLA_ROOT_BONE]
        ] = Track()

        if pose["shapeDatas"]:
            anim.FloatTracks[BLENDSHAPES_CRC] = dict()
            for shape in RLA_VALID_BLENDSHAPES:
                anim.FloatTracks[BLENDSHAPES_CRC][inv_shape_table[shape]] = Track()

        for idx, boneEuler in enumerate(pose["boneDatas"]):
            if RLA_VALID_BONES[idx] != RLA_ROOT_BONE:
                anim.TransformTracks[TransformType.Rotation][
                    inv_bone_hash_table[RLA_VALID_BONES[idx]]
                ].add_keyframe(
                    KeyFrame(
                        0,
                        euler3_to_quat_swizzled(*boneEuler),
                        uQuaternion(),
                        uQuaternion(),
                        0,
                    )
                )
        anim.TransformTracks[TransformType.Translation][
            inv_bone_hash_table[RLA_ROOT_BONE]
        ].add_keyframe(
            KeyFrame(0, uVector3(*pose["bodyPosition"]), uVector3(), uVector3(), 0)
        )
        anim.TransformTracks[TransformType.Rotation][
            inv_bone_hash_table[RLA_ROOT_BONE]
        ].add_keyframe(
            KeyFrame(
                0,
                euler3_to_quat_swizzled(*pose["bodyRotation"]),
                uQuaternion(),
                uQuaternion(),
                0,
            )
        )

        for idx, value in enumerate(pose["shapeDatas"]):
            anim.FloatTracks[BLENDSHAPES_CRC][
                inv_shape_table[RLA_VALID_BLENDSHAPES[idx]]
            ].add_keyframe(KeyFrame(0, value, 0, 0, 0))

        action = load_armature_animation(
            "RLAPose", anim, arma_obj, wm.sssekai_animation_import_offset, None
        )
        apply_action(arma_obj, action, False)
        if pose["shapeDatas"]:
            action = load_keyshape_animation("RLAPose", anim, mesh_obj, 0, None)
            apply_action(mesh_obj.data.shape_keys, action, False)
        bpy.context.scene.frame_end = max(
            bpy.context.scene.frame_end, wm.sssekai_animation_import_offset
        )
        bpy.context.scene.frame_current = wm.sssekai_animation_import_offset
        return {"FINISHED"}


@register_class
class SSSekaiBlenderImportRLAArmatureAnimationOperator(bpy.types.Operator):
    bl_idname = "sssekai.rla_import_armature_animation_op"
    bl_label = T("Import Armature Animation")
    bl_description = T("Import Armature Animation for the selected character")

    def execute(self, context):
        obj = bpy.context.active_object
        assert (
            obj.type == "ARMATURE"
        ), "Please select an armature to import the animation to!"

        wm = context.window_manager
        active_chara = wm.sssekai_rla_active_character
        active_chara_height = wm.sssekai_rla_active_character_height
        chara_segments = list()
        has_boneData = False
        for tick, data in sssekai_global.rla_clip_data.items():
            m_data = data.get("MotionCaptureData", None)
            if m_data:
                for data in m_data:
                    for pose in data["data"]:
                        if pose["id"] == active_chara:
                            chara_segments.append(pose)
                            if pose["pose"]["boneDatas"]:
                                has_boneData = True
        logger.debug(
            "Found %d segments for character %d" % (len(chara_segments), active_chara)
        )
        if not has_boneData:
            logger.warning("No bone data found in the segments.")
        inv_hash_table = obj.data[KEY_BONE_NAME_HASH_TBL]
        inv_hash_table = json.loads(inv_hash_table)
        inv_hash_table = {v: k for k, v in inv_hash_table.items()}

        anim = Animation()
        if has_boneData:
            for bone in RLA_VALID_BONES:
                anim.TransformTracks[TransformType.Rotation][
                    inv_hash_table[bone]
                ] = Track()
        else:
            anim.TransformTracks[TransformType.Rotation][
                inv_hash_table[RLA_ROOT_BONE]
            ] = Track()
        anim.TransformTracks[TransformType.Translation][
            inv_hash_table[RLA_ROOT_BONE]
        ] = Track()
        base_tick = sssekai_global.rla_header["baseTicks"]
        tick_min, tick_max = 1e18, 0
        for segment in chara_segments:
            timestamp = (segment["timestamp"] - base_tick) / RLA_TIME_MAGNITUDE
            tick_min = min(tick_min, timestamp)
            tick_max = max(tick_max, timestamp)
            for idx, boneEuler in enumerate(segment["pose"]["boneDatas"]):
                if RLA_VALID_BONES[idx] != RLA_ROOT_BONE:
                    anim.TransformTracks[TransformType.Rotation][
                        inv_hash_table[RLA_VALID_BONES[idx]]
                    ].add_keyframe(
                        KeyFrame(
                            timestamp,
                            euler3_to_quat_swizzled(*boneEuler),
                            uQuaternion(),
                            uQuaternion(),
                            0,
                        )
                    )
            anim.TransformTracks[TransformType.Translation][
                inv_hash_table[RLA_ROOT_BONE]
            ].add_keyframe(
                KeyFrame(
                    timestamp,
                    uVector3(
                        *(
                            v / active_chara_height
                            for v in segment["pose"]["bodyPosition"]
                        )
                    ),
                    uVector3(),
                    uVector3(),
                    0,
                )
            )
            anim.TransformTracks[TransformType.Rotation][
                inv_hash_table[RLA_ROOT_BONE]
            ].add_keyframe(
                KeyFrame(
                    timestamp,
                    euler3_to_quat_swizzled(*segment["pose"]["bodyRotation"]),
                    uQuaternion(),
                    uQuaternion(),
                    0,
                )
            )
        action = load_armature_animation(
            "RLA",
            anim,
            obj,
            0,
            retrive_action(obj) if wm.sssekai_animation_append_exisiting else None,
        )
        apply_action(obj, action, wm.sssekai_animation_import_use_nla)
        # TODO: Figure out why the frame_end is not being set correctly sometimes
        try:
            bpy.context.scene.frame_end = max(
                bpy.context.scene.frame_end,
                int(tick_max * bpy.context.scene.render.fps),
            )
            bpy.context.scene.frame_current = int(
                tick_min * bpy.context.scene.render.fps
            )
        except Exception as e:
            logger.error(
                "Failed to set frame range: %s (%d-%d)" % (e, tick_min, tick_max)
            )
        return {"FINISHED"}


@register_class
class SSSekaiBlenderImportRLAShapekeyAnimationOperator(bpy.types.Operator):
    bl_idname = "sssekai.rla_import_shapekey_animation_op"
    bl_label = T("Import Shapekey Animation")
    bl_description = T("Import Shapekey Animation for the selected character")

    def execute(self, context):
        obj = bpy.context.active_object
        wm = context.window_manager
        active_chara = wm.sssekai_rla_active_character

        assert (
            obj.type == "ARMATURE"
        ), "Please select an armature to import the animation to!"
        mesh_obj = None
        for child in bpy.context.active_object.children:
            if KEY_SHAPEKEY_NAME_HASH_TBL in child.data:
                mesh_obj = child
                break
        assert (
            mesh_obj
        ), "KEY_SHAPEKEY_NAME_HASH_TBL not found in any of the sub meshes!"

        shapekey_segments = list()
        for tick, data in sssekai_global.rla_clip_data.items():
            m_data = data.get("MotionCaptureData", None)
            if m_data:
                for data in m_data:
                    for pose in data["data"]:
                        if pose["id"] == active_chara:
                            shapeData = pose["pose"]["shapeDatas"]
                            if shapeData:
                                shapekey_segments.append((pose["timestamp"], shapeData))

        inv_hash_table = mesh_obj.data[KEY_SHAPEKEY_NAME_HASH_TBL]
        inv_hash_table = json.loads(inv_hash_table)
        inv_hash_table = {v: k for k, v in inv_hash_table.items()}
        anim = Animation()
        base_tick = sssekai_global.rla_header["baseTicks"]
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
                anim.FloatTracks[BLENDSHAPES_CRC][
                    inv_hash_table[RLA_VALID_BLENDSHAPES[idx]]
                ].add_keyframe(KeyFrame(timestamp, value, 0, 0, 0))
        action = load_keyshape_animation(
            "RLA",
            anim,
            mesh_obj,
            0,
            (
                retrive_action(mesh_obj.data.shape_keys)
                if wm.sssekai_animation_append_exisiting
                else None
            ),
        )
        apply_action(
            mesh_obj.data.shape_keys, action, wm.sssekai_animation_import_use_nla
        )
        try:
            bpy.context.scene.frame_end = max(
                bpy.context.scene.frame_end,
                int(tick_max * bpy.context.scene.render.fps),
            )
            bpy.context.scene.frame_current = int(
                tick_min * bpy.context.scene.render.fps
            )
        except Exception as e:
            logger.error(
                "Failed to set frame range: %s (%d-%d)" % (e, tick_min, tick_max)
            )
        return {"FINISHED"}


@register_class
class SSSekaiBlenderImportRLABatchOperator(bpy.types.Operator):
    bl_idname = "sssekai.rla_import_batch_op"
    bl_label = T("Batch Import")
    bl_description = T(
        """Import RLA clips (Armature/KeyShape) from the selected range for the selected character.
NOTE: NLA tracks will be used regardless of the option specified!"""
    )

    @staticmethod
    def update_selected_rla_asset(entry):
        global sssekai_global
        from sssekai.fmt.rla import read_rla
        from io import BytesIO

        logger.debug("Loading RLA index %s" % entry)
        version = sssekai_global.rla_get_version()
        sssekai_global.rla_clip_data = read_rla(
            BytesIO(sssekai_global.rla_raw_clips[entry]), version, strict=False
        )
        sssekai_global.rla_selected_raw_clip = entry
        min_tick, max_tick = 1e18, 0
        sssekai_global.rla_clip_charas.clear()
        for tick, data in sssekai_global.rla_clip_data.items():
            m_data = data.get("MotionCaptureData", None)
            if m_data:
                min_tick = min(min_tick, tick)
                max_tick = max(max_tick, tick)
                for data in m_data:
                    for pose in data["data"]:
                        sssekai_global.rla_clip_charas.add(pose["id"])
        base_tick = sssekai_global.rla_header["baseTicks"]
        sssekai_global.rla_clip_tick_range = (
            (min_tick - base_tick) / RLA_TIME_MAGNITUDE,
            (max_tick - base_tick) / RLA_TIME_MAGNITUDE,
        )

    def execute(self, context):
        wm = context.window_manager
        rla_range = wm.sssekai_rla_import_range
        entries = list(sssekai_global.rla_raw_clips)
        entries = entries[rla_range[0] : rla_range[1]]
        wm.sssekai_animation_import_use_nla = True
        for entry in entries:
            sssekai_global.rla_selected_raw_clip = entry
            SSSekaiBlenderImportRLABatchOperator.update_selected_rla_asset(entry)
            try:
                bpy.ops.sssekai.rla_import_armature_animation_op()
            except Exception as e:
                logger.error("Failed to import armature animation: %s" % e)
            try:
                bpy.ops.sssekai.rla_import_shapekey_animation_op()
            except Exception as e:
                logger.error("Failed to import shapekey animation: %s" % e)
        return {"FINISHED"}
