# LV2 & TTL: A Practical Guide for pi-Stomp

This document captures what we've learned about LV2 plugin bundles, Turtle (TTL) format,
and how MOD-UI/pedalboard TTLs work in practice. It is not a spec — it is tribal knowledge
earned through trial and error.

## LV2 Plugin Bundle Structure

An LV2 plugin lives in a `.lv2` directory (the "bundle"):

```
{name}.lv2/
  manifest.ttl          # Entry point: declares the plugin URI and points to the main TTL
  {name}.ttl            # Plugin definition: ports, metadata, UI binding
  {name}.so             # Compiled DSP binary
  modgui.ttl            # MOD GUI customization
  modgui/               # MOD GUI assets (HTML, CSS, images)
  default-preset.ttl    # Optional default preset
```

### manifest.ttl

```turtle
@prefix lv2:  <http://lv2plug.in/ns/lv2core#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

<urn:distrho:a-eq>
    a lv2:Plugin ;
    lv2:binary <a-eq.so> ;
    rdfs:seeAlso <a-eq.ttl>, <modgui.ttl> .
```

The URI (`<urn:distrho:a-eq>`) is the **canonical plugin identifier**. It must match
exactly in the pedalboard TTL's `lv2:prototype` and in pi-stomp's `register()` call.

### Plugin TTL — Port Definition

Ports are defined with `lv2:index` in the plugin's own TTL. The index determines the
port's position in the DSP binary's port array:

```turtle
lv2:port [
    a lv2:InputPort, lv2:ControlPort ;
    lv2:index 0 ;
    lv2:symbol "freql" ;
    lv2:name "Frequency L" ;
    lv2:default 160.000000 ;
    lv2:minimum 20.000000 ;
    lv2:maximum 20000.000000 ;
],
[
    a lv2:InputPort, lv2:ControlPort ;
    lv2:index 1 ;
    lv2:symbol "gl" ;
    lv2:name "Gain L" ;
    lv2:default 0.000000 ;
    lv2:minimum -20.000000 ;
    lv2:maximum 20.000000 ;
],
```

Audio ports are defined the same way:

```turtle
[
    a lv2:InputPort, lv2:AudioPort ;
    lv2:index 24 ;
    lv2:symbol "in_1" ;
    lv2:name "Audio Input 1" ;
],
[
    a lv2:OutputPort, lv2:AudioPort ;
    lv2:index 25 ;
    lv2:symbol "out_1" ;
    lv2:name "Audio Output 1" ;
]
```

## Pedalboard TTL Structure

A pedalboard is an ingen:Graph — a container that instantiates plugins and wires them
together. It lives in a `.pedalboard` directory:

```
{name}.pedalboard/
  manifest.ttl          # Entry point (same pattern as LV2 bundles)
  {name}.ttl            # Main TTL: graph definition, blocks, arcs, ports
  snapshots.json        # Per-plugin parameter state
  addressings.json      # MIDI/control bindings
  screenshot.png        # Visual preview
  thumbnail.png         # Small preview
  effect-{N}/           # Per-plugin LV2 preset state (optional)
    manifest.ttl
    effect.ttl
  config.yml            # pi-Stomp hardware overlay (optional)
```

### manifest.ttl

```turtle
@prefix ingen: <http://drobilla.net/ns/ingen#> .
@prefix lv2:   <http://lv2plug.in/ns/lv2core#> .
@prefix pedal: <http://moddevices.com/ns/modpedal#> .
@prefix rdfs:  <http://www.w3.org/2000/01/rdf-schema#> .

<{name}.ttl>
    lv2:prototype ingen:GraphPrototype ;
    a lv2:Plugin ,
        ingen:Graph ,
        pedal:Pedalboard ;
    rdfs:seeAlso <{name}.ttl> .
```

### Main TTL — Plugin Block

Each plugin instance is an `ingen:Block`. The block's `lv2:port` list defines the
**pedalboard-level port order**, which is **different from the plugin's own port order**.

#### CRITICAL: Port Order Convention

The `lv2:port` list on a Block determines the port indices for that instance. The
convention used by MOD-UI (and required for correct operation) is:

1. **Audio ports first** (input, then output)
2. **Control ports** in the order they appear in the plugin's own TTL
3. **`:bypass` last**

This is **not** the same order as the plugin's own TTL, which typically puts audio
ports at the end. The pedalboard TTL reorders them.

**Example — DISTRHO Audio EQ (a-eq):**

Plugin's own TTL order (indices 0-25):
```
freql(0), gl(1), freq1(2), g1(3), bw1(4), ..., enable(23), in_1(24), out_1(25)
```

Pedalboard TTL order (indices 0-27):
```
in_1(0), out_1(1), freql(2), gl(3), freq1(4), g1(5), bw1(6), ..., enable(26), :bypass(27)
```

The audio ports move from the end to the beginning, and `:bypass` is appended at the end.

**Why this matters:** mod-host assigns `ingen:value` by port index in the `lv2:port`
list. If you put control ports at index 0-23 and audio ports at 24-25, the audio
port values will be read from the wrong control ports, and vice versa. This causes
all bands to show the same frequency, bypass to not work, and other mysterious failures.

