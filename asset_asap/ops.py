import bpy
import concurrent.futures
import os
import time
import threading
from bpy.types import Operator
from . import api, cache
from .preferences import get_prefs
from .cache import MODEL_EXTENSIONS



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


def _is_vehicle_path(asset_path):
    """Return True if the asset path contains a 'vehicles' folder."""
    pl = asset_path.lower().replace("\\", "/")
    return "/vehicles/" in pl or pl.endswith("/vehicles")


def _is_ped_path(asset_path):
    """Return True if the asset path contains a 'peds' folder."""
    pl = asset_path.lower().replace("\\", "/")
    return "/peds/" in pl or pl.endswith("/peds")


def _collect_subtree(obj, result):
    """Recursively add all descendants of obj into result."""
    for child in obj.children:
        result.add(child)
        _collect_subtree(child, result)


def _merge_meshes(objects, final_name):
    """
    Join all MESH objects in the list into a single object.
    Returns the merged object or None.
    """
    meshes = [o for o in objects if o is not None and o.type == "MESH"]
    if not meshes:
        return None
    if len(meshes) == 1:
        meshes[0].name = final_name
        if meshes[0].data:
            meshes[0].data.name = final_name
        return meshes[0]

    # Deselect everything first
    bpy.ops.object.select_all(action="DESELECT")

    # Select all mesh parts and set the first as active
    for m in meshes:
        m.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]

    # Join into one
    bpy.ops.object.join()

    merged = bpy.context.active_object
    if merged:
        merged.name = final_name
        if merged.data:
            merged.data.name = final_name
        print(f"[AssetASAP]   merged {len(meshes)} meshes into '{final_name}'")
    return merged


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
        # Don't save on every single asset during batch — caller handles it
        return True, None
    else:
        return False, "Save the .blend file to persist the asset in the browser"


def _do_import_single(asset_path, ytd_path, temp_dir, clean, is_vehicle=False):
    """
    Import a single asset_path via Sollumz with drawable_only + asset_browser.
    If is_vehicle=True, merges all drawable meshes into a single object.
    Returns (success: bool, asset_name: str, warning: str | None).
    Must run on main thread.
    """
    print(f"[AssetASAP] _do_import_single: path={asset_path} vehicle={is_vehicle}")
    basename = os.path.basename(asset_path)
    xml_name = basename + ".xml"
    xml_path = os.path.join(temp_dir, xml_name)

    if not os.path.exists(xml_path):
        return False, basename, f"{xml_name} not found in temp dir"

    existing = set(bpy.context.scene.objects)

    try:
        result = bpy.ops.sollumz.import_assets(
            directory=temp_dir,
            files=[{"name": xml_name}],
        )
    except Exception as e:
        return False, basename, f"Sollumz error: {e}"

    if result != {"FINISHED"}:
        return False, basename, "Import failed (Sollumz returned non-FINISHED)"

    new_objs = [o for o in bpy.context.scene.objects if o not in existing]

    # Apply drawable_only — strips collisions and containers
    final_obj = _apply_drawable_only(new_objs, asset_path)

    # For vehicles: merge all remaining meshes into one object
    if is_vehicle and final_obj:
        asset_name_base = os.path.splitext(basename)[0]
        # Gather all mesh objects that were part of this import
        remaining = [o for o in bpy.context.scene.objects
                     if o not in existing and o.type == "MESH"]
        if not remaining and final_obj.type == "MESH":
            remaining = [final_obj]
        if len(remaining) > 1:
            final_obj = _merge_meshes(remaining, asset_name_base)
        elif remaining:
            final_obj = remaining[0]
            final_obj.name = asset_name_base
            if final_obj.data:
                final_obj.data.name = asset_name_base

    # Mark as asset for Asset Browser
    if final_obj:
        ok, warn = _mark_as_asset(final_obj)
        if not ok and warn:
            print(f"[AssetASAP]   Asset warning: {warn}")

    if clean:
        ytd_basename = os.path.basename(ytd_path) if ytd_path else None
        removed = _clean_temp_files(temp_dir, basename, ytd_basename)
        print(f"[AssetASAP] Clean temp: {removed} file(s) removed")

    asset_name = final_obj.name if final_obj else basename
    return True, asset_name, None


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


class AS_OT_load_dlcs(Operator):
    bl_idname = "as.load_dlcs"
    bl_label = "Load DLCs"
    bl_description = "Read the asset cache and list all available DLCs"

    def execute(self, context):
        props = context.scene.as_props
        cache_data = cache.load(cache.get_cache_path())

        if not cache_data:
            self.report({"ERROR"}, "No cache found — build the cache first")
            props.status_message = "No cache — build it first"
            return {"CANCELLED"}

        dlcs = cache.list_dlcs(cache_data, extensions=(".ydr", ".yft"))

        props.dlc_list.clear()
        for d in dlcs:
            item = props.dlc_list.add()
            item.name = d["name"]
            item.ydr_count = d["ydr_count"]
            item.yft_count = d["yft_count"]
            item.total = d["total"]

        props.status_message = f"Found {len(dlcs)} DLC(s)"
        return {"FINISHED"}


