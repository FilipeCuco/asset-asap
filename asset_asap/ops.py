import bpy
import concurrent.futures
import os
import time
import threading
from bpy.types import Operator
from . import api, cache
from .preferences import get_prefs
from .cache import MODEL_EXTENSIONS
from .textures import get_object_images, copy_textures_from_temp


# ---------------------------------------------------------------------------
# Sollumz type constants (string values of SollumType enum)
# ---------------------------------------------------------------------------

_SOLLUM_DRAWABLE       = "sollumz_drawable"
_SOLLUM_DRAWABLE_MODEL = "sollumz_drawable_model"
_SOLLUM_FRAGMENT       = "sollumz_fragment"
_SOLLUM_BOUND_TYPES = frozenset({
    "sollumz_bound_composite",
    "sollumz_bound_box",
    "sollumz_bound_sphere",
    "sollumz_bound_capsule",
    "sollumz_bound_cylinder",
    "sollumz_bound_disc",
    "sollumz_bound_cloth",
    "sollumz_bound_geometry",
    "sollumz_bound_geometry_bvh",
    "sollumz_bound_poly_triangle",
    "sollumz_bound_poly_box",
    "sollumz_bound_poly_sphere",
    "sollumz_bound_poly_capsule",
    "sollumz_bound_poly_cylinder",
})

# ---------------------------------------------------------------------------
# Asset Browser catalog — fixed UUID so it's stable across sessions
# ---------------------------------------------------------------------------

_CATALOG_UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
_CATALOG_NAME = "Asset ASAP"
_CATS_FILE    = "blender_assets.cats.txt"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _clean_temp_files(directory, *basenames):
    """Delete <basename>*.xml and <basename>*.dds files in directory for each basename."""
    try:
        files = os.listdir(directory)
    except Exception as e:
        print(f"[AssetASAP] Cleanup listing error: {e}")
        return 0
    removed = 0
    for basename in basenames:
        if not basename:
            continue
        b = basename.lower()
        for f in files:
            fl = f.lower()
            if fl.startswith(b) and fl.endswith((".xml", ".dds")):
                try:
                    os.remove(os.path.join(directory, f))
                    removed += 1
                except Exception as e:
                    print(f"[AssetASAP] Cleanup error ({f}): {e}")
    return removed


def _find_ytd_path(asset_path, port, use_cache):
    """Return the best matching .ytd path for a model asset, or None."""
    if asset_path.lower().endswith(".ytd"):
        return None

    basename = os.path.splitext(os.path.basename(asset_path))[0]
    ytd_query = basename + ".ytd"

    if use_cache:
        cache_data = cache.load(cache.get_cache_path())
        if cache_data:
            return cache.find_ytd(cache_data, asset_path)

    ok, result = api.search_file(port, ytd_query)
    if not ok or not result:
        return None

    asset_dir = os.path.dirname(asset_path)
    same_dir = [r for r in result if os.path.dirname(r) == asset_dir]
    return same_dir[0] if same_dir else result[0]


def _collect_subtree(obj, result):
    """Recursively add all descendants of obj into result."""
    for child in obj.children:
        result.add(child)
        _collect_subtree(child, result)


