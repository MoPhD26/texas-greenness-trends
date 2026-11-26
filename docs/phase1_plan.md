# Phase 1: Literature Review and Study Plan (revision 2)

Texas greenness trends, Bailey's Prairie Parkland (Subtropical) Province 255, 2000-2026

Status: **approved** (revision 3, 2026-11-25). Revision 2 was approved with the decisions listed in Section 0.1.

---

## 0.1 Revision 3: approved decisions and additions

| Item | Decision |
|---|---|
| Landsat 7 cutoff | January 1, 2020. The OLI-only sensitivity run (2013-2026) directly tests the effect of including Landsat 7 in 2013-2019 (Section 5.6). |
| Harmonization | Coefficients fitted on our Collection 2 data are primary. Roy et al. (2016) is the comparison run. |
| Index | EVI2 primary. NIRv and kNDVI as checks. |
| Thresholds | At least 4 clear observations per pixel-year. At least 20 valid years of 27. Plus two new rules: seasonal coverage and endpoint coverage (Section 5.1). Pixels removed by each rule are reported by year and by class. |
| Export storage | Batched Google Drive exports of about 5 years each, with a fixed export, download, verify, delete procedure (Section 8.5) |
| Phases | Renumbered. Phase 5 is outputs. |
| Endpoint check | Leave-one-year-out on EVI2 only |
| Data location | All data in `C:\rsdata`, outside the repo and outside any synced folder. Set by the `RS_DATA_DIR` environment variable, with the config as fallback. Data paths are in `.gitignore`. |
| Resumable jobs | Every long local job writes results chunk by chunk and skips chunks already done (Section 8.6) |
| Gates before full runs | The one-year pilot export and the one-chunk benchmark come first, and the measured numbers go to you before anything else is launched |

---

## 0. What changed from revision 1

| Area | Revision 1 | Revision 2 | Driven by |
|---|---|---|---|
| Period | 2015-2026 | 2000-2026, or 2000-2025 if the 2026 March-October season is incomplete in the archive | Your decision 1 |
| Primary data | HLS v2.0 (Landsat 8/9 plus Sentinel-2) | Landsat Collection 2 Level-2 surface reflectance, Landsat 5, 7, 8, 9. Sentinel-2 dropped. | Your decision 1 |
| Harmonization | Built into HLS | Red and NIR of TM and ETM+ harmonized to OLI with coefficients fitted on Collection 2 data in the study area. Roy et al. (2016) coefficients as a comparison. | Your decision 1 and new evidence (Section 3) |
| Landsat 7 | Not used | Used 2000-2019, excluded from 2020 onward because of orbit drift | Qiu et al. 2021, USGS |
| Landsat 5 | Not used | Used 2000-2011 with year-specific adjustment to Landsat 7, because its orbit drifted fast in 2003-2007 | Zhang and Roy 2016, Roy et al. 2020 |
| Primary index | EVI | EVI2. NIRv and kNDVI as sensitivity checks. | Your decision 1, Section 4 |
| Research questions | Five | Three | Your decision 3 |
| Robustness | A research question with five checks | A sensitivity analysis section with three checks. MODIS and VIIRS checks dropped. | Your decision 3 |
| Land cover change | Area estimation with your reference labels | Removed. Annual NLCD used only to define stable pixels. Accuracy assessment listed as future work. | Your decision 4 |
| Study area | Open question | Full Province 255, Texas and Oklahoma | Your decision 5 |
| Compute | Rough estimate | Full estimate for 27 years, chunked local processing with dask and xarray, sized to your laptop | Your decision 6 |
| Non-monotonic trends | Not addressed | Stated limitation plus descriptive trajectories and a break check inside RQ3 | Your note |
| Phases | Six | Five. The accuracy assessment phase is removed, so outputs become Phase 5. | Your decision 4 |
| References | 42 (38 science, 4 software) | 46 (40 science, 6 software). Removed 10 that no longer apply, added 14. Removals listed in Section 2.8. | All of the above |

**MODIS and VIIRS checks: dropped, and I agree they are not essential.** They existed to test the MODIS drift problem. With Landsat as the only record, the right test of sensor effects is inside the Landsat family itself: compare single-sensor subsets against the mixed record over the same years. That is check (a). A 500 m VIIRS comparison would add a resolution mismatch without testing anything check (a) does not already test.

---

## 1. Data facts verified for the new design

| Fact | Finding | Source | Effect on design |
|---|---|---|---|
| Landsat 5 TM end | TM imaging ended in November 2011 | USGS | No TM data in the 2012 season |
| Landsat 5 orbit | Overpass time changed by nearly 1 hour over the mission. The orbit was stable in 1984-1994 and 2007-2011 but changed rapidly in 1995-2000 and 2003-2007. NDVI differences up to 0.11 between years were found for anisotropic cover types. | Zhang and Roy 2016, Roy et al. 2020 | TM is adjusted to ETM+ year by year for 2000-2011 (Section 3) |
| Landsat 7 SLC failure | Scan Line Corrector failed May 31, 2003. Each later scene is missing about 22% of pixels in wedge-shaped stripes. | USGS | Handled by compositing many dates and by clear-count thresholds (Section 5.1) |
| Landsat 7 orbit drift | Last orbit maneuver August 2017, after which the crossing time drifted earlier. A USGS source puts the crossing time outside mission requirements in early 2020. Qiu et al. (2021) measured 2018-2020 effects: small so far (reflectance change under 0.007, NDVI change under 0.003 in 2020), largest in NIR and SWIR, and concluded Landsat 7 kept its science capability until 2020 but is less reliable after. | USGS Landsat 7 pages, Qiu et al. 2021 | **Exclude Landsat 7 from January 1, 2020.** Reasons below. |
| Landsat 7 end | Science data acquired until January 19, 2024. Acquisitions from May 2022 were at a lower orbit, off the WRS-2 grid. Decommissioned June 4, 2025. | USGS | Excluded anyway by the 2020 cutoff |
| Landsat 8 start | In HLS, Landsat 8 data start April 11, 2013, the date the satellite reached its operational orbit | NASA HLS data page | 2013 season has Landsat 8 from mid April onward plus Landsat 7 |
| Landsat 9 start | Data from October 31, 2021. OLI-2 cross-calibrated to OLI during the November 2021 underfly. | NASA HLS data page, Gross et al. 2022 | Treated as equivalent to OLI from the 2022 season |
| Collection 2 processing | TM and ETM+ surface reflectance use LEDAPS. OLI uses LaSRC. | USGS Collection 2 pages, Crawford et al. 2023 | Different atmospheric correction is one reason harmonization still matters |
| Harmonization guidance for Collection 2 | No Roy et al. style analysis has been published for Collection 2. Google's Earth Engine tutorial that applies Roy et al. (2016) coefficients flags that procedure as outdated for Collection 2 surface reflectance. A 2024 study still recommends harmonizing OLI with TM and ETM+. | Earth Engine community tutorial, Trevisiol et al. 2024 | We fit our own coefficients on Collection 2 data and report Roy et al. as a comparison |
| Annual NLCD accuracy | USGS validated Collection 1.0 with 8,360 independent reference plots for 1985-2023. Example: 82.75% overall agreement at Anderson Level I for 2023 (standard error 0.42). Accuracy methods are in Section 6 of the Collection 1 user guide (LSDS-2103, v1.2). | USGS Annual NLCD reference and validation pages | Cited in RQ2. Class-level and per-year figures extracted from the user guide in Phase 3. |

