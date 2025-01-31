import bpy
from typing import Dict
from .math import blMatrix, blVector
from .utils import get_addon_relative_path
from .consts import DEFAULT_BONE_SIZE
from .. import logger


def ensure_sssekai_shader_blend():
    SHADER_BLEND_FILE = get_addon_relative_path("assets", "SekaiShaderStandalone.blend")
    if not "SSSekaiWasHere" in bpy.data.materials:
        logger.warning("SekaiShader not loaded. Importing from %s" % SHADER_BLEND_FILE)
        with bpy.data.libraries.load(SHADER_BLEND_FILE, link=False) as (
            data_from,
            data_to,
        ):
            data_to.materials = data_from.materials
            data_to.node_groups = data_from.node_groups
            data_to.collections = data_from.collections
            logger.debug("Loaded shader blend file.")
        bpy.context.scene.collection.children.link(
            bpy.data.collections["SekaiShaderBase"]
        )


rgba_to_rgb_tuple = lambda col: (col.r, col.g, col.b, col.a)


def create_empty(name: str, parent=None):
    joint = bpy.data.objects.new(name, None)
    joint.empty_display_size = 0.1
    joint.empty_display_type = "ARROWS"
    joint.parent = parent
    bpy.context.collection.objects.link(joint)
    return joint


def auto_connect_shader_nodes_by_name(node_tree, lhs, rhs):
    """Automatically connects nodes by name

    Connections are made between the intersection of the output and input names.
    No checks are made for type compatibility.
    """
    outputs = {k.name: i for i, k in enumerate(lhs.outputs)}
    inputs = {k.name: i for i, k in enumerate(rhs.inputs)}
    for output in outputs:
        if output in inputs:
            node_tree.links.new(
                lhs.outputs[outputs[output]], rhs.inputs[inputs[output]]
            )


def auto_setup_shader_node_driver(node_group, target_obj, target_bone=None):
    """Automatically sets up the driver for the node group

    This connects node group inputs *by name* to `target_obj`'s properties.
    The function makes the following assumptions:
        * `VECTOR_ROTATE` nodes are connected to the object's GLOBAL (World Space) euler rotation
        * Otherwise, the nodes are connected by name to the object's *Custom Properties*

    Bones are supported by setting the `target_bone` parameter to the bone name.
    `target_obj` in this case must be an Armature object.
    """

    def fcurves_for_input(node, input_path):
        node.inputs[input_path].driver_remove("default_value")
        return node.inputs[input_path].driver_add("default_value")

    def fcurves_for_output(node, input_path):
        node.outputs[input_path].driver_remove("default_value")
        return node.outputs[input_path].driver_add("default_value")

    def drivers_setup(fcurves, paths, as_transform=False):
        for fcurve, path in zip(fcurves, paths):
            fcurve: bpy.types.FCurve
            driver = fcurve.driver
            driver.type = "SCRIPTED"
            driver.expression = "var"
            var = driver.variables.new()
            var.name = "var"
            var.targets[0].id = target_obj
            var.targets[0].data_path = path
            if as_transform:
                var.type = "TRANSFORMS"
                if target_bone:
                    var.targets[0].bone_target = target_bone
                var.targets[0].transform_space = "WORLD_SPACE"
                var.targets[0].transform_type = path

    for node in node_group.nodes:
        if node.type == "VECTOR_ROTATE":
            fcurves = fcurves_for_input(node, "Rotation")
            drivers_setup(
                fcurves,
                ["ROT_X", "ROT_Y", "ROT_Z"],
                as_transform=True,
            )
        elif node.name in target_obj:
            if node.type == "VECT_MATH":
                fcurves = fcurves_for_input(node, 0)
                drivers_setup(
                    fcurves,
                    [
                        f'["{node.name}"][0]',
                        f'["{node.name}"][1]',
                        f'["{node.name}"][2]',
                    ],
                )
            if node.type == "VALUE":
                fcurves = fcurves_for_output(node, 0)
                drivers_setup([fcurves], [f'["{node.name}"]'])
    pass


def time_to_frame(time: float, frame_offset: int = 0):
    return time * bpy.context.scene.render.fps + frame_offset


def retrive_action(object: bpy.types.Object):
    """Retrieves the action bound to an object, if any"""
    return object.animation_data.action if object.animation_data else None


