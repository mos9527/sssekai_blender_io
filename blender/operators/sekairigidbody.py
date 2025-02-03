import bpy, math
from bpy.app.translations import pgettext as T
from ..core.types import Hierarchy
from ..core.consts import *
from collections import defaultdict
from .. import register_class, register_wm_props, logger
from .. import sssekai_global
from ..core.helpers import set_obj_bone_parent, create_empty
from ..core.math import blVector, blEuler
from UnityPy.classes import Transform, MonoBehaviour, GameObject
from UnityPy.enums import ClassIDType


def create_capsule_rigidbody_springbone(name: str, radius: float, length: float):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=length)
    obj = bpy.context.object
    obj.name = name + "_CAPSULE_RB"
    # Aligns to Y
    obj.rotation_euler.rotate_axis("Y", math.radians(90))
    obj.location += blVector((length / 2, 0, 0))
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.rigidbody.object_add()
    obj.rigid_body.collision_shape = "CONVEX_HULL"
    obj.rigid_body.type = "ACTIVE"
    obj.rigid_body.kinematic = False
    obj.display_type = "BOUNDS"

    bpy.ops.rigidbody.object_add()
    return obj


def create_sphere_rigidbody(name: str, radius: float):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius)
    obj = bpy.context.object
    obj.name = name + "_SPHERE_RB"
    bpy.ops.rigidbody.object_add()
    obj.rigid_body.collision_shape = "CONVEX_HULL"
    obj.rigid_body.type = "ACTIVE"
    obj.rigid_body.kinematic = False
    obj.display_type = "BOUNDS"
    return obj


def set_no_collision(a, b):
    joint = create_empty(a.name + "_NC", b, DEFAULT_SPRINGBONE_CONSTRAINT_OBJ_SIZE)
    bpy.context.view_layer.objects.active = joint
    bpy.ops.rigidbody.constraint_add(type="GENERIC")
    # Without limits. This acts as a dummy constraint
    # to disable collisions between the two objects
    ct = joint.rigid_body_constraint
    ct.disable_collisions = True
    ct.object1 = a
    ct.object2 = b


def set_spring_constraint(a, b, params):
    """
    NOTE: The translation of the values here aren't 1-to-1 since it's a very different system
    i.e. https://github.com/unity3d-jp/UnityChanSpringBone vs. Blender's in-built Bullet physics
    Best I can do here is to make them visually similar. Use with discretion.
    """
    joint = create_empty(a.name + "_SC", b, DEFAULT_SPRINGBONE_CONSTRAINT_OBJ_SIZE)
    bpy.context.view_layer.objects.active = joint
    bpy.ops.rigidbody.constraint_add(type="GENERIC_SPRING")
    ct = joint.rigid_body_constraint
    ct.use_limit_lin_x = True
    ct.use_limit_lin_y = True
    ct.use_limit_lin_z = True
    # No linear movement
    ct.limit_lin_x_lower = 0
    ct.limit_lin_x_upper = 0
    ct.limit_lin_y_lower = 0
    ct.limit_lin_y_upper = 0
    ct.limit_lin_z_lower = 0
    ct.limit_lin_z_upper = 0
    # Angular movement per physics data
    # Note that the axis are swapped
    ct.use_limit_ang_x = True
    ct.use_limit_ang_y = True
    ct.use_limit_ang_z = True
    ct.limit_ang_x_lower = 0
    ct.limit_ang_x_upper = 0
    ct.limit_ang_y_lower = math.radians(params.zAngleLimits.min)
    ct.limit_ang_y_upper = math.radians(params.zAngleLimits.max)
    ct.limit_ang_z_lower = math.radians(params.yAngleLimits.min)
    ct.limit_ang_z_upper = math.radians(params.yAngleLimits.max)
    # Spring damping effect
    ct.use_spring_ang_x = True
    ct.use_spring_ang_y = True
    ct.use_spring_ang_z = True
    ct.spring_stiffness_ang_x = ct.spring_stiffness_ang_y = (
        ct.spring_stiffness_ang_z
    ) = params.angularStiffness
    ct.spring_damping_x = ct.spring_damping_y = ct.spring_damping_z = params.dragForce
    ct.disable_collisions = True
    ct.object1 = a
    ct.object2 = b


def set_fixed_constraint(a, b):
    joint = create_empty(a.name + "_FC", b, DEFAULT_SPRINGBONE_CONSTRAINT_OBJ_SIZE)
    bpy.context.view_layer.objects.active = joint
    bpy.ops.rigidbody.constraint_add(type="FIXED")
    ct = joint.rigid_body_constraint
    ct.object1 = a
    ct.object2 = b