**Why exclude Landsat 7 from 2020 and not later or earlier.**
- Our indices (EVI2, NIRv, kNDVI) depend on NIR, the band Qiu et al. (2021) found most affected by the drift. NDVI partly cancels the effect because it is a ratio. EVI2 and NIRv do not.
- Qiu et al. found effects detectable but small through 2020. USGS says the crossing time left requirements in early 2020. A January 1, 2020 cutoff keeps the well-characterized years and drops the rest.
- The cost is low. Landsat 8 alone covers 2020-2021, and Landsat 9 joins from 2022.
- Cutting at the last maneuver (August 2017) would be more cautious. I don't recommend it because Qiu et al. found no meaningful effect before 2019, and it would throw away two more years of observations. If you prefer it, it is a one-line config change.

---

## 2. Literature review

Every DOI was checked against the Crossref registry on 2026-11-25. Numbering is new.

### 2.1 Trend detection

1. **Sen, P. K. (1968).** Estimates of the regression coefficient based on Kendall's tau. *Journal of the American Statistical Association*. https://doi.org/10.1080/01621459.1968.10480934
   Takeaway: the median of pairwise slopes resists outliers such as single drought years.
2. **Mann, H. B. (1945).** Nonparametric tests against trend. *Econometrica*. https://doi.org/10.2307/1907187
   Takeaway: rank-based test for monotonic trend with no normality assumption.
3. **Hamed, K. H., & Rao, A. R. (1998).** A modified Mann-Kendall trend test for autocorrelated data. *Journal of Hydrology*. https://doi.org/10.1016/S0022-1694(97)00125-X
   Takeaway: corrects the Mann-Kendall variance for autocorrelation, which otherwise inflates false positives.
4. **Yue, S., et al. (2002).** The influence of autocorrelation on the ability to detect trend in hydrological series. *Hydrological Processes*. https://doi.org/10.1002/hyp.1095
   Takeaway: plain prewhitening removes part of a real trend. Supports choosing a variance correction over prewhitening.
5. **Weatherhead, E. C., et al. (1998).** Factors affecting the detection of trends: statistical considerations and applications to environmental data. *Journal of Geophysical Research: Atmospheres*. https://doi.org/10.1029/98JD00995
   Takeaway: the basis of our power analysis, linking detectable trend size to record length, noise, and autocorrelation.
6. **Benjamini, Y., & Hochberg, Y. (1995).** Controlling the false discovery rate: a practical and powerful approach to multiple testing. *Journal of the Royal Statistical Society Series B*. https://doi.org/10.1111/j.2517-6161.1995.tb02031.x
   Takeaway: controls the share of false positives among significant pixels.
7. **Wilks, D. S. (2016).** "The stippling shows statistically significant grid points": how research results are routinely overstated and overinterpreted, and what to do about it. *Bulletin of the American Meteorological Society*. https://doi.org/10.1175/BAMS-D-15-00267.1
   Takeaway: use Benjamini-Hochberg at twice the target alpha for spatially correlated fields.
8. **Cortés, J., et al. (2021).** Where are global vegetation greening and browning trends significant? *Geophysical Research Letters*. https://doi.org/10.1029/2020GL091496
   Takeaway: many reported greening and browning pixels lose significance once multiple testing is controlled.
9. **de Jong, R., et al. (2011).** Analysis of monotonic greening and browning trends from global NDVI time-series. *Remote Sensing of Environment*. https://doi.org/10.1016/j.rse.2010.10.011
   Takeaway: standard reference for Mann-Kendall greening and browning maps.

### 2.2 Non-monotonic change and breaks

10. **de Jong, R., et al. (2012).** Trend changes in global greening and browning: contribution of short-term trends to longer-term change. *Global Change Biology*. https://doi.org/10.1111/j.1365-2486.2011.02578.x
    Takeaway: many long-term trends contain reversals, so a single monotonic slope can hide a greening then browning sequence. The basis of our limitation statement.
11. **Forkel, M., et al. (2013).** Trend change detection in NDVI time series: effects of inter-annual variability and methodology. *Remote Sensing*. https://doi.org/10.3390/rs5052113
    Takeaway: trend results depend on aggregation and method, and breaks change conclusions.
12. **Verbesselt, J., et al. (2010).** Detecting trend and seasonal changes in satellite image time series. *Remote Sensing of Environment*. https://doi.org/10.1016/j.rse.2009.08.014
    Takeaway: BFAST separates trend from breaks. Cited as the method for future break analysis and for our break check framing.

### 2.3 Landsat Collection 2, QA, and compositing

13. **Crawford, C. J., et al. (2023).** The 50-year Landsat collection 2 archive. *Science of Remote Sensing*. https://doi.org/10.1016/j.srs.2023.100103
    Takeaway: describes Collection 2 processing, tiers, and Level-2 products, the reference for our data choice.
14. **Masek, J. G., et al. (2006).** A Landsat surface reflectance dataset for North America, 1990-2000. *IEEE Geoscience and Remote Sensing Letters*. https://doi.org/10.1109/LGRS.2005.857030
    Takeaway: LEDAPS, the atmospheric correction behind TM and ETM+ surface reflectance.
15. **Vermote, E., et al. (2016).** Preliminary analysis of the performance of the Landsat 8/OLI land surface reflectance product. *Remote Sensing of Environment*. https://doi.org/10.1016/j.rse.2016.04.008
    Takeaway: LaSRC, the atmospheric correction behind OLI surface reflectance. The difference from LEDAPS is one reason to harmonize.
