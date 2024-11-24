# Build the addon zip locally
# With `--no-ext` the file hierarchy is the same with what Github will generate when you download the source code
# Otherwise, the external dependencies will be included in the zip file which would allow the addon to be installed directly
# * Used to reproduce https://github.com/mos9527/sssekai_blender_io/issues/9
import zipfile, os, argparse, shutil

PIPTEMP_DIR = ".temp"

def fetch_external_dependencies():
    from pip import main as pip_main
    pip_main(["install", "sssekai", "-t", PIPTEMP_DIR])    

def get_dependencies():    
    return [(os.path.join(folder,file),os.path.join('/'.join(folder.split('/')[1:]),file)) for folder,subs,files in os.walk(PIPTEMP_DIR) for file in files]

def get_tracked_files(branch : str):
    ret = os.popen("git ls-tree %s -r --name-only" % branch).read().split("\n")[:-1]
    return list(zip(ret, ret))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Build the addon zip locally')
    parser.add_argument('--branch', type=str, default="master", help='Branch name')
    parser.add_argument('--no-ext', action='store_true', help='Do not include external dependencies')
    parser.add_argument('outfile', type=str, help='Output file name')
    args = parser.parse_args()
    assert not '.' in args.outfile, "Output file name should not contain '.'"
    files = get_tracked_files(args.branch)
    if not args.no_ext:
        if os.path.exists(PIPTEMP_DIR):
            shutil.rmtree(PIPTEMP_DIR)
        os.mkdir(PIPTEMP_DIR)
        fetch_external_dependencies()
        files += get_dependencies()            
    with open(args.outfile + '.zip', "wb") as f:
        z = zipfile.ZipFile(f, "w")
        for src,filename in files:
            print("* writing %s" % filename)
            z.write(src, ('%s/%s' % (args.outfile, filename)))
        z.close()
