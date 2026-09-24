# Data licence and attribution

This repository contains a small, normalized KGMT-only air-quality snapshot derived from the public AirData.kz Almaty hourly files.

AirData.kz states that its open dataset is licensed under **CC BY-NC 4.0** for non-commercial use, sharing and adaptation with attribution. AirData.kz also states that upstream source terms continue to apply. The repository README should therefore credit AirData.kz and link to the upstream dataset.

Upstream dataset:
- AirData.kz / `qazybekb/AirDatakz-OpenData`
- https://github.com/qazybekb/AirDatakz-OpenData

Recommended attribution:
> AirData.kz. Open Air Quality Dataset for Kazakhstan. Global Shapers Almaty Hub, 2019–present. https://airdata.kz

Important: this data licence does **not** automatically determine the licence for the analysis code in this repository. A software licence should be chosen separately by the authors before public release.

The locked normalized snapshot in `data/derived/baseline/almaty_hourly_long.csv.gz` has SHA-256:

`1188fc9d87ac3f0a3a947c81ec5083646f4703620e0e3db7ed48c3d90f57b8f8`

The exact AirData.kz Git commit used to create the supplied snapshot cannot be recovered from the CSV bytes alone because the accompanying builder QC JSON containing `resolved_main_commit_sha` was not supplied. The snapshot itself is therefore hash-locked, while its original upstream commit remains **not verified**.
