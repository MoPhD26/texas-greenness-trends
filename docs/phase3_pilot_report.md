# Phase 3 pilot report

Status: pilot stage done. Nothing beyond the pilot tasks has been launched. Measured on 2026-11-26 (UTC).

## 1. Study area boundary

| Item | Value |
|---|---|
| Source | USDA Forest Service ECOMAP Ecological Provinces, 2007 release (`Ecosys_EcoMapProvinces_2007`), Forest Service Geodata Clearinghouse |
| Citation | Cleland, D.T., Freeouf, J.A., Keys, J.E., Nowacki, G.J., Carpenter, C.A., McNab, W.H. 2007. Ecological Subregions: Sections and Subsections for the conterminous United States. Gen. Tech. Report WO-76D. Washington, DC: USDA Forest Service. Presentation scale 1:3,500,000. https://doi.org/10.2737/WO-GTR-76D |
| Selected feature | `MAP_UNIT_S = 255`, Prairie Parkland (Subtropical) Province |
| Area | 246,477 km2 (CONUS Albers), 66 polygon parts, 10,583 vertices |
| 30 m pixels | 273.9 million |
| File checksum (SHA-256) | 6f4463d0...affd91, stored in the config |

Findings that change the plan:

* **Province 255 does not exist in the newer Ecomap 2025 release.** That release reorganized the hierarchy. The old Province 255 area now falls mostly in Province 352 Cross Timbers (57%) and Province 353 Texas Gulf (24%). The study keeps the 2007 delineation because it is the only source that defines Province 255.
* **The province is 19% larger than the plan said.** The plan used 207,500 km2 and 231 million pixels. The measured values are 246,477 km2 and 273.9 million pixels. Every size and run time estimate scales up by the same amount.

## 2. Harmonization sample and coefficients

Sample: 29,999 points, area proportional by Annual NLCD class with a floor of 500 points per class. 85% of 180,000 random candidates had one land cover class through 2000-2017.

Provisional fit, ETM+ to OLI, 2013 only (25,874 point pairs with at least 4 clear observations from each sensor):

| Band | Method | Slope (95% CI) | Intercept (95% CI) | r | Roy et al. 2016 OLS slope | Roy et al. 2016 OLS intercept |
|---|---|---|---|---|---|---|
| Red | RMA | 1.030 (1.024 to 1.037) | -0.0071 (-0.0076 to -0.0065) | 0.92 | | |
| Red | OLS | 0.950 (0.943 to 0.957) | 0.0001 (-0.0005 to 0.0006) | 0.92 | 0.9047 | 0.0061 |
| NIR | RMA | 1.082 (1.073 to 1.092) | 0.0026 (-0.0002 to 0.0051) | 0.74 | | |
| NIR | OLS | 0.802 (0.791 to 0.812) | 0.0790 (0.0761 to 0.0820) | 0.74 | 0.8462 | 0.0412 |

Mean EVI2 offset (OLI minus ETM+) on the sample: 0.046 before and 0.0002 after the RMA transform.

Read these numbers with three cautions.

1. They use one year of the planned five (2013-2017). The other four years and the twelve TM to ETM+ years have not been sampled yet.
2. In 2013 Landsat 8 data start on April 11, but the Landsat 7 median used March 1 onward. The mismatch adds noise, which is probably why NIR r is only 0.74. The code now restricts both sensors to their common window. 2013 needs to be sampled again with that fix.
3. The Roy et al. values shown are the Table 2 OLS set as given in the Earth Engine community tutorial. I could not open the paper to read its RMA set, so the RMA comparison is still open. If you can share the PDF, I will add it. Our OLS NIR slope is lower than Roy's, as expected when season medians from different dates add noise to the x variable. This is why RMA is primary.

## 3. Pilot export (2012)

