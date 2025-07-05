import bpy
from ..core.types import Hierarchy
from ..core.math import blVector, blEuler
from .. import register_class, register_wm_props, logger
from .. import sssekai_global
from .utils import crc32
from ..core.helpers import auto_connect_tex_vaule_nodes_by_name


def set_generic_material_nodegroup(
    mat: bpy.types.Material, mode: str, custom_node_group: str = ""
):
    if mode == "SKIP":
        return
    for node in mat.node_tree.nodes:
        if node.name.startswith("Sekai"):
            mat.node_tree.nodes.remove(node)

    def set_nodegroup(node_group_name: str):
        node_group = mat.node_tree.nodes.new("ShaderNodeGroup")
        node_group.name = node_group_name
        node_group.node_tree = bpy.data.node_groups.get(node_group_name)
        auto_connect_tex_vaule_nodes_by_name(mat.node_tree, node_group)
        # To output
        output_node = mat.node_tree.nodes.get("Material Output")
        mat.node_tree.links.new(node_group.outputs[0], output_node.inputs[0])

    match mode:
        case "UNITY_PBR_STANDARD":
            node_group = set_nodegroup("SekaiGenericUnityPBRStandard")
        case "BASIC":
            node_group = set_nodegroup("SekaiGenericBasic")
        case "BASIC_TOON":
            node_group = set_nodegroup("SekaiGenericBasicToon")
        case "EMISSIVE":
            node_group = set_nodegroup("SekaiGenericEmissive")
        case "COLORADD":
            node_group = set_nodegroup("SekaiGenericColorAdd")
        case "CUSTOM":
            node_group = set_nodegroup(custom_node_group)
    return node_group


@register_class
class SSSekaiGenericMaterialSetModeOperator(bpy.types.Operator):
    bl_idname = "sssekai.generic_material_set_mode"
    bl_label = "Set Generic Material Mode"
    bl_description = "Set Generic Material Mode"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        active_object = bpy.context.active_object
        wm = bpy.context.window_manager
        for obj in list([active_object] + active_object.children_recursive):
            obj: bpy.types.Object
            if obj.type == "MESH":
                for mat in obj.data.materials:
                    set_generic_material_nodegroup(
                        mat,
                        wm.sssekai_generic_material_import_mode,
                        wm.sssekai_generic_material_import_mode_custom_group,
                    )
        return {"FINISHED"}
