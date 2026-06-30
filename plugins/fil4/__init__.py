"""On-device UI for the x42-eq (fil4) parametric EQ plugin."""

from plugins.customization import PluginCustomization, register
from plugins.fil4.panel import Fil4Panel

FIL4_MONO_URI = "http://gareus.org/oss/lv2/fil4#mono"
FIL4_STEREO_URI = "http://gareus.org/oss/lv2/fil4#stereo"
FIL4_URIS = (FIL4_MONO_URI, FIL4_STEREO_URI)

register(*FIL4_URIS, customization=PluginCustomization(panel_cls=Fil4Panel))
