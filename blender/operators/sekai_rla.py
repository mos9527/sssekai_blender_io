from bpy.app.translations import pgettext as T
import bpy, bpy.utils.previews
import json

from sssekai.unity.AnimationClip import (
    AnimationHelper,
    KeyframeHelper,
    kBindTransformRotation,
    kBindTransformPosition,
)
from UnityPy.classes import GenericBinding

from ..core.consts import *
from ..core.helpers import (
    apply_action,
)
from ..core.math import uVector3, uQuaternion
from ..core.math import euler3_to_quat_swizzled
from .. import register_class, logger
from ..core.animation import (
    load_armature_animation,
    load_sekai_keyshape_animation,
)
from ..core.helpers import armature_editbone_children_recursive
from .. import sssekai_global


def binding_of(path: int, attribute: int):
    return GenericBinding(attribute, 0, 0, path, None)


@register_class
class SSSekaiBlenderImportRLASegmentOperator(bpy.types.Operator):
    bl_idname = "sssekai.rla_import_segment_op"
    bl_label = T("Import RLA Segment")
    bl_description = T("Import RLA Segment for the selected character")

    def execute(self, context):
        wm = context.window_manager
        active_object = bpy.context.active_object
        assert (
            active_object and KEY_SEKAI_CHARACTER_ROOT in active_object
        ), "Please select an Character Root to import the animation to!"
        (
            wm.sssekai_animation_import_use_nla,
            wm.sssekai_animation_import_nla_always_new_track,
        ) = (True, False)
        body_obj = active_object.get(KEY_SEKAI_CHARACTER_BODY_OBJ, None)
        face_obj = active_object.get(KEY_SEKAI_CHARACTER_FACE_OBJ, None)

        active_chara = wm.sssekai_rla_active_character
        active_chara_height = active_object[KEY_SEKAI_CHARACTER_HEIGHT]

        chara_segments = list()
        for tick, data in sssekai_global.rla_clip_data:
            if data["type"] == "MotionCaptureData":
                for chunk in data["data"]:
                    if chunk["id"] == active_chara:
                        chara_segments.append((chunk["timestamp"], chunk["pose"]))
        chara_segments = sorted(chara_segments, key=lambda x: x[0])
        if not chara_segments:
            logger.warning(
                "Skipping empty segment %s" % sssekai_global.rla_selected_raw_clip
            )
            return {"FINISHED"}
        base_tick = sssekai_global.rla_header["baseTicks"]
        tick_min, tick_max = 1e10, 0
        logger.debug("Transport type: %s" % wm.sssekai_rla_transport_type)
        rla_transport_bones, rla_transport_shapes = SEKAI_RLA_TRANSPORT[
            wm.sssekai_rla_transport_type
        ]
        if body_obj:
            bpy.context.view_layer.objects.active = body_obj
            bpy.ops.object.mode_set(mode="EDIT")
            tos_crc_table = dict()
            for parent, child, depth in armature_editbone_children_recursive(
                body_obj.data
            ):
                if not parent:
                    tos_crc_table[child.name] = child.name
                else:
                    tos_crc_table[child.name] = (
                        tos_crc_table[parent.name] + "/" + child.name
                    )
            tos_crc_table = {crc32(v): k for k, v in tos_crc_table.items()}
            inv_tos_crc_table = {v: k for k, v in tos_crc_table.items()}
            bpy.ops.object.mode_set(mode="OBJECT")
            anim = AnimationHelper(sssekai_global.rla_selected_raw_clip + "_MOT", 0, 0)
            # fmt: off
            for tick, pose in chara_segments:                
                frame = (tick - base_tick) / SEKAI_RLA_TIME_MAGNITUDE
                tick_min = min(tick_min, frame)
                tick_max = max(tick_max, frame)
                if len(pose["boneDatas"]) != len(rla_transport_bones):
                    logger.warning("Invalid bone count: %d. Wrong transport type?" % len(pose["boneDatas"]))
                    continue
                for i, bone_euler in enumerate(pose["boneDatas"]):
                    if i == 0: continue
                    # Eulers
                    bone_path_crc = inv_tos_crc_table.get(rla_transport_bones[i])
                    curve = anim.get_curve(binding_of(bone_path_crc,kBindTransformRotation))
                    curve.Data.append(KeyframeHelper(
                        frame, 0, euler3_to_quat_swizzled(*bone_euler), isDense=True, 
                        inSlope=uQuaternion(0,0,0,1), outSlope=uQuaternion(0,0,0,1)
                    ))
                # Root loc/rot
                curve = anim.get_curve(binding_of(inv_tos_crc_table[rla_transport_bones[0]],kBindTransformPosition))
                curve.Data.append(KeyframeHelper(frame, 0, uVector3(*(
                    v / active_chara_height for v in pose["bodyPosition"]
                )), isDense=True, inSlope=uVector3(0,0,0), outSlope=uVector3(0,0,0)))
                curve = anim.get_curve(binding_of(inv_tos_crc_table[rla_transport_bones[0]],kBindTransformRotation))
                curve.Data.append(KeyframeHelper(
                    frame, 0, euler3_to_quat_swizzled(*pose["bodyRotation"]), isDense=True,
                    inSlope=uQuaternion(0,0,0,1), outSlope=uQuaternion(0,0,0,1)
                ))
            # Always use NLAs
            action = load_armature_animation(anim.Name, anim, body_obj, tos_crc_table, True)
            try:
                logger.info("Armature Frame range: %d - %d" % (tick_min, tick_max))
                apply_action(body_obj, action, wm.sssekai_animation_import_use_nla, wm.sssekai_animation_import_nla_always_new_track)
            except Exception as e:
                logger.error("Failed to Armature action: %s" % e)
            # fmt: on
        else:
            logger.warning("No body object found, skipping body animation")
        if face_obj:
            morphs = list(
                filter(
                    lambda obj: obj.type == "MESH"
                    and KEY_SHAPEKEY_HASH_TABEL in obj.data,
                    face_obj.children_recursive,
                )
            )
            try:
                assert morphs, "No meshes with shapekey found"
                assert (
                    len(morphs) == 1
                ), "Multiple meshes with shapekeys found. Please keep only one"
                morph = morphs[0]
                morph_crc_table = json.loads(morph.data[KEY_SHAPEKEY_HASH_TABEL])
                inv_mod_crc_table = {v: k for k, v in morph_crc_table.items()}
                # fmt: off
                anim = AnimationHelper(sssekai_global.rla_selected_raw_clip + "_FACE", 0, 0)
                for tick, pose in chara_segments:                
                    frame = (tick - base_tick) / SEKAI_RLA_TIME_MAGNITUDE
                    tick_min = min(tick_min, frame)
                    tick_max = max(tick_max, frame)
                    if len(pose["shapeDatas"]) != len(rla_transport_shapes):
                        logger.warning("Invalid shape count: %d. Wrong transport type?" % len(pose["shapeDatas"]))
                        continue
                    for i, shapeValue in enumerate(pose["shapeDatas"]):
                        shape_name = rla_transport_shapes[i]
                        curve = anim.get_curve(binding_of(SEKAI_BLENDSHAPE_CRC, inv_mod_crc_table[shape_name]))
                        curve.Data.append(KeyframeHelper(frame,0,shapeValue,isDense=True,inSlope=0,outSlope=0))
                # Always use NLAs
                action = load_sekai_keyshape_animation(anim.Name, anim, morph_crc_table, True)
                try:
                    logger.info("Face Frame range: %d - %d" % (tick_min, tick_max))
                    apply_action(morph.data.shape_keys, action, wm.sssekai_animation_import_use_nla, wm.sssekai_animation_import_nla_always_new_track)
                except Exception as e:
                    logger.error("Failed to ShapeKey action: %s" % e)
            except Exception as e:
                logger.error("Failed to bind face mesh: %s" % e)
            # fmt: on
        else:
            logger.warning("No face object found, skipping face animation")
        if tick_max > 0:
            logger.debug("Setting frame range to %d - %d" % (tick_min, tick_max))
            try:
                bpy.context.scene.frame_end = max(
                    bpy.context.scene.frame_end,
                    int(tick_max * bpy.context.scene.render.fps),
                )
                bpy.context.scene.frame_current = int(
                    tick_min * bpy.context.scene.render.fps
                )
                if bpy.context.scene.rigidbody_world:
                    bpy.context.scene.rigidbody_world.point_cache.frame_end = max(
                        bpy.context.scene.rigidbody_world.point_cache.frame_end,
                        bpy.context.scene.frame_end,
                    )
            except Exception as e:
                logger.error("Failed to set frame range: %s" % e)
        bpy.context.view_layer.objects.active = active_object
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.sssekai.update_character_controller_body_position_driver_op()
        return {"FINISHED"}


