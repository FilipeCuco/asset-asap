import bpy


class AS_SearchResult(bpy.types.PropertyGroup):
    """Single item in the search results list."""
    name: bpy.props.StringProperty()


def _on_search_query_update(self, context):
    """Clear the query cache whenever the search field changes."""
    self.last_query_text = ""


class AS_Properties(bpy.types.PropertyGroup):
    search_query: bpy.props.StringProperty(
        name="Asset Name",
        description="Name of the GTA V asset to search for",
        default="",
        update=_on_search_query_update,
    )
    search_results: bpy.props.CollectionProperty(type=AS_SearchResult)
    active_result_index: bpy.props.IntProperty(default=0)
    drawable_only: bpy.props.BoolProperty(
        name="Drawable Only",
        description=(
            "Import only the visual drawable — collisions and fragment wrapper are deleted. "
            "The drawable is renamed to match the fragment/file name"
        ),
        default=False,
    )
    send_to_asset_browser: bpy.props.BoolProperty(
        name="Add to Asset Browser",
        description=(
            "Mark the imported drawable as a Blender asset and save the file automatically. "
            "Only available when Drawable Only is enabled"
        ),
        default=False,
    )
    clean_temp: bpy.props.BoolProperty(
        name="Clean Temp After Import",
        description="Delete temporary XML files after import completes",
        default=True,
    )
    texture_export_dir: bpy.props.StringProperty(
        name="Export Folder",
        description="Folder where textures will be saved as .dds",
        subtype="DIR_PATH",
        default="",
    )
    cache_info: bpy.props.StringProperty(default="")
    status_message: bpy.props.StringProperty(default="Ready")
    is_searching: bpy.props.BoolProperty(default=False)
    is_importing: bpy.props.BoolProperty(default=False)
    is_building_cache: bpy.props.BoolProperty(default=False)
    server_running: bpy.props.BoolProperty(default=False)
    last_query_text: bpy.props.StringProperty(default="")
    total_results: bpy.props.IntProperty(default=0)


classes = [AS_SearchResult, AS_Properties]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.as_props = bpy.props.PointerProperty(type=AS_Properties)
    bpy.types.Scene.as_active_index = bpy.props.IntProperty()


def unregister():
    del bpy.types.Scene.as_props
    del bpy.types.Scene.as_active_index
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
