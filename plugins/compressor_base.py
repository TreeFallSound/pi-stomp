from __future__ import annotations

import logging
from dataclasses import dataclass

from common.contexts import (
    BindingDecl,
    ContextKind,
    ContextRef,
    ControlClass,
    ControlRef,
    EventKind,
    ParamEffect,
    SelectionEditEffect,
)
from common.parameter import Symbol
from pistomp.compmeter.client import GrMeterClient
from plugins.fullscreen import FullscreenPluginPanel
from plugins.layouts.arc_column import ArcColumnWidget, ArcSelectable
from plugins.layouts.compressor_spec import CompressorSpec, build_arc_specs
from plugins.layouts.gr_bar import GrBarWidget
from plugins.layouts.reticule_graph import ReticuleGraphWidget
from uilib.box import Box
from uilib.config import Config


@dataclass(frozen=True)
class CompressorState:
    thr: float
    rat: float
    kn: float
    mak: float


_W = 320
_CONTENT_H = 210
_GRAPH_SIDE = 188
_GRAPH_X0 = _W - _GRAPH_SIDE
_COL_W = _GRAPH_X0
_GR_BAR_Y = 2
_GR_BAR_H = 14
_GRAPH_Y0 = _GR_BAR_Y + _GR_BAR_H + 4


