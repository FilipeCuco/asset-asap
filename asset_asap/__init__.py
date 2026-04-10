bl_info = {
    "name": "Asset ASAP — GTA V via CodeWalker.API",
    "author": "Lando",
    "version": (2, 0, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Asset ASAP",
    "description": (
        "Import GTA V DLC assets in bulk from RPF archives via CodeWalker.API. "
        "Browse DLCs and import all models directly to the Asset Browser."
    ),
    "category": "Import-Export",
}

from . import props, preferences, ops, ui, server, cache, textures


def _on_load_post(*_):
    """Restore persistent state (asset cache info + DLC list) after Blender loads a file."""
    import bpy

    def _init():
        try:
            scene_props = bpy.context.scene.as_props
        except Exception:
            return None

        # Restore asset cache info label
        info = cache.cache_info_str(cache.get_cache_path())
        if info:
            scene_props.cache_info = info

        # Auto-load DLC list if cache exists
        cache_data = cache.load(cache.get_cache_path())
        if cache_data:
            try:
                dlcs = cache.list_dlcs(cache_data, extensions=(".ydr", ".yft"))
                scene_props.dlc_list.clear()
                for d in dlcs:
                    item = scene_props.dlc_list.add()
                    item.name = d["name"]
                    item.ydr_count = d["ydr_count"]
                    item.yft_count = d["yft_count"]
                    item.total = d["total"]
                scene_props.status_message = f"Loaded {len(dlcs)} DLC(s)"
            except Exception as e:
                print(f"[AssetASAP] Failed to restore DLC list: {e}")
        return None

    bpy.app.timers.register(_init, first_interval=0.1)


def register():
    props.register()

    import bpy
    bpy.utils.register_class(preferences.AS_Preferences)

    ops.register()
    ui.register()

    bpy.app.handlers.load_post.append(_on_load_post)

    server.start(7890)


def unregister():
    import bpy
    if _on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load_post)

    server.stop()
    ui.unregister()
    ops.unregister()

    bpy.utils.unregister_class(preferences.AS_Preferences)

    props.unregister()


if __name__ == "__main__":
    register()
