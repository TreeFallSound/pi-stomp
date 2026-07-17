"""Registration for the rkr Parametric EQ (eqp) plugin."""

from plugins.customization import PluginCustomization, register
from plugins.eqp.panel import RkrParametricEqPanel

register(
    "http://rakarrack.sourceforge.net/effects.html#eqp",
    customization=PluginCustomization(
        panel_cls=RkrParametricEqPanel,
        display_name="rkr Parametric EQ",
    ),
)