| Measure | Value |
|---|---|
| Task | `P_main_2012`, one task, Drive folder `rs_trends_P` |
| Wall time | 33.2 minutes (04:23:49 to 04:57:01 UTC) |
| EECU-hours | 21.35 (76,851 EECU-seconds) |
| Scenes processed | 488 Landsat 7 scenes (bounding box filter) |
| Harmonization used | provisional 2013 ETM+ to OLI coefficients. Run time and cost do not depend on the coefficient values. 2012 is exported again in batch B3. |
| File size | 3.31 GB in 2 files (Section 11.2) |

2012 is a low density year (Landsat 7 only), so it is a lower bound per year. A typical two sensor year has about 1,000 to 1,100 scenes in the bounding box.

## 4. Interactive Earth Engine use (separate line)

Interactive requests made during this stage: the setup check, data probes, the candidate point step (72 requests, 85 s), the 2013 interactive harmonization sample (12 requests, 358 s), the benchmark chunk (27 requests, about 2.5 minutes), and scene count queries. All ran on 2026-11-26 UTC between about 03:45 and 05:10.

Interactive EECU-hours: **to be filled in from the Cloud console.**

## 5. Why the 2013 batch harmonization sample needed three attempts

The batch version of the 2013 sample (`H_sample_etm_oli_2013`) was restarted by Earth Engine twice and was still on attempt 3 when this report was written. The interactive version of the same sample finished in 6 minutes with no failures.

* **Cause.** Earth Engine does not keep the error from a failed attempt in the task record, so I cannot confirm it. The most likely cause is the shape of the job: the 30,000 points travel inside the request as one client side collection, so the export cannot split them across many workers. Each worker then computes per point medians over about 970 scenes, and it can run out of memory or time, which triggers an automatic retry.
* **Quota.** The task record shows EECU for the current attempt only (attempt 1 reached about 1.1 EECU-hours before it restarted). Failed attempts most likely still count against the quota, because the compute was done. The Cloud console total will confirm this.
* **Prevention.** Use the interactive path, which worked: 12 parallel requests of 2,500 points per year. If batch is needed, split each year into about 12 tasks of 2,500 points and raise tileScale. Storing the points as a table asset would also let Earth Engine split the work, but the project has no asset root yet (Section 9).

## 6. One chunk benchmark

Chunk: 512 x 512 pixels in the Blackland Prairie, all 27 years, real data. 98.2% of pixels pass all four validity rules. The median pixel has 26 valid years.

| Measure | Value |
|---|---|
| Core trend suite, one process | 5.4 to 6.0 s per chunk |
| Peak memory per process | 1.6 GB |
| Throughput, 4 workers with one BLAS thread each | 0.268 chunks per second (the best setting tested. 4 workers with multithreaded BLAS gave 0.204, and 6 workers gave 0.248) |
| Chunks that touch the province | 1,318 |
| Benjamini-Hochberg on 27 million p-values | 6.8 s, about 1 minute per index for the province |
| Share of valid pixels significant at q < 0.10 in this chunk | 48.5% (38.3% at q < 0.05) |
| Leave-one-year-out, all pixels | 46 s per chunk |
| Leave-one-year-out, significant pixels only | 12.7 s per chunk |

Projected local run time:

| Step | Hours |
|---|---|
| Core suite, each full length index (EVI2, NIRv, kNDVI, Roy comparison) | 1.4 each, 5.5 total |
| ETM+ only subset (20 years) and OLI only subset (14 years) | 0.7 and 0.4 |
| Leave-one-year-out on all pixels (old plan) | 10.4 |
| **Leave-one-year-out on FDR significant EVI2 pixels (new plan)** | **about 3.2** (1.7 to 4 if 25% to 60% of pixels are significant province wide) |
| **Total with the new leave-one-year-out rule** | **about 10 hours** |

The leave-one-year-out run uses the q-values from the full province EVI2 core run, so it starts after that run and the FDR step finish. Pixels are packed so only significant ones are processed. The config gets one setting for this: `dask_workers: 4` with BLAS threads set to 1 per worker.

