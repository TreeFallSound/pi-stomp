"""Tests for the selection-tree API on Widget + Panel.

Verifies that any entry in Panel.sel_list is treated as a subtree,
lazily expanded via Widget.sel_children() into a flat list of leaves.
The default leaf returns [self]. Containers override to yield their
grouped selectables in their own iteration order.

These tests pin the contract independently of any GridPanel specifics.
"""

from __future__ import annotations

import pytest

from uilib.box import Box
from uilib.misc import InputEvent
from uilib.panel import LcdBase, Panel, PanelStack
from uilib.text import TextWidget
from uilib.widget import Widget


class _StubLcd(LcdBase):
    def dimensions(self):
        return (320, 240)

    def default_format(self):
        return "RGB"

    def update(self, image, box=None):
        pass


@pytest.fixture
def panel_stack():
    return PanelStack(_StubLcd(), use_dimming=False)


@pytest.fixture
def panel(panel_stack):
    p = Panel(box=Box.xywh(0, 0, 320, 240))
    panel_stack.push_panel(p, refresh=False)
    return p


def _txt(panel, label):
    return TextWidget(box=Box.xywh(0, 0, 10, 10), text=label, parent=panel)


class _Group(Widget):
    """A minimal container that groups child leaves and yields them in a
    caller-specified order via sel_children()."""

    def __init__(self, box, parent, members_order):
        super().__init__(box=box, parent=parent)
        self.members_order = members_order

    def sel_children(self):
        return list(self.members_order)


# --------------------------------------------------------------------------- #
# Defaults: every widget is its own leaf.
# --------------------------------------------------------------------------- #


def test_widget_sel_children_default_is_self(panel):
    w = _txt(panel, "x")
    assert list(w.sel_children()) == [w]


def test_flat_sel_of_only_leaves_matches_sel_list(panel):
    a, b, c = (_txt(panel, n) for n in "abc")
    for w in (a, b, c):
        panel.add_sel_widget(w)
    assert panel._flat_sel() == [a, b, c]


# --------------------------------------------------------------------------- #
# Subtree expansion + nav.
# --------------------------------------------------------------------------- #


def test_flat_sel_expands_subtree_in_place(panel):
    a, b, c, d = (_txt(panel, n) for n in "abcd")
    group = _Group(Box.xywh(0, 0, 10, 10), panel, [b, c])
    panel.add_sel_widget(a)
    panel.add_sel_widget(group)
    panel.add_sel_widget(d)
    assert panel._flat_sel() == [a, b, c, d]


def test_sel_next_walks_into_and_out_of_subtree(panel):
    a, b, c, d = (_txt(panel, n) for n in "abcd")
    group = _Group(Box.xywh(0, 0, 10, 10), panel, [b, c])
    panel.add_sel_widget(a)
    panel.add_sel_widget(group)
    panel.add_sel_widget(d)
    assert panel.sel_ref is a
    panel.sel_next()
    assert panel.sel_ref is b
    panel.sel_next()
    assert panel.sel_ref is c
    panel.sel_next()
    assert panel.sel_ref is d
    panel.sel_next()
    assert panel.sel_ref is a  # wraps


def test_sel_prev_is_symmetric(panel):
    a, b, c = (_txt(panel, n) for n in "abc")
    group = _Group(Box.xywh(0, 0, 10, 10), panel, [b])
    panel.add_sel_widget(a)
    panel.add_sel_widget(group)
    panel.add_sel_widget(c)
    panel.sel_widget(c)
    panel.sel_prev()
    assert panel.sel_ref is b
    panel.sel_prev()
    assert panel.sel_ref is a
    panel.sel_prev()
    assert panel.sel_ref is c  # wraps


def test_input_event_left_right_drives_selection(panel):
    a, b = (_txt(panel, n) for n in "ab")
    group = _Group(Box.xywh(0, 0, 10, 10), panel, [b])
    panel.add_sel_widget(a)
    panel.add_sel_widget(group)
    panel.input_event(InputEvent.RIGHT)
    assert panel.sel_ref is b
    panel.input_event(InputEvent.LEFT)
    assert panel.sel_ref is a


def test_sel_widget_can_target_leaf_inside_subtree(panel):
    a, b, c = (_txt(panel, n) for n in "abc")
    group = _Group(Box.xywh(0, 0, 10, 10), panel, [b, c])
    panel.add_sel_widget(a)
    panel.add_sel_widget(group)
    panel.sel_widget(c)
    assert panel.sel_ref is c


def test_sel_widget_silently_ignores_unknown(panel):
    a = _txt(panel, "a")
    other = _txt(panel, "other")
    panel.add_sel_widget(a)
    panel.sel_widget(other)
    assert panel.sel_ref is a


# --------------------------------------------------------------------------- #
# Runtime (un)mounting: subtree-internal detach must not strand the cursor.
# --------------------------------------------------------------------------- #


def test_detaching_subtree_falls_back_to_first_leaf(panel):
    a, b, c = (_txt(panel, n) for n in "abc")
    group = _Group(Box.xywh(0, 0, 10, 10), panel, [b, c])
    panel.add_sel_widget(a)
    panel.add_sel_widget(group)
    panel.sel_widget(c)
    panel.del_sel_widget(group)
    assert panel.sel_ref is a


def test_subtree_can_grow_after_creation(panel):
    a = _txt(panel, "a")
    b = _txt(panel, "b")
    group = _Group(Box.xywh(0, 0, 10, 10), panel, [])
    panel.add_sel_widget(a)
    panel.add_sel_widget(group)
    assert panel._flat_sel() == [a]
    group.members_order.append(b)
    assert panel._flat_sel() == [a, b]
    panel.sel_next()
    assert panel.sel_ref is b


def test_subtree_can_shrink_during_navigation(panel):
    a, b, c = (_txt(panel, n) for n in "abc")
    group = _Group(Box.xywh(0, 0, 10, 10), panel, [b, c])
    panel.add_sel_widget(a)
    panel.add_sel_widget(group)
    panel.sel_widget(c)
    group.members_order.remove(c)
    panel.sel_next()
    assert panel.sel_ref in (a, b)
