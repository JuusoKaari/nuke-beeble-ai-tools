# nuke-beeble-ai-tools

Nuke plugin for [Beeble SwitchX](https://developer.beeble.ai/docs) video compositing (custom alpha mask mode).

## Requirements

- Foundry Nuke 8.0+ (tested on 11.3v6)
- System Python 3 (runs the API helper via subprocess; stdlib only, no pip packages)
- ffmpeg + ffprobe on `PATH` (video prerender and input validation)
- Beeble API key ([authentication docs](https://developer.beeble.ai/docs/authentication))

## Quick start

1. Download the [latest release](https://github.com/JuusoKaari/nuke-beeble-ai-tools/releases/latest) or `git clone`.
2. Extract (or clone) to a permanent folder. The release zip contains a single top-level `nuke-beeble-ai-tools/` folder.
3. Add **that folder** (the one with `init.py`) to `NUKE_PATH` (separate from nuke-fal-ai-tools if you use both).
4. Set environment variable `BEEBLE_API_KEY`.
5. Restart Nuke.
6. Create a node via **Nodes -> beeble.ai -> SwitchX** or **SwitchX 2.0**.

See [docs/INSTALL.md](docs/INSTALL.md) for full setup steps. Release notes: [CHANGELOG.md](CHANGELOG.md).

## Two SwitchX nodes

| Menu item | API | Notes |
|-----------|-----|--------|
| **SwitchX** | Legacy `POST /v1/switchx/generations` | Original integration. Unchanged. |
| **SwitchX 2.0** | Product API `POST /v1/products/switchx/jobs` with model `switchx-2.0` | New node. Polls `/v1/product-jobs/{id}`. Results under `outputs`. |

SwitchX 2.0 needs an **organization-bound** API key with the `switchx` product enabled for your Beeble organization. Product availability depends on your org rollout. Optional `BEEBLE_TEAM_ID` is sent as `X-Beeble-Team-Id` when set.

### SwitchX 2.0 controls

- **Camera tracking** - when enabled, the generated environment follows the source camera motion (SwitchX 2.0-specific).
- **Mode** - `standard` (default) or `fast`. A later Finish workflow needs a successful **standard** parent job ID (`dap_...`), which this node stores on `last_job_id`. Finish itself is not implemented in this pass.
- **Max resolution** - `720` or `1080` (Product API examples use 720; higher resolutions for Finish are documented separately).

Local pre-upload checks still use the same frame/pixel caps as legacy SwitchX (240 frames, 2,770,000 pixels). Live `input_schema` for `switchx-2.0` may differ; fetch `GET /v1/products/switchx/models` with an org key to confirm.

## Node inputs (both nodes)

Inputs are Nuke graph pipes. The runners prerender automatically when needed; you do not have to write intermediate files by hand.

| Input | Required | Notes |
|-------|----------|-------|
| `source_video` | Yes | Any Nuke image/video pipe. Automatically prerendered to compatible video when needed. |
| `alpha_mask` | Yes | Any Nuke matte pipe. **Mask channel** selects alpha or luminance; automatically normalized and prerendered. |
| `reference_image` | No | Any Nuke image pipe. Automatically rendered to a compatible still when needed. |

At least one of **prompt** or **reference_image** is required.

### Mask channel

Both SwitchX nodes expose **Mask channel** (default `alpha`):

- **alpha** - use the input alpha channel, copy it into grayscale RGB (`R = G = B = alpha`) for the upload video
- **luminance** - convert visible RGB to grayscale and copy that into R/G/B

Alpha masks always go through this normalization so the selected channel is what Beeble receives.

### When prerender is skipped

- **source_video**: a Read pointing at a single compatible MP4/MOV may be used directly
- **reference_image**: a Read pointing at a PNG/JPEG may be used directly
- **alpha_mask**: always normalized and prerendered (no direct MP4/MOV pass-through)

## License

See [LICENSE](LICENSE).

## Links

- [Latest release](https://github.com/JuusoKaari/nuke-beeble-ai-tools/releases/latest)
- [Beeble developer docs](https://developer.beeble.ai/docs)
