"""`{% cover_img game "small" %}`: the one cover <img> used on every page."""

from django import template
from django.templatetags.static import static

from games.covers import DIMENSIONS, HIGH_DPI, PLACEHOLDER_STATIC_PATH, cover_url

register = template.Library()


@register.inclusion_tag("games/_cover_img.html")
def cover_img(game, size):
    """A fixed-size, lazy-loaded cover, or the local placeholder when there's no ID.

    Remote covers carry the placeholder URL in `data-cover-placeholder` for the
    fallback script (games/js/cover-fallback.js). The placeholder itself doesn't.
    """
    width, height = DIMENSIONS[size]
    placeholder = static(PLACEHOLDER_STATIC_PATH)
    src = cover_url(game.cover_image_id, size)
    srcset = ""
    fallback = ""
    if src is None:
        src = placeholder
    else:
        fallback = placeholder
        if size in HIGH_DPI:
            srcset = f"{cover_url(game.cover_image_id, HIGH_DPI[size])} 2x"
    return {
        "src": src,
        "srcset": srcset,
        "fallback": fallback,
        "width": width,
        "height": height,
        "alt": game.name,
    }