## 7. EECU projection for every planned export

Two ways to scale from the pilot set the range. "Per scene" assumes cost grows with the number of scenes (0.0437 EECU-hours per scene in the pilot). "Per year" assumes each year costs the same as 2012. Most of the cost is per scene work (reading, masking, and reprojecting each scene), so the per scene figure is the better guess.

| Export | Scenes | Per year EECU-h | Per scene EECU-h (central) |
|---|---|---|---|
| Main stack, 27 years | 26,294 | 576 | **1,150** |
| ETM+ only subset, 2000-2019 (1 index band) | 10,106 | | up to 442, likely 300-440 |
| OLI only subset, 2013-2019 (1 index band) | 3,671 | | up to 161, likely 110-160 |
| Harmonization samples, 17 years plus the 2013 rerun | | | batch: 40-80 with retries. Interactive: from the console |
| Stable pixel mask, SPEI | | | under 5 (estimate) |
| **Total, current design** | | | **about 1,000 to 1,840, central about 1,800** |

High and low density years: years with two sensors (2000-2011, 2013-2019, 2022-2026) have 870 to 1,117 scenes and should cost about 38 to 49 EECU-hours each. Single sensor years (2012, 2020, 2021) have 488 to 538 scenes and should cost about 21 to 24. Cloudier years cost the same as clear years, because every scene is read whether or not it is clear.

## 8. Ways to cut the cost per year

Savings are estimates. A cheap cost test (Section 10) would measure them before the full run.

| Change | Estimated saving | Effect on the science |
|---|---|---|
| Filter scenes by the province polygon instead of its bounding box | 15-18% (measured: 21,477 scenes instead of 26,294) | None |
| Compute the median and all counts in one pass over the scenes with a combined reducer. The current code passes over the scenes five times (median, three sub-season counts, acquisition count). | 0-40%, depends on how much work Earth Engine shares between passes | None |
| Drop the all-acquisitions count from the annual export and compute it at 300 m for the quality report | 5-15% | Quality report shows acquisitions at 300 m instead of 30 m |
| Export EVI2 only. Run the NIRv and kNDVI checks on a random 10% of chunks. | 20-30% of the main stack | The checks cover a sample, not the whole province. NIRv and kNDVI cannot be rebuilt locally from EVI2 or from median red and NIR, because the median of an index is not the index of the median reflectances. |
| Put the ETM+ only and OLI only medians into the same yearly tasks as extra bands, so each scene is read once | Most of the 410-600 subset cost, leaving maybe 100-200 | None |
| Skip scenes with more than 90% land cloud cover | about 5% (1,000 of 21,477 scenes) | Slightly fewer clear observations. These scenes have under 10% clear land. Reported in the quality report. |
| Export in 60 km tiles that follow the province outline | 0-26% (the province fills 44% of its bounding box) | None, but 110 tasks per year. Only helps if Earth Engine computes masked pixels. Low priority. |
| Export scale | none | 30 m is required for the study |

Combined, my central estimate is a main stack of about 450-650 EECU-hours, subsets of about 100-200, and a total of **about 600-900 EECU-hours**, roughly half the current design.

## 9. Other findings

* **2026 is included.** All 33 path-rows over the province have Tier 1 scenes after October 15, 2026, and the 2026 season has 920 scenes against 897 in 2025. The plan's decision rule keeps 2026.
* **Grid.** Annual NLCD Collection 1 version 2 (from the Earth Engine community catalog) uses Albers on a WGS84 datum, not EPSG:5070. Exports use its exact CRS and transform so pixels align with land cover.
* **Landsat 8 start date** set to April 11, 2013, in the config (operational orbit date, NASA HLS).
* **No Earth Engine asset root.** The project cannot write assets yet ("projects/.../assets not found"). Everything in this stage avoids assets. Setting it up would allow sharded point tables and cheaper reruns, but it is optional.
* **Export bands are all int16**, because one Earth Engine image export uses a single data type. Count bands compress well, so the size cost is small. The verify step will measure it.

