# Installation

Setup guide for **nuke-beeble-ai-tools**.

**Platform support:** Developed and tested on **Windows**. macOS and Linux should work with the same env vars and folder layout, but path separators and Python launchers differ.

## Requirements

| Item | Notes |
|------|--------|
| **Foundry Nuke** | Nuke 8.0+ (tested on 11.3v6). Group nodes; embedded Python 2.7 or 3.x |
| **System Python 3** | Separate from Nuke - runs helpers via subprocess |
| **ffmpeg + ffprobe** | On `PATH` for video prerender, validation, and Read frame-range probing |
| **Beeble account** | API key from [Beeble developer docs](https://developer.beeble.ai/docs/authentication) |
| **Internet** | Helper calls Beeble cloud APIs |

### Two Python versions (important)

| Runtime | Version | What runs there |
|---------|---------|-----------------|
| **Nuke embedded** | 2.7 (classic) or 3.x (Nuke 13.2+) | `init.py`, `menu.py`, runners, prerender utilities |
| **System / shell** | Python 3 | `beeble_switchx_helper.py`, `beeble_switchx2_helper.py`, Beeble REST API calls |

Helpers use **stdlib only** - no `pip install` is required.

The **Python 3 cmd** knob on the node (default `py -3`) points at the system interpreter, not Nuke's.

## 1. Get the toolkit

Pick a permanent install location, for example:

```text
C:\Tools\nuke-beeble-ai-tools
```

`NUKE_PATH` must point at the folder that contains `init.py`, `menu.py`, and `nuke/` (the install root). Do not point at the inner `nuke/` folder.

### Option A: Download release zip (recommended)

1. Open the [latest release](https://github.com/JuusoKaari/nuke-beeble-ai-tools/releases/latest).
2. Download `nuke-beeble-ai-tools-vX.Y.Z.zip` (asset name matches the release tag).
3. Extract the zip. It contains a single top-level folder `nuke-beeble-ai-tools/`.
4. Move or rename that folder to your install path, e.g. `C:\Tools\nuke-beeble-ai-tools`.

After extraction, `C:\Tools\nuke-beeble-ai-tools\init.py` should exist.

Nuke install hints prefer the latest release URL when a published tag exists; otherwise they fall back to the repo page.

### Option B: Clone with Git

Use this if you prefer `git pull` for updates.

```powershell
git clone https://github.com/JuusoKaari/nuke-beeble-ai-tools.git C:\Tools\nuke-beeble-ai-tools
```

## 2. Set your Beeble API key

**Recommended:** set user environment variable `BEEBLE_API_KEY` to your secret key. The runner passes it to the helper via the subprocess environment (not the command line).

**Legacy SwitchX** works with a Developer API key for `/v1/switchx/generations`.

**SwitchX 2.0** uses the Product API and needs an **organization-bound** key with the `switchx` product enabled. Optional: set `BEEBLE_TEAM_ID` if your org uses internal teams (sent as `X-Beeble-Team-Id`).

**Alternative:** paste the key into the **BEEBLE_API_KEY** knob on the node. That value is **saved into the `.nk` script** - never share or commit scripts that contain a real key.

Get a key via [Beeble authentication docs](https://developer.beeble.ai/docs/authentication) (legacy) or [enterprise / organization keys](https://developer.beeble.ai/docs/enterprise/authentication).

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

## 4. Use the nodes

### SwitchX (legacy)

1. **Nodes -> beeble.ai -> SwitchX** (or **Nuke -> beeble.ai -> SwitchX**)
2. Connect any Nuke image/video pipe to `source_video` and any matte pipe to `alpha_mask` (both required)
3. Optionally connect any image pipe to `reference_image`
4. Enter a **prompt** (or rely on reference image alone)
5. Set **Mask channel** (`alpha` or `luminance`; default `alpha`)
6. Set **Input frame range** when inputs need prerendering from a pipe
7. Press **Execute**

### SwitchX 2.0 (Product API)

1. **Nodes -> beeble.ai -> SwitchX 2.0**
2. Same inputs and **Mask channel** as legacy SwitchX
3. Set **Camera tracking** if you want the generated environment to follow source camera motion
4. Prefer **Mode = standard** if you may Finish the job later (Finish is not in this toolkit yet; the node stores `last_job_id`)
5. Press **Execute**

On success, a Read node is created in the main graph with the composited MP4.

Temp prerenders go to `nuke_beeble_temp/` next to your saved `.nk` script; API downloads go to `nuke_beeble_output/`.

### Input pipes and prerender

| Input | Required | Notes |
|-------|----------|-------|
| `source_video` | Yes | Any Nuke image/video pipe. Automatically prerendered to compatible video when needed. |
| `alpha_mask` | Yes | Any Nuke matte pipe. Mask channel selects alpha or luminance; automatically normalized and prerendered. |
| `reference_image` | No | Any Nuke image pipe. Automatically rendered to a compatible still when needed. |

- Compatible **source_video** Reads (single MP4/MOV) may bypass prerendering.
- Compatible **reference_image** Reads (PNG/JPEG) may be used directly.
- **alpha_mask** always goes through mask normalization so the selected **Mask channel** is sent correctly (no direct video pass-through).

## Input limits (enforced before upload)

The runner **cancels** if inputs violate the local SwitchX limits used by this toolkit:

- Max **240 frames** per source and alpha video
- Max **2,770,000 pixels** (width x height)
- Source and alpha must have **matching frame count and resolution**

These match the legacy SwitchX docs. SwitchX 2.0 live model schema may differ; confirm with `GET /v1/products/switchx/models` when you have an org key.

`ffprobe` must be on `PATH` for validation. If it is missing, the run is cancelled with an error message.

## Troubleshooting

| Problem | What to check |
|---------|----------------|
| Missing group file under `nuke-fal-ai-tools` | Add **nuke-beeble-ai-tools** to `NUKE_PATH` (not only nuke-fal-ai-tools). Restart Nuke. |
| Node missing from menu | `NUKE_PATH` points at install root; restart Nuke |
| Helper fails immediately | **Python 3 cmd** knob matches your launcher (`py -3`, `python3`, or full path) |
| Validation errors | Frame count, resolution, ffprobe on PATH |
| Legacy API auth errors | `BEEBLE_API_KEY` env var or node knob |
| SwitchX 2.0 "organization-bound" / product errors | Use an org API key; confirm `switchx` is enabled; optional `BEEBLE_TEAM_ID` |
| Prerender fails | ffmpeg on PATH; save the Nuke script first (temp dirs are next to the `.nk`) |

See [Beeble API errors](https://developer.beeble.ai/docs/errors) and [enterprise errors](https://developer.beeble.ai/docs/enterprise/errors) for API-side failure details.

## Updating

### Zip install

1. Download the new release zip from [Releases](https://github.com/JuusoKaari/nuke-beeble-ai-tools/releases/latest).
2. Extract over your existing install folder, or extract to a new folder and update `NUKE_PATH`.
3. Restart Nuke. Recreate SwitchX / SwitchX 2.0 nodes from the menu if baked group graphs need a refresh.

### Git clone

```powershell
cd C:\Tools\nuke-beeble-ai-tools
git pull
```

Restart Nuke afterward.

## Brand attribution

Applications using the Beeble SwitchX API should include attribution. The group nodes include **Powered by SwitchX** in their guide text. See [Beeble brand attribution](https://developer.beeble.ai/docs/brand-attribution).
