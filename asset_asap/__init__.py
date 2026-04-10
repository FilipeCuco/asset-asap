bl_info = {
    "name": "Asset ASAP — GTA V via CodeWalker.API",
    "author": "Lando",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Asset ASAP",
    "description": (
        "Import GTA V assets directly from RPF archives via CodeWalker.API. "
        "Integrates with the forge.plebmasters.de browser extension."
    ),
    "category": "Import-Export",
}

from . import props, preferences, ops, ui, server, cache, textures


def _on_load_post(*_):
    """Restore persistent state (asset cache info + last search) after Blender loads a file."""
    import bpy

    props = None
    try:
        props = bpy.context.scene.as_props
    except Exception:
        return

    # Restore asset cache info label
    info = cache.cache_info_str(cache.get_cache_path())
    if info:
        props.cache_info = info

    # Restore last search results from disk
    sc = cache.load_search_cache()
    if sc and sc.get("query") and sc.get("results"):
        try:
            props.last_query_text = sc["query"]
            props.total_results = sc.get("total", len(sc["results"]))
            props.search_results.clear()
            for path in sc["results"]:
                item = props.search_results.add()
                item.name = path
            count = len(sc["results"])
            total = props.total_results
            if total > count:
                props.status_message = f"Showing {count} of {total} results — refine your search"
            else:
                props.status_message = f"Found {count} result(s) (restored)"
        except Exception as e:
            print(f"[AssetASAP] Failed to restore search cache: {e}")


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
