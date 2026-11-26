# Greening and Browning in Texas and Oklahoma Prairie Parkland, 2000-2026

Where did vegetation greenness change across Bailey's Prairie Parkland (Subtropical) Province 255 over the last 27 years, how did trends differ by land cover, and how much of the change remains once drought is accounted for?

**Status:** Phase 2 of 5 (setup). Results, maps, and the full write-up arrive in later phases.

## Approach in one paragraph

Landsat 5, 7, 8, and 9 Collection 2 surface reflectance, harmonized across sensors, is composited into a March-October median EVI2 for every 30 m pixel and year. Per-pixel trends use the Theil-Sen slope with a Mann-Kendall test corrected for autocorrelation, and false discoveries are controlled across 231 million pixels. Trends are summarized on stable Annual NLCD land cover pixels and compared with drought (SPEI) through residual trend analysis. The full plan, literature review, and design decisions are in [docs/phase1_plan.md](docs/phase1_plan.md).

## Repository layout

| Path | Contents |
|---|---|
| `config/config.yaml` | Study area, years, season, thresholds, grid, compute settings |
| `src/rstrends/` | Pure functions with no network access (validity rules, chunk ledger, and later QA decoding, indices, trend tests) |
| `src/NN_*.py` | Numbered pipeline scripts that do data access |
| `tests/` | pytest tests on small synthetic arrays |
| `docs/` | Plan, setup guides, figures |

Data is never stored in the repo. It lives in `C:\rsdata` (set by `RS_DATA_DIR`).

## Reproduce

1. Install Miniconda, then create the environment from conda-forge:
   `CONDA_CHANNEL_PRIORITY=strict conda env create -f environment.yml`
2. Set up Earth Engine: [docs/earth_engine_setup.md](docs/earth_engine_setup.md)
3. Check setup: `conda run -n rs-trends python src/00_check_setup.py`
4. Run tests: `conda run -n rs-trends pytest`

Inspired by a 2016 class project with Zahra Ghaffari and Saber Brasher.
