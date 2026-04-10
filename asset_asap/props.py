import bpy


class AS_DlcItem(bpy.types.PropertyGroup):
    """Single DLC entry in the DLC browser list."""
    name: bpy.props.StringProperty()
    ydr_count: bpy.props.IntProperty(default=0)
    yft_count: bpy.props.IntProperty(default=0)
    total: bpy.props.IntProperty(default=0)


class AS_Properties(bpy.types.PropertyGroup):
    # ── DLC Browser ──────────────────────────────────
    dlc_list: bpy.props.CollectionProperty(type=AS_DlcItem)
    active_dlc_index: bpy.props.IntProperty(default=0)
    dlc_import_progress: bpy.props.StringProperty(default="")
    is_importing_dlc: bpy.props.BoolProperty(default=False)
    import_filter: bpy.props.EnumProperty(
        name="File Types",
        description="Choose which model types to import",
        items=[
            ("BOTH", "YDR + YFT", "Import both .ydr and .yft files"),
            ("YDR", "YDR Only", "Import only .ydr files (drawables)"),
            ("YFT", "YFT Only", "Import only .yft files (fragments)"),
        ],
        default="BOTH",
    )
    asset_category: bpy.props.EnumProperty(
        name="Category",
        description="Filter assets by category based on RPF folder structure",
        items=[
            ("ALL", "All", "Import all assets"),
            ("VEHICLES", "Vehicles", "Import only vehicle models (merges meshes)"),
            ("PEDS", "Peds", "Import only ped models (merges meshes)"),
            ("PROPS", "Props", "Import only non-vehicle/non-ped assets"),
        ],
        default="ALL",
    )

    # ── Options ──────────────────────────────────────
    clean_temp: bpy.props.BoolProperty(
        name="Clean Temp After Import",
        description="Delete temporary XML files after import completes",
        default=True,
    )


    # ── Internal state ───────────────────────────────
    cache_info: bpy.props.StringProperty(default="")
    status_message: bpy.props.StringProperty(default="Ready")
    is_importing: bpy.props.BoolProperty(default=False)
    is_building_cache: bpy.props.BoolProperty(default=False)
    server_running: bpy.props.BoolProperty(default=False)


classes = [AS_DlcItem, AS_Properties]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.as_props = bpy.props.PointerProperty(type=AS_Properties)
    bpy.types.Scene.as_active_dlc_index = bpy.props.IntProperty()


def unregister():
    del bpy.types.Scene.as_props
    del bpy.types.Scene.as_active_dlc_index
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
