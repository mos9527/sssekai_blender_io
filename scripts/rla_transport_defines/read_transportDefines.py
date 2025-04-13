import UnityPy
import UnityPy.config
from UnityPy.enums import ClassIDType
from UnityPy.classes import MonoBehaviour
from UnityPy.streams import EndianBinaryReader
import pprint

UnityPy.config.FALLBACK_UNITY_VERSION = "2022.3.21f1"
env = UnityPy.load(r"C:\Users\mos9527\Desktop\sekaijp\jp\assets\bin\Data")

from generated.Sekai.Streaming import TransportDefine
from generated import UTTCGen_AsInstance

for reader in filter(lambda x: x.type == ClassIDType.MonoBehaviour, env.objects):
    name = reader.peek_name()
    if name.startswith("TransportDefine"):
        instance = UTTCGen_AsInstance(reader, "Sekai.Streaming.TransportDefine")
        instance: TransportDefine
        print(f'"{name}":({instance.validBones}, {instance.validBlendShapes}),')
        instance.save()
        break
