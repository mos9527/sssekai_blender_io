import zipfile, os, argparse, shutil, sys

PIPTEMP_DIR = ".temp"


def fetch_external_dependencies():
    from pip import main as pip_main

    pip_main(["install", "sssekai", "-t", PIPTEMP_DIR])


def get_dependencies():
    return [
        (
            os.path.join(folder, file),
            os.path.join("/".join(folder.split("/")[1:]), file),
        )
        for folder, subs, files in os.walk(PIPTEMP_DIR)
        for file in files
    ]


def get_tracked_files(branch: str):
    ret = os.popen("git ls-tree %s -r --name-only" % branch).read().split("\n")[:-1]
    return list(zip(ret, ret))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the addon zip locally")
    parser.add_argument("--branch", type=str, default="master", help="Branch name")
    parser.add_argument(
        "--no-ext", action="store_true", help="Do not include external dependencies"
    )
    parser.add_argument(
        "--outfile",
        type=str,
        help="Output file name WITHOUT extension. Addon will always be bundled in ZIP format.",
        default="sssekai_blender_io",
    )
    args = parser.parse_args()

    files = get_tracked_files(args.branch)
    assert "__init__.py" in [
        f[0] for f in files
    ], "No __init__.py found in tracked files. Please run this script in the addon root directory."
    print("** Bundle information")
    print("** Branch: %s" % args.branch)
    print("** Bundler Python Runtime: %s" % sys.version)
    print("-- Checking extension dependencies")
    if not args.no_ext:
        if os.path.exists(PIPTEMP_DIR):
            shutil.rmtree(PIPTEMP_DIR)
        os.mkdir(PIPTEMP_DIR)
        fetch_external_dependencies()
        files += get_dependencies()
        # Push import dir
        sys.path.insert(0, PIPTEMP_DIR)
    try:
        import UnityPy
        import sssekai
    except ImportError as e:
        print("** Error: %s" % e)
        print(
            "** Do NOT use `--no-ext`, or install `sssekai` in your Python environment first."
        )
        sys.exit(1)
    print("** SSSekai: %s" % sssekai.__version__)
    print("** UnityPy: %s" % UnityPy.__version__)
    print("-- Bundling files")
    with open(args.outfile + ".bundled.zip", "wb") as f:
        z = zipfile.ZipFile(f, "w")
        for i, (src, filename) in enumerate(files):
            print("[%3d/%3d] %s" % (i + 1, len(files), filename), " " * 50, end="\r")
            z.write(src, ("%s/%s" % (args.outfile, filename)))
        z.close()
    print("\n-- Bundle complete: %s.zip" % args.outfile)
