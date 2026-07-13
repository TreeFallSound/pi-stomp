"""Dialog colour schemes derived from plugin category colours.

``scheme_for_category`` is the single entry point — used by ``PluginWindow``
to tint its title bar and outline to match the plugin's category. System menus
pass ``None`` and get the fixed default look.
"""

from __future__ import annotations

from pistomp.category import get_category_color
from uilib.dialog import DialogScheme
from uilib.misc import shade_color


def scheme_for_category(category: str | None) -> DialogScheme | None:
    """Return a ``DialogScheme`` tinted to *category*, or None for the default look.

    The accent colour is the category colour from ``get_category_color``.
    The title bar background is a dimmed version of the accent.
    The outline matches the accent.
    Title text stays white for contrast.
    """
    if category is None:
        return None
    accent = get_category_color(category)
    return DialogScheme(
        title_fgnd=(255, 255, 255),
        title_bkgnd=shade_color(accent, 0.3),
        outline_color=accent,
        accent=accent,
    )