16. **Zhu, Z., & Woodcock, C. E. (2012).** Object-based cloud and cloud shadow detection in Landsat imagery. *Remote Sensing of Environment*. https://doi.org/10.1016/j.rse.2011.10.028
    Takeaway: Fmask, the algorithm behind the CFMask flags in the QA_PIXEL band.
17. **Foga, S., et al. (2017).** Cloud detection algorithm comparison and validation for operational Landsat data products. *Remote Sensing of Environment*. https://doi.org/10.1016/j.rse.2017.03.026
    Takeaway: validates CFMask as the operational USGS cloud mask and documents its known weaknesses.
18. **White, J. C., et al. (2014).** Pixel-based image compositing for large-area dense time series applications and science. *Canadian Journal of Remote Sensing*. https://doi.org/10.1080/07038992.2014.945827
    Takeaway: best practices for annual composites from many clear Landsat observations.

### 2.4 Cross-sensor harmonization and orbit effects within Landsat

19. **Roy, D. P., et al. (2016).** Characterization of Landsat-7 to Landsat-8 reflective wavelength and normalized difference vegetation index continuity. *Remote Sensing of Environment*. https://doi.org/10.1016/j.rse.2015.12.024
    Takeaway: OLI and ETM+ differ most in NIR and SWIR. Gives OLS and reduced major axis transformation functions, widely applied to TM as well.
20. **Trevisiol, F., et al. (2024).** Cross-sensors comparison of popular vegetation indexes from Landsat TM, ETM+, OLI, and Sentinel MSI for time-series analysis over Europe. *IEEE Transactions on Geoscience and Remote Sensing*. https://doi.org/10.1109/TGRS.2023.3343071
    Takeaway: a recent analysis that still recommends harmonization when combining OLI with TM and ETM+.
21. **Gross, G., et al. (2022).** Initial cross-calibration of Landsat 8 and Landsat 9 using the simultaneous underfly event. *Remote Sensing*. https://doi.org/10.3390/rs14102418
    Takeaway: OLI-2 was cross-calibrated to OLI, which supports treating Landsat 8 and 9 as one sensor.
22. **Zhang, H. K., & Roy, D. P. (2016).** Landsat 5 Thematic Mapper reflectance and NDVI 27-year time series inconsistencies due to satellite orbit changes. *Remote Sensing of Environment*. https://doi.org/10.1016/j.rse.2016.08.022
    Takeaway: Landsat 5 orbit changes shifted solar zenith by more than 10 degrees and NDVI by up to 0.11 between years, with fast change in 2003-2007.
23. **Roy, D. P., et al. (2020).** A conterminous United States analysis of the impact of Landsat 5 orbit drift on the temporal consistency of Landsat 5 Thematic Mapper data. *Remote Sensing of Environment*. https://doi.org/10.1016/j.rse.2020.111701
    Takeaway: confirmed with real data across the US that red and NDVI shifts scale with solar zenith change between years.
24. **Qiu, S., et al. (2021).** Can Landsat 7 preserve its science capability with a drifting orbit? *Science of Remote Sensing*. https://doi.org/10.1016/j.srs.2021.100026
    Takeaway: Landsat 7 drift effects were small through 2020 but largest in NIR and expected to grow. The basis of our 2020 cutoff.
25. **Ju, J., & Masek, J. G. (2016).** The vegetation greenness trend in Canada and US Alaska from 1984-2012 Landsat data. *Remote Sensing of Environment*. https://doi.org/10.1016/j.rse.2016.01.001
    Takeaway: a model for a multi-decade, multi-sensor Landsat greenness trend study.
26. **Berner, L. T., et al. (2020).** Summer warming explains widespread but not uniform greening in the Arctic tundra biome. *Nature Communications*. https://doi.org/10.1038/s41467-020-18479-5
    Takeaway: cross-calibrated Landsat sensors before trend analysis and reported robustness, the template for our sensitivity section.

### 2.5 Vegetation indices

27. **Huete, A., et al. (2002).** Overview of the radiometric and biophysical performance of the MODIS vegetation indices. *Remote Sensing of Environment*. https://doi.org/10.1016/S0034-4257(02)00096-2
    Takeaway: EVI reduces soil and atmospheric effects and saturates less than NDVI.
28. **Jiang, Z., et al. (2008).** Development of a two-band enhanced vegetation index without a blue band. *Remote Sensing of Environment*. https://doi.org/10.1016/j.rse.2008.06.006
    Takeaway: EVI2 matches EVI closely using only red and NIR, recommended where the blue band is unreliable or inconsistent across sensors.
29. **Camps-Valls, G., et al. (2021).** A unified vegetation index for quantifying the terrestrial biosphere. *Science Advances*. https://doi.org/10.1126/sciadv.abc7447
    Takeaway: kNDVI saturates less and tracks productivity better than NDVI.
30. **Badgley, G., et al. (2017).** Canopy near-infrared reflectance and terrestrial photosynthesis. *Science Advances*. https://doi.org/10.1126/sciadv.1602244
    Takeaway: NIRv isolates the vegetation signal from soil and relates closely to photosynthesis.

### 2.6 Land cover

31. **Brown, J. F., et al. (2020).** Lessons learned implementing an operational continuous United States national land change monitoring capability: the LCMAP approach. *Remote Sensing of Environment*. https://doi.org/10.1016/j.rse.2019.111356
    Takeaway: the time series approach Annual NLCD builds on.
32. **Wickham, J., et al. (2023).** Thematic accuracy assessment of the NLCD 2019 land cover for the conterminous United States. *GIScience & Remote Sensing*. https://doi.org/10.1080/15481603.2023.2181143
    Takeaway: accuracy of the legacy NLCD, showing that grassland, pasture, and shrubland are the most confused classes. Annual NLCD's own validation (USGS user guide) is the primary accuracy citation.
33. **Olofsson, P., et al. (2014).** Good practices for estimating area and assessing accuracy of land change. *Remote Sensing of Environment*. https://doi.org/10.1016/j.rse.2014.02.015
    Takeaway: cited only in future work, as the standard for a sample-based accuracy and area assessment.

### 2.7 Drought and vegetation in Texas and the southern Great Plains

34. **Vicente-Serrano, S. M., et al. (2010).** A multiscalar drought index sensitive to global warming: the Standardized Precipitation Evapotranspiration Index. *Journal of Climate*. https://doi.org/10.1175/2009JCLI2909.1
    Takeaway: SPEI includes evaporative demand and works at several time scales.
