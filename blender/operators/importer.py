from bpy.app.translations import pgettext as T
import bpy, bpy.utils.previews, bpy_extras

from sssekai.unity.AnimationClip import (
    TransformType,
    read_animation,
)

from UnityPy.classes import (
    Mesh,
    Material,
    SkinnedMeshRenderer,
    MeshFilter,
    MeshRenderer,
)

from ..core.consts import *
from ..core.utils import encode_asset_id
from ..core.helpers import (
    ensure_sssekai_shader_blend,
    retrive_action,
    apply_action,
)

from ..core.asset import (
    import_eye_material,
    import_eyelight_material,
    import_character_material,
    import_character_face_sdf_material,
    import_mesh,
    import_articulation,
    import_armature,
    import_armature_physics_constraints,
    import_stage_lightmap_material,
)
from ..core.animation import (
    load_armature_animation,
    load_camera_animation,
    load_keyshape_animation,
    import_articulation_animation,
)
from ..core.types import Hierarchy
from .. import register_class, logger
from .. import sssekai_global


@register_class
class SSSekaiBlenderImportOperator(bpy.types.Operator):
    bl_idname = "sssekai.import_op"
    bl_label = T("Import Selected")
    bl_description = T("Import the selected asset from the selected asset bundle")

    def execute(self, context):
        global sssekai_global
        wm = context.window_manager
        ensure_sssekai_shader_blend()
        logger.debug("Loading selected asset: %s" % wm.sssekai_hierarchy_selected)
        texture_cache = dict()
        material_cache = dict()

        def add_material(
            m_Materials: Material,
            obj: bpy.types.Object,
            mesh_data: Mesh,
            default_parser=None,
            **kwargs,
        ):
            for ppmat in m_Materials:
                if ppmat:
                    material: Material = ppmat.read()
                    parser = default_parser
                    # Override parser by name when not using blender's Principled BSDF
                    # These are introduced by v2 meshes
                    texEnvs = dict(material.m_SavedProperties.m_TexEnvs)
                    texFloats = dict(material.m_SavedProperties.m_Floats)
                    if "_eye" in material.m_Name:
                        parser = import_eye_material
                    if "_ehl_" in material.m_Name:
                        parser = import_eyelight_material
                    if "_FaceShadowTex" in texEnvs and texFloats.get("_UseFaceSDF", 0):
                        parser = import_character_face_sdf_material
                    if material.m_Name in material_cache:
                        asset = material_cache[material.m_Name]
                        logger.debug("Reusing Material %s" % material.m_Name)
                    else:
                        asset = parser(
                            material.m_Name,
                            material,
                            texture_cache=texture_cache,
                            **kwargs,
                        )
                        material_cache[material.m_Name] = asset
                        logger.debug("Imported new Material %s" % material.m_Name)
                    obj.data.materials.append(asset)
                    bpy.context.view_layer.objects.active = obj
                    bpy.ops.object.mode_set(mode="OBJECT")
                    mesh = obj.data
                    for index, sub in enumerate(mesh_data.m_SubMeshes):
                        start, count = sub.firstVertex, sub.vertexCount
                        for i in range(start, start + count):
                            mesh.vertices[i].select = True
                        bpy.ops.object.mode_set(mode="EDIT")
                        bpy.context.object.active_material_index = index
                        bpy.ops.object.material_slot_assign()
                        bpy.ops.mesh.select_all(action="DESELECT")
                        bpy.ops.object.mode_set(mode="OBJECT")

        def add_mesh(
            gameObject,
            name: str = None,
            parent_obj=None,
            bone_hash_tbl: dict = None,
            **material_kwargs,
        ):
            name = name or gameObject.m_Name
            if getattr(gameObject, "m_SkinnedMeshRenderer", None):
                logger.debug("Found Skinned Mesh at %s" % gameObject.m_Name)
                mesh_rnd: SkinnedMeshRenderer = gameObject.m_SkinnedMeshRenderer.read()
                bone_order = [
                    b.read().m_GameObject.read().m_Name for b in mesh_rnd.m_Bones
                ]
                if getattr(mesh_rnd, "m_Mesh", None):
                    mesh_data: Mesh = mesh_rnd.m_Mesh.read()
                    mesh, obj = import_mesh(
                        name, mesh_data, True, bone_hash_tbl, bone_order
                    )
                    if parent_obj:
                        obj.parent = parent_obj
                    add_material(
                        mesh_rnd.m_Materials,
                        obj,
                        mesh_data,
                        import_character_material,
                        **material_kwargs,
                    )
                    logger.debug("Imported Skinned Mesh %s" % mesh_data.m_Name)
                    return obj
            elif getattr(gameObject, "m_MeshFilter", None):
                logger.debug("Found Static Mesh at %s" % gameObject.m_Name)
                mesh_filter: MeshFilter = gameObject.m_MeshFilter.read()
                mesh_rnd: MeshRenderer = gameObject.m_MeshRenderer.read()
                mesh_data = mesh_filter.m_Mesh.read()
                mesh, obj = import_mesh(mesh_data.m_Name, mesh_data, False)
                if parent_obj:
                    obj.parent = parent_obj
                add_material(
                    mesh_rnd.m_Materials,
                    obj,
                    mesh_data,
                    import_stage_lightmap_material,
                    **material_kwargs,
                )
                logger.debug("Imported Static Mesh %s" % mesh_data.m_Name)
                return obj

        def add_articulation(articulation: Hierarchy):
            joint_map, parent_object = import_articulation(articulation)
            for bone_name, joint in joint_map.items():
                bone = articulation.nodes[bone_name]
                try:
                    mesh = add_mesh(bone.game_object, bone_name, joint)
                except Exception as e:
                    logger.warning(
                        "Could not import mesh at GameObject %s: %s"
                        % (bone.game_object.m_Name, e)
                    )
            logger.debug("Imported Articulation %s" % articulation.name)

        def add_armature(armature: Hierarchy):
            selected = context.active_object
            armInst, armObj = import_armature(armature)
            # XXX: Assume *all* armatures are for characters
            # -- Rim light setup
            # Reuse rim light if we're importing whilst selecting an object that already has one
            rim_controller = None
            if selected:
                rim_controller = next(
                    filter(
                        lambda o: o.name.startswith("SekaiCharaRimLight"),
                        [selected, *selected.children_recursive],
                    ),
                    None,
                )
                if rim_controller:
                    logger.debug("Reusing Rim Light %s" % rim_controller.name)
            # Otherwise make a new one
            if not rim_controller:
                rim_controller = bpy.data.objects["SekaiCharaRimLight"].copy()
                rim_controller.parent = armObj
                bpy.context.collection.objects.link(rim_controller)
                logger.debug(
                    "Creating new Rim Light controller %s" % rim_controller.name
                )
            for parent, bone, depth in armature.root.children_recursive():
                try:
                    mesh = add_mesh(
                        bone.game_object,
                        bone.name,
                        armObj,
                        armature.global_path_hash_table,
                        rim_light_controller=rim_controller,
                        armature_obj=armObj,
                        head_bone_target="Head",
                    )
                    if mesh:
                        mesh.modifiers.new("Armature", "ARMATURE").object = armObj
                        mesh.parent_type = "BONE"
                        mesh.parent_bone = bone.name
                except Exception as e:
                    logger.warning(
                        "Could not import mesh at GameObject %s: %s"
                        % (bone.game_object.m_Name, e)
                    )
                    raise e
            logger.debug("Imported Armature %s" % armature.name)

        for hierarchy in sssekai_global.hierarchies:
            if (
                encode_asset_id(hierarchy.root.game_object)
                == wm.sssekai_hierarchy_selected
            ):
                if wm.sssekai_armatures_as_articulations:
                    add_articulation(hierarchy)
                else:
                    add_armature(hierarchy)

        for animation in sssekai_global.animations:
            if encode_asset_id(animation) == wm.sssekai_hierarchy_selected:
                logger.debug("Reading AnimationClip: %s" % animation.m_Name)
                logger.debug("Loading...")
                clip = read_animation(animation)
                logger.debug("Importing...")
                # Set the fps. Otherwise keys may get lost!
                bpy.context.scene.render.fps = int(clip.Framerate)
                bpy.context.scene.frame_end = max(
                    bpy.context.scene.frame_end,
                    int(
                        clip.Framerate * clip.Duration
                        + 0.5
                        + wm.sssekai_animation_import_offset
                    ),
                )
                if bpy.context.scene.rigidbody_world:
                    bpy.context.scene.rigidbody_world.point_cache.frame_end = max(
                        bpy.context.scene.rigidbody_world.point_cache.frame_end,
                        bpy.context.scene.frame_end,
                    )
                logger.debug("Duration: %f" % clip.Duration)
                logger.debug("Framerate: %d" % clip.Framerate)
                logger.debug("Frames: %d" % bpy.context.scene.frame_end)
                logger.debug("Blender FPS set to: %d" % bpy.context.scene.render.fps)
                active_type = bpy.context.active_object.type
                if (
                    active_type == "CAMERA"
                    or KEY_CAMERA_RIG in bpy.context.active_object
                ):
                    camera_obj = bpy.context.active_object
                    if KEY_CAMERA_RIG in bpy.context.active_object:
                        camera_obj = camera_obj.children[0]
                    track = clip.TransformTracks[TransformType.Translation]
                    if (
                        CAMERA_TRANS_ROT_CRC_MAIN in track
                        or CAMERA_TRANS_SCALE_EXTRA_CRC_EXTRA in track
                    ):
                        logger.debug("Importing Camera animation %s" % animation.m_Name)
                        action = load_camera_animation(
                            animation.m_Name,
                            clip,
                            camera_obj,
                            wm.sssekai_animation_import_offset,
                            wm.sssekai_animation_import_camera_scaling,
                            wm.sssekai_animation_import_camera_offset,
                            wm.sssekai_animation_import_camera_fov_offset,
                            (
                                retrive_action(camera_obj.parent)
                                if wm.sssekai_animation_append_exisiting
                                else None
                            ),
                        )
                        apply_action(
                            camera_obj.parent,
                            action,
                            wm.sssekai_animation_import_use_nla,
                            wm.sssekai_animation_import_nla_always_new_tracks,
                        )
                        logger.debug("Imported Camera animation %s" % animation.m_Name)
                elif active_type == "ARMATURE":
                    if BLENDSHAPES_CRC in clip.FloatTracks:
                        logger.debug(
                            "Importing Keyshape animation %s" % animation.m_Name
                        )
                        mesh_obj = None
                        for obj in bpy.context.active_object.children:
                            if KEY_SHAPEKEY_NAME_HASH_TBL in obj.data:
                                mesh_obj = obj
                                break
                        assert (
                            mesh_obj
                        ), "KEY_SHAPEKEY_NAME_HASH_TBL not found in any of the sub meshes!"
                        logger.debug("Importing into %s" % mesh_obj.name)
                        action = load_keyshape_animation(
                            animation.m_Name,
                            clip,
                            mesh_obj,
                            wm.sssekai_animation_import_offset,
                            (
                                retrive_action(mesh_obj.data.shape_keys)
                                if wm.sssekai_animation_append_exisiting
                                else None
                            ),
                        )
                        apply_action(
                            mesh_obj.data.shape_keys,
                            action,
                            wm.sssekai_animation_import_use_nla,
                        )
                        logger.debug(
                            "Imported Keyshape animation %s" % animation.m_Name
                        )
                    if (
                        clip.TransformTracks[TransformType.Translation]
                        or clip.TransformTracks[TransformType.Rotation]
                        or clip.TransformTracks[TransformType.EulerRotation]
                        or clip.TransformTracks[TransformType.Scaling]
                    ):
                        logger.debug(
                            "Importing Armature animation %s" % animation.m_Name
                        )
                        action = load_armature_animation(
                            animation.m_Name,
                            clip,
                            bpy.context.active_object,
                            wm.sssekai_animation_import_offset,
                            (
                                retrive_action(bpy.context.active_object)
                                if wm.sssekai_animation_append_exisiting
                                else None
                            ),
                        )
                        apply_action(
                            bpy.context.active_object,
                            action,
                            wm.sssekai_animation_import_use_nla,
                        )
                        logger.debug(
                            "Imported Armature animation %s" % animation.m_Name
                        )
                elif active_type == "EMPTY":
                    if (
                        clip.TransformTracks[TransformType.Translation]
                        or clip.TransformTracks[TransformType.Rotation]
                        or clip.TransformTracks[TransformType.EulerRotation]
                        or clip.TransformTracks[TransformType.Scaling]
                    ):
                        logger.debug(
                            "Importing Articulation animation %s" % animation.m_Name
                        )
                        import_articulation_animation(
                            animation.m_Name,
                            clip,
                            bpy.context.active_object,
                            wm.sssekai_animation_import_offset,
                            not wm.sssekai_animation_append_exisiting,
                        )
                        logger.debug(
                            "Imported Articulation animation %s" % animation.m_Name
                        )

                return {"FINISHED"}
        return {"CANCELLED"}


