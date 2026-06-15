"""Footswitches render and navigate in physical slot order, regardless of the
plugin/binding order in the pedalboard, and that order survives a reload.

Black-box: bind real hardware footswitches via :bypass bindings, load through the
handler, then drive the universal encoder and watch which FootswitchWidget the
selection lands on. The snapshot guards the visual ordering of the strip.
"""
from uilib.footswitch import FootswitchWidget

# Footswitch slot -> MIDI CC, from default_config_pistomptre.yml.
SLOT_CC = {0: 60, 1: 61, 2: 62, 3: 63}


def _footswitch_nav_order(handler, lcd):
    """Rotate the universal encoder once around the main panel's selection ring
    and return the footswitch slot ids in the order the selection visits them."""
    flat = lcd.main_panel._flat_sel()
    order = []
    for _ in range(len(flat)):
        handler.universal_encoder_select(1)
        sel = lcd.main_panel.sel_ref
        if isinstance(sel, FootswitchWidget):
            order.append(sel.num)
    return order


def test_footswitch_order_stable_across_reload(v3_system, make_plugin, snapshot):
    handler = v3_system.handler
    lcd = handler.lcd
    ch = v3_system.hw.midi_channel
    board = handler.pedalboards["/path/to/rig.pedalboard"]

    def bound(instance_id, slot, category):
        # A plugin whose :bypass is bound to the footswitch in `slot`. binding is
        # the "<channel>:<cc>" key that bind_current_pedalboard resolves to the
        # hardware footswitch controller.
        p = make_plugin(instance_id, category=category, has_footswitch=True)
        p.parameters[":bypass"].binding = f"{ch}:{SLOT_CC[slot]}"
        return p

    # PB1: two switches bound, plugin order reversed vs slot order (slot 3 first).
    board.plugins = [bound("Echo", 3, "Delay"), bound("Fuzz", 1, "Distortion")]
    handler.set_current_pedalboard(board)
    snapshot("pb1")
    assert _footswitch_nav_order(handler, lcd) == [0, 1, 2, 3]

    # PB2: all four bound, scrambled plugin order. A regression that built widgets
    # in plugin order would navigate 2,0,3,1 here; slot order must stay 0,1,2,3.
    board.plugins = [
        bound("Verb", 2, "Reverb"),
        bound("Comp", 0, "Dynamics"),
        bound("Trem", 3, "Modulator"),
        bound("Drive", 1, "Distortion"),
    ]
    handler.set_current_pedalboard(board)
    snapshot("pb2")
    assert _footswitch_nav_order(handler, lcd) == [0, 1, 2, 3]
