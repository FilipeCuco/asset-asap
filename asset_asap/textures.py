import os
import shutil


def get_object_images(obj):
    """
    Return all unique Image datablocks used by the object's material nodes.
    Skips materials without nodes and nodes without an assigned image.
    """
    import bpy
    seen = {}
    if not obj:
        return []
    for slot in obj.material_slots:
        mat = slot.material
        if not mat or not mat.use_nodes:
            continue
        for node in mat.node_tree.nodes:
            if node.type == "TEX_IMAGE" and node.image:
                img = node.image
                seen[img.name] = img
    return list(seen.values())


def copy_textures_from_temp(obj, temp_dir, output_dir):
    """
    For each texture used by obj, look for the matching .dds file that
    CodeWalker already extracted to temp_dir, then copy it to output_dir.

    Image names in Blender after a Sollumz import typically match the
    original texture filenames (with or without the .dds extension).

    Returns:
        copied : list of destination file paths
        failed : list of (name, reason) tuples
    """
    images = get_object_images(obj)
    if not images:
        return [], [("(none)", "No textures found on this object")]

    copied = []
    failed = []

    for image in images:
        # Strip any extension Blender may have appended, then add .dds
        name_base = os.path.splitext(image.name)[0]
        dds_filename = name_base + ".dds"
        src = os.path.join(temp_dir, dds_filename)

        if not os.path.isfile(src):
            failed.append((dds_filename, f"Not found in temp dir: {src}"))
            continue

        dst = os.path.join(output_dir, dds_filename)
        try:
            shutil.copy2(src, dst)
            copied.append(dst)
        except Exception as e:
            failed.append((dds_filename, str(e)))

    return copied, failed
