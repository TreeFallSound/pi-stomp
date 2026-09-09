# pi-Stomp

Python hardware controller for MOD-UI, running on a Raspberry Pi. Reads physical
controls (footswitches, encoders, knobs, expression pedals), emits MIDI CC / WebSocket
params, and paints a 320x240 LCD. A 10ms polling loop drives everything.

Architecture reference: `docs/architecture.md`. Subsystem detail:
`pistomp/input/README.md` (input dispatch), `uilib/README.md` (paint system).
Wire protocol: `../pistomp-manual/src/developers/websocket-bridge.md` (message table,
bypass paths); `../pistomp-manual/src/plugins/choosing-pedals/build.md` (REST add/connect/save).
**Read the code before trusting any doc, excluding this one.**

## Agent behaviour

As the user, I expect you to lead with suggestions and uncover facts. I hold that context; you do not. An implementation built on a guess is expensive to me: I have to find the guess, see where it left the intent, and unwind it. A suggestion costs one read and a "no." So lead with suggestions and uncover facts; I own the architecture and judgment.

1. **Suggest, with justification** — prior art, real hardware/ecosystem examples, ways this lets players express themselves. A suggestion I can reject beats an implementation I have to unwind.
2. **When the design space is open, hand it back as a question.** Decompose it into its principal axes and ask with the multi-select tool, not as prose options. *Open* means more than one defensible architecture, or a choice that's expensive to reverse. A bug fix or an already-constrained detail is not open — just do it. (Debounce constant for a new encoder: constrained, do it. Whether encoders map to parameter pages at all: open, ask.)
3. **I own the scaffolding.** Once my choices constrain the space, fill in the rest. That's where you accelerate me.

Don't correct me on things that aren't germane, especially when you're only guessing I don't understand. Do tell me when I'm wrong about the thing at hand.

### Rules

- **pyright zero.** No new errors, ever.
- **No broad `# pyright: ignore`.** A blanket ignore is a bug you haven't found yet.
- **`getattr` / `hasattr` are banned.** If you reach for them, the type is wrong — lean on the annotations and `cast` where you must. A dynamic attribute is a typed protocol you haven't written yet.
- **Dependencies form a DAG.** No cycles between modules.
- **MOD-UI is the single writer** of bypass and parameter state. We emit, paint
  optimistically, and reconcile against its echo. Never treat local state as truth.
- **No comments explaining course corrections.**
- **Production python files must always have AGPL headers.** Copy the SPDX block from any of them, e.g. `pistomp/adcswitch.py`.
- **NAV is unhijackable.** Rotate/click/longpress on the NAV control always operates on
  the current selection. No panel or binding may consume a raw NAV event, and no
  `declare_bindings()` row may name `cls=NAV` — it's the one axiom the precedence
  resolver doesn't apply to. Enforced by the base `Panel`, not convention.
- **Immutable at domain boundaries.** Data that crosses from config to application is a frozen dataclass. Do not mutate it.
- **Lifecycle symmetry.** The code that creates an association must close it. Do not depend on a downstream sweep to clean up.
- **Domain separation.** Config (`pistomp/config/`), hardware, and application are three separate domains. Hardware objects must not cache config state. Config types must not reference hardware objects.

### Writing code here

Match the file you're editing — its naming, its purpose, its comment density, docstrings or no (ask: is this an API or something internal)?

**Comments are short clauses, and rare.** Write one only to state a constraint the code
cannot show: a hardware quirk, a protocol asymmetry, a why-not-the-obvious-thing. Never
narrate what the next line does, never justify your change to the reviewer, never leave
observability cruft. If a comment explains *what*, delete it and fix the name instead.

```python
# good — states a constraint you cannot read off the code
# ADC noise never reaches the rails; clamp or the pedal loses its endpoints.

# bad — narrates, justifies, or restates
# Now we clamp the endpoints. This is important because we want the expression
# pedal to be able to reach its full range, which it otherwise would not due to
# noise in the ADC readings, so we force values near the extremes to snap.
```

Same for prose: answer the question, skip the preamble.