35. **Vicente-Serrano, S. M., et al. (2013).** Response of vegetation to drought time-scales across global land biomes. *Proceedings of the National Academy of Sciences*. https://doi.org/10.1073/pnas.1207068110
    Takeaway: vegetation responds to drought at different time scales by biome, so we test several.
36. **Tadesse, T., et al. (2015).** Assessing the vegetation condition impacts of the 2011 drought across the U.S. Southern Great Plains using the Vegetation Drought Response Index (VegDRI). *Journal of Applied Meteorology and Climatology*. https://doi.org/10.1175/JAMC-D-14-0048.1
    Takeaway: the 2011 drought, now inside our record, hit vegetation hard and unevenly by land cover.
37. **Schwantes, A. M., et al. (2016).** Quantifying drought-induced tree mortality in the open canopy woodlands of central Texas. *Remote Sensing of Environment*. https://doi.org/10.1016/j.rse.2016.03.027
    Takeaway: 2011 drought killed many trees in central Texas, so a post-2011 rise can be recovery rather than long-term greening.
38. **Evans, J., & Geerken, R. (2004).** Discrimination between climate and human-induced dryland degradation. *Journal of Arid Environments*. https://doi.org/10.1016/S0140-1963(03)00121-6
    Takeaway: RESTREND, the trend in residuals after regressing vegetation on climate.
39. **Wessels, K. J., et al. (2012).** Limits to detectability of land degradation by trend analysis of vegetation index data. *Remote Sensing of Environment*. https://doi.org/10.1016/j.rse.2012.06.022
    Takeaway: rainfall-driven series can hide or fake trends, the reason RQ3 exists.
40. **Burrell, A. L., et al. (2017).** Detecting dryland degradation using time series segmentation and residual trend analysis (TSS-RESTREND). *Remote Sensing of Environment*. https://doi.org/10.1016/j.rse.2017.05.018
    Takeaway: RESTREND fails when the vegetation-climate relationship breaks, so breaks are checked first.

### Platform and software

41. **Gorelick, N., et al. (2017).** Google Earth Engine: planetary-scale geospatial analysis for everyone. *Remote Sensing of Environment*. https://doi.org/10.1016/j.rse.2017.06.031
42. **Wu, Q. (2020).** geemap: a Python package for interactive mapping with Google Earth Engine. *Journal of Open Source Software*. https://doi.org/10.21105/joss.02305
43. **Hussain, M. M., & Mahmud, I. (2019).** pyMannKendall: a python package for non parametric Mann Kendall family of trend tests. *Journal of Open Source Software*. https://doi.org/10.21105/joss.01556 (reference implementation for unit tests)
44. **Hoyer, S., & Hamman, J. (2017).** xarray: N-D labeled arrays and datasets in Python. *Journal of Open Research Software*. https://doi.org/10.5334/jors.148
45. **Rocklin, M. (2015).** Dask: parallel computation with blocked algorithms and task scheduling. *Proceedings of the 14th Python in Science Conference*. https://doi.org/10.25080/Majora-7b98e3ed-013
46. **Abatzoglou, J. T. (2013).** Development of gridded surface meteorological data for ecological applications and modelling. *International Journal of Climatology*. https://doi.org/10.1002/joc.3413 (gridMET, source of SPEI)

The 40 numbered science papers include 37 core papers plus 3 kept only for framing or future work (Verbesselt 2010, Brown 2020, Olofsson 2014). Items 41-46 are software and data citations.

### 2.8 References removed and why

| Removed | Reason |
|---|---|
| Claverie et al. 2018, Ju et al. 2025 (HLS) | HLS no longer used |
| Qiu et al. 2019 (Fmask 4.0) | That version is HLS's mask. Collection 2 uses CFMask, cited via Zhu and Woodcock 2012 and Foga et al. 2017. |
| Wang et al. 2012, Lyapustin et al. 2014 | MODIS-specific sensor degradation, MODIS no longer used |
| Nagol et al. 2014 | AVHRR orbit drift. Replaced by Landsat-specific drift papers (Zhang and Roy 2016, Roy et al. 2020, Qiu et al. 2021). |
| Stehman 2014, Stehman and Foody 2019 | Area estimation and accuracy assessment removed from the study |
| Kennedy et al. 2010 (LandTrendr), Zhu and Woodcock 2014 (CCDC) | Not used. Annual NLCD lineage is covered by Brown et al. 2020. |
| MODIS MOD13Q1, VIIRS VNP13A1, MCD12Q1, HLS dataset DOIs | Data no longer used |

### 2.9 What the literature implies for a 27-year Landsat record

- 27 annual values give far more power than 12, but the record now spans four sensors, two atmospheric correction codes, and two drifting orbits (Landsat 5 and late Landsat 7). Harmonization and drift handling are now the main threats to validity, not sample size (refs 19-24).
- Long records are rarely monotonic. The 2011 drought and the recovery after it sit in the middle of our series (refs 10, 36, 37).
- In drylands, climate sequence can drive trends, so RQ3 separates the drought-associated part (refs 38-40).

---

## 3. Cross-sensor harmonization: choice and justification

**The problem.** TM, ETM+, and OLI have different spectral bands, and Collection 2 corrects TM and ETM+ with LEDAPS but OLI with LaSRC. A small, systematic offset at the 2013 switch to OLI would show up as a false trend over 27 years.

**Options considered.**

| Option | For | Against |
|---|---|---|
| No harmonization | Simplest. Some Collection 2 guidance suggests it is often unnecessary. | No published Collection 2 analysis supports skipping it. Trevisiol et al. (2024) recommend harmonizing. The risk is a false trend, which is worse than a small extra step. |
| Roy et al. (2016) coefficients | Most cited, CONUS-wide, peer reviewed | Fitted before Collection 2. Earth Engine's own tutorial flags this procedure as outdated for Collection 2. Does not address Landsat 5 orbit drift. |
| **Coefficients fitted on our own Collection 2 data (recommended)** | Matches the exact product and region. Also absorbs Landsat 5 drift if fitted year by year. Shows the skill directly. | More work. Needs a clean overlap design. |