## 10. Tier recommendation and schedule

Usage so far this month: 21.35 (pilot) plus at least 2.3 (batch harmonization attempts) plus the interactive total. The quota resets on December 1.

| | Current design (about 1,800) | Reduced design (about 600-900) |
|---|---|---|
| Community, 150 per month | about 12 months | 4-6 months |
| Contributor, 1,000 per month | about 2 months | about 1 month, limited by downloads and Drive space, not quota |

**Recommendation: switch to the Contributor tier, and make the cost reductions anyway.** Even the reduced design takes 4 to 6 months on Community, and going over the quota drops the project into restricted mode until the next month. Contributor needs an active billing account for identity verification, but noncommercial Earth Engine use is not charged (Earth Engine noncommercial tiers page, as checked for the Phase 1 plan). You would do that sign-up yourself.

Recommended schedule, Contributor tier:

1. Now: decide whether to cancel the still running 2013 batch harmonization task. Download the pilot folder and run the verify step to get the real file size.
2. Cost test, needs your approval: export 2012 for one 123 km tile in four variants (current, polygon filter plus single pass, plus EVI2 only, plus folded subsets). About 0.6 EECU-hours each, about 3 total.
3. Harmonization samples: the remaining 16 years plus 2013 again, interactive (about 6 minutes each, about 2 hours in total, so it needs your go-ahead under the 30 minute rule).
4. Main batches B1 to B6 in order, one at a time, each verified and cleared from Drive before the next. With an estimated 1.5 to 2.3 GB per year, a 5 year batch needs 7.5 to 11.5 GB of the 15 GB free Drive space. If the pilot file comes in above 2.5 GB, I will switch to 3 year batches.

On the Community tier, the same order holds, with one or two batches per month after the December 1 reset.

Size estimates stay estimates until the pilot file is measured.

## 11. Update after the Contributor switch (2026-11-26, evening UTC)

### 11.1 Restricted Mode

The project moved to the Contributor tier (1,000 EECU-hours per month). Signs that Restricted Mode has lifted: a small interactive request succeeded, and the harmonization cost check task ran on its first attempt in 42 seconds. Under Restricted Mode, every cost test task had needed 2 or 3 attempts spread over several hours. The Cloud console is the place to confirm the tier status.

### 11.2 Pilot file size (measured)

| Measure | Value |
|---|---|
| Files | 2 GeoTIFF tiles, 683 million grid pixels (the province bounding box) |
| On disk | 3.31 GB, of which 2.45 GB is full resolution data and 0.86 GB is Cloud Optimized GeoTIFF overviews (35% extra) |
| Compression | LZW, pixel interleaved. Inside the province, 7 int16 bands compress to 0.64 of raw, so about 1.28 bytes per band per pixel. Pixels outside the province cost almost nothing. |
| Verification | passed (CRS, 30 m grid alignment, 7 bands, int16, nodata tag) |

**Problem found.** Masked pixels were written as 0, not as the nodata value -32768, even though the export set the nodata option. That covers pixels outside the province and any pixel without a clear view, and 0 is a valid EVI2 value. The pilot file is still fine for timing and size, since zeros and nodata compress alike. Fixes: the export script now replaces masked pixels with -32768 explicitly before export. The verify script now fails a batch if band 1 has no nodata pixels or is exactly 0 in more than 1% of pixels.

### 11.3 Export size and Drive space, from the measured pilot

Bands per year under the revision 4 design: EVI2 and 3 counts, plus 4 ETM+ only bands for 2000-2019 and 4 OLI only bands for 2013-2019. That is 216 band-years.

