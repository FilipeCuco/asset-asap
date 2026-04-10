import bpy
import os
from bpy.types import Panel, UIList
from .preferences import get_prefs
from .textures import get_object_images
from . import cache

_SPACE  = "VIEW_3D"
_REGION = "UI"
_CAT    = "Asset ASAP"


class AS_UL_results(UIList):
    bl_idname = "AS_UL_results"

    def draw_item(self, context, layout, data, item, icon, active_data, active_property, index):
        row = layout.row(align=True)
        row.label(text=os.path.basename(item.name), icon="FILE")
        op = row.operator("as.import_asset", text="Import", icon="IMPORT")
        op.index = index


# ── Root panel — Search Asset + Options (no collapse arrow on these sections) ─

class AS_PT_panel(Panel):
    bl_label       = "Asset ASAP"
    bl_idname      = "AS_PT_panel"
    bl_space_type  = _SPACE
    bl_region_type = _REGION
    bl_category    = _CAT

    def draw(self, context):
        layout = self.layout
        props  = context.scene.as_props
        busy   = props.is_searching or props.is_importing

        # ── Search Asset ─────────────────────────────────
        layout.label(text="Search Asset", icon="VIEWZOOM")
        row = layout.row(align=True)
        row.prop(props, "search_query", text="")
        sub = row.row()
        sub.enabled = not busy
        sub.operator("as.search", text="", icon="VIEWZOOM")

        if props.search_results:
            count = len(props.search_results)
            total = props.total_results
            header = f"Results ({count} of {total})" if total > count else f"Results ({count})"
            layout.label(text=header, icon="PRESET")
            layout.template_list(
                "AS_UL_results", "",
                props, "search_results",
                context.scene, "as_active_index",
                rows=min(count, 5),
            )
            if total > count:
                row = layout.row()
                row.enabled = False
                row.label(text="Refine your search to see more", icon="INFO")

        row = layout.row()
        row.enabled = False
        row.label(text=props.status_message, icon="TIME" if busy else "INFO")

        layout.separator()

        # ── Options ──────────────────────────────────────
        layout.label(text="Options", icon="SETTINGS")
        layout.prop(props, "drawable_only")
        asset_row = layout.row()
        asset_row.enabled = props.drawable_only
        asset_row.prop(props, "send_to_asset_browser")
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


# ── Textures (collapsible) ───────────────────────────────────────────────────

class AS_PT_textures(Panel):
    bl_label       = "Textures"
    bl_idname      = "AS_PT_textures"
    bl_space_type  = _SPACE
    bl_region_type = _REGION
    bl_category    = _CAT
    bl_parent_id   = "AS_PT_panel"
    bl_order       = 3
    bl_options     = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        props  = context.scene.as_props
        obj    = context.active_object
        images = get_object_images(obj) if obj else []

        box = layout.box()
        if obj:
            row = box.row()
            row.label(text=obj.name, icon="OBJECT_DATA")
            if images:
                for img in images:
                    row = box.row()
                    row.enabled = False
                    row.label(text=img.name, icon="IMAGE_DATA")
            else:
                row = box.row()
                row.enabled = False
                row.label(text="No textures on this object", icon="INFO")
        else:
            row = box.row()
            row.enabled = False
            row.label(text="Select an object in the viewport", icon="INFO")

        layout.prop(props, "texture_export_dir", text="Destination")

        has_textures = bool(images)
        has_dir      = bool(props.texture_export_dir)

        row = layout.row()
        row.scale_y = 1.3
        row.enabled = obj is not None and has_dir and has_textures
        row.operator("as.export_textures", text="Copy Textures", icon="IMAGE_DATA")

        if obj and not has_textures:
            warn = layout.row()
            warn.enabled = False
            warn.label(text="Object has no textures", icon="ERROR")
        elif not has_dir:
            warn = layout.row()
            warn.enabled = False
            warn.label(text="Choose a destination folder above", icon="ERROR")


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
    AS_UL_results,
    AS_PT_panel,
    AS_PT_cache,
    AS_PT_textures,
    AS_PT_config,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
