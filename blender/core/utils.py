import os, zlib
from .. import SCRIPT_DIR
from sssekai.abcache import fromdict as dataclass_from_dict


def crc32(name: str | bytes) -> int:
    if isinstance(name, str):
        return zlib.crc32(name.encode("utf-8"))
    else:
        return zlib.crc32(name)


def get_addon_relative_path(*args):
    return os.path.join(SCRIPT_DIR, *args)
