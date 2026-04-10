import json
import urllib.request
import urllib.parse
import urllib.error


def get_base_url(port):
    return f"http://localhost:{port}/api"


def _get(url, params=None, timeout=30):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
            return r.status, data, None
    except urllib.error.HTTPError as e:
        return e.code, None, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return 0, None, f"Connection error: {e.reason}"
    except Exception as e:
        return 0, None, str(e)


def _post(url, payload, timeout=10):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8"), None
    except urllib.error.HTTPError as e:
        return e.code, None, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return 0, None, f"Connection error: {e.reason}"
    except Exception as e:
        return 0, None, str(e)


def search_file(port, filename, extensions=None, timeout=15):
    """
    Search for assets by filename substring.

    extensions: optional tuple/list of extensions to keep, e.g. (".ydr", ".yft").
    timeout: seconds before giving up (reduced from 30 to 15 for snappier feedback).
    """
    status, data, err = _get(
        f"{get_base_url(port)}/search-file",
        {"filename": filename},
        timeout=timeout,
    )
    if err:
        return False, err
    if status == 200:
        if extensions and isinstance(data, list):
            ext_tuple = tuple(extensions)
            data = [p for p in data if p.lower().endswith(ext_tuple)]
        return True, data
    return False, f"HTTP {status}"


def set_config(port, gta_path, output_dir, enable_mods=False, gen9=False, dlc=""):
    payload = {
        "GTAPath": gta_path,
        "CodewalkerOutputDir": output_dir,
        "EnableMods": enable_mods,
        "Gen9": gen9,
        "Dlc": dlc,
    }
    status, _, err = _post(f"{get_base_url(port)}/set-config", payload)
    if err:
        return False, err
    return status == 200, f"HTTP {status}"


def download_file(port, full_paths, output_dir):
    """
    Download one or more RPF assets and export them as XML.

    full_paths: str or list[str] — one or multiple asset paths to extract.
    """
    if isinstance(full_paths, str):
        full_paths = [full_paths]

    # urlencode with a list of tuples produces repeated keys: fullPaths=a&fullPaths=b
    params = [("fullPaths", p) for p in full_paths]
    params += [("xml", "true"), ("outputFolderPath", output_dir)]
    url = f"{get_base_url(port)}/download-files?" + urllib.parse.urlencode(params)

    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            return r.status == 200, None
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return False, f"Connection error: {e.reason}"
    except Exception as e:
        return False, str(e)