def _apply_drawable_only(new_objects, asset_path):
    """
    Keep only the sollumz_drawable_model mesh — the actual visible geometry.
    Delete everything else: fragment armature, drawable container, all collisions.

    User terminology:
      "fragment" = Armature container (sollumz_fragment or sollumz_drawable)
      "drawable" = the visible MESH (sollumz_drawable_model) — what we keep
    """
    asset_name      = os.path.splitext(os.path.basename(asset_path))[0]
    fragment_name   = asset_name
    drawable_models = []
    to_delete       = []

    for obj in new_objects:
        stype = getattr(obj, "sollum_type", "")
        nl    = obj.name.lower()

        if stype == _SOLLUM_FRAGMENT:
            fragment_name = obj.name
            to_delete.append(obj)
        elif stype == _SOLLUM_DRAWABLE:
            # Container (Armature or Empty) — delete it, keep only the mesh inside
            to_delete.append(obj)
        elif stype == _SOLLUM_DRAWABLE_MODEL:
            drawable_models.append(obj)
        elif stype in _SOLLUM_BOUND_TYPES or nl.endswith(".col") or nl.startswith("bound"):
            to_delete.append(obj)

    print(f"[AssetASAP]   models={[o.name for o in drawable_models]}  "
          f"fragment='{fragment_name}'  to_delete={[o.name for o in to_delete]}")

    # Capture all names before touching anything — avoids stale refs in Blender 4.x
    delete_names = [o.name for o in to_delete]
    model_names  = [o.name for o in drawable_models]

    # Unparent every model from its container before the container is deleted
    for model in drawable_models:
        if model.parent and model.parent in to_delete:
            world_mat = model.matrix_world.copy()
            model.parent = None
            model.matrix_world = world_mat

    # Delete by fresh name lookup — no stale Python reference risk
    for name in delete_names:
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        try:
            bpy.data.objects.remove(obj, do_unlink=True)
            print(f"[AssetASAP]   removed '{name}'")
        except Exception as e:
            print(f"[AssetASAP]   FAILED '{name}': {e}")

    # Re-fetch models after deletions and rename the primary one
    models  = [bpy.data.objects.get(n) for n in model_names]
    models  = [m for m in models if m is not None]
    primary = models[0] if models else None

    if primary:
        primary.name = fragment_name
        if primary.data:
            primary.data.name = fragment_name
        print(f"[AssetASAP]   renamed to '{fragment_name}'")

    return primary


def _ensure_catalog(blend_filepath):
    """
    Write/update blender_assets.cats.txt next to the .blend file
    to ensure the 'Asset ASAP' catalog entry exists.
    """
    cats_path = os.path.join(os.path.dirname(blend_filepath), _CATS_FILE)
    entry     = f"{_CATALOG_UUID}:{_CATALOG_NAME}:{_CATALOG_NAME}\n"

    if os.path.isfile(cats_path):
        with open(cats_path, "r", encoding="utf-8") as f:
            content = f.read()
        if _CATALOG_UUID in content:
            return
        with open(cats_path, "a", encoding="utf-8") as f:
            f.write(entry)
    else:
        with open(cats_path, "w", encoding="utf-8") as f:
            f.write("# Asset Catalog Definition file for Blender.\n")
            f.write("# Format: UUID:catalog/path:Simple Name\n\n")
            f.write("VERSION 1\n\n")
            f.write(entry)


def _is_already_asset(asset_name):
    """Return True if an object with this exact name is already marked as asset."""
    obj = bpy.data.objects.get(asset_name)
    return obj is not None and obj.asset_data is not None


def _mark_as_asset(obj):
    """
    Mark obj as a Blender asset under the 'Asset ASAP' catalog and
    auto-save the .blend file. Skips silently if already catalogued.
    Returns (success: bool, warning: str | None).
    """
    if _is_already_asset(obj.name):
        return True, None

    obj.asset_mark()
    obj.asset_data.catalog_id = _CATALOG_UUID
    obj.asset_generate_preview()

    if bpy.data.filepath:
        _ensure_catalog(bpy.data.filepath)
        bpy.ops.wm.save_mainfile()
        return True, None
    else:
        return False, "Save the .blend file to persist the asset in the browser"


