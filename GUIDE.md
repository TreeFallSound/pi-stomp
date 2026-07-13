# pi-Stomp

Python hardware controller for MOD-UI, running on a Raspberry Pi. Reads physical
controls (footswitches, encoders, knobs, expression pedals), emits MIDI CC / WebSocket
params, and paints a 320x240 LCD. A 10ms polling loop drives everything.

Architecture reference: `docs/architecture.md`. Subsystem detail:
`pistomp/input/README.md` (input dispatch), `uilib/README.md` (paint system).
**Read the code before trusting any doc, including this one.**

## Rules

- **pyright zero.** No new errors, ever.
- **No broad `# pyright: ignore`.** A blanket ignore is a bug you haven't found yet.
- **`getattr` / `hasattr` are banned.** If you reach for them, the type is wrong.
- **Dependencies form a DAG.** No cycles between modules.
- **MOD-UI is the single writer** of bypass and parameter state. We emit, paint
  optimistically, and reconcile against its echo. Never treat local state as truth.

## Writing code here

Match the file you're editing — its naming, its idiom, its comment density.

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

## Commands

```bash
uv run pytest                    # all tests
uv run pytest --snapshot-update  # accept changed LCD snapshots
uv run pyright                   # must be clean
uv sync                          # ALWAYS run after touching uv.lock

ssh pistomp@pistomp.local "ps-restart"                          # restart service
ssh pistomp@pistomp.local "journalctl -u mod-ala-pi-stomp -f"   # live logs
```

Deploy by `scp` to the device or `./deploy.sh`; source lives at
`/home/pistomp/pi-stomp/`. Shipping a release requires a version bump in the
*separate* `pi-gen-pistomp` repo — see `docs/architecture.md`.

The system python provides base packages (`python3-lilv`); PyPI deps live in a
uv-managed venv. Don't try to pip-install the system ones.

## Traps

- **Never create a bare `pygame.Surface((w, h))`.** It inherits the display format —
  opaque RGB when headless (device/tests) but ARGB under a real window driver (the
  cocoa emulator). The stray alpha silently breaks SRCALPHA compositing; glyph pastes
  drop their fill and you will blame the wrong thing. Be explicit: `pygame.SRCALPHA`
  for alpha, or `depth=32, masks=(0xFF0000, 0xFF00, 0xFF, 0)` for opaque RGB
  (bit-identical to the device; `depth=24` differs in AA rounding).

- **Snapshot loads broadcast only deltas** against mod-ui's own cache; pedalboard loads
  and connect dumps rebroadcast unconditionally. Reselecting a *board* is a full
  resync. Reselecting a *snapshot* is not.

- **A UI bypass gets no echo.** mod-ui skips the origin socket, and mod-host emits no
  `param_set` for bypasses it received from mod-ui. Footswitch bypasses *do* echo
  (they arrive as MIDI). So the UI path must update local state itself — this
  asymmetry is deliberate, not a bug to "fix."

- **Never extract `lv2plugins.tar.gz` whole.** It's huge. Pull single files with
  `tar --to-stdout`. Prefer inspecting the live device anyway.

- **Blocking subprocess calls (nmcli, systemctl) must not run on the UI thread.** They
  stall the 10ms loop. Use a worker thread and poll-drain the result.

## Tests

The `snapshot` fixture asserts the rendered LCD matches a baseline PNG.

```python
def test_my_flow(v3_system, snapshot):
    snapshot()           # auto-numbered
    snapshot("label")    # named
    snapshot("label")    # same name again → asserts the screen returned to that state
```

On a snapshot mismatch: **fix real failures first.** Only then `--snapshot-update`, and
say what you expect to change before regenerating.