| Batch | Years | Band-years | Size with overviews | Without overviews |
|---|---|---|---|---|
| B1 | 2000-2004 | 40 | 18.9 GB | 14.0 GB |
| B2 | 2005-2009 | 40 | 18.9 GB | 14.0 GB |
| B3 | 2010-2014 | 48 | 22.7 GB | 16.8 GB |
| B4 | 2015-2019 | 60 | 28.4 GB | 21.0 GB |
| B5 | 2020-2024 | 20 | 9.5 GB | 7.0 GB |
| B6 | 2025-2026 | 8 | 3.8 GB | 2.8 GB |
| Total | | 216 | about 102 GB | about 76 GB |

These use the pilot's 1.28 bytes per band per pixel, which is conservative: the new design has a larger share of count bands, which compress better than index bands. Local disk has 782 GB free, so local space is not a constraint.

Drive is the constraint. B4 alone needs about 28 GB. Two changes would fit it in less space:

1. Export plain GeoTIFF instead of Cloud Optimized GeoTIFF. The overviews are never used, because the files are read into 512 x 512 chunks locally. This saves about 26%.
2. Split the larger batches. On 15 GB of free Drive space, B1 to B4 would each need to be split in two (about 2-3 years per task group). With 100 GB or more, the planned 5 year batches fit, one at a time.

### 11.4 Cost test result: not usable as measured

| Variant | EECU-hours | Attempts |
|---|---|---|
| A (pilot design, bounding box filter) | 0.517 | 2 |
| B (outline filter, cloud skip, single pass, 3 indices) | 0.678 | 2 |
| C (B with EVI2 only) | 0.804 | 2 |
| D (C plus subset bands, production design) | 0.806 | 3 |

All four ran under Restricted Mode and were restarted by Earth Engine. The EECU totals include the failed attempts, which is visible because B and C reported EECU while still queued. C costing more than B cannot be a real effect, since C computes a subset of B. A clean rerun of the four variants on the same tile, now that the quota is restored, would cost about 3 EECU-hours. Not started. It needs approval.

### 11.5 Harmonization: clustered batch sample

Design: 200 random boxes of 64 x 64 pixels (1.92 km) fully inside the province, grid-aligned and non-overlapping. Inside the boxes, 10,005 stable Annual NLCD pixels are drawn, area proportional by class with a floor of 300 points per class. The draw happens inside each batch task with a fixed seed. Each row records the pixel's grid coordinates, so the point sets of different tasks can be checked against each other.

| Class | Stable pixels in boxes | Points |
|---|---|---|
| 21 developed open | 25,689 | 321 |
| 22 developed low | 25,474 | 318 |
| 23 developed medium | 12,193 | 300 |
| 24 developed high | 3,607 | 300 |
| 31 barren | 1,751 | 300 |
| 41 deciduous forest | 69,647 | 869 |
| 42 evergreen forest | 16,254 | 300 |
| 43 mixed forest | 18,210 | 300 |
| 52 shrub | 27,301 | 341 |
| 71 grassland | 187,152 | 2,336 |
| 81 pasture and hay | 215,588 | 2,691 |
| 82 cropland | 82,404 | 1,029 |
| 90 woody wetlands | 23,562 | 300 |
| 95 emergent wetlands | 3,688 | 300 |

Rare classes (barren, developed high, emergent wetlands) come from few boxes, so their by-class statistics will have wide intervals.

Each task samples, for both sensors: median red and NIR, their standard deviations, and the clear observation count, all over the dates both sensors cover.

**Cost check (one year, TM to ETM+ 2006): 3.02 EECU-hours, one attempt, 42 seconds.** That is about 10 times cheaper per year than the interactive sample of scattered points (about 30 EECU-hours per year).

Projection for the rest:

| Job | Estimate |
|---|---|
| TM to ETM+, 11 more years (2000-2005, 2007-2011) | about 33 EECU-hours (2.5-4 per year) |
| ETM+ to OLI, pooled 2013-2017 (one task over five years of both sensors) | about 15 EECU-hours (12-20) |
| Total remaining | about 48 EECU-hours (40-60) |