@register_class
class SSSekaiBlenderImportPhysicsOperator(bpy.types.Operator):
    bl_idname = "sssekai.import_physics_op"
    bl_label = T("Import Physics")
    bl_description = T(
        "Import physics data from the selected asset bundle. NOTE: This operation is irreversible!"
    )

    def execute(self, context):
        global sssekai_global
        assert (
            bpy.context.active_object and bpy.context.active_object.type == "ARMATURE"
        ), "Please select an armature to import physics data to!"
        wm = context.window_manager
        for hierarchy in sssekai_global.hierarchies:
            if (
                encode_asset_id(hierarchy.root.game_object)
                == wm.sssekai_hierarchy_selected
            ):
                bpy.context.scene.frame_current = 0
                import_armature_physics_constraints(
                    bpy.context.active_object, hierarchy
                )
                return {"FINISHED"}
        return {"CANCELLED"}


@register_class
class SSSekaiBlenderPhysicsDisplayOperator(bpy.types.Operator):
    bl_idname = "sssekai.display_physics_op"
    bl_label = T("Show Physics Objects")
    bl_description = T("Show or hide physics objects")

    def execute(self, context):
        assert (
            bpy.context.active_object and bpy.context.active_object.type == "ARMATURE"
        ), "Please select an armature!"
        arma = bpy.context.active_object
        wm = context.window_manager
        display = not wm.sssekai_armature_display_physics
        for child in (child for child in arma.children if "_rigidbody" in child.name):
            child.hide_set(display)
            child.hide_render = display
            for cchild in child.children_recursive:
                cchild.hide_set(display)
                cchild.hide_render = display
        return {"FINISHED"}