#### Block Definition

```turtle
<a_eq>
    ingen:canvasX 1516.2 ;
    ingen:canvasY 675.6 ;
    ingen:enabled true ;
    ingen:polyphonic false ;
    lv2:microVersion 2 ;
    lv2:minorVersion 2 ;
    mod:builderVersion 0 ;
    mod:releaseNumber 0 ;
    lv2:port <a_eq/in_1> ,          # audio input (index 0)
             <a_eq/out_1> ,          # audio output (index 1)
             <a_eq/freql> ,          # control (index 2)
             <a_eq/gl> ,             # control (index 3)
             ...
             <a_eq/enable> ,         # control (index 26)
             <a_eq/:bypass> ;        # bypass (index 27, LAST)
    lv2:prototype <urn:distrho:a-eq> ;
    pedal:instanceNumber 1 ;
    pedal:preset <> ;
    a ingen:Block .
```

#### Port Definitions

Each port in the `lv2:port` list must have a corresponding definition. Audio ports
are defined with **both** `lv2:InputPort` and `lv2:OutputPort` (ingen uses a
send/return model where the same port name serves both directions):

```turtle
<a_eq/in_1>
    a lv2:AudioPort ,
        lv2:InputPort .

<a_eq/in_1>
    a lv2:AudioPort ,
        lv2:OutputPort .
```

Control ports get `ingen:value` for their initial state:

```turtle
<a_eq/freql>
    ingen:value 160.000000 ;
    a lv2:ControlPort ,
        lv2:InputPort .
```

The `:bypass` port:

```turtle
<a_eq/:bypass>
    ingen:value 0 ;
    a lv2:ControlPort ,
        lv2:InputPort .
```

### Audio Arcs

Arcs wire blocks together. Each arc connects a source port to a destination port:

```turtle
_:b1
    ingen:tail <capture_1> ;
    ingen:head <a_eq/in_1> .

_:b2
    ingen:tail <a_eq/out_1> ;
    ingen:head <playback_1> .
```

### Global Ports

Every pedalboard must define these global ports:

```turtle
<:bpb> ingen:value 4.000000 ; lv2:index 0 ; a lv2:ControlPort , lv2:InputPort .
<:bpm> ingen:value 120.000000 ; lv2:index 1 ; a lv2:ControlPort , lv2:InputPort .
<:rolling> ingen:value 0 ; lv2:index 2 ; a lv2:ControlPort , lv2:InputPort .

<control_in> ... a atom:AtomPort , lv2:InputPort .
<control_out> ... a atom:AtomPort , lv2:OutputPort .
<capture_1> ... a lv2:AudioPort , lv2:InputPort .
<playback_1> ... a lv2:AudioPort , lv2:OutputPort .
<playback_2> ... a lv2:AudioPort , lv2:OutputPort .
<midi_separated_mode> ... a atom:AtomPort , lv2:InputPort .
<midi_loopback> ... a atom:AtomPort , lv2:InputPort .
```

### Pedalboard Metadata

```turtle
<>
    doap:name "All EQ" ;
    pedal:unitName "MOD Desktop" ;
    pedal:unitModel "MOD Desktop" ;
    pedal:width 2800 ;
    pedal:height 600 ;
    pedal:addressings <addressings.json> ;
    pedal:screenshot <screenshot.png> ;
    pedal:thumbnail <thumbnail.png> ;
    pedal:version 1 ;
    ingen:polyphony 1 ;
    ingen:arc _:b1 , _:b2 , ... ;
    ingen:block <a_eq> , <eq> , ... ;
    lv2:port <:bpb> , <:bpm> , <:rolling> , ... ;
    lv2:extensionData <http://lv2plug.in/ns/ext/state#interface> ;
    a lv2:Plugin , ingen:Graph , pedal:Pedalboard .
```

## effect-N Directories — Per-Instance Non-Port State

Each plugin instance can have an `effect-{N}/` directory containing LV2 preset state.
The `N` matches `pedal:instanceNumber` on the block. These store state that is **not a
control port** — things that don't fit the numeric/MIDI-bindable `lv2:ControlPort` model
and so never appear in `parameters`. Examples:

- **NAM** (Neural Amp Modeler): the loaded model file (`…neural-amp-modeler-lv2#model`).
- **Notes** (open-music-kontrollers): the note text (`…notes#text`).
- **fil4**: display settings like `dbscale`, `fftgain`, `fftmode`.

```
effect-21/
  manifest.ttl    # declares effect.ttl as a pset:Preset that appliesTo the plugin URI
  effect.ttl      # the preset body: state:state holds the actual properties
```

The state is a standard **LV2 preset** (`pset:Preset`) carrying an **`state:state`** node:

```turtle
# effect-21/effect.ttl
<>
    a pset:Preset ;
    lv2:appliesTo <http://github.com/mikeoliphant/neural-amp-modeler-lv2> ;
    state:state [
        <http://github.com/mikeoliphant/neural-amp-modeler-lv2#model>
            <Clean%20(G1%20L0%20B1%20T1).nam>
    ] .
```