Fit method: ETM+ to OLI on pooled per-point medians, TM to ETM+ by year, at least 10 clear observations per sensor at each point. RMA is primary, OLS for the Roy comparison, and Deming as a check. The Deming error variance ratio is estimated from each point's sampling variance of the median, (pi / 2) x sd^2 / n, averaged per sensor. Confidence intervals come from a cluster bootstrap over boxes (1,000 resamples). Outputs: `fit_table.csv`, `fit_by_class.csv`, and `evi2_offsets.csv`. The last gives mean EVI2 offset and RMSD before and after each transform (our RMA, Deming, and OLS, and Roy RMA and OLS), overall and by class. All of this was tested end to end on synthetic files.

Roy et al. (2016), Table 2, surface reflectance, ETM+ to OLI (OLI = intercept + slope x ETM+):

| Band | Roy OLS slope | Roy OLS intercept | Roy RMA slope | Roy RMA intercept |
|---|---|---|---|---|
| Red | 0.9047 | 0.0061 | 0.9825 | -0.0022 |
| NIR | 0.8462 | 0.0412 | 1.0073 | -0.0021 |

Checked against the printed Table 2 (2026-11-26). Roy's OLS r-squared, from ETM+ and OLI pairs one day apart: red 0.848, NIR 0.706. That is the context for our fit quality: our medians come from different dates over a season or several seasons, not pairs one day apart, so r-squared values near Roy's would be a good result. Source: https://pmc.ncbi.nlm.nih.gov/articles/PMC6999663/

### 11.6 Budget, November 2026 (Contributor, 1,000 EECU-hours)

| Item | EECU-hours |
|---|---|
| Total this month (Cloud console, 17.95% of the 1,000 quota) | 179.5 |
| of which batch tasks | 28.3 (pilot 21.35, cost test 2.8 with failed attempts, cancelled 2013 sample 1.18, harmonization cost check 3.02) |
| of which interactive | about 151, almost all of it the scattered-point harmonization sample |
| Committed: remaining harmonization (12 tasks) and the clean cost test rerun | about 51 (estimate) |
| Remaining | about 770 of 1,000 (stop-and-ask line 850) |

The quota is confirmed as 1,000: the project's "Monthly EECU-seconds" quota reads 3,600,000 seconds in the Service Usage API.

### 11.7 Export schedule with 400 GB of Drive

All batches fit in Drive at once as plain GeoTIFF (about 76 GB), so batches no longer wait for the one before to be downloaded and cleared. The export script now writes plain GeoTIFF and only requires the pilot to be verified before a main batch.

1. Review the harmonization fits and the clean cost test together. Finalize the coefficients. No main exports before this.
2. Submit B1 to B6 together or in two waves, within the month's quota. Earth Engine runs a few tasks at a time per project and queues the rest.
3. Download each batch as it finishes, while later batches still run. Verify each batch with `03_verify_batch.py`. Nothing is deleted from Drive until its batch passes, and deleting still needs your approval.
4. Expected cost with the approved cuts: about 600-900 EECU-hours for the main stack (Section 7 and 8). This will be updated from the clean cost test. If the November remainder is not enough, the rest runs after the December 1 reset, within December's 850 stop-and-ask line.

## 12. Harmonization review and export plan (2026-11-27 UTC)

### 12.1 Class offsets after ETM+ to OLI

Detectable trends come from the one-chunk benchmark (27 years of real composites, 260,325 valid pixels, 12 classes with at least 200 pixels), using Weatherhead et al. (1998). Shrub (52) and emergent wetlands (95) are missing from the chunk, so their values are a quick estimate from Landsat 7 yearly medians at the harmonization points. The two sources agree overall (median 0.00101 and 0.00102 EVI2 per year). A step of size d at 2013 turns into a false Theil-Sen trend of 0.055 d per year (OLS gives 0.056 d).