def _do_import(asset_path, ytd_path, temp_dir, props, drawable_only, asset_browser, clean):
    """
    Import asset_path via Sollumz, then apply post-processing based on flags.
    Runs on the main thread (called from bpy.app.timers).
    """
    print(f"[AssetASAP] _do_import: drawable_only={drawable_only} asset_browser={asset_browser} path={asset_path}")
    basename = os.path.basename(asset_path)
    xml_name = basename + ".xml"
    xml_path = os.path.join(temp_dir, xml_name)

    if not os.path.exists(xml_path):
        props.status_message = f"Error: {xml_name} not found in temp dir"
        props.is_importing = False
        return None

    existing = set(bpy.context.scene.objects)

    try:
        result = bpy.ops.sollumz.import_assets(
            directory=temp_dir,
            files=[{"name": xml_name}],
        )
    except Exception as e:
        props.status_message = f"Sollumz error: {e}"
        props.is_importing = False
        return None

    if result != {"FINISHED"}:
        props.status_message = "Import failed (Sollumz returned non-FINISHED)"
        props.is_importing = False
        return None

    new_objs = [o for o in bpy.context.scene.objects if o not in existing]

    final_obj = None
    if drawable_only:
        final_obj = _apply_drawable_only(new_objs, asset_path)

    if asset_browser and final_obj:
        ok, warn = _mark_as_asset(final_obj)
        if warn:
            props.status_message = f"Imported: {final_obj.name}  ({warn})"
            props.is_importing = False
            return None

    if clean:
        ytd_basename = os.path.basename(ytd_path) if ytd_path else None
        removed = _clean_temp_files(temp_dir, basename, ytd_basename)
        print(f"[AssetASAP] Clean temp: {removed} file(s) removed")

    asset_name = final_obj.name if final_obj else basename
    props.status_message = f"Imported: {asset_name}"
    props.is_importing = False
    return None


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class AS_OT_sync_config(Operator):
    bl_idname = "as.sync_config"
    bl_label = "Sync Config to API"

    def execute(self, context):
        prefs = get_prefs(context)
        ok, msg = api.set_config(
            port=prefs.cw_api_port,
            gta_path=prefs.gta_path,
            output_dir=prefs.temp_dir,
            enable_mods=prefs.enable_mods,
            dlc=prefs.dlc,
        )
        if ok:
            self.report({"INFO"}, "Config synced to CodeWalker.API")
        else:
            self.report({"ERROR"}, f"Sync failed: {msg}")
        return {"FINISHED"}


class AS_OT_build_cache(Operator):
    bl_idname = "as.build_cache"
    bl_label = "Build Asset Cache"
    bl_description = (
        "Query CodeWalker.API for all .ydr / .yft / .ydd / .ybn / .ytd assets "
        "and save them locally. Only needs to be done once (or after a GTA update)."
    )

    def execute(self, context):
        props = context.scene.as_props
        prefs = get_prefs(context)

        if props.is_building_cache:
            self.report({"WARNING"}, "Cache build already in progress")
            return {"CANCELLED"}

        props.is_building_cache = True
        props.status_message = "Building cache…"

        port = prefs.cw_api_port
        temp_dir = prefs.temp_dir

        def _thread():
            def _progress(current, total, label):
                def _upd():
                    bpy.context.scene.as_props.status_message = (
                        f"Caching {label}  ({current}/{total})…"
                    )
                    return None
                bpy.app.timers.register(_upd, first_interval=0.0)

            ok, msg = cache.build(port, progress_cb=_progress)

            def _done():
                p = bpy.context.scene.as_props
                p.is_building_cache = False
                p.status_message = msg
                if ok:
                    p.cache_info = msg
                return None

            bpy.app.timers.register(_done, first_interval=0.0)

        threading.Thread(target=_thread, daemon=True).start()
        return {"FINISHED"}


