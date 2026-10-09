# 〰️ Parallel Routing Tool for KiCad 10

> **You** route one track: the plugin routes the rest of the bus **parallel and close together**, 0/45/90° only, detouring where needed to get around obstacles.

![KiCad](https://img.shields.io/badge/KiCad-10.0-314cb0)
![API](https://img.shields.io/badge/API-IPC%20(kicad--python)-0a7)
![Version](https://img.shields.io/badge/version-V0%20provisional-red)

> ⚠️ **V0: provisional, not final.** The tool is still under development. It works on the cases tested so far, but results are not yet at their final quality, and behaviour, interface and rules may change. Always check the result and run KiCad's DRC.

**This is not an autorouter.** You decide the path by routing one guide track by hand with KiCad's router. Every other net gets a lane parallel to the guide and is routed along it, leaving the lane only to get around obstacles. You decide whether to apply the result, then run KiCad's DRC.

---

## ✨ What it does

| | |
|---|---|
| ✋ **Manual path** | You route a single track (the guide) with KiCad's router; the others follow it. |
| 📏 **Parallel bus** | Each track is a copy of the guide, offset by its pad's distance from the guide: near the pads the bus keeps the pad pitch and makes the same bends as the guide. On long runs it tightens up. |
| 🧭 **Flexible** | If an obstacle blocks a lane, only that track detours (its neighbours follow), then it returns to its lane. |
| 📐 **0/45/90° only** | Horizontal, vertical or 45° segments: no skewed segments. |
| 🎯 **Explicit selection** | Exactly 2 pads per net, no guessed connections. |
| 🛡️ **Safe** | One layer, no vias, existing tracks are never touched, nothing changes without confirmation or if clearance is not met. A single operation, undoable with `Ctrl+Z`. |

## 🚦 Project status

| Stage | Content | Status |
|---|---|---|
| 1 | Check KiCad 10 environment and API | ✅ done |
| 2 | Minimal installable plugin | ✅ loaded in KiCad 10.0.7 (Windows) |
| 3 | Board reading and selection | ✅ verified in KiCad 10.0.7 |
| 4 | Routing proposal (guide-track mode) | 🟡 V0: tested in KiCad 10.0.7, results need improvement |
| 5 | Apply and control | ✅ Apply / Keep / Remove tested in KiCad 10.0.7 |

> ℹ️ Verified in the real PCB Editor (KiCad 10.0.7, Windows 11): plugin loading, selection reading, track creation and removal, guide-track mode. Tightening the bus on long runs is new and **not yet tested** in KiCad.

## 📦 Requirements

- **KiCad 10.0** (environment verified with 10.0.7, Windows 11)
- **IPC API enabled**: `Preferences → Plugins → Enable KiCad API`
- Internet connection on first start (KiCad installs `kicad-python` into the plugin's virtual environment)

The plugin uses the new **IPC API** (`kicad-python` / `kipy`), not the legacy SWIG `pcbnew` interface, which is deprecated in KiCad 10.

## 🔧 Installation

KiCad 10 loads IPC plugins from a subfolder of:

| System | Plugin folder |
|---|---|
| Windows | `%USERPROFILE%\Documents\KiCad\10.0\plugins\` |
| macOS | `~/Documents/KiCad/10.0/plugins/` |
| Linux | `~/.local/share/KiCad/10.0/plugins/` |

### Option A: copy

1. Download or clone this repository.
2. Copy the `plugin/` folder into the plugin folder and rename it `parallel_routing_tool`.
3. Restart KiCad and open the PCB Editor.
4. Wait a few seconds while KiCad creates the plugin's Python environment in the background. The **Parallel Routing Tool** button then appears in the toolbar.

### Option B: link for development (changes take effect immediately)

**Windows (PowerShell):**

```powershell
New-Item -ItemType Junction -Path "$env:USERPROFILE\Documents\KiCad\10.0\plugins\parallel_routing_tool" -Target "$PWD\plugin"
```

**macOS / Linux:**

```bash
ln -s "$PWD/plugin" ~/Documents/KiCad/10.0/plugins/parallel_routing_tool
```

### If the button does not appear

- Check that the API server is enabled (see *Requirements*).
- In `Preferences → Plugins`, check the Python interpreter path, then right-click the action → **Recreate Plugin Environment**.
- On Windows the virtual environment is in `%LOCALAPPDATA%\KiCad\10.0\python-environments\<plugin-id>`.

## 🗑️ Uninstall

1. Close KiCad.
2. Delete the `parallel_routing_tool` folder from the plugin folder. With option B's link, only the link is removed, not the repository.
3. Optional: delete its environment in `python-environments`.

## 🧪 Usage

1. With KiCad's router (`X`), route **one track by hand**, the *guide*, between two pads of the group. Use only horizontal, vertical or 45° segments.
2. Select **all the pads** of the bus, including the guide's two. **Rule:** exactly 2 pads per net.
3. Run **Parallel Routing Tool**. The other tracks are routed:
   - along lanes parallel to the guide, on the side where their pads are;
   - around obstacles when needed, then back into their lane;
   - with 0/45/90° segments only, using the guide's width and layer.
4. Until you press **Applica** (Apply), the board does not change. Apply creates everything in a single operation (one `Ctrl+Z`). Then choose **Mantieni** (Keep) or **Rimuovi** (Remove); Remove deletes only the segments just created.
5. Refill zones (`B`) and **always run KiCad's DRC**.

If the proposal is rejected (crossed pad order, no free path, clearance violated), move the guide and try again.

> The plugin's dialogs are currently in Italian.

> The API documents that changes inside a commit are not visible until the commit is pushed. That is why the "preview" is: apply, look, then keep or remove.

## ⚙️ How it works

```
plugin/
  entrypoint.py   flow and dialogs (wx)
  board_io.py     KiCad side: selection, guide track, rules, obstacles, apply/remove
  selection.py    "2 pads per net" rule                       ← no KiCad needed, tested
  follow.py       guide track and parallel lanes              ← no KiCad needed, tested
  router.py       grid + 8-direction A* + clearance check     ← no KiCad needed, tested
```

- **Guide:** the only net in the group whose pads are already connected. It must be a single chain of straight segments, on one layer, with one width.
- **Lanes:** the guide is offset sideways. On the first and last segment the offset is the distance of each net's pads from the guide, measured at each end, so tracks leave and enter their pads straight. On guide segments longer than twice the bus width, the bus tightens to `1.5 × (width + clearance)` between tracks, if that geometry works for every track; otherwise the pad pitch is kept everywhere. Corners are the intersections of the offset lines, so 45° stays 45°.
- **Exact copy:** if the pad → lane → pad path hits nothing, it is used as is: perfectly straight lines, no grid.
- **Detour:** if the exact copy hits an obstacle, only that track is routed with an 8-direction A* (0/45/90° only). The grid pitch is `(width + clearance) / 4`, aligned to the start of the guide. Cost of each step = length + bends + distance from its own lane (beyond a one-step tolerance). Tracks are laid from the inside of the bus outwards and become obstacles for the next ones. The weights are in `WEIGHTS` in [`plugin/router.py`](plugin/router.py).
- **Grid margin:** a cell is free only if it meets the clearance plus `pitch × √2/2`. This keeps the segments between cells safe too.
- **Order:** the side-by-side order of the pads must be the same at both ends. Otherwise, on a single layer, tracks would cross and the proposal is rejected.
- **Rules:** clearance is the maximum over the netclasses of the nets involved. For each obstacle, `max(group clearance, obstacle netclass clearance)` applies.
- **Obstacles:** pads, holes, tracks and arcs, vias (treated as through vias), rule areas and board edge. Copper zones must be refilled after applying.
- **Final check:** every new segment is verified with exact geometric distances. If one violates clearance, the proposal is discarded.

### Known limitations

- One layer, no vias, existing tracks are never modified.
- Guide tracks with arcs are not supported.
- Tightening on long runs uses fixed parameters (`COMPACT_FACTOR`, `COMPACT_MIN_RATIO` in `follow.py`).
- Tracks that detour keep a tiny link between the pad centre and the grid (< 0.1 mm, inside the pad copper).
- Fine-pitch pads may end up "too close to an obstacle for the grid".
- Custom `.kicad_dru` rules, specific copper-to-edge clearance, copper graphics and copper text are not considered.
- In KiCad 10.0.7 the API returns displaced pad shapes for some rotated footprints. For those pads a conservative outline is used.
- `kicad-python` 0.8.0 does not send the document in `BeginCommit`/`EndCommit`, which KiCad 10.0.7 requires when more than one editor is open. The plugin adds the field itself.
- The plugin **does not replace** KiCad's DRC.

### Simulated tests (no KiCad)

```bash
python tests/test_selection.py
python tests/test_follow.py
```

## 📚 References

- [KiCad IPC API — for add-on developers](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/for-addon-developers/)
- [kicad-python (kipy)](https://gitlab.com/kicad/code/kicad-python)
- [`plugin.json` schema](https://go.kicad.org/api/schemas/v1)