| Class | Offset, single fit (95% CI) | False trend / detectable | Offset, group fit (95% CI) | False trend / detectable |
|---|---|---|---|---|
| 21 developed open | -0.002 (-0.005 to 0.001) | 0.09 | -0.003 (-0.007 to 0.001) | 0.17 |
| 22 developed low | -0.002 (-0.006 to 0.001) | 0.15 | -0.001 (-0.004 to 0.002) | 0.06 |
| 23 developed medium | -0.008 (-0.013 to -0.003) | 0.75 | -0.001 (-0.005 to 0.003) | 0.09 |
| 24 developed high | -0.013 (-0.017 to -0.010) | **2.37** | 0.000 (-0.004 to 0.004) | 0.02 |
| 31 barren | -0.004 (-0.008 to 0.002) | 0.36 | 0.006 (0.001 to 0.010) | 0.59 |
| 41 deciduous forest | -0.005 (-0.010 to 0.000) | 0.27 | 0.002 (-0.001 to 0.006) | 0.13 |
| 42 evergreen forest | -0.003 (-0.011 to 0.006) | 0.21 | 0.001 (-0.005 to 0.007) | 0.04 |
| 43 mixed forest | -0.019 (-0.026 to -0.013) | **1.19** | -0.010 (-0.017 to -0.005) | 0.66 |
| 52 shrub (sample estimate) | 0.007 (0.002 to 0.012) | 0.54 | 0.005 (0.001 to 0.010) | 0.41 |
| 71 grassland | 0.009 (0.006 to 0.012) | 0.48 | 0.005 (0.003 to 0.008) | 0.30 |
| 81 pasture and hay | -0.003 (-0.006 to -0.001) | 0.14 | -0.005 (-0.008 to -0.003) | 0.24 |
| 82 cropland | 0.010 (0.005 to 0.016) | 0.38 | 0.006 (0.001 to 0.011) | 0.21 |
| 90 woody wetlands | -0.012 (-0.019 to -0.006) | 0.65 | -0.003 (-0.008 to 0.002) | 0.17 |
| 95 emergent wetlands (sample estimate) | -0.011 (-0.017 to 0.007) | 0.56 | -0.015 (-0.021 to 0.003) | 0.76 |

Recommendation: **group fits**. The single fit fails the rule "well below the detectable trend" in two classes and is half or more of it in four more. The group fits bring every class to 0.76 or less, and 11 of 14 below 0.45. Mixed forest keeps the largest remaining offset (-0.010), which the OLI only subset check will watch. A 64 x 64 pixel test in Earth Engine confirmed the group transform works per pixel from the Annual NLCD class of each year, with shifts in the expected direction for each class.

### 12.2 TM to ETM+ fits (minimum 6 clear observations)

| Year | Points (of 10,005) | Boxes | Red RMA slope | NIR RMA slope (95% CI) | NIR R2 | Raw EVI2 offset (95% CI) | After |
|---|---|---|---|---|---|---|---|
| 2000 | 6,954 | 160 | 1.031 | 0.973 (0.942-1.013) | 0.67 | -0.015 (-0.022 to -0.009) | 0.000 |
| 2001 | 7,461 | 174 | 1.046 | 0.957 (0.920-0.995) | 0.70 | +0.014 (0.011 to 0.018) | 0.000 |
| 2002 | 5,385 | 140 | 1.020 | 0.988 (0.943-1.034) | 0.63 | -0.003 (-0.008 to 0.002) | 0.000 |
| 2003 | 4,977 | 143 | 0.985 | 1.029 (0.984-1.080) | 0.62 | -0.007 (-0.013 to -0.001) | 0.000 |
| 2004 | 4,376 | 136 | 1.011 | **1.098 (1.030-1.166)** | 0.48 | -0.022 (-0.030 to -0.014) | 0.000 |
| 2005 | 6,885 | 180 | 1.018 | 0.998 (0.963-1.032) | 0.64 | +0.003 (-0.001 to 0.007) | 0.000 |
| 2006 | 7,393 | 185 | 1.016 | 0.956 (0.914-1.001) | 0.66 | -0.001 (-0.006 to 0.004) | 0.000 |
| 2007 | 3,624 | 118 | 1.047 | 0.996 (0.947-1.047) | 0.57 | +0.011 (0.003 to 0.019) | 0.000 |
| 2008 | 6,396 | 170 | 1.029 | 1.036 (0.991-1.093) | 0.45 | +0.015 (0.009 to 0.021) | 0.000 |
| 2009 | 5,853 | 152 | 1.078 | 1.007 (0.965-1.050) | 0.51 | +0.002 (-0.004 to 0.009) | 0.000 |
| 2010 | 6,797 | 175 | 1.022 | 1.038 (0.974-1.111) | 0.62 | -0.007 (-0.011 to -0.003) | 0.000 |
| 2011 | 8,507 | 192 | 1.063 | 0.965 (0.940-0.994) | 0.75 | +0.005 (0.002 to 0.008) | 0.000 |