class AS_OT_search(Operator):
    bl_idname = "as.search"
    bl_label = "Search"

    def execute(self, context):
        props = context.scene.as_props
        prefs = get_prefs(context)
        query = props.search_query.strip()

        if not query:
            self.report({"WARNING"}, "Enter an asset name first")
            return {"CANCELLED"}

        # Return cached results when the same query is repeated
        if query == props.last_query_text and props.search_results:
            count = len(props.search_results)
            total = props.total_results
            if total > count:
                props.status_message = f"Showing {count} of {total} results — refine your search"
            else:
                props.status_message = f"Found {count} result(s)"
            return {"FINISHED"}

        props.search_results.clear()
        props.status_message = f"Searching '{query}'…"
        props.is_searching = True

        port = prefs.cw_api_port
        use_cache = prefs.use_cache

        def _thread():
            total = 0
            if use_cache:
                cache_data = cache.load(cache.get_cache_path())
                if cache_data:
                    result, total = cache.search_local(cache_data, query, extensions=MODEL_EXTENSIONS)
                    ok = True
                else:
                    ok, result = api.search_file(port, query, extensions=MODEL_EXTENSIONS)
                    if ok and result:
                        total = len(result)
                        result = result[:200]
            else:
                ok, result = api.search_file(port, query, extensions=MODEL_EXTENSIONS)
                if ok and result:
                    total = len(result)
                    result = result[:200]

            def _apply():
                props.is_searching = False
                if not ok:
                    props.status_message = f"Search error: {result}"
                    return None
                props.search_results.clear()
                for path in result:
                    item = props.search_results.add()
                    item.name = path
                props.total_results = total
                props.last_query_text = query
                cache.save_search_cache(query, list(result), total)
                count = len(result)
                if total > count:
                    props.status_message = f"Showing {count} of {total} results — refine your search"
                elif count:
                    props.status_message = f"Found {count} result(s)"
                elif use_cache and not cache.load(cache.get_cache_path()):
                    props.status_message = "No results — build the cache first"
                else:
                    props.status_message = "No results found"
                return None

            bpy.app.timers.register(_apply, first_interval=0.0)

        threading.Thread(target=_thread, daemon=True).start()
        return {"FINISHED"}


class AS_OT_import(Operator):
    bl_idname = "as.import_asset"
    bl_label = "Import"

    index: bpy.props.IntProperty()

    def execute(self, context):
        props = context.scene.as_props
        prefs = get_prefs(context)

        if self.index >= len(props.search_results):
            self.report({"ERROR"}, "Invalid result index")
            return {"CANCELLED"}

        asset_path = props.search_results[self.index].name
        temp_dir = prefs.temp_dir

        if not temp_dir or not os.path.isdir(temp_dir):
            self.report({"ERROR"}, "Temp directory is not set or does not exist")
            return {"CANCELLED"}

        props.status_message = f"Downloading {os.path.basename(asset_path)}…"
        props.is_importing = True

        port = prefs.cw_api_port
        use_cache = prefs.use_cache
        drawable_only = props.drawable_only
        asset_browser = props.send_to_asset_browser and drawable_only
        clean = props.clean_temp

        def _thread():
            # Skip download if XML already in temp from a previous import
            xml_path = os.path.join(temp_dir, os.path.basename(asset_path) + ".xml")
            if os.path.exists(xml_path):
                print(f"[AssetASAP] XML in temp — skipping download")
                def _skip():
                    props.status_message = "Importing (from temp)…"
                    return _do_import(
                        asset_path, None, temp_dir, props,
                        drawable_only, asset_browser, clean,
                    )
                bpy.app.timers.register(_skip, first_interval=0.0)
                return

            if use_cache:
                # YTD lookup is instant from cache — batch both in one download call
                ytd_path = _find_ytd_path(asset_path, port, use_cache)
                paths = [asset_path] + ([ytd_path] if ytd_path else [])
                ok, err = api.download_file(port, paths, temp_dir)
            else:
                # No cache: model download + YTD search run in parallel
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
                    fut_model = ex.submit(api.download_file, port, [asset_path], temp_dir)
                    fut_ytd   = ex.submit(_find_ytd_path, asset_path, port, use_cache)
                ok, err = fut_model.result()
                ytd_path = fut_ytd.result()
                if ok and ytd_path:
                    ok2, err2 = api.download_file(port, [ytd_path], temp_dir)
                    if not ok2:
                        print(f"[AssetASAP] YTD download failed (non-fatal): {err2}")

            def _after():
                if not ok:
                    props.status_message = f"Download error: {err}"
                    props.is_importing = False
                    return None
                props.status_message = "Importing…"
                return _do_import(
                    asset_path, ytd_path, temp_dir, props,
                    drawable_only, asset_browser, clean,
                )

            bpy.app.timers.register(_after, first_interval=0.0)

        threading.Thread(target=_thread, daemon=True).start()
        return {"FINISHED"}


