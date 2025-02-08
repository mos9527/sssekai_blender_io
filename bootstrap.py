bl_info = {
    "name": "SSSekai Blender IO Bootstrapper",
    "author": "mos9527",
    "version": (0, 0, 1),
    "blender": (4, 0, 0),
    "description": "SSSekai Blender IO Addon Bootstrapper. This is NOT the actual addon. Please Enable for more info.",
    "warning": "",
    "wiki_url": "https://github.com/mos9527/sssekai_blender_io/wiki",
    "tracker_url": "https://github.com/mos9527/sssekai_blender_io",
    "category": "Import-Export",
}


import bpy, os, subprocess, sys, shutil
import addon_utils
from dataclasses import dataclass

ADDON_INSTALLATION_LINK_FOLDER = "sssekai_blender_io_bootstrapped"


@dataclass
class SSSekaiAddonEnviornmentStatus:
    git_installed: str = None
    sssekai_installed: str = None

    addon_path: str = None
    addon_writable: bool = False
    addon_installed: str = None

    lib_path: str = None
    lib_writable: bool = False

    install_path: str = None

    path_relinked: bool = False

    @property
    def addon_link_path(self):
        return os.path.join(self.addon_path, ADDON_INSTALLATION_LINK_FOLDER)

    def refresh(self):
        self.addon_path = addon_utils.paths()[-1]
        self.lib_path = os.path.dirname(os.__file__)

        self.addon_writable = os.access(self.addon_path, os.W_OK)
        self.lib_writable = os.access(self.lib_path, os.W_OK)

        try:
            result = subprocess.run(
                ["git", "--version"], capture_output=True, text=True, check=True
            )
            self.git_installed = result.stdout.strip()
        except Exception:
            self.git_installed = None

        if self.git_installed:
            try:
                result = subprocess.run(
                    ["git", "log", "-1", '--format="%h: %s"'],
                    cwd=self.addon_link_path,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                self.addon_installed = result.stdout.strip()
                result = subprocess.run(
                    ["git", "branch", "--show-current"],
                    cwd=self.addon_link_path,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                self.addon_installed += f" ({result.stdout.strip()})"
            except Exception:
                self.addon_installed = None
        else:
            self.addon_installed = None

        try:
            import sssekai

            self.sssekai_installed = sssekai.__version__
        except ImportError:
            self.sssekai_installed = None

    @property
    def is_ok(self):
        return (
            self.addon_writable
            and self.lib_writable
            and self.git_installed
            and self.sssekai_installed
        )

    @property
    def is_currently_installed(self):
        return self.addon_installed is not None

    @property
    def is_current_installation_symlinked(self):
        return os.path.islink(self.addon_link_path)

    @property
    def current_installation_link_target(self):
        return os.readlink(self.addon_link_path)


env = SSSekaiAddonEnviornmentStatus()
env.refresh()


class SSSekaiRefreshEnvironmentOperator(bpy.types.Operator):
    bl_idname = "sssekai.refresh_environment"
    bl_label = "Refresh Environment"

    def execute(self, context):
        global env

        env.refresh()
        return {"FINISHED"}


class SSSekaiUpdateSSSekaiOperator(bpy.types.Operator):
    bl_idname = "sssekai.update_sssekai"
    bl_label = "Install/Update SSSekai"
    bl_description = "Install/Update SSSekai to the latest version."

    def execute(self, context):
        global env

        try:
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--no-user",
                    "--upgrade",
                    "sssekai",
                ],
                capture_output=False,
                text=False,
                check=True,
            )
            env.refresh()
        except subprocess.CalledProcessError as e:
            self.report({"ERROR"}, "Process reported: %s" % e.stderr)
        return {"FINISHED"}


class SSSekaiUpdateAddonOperator(bpy.types.Operator):
    bl_idname = "sssekai.update_addon"
    bl_label = "Install/Update SSSekai Blender IO Addon"
    bl_description = "Install/Update SSSekai Blender IO Addon to the latest version."

    def execute(self, context):
        global env

        install_path = env.install_path
        link_path = env.addon_link_path
        if install_path != link_path:
            # Relink the source path
            try:
                if env.is_currently_installed:
                    if env.is_current_installation_symlinked:
                        os.unlink(link_path)
                    else:
                        shutil.rmtree(link_path)
                os.symlink(install_path, link_path, True)
                self.report({"INFO"}, "Source path has been relinked.")
                env.path_relinked = True
            except Exception as e:
                self.report({"ERROR"}, str(e))
            env.refresh()
            return {"FINISHED"}
        else:
            if env.is_currently_installed:
                subprocess.run(
                    ["git", "pull"],
                    cwd=install_path,
                    check=True,
                )
                self.report({"INFO"}, "Addon has been updated!")
                return {"FINISHED"}
            else:
                # Invalid git repository.
                if env.is_current_installation_symlinked:
                    self.report(
                        {"ERROR"},
                        "Invalid linked source directory. Target is not a Git repository",
                    )
                    env.refresh()
                    return {"CANCELLED"}
                # Otherwise - first time or broken git repository.
                # Delete the old folder and clone the repository.
                try:
                    if os.path.exists(install_path):
                        os.rmdir(install_path)
                    subprocess.run(
                        [
                            "git",
                            "clone",
                            "https://github.com/mos9527/sssekai_blender_io",
                            ADDON_INSTALLATION_LINK_FOLDER,
                        ],
                        cwd=os.path.dirname(install_path),
                        check=True,
                    )
                    self.report({"INFO"}, "Repository has been cloned!")
                except Exception:
                    self.report(
                        {"ERROR"},
                        "Failed to clone the repository. See System Console for more info.",
                    )
                    env.refresh()
                    return {"CANCELLED"}
                env.refresh()
                return {"FINISHED"}


class SSSekaiAddonBootstrapperPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    source_path: bpy.props.StringProperty(
        name="Source Directory",
        description="Where the addon source will be located.",
        subtype="DIR_PATH",
    )  # type: ignore

    def draw(self, context):
        layout = self.layout
        layout.label(text="SSSekai Blender IO Addon Bootstrapper")
        row = layout.row()
        row.label(
            text="NOTE: It's recommended to bring up the System Console for easy diagnostics.",
            icon="INFO",
        )
        row = layout.row()
        row.label(text="Git Version")
        row = layout.row()
        if env.git_installed:
            row.label(text=env.git_installed, icon="CHECKMARK")
        else:
            row.label(text="Git is NOT available.", icon="ERROR")
        row = layout.row()

        row.label(text="SSSekai Version")
        row = layout.row()
        if env.sssekai_installed:
            row.label(text=env.sssekai_installed, icon="CHECKMARK")
        else:
            row.label(text="SSSekai is NOT available.", icon="ERROR")
        row = layout.row()

        row.label(text="Addon Path")
        row = layout.row()
        row.label(
            text=f"{env.addon_path} ({'writable' if env.addon_writable else 'READ ONLY!'})",
            icon="CHECKMARK" if env.addon_writable else "ERROR",
        )
        row = layout.row()

        row.label(text="Library Path")
        row = layout.row()
        row.label(
            text=f"{env.lib_path} ({'writable' if env.lib_writable else 'READ ONLY!'})",
            icon="CHECKMARK" if env.addon_writable else "ERROR",
        )

        layout.separator()
        row = layout.row()
        if env.is_ok:
            if not self.source_path or env.path_relinked:
                self.source_path = env.addon_link_path
                env.path_relinked = False
            env.install_path = self.source_path

            row.label(
                text="Your Blender environment is ready for the addon installation!",
                icon="INFO",
            )
            row = layout.row()
            row.prop(self, "source_path")
            row = layout.row()
            row.label(text="You can install the addon now.")
            row = layout.row()
            row.label(
                text="It's possible to change the source directory - in this case the source folder will be symlinked."
            )
            row = layout.row()
            row.label(
                text="Meaning that you can edit the source code *there* and see the changes in Blender."
            )
            row = layout.row()
            row.label(
                text="Otherwise, the source will be installed directly into the addons folder."
            )
            row = layout.row()
            row.label(text="Current installed version:", icon="INFO")
            row = layout.row()
            row.label(
                text=env.addon_installed or "(not installed or invalid source path)"
            )
            row = layout.row()
            row.label(
                text="After an update, you should restart Blender for changes to take effect.",
                icon="INFO",
            )
            row = layout.row()
            if env.is_currently_installed:
                row.label(
                    text="You can UPDATE the addon by clicking the button below.",
                    icon="INFO",
                )
                row = layout.row()
                if env.is_current_installation_symlinked:
                    row.label(
                        text=f"Current source path is symlinked to: {env.current_installation_link_target}",
                        icon="CHECKMARK",
                    )
                else:
                    row.label(
                        text="Current source path is installed directly into the addons folder.",
                        icon="CHECKMARK",
                    )
                if env.addon_link_path != env.install_path:
                    row = layout.row()
                    row.label(text="Installation will be relinked", icon="INFO")
                    if not env.is_current_installation_symlinked:
                        row = layout.row()
                        row.label(
                            text="WARNING: This will destory the current installation!",
                            icon="INFO",
                        )
            else:
                row.label(
                    text="You can INSTALL the addon by clicking the button below.",
                    icon="INFO",
                )
                row = layout.row()
                if env.addon_link_path == env.install_path:
                    row.label(
                        text="Direct installation is enabled.",
                        icon="INFO",
                    )
                else:
                    row.label(
                        text="Link installation is enabled. (source path will be symlinked)",
                        icon="INFO",
                    )
                    row = layout.row()
                    row.label(
                        text="After this operation, the source path will be symlinked to the addons folder."
                    )
            row = layout.row()
            row.operator(SSSekaiUpdateAddonOperator.bl_idname)
        else:
            row.label(
                text="You CANNOT install the addon at the moment since there still are issues.",
                icon="ERROR",
            )
            row = layout.row()
            row.label(
                text="NOTE: All paths shown in the diagnostics should be writable."
            )
            row = layout.row()
            row.label(text="Please fix the issues above and try again.")
        row = layout.row()

        if env.lib_writable:
            row.operator(SSSekaiUpdateSSSekaiOperator.bl_idname)
        row.operator(SSSekaiRefreshEnvironmentOperator.bl_idname)


def register():
    bpy.utils.register_class(SSSekaiAddonBootstrapperPreferences)
    bpy.utils.register_class(SSSekaiRefreshEnvironmentOperator)
    bpy.utils.register_class(SSSekaiUpdateSSSekaiOperator)
    bpy.utils.register_class(SSSekaiUpdateAddonOperator)


def unregister():
    bpy.utils.unregister_class(SSSekaiAddonBootstrapperPreferences)
    bpy.utils.unregister_class(SSSekaiRefreshEnvironmentOperator)
    bpy.utils.unregister_class(SSSekaiUpdateSSSekaiOperator)
    bpy.utils.unregister_class(SSSekaiUpdateAddonOperator)