def ensure_action(object: bpy.types.Object, name: str, always_create_new: bool):
    """Creates (or retrieves) an action for an object, whilst ensuring that the action is bound to animation_data"""
    existing_action = retrive_action(object)
    if always_create_new or not existing_action:
        object.animation_data_clear()
        object.animation_data_create()
        action = bpy.data.actions.new(name)
        object.animation_data.action = action
        return action
    else:
        return object.animation_data.action


def create_action(name: str):
    """Creates a new action"""
    action = bpy.data.actions.new(name)
    return action


def apply_action(
    object: bpy.types.Object,
    action: bpy.types.Action,
    use_nla: bool = False,
    nla_always_new_track: bool = False,
):
    """Applies an action to an object

    Args:

        object (bpy.types.Object): target object
        action (bpy.types.Action): action to apply
        use_nla (bool): whether to use NLA tracks
        nla_always_new_track (bool): whether to always create a new track. otherwise, the NLA clip (is use_nla) will be appended to the last track
    """
    if not object.animation_data:
        object.animation_data_create()
    if not use_nla:
        object.animation_data_clear()
        object.animation_data_create()
        object.animation_data.action = action
    else:
        nla_tracks = object.animation_data.nla_tracks
        if not len(nla_tracks):
            object.animation_data_clear()
            object.animation_data_create()
            nla_tracks = object.animation_data.nla_tracks
            nla_tracks.new()
            nla_always_new_track = False
        if nla_always_new_track:
            nla_track = nla_tracks.new()
        else:
            nla_track = nla_tracks[-1]  # Use the last track if available
        nla_track.name = action.name
        frame_begin = max(0, action.frame_range[0])
        strip = nla_track.strips.new(action.name, int(frame_begin), action)
        strip.action_frame_start = max(0, frame_begin)


def editbone_children_recursive(root: bpy.types.EditBone):
    """Yields a tuple of (parent, child, depth) for children of a edit bone.

    The tree is traversed in depth-first order and from top to bottom.
    """

    def dfs(bone: bpy.types.EditBone, parent=None, depth=0):
        yield parent, bone, depth
        for child in bone.children:
            yield from dfs(child, bone, depth + 1)

    yield from dfs(root)


def armature_editbone_children_recursive(arma: bpy.types.Armature):
    """Yields a tuple of (parent, child, depth) for edit bones in an Armature.

    Armature MUST be in Edit Mode.

    The tree is traversed in depth-first order and from top to bottom.
    """

    for ebone in arma.edit_bones:
        if ebone.parent is None:
            yield from editbone_children_recursive(ebone)


def apply_pose_matrix(
    dest: bpy.types.Object,
    pose_matrix: Dict[str, blMatrix],
    edit_mode: bool = False,
):
    """Applies a pose matrix to an armature object

    Args:
        dest (bpy.types.Object): target armature object
        pose_matrix (Dict[str, blMatrix]): bone name to pose TRS matrix in Armature space
        edit_mode (bool, optional): apply in Edit Mode. otherwise done in Pose Mode. this resets the pose-space transforms. Defaults to False.
    """
    bpy.context.view_layer.objects.active = dest
    bpy.ops.object.mode_set(mode="EDIT")
    edit_space = {bone.name: bone.matrix for bone in dest.data.edit_bones}
    if not edit_mode:
        bpy.ops.object.mode_set(mode="POSE")
        bpy.ops.pose.select_all(action="SELECT")
        bpy.ops.pose.transforms_clear()
        bpy.ops.pose.select_all(action="DESELECT")
    for bone_name, M_final in pose_matrix.items():
        if edit_mode:
            ebone = dest.data.edit_bones.get(bone_name)
            ebone.head = M_final @ blVector((0, 0, 0))
            ebone.tail = M_final @ blVector((0, 1, 0))
            ebone.length = DEFAULT_BONE_SIZE
            ebone.align_roll(M_final @ blVector((0, 0, 1)) - ebone.head)
        else:
            pbone = dest.pose.bones.get(bone_name)
            M_edit = edit_space[pbone.name]
            M_parent = (
                edit_space[pbone.parent.name] if pbone.parent else blMatrix.Identity(4)
            )
            M_local = M_parent.inverted() @ M_edit
            M_final_parent = pose_matrix.get(pbone.parent.name, blMatrix.Identity(4))
            M_final_local = M_final_parent.inverted() @ M_final
            # Apply pose specified in the hierarchy
            # PoseBone = EditBone^-1 * Final
            # Also applies to local space
            M_pose = M_local.inverted() @ M_final_local
            pbone.matrix_basis = M_pose
    bpy.ops.object.mode_set(mode="POSE")