@register_class
class SSSekaiBlenderHierarchyAddSekaiRigidBodiesOperator(bpy.types.Operator):
    """Add rigid bodies to the selected armature

    Implementation wise, Sekai uses https://github.com/unity3d-jp/UnityChanSpringBone
    for its secondary animations, which has its own rigid body system independent of Unity's
    """

    bl_idname = "sssekai.hierarchy_add_sekai_rigid_bodies"
    bl_label = T("Apply Rigid Bodies")
    bl_description = T(
        "Secondary animations! NOTE: This feature is very experimental and does not guarantee visual correctness. To use, select the armature in the View Layer *AND* the addon's Asset Selector and run this operator."
    )

    def execute(self, context):
        wm = context.window_manager
        active_obj = context.active_object
        assert KEY_HIERARCHY_PATHID in active_obj, "Active object is not a Hierachy"
        path_id = active_obj[KEY_HIERARCHY_PATHID]
        container = wm.sssekai_selected_hierarchy_container
        # fmt: off
        hierarchy = sssekai_global.cotainers[container].hierarchies.get(int(path_id), None)
        assert hierarchy, "Hierarchy Data not found. Please ensure you've selected the container the hierarchy is in"
        armature = active_obj.data
        def find_by_script(game_object: GameObject, name: str):
            for comp in game_object.m_Components:
                if comp.type == ClassIDType.MonoBehaviour:
                    comp = comp.read()
                    comp: MonoBehaviour
                    script = comp.m_Script.read()
                    if script.m_Name == name:
                        yield comp
        def swizzle_data(comp: MonoBehaviour):
            obj = comp.m_GameObject.read()
            script = comp.m_Script.read()
            return (obj.m_Name, obj.m_Transform.m_PathID, script.m_Name, comp, obj)
        sphereColliders, capsuleColliders, panelColliders = list(), list(), list()
        spring_mananger = None
        for node in hierarchy.nodes.values():
            game_object = node.game_object
            spring_mananger = spring_mananger or next(
                find_by_script(game_object, "SpringManager"), None
            )
            sphereColliders += list(find_by_script(game_object, "SpringSphereCollider"))
            capsuleColliders += list(find_by_script(game_object, "SpringCapsuleCollider"))
            panelColliders += list(find_by_script(game_object, "SpringPanelCollider"))
        # Graph setup
        assert spring_mananger
        nodeDict = {node.name: node for node in hierarchy.nodes.values()}
        nodeDepths = {node.name: depth for pa,node,depth in hierarchy.root.children_recursive()}
        springBones = [
            swizzle_data(bone.read()) for bone in spring_mananger.springBones
        ]
        springBoneDict = {name: (name,*data) for name, *data in springBones}
        springNodeNames = set()
        springPivotNames = set()
        springPivotDict = dict()
        springPivotDictT = dict()
        for name, path_id, script_name, bone, obj in springBones:
            pivot = bone.pivotNode.read()
            pivot_obj = pivot.m_GameObject.read()
            springPivotNames.add(pivot_obj.m_Name)
            springNodeNames.add(pivot_obj.m_Name)
            springNodeNames.add(obj.m_Name)
            springPivotDict[obj.m_Name] = pivot_obj.m_Name
            springPivotDictT[pivot_obj.m_Name] = obj.m_Name
        springRootNames = set()        
        for name, path_id, script_name, bone, obj in springBones:
            for obj in [obj, bone.pivotNode.read().m_GameObject.read()]:
                pa = obj.m_Transform.read().m_Father.read()
                pa_obj = pa.m_GameObject.read()
                if pa_obj.m_Name not in springNodeNames:
                    springRootNames.add(obj.m_Name)
        springNodeParents = dict()
        # DSU
        for root in springRootNames:
            node = nodeDict[root]
            for parent, child, depth in node.children_recursive():
                springNodeParents[child.name] = root
        # https://github.com/unity3d-jp/UnityChanSpringBone/tree/9415071549aee47c094657d9ef5af239b96c201f/Runtime/Colliders
        sphereColliders = [swizzle_data(collider) for collider in sphereColliders]
        capsuleColliders = [swizzle_data(collider) for collider in capsuleColliders]
        panelColliders = [swizzle_data(collider) for collider in panelColliders]
        bpy.context.view_layer.objects.active = active_obj
        # Reset the pose
        bpy.ops.object.mode_set(mode="POSE")
        Position_world = active_obj.pose.bones.get("Position").matrix
        bpy.ops.pose.select_all(action="SELECT")
        bpy.ops.pose.transforms_clear()
        bpy.ops.pose.select_all(action="DESELECT")
        bpy.ops.object.mode_set(mode="EDIT")
        # Attach passive rigidbodies to the bones
        for name, path_id, script_name, bone, obj in sphereColliders:
            next_sphere_rb = create_sphere_rigidbody(name + "_SPHERE", DEFAULT_SPRINGBONE_SIZE)
            set_obj_bone_parent(next_sphere_rb, name, active_obj)
            next_sphere_rb.rigid_body.kinematic = True
            next_sphere_rb.rigid_body.type = "PASSIVE"
        for name, path_id, script_name, bone, obj in capsuleColliders:
            next_capsule_rb = create_capsule_rigidbody_springbone(name + "_CAPSULE", DEFAULT_SPRINGBONE_SIZE, DEFAULT_SPRINGBONE_SIZE)
            set_obj_bone_parent(next_capsule_rb, name, active_obj)
            next_capsule_rb.rigid_body.kinematic = True
            next_capsule_rb.rigid_body.type = "PASSIVE"
        for name, path_id, script_name, bone, obj in panelColliders:
            pass # XXX: Not implemented
        # Make rigidbody colliders for the spring bones as capsules
        springBoneRbs = defaultdict(list)
        springBoneRbsFlatten = dict()
        for spring in springBoneDict:
            spring_name, spring_path_id, spring_script_name, spring_params, spring_obj = springBoneDict[spring]
            bpy.context.view_layer.objects.active = active_obj
            bpy.ops.object.mode_set(mode="EDIT")
            spring_ebone = armature.edit_bones.get(spring_name)
            spring_length = [(spring_ebone.head - ch.head).magnitude for ch in spring_ebone.children]
            spring_length = min(spring_length) if spring_length else DEFAULT_SPRINGBONE_SIZE
            next_spring_rb = create_capsule_rigidbody_springbone(spring_name + "_SPRING", spring_params.radius * DEFAULT_SPRINGBONE_RADIUS_SCALE,spring_length)
            set_obj_bone_parent(next_spring_rb, spring_name, active_obj)
            springBoneRbs[springNodeParents[spring_name]].append((spring_name,next_spring_rb))
            springBoneRbsFlatten[spring_name] = next_spring_rb
        for root, rbs in springBoneRbs.items():
            rbs = sorted(rbs, key=lambda x: nodeDepths[x[0]])
        # Detach the pivot bones and keep the transform
        bpy.context.view_layer.objects.active = active_obj
        bpy.ops.object.mode_set(mode="EDIT")
        for pivot_name in springNodeNames:
            # Keep the root one since it's the one that's actually parented to the armature
            if pivot_name not in springRootNames:
                armature.edit_bones.get(pivot_name).parent = None
        # For each subtree of spring bones, disable self-collision
        for root,rbs in springBoneRbs.items():
            for i,(name,rb) in enumerate(rbs):
                rb : bpy.types.Object
                rb.rigid_body.collision_collections[0] = i & 1
        # Connect these with rigidbody constraints
        # Pivot*Spring ~ Pivot*Spring ~ ...
        # [*] fixed [~] spring
        # Create rigidbodies on the pivot nodes
        pivotRbs = dict()
        for pivot_name in springPivotNames:
            pivot_rb = create_sphere_rigidbody(pivot_name + "_PIVOT", DEFAULT_SPRINGBONE_PIVOT_SIZE)
            set_obj_bone_parent(pivot_rb, pivot_name, active_obj)
            pivotRbs[pivot_name] = pivot_rb
            # Connect the root pivot to the first spring
            spring = springPivotDictT[pivot_name]
            spring_name, spring_path_id, spring_script_name, spring_params, spring_obj = springBoneDict[spring]
            spring_rb = springBoneRbsFlatten[spring]
            set_fixed_constraint(pivot_rb, spring_rb)
        # Make the pivot nodes kinematic
        for root in springRootNames:
            pivot_rb = pivotRbs[root]
            pivot_rb.rigid_body.kinematic = True
            pivot_rb.rigid_body.type = "PASSIVE"
        bpy.context.view_layer.objects.active = active_obj
        bpy.ops.object.mode_set(mode="EDIT")
        for root,rbs in springBoneRbs.items():
            for i in range(len(rbs)-1):
                spring, spring_rb = rbs[i]
                next_spring, next_spring_rb = rbs[i+1]
                next_pivot = springPivotDict[next_spring]
                next_pivot_rb = pivotRbs[next_pivot]
                spring_name, spring_path_id, spring_script_name, spring_params, spring_obj = springBoneDict[spring]
                set_spring_constraint(spring_rb, next_pivot_rb, spring_params)
        # Reparent the rigidbodies to the armature's Position bone
        bpy.context.view_layer.update()
        def set_parent_keep_transform(obj : bpy.types.Object,  bone : str, parent: bpy.types.Object):
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.mode_set(mode="OBJECT")
            world = obj.matrix_world
            obj.parent = parent
            obj.parent_type = "BONE"
            obj.parent_bone = bone  
            obj.matrix_parent_inverse = Position_world.inverted() @ world
        for pivot, pivot_rb in pivotRbs.items():
            if pivot not in springRootNames:
                set_parent_keep_transform(pivot_rb, "Position", active_obj)
        for spring, spring_rb in springBoneRbsFlatten.items():
            set_parent_keep_transform(spring_rb, "Position", active_obj)
        # Apply the poses of the rigidbodies back to the pose bones
        bpy.context.view_layer.update()
        bpy.context.view_layer.objects.active = active_obj
        bpy.ops.object.mode_set(mode="POSE")
        for pivot, pivot_rb in pivotRbs.items():
            if pivot not in springRootNames:
                pbone = active_obj.pose.bones.get(pivot)
                ct = pbone.constraints.new("COPY_TRANSFORMS")
                ct.target = pivot_rb
        for spring, spring_rb in springBoneRbsFlatten.items():
            pbone = active_obj.pose.bones.get(spring)
            ct = pbone.constraints.new("COPY_TRANSFORMS")
            ct.target = spring_rb
        # fmt: on
        return {"FINISHED"}