class CompressorPanel(FullscreenPluginPanel[CompressorState]):
    SPEC: CompressorSpec = CompressorSpec(thr_sym=Symbol("thr"), rat_sym=Symbol("rat"), mak_sym=Symbol("mak"), kn_sym=Symbol("kn"))

    def snapshot_state(self) -> CompressorState:
        def _v(sym: Symbol | None, default: float) -> float:
            p = self.plugin.parameters.get(sym) if sym is not None else None
            return float(p.value) if p is not None else default

        spec = self.SPEC
        return CompressorState(
            thr=_v(spec.thr_sym, 0.0),
            rat=_v(spec.rat_sym, 4.0),
            kn=_v(spec.kn_sym, 0.0),
            mak=_v(spec.mak_sym, 0.0),
        )

    def apply_state(self, state: CompressorState) -> None:
        self._column.sync()
        self._graph.set_state(state.thr, state.rat, state.kn, state.mak)

    def build_widgets(self) -> None:
        cfg = Config()
        value_font = cfg.get_font("small")
        label_font = cfg.get_font("arc_label")
        axis_font = cfg.get_font("tiny")

        self._graph = ReticuleGraphWidget(
            box=Box.xywh(_GRAPH_X0, _GRAPH_Y0, _GRAPH_SIDE, _GRAPH_SIDE),
            font=axis_font,
            parent=self,
        )
        state = self.snapshot_state()
        self._graph.set_state(state.thr, state.rat, state.kn, state.mak)

        self._gr_bar = GrBarWidget(
            box=Box.xywh(_GRAPH_X0, _GR_BAR_Y, _GRAPH_SIDE, _GR_BAR_H),
            font=axis_font,
            parent=self,
        )

        self._arcs = build_arc_specs(self.SPEC)
        self._column = ArcColumnWidget(
            box=Box.xywh(0, 0, _COL_W, _CONTENT_H),
            owner=self,
            arcs=self._arcs,
            value_font=value_font,
            label_font=label_font,
            parent=self,
        )
        self._selectables: list[ArcSelectable] = []
        for i, spec in enumerate(self._arcs):
            sel = ArcSelectable(self, i, spec.symbol)
            self._selectables.append(sel)
            self.add_sel_widget(sel)

        self._last_bypassed = self.plugin.is_bypassed()
        self._refresh_bypass_style()
        self.sel_widget(self._selectables[0])

        self._meter: GrMeterClient | None = None

    def declare_bindings(self) -> tuple[BindingDecl, ...]:
        panel_ctx = ContextRef(kind=ContextKind.PANEL, name="compressor")
        # enc3 is chassis-labeled Tweak3/Volume; rat stays bound there as a
        # deliberate, explicit override (see ContextLayer.add in common/contexts.py).
        volume_ctx = ContextRef(kind=ContextKind.PANEL, name="compressor", override_volume=True)
        return (
            BindingDecl(
                control=ControlRef(cls=ControlClass.TWEAK, id=1),
                event_kind=EventKind.ROTATE,
                effects=(SelectionEditEffect(),),
                context=panel_ctx,
            ),
            BindingDecl(
                control=ControlRef(cls=ControlClass.TWEAK, id=2),
                event_kind=EventKind.ROTATE,
                effects=(ParamEffect(plugin=self.plugin, symbol=self.SPEC.thr_sym),),
                context=panel_ctx,
            ),
            BindingDecl(
                control=ControlRef(cls=ControlClass.VOLUME, id=3),
                event_kind=EventKind.ROTATE,
                effects=(ParamEffect(plugin=self.plugin, symbol=self.SPEC.rat_sym),),
                context=volume_ctx,
            ),
        )

    def edit_symbol(self, symbol: Symbol, rotations: int, multiplier: float = 1.0) -> bool:
        if not super().edit_symbol(symbol, rotations, multiplier):
            return False
        self._column.sync_symbol(symbol)
        state = self.snapshot_state()
        self._graph.set_state(state.thr, state.rat, state.kn, state.mak)
        return True

    def _reset_symbol(self, symbol: Symbol) -> None:
        snap = self.plugin.pedalboard_snapshot
        if symbol not in snap or self._is_symbol_locked(self.plugin.instance_id, symbol):
            return
        self.set_param(symbol, snap[symbol])
        self._column.sync_symbol(symbol)
        state = self.snapshot_state()
        self._graph.set_state(state.thr, state.rat, state.kn, state.mak)

    def set_param(self, symbol: Symbol, value: float) -> None:
        super().set_param(symbol, value)
        if symbol == self.SPEC.mak_sym and self._meter is not None:
            self._meter.set_makeup(value)

    def _select_widget_ref(self, w) -> None:
        super()._select_widget_ref(w)
        idx = w.index if isinstance(w, ArcSelectable) else None
        self._column.set_active_arc(idx)

    def tick(self) -> None:
        bypassed = self.plugin.is_bypassed()
        if bypassed != self._last_bypassed:
            self._last_bypassed = bypassed
            self._refresh_bypass_style()
        if self._meter is None:
            self._start_meter()
        if self._meter is not None:
            reading = self._meter.get_reading()
            if reading is not None:
                self._graph.set_reticule(reading.in_db, reading.out_db, reading.gr_db, reading.valid)
                self._gr_bar.set_gr(reading.gr_db if reading.valid else None)
            else:
                self._graph.set_reticule(-60.0, -60.0, 0.0, False)
                self._gr_bar.set_gr(None)
        super().tick()

    def _refresh_bypass_style(self) -> None:
        super()._refresh_bypass_style()
        bypassed = self.plugin.is_bypassed()
        self._graph.set_bypassed(bypassed)
        self._gr_bar.set_bypassed(bypassed)
        self._column.set_bypassed(bypassed)

    def destroy(self) -> None:
        self._stop_meter()
        super().destroy()

    def _start_meter(self) -> None:
        n = self.plugin.instance_number
        if n is None:
            return
        try:
            meter = GrMeterClient()
            in_port = f"effect_{n}:{self.SPEC.in_audio_sym}"
            out_port = f"effect_{n}:{self.SPEC.out_audio_sym}"
            meter.start(in_port, out_port, self.snapshot_state().mak)
            self._meter = meter
        except Exception as exc:
            logging.warning("compressor GR meter failed to start: %s", exc)
            self._meter = None

    def _stop_meter(self) -> None:
        if self._meter is not None:
            try:
                self._meter.stop()
            except Exception:
                pass
            self._meter = None
