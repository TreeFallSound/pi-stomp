# Remove WebSocket backpressure; refuse a send when there is no connection

**Status:** done. Sections 3-5 are implemented; section 6 still stands.
**Branch:** `feat/remove-backpressure`, off the PR #251 work.
**Scope:** `modalapi/websocket_bridge.py` and its callers. MIDI, the LCD and the
binding table do not change.
**Goal:** `send_parameter` and `send_bpm` refuse a send only when the bridge has no
live connection. The write-buffer measurement goes away.

---

## 1. Why

### The number does not measure MOD-UI

`_get_write_buffer_size` (`websocket_bridge.py:249`) returns
`ws.transport.get_write_buffer_size()`. That is the count of bytes that our own
asyncio transport holds and has not yet given to the kernel. It is our side of the
socket. MOD-UI supplies no part of it.

The buffer increases only when the kernel refuses more bytes, which is TCP flow
control. On loopback this does show that the peer does not read its socket. It does
not show that MOD-UI processed a message. MOD-UI can read every byte into its own
buffers and stay far behind, while we measure zero.

### The threshold is below the level that the library acts on

`Connection.send` in websockets 16 calls `send_data()` and then `await self.drain()`.
`drain()` waits only while the transport is paused, and asyncio pauses the transport
at its high-water mark. The code sets that mark to 65536 with `write_limit`
(`websocket_bridge.py:122`). So `send()` returns with a buffer below 64 KB, and the
sample at line 198 flags the band from 8 KB to 64 KB. The library does not hold a
write in that band.

### The flag can stay set for the remainder of the session

`backpressure_active` becomes true only after a successful send (line 200). It
becomes false only at the same place (line 208). `send_bpm` (293) and
`send_parameter` (301) are the only producers, and each one refuses **and does not
put its message in the queue**. So, if the flag becomes true on the last message in
the queue, `_process_queue` parks on `self._wakeup.wait()` (line 191) and no producer
can wake it. No path resets the flag on a reconnect.

Measured with a fake transport that reports 9000 bytes:

```
WebSocket backpressure START: 9000 bytes buffered, queue=0, threshold=8192
after burst:                  backpressure_active = True   queue depth = 0
send while socket is idle ->  False                        queue depth = 0
after a full drain window:    backpressure_active = True
send again ->                 False
```

`queue=0` in the warning is the condition for the latch: the flag becomes true with
an empty queue. For the player, the symptom is the symptom of PR #251. The parameter
dialog opens, but no value changes.

### The flag guards the wrong failure

A reconnect empties the command queue (`websocket_bridge.py:131-141`). A value that we
send while the socket is down goes into the queue, `send_parameter` returns true,
`commit` paints it, and the reconnect discards it. The LCD then shows a value that
MOD-UI does not have. Backpressure never covered this condition.

### MOD-UI stops reading only while it loads a pedalboard

`Host.load` (`../mod-ui/mod/host.py:3519`) is a plain function. It contains no
`yield` and no `@gen.coroutine` through its full length, to line 3773, and it does
the plugin load, the connections, the lilv work and many socket writes to mod-host.
Tornado runs it on the ioloop thread, so MOD-UI reads no socket while it runs. This
is the one condition that can fill our transport buffer.

MOD-UI brackets that same condition with `loading_start` (`mod/host.py:3550`) and
`loading_end` (`mod/host.py:3743`). We already receive that signal, and PR #251 made
our use of it correct. So the buffer measurement is a second detector, and a worse
one, for a condition that we detect exactly.

### MOD-UI sends a local client very little

`Session.websocket_opened` (`../mod-ui/mod/session.py:241-244`) marks a client from
`127.0.0.1` or `::1` as `_is_local`. `msg_callback` (`mod/session.py:416-443`) then
keeps `output_set` and `data_ready` away from such a client, and acknowledges
`data_ready` on its behalf. pi-stomp is such a client. So our socket does not carry
the meter traffic that fills a browser's socket.

### MOD-UI never tells us to slow down