These are optional — plugins use defaults if absent — and are generated by MOD-UI when
saving a pedalboard. The block links to them by `pedal:instanceNumber N` (→ `effect-N/`)
plus `pedal:preset <>`.

### CRITICAL: this data is NOT in the pedalboard graph

Loading the pedalboard bundle does **not** make these properties queryable from the block.
Verified on-device against a real NAM board:

```python
w = lilv.World(); w.load_specifications(); w.load_plugin_classes()
w.load_bundle(w.new_file_uri(None, "/…/Bassguy.pedalboard/"))
# block found via ingen:block, prototype + instanceNumber present, BUT:
w.get(nam_block, w.new_uri("…neural-amp-modeler-lv2#model"))  # -> None
```

The block carries only `lv2:prototype`, `pedal:instanceNumber`, ports, and canvas coords.
MOD stores per-instance state as **separate presets outside the graph**, so "just read it
from what we already parsed" is impossible by construction — the triple isn't loaded.

### Reading effect-N state — two routes

**1. Regex over `effect.ttl` (what pi-Stomp does today).** Cheap, no extra lilv load, but
fragile and returns the raw escaped relative path:

```python
ttl = Path(bundlepath, f"effect-{instance_number}", "effect.ttl").read_text()
m = re.search(r'<[^>]*#model>\s+<([^>]+)>', ttl)   # -> "Clean%20(G1%20L0%20B1%20T1).nam"
```

**2. Proper lilv via the preset + state node.** Standards-based, and lilv resolves the
value to an absolute, correctly-unescaped `file://` URI for free. Requires a **second
bundle load** plus `load_resource` (presets only declare `rdfs:seeAlso` in their manifest;
the body isn't read until you ask):

```python
w.load_bundle(w.new_file_uri(None, f"/…/effect-{N}/"))
preset = next(iter(w.find_nodes(None, lv2_appliesTo, w.new_uri(PLUGIN_URI))))
w.load_resource(preset)                                    # follow rdfs:seeAlso -> effect.ttl
blank  = next(iter(w.find_nodes(preset, state_state, None)))
model  = next(iter(w.find_nodes(blank, w.new_uri(MODEL_URI), None)))
# -> file:///…/effect-21/Clean%20(G1%20L0%20B1%20T1).nam
```

Because lilv exposes the whole `state:state` node, you can also enumerate **all** its
properties generically — no per-plugin predicate knowledge needed in the parser.

> **The extra file read is irreducible** either way: the data physically lives in a
> separate preset file. You can choose regex vs. lilv, but something must open `effect-N/`.

## snapshots.json

Stores per-plugin parameter values for each snapshot:

```json
{
    "current": 0,
    "snapshots": [
        {
            "name": "Default",
            "data": {
                "a_eq": {
                    "bypassed": false,
                    "parameters": {},
                    "ports": {
                        "freql": 160.0,
                        "gl": 0.0,
                        "freq1": 300.0,
                        ...
                    },
                    "preset": ""
                }
            }
        }
    ]
}
```

Ports are keyed by symbol name (not index), so the ordering in snapshots.json is
independent of the TTL port order.

## addressings.json

MIDI/control bindings:

```json
{
    "/bpm": []
}
```

## pi-Stomp Plugin Registration

pi-Stomp registers custom panels by plugin URI in `plugins/{name}/__init__.py`:

```python
from plugins.customization import PluginCustomization, register

register(
    "urn:distrho:a-eq",
    customization=PluginCustomization(
        panel_cls=DistrhoAEqPanel,
        display_name="DISTRHO Audio EQ",
    ),
)
```

The URI must match **exactly** what appears in the plugin's `manifest.ttl` and the
pedalboard TTL's `lv2:prototype`. There is no normalization, prefix stripping, or
fuzzy matching — it's a direct `dict.get()`.

## Common Pitfalls

1. **Port order mismatch** — The pedalboard TTL's `lv2:port` list must use the
   MOD-UI convention (audio first, controls, `:bypass` last), not the plugin's own
   TTL order. Getting this wrong causes all bands to share the same frequency,
   bypass to not work, and other mysterious failures.

2. **`:bypass` not in the `lv2:port` list** — The bypass port must be the last entry
   in the `lv2:port` list. If it's declared separately, it won't get the correct
   index and bypass will appear stuck.

3. **Audio ports not in the `lv2:port` list** — Audio ports must be in the list
   (first two entries). If they're declared separately, the port indices will be
   wrong.

4. **URI mismatch** — The `lv2:prototype` URI in the pedalboard TTL must match the
   plugin's `manifest.ttl` URI exactly. A trailing `#` or missing `#` is a
   different URI.

5. **Missing `lv2:microVersion`/`lv2:minorVersion`** — These should match the
   plugin's own TTL. MOD-UI sets them from the plugin metadata.

6. **Missing `pedal:instanceNumber`** — Each block needs a unique instance number.
   This maps to `effect-N/` directories if present.

7. **Missing `pedal:preset <>`** — The empty preset reference is required for
   MOD-UI to associate preset state with the block.