@register_class
class SSSekaiBlenderImportRLABatchOperator(bpy.types.Operator):
    bl_idname = "sssekai.rla_import_batch_op"
    bl_label = T("Import RLA Segments By Range")
    bl_description = T(
        """Import RLA clips (Armature/KeyShape) from the selected range for the selected character.
NOTE: NLA tracks will be used regardless of the option specified!"""
    )

    @staticmethod
    def update_selected_rla_asset(entry):
        global sssekai_global
        from sssekai.fmt.rla import read_archive_rla_frames
        from io import BytesIO

        logger.debug("Loading RLA index %s" % entry)
        version = sssekai_global.rla_get_version()
        try:
            sssekai_global.rla_clip_data = list(
                read_archive_rla_frames(
                    BytesIO(sssekai_global.rla_raw_clips[entry]), version, strict=True
                )
            )
        except Exception as e:
            logger.error("Failed to load RLA bundle: %s" % e)
            return {"CANCELLED"}
        sssekai_global.rla_selected_raw_clip = entry
        min_tick, max_tick = 1e10, 0
        sssekai_global.rla_clip_charas.clear()
        for tick, data in sssekai_global.rla_clip_data:
            if data["type"] == "MotionCaptureData":
                for chunk in data["data"]:
                    min_tick = min(min_tick, chunk["timestamp"])
                    max_tick = max(max_tick, chunk["timestamp"])
                    sssekai_global.rla_clip_charas.add(chunk["id"])
        base_tick = sssekai_global.rla_header["baseTicks"]
        sssekai_global.rla_clip_tick_range = (
            (min_tick - base_tick) / SEKAI_RLA_TIME_MAGNITUDE,
            (max_tick - base_tick) / SEKAI_RLA_TIME_MAGNITUDE,
        )

    def execute(self, context):
        wm = context.window_manager
        rla_range = wm.sssekai_rla_import_range
        entries = list(sssekai_global.rla_raw_clips)
        entries = entries[rla_range[0] : rla_range[1] + 1]
        wm.sssekai_animation_import_use_nla = True
        for entry in entries:
            sssekai_global.rla_selected_raw_clip = entry
            SSSekaiBlenderImportRLABatchOperator.update_selected_rla_asset(entry)
            try:
                bpy.ops.sssekai.rla_import_segment_op()
            except Exception as e:
                logger.error("Failed to import segment: %s" % e)
        return {"FINISHED"}