class AS_OT_import_by_name(Operator):
    bl_idname = "as.import_by_name"
    bl_label = "Import Asset by Name"

    asset_name: bpy.props.StringProperty()

    def execute(self, context):
        # Fallback to current scene if context is empty (common in timers)
        scene = context.scene if context and context.scene else bpy.context.scene
        props = scene.as_props
        prefs = get_prefs()
        asset_name = self.asset_name

        if not asset_name:
            print("[AssetASAP] Error: No asset name provided to operator")
            return {"CANCELLED"}

        print(f"[AssetASAP] Starting import workflow for: {asset_name}")
        props.search_query = asset_name
        port = prefs.cw_api_port
        temp_dir = prefs.temp_dir
        use_cache = prefs.use_cache
        drawable_only = props.drawable_only
        asset_browser = props.send_to_asset_browser and drawable_only
        clean = props.clean_temp

        def _thread():
            print(f"[AssetASAP] [Thread] Searching for '{asset_name}' (Cache: {use_cache})...")
            if use_cache:
                cache_data = cache.load(cache.get_cache_path())
                if cache_data:
                    result, _ = cache.search_local(
                        cache_data, asset_name, extensions=MODEL_EXTENSIONS
                    )
                    ok = True
                else:
                    print("[AssetASAP] [Thread] Cache requested but not found, falling back to API.")
                    ok, result = api.search_file(
                        port, asset_name, extensions=MODEL_EXTENSIONS
                    )
            else:
                ok, result = api.search_file(
                    port, asset_name, extensions=MODEL_EXTENSIONS
                )

            if not ok or not result:
                print(f"[AssetASAP] [Thread] NOT FOUND: '{asset_name}' (Result: {result})")
                def _err():
                    bpy.context.scene.as_props.status_message = f"Not found: {asset_name}"
                    return None
                bpy.app.timers.register(_err, first_interval=0.0)
                return

            # Prefer .ydr or .yft
            best = next(
                (p for p in result if p.lower().endswith((".ydr", ".yft"))),
                result[0],
            )
            print(f"[AssetASAP] [Thread] Best match: {best}")

            # Skip download if XML already in temp from a previous import
            xml_path = os.path.join(temp_dir, os.path.basename(best) + ".xml")
            if os.path.exists(xml_path):
                print(f"[AssetASAP] [Thread] XML in temp — skipping download")
                def _skip():
                    p = bpy.context.scene.as_props
                    p.search_results.clear()
                    for path in result:
                        item = p.search_results.add()
                        item.name = path
                    p.status_message = "Importing (from temp)…"
                    p.is_importing = True
                    return _do_import(best, None, temp_dir, p, drawable_only, asset_browser, clean)
                bpy.app.timers.register(_skip, first_interval=0.0)
                return

            def _populate():
                p = bpy.context.scene.as_props
                p.search_results.clear()
                for path in result:
                    item = p.search_results.add()
                    item.name = path
                p.status_message = f"Downloading {os.path.basename(best)}…"
                p.is_importing = True
                return None

            bpy.app.timers.register(_populate, first_interval=0.0)

            if use_cache:
                ytd_path = _find_ytd_path(best, port, use_cache)
                paths = [best] + ([ytd_path] if ytd_path else [])
                print(f"[AssetASAP] [Thread] Downloading paths: {paths}")
                ok2, err = api.download_file(port, paths, temp_dir)
            else:
                print(f"[AssetASAP] [Thread] Parallel: downloading model + searching YTD")
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
                    fut_model = ex.submit(api.download_file, port, [best], temp_dir)
                    fut_ytd   = ex.submit(_find_ytd_path, best, port, use_cache)
                ok2, err = fut_model.result()
                ytd_path = fut_ytd.result()
                if ok2 and ytd_path:
                    print(f"[AssetASAP] [Thread] Downloading YTD: {ytd_path}")
                    ok3, err3 = api.download_file(port, [ytd_path], temp_dir)
                    if not ok3:
                        print(f"[AssetASAP] [Thread] YTD download failed (non-fatal): {err3}")

            def _after():
                p = bpy.context.scene.as_props
                if not ok2:
                    print(f"[AssetASAP] [Thread] Download error: {err}")
                    p.status_message = f"Download error: {err}"
                    p.is_importing = False
                    return None
                print(f"[AssetASAP] [Thread] Download successful, calling _do_import...")
                return _do_import(
                    best, ytd_path, temp_dir, p,
                    drawable_only, asset_browser, clean,
                )

            bpy.app.timers.register(_after, first_interval=0.0)

        threading.Thread(target=_thread, daemon=True).start()
        return {"FINISHED"}