`ws_parameter_set` (`mod/session.py:323`) and `msg_callback_broadcast`
(`mod/session.py:445`) call Tornado's `write_message` and do not wait. Tornado
buffers for each connection. So no message from MOD-UI reports congestion to us. The
only signal we can read is the TCP window, which is the number that section 1 shows
to be wrong.

### The ecosystem controls flow with acknowledgements, not buffer sizes

mod-host, MOD-UI and the browser use a credit handshake: `data_finish`, then
`data_ready N`, then `output_data_ready`. `../mod-ui/docs/output-data-flow.md`
records it, and `mod/host.py:1619` adds a 150 ms fallback timer for a client that
does not answer. If pi-stomp ever needs true flow control for its own sends, that
handshake is the pattern to copy. A transport-buffer probe is not that pattern.

### Two callers are wired to the wrong signal

- `set_mod_tap_tempo` (`modhandler.py:1855`) sends a REST POST when the WebSocket
  send fails. That POST blocks the 10 ms loop. Today it runs for a full transport
  buffer, but not for the disconnection that loses the value.
- `command_queue` is unbounded, with the comment "never drop blend mode messages"
  (line 266). Blend messages go through `send_parameter`
  (`blend/parameter_setter.py:56`), so the flag refuses them before they can reach
  that queue.

---

## 2. The replacement

`self.ws` is the connection handle. The worker sets it in the `connect()` scope
(line 126) and clears it in the two outer error arms (159, 175). The connect loop
controls it, not the send path, so it cannot latch.

**One correction is necessary first.** `_process_queue` catches `ConnectionClosed`
and breaks (line 220), so it returns without an exception. `asyncio.wait` then
completes, the `async with` scope ends, and `self.ws` keeps a closed connection
object. Clear it in a `finally` on the connection scope, so that one place owns the
value:

```python
async with websockets.connect(...) as ws:
    self.ws = ws
    try:
        ...                      # flush, then the two tasks
    finally:
        self.ws = None
```

Then the bridge exposes the predicate, and the two send methods use it:

```python
@property
def connected(self) -> bool:
    return self._worker.ws is not None
```

A `False` return keeps its present meaning for every caller: the value did not leave,
so do not show it as accepted.

---

## 3. Changes

### `modalapi/websocket_bridge.py`

| Line | Change |
|------|--------|
| 48 | Docstring: "backpressure monitoring" becomes "connection state". |
| 51-55 | `WebSocketWorker.__init__`: delete the `backpressure_threshold` parameter and field. |
| 67-68 | Delete `backpressure_events` and `backpressure_active`. |
| 126 | Add the `try` / `finally` that clears `self.ws` when the scope ends. |
| 198-212 | Delete the buffer sample and both log branches. |
| 214-218 | The 1000-message debug log reads `buffer_size`. Keep the log; report `queue` only. |
| 249-254 | Delete `_get_write_buffer_size`. |
| 264-268 | `AsyncWebSocketBridge.__init__`: delete the `backpressure_threshold` parameter. |
| 293-299 | `send_bpm`: refuse when `not self.connected`. Correct the docstring. |
| 301-308 | `send_parameter`: the same. |
| 323-333 | `get_stats`: delete `backpressure_events`, `backpressure_active` and `write_buffer_bytes`. |
| new | Add the `connected` property. |

### Callers

| File | Change |
|------|--------|
| `modalapi/modhandler.py:219` | Delete the `backpressure_threshold=8192` argument. |
| `emulator/modhandler.py:69` | The same. |
| `modalapi/modhandler.py:1857` | Comment: the POST runs when the WebSocket is not connected. |
| `blend/parameter_setter.py:48` | Docstring: "de-duplication or backpressure" becomes "de-duplication, or no connection". |
| `blend/parameter_setter.py:60` | Log text: "Dropped (backpressure)" becomes "Dropped (not connected)". Keep the arm; the send can still fail. |
| `plugins/base.py:293` | Comment: a send that did not leave stays queued. Do not name backpressure. |

### Docs

| File | Change |
|------|--------|
| `docs/architecture.md:226` | "during a pedalboard load, or under backpressure" becomes "during a pedalboard load, or while the bridge is not connected". |
| `docs/architecture.md:240` | Retitle the "Backpressure" section to "Refused sends" and state the new rule: a send is refused only when there is no connection, and a reconnect empties the queue. |
| `docs/architecture.md:437` | Module list: "(daemon thread, backpressure)" becomes "(daemon thread, reconnect)". |

