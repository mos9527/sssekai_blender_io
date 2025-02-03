from tests import *

from UnityPy.classes import Transform, MonoBehaviour, GameObject
from UnityPy.enums import ClassIDType


def test_rigidbody():
    PATH = sample_file_path("mesh", "face_31_0001")
    with open(PATH, "rb") as f:
        env = load_assetbundle(f)
        spring_mananger = None

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
        for obj in filter(lambda obj: obj.type == ClassIDType.Transform, env.objects):
            obj = obj.read()
            obj: Transform
            game_object = obj.m_GameObject.read()
            spring_mananger = spring_mananger or next(
                find_by_script(game_object, "SpringManager"), None
            )
            sphereColliders += list(find_by_script(game_object, "SpringSphereCollider"))
            capsuleColliders += list(
                find_by_script(game_object, "SpringCapsuleCollider")
            )
            panelColliders += list(find_by_script(game_object, "SpringPanelCollider"))

        assert spring_mananger
        springBones = [
            swizzle_data(bone.read()) for bone in spring_mananger.springBones
        ]
        springBoneDict = {name: data for name, *data in springBones}
        springNodeNames = set()
        for name, path_id, script_name, bone, obj in springBones:
            pivot = bone.pivotNode.read()
            pivot_obj = pivot.m_GameObject.read()
            springNodeNames.add(pivot_obj.m_Name)
            springNodeNames.add(obj.m_Name)
        springRootNames = set()
        for name, path_id, script_name, bone, obj in springBones:
            for obj in [obj, bone.pivotNode.read().m_GameObject.read()]:
                pa = obj.m_Transform.read().m_Father.read()
                pa_obj = pa.m_GameObject.read()
                if pa_obj.m_Name not in springNodeNames:
                    springRootNames.add(obj.m_Name)
        print(springRootNames)
        # https://github.com/unity3d-jp/UnityChanSpringBone/tree/9415071549aee47c094657d9ef5af239b96c201f/Runtime/Colliders
        sphereColliders = [swizzle_data(collider) for collider in sphereColliders]
        capsuleColliders = [swizzle_data(collider) for collider in capsuleColliders]
        panelColliders = [swizzle_data(collider) for collider in panelColliders]
        pass


if __name__ == "__main__":
    test_rigidbody()
