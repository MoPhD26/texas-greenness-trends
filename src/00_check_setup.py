"""Phase 2 setup check: environment, config, data folder, and Earth Engine access.

Run:  conda run -n rs-trends python src/00_check_setup.py
Add --skip-ee to check everything except Earth Engine.

The Earth Engine project ID is read from the EE_PROJECT environment variable and is
never printed in full or written to disk by this script.
"""

from __future__ import annotations

import argparse
import importlib
import sys

from rstrends.config import ConfigError, data_dir, ee_project, load_config, n_years

PACKAGES = [
    "ee",
    "geemap",
    "numpy",
    "xarray",
    "rioxarray",
    "rasterio",
    "dask",
    "zarr",
    "geopandas",
    "shapely",
    "pyproj",
    "scipy",
    "pandas",
    "statsmodels",
    "pymannkendall",
    "matplotlib",
    "yaml",
]


def mask(value: str) -> str:
    return value[:3] + "*" * max(len(value) - 3, 0)


def check_packages() -> bool:
    ok = True
    for name in PACKAGES:
        try:
            mod = importlib.import_module(name)
            print(f"  ok   {name} {getattr(mod, '__version__', '')}")
        except ImportError as exc:
            ok = False
            print(f"  FAIL {name}: {exc}")
    return ok


def check_data_dir(cfg) -> bool:
    try:
        root = data_dir(cfg)
    except ConfigError as exc:
        print(f"  FAIL {exc}")
        return False
    for sub in cfg["paths"]["subdirs"]:
        (root / sub).mkdir(parents=True, exist_ok=True)
    print(f"  ok   data folder {root} with {', '.join(cfg['paths']['subdirs'])}")
    return True


def check_earth_engine(cfg) -> bool:
    import ee

    try:
        project = ee_project()
    except ConfigError as exc:
        print(f"  FAIL {exc}")
        return False
    try:
        ee.Initialize(project=project)
    except Exception as exc:  # noqa: BLE001  Earth Engine raises several exception types
        print(f"  FAIL could not initialize Earth Engine for project {mask(project)}: {exc}")
        print("       Run the sign-in in docs/earth_engine_setup.md, step 4.")
        return False
    print(f"  ok   initialized Earth Engine for project {mask(project)}")

    ok = True
    for sensor, spec in cfg["sensors"].items():
        if not isinstance(spec, dict):
            continue
        try:
            first = ee.ImageCollection(spec["collection"]).limit(1).first().get("system:index")
            print(f"  ok   {sensor}: {spec['collection']} readable (example {first.getInfo()})")
        except Exception as exc:  # noqa: BLE001
            ok = False
            print(f"  FAIL {sensor}: {spec['collection']}: {exc}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-ee", action="store_true", help="skip the Earth Engine check")
    args = parser.parse_args()

    print(f"Python {sys.version.split()[0]}")
    print("Packages:")
    ok = check_packages()

    print("Config:")
    cfg = load_config()
    print(
        f"  ok   {cfg['period']['start_year']}-{cfg['period']['end_year']} ({n_years(cfg)} years)"
    )

    print("Data folder:")
    ok &= check_data_dir(cfg)

    if not args.skip_ee:
        print("Earth Engine:")
        ok &= check_earth_engine(cfg)

    print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
