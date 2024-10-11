# Build the addon zip locally
# The file hierarchy is the same with what Github will generate when you download the source code
# * Used to reproduce https://github.com/mos9527/sssekai_blender_io/issues/9
import zipfile, os

BRANCH = "master"
OUTFILE = "sssekai_blender_io-%s.zip" % BRANCH


def get_tracked_files():
    return os.popen("git ls-tree %s -r --name-only" % BRANCH).read().split("\n")[:-1]


with open(OUTFILE, "wb") as f:
    z = zipfile.ZipFile(f, "w")
    for file in get_tracked_files():
        print("* writing %s" % file)
        z.write(file, ("sssekai_blender_io-%s/" % BRANCH) + file)
    z.close()
