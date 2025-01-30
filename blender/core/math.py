import math

from mathutils import (
    Matrix as blMatrix,
    Quaternion as blQuaternion,
    Vector as blVector,
    Euler as blEuler,
)
from UnityPy.classes.math import (
    Vector3f as uVector3,
    Quaternionf as uQuaternion,
    Matrix4x4f as uMatrix4x4,
)


# Coordinate System | Forward |  Up  |  Left
# Unity:   LH, Y Up |   Z     |   Y  |  -X
# Blender: RH, Z Up |  -Y     |   Z  |   X
UNITY_TO_BLENDER = blMatrix(((-1, 0, 0, 0), (0, 0, 1, 0), (0, -1, 0, 0), (0, 0, 0, 1)))


def swizzle_matrix(mat: uMatrix4x4):
    blmat = blMatrix(
        (
            (mat.e00, mat.e01, mat.e02, mat.e03),
            (mat.e10, mat.e11, mat.e12, mat.e13),
            (mat.e20, mat.e21, mat.e22, mat.e23),
            (mat.e30, mat.e31, mat.e32, mat.e33),
        )
    )
    return blmat


def swizzle_vector_scale(vec: uVector3):
    return blVector((vec.x, vec.z, vec.y))


def swizzle_vector3(X, Y, Z):
    return blVector((-X, -Z, Y))


def swizzle_vector(vec: uVector3):
    return swizzle_vector3(vec.x, vec.y, vec.z)


def swizzle_euler3(X, Y, Z):
    return blEuler((X, Z, -Y), "YXZ")


def swizzle_euler(euler: uVector3, isDegrees=True):
    """mode -> YXZ on the objects that support it. see euler3_to_quat_swizzled"""
    if isDegrees:
        return swizzle_euler3(
            math.radians(euler.x), math.radians(euler.y), math.radians(euler.z)
        )
    else:
        return swizzle_euler3(euler.x, euler.y, euler.z)


def swizzle_quaternion4(X, Y, Z, W):
    return blQuaternion((W, X, Z, -Y))  # conjugate (W,-X,-Z,Y)


def swizzle_quaternion(quat: uQuaternion):
    return swizzle_quaternion4(quat.x, quat.y, quat.z, quat.w)


# See swizzle_quaternion4. This is the inverse of that since we're reproducing Unity's quaternion
def euler3_to_quat_swizzled(x, y, z):
    # See https://docs.unity3d.com/ScriptReference/Quaternion.Euler.html
    # Unity uses ZXY rotation order
    quat = (
        blQuaternion((0, 0, 1), -y)
        @ blQuaternion((1, 0, 0), x)
        @ blQuaternion((0, 1, 0), z)
    )  # Left multiplication
    return uQuaternion(quat.x, -quat.z, quat.y, quat.w)
