# Project rules for Claude Code

These rules apply to every session in this repository. Follow them unless I say otherwise in chat.

## Python environment

* Use a dedicated conda environment named `rs-trends`. Never install packages into `base`.
* Install from conda-forge with strict channel priority. Geospatial libraries such as GDAL, rasterio, and geopandas install cleanly on Windows from conda-forge and often break with pip. Use pip only for packages that are not on conda-forge, and say so when you do.
* Python version: 3.11 unless a required package needs something else. Tell me if it does.
* Keep `environment.yml` in the repo root as the source of truth. Whenever you add or remove a package, update `environment.yml` in the same step and tell me what the package is for.
* Each shell command you run starts fresh, so `conda activate` does not carry over between commands. Run Python through the environment explicitly:
  * `conda run -n rs-trends python src/01_example.py`
  * `conda run -n rs-trends pytest`
* If `conda` is not found in Git Bash, stop and tell me. I'll fix it by running `conda init bash` in the Anaconda Prompt.

## Core libraries (confirm or adjust in the Phase 1 plan)

* Data access: `earthengine-api`, `geemap`, or `earthaccess`, depending on the platform chosen in Phase 1
* Rasters and arrays: `xarray`, `rioxarray`, `rasterio`, `numpy`
* Vectors: `geopandas`, `shapely`, `pyproj`
* Statistics: `scipy`, `statsmodels`, `pymannkendall`
* Plotting and maps: `matplotlib`, plus `cartopy` or `contextily` if needed
* Quality: `pytest`, `ruff`

Don't add heavy dependencies without asking. If one library would replace three, propose it.

## Code standards

* Numbered pipeline scripts in `src/`. One config file for the study area, years, and thresholds. No hard-coded paths or magic numbers in scripts.
* Keep pure functions (math, QA bit decoding, trend tests) separate from data access, so they can be tested without network access.
* Write pytest tests with small synthetic arrays for every pure function. Run `ruff` and `pytest` before calling any step done.
* GitHub Actions CI runs ruff and pytest on every push.

## Secrets

* Never commit credentials, Earth Engine project IDs, Earthdata logins, tokens, or `.netrc` files. Read them from environment variables. Keep any local credential files in `.gitignore`.
* CI fails if anything resembling a key is committed.
* I do all sign-ins myself. Never ask me to paste a password into chat.

## Working style

* Work in the phases from my kickoff prompt and stop for approval after each one.
* Explain decisions in plain language, with the reason and a citation where one applies. I need to defend every choice in interviews.
* Only cite papers you can verify. Never invent ASPRS requirements.
* Before any long download or computation, estimate the data size and run time and ask first.

## Writing rules for anything I'll publish (README, docs, figure captions, manuscript text)

* No em dashes or en dashes. Use hyphens for year ranges (2015-2026).
* No semicolons.
* Plain, human language. No filler.
