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
5. Create a node via **Nodes -> beeble.ai -> SwitchX**

See [docs/INSTALL.md](docs/INSTALL.md) for full setup steps.

## SwitchX node inputs

| Input | Required | Notes |
|-------|----------|-------|
| `source_video` | Yes | MP4/MOV, max 240 frames, max 2,770,000 pixels |
| `alpha_mask` | Yes | Frame-by-frame video matte, same length and resolution as source |
| `reference_image` | No | Style/target still (PNG/JPEG/WebP); strongly recommended |

At least one of **prompt** or **reference_image** is required by the Beeble API.

## License

See [LICENSE](LICENSE).
