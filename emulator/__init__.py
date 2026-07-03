import os
from pathlib import Path
from PIL import ImageFont

from common.fonts import FONTS_DIR

_orig_truetype = ImageFont.truetype


def _resolve_truetype(font=None, size=10, **kwargs):
    if isinstance(font, str) and not Path(font).is_absolute() and not Path(font).exists():
        candidate = FONTS_DIR / font
        if candidate.exists():
            font = str(candidate)
    return _orig_truetype(font, size, **kwargs)


ImageFont.truetype = _resolve_truetype
