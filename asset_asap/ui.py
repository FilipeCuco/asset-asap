import bpy
import os
from bpy.types import Panel, UIList
from .preferences import get_prefs
from . import cache

_SPACE  = "VIEW_3D"
_REGION = "UI"
_CAT    = "Asset ASAP"


class AS_UL_dlcs(UIList):
    bl_idname = "AS_UL_dlcs"

    def draw_item(self, context, layout, data, item, icon, active_data, active_property, index):
        props = context.scene.as_props
        row = layout.row(align=True)
        row.label(text=item.name, icon="FILE_FOLDER")
        sub = row.row(align=True)
        sub.scale_x = 0.5
        sub.label(text=f"{item.ydr_count} ydr + {item.yft_count} yft")
        op_row = row.row()
        op_row.enabled = not props.is_importing_dlc
        op = op_row.operator("as.import_dlc", text="", icon="IMPORT")
        op.index = index


# ── Root panel — DLC Browser + Options ────────────────────────────────────────

class AS_PT_panel(Panel):
    bl_label       = "Asset ASAP"
    bl_idname      = "AS_PT_panel"
    bl_space_type  = _SPACE
    bl_region_type = _REGION
    bl_category    = _CAT

    def draw(self, context):
        layout = self.layout
        props  = context.scene.as_props
        busy   = props.is_importing_dlc or props.is_building_cache

        # ── DLC Browser ─────────────────────────────────
        layout.label(text="DLC Browser", icon="FILE_FOLDER")

        row = layout.row(align=True)
        sub = row.row()
        sub.enabled = not busy
        sub.operator("as.load_dlcs", text="Load DLCs", icon="FILE_REFRESH")

        if props.dlc_list:
            count = len(props.dlc_list)
            layout.label(text=f"DLCs ({count})", icon="PRESET")
            layout.template_list(
                "AS_UL_dlcs", "",
                props, "dlc_list",
                context.scene, "as_active_dlc_index",
                rows=min(count, 8),
            )

        # ── Progress ─────────────────────────────────────
        if props.is_importing_dlc and props.dlc_import_progress:
            prog_row = layout.row()
            prog_row.enabled = False
            prog_row.label(text=props.dlc_import_progress, icon="TIME")

        # ── Status ───────────────────────────────────────
        row = layout.row()
        row.enabled = False
        row.label(text=props.status_message, icon="TIME" if busy else "INFO")

        layout.separator()

        # ── Options ──────────────────────────────────────
        layout.label(text="Options", icon="SETTINGS")
        layout.prop(props, "import_filter")
        layout.prop(props, "asset_category")
        layout.prop(props, "clean_temp")


# ── Asset Cache (collapsible) ────────────────────────────────────────────────

class AS_PT_cache(Panel):
    bl_label       = "Asset Cache"
    bl_idname      = "AS_PT_cache"
    bl_space_type  = _SPACE
    bl_region_type = _REGION
    bl_category    = _CAT
    bl_parent_id   = "AS_PT_panel"
    bl_order       = 2
    bl_options     = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        props  = context.scene.as_props
        prefs  = get_prefs(context)

        layout.prop(prefs, "use_cache")

        status_row = layout.row()
        status_row.enabled = False
        if props.is_building_cache:
            status_row.label(text=props.status_message, icon="TIME")
        elif props.cache_info:
            status_row.label(text=props.cache_info, icon="CHECKMARK")
        else:
            status_row.label(text="No cache built yet", icon="INFO")

        build_row = layout.row()
        build_row.enabled = not props.is_building_cache
        build_row.operator(
            "as.build_cache",
            text="Building…" if props.is_building_cache else "Build Cache",
            icon="FILE_REFRESH",
        )




# ── Configuration (collapsible) ──────────────────────────────────────────────

class AS_PT_config(Panel):
    bl_label       = "Configuration"
    bl_idname      = "AS_PT_config"
    bl_space_type  = _SPACE
    bl_region_type = _REGION
    bl_category    = _CAT
    bl_parent_id   = "AS_PT_panel"
    bl_order       = 4
    bl_options     = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        prefs  = get_prefs(context)
        layout.prop(prefs, "gta_path", text="GTA V")
        layout.prop(prefs, "temp_dir", text="Temp")
        row = layout.row(align=True)
        row.prop(prefs, "cw_api_port", text="API Port")
        row.operator("as.sync_config", text="Sync", icon="FILE_REFRESH")
        layout.operator("as.clean_orphans", text="Clean Old Temp Files", icon="TRASH")


classes = [
    AS_UL_dlcs,
    AS_PT_panel,
    AS_PT_cache,
    AS_PT_config,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