Red R2 is 0.82-0.94 in every year. 2004 NIR still stands out: it is the only year whose NIR slope interval lies above 1, and it has the largest raw offset. It falls in the fast 2003-2007 Landsat 5 drift period, so it is plausible rather than an artifact. The smooth-in-time check (cubic in slope and level) leaves offsets close to the raw ones, because the raw offsets change sign from year to year. Yearly fits stay primary.

By class within single years, offsets after the TM to ETM+ transform reach 0.03-0.06 in a few small groups (mixed forest, wetlands, 60-470 points). These rest on few points per year and enter only the TM share of 2000-2011 composites.

### 12.3 Clean cost test (one 3,072 x 3,072 pixel tile, 2015, first attempts)

| Variant | EECU-hours | Ratio to A |
|---|---|---|
| A: pilot design, 3 indices, five passes, bounding box filter | 0.519 | 1.00 |
| B: outline filter, cloud skip, single pass, 3 indices | 0.868 | 1.67 |
| C: B with EVI2 only | 0.541 | 1.04 |
| D: C plus ETM+ only and OLI only bands (production) | 0.672 | 1.29 |

The single pass and dropping NIRv and kNDVI did not reduce cost on this tile, and B cost more than A. The tile lies inside the scene footprints, so the outline filter cannot save anything here. The real saving in D is folding the subsets in: the old design needed separate subset exports, about 1.5 to 2 times A for 2000-2019. The outline filter and cloud skip still remove about 21% of scenes province wide (scene counts).

Projection per year: the pilot cost (21.35 EECU-hours for 488 scenes) scaled by each year's scene count after the outline filter and cloud skip, times 1.29 (2000-2019, D) or 1.04 (2020-2026, C).

| Batch | Years | EECU-hours |
|---|---|---|
| B1 | 2000-2004 | 214 |
| B2 | 2005-2009 | 224 |
| B3 | 2010-2014 | 205 |
| B4 | 2015-2019 | 233 |
| B5 | 2020-2024 | 157 |
| B6 | 2025-2026 | 80 |
| Total | | about 1,110 (about 1,420 if the outline filter saves nothing) |

Two-sensor years cost about 40-49, single-sensor years (2012, 2020, 2021) about 18-22. The group harmonization adds a class lookup per observation, which is not yet measured.

### 12.4 Export plan and budget

| Item | EECU-hours |
|---|---|
| November spent (interactive 151.2, batch 86.6) | 237.8 |
| Committed | 0 |
| Remaining under the 850 stop line | about 612 |

Proposed waves, once the coefficients are final:

1. November: B4 first (the costliest design, 2 sensors with both subsets). Check the EECU of its first finished year against the projection (about 46) before adding more. Then B1 and B6. Total about 527, leaving about 85 under the 850 line.
2. December (after the reset): B2, B3, B5, about 586.
3. Download and verify each batch as it lands, without overviews (about 76 GB in Drive at peak if nothing is cleared).

If the first year comes in more than 20% above projection, I stop and re-plan before submitting more.