A panel declares its input handling with `declare_bindings()` → `BindingDecl`s
(`common/contexts.py`); the precedence resolver picks the winner and badges render off the
same table. Two things the source won't tell you: nav stays the axiom above the resolver,
and `on_event` is only for a panel that is a genuine state machine (NAM's capture flow), not
a binding set.

## Commands

```bash
uv run pytest                    # all tests
uv run pytest --snapshot-update  # accept changed LCD snapshots
uv run pyright                   # must be clean
uv sync                          # ALWAYS run after touching uv.lock

ssh pistomp@pistomp.local "ps-restart"                          # restart service
ssh pistomp@pistomp.local "journalctl -u mod-ala-pi-stomp -f"   # live logs
```

Deploy by `scp` + `ps-restart` on the device or by `./deploy.sh`; source lives at
`/home/pistomp/pi-stomp/`. Shipping a release needs a version bump in the `pi-gen-pistomp`
repo, which is not in this checkout — see `docs/architecture.md`.

The system python provides base packages (`python3-lilv`); PyPI deps live in a
uv-managed venv. Don't try to pip-install the system ones.

## Traps

- **Never create a bare `pygame.Surface((w, h))`.** It inherits the display format — opaque
  RGB when headless (device/tests), ARGB under a real window driver (the cocoa emulator) —
  and the stray alpha breaks SRCALPHA compositing. Be explicit: `pygame.SRCALPHA` for alpha,
  or the opaque 32-bit `masks=` construction in `uilib/container.py` for a blend destination
  (bit-identical to the device; `depth=24` differs in AA rounding).

- **`PanelStack`'s root surface must stay opaque.** `LcdIli9341.update` quantises it to
  RGB565 with a convert-blit; an `SRCALPHA` source flips SDL to its per-pixel
  alpha-blending blitter — ~7x slower, on every LCD push. The root is a blend
  *destination*: it needs 32-bit for blend precision but no dest alpha channel. Panel
  surfaces (`ShroudedPanel`, `RoundedPanel`) are blit *sources* and do need `RGBA`.
  Benchmark the pack path with `tools/bench_pack_variants.py`.

- **Snapshot loads broadcast only deltas** against mod-ui's own cache; pedalboard loads
  and connect dumps rebroadcast unconditionally. Reselecting a *board* is a full
  resync. Reselecting a *snapshot* is not.

- **A UI bypass of a footswitch-less plugin gets no echo.** mod-ui skips the origin socket,
  and mod-host emits no `param_set` for a bypass it received from mod-ui — so that path must
  update local state itself (`Plugin.toggle_bypass` commits). A footswitch-bound plugin is
  the opposite: `_sink_for` routes the commit out as MIDI CC and the echo reconciles it. The
  asymmetry is one of *transport*, chosen by `_sink_for`, and it is deliberate. (Dispatch
  carries no such fork; never fake a press to reach the wire — see `_fire_row`.)

- **A switch's CC carries only the two ends of the binding range.** A press alternates
  between exactly the min/max mod-ui's advanced MIDI-learn assigned. A UI edit that lands
  *between* them has no CC code, so `_publish_switch_cc` sends it over the WebSocket
  instead — else mod-host answers an endpoint against a screen showing the real value.
  Pinned by the endpoint pair in `tests/v3/test_sink_routing.py`.

- **`loading_start` opens a window that suppresses outbound sends; `loading_end` closes
  it.** Both come from mod-ui in pairs, from a board load and a connect dump alike. Nothing
  else may raise `_is_pedalboard_loading` — an unclosed window silently refuses every send
  for the rest of the session, and `commit` then rolls each edit back on screen.
  `set_current_pedalboard` also clears it, covering the aborted load that returns before
  `loading_end`.

- **Send form and echo form differ.** We send `param_set /graph/{id}/{sym} {v}`; both broadcast paths come back as `param_set /graph/{id} {sym} {v:%f}`

- **Never extract `lv2plugins.tar.gz` whole.** It's huge. Pull single files with
  `tar --to-stdout`. Prefer inspecting the live device anyway.

- **Blocking subprocess calls (nmcli, systemctl) must not run on the UI thread.** They
  stall the polling loop. Use a worker thread and poll-drain the result.

## Tests

The `snapshot` fixture asserts the rendered LCD matches a baseline PNG.

```python
def test_my_flow(v3_system, snapshot):
    snapshot()           # auto-numbered
    snapshot("label")    # named
    snapshot("label")    # same name again → asserts the screen returned to that state
```

On a snapshot mismatch: **fix real failures first.** When only snapshot differences remain, run `--snapshot-update` to populate the working copy, then show me the changed files as soon as they regenerate and what you expect them to look like. You can lean on me to tell you if anything's wrong.

## Create an LCD screen capture

On the device with services running, `ps-record-lcd --still` writes
`~/pistomp_capture_YYYYMMDD_HHMMSS.png`; `-o FILE` overrides the name, and dropping `--still`
records `.mp4` instead. It's a PATH symlink to `util/record_lcd.py`, installed by the
`pi-gen-pistomp` image build (not this checkout).
