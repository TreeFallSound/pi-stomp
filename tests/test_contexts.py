# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

"""The per-control-class precedence resolver and the VOLUME opt-in guard.
See common/contexts.py's module docstring and ContextLayer.add."""

import pytest

from common.contexts import (
    BindingDecl,
    ContextKind,
    ContextLayer,
    ContextRef,
    ContextStack,
    ControlClass,
    ControlRef,
    EventKind,
    NoneEffect,
    ShadowState,
)


def _row(cls: ControlClass, ctx: ContextRef, event_kind=EventKind.ROTATE, control_id=1, enabled_when=None):
    return BindingDecl(
        control=ControlRef(cls=cls, id=control_id),
        event_kind=event_kind,
        effects=(NoneEffect(),),
        context=ctx,
        enabled_when=enabled_when,
    )


PEDALBOARD = ContextRef(kind=ContextKind.PEDALBOARD)


class TestResolvePrecedence:
    def test_panel_wins_over_pedalboard_for_tweak(self):
        panel_ctx = ContextRef(kind=ContextKind.PANEL, name="compressor")
        pedalboard_layer = ContextLayer(ref=PEDALBOARD)
        panel_layer = ContextLayer(ref=panel_ctx)
        pedalboard_row = _row(ControlClass.TWEAK, PEDALBOARD)
        panel_row = _row(ControlClass.TWEAK, panel_ctx)
        pedalboard_layer.add(pedalboard_row)
        panel_layer.add(panel_row)
        stack = ContextStack(layers=[pedalboard_layer, panel_layer])

        winner = stack.resolve(ControlRef(cls=ControlClass.TWEAK, id=1), EventKind.ROTATE)

        assert winner is panel_row
        assert panel_row.shadow_state == ShadowState.ACTIVE
        assert pedalboard_row.shadow_state == ShadowState.SHADOWED

    def test_panel_does_not_shadow_a_control_it_never_declares(self):
        """Panel-shadowing is per-(control, event_kind), never the whole class."""
        panel_ctx = ContextRef(kind=ContextKind.PANEL, name="compressor")
        pedalboard_layer = ContextLayer(ref=PEDALBOARD)
        panel_layer = ContextLayer(ref=panel_ctx)
        pedalboard_row_2 = _row(ControlClass.TWEAK, PEDALBOARD, control_id=2)
        panel_layer.add(_row(ControlClass.TWEAK, panel_ctx, control_id=1))
        pedalboard_layer.add(pedalboard_row_2)
        stack = ContextStack(layers=[pedalboard_layer, panel_layer])

        winner = stack.resolve(ControlRef(cls=ControlClass.TWEAK, id=2), EventKind.ROTATE)

        assert winner is pedalboard_row_2
        assert pedalboard_row_2.shadow_state == ShadowState.ACTIVE

    def test_analog_has_no_panel_chain_entry(self):
        """ANALOG is pedalboard-scoped only; a PANEL row can't even be consulted
        because the chain for ANALOG skips PANEL entirely."""
        panel_ctx = ContextRef(kind=ContextKind.PANEL, name="graphic_eq")
        pedalboard_layer = ContextLayer(ref=PEDALBOARD)
        panel_layer = ContextLayer(ref=panel_ctx)
        pedalboard_row = _row(ControlClass.ANALOG, PEDALBOARD)
        pedalboard_layer.add(pedalboard_row)
        stack = ContextStack(layers=[pedalboard_layer, panel_layer])

        winner = stack.resolve(ControlRef(cls=ControlClass.ANALOG, id=1), EventKind.ROTATE)

        assert winner is pedalboard_row

    def test_disabled_row_falls_through_to_lower_context(self):
        panel_ctx = ContextRef(kind=ContextKind.PANEL, name="nam")
        pedalboard_layer = ContextLayer(ref=PEDALBOARD)
        panel_layer = ContextLayer(ref=panel_ctx)
        pedalboard_row = _row(ControlClass.TWEAK, PEDALBOARD)
        disabled_row = _row(ControlClass.TWEAK, panel_ctx, enabled_when=lambda: False)
        pedalboard_layer.add(pedalboard_row)
        panel_layer.add(disabled_row)
        stack = ContextStack(layers=[pedalboard_layer, panel_layer])

        winner = stack.resolve(ControlRef(cls=ControlClass.TWEAK, id=1), EventKind.ROTATE)

        assert winner is pedalboard_row

    def test_no_matching_row_returns_none(self):
        stack = ContextStack(layers=[ContextLayer(ref=PEDALBOARD)])

        assert stack.resolve(ControlRef(cls=ControlClass.TWEAK, id=1), EventKind.ROTATE) is None


class TestVolumeOptIn:
    def test_panel_volume_row_rejected_without_override(self):
        panel_ctx = ContextRef(kind=ContextKind.PANEL, name="compressor")
        layer = ContextLayer(ref=panel_ctx)

        with pytest.raises(ValueError, match="override_volume"):
            layer.add(_row(ControlClass.VOLUME, panel_ctx))

    def test_panel_volume_row_accepted_with_override(self):
        panel_ctx = ContextRef(kind=ContextKind.PANEL, name="compressor", override_volume=True)
        layer = ContextLayer(ref=panel_ctx)

        layer.add(_row(ControlClass.VOLUME, panel_ctx))  # does not raise

        assert layer.rows[(ControlClass.VOLUME, EventKind.ROTATE)]

    def test_pedalboard_volume_row_needs_no_override(self):
        layer = ContextLayer(ref=PEDALBOARD)

        layer.add(_row(ControlClass.VOLUME, PEDALBOARD))  # does not raise
