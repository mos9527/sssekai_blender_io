import bpy
from .utils import get_addon_relative_path
from . import logger


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
