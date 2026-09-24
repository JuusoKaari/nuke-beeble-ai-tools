# Changelog

All notable changes to this project are documented here.

## [Unreleased]

Initial public release packaging for the Beeble SwitchX toolkit for Foundry Nuke.

### Included nodes (2)

- SwitchX (`beeble_switchx_v1.nk`) - legacy `POST /v1/switchx/generations` with custom alpha mask
- SwitchX 2.0 (`beeble_switchx2_v1.nk`) - Product API `POST /v1/products/switchx/jobs` with model `switchx-2.0`, camera tracking, mode, and max resolution knobs; stores `last_job_id` for a future Finish workflow

### Notes

- Install from the GitHub Release ZIP or clone; point `NUKE_PATH` at the folder that contains `init.py` (see [docs/INSTALL.md](docs/INSTALL.md)).
- System Python 3 runs the API helpers (stdlib only). Nuke embedded Python runs runners and menu bootstrap.
- SwitchX 2.0 needs an organization-bound Beeble API key with the `switchx` product enabled.
- Beeble API usage is billed to your account; models and endpoints may change without notice.