class AS_OT_export_textures(Operator):
    bl_idname = "as.export_textures"
    bl_label = "Export Textures"
    bl_description = (
        "Copy the .dds textures that CodeWalker already extracted to the temp folder "
        "into the chosen destination folder"
    )

    def execute(self, context):
        props = context.scene.as_props
        prefs = get_prefs(context)
        obj = context.active_object

        if not obj:
            self.report({"WARNING"}, "No active object selected")
            return {"CANCELLED"}

        temp_dir = bpy.path.abspath(prefs.temp_dir)
        if not temp_dir or not os.path.isdir(temp_dir):
            self.report({"ERROR"}, "Temp directory is not set or does not exist")
            return {"CANCELLED"}

        out_dir = bpy.path.abspath(props.texture_export_dir)
        if not out_dir or not os.path.isdir(out_dir):
            self.report({"ERROR"}, "Select a valid destination folder first")
            return {"CANCELLED"}

        copied, failed = copy_textures_from_temp(obj, temp_dir, out_dir)

        for dst in copied:
            self.report({"INFO"}, f"Copied: {os.path.basename(dst)}")

        for name, reason in failed:
            self.report({"WARNING"}, f"Skipped '{name}': {reason}")

        if copied:
            props.status_message = f"Copied {len(copied)} texture(s) to {out_dir}"
        else:
            props.status_message = "No textures copied — check temp folder"

        return {"FINISHED"}


class AS_OT_clean_orphans(Operator):
    bl_idname = "as.clean_orphans"
    bl_label = "Clean Old Temp Files"
    bl_description = "Remove XML and DDS files older than 1 hour from the temp folder"

    def execute(self, context):
        prefs = get_prefs(context)
        temp_dir = bpy.path.abspath(prefs.temp_dir)
        if not temp_dir or not os.path.isdir(temp_dir):
            self.report({"ERROR"}, "Temp directory is not set or does not exist")
            return {"CANCELLED"}

        now = time.time()
        removed, freed = 0, 0
        for f in os.listdir(temp_dir):
            if not f.lower().endswith((".xml", ".dds")):
                continue
            fp = os.path.join(temp_dir, f)
            try:
                if now - os.path.getmtime(fp) > 3600:
                    freed += os.path.getsize(fp)
                    os.remove(fp)
                    removed += 1
            except Exception as e:
                print(f"[AssetASAP] Orphan cleanup error ({f}): {e}")

        if removed:
            self.report({"INFO"}, f"Removed {removed} files ({freed // 1024} KB freed)")
        else:
            self.report({"INFO"}, "No orphaned files found (all files younger than 1 hour)")
        return {"FINISHED"}


classes = [
    AS_OT_sync_config,
    AS_OT_build_cache,
    AS_OT_search,
    AS_OT_import,
    AS_OT_import_by_name,
    AS_OT_export_textures,
    AS_OT_clean_orphans,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
