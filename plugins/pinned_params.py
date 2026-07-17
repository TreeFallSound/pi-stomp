"""Explicit pinned-param customizations for plugins whose LV2 port order
doesn't put the most useful controls in the first 4 slots."""

from __future__ import annotations

from common.parameter import Symbol
from modalapi.plugin_customization import PinnedParam
from plugins.customization import PluginCustomization, register
from plugins.mixer.panel import MixerPanel

SYSTEM_COMPRESSOR_URI = "http://moddevices.com/plugins/mod-devel/System-Compressor"
COLLISION_DRIVE_URI = "https://github.com/brummer10/CollisionDrive"
CAPS_AMPVTS_URI = "http://moddevices.com/plugins/caps/AmpVTS"
BOLLIEDELAY_URI = "https://ca9.eu/lv2/bolliedelay"
BOLLIEDELAYXT_URI = "https://ca9.eu/lv2/bolliedelayxt"
TAP_DYNAMICS_URI = "http://moddevices.com/plugins/tap/dynamics"
TAP_DYNAMICS_ST_URI = "http://moddevices.com/plugins/tap/dynamics-st"
MOD_MIXER_URI = "http://moddevices.com/plugins/mod-devel/mixer"
MOD_MIXER_STEREO_URI = "http://moddevices.com/plugins/mod-devel/mixer-stereo"
TAP_CHORUSFLANGER_URI = "http://moddevices.com/plugins/tap/chorusflanger"
GX_AMP_URI = "http://guitarix.sourceforge.net/plugins/gx_amp#GUITARIX"
GX_AMP_ST_URI = "http://guitarix.sourceforge.net/plugins/gx_amp_stereo#GUITARIX_ST"
KUIZA_URI = "http://www.openavproductions.com/artyfx#kuiza"

register(
    SYSTEM_COMPRESSOR_URI,
    customization=PluginCustomization(
        display_name="System Compressor",
        pinned_params=(
            PinnedParam(Symbol("COMP_MODE"), "Mode"),
            PinnedParam(Symbol("RELEASE"), "Release"),
            PinnedParam(Symbol("MASTER_VOL"), "Volume"),
        ),
    ),
)

register(
    COLLISION_DRIVE_URI,
    customization=PluginCustomization(
        display_name="Collision Drive",
        pinned_params=(
            PinnedParam(Symbol("DRIVE"), "Drive"),
            PinnedParam(Symbol("LEVEL"), "Level"),
            PinnedParam(Symbol("BRIGHT"), "Bright"),
            PinnedParam(Symbol("GATE"), "Gate"),
        ),
    ),
)

register(
    CAPS_AMPVTS_URI,
    customization=PluginCustomization(
        display_name="C* AmpVTS",
        pinned_params=(
            PinnedParam(Symbol("gain"), "Gain"),
            PinnedParam(Symbol("bass"), "Bass"),
            PinnedParam(Symbol("mid"), "Mid"),
            PinnedParam(Symbol("treble"), "Treble"),
        ),
    ),
)

register(
    BOLLIEDELAY_URI,
    customization=PluginCustomization(
        display_name="BollieDelay",
        pinned_params=(
            PinnedParam(Symbol("mix"), "Mix"),
            PinnedParam(Symbol("feedback"), "Feedback"),
            PinnedParam(Symbol("crossf"), "Crossfeed"),
            PinnedParam(Symbol("tempo_mode"), "Tempo"),
        ),
    ),
)

register(
    BOLLIEDELAYXT_URI,
    customization=PluginCustomization(
        display_name="BollieDelay XT",
        pinned_params=(
            PinnedParam(Symbol("CP_FB"), "Feedback"),
            PinnedParam(Symbol("CP_CF"), "Crossfeed"),
            PinnedParam(Symbol("CP_GAIN_DRY"), "Dry"),
            PinnedParam(Symbol("CP_GAIN_WET"), "Wet"),
        ),
    ),
)

register(
    TAP_DYNAMICS_URI,
    TAP_DYNAMICS_ST_URI,
    customization=PluginCustomization(
        display_name="TAP Dynamics",
        pinned_params=(
            PinnedParam(Symbol("attack"), "Attack"),
            PinnedParam(Symbol("release"), "Release"),
            PinnedParam(Symbol("offset"), "Offset"),
            PinnedParam(Symbol("makeup"), "Makeup"),
        ),
    ),
)

register(
    MOD_MIXER_URI,
    MOD_MIXER_STEREO_URI,
    customization=PluginCustomization(
        display_name="Mixer",
        panel_cls=MixerPanel,
        pinned_params=(
            PinnedParam(Symbol("Volume1"), "Ch 1"),
            PinnedParam(Symbol("Volume2"), "Ch 2"),
            PinnedParam(Symbol("Volume3"), "Ch 3"),
            PinnedParam(Symbol("Volume4"), "Ch 4"),
        ),
    ),
)

register(
    TAP_CHORUSFLANGER_URI,
    customization=PluginCustomization(
        display_name="TAP Chorus/Flanger",
        pinned_params=(
            PinnedParam(Symbol("Frequency"), "Rate"),
            PinnedParam(Symbol("Depth"), "Depth"),
            PinnedParam(Symbol("Delay"), "Delay"),
            PinnedParam(Symbol("Contour"), "Contour"),
        ),
    ),
)

register(
    GX_AMP_URI,
    GX_AMP_ST_URI,
    customization=PluginCustomization(
        display_name="Gx Amp",
        pinned_params=(
            PinnedParam(Symbol("PreGain"), "PreGain"),
            PinnedParam(Symbol("Drive"), "Drive"),
            PinnedParam(Symbol("MasterGain"), "Master"),
            PinnedParam(Symbol("Presence"), "Presence"),
        ),
    ),
)

register(
    KUIZA_URI,
    customization=PluginCustomization(
        display_name="Kuiza",
        pinned_params=(
            PinnedParam(Symbol("Low"), "Low"),
            PinnedParam(Symbol("Lo_Mid"), "LoMid"),
            PinnedParam(Symbol("Hi_Mid"), "HiMid"),
            PinnedParam(Symbol("High"), "High"),
        ),
    ),
)