class AS_OT_import_dlc(Operator):
    bl_idname = "as.import_dlc"
    bl_label = "Import DLC"
    bl_description = (
        "Import all .ydr and .yft files from the selected DLC, "
        "including textures, and add them to the Asset Browser"
    )

    index: bpy.props.IntProperty()

    def execute(self, context):
        props = context.scene.as_props
        prefs = get_prefs(context)

        if props.is_importing_dlc:
            self.report({"WARNING"}, "A DLC import is already in progress")
            return {"CANCELLED"}

        if self.index >= len(props.dlc_list):
            self.report({"ERROR"}, "Invalid DLC index")
            return {"CANCELLED"}

        dlc_item = props.dlc_list[self.index]
        dlc_name = dlc_item.name
        temp_dir = prefs.temp_dir

        if not temp_dir or not os.path.isdir(temp_dir):
            self.report({"ERROR"}, "Temp directory is not set or does not exist")
            return {"CANCELLED"}

        if not bpy.data.filepath:
            self.report({"ERROR"}, "Save the .blend file first to use Asset Browser")
            return {"CANCELLED"}

        cache_data = cache.load(cache.get_cache_path())
        if not cache_data:
            self.report({"ERROR"}, "Cache not found — build it first")
            return {"CANCELLED"}

        # Determine which extensions to import based on user filter
        filt = props.import_filter
        if filt == "YDR":
            ext_filter = (".ydr",)
        elif filt == "YFT":
            ext_filter = (".yft",)
        else:
            ext_filter = (".ydr", ".yft")

        asset_files = cache.get_dlc_files(
            cache_data, dlc_name, extensions=ext_filter
        )

        if not asset_files:
            self.report({"WARNING"}, f"No files found in '{dlc_name}' for filter '{filt}'")
            return {"CANCELLED"}

        # Apply category filter (Vehicles / Peds / Props / All)
        category = props.asset_category
        if category == "VEHICLES":
            asset_files = [f for f in asset_files if _is_vehicle_path(f)]
        elif category == "PEDS":
            asset_files = [f for f in asset_files if _is_ped_path(f)]
        elif category == "PROPS":
            asset_files = [f for f in asset_files if not _is_vehicle_path(f) and not _is_ped_path(f)]

        if not asset_files:
            self.report({"WARNING"}, f"No {category.lower()} found in '{dlc_name}'")
            return {"CANCELLED"}

        # Auto-sync config so CodeWalker.API saves XMLs to the addon's temp_dir
        port = prefs.cw_api_port
        ok_sync, sync_msg = api.set_config(
            port=port,
            gta_path=prefs.gta_path,
            output_dir=temp_dir,
            enable_mods=prefs.enable_mods,
            dlc=prefs.dlc,
        )
        if not ok_sync:
            self.report({"ERROR"}, f"Config sync failed: {sync_msg}")
            return {"CANCELLED"}

        props.is_importing_dlc = True
        props.dlc_import_progress = f"Preparing {dlc_name} (0/{len(asset_files)})…"
        props.status_message = f"Importing DLC: {dlc_name}…"

        use_cache = prefs.use_cache
        clean = props.clean_temp
        total = len(asset_files)

        def _thread():
            successes = 0
            failures = 0

            for i, asset_path in enumerate(asset_files):
                basename = os.path.basename(asset_path)

                # Update progress on main thread
                def _progress(idx=i, name=basename):
                    p = bpy.context.scene.as_props
                    p.dlc_import_progress = f"Downloading {name} ({idx + 1}/{total})…"
                    return None
                bpy.app.timers.register(_progress, first_interval=0.0)

                # Skip if already imported as asset
                asset_name_check = os.path.splitext(basename)[0]
                # We can't check _is_already_asset from thread, so skip this check

                # Download model + YTD
                try:
                    xml_path = os.path.join(temp_dir, basename + ".xml")
                    if not os.path.exists(xml_path):
                        # Find YTD
                        ytd_path = _find_ytd_path(asset_path, port, use_cache)
                        paths = [asset_path] + ([ytd_path] if ytd_path else [])
                        ok, err = api.download_file(port, paths, temp_dir)
                        if not ok:
                            print(f"[AssetASAP] Download failed for {basename}: {err}")
                            failures += 1
                            continue
                    else:
                        ytd_path = None
                        print(f"[AssetASAP] XML in temp — skipping download for {basename}")

                except Exception as e:
                    print(f"[AssetASAP] Error downloading {basename}: {e}")
                    failures += 1
                    continue

                # Import on main thread and wait for it to complete
                import_done = threading.Event()
                import_result = [False, "", None]  # success, name, warning

                def _import(_ap=asset_path, _yp=ytd_path):
                    try:
                        merge = _is_vehicle_path(_ap) or _is_ped_path(_ap)
                        s, n, w = _do_import_single(_ap, _yp, temp_dir, clean, is_vehicle=merge)
                        import_result[0] = s
                        import_result[1] = n
                        import_result[2] = w
                    except Exception as e:
                        print(f"[AssetASAP] Import error: {e}")
                        import_result[0] = False
                    finally:
                        import_done.set()
                    return None

                bpy.app.timers.register(_import, first_interval=0.0)
                import_done.wait(timeout=120)  # 2 min max per asset

                if import_result[0]:
                    successes += 1
                else:
                    failures += 1
                    print(f"[AssetASAP] Failed to import {basename}: {import_result[2]}")

            # All done — save the blend file once and update UI
            def _finish():
                p = bpy.context.scene.as_props
                p.is_importing_dlc = False
                p.dlc_import_progress = ""

                # Save the .blend file once after all imports
                if bpy.data.filepath:
                    _ensure_catalog(bpy.data.filepath)
                    bpy.ops.wm.save_mainfile()

                msg = f"DLC '{dlc_name}': {successes} imported"
                if failures:
                    msg += f", {failures} failed"
                p.status_message = msg
                return None

            bpy.app.timers.register(_finish, first_interval=0.0)

        threading.Thread(target=_thread, daemon=True).start()
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
    AS_OT_load_dlcs,
    AS_OT_import_dlc,
    AS_OT_clean_orphans,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
