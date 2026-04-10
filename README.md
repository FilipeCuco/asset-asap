# Asset ASAP — GTA V Asset Importer for Blender

Import GTA V assets directly into Blender from RPF archives via [CodeWalker API](https://www.gta5-mods.com/tools/codewalker-api). Search, preview and import `.ydr`, `.yft`, `.ydd`, `.ybn` and `.ytd` files without ever leaving Blender — or send assets straight from [PlebMasters Forge](https://forge.plebmasters.de) with one click using the Chrome extension.

---

## Requirements

| Requirement | Version |
|---|---|
| Blender | 3.0 or newer |
| [Sollumz](https://github.com/Sollumz/Sollumz) | Latest |
| [CodeWalker API](https://www.gta5-mods.com/tools/codewalker-api) | Latest |
| GTA V | Any version |

---

## Installation

### 1. CodeWalker API

Download and run **CodeWalker API** from [gta5-mods.com](https://www.gta5-mods.com/tools/codewalker-api). This tool exposes a local REST API that reads GTA V's RPF archives and extracts assets on demand.

Keep it running in the background while using Asset ASAP.

### 2. Blender Addon

1. Download `asset_asap.zip` from the [latest release](../../releases/latest)
2. In Blender, go to **Edit → Preferences → Add-ons → Install**
3. Select the downloaded `asset_asap.zip`
4. Enable **Asset ASAP — GTA V via CodeWalker.API**

### 3. Chrome Extension (optional)

The extension adds a **Send to Blender** button on [PlebMasters Forge](https://forge.plebmasters.de), letting you import any asset with a single click.

1. Download `chrome_extension.zip` from the [latest release](../../releases/latest) and extract it
2. Open Chrome and go to `chrome://extensions`
3. Enable **Developer mode** (top right toggle)
4. Click **Load unpacked**
5. Select the extracted `chrome_extension` folder

---

## Configuration

Open **Edit → Preferences → Add-ons → Asset ASAP** and fill in:

| Setting | Description |
|---|---|
| **GTA V Path** | Root folder of your GTA V installation |
| **Temp Directory** | Folder where extracted XML/DDS files are stored temporarily |
| **CodeWalker API Port** | Port where CodeWalker API is listening (default: `5555`) |
| **Enable Mods** | Include modded content in searches |
| **DLC Override** | Optional DLC name (e.g. `patchday24ng`). Leave blank for base game |

After filling in the paths, click **Sync Config to API** to apply settings to CodeWalker API.

---

## Usage

### Searching and Importing

1. Open the **Asset ASAP** panel in the 3D Viewport sidebar (`N` key → **Asset ASAP** tab)
2. Type an asset name in the **Search Asset** field (e.g. `prop_tree_cedar`)
3. Click the search icon or press Enter
4. Click **Import** next to any result

### Import Options

| Option | Description |
|---|---|
| **Drawable Only** | Imports only the visible mesh — removes collision, fragment wrapper and armature |
| **Add to Asset Browser** | Marks the imported object as a Blender asset (requires Drawable Only) |
| **Clean Temp After Import** | Deletes temporary XML and DDS files from the temp folder after import |

### Asset Cache

For instant search results without querying CodeWalker API each time:

1. Open the **Asset Cache** panel (inside Asset ASAP sidebar)
2. Enable **Use Cache for Search**
3. Click **Build Cache** — this queries all asset types once and stores them locally

The cache is saved persistently and survives Blender restarts. Rebuild only when your GTA V installation or mods change.

### Exporting Textures

1. Import an asset
2. Select the imported object
3. Open the **Textures** panel in the Asset ASAP sidebar
4. Choose a destination folder
5. Click **Copy Textures**

### Cleaning Old Temp Files

Open the **Configuration** panel in the sidebar and click **Clean Old Temp Files** to remove XML and DDS files older than 1 hour from the temp folder.

---

## Chrome Extension

With the extension loaded, browse [PlebMasters Forge](https://forge.plebmasters.de):

- A **Send to Blender** button appears on individual asset pages
- A smaller **Send** button appears on each asset card in list view

Clicking either button sends the asset name directly to Blender and triggers an automatic import. Blender and CodeWalker API must both be running.

---

## Project Structure

```
asset_asap/          Blender addon
  __init__.py        Addon entry point and registration
  api.py             CodeWalker API HTTP client
  cache.py           Local asset cache (build, search, persist)
  ops.py             Blender operators (search, import, clean)
  props.py           Scene properties
  preferences.py     Addon preferences
  ui.py              Sidebar panels
  server.py          Local HTTP server for Chrome extension
  textures.py        Texture export utilities

chrome_extension/    Chrome extension
  manifest.json
  content.js         Injects Send to Blender buttons on Forge
```

---

## Contributing

Pull requests are welcome. The addon is written in pure Python against the Blender API — no build step required. Load the `asset_asap` folder directly as an unpacked addon during development.

---

## License

MIT
