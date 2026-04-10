import json
import os
import time

ASSET_EXTENSIONS = (".ydr", ".yft", ".ydd", ".ybn", ".ytd")
MODEL_EXTENSIONS = (".ydr", ".yft", ".ydd", ".ybn")
_CACHE_FILE = "asset_spawner_cache.json"
_SEARCH_CACHE_FILE = "search_cache.json"


def _get_data_dir():
    import bpy
    return bpy.utils.user_resource("DATAFILES", path=__package__, create=True)


def get_cache_path():
    """Returns the asset cache file path in the persistent addon data folder."""
    return os.path.join(_get_data_dir(), _CACHE_FILE)


def get_search_cache_path():
    """Returns the search cache file path in the persistent addon data folder."""
    return os.path.join(_get_data_dir(), _SEARCH_CACHE_FILE)


def save_search_cache(query, results, total):
    """Persist the last search query and results to disk."""
    data = {
        "query": query,
        "results": results,
        "total": total,
        "saved_at": time.time(),
    }
    try:
        with open(get_search_cache_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"))
    except Exception as e:
        print(f"[AssetASAP] Failed to save search cache: {e}")


def load_search_cache():
    """Load the persisted search cache. Returns dict or None if missing/corrupt."""
    try:
        with open(get_search_cache_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def load(cache_path):
    """Returns the full cache dict or None if missing/corrupt."""
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def cache_info_str(cache_path):
    """One-line summary for UI display. Empty string if no cache."""
    data = load(cache_path)
    if not data:
        return ""
    ts = time.strftime("%d/%m/%Y %H:%M", time.localtime(data.get("built_at", 0)))
    count = data.get("count", 0)
    return f"{count:,} assets  ({ts})"


def _save(cache_path, files):
    dir_ = os.path.dirname(cache_path)
    if dir_:
        os.makedirs(dir_, exist_ok=True)
    data = {
        "built_at": time.time(),
        "count": len(files),
        "files": files,
    }
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    return data


def search_local(cache_data, query, extensions=None, limit=200):
    """Substring search over local cache with relevance sorting and result limit.

    Returns (results, total) where results is capped at limit and total is the
    full match count before limiting. extensions filters by file extension.
    """
    q = query.lower()
    files = cache_data["files"]
    if extensions:
        ext_tuple = tuple(extensions)
        files = [f for f in files if f.lower().endswith(ext_tuple)]

    exact, starts, contains = [], [], []
    for f in files:
        b = os.path.splitext(os.path.basename(f))[0].lower()
        if b == q:
            exact.append(f)
        elif b.startswith(q):
            starts.append(f)
        elif q in os.path.basename(f).lower():
            contains.append(f)

    ranked = exact + starts + contains
    return ranked[:limit], len(ranked)


def find_ytd(cache_data, asset_path):
    """
    Return the best matching .ytd path for a model asset, or None.
    Prefers a .ytd in the same directory as the asset.
    """
    basename = os.path.splitext(os.path.basename(asset_path))[0].lower()
    asset_dir = os.path.dirname(asset_path).lower()
    ytd_suffix = basename + ".ytd"

    candidates = [f for f in cache_data["files"] if f.lower().endswith(ytd_suffix)]
    if not candidates:
        return None
    same_dir = [c for c in candidates if os.path.dirname(c).lower() == asset_dir]
    return same_dir[0] if same_dir else candidates[0]


def build(port, progress_cb=None):
    """
    Build the local cache by querying the API for all asset extensions in parallel.

    All 5 extension queries run simultaneously via ThreadPoolExecutor, reducing
    total build time from ~sum(all requests) to ~max(slowest request).

    progress_cb(current, total, label) is called from the worker thread;
    callers are responsible for marshalling UI updates via bpy.app.timers.

    Returns (ok: bool, message: str).
    """
    import concurrent.futures
    from . import api

    exts = list(ASSET_EXTENSIONS)
    all_files = set()
    completed = 0

    def _fetch(ext):
        return ext, api.search_file(port, ext, timeout=120)

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(exts)) as ex:
        futures = {ex.submit(_fetch, ext): ext for ext in exts}
        for fut in concurrent.futures.as_completed(futures):
            ext, (ok, result) = fut.result()
            completed += 1
            if progress_cb:
                progress_cb(completed, len(exts), ext)
            if ok and isinstance(result, list):
                for path in result:
                    if path.lower().endswith(tuple(ASSET_EXTENSIONS)):
                        all_files.add(path)

    if not all_files:
        return False, "No assets found — is CodeWalker.API running and configured?"

    path = get_cache_path()
    _save(path, sorted(all_files))
    return True, f"Cached {len(all_files):,} assets"