@register_class
class SSSekaiBlenderApplyOutlineOperator(bpy.types.Operator):
    bl_idname = "sssekai.apply_outline_op"
    bl_label = T("Add Outline to Selected")
    bl_description = T("Add outline to selected objects")

    def execute(self, context):
        ensure_sssekai_shader_blend()
        outline_material = bpy.data.materials["SekaiShaderOutline"].copy()
        for pa in bpy.context.selected_objects:
            for obj in [pa] + pa.children_recursive:
                if obj.type == "MESH" and obj.hide_get() == False:
                    bpy.context.view_layer.objects.active = obj
                    bpy.ops.object.mode_set(mode="OBJECT")
                    obj.data.materials.append(outline_material)
                    modifier = obj.modifiers.new(name="SekaiShellOutline", type="NODES")
                    modifier.node_group = bpy.data.node_groups[
                        "SekaiShellOutline"
                    ].copy()
                    index = len(obj.data.materials) - 1
                    modifier["Socket_4"] = (
                        index  # XXX: Any other way to assign this attribute?
                    )
        return {"FINISHED"}


@register_class
class SSSekaiBlenderExportAnimationTypeTree(
    bpy.types.Operator, bpy_extras.io_utils.ExportHelper
):
    bl_idname = "sssekai.export_typetree_op"
    bl_label = T("Export Animation TypeTree")
    bl_description = T("Export the TypeTree of the selected animation")

    filename_ext = ".anim"

    filter_glob: bpy.props.StringProperty(default="*.anim;", options={"HIDDEN"})  # type: ignore

    def execute(self, context):
        global sssekai_global
        raise Exception("Not implemented")