**Recommended procedure.**
1. **Bands.** Only red and NIR need harmonizing, because all three indices (EVI2, NIRv, kNDVI) use only those two bands. This is a real advantage of dropping the blue band.
2. **ETM+ to OLI.** Fit using the 2013-2017 seasons, when both satellites flew and Landsat 7 was still in its maintained orbit (last maneuver August 2017). For a stratified random sample of about 30,000 stable Annual NLCD pixels, compute separate Landsat 7 and Landsat 8 March-October median red and NIR. Fit reduced major axis regression per band. RMA is used because both sensors have measurement error, and OLS would bias the slope toward zero (Roy et al. 2016 report both).
3. **TM to ETM+, year by year.** For each year 2000-2011, fit the same way using Landsat 5 and Landsat 7 medians from that year. Landsat 7 held its orbit during those years, so year-specific coefficients absorb the Landsat 5 drift that Zhang and Roy (2016) and Roy et al. (2020) documented, including its fast 2003-2007 change.
4. **Chain.** TM goes to ETM+ (by year) and then to OLI. Landsat 9 is treated as OLI (Gross et al. 2022).
5. **Apply per observation.** A median of one band commutes with an increasing linear transform, so coefficients fitted on season medians apply directly to each observation before indices are computed.
6. **Report.** The coefficients, their confidence intervals, how far they differ from Roy et al. (2016), and the EVI2 offset each one removes. If our coefficients are close to Roy's, that is useful confirmation. If not, that is itself a finding about Collection 2.
7. **Comparison run.** The full EVI2 trend is repeated with Roy et al. (2016) coefficients and the difference in slopes is reported.

**Why season medians and not same-day pairs.** Landsat 5 and 7, and Landsat 7 and 8, image the same path 8 days apart, so true same-day pairs exist only in narrow sidelap zones. Matching season medians fits our use exactly, because our composites are season medians. Different acquisition dates add noise to the fit but no systematic bias, given thousands of sample pixels.

---

## 4. Primary index: EVI2

| Index | Bands | Verdict for a 27-year multi-sensor record |
|---|---|---|
| EVI | blue, red, NIR | **Drop as primary.** The blue band differs most between LEDAPS and LaSRC, is most sensitive to aerosol errors, and would need a third harmonized band. |
| **EVI2** | red, NIR | **Primary.** Keeps EVI's soil adjustment and lower saturation (Jiang et al. 2008 show close agreement with EVI). Only two bands to harmonize. Suits a province that runs from open grassland to closed oak woodland. |
| NDVI | red, NIR | Not primary. Saturates over dense woody cover in the Oak Woods and Prairies section and responds strongly to soil background in sparse grassland. Its ratio form is somewhat less sensitive to orbit-driven NIR changes, which is a point in its favor. It is the index most of the drift literature reports, so it is a fallback if harmonization of EVI2 proves unstable. |
| NIRv, kNDVI | red, NIR | Sensitivity check (c). Both need only red and NIR, so they share EVI2's harmonization. |

This keeps the spirit of the 2016 project, which used EVI, while removing the band that causes most trouble across sensors.

---

## 5. Methods

### 5.1 Preprocessing and QA (Earth Engine)
- Collections: Landsat 5, 7, 8, 9 Collection 2 Tier 1 Level-2 (Tier 1 only, the best geometric quality tier).
- Scale reflectance with the Collection 2 factors from the USGS product guide.
- Mask with QA_PIXEL: fill, dilated cloud, cloud, cloud shadow, snow, water, and cirrus for OLI. Mask saturated red or NIR pixels using QA_RADSAT. Screen hazy observations with the atmospheric opacity band (TM, ETM+) and aerosol QA band (OLI), using thresholds from the USGS product guides. Drop reflectance outside 0-1. QA bit decoding is a tested pure function.
- Landsat 7 observations from January 1, 2020 onward are excluded.
- Harmonize red and NIR (Section 3), then compute EVI2, NIRv, kNDVI per observation.
- Composite: per-pixel median of each index over clear observations, March 1 to October 31.
- Per pixel per year, also export the clear observation count in each of three sub-seasons (March-May, June-August, September-October) and the count of all acquisitions, so loss to masking and each validity rule can be reported.

