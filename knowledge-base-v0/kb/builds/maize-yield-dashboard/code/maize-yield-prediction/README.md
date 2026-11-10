# 🌽 NeuroCrop — Maize Yield Prediction Platform

> **Generative breeding platform** that predicts maize hybrid grain yield for any parent cross × location combination using **XGBoost**, **genomic SNPs (VCF)**, and **multi-environment weather + soil features**. Models **G×E (Genotype × Environment) interactions** across 5 years and 38 US field locations to guide breeders in selecting optimal parent combinations before committing to expensive field trials.

**Competitive moat:** Standard genomic tools used by Pioneer and Bayer (GBLUP/BLUP) use pedigree + genomics but ignore real environment data. NeuroCrop ingests actual field-level climate and soil per location — that is the core technical differentiation.

---

👤 **Author:** Abdul Manan — Plant Breeder | ML/DL Researcher | Generative Breeding  
📧 [[email removed]](mailto:[email removed]) &nbsp;|&nbsp; 🔗 [LinkedIn](https://www.linkedin.com/in/abdul-manan-0aa546332/) &nbsp;|&nbsp; 💻 [GitHub](https://github.com/manan348)  
🌐 **Live App:** [maize-yield-prediction-ryntvaanvvfya8wkdtkkba.streamlit.app](https://maize-yield-prediction-ryntvaanvvfya8wkdtkkba.streamlit.app/)  
🗓️ **Last Updated:** April 2026

---

## 📋 Table of Contents

- [🎯 Overview](#-overview)
- [📂 Dataset](#-dataset)
- [📊 Model Performance](#-model-performance)
- [🔍 Feature Importance](#-feature-importance)
- [🧠 Pipeline Overview](#-pipeline-overview)
- [🌽 Example Predictions](#-example-predictions)
- [📊 Visualizations](#-visualizations)
- [⚙️ Requirements](#️-requirements)
- [🚀 Installation](#-installation)
- [🖥️ Running the App](#️-running-the-app)
- [📦 Artifacts](#-artifacts)
- [📁 Project Structure](#-project-structure)
- [📄 License](#-license)

---

## 🎯 Overview

NeuroCrop builds a **multi-year genomic prediction system** for maize grain yield using SNP markers, plant traits, weather, and soil features across the G2F (Genomes to Fields) public dataset.

**What it does:**

- Predicts yield (bu/A) for any `(female × male, location)` combination from **2,994,894 pre-computed predictions**
- Ranks hybrids by **G×E stability** (CV% across locations) — wide-adapted vs. location-specific
- Identifies **best location** for a given cross and **best cross** for a given location
- Classifies predictions into **High / Medium / Low** yield categories with percentile rank
- Exports PDF reports and batch predictions (CSV / Excel)

**Key numbers from the latest full run:**

| Metric | Value |
|--------|-------|
| Training samples | **46,686** hybrid × location observations |
| Years | **5** (G2F 2014–2018) |
| Locations | **38** US field locations |
| Unique hybrids | **2,912** |
| Predictions generated | **2,994,894** cross × location combinations |
| Model | **XGBoost** (400 trees, lr=0.03) |
| CV R² (honest, normalized) | **0.355** |
| Test R² (normalized) | **0.361** |

---

## 📂 Dataset

All data is from the public **G2F — Genomes to Fields** initiative.

| Source | Details |
|--------|---------|
| **DOI** | [10.25739/ragt-7213](https://datacommons.cyverse.org/browse/iplant/home/shared/commons_repo/curated/GenomesToFields_2014_2017_v1) |
| **License** | Public research dataset |

**Files used:**

| File | Description | Size |
|------|-------------|------|
| `inbreds_G2F_2014-2023_437k.vcf` | Combined genotype VCF — 2,193 inbreds, 437,214 SNPs | 217 MB |
| `g2f_20XX_hybrid_data_clean.csv` | Phenotype data per year (2014–2018) | ~2–5 MB each |
| `g2f_20XX_weather_data.csv` | Daily weather per location (2014–2018) | 28–251 MB each |
| `g2f_20XX_soil_data_clean.csv` | Soil properties per location (2015–2018) | <1 MB each |

**Years used:** 2014, 2015, 2016, 2017, 2018 — the only years with both phenotype AND genotype data. 2019–2023 have phenotype but no SNP data and are excluded.

---

## 📊 Model Performance

### Evolution across versions

Each version builds incrementally, demonstrating the value of each added data source:

| Version | Key Change | CV R² | Test R² | Samples |
|---------|-----------|:-----:|:-------:|:-------:|
| v1 | Raw SNPs only | neg | 0.146 | 2,867 |
| v2 | + Environment | 0.111 | 0.487 | 2,867 |
| v3 | + PCA compression | 0.169 | 0.490 | 2,867 |
| v4 | + Weather data | 0.183 | 0.508 | 2,867 |
| v5 | Random Forest, 2017 only | 0.572 | 0.635 | 2,867 |
| **v25** | **XGBoost, 5-year multi-location** | **0.355** | **0.361** | **46,686** |

> **Why did CV R² drop from v5 to v25?** v5 was trained on 2017-only data (1 year, 23 locations). The v25 honest CV is harder: it trains on 5 years × 38 locations with proper per-fold location re-normalisation, making it a much more rigorous generalisation test. The v5 CV also had data leakage (y_norm computed on full dataset before CV splits). v25 is the honest number.

### ✅ Current Model — v25 (XGBoost, 5-year G2F)

| Metric | Value | Notes |
|--------|-------|-------|
| CV R² (normalized) | **0.355 ± 0.007** | Honest 3-fold; location z-scores re-computed per fold |
| Test R² (normalized) | **0.361** | 20% held-out test set, never seen during training |
| Training samples | **46,686** | 5 years × 38 locations × 2,912 hybrids |
| Algorithm | **XGBoost** | 400 trees, lr=0.03, max_depth=5 |
| SNP strategy | **Mid-parent average** | `(female_dosage + male_dosage) / 2` → 10k features |
| PCA components | **20** | TruncatedSVD on scaled mid-parent SNP matrix |
| Total features | **47** | 20 PCA + 27 env/trait features |

> **Context:** Published GBLUP benchmarks on G2F data typically achieve R² = 0.35–0.55 on normalized yield. NeuroCrop is competitive while additionally modelling real field-level environment — something standard GBLUP does not do.

---

## 🔍 Feature Importance

| Feature Group | Importance | Features Included |
|---------------|:----------:|-------------------|
| **Genetics (PCA)** | **41.1%** | 20 principal components from top-10k SNPs (mid-parent) |
| **Plant Traits** | **23.7%** | Height, ear height, moisture, silk DAP, pollen DAP |
| **Season Weather** | **18.9%** | Temp, humidity, rainfall, solar radiation, wind, photoperiod (May–Sep) |
| **Critical Weather** | **16.3%** | Temp mean/max, rainfall, solar, humidity (Jun–Aug flowering window) |
| **Soil** | **0.0%** | pH, OM, N, K, CEC, sand/silt/clay *(limited coverage — 1 of 38 locations matched)* |

> **Note on soil:** Soil files exist for 2015–2018 but only 1 location had matching `Field-Location` keys in the current run. Improving soil coverage is the highest-priority data quality task.

---

## 🧠 Pipeline Overview

### 1️⃣ Data Preprocessing

- Stack 5 years of phenotype CSVs → 84,045 rows → filter to 46,686 after genotype matching
- Weather: load only 8 columns per year via `usecols` (2018 = 251 MB → 24 MB in RAM); parse `Month [Local]` column
- Soil: concat years, deduplicate `Field-Location` columns, fill missing with column mean
- Retry logic on all Drive reads (`OSError [Errno 107]` = Drive disconnect → auto-remount)

### 2️⃣ Genotype Loading (VCF, two-pass streaming)

```
Pass 1: iter_vcf_chunks(chunk_length=50k) → per-SNP variance → TOP_SNP_IDX
Pass 2: iter_vcf_chunks(chunk_length=50k) → extract only top-10k rows → dosage_top
```

- Never allocates full dosage matrix (3.6 GB) — peak RAM ≈ 500 MB
- `dosage_top` shape: `(2,193 inbreds, 10,000 SNPs)` = 84 MB
- SNP representation: **mid-parent average** `(female + male) / 2` → `(n_samples, 10,000)`

### 3️⃣ Feature Engineering

- `scaler_snp`: StandardScaler fitted via `partial_fit` chunks (in-place, no extra allocation)
- `PCA_SNP_MEAN`: column mean subtracted in-place for TruncatedSVD compatibility
- `TruncatedSVD(n_components=20)`: no hidden float64 copy — peak Cell 23 RAM ≈ 5.6 GB
- Final feature matrix: `X_final (46,686 × 47)` = 8 MB

### 4️⃣ Model Training

- **Algorithm:** XGBoost (400 trees, lr=0.03, max_depth=5, subsample=0.8)
- **Yield normalisation:** per-location z-score (`(y - loc_mean) / loc_std`)
- **Validation:** honest 3-fold CV — location z-scores re-computed inside each fold to prevent leakage
- **De-normalisation at inference:** `pred_bu_A = pred_norm × loc_std + loc_mean`

### 5️⃣ Prediction System

```python
predict_yield(parent1, parent2, location)
# → Returns: (yield_bu_A, std_bu_A)
```

- Pre-cached SNP vectors (`SNP_CACHE`) and location env vectors (`LOC_ENV_CACHE`) for fast lookup
- 2,994,894 combinations pre-computed and saved to `all_predictions.csv` (99.8 MB)
- Streamlit app serves predictions via CSV lookup — no model inference at runtime

---

## 🌽 Example Predictions

### Single-Cross Predictions (v25 model)

| Female | Male | Location | Predicted (bu/A) | Category |
|--------|------|----------|:----------------:|:--------:|
| B73 | Mo17 | ILH1 | **180.27** | 🟢 High |
| B73 | Mo17 | GAH1 | **134.40** | 🔴 Low |
| Oh43 | Mo17 | IAH4 | **176.21** | 🟢 High |

### Top Locations for B73 × Mo17

| Rank | Location | Predicted Yield (bu/A) |
|:----:|----------|:----------------------:|
| 1 | WIH1 | **194.04** |
| 2 | ONH1 | **194.00** |
| 3 | IAH2 | **185.12** |
| 4 | NCH1 | **183.05** |
| 5 | IAH4 | **182.98** |

---

## 📊 Visualizations

Generated by the notebook and available in the Streamlit app:

| Output | Description |
|--------|-------------|
| Actual vs Predicted scatter | Test set R² = 0.361, normalized yield |
| Feature importance bar chart | Grouped by category (genetics, traits, weather, soil) |
| PCA variance explained | TruncatedSVD scree plot |
| Residual plot | Bias and variance pattern by predicted value |
| Yield distribution | Histogram + by-location boxplot |
| G×E interaction lines | Hybrid performance across locations |
| G×E heatmap | Genotype × environment yield matrix |
| CV fold scores | Honest 3-fold R² per fold |
| Stability scatter | Mean yield vs CV% for all 2,912 hybrids |

---

## ⚙️ Requirements

| Library | Version | Purpose |
|---------|---------|---------|
| Python | 3.9+ | |
| numpy | ≥ 1.24 | Array operations |
| pandas | ≥ 2.0 | Data loading |
| scikit-learn | ≥ 1.3 | Scaler, PCA, CV |
| xgboost | ≥ 1.7 | Primary model |
| scikit-allel | 1.3.13 | VCF loading (`iter_vcf_chunks`) |
| plotly | latest | Interactive charts |
| streamlit | ≥ 1.28 | Web app |
| reportlab | latest | PDF report generation |
| openpyxl | latest | Excel export |

---

## 🚀 Installation

```bash
git clone https://github.com/manan348/maize-yield-prediction.git
cd maize-yield-prediction
pip install -r requirements.txt
```

---

## 🖥️ Running the App

### Streamlit (local)

```bash
streamlit run app/app.py
```

The app expects `outputs/predictions/all_predictions.csv` to be present. It serves pre-computed predictions — no model inference at runtime.

### Live deployment

The app is deployed on Streamlit Cloud:  
🌐 [maize-yield-prediction-ryntvaanvvfya8wkdtkkba.streamlit.app](https://maize-yield-prediction-ryntvaanvvfya8wkdtkkba.streamlit.app/)

### Retraining (Google Colab)

Open `notebook/maize_yield_prediction_v25_fixed.ipynb` in Colab with Drive mounted. Run cells in order:

```
9 (paths) → 10 (pip install) → 11 (phenotype + VCF names) →
13 (lookups) → 14 (prep phenotype) → 16 (weather + soil) →
18 (merge) → 20 (imports) → 21 (~5 min, VCF load) →
23 (~6 min, PCA) → 25 (~8 min, train) → 28 (save) →
36 (cache + predict_yield) → 37 (~20 min, all_predictions.csv)
```

**After a crash:** Run Cell 33 (loads all saved `.npy`/`.pkl` from Drive) → jump to Cell 36 → Cell 37.

---

## 📦 Artifacts

### `outputs/predictions/`

| File | Size | Description |
|------|------|-------------|
| `all_predictions.csv` | **99.8 MB** | 2,994,894 cross × location predictions |
| `loc_stats.csv` | <1 MB | Per-location yield mean + std for de-normalisation |
| `df_raw.csv` | 12.4 MB | Processed phenotype dataframe (46,686 rows) |
| `feat_cols.json` | <1 MB | FEAT_COLS, SOIL_COLS, N_SNPS, N_COMP |
| `taxa_lookup.json` | <1 MB | Inbred name → VCF row index mapping |
| `best_model.pkl` | 1.0 MB | Fitted XGBoost model |
| `pca.pkl` | 0.8 MB | TruncatedSVD (20 components) |
| `scaler_snp.pkl` | 0.2 MB | StandardScaler for 10k mid-parent SNP features |
| `scaler_final.pkl` | <1 MB | StandardScaler for 47-feature final matrix |
| `dosage_top.npy` | 83.7 MB | Top-10k SNP dosage matrix (2,193 × 10,000) |
| `pca_snp_mean.npy` | <1 MB | Column mean for pre-centering before TruncatedSVD |
| `TOP_SNP_IDX.npy` | 0.1 MB | Global VCF positions of top-10k SNPs |
| `kept_df_indices.npy` | 0.4 MB | df row indices used for training alignment |
| `X_snp.npy` | — | Mid-parent SNP matrix (46,686 × 10,000) |
| `X_env.npy` | 0.3 MB | Environment feature matrix |
| `X_final.npy` | 0.5 MB | Final feature matrix (46,686 × 47) |
| `y.npy` / `y_norm.npy` | 0.2 MB | Raw and normalised yield targets |

---

## 📁 Project Structure

```
maize-yield-prediction/
├── app/
│   └── app.py                        # Streamlit UI (NeuroCrop — 6 tabs)
├── notebook/
│   └── maize_yield_prediction_v25_fixed.ipynb   # Colab training notebook
├── outputs/
│   ├── predictions/
│   │   ├── all_predictions.csv       # 2,994,894 pre-computed predictions (99.8 MB)
│   │   ├── loc_stats.csv
│   │   ├── df_raw.csv
│   │   ├── feat_cols.json
│   │   ├── taxa_lookup.json
│   │   ├── best_model.pkl
│   │   ├── pca.pkl
│   │   ├── scaler_snp.pkl
│   │   ├── scaler_final.pkl
│   │   ├── dosage_top.npy
│   │   ├── pca_snp_mean.npy
│   │   └── *.npy
│   └── plots/
│       ├── actual_vs_predicted.png
│       ├── feature_importance.png
│       ├── pca_variance.png
│       └── residual_plot.png
├── requirements.txt
└── README.md
```

---

## 🗺️ Roadmap

| Timeline | Goal |
|----------|------|
| **Now** | Validate predictions against held-out G2F trial data; screenshot for investor deck |
| **+2 weeks** | FastAPI endpoint: `POST /predict {female, male, location}` → yield + std + percentile |
| **+1 month** | Add soybean (same G2F pipeline, broader TAM) |
| **+1 month** | Talk to 10 seed companies / plant breeders before building further |
| **+3 months** | Breeding recommendation engine: "Given my gene pool, recommend top 20 untested crosses" |
| **Fundraising** | 1 paying API customer + 2–3 letters of intent + working multi-year demo |

---

## 📄 License

**Dataset:** The G2F dataset is a public research resource from CyVerse Data Commons. Please cite the original source (DOI: 10.25739/ragt-7213) in any publications.

**Code:** MIT License — see `LICENSE` for details.

---

*NeuroCrop — predicting the field before planting it.*
