"""Cover image URLs on IGDB's image server, built from a stored cover image ID.

This is the one cover URL builder, used by templates (and by the API in Phase 10).
Covers are hotlinked, never downloaded or re-hosted.
"""

IGDB_IMAGE_BASE = "https://images.igdb.com/igdb/image/upload"

# Our size names -> IGDB image sizes (cover_small is 90x128, cover_big is 264x374).
SIZES = {
    "small": "cover_small",
    "small_2x": "cover_small_2x",
    "large": "cover_big",
}

# Rendered <img> width and height for each display size, reserving layout space.
DIMENSIONS = {
    "small": (90, 128),
    "large": (264, 374),
}

# Display sizes that get a high-DPI source, and the size name used for it.
HIGH_DPI = {"small": "small_2x"}

PLACEHOLDER_STATIC_PATH = "games/img/cover-placeholder.svg"


def cover_url(image_id, size):
    """The IGDB image URL for `image_id` at `size`, or None when there's no cover ID."""
    if not image_id:
        return None
    return f"{IGDB_IMAGE_BASE}/t_{SIZES[size]}/{image_id}.jpg"
