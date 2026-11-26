"""Load and validate the study configuration, and resolve local paths and secrets.

Secrets are never read from the config file. The Earth Engine project ID comes from
the EE_PROJECT environment variable. The data folder comes from RS_DATA_DIR, with
the config value as a fallback.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "config" / "config.yaml"

DATA_DIR_ENV = "RS_DATA_DIR"
EE_PROJECT_ENV = "EE_PROJECT"

# Folder names used by common sync clients. Data must not live under any of them.
SYNCED_FOLDER_MARKERS = ("onedrive", "dropbox", "google drive", "googledrive", "icloud", "box sync")


class ConfigError(ValueError):
    """Raised when the configuration is internally inconsistent."""


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Read the YAML config and validate it."""
    cfg_path = Path(path) if path is not None else DEFAULT_CONFIG
    with open(cfg_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    validate_config(cfg)
    return cfg


def n_years(cfg: dict[str, Any]) -> int:
    """Number of years in the study record, inclusive."""
    return cfg["period"]["end_year"] - cfg["period"]["start_year"] + 1


def validate_config(cfg: dict[str, Any]) -> None:
    """Check that thresholds and years are consistent with each other.

    Raises ConfigError with a plain description of the first problem found.
    """
    start, end = cfg["period"]["start_year"], cfg["period"]["end_year"]
    if end <= start:
        raise ConfigError(f"end_year ({end}) must be after start_year ({start})")
    years = n_years(cfg)

    v = cfg["validity"]
    n_sub = len(cfg["season"]["sub_seasons"])
    if v["min_clear_obs_per_year"] < 1:
        raise ConfigError("min_clear_obs_per_year must be at least 1")
    if not 1 <= v["min_sub_seasons_covered"] <= n_sub:
        raise ConfigError(f"min_sub_seasons_covered must be between 1 and {n_sub}")
    if not 1 <= v["min_valid_years"] <= years:
        raise ConfigError(f"min_valid_years must be between 1 and the record length ({years})")
    window = v["endpoint_window_years"]
    if 2 * window > years:
        raise ConfigError("the two endpoint windows overlap: 2 * endpoint_window_years > record")
    if not 1 <= v["min_valid_years_per_endpoint"] <= window:
        raise ConfigError("min_valid_years_per_endpoint must be between 1 and the window length")

    q = cfg["trend"]["fdr_q"]
    if not 0 < q < 1:
        raise ConfigError("fdr_q must be between 0 and 1")
    b0, b1 = cfg["trend"]["baseline_years"]
    if not start <= b0 <= b1 <= end:
        raise ConfigError("baseline_years must fall inside the study period")


def looks_synced(path: str | Path) -> bool:
    """True if any part of the path looks like a cloud sync folder."""
    parts = [p.lower() for p in Path(path).parts]
    return any(marker in part for part in parts for marker in SYNCED_FOLDER_MARKERS)


def data_dir(cfg: dict[str, Any], environ: dict[str, str] | None = None) -> Path:
    """Resolve the data folder from RS_DATA_DIR, falling back to the config value.

    Raises ConfigError if the folder is inside the repository or a synced folder.
    """
    env = os.environ if environ is None else environ
    path = Path(env.get(DATA_DIR_ENV) or cfg["paths"]["data_dir"]).expanduser().resolve()
    if path == REPO_ROOT or REPO_ROOT in path.parents:
        raise ConfigError(f"data folder {path} is inside the repository")
    if looks_synced(path):
        raise ConfigError(f"data folder {path} appears to be inside a synced folder")
    return path


def ee_project(environ: dict[str, str] | None = None) -> str:
    """Return the Earth Engine Cloud project ID from the EE_PROJECT environment variable."""
    env = os.environ if environ is None else environ
    project = env.get(EE_PROJECT_ENV, "").strip()
    if not project:
        raise ConfigError(f"{EE_PROJECT_ENV} is not set. See docs/earth_engine_setup.md, step 5.")
    return project
