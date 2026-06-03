import os
from pathlib import Path
from PIL import ImageFont

_FONTS_DIR = Path(__file__).parent.parent / "fonts"
_orig_truetype = ImageFont.truetype


def _resolve_truetype(font=None, size=10, **kwargs):
    if isinstance(font, str) and not Path(font).is_absolute() and not Path(font).exists():
        candidate = _FONTS_DIR / font
        if candidate.exists():
            font = str(candidate)
    return _orig_truetype(font, size, **kwargs)


ImageFont.truetype = _resolve_truetype
