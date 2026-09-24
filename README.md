# nuke-beeble-ai-tools

Nuke plugin for [Beeble SwitchX](https://developer.beeble.ai/docs) video compositing (custom alpha mask mode).

## Requirements

- Foundry Nuke 8.0+ (tested on 11.3v6)
- System Python 3 (runs the API helper via subprocess; stdlib only, no pip packages)
- ffmpeg + ffprobe on `PATH` (video prerender and input validation)
- Beeble API key ([authentication docs](https://developer.beeble.ai/docs/authentication))

## Quick start

1. Clone or download this repo to a stable folder, e.g. `C:\Tools\nuke-beeble-ai-tools`
2. Add **this repo's root** to `NUKE_PATH` (separate from nuke-fal-ai-tools if you use both)
3. Set environment variable `BEEBLE_API_KEY`
4. Restart Nuke
5. Create a node via **Nodes -> beeble.ai -> SwitchX** or **SwitchX 2.0**

See [docs/INSTALL.md](docs/INSTALL.md) for full setup steps.

## Two SwitchX nodes

| Menu item | API | Notes |
|-----------|-----|--------|
| **SwitchX** | Legacy `POST /v1/switchx/generations` | Original integration. Unchanged. |
| **SwitchX 2.0** | Product API `POST /v1/products/switchx/jobs` with model `switchx-2.0` | New node. Polls `/v1/product-jobs/{id}`. Results under `outputs`. |

SwitchX 2.0 needs an **organization-bound** API key with the `switchx` product enabled for your Beeble organization. Product availability depends on your org rollout. Optional `BEEBLE_TEAM_ID` is sent as `X-Beeble-Team-Id` when set.

### SwitchX 2.0 controls

- **Camera tracking** — when enabled, the generated environment follows the source camera motion (SwitchX 2.0-specific).
- **Mode** — `standard` (default) or `fast`. A later Finish workflow needs a successful **standard** parent job ID (`dap_…`), which this node stores on `last_job_id`. Finish itself is not implemented in this pass.
- **Max resolution** — `720` or `1080` (Product API examples use 720; higher resolutions for Finish are documented separately).

Local pre-upload checks still use the same frame/pixel caps as legacy SwitchX (240 frames, 2,770,000 pixels). Live `input_schema` for `switchx-2.0` may differ; fetch `GET /v1/products/switchx/models` with an org key to confirm.

## Node inputs (both nodes)

| Input | Required | Notes |
|-------|----------|-------|
| `source_video` | Yes | MP4/MOV |
| `alpha_mask` | Yes | Frame-by-frame video matte, same length and resolution as source |
| `reference_image` | No | Style/target still (PNG/JPEG/WebP); strongly recommended |

At least one of **prompt** or **reference_image** is required.

## License

See [LICENSE](LICENSE).