`GUIDE.md` does not mention backpressure. It needs no change.

---

## 4. Tests

### Change

| File | Change |
|------|--------|
| `tests/test_blend_parameter_setter.py:31` | Rename `test_bridge_backpressure_returns_false` to name a refused send. Assert the new log text. |
| `tests/integration/test_tap_tempo.py:32` | Rename `test_set_mod_tap_tempo_falls_back_to_post_under_backpressure`. The condition is now "the bridge is not connected". |
| `tests/v3/test_transport_bindings.py:504, 518` | Comments name backpressure. Correct them. |
| `tests/test_plugin_panels.py:24` | `self.refusing = False  # stands in for backpressure` becomes a refused send. |

### Add

Put these in a new `tests/test_websocket_bridge.py`, with a fake connection object.

1. **A send is refused before the first connect.** `send_parameter` returns `False`
   and the queue stays empty.
2. **A send is accepted while connected.** The message reaches `command_queue`.
3. **A send is refused after the connection ends.** Clear `worker.ws`, then assert
   the refusal.
4. **There is no latch.** Refuse a send while disconnected, set `worker.ws` again,
   then assert that the next send is accepted. This test fails against the present
   code, which is the point of it.
5. **A reconnect empties the queue.** Put a message in the queue, run the flush, and
   assert the queue is empty. This records the hole in section 6.

---

## 5. What changes for the player

- A parameter edit made before MOD-UI accepts the WebSocket is refused, so `commit`
  puts the confirmed value back. Today the edit goes to the queue and the reconnect
  discards it, and the LCD keeps a value that MOD-UI does not have.
- The tap-tempo REST POST now runs for a disconnection. The 10 ms loop can block for
  the length of that POST, but only in that condition, and only for one detent.
- Nothing changes while the connection is good, which is nearly all of the time.

---

## 6. Not in this work

- **A reconnect still discards queued messages** (`websocket_bridge.py:131-141`). The
  new predicate makes the window small: only a send that passes the `connected` test
  as the socket drops can be lost. It does not close the window. To close it, the
  queue must survive a reconnect, or the bridge must report each discarded message to
  its caller.
- **The command queue does not coalesce.** A long stall still builds a backlog of
  values for one symbol, and MOD-UI receives each of them in turn. A queue keyed by
  `(instance_id, symbol)`, the shape that `PluginPanel._param_queue` already uses,
  would keep only the newest value for each parameter. This is a separate change.
- **`PluginPanel._send_param` does not use `_sink_for`.** This is recorded in PR
  #251 and does not change here.

---

## 7. Order of work

1. Add the `try` / `finally` that clears `self.ws`, and the `connected` property.
   Nothing uses them yet.
2. Add the five new tests. Test 4 fails.
3. Point `send_bpm` and `send_parameter` at `connected`. Test 4 passes.
4. Delete the threshold, the two counters, `_get_write_buffer_size`, the sample, the
   log branches and the stats fields.
5. Correct the callers, the comments and the docs.
6. Run `uv run pytest` and `uv run pyright`. Both must be clean.

---

## 8. Risks

- **The predicate reads a field written by the worker thread.** This is the same
  arrangement as `backpressure_active` today, and a reference read is safe. Do not
  add a lock for it.
- **A stale `self.ws`.** The whole plan depends on the `finally` in step 1. Without
  it, `connected` reports true against a closed connection, and step 3 makes that
  worse than the flag it replaces. Test 3 covers this.
- **Refusal at start.** Every send before the first connect now returns `False`.
  `_is_pedalboard_loading` is open for that period, so `_publish_plugin_param`
  already refuses, and the LCD shows no new reverts. Confirm this on hardware.
- **The blend path sends at a high rate.** Blend calls `send_parameter` for each
  parameter of each stop. Check the log level of the "Dropped" warning at
  `blend/parameter_setter.py:60`: one warning for each parameter of a disconnected
  sweep is a lot of text.
