import bpy


class AS_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    gta_path: bpy.props.StringProperty(
        name="GTA V Path",
        description="Root folder of your GTA V installation",
        subtype="DIR_PATH",
        default="C:\\Program Files (x86)\\Steam\\steamapps\\common\\Grand Theft Auto V",
    )
    cw_api_port: bpy.props.StringProperty(
        name="CodeWalker API Port",
        description="Port where CodeWalker.API is listening",
        default="5555",
    )
    addon_server_port: bpy.props.IntProperty(
        name="Addon Server Port",
        description="Port the addon listens on for browser extension requests",
        default=7890,
        min=1024,
        max=65535,
    )
    temp_dir: bpy.props.StringProperty(
        name="Temp Directory",
        description="Folder for temporary XML files during import",
        subtype="DIR_PATH",
        default="C:\\GTA_FILES\\cw_out",
    )
    use_cache: bpy.props.BoolProperty(
        name="Use Cache for Search",
        description=(
            "Search the local asset cache instead of querying CodeWalker.API each time. "
            "Build the cache once via the Cache panel — subsequent searches become instant."
        ),
        default=False,
    )
    enable_mods: bpy.props.BoolProperty(
        name="Enable Mods",
        description="Allow loading modded content",
        default=False,
    )
    dlc: bpy.props.StringProperty(
        name="DLC Override",
        description="Optional DLC name (e.g. patchday24ng). Leave blank for base game.",
        default="",
    )

    def draw(self, context):
        import bpy as _bpy
        layout = self.layout

        # ── Paths ────────────────────────────────────────
        box = layout.box()
        box.label(text="Paths", icon="FILE_FOLDER")
        box.prop(self, "gta_path")
        box.prop(self, "temp_dir")
        row = box.row()
        row.prop(self, "cw_api_port")
        row.prop(self, "addon_server_port")
        box.operator("as.sync_config", icon="FILE_REFRESH")

        # ── Mods / DLC ───────────────────────────────────
        box = layout.box()
        box.label(text="Content", icon="MODIFIER")
        box.prop(self, "enable_mods")
        box.prop(self, "dlc")


def get_prefs(context=None):
    ctx = context or bpy.context
    return ctx.preferences.addons[__package__].preferences
