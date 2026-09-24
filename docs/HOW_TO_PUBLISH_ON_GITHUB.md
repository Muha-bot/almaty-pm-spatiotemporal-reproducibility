# How to publish this package on GitHub

## Simplest route: GitHub Desktop

1. Unzip the package on your computer.
2. Install **GitHub Desktop** and sign in to your GitHub account.
3. In GitHub Desktop, choose **File → Add Local Repository**.
4. Point it at the unzipped `almaty-pm-scopus` folder.
5. If prompted to create a Git repository here, accept.
6. Click **Publish repository**.
7. Suggested repository name: `almaty-pm25-pm10-spatiotemporal`.
8. Publish it as **Private** first.
9. After the manuscript text and author list are finalized and confirmed
   consistent with this repository, switch it to Public if that matches
   the target journal's policy.

## Command line route

First create an **empty** repository on GitHub. Do not let GitHub add its
own README, license, or `.gitignore` — this package already has all three.

From inside the unzipped folder:

```bash
git init
git add .
git commit -m "Initial reproducibility package for Almaty PM2.5/PM10 study"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/almaty-pm25-pm10-spatiotemporal.git
git push -u origin main
```

Replace `YOUR_USERNAME` with your GitHub account name.

## What should be visible at the repository root

- `README.md`
- `LICENSE.md`
- `CITATION.cff`
- `MANIFEST_SHA256.txt`
- `requirements.txt`, `requirements-minimal.txt`
- `data/`, `src/`, `configs/`, `tests/`, `results/`, `figures/`, `docs/`

## What NOT to upload

Do not manually add any of the following, even though `.gitignore` already
excludes most of them by default:

- the unpublished manuscript (`.docx`/`.doc`);
- `.cdsapirc`, API tokens, or passwords;
- raw ERA5 `.nc`/`.nc4`/`.grib`/`.grib2` files;
- raw Copernicus DEM / ESA WorldCover `.tif` tiles;
- the Kazakhstan OpenStreetMap `.pbf` extract;
- model binaries (`.pkl`, `.joblib`);
- stray intermediate files from a local working directory;
- any figure whose numbers were illustrative or placeholder rather than
  computed from the committed data.

## Checklist before making the repository Public

1. Confirm the manuscript text matches the experimental status described
   in this repository (see `docs/REPRODUCIBILITY_STATUS.md`).
2. Add the final author list to `README.md` and `CITATION.cff`.
3. Read `docs/DATA_LICENSE.md`: the AirData.kz data has its own CC BY-NC 4.0
   terms and must not be presented under the code's licence.
4. Confirm the licence in `LICENSE.md` (see its "Before making the
   repository public" checklist) and run the placeholder check:

   ```bash
   python scripts/check_no_placeholders.py
   ```

   It must print "No unresolved placeholders found." before the
   repository is made Public — see `docs/KNOWN_LIMITATIONS.md` §5.
5. Run:

   ```bash
   make verify
   make figures
   make test
   ```

6. Confirm all three commands complete without errors.
7. Cross-check `docs/REPRODUCIBILITY_STATUS.md` against the final
   manuscript — the two should not describe different ERA5/GIS/GWR status
   or a different AirGradient cohort size.
8. Create a GitHub Release, e.g. `v1.0.0`.
9. If the journal requires a persistent DOI for the code, archive that
   exact Release in a DOI-issuing repository (e.g. Zenodo).
