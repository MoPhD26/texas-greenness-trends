import copy

import pytest

from rstrends.config import (
    REPO_ROOT,
    ConfigError,
    data_dir,
    ee_project,
    load_config,
    looks_synced,
    n_years,
    validate_config,
)


@pytest.fixture
def cfg():
    return load_config()


def test_repo_config_is_valid(cfg):
    assert n_years(cfg) == cfg["period"]["end_year"] - cfg["period"]["start_year"] + 1
    # 30 m north-up grid on the Annual NLCD origin
    a, b, _, d, e, _ = cfg["grid"]["crs_transform"]
    assert (a, b, d, e) == (30, 0, 0, -30)


def test_config_holds_no_project_id(cfg):
    text = (REPO_ROOT / "config" / "config.yaml").read_text(encoding="utf-8").lower()
    assert "ee_project:" not in text
    assert "project_id" not in text


@pytest.mark.parametrize(
    "path, value",
    [
        (("validity", "min_valid_years"), 99),
        (("validity", "endpoint_window_years"), 14),
        (("validity", "min_valid_years_per_endpoint"), 6),
        (("validity", "min_sub_seasons_covered"), 4),
        (("trend", "fdr_q"), 1.5),
        (("trend", "baseline_years"), [1990, 1994]),
    ],
)
def test_inconsistent_values_rejected(cfg, path, value):
    bad = copy.deepcopy(cfg)
    bad[path[0]][path[1]] = value
    with pytest.raises(ConfigError):
        validate_config(bad)


def test_synced_folder_detection():
    assert looks_synced("C:/Users/me/OneDrive/rsdata")
    assert looks_synced("C:/Users/me/Dropbox/data")
    assert not looks_synced("C:/rsdata")


def test_data_dir_env_overrides_config(cfg, tmp_path):
    assert data_dir(cfg, environ={"RS_DATA_DIR": str(tmp_path)}) == tmp_path.resolve()


def test_data_dir_rejects_repo_and_synced(cfg):
    with pytest.raises(ConfigError):
        data_dir(cfg, environ={"RS_DATA_DIR": str(REPO_ROOT / "data")})
    with pytest.raises(ConfigError):
        data_dir(cfg, environ={"RS_DATA_DIR": "C:/Users/me/OneDrive/rsdata"})


def test_ee_project_from_environment_only():
    assert ee_project({"EE_PROJECT": "  abc  "}) == "abc"
    with pytest.raises(ConfigError):
        ee_project({})
