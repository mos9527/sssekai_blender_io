import UnityPy
import UnityPy.config
from UnityPy.enums import ClassIDType
from UnityPy.classes import MonoBehaviour
from UnityPy.streams import EndianBinaryReader
import pprint

UnityPy.config.FALLBACK_UNITY_VERSION = "2022.3.21f1"
env = UnityPy.load("/Users/mos9527/Applications/PlayCover/プロセカ.app/Data/")
for reader in filter(lambda x: x.type == ClassIDType.MonoBehaviour, env.objects):
    obj = reader.read(check_read=False)
    if obj.m_Name.startswith("TransportDefine"):
        reader.reset()
        b = bytes(reader.reader.read_bytes(65536))
        p = b.find(obj.m_Name.encode())
        b = b[p:]
        # TODO: Typetree. Really.
        reader = EndianBinaryReader(b, endian="<")
        n = reader.read_string_to_null()
        reader.align_stream()
        a = reader.read_string_array()
        b = reader.read_string_array()
        print(f'"{n}": ({a},{b})')
