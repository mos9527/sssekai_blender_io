import os, zlib
from .. import SCRIPT_DIR
from sssekai.abcache import fromdict as dataclass_from_dict


def get_name_hash(name: str):
    return zlib.crc32(name.encode("utf-8"))


def get_addon_relative_path(*args):
    return os.path.join(SCRIPT_DIR, *args)


def encode_asset_id(obj):
    prop = lambda x: "<%s %s>" % (x, getattr(obj, x, "<unk>"))
    obj_prop = lambda x: "<%s %s>" % (
        x,
        (
            getattr(obj.object_reader, x, "<unk>")
            if hasattr(obj, "object_reader")
            else "<unk>"
        ),
    )
    return f"""{prop('m_Name')},{obj_prop('container')},{obj_prop('path_id')}"""
