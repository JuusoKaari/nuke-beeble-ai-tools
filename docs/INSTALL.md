# Installation

Setup guide for **nuke-beeble-ai-tools**.

**Platform support:** Developed and tested on **Windows**. macOS and Linux should work with the same env vars and folder layout, but path separators and Python launchers differ.

## Requirements

| Item | Notes |
|------|--------|
| **Foundry Nuke** | Nuke 8.0+ (tested on 11.3v6). Group nodes; embedded Python 2.7 or 3.x |
| **System Python 3** | Separate from Nuke - runs `beeble_switchx_helper.py` via subprocess |
| **ffmpeg + ffprobe** | On `PATH` for video prerender, validation, and Read frame-range probing |
| **Beeble account** | API key from [Beeble developer docs](https://developer.beeble.ai/docs/authentication) |
| **Internet** | Helper calls Beeble cloud APIs |

### Two Python versions (important)

| Runtime | Version | What runs there |
|---------|---------|-----------------|
| **Nuke embedded** | 2.7 (classic) or 3.x (Nuke 13.2+) | `init.py`, `menu.py`, `beeble_switchx_runner_v1.py`, prerender utilities |
| **System / shell** | Python 3 | `beeble_switchx_helper.py`, Beeble REST API calls |

The helper uses **stdlib only** - no `pip install` is required.

The **Python 3 cmd** knob on the node (default `py -3`) points at the system interpreter, not Nuke's.

## 1. Get the toolkit

Pick a permanent install location, for example:

```text
C:\Tools\nuke-beeble-ai-tools
```

`NUKE_PATH` must point at the folder that contains `init.py`, `menu.py`, and `nuke/` (the install root).

### Clone with Git

```powershell
git clone https://github.com/JuusoKaari/nuke-beeble-ai-tools.git C:\Tools\nuke-beeble-ai-tools
```

## 2. Set your Beeble API key

**Recommended:** set user environment variable `BEEBLE_API_KEY` to your secret key. The runner passes it to the helper via the subprocess environment (not the command line).

**Alternative:** paste the key into the **BEEBLE_API_KEY** knob on the node. That value is **saved into the `.nk` script** - never share or commit scripts that contain a real key.

Get a key via [Beeble authentication docs](https://developer.beeble.ai/docs/authentication).

## 3. Add to `NUKE_PATH`

Add **nuke-beeble-ai-tools** as its own entry. It is a separate install from nuke-fal-ai-tools.

```text
NUKE_PATH=C:\Tools\nuke-beeble-ai-tools
```

Or combine with other toolkits (semicolon-separated on Windows):

```text
NUKE_PATH=C:\Tools\nuke-fal-ai-tools;C:\Tools\nuke-beeble-ai-tools
```

Both repos can coexist on `NUKE_PATH`. Each has its own `init.py`, `menu.py`, and `nuke/groups/` folder.

Restart Nuke after changing `NUKE_PATH`.

## 4. Use the SwitchX node

1. **Nodes -> beeble.ai -> SwitchX** (or **Nuke -> beeble.ai -> SwitchX**)
2. Connect `source_video` and `alpha_mask` (both required)
3. Optionally connect `reference_image`
4. Enter a **prompt** (or rely on reference image alone)
5. Set **Input frame range** when inputs need prerendering from a pipe
6. Press **Execute**

On success, a Read node is created in the main graph with the composited MP4.

Temp prerenders go to `nuke_beeble_temp/` next to your saved `.nk` script; API downloads go to `nuke_beeble_output/`.

## Input limits (enforced before upload)

The runner **cancels** if inputs violate Beeble SwitchX limits:

- Max **240 frames** per source and alpha video
- Max **2,770,000 pixels** (width x height)
- Source and alpha must have **matching frame count and resolution**

`ffprobe` must be on `PATH` for validation. If it is missing, the run is cancelled with an error message.

## Troubleshooting

| Problem | What to check |
|---------|----------------|
| Missing group file under `nuke-fal-ai-tools` | Add **nuke-beeble-ai-tools** to `NUKE_PATH` (not only nuke-fal-ai-tools). Restart Nuke. |
| Node missing from menu | `NUKE_PATH` points at install root; restart Nuke |
| Helper fails immediately | **Python 3 cmd** knob matches your launcher (`py -3`, `python3`, or full path) |
| Validation errors | Frame count, resolution, ffprobe on PATH |
| API auth errors | `BEEBLE_API_KEY` env var or node knob |
| Prerender fails | ffmpeg on PATH; save the Nuke script first (temp dirs are next to the `.nk`) |

See [Beeble API errors](https://developer.beeble.ai/docs/errors) for API-side failure details.

## Brand attribution

Applications using the Beeble SwitchX API should include attribution. The SwitchX group node includes **Powered by SwitchX** in its guide text. See [Beeble brand attribution](https://developer.beeble.ai/docs/brand-attribution).