**Validity rules (all in the config, applied locally so every rule's effect can be counted):**

| Rule | Level | Requirement | Why |
|---|---|---|---|
| Clear count | pixel-year | at least 4 clear observations, March-October | A median of very few dates is noisy |
| Seasonal coverage | pixel-year | clear observations in at least 2 of the 3 sub-seasons | If all clear dates fall in one part of the season, the median reflects that part, not the season. This matters most in low-density years such as 2012. |
| Valid years | pixel | at least 20 valid years of 27 | Enough points for a stable trend test |
| Endpoint coverage | pixel | at least 3 valid years in each of the first 5 years and the last 5 years of the record | Ensures the slope spans the study period instead of being fitted to the middle of it |

The rules are applied in that order. The data quality report gives the number and percent of pixel-years or pixels removed by each rule, by year (for the pixel-year rules) and by land cover class.
- Grid: Annual NLCD grid, CONUS Albers Equal Area (EPSG:5070), 30 m, pixel-aligned.

**SLC-off gaps (2003-2019).** The missing stripes move from one date to the next, so a season median from many dates fills most of them. In 2003-2011 Landsat 5 also fills them, and in 2013-2019 Landsat 8 does. No gap-filling interpolation is used, because interpolated values would put invented data into a trend test. Pixels that still fall below the clear-count minimum are treated as missing years.

**2012.** Only Landsat 7 SLC-off was imaging. 2012 will have the lowest clear counts in the record, and the stripe pattern may show in its composite. It is kept as a year with more missing pixels, not dropped wholesale. Theil-Sen and Mann-Kendall both handle missing years.

### 5.2 Data quality report (Phase 3 deliverable)
- Per year: province total acquisitions, clear observations, percent lost to masking, median clear count per pixel, and percent of pixels below the minimum.
- Per pixel maps of clear counts for each year.
- Flagged years with expected low density: 2012 (Landsat 7 SLC-off only), 2013 (Landsat 8 starts mid April), 2020-2021 (Landsat 8 only after the Landsat 7 cutoff), and any year the counts reveal.

### 5.3 RQ1: where and how much greenness changed
- Theil-Sen slope with confidence interval, Mann-Kendall with Hamed-Rao correction, Benjamini-Hochberg FDR at q = 0.10 (Wilks 2016) with q = 0.05 as a sensitivity.
- Effect sizes: slope per decade in EVI2 units, and total change 2000-2026 as percent of the 2000-2004 mean.
- Power: minimum detectable trend per pixel from Weatherhead et al. (1998). A non-significant pixel is reported as "no detectable trend".
- Endpoint check: leave-one-year-out Theil-Sen slopes. A trend whose sign flips when one year is removed is flagged.

### 5.4 RQ2: trends by land cover class
- Stable pixels: same Annual NLCD class in every year 2000-2025, and Annual NLCD confidence above a config threshold. Over 26 years, especially around Dallas-Fort Worth, Austin, and Houston, the stable share will be lower than in revision 1. Its size is reported.
- Classes aggregated to about 8 (water, developed, barren, forest, shrubland, grassland, pasture and hay, cultivated crops, wetlands, with water and developed excluded from interpretation).
- Per class: share greening, browning, and no detectable trend, and median slope with a bootstrap interval.
- Accuracy context: Annual NLCD's own validation from the USGS user guide, plus Wickham et al. (2023) for known class confusions. No new accuracy assessment in this study.

### 5.5 RQ3: how much trend remains after accounting for drought
- Framed as association, not cause.
- SPEI from gridMET at 1, 3, 6, 9, and 12 month scales, for several end months. The best-correlated scale is picked per class (Vicente-Serrano et al. 2013).
- Break check before RESTREND (Burrell et al. 2017): test class-level series for a break in the EVI2 to SPEI relationship. Classes with a break are reported separately, not forced through RESTREND.
- RESTREND (Evans and Geerken 2004): regress annual EVI2 on the chosen SPEI, then run the same Theil-Sen, Hamed-Rao, and FDR procedure on the residuals.
- Report: share of RQ1 significant pixels that stay significant, and residual slope as a share of the original slope, by class.
- gridMET is about 4 km, so RQ3 is interpreted at class level, not per 30 m pixel.

### 5.6 Sensitivity analysis (not a research question)

**(a) Single-sensor subsets.** Same trend procedure, same windows, compared with the main series:
- ETM+ only, 2000-2019, against the main series over 2000-2019. Tests Landsat 5 drift handling and TM harmonization.
- OLI only, 2013-2026, against the main series over 2013-2026. Because Landsat 7 is the only difference between the two series in those years, this directly tests the effect of including Landsat 7 in 2013-2019.
- Metrics: sign agreement among significant pixels, Spearman correlation of slopes, median slope difference, by class.
- Plus the harmonization comparison run with Roy et al. (2016) coefficients (Section 3, step 7).

**(b) Observation density.** Spearman correlation between each pixel's EVI2 slope and the Theil-Sen slope of its clear-observation count, overall and by class. A strong correlation would mean the trend tracks changing data density rather than vegetation.

**(c) Index agreement.** Repeat RQ1 with NIRv and kNDVI. Report sign agreement among significant pixels and correlation of standardized slopes (slope divided by each pixel's interannual standard deviation, since the indices have different units).

A pixel is called a **robust trend** when it is FDR-significant in EVI2, keeps its sign in the applicable subset from (a), and agrees in sign with NIRv and kNDVI.

### 5.7 Non-monotonic trends: how the paper handles them
A 27-year record that contains the 2011 drought, the recovery after it, and the 2022 drought is unlikely to be monotonic everywhere. Theil-Sen and Mann-Kendall estimate the net monotonic tendency, and a pixel that browned then greened can show no trend at all (de Jong et al. 2012). The paper handles this in four ways without a new research question:
1. **Stated limitation.** Results are described as net change over 2000-2026, not as a steady rate.
2. **Descriptive trajectories.** A figure of annual median EVI2 by class, with drought years marked, so readers see the shape behind each slope.
3. **RQ3 absorbs part of it.** Regressing on SPEI removes much of the drought dip and recovery, so residual trends are closer to monotonic.
4. **Break check.** The RQ3 break test reports which classes have a structural break. Full break detection (for example BFAST, Verbesselt et al. 2010) is listed as future work.

### 5.8 Maps
- CONUS Albers Equal Area (EPSG:5070) for all maps and area statistics.
- Colorblind-safe diverging palette for slopes, checked with a colorblind simulator.
- Scale bar, data credits for USGS Landsat, USGS Annual NLCD, and gridMET on every map.

---

## 6. Research questions (final)

**RQ1.** Where did growing-season greenness change across Province 255 from 2000 to 2026, and by how much?

**RQ2.** How do trends differ among land cover classes, using stable Annual NLCD pixels only?

**RQ3.** How much of the trend remains after accounting for drought, using SPEI association and RESTREND, framed as association, not cause?

---

## 7. Data sources

| Role | Product | Version | Resolution | Years used | DOI |
|---|---|---|---|---|---|
| Reflectance | Landsat 4-5 TM Collection 2 Level-2 | C2 Tier 1 | 30 m | 2000-2011 | https://doi.org/10.5066/P9IAXOVV |
| Reflectance | Landsat 7 ETM+ Collection 2 Level-2 | C2 Tier 1 | 30 m | 2000-2019 | https://doi.org/10.5066/P9C7I13B |
| Reflectance | Landsat 8-9 OLI/TIRS Collection 2 Level-2 | C2 Tier 1 | 30 m | 2013-2026 (Landsat 9 from 2022) | https://doi.org/10.5066/P9OGBGM6 |
| Land cover and confidence | USGS Annual NLCD | Collection 1 (1.1 or 1.2, confirmed in Phase 3) | 30 m | 2000-2025 | https://doi.org/10.5066/P94UXNTS |
| Land cover accuracy reference | Annual NLCD reference data | Collection 1.0 | plots | cited only | https://doi.org/10.5066/P13EDMAF |
| Drought | gridMET drought indices (SPEI) | current | about 4 km | 2000-2026 | Abatzoglou 2013, https://doi.org/10.1002/joc.3413 |
| Study area | USDA Forest Service Bailey's ecoregion provinces (ECOMAP) | current | vector | n/a | Citation confirmed in Phase 3 |

All dataset DOIs resolve at doi.org as of 2026-11-25. Access dates go in the README when data is pulled.

**2026 decision rule.** In Phase 3 I check whether Landsat 8 and 9 Tier 1 Level-2 scenes through October 31, 2026 are in the archive for all path-rows. If yes, 2026 is included. If not, the study period is 2000-2025.

---

## 8. Compute estimate (for your approval before Phase 3)

Your machine: AMD Ryzen 7 7730U (8 cores, 16 threads), 15.4 GB RAM, 790 GB free on C:.

Province 255 is about 207,500 km2, which is **about 231 million valid 30 m pixels**. Pixels outside the boundary are stored as nodata and compress to almost nothing.

### 8.1 Earth Engine exports

| Export | Content | Raw size | On disk (compressed) |
|---|---|---|---|
Revised for revision 3: each pixel-year now carries three sub-season clear counts instead of one clear count.

| Export | Content | Raw size | On disk (compressed) |
|---|---|---|---|
| Main annual stack, 2000-2026 | EVI2, NIRv, kNDVI (int16) plus 3 sub-season clear counts and total count (uint8), 10 bytes per pixel per year | 62.3 GB | about 30-40 GB |
| ETM+ only subset, 2000-2019 | EVI2 plus 3 sub-season clear counts, 5 bytes per pixel per year | 23.1 GB | about 10-14 GB |
| OLI only subset, 2013-2019 | Same bands (2020-2026 is already OLI only in the main stack) | 8.1 GB | about 4-5 GB |
| Stable pixel mask and class | 2 bands, uint8 | 0.5 GB | under 0.3 GB |
| Harmonization sample | about 30,000 points by sensor by year, red and NIR | under 0.1 GB | under 0.1 GB |
| SPEI | monthly, 4 km | under 0.5 GB | under 0.5 GB |
| **Total** | | **about 95 GB** | **about 45-60 GB** |

Small integer count bands compress well, so the compressed figure is likely at the low end. The pilot export will give the real ratio.

**Earth Engine compute quota.** Since April 27, 2026, noncommercial projects have a monthly compute quota in EECU-hours, and batch exports count against it. The Community tier gives 150 EECU-hours per month with no billing account. The Contributor tier gives 1,000 EECU-hours per month. It requires an active billing account for identity verification, but Earth Engine noncommercial use is not charged. Going over the quota does not stop tasks, but the project drops into a restricted mode with lower throughput until the quota resets on the first of the month (Earth Engine noncommercial tiers page). I can't predict our EECU use before the pilot. The pilot reports the EECU-hours one year actually used, and I will project the total from that. If the projection fits under 150 per month across a few months, Community is fine. If not, Contributor is the practical choice.

Earth Engine run time: about 55 export tasks. Export speed varies with Earth Engine load, so I can't promise a number. My working estimate is 1-4 hours per annual task, run a few at a time, for **1-4 days of wall clock time**. It runs unattended. I will run a one-year pilot export first and give you a measured number before launching the rest.

Download: 35-45 GB takes about 2 hours at 50 Mbps, or about 5 hours at 20 Mbps.

**Storage: batched Google Drive exports (approved).** Procedure in Section 8.5.

### 8.2 Local disk

| Item | Size |
|---|---|
| Exported inputs | 45-60 GB |
| Trend outputs, EVI2 full suite (slope, CI, tau, p, Hamed-Rao p, q, autocorrelation, valid years, detectable trend, jackknife min and max), float32 | about 13 GB raw, 8 GB compressed |
| Trend outputs for NIRv, kNDVI, two subsets, Roy comparison (slope, p, q) | about 14 GB raw, 9 GB compressed |
| RESTREND outputs | about 5 GB |
| Scratch space for dask | 10-20 GB |
| **Peak need** | **about 85-110 GB**, so plan for 120 GB. You have 790 GB free. |

All of it lives under `C:\rsdata` (Section 8.6), never in the repo.

### 8.3 Memory and chunking
- Data read lazily from Cloud Optimized GeoTIFFs with rioxarray, in dask chunks of 512 by 512 pixels by all years.
- One chunk of one index is 512 x 512 x 27 x 4 bytes = 28 MB. Theil-Sen needs all 351 pairwise slopes per pixel: 351 x 262,144 x 4 bytes = 368 MB. With temporaries, about 1-1.5 GB per worker.
- **4 dask workers, about 6 GB peak**, leaves headroom on 15.4 GB for Windows and other apps. Chunks entirely outside the province are skipped.

### 8.4 Local run time (estimates, to be benchmarked)
These are estimates from operation counts, not measurements. The environment does not exist yet, so I could not benchmark. In Phase 3, before any full run, I will time one chunk and update these numbers.

| Step | Estimate with 4 workers |
|---|---|
| Core trend suite (Theil-Sen, Mann-Kendall, Hamed-Rao, FDR) per index over the full province | 0.5-1.5 hours |
| Leave-one-year-out endpoint check, EVI2 only (27 refits) | 3-6 hours |
| NIRv, kNDVI, two subsets, Roy comparison | 2-5 hours total |
| RESTREND and drought correlations | 1-2 hours |
| **Total local compute** | **about 7-15 hours**, split across overnight runs |

The trend math is written as vectorized NumPy and unit tested against pyMannKendall on small arrays. Looping pyMannKendall over 231 million pixels would take days.

### 8.5 Batch export procedure (Google Drive, about 5 years per batch)

Each batch is at most about 10 GB compressed, under the 15 GB free Drive limit with room to spare.

| Batch | Content |
|---|---|
| P | Pilot: main stack for one year (2012, the hardest year), measured for time, size, and EECU-hours |
| B1-B5 | Main stack 2000-2004, 2005-2009, 2010-2014, 2015-2019, 2020-2024 |
| B6 | Main stack 2025-2026, stable pixel mask, SPEI, harmonization sample |
| B7-B8 | ETM+ only subset 2000-2009, 2010-2019 |
| B9 | OLI only subset 2013-2019 |

Steps for every batch:

1. **Export.** `conda run -n rs-trends python src/03_export.py --batch B1` submits that batch's tasks to a Drive folder named after the batch (for example `rs_trends_B1`). The script refuses to start a batch while an earlier batch is still in Drive and not yet verified.
2. **Wait.** `conda run -n rs-trends python src/03_export.py --status` shows task states and EECU use. Or watch the Tasks list in the Earth Engine Code Editor.
3. **Download.** In Google Drive in your browser, right-click the batch folder and choose Download. Drive zips it, in several parts for large folders. Save the zips to `C:\rsdata\incoming\B1`. Do not use the Google Drive desktop sync app for this, because that would put the data in a synced folder.
4. **Verify.** `conda run -n rs-trends python src/03_verify_batch.py --batch B1` unzips, checks that every expected file is present, opens each one, and checks CRS (EPSG:5070), 30 m pixels, alignment to the NLCD grid, band names, data types, and nodata. It writes a SHA-256 checksum for every file to `C:\rsdata\manifest.csv` with the batch, file name, size, and date. It then moves the files to `C:\rsdata\raw\` and prints PASS or FAIL.
5. **Delete, only after PASS.** Delete the batch folder in Drive, then empty the Drive trash. Trashed files still count against the 15 GB quota until the trash is emptied.
6. **Next batch.** The verify step records the batch as done, which unlocks the next export.

If verify FAILS, the script lists what is wrong, keeps the files in `incoming`, and you do not delete anything from Drive. We fix it and re-export only the failed pieces.

### 8.6 Data location and resumable jobs

- **Location.** All data lives under `C:\rsdata`, which is outside the repo and outside OneDrive and Dropbox. Scripts read the path from the `RS_DATA_DIR` environment variable, falling back to the config value. Subfolders: `incoming`, `raw`, `interim`, `outputs`, `logs`. `.gitignore` excludes data file types and any local data folders as a second safeguard.
- **Resumable jobs.** Every long local job splits the grid into fixed chunks. Each chunk's results are written to the output store as soon as they are computed, and a small "done" marker for that chunk is written only after the results are safely on disk. On restart, the job skips every chunk with a marker. A crash loses at most the chunks in progress. Markers are written atomically (to a temporary file, then renamed) so a crash mid-write cannot leave a false "done".
- **Gates.** The pilot export (batch P) and a one-chunk benchmark run first. I report the measured export time, file size, compression ratio, EECU-hours, and per-chunk run time, with updated totals, and wait for your go-ahead before launching anything else.

---

## 9. Platform (unchanged)

Hybrid: Earth Engine with geemap for QA masking, harmonization, and compositing. Local open-source statistics in xarray, dask, NumPy, and SciPy. The reasons are unchanged and stronger now. Raw Landsat for 27 years over about 30 path-rows is tens of thousands of scenes, which only makes sense to process in the cloud. The custom statistics (Hamed-Rao, Benjamini-Hochberg, power, RESTREND) are not built into Earth Engine and belong in tested open code.

---

## 10. ASPRS standards

The ASPRS Positional Accuracy Standards for Digital Geospatial Data, current version Edition 2, Version 2 (adopted June 24, 2024, earlier edition in PE&RS 2015, https://doi.org/10.14358/PERS.81.3.A1-A26), define how to test and report the absolute positional accuracy of data such as orthoimagery, planimetric data, and elevation data using checkpoints.

**Relevance: limited.** This study does not produce a mapping product whose positional accuracy is the deliverable. It uses Landsat Collection 2 Tier 1 scenes, which USGS assigns to Tier 1 based on its own geometric criteria, documented in the Collection 2 product guides. The methods will cite those USGS criteria, not ASPRS, and make no ASPRS compliance claim. The standard does not cover thematic accuracy or trend statistics. For those we cite the method literature above.

---

## 11. Target journal (unchanged)

Photogrammetric Engineering & Remote Sensing (PE&RS). Alternative: Remote Sensing (MDPI). A 27-year record with an explicit treatment of Landsat 5 and 7 orbit drift and Collection 2 harmonization strengthens the methods contribution compared with revision 1.

---

## 12. Timeline (part-time)

| Phase | Work | Estimate |
|---|---|---|
| 2 Setup | conda env, repo skeleton, config, CI with secret scanning, Earth Engine sign-in by you | 1-2 sessions |
| 3 Data | boundary, harmonization sample and fit, QA and composites, pilot export, full exports (1-4 days unattended), data quality report, one-chunk benchmark | about 1-2 weeks |
| 4 Analysis | trends, FDR, power, endpoint check, class summaries, drought and RESTREND, sensitivity checks | about 1-2 weeks |
| 5 Outputs | figures, tables, README, manuscript outline with draft methods and results | about 1 week |

## 13. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Harmonization leaves an offset at the 2013 OLI switch | Fitted coefficients on Collection 2, Roy comparison run, OLI-only subset check |
| Landsat 5 drift in 2003-2007 | Year-specific TM to ETM+ fit, ETM+-only subset check |
| Low density in 2012 and 2020-2021 | Clear-count thresholds, missing years allowed, check (b) |
| SLC-off stripes visible in composites | Multi-date medians, Landsat 5 and 8 overlap, count maps reviewed in the quality report |
| Non-monotonic trajectories | Limitation, trajectories figure, RQ3 break check |
| Smaller stable-pixel share over 26 years | Share reported per class. Classes with too few stable pixels are flagged. |
| Drive quota smaller than exports | Batched exports or a Cloud Storage bucket (your choice) |
| 2026 season incomplete | Decision rule in Section 7 |
| Earth Engine export failures | Export by year with resume logic and a pilot first |

---

## 14. Future work (stated in the paper)
- Sample-based accuracy assessment and area estimation of land cover change (Olofsson et al. 2014), with reference labels from NAIP.
- Full break detection (for example BFAST) to describe non-monotonic trajectories.

---

## 15. Decisions

All decisions from revision 2 were resolved in revision 3 (Section 0.1). The one open item is the Earth Engine quota tier, which is decided after the pilot measures EECU use (Section 8.1).

---

## Web sources used for data facts

- USGS, Landsat 7 maneuvers: https://www.usgs.gov/landsat-missions/landsat-7-maneuvers
- USGS, Landsat 7 extended science mission: https://usgs.gov/landsat-missions/landsat-7-extended-science-mission
- USGS, End of an era, Landsat 7 decommissioned: https://www.usgs.gov/news/national-news-release/end-era-landsat-7-decommissioned-after-25-years-earth-observation
- USGS, Can Landsat 7 preserve its science capability: https://www.usgs.gov/publications/can-landsat-7-preserve-its-science-capability-a-drifting-orbit
- USGS, Landsat Collection 2 surface reflectance: https://www.usgs.gov/landsat-missions/landsat-collection-2-surface-reflectance
- Earth Engine community tutorial, ETM+ to OLI harmonization: https://github.com/google/earthengine-community/blob/master/tutorials/landsat-etm-to-oli-harmonization/index.md
- NASA HLS data page (sensor start dates): https://hls.gsfc.nasa.gov/hls-data
- USGS, Annual NLCD validation and reference data: https://www.usgs.gov/centers/eros/news/new-reference-and-validation-data-available-annual-nlcd
- USGS, Annual NLCD overall agreement: https://www.usgs.gov/media/images/overall-agreement-collection-10-annual-nlcd
- USDA Forest Service, Ecoregions chapter 29: https://www.fs.usda.gov/land/pubs/ecoregions/ch29.html
- ASPRS Edition 2 Version 2 announcement: https://asprs.org/2024/06
