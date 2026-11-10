import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import scipy.stats as stats
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle, SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image as RLImage
from reportlab.lib.units import inch
from reportlab.pdfbase.ttfonts import TTFont
from reportlab import pdfbase
from reportlab.pdfbase import pdfmetrics
import plotly.io as pio
import matplotlib.pyplot as plt
import matplotlib.font_manager as _mpl_fm

try:
    plt.rcParams['font.family'] = 'DejaVu Sans'
    plt.rcParams['axes.unicode_minus'] = False
except Exception:
    pass
from reportlab.lib import colors
import streamlit.components.v1 as components
import os
import urllib.request
import glob



# ─── RDML PARSER ──────────────────────────────────────────────────────────────
def parse_rdml(file_bytes):
    """
    Parse an RDML file (.rdml is a ZIP containing rdml_data.xml).
    Returns a dict: {target_name: {'unkn': [cq,...], 'ref': [cq,...]}}
    Also returns a flat DataFrame for inspection.
    """
    import zipfile, io
    try:
        import xml.etree.ElementTree as ET
    except ImportError:
        return None, "xml.etree.ElementTree not available"

    rows = []
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            xml_name = next((n for n in zf.namelist() if n.endswith(".xml")), None)
            if xml_name is None:
                return None, "No XML found inside RDML file."
            with zf.open(xml_name) as xf:
                tree = ET.parse(xf)
        root = tree.getroot()

        # RDML uses namespaces like {http://www.rdml.org/rdml_v1_2.rng}
        ns_raw = root.tag.split("}")[0].lstrip("{") if "}" in root.tag else ""
        ns = f"{{{ns_raw}}}" if ns_raw else ""

        # Build lookup dicts for targets and samples
        target_types = {}   # id -> type ('toi' or 'ref')
        target_names = {}   # id -> name
        for t in root.findall(f"{ns}target"):
            tid  = t.get("id", "")
            tname = t.findtext(f"{ns}commercialAssay") or tid
            ttype = t.findtext(f"{ns}type") or "toi"
            target_types[tid] = ttype
            target_names[tid] = tname

        sample_types = {}  # id -> type ('unkn', 'ntc', 'std', etc.)
        for s in root.findall(f"{ns}sample"):
            sid   = s.get("id", "")
            stype = s.findtext(f"{ns}type") or "unkn"
            sample_types[sid] = stype

        for exp in root.findall(f"{ns}experiment"):
            for run in exp.findall(f"{ns}run"):
                for react in run.findall(f"{ns}react"):
                    sample_id = react.findtext(f"{ns}sample") or react.get("id", "")
                    stype = sample_types.get(sample_id, "unkn")
                    for data_el in react.findall(f"{ns}data"):
                        target_id = data_el.findtext(f"{ns}tar") or ""
                        cq_text   = data_el.findtext(f"{ns}cq")
                        try:
                            cq = float(cq_text) if cq_text else None
                        except ValueError:
                            cq = None
                        rows.append({
                            "Sample":      sample_id,
                            "SampleType":  stype,
                            "Target":      target_names.get(target_id, target_id),
                            "TargetType":  target_types.get(target_id, "toi"),
                            "Cq":          cq,
                        })

    except zipfile.BadZipFile:
        # Some RDML files are plain XML, not ZIP
        try:
            tree = ET.parse(io.BytesIO(file_bytes))
            root = tree.getroot()
            ns_raw = root.tag.split("}")[0].lstrip("{") if "}" in root.tag else ""
            ns = f"{{{ns_raw}}}" if ns_raw else ""
            target_types = {}
            target_names = {}
            for t in root.findall(f"{ns}target"):
                tid   = t.get("id", "")
                ttype = t.findtext(f"{ns}type") or "toi"
                target_types[tid] = ttype
                target_names[tid] = tid
            sample_types = {}
            for s in root.findall(f"{ns}sample"):
                sid   = s.get("id", "")
                stype = s.findtext(f"{ns}type") or "unkn"
                sample_types[sid] = stype
            for exp in root.findall(f"{ns}experiment"):
                for run in exp.findall(f"{ns}run"):
                    for react in run.findall(f"{ns}react"):
                        sample_id = react.findtext(f"{ns}sample") or react.get("id", "")
                        stype = sample_types.get(sample_id, "unkn")
                        for data_el in react.findall(f"{ns}data"):
                            target_id = data_el.findtext(f"{ns}tar") or ""
                            cq_text   = data_el.findtext(f"{ns}cq")
                            try:
                                cq = float(cq_text) if cq_text else None
                            except ValueError:
                                cq = None
                            rows.append({
                                "Sample":     sample_id,
                                "SampleType": stype,
                                "Target":     target_names.get(target_id, target_id),
                                "TargetType": target_types.get(target_id, "toi"),
                                "Cq":         cq,
                            })
        except Exception as e:
            return None, f"RDML parse error: {e}"
    except Exception as e:
        return None, f"RDML parse error: {e}"

    if not rows:
        return None, "No reaction data found in RDML file."

    df = pd.DataFrame(rows)
    return df, None


# ─── RDES PARSER ──────────────────────────────────────────────────────────────
def parse_rdes(file_bytes):
    """
    Parse an RDES file (tab-separated, .tsv / .csv / .txt).
    Required columns: Well, Sample, Sample Type, Target, Target Type, Dye, Cq
    Returns DataFrame with columns: Sample, SampleType, Target, TargetType, Cq
    """
    try:
        content = file_bytes.decode("utf-8", errors="replace")
        lines   = [l.rstrip("\r") for l in content.split("\n") if l.strip()]
        if not lines:
            return None, "Empty RDES file."

        header = [h.strip() for h in lines[0].split("\t")]
        required = ["Well", "Sample", "Sample Type", "Target", "Target Type", "Dye", "Cq"]
        missing  = [c for c in required if c not in header]
        if missing:
            return None, f"RDES file missing required columns: {missing}"

        rows = []
        for line in lines[1:]:
            if not line.strip():
                continue
            cells = line.split("\t")
            row   = dict(zip(header, cells))
            cq_raw = row.get("Cq", "").strip()
            try:
                cq = float(cq_raw.replace(",", ".")) if cq_raw and cq_raw != "-1.0" else None
            except ValueError:
                cq = None
            rows.append({
                "Sample":     row.get("Sample", "").strip(),
                "SampleType": row.get("Sample Type", "unkn").strip(),
                "Target":     row.get("Target", "").strip(),
                "TargetType": row.get("Target Type", "toi").strip(),
                "Cq":         cq,
            })

        if not rows:
            return None, "No data rows found in RDES file."
        return pd.DataFrame(rows), None

    except Exception as e:
        return None, f"RDES parse error: {e}"


# ─── RDML/RDES → session_state mapper ─────────────────────────────────────────



st.set_page_config(
    page_title="GeneQuantify",
    page_icon="🧬",
    layout="wide"
)

if 'language' not in st.session_state:
    st.session_state.language = "English"

# ── Global CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Başlığın üstten kesilmesini önle */
.block-container { padding-top: 3rem !important; padding-bottom: 1rem !important; }

/* Alert kutularını küçült */
div[data-testid="stAlert"] { padding: 5px 10px !important; font-size: 12px !important; }

/* Widget margin azalt */
div[data-testid="stNumberInput"] { margin-bottom: 0 !important; }
div[data-testid="stRadio"]       { margin-bottom: 0 !important; }

/* Sidebar sıkıştır */
section[data-testid="stSidebar"] > div:first-child { padding-top: 0.8rem !important; }
section[data-testid="stSidebar"] hr { margin: 4px 0 !important; }
</style>
""", unsafe_allow_html=True)
    

flags = {
    "Türkçe": "🇹🇷",
    "English": "🇬🇧",
    "Deutsch": "🇩🇪",
    "Français": "🇫🇷",
    "Español": "🇪🇸",
    "العربية": "🇸🇦"
}
default_index = list(flags.keys()).index(st.session_state.language)

# Sidebar — logo küçük ve ortalı
try:
    import base64 as _b64, os as _os
    _logo_path = "geneq.jpg"
    if _os.path.exists(_logo_path):
        with open(_logo_path, "rb") as _f:
            _logo_b64 = _b64.b64encode(_f.read()).decode()
        st.sidebar.markdown(
            f"<div style='text-align:center;padding:4px 0 6px 0;'>"
            f"<img src='data:image/jpeg;base64,{_logo_b64}' width='130' style='border-radius:8px;'/>"
            f"</div>",
            unsafe_allow_html=True
        )
    else:
        st.sidebar.image("geneq.jpg", width=140)
except Exception:
    st.sidebar.image("geneq.jpg", width=140)
selected_language = st.sidebar.selectbox(
    "🌐 Language",
    options=[f"{flags[lang]} {lang}" for lang in flags],
    index=default_index,
    label_visibility="collapsed"
)

try:
    selected_language_name = selected_language.split(' ', 1)[1]
    selected_flag = flags[selected_language_name]
except KeyError:
    selected_language_name = selected_language
    selected_flag = None

st.sidebar.markdown(
    f"<div style='font-size:11px;color:#888;margin:-6px 0 4px 0;'>"
    f"Language / Dil / Sprache / Langue / Idioma / لغة</div>",
    unsafe_allow_html=True
)

st.markdown("""
<style>
[data-testid="stSidebarCollapseButton"] {
    display: block !important;
    visibility: visible !important;
    opacity: 1 !important;
}
</style>
""", unsafe_allow_html=True)

st.sidebar.divider()
instruction_clicked = st.sidebar.button("📘 User Guide", use_container_width=True)

if instruction_clicked or selected_language_name == "Instruction":

    @st.dialog("📘 GeneQuantify — User Guide", width="large")
    def show_guide():
        st.markdown("""
<style>
.guide-section { background:#f8f9fa; border-left:4px solid #2196F3; padding:10px 16px; border-radius:4px; margin-bottom:12px; }
.guide-formula { background:#1e1e2e; color:#cdd6f4; font-family:monospace; padding:10px 14px; border-radius:6px; font-size:14px; margin:8px 0; }
.guide-warn { background:#fff3cd; border-left:4px solid #ffc107; padding:8px 14px; border-radius:4px; }
.guide-ok   { background:#d4edda; border-left:4px solid #28a745; padding:8px 14px; border-radius:4px; }
</style>
""", unsafe_allow_html=True)

        tab1, tab2, tab3, tab4, tab5 = st.tabs(["📥 Data Input", "🧮 Calculations", "📊 Statistics", "⚙️ Settings", "⚖️ Disclaimer"])

        with tab1:
            st.markdown("### 📥 Data Input Format")
            st.info("GeneQuantify accepts Cq values entered as a column — one value per line. Compatible with direct **Excel/spreadsheet copy–paste**.")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**✅ Correct format**")
                st.code("23.15\n22.90\n25.20\n24.88\n23.45", language="text")
            with col2:
                st.markdown("**✅ Also accepted (comma as decimal)**")
                st.code("23,15\n22,90\n25,20\n24,88\n23,45", language="text")
            st.markdown("""
**Guidelines:**
- Minimum **3 replicates** recommended per group (required for outlier detection)
- All groups for the same gene should have the **same number of replicates** (app auto-trims to shortest)
- Enter one target gene and one reference gene per section
- Multiple reference genes (geNorm normalization) can be enabled in the settings
""")
            st.markdown("### 📋 Example Study Design")
            st.dataframe({
                "Group": ["Control","Control","Control","Patient 1","Patient 1","Patient 1"],
                "Target Cq": [23.1, 22.9, 25.2, 27.3, 28.1, 26.8],
                "Reference Cq": [18.2, 17.9, 18.5, 18.3, 18.0, 18.6],
            }, use_container_width=True)

        with tab2:
            st.markdown("### 🧮 Calculation Methods")
            st.markdown("#### 1. Classic ΔΔCq Method (Livak & Schmittgen, 2001)")
            st.code("ΔCq        = Cq(target) − Cq(reference)\nΔΔCq       = ΔCt(sample) − ΔCt(control)\nFold Change = 2^(−ΔΔCq)", language="text")
            st.markdown("""
**Assumptions:**
- Target and reference gene efficiencies are both ~100% (E ≈ 2.0)
- Efficiency difference between target and reference < 10%
- If these assumptions are violated, use the **Pfaffl method** instead
""")
            st.markdown("#### 2. Pfaffl Method (Pfaffl, 2001)")
            st.code("Ratio = (E_target ^ ΔCq_target) / (E_ref ^ ΔCt_ref)\n\nwhere:\n  ΔCt_target = Ct_control(target) − Ct_sample(target)\n  ΔCt_ref    = Ct_control(ref)    − Ct_sample(ref)", language="text")
            st.info("The Pfaffl method accounts for primer-specific efficiencies and is more accurate when E differs between genes.")

            st.markdown("#### 3. Amplification Efficiency (E)")
            st.code("E = 10^(−1 / slope)\n\nPerfect efficiency: E = 2.0 (100%)\nAcceptable range:   E = 1.8 – 2.2  (90–110%)\nSlope range:        −3.10 to −3.58", language="text")
            st.markdown("""
**How to obtain E:**
| Method | Description |
|--------|-------------|
| Standard Curve | Run 4–5 serial dilutions; qPCR software reports slope → use built-in calculator |
| LinRegPCR | Free software; calculates E from raw fluorescence |
| qBase+ / CFX Maestro | Automated E calculation |
| Primer datasheet | Manufacturer-validated E for commercial kits |
""")
            st.markdown("#### 4. Multiple Reference Genes (geNorm, Vandesompele 2002)")
            st.code("Normalization Factor (NF) = arithmetic mean of reference gene Cq values\nGeNorm M-value < 0.5  → Excellent stability\nGeNorm M-value 0.5–1.0 → Acceptable\nGeNorm M-value ≥ 1.0  → Unstable — consider excluding", language="text")

        with tab3:
            st.markdown("### 📊 Statistical Decision Pathway")
            st.markdown("""
The app automatically selects the appropriate statistical test:

```
Input ΔCq values
      │
      ▼
Shapiro-Wilk normality test (p > 0.05 = normal)
      │
      ├── Both groups NORMAL ──▶ Levene's test (equal variance?)
      │                               │
      │                    ┌──────────┴──────────┐
      │                  YES (p>0.05)           NO (p≤0.05)
      │                    │                     │
      │             Student's t-test       Welch's t-test
      │
      └── Any group NON-NORMAL ──▶ Mann-Whitney U test
```

**Multi-group (≥3 groups):**
```
Normal + Equal variance     → One-way ANOVA → Tukey HSD post-hoc
Normal + Unequal variance   → Welch ANOVA   → Games-Howell post-hoc
Any non-normal              → Kruskal-Wallis → Dunn's test post-hoc
```
""")
            st.markdown("### 🔢 Multiple Testing Correction")
            st.markdown("""
When analyzing **multiple target genes**, the false positive risk increases:

| Method | Controls | Best for |
|--------|----------|----------|
| **Bonferroni** | Family-wise error rate (FWER) | Few genes, conservative |
| **FDR (Benjamini-Hochberg)** | False discovery rate | Many genes, more power |

**Rule of thumb:** Report both. Use FDR for exploratory studies (≥5 genes), Bonferroni for confirmatory studies.
""")

        with tab4:
            st.markdown("### ⚙️ Settings Guide")
            st.markdown("""
#### Gene & Group Count
Set the number of target genes and patient groups before entering data.  
Each target gene gets its own Ct input sections for control and each patient group.

#### Reference Genes
- **1 reference gene:** Simpler, but less reliable normalization
- **2+ reference genes:** Recommended (MIQE guidelines); geNorm stability automatically calculated
- Reference genes should be stably expressed across all conditions

#### Outlier Detection
| Setting | Description |
|---------|-------------|
| **Grubbs test** | Best for small samples (n=3–8); detects single extreme outliers |
| **IQR method** | Better for larger samples; flags values outside Q1−k×IQR / Q3+k×IQR |
| **Alpha (Grubbs)** | Significance threshold; 0.05 recommended |
| **k multiplier (IQR)** | 1.5 = standard Tukey fence; 3.0 = extreme outliers only |

> ⚠️ Outlier exclusion **requires biological or technical justification**. The app flags candidates — the researcher decides.

#### Efficiency Threshold
If |E_target − E_ref| exceeds this threshold (default 10%), a warning is shown and Pfaffl method is recommended.
""")

        with tab5:
            st.markdown("### ⚖️ Disclaimer & Citation")
            st.warning("""
**For Research & Education Use Only**

This application is intended for research, education, and preliminary laboratory analysis only.  
It is **NOT** designed or validated for clinical diagnosis, treatment decisions, or patient management.

**Users are responsible for:**
- Verifying the accuracy of entered Cq data
- Appropriate interpretation of results
- Confirming findings using validated laboratory methods

The developers are **not liable** for any decisions, losses, or damages arising from application use.  
All clinical decisions must be made by qualified professionals.
""")
            st.markdown("""
**How to cite GeneQuantify:**
Yalçınkaya B (2026). GeneQuantify: a web-based tool for qPCR gene expression and copy number variation analysis. *Molecular and Cellular Biochemistry*. https://doi.org/10.1007/s11010-026-05621-y

**References:**
- Livak KJ & Schmittgen TD. *Methods* 2001;25:402–408. (ΔΔCq method)
- Pfaffl MW. *Nucleic Acids Res* 2001;29(9):e45. (Pfaffl method)
- Vandesompele J et al. *Genome Biol* 2002;3(7). (geNorm)
- Bustin SA et al. *Clin Chem* 2009;55(4):611–622. (MIQE guidelines)
- Grubbs FE. *Technometrics* 1969;11(1):1–21. (Outlier detection)
- Benjamini Y & Hochberg Y. *J R Stat Soc B* 1995;57(1):289–300. (FDR)

**Contact:** [email removed]
""")

    show_guide()
    
language_map = {
    "Türkçe": "tr",
    "Español": "es",
    "English": "en",
    "Français": "fr",
    "Deutsch": "de",
    "العربية": "ar"
}

language_code = language_map.get(selected_language_name, "en")  

translations = {
    "tr": {
        "title": "🧬 GeneQuantify: Gen Ekspresyonu ve Kopya Sayısı Varyasyonu (CNV) Analizi",
        "tab_data": "Veri Girişi",
        "tab_results": "Sonuçlar",
        "tab_report": "Rapor",
        "subtitle": "B. Yalçınkaya tarafından geliştirildi",
        "patient_data_header": "📊 Hasta ve Kontrol Grubu Verisi Girin",
        "num_target_genes": "🔹 Hedef Gen Sayısını Girin",
        "num_patient_groups": "🔹 Hasta Grubu Sayısını Girin",
        "sample_number": "Örnek Numarası",
        "Grup": "Grup",
        "x_axis_title": "Grup Adı",
        "ct_value": "Cq Değeri",
        "reference_ct": "Referans Cq",
        "delta_ct_control": "ΔCq (Kontrol)",
        "delta_ct_patient": "ΔCq (Hasta)",
        "warning_empty_input": "⚠️ Dikkat: Verileri alt alta yazın veya boşluk içeren hücre olmayacak şekilde excelden kopyalayıp yapıştırın.",
        "download_csv": "📥 CSV İndir",
        "generate_pdf": "📥 PDF Raporu Hazırla",
        "pdf_report": "Gen Ekspresyon Analizi Raporu",
        "statistics": "istatistiksel Sonuçlar",
        "nil_mine": "📊 Sonuçlar",
        "gr_tbl": "📋 Giriş Verileri Tablosu",
        "control_group": "🧬 Kontrol Grubu",
        "ctrl_trgt_ct": "🟦 Kontrol Grubu Hedef Gen {i} Cq Değerleri",
        "ctrl_ref_ct": "🟦 Kontrol Grubu Referans Gen {i} Cq Değerleri",
        "hst_trgt_ct": "🩸 Hasta Grubu Hedef Gen {j} Cq Değerleri",
        "hst_ref_ct": "🩸 Hasta Grubu Referans Gen {j} Cq Değerleri",
        "warning_control_ct": "⚠️ Dikkat: Kontrol Grubu {i} verilerini alt alta yazın veya boşluk içeren hücre olmayacak şekilde Excel'den kopyalayıp yapıştırın.",
        "warning_patient_cq": "⚠️ Dikkat: Hasta grubu Cq verilerini alt alta yazın veya boşluk içeren hücre olmayacak şekilde Excel'den kopyalayıp yapıştırın.",
        "target_gene": "Hedef Gen",
        "reference_gene": "Referans Gen",
        "target_ct": "Hedef Gen Cq",
        "distribution_graph": "Dağılım Grafiği",
        "error_missing_control_data": "⚠️ Hata: Kontrol Grubu için Hedef Gen {i} verileri eksik!",
        "control_group_avg": "Kontrol Grubu Ortalama",
        "avg": "Ortalama",
        "control": "Kontrol",
        "sample": "Örnek",
        "patient": "Hasta",
        "delta_ct_distribution": "ΔCq Dağılımı",
        "delta_ct_value": "ΔCq Değeri",
        "parametric": "Parametrik",
        "non_parametric": "Nonparametrik",
        "t_test": "t-test",
        "mann_whitney_u_test": "Mann-Whitney U testi",
        "welch_t_test": "welch_t_testi",
        "significant": "Anlamlı",
        "insignificant": "Anlamsız",
        "test_type": "Test Türü",
        "test_method": "Kullanılan Test",
        "test_pvalue": "Test P-değeri",
        "significance": "Anlamlılık",
        "delta_delta_ct": "ΔΔCq",
        "gene_expression_change": "Gen Ekspresyon Değişimi (2^(-ΔΔCq))",
        "regulation_status": "Regülasyon Durumu",
        "no_change": "Değişim Yok",
        "upregulated": "Yukarı Regüle",
        "downregulated": "Aşağı Regüle",
        "report_title": "Gen Ekspresyon Analizi Raporu",
        "input_data_table": "Giriş Verileri Tablosu",
        "results": "Sonuçlar",
        "statistical_results": "📈 İstatistiksel Sonuçlar",
        "statistical_evaluation": "İstatistiksel Değerlendirme",
        "target_gene": "Hedef Gen",
        "patient_group": "🩸 Hasta Grubu",
        "expression_change": "Gen Ekspresyon Değişimi",
        "generate_pdf": "PDF Oluştur",
        "pdf_report": "Gen Ekspresyon Raporu",
        "error_no_data": "Veri bulunamadı, PDF oluşturulamadı.",
        # Efficiency translations
        "efficiency_header": "🔬 Amplifikasyon Etkinliği (Efficiency) Doğrulaması",
        "efficiency_method": "Efficiency Giriş Yöntemi",
        "efficiency_manual": "Manuel E değeri gir",
        "efficiency_slope": "Slope (eğim) ile hesapla",
        "efficiency_target_label": "Hedef Gen {i} Efficiency (E)",
        "efficiency_ref_label": "Referans Gen {i} Efficiency (E)",
        "efficiency_target_slope_label": "Hedef Gen {i} Slope",
        "efficiency_ref_slope_label": "Referans Gen {i} Slope",
        "efficiency_threshold": "Kabul edilebilir efficiency farkı eşiği (%)",
        "efficiency_ok": "✅ Efficiency farkı kabul edilebilir ({diff:.1f}%)",
        "efficiency_warning": "⚠️ Efficiency farkı eşiği aşıyor ({diff:.1f}%) — ΔΔCq yöntemi güvenilir olmayabilir!",
        "efficiency_target_pct": "Hedef Gen Efficiency",
        "efficiency_ref_pct": "Referans Gen Efficiency",
        "efficiency_diff": "Fark",
        "pfaffl_result": "Pfaffl Oranı",
        "pfaffl_header": "Pfaffl Metodu Sonuçları",
        "classic_ddct": "Klasik ΔΔCq Sonucu (2^(-ΔΔCq))",
        "pfaffl_ratio": "Pfaffl Oranı",
        "method_comparison": "📊 Yöntem Karşılaştırması",
        "efficiency_note": "Not: E=2.0 mükemmel etkinliği (100%) temsil eder. Kabul edilen aralık: 1.8–2.2 (90–110%)",
        "statistical_explanation": (
            "İstatistiksel değerlendirme sürecinde veri dağılımı Shapiro-Wilk testi ile analiz edilmiştir. "
            "Normallik sağlanırsa, gruplar arasındaki varyans eşitliği Levene testi ile kontrol edilmiştir. "
            "Varyans eşitliği varsa bağımsız örneklem t-testi, yoksa Welch t-testi uygulanmıştır. "
            "Normal dağılım sağlanmazsa, parametrik olmayan Mann-Whitney U testi kullanılmıştır. "
            "Sonuçların anlamlılığı p < 0.05 kriterine göre belirlenmiştir. "
            "<b>Öneri ve destekleriniz için:</b> Burhanettin Yalçınkaya - mail: [email removed]"
        ),
        # Outlier section
        "outlier_section_title": "### 🔍 Aykırı Değer Tespiti Ayarları",
        "outlier_enable": "Aykırı değer tespitini etkinleştir",
        "outlier_enable_help": "İstatistiksel olarak aşırı Cq değerlerini tespit eder.",
        "outlier_method_label": "Tespit yöntemi",
        "outlier_method_help": "Grubbs: normal dağılım için, tek aykırı değer. IQR: parametrik olmayan, çarpık dağılımlar için.",
        "outlier_alpha_label": "Anlamlılık düzeyi (α)",
        "outlier_alpha_help": "α = 0.05 standart değerdir. Düşük α = daha muhafazakâr.",
        "outlier_iqr_label": "IQR çarpanı (k)",
        "outlier_iqr_help": "k=1.5 = standart Tukey sınırları. k=3.0 = yalnızca aşırı aykırı değerler.",
        "outlier_expander": "ℹ️ qPCR'de aykırı değer tespiti hakkında",
        "grubbs_info": "ℹ️ **Grubbs testi gereksinimleri:** Her grup için minimum **n ≥ 3** replikat. Anlamlılık eşiği: **α = {alpha:.2f}**. Test normallik varsayar; n < 8 için normallik güvenilir biçimde değerlendirilemez — sonuçlar dikkatli yorumlanmalıdır. Gürültülü replikatların ΔCq hesabına yansımasını önlemek için **ham Cq değerlerine** (normalizasyon öncesi) uygulanması önerilir.",
        "outlier_excluded_no": "Hayır",
        "outlier_excluded_yes": "Evet",
        # Outlier stage selector 
        "outlier_stage_label": "🔬 Aykırı Değer Uygulama Aşaması",
        "outlier_stage_raw": "Ham Cq — normalizasyon öncesi (önerilen)",
        "outlier_stage_dct": "ΔCq — normalizasyon sonrası (eski davranış)",
        "outlier_stage_help": (
            "**Ham Ct (önerilen):** Aykırı değerler, ΔCq hesaplanmadan önce ham Cq değerlerine "
            "uygulanır. Her target ve referans gen için ayrı ayrı kontrol edilir. "
            "Gürültülü replikatların normalizasyona sızması engellenir.\n\n"
            "**ΔCq:** Aykırı değerler normalizasyon sonrası uygulanır (orijinal davranış)."
        ),
        # Distribution plot mode selector 
        "dist_plot_mode_label": "📊 Dağılım Grafiği — Görüntüleme Modu",
        "dist_plot_rq":   "RQ (2^-ΔCq)  — önerilen",
        "dist_plot_dct":  "ΔCq  — ham normalize değerler",
        "dist_plot_ddct": "ΔΔCq  — kontrol ortalamasına göre",
        "dist_plot_help": (
            "**RQ (önerilen):** ΔCq → 2^(-ΔCt) dönüşümü. Yüksek değer = yüksek ekspresyon. "
            "Yüksek ΔCq = düşük ekspresyon paradoksunu ortadan kaldırır.\n\n"
            "**ΔCq:** Ham logaritmik değerler. Veri dağılımı ve normallik kontrolü için.\n\n"
            "**ΔΔCq:** Her örneğin ΔCq'si eksi kontrol grubu ortalaması. Kontrole göre değişimi gösterir."
        ),
        "unequal_n_warning": (
            "⚠️ **Eşit olmayan replikat sayısı — {group}:**  \n"
            "{details}  \nAnaliz **en kısa ortak uzunluk (n={min_n})** kullanılarak devam edecek.  \n"
            "Veri girişinizi kontrol edin — farklı n değerleri veri giriş hatası olabilir."
        ),
        # Sidebar
        "sidebar_load_example": "📂 Örnek Veri Yükle",
        "sidebar_example_loaded": "✅ Örnek veri yüklendi! Veri Girişi sekmesine geçin.",
        "sidebar_desktop_title": "### 💻 Masaüstü Uygulaması",
        "sidebar_desktop_btn": "⬇️ Masaüstü Uygulamasını İndir",
        "sidebar_opensource_title": "### 🔓 Açık Kaynak",
        "sidebar_opensource_body": "GeneQuantify açık kaynaklıdır (GPL-3.0).  \nKaynak kod GitHub'da mevcuttur:",
        "sidebar_github_btn": "⭐ GitHub'da Kaynak Kodu Görüntüle",
        "sidebar_scenarios_title": "📋 Doğrulama Senaryosu Yükle",
        "sidebar_scenario_select": "Senaryo seçin",
        "sidebar_load_scenario_btn": "▶ Senaryoyu Yükle",
        "sidebar_scenario_loaded": "✅ {s} yüklendi! Veri Girişi sekmesine geçin.",
        # Statistical decision
        "stat_decision_title": "🔬 İstatistiksel karar",
        "stat_decision_steps": "**Adım adım test seçimi:**",
        "stat_shapiro_title": "**1. Shapiro-Wilk normallik testi**",
        "stat_normal": "Normal",
        "stat_nonnormal": "Normal değil",
        "stat_levene_title": "**2. Levene varyans homojenliği testi**",
        "stat_levene_skipped": "**2. Levene testi** — *atlandı* (normallik sağlanmadı; parametrik olmayan test kullanılacak)",
        "stat_equal_var": "Eşit varyans",
        "stat_unequal_var": "Eşitsiz varyans",
        "stat_selected_test": "**3. Seçilen test:**",
        "stat_reason": "**Gerekçe:**",
        "stat_result": "**Sonuç:**",
        "stat_reason_nonnormal": "Bir veya her iki grupta normal dağılım sağlanmadı",
        "stat_reason_normal_equal": "Her iki grup normal + eşit varyans",
        "stat_reason_normal_unequal": "Her iki grup normal + eşitsiz varyans (Levene p < 0.05)",
        "stat_multigroup_note": "⚠️ Not: ≥ 3 grup varsa, ANOVA / Kruskal-Wallis testi için aşağıdaki **Çoklu Grup Karşılaştırması** bölümüne bakın.",
        # Multi-group
        "multigroup_title": "## 📊 Çoklu Grup Karşılaştırma Analizi",
        "multigroup_expander": "ℹ️ Çoklu grup istatistiksel analizi hakkında",
        "multigroup_omnibus_test": "Omnibus Testi",
        "multigroup_pvalue": "p-değeri",
        "multigroup_result": "Sonuç",
        "multigroup_significant": "Anlamlı",
        "multigroup_not_significant": "Anlamlı değil",
        "multigroup_omnibus_ns": "ℹ️ Omnibus testi **anlamlı değil** (p ≥ 0.05). Post-hoc karşılaştırmalar bilgi amaçlı gösterilmektedir — genel grup etkisi tespit edilmedi.",
        "multigroup_posthoc_label": "**Post-hoc:**",
        "multigroup_dl_button": "📥 Post-hoc sonuçlarını indir —",
        "multigroup_2group_note": "ℹ️ **Çoklu grup analizi uygulanamaz:** Yalnızca 2 grup tespit edildi (Kontrol + 1 hasta grubu). İkili istatistikler yukarıda raporlanmıştır.",
        "multigroup_decision_normal_equal": "✅ Normal dağılım + eşit varyans → **Tek yönlü ANOVA + Tukey HSD**",
        "multigroup_decision_normal_unequal": "⚠️ Normal dağılım + **eşitsiz varyans** → **Welch ANOVA + Games-Howell**",
        "multigroup_decision_nonnormal": "⚠️ **Normal dağılım sağlanmadı** → **Kruskal-Wallis + Dunn post-hoc**",
        # Multi-gene correction
        "multigene_title": "### 🧬 Çoklu Gen Çoklu Karşılaştırma Düzeltmesi",
        "multigene_expander": "ℹ️ Bu neden gereklidir?",
        "multigene_sig_raw": "Anlamlı (ham)",
        "multigene_sig_bonf": "Anlamlı (Bonferroni)",
        "multigene_sig_fdr": "Anlamlı (FDR B-H)",
        "multigene_warning": "⚠️ Düzeltme sonrası, ham p < 0.05 eşiğinde anlamlı görünen {lost} sonuç FDR düzeltmesi sonrası anlamlılığını yitirdi. Çoklu gen analizlerinde düzeltilmiş p-değerlerini birincil sonuç olarak raporlayın.",
        "multigene_success": "✅ {n} anlamlı sonucun tamamı FDR düzeltmesi sonrasında da anlamlı kalmaktadır — bulgular çoklu karşılaştırmaya karşı güçlüdür.",
        "multigene_no_sig": "Ham p < 0.05 eşiğinde anlamlı ikili sonuç tespit edilmedi.",
        "multigene_dl_button": "📥 Düzeltilmiş p-değerlerini indir (CSV)",
        "multigene_chart_title": "Çoklu Gen p-değeri Düzeltmesi: Ham / Bonferroni / FDR",
        "multigene_fc_chart_title": "Çoklu Gen İfade Karşılaştırması",
        "multigene_1gene_note": "ℹ️ **Çoklu gen düzeltmesi:** Yalnızca 1 hedef gen analiz edildi — genler arası çoklu karşılaştırma düzeltmesi uygulanamaz.",
        "multigene_no_data": "Henüz p-değeri yok — hesaplama için yukarıya veri girin.",
        # Reference gene settings
        "ref_gene_section_title": "### 📚 Referans Gen Ayarları",
        "ref_gene_num_label": "Hedef gen başına referans gen sayısı",
        "ref_gene_num_help": "MIQE kılavuzları sağlam normalizasyon için ≥2 doğrulanmış referans gen önerir.",
        "ref_gene_1_warning": "⚠️ **Metodolojik not:** Tek referans gen kullanımı normalizasyon sağlamlığını kısıtlar. MIQE kılavuzları (Bustin et al. 2009) **≥2 referans gen** ve stabilite değerlendirmesi (geNorm/NormFinder) önermektedir.",
        "ref_gene_multi_success": "✅ {n} referans gen seçildi. Geometrik ortalama normalizasyonu ve geNorm M-değeri stabilitesi otomatik hesaplanacaktır.",
        "ref_gene_expander": "ℹ️ Çoklu referans normalizasyonu hakkında",
        # Standard curve calculator
        "sc_expander": "📐 Standart Eğri Hesaplayıcı — Dilüsyon serisinden E hesapla",
        "sc_gene_label": "Gen / Primer etiketi",
        "sc_num_points": "Dilüsyon noktası sayısı",
        "sc_dilution_factor_label": "**Dilüsyon faktörü** (örn. 10 katlı dilüsyon için 10)",
        "sc_dilution_factor_input": "Dilüsyon faktörü",
        "sc_start_conc_label": "**Başlangıç konsantrasyonu** (keyfi birim, örn. 1)",
        "sc_start_conc_input": "Başlangıç konsantrasyonu",
        "sc_enter_ct": "**Her dilüsyon için ortalama Cq girin:**",
        "sc_calc_button": "📊 Etkinliği Hesapla",
        "sc_slope": "Eğim",
        "sc_e_value": "E değeri",
        "sc_efficiency_pct": "Etkinlik %",
        "sc_excellent": "✅ Mükemmel! E={e:.4f} ({pct:.1f}%), R²={r2:.4f} — Bu E değerini aşağıdaki etkinlik bölümüne girin.",
        "sc_warning_r2": "⚠️ E kabul edilebilir ({pct:.1f}%) ancak R²={r2:.4f} < 0.99 — dilüsyon serinizi kontrol edin.",
        "sc_error_range": "❌ E={e:.4f} ({pct:.1f}%) kabul edilebilir aralığın dışında (90–110%). Primer tasarımınızı veya dilüsyon serinizi gözden geçirin.",
        "sc_chart_title": "Standart Eğri — {label} | E={e:.4f} ({pct:.1f}%), R²={r2:.4f}",
        "sc_xaxis": "log₁₀(Konsantrasyon)",
        "sc_data_points": "Veri noktaları",
        "sc_copy_hint": "💡 Aşağıdaki etkinlik girdilerine eğim **{slope:.4f}** veya E değeri **{e:.4f}** kopyalayın.",
        "sc_description": """\
**Standart Eğri Hesaplayıcı nasıl kullanılır:**

Seri dilüsyon Cq değerlerinizi aşağıya girin. Hesaplayıcı doğrusal regresyon uygulayarak eğim, R² ve amplifikasyon etkinliğini otomatik hesaplar.

**Kullanım:**  
1. Her primer için seri dilüsyonlarda qPCR çalıştırın (örn. seyreltilmemiş, 1:10, 1:100, 1:1000, 1:10000)  
2. Her dilüsyon için ortalama Cq değerini girin  
3. Eğim, E ve R² değerlerini okuyun  
""",
        "ref_multi_description": """\
**Geometrik ortalama normalizasyonu** (Vandesompele et al. 2002)  
Normalizasyon faktörü (NF), her örnek için tüm referans genlerinin Cq değerlerinin aritmetik ortalamasıdır;  
bu da ifade düzeylerinin geometrik ortalamasına karşılık gelir.  
`NF_örnek = ortalama(Ct_ref1, Ct_ref2, ..., Ct_refN)` her örnek için  
`ΔCq = Ct_hedef − NF`

**geNorm M-değeri** (stabilite skoru)  
Her referans gen için M, diğer tüm referans genlerine karşı log-oranlarının ortalama standart sapmasıdır.  
**Düşük M = daha kararlı.** MIQE tavsiye edilen eşik: M < 0,5 (katı) veya M < 1,0 (kabul edilebilir).

**CV (Varyasyon Katsayısı)**  
`CV = (SS / ortalama) × 100%` tüm örneklerdeki ham Cq değerlerinin.  
Düşük CV, daha az varyasyon ve referans olarak daha iyi kararlılık anlamına gelir.

**Referans:** Vandesompele J et al. *Genome Biology* 2002; Bustin SA et al. *Clin Chem* 2009 (MIQE).
""",
        "outlier_description": """\
**qPCR'de aykırı değer tespiti neden önemlidir?**

Teknik değişkenlik qPCR'ye özgüdür: pipetleme hataları, hava kabarcığı oluşumu, inhibitör taşınması veya RNA kalite farklılıkları, replikat grubunun geri kalanıyla istatistiksel olarak uyumsuz Cq değerleri üretebilir.  
Bu tür değerlerin dahil edilmesi varyansı şişirir, ortalamaları saptırır ve yanlış sonuçlara yol açabilir — özellikle küçük örneklem büyüklüklüeri olan klinik veri setlerinde.

**Bu kısıtlamanın kritik hale geldiği durumlar:**
- Küçük gruplar (n < 5): tek bir hatalı Ct ortalamayı önemli ölçüde kaydırır
- Yüksek biyolojik değişkenlik (örn. tümör heterojenliği, klinik kohortlar)
- Bir replikatın diğerlerinden > 0,5 Ct sapma gösterdiği teknik triplıkatlar
- Ct > 35 olan düşük bolluklu hedefler, gürültünün baskın olduğu durumlar

**Grubbs testi** *(Grubbs 1969)*  
Normallik varsayar. En uç değerin istatistiksel olarak anlamlı bir aykırı değer olup olmadığını test eder (p < α). Başka aykırı değer bulunmayana kadar tekrarlanır.  
En iyi: tek bir deneysel gruptan replikat Cq değerleri için.

**IQR yöntemi** *(Tukey 1977)*  
Parametrik olmayan. Q1 − k×IQR veya Q3 + k×IQR dışındaki değerleri işaretler.  
En iyi: daha büyük gruplar veya normal olmayan dağılımlar için.

**Önemli:** Aykırı değer dışlama **biyolojik veya teknik gerekçe** gerektirir.  
Bu araç adayları işaretler — nihai karar her zaman araştırmacıya aittir.  
Tüm dışlamalar kaydedilir ve PDF çıktısında raporlanır.

**Referanslar:** Grubbs FE. *Technometrics* 1969; Tukey JW. *Exploratory Data Analysis* 1977;  
Bustin SA et al. *Clin Chem* 2009 (MIQE kılavuzları).
""",

        # ── PDF rapor stringleri ──────────────────────────────────────────────
        "pdf_cover_subtitle": "qPCR Gen Ekspresyonu Analiz Raporu",
        "pdf_generated": "Oluşturulma tarihi: {now}",
        "pdf_s1_title": "1. Yöntemler ve Analiz Ayarları",
        "pdf_s1_calc": "1.1 Hesaplama Yöntemleri",
        "pdf_s1_calc_body": "Kat değişimi hesabı için iki tamamlayıcı yöntem kullanıldı:",
        "pdf_s1_classic": "Klasik ΔΔCq (Livak & Schmittgen, 2001): ΔCq = Cq(hedef) - Ct(referans);  ΔΔCq = ΔCq(örnek) - ΔCt(kontrol);  Kat Değişimi = 2^(-ΔΔCt). Her iki gen için eşit amplifikasyon verimliliği varsayar (E ≈ 2.0).",
        "pdf_s1_pfaffl": "Pfaffl Yöntemi (Pfaffl, 2001): Oran = (E_hedef ^ ΔCq_hedef) / (E_ref ^ ΔCt_ref). Primer'e özgü verimlilikleri düzeltir; verimlilik farkı > %10 olduğunda önerilir.",
        "pdf_s1_norm": "1.2 Normalizasyon",
        "pdf_s1_norm_multi": "Çoklu referans gen (n={n}) kullanıldı. Normalizasyon faktörü (NF), her örnek için referans gen Cq değerlerinin aritmetik ortalaması olarak hesaplandı (geNorm yaklaşımı, Vandesompele et al. 2002). geNorm M-değerleri ve varyasyon katsayısı (CV%) hesaplandı.",
        "pdf_s1_norm_single": "Normalizasyon için tek referans gen kullanıldı. MIQE kılavuzları sağlam normalizasyon için ≥2 referans gen önermektedir.",
        "pdf_s1_eff": "1.3 Amplifikasyon Verimliliği",
        "pdf_s1_eff_range": "Kabul edilebilir verimlilik aralığı: E = 1.8-2.2 (%90-110%). Uygulanan verimlilik farkı eşiği: {thr}%.",
        "pdf_s1_outlier": "1.4 Aykırı Değer Tespiti",
        "pdf_s1_grubbs": "Grubbs testi (Grubbs 1969) uygulandı, alfa = {alpha}. Test, bir veri setindeki en uç değerin istatistiksel olarak anlamlı bir aykırı değer olup olmadığını t-dağılımı kritik değeri ile test eder. {n} örnek işaretlendi ve kullanıcı tarafından dışlama onaylandı.",
        "pdf_s1_iqr": "IQR yöntemi (Tukey 1977) uygulandı, çarpan k = {k}. [Q1 - k*IQR, Q3 + k*IQR] dışındaki değerler potansiyel aykırı değer olarak işaretlendi. {n} örnek dışlama için kullanıcı tarafından onaylandı.",
        "pdf_s1_outlier_warn": "UYARI: Aykırı değer dışlama biyolojik veya teknik gerekçe gerektirir. Dışlanan örnekler aşağıdaki veri tablosunda işaretlendi.",
        "pdf_s1_outlier_off": "Bu analiz için aykırı değer tespiti devre dışı bırakıldı.",
        "pdf_s2_title": "2. Giriş Verileri",
        "pdf_s2_body": "Aykırı değer işleme sonrası kullanıcı tarafından girilen ham Cq değerleri. 'Aykırı Değer Dışlandı' sütununda 'Evet' olan satırlar hesaplamalardan çıkarıldı.",
        "pdf_s3_title": "3. Gen Ekspresyonu Sonuçları",
        "pdf_s3_body": "Klasik ΔΔCq ve Pfaffl yöntemleriyle hesaplanan kat değişimi değerleri. Kat değişimi > 1 hasta grubunda kontrole göre yüksek ekspresyonu gösterir.",
        "pdf_s4_title": "4. İstatistiksel Analiz",
        "pdf_s4_body": "Kontrol ve hasta grupları arasındaki gen ekspresyon farklılıklarının istatistiksel anlamlılığı. Tüm testler ham ΔCq değil RQ (2^-ΔCt) değerleri üzerinden uygulandı; çünkü ΔCt logaritmik ölçekte olduğundan, ΔCt üzerinden t-testi biyolojik değişkenliği hafife alabilir. Test seçimi normallik (Shapiro-Wilk) ve varyans homojenliği (Levene) testlerine göre otomatik yapıldı. Anlamlılık eşiği: p < 0.05.",
        "pdf_s4_interp": "İstatistiksel Testlerin Yorumu",
        "pdf_s4_interp_body": "Student t-testi: Her iki grup normal dağılım ve eşit varyanstaysa kullanılır. Welch t-testi: Her iki grup normal fakat varyanslar eşit değilse kullanılır. Mann-Whitney U: Normallik varsayımı karşılanmadığında kullanılan parametrik olmayan test. p < 0.05 istatistiksel olarak anlamlı diferansiyel ekspresyonu gösterir.",
        "pdf_s5_title": "5. Göreli Miktar (RQ) Dağılım Grafikleri",
        "pdf_s5_body": "Her hedef gen için RQ (2^-ΔCq) değerlerinin dağılımı. Her nokta bir biyolojik replikatı temsil eder. Yatay çubuklar grup ortalamalarını gösterir. İstatistiksel testler de RQ değerleri üzerinden gerçekleştirilmiştir.",
        "pdf_s6_title": "6. Sonuçların Yorumlanması",
        "pdf_s6_fc": "6.1 Kat Değişimi Yorumu",
        "pdf_s6_choose": "6.2 ΔΔCq ve Pfaffl Arasında Seçim",
        "pdf_s6_choose_body": "Klasik ΔΔCq'yi şu durumlarda kullanın: Her iki genin verimliliği %90-110 aralığında ve aralarındaki fark %10'dan az. Pfaffl'ı şu durumlarda kullanın: Verimlilik farkı %10'u aşıyor ya da gen verimlilikleri ölçülmüş ve farklı. Her durumda her iki değeri de raporlayın.",
        "pdf_s6_stat": "6.3 İstatistiksel Test Seçimi Gerekçesi",
        "pdf_s6_stat_body": "Normallik değerlendirmesi için Shapiro-Wilk testi (küçük örneklemler, n < 50 için önerilir) kullanıldı. Varyans homojenliği için Levene testi uygulandı. Eşit varyanslı parametrik veriler için Student t-testi maksimum istatistiksel güç sağlar. Welch t-testi varyanslar farklı olduğunda daha sağlamdır. Mann-Whitney U normallik varsayılamadığında parametrik olmayan alternatiftir.",
        "pdf_s7_title": "7. Kaynaklar",
        "pdf_fc_interp_header": ["Kat Değişimi", "ΔΔCq", "Yorum", "Biyolojik Önem"],
        "pdf_fc_interp_rows": [
            [">2.0", "<-1.0", "Güçlü yukarı regülasyon", "Biyolojik olarak anlamlı kabul edilebilir"],
            ["1.5-2.0", "-1.0 ila -0.58", "Orta yukarı regülasyon", "İlgili olabilir; doğrulayın"],
            ["1.0-1.5", "-0.58 ila 0", "Zayıf yukarı regülasyon", "Tek başına genellikle önemsiz"],
            ["1.0", "0", "Değişim yok", "Diferansiyel ekspresyon yok"],
            ["0.67-1.0", "0 ila 0.58", "Zayıf aşağı regülasyon", "Tek başına genellikle önemsiz"],
            ["0.5-0.67", "0.58 ila 1.0", "Orta aşağı regülasyon", "İlgili olabilir; doğrulayın"],
            ["<0.5", ">1.0", "Güçlü aşağı regülasyon", "Biyolojik olarak anlamlı kabul edilebilir"],
        ],
        "pdf_stat_note": "Not: İstatistiksel anlamlılık (p < 0.05) ve biyolojik anlamlılık (kat değişimi büyüklüğü) birlikte değerlendirilmelidir.",
        "pdf_summary_param": "Parametre",
        "pdf_summary_val": "Değer",
        "pdf_summary_genes": "Analiz edilen hedef gen sayısı",
        "pdf_summary_groups": "Hasta grupları",
        "pdf_summary_samples": "Toplam örnek (satır)",
        "pdf_summary_excluded": "Aykırı değer dışlanan örnek",
        "pdf_summary_tests": "karşılaştırma",
        "pdf_summary_norm": "Normalizasyon yöntemi",
        "pdf_summary_norm_multi": "geNorm NF",
        "pdf_summary_norm_single": "Tek referans gen",
        "pdf_summary_methods": "Hesaplama yöntemleri",
        "pdf_summary_methods_val": "Klasik ΔΔCq + Pfaffl",
        "pdf_disclaimer": "Bu rapor GeneQuantify tarafından otomatik oluşturulmuştur. Tüm hesaplamalar MIQE kılavuzlarını (Bustin et al., Clin Chem 2009) izler.",
        "pdf_footer": "GeneQuantify — Yalnızca araştırma ve eğitim amaçlı. Klinik tanı için doğrulanmamıştır.",
        "pdf_fig1": "Şekil 1. Klasik ΔΔCq ve Pfaffl yöntemleri arasında kat değişimi karşılaştırması. Kesikli çizgi y=1'de kontrole göre değişim olmadığını gösterir.",
        "pdf_fig2": "Şekil 2. Tüm ikili karşılaştırmalar için p-değerleri. Kırmızı çubuklar istatistiksel olarak anlamlı sonuçları (p < 0.05) gösterir. Kesikli çizgi anlamlılık eşiğini işaretler.",
        "pdf_fig3": "Şekil. {gene} için RQ (2^-ΔCq) dağılımı. Noktalar = bireysel replikatlar; yatay çubuklar = grup ortalamaları.",
        "pdf_nochange": "Değişim Yok",
        "pdf_stat_cols": ["Hedef Gen", "Karşılaştırma", "Test Türü", "Kullanılan Test", "p-değeri", "Anlamlılık"],
        "pdf_res_cols": ["Hedef Gen", "Grup", "ΔCq Kontrol", "ΔCq Örnek", "ΔΔCq", "2^(-ΔΔCq)", "Pfaffl Oranı", "Regülasyon", "E hedef", "E ref"],
        "pdf_eff_cols": ["Gen", "E (hedef)", "Eff% (hedef)", "E (ref)", "Eff% (ref)", "Fark%", "Durum"],
        "pdf_eff_ok": "Kabul edilebilir",
        "pdf_eff_warn": "UYARI: Pfaffl kullanın",
        "pdf_outlier_col": "Aykırı Değer Dışlandı",
        "pdf_contact": "İletişim: [email removed]",
        "pdf_ready": "{n} kayıt hazır — PDF oluşturabilirsiniz.",
        # RDML / RDES import
        "rdml_expander":        "📂 RDML / RDES Dosyası İçe Aktar",
        "rdml_description":     "Cq değerlerini otomatik doldurmak için **RDML** (`.rdml`) veya **RDES** (`.tsv`/`.csv`/`.txt`) dosyası yükleyin.",
        "rdml_uploader":        "Dosya seçin",
        "rdml_uploader_help":   "RDML: Bio-Rad CFX, Roche LightCycler vb.  RDES: sekmeyle ayrılmış tablo formatı.",
        "rdml_success":         "✅ {fmt} dosyası yüklendi — {n} reaksiyon bulundu.",
        "rdml_error":           "❌ {fmt} ayrıştırma hatası: {err}",
        "rdml_preview":         "Ayrıştırılan verileri önizle",
        "rdml_step1":           "**Adım 1 — Kontrol grubunu etiketleyin**",
        "rdml_ctrl_label":      "Kontrol örnek adı (virgülle ayrılmış alt dizeler)",
        "rdml_ctrl_help":       "Adı bu metni içeren tüm örnekler Kontrol grubu olarak işlenecektir.",
        "rdml_step2":           "**Adım 2 — Hasta gruplarını etiketleyin**",
        "rdml_n_pat":           "Hasta grubu sayısı",
        "rdml_pat_label":       "Hasta grubu {i} örnek adı (adları)",
        "rdml_pat_help":        "Virgülle ayrılmış alt dizeler. Eşleşen tüm örnekler bu gruba dahil edilir.",
        "rdml_apply":           "✅ {fmt} verilerini Veri Girişine Uygula",
        "rdml_apply_success":   "✅ {n} Cq değeri Veri Girişi sekmesine yüklendi! Kontrol edip ayarlayabilirsiniz.",
        "rdml_apply_warning":   "⚠️ Hiçbir değer eşleştirilemedi. Kontrol/hasta etiketlerinin yukarıdaki önizlemedeki örnek adlarıyla uyuştuğundan emin olun.",
    },

    "en": {
        "title": "🧬 GeneQuantify: Expression & CNV Analysis",
        "tab_data": "Data Entry",
        "tab_results": "Results",
        "tab_report": "Report",
        "subtitle": "Developed by B. Yalçınkaya",
        "patient_data_header": "📊 Enter Patient and Control Group Data",
        "num_target_genes": "🔹 Enter the Number of Target Genes",
        "num_patient_groups": "🔹 Enter the Number of Patient Groups",
        "sample_number": "Sample Number",
        "Grup": "Group",
        "x_axis_title": "Group Name",
        "ct_value": "Cq Value",
        "reference_ct": "Reference Cq",
        "delta_ct_control": "ΔCq (Control)",
        "delta_ct_patient": "ΔCq (Patient)",
        "warning_empty_input": "⚠️ Warning: Write data one below the other or copy-paste without empty cells from Excel.",
        "download_csv": "📥 Download CSV",
        "generate_pdf": "📥 Prepare PDF Report",
        "pdf_report": "Gene Expression Analysis Report",
        "nil_mine": "📊 Results",
        "gr_tbl": "📋 Input Data Table",
        "control_group": "🧬 Control Group",
        "ctrl_trgt_ct": "🟦 Control Group Target Gene {i} Cq Values",
        "ctrl_ref_ct": "🟦 Control Group Reference Gene {i} Cq Values",
        "hst_trgt_ct": "🩸 Patient Group Target Gene {j} Cq Values",
        "hst_ref_ct": "🩸 Patient Group Reference Gene {j} Cq Values",
        "warning_control_ct": "⚠️ Warning: Control Group {i} data should be entered line by line or copied from Excel without empty cells.",
        "warning_patient_cq": "⚠️ Warning: Enter patient group Cq values line by line or copy-paste from Excel without empty cells.",
        "target_gene": "Target Gene",
        "reference_gene": "Reference Gene",
        "target_ct": "Target Gene Cq", 
        "distribution_graph": "Distribution Graph",
        "error_missing_control_data": "⚠️ Error: Missing data for Target Gene {i} in the Control Group!",
        "control_group_avg": "Control Group Average",
        "avg": "Average",
        "control": "Control",
        "sample": "Sample",
        "patient": "Patient",
        "delta_ct_distribution": "ΔCq Distribution",
        "delta_ct_value": "ΔCq Value",
        "parametric": "Parametric",
        "non_parametric": "Nonparametric",
        "t_test": "t-test",
        "mann_whitney_u_test": "Mann-Whitney U test",
        "welch_t_test": "Welch t-test",
        "significant": "Significant",
        "insignificant": "Insignificant",
        "test_type": "Test Type",
        "test_method": "Test Method",
        "test_pvalue": "Test P-value",
        "significance": "Significance",
        "delta_delta_ct": "ΔΔCq",
        "gene_expression_change": "Gene Expression Change (2^(-ΔΔCq))",
        "regulation_status": "Regulation Status",
        "no_change": "No Change",
        "upregulated": "Upregulated",
        "downregulated": "Downregulated",
        "report_title": "Gene Expression Analysis Report",
        "input_data_table": "Input Data Table",
        "results": "Results",
        "statistical_results": "📈 Statistical Results",
        "statistics": "Statistical Results",
        "statistical_evaluation": "Statistical Evaluation",
        "target_gene": "Target Gene",
        "patient_group": "🩸 Patient Group",
        "expression_change": "Gene Expression Change",
        "generate_pdf": "Generate PDF",
        "pdf_report": "Gene Expression Report",
        "error_no_data": "No data found, PDF could not be generated.",
        # Efficiency translations
        "efficiency_header": "🔬 Amplification Efficiency Validation",
        "efficiency_method": "Efficiency Input Method",
        "efficiency_manual": "Enter E value manually",
        "efficiency_slope": "Calculate from slope",
        "efficiency_target_label": "Target Gene {i} Efficiency (E)",
        "efficiency_ref_label": "Reference Gene {i} Efficiency (E)",
        "efficiency_target_slope_label": "Target Gene {i} Slope",
        "efficiency_ref_slope_label": "Reference Gene {i} Slope",
        "efficiency_threshold": "Acceptable efficiency difference threshold (%)",
        "efficiency_ok": "✅ Efficiency difference is acceptable ({diff:.1f}%)",
        "efficiency_warning": "⚠️ Efficiency difference exceeds threshold ({diff:.1f}%) — ΔΔCq method may not be reliable!",
        "efficiency_target_pct": "Target Gene Efficiency",
        "efficiency_ref_pct": "Reference Gene Efficiency",
        "efficiency_diff": "Difference",
        "pfaffl_result": "Pfaffl Ratio",
        "pfaffl_header": "Pfaffl Method Results",
        "classic_ddct": "Classic ΔΔCq Result (2^(-ΔΔCq))",
        "pfaffl_ratio": "Pfaffl Ratio",
        "method_comparison": "📊 Method Comparison",
        "efficiency_note": "Note: E=2.0 represents perfect efficiency (100%). Accepted range: 1.8–2.2 (90–110%)",
        "statistical_explanation": (
            "During the statistical evaluation process, data distribution was analyzed using the Shapiro-Wilk test. "
            "If normality was met, variance homogeneity between groups was checked with Levene's test. "
            "If variance was equal, an independent sample t-test was applied; otherwise, a Welch t-test was used. "
            "If normal distribution was not achieved, the non-parametric Mann-Whitney U test was applied. "
            "Significance was determined using the p < 0.05 criterion. "
            "For suggestions and support, Burhanettin Yalçinkaya - email: [email removed]"
        ),
        "outlier_section_title": "### 🔍 Outlier Detection Settings",
        "outlier_enable": "Enable outlier detection",
        "outlier_enable_help": "Detects statistically extreme Cq values that may reflect technical errors.",
        "outlier_method_label": "Detection method",
        "outlier_method_help": "Grubbs: best for normally distributed data, detects one outlier at a time. IQR: non-parametric, robust for skewed distributions.",
        "outlier_alpha_label": "Significance level (α)",
        "outlier_alpha_help": "α = 0.05 is standard. Lower α = more conservative (fewer outliers flagged).",
        "outlier_iqr_label": "IQR multiplier (k)",
        "outlier_iqr_help": "k=1.5 = standard Tukey fences. k=3.0 = extreme outliers only.",
        "outlier_expander": "ℹ️ About outlier detection in qPCR",
        "grubbs_info": "ℹ️ **Grubbs' test requirements:** Minimum **n ≥ 3** replicates per group. Significance threshold: **α = {alpha:.2f}**. The test assumes normality; for n < 8, normality cannot be reliably assessed — results should be interpreted with caution. Applying the test on **raw Cq values** (before normalization) is recommended to prevent noisy replicates from propagating into the ΔCq calculation.",
        "outlier_excluded_no": "No",
        "outlier_excluded_yes": "Yes",
        # Outlier stage selector
        "outlier_stage_label": "🔬 Outlier Detection Stage",
        "outlier_stage_raw": "Raw Cq — before normalization (recommended)",
        "outlier_stage_dct": "ΔCq — after normalization (previous behaviour)",
        "outlier_stage_help": (
            "**Raw Cq (recommended):** Outliers are flagged on raw Ct values before ΔCq is computed. "
            "Applied separately to target and each reference gene. Prevents noisy replicates from "
            "propagating into the normalization step.\n\n"
            "**ΔCq:** Outliers are flagged after normalization (original behaviour)."
        ),
        # Distribution plot mode selector
        "dist_plot_mode_label": "📊 Distribution Plot — Display Mode",
        "dist_plot_rq":   "RQ (2^-ΔCq)  — recommended",
        "dist_plot_dct":  "ΔCq  — raw normalized values",
        "dist_plot_ddct": "ΔΔCq  — relative to control mean",
        "dist_plot_help": (
            "**RQ (recommended):** Converts ΔCq to 2^(-ΔCt). Higher value = higher expression. "
            "Avoids the counter-intuitive ΔCq paradox (high ΔCt = low expression).\n\n"
            "**ΔCq:** Raw normalized values on a log scale. Useful for checking data spread and normality.\n\n"
            "**ΔΔCq:** Each sample's ΔCq minus the control group mean ΔCt. "
            "Shows expression change relative to control on a log scale."
        ),
        "unequal_n_warning": (
            "⚠️ **Unequal replicate counts detected — {group}:**  \n"
            "{details}  \nAnalysis will proceed using the **shortest common length (n={min_n})**.  \n"
            "Please verify your input data — mismatched replicates may indicate a data entry error."
        ),
        # Sidebar
        "sidebar_load_example": "📂 Load Example Data",
        "sidebar_example_loaded": "✅ Example data loaded! Switch to Data Entry tab.",
        "sidebar_desktop_title": "### 💻 Desktop Application",
        "sidebar_desktop_btn": "⬇️ Download Desktop App",
        "sidebar_opensource_title": "### 🔓 Open Source",
        "sidebar_opensource_body": "GeneQuantify is open source (GPL-3.0).  \nSource code available on GitHub:",
        "sidebar_github_btn": "⭐ View Source on GitHub",
        "sidebar_scenarios_title": "📋 Load Validation Scenario",
        "sidebar_scenario_select": "Select scenario",
        "sidebar_load_scenario_btn": "▶ Load Scenario",
        "sidebar_scenario_loaded": "✅ {s} loaded! Switch to Data Entry tab.",
        "stat_decision_title": "🔬 Statistical decision",
        "stat_decision_steps": "**Step-by-step test selection:**",
        "stat_shapiro_title": "**1. Shapiro-Wilk normality test**",
        "stat_normal": "Normal",
        "stat_nonnormal": "Non-normal",
        "stat_levene_title": "**2. Levene variance homogeneity test**",
        "stat_levene_skipped": "**2. Levene test** — *skipped* (normality not met; non-parametric test will be used)",
        "stat_equal_var": "Equal variances",
        "stat_unequal_var": "Unequal variances",
        "stat_selected_test": "**3. Selected test:**",
        "stat_reason": "**Reason:**",
        "stat_result": "**Result:**",
        "stat_reason_nonnormal": "Non-normal distribution in one or both groups",
        "stat_reason_normal_equal": "Both groups normal + equal variances",
        "stat_reason_normal_unequal": "Both groups normal + unequal variances (Levene p < 0.05)",
        "stat_multigroup_note": "⚠️ Note: When ≥ 3 groups are present, see the **Multi-Group Comparison** section below for ANOVA / Kruskal-Wallis testing with post-hoc correction.",
        "multigroup_title": "## 📊 Multi-Group Comparison Analysis",
        "multigroup_expander": "ℹ️ About multi-group statistical analysis",
        "multigroup_omnibus_test": "Omnibus Test",
        "multigroup_pvalue": "p-value",
        "multigroup_result": "Result",
        "multigroup_significant": "Significant",
        "multigroup_not_significant": "Not significant",
        "multigroup_omnibus_ns": "ℹ️ Omnibus test is **not significant** (p ≥ 0.05). Post-hoc comparisons are shown for completeness but should be interpreted with caution — no overall group effect was detected.",
        "multigroup_posthoc_label": "**Post-hoc:**",
        "multigroup_dl_button": "📥 Download post-hoc results —",
        "multigroup_2group_note": "ℹ️ **Multi-group analysis not applicable:** Only 2 groups detected (Control + 1 patient group). Pairwise statistics are reported above.",
        "multigroup_decision_normal_equal": "✅ Normal distribution + equal variances → **One-way ANOVA + Tukey HSD**",
        "multigroup_decision_normal_unequal": "⚠️ Normal distribution + **unequal variances** → **Welch ANOVA + Games-Howell**",
        "multigroup_decision_nonnormal": "⚠️ **Non-normal distribution** → **Kruskal-Wallis + Dunn post-hoc**",
        "multigene_title": "### 🧬 Multi-Gene Multiple Comparison Correction",
        "multigene_expander": "ℹ️ Why is this needed?",
        "multigene_sig_raw": "Significant (raw)",
        "multigene_sig_bonf": "Significant (Bonferroni)",
        "multigene_sig_fdr": "Significant (FDR B-H)",
        "multigene_warning": "⚠️ After correction, {lost} result(s) that appeared significant at raw p < 0.05 are no longer significant after FDR adjustment. Report corrected p-values as primary results in multi-gene analyses.",
        "multigene_success": "✅ All {n} significant result(s) remain significant after FDR correction — findings are robust to multiple testing.",
        "multigene_no_sig": "No significant pairwise results detected (raw p < 0.05).",
        "multigene_dl_button": "📥 Download corrected p-values (CSV)",
        "multigene_chart_title": "Multi-Gene p-value Correction: Raw vs Bonferroni vs FDR",
        "multigene_fc_chart_title": "Multi-Gene Expression Comparison",
        "multigene_1gene_note": "ℹ️ **Multi-gene correction:** Only 1 target gene analysed — multiple comparison correction across genes is not applicable.",
        "multigene_no_data": "No p-values available yet — enter data above to calculate corrections.",
        "ref_gene_section_title": "### 📚 Reference Gene Settings",
        "ref_gene_num_label": "Number of reference genes per target gene",
        "ref_gene_num_help": "MIQE guidelines recommend ≥2 validated reference genes for robust normalization.",
        "ref_gene_1_warning": "⚠️ **Methodological note:** Using a single reference gene is a meaningful constraint on normalization robustness. MIQE guidelines (Bustin et al. 2009) recommend using **≥ 2 validated reference genes** and assessing their stability with tools such as geNorm or NormFinder.",
        "ref_gene_multi_success": "✅ {n} reference genes selected. Geometric mean normalization and geNorm M-value stability will be calculated automatically.",
        "ref_gene_expander": "ℹ️ About multi-reference normalization",
        "sc_expander": "📐 Standard Curve Calculator — Calculate E from dilution series",
        "sc_gene_label": "Gene / Primer label",
        "sc_num_points": "Number of dilution points",
        "sc_dilution_factor_label": "**Dilution factor** (e.g. 10 for 10-fold dilutions)",
        "sc_dilution_factor_input": "Dilution factor",
        "sc_start_conc_label": "**Starting concentration** (arbitrary units, e.g. 1)",
        "sc_start_conc_input": "Starting concentration",
        "sc_enter_ct": "**Enter mean Cq for each dilution:**",
        "sc_calc_button": "📊 Calculate Efficiency",
        "sc_slope": "Slope",
        "sc_e_value": "E value",
        "sc_efficiency_pct": "Efficiency %",
        "sc_excellent": "✅ Excellent! E={e:.4f} ({pct:.1f}%), R²={r2:.4f} — Use this E value in the efficiency section below.",
        "sc_warning_r2": "⚠️ E is acceptable ({pct:.1f}%) but R²={r2:.4f} is below 0.99 — check your dilution series.",
        "sc_error_range": "❌ E={e:.4f} ({pct:.1f}%) is outside acceptable range (90–110%). Review your primer design or dilution series.",
        "sc_chart_title": "Standard Curve — {label} | E={e:.4f} ({pct:.1f}%), R²={r2:.4f}",
        "sc_xaxis": "log₁₀(Concentration)",
        "sc_data_points": "Data points",
        "sc_copy_hint": "💡 Copy slope **{slope:.4f}** or E value **{e:.4f}** into the efficiency inputs below.",
        "sc_description": """\
Enter your serial dilution Ct values below. The calculator will fit a linear regression,
compute the slope, R², and amplification efficiency automatically.

**How to use:**  
1. Run qPCR on serial dilutions (e.g. undiluted, 1:10, 1:100, 1:1000, 1:10000)  
2. Enter the mean Ct for each dilution below  
3. Read off slope, E, and R²  
""",
        "ref_multi_description": """\
**Geometric mean normalization** (Vandesompele et al. 2002)  
The normalization factor (NF) is the arithmetic mean of Ct values across all reference genes per sample,
which corresponds to the geometric mean of their expression levels.  
`NF_sample = mean(Ct_ref1, Ct_ref2, ..., Ct_refN)` for each sample  
`ΔCq = Ct_target − NF`

**geNorm M-value** (stability score)  
For each reference gene, M = average standard deviation of log-ratios against all other reference genes.  
**Lower M = more stable.** MIQE-recommended threshold: M < 0.5 (strict) or M < 1.0 (acceptable).

**CV (Coefficient of Variation)**  
`CV = (SD / mean) × 100%` of raw Ct values across all samples.  
Lower CV indicates less variation and better stability as a reference.

**Reference:** Vandesompele J et al. *Genome Biology* 2002; Bustin SA et al. *Clin Chem* 2009 (MIQE).
""",
        "outlier_description": """\
**Why outlier detection matters in qPCR**

Technical variability is inherent to qPCR: pipetting errors, bubble formation, 
inhibitor carry-over, or RNA quality variation can produce Ct values that are 
statistically inconsistent with the rest of a replicate group. 
Including such values inflates variance, biases means, and can lead to false 
conclusions — particularly in clinical datasets with small sample sizes.

**When this limitation becomes critical:**
- Small groups (n < 5): a single erroneous Ct shifts the mean substantially
- High biological variability (e.g. tumour heterogeneity, clinical cohorts)
- Technical triplicates where one replicate diverges > 0.5 Ct from the others
- Low-abundance targets with Ct > 35, where noise dominates

**Grubbs test** *(Grubbs 1969)*  
Assumes normality. Tests whether the most extreme value is a statistically 
significant outlier (p < α). Iterates until no further outliers are found.  
Best for: replicate Ct values from a single experimental group.

**IQR method** *(Tukey 1977)*  
Non-parametric. Flags values outside Q1 − k×IQR or Q3 + k×IQR.  
Best for: larger groups or non-normal distributions.

**Important:** Outlier exclusion requires **biological or technical justification**. 
This tool flags candidates — the final decision always rests with the researcher.  
All exclusions are logged and reported in the PDF output.

**References:** Grubbs FE. *Technometrics* 1969; Tukey JW. *Exploratory Data Analysis* 1977;  
Bustin SA et al. *Clin Chem* 2009 (MIQE guidelines).
""",

        # ── PDF report strings ────────────────────────────────────────────────
        "pdf_cover_subtitle": "qPCR Gene Expression Analysis Report",
        "pdf_generated": "Generated: {now}",
        "pdf_s1_title": "1. Methods and Analysis Settings",
        "pdf_s1_calc": "1.1 Calculation Methods",
        "pdf_s1_calc_body": "Two complementary methods were applied for fold-change calculation:",
        "pdf_s1_classic": "Classic ΔΔCq (Livak & Schmittgen, 2001): ΔCq = Cq(target) - Cq(reference);  ΔΔCq = ΔCq(sample) - ΔCt(control);  Fold Change = 2^(-ΔΔCt). Assumes equal amplification efficiencies (E ≈ 2.0) for both genes.",
        "pdf_s1_pfaffl": "Pfaffl Method (Pfaffl, 2001): Ratio = (E_target ^ ΔCq_target) / (E_ref ^ ΔCt_ref). Corrects for primer-specific efficiencies; recommended when efficiency difference > 10%.",
        "pdf_s1_norm": "1.2 Normalization",
        "pdf_s1_norm_multi": "Multiple reference genes (n={n}) were used. Normalization factor (NF) was calculated as the arithmetic mean of reference gene Cq values per sample (geNorm approach, Vandesompele et al. 2002). geNorm M-values and CV% were computed.",
        "pdf_s1_norm_single": "A single reference gene was used. MIQE guidelines recommend ≥2 reference genes for robust normalization.",
        "pdf_s1_eff": "1.3 Amplification Efficiency",
        "pdf_s1_eff_range": "Acceptable efficiency range: E = 1.8-2.2 (90-110%). Efficiency difference threshold applied: {thr}%.",
        "pdf_s1_outlier": "1.4 Outlier Detection",
        "pdf_s1_grubbs": "Grubbs test (Grubbs 1969) applied at alpha = {alpha}. {n} sample(s) flagged and confirmed for exclusion by user.",
        "pdf_s1_iqr": "IQR method (Tukey 1977) applied with multiplier k = {k}. {n} sample(s) flagged and confirmed for exclusion by user.",
        "pdf_s1_outlier_warn": "WARNING: Outlier exclusion requires biological or technical justification. Excluded samples are flagged in the data table.",
        "pdf_s1_outlier_off": "Outlier detection was disabled for this analysis.",
        "pdf_s2_title": "2. Input Data",
        "pdf_s2_body": "Raw Cq values entered by the user, after outlier processing. Rows marked Yes in the Outlier Excluded column were removed from calculations.",
        "pdf_s3_title": "3. Gene Expression Results",
        "pdf_s3_body": "Fold change values calculated by both Classic ΔΔCq and Pfaffl methods. Fold change > 1 indicates higher expression in patient group relative to control.",
        "pdf_s4_title": "4. Statistical Analysis",
        "pdf_s4_body": "Statistical significance of gene expression differences between control and patient groups. All tests are performed on RQ values (2^-ΔCq) rather than raw ΔCt, because ΔCt is on a logarithmic scale and direct parametric testing on ΔCt underestimates biological variability. Test selection is automatic based on normality (Shapiro-Wilk) and variance homogeneity (Levene). Significance threshold: p < 0.05.",
        "pdf_s4_interp": "Interpretation of Statistical Tests",
        "pdf_s4_interp_body": "Student's t-test: Used when both groups are normal with equal variances. Welch's t-test: Used when groups are normal but variances differ. Mann-Whitney U: Non-parametric test when normality is violated. p < 0.05 = statistically significant differential expression.",
        "pdf_s5_title": "5. Relative Quantity (RQ) Distribution Plots",
        "pdf_s5_body": "RQ values (2^-ΔCq) per target gene across groups. Each dot = one biological replicate; horizontal bars = group means. Statistical tests are performed on RQ values, not raw ΔCt, to avoid underestimation of biological variability on the logarithmic scale.",
        "pdf_s6_title": "6. How to Interpret Your Results",
        "pdf_s6_fc": "6.1 Fold Change Interpretation",
        "pdf_s6_choose": "6.2 Choosing Between ΔΔCq and Pfaffl",
        "pdf_s6_choose_body": "Use Classic ΔΔCq when: both efficiencies are 90-110% and difference < 10%. Use Pfaffl when: efficiency difference > 10%. Always report both values.",
        "pdf_s6_stat": "6.3 Statistical Test Selection Rationale",
        "pdf_s6_stat_body": "Normality assessed using Shapiro-Wilk (recommended for n < 50). Variance homogeneity assessed using Levene's test. Parametric data with equal variances: Student's t-test. Unequal variances: Welch's t-test. Non-normal: Mann-Whitney U.",
        "pdf_s7_title": "7. References",
        "pdf_fc_interp_header": ["Fold Change", "ΔΔCq", "Interpretation", "Biological Significance"],
        "pdf_fc_interp_rows": [
            [">2.0", "<-1.0", "Strong upregulation", "Consider biologically relevant"],
            ["1.5-2.0", "-1.0 to -0.58", "Moderate upregulation", "May be relevant; verify"],
            ["1.0-1.5", "-0.58 to 0", "Weak upregulation", "Likely not significant alone"],
            ["1.0", "0", "No change", "No differential expression"],
            ["0.67-1.0", "0 to 0.58", "Weak downregulation", "Likely not significant alone"],
            ["0.5-0.67", "0.58 to 1.0", "Moderate downregulation", "May be relevant; verify"],
            ["<0.5", ">1.0", "Strong downregulation", "Consider biologically relevant"],
        ],
        "pdf_stat_note": "Note: Statistical significance (p < 0.05) and biological significance (fold change) should be considered together.",
        "pdf_summary_param": "Parameter",
        "pdf_summary_val": "Value",
        "pdf_summary_genes": "Target genes analyzed",
        "pdf_summary_groups": "Patient groups",
        "pdf_summary_samples": "Total samples (rows)",
        "pdf_summary_excluded": "Outlier-excluded samples",
        "pdf_summary_tests": "comparisons",
        "pdf_summary_norm": "Normalization method",
        "pdf_summary_norm_multi": "geNorm NF",
        "pdf_summary_norm_single": "Single reference gene",
        "pdf_summary_methods": "Calculation methods",
        "pdf_summary_methods_val": "Classic ΔΔCq + Pfaffl",
        "pdf_disclaimer": "This report was generated automatically by GeneQuantify. All calculations follow MIQE guidelines (Bustin et al., Clin Chem 2009).",
        "pdf_footer": "GeneQuantify — For research and educational use only. Not validated for clinical diagnostic purposes.",
        "pdf_fig1": "Figure 1. Fold change comparison: Classic ΔΔCq vs Pfaffl. Dashed line at y=1 = no change relative to control.",
        "pdf_fig2": "Figure 2. p-values for all comparisons. Red bars = significant (p < 0.05). Dashed line = significance threshold.",
        "pdf_fig3": "Figure. RQ (2^-ΔCq) distribution for {gene}. Points = individual replicates; horizontal bars = group means. Statistical tests performed on RQ values.",
        "pdf_nochange": "No Change",
        "pdf_stat_cols": ["Target Gene", "Comparison", "Test Type", "Test Method", "p-value", "Significance"],
        "pdf_res_cols": ["Target Gene", "Group", "ΔCq Control", "ΔCq Sample", "ΔΔCq", "2^(-ΔΔCq)", "Pfaffl Ratio", "Regulation", "E target", "E ref"],
        "pdf_eff_cols": ["Gene", "E (target)", "Eff% (target)", "E (ref)", "Eff% (ref)", "Diff%", "Status"],
        "pdf_eff_ok": "OK",
        "pdf_eff_warn": "WARNING: use Pfaffl",
        "pdf_outlier_col": "Outlier Excluded",
        "pdf_contact": "Contact: [email removed]",
        "pdf_ready": "{n} records ready — you can generate the PDF.",
        # RDML / RDES import
        "rdml_expander":        "📂 Import RDML / RDES File",
        "rdml_description":     "Upload an **RDML** (`.rdml`) or **RDES** (`.tsv`/`.csv`/`.txt`) file to auto-fill Cq values.",
        "rdml_uploader":        "Choose file",
        "rdml_uploader_help":   "RDML: Bio-Rad CFX, Roche LightCycler, etc.  RDES: tab-separated spreadsheet format.",
        "rdml_success":         "✅ {fmt} file loaded — {n} reactions found.",
        "rdml_error":           "❌ {fmt} parse error: {err}",
        "rdml_preview":         "Preview parsed data",
        "rdml_step1":           "**Step 1 — Label your Control group**",
        "rdml_ctrl_label":      "Control sample name(s) (comma-separated substrings)",
        "rdml_ctrl_help":       "Any sample whose name contains this text will be treated as Control.",
        "rdml_step2":           "**Step 2 — Label your Patient groups**",
        "rdml_n_pat":           "Number of patient groups",
        "rdml_pat_label":       "Patient group {i} sample name(s)",
        "rdml_pat_help":        "Comma-separated substrings. All matching samples will be pooled into this group.",
        "rdml_apply":           "✅ Apply {fmt} import to Data Entry",
        "rdml_apply_success":   "✅ {n} Cq values loaded into Data Entry tab! Switch to review and adjust.",
        "rdml_apply_warning":   "⚠️ No values were mapped. Check that your labels match the sample names in the preview above.",
    },

    "de": {
        "title": "🧬 GeneQuantify: Expressions- und CNV-Analyse",
        "tab_data": "Dateneingabe",
        "tab_results": "Ergebnisse",
        "tab_report": "Bericht",
        "subtitle": "Entwickelt von B. Yalçınkaya",
        "patient_data_header": "📊 Geben Sie Patientendaten und Kontrollgruppen ein",
        "num_target_genes": "🔹 Geben Sie die Anzahl der Zielgene ein",
        "num_patient_groups": "🔹 Geben Sie die Anzahl der Patientengruppen ein",
        "sample_number": "Beispielnummer",
        "Grup": "Gruppe",
        "x_axis_title": "Gruppenname",
        "ct_value": "Cq-Wert",
        "reference_ct": "Referenz Cq",
        "delta_ct_control": "ΔCq (Kontrolle)",
        "delta_ct_patient": "ΔCq (Patientendaten)",
        "warning_empty_input": "⚠️ Warnung: Geben Sie die Daten untereinander ein oder kopieren Sie sie ohne leere Zellen aus Excel.",
        "download_csv": "📥 CSV herunterladen",
        "generate_pdf": "📥 PDF-Bericht erstellen",
        "pdf_report": "Genexpression-Analysebericht",
        "nil_mine": "📊 Ergebnisse",
        "gr_tbl": "📋 Eingabedaten Tabelle",
        "control_group": "🧬 Kontrollgruppe",
        "ctrl_trgt_ct": "🟦 Kontrollgruppe Zielgen {i} Cq-Werte",
        "ctrl_ref_ct": "🟦 Kontrollgruppe Referenz {i} Ct-Werte",
        "hst_trgt_ct": "🩸 Patientengruppe Zielgen {j} Cq-Werte",
        "hst_ref_ct": "🩸 Patientengruppe Referenz {j} Ct-Werte",
        "warning_control_ct": "⚠️ Achtung: Kontrollgruppe {i} Daten sollten untereinander eingegeben oder aus Excel ohne leere Zellen eingefügt werden.",
        "warning_patient_cq": "⚠️ Achtung: Geben Sie die Cq-Werte der Patientengruppe untereinander ein oder kopieren Sie sie aus Excel ohne leere Zellen.",
        "target_gene": "Zielgen",
        "reference_gene": "Referenzgen",
        "target_ct": "Zielgen Cq",
        "distribution_graph": "Verteilungsdiagramm",
        "error_missing_control_data": "⚠️ Fehler: Fehlende Daten für Zielgen {i} in der Kontrollgruppe!",
        "control_group_avg": "Durchschnitt der Kontrollgruppe",
        "avg": "Durchschnitt",
        "control": "Kontrolle",
        "sample": "Probe",
        "patient": "Patient",
        "delta_ct_distribution": "ΔCq-Verteilung",
        "delta_ct_value": "ΔCq-Wert",
        "parametric": "Parametrisch",
        "non_parametric": "Nicht parametrisch",
        "t_test": "t-Test",
        "mann_whitney_u_test": "Mann-Whitney U-Test",
        "welch_t_test": "Welch t-Test",
        "significant": "Signifikant",
        "insignificant": "Nicht signifikant",
        "test_type": "Testtyp",
        "test_method": "Verwendeter Test",
        "test_pvalue": "P-Wert",
        "significance": "Signifikanz",
        "delta_delta_ct": "ΔΔCq",
        "gene_expression_change": "Genexpression Veränderung (2^(-ΔΔCq))",
        "regulation_status": "Regulierungsstatus",
        "no_change": "Keine Veränderung",
        "upregulated": "Hochreguliert",
        "downregulated": "Herunterreguliert",
        "report_title": "Genexpressionsanalysebericht",
        "input_data_table": "Eingabedatentabelle",
        "results": "Ergebnisse",
        "statistical_results": "📈 Statistische Ergebnisse",
        "statistics": "Statistische Ergebnisse",
        "statistical_evaluation": "Statistische Auswertung",
        "target_gene": "Zielgen",
        "patient_group": "🩸 Patientengruppe",
        "expression_change": "Genexpressionsänderung",
        "generate_pdf": "PDF Erstellen",
        "pdf_report": "Genexpressionsbericht",
        "error_no_data": "Keine Daten gefunden, PDF konnte nicht erstellt werden.",
        # Efficiency translations
        "efficiency_header": "🔬 Amplifikationseffizienz-Validierung",
        "efficiency_method": "Effizienzeingabemethode",
        "efficiency_manual": "E-Wert manuell eingeben",
        "efficiency_slope": "Aus Steigung berechnen",
        "efficiency_target_label": "Zielgen {i} Effizienz (E)",
        "efficiency_ref_label": "Referenzgen {i} Effizienz (E)",
        "efficiency_target_slope_label": "Zielgen {i} Steigung",
        "efficiency_ref_slope_label": "Referenzgen {i} Steigung",
        "efficiency_threshold": "Akzeptable Effizienzdifferenz-Schwelle (%)",
        "efficiency_ok": "✅ Effizienzdifferenz ist akzeptabel ({diff:.1f}%)",
        "efficiency_warning": "⚠️ Effizienzdifferenz überschreitet Schwelle ({diff:.1f}%) — ΔΔCq-Methode möglicherweise nicht zuverlässig!",
        "efficiency_target_pct": "Zielgen-Effizienz",
        "efficiency_ref_pct": "Referenzgen-Effizienz",
        "efficiency_diff": "Differenz",
        "pfaffl_result": "Pfaffl-Verhältnis",
        "pfaffl_header": "Pfaffl-Methode Ergebnisse",
        "classic_ddct": "Klassisches ΔΔCq-Ergebnis (2^(-ΔΔCq))",
        "pfaffl_ratio": "Pfaffl-Verhältnis",
        "method_comparison": "📊 Methodenvergleich",
        "efficiency_note": "Hinweis: E=2.0 steht für perfekte Effizienz (100%). Akzeptierter Bereich: 1.8–2.2 (90–110%)",
        "statistical_explanation": (
            "Während des statistischen Bewertungsprozesses wurde die Datenverteilung mit dem Shapiro-Wilk-Test analysiert. "
            "Wenn die Normalität erfüllt war, wurde die Varianzhomogenität zwischen den Gruppen mit dem Levene-Test überprüft. "
            "War die Varianz gleich, wurde ein unabhängiger Stichprobent-Test angewendet; andernfalls wurde ein Welch-T-Test verwendet. "
            "Wenn keine normale Verteilung vorlag, wurde der nicht-parametrische Mann-Whitney-U-Test angewendet. "
            "Die Signifikanz wurde anhand des Kriteriums p < 0,05 bestimmt. "
            "Für Vorschläge und Unterstützung, Burhanettin Yalçinkaya - E-Mail: [email removed]"
        ),
        "outlier_section_title": "### 🔍 Ausreißer-Erkennungseinstellungen",
        "outlier_enable": "Ausreißererkennung aktivieren",
        "outlier_enable_help": "Erkennt statistisch extreme Cq-Werte, die auf technische Fehler hinweisen können.",
        "outlier_method_label": "Erkennungsmethode",
        "outlier_method_help": "Grubbs: für normalverteilte Daten. IQR: nicht-parametrisch, robust bei schiefen Verteilungen.",
        "outlier_alpha_label": "Signifikanzniveau (α)",
        "outlier_alpha_help": "α = 0,05 ist Standard. Niedrigeres α = konservativer.",
        "outlier_iqr_label": "IQR-Multiplikator (k)",
        "outlier_iqr_help": "k=1,5 = Standard Tukey-Grenzen. k=3,0 = nur extreme Ausreißer.",
        "outlier_expander": "ℹ️ Über Ausreißererkennung in qPCR",
        "grubbs_info": "ℹ️ **Grubbs-Test-Anforderungen:** Mindestens **n ≥ 3** Replikate pro Gruppe. Signifikanzschwelle: **α = {alpha:.2f}**. Der Test setzt Normalverteilung voraus; bei n < 8 kann Normalität nicht zuverlässig geprüft werden. Die Anwendung auf **rohe Cq-Werte** (vor Normalisierung) wird empfohlen.",
        "outlier_excluded_no": "Nein",
        "outlier_excluded_yes": "Ja",
        # Outlier stage selector
        "outlier_stage_label": "🔬 Ausreißererkennung — Analysestufe",
        "outlier_stage_raw": "Roh-Cq — vor Normalisierung (empfohlen)",
        "outlier_stage_dct": "ΔCq — nach Normalisierung (bisheriges Verhalten)",
        "outlier_stage_help": (
            "**Roh-Ct (empfohlen):** Ausreißer werden vor der ΔCq-Berechnung erkannt. "
            "Für Zielgen und jedes Referenzgen separat angewendet.\n\n"
            "**ΔCq:** Ausreißer werden nach der Normalisierung erkannt (bisheriges Verhalten)."
        ),
        # Distribution plot mode selector
        "dist_plot_mode_label": "📊 Verteilungsdiagramm — Anzeigemodus",
        "dist_plot_rq":   "RQ (2^-ΔCq)  — empfohlen",
        "dist_plot_dct":  "ΔCq  — rohe normalisierte Werte",
        "dist_plot_ddct": "ΔΔCq  — relativ zum Kontrollmittelwert",
        "dist_plot_help": (
            "**RQ (empfohlen):** Konvertiert ΔCq zu 2^(-ΔCt). Höherer Wert = höhere Expression.\n\n"
            "**ΔCq:** Rohe logarithmische Werte. Nützlich zur Überprüfung der Datenverteilung.\n\n"
            "**ΔΔCq:** ΔCq jeder Probe minus dem Kontrollgruppenmittelwert."
        ),
        "unequal_n_warning": (
            "⚠️ **Ungleiche Replikatanzahl erkannt — {group}:**  \n"
            "{details}  \nAnalyse wird mit der **kürzesten gemeinsamen Länge (n={min_n})** fortgesetzt.  \n"
            "Bitte überprüfen Sie Ihre Eingabedaten."
        ),
        # Sidebar
        "sidebar_load_example": "📂 Beispieldaten laden",
        "sidebar_example_loaded": "✅ Beispieldaten geladen! Wechseln Sie zur Dateneingabe-Registerkarte.",
        "sidebar_desktop_title": "### 💻 Desktop-Anwendung",
        "sidebar_desktop_btn": "⬇️ Desktop-App herunterladen",
        "sidebar_opensource_title": "### 🔓 Open Source",
        "sidebar_opensource_body": "GeneQuantify ist Open Source (GPL-3.0).  \nQuellcode auf GitHub verfügbar:",
        "sidebar_github_btn": "⭐ Quellcode auf GitHub ansehen",
        "sidebar_scenarios_title": "📋 Validierungsszenario laden",
        "sidebar_scenario_select": "Szenario auswählen",
        "sidebar_load_scenario_btn": "▶ Szenario laden",
        "sidebar_scenario_loaded": "✅ {s} geladen! Zur Dateneingabe wechseln.",
        "outlier_excluded_no": "Nein",
        "outlier_excluded_yes": "Ja",
        "stat_decision_title": "🔬 Statistische Entscheidung",
        "stat_decision_steps": "**Schrittweise Testauswahl:**",
        "stat_shapiro_title": "**1. Shapiro-Wilk-Normalitätstest**",
        "stat_normal": "Normal",
        "stat_nonnormal": "Nicht normal",
        "stat_levene_title": "**2. Levene-Varianzhomogeintätstest**",
        "stat_levene_skipped": "**2. Levene-Test** — *übersprungen* (Normalität nicht erfüllt; nicht-parametrischer Test wird verwendet)",
        "stat_equal_var": "Gleiche Varianzen",
        "stat_unequal_var": "Ungleiche Varianzen",
        "stat_selected_test": "**3. Ausgewählter Test:**",
        "stat_reason": "**Grund:**",
        "stat_result": "**Ergebnis:**",
        "stat_reason_nonnormal": "Nicht-normale Verteilung in einer oder beiden Gruppen",
        "stat_reason_normal_equal": "Beide Gruppen normal + gleiche Varianzen",
        "stat_reason_normal_unequal": "Beide Gruppen normal + ungleiche Varianzen (Levene p < 0,05)",
        "stat_multigroup_note": "⚠️ Hinweis: Bei ≥ 3 Gruppen siehe Abschnitt **Mehrgruppen-Vergleich** unten für ANOVA / Kruskal-Wallis.",
        "multigroup_title": "## 📊 Mehrgruppen-Vergleichsanalyse",
        "multigroup_expander": "ℹ️ Über die Mehrgruppen-Statistikanalyse",
        "multigroup_omnibus_test": "Omnibus-Test",
        "multigroup_pvalue": "p-Wert",
        "multigroup_result": "Ergebnis",
        "multigroup_significant": "Signifikant",
        "multigroup_not_significant": "Nicht signifikant",
        "multigroup_omnibus_ns": "ℹ️ Omnibus-Test ist **nicht signifikant** (p ≥ 0,05). Post-hoc-Vergleiche werden zur Information angezeigt.",
        "multigroup_posthoc_label": "**Post-hoc:**",
        "multigroup_dl_button": "📥 Post-hoc-Ergebnisse herunterladen —",
        "multigroup_2group_note": "ℹ️ **Mehrgruppen-Analyse nicht anwendbar:** Nur 2 Gruppen erkannt (Kontrolle + 1 Patientengruppe).",
        "multigroup_decision_normal_equal": "✅ Normalverteilung + gleiche Varianzen → **Einfaktorielle ANOVA + Tukey HSD**",
        "multigroup_decision_normal_unequal": "⚠️ Normalverteilung + **ungleiche Varianzen** → **Welch-ANOVA + Games-Howell**",
        "multigroup_decision_nonnormal": "⚠️ **Keine Normalverteilung** → **Kruskal-Wallis + Dunn post-hoc**",
        "multigene_title": "### 🧬 Mehrgen-Mehrfachvergleichskorrektur",
        "multigene_expander": "ℹ️ Warum ist das notwendig?",
        "multigene_sig_raw": "Signifikant (roh)",
        "multigene_sig_bonf": "Signifikant (Bonferroni)",
        "multigene_sig_fdr": "Signifikant (FDR B-H)",
        "multigene_warning": "⚠️ Nach Korrektur sind {lost} Ergebnis(se) nach FDR-Anpassung nicht mehr signifikant. Korrigierte p-Werte als Hauptergebnisse berichten.",
        "multigene_success": "✅ Alle {n} signifikanten Ergebnis(se) bleiben nach FDR-Korrektur signifikant.",
        "multigene_no_sig": "Keine signifikanten paarweisen Ergebnisse erkannt (roh p < 0,05).",
        "multigene_dl_button": "📥 Korrigierte p-Werte herunterladen (CSV)",
        "multigene_chart_title": "Mehrgen p-Wert-Korrektur: Roh / Bonferroni / FDR",
        "multigene_fc_chart_title": "Mehrgen-Expressionsvergleich",
        "multigene_1gene_note": "ℹ️ **Mehrgen-Korrektur:** Nur 1 Zielgen analysiert — Mehrfachvergleichskorrektur nicht anwendbar.",
        "multigene_no_data": "Noch keine p-Werte — oben Daten eingeben.",
        "ref_gene_section_title": "### 📚 Referenzgen-Einstellungen",
        "ref_gene_num_label": "Anzahl der Referenzgene pro Zielgen",
        "ref_gene_num_help": "MIQE-Richtlinien empfehlen ≥2 validierte Referenzgene für eine robuste Normalisierung.",
        "ref_gene_1_warning": "⚠️ **Methodischer Hinweis:** Die Verwendung eines einzigen Referenzgens schränkt die Normalisierungsrobustheit ein. MIQE-Richtlinien (Bustin et al. 2009) empfehlen **≥2 validierte Referenzgene** und Stabilitätsbewertung (geNorm/NormFinder).",
        "ref_gene_multi_success": "✅ {n} Referenzgene ausgewählt. Geometrische Mittelnormalisierung und geNorm M-Wert-Stabilität werden automatisch berechnet.",
        "ref_gene_expander": "ℹ️ Über die Mehrfach-Referenznormalisierung",
        "sc_expander": "📐 Standardkurven-Rechner — E aus Verdünnungsreihe berechnen",
        "sc_gene_label": "Gen / Primer-Bezeichnung",
        "sc_num_points": "Anzahl der Verdünnungspunkte",
        "sc_dilution_factor_label": "**Verdünnungsfaktor** (z.B. 10 für 10-fache Verdünnung)",
        "sc_dilution_factor_input": "Verdünnungsfaktor",
        "sc_start_conc_label": "**Ausgangskonzentration** (beliebige Einheiten, z.B. 1)",
        "sc_start_conc_input": "Ausgangskonzentration",
        "sc_enter_ct": "**Mittleren Cq-Wert für jede Verdünnung eingeben:**",
        "sc_calc_button": "📊 Effizienz berechnen",
        "sc_slope": "Steigung",
        "sc_e_value": "E-Wert",
        "sc_efficiency_pct": "Effizienz %",
        "sc_excellent": "✅ Ausgezeichnet! E={e:.4f} ({pct:.1f}%), R²={r2:.4f} — Diesen E-Wert im Effizienzabschnitt unten verwenden.",
        "sc_warning_r2": "⚠️ E ist akzeptabel ({pct:.1f}%), aber R²={r2:.4f} < 0,99 — Verdünnungsreihe überprüfen.",
        "sc_error_range": "❌ E={e:.4f} ({pct:.1f}%) liegt außerhalb des akzeptablen Bereichs (90–110%). Primerdesign oder Verdünnungsreihe überprüfen.",
        "sc_chart_title": "Standardkurve — {label} | E={e:.4f} ({pct:.1f}%), R²={r2:.4f}",
        "sc_xaxis": "log₁₀(Konzentration)",
        "sc_data_points": "Datenpunkte",
        "sc_copy_hint": "💡 Steigung **{slope:.4f}** oder E-Wert **{e:.4f}** in die Effizienz-Eingaben unten kopieren.",
        "sc_description": """\
Geben Sie die Ct-Werte Ihrer seriellen Verdünnung unten ein. Der Rechner passt eine lineare Regression an und berechnet Steigung, R² und Amplifikationseffizienz automatisch.

**Verwendung:**  
1. Führen Sie qPCR auf seriellen Verdünnungen durch (z.B. unverdünnt, 1:10, 1:100, 1:1000, 1:10000)  
2. Geben Sie den mittleren Ct-Wert für jede Verdünnung ein  
3. Lesen Sie Steigung, E und R² ab  
""",
        "ref_multi_description": """\
**Geometrische Mittelnormalisierung** (Vandesompele et al. 2002)  
Der Normalisierungsfaktor (NF) ist das arithmetische Mittel der Ct-Werte über alle Referenzgene pro Probe,  
was dem geometrischen Mittel ihrer Expressionsniveaus entspricht.  
`NF_Probe = Mittel(Ct_ref1, Ct_ref2, ..., Ct_refN)` für jede Probe  
`ΔCq = Ct_Ziel − NF`

**geNorm M-Wert** (Stabilitätsscore)  
Für jedes Referenzgen ist M die durchschnittliche Standardabweichung der Log-Verhältnisse gegenüber allen anderen Referenzgenen.  
**Niedrigerer M = stabiler.** MIQE-empfohlener Schwellenwert: M < 0,5 (streng) oder M < 1,0 (akzeptabel).

**CV (Variationskoeffizient)**  
`CV = (SD / Mittel) × 100%` der rohen Ct-Werte über alle Proben.  
Niedrigerer CV weist auf weniger Variation und bessere Stabilität als Referenz hin.

**Referenz:** Vandesompele J et al. *Genome Biology* 2002; Bustin SA et al. *Clin Chem* 2009 (MIQE).
""",
        "outlier_description": """\
**Warum Ausreißererkennung in qPCR wichtig ist**

Technische Variabilität ist qPCR inhärent: Pipettierfehler, Blasenbildung, Inhibitor-Verschleppung oder RNA-Qualitätsschwankungen können Ct-Werte erzeugen, die statistisch inkonsistent mit dem Rest einer Replikatgruppe sind.  
Das Einschließen solcher Werte erhöht die Varianz, verzerrt Mittelwerte und kann zu falschen Schlussfolgerungen führen — besonders in klinischen Datensätzen mit kleinen Stichprobengrößen.

**Wann diese Einschränkung kritisch wird:**
- Kleine Gruppen (n < 5): ein einziger fehlerhafter Ct verschiebt den Mittelwert erheblich
- Hohe biologische Variabilität (z.B. Tumorheterogenität, klinische Kohorten)
- Technische Triplikate, bei denen ein Replikat > 0,5 Ct von den anderen abweicht
- Targets mit geringer Abundanz mit Ct > 35, wo Rauschen dominiert

**Grubbs-Test** *(Grubbs 1969)*  
Setzt Normalverteilung voraus. Testet, ob der extremste Wert ein statistisch signifikanter Ausreißer ist (p < α). Iteriert, bis keine weiteren Ausreißer gefunden werden.  
Am besten für: Replikat-Ct-Werte aus einer einzelnen experimentellen Gruppe.

**IQR-Methode** *(Tukey 1977)*  
Nicht-parametrisch. Markiert Werte außerhalb Q1 − k×IQR oder Q3 + k×IQR.  
Am besten für: größere Gruppen oder nicht-normale Verteilungen.

**Wichtig:** Ausreißerausschluss erfordert **biologische oder technische Begründung**.  
Dieses Tool markiert Kandidaten — die endgültige Entscheidung liegt immer beim Forscher.  
Alle Ausschlüsse werden protokolliert und im PDF-Bericht gemeldet.

**Referenzen:** Grubbs FE. *Technometrics* 1969; Tukey JW. *Exploratory Data Analysis* 1977;  
Bustin SA et al. *Clin Chem* 2009 (MIQE-Richtlinien).
""",

        # ── PDF-Berichtsstrings ───────────────────────────────────────────────
        "pdf_cover_subtitle": "qPCR-Genexpressionsanalysebericht",
        "pdf_generated": "Erstellt: {now}",
        "pdf_s1_title": "1. Methoden und Analyseeinstellungen",
        "pdf_s1_calc": "1.1 Berechnungsmethoden",
        "pdf_s1_calc_body": "Zwei komplementäre Methoden zur Berechnung des Fold-Change:",
        "pdf_s1_classic": "Klassische ΔΔCq-Methode (Livak & Schmittgen, 2001): Fold-Change = 2^(-ΔΔCq). Gleiche Effizienz vorausgesetzt.",
        "pdf_s1_pfaffl": "Pfaffl-Methode (Pfaffl, 2001): Verhältnis = (E_Ziel ^ ΔCq_Ziel) / (E_Ref ^ ΔCt_Ref). Empfohlen bei Effizienzunterschied > 10%.",
        "pdf_s1_norm": "1.2 Normalisierung",
        "pdf_s1_norm_multi": "Mehrere Referenzgene (n={n}) verwendet (geNorm, Vandesompele et al. 2002).",
        "pdf_s1_norm_single": "Ein Referenzgen verwendet. MIQE empfiehlt ≥2 Referenzgene.",
        "pdf_s1_eff": "1.3 Amplifikationseffizienz",
        "pdf_s1_eff_range": "Akzeptabler Effizienzbereich: E = 1,8-2,2 (90-110%). Schwellenwert: {thr}%.",
        "pdf_s1_outlier": "1.4 Ausreißererkennung",
        "pdf_s1_grubbs": "Grubbs-Test (1969), Alpha = {alpha}. {n} Probe(n) ausgeschlossen.",
        "pdf_s1_iqr": "IQR-Methode (Tukey 1977), k = {k}. {n} Probe(n) ausgeschlossen.",
        "pdf_s1_outlier_warn": "WARNUNG: Ausreißerausschluss erfordert biologische oder technische Begründung.",
        "pdf_s1_outlier_off": "Ausreißererkennung deaktiviert.",
        "pdf_s2_title": "2. Eingabedaten",
        "pdf_s2_body": "Roh-Cq-Werte nach der Ausreißerverarbeitung.",
        "pdf_s3_title": "3. Genexpressionsergebnisse",
        "pdf_s3_body": "Fold-Change berechnet mit Klassischer ΔΔCq- und Pfaffl-Methode.",
        "pdf_s4_title": "4. Statistische Analyse",
        "pdf_s4_body": "Statistische Signifikanz. Testauswahl automatisch (Shapiro-Wilk, Levene). p < 0,05.",
        "pdf_s4_interp": "Interpretation der Tests",
        "pdf_s4_interp_body": "Student-t: Normalverteilung, gleiche Varianzen. Welch-t: ungleiche Varianzen. Mann-Whitney U: nicht-normal.",
        "pdf_s5_title": "5. Delta-Cq-Verteilungsdiagramme",
        "pdf_s5_body": "ΔCq-Verteilung je Zielgen. Punkte = Replikate; Balken = Mittelwerte.",
        "pdf_s6_title": "6. Interpretation",
        "pdf_s6_fc": "6.1 Fold-Change-Interpretation",
        "pdf_s6_choose": "6.2 ΔΔCq vs. Pfaffl",
        "pdf_s6_choose_body": "ΔΔCq wenn Effizienzen 90-110% und Unterschied < 10%. Pfaffl wenn > 10%.",
        "pdf_s6_stat": "6.3 Testauswahl-Begründung",
        "pdf_s6_stat_body": "Normalität: Shapiro-Wilk. Varianzhomogenität: Levene. Student/Welch/Mann-Whitney je nach Ergebnis.",
        "pdf_s7_title": "7. Referenzen",
        "pdf_fc_interp_header": ["Fold-Change", "ΔΔCq", "Interpretation", "Biologische Bedeutung"],
        "pdf_fc_interp_rows": [
            [">2,0", "<-1,0", "Starke Hochregulation", "Biologisch relevant"],
            ["1,5-2,0", "-1,0 bis -0,58", "Mäßige Hochregulation", "Möglicherweise relevant"],
            ["1,0-1,5", "-0,58 bis 0", "Schwache Hochregulation", "Wahrscheinlich nicht signifikant"],
            ["1,0", "0", "Keine Änderung", "Keine differentielle Expression"],
            ["0,67-1,0", "0 bis 0,58", "Schwache Herunterregulation", "Wahrscheinlich nicht signifikant"],
            ["0,5-0,67", "0,58 bis 1,0", "Mäßige Herunterregulation", "Möglicherweise relevant"],
            ["<0,5", ">1,0", "Starke Herunterregulation", "Biologisch relevant"],
        ],
        "pdf_stat_note": "Hinweis: Statistische und biologische Signifikanz gemeinsam bewerten.",
        "pdf_summary_param": "Parameter", "pdf_summary_val": "Wert",
        "pdf_summary_genes": "Analysierte Zielgene", "pdf_summary_groups": "Patientengruppen",
        "pdf_summary_samples": "Proben gesamt", "pdf_summary_excluded": "Ausgeschlossene Ausreißer",
        "pdf_summary_tests": "Vergleiche", "pdf_summary_norm": "Normalisierungsmethode",
        "pdf_summary_norm_multi": "geNorm NF", "pdf_summary_norm_single": "Einzelnes Referenzgen",
        "pdf_summary_methods": "Berechnungsmethoden", "pdf_summary_methods_val": "Klassische ΔΔCq + Pfaffl",
        "pdf_disclaimer": "Dieser Bericht wurde automatisch von GeneQuantify erstellt (MIQE-Richtlinien).",
        "pdf_footer": "GeneQuantify — Nur für Forschung und Bildung. Nicht für klinische Diagnostik.",
        "pdf_fig1": "Abbildung 1. Fold-Change: Klassisches ΔΔCq vs. Pfaffl. Linie y=1 = keine Änderung.",
        "pdf_fig2": "Abbildung 2. p-Werte. Rote Balken = signifikant (p < 0,05).",
        "pdf_fig3": "Abbildung. ΔCq-Verteilung für {gene}.",
        "pdf_nochange": "Keine Änderung",
        "pdf_stat_cols": ["Zielgen", "Vergleich", "Testtyp", "Testmethode", "p-Wert", "Signifikanz"],
        "pdf_res_cols": ["Zielgen", "Gruppe", "ΔCq Kontrolle", "ΔCq Probe", "ΔΔCq", "2^(-ΔΔCq)", "Pfaffl-Verhältnis", "Regulation", "E Ziel", "E Ref"],
        "pdf_eff_cols": ["Gen", "E (Ziel)", "Eff% (Ziel)", "E (Ref)", "Eff% (Ref)", "Diff%", "Status"],
        "pdf_eff_ok": "OK", "pdf_eff_warn": "WARNUNG: Pfaffl verwenden",
        "pdf_outlier_col": "Ausreißer ausgeschlossen", "pdf_contact": "Kontakt: [email removed]",
        "pdf_ready": "{n} Einträge bereit — Sie können das PDF erstellen.",
        # RDML / RDES import
        "rdml_expander":        "📂 RDML / RDES-Datei importieren",
        "rdml_description":     "Laden Sie eine **RDML** (`.rdml`) oder **RDES** (`.tsv`/`.csv`/`.txt`) Datei hoch, um Cq-Werte automatisch einzufügen.",
        "rdml_uploader":        "Datei auswählen",
        "rdml_uploader_help":   "RDML: Bio-Rad CFX, Roche LightCycler usw.  RDES: tabulatorgetrennte Tabellenkalkulation.",
        "rdml_success":         "✅ {fmt}-Datei geladen — {n} Reaktionen gefunden.",
        "rdml_error":           "❌ {fmt}-Fehler: {err}",
        "rdml_preview":         "Geparste Daten anzeigen",
        "rdml_step1":           "**Schritt 1 — Kontrollgruppe bezeichnen**",
        "rdml_ctrl_label":      "Kontrollprobenname(n) (kommagetrennte Teilstrings)",
        "rdml_ctrl_help":       "Alle Proben, deren Name diesen Text enthält, werden als Kontrolle behandelt.",
        "rdml_step2":           "**Schritt 2 — Patientengruppen bezeichnen**",
        "rdml_n_pat":           "Anzahl der Patientengruppen",
        "rdml_pat_label":       "Patientengruppe {i} Probenname(n)",
        "rdml_pat_help":        "Kommagetrennte Teilstrings. Alle passenden Proben werden in diese Gruppe zusammengeführt.",
        "rdml_apply":           "✅ {fmt}-Import auf Dateneingabe anwenden",
        "rdml_apply_success":   "✅ {n} Cq-Werte in den Dateneingabe-Tab geladen! Wechseln Sie dorthin zum Überprüfen.",
        "rdml_apply_warning":   "⚠️ Keine Werte zugeordnet. Prüfen Sie, ob Ihre Bezeichnungen mit den Probennamen in der Vorschau übereinstimmen.",
    },

    "fr": {
        "title": "🧬 GeneQuantify : Analyse de l'expression génique et des variations du nombre de copies (CNV)",
        "tab_data": "Saisie des données",
        "tab_results": "Résultats",
        "tab_report": "Rapport",
        "subtitle": "Développé par B. Yalçınkaya",
        "patient_data_header": "📊 Entrez les données des groupes patients et témoins",
        "num_target_genes": "🔹 Entrez le nombre de gènes cibles",
        "num_patient_groups": "🔹 Entrez le nombre de groupes de patients",
        "sample_number": "Numéro de l'échantillon",
        "Grup": "Groupe",
        "x_axis_title": "Nom du Groupe",
        "ct_value": "Valeur Cq",
        "reference_ct": "Cq de Référence",
        "delta_ct_control": "ΔCq (Contrôle)",
        "delta_ct_patient": "ΔCq (Patient)",
        "warning_empty_input": "⚠️ Avertissement : Entrez les données sous forme de liste ou copiez-collez sans cellules vides depuis Excel.",
        "download_csv": "📥 Télécharger CSV",
        "generate_pdf": "📥 Préparer le Rapport PDF",
        "pdf_report": "Rapport d'Analyse de l'Expression Génétique",
        "nil_mine": "📊 Résultats",
        "gr_tbl": "📋 Tableau des Données d'Entrée",
        "control_group": "🧬 Groupe Contrôle",
        "ctrl_trgt_ct": "🟦 Valeurs Cq du Gène Cible {i} pour le Groupe Contrôle",
        "ctrl_ref_ct": "🟦 Valeurs Ct du Gène Référence {i} pour le Groupe Contrôle",
        "hst_trgt_ct": "🩸 Valeurs Cq du Gène Cible {j} pour le Groupe Patient",
        "hst_ref_ct": "🩸 Valeurs Ct du Gène Référence {j} pour le Groupe Patient",
        "warning_control_ct": "⚠️ Avertissement : Les données du groupe témoin {i} doivent être saisies ligne par ligne ou copiées depuis Excel sans cellules vides.",
        "warning_patient_cq": "⚠️ Avertissement : Entrez les valeurs Cq du groupe patient ligne par ligne ou copiez-les depuis Excel sans cellules vides.",
        "target_gene": "Gène Cible",
        "reference_gene": "Gène Référence",
        "target_ct": "Cq du Gène Cible", 
        "distribution_graph": "Graphique de Distribution",
        "error_missing_control_data": "⚠️ Erreur : Données manquantes pour le Gène Cible {i} dans le Groupe Contrôle!",
        "control_group_avg": "Moyenne du Groupe Contrôle",
        "avg": "Moyenne",
        "control": "Contrôle",
        "sample": "Échantillon",
        "patient": "Patient",
        "delta_ct_distribution": "Distribution ΔCq",
        "delta_ct_value": "Valeur ΔCq",
        "parametric": "Paramétrique",
        "non_parametric": "Non paramétrique",
        "t_test": "Test t",
        "mann_whitney_u_test": "Test Mann-Whitney U",
        "welch_t_test": "Test t de Welch",
        "significant": "Significatif",
        "insignificant": "Non Significatif",
        "test_type": "Type de Test",
        "test_method": "Méthode de Test",
        "test_pvalue": "P-valeur du Test",
        "significance": "Signification",
        "delta_delta_ct": "ΔΔCq",
        "gene_expression_change": "Changement de l'Expression Génétique (2^(-ΔΔCq))",
        "regulation_status": "Statut de Régulation",
        "no_change": "Aucun Changement",
        "upregulated": "Upregulé",
        "downregulated": "Downregulé",
        "report_title": "Rapport d'Analyse de l'Expression Génétique",
        "input_data_table": "Tableau des Données d'Entrée",
        "results": "Résultats",
        "statistical_results": "📈 Résultats Statistiques",
        "statistics": "Résultats statistiques",
        "statistical_evaluation": "Évaluation Statistique",
        "target_gene": "Gène Cible",
        "patient_group": "🩸 Groupe Patient",
        "expression_change": "Changement de l'Expression Génétique",
        "generate_pdf": "Générer le PDF",
        "pdf_report": "Rapport sur l'Expression Génétique",
        "error_no_data": "Aucune donnée trouvée, le PDF n'a pas pu être généré.",
        # Efficiency translations
        "efficiency_header": "🔬 Validation de l'Efficacité d'Amplification",
        "efficiency_method": "Méthode de saisie d'efficacité",
        "efficiency_manual": "Entrer la valeur E manuellement",
        "efficiency_slope": "Calculer à partir de la pente",
        "efficiency_target_label": "Efficacité du Gène Cible {i} (E)",
        "efficiency_ref_label": "Efficacité du Gène Référence {i} (E)",
        "efficiency_target_slope_label": "Pente du Gène Cible {i}",
        "efficiency_ref_slope_label": "Pente du Gène Référence {i}",
        "efficiency_threshold": "Seuil de différence d'efficacité acceptable (%)",
        "efficiency_ok": "✅ La différence d'efficacité est acceptable ({diff:.1f}%)",
        "efficiency_warning": "⚠️ La différence d'efficacité dépasse le seuil ({diff:.1f}%) — La méthode ΔΔCq peut ne pas être fiable!",
        "efficiency_target_pct": "Efficacité du Gène Cible",
        "efficiency_ref_pct": "Efficacité du Gène Référence",
        "efficiency_diff": "Différence",
        "pfaffl_result": "Rapport Pfaffl",
        "pfaffl_header": "Résultats de la Méthode Pfaffl",
        "classic_ddct": "Résultat ΔΔCq Classique (2^(-ΔΔCq))",
        "pfaffl_ratio": "Rapport Pfaffl",
        "method_comparison": "📊 Comparaison des Méthodes",
        "efficiency_note": "Note : E=2.0 représente une efficacité parfaite (100%). Plage acceptée : 1.8–2.2 (90–110%)",
        "statistical_explanation": (
            "Au cours du processus d'évaluation statistique, la répartition des données a été analysée à l'aide du test de Shapiro-Wilk. "
            "Si la normalité était remplie, l'homogénéité de la variance entre les groupes a été vérifiée à l'aide du test de Levene. "
            "Si la variance était égale, un test t pour échantillons indépendants a été appliqué, sinon, un test t de Welch a été utilisé. "
            "Si aucune distribution normale n'était atteinte, le test non paramétrique de Mann-Whitney U a été appliqué. "
            "La signification a été déterminée en utilisant le critère p < 0,05. "
            "Pour des suggestions et un soutien, Burhanettin Yalçınkaya - e-mail : [email removed]"
        ),
        "outlier_section_title": "### 🔍 Paramètres de détection des valeurs aberrantes",
        "outlier_enable": "Activer la détection des valeurs aberrantes",
        "outlier_enable_help": "Détecte les valeurs Cq statistiquement extrêmes pouvant indiquer des erreurs techniques.",
        "outlier_method_label": "Méthode de détection",
        "outlier_method_help": "Grubbs : pour les données normalement distribuées. IQR : non paramétrique, robuste pour les distributions asymétriques.",
        "outlier_alpha_label": "Niveau de signification (α)",
        "outlier_alpha_help": "α = 0,05 est standard. α plus bas = plus conservateur.",
        "outlier_iqr_label": "Multiplicateur IQR (k)",
        "outlier_iqr_help": "k=1,5 = clôtures de Tukey standard. k=3,0 = uniquement les valeurs extrêmes.",
        "outlier_expander": "ℹ️ À propos de la détection des valeurs aberrantes en qPCR",
        "grubbs_info": "ℹ️ **Conditions du test de Grubbs :** Minimum **n ≥ 3** réplicats par groupe. Seuil de signification : **α = {alpha:.2f}**. Le test suppose la normalité ; pour n < 8, la normalité ne peut pas être évaluée de manière fiable. L'application sur les **valeurs Cq brutes** (avant normalisation) est recommandée.",
        "outlier_excluded_no": "Non",
        "outlier_excluded_yes": "Oui",
        # Outlier stage selector
        "outlier_stage_label": "🔬 Étape de détection des valeurs aberrantes",
        "outlier_stage_raw": "Cq brut — avant normalisation (recommandé)",
        "outlier_stage_dct": "ΔCq — après normalisation (comportement précédent)",
        "outlier_stage_help": (
            "**Cq brut (recommandé):** Les valeurs aberrantes sont détectées sur les valeurs Cq brutes "
            "avant le calcul du ΔCq. Appliqué séparément au gène cible et à chaque gène de référence.\n\n"
            "**ΔCq:** Détection après normalisation (comportement original)."
        ),
        # Distribution plot mode selector
        "dist_plot_mode_label": "📊 Graphique de distribution — Mode d'affichage",
        "dist_plot_rq":   "RQ (2^-ΔCq)  — recommandé",
        "dist_plot_dct":  "ΔCq  — valeurs normalisées brutes",
        "dist_plot_ddct": "ΔΔCq  — relatif à la moyenne du contrôle",
        "dist_plot_help": (
            "**RQ (recommandé):** Convertit ΔCq en 2^(-ΔCt). Valeur plus élevée = expression plus élevée.\n\n"
            "**ΔCq:** Valeurs logarithmiques brutes. Utile pour vérifier la distribution des données.\n\n"
            "**ΔΔCq:** ΔCq de chaque échantillon moins la moyenne du groupe contrôle."
        ),
        "unequal_n_warning": (
            "⚠️ **Nombre de réplicats inégal détecté — {group}:**  \n"
            "{details}  \nL'analyse utilisera la **longueur commune la plus courte (n={min_n})**.  \n"
            "Veuillez vérifier vos données d'entrée."
        ),
        # Sidebar
        "sidebar_load_example": "📂 Charger les données d'exemple",
        "sidebar_example_loaded": "✅ Données d'exemple chargées ! Allez à l'onglet Saisie des données.",
        "sidebar_desktop_title": "### 💻 Application de bureau",
        "sidebar_desktop_btn": "⬇️ Télécharger l'application de bureau",
        "sidebar_opensource_title": "### 🔓 Open Source",
        "sidebar_opensource_body": "GeneQuantify est open source (GPL-3.0).  \nCode source disponible sur GitHub :",
        "sidebar_github_btn": "⭐ Voir le code source sur GitHub",
        "sidebar_scenarios_title": "📋 Charger un scénario de validation",
        "sidebar_scenario_select": "Sélectionner un scénario",
        "sidebar_load_scenario_btn": "▶ Charger le scénario",
        "sidebar_scenario_loaded": "✅ {s} chargé ! Allez à la saisie des données.",
        "outlier_excluded_no": "Non",
        "outlier_excluded_yes": "Oui",
        "stat_decision_title": "🔬 Décision statistique",
        "stat_decision_steps": "**Sélection du test étape par étape :**",
        "stat_shapiro_title": "**1. Test de normalité de Shapiro-Wilk**",
        "stat_normal": "Normal",
        "stat_nonnormal": "Non normal",
        "stat_levene_title": "**2. Test d'homogénéité des variances de Levene**",
        "stat_levene_skipped": "**2. Test de Levene** — *ignoré* (normalité non satisfaite ; test non paramétrique utilisé)",
        "stat_equal_var": "Variances égales",
        "stat_unequal_var": "Variances inégales",
        "stat_selected_test": "**3. Test sélectionné :**",
        "stat_reason": "**Raison :**",
        "stat_result": "**Résultat :**",
        "stat_reason_nonnormal": "Distribution non normale dans un ou les deux groupes",
        "stat_reason_normal_equal": "Les deux groupes normaux + variances égales",
        "stat_reason_normal_unequal": "Les deux groupes normaux + variances inégales (Levene p < 0,05)",
        "stat_multigroup_note": "⚠️ Remarque : Avec ≥ 3 groupes, voir la section **Comparaison multi-groupes** ci-dessous pour ANOVA / Kruskal-Wallis.",
        "multigroup_title": "## 📊 Analyse de comparaison multi-groupes",
        "multigroup_expander": "ℹ️ À propos de l'analyse statistique multi-groupes",
        "multigroup_omnibus_test": "Test omnibus",
        "multigroup_pvalue": "p-valeur",
        "multigroup_result": "Résultat",
        "multigroup_significant": "Significatif",
        "multigroup_not_significant": "Non significatif",
        "multigroup_omnibus_ns": "ℹ️ Le test omnibus est **non significatif** (p ≥ 0,05). Les comparaisons post-hoc sont affichées à titre indicatif.",
        "multigroup_posthoc_label": "**Post-hoc :**",
        "multigroup_dl_button": "📥 Télécharger les résultats post-hoc —",
        "multigroup_2group_note": "ℹ️ **Analyse multi-groupes non applicable :** Seulement 2 groupes détectés (Contrôle + 1 groupe patient).",
        "multigroup_decision_normal_equal": "✅ Distribution normale + variances égales → **ANOVA à un facteur + Tukey HSD**",
        "multigroup_decision_normal_unequal": "⚠️ Distribution normale + **variances inégales** → **ANOVA de Welch + Games-Howell**",
        "multigroup_decision_nonnormal": "⚠️ **Distribution non normale** → **Kruskal-Wallis + post-hoc Dunn**",
        "multigene_title": "### 🧬 Correction des comparaisons multiples multi-gènes",
        "multigene_expander": "ℹ️ Pourquoi est-ce nécessaire ?",
        "multigene_sig_raw": "Significatif (brut)",
        "multigene_sig_bonf": "Significatif (Bonferroni)",
        "multigene_sig_fdr": "Significatif (FDR B-H)",
        "multigene_warning": "⚠️ Après correction, {lost} résultat(s) ne sont plus significatifs après ajustement FDR. Rapportez les p-valeurs corrigées comme résultats principaux.",
        "multigene_success": "✅ Tous les {n} résultats significatifs restent significatifs après correction FDR.",
        "multigene_no_sig": "Aucun résultat pairwise significatif détecté (p brut < 0,05).",
        "multigene_dl_button": "📥 Télécharger les p-valeurs corrigées (CSV)",
        "multigene_chart_title": "Correction p-valeur multi-gènes : Brut / Bonferroni / FDR",
        "multigene_fc_chart_title": "Comparaison d'expression multi-gènes",
        "multigene_1gene_note": "ℹ️ **Correction multi-gènes :** Seulement 1 gène cible analysé — correction non applicable.",
        "multigene_no_data": "Pas encore de p-valeurs — entrez des données ci-dessus.",
        "ref_gene_section_title": "### 📚 Paramètres des gènes de référence",
        "ref_gene_num_label": "Nombre de gènes de référence par gène cible",
        "ref_gene_num_help": "Les directives MIQE recommandent ≥2 gènes de référence validés pour une normalisation robuste.",
        "ref_gene_1_warning": "⚠️ **Note méthodologique :** L'utilisation d'un seul gène de référence limite la robustesse de la normalisation. Les directives MIQE (Bustin et al. 2009) recommandent **≥2 gènes de référence validés** avec évaluation de la stabilité (geNorm/NormFinder).",
        "ref_gene_multi_success": "✅ {n} gènes de référence sélectionnés. La normalisation par moyenne géométrique et la stabilité geNorm M seront calculées automatiquement.",
        "ref_gene_expander": "ℹ️ À propos de la normalisation multi-référence",
        "sc_expander": "📐 Calculateur de courbe standard — Calculer E à partir d'une série de dilutions",
        "sc_gene_label": "Gène / étiquette d'amorce",
        "sc_num_points": "Nombre de points de dilution",
        "sc_dilution_factor_label": "**Facteur de dilution** (ex. 10 pour des dilutions 10 fois)",
        "sc_dilution_factor_input": "Facteur de dilution",
        "sc_start_conc_label": "**Concentration initiale** (unités arbitraires, ex. 1)",
        "sc_start_conc_input": "Concentration initiale",
        "sc_enter_ct": "**Entrez la valeur Cq moyenne pour chaque dilution :**",
        "sc_calc_button": "📊 Calculer l'efficacité",
        "sc_slope": "Pente",
        "sc_e_value": "Valeur E",
        "sc_efficiency_pct": "Efficacité %",
        "sc_excellent": "✅ Excellent ! E={e:.4f} ({pct:.1f}%), R²={r2:.4f} — Utilisez cette valeur E dans la section efficacité ci-dessous.",
        "sc_warning_r2": "⚠️ E est acceptable ({pct:.1f}%) mais R²={r2:.4f} < 0,99 — vérifiez votre série de dilutions.",
        "sc_error_range": "❌ E={e:.4f} ({pct:.1f}%) est hors de la plage acceptable (90–110%). Vérifiez la conception des amorces ou la série de dilutions.",
        "sc_chart_title": "Courbe standard — {label} | E={e:.4f} ({pct:.1f}%), R²={r2:.4f}",
        "sc_xaxis": "log₁₀(Concentration)",
        "sc_data_points": "Points de données",
        "sc_copy_hint": "💡 Copiez la pente **{slope:.4f}** ou la valeur E **{e:.4f}** dans les champs d'efficacité ci-dessous.",
        "sc_description": """\
Entrez vos valeurs Ct de dilution en série ci-dessous. Le calculateur ajustera une régression linéaire et calculera automatiquement la pente, R² et l'efficacité d'amplification.

**Comment utiliser :**  
1. Effectuez la qPCR sur des dilutions en série (ex. non dilué, 1:10, 1:100, 1:1000, 1:10000)  
2. Entrez la valeur Ct moyenne pour chaque dilution  
3. Lisez la pente, E et R²  
""",
        "ref_multi_description": """\
**Normalisation par moyenne géométrique** (Vandesompele et al. 2002)  
Le facteur de normalisation (NF) est la moyenne arithmétique des valeurs Ct de tous les gènes de référence par échantillon,  
ce qui correspond à la moyenne géométrique de leurs niveaux d'expression.  
`NF_échantillon = moyenne(Ct_ref1, Ct_ref2, ..., Ct_refN)` pour chaque échantillon  
`ΔCq = Ct_cible − NF`

**Valeur M de geNorm** (score de stabilité)  
Pour chaque gène de référence, M = écart-type moyen des log-ratios par rapport à tous les autres gènes de référence.  
**M plus bas = plus stable.** Seuil recommandé MIQE : M < 0,5 (strict) ou M < 1,0 (acceptable).

**CV (Coefficient de Variation)**  
`CV = (ET / moyenne) × 100%` des valeurs Cq brutes sur tous les échantillons.  
Un CV plus faible indique moins de variation et une meilleure stabilité comme référence.

**Référence :** Vandesompele J et al. *Genome Biology* 2002 ; Bustin SA et al. *Clin Chem* 2009 (MIQE).
""",
        "outlier_description": """\
**Pourquoi la détection des valeurs aberrantes est importante en qPCR**

La variabilité technique est inhérente à la qPCR : erreurs de pipetage, formation de bulles, contamination par des inhibiteurs ou variation de la qualité de l'ARN peuvent produire des valeurs Cq statistiquement incohérentes avec le reste d'un groupe de réplicats.  
L'inclusion de telles valeurs gonfle la variance, biaise les moyennes et peut conduire à de fausses conclusions — particulièrement dans les jeux de données cliniques avec de petits effectifs.

**Quand cette limitation devient critique :**
- Petits groupes (n < 5) : un seul Ct erroné déplace substantiellement la moyenne
- Variabilité biologique élevée (ex. hétérogénéité tumorale, cohortes cliniques)
- Triplicats techniques où un réplicat diverge de > 0,5 Ct des autres
- Cibles à faible abondance avec Ct > 35, où le bruit domine

**Test de Grubbs** *(Grubbs 1969)*  
Suppose la normalité. Teste si la valeur la plus extrême est un outlier statistiquement significatif (p < α). Itère jusqu'à ce qu'aucun autre outlier ne soit trouvé.  
Meilleur pour : valeurs Ct répliquées d'un seul groupe expérimental.

**Méthode IQR** *(Tukey 1977)*  
Non paramétrique. Signale les valeurs en dehors de Q1 − k×IQR ou Q3 + k×IQR.  
Meilleur pour : groupes plus importants ou distributions non normales.

**Important :** L'exclusion des outliers nécessite une **justification biologique ou technique**.  
Cet outil signale des candidats — la décision finale appartient toujours au chercheur.  
Toutes les exclusions sont enregistrées et rapportées dans le rapport PDF.

**Références :** Grubbs FE. *Technometrics* 1969 ; Tukey JW. *Exploratory Data Analysis* 1977 ;  
Bustin SA et al. *Clin Chem* 2009 (directives MIQE).
""",

        # ── Chaînes du rapport PDF ────────────────────────────────────────────
        "pdf_cover_subtitle": "Rapport d'analyse d'expression génique qPCR",
        "pdf_generated": "Généré le: {now}",
        "pdf_s1_title": "1. Méthodes et paramètres d'analyse",
        "pdf_s1_calc": "1.1 Méthodes de calcul",
        "pdf_s1_calc_body": "Deux méthodes complémentaires ont été appliquées pour le calcul du fold-change:",
        "pdf_s1_classic": "ΔΔCq classique (Livak & Schmittgen, 2001): ΔCq = Ct(cible) - Ct(référence);  ΔΔCt = ΔCt(échantillon) - ΔCt(contrôle);  Fold-Change = 2^(-ΔΔCt). Suppose des efficacités égales (E ≈ 2,0).",
        "pdf_s1_pfaffl": "Méthode Pfaffl (Pfaffl, 2001): Ratio = (E_cible ^ ΔCq_cible) / (E_réf ^ ΔCt_réf). Corrige les efficacités spécifiques; recommandé si différence > 10%.",
        "pdf_s1_norm": "1.2 Normalisation",
        "pdf_s1_norm_multi": "Gènes de référence multiples (n={n}) utilisés. NF = moyenne arithmétique des Cq des gènes de référence par échantillon (geNorm, Vandesompele et al. 2002).",
        "pdf_s1_norm_single": "Un seul gène de référence utilisé. Les directives MIQE recommandent ≥2 gènes de référence.",
        "pdf_s1_eff": "1.3 Efficacité d'amplification",
        "pdf_s1_eff_range": "Plage d'efficacité acceptable: E = 1,8-2,2 (90-110%). Seuil de différence appliqué: {thr}%.",
        "pdf_s1_outlier": "1.4 Détection des valeurs aberrantes",
        "pdf_s1_grubbs": "Test de Grubbs (Grubbs 1969) appliqué, alpha = {alpha}. {n} échantillon(s) signalé(s) et confirmé(s) par l'utilisateur.",
        "pdf_s1_iqr": "Méthode IQR (Tukey 1977), multiplicateur k = {k}. {n} échantillon(s) exclu(s).",
        "pdf_s1_outlier_warn": "AVERTISSEMENT: L'exclusion des valeurs aberrantes nécessite une justification biologique ou technique.",
        "pdf_s1_outlier_off": "Détection des valeurs aberrantes désactivée pour cette analyse.",
        "pdf_s2_title": "2. Données d'entrée",
        "pdf_s2_body": "Valeurs Cq brutes saisies par l'utilisateur après traitement des valeurs aberrantes.",
        "pdf_s3_title": "3. Résultats d'expression génique",
        "pdf_s3_body": "Valeurs de fold-change calculées par ΔΔCq classique et méthode Pfaffl. Fold-change > 1 = expression plus élevée dans le groupe patient.",
        "pdf_s4_title": "4. Analyse statistique",
        "pdf_s4_body": "Signification statistique des différences d'expression génique. Sélection automatique du test selon normalité (Shapiro-Wilk) et homogénéité des variances (Levene). Seuil: p < 0,05.",
        "pdf_s4_interp": "Interprétation des tests statistiques",
        "pdf_s4_interp_body": "t de Student: groupes normaux avec variances égales. t de Welch: normaux mais variances inégales. Mann-Whitney U: non-paramétrique. p < 0,05 = expression différentielle significative.",
        "pdf_s5_title": "5. Graphiques de distribution Delta Cq",
        "pdf_s5_body": "Distribution des valeurs ΔCq pour chaque gène cible. Chaque point = un réplicat. Barres horizontales = moyennes des groupes.",
        "pdf_s6_title": "6. Comment interpréter vos résultats",
        "pdf_s6_fc": "6.1 Interprétation du fold-change",
        "pdf_s6_choose": "6.2 Choisir entre ΔΔCq et Pfaffl",
        "pdf_s6_choose_body": "ΔΔCq classique si: efficacités 90-110% et différence < 10%. Pfaffl si: différence > 10%. Toujours rapporter les deux valeurs.",
        "pdf_s6_stat": "6.3 Justification du choix du test",
        "pdf_s6_stat_body": "Normalité: test de Shapiro-Wilk (n < 50). Homogénéité des variances: test de Levene. Paramétrique/variances égales: t de Student. Variances inégales: t de Welch. Non-normal: Mann-Whitney U.",
        "pdf_s7_title": "7. Références",
        "pdf_fc_interp_header": ["Fold-Change", "ΔΔCq", "Interprétation", "Signification biologique"],
        "pdf_fc_interp_rows": [
            [">2,0", "<-1,0", "Forte surexpression", "Biologiquement pertinent"],
            ["1,5-2,0", "-1,0 à -0,58", "Surexpression modérée", "Potentiellement pertinent"],
            ["1,0-1,5", "-0,58 à 0", "Faible surexpression", "Probablement non significatif seul"],
            ["1,0", "0", "Aucun changement", "Pas d'expression différentielle"],
            ["0,67-1,0", "0 à 0,58", "Faible sous-expression", "Probablement non significatif seul"],
            ["0,5-0,67", "0,58 à 1,0", "Sous-expression modérée", "Potentiellement pertinent"],
            ["<0,5", ">1,0", "Forte sous-expression", "Biologiquement pertinent"],
        ],
        "pdf_stat_note": "Note: La signification statistique et biologique doivent être évaluées ensemble.",
        "pdf_summary_param": "Paramètre",
        "pdf_summary_val": "Valeur",
        "pdf_summary_genes": "Gènes cibles analysés",
        "pdf_summary_groups": "Groupes de patients",
        "pdf_summary_samples": "Échantillons totaux",
        "pdf_summary_excluded": "Valeurs aberrantes exclues",
        "pdf_summary_tests": "comparaisons",
        "pdf_summary_norm": "Méthode de normalisation",
        "pdf_summary_norm_multi": "geNorm NF",
        "pdf_summary_norm_single": "Gène de référence unique",
        "pdf_summary_methods": "Méthodes de calcul",
        "pdf_summary_methods_val": "ΔΔCq classique + Pfaffl",
        "pdf_disclaimer": "Ce rapport a été généré automatiquement par GeneQuantify conformément aux directives MIQE.",
        "pdf_footer": "GeneQuantify — Usage recherche et éducation uniquement. Non validé pour usage clinique.",
        "pdf_fig1": "Figure 1. Comparaison du fold-change: ΔΔCq classique vs Pfaffl. Ligne pointillée y=1 = aucun changement.",
        "pdf_fig2": "Figure 2. Valeurs p de toutes les comparaisons. Barres rouges = significatif (p < 0,05).",
        "pdf_fig3": "Figure. Distribution ΔCq pour {gene}. Points = réplicats; barres = moyennes des groupes.",
        "pdf_nochange": "Aucun changement",
        "pdf_stat_cols": ["Gène cible", "Comparaison", "Type de test", "Méthode", "Valeur p", "Signification"],
        "pdf_res_cols": ["Gène cible", "Groupe", "ΔCq Contrôle", "ΔCq Échantillon", "ΔΔCq", "2^(-ΔΔCq)", "Ratio Pfaffl", "Régulation", "E cible", "E réf"],
        "pdf_eff_cols": ["Gène", "E (cible)", "Eff% (cible)", "E (réf)", "Eff% (réf)", "Diff%", "Statut"],
        "pdf_eff_ok": "OK",
        "pdf_eff_warn": "AVERTISSEMENT: utiliser Pfaffl",
        "pdf_outlier_col": "Valeur aberrante exclue",
        "pdf_contact": "Contact: [email removed]",
        "pdf_ready": "{n} enregistrements prêts — vous pouvez générer le PDF.",
        # RDML / RDES import
        "rdml_expander":        "📂 Importer un fichier RDML / RDES",
        "rdml_description":     "Importez un fichier **RDML** (`.rdml`) ou **RDES** (`.tsv`/`.csv`/`.txt`) pour remplir automatiquement les valeurs Cq.",
        "rdml_uploader":        "Choisir un fichier",
        "rdml_uploader_help":   "RDML: Bio-Rad CFX, Roche LightCycler, etc.  RDES: tableau séparé par tabulations.",
        "rdml_success":         "✅ Fichier {fmt} chargé — {n} réactions trouvées.",
        "rdml_error":           "❌ Erreur d'analyse {fmt} : {err}",
        "rdml_preview":         "Aperçu des données analysées",
        "rdml_step1":           "**Étape 1 — Étiquetez votre groupe contrôle**",
        "rdml_ctrl_label":      "Nom(s) d'échantillon contrôle (sous-chaînes séparées par des virgules)",
        "rdml_ctrl_help":       "Tout échantillon dont le nom contient ce texte sera traité comme Contrôle.",
        "rdml_step2":           "**Étape 2 — Étiquetez vos groupes patients**",
        "rdml_n_pat":           "Nombre de groupes patients",
        "rdml_pat_label":       "Nom(s) d'échantillon du groupe patient {i}",
        "rdml_pat_help":        "Sous-chaînes séparées par des virgules. Tous les échantillons correspondants seront regroupés.",
        "rdml_apply":           "✅ Appliquer l'import {fmt} à la saisie des données",
        "rdml_apply_success":   "✅ {n} valeurs Cq chargées dans l'onglet Saisie ! Vérifiez et ajustez si nécessaire.",
        "rdml_apply_warning":   "⚠️ Aucune valeur correspondante. Vérifiez que vos étiquettes correspondent aux noms dans l'aperçu.",
    },

    "es": {
        "title": "🧬 GeneQuantify: Análisis de Expresión Génica y CNV",
        "tab_data": "Entrada de datos",
        "tab_results": "Resultados",
        "tab_report": "Informe",
        "subtitle": "Desarrollado por B. Yalçınkaya",
        "patient_data_header": "📊 Ingrese Datos de Grupos de Pacientes y de Control",
        "num_target_genes": "🔹 Ingrese el número de Genes Objetivo",
        "num_patient_groups": "🔹 Ingrese el número de Grupos de Pacientes",
        "sample_number": "Número de muestra",
        "Grup": "Grupo",
        "x_axis_title": "Nombre del Grupo",
        "ct_value": "Valor de Cq",
        "reference_ct": "Ct de Referencia",
        "delta_ct_control": "ΔCq (Control)",
        "delta_ct_patient": "ΔCq (Paciente)",
        "warning_empty_input": "⚠️ Advertencia: Ingrese los datos uno debajo del otro o cópielos sin celdas vacías desde Excel.",
        "download_csv": "📥 Descargar CSV",
        "generate_pdf": "📥 Preparar Informe en PDF",
        "pdf_report": "Informe de Análisis de Expresión Génica",
        "nil_mine": "📊 Resultados",
        "gr_tbl": "📋 Tabla de Datos de Entrada",
        "control_group": "🧬 Grupo Control",
        "ctrl_trgt_ct": "🟦 Valores Ct del Gen Objetivo {i} para el Grupo Control",
        "ctrl_ref_ct": "🟦 Valores Ct del Gen de Referencia {i} para el Grupo Control",
        "hst_trgt_ct": "🩸 Valores Ct del Gen Objetivo {j} para el Grupo Paciente",
        "hst_ref_ct": "🩸 Valores Ct del Gen de Referencia {j} para el Grupo Paciente",
        "warning_control_ct": "⚠️ Advertencia: Los datos del grupo control {i} deben ingresarse fila por fila o copiarse desde Excel sin celdas vacías.",
        "warning_patient_cq": "⚠️ Advertencia: Ingrese los valores de Ct del grupo paciente fila por fila o cópielos desde Excel sin celdas vacías.",
        "target_gene": "Gen Objetivo",
        "reference_gene": "Gen de Referencia",
        "target_ct": "Ct del Gen Objetivo", 
        "distribution_graph": "Gráfico de Distribución",
        "error_missing_control_data": "⚠️ Error: ¡Datos faltantes para el Gen Objetivo {i} en el Grupo Control!",
        "control_group_avg": "Promedio del Grupo Control",
        "avg": "Promedio",
        "control": "Control",
        "sample": "Muestra",
        "patient": "Paciente",
        "delta_ct_distribution": "Distribución ΔCq",
        "delta_ct_value": "Valor ΔCq",
        "parametric": "Paramétrico",
        "non_parametric": "No paramétrico",
        "t_test": "Test t",
        "mann_whitney_u_test": "Test Mann-Whitney U",
        "welch_t_test": "Test t de Welch",
        "significant": "Significativo",
        "insignificant": "No Significativo",
        "test_type": "Tipo de Test",
        "test_method": "Método de Test",
        "test_pvalue": "P-valor del Test",
        "significance": "Significación",
        "delta_delta_ct": "ΔΔCq",
        "gene_expression_change": "Cambio de Expresión Génica (2^(-ΔΔCq))",
        "regulation_status": "Estado de Regulación",
        "no_change": "Sin Cambio",
        "upregulated": "Upregulado",
        "downregulated": "Downregulado",
        "report_title": "Informe de Análisis de Expresión Génica",
        "input_data_table": "Tabla de Datos de Entrada",
        "results": "Resultados",
        "statistical_results": "📈 Resultados Estadísticos",
        "statistics": "Resultados estadísticos",
        "statistical_evaluation": "Evaluación Estadística",
        "target_gene": "Gen Objetivo",
        "patient_group": "🩸 Grupo Paciente",
        "expression_change": "Cambio de Expresión Génica",
        "generate_pdf": "Generar PDF",
        "pdf_report": "Informe de Expresión Génica",
        "error_no_data": "No se encontraron datos, no se pudo generar el PDF.",
        # Efficiency translations
        "efficiency_header": "🔬 Validación de Eficiencia de Amplificación",
        "efficiency_method": "Método de entrada de eficiencia",
        "efficiency_manual": "Ingresar valor E manualmente",
        "efficiency_slope": "Calcular desde pendiente",
        "efficiency_target_label": "Eficiencia del Gen Objetivo {i} (E)",
        "efficiency_ref_label": "Eficiencia del Gen de Referencia {i} (E)",
        "efficiency_target_slope_label": "Pendiente del Gen Objetivo {i}",
        "efficiency_ref_slope_label": "Pendiente del Gen de Referencia {i}",
        "efficiency_threshold": "Umbral de diferencia de eficiencia aceptable (%)",
        "efficiency_ok": "✅ La diferencia de eficiencia es aceptable ({diff:.1f}%)",
        "efficiency_warning": "⚠️ La diferencia de eficiencia supera el umbral ({diff:.1f}%) — ¡El método ΔΔCq puede no ser confiable!",
        "efficiency_target_pct": "Eficiencia del Gen Objetivo",
        "efficiency_ref_pct": "Eficiencia del Gen de Referencia",
        "efficiency_diff": "Diferencia",
        "pfaffl_result": "Relación Pfaffl",
        "pfaffl_header": "Resultados del Método Pfaffl",
        "classic_ddct": "Resultado ΔΔCq Clásico (2^(-ΔΔCq))",
        "pfaffl_ratio": "Relación Pfaffl",
        "method_comparison": "📊 Comparación de Métodos",
        "efficiency_note": "Nota: E=2.0 representa eficiencia perfecta (100%). Rango aceptado: 1.8–2.2 (90–110%)",
        "statistical_explanation": (
            "Durante el proceso de evaluación estadística, se analizó la distribución de los datos mediante la prueba de Shapiro-Wilk. "
            "Si se cumplió la normalidad, se verificó la homogeneidad de varianza entre los grupos mediante la prueba de Levene. "
            "Si la varianza era igual, se aplicó la prueba t de muestras independientes; de lo contrario, se utilizó la prueba t de Welch. "
            "Si no se alcanzó una distribución normal, se aplicó la prueba no paramétrica Mann-Whitney U. "
            "La significancia se determinó utilizando el criterio p < 0.05. "
            "Para sugerencias y soporte, Burhanettin Yalçınkaya - correo electrónico: [email removed]"
        ),
        "outlier_section_title": "### 🔍 Configuración de detección de valores atípicos",
        "outlier_enable": "Activar detección de valores atípicos",
        "outlier_enable_help": "Detecta valores Ct estadísticamente extremos que pueden reflejar errores técnicos.",
        "outlier_method_label": "Método de detección",
        "outlier_method_help": "Grubbs: para datos normalmente distribuidos. IQR: no paramétrico, robusto para distribuciones asimétricas.",
        "outlier_alpha_label": "Nivel de significancia (α)",
        "outlier_alpha_help": "α = 0,05 es estándar. α más bajo = más conservador.",
        "outlier_iqr_label": "Multiplicador IQR (k)",
        "outlier_iqr_help": "k=1,5 = cercas de Tukey estándar. k=3,0 = solo valores extremos.",
        "outlier_expander": "ℹ️ Sobre la detección de valores atípicos en qPCR",
        "grubbs_info": "ℹ️ **Requisitos del test de Grubbs:** Mínimo **n ≥ 3** réplicas por grupo. Umbral de significancia: **α = {alpha:.2f}**. El test asume normalidad; para n < 8, la normalidad no puede evaluarse de forma confiable. Se recomienda aplicar el test a los **valores Cq brutos** (antes de la normalización).",
        "outlier_excluded_no": "No",
        "outlier_excluded_yes": "Sí",
        # Outlier stage selector
        "outlier_stage_label": "🔬 Etapa de detección de valores atípicos",
        "outlier_stage_raw": "Ct bruto — antes de la normalización (recomendado)",
        "outlier_stage_dct": "ΔCq — después de la normalización (comportamiento anterior)",
        "outlier_stage_help": (
            "**Ct bruto (recomendado):** Los valores atípicos se detectan en los valores Ct brutos "
            "antes del cálculo del ΔCq. Aplicado por separado al gen objetivo y a cada gen de referencia.\n\n"
            "**ΔCq:** Detección después de la normalización (comportamiento original)."
        ),
        # Distribution plot mode selector
        "dist_plot_mode_label": "📊 Gráfico de distribución — Modo de visualización",
        "dist_plot_rq":   "RQ (2^-ΔCq)  — recomendado",
        "dist_plot_dct":  "ΔCq  — valores normalizados brutos",
        "dist_plot_ddct": "ΔΔCq  — relativo a la media del control",
        "dist_plot_help": (
            "**RQ (recomendado):** Convierte ΔCq a 2^(-ΔCt). Mayor valor = mayor expresión.\n\n"
            "**ΔCq:** Valores logarítmicos brutos. Útil para verificar la distribución.\n\n"
            "**ΔΔCq:** ΔCq de cada muestra menos la media del grupo control."
        ),
        "unequal_n_warning": (
            "⚠️ **Recuentos de réplicas desiguales detectados — {group}:**  \n"
            "{details}  \nEl análisis usará la **longitud común más corta (n={min_n})**.  \n"
            "Verifique sus datos de entrada."
        ),
        # Sidebar
        "sidebar_load_example": "📂 Cargar datos de ejemplo",
        "sidebar_example_loaded": "✅ ¡Datos de ejemplo cargados! Cambie a la pestaña de entrada de datos.",
        "sidebar_desktop_title": "### 💻 Aplicación de escritorio",
        "sidebar_desktop_btn": "⬇️ Descargar aplicación de escritorio",
        "sidebar_opensource_title": "### 🔓 Código abierto",
        "sidebar_opensource_body": "GeneQuantify es de código abierto (GPL-3.0).  \nCódigo fuente disponible en GitHub:",
        "sidebar_github_btn": "⭐ Ver código fuente en GitHub",
        "sidebar_scenarios_title": "📋 Cargar escenario de validación",
        "sidebar_scenario_select": "Seleccionar escenario",
        "sidebar_load_scenario_btn": "▶ Cargar escenario",
        "sidebar_scenario_loaded": "✅ {s} cargado. Vaya a Entrada de datos.",
        "outlier_excluded_no": "No",
        "outlier_excluded_yes": "Sí",
        "stat_decision_title": "🔬 Decisión estadística",
        "stat_decision_steps": "**Selección de prueba paso a paso:**",
        "stat_shapiro_title": "**1. Prueba de normalidad de Shapiro-Wilk**",
        "stat_normal": "Normal",
        "stat_nonnormal": "No normal",
        "stat_levene_title": "**2. Prueba de homogeneidad de varianzas de Levene**",
        "stat_levene_skipped": "**2. Prueba de Levene** — *omitida* (normalidad no cumplida; se usará prueba no paramétrica)",
        "stat_equal_var": "Varianzas iguales",
        "stat_unequal_var": "Varianzas desiguales",
        "stat_selected_test": "**3. Prueba seleccionada:**",
        "stat_reason": "**Razón:**",
        "stat_result": "**Resultado:**",
        "stat_reason_nonnormal": "Distribución no normal en uno o ambos grupos",
        "stat_reason_normal_equal": "Ambos grupos normales + varianzas iguales",
        "stat_reason_normal_unequal": "Ambos grupos normales + varianzas desiguales (Levene p < 0,05)",
        "stat_multigroup_note": "⚠️ Nota: Con ≥ 3 grupos, consulte la sección **Comparación multigrupo** para ANOVA / Kruskal-Wallis.",
        "multigroup_title": "## 📊 Análisis de comparación multigrupo",
        "multigroup_expander": "ℹ️ Sobre el análisis estadístico multigrupo",
        "multigroup_omnibus_test": "Prueba ómnibus",
        "multigroup_pvalue": "p-valor",
        "multigroup_result": "Resultado",
        "multigroup_significant": "Significativo",
        "multigroup_not_significant": "No significativo",
        "multigroup_omnibus_ns": "ℹ️ La prueba ómnibus es **no significativa** (p ≥ 0,05). Las comparaciones post-hoc se muestran a título informativo.",
        "multigroup_posthoc_label": "**Post-hoc:**",
        "multigroup_dl_button": "📥 Descargar resultados post-hoc —",
        "multigroup_2group_note": "ℹ️ **Análisis multigrupo no aplicable:** Solo 2 grupos detectados (Control + 1 grupo paciente).",
        "multigroup_decision_normal_equal": "✅ Distribución normal + varianzas iguales → **ANOVA de un factor + Tukey HSD**",
        "multigroup_decision_normal_unequal": "⚠️ Distribución normal + **varianzas desiguales** → **ANOVA de Welch + Games-Howell**",
        "multigroup_decision_nonnormal": "⚠️ **Distribución no normal** → **Kruskal-Wallis + post-hoc Dunn**",
        "multigene_title": "### 🧬 Corrección de comparaciones múltiples multigénicas",
        "multigene_expander": "ℹ️ ¿Por qué es necesario?",
        "multigene_sig_raw": "Significativo (bruto)",
        "multigene_sig_bonf": "Significativo (Bonferroni)",
        "multigene_sig_fdr": "Significativo (FDR B-H)",
        "multigene_warning": "⚠️ Tras la corrección, {lost} resultado(s) ya no son significativos tras el ajuste FDR. Reporte los p-valores corregidos como resultados principales.",
        "multigene_success": "✅ Todos los {n} resultados significativos permanecen significativos tras la corrección FDR.",
        "multigene_no_sig": "No se detectaron resultados pairwise significativos (p bruto < 0,05).",
        "multigene_dl_button": "📥 Descargar p-valores corregidos (CSV)",
        "multigene_chart_title": "Corrección p-valor multigénica: Bruto / Bonferroni / FDR",
        "multigene_fc_chart_title": "Comparación de expresión multi-gen",
        "multigene_1gene_note": "ℹ️ **Corrección multigénica:** Solo 1 gen objetivo analizado — corrección no aplicable.",
        "multigene_no_data": "Aún no hay p-valores — ingrese datos arriba.",
        "ref_gene_section_title": "### 📚 Configuración de genes de referencia",
        "ref_gene_num_label": "Número de genes de referencia por gen objetivo",
        "ref_gene_num_help": "Las directrices MIQE recomiendan ≥2 genes de referencia validados para una normalización robusta.",
        "ref_gene_1_warning": "⚠️ **Nota metodológica:** El uso de un solo gen de referencia limita la robustez de la normalización. Las directrices MIQE (Bustin et al. 2009) recomiendan **≥2 genes de referencia validados** con evaluación de estabilidad (geNorm/NormFinder).",
        "ref_gene_multi_success": "✅ {n} genes de referencia seleccionados. La normalización por media geométrica y la estabilidad geNorm M se calcularán automáticamente.",
        "ref_gene_expander": "ℹ️ Sobre la normalización con múltiples referencias",
        "sc_expander": "📐 Calculadora de curva estándar — Calcular E a partir de serie de diluciones",
        "sc_gene_label": "Gen / etiqueta de cebador",
        "sc_num_points": "Número de puntos de dilución",
        "sc_dilution_factor_label": "**Factor de dilución** (ej. 10 para diluciones 10 veces)",
        "sc_dilution_factor_input": "Factor de dilución",
        "sc_start_conc_label": "**Concentración inicial** (unidades arbitrarias, ej. 1)",
        "sc_start_conc_input": "Concentración inicial",
        "sc_enter_ct": "**Ingrese el Cq medio para cada dilución:**",
        "sc_calc_button": "📊 Calcular eficiencia",
        "sc_slope": "Pendiente",
        "sc_e_value": "Valor E",
        "sc_efficiency_pct": "Eficiencia %",
        "sc_excellent": "✅ ¡Excelente! E={e:.4f} ({pct:.1f}%), R²={r2:.4f} — Use este valor E en la sección de eficiencia abajo.",
        "sc_warning_r2": "⚠️ E es aceptable ({pct:.1f}%) pero R²={r2:.4f} < 0,99 — verifique su serie de diluciones.",
        "sc_error_range": "❌ E={e:.4f} ({pct:.1f}%) está fuera del rango aceptable (90–110%). Revise el diseño de cebadores o la serie de diluciones.",
        "sc_chart_title": "Curva estándar — {label} | E={e:.4f} ({pct:.1f}%), R²={r2:.4f}",
        "sc_xaxis": "log₁₀(Concentración)",
        "sc_data_points": "Puntos de datos",
        "sc_copy_hint": "💡 Copie la pendiente **{slope:.4f}** o el valor E **{e:.4f}** en los campos de eficiencia abajo.",
        "sc_description": """\
Ingrese sus valores Ct de dilución en serie a continuación. La calculadora ajustará una regresión lineal y calculará automáticamente la pendiente, R² y la eficiencia de amplificación.

**Cómo usar:**  
1. Realice qPCR en diluciones seriadas (ej. sin diluir, 1:10, 1:100, 1:1000, 1:10000)  
2. Ingrese el Ct medio para cada dilución  
3. Lea la pendiente, E y R²  
""",
        "ref_multi_description": """\
**Normalización por media geométrica** (Vandesompele et al. 2002)  
El factor de normalización (NF) es la media aritmética de los valores Ct de todos los genes de referencia por muestra,  
lo que corresponde a la media geométrica de sus niveles de expresión.  
`NF_muestra = media(Ct_ref1, Ct_ref2, ..., Ct_refN)` para cada muestra  
`ΔCq = Ct_objetivo − NF`

**Valor M de geNorm** (puntuación de estabilidad)  
Para cada gen de referencia, M = desviación estándar media de los log-ratios contra todos los demás genes de referencia.  
**M más bajo = más estable.** Umbral recomendado MIQE: M < 0,5 (estricto) o M < 1,0 (aceptable).

**CV (Coeficiente de Variación)**  
`CV = (DE / media) × 100%` de los valores Ct brutos en todas las muestras.  
Un CV más bajo indica menos variación y mejor estabilidad como referencia.

**Referencia:** Vandesompele J et al. *Genome Biology* 2002; Bustin SA et al. *Clin Chem* 2009 (MIQE).
""",
        "outlier_description": """\
**Por qué la detección de valores atípicos es importante en qPCR**

La variabilidad técnica es inherente a la qPCR: errores de pipeteo, formación de burbujas, arrastre de inhibidores o variación en la calidad del ARN pueden producir valores Ct estadísticamente inconsistentes con el resto de un grupo de réplicas.  
Incluir tales valores infla la varianza, sesga las medias y puede llevar a conclusiones falsas — particularmente en conjuntos de datos clínicos con tamaños de muestra pequeños.

**Cuándo esta limitación se vuelve crítica:**
- Grupos pequeños (n < 5): un único Ct erróneo desplaza sustancialmente la media
- Alta variabilidad biológica (ej. heterogeneidad tumoral, cohortes clínicas)
- Triplicados técnicos donde una réplica diverge > 0,5 Ct de las demás
- Objetivos de baja abundancia con Ct > 35, donde el ruido domina

**Prueba de Grubbs** *(Grubbs 1969)*  
Asume normalidad. Prueba si el valor más extremo es un outlier estadísticamente significativo (p < α). Itera hasta que no se encuentren más outliers.  
Mejor para: valores Ct replicados de un único grupo experimental.

**Método IQR** *(Tukey 1977)*  
No paramétrico. Señala valores fuera de Q1 − k×IQR o Q3 + k×IQR.  
Mejor para: grupos más grandes o distribuciones no normales.

**Importante:** La exclusión de outliers requiere **justificación biológica o técnica**.  
Esta herramienta señala candidatos — la decisión final siempre recae en el investigador.  
Todas las exclusiones se registran y reportan en el PDF.

**Referencias:** Grubbs FE. *Technometrics* 1969; Tukey JW. *Exploratory Data Analysis* 1977;  
Bustin SA et al. *Clin Chem* 2009 (directrices MIQE).
""",

        # ── Cadenas del informe PDF ───────────────────────────────────────────
        "pdf_cover_subtitle": "Informe de análisis de expresión génica por qPCR",
        "pdf_generated": "Generado: {now}",
        "pdf_s1_title": "1. Métodos y configuración del análisis",
        "pdf_s1_calc": "1.1 Métodos de cálculo",
        "pdf_s1_calc_body": "Se aplicaron dos métodos complementarios para el cálculo del fold-change:",
        "pdf_s1_classic": "ΔΔCq clásico (Livak & Schmittgen, 2001): ΔCq = Ct(objetivo) - Ct(referencia);  ΔΔCt = ΔCt(muestra) - ΔCt(control);  Fold-Change = 2^(-ΔΔCt). Asume eficiencias iguales (E ≈ 2,0).",
        "pdf_s1_pfaffl": "Método Pfaffl (Pfaffl, 2001): Ratio = (E_objetivo ^ ΔCq_objetivo) / (E_ref ^ ΔCt_ref). Corrige eficiencias específicas; recomendado si diferencia > 10%.",
        "pdf_s1_norm": "1.2 Normalización",
        "pdf_s1_norm_multi": "Genes de referencia múltiples (n={n}) utilizados. NF calculado como media aritmética de Ct de referencia (geNorm, Vandesompele et al. 2002).",
        "pdf_s1_norm_single": "Un solo gen de referencia utilizado. Las directrices MIQE recomiendan ≥2 genes de referencia.",
        "pdf_s1_eff": "1.3 Eficiencia de amplificación",
        "pdf_s1_eff_range": "Rango aceptable: E = 1,8-2,2 (90-110%). Umbral de diferencia aplicado: {thr}%.",
        "pdf_s1_outlier": "1.4 Detección de valores atípicos",
        "pdf_s1_grubbs": "Prueba de Grubbs (Grubbs 1969), alpha = {alpha}. {n} muestra(s) marcada(s) y confirmada(s) por el usuario.",
        "pdf_s1_iqr": "Método IQR (Tukey 1977), multiplicador k = {k}. {n} muestra(s) excluida(s).",
        "pdf_s1_outlier_warn": "ADVERTENCIA: La exclusión de valores atípicos requiere justificación biológica o técnica.",
        "pdf_s1_outlier_off": "Detección de valores atípicos desactivada para este análisis.",
        "pdf_s2_title": "2. Datos de entrada",
        "pdf_s2_body": "Valores Ct brutos introducidos por el usuario tras el procesamiento de valores atípicos.",
        "pdf_s3_title": "3. Resultados de expresión génica",
        "pdf_s3_body": "Valores de fold-change calculados por ΔΔCq clásico y método Pfaffl. Fold-change > 1 = expresión mayor en el grupo paciente.",
        "pdf_s4_title": "4. Análisis estadístico",
        "pdf_s4_body": "Significación estadística de las diferencias de expresión. Selección automática según normalidad (Shapiro-Wilk) y homogeneidad de varianzas (Levene). Umbral: p < 0,05.",
        "pdf_s4_interp": "Interpretación de los tests estadísticos",
        "pdf_s4_interp_body": "t de Student: grupos normales con varianzas iguales. t de Welch: normales con varianzas desiguales. Mann-Whitney U: no paramétrico. p < 0,05 = expresión diferencial significativa.",
        "pdf_s5_title": "5. Gráficos de distribución Delta Ct",
        "pdf_s5_body": "Distribución de valores ΔCq por gen objetivo. Cada punto = un réplica. Barras horizontales = medias de grupo.",
        "pdf_s6_title": "6. Cómo interpretar los resultados",
        "pdf_s6_fc": "6.1 Interpretación del fold-change",
        "pdf_s6_choose": "6.2 Elección entre ΔΔCq y Pfaffl",
        "pdf_s6_choose_body": "ΔΔCq clásico si: eficiencias 90-110% y diferencia < 10%. Pfaffl si: diferencia > 10%. Reportar siempre ambos valores.",
        "pdf_s6_stat": "6.3 Justificación de la selección del test",
        "pdf_s6_stat_body": "Normalidad: Shapiro-Wilk (n < 50). Homogeneidad: Levene. Paramétrico/varianzas iguales: t de Student. Desiguales: Welch. No normal: Mann-Whitney U.",
        "pdf_s7_title": "7. Referencias",
        "pdf_fc_interp_header": ["Fold-Change", "ΔΔCq", "Interpretación", "Significado biológico"],
        "pdf_fc_interp_rows": [
            [">2,0", "<-1,0", "Fuerte sobreexpresión", "Considerar biológicamente relevante"],
            ["1,5-2,0", "-1,0 a -0,58", "Sobreexpresión moderada", "Puede ser relevante"],
            ["1,0-1,5", "-0,58 a 0", "Sobreexpresión débil", "Probablemente no significativo solo"],
            ["1,0", "0", "Sin cambio", "Sin expresión diferencial"],
            ["0,67-1,0", "0 a 0,58", "Subexpresión débil", "Probablemente no significativo solo"],
            ["0,5-0,67", "0,58 a 1,0", "Subexpresión moderada", "Puede ser relevante"],
            ["<0,5", ">1,0", "Fuerte subexpresión", "Considerar biológicamente relevante"],
        ],
        "pdf_stat_note": "Nota: Evaluar conjuntamente la significación estadística y biológica.",
        "pdf_summary_param": "Parámetro",
        "pdf_summary_val": "Valor",
        "pdf_summary_genes": "Genes objetivo analizados",
        "pdf_summary_groups": "Grupos de pacientes",
        "pdf_summary_samples": "Muestras totales",
        "pdf_summary_excluded": "Muestras excluidas",
        "pdf_summary_tests": "comparaciones",
        "pdf_summary_norm": "Método de normalización",
        "pdf_summary_norm_multi": "geNorm NF",
        "pdf_summary_norm_single": "Gen de referencia único",
        "pdf_summary_methods": "Métodos de cálculo",
        "pdf_summary_methods_val": "ΔΔCq clásico + Pfaffl",
        "pdf_disclaimer": "Este informe fue generado automáticamente por GeneQuantify siguiendo las directrices MIQE.",
        "pdf_footer": "GeneQuantify — Solo para investigación y educación. No validado para diagnóstico clínico.",
        "pdf_fig1": "Figura 1. Comparación fold-change: ΔΔCq clásico vs Pfaffl. Línea discontinua y=1 = sin cambio.",
        "pdf_fig2": "Figura 2. Valores p de todas las comparaciones. Barras rojas = significativo (p < 0,05).",
        "pdf_fig3": "Figura. Distribución ΔCq para {gene}. Puntos = réplicas; barras = medias de grupo.",
        "pdf_nochange": "Sin cambio",
        "pdf_stat_cols": ["Gen objetivo", "Comparación", "Tipo de test", "Método", "Valor p", "Significación"],
        "pdf_res_cols": ["Gen objetivo", "Grupo", "ΔCq Control", "ΔCq Muestra", "ΔΔCq", "2^(-ΔΔCq)", "Ratio Pfaffl", "Regulación", "E objetivo", "E ref"],
        "pdf_eff_cols": ["Gen", "E (objetivo)", "Eff% (objetivo)", "E (ref)", "Eff% (ref)", "Dif%", "Estado"],
        "pdf_eff_ok": "OK",
        "pdf_eff_warn": "ADVERTENCIA: usar Pfaffl",
        "pdf_outlier_col": "Valor atípico excluido",
        "pdf_contact": "Contacto: [email removed]",
        "pdf_ready": "{n} registros listos — puede generar el PDF.",
        # RDML / RDES import
        "rdml_expander":        "📂 Importar archivo RDML / RDES",
        "rdml_description":     "Cargue un archivo **RDML** (`.rdml`) o **RDES** (`.tsv`/`.csv`/`.txt`) para rellenar automáticamente los valores Cq.",
        "rdml_uploader":        "Seleccionar archivo",
        "rdml_uploader_help":   "RDML: Bio-Rad CFX, Roche LightCycler, etc.  RDES: tabla separada por tabulaciones.",
        "rdml_success":         "✅ Archivo {fmt} cargado — {n} reacciones encontradas.",
        "rdml_error":           "❌ Error al analizar {fmt}: {err}",
        "rdml_preview":         "Vista previa de los datos analizados",
        "rdml_step1":           "**Paso 1 — Etiquete su grupo de control**",
        "rdml_ctrl_label":      "Nombre(s) de muestra de control (subcadenas separadas por comas)",
        "rdml_ctrl_help":       "Cualquier muestra cuyo nombre contenga este texto se tratará como Control.",
        "rdml_step2":           "**Paso 2 — Etiquete sus grupos de pacientes**",
        "rdml_n_pat":           "Número de grupos de pacientes",
        "rdml_pat_label":       "Nombre(s) de muestra del grupo de pacientes {i}",
        "rdml_pat_help":        "Subcadenas separadas por comas. Todas las muestras coincidentes se agruparán.",
        "rdml_apply":           "✅ Aplicar importación {fmt} a la entrada de datos",
        "rdml_apply_success":   "✅ {n} valores Cq cargados en la pestaña de entrada. ¡Revise y ajuste si es necesario!",
        "rdml_apply_warning":   "⚠️ No se mapearon valores. Compruebe que sus etiquetas coinciden con los nombres de muestra de la vista previa.",
    },

    "ar": {
        "title": "🧬 جين كوانتيفاي: تحليل التعبير الجيني وتغير عدد النسخ (CNV)",
        "tab_data": "إدخال البيانات",
        "tab_results": "النتائج",
        "tab_report": "التقرير",
        "subtitle": "تم تطويره بواسطة ب. يالجنكايا",
        "patient_data_header": "📊 إدخال بيانات مجموعة المرضى ومجموعة التحكم",
        "num_target_genes": "🔹 إدخال عدد الجينات المستهدفة",
        "num_patient_groups": "🔹 إدخال عدد مجموعات المرضى",
        "sample_number": "رقم العينة",
        "Grup": "مجموعة",
        "x_axis_title": "اسم المجموعة",
        "ct_value": "قيمة Cq",
        "reference_ct": "قيمة Ct المرجعية",
        "delta_ct_control": "ΔCq (التحكم)",
        "delta_ct_patient": "ΔCq (المريض)",
        "warning_empty_input": "⚠️ تحذير: أدخل البيانات واحدًا تلو الآخر أو انسخها دون خلايا فارغة من Excel.",
        "download_csv": "📥 تحميل CSV",
        "generate_pdf": "📥 إعداد تقرير PDF",
        "pdf_report": "تقرير تحليل التعبير الجيني",
        "nil_mine": "📊 النتائج",
        "gr_tbl": "📋 جدول بيانات الإدخال",
        "control_group": "🧬 مجموعة التحكم",
        "ctrl_trgt_ct": "🟦 قيم Ct الجين المستهدف {i} لمجموعة التحكم",
        "ctrl_ref_ct": "🟦 قيم Ct الجين المرجعي {i} لمجموعة التحكم",
        "hst_trgt_ct": "🩸 قيم Ct الجين المستهدف {j} لمجموعة المرضى",
        "hst_ref_ct": "🩸 قيم Ct الجين المرجعي {j} لمجموعة المرضى",
        "warning_control_ct": "⚠️ تحذير: يجب إدخال بيانات مجموعة التحكم {i} سطرًا بسطر أو نسخها من Excel دون خلايا فارغة.",
        "warning_patient_cq": "⚠️ تحذير: أدخل قيم Ct لمجموعة المرضى سطرًا بسطر أو انسخها من Excel دون خلايا فارغة.",
        "target_gene": "الجين المستهدف",
        "reference_gene": "الجين المرجعي",
        "target_ct": "قيمة Ct الجين المستهدف", 
        "distribution_graph": "رسم بياني للتوزيع",
        "error_missing_control_data": "⚠️ خطأ: بيانات مفقودة للجين المستهدف {i} في مجموعة التحكم!",
        "control_group_avg": "متوسط مجموعة التحكم",
        "avg": "متوسط",
        "control": "التحكم",
        "sample": "عينة",
        "patient": "مريض",
        "delta_ct_distribution": "توزيع ΔCq",
        "delta_ct_value": "قيمة ΔCq",
        "parametric": "معلمي",
        "non_parametric": "غير معلمي",
        "t_test": "اختبار t",
        "mann_whitney_u_test": "اختبار مان-ويتني U",
        "welch_t_test": "اختبار ويلش t",
        "significant": "مهم",
        "insignificant": "غير مهم",
        "test_type": "نوع الاختبار",
        "test_method": "طريقة الاختبار",
        "test_pvalue": "قيمة P للاختبار",
        "significance": "الدلالة",
        "delta_delta_ct": "ΔΔCq",
        "gene_expression_change": "تغيير التعبير الجيني (2^(-ΔΔCq))",
        "regulation_status": "حالة التنظيم",
        "no_change": "لا تغيير",
        "upregulated": "مرتفع التنظيم",
        "downregulated": "منخفض التنظيم",
        "report_title": "تقرير تحليل التعبير الجيني",
        "input_data_table": "جدول بيانات الإدخال",
        "results": "النتائج",
        "statistical_results": "📈 النتائج الإحصائية",
        "statistics": "النتائج الإحصائية",
        "statistical_evaluation": "التقييم الإحصائي",
        "target_gene": "الجين المستهدف",
        "patient_group": "🩸 مجموعة المرضى",
        "expression_change": "تغيير التعبير الجيني",
        "generate_pdf": "توليد تقرير PDF",
        "pdf_report": "تقرير التعبير الجيني",
        "error_no_data": "لم يتم العثور على بيانات، لم يتم إنشاء التقرير PDF.",
        # Efficiency translations
        "efficiency_header": "🔬 التحقق من كفاءة التضخيم",
        "efficiency_method": "طريقة إدخال الكفاءة",
        "efficiency_manual": "إدخال قيمة E يدويًا",
        "efficiency_slope": "الحساب من الانحدار",
        "efficiency_target_label": "كفاءة الجين المستهدف {i} (E)",
        "efficiency_ref_label": "كفاءة الجين المرجعي {i} (E)",
        "efficiency_target_slope_label": "انحدار الجين المستهدف {i}",
        "efficiency_ref_slope_label": "انحدار الجين المرجعي {i}",
        "efficiency_threshold": "عتبة فرق الكفاءة المقبول (%)",
        "efficiency_ok": "✅ فرق الكفاءة مقبول ({diff:.1f}%)",
        "efficiency_warning": "⚠️ فرق الكفاءة يتجاوز العتبة ({diff:.1f}%) — قد لا تكون طريقة ΔΔCq موثوقة!",
        "efficiency_target_pct": "كفاءة الجين المستهدف",
        "efficiency_ref_pct": "كفاءة الجين المرجعي",
        "efficiency_diff": "الفرق",
        "pfaffl_result": "نسبة Pfaffl",
        "pfaffl_header": "نتائج طريقة Pfaffl",
        "classic_ddct": "نتيجة ΔΔCq الكلاسيكية (2^(-ΔΔCq))",
        "pfaffl_ratio": "نسبة Pfaffl",
        "method_comparison": "📊 مقارنة الطرق",
        "efficiency_note": "ملاحظة: E=2.0 تمثل الكفاءة المثالية (100%). النطاق المقبول: 1.8–2.2 (90–110%)",
        "statistical_explanation": (
            "أثناء عملية التقييم الإحصائي، تم تحليل توزيع البيانات باستخدام اختبار شابيرو-ويلك. "
            "إذا تم تحقيق التوزيع الطبيعي، تم التحقق من تجانس التباين بين المجموعات باستخدام اختبار ليفين. "
            "إذا كانت التباين متساويًا، تم تطبيق اختبار t للعينة المستقلة، وإذا لم يكن كذلك، تم استخدام اختبار t ويلش. "
            "إذا لم يتم تحقيق التوزيع الطبيعي، تم تطبيق اختبار مان-ويتني U غير المعلمي. "
            "تم تحديد الدلالة باستخدام المعيار p < 0.05. "
            "للاقتراحات والدعم، بورهانيتين يالجنكايا - البريد الإلكتروني: [email removed]"
        ),
        "outlier_section_title": "### 🔍 إعدادات اكتشاف القيم الشاذة",
        "outlier_enable": "تفعيل اكتشاف القيم الشاذة",
        "outlier_enable_help": "يكتشف قيم Ct المتطرفة إحصائياً التي قد تعكس أخطاء تقنية.",
        "outlier_method_label": "طريقة الاكتشاف",
        "outlier_method_help": "Grubbs: للبيانات الموزعة طبيعياً. IQR: غير معلمي، قوي للتوزيعات غير المتماثلة.",
        "outlier_alpha_label": "مستوى الدلالة (α)",
        "outlier_alpha_help": "α = 0.05 هو المعيار. α أقل = أكثر تحفظاً.",
        "outlier_iqr_label": "مُضاعف IQR (k)",
        "outlier_iqr_help": "k=1.5 = حدود Tukey القياسية. k=3.0 = القيم الشاذة الشديدة فقط.",
        "outlier_expander": "ℹ️ حول اكتشاف القيم الشاذة في qPCR",
        "grubbs_info": "ℹ️ **متطلبات اختبار Grubbs:** الحد الأدنى **n ≥ 3** مكررات لكل مجموعة. عتبة الأهمية: **α = {alpha:.2f}**. يفترض الاختبار التوزيع الطبيعي؛ لـ n < 8، لا يمكن تقييم الطبيعية بشكل موثوق. يُنصح بتطبيق الاختبار على **قيم Cq الخام** (قبل التطبيع).",
        "outlier_excluded_no": "لا",
        "outlier_excluded_yes": "نعم",
        # Outlier stage selector
        "outlier_stage_label": "🔬 مرحلة اكتشاف القيم الشاذة",
        "outlier_stage_raw": "Ct الخام — قبل التطبيع (موصى به)",
        "outlier_stage_dct": "ΔCq — بعد التطبيع (السلوك السابق)",
        "outlier_stage_help": (
            "**Ct الخام (موصى به):** يتم اكتشاف القيم الشاذة على قيم Ct الخام قبل حساب ΔCq. "
            "يُطبَّق بشكل منفصل على الجين المستهدف وكل جين مرجعي.\n\n"
            "**ΔCq:** الاكتشاف بعد التطبيع (السلوك الأصلي)."
        ),
        # Distribution plot mode selector
        "dist_plot_mode_label": "📊 مخطط التوزيع — وضع العرض",
        "dist_plot_rq":   "RQ (2^-ΔCq)  — موصى به",
        "dist_plot_dct":  "ΔCq  — القيم المطبَّعة الخام",
        "dist_plot_ddct": "ΔΔCq  — بالنسبة لمتوسط المجموعة الضابطة",
        "dist_plot_help": (
            "**RQ (موصى به):** يحوّل ΔCq إلى 2^(-ΔCt). قيمة أعلى = تعبير أعلى.\n\n"
            "**ΔCq:** قيم لوغاريتمية خام. مفيد للتحقق من توزيع البيانات.\n\n"
            "**ΔΔCq:** ΔCq لكل عينة ناقص متوسط مجموعة التحكم."
        ),
        "unequal_n_warning": (
            "⚠️ **تم اكتشاف أعداد متكررة غير متساوية — {group}:**  \n"
            "{details}  \nسيستمر التحليل باستخدام **أقصر طول مشترك (n={min_n})**.  \n"
            "يرجى التحقق من بيانات الإدخال."
        ),
        # Sidebar
        "sidebar_load_example": "📂 تحميل البيانات النموذجية",
        "sidebar_example_loaded": "✅ تم تحميل البيانات النموذجية! انتقل إلى تبويب إدخال البيانات.",
        "sidebar_desktop_title": "### 💻 تطبيق سطح المكتب",
        "sidebar_desktop_btn": "⬇️ تنزيل تطبيق سطح المكتب",
        "sidebar_opensource_title": "### 🔓 مفتوح المصدر",
        "sidebar_opensource_body": "GeneQuantify مفتوح المصدر (GPL-3.0).  \nالكود المصدري متاح على GitHub:",
        "sidebar_github_btn": "⭐ عرض الكود المصدري على GitHub",
        "sidebar_scenarios_title": "📋 تحميل سيناريو التحقق",
        "sidebar_scenario_select": "اختر سيناريو",
        "sidebar_load_scenario_btn": "▶ تحميل السيناريو",
        "sidebar_scenario_loaded": "✅ تم تحميل {s}! انتقل إلى تبويب إدخال البيانات.",
        "outlier_excluded_no": "لا",
        "outlier_excluded_yes": "نعم",
        "stat_decision_title": "🔬 القرار الإحصائي",
        "stat_decision_steps": "**اختيار الاختبار خطوة بخطوة:**",
        "stat_shapiro_title": "**1. اختبار شابيرو-ويلك للتوزيع الطبيعي**",
        "stat_normal": "طبيعي",
        "stat_nonnormal": "غير طبيعي",
        "stat_levene_title": "**2. اختبار ليفين لتجانس التباين**",
        "stat_levene_skipped": "**2. اختبار ليفين** — *تم تخطيه* (لم يتحقق التوزيع الطبيعي؛ سيُستخدم اختبار غير معلمي)",
        "stat_equal_var": "تبايانات متساوية",
        "stat_unequal_var": "تبايانات غير متساوية",
        "stat_selected_test": "**3. الاختبار المختار:**",
        "stat_reason": "**السبب:**",
        "stat_result": "**النتيجة:**",
        "stat_reason_nonnormal": "توزيع غير طبيعي في مجموعة واحدة أو كلتيهما",
        "stat_reason_normal_equal": "كلا المجموعتين طبيعيتان + تبايانات متساوية",
        "stat_reason_normal_unequal": "كلا المجموعتين طبيعيتان + تبايانات غير متساوية (Levene p < 0.05)",
        "stat_multigroup_note": "⚠️ ملاحظة: مع ≥ 3 مجموعات، راجع قسم **المقارنة متعددة المجموعات** أدناه لاختبار ANOVA / كروسكال-واليس.",
        "multigroup_title": "## 📊 تحليل مقارنة متعددة المجموعات",
        "multigroup_expander": "ℹ️ حول التحليل الإحصائي متعدد المجموعات",
        "multigroup_omnibus_test": "اختبار شامل",
        "multigroup_pvalue": "قيمة p",
        "multigroup_result": "النتيجة",
        "multigroup_significant": "دال",
        "multigroup_not_significant": "غير دال",
        "multigroup_omnibus_ns": "ℹ️ الاختبار الشامل **غير دال** (p ≥ 0.05). المقارنات البعدية معروضة للاطلاع فقط.",
        "multigroup_posthoc_label": "**ما بعد الاختبار:**",
        "multigroup_dl_button": "📥 تحميل نتائج ما بعد الاختبار —",
        "multigroup_2group_note": "ℹ️ **تحليل متعدد المجموعات غير قابل للتطبيق:** تم الكشف عن مجموعتين فقط (مجموعة التحكم + مجموعة مرضى واحدة).",
        "multigroup_decision_normal_equal": "✅ توزيع طبيعي + تبايانات متساوية → **ANOVA أحادي الاتجاه + Tukey HSD**",
        "multigroup_decision_normal_unequal": "⚠️ توزيع طبيعي + **تبايانات غير متساوية** → **Welch ANOVA + Games-Howell**",
        "multigroup_decision_nonnormal": "⚠️ **توزيع غير طبيعي** → **كروسكال-واليس + Dunn**",
        "multigene_title": "### 🧬 تصحيح المقارنات المتعددة متعدد الجينات",
        "multigene_expander": "ℹ️ لماذا هذا ضروري؟",
        "multigene_sig_raw": "دال (خام)",
        "multigene_sig_bonf": "دال (بونفيروني)",
        "multigene_sig_fdr": "دال (FDR B-H)",
        "multigene_warning": "⚠️ بعد التصحيح، {lost} نتيجة لم تعد دالة بعد تعديل FDR. أبلغ عن قيم p المصححة كنتائج رئيسية.",
        "multigene_success": "✅ جميع {n} النتائج الدالة لا تزال دالة بعد تصحيح FDR.",
        "multigene_no_sig": "لم يتم اكتشاف نتائج زوجية دالة (p خام < 0.05).",
        "multigene_dl_button": "📥 تحميل قيم p المصححة (CSV)",
        "multigene_chart_title": "تصحيح قيمة p متعدد الجينات: خام / بونفيروني / FDR",
        "multigene_fc_chart_title": "مقارنة التعبير الجيني المتعدد",
        "multigene_1gene_note": "ℹ️ **تصحيح متعدد الجينات:** تم تحليل جين مستهدف واحد فقط — التصحيح غير قابل للتطبيق.",
        "multigene_no_data": "لا توجد قيم p بعد — أدخل البيانات أعلاه.",
        "ref_gene_section_title": "### 📚 إعدادات الجين المرجعي",
        "ref_gene_num_label": "عدد الجينات المرجعية لكل جين مستهدف",
        "ref_gene_num_help": "توصي إرشادات MIQE بـ ≥2 جين مرجعي معتمد لتطبيع قوي.",
        "ref_gene_1_warning": "⚠️ **ملاحظة منهجية:** استخدام جين مرجعي واحد يحد من متانة التطبيع. توصي إرشادات MIQE (Bustin et al. 2009) بـ **≥2 جين مرجعي معتمد** مع تقييم الاستقرار (geNorm/NormFinder).",
        "ref_gene_multi_success": "✅ تم اختيار {n} جينات مرجعية. سيتم حساب التطبيع بالوسط الهندسي وقيمة M لـ geNorm تلقائياً.",
        "ref_gene_expander": "ℹ️ حول التطبيع متعدد المراجع",
        "sc_expander": "📐 حاسبة المنحنى المعياري — احسب E من سلسلة التخفيف",
        "sc_gene_label": "الجين / تسمية البادئ",
        "sc_num_points": "عدد نقاط التخفيف",
        "sc_dilution_factor_label": "**عامل التخفيف** (مثال: 10 للتخفيف العشري)",
        "sc_dilution_factor_input": "عامل التخفيف",
        "sc_start_conc_label": "**التركيز الابتدائي** (وحدات اعتباطية، مثال: 1)",
        "sc_start_conc_input": "التركيز الابتدائي",
        "sc_enter_ct": "**أدخل متوسط Cq لكل تخفيف:**",
        "sc_calc_button": "📊 احسب الكفاءة",
        "sc_slope": "الميل",
        "sc_e_value": "قيمة E",
        "sc_efficiency_pct": "الكفاءة %",
        "sc_excellent": "✅ ممتاز! E={e:.4f} ({pct:.1f}%)، R²={r2:.4f} — استخدم هذه القيمة في قسم الكفاءة أدناه.",
        "sc_warning_r2": "⚠️ E مقبولة ({pct:.1f}%) لكن R²={r2:.4f} < 0.99 — تحقق من سلسلة التخفيف.",
        "sc_error_range": "❌ E={e:.4f} ({pct:.1f}%) خارج النطاق المقبول (90–110%). راجع تصميم البادئ أو سلسلة التخفيف.",
        "sc_chart_title": "المنحنى المعياري — {label} | E={e:.4f} ({pct:.1f}%)، R²={r2:.4f}",
        "sc_xaxis": "log₁₀(التركيز)",
        "sc_data_points": "نقاط البيانات",
        "sc_copy_hint": "💡 انسخ الميل **{slope:.4f}** أو قيمة E **{e:.4f}** في حقول الكفاءة أدناه.",
        "sc_description": """\
أدخل قيم Ct لتخفيفاتك التسلسلية أدناه. سيطبق الحاسب انحداراً خطياً ويحسب الميل وR² وكفاءة التضخيم تلقائياً.

**كيفية الاستخدام:**  
1. قم بتشغيل qPCR على تخفيفات تسلسلية (مثل غير مخفف، 1:10، 1:100، 1:1000، 1:10000)  
2. أدخل متوسط Ct لكل تخفيف  
3. اقرأ الميل وE وR²  
""",
        "ref_multi_description": """\
**التطبيع بالوسط الهندسي** (Vandesompele et al. 2002)  
عامل التطبيع (NF) هو المتوسط الحسابي لقيم Ct عبر جميع الجينات المرجعية لكل عينة،  
وهو ما يتوافق مع الوسط الهندسي لمستويات تعبيرها.  
`NF_عينة = متوسط(Ct_ref1, Ct_ref2, ..., Ct_refN)` لكل عينة  
`ΔCq = Ct_المستهدف − NF`

**قيمة M لـ geNorm** (درجة الاستقرار)  
لكل جين مرجعي، M = متوسط الانحراف المعياري للنسب اللوغاريتمية مقابل جميع الجينات المرجعية الأخرى.  
**M أقل = أكثر استقراراً.** العتبة الموصى بها من MIQE: M < 0.5 (صارم) أو M < 1.0 (مقبول).

**CV (معامل الاختلاف)**  
`CV = (الانحراف المعياري / المتوسط) × 100%` لقيم Ct الخام عبر جميع العينات.  
CV أقل يشير إلى تباين أقل واستقرار أفضل كمرجع.

**مرجع:** Vandesompele J et al. *Genome Biology* 2002; Bustin SA et al. *Clin Chem* 2009 (MIQE).
""",
        "outlier_description": """\
**لماذا يهم اكتشاف القيم الشاذة في qPCR**

التباين التقني متأصل في qPCR: أخطاء السحب بالماصة، وتكوين الفقاعات، وانتقال المثبطات، أو تباين جودة RNA يمكن أن تنتج قيم Ct غير متسقة إحصائياً مع بقية مجموعة الطبعات.  
تضمين هذه القيم يضخم التباين، ويحيز المتوسطات، ويمكن أن يؤدي إلى استنتاجات خاطئة — خاصة في مجموعات البيانات السريرية ذات الأحجام الصغيرة.

**عندما تصبح هذه القيود حرجة:**
- مجموعات صغيرة (n < 5): Ct واحد خاطئ يزيح المتوسط بشكل كبير
- تباين بيولوجي عالٍ (مثل عدم تجانس الورم، الدراسات السريرية)
- طبعات ثلاثية تقنية حيث تنحرف طبعة واحدة > 0.5 Ct عن الأخريات
- أهداف منخفضة الوفرة مع Ct > 35، حيث يسود الضوضاء

**اختبار Grubbs** *(Grubbs 1969)*  
يفترض التوزيع الطبيعي. يختبر ما إذا كانت القيمة الأكثر تطرفاً تمثل قيمة شاذة ذات دلالة إحصائية (p < α). يتكرر حتى لا يجد المزيد من القيم الشاذة.  
الأفضل لـ: قيم Ct المكررة من مجموعة تجريبية واحدة.

**طريقة IQR** *(Tukey 1977)*  
غير معلمية. تعلم القيم خارج Q1 − k×IQR أو Q3 + k×IQR.  
الأفضل لـ: مجموعات أكبر أو توزيعات غير طبيعية.

**مهم:** يتطلب استبعاد القيم الشاذة **مبرراً بيولوجياً أو تقنياً**.  
تُعلم هذه الأداة المرشحين — القرار النهائي يعود دائماً للباحث.  
يتم تسجيل جميع الاستبعادات والإبلاغ عنها في تقرير PDF.

**المراجع:** Grubbs FE. *Technometrics* 1969; Tukey JW. *Exploratory Data Analysis* 1977;  
Bustin SA et al. *Clin Chem* 2009 (إرشادات MIQE).
""",

        # ── سلاسل تقرير PDF ───────────────────────────────────────────────────
        "pdf_cover_subtitle": "تقرير تحليل التعبير الجيني بـ qPCR",
        "pdf_generated": "تم الإنشاء: {now}",
        "pdf_s1_title": "1. الطرق وإعدادات التحليل",
        "pdf_s1_calc": "1.1 طرق الحساب",
        "pdf_s1_calc_body": "طُبِّقت طريقتان متكاملتان لحساب نسبة التضخيم:",
        "pdf_s1_classic": "طريقة ΔΔCq الكلاسيكية: نسبة التضخيم = 2^(-ΔΔCq). تفترض كفاءة متساوية.",
        "pdf_s1_pfaffl": "طريقة Pfaffl: النسبة = (E_الهدف ^ ΔCq_الهدف) / (E_مرجع ^ ΔCt_مرجع). موصى بها عند اختلاف الكفاءة > 10%.",
        "pdf_s1_norm": "1.2 التطبيع",
        "pdf_s1_norm_multi": "استُخدمت جينات مرجعية متعددة (n={n}) (geNorm, Vandesompele et al. 2002).",
        "pdf_s1_norm_single": "استُخدم جين مرجعي واحد. توصي MIQE باستخدام ≥2 جين.",
        "pdf_s1_eff": "1.3 كفاءة التضخيم",
        "pdf_s1_eff_range": "النطاق المقبول: E = 1.8-2.2 (90-110%). عتبة الفارق: {thr}%.",
        "pdf_s1_outlier": "1.4 اكتشاف القيم الشاذة",
        "pdf_s1_grubbs": "اختبار Grubbs (1969) عند alpha = {alpha}. {n} عينة مستبعدة.",
        "pdf_s1_iqr": "طريقة IQR (Tukey 1977) بمعامل k = {k}. {n} عينة مستبعدة.",
        "pdf_s1_outlier_warn": "تحذير: يستلزم الاستبعاد مبرراً بيولوجياً أو تقنياً.",
        "pdf_s1_outlier_off": "تم تعطيل اكتشاف القيم الشاذة.",
        "pdf_s2_title": "2. بيانات الإدخال",
        "pdf_s2_body": "قيم Ct الخام بعد معالجة القيم الشاذة.",
        "pdf_s3_title": "3. نتائج التعبير الجيني",
        "pdf_s3_body": "نسب التضخيم المحسوبة بطريقتي ΔΔCq الكلاسيكية و Pfaffl.",
        "pdf_s4_title": "4. التحليل الإحصائي",
        "pdf_s4_body": "الدلالة الإحصائية. اختيار الاختبار تلقائياً (Shapiro-Wilk، Levene). p < 0.05.",
        "pdf_s4_interp": "تفسير الاختبارات",
        "pdf_s4_interp_body": "t للطلاب: متساويا التباين. Welch: غير متساويا التباين. Mann-Whitney U: لامعلمي.",
        "pdf_s5_title": "5. مخططات توزيع Delta Ct",
        "pdf_s5_body": "توزيع قيم ΔCq. كل نقطة = مكرر. الأشرطة = المتوسطات.",
        "pdf_s6_title": "6. تفسير النتائج",
        "pdf_s6_fc": "6.1 تفسير نسبة التضخيم",
        "pdf_s6_choose": "6.2 الاختيار بين ΔΔCq و Pfaffl",
        "pdf_s6_choose_body": "ΔΔCq إذا كانت الكفاءتان 90-110% والفارق < 10%. Pfaffl إذا كان > 10%.",
        "pdf_s6_stat": "6.3 مبررات اختيار الاختبار",
        "pdf_s6_stat_body": "التوزيع الطبيعي: Shapiro-Wilk. تجانس التباين: Levene. Student/Welch/Mann-Whitney حسب النتيجة.",
        "pdf_s7_title": "7. المراجع",
        "pdf_fc_interp_header": ["نسبة التضخيم", "ΔΔCq", "التفسير", "الأهمية البيولوجية"],
        "pdf_fc_interp_rows": [
            [">2.0", "<-1.0", "زيادة تعبير قوية", "مهم بيولوجياً"],
            ["1.5-2.0", "-1.0 إلى -0.58", "زيادة معتدلة", "قد يكون مهماً"],
            ["1.0-1.5", "-0.58 إلى 0", "زيادة طفيفة", "غير مهم منفرداً"],
            ["1.0", "0", "لا تغيير", "لا تعبير تفاضلي"],
            ["0.67-1.0", "0 إلى 0.58", "انخفاض طفيف", "غير مهم منفرداً"],
            ["0.5-0.67", "0.58 إلى 1.0", "انخفاض معتدل", "قد يكون مهماً"],
            ["<0.5", ">1.0", "انخفاض قوي", "مهم بيولوجياً"],
        ],
        "pdf_stat_note": "ملاحظة: يجب تقييم الدلالة الإحصائية والبيولوجية معاً.",
        "pdf_summary_param": "المعلمة", "pdf_summary_val": "القيمة",
        "pdf_summary_genes": "الجينات الهدف", "pdf_summary_groups": "مجموعات المرضى",
        "pdf_summary_samples": "إجمالي العينات", "pdf_summary_excluded": "العينات المستبعدة",
        "pdf_summary_tests": "مقارنات", "pdf_summary_norm": "طريقة التطبيع",
        "pdf_summary_norm_multi": "geNorm NF", "pdf_summary_norm_single": "جين مرجعي واحد",
        "pdf_summary_methods": "طرق الحساب", "pdf_summary_methods_val": "ΔΔCq الكلاسيكي + Pfaffl",
        "pdf_disclaimer": "تم إنشاء هذا التقرير تلقائياً بواسطة GeneQuantify وفق إرشادات MIQE.",
        "pdf_footer": "GeneQuantify — للبحث والتعليم فقط. غير مُصادَق لأغراض التشخيص السريري.",
        "pdf_fig1": "شكل 1. مقارنة نسبة التضخيم. الخط المتقطع y=1 = لا تغيير.",
        "pdf_fig2": "شكل 2. قيم p. الأشرطة الحمراء = دالة (p < 0.05).",
        "pdf_fig3": "شكل. توزيع ΔCq لـ {gene}.",
        "pdf_nochange": "لا تغيير",
        "pdf_stat_cols": ["الجين الهدف", "المقارنة", "نوع الاختبار", "الاختبار", "قيمة p", "الدلالة"],
        "pdf_res_cols": ["الجين الهدف", "المجموعة", "ΔCq الضبط", "ΔCq العينة", "ΔΔCq", "2^(-ΔΔCq)", "نسبة Pfaffl", "التنظيم", "E الهدف", "E المرجع"],
        "pdf_eff_cols": ["الجين", "E (الهدف)", "Eff% (الهدف)", "E (المرجع)", "Eff% (المرجع)", "الفارق%", "الحالة"],
        "pdf_eff_ok": "مقبول", "pdf_eff_warn": "تحذير: استخدم Pfaffl",
        "pdf_outlier_col": "قيمة شاذة مستبعدة", "pdf_contact": "التواصل: [email removed]",
        "pdf_ready": "{n} سجلات جاهزة — يمكنك إنشاء تقرير PDF.",
        # RDML / RDES import
        "rdml_expander":        "📂 استيراد ملف RDML / RDES",
        "rdml_description":     "ارفع ملف **RDML** (`.rdml`) أو **RDES** (`.tsv`/`.csv`/`.txt`) لملء قيم Cq تلقائيًا.",
        "rdml_uploader":        "اختر ملفًا",
        "rdml_uploader_help":   "RDML: Bio-Rad CFX، Roche LightCycler، إلخ.  RDES: جدول مفصول بعلامات تبويب.",
        "rdml_success":         "✅ تم تحميل ملف {fmt} — تم العثور على {n} تفاعل.",
        "rdml_error":           "❌ خطأ في تحليل {fmt}: {err}",
        "rdml_preview":         "معاينة البيانات المحللة",
        "rdml_step1":           "**الخطوة 1 — حدد مجموعة التحكم**",
        "rdml_ctrl_label":      "اسم (أسماء) عينة التحكم (سلاسل فرعية مفصولة بفواصل)",
        "rdml_ctrl_help":       "أي عينة يحتوي اسمها على هذا النص ستُعامَل كمجموعة تحكم.",
        "rdml_step2":           "**الخطوة 2 — حدد مجموعات المرضى**",
        "rdml_n_pat":           "عدد مجموعات المرضى",
        "rdml_pat_label":       "اسم (أسماء) عينات مجموعة المرضى {i}",
        "rdml_pat_help":        "سلاسل فرعية مفصولة بفواصل. سيتم تجميع جميع العينات المطابقة في هذه المجموعة.",
        "rdml_apply":           "✅ تطبيق استيراد {fmt} على إدخال البيانات",
        "rdml_apply_success":   "✅ تم تحميل {n} قيمة Cq في تبويب إدخال البيانات! انتقل إليه للمراجعة والتعديل.",
        "rdml_apply_warning":   "⚠️ لم يتم تعيين أي قيم. تحقق من أن التسميات تتطابق مع أسماء العينات في المعاينة.",
    }
}

                  
# ═══════════════════════════════════════════════════════════════════════════════
# RDML / RDES SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════════
_t = translations[language_code]

# ──Scenario-based example data loader ────────
st.sidebar.markdown("---")
st.sidebar.markdown(f"### {_t.get('sidebar_scenarios_title', '📋 Load Validation Scenario')}")

# Scenario definitions — all 7 validation datasets from Supplementary Data S1
SCENARIOS = {
    "S1 — Basic (n=3, t-test)": {
        "gene_count": 1, "patient_count": 1, "num_ref_genes": 1,
        "outlier_method": "Grubbs", "outlier_enabled": True,
        "description": "1 gene, 1 group, n=3. Strong upregulation (~4.1x). n<8 → t-test assumed.",
        "control_target_ct_0": "23.15\n22.98\n23.42",
        "control_reference_ct_0_0": "18.22\n18.05\n18.38",
        "sample_target_ct_0_0": "21.05\n20.88\n21.23",
        "sample_reference_ct_0_0_0": "18.15\n17.98\n18.28",
        "target_E_0": 2.0, "ref_E_0": 2.0,
    },
    "S2 — Multi-gene + dual ref (n=4)": {
        "gene_count": 3, "patient_count": 2, "num_ref_genes": 2,
        "outlier_method": "IQR", "outlier_enabled": True,
        "description": "3 genes, 2 groups, n=4. Dual reference (geNorm). Gene 2: Pfaffl recommended (E diff >10%).",
        # Gene 1 control
        "control_target_ct_0": "23.88\n24.12\n23.95\n24.32",
        "control_reference_ct_0_0": "18.32\n18.55\n18.44\n18.68",
        "control_reference_ct_0_1": "19.95\n20.18\n20.05\n20.28",
        # Gene 2 control
        "control_target_ct_1": "19.05\n19.28\n19.15\n19.38",
        "control_reference_ct_1_0": "18.32\n18.55\n18.44\n18.68",
        "control_reference_ct_1_1": "19.95\n20.18\n20.05\n20.28",
        # Gene 3 control
        "control_target_ct_2": "24.92\n25.15\n25.02\n25.28",
        "control_reference_ct_2_0": "18.32\n18.55\n18.44\n18.68",
        "control_reference_ct_2_1": "19.95\n20.18\n20.05\n20.28",
        # Gene 1 Group 1
        "sample_target_ct_0_0": "21.50\n21.82\n21.65\n21.95",
        "sample_reference_ct_0_0_0": "18.35\n18.58\n18.47\n18.70",
        "sample_reference_ct_0_0_1": "19.98\n20.22\n20.08\n20.30",
        # Gene 1 Group 2
        "sample_target_ct_0_1": "22.45\n22.68\n22.55\n22.78",
        "sample_reference_ct_0_1_0": "18.35\n18.58\n18.47\n18.70",
        "sample_reference_ct_0_1_1": "19.98\n20.22\n20.08\n20.30",
        # Gene 2 Group 1
        "sample_target_ct_1_0": "22.10\n22.38\n22.22\n22.48",
        "sample_reference_ct_1_0_0": "18.35\n18.58\n18.47\n18.70",
        "sample_reference_ct_1_0_1": "19.98\n20.22\n20.08\n20.30",
        # Gene 2 Group 2
        "sample_target_ct_1_1": "23.75\n24.02\n23.88\n24.15",
        "sample_reference_ct_1_1_0": "18.35\n18.58\n18.47\n18.70",
        "sample_reference_ct_1_1_1": "19.98\n20.22\n20.08\n20.30",
        # Gene 3 Group 1
        "sample_target_ct_2_0": "25.05\n25.28\n25.15\n25.38",
        "sample_reference_ct_2_0_0": "18.35\n18.58\n18.47\n18.70",
        "sample_reference_ct_2_0_1": "19.98\n20.22\n20.08\n20.30",
        # Gene 3 Group 2
        "sample_target_ct_2_1": "25.02\n25.25\n25.12\n25.35",
        "sample_reference_ct_2_1_0": "18.35\n18.58\n18.47\n18.70",
        "sample_reference_ct_2_1_1": "19.98\n20.22\n20.08\n20.30",
        "target_E_0": 2.0, "ref_E_0": 2.0,
        "target_E_1": 2.103, "ref_E_1": 1.952,
        "target_E_2": 1.99, "ref_E_2": 2.0,
    },
    "S3 — Outlier detection (Grubbs, n=6)": {
        "gene_count": 1, "patient_count": 1, "num_ref_genes": 1,
        "outlier_method": "Grubbs", "outlier_enabled": True, "grubbs_alpha": 0.05,
        "description": "1 gene, 1 group, n=6. Sample 5 is an outlier (Cq=27.82). Grubbs on raw Cq detects it.",
        "control_target_ct_0": "23.12\n22.95\n23.38\n23.05\n27.82\n23.22",
        "control_reference_ct_0_0": "18.15\n17.98\n18.32\n18.08\n18.22\n18.12",
        "sample_target_ct_0_0": "21.05\n20.88\n21.23\n20.95\n21.15\n20.72",
        "sample_reference_ct_0_0_0": "18.15\n17.98\n18.28\n18.05\n18.20\n17.88",
        "target_E_0": 2.0, "ref_E_0": 2.0,
    },
    "S4 — ANOVA 3 groups (n=5)": {
        "gene_count": 1, "patient_count": 3, "num_ref_genes": 1,
        "outlier_method": "Grubbs", "outlier_enabled": True,
        "description": "1 gene, 3 groups, n=5. One-way ANOVA + Tukey HSD. Group 3 = no change.",
        "control_target_ct_0": "24.12\n23.95\n24.38\n24.05\n24.22",
        "control_reference_ct_0_0": "18.50\n18.38\n18.72\n18.42\n18.55",
        # Group 1: mild upregulation
        "sample_target_ct_0_0": "23.28\n23.05\n23.52\n23.18\n23.38",
        "sample_reference_ct_0_0_0": "18.52\n18.40\n18.75\n18.45\n18.58",
        # Group 2: strong upregulation
        "sample_target_ct_0_1": "21.05\n20.88\n21.23\n20.95\n21.15",
        "sample_reference_ct_0_1_0": "18.52\n18.40\n18.75\n18.45\n18.58",
        # Group 3: no change
        "sample_target_ct_0_2": "24.10\n23.92\n24.35\n24.02\n24.18",
        "sample_reference_ct_0_2_0": "18.52\n18.40\n18.75\n18.45\n18.58",
        "target_E_0": 2.0, "ref_E_0": 2.0,
    },
    "S1B — Student t-test (n=8, equal var)": {
        "gene_count": 1, "patient_count": 1, "num_ref_genes": 1,
        "outlier_method": "Grubbs", "outlier_enabled": True,
        "description": "n=8, normal distribution, equal variance → Student t-test. FC ≈ 4.15.",
        "control_target_ct_0": "23.15\n22.98\n23.42\n23.05\n23.28\n22.88\n23.52\n23.18",
        "control_reference_ct_0_0": "18.22\n18.05\n18.38\n18.12\n18.30\n17.95\n18.45\n18.18",
        "sample_target_ct_0_0": "21.05\n20.88\n21.23\n20.95\n21.15\n20.72\n21.38\n21.02",
        "sample_reference_ct_0_0_0": "18.15\n17.98\n18.28\n18.05\n18.20\n17.88\n18.35\n18.10",
        "target_E_0": 2.0, "ref_E_0": 2.0,
    },
    "S1C — Welch t-test (n=8, unequal var)": {
        "gene_count": 1, "patient_count": 1, "num_ref_genes": 1,
        "outlier_method": "Grubbs", "outlier_enabled": True,
        "description": "n=8, normal distribution, unequal variance → Welch t-test. FC ≈ 3.86.",
        "control_target_ct_0": "23.15\n22.98\n23.42\n23.05\n23.28\n22.88\n23.52\n23.18",
        "control_reference_ct_0_0": "18.22\n18.05\n18.38\n18.12\n18.30\n17.95\n18.45\n18.18",
        "sample_target_ct_0_0": "21.20\n20.50\n21.80\n20.85\n21.55\n20.65\n21.90\n20.75",
        "sample_reference_ct_0_0_0": "18.15\n17.98\n18.28\n18.05\n18.20\n17.88\n18.35\n18.10",
        "target_E_0": 2.0, "ref_E_0": 2.0,
    },
    "S1D — Mann-Whitney U (n=8, bimodal)": {
        "gene_count": 1, "patient_count": 1, "num_ref_genes": 1,
        "outlier_method": "Grubbs", "outlier_enabled": True,
        "description": "n=8, bimodal (responder/non-responder) → Mann-Whitney U. FC ≈ 12.43.",
        "control_target_ct_0": "23.15\n22.98\n23.42\n23.05\n23.28\n22.88\n23.52\n23.18",
        "control_reference_ct_0_0": "18.22\n18.05\n18.38\n18.12\n18.30\n17.95\n18.45\n18.18",
        "sample_target_ct_0_0": "20.05\n19.88\n20.23\n17.50\n20.15\n19.72\n20.38\n17.80",
        "sample_reference_ct_0_0_0": "18.15\n17.98\n18.28\n18.05\n18.20\n17.88\n18.35\n18.10",
        "target_E_0": 2.0, "ref_E_0": 2.0,
    },
}

st.sidebar.markdown(
    "<div style='font-size:12px;font-weight:600;color:#1a237e;margin-bottom:2px;'>"
    f"📋 {_t.get('sidebar_scenarios_title','Validation Scenarios')}</div>",
    unsafe_allow_html=True
)
selected_scenario = st.sidebar.selectbox(
    _t.get('sidebar_scenario_select', 'Select scenario'),
    options=["—"] + list(SCENARIOS.keys()),
    key="scenario_selector",
    label_visibility="collapsed"
)

if selected_scenario != "—":
    sc = SCENARIOS[selected_scenario]
    st.sidebar.caption(sc.get("description", ""))
    if st.sidebar.button(_t.get('sidebar_load_scenario_btn', '▶ Load Scenario'), key="load_scenario_btn", use_container_width=True):
        for key, val in sc.items():
            if key == "description":
                continue
            st.session_state[key] = val
        st.sidebar.success(_t.get('sidebar_scenario_loaded', f'✅ {selected_scenario} loaded!').format(s=selected_scenario))

st.sidebar.divider()
with st.sidebar.expander(_t.get("rdml_expander", "📂 Import RDML / RDES"), expanded=False):
    st.markdown(_t.get("rdml_description", "Upload an RDML or RDES file to auto-fill Cq values."))
    imported_file = st.file_uploader(
        _t.get("rdml_uploader", "Choose file"),
        type=["rdml", "tsv", "csv", "txt"],
        key="rdml_rdes_uploader",
        help=_t.get("rdml_uploader_help", "RDML: Bio-Rad CFX, Roche LightCycler, etc.  RDES: tab-separated format."),
    )
    if imported_file is not None:
        file_bytes = imported_file.read()
        fname = imported_file.name.lower()
        if fname.endswith(".rdml"):
            import_df, import_err = parse_rdml(file_bytes)
            fmt_label = "RDML"
        else:
            import_df, import_err = parse_rdes(file_bytes)
            fmt_label = "RDES"
        if import_err:
            st.error(_t.get("rdml_error", "❌ {fmt} parse error: {err}").format(fmt=fmt_label, err=import_err))
            import_df = None
        if import_df is not None:
            st.success(_t.get("rdml_success", "✅ {fmt} file loaded — {n} reactions found.").format(fmt=fmt_label, n=len(import_df)))
            with st.expander(_t.get("rdml_preview", "Preview parsed data"), expanded=False):
                st.dataframe(import_df, use_container_width=True)
            all_samples = sorted(import_df["Sample"].unique())
            st.markdown(_t.get("rdml_step1", "**Step 1 — Label your Control group**"))
            ctrl_label = st.text_input(
                _t.get("rdml_ctrl_label", "Control sample name(s) (comma-separated substrings)"),
                value=", ".join([s for s in all_samples[:1]]),
                key="rdml_ctrl_label_input",
                help=_t.get("rdml_ctrl_help", "Any sample whose name contains this text will be treated as Control.")
            )
            st.markdown(_t.get("rdml_step2", "**Step 2 — Label your Patient groups**"))
            n_pat_grps = st.number_input(
                _t.get("rdml_n_pat", "Number of patient groups"),
                min_value=1, max_value=10, value=1, step=1, key="rdml_n_pat"
            )
            patient_labels = []
            for pg in range(int(n_pat_grps)):
                default_pat = all_samples[pg + 1] if pg + 1 < len(all_samples) else ""
                pat_lbl = st.text_input(
                    _t.get("rdml_pat_label", "Patient group {i} sample name(s)").format(i=pg+1),
                    value=default_pat,
                    key=f"rdml_pat_{pg}",
                    help=_t.get("rdml_pat_help", "Comma-separated substrings.")
                )
                patient_labels.append(pat_lbl)
            if st.button(_t.get("rdml_apply", "✅ Apply {fmt} import to Data Entry").format(fmt=fmt_label), key="rdml_apply_btn"):
                n_filled = apply_import_to_session(import_df, ctrl_label, patient_labels)
                if n_filled > 0:
                    st.success(_t.get("rdml_apply_success", "✅ {n} Cq values loaded!").format(n=n_filled))
                else:
                    st.warning(_t.get("rdml_apply_warning", "⚠️ No values were mapped. Check your labels."))

# ═══════════════════════════════════════════════════════════════════════════════
# ANA BAŞLIK
# ═══════════════════════════════════════════════════════════════════════════════
_title_txt = _t.get('title', '🧬 GeneQuantify')
_sub_txt   = _t.get('subtitle', 'Developed by B. Yalçınkaya')
_title_parts = _title_txt.split(' ', 1)
_header_emoji = _title_parts[0]
_header_title_text = _title_parts[1] if len(_title_parts) > 1 else _title_txt
st.markdown(
    f"""
    <div style="background:linear-gradient(90deg,#1a237e,#3949ab);
                color:white;padding:16px 18px;border-radius:8px;margin-bottom:8px;
                display:flex;align-items:center;gap:12px;">
        <span style="font-size:28px;line-height:1;flex-shrink:0;">{_header_emoji}</span>
        <div style="display:flex;flex-direction:column;justify-content:center;">
            <span style="font-size:20px;font-weight:800;line-height:1.3;">{_header_title_text}</span>
            <span style="font-size:11px;opacity:0.75;margin-top:3px;line-height:1.3;">{_sub_txt}</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

tab_data, tab_results, tab_report = st.tabs([
    f"📥 {_t.get('tab_data', 'Veri Girişi')}",
    f"📊 {_t.get('tab_results', 'Sonuçlar')}",
    f"📄 {_t.get('tab_report', 'Rapor')}",
])

# ─── HELPER FUNCTIONS ─────────────────────────────────────────────────────────
def parse_input_data(input_data):
    values = [x.replace(",", ".").strip() for x in input_data.split() if x.strip()]
    return np.array([float(x) for x in values if x])


def apply_import_to_session(df, ctrl_sample_label, patient_labels):
    """
    Given a parsed DataFrame (columns: Sample, SampleType, Target, TargetType, Cq),
    fill st.session_state keys that GeneQuantify's text_area widgets read from.

    Mapping logic:
      - Rows where SampleType in ('ntc','nac','ntp','std','opt') → skipped
      - ctrl_sample_label: sample name(s) that belong to the control group
        (comma-separated string; matches by substring if needed)
      - patient_labels: list of sample names for each patient group
      - TargetType == 'ref' → reference gene; 'toi' → target gene
    """
    if df is None:
        return 0

    # Clean: drop rows without a Cq value or with Cq == -1
    df = df.dropna(subset=["Cq"]).copy()
    df = df[df["Cq"] != -1.0]

    ctrl_keywords = [s.strip() for s in ctrl_sample_label.split(",") if s.strip()]

    def is_ctrl(sample_name):
        return any(kw.lower() in sample_name.lower() for kw in ctrl_keywords)

    # Separate target genes and reference genes
    targets = sorted(df[df["TargetType"] == "toi"]["Target"].unique())
    refs    = sorted(df[df["TargetType"] == "ref"]["Target"].unique())

    count = 0
    for gene_i, target_name in enumerate(targets):
        tgt_df = df[(df["Target"] == target_name) & (df["TargetType"] == "toi")]

        # Control group — target gene
        ctrl_cqs = tgt_df[tgt_df["Sample"].apply(is_ctrl)]["Cq"].dropna().tolist()
        if ctrl_cqs:
            st.session_state[f"control_target_ct_{gene_i}"] = "\n".join(f"{v:.4f}" for v in ctrl_cqs)
            count += len(ctrl_cqs)

        # Control group — reference genes
        for ref_i, ref_name in enumerate(refs):
            ref_df = df[(df["Target"] == ref_name) & (df["TargetType"] == "ref")]
            ctrl_ref_cqs = ref_df[ref_df["Sample"].apply(is_ctrl)]["Cq"].dropna().tolist()
            if ctrl_ref_cqs:
                st.session_state[f"control_reference_ct_{gene_i}_{ref_i}"] = "\n".join(f"{v:.4f}" for v in ctrl_ref_cqs)
                count += len(ctrl_ref_cqs)

        # Patient groups
        for grp_i, pat_label in enumerate(patient_labels):
            pat_keywords = [s.strip() for s in pat_label.split(",") if s.strip()]

            def is_pat(sample_name, kws=pat_keywords):
                return any(kw.lower() in sample_name.lower() for kw in kws)

            pat_cqs = tgt_df[tgt_df["Sample"].apply(is_pat)]["Cq"].dropna().tolist()
            if pat_cqs:
                st.session_state[f"sample_target_ct_{gene_i}_{grp_i}"] = "\n".join(f"{v:.4f}" for v in pat_cqs)
                count += len(pat_cqs)

            for ref_i, ref_name in enumerate(refs):
                ref_df = df[(df["Target"] == ref_name) & (df["TargetType"] == "ref")]
                pat_ref_cqs = ref_df[ref_df["Sample"].apply(is_pat)]["Cq"].dropna().tolist()
                if pat_ref_cqs:
                    st.session_state[f"sample_reference_ct_{gene_i}_{grp_i}_{ref_i}"] = "\n".join(f"{v:.4f}" for v in pat_ref_cqs)
                    count += len(pat_ref_cqs)
    return count

def compute_genorm_m(ref_ct_matrix):
    n_refs, n_samples = ref_ct_matrix.shape
    if n_refs < 2:
        return np.array([0.0])
    m_values = []
    for i in range(n_refs):
        pairwise_vars = []
        for j in range(n_refs):
            if i == j:
                continue
            ratio = ref_ct_matrix[i] - ref_ct_matrix[j]
            pairwise_vars.append(np.std(ratio, ddof=1) if len(ratio) > 1 else 0.0)
        m_values.append(np.mean(pairwise_vars))
    return np.array(m_values)

def compute_cv(ct_values):
    if len(ct_values) < 2 or np.mean(ct_values) == 0:
        return 0.0
    return (np.std(ct_values, ddof=1) / np.mean(ct_values)) * 100

def geometric_mean_ct(ct_arrays):
    stacked = np.vstack(ct_arrays)
    return np.mean(stacked, axis=0)

# ─── OUTLIER DETECTION FUNCTIONS ─────────────────────────────────────────────
def detect_outliers_grubbs(data, alpha=0.05):
    data = np.array(data, dtype=float)
    n = len(data)
    if n < 3:
        return []
    outlier_indices = []
    working = data.copy()
    original_indices = list(range(n))
    while len(working) >= 3:
        mean_w = np.mean(working)
        std_w  = np.std(working, ddof=1)
        if std_w == 0:
            break
        g_vals = np.abs(working - mean_w) / std_w
        max_idx = np.argmax(g_vals)
        G = g_vals[max_idx]
        t_crit = stats.t.ppf(1 - alpha / (2 * len(working)), df=len(working) - 2)
        G_crit = ((len(working) - 1) / np.sqrt(len(working))) * \
                 np.sqrt(t_crit**2 / (len(working) - 2 + t_crit**2))
        if G > G_crit:
            outlier_indices.append(original_indices[max_idx])
            original_indices.pop(max_idx)
            working = np.delete(working, max_idx)
        else:
            break
    return outlier_indices

def detect_outliers_iqr(data, multiplier=1.5):
    data = np.array(data, dtype=float)
    q1, q3 = np.percentile(data, [25, 75])
    iqr = q3 - q1
    lower = q1 - multiplier * iqr
    upper = q3 + multiplier * iqr
    return [i for i, v in enumerate(data) if v < lower or v > upper]

def render_outlier_ui(data, label, key_prefix, method):
    data = np.array(data, dtype=float)
    if method == "Grubbs":
        detected = detect_outliers_grubbs(data)
    else:
        detected = detect_outliers_iqr(data)
    if not detected:
        return data, []
    st.warning(
        f"⚠️ **Potential outlier(s) detected in {label}** "
        f"({method} test): Sample(s) **{[i+1 for i in detected]}** "
        f"— values: **{[round(data[i], 3) for i in detected]}**\n\n"
        f"Select which samples to exclude from analysis:"
    )
    excluded = []
    for idx in detected:
        confirm = st.checkbox(
            f"Exclude Sample {idx+1}  (Ct = {data[idx]:.3f}) from {label}",
            value=False,
            key=f"{key_prefix}_excl_{idx}"
        )
        if confirm:
            excluded.append(idx)
    if excluded:
        cleaned = np.delete(data, excluded)
        st.info(
            f"ℹ️ {len(excluded)} sample(s) excluded from {label}. "
            f"Remaining n = {len(cleaned)}. "
            f"Excluded values will be flagged in the results table and PDF report."
        )
        return cleaned, excluded
    return data, []

# ─────────────────────────────────────────────────────────────────────────────

input_values_table = []
data = []
stats_data = []

last_control_delta_ct = None
last_gene_index = None

control_group = "Control"
target_gene = _t.get('target_gene', '')
reference_gene = _t.get('reference_gene', '')
ct_value = _t.get('ct_value', '')
patient_group = _t.get('patient_group', '')

# ═══════════════════════════════════════════════════════════════════════════════
# SEKME 1: VERİ GİRİŞİ  (tüm girişler bu tab içinde)
# ═══════════════════════════════════════════════════════════════════════════════

# ── Genel CSS: boşlukları azalt, kartları güzelleştir ─────────────────────────
st.markdown("""
<style>
/* Bölümler arası boşluğu azalt */
/* padding-top ayarı yukarıda (satır ~209) merkezi olarak tanımlı — burada tekrar ezilmiyor */
div[data-testid="stVerticalBlock"] > div { gap: 0.4rem; }
/* st.info kutusunu küçült */
div[data-testid="stAlert"] { padding: 6px 12px !important; font-size: 12px !important; }
/* number_input ve radio margin azalt */
div[data-testid="stNumberInput"] { margin-bottom: 0 !important; }
div[data-testid="stRadio"] { margin-bottom: 0 !important; }
</style>
""", unsafe_allow_html=True)

with tab_data:

    # ── KART 1: Çalışma Tasarımı ──────────────────────────────────────────────
    with st.container(border=True):
        st.markdown(f"**⚙️ {_t.get('tab_data', 'Data Entry')} — Study Design**")
        sd_c1, sd_c2, sd_c3 = st.columns(3)
        with sd_c1:
            num_target_genes = st.number_input(
                _t.get('num_target_genes', '🔹 Target Genes'),
                min_value=1, step=1, key="gene_count",
            )
        with sd_c2:
            num_patient_groups = st.number_input(
                _t.get('num_patient_groups', '🔹 Patient Groups'),
                min_value=1, step=1, key="patient_count",
            )
        with sd_c3:
            num_ref_genes = st.number_input(
                _t.get('ref_gene_num_label', '🔹 Reference Genes'),
                min_value=1, max_value=10, value=1, step=1,
                key="num_ref_genes",
                help=_t.get('ref_gene_num_help', 'MIQE: ≥2 reference genes recommended')
            )
        # Referans gen durumu — tek satır
        if num_ref_genes == 1:
            st.caption(_t.get('ref_gene_1_warning', '⚠️ Single reference gene — MIQE recommends ≥2.').replace("**Methodological note:** ", "").replace("**", ""))
        else:
            st.caption(_t.get('ref_gene_multi_success', '✅ {n} reference genes selected.').format(n=num_ref_genes))
        if num_ref_genes > 1:
            with st.expander(_t.get('ref_gene_expander', 'ℹ️ About multi-reference normalization'), expanded=False):
                st.markdown(_t.get('ref_multi_description', ''))

    # ── KART 2: Aykırı Değer + Stage ─────────────────────────────────────────
    with st.container(border=True):
        st.markdown(f"**🔍 {_t.get('outlier_section_title', 'Outlier Detection').replace('### ', '').replace('🔍 ', '')}**")
        out_c1, out_c2, out_c3 = st.columns([1, 2, 2])
        with out_c1:
            outlier_enabled = st.checkbox(
                _t.get('outlier_enable', 'Enable'),
                value=True, key="outlier_enabled",
                help=_t.get('outlier_enable_help', '')
            )
            outlier_method = st.radio(
                _t.get('outlier_method_label', 'Method'),
                options=["Grubbs", "IQR"], key="outlier_method",
                help=_t.get('outlier_method_help', '')
            )
        with out_c2:
            if outlier_method == "Grubbs":
                grubbs_alpha = st.number_input(
                    _t.get('outlier_alpha_label', 'Significance level (α)'),
                    min_value=0.01, max_value=0.10, value=0.05, step=0.01, format="%.2f",
                    key="grubbs_alpha", help=_t.get('outlier_alpha_help', '')
                )
                iqr_multiplier = 1.5
                st.caption(_t.get('grubbs_info', 'ℹ️ min n ≥ 3, normality assumed').format(alpha=grubbs_alpha))
            else:
                iqr_multiplier = st.number_input(
                    _t.get('outlier_iqr_label', 'IQR multiplier (k)'),
                    min_value=1.0, max_value=3.0, value=1.5, step=0.25, format="%.2f",
                    key="iqr_mult", help=_t.get('outlier_iqr_help', '')
                )
                grubbs_alpha = 0.05
                st.caption("ℹ️ Q1−k×IQR / Q3+k×IQR")
        with out_c3:
            outlier_stage = st.radio(
                _t.get('outlier_stage_label', '🔬 Detection Stage'),
                options=[
                    _t.get('outlier_stage_raw', 'Raw Cq — before normalization (recommended)'),
                    _t.get('outlier_stage_dct', 'ΔCq — after normalization'),
                ],
                index=0, key="outlier_stage",
                help=_t.get('outlier_stage_help', '')
            )
        with st.expander(_t.get('outlier_expander', 'ℹ️ About outlier detection in qPCR'), expanded=False):
            st.markdown(_t.get('outlier_description', ''))

    outlier_on_raw = st.session_state.get("outlier_stage", _t.get('outlier_stage_raw', 'Raw Cq — before normalization (recommended)')) == _t.get('outlier_stage_raw', 'Raw Cq — before normalization (recommended)')

    # ── KART 3: Amplifikasyon Verimliliği ─────────────────────────────────────
    with st.container(border=True):
        st.markdown(f"**🔬 {_t.get('efficiency_header', 'Amplification Efficiency').replace('🔬 ', '')}**")
        eff_c1, eff_c2, eff_c3 = st.columns([2, 2, 3])
        with eff_c1:
            efficiency_method = st.radio(
                _t.get('efficiency_method', 'Input Method'),
                options=[_t.get('efficiency_manual', 'Manual E value'), _t.get('efficiency_slope', 'Calculate from slope')],
                key="eff_method", horizontal=True
            )
        with eff_c2:
            efficiency_threshold = st.number_input(
                _t.get('efficiency_threshold', 'Max diff threshold (%)'),
                min_value=1.0, max_value=50.0, value=10.0, step=0.5, key="eff_threshold",
                help=_t.get('efficiency_note', 'Recommended: 10% (MIQE guidelines).')
            )
        with eff_c3:
            st.caption(_t.get('efficiency_note', 'E=2.0 = perfect (100%). Accepted: 1.8–2.2 (90–110%).'))
        with st.expander(_t.get('ref_gene_expander', 'ℹ️ How to obtain Efficiency (E)').replace('📚 ', ''), expanded=False):
            st.markdown(_t.get('ref_multi_description', '') or
                "**Method 1 — Standard Curve:** `E = 10^(-1 / slope)`  \n"
                "**Method 2 — Software:** LinRegPCR, qBase+, CFX Maestro  \n"
                "**Accepted range:** E = 1.8–2.2 (90–110%)"
            )

    st.divider()

    # ── Standart eğri hesaplayıcı ─────────────────────────────────────────────
    with st.expander(_t.get('sc_expander', ''), expanded=False):
        st.markdown(_t.get('sc_description', ''))
        sc_c1, sc_c2 = st.columns(2)
        with sc_c1:
            sc_gene_label = st.text_input(_t.get('sc_gene_label', ''), value="Target Gene 1", key="sc_label")
            sc_num_points = st.number_input(_t.get('sc_num_points', ''), min_value=3, max_value=10, value=5, step=1, key="sc_npts")
        with sc_c2:
            st.markdown(_t.get('sc_dilution_factor_label', ''))
            sc_dilution_factor = st.number_input(_t.get('sc_dilution_factor_input', ''), min_value=2, max_value=100, value=10, step=1, key="sc_dilfactor")
            st.markdown(_t.get('sc_start_conc_label', ''))
            sc_start_conc = st.number_input(_t.get('sc_start_conc_input', ''), min_value=0.0001, value=1.0, format="%.4f", key="sc_startconc")
        st.markdown(_t.get('sc_enter_ct', ''))
        sc_ct_cols = st.columns(min(sc_num_points, 5))
        sc_ct_values = []
        sc_log_concs = []
        for pt in range(sc_num_points):
            conc = sc_start_conc / (sc_dilution_factor ** pt)
            log_c = np.log10(conc)
            with sc_ct_cols[pt % 5]:
                ct_val = st.number_input(f"Dil. {pt+1} (log={log_c:.2f})", value=18.0 + pt * 3.32, step=0.01, format="%.2f", key=f"sc_ct_{pt}")
            sc_ct_values.append(ct_val)
            sc_log_concs.append(log_c)
        if st.button(_t.get('sc_calc_button', ''), key="sc_calc"):
            sc_log_concs_arr = np.array(sc_log_concs)
            sc_ct_arr = np.array(sc_ct_values)
            slope_val, intercept_val, r_val, p_val, se_val = stats.linregress(sc_log_concs_arr, sc_ct_arr)
            r2 = r_val ** 2
            E_calc = 10 ** (-1.0 / slope_val) if slope_val != 0 else float('nan')
            E_pct = (E_calc - 1) * 100
            rc1, rc2, rc3, rc4 = st.columns(4)
            rc1.metric(_t.get('sc_slope', ''), f"{slope_val:.4f}")
            rc2.metric(_t.get('sc_e_value', ''), f"{E_calc:.4f}")
            rc3.metric(_t.get('sc_efficiency_pct', ''), f"{E_pct:.1f}%")
            rc4.metric("R²", f"{r2:.4f}")
            if 1.8 <= E_calc <= 2.2 and r2 >= 0.99:
                st.success(_t.get('sc_excellent', '').format(e=E_calc, pct=E_pct, r2=r2))
            elif 1.8 <= E_calc <= 2.2:
                st.warning(_t.get('sc_warning_r2', '').format(pct=E_pct, r2=r2))
            else:
                st.error(_t.get('sc_error_range', '').format(e=E_calc, pct=E_pct))
            st.info(_t.get('sc_copy_hint', '').format(slope=slope_val, e=E_calc))

    # ── Per-gen efficiency girişi ─────────────────────────────────────────────
    gene_efficiencies = {}
    use_slope = (efficiency_method == _t.get('efficiency_slope', ''))
    for i in range(num_target_genes):
        with st.expander(f"🔬 {_t.get('target_gene', "")} {i+1} — Efficiency", expanded=(i == 0)):
            ec1, ec2 = st.columns(2)
            with ec1:
                if use_slope:
                    target_slope = st.number_input(_t.get('efficiency_target_slope_label', '').format(i=i+1), value=-3.32, step=0.01, format="%.4f", key=f"target_slope_{i}")
                    target_E = 10 ** (-1.0 / target_slope) if target_slope != 0 else 2.0
                    st.markdown(f"**E (target) = {target_E:.4f}** ({(target_E-1)*100:.1f}%)")
                else:
                    target_E = st.number_input(_t.get('efficiency_target_label', '').format(i=i+1), min_value=1.0, max_value=3.0, value=2.0, step=0.01, format="%.4f", key=f"target_E_{i}")
                    st.markdown(f"**{(target_E-1)*100:.1f}%**")
            with ec2:
                if use_slope:
                    ref_slope = st.number_input(_t.get('efficiency_ref_slope_label', '').format(i=i+1), value=-3.32, step=0.01, format="%.4f", key=f"ref_slope_{i}")
                    ref_E = 10 ** (-1.0 / ref_slope) if ref_slope != 0 else 2.0
                    st.markdown(f"**E (ref) = {ref_E:.4f}** ({(ref_E-1)*100:.1f}%)")
                else:
                    ref_E = st.number_input(_t.get('efficiency_ref_label', '').format(i=i+1), min_value=1.0, max_value=3.0, value=2.0, step=0.01, format="%.4f", key=f"ref_E_{i}")
                    st.markdown(f"**{(ref_E-1)*100:.1f}%**")
            diff = abs((target_E-1)*100 - (ref_E-1)*100)
            if diff <= efficiency_threshold:
                st.success(_t.get('efficiency_ok', '').format(diff=diff))
            else:
                st.warning(_t.get('efficiency_warning', '').format(diff=diff))
            gene_efficiencies[i] = {"target_E": target_E, "ref_E": ref_E}

    st.divider()

    # ── Gen verisi giriş başlığı ───────────────────────────────────────────────
    st.markdown(
        f"<div style='font-size:15px;font-weight:700;color:#1a237e;margin-bottom:6px;'>"
        f"📥 {_t.get('patient_data_header', 'Enter Patient and Control Group Data')}"
        f"</div>",
        unsafe_allow_html=True
    )

    # Kontrol + Hasta Grubu Veri Giriş Döngüsü
    for i in range(num_target_genes):
        st.markdown(
            f"<h4 style='margin-top:12px;margin-bottom:4px;color:#283593;'>"
            f"🧬 {_t.get('target_gene', 'Target Gene')} {i+1}</h4>",
            unsafe_allow_html=True
        )

        control_target_ct = st.text_area(
            f"Control {i+1} - {_t.get('target_gene', '')} {i+1} - {_t.get('ct_value', '')}",
            value=st.session_state.get(f"control_target_ct_{i}", ""),
            key=f"control_target_ct_{i}"
        )

        # ── Multi-reference gene input (Control) ─────────────────────────────────
        ctrl_ref_arrays = []
        ctrl_ref_names  = []
        all_ctrl_refs_valid = True

        for r in range(num_ref_genes):
            ref_label = f"Ref Gene {r+1}" if num_ref_genes > 1 else _t.get('reference_gene', '')
            ctrl_ref_ct_raw = st.text_area(
                f"Control {i+1} — {ref_label} {i+1} — {_t.get('ct_value', "")}",
                value=st.session_state.get(f"control_reference_ct_{i}_{r}", ""),
                key=f"control_reference_ct_{i}_{r}"
            )
            parsed = parse_input_data(ctrl_ref_ct_raw)
            if len(parsed) == 0:
                all_ctrl_refs_valid = False
            else:
                ctrl_ref_arrays.append(parsed)
                ctrl_ref_names.append(f"Ref Gene {r+1}")

        control_target_ct_values = np.array(parse_input_data(control_target_ct))

        if len(control_target_ct_values) == 0 or not all_ctrl_refs_valid or len(ctrl_ref_arrays) == 0:
            st.error(_t.get('warning_control_ct', '').format(i=i+1))
            continue

        # Trim all arrays to common length
        # warn user if n differs between target and reference genes
        min_control_len = min(len(control_target_ct_values), *[len(a) for a in ctrl_ref_arrays])
        all_ctrl_lengths = [len(control_target_ct_values)] + [len(a) for a in ctrl_ref_arrays]
        if len(set(all_ctrl_lengths)) > 1:
            details = f"Target Gene: n={len(control_target_ct_values)}" + \
                      "".join([f", Ref Gene {r+1}: n={len(ctrl_ref_arrays[r])}" for r in range(len(ctrl_ref_arrays))])
            st.warning(_t.get('unequal_n_warning', '').format(
                group=f"Control Group {i+1}",
                details=details,
                min_n=min_control_len
            ))
        control_target_ct_values = control_target_ct_values[:min_control_len]
        ctrl_ref_arrays = [a[:min_control_len] for a in ctrl_ref_arrays]

        # ── Outlier detection — Raw Cq stage (BEFORE normalization) ──────────────
        # When outlier_on_raw is True, Grubbs/IQR is applied to raw Ct values
        # separately for target gene and each reference gene before ΔCq is computed.
        # This prevents noisy replicates from propagating into normalization.
        ctrl_excluded_target = []

        if outlier_enabled and outlier_on_raw:
            # --- Target Ct outlier check ---
            if len(control_target_ct_values) >= 3:
                detected_raw_tgt = detect_outliers_grubbs(control_target_ct_values, alpha=grubbs_alpha) \
                                   if outlier_method == "Grubbs" \
                                   else detect_outliers_iqr(control_target_ct_values, multiplier=iqr_multiplier)
                if detected_raw_tgt:
                    control_target_ct_values, ctrl_excluded_target = render_outlier_ui(
                        control_target_ct_values,
                        f"Control Group {i+1} — Target Gene {i+1} (Raw Cq)",
                        f"ctrl_raw_tgt_{i}",
                        outlier_method
                    )
                    if ctrl_excluded_target:
                        keep_indices = [k for k in range(min_control_len) if k not in ctrl_excluded_target]
                        ctrl_ref_arrays = [a[keep_indices] for a in ctrl_ref_arrays]
                        min_control_len = len(keep_indices)

            # --- Reference gene Ct outlier check (each ref gene separately) ---
            for r in range(len(ctrl_ref_arrays)):
                if len(ctrl_ref_arrays[r]) >= 3:
                    detected_raw_ref = detect_outliers_grubbs(ctrl_ref_arrays[r], alpha=grubbs_alpha) \
                                       if outlier_method == "Grubbs" \
                                       else detect_outliers_iqr(ctrl_ref_arrays[r], multiplier=iqr_multiplier)
                    if detected_raw_ref:
                        cleaned_ref, excl_ref = render_outlier_ui(
                            ctrl_ref_arrays[r],
                            f"Control Group {i+1} — Reference Gene {r+1} (Raw Cq)",
                            f"ctrl_raw_ref_{i}_{r}",
                            outlier_method
                        )
                        if excl_ref:
                            # Remove same indices from target and all other refs
                            keep_ref = [k for k in range(len(ctrl_ref_arrays[r])) if k not in excl_ref]
                            control_target_ct_values = control_target_ct_values[keep_ref]
                            ctrl_ref_arrays = [a[keep_ref] for a in ctrl_ref_arrays]
                            min_control_len = len(keep_ref)

        # ── Outlier detection — Control Target Ct (ΔCq stage fallback) ──────────
        elif outlier_enabled and not outlier_on_raw and len(control_target_ct_values) >= 3:
            detected_ctrl_tgt = detect_outliers_grubbs(control_target_ct_values, alpha=grubbs_alpha) \
                                if outlier_method == "Grubbs" \
                                else detect_outliers_iqr(control_target_ct_values, multiplier=iqr_multiplier)
            if detected_ctrl_tgt:
                control_target_ct_values, ctrl_excluded_target = render_outlier_ui(
                    control_target_ct_values,
                    f"Control Group {i+1} — Target Gene {i+1}",
                    f"ctrl_tgt_{i}",
                    outlier_method
                )
                if ctrl_excluded_target:
                    keep_indices = [k for k in range(min_control_len) if k not in ctrl_excluded_target]
                    ctrl_ref_arrays = [a[keep_indices] for a in ctrl_ref_arrays]
                    min_control_len = len(keep_indices)

        # ── geNorm + CV stability (shown when ≥2 ref genes) ──────────────────────
        if num_ref_genes >= 2:
            ref_matrix = np.vstack(ctrl_ref_arrays)   # (n_refs, n_samples)
            m_values   = compute_genorm_m(ref_matrix)
            cv_values  = [compute_cv(a) for a in ctrl_ref_arrays]

            unstable_ctrl = [r for r, m in enumerate(m_values) if m >= 1.0]
            borderline_ctrl = [r for r, m in enumerate(m_values) if 0.5 <= m < 1.0]

            st.markdown(f"##### 📊 " + _t.get('genorm_title', 'Reference Gene Stability') + f" — " + _t.get('control_group', 'Control Group') + f" {i+1}")
            stab_cols = st.columns(num_ref_genes)
            for r, col in enumerate(stab_cols):
                m_ok = m_values[r] < 1.0
                cv_ok = cv_values[r] < 5.0
                with col:
                    st.metric(
                        label=f"Ref Gene {r+1}",
                        value=f"M = {m_values[r]:.3f}",
                        delta=f"CV = {cv_values[r]:.2f}%"
                    )
                    if m_ok and cv_ok:
                        st.caption("✅ " + _t.get("stable", "Stable"))
                    elif m_ok or cv_ok:
                        st.caption("⚠️ " + _t.get("borderline", "Borderline"))
                    else:
                        st.caption("❌ " + _t.get("unstable", "Unstable") + " — M ≥ 1.0")

            # Stability bar chart
            fig_stab = go.Figure()
            fig_stab.add_trace(go.Bar(
                name="geNorm M-value",
                x=[f"Ref {r+1}" for r in range(num_ref_genes)],
                y=m_values,
                marker_color=["#2ecc71" if m < 0.5 else "#f39c12" if m < 1.0 else "#e74c3c" for m in m_values],
                text=[f"{m:.3f}" for m in m_values],
                textposition="outside"
            ))
            fig_stab.add_hline(y=0.5, line_dash="dot", line_color="green",
                               annotation_text="M=0.5 (strict)", annotation_position="right")
            fig_stab.add_hline(y=1.0, line_dash="dash", line_color="orange",
                               annotation_text="M=1.0 (acceptable)", annotation_position="right")
            fig_stab.update_layout(
                title=f"geNorm M-value — {_t.get('control_group', 'Control Group').replace('🧬 ','')} {i+1}",
                yaxis_title=_t.get('m_value', 'M-value') + " (lower = more stable)",
                height=280
            )
            st.plotly_chart(fig_stab, use_container_width=True, key=f"stab_ctrl_{i}")

            # ── Stability warnings ────────────────────────────────────────────────
            _ctrl_grp_lbl = f"{_t.get('control_group','Control Group').replace('🧬 ','')} {i+1}"
            if unstable_ctrl:
                unstable_names = ", ".join([f"{_t.get('ref_gene','Ref Gene')} {r+1}" for r in unstable_ctrl])
                st.warning(
                    f"⚠️ **{_t.get('unstable','Unstable')} — {_ctrl_grp_lbl}: {unstable_names}**\n\n"
                    f"geNorm M ≥ 1.0 — expression varies considerably. Normalization may be distorted.\n\n"
                    f"- Verify Ct values for {unstable_names}\n"
                    f"- Consider replacing with a more stable reference gene\n"
                    f"- Ref: Vandesompele et al. *Genome Biology* 2002"
                )
            elif borderline_ctrl:
                borderline_names = ", ".join([f"{_t.get('ref_gene','Ref Gene')} {r+1}" for r in borderline_ctrl])
                st.info(
                    f"ℹ️ **{_t.get('borderline','Borderline')} — {_ctrl_grp_lbl}: {borderline_names}** (M = 0.5–1.0)\n\n"
                    f"{_t.get('stability','Stability')} acceptable per MIQE. Consider adding a third reference gene."
                )
            else:
                st.success(
                    f"✅ {_t.get('stable','All stable')} — {_ctrl_grp_lbl} (M < 0.5). "
                    f"Normalization quality is excellent."
                )

        # ── Compute normalization factor (geometric mean of refs) ─────────────────
        # Re-sync min_control_len to actual array lengths after any outlier removal
        min_control_len = min(len(control_target_ct_values), *[len(a) for a in ctrl_ref_arrays])
        control_target_ct_values = control_target_ct_values[:min_control_len]
        ctrl_ref_arrays = [a[:min_control_len] for a in ctrl_ref_arrays]

        ctrl_norm_factor = geometric_mean_ct(ctrl_ref_arrays)   # per-sample NF
        control_delta_ct = control_target_ct_values - ctrl_norm_factor

        # For table: show first ref gene Ct as representative; NF shown separately
        control_reference_ct_values = ctrl_ref_arrays[0]   # kept for legacy table column

        average_control_delta_ct = np.mean(control_delta_ct) if len(control_delta_ct) > 0 else None
        sample_counter = 1

        for idx in range(min_control_len):
            row = {
                "__sample_num__": sample_counter,
                "__target_gene__": f"Gene {i+1}",
                "Grup": "Control",
                "__target_ct__": control_target_ct_values[idx],
                "__ref_ct__": round(ctrl_norm_factor[idx], 4),
                "__dct_ctrl__": round(control_delta_ct[idx], 4),
                "Outlier Excluded": "No"
            }
            if num_ref_genes > 1:
                for r, arr in enumerate(ctrl_ref_arrays):
                    row[f"Ref Gene {r+1} Ct"] = arr[idx]
            input_values_table.append(row)
            sample_counter += 1

        # Log excluded outliers as separate flagged rows
        for ex_idx in ctrl_excluded_target:
            input_values_table.append({
                "__sample_num__": f"{ex_idx + 1} ⚠️",
                "__target_gene__": f"Gene {i+1}",
                "Grup": "Control",
                "__target_ct__": "EXCLUDED",
                "__ref_ct__": "EXCLUDED",
                "__dct_ctrl__": "EXCLUDED",
                "Outlier Excluded": f"Yes ({outlier_method})"
            })

        for j in range(num_patient_groups):
            st.markdown(
                f"<h4>{_t.get('patient_group', "")} {j+1} - {_t.get('target_gene', "")} {i+1}</h4>",
                unsafe_allow_html=True
            )

            sample_target_ct = st.text_area(
                f"{_t.get('patient_group', "")} {j+1} - {_t.get('target_gene', "")} {i+1} - {_t.get('ct_value', "")}",
                value=st.session_state.get(f"sample_target_ct_{i}_{j}", ""),
                key=f"sample_target_ct_{i}_{j}"
            )

            # ── Multi-reference gene input (Patient) ──────────────────────────────
            smp_ref_arrays = []
            all_smp_refs_valid = True

            for r in range(num_ref_genes):
                ref_label = f"Ref Gene {r+1}" if num_ref_genes > 1 else _t.get('reference_gene', '')
                smp_ref_ct_raw = st.text_area(
                    f"{_t.get('patient_group', "")} {j+1} — {ref_label} {i+1} — {_t.get('ct_value', "")}",
                    value=st.session_state.get(f"sample_reference_ct_{i}_{j}_{r}", ""),
                    key=f"sample_reference_ct_{i}_{j}_{r}"
                )
                parsed = parse_input_data(smp_ref_ct_raw)
                if len(parsed) == 0:
                    all_smp_refs_valid = False
                else:
                    smp_ref_arrays.append(parsed)

            sample_target_ct_values = np.array(parse_input_data(sample_target_ct))

            if len(sample_target_ct_values) == 0 or not all_smp_refs_valid or len(smp_ref_arrays) == 0:
                st.error(_t.get('warning_patient_cq', '').format(j=j+1))
                continue

            # warn if n differs between target and reference genes
            min_sample_len = min(len(sample_target_ct_values), *[len(a) for a in smp_ref_arrays])
            all_smp_lengths = [len(sample_target_ct_values)] + [len(a) for a in smp_ref_arrays]
            if len(set(all_smp_lengths)) > 1:
                details = f"Target Gene: n={len(sample_target_ct_values)}" + \
                          "".join([f", Ref Gene {r+1}: n={len(smp_ref_arrays[r])}" for r in range(len(smp_ref_arrays))])
                st.warning(_t.get('unequal_n_warning', '').format(
                    group=f"{_t.get('patient_group', "")} {j+1}, Gene {i+1}",
                    details=details,
                    min_n=min_sample_len
                ))
            sample_target_ct_values = sample_target_ct_values[:min_sample_len]
            smp_ref_arrays = [a[:min_sample_len] for a in smp_ref_arrays]

            # ── Outlier detection — Raw Cq stage (BEFORE normalization) ──────────
            # same logic as control group above
            smp_excluded_target = []

            if outlier_enabled and outlier_on_raw:
                # --- Target Ct ---
                if len(sample_target_ct_values) >= 3:
                    detected_raw_smp_tgt = detect_outliers_grubbs(sample_target_ct_values, alpha=grubbs_alpha) \
                                           if outlier_method == "Grubbs" \
                                           else detect_outliers_iqr(sample_target_ct_values, multiplier=iqr_multiplier)
                    if detected_raw_smp_tgt:
                        sample_target_ct_values, smp_excluded_target = render_outlier_ui(
                            sample_target_ct_values,
                            f"{_t.get('patient_group', "")} {j+1} — Target Gene {i+1} (Raw Cq)",
                            f"smp_raw_tgt_{i}_{j}",
                            outlier_method
                        )
                        if smp_excluded_target:
                            keep_indices_smp = [k for k in range(min_sample_len) if k not in smp_excluded_target]
                            smp_ref_arrays = [a[keep_indices_smp] for a in smp_ref_arrays]
                            min_sample_len = len(keep_indices_smp)

                # --- Reference gene Ct (each separately) ---
                for r in range(len(smp_ref_arrays)):
                    if len(smp_ref_arrays[r]) >= 3:
                        detected_raw_smp_ref = detect_outliers_grubbs(smp_ref_arrays[r], alpha=grubbs_alpha) \
                                               if outlier_method == "Grubbs" \
                                               else detect_outliers_iqr(smp_ref_arrays[r], multiplier=iqr_multiplier)
                        if detected_raw_smp_ref:
                            cleaned_smp_ref, excl_smp_ref = render_outlier_ui(
                                smp_ref_arrays[r],
                                f"{_t.get('patient_group', "")} {j+1} — Reference Gene {r+1} (Raw Cq)",
                                f"smp_raw_ref_{i}_{j}_{r}",
                                outlier_method
                            )
                            if excl_smp_ref:
                                keep_ref_smp = [k for k in range(len(smp_ref_arrays[r])) if k not in excl_smp_ref]
                                sample_target_ct_values = sample_target_ct_values[keep_ref_smp]
                                smp_ref_arrays = [a[keep_ref_smp] for a in smp_ref_arrays]
                                min_sample_len = len(keep_ref_smp)

            # ── Outlier detection — Patient Target Ct (ΔCq stage fallback) ──────
            elif outlier_enabled and not outlier_on_raw and len(sample_target_ct_values) >= 3:
                detected_smp_tgt = detect_outliers_grubbs(sample_target_ct_values, alpha=grubbs_alpha) \
                                   if outlier_method == "Grubbs" \
                                   else detect_outliers_iqr(sample_target_ct_values, multiplier=iqr_multiplier)
                if detected_smp_tgt:
                    sample_target_ct_values, smp_excluded_target = render_outlier_ui(
                        sample_target_ct_values,
                        f"{_t.get('patient_group', "")} {j+1} — Target Gene {i+1}",
                        f"smp_tgt_{i}_{j}",
                        outlier_method
                    )
                    if smp_excluded_target:
                        keep_indices_smp = [k for k in range(min_sample_len) if k not in smp_excluded_target]
                        smp_ref_arrays = [a[keep_indices_smp] for a in smp_ref_arrays]
                        min_sample_len = len(keep_indices_smp)

            # ── geNorm + CV stability (Patient, shown when ≥2 ref genes) ─────────
            if num_ref_genes >= 2:
                smp_ref_matrix = np.vstack(smp_ref_arrays)
                smp_m_values   = compute_genorm_m(smp_ref_matrix)
                smp_cv_values  = [compute_cv(a) for a in smp_ref_arrays]

                unstable_smp   = [r for r, m in enumerate(smp_m_values) if m >= 1.0]
                borderline_smp = [r for r, m in enumerate(smp_m_values) if 0.5 <= m < 1.0]

                st.markdown(f"##### 📊 Reference Gene Stability — {_t.get('patient_group', "")} {j+1}")
                smp_stab_cols = st.columns(num_ref_genes)
                for r, col in enumerate(smp_stab_cols):
                    m_ok = smp_m_values[r] < 1.0
                    cv_ok = smp_cv_values[r] < 5.0
                    with col:
                        st.metric(
                            label=f"Ref Gene {r+1}",
                            value=f"M = {smp_m_values[r]:.3f}",
                            delta=f"CV = {smp_cv_values[r]:.2f}%"
                        )
                        if m_ok and cv_ok:
                            st.caption("✅ " + _t.get("stable", "Stable"))
                        elif m_ok or cv_ok:
                            st.caption("⚠️ " + _t.get("borderline", "Borderline"))
                        else:
                            st.caption("❌ " + _t.get("unstable", "Unstable") + " — M ≥ 1.0")

                # Stability bar chart (patient)
                fig_stab_smp = go.Figure()
                fig_stab_smp.add_trace(go.Bar(
                    name="geNorm M-value",
                    x=[f"Ref {r+1}" for r in range(num_ref_genes)],
                    y=smp_m_values,
                    marker_color=["#2ecc71" if m < 0.5 else "#f39c12" if m < 1.0 else "#e74c3c" for m in smp_m_values],
                    text=[f"{m:.3f}" for m in smp_m_values],
                    textposition="outside"
                ))
                fig_stab_smp.add_hline(y=0.5, line_dash="dot", line_color="green",
                                   annotation_text="M=0.5 (strict)", annotation_position="right")
                fig_stab_smp.add_hline(y=1.0, line_dash="dash", line_color="orange",
                                   annotation_text="M=1.0 (acceptable)", annotation_position="right")
                fig_stab_smp.update_layout(
                    title=f"geNorm M-value — {_t.get('patient_group', '').replace('🩸 ','')} {j+1}",
                    yaxis_title=_t.get('m_value', 'M-value') + " (lower = more stable)",
                    height=280
                )
                st.plotly_chart(fig_stab_smp, use_container_width=True, key=f"stab_smp_{i}_{j}")

                # ── Stability warnings (patient) ──────────────────────────────────
                _smp_grp_lbl = f"{_t.get('patient_group','').replace('🩸 ','')} {j+1}"
                if unstable_smp:
                    unstable_names = ", ".join([f"{_t.get('ref_gene','Ref Gene')} {r+1}" for r in unstable_smp])
                    st.warning(
                        f"⚠️ **{_t.get('unstable','Unstable')} — {_smp_grp_lbl}: {unstable_names}**\n\n"
                        f"geNorm M ≥ 1.0 — normalization reliability compromised. Interpret with caution.\n\n"
                        f"- Check for outliers or data entry errors\n"
                        f"- Validate {unstable_names} in this sample group\n"
                        f"- Consider replacing with a validated reference gene"
                    )
                elif borderline_smp:
                    borderline_names = ", ".join([f"{_t.get('ref_gene','Ref Gene')} {r+1}" for r in borderline_smp])
                    st.info(
                        f"ℹ️ **{_t.get('borderline','Borderline')} — {_smp_grp_lbl}: {borderline_names}** (M = 0.5–1.0)\n\n"
                        f"{_t.get('stability','Stability')} within MIQE range. Consider a third reference gene."
                    )
                else:
                    st.success(
                        f"✅ {_t.get('stable','Stable')} — {_smp_grp_lbl} (M < 0.5)."
                    )

            # ── Normalization factor & ΔCq ────────────────────────────────────────
            # Re-sync lengths after any outlier removal
            min_sample_len = min(len(sample_target_ct_values), *[len(a) for a in smp_ref_arrays])
            sample_target_ct_values = sample_target_ct_values[:min_sample_len]
            smp_ref_arrays = [a[:min_sample_len] for a in smp_ref_arrays]

            smp_norm_factor = geometric_mean_ct(smp_ref_arrays)
            sample_delta_ct = sample_target_ct_values - smp_norm_factor
            sample_reference_ct_values = smp_ref_arrays[0]

            average_sample_delta_ct = np.mean(sample_delta_ct) if len(sample_delta_ct) > 0 else None

            sample_counter = 1
            for idx in range(min_sample_len):
                row = {
                    "__sample_num__": sample_counter,
                    "__target_gene__": f"Gene {i+1}",
                    "Grup": f"Group {j+1}",
                    "__target_ct__": sample_target_ct_values[idx],
                    "__ref_ct__": round(smp_norm_factor[idx], 4),
                    "__dct_patient__": round(sample_delta_ct[idx], 4),
                    "Outlier Excluded": "No"
                }
                if num_ref_genes > 1:
                    for r, arr in enumerate(smp_ref_arrays):
                        row[f"Ref Gene {r+1} Ct"] = arr[idx]
                input_values_table.append(row)
                sample_counter += 1

            # Log excluded outliers as flagged rows
            for ex_idx in smp_excluded_target:
                input_values_table.append({
                    "__sample_num__": f"{ex_idx + 1} ⚠️",
                    "__target_gene__": f"Gene {i+1}",
                    "Grup": f"Group {j+1}",
                    "__target_ct__": "EXCLUDED",
                    "__ref_ct__": "EXCLUDED",
                    "__dct_patient__": "EXCLUDED",
                    "Outlier Excluded": f"Yes ({outlier_method})"
                })

            # ΔΔCq ve Gen Ekspresyon Değişimi Hesaplama
            if average_control_delta_ct is not None and average_sample_delta_ct is not None:
                delta_delta_ct = average_sample_delta_ct - average_control_delta_ct
                expression_change = 2 ** (-delta_delta_ct)

                # ── Pfaffl Calculation ──────────────────────────────────────────
                eff = gene_efficiencies.get(i, {"target_E": 2.0, "ref_E": 2.0})
                E_target = eff["target_E"]
                E_ref = eff["ref_E"]

                avg_ctrl_target = np.mean(control_target_ct_values)
                avg_ctrl_ref    = np.mean(ctrl_norm_factor)
                avg_smp_target  = np.mean(sample_target_ct_values)
                avg_smp_ref     = np.mean(smp_norm_factor)

                delta_ct_target_pfaffl = avg_ctrl_target - avg_smp_target
                delta_ct_ref_pfaffl    = avg_ctrl_ref    - avg_smp_ref

                pfaffl_ratio = (E_target ** delta_ct_target_pfaffl) / (E_ref ** delta_ct_ref_pfaffl)
                # ────────────────────────────────────────────────────────────────
            
                # Regulation: literatür standardı FC > 1.5 = up, < 0.67 = down
                # (bazı çalışmalar 1.2/0.83 kullanır — burada 1.5/0.67)
                if expression_change >= 1.5:
                    regulation_status = _t.get('upregulated', '')
                elif expression_change <= 0.67:
                    regulation_status = _t.get('downregulated', '')
                else:
                    regulation_status = _t.get('no_change', '')

                # Pfaffl regulation
                if pfaffl_ratio >= 1.5:
                    pfaffl_regulation = _t.get('upregulated', '')
                elif pfaffl_ratio <= 0.67:
                    pfaffl_regulation = _t.get('downregulated', '')
                else:
                    pfaffl_regulation = _t.get('no_change', '')

                # ── Method comparison display ─────────────────────────────────
                st.markdown(f"#### {_t.get('method_comparison', "")} — {_t.get('target_gene', "")} {i+1} / {_t.get('patient_group', "")} {j+1}")
                comp_col1, comp_col2 = st.columns(2)
                with comp_col1:
                    st.metric(
                        label=_t.get('classic_ddct', ''),
                        value=f"{expression_change:.4f}",
                        delta=regulation_status
                    )
                with comp_col2:
                    st.metric(
                        label=_t.get('pfaffl_ratio', ''),
                        value=f"{pfaffl_ratio:.4f}",
                        delta=pfaffl_regulation
                    )
                # ─────────────────────────────────────────────────────────────

                # ── Per-group pairwise stats (control vs this patient group) ────
                # Statistical tests are now performed on RQ values (2^-ΔCq) instead of
                # raw ΔCt values. ΔCt values are on a logarithmic scale; performing
                # t-tests directly on ΔCt underestimates biological variability and can
                # produce false significant differences compared to linear RQ-based tests.
                control_rq = 2 ** (-np.array(control_delta_ct))
                sample_rq  = 2 ** (-np.array(sample_delta_ct))

                n_ctrl = len(control_rq)
                n_smp  = len(sample_rq)

                # n < 2 ise istatistik hesaplanamaz
                if n_ctrl < 2 or n_smp < 2:
                    test_pvalue = float('nan')
                    test_method = "N/A (n < 2)"
                    test_type   = "—"
                    significance = "—"
                    equal_variance = True
                    control_normal = True
                    sample_normal  = True
                    shapiro_control = type('SW', (), {'statistic': float('nan'), 'pvalue': float('nan')})()
                    shapiro_sample  = type('SW', (), {'statistic': float('nan'), 'pvalue': float('nan')})()
                    levene_test     = type('LV', (), {'statistic': float('nan'), 'pvalue': float('nan')})()
                else:
                    _MIN_N_SHAPIRO = 8

                    if n_ctrl >= _MIN_N_SHAPIRO and n_smp >= _MIN_N_SHAPIRO:
                        shapiro_control = stats.shapiro(control_rq)
                        shapiro_sample  = stats.shapiro(sample_rq)
                        control_normal  = shapiro_control.pvalue > 0.05
                        sample_normal   = shapiro_sample.pvalue  > 0.05
                    else:
                        shapiro_control = type('SW', (), {'statistic': float('nan'), 'pvalue': float('nan')})()
                        shapiro_sample  = type('SW', (), {'statistic': float('nan'), 'pvalue': float('nan')})()
                        control_normal  = True
                        sample_normal   = True

                    try:
                        levene_test    = stats.levene(control_rq, sample_rq)
                        equal_variance = (levene_test.pvalue > 0.05) if not np.isnan(levene_test.pvalue) else True
                    except Exception:
                        levene_test    = type('LV', (), {'statistic': float('nan'), 'pvalue': float('nan')})()
                        equal_variance = True

                    try:
                        if control_normal and sample_normal:
                            if equal_variance:
                                test_pvalue = stats.ttest_ind(control_rq, sample_rq).pvalue
                                test_method = _t.get('t_test', '')
                            else:
                                test_pvalue = stats.ttest_ind(control_rq, sample_rq, equal_var=False).pvalue
                                test_method = _t.get('welch_t_test', '')
                            test_type = _t.get('parametric', '')
                        else:
                            test_pvalue = stats.mannwhitneyu(control_rq, sample_rq,
                                                              alternative='two-sided').pvalue
                            test_method = _t.get('mann_whitney_u_test', '')
                            test_type   = _t.get('non_parametric', '')
                    except Exception:
                        test_pvalue = float('nan')
                        test_method = "Error"
                        test_type   = "—"

                    significance = _t.get('significant', '') if (not np.isnan(test_pvalue) and test_pvalue < 0.05) \
                                   else (_t.get('insignificant', '') if not np.isnan(test_pvalue) else "—")

                # ── Decision pathway display ──────────────────────────────────
                with st.expander(
                    f"{_t.get('stat_decision_title', "")} — "
                    f"{_t.get('target_gene', "")} {i+1} / "
                    f"Group {j+1}",
                    expanded=False
                ):
                    st.markdown(_t.get('stat_decision_steps', ''))

                    sw_ctrl_sym = "✅" if control_normal else "❌"
                    sw_smp_sym  = "✅" if sample_normal  else "❌"

                    if n_ctrl >= _MIN_N_SHAPIRO and n_smp >= _MIN_N_SHAPIRO:
                        st.markdown(
                            f"{_t.get('stat_shapiro_title', "")}  \n"
                            f"- Control: W={shapiro_control.statistic:.4f}, "
                            f"p={shapiro_control.pvalue:.4f} {sw_ctrl_sym} "
                            f"{_t.get('stat_normal', "") if control_normal else _t.get('stat_nonnormal', "")}  \n"
                            f"- {_t.get('patient_group', "")} {j+1}: "
                            f"W={shapiro_sample.statistic:.4f}, "
                            f"p={shapiro_sample.pvalue:.4f} {sw_smp_sym} "
                            f"{_t.get('stat_normal', "") if sample_normal else _t.get('stat_nonnormal', "")}"
                        )
                    else:
                        st.info(
                            f"ℹ️ **Shapiro-Wilk atlandı** — n={min(n_ctrl, n_smp)} "
                            f"(gerekli minimum: {_MIN_N_SHAPIRO}). "
                            f"Küçük örneklemde Shapiro-Wilk güvenilir sonuç vermez; "
                            f"normallik varsayılarak parametrik test uygulandı."
                        )

                    if control_normal and sample_normal:
                        lev_sym = "✅" if equal_variance else "⚠️"
                        st.markdown(
                            f"{_t.get('stat_levene_title', "")}  \n"
                            f"- F={levene_test.statistic:.4f}, p={levene_test.pvalue:.4f} "
                            f"{lev_sym} {_t.get('stat_equal_var', "") if equal_variance else _t.get('stat_unequal_var', "")}"
                        )
                    else:
                        st.markdown(_t.get('stat_levene_skipped', ''))

                    if not control_normal or not sample_normal:
                        reason = _t.get('stat_reason_nonnormal', '')
                    elif equal_variance:
                        reason = _t.get('stat_reason_normal_equal', '')
                    else:
                        reason = _t.get('stat_reason_normal_unequal', '')

                    st.success(
                        f"{_t.get('stat_selected_test', "")} {test_method}  \n"
                        f"{_t.get('stat_reason', "")} {reason}  \n"
                        f"{_t.get('stat_result', "")} p = {test_pvalue:.4f} → **{significance}**"
                    )

                    if num_patient_groups >= 2:
                        st.caption(_t.get('stat_multigroup_note', ''))
                # ─────────────────────────────────────────────────────────────

                stats_data.append({
                    "__target_gene__":   f"Gene {i+1}",
                    "__patient_group__": f"Group {j+1}",
                    "__test_type__":     test_type,
                    "__test_method__":   test_method,
                    "__pvalue__":   test_pvalue,
                    "__significance__":  significance,
                    "Comparison": f"Control vs Group {j+1}"
                })

                data.append({
                    "__target_gene__":         f"Gene {i+1}",
                    "__patient_group__":       f"Group {j+1}",
                    "__ddct__":      delta_delta_ct,
                    "__fc__": expression_change,
                    "__pfaffl__":        pfaffl_ratio,
                    "E target":                                          round(E_target, 4),
                    "E ref":                                             round(E_ref, 4),
                    "__regulation__":   regulation_status,
                    "__dct_ctrl__":    average_control_delta_ct,
                    "__dct_patient__":    average_sample_delta_ct
                })

# ─── MULTI-GROUP ANALYSIS (3+ patient groups per target gene) ────────────────
# Collect all ΔCq arrays per target gene for omnibus testing
multigroup_results = []   # records for display / PDF

for i in range(num_target_genes):
    # Pull per-group ΔCt values from stats_data provenance via data dict
    # Re-derive from input_values_table (source of truth after outlier removal)
    gene_label = f"Gene {i+1}"

    ctrl_dct = [
        float(d["__dct_ctrl__"])
        for d in input_values_table
        if d.get("Grup") == "Control"
        and d.get("__target_gene__") == gene_label
        and d.get("__dct_ctrl__") not in ("EXCLUDED", None)
        and d.get("Outlier Excluded", "No") == "No"
    ]

    patient_dcts = {}
    for j in range(num_patient_groups):
        pg_label = f"Group {j+1}"
        vals = [
            float(d["__dct_patient__"])
            for d in input_values_table
            if d.get("Grup") == pg_label
            and d.get("__target_gene__") == gene_label
            and d.get("__dct_patient__") not in ("EXCLUDED", None)
            and d.get("Outlier Excluded", "No") == "No"
        ]
        if vals:
            patient_dcts[pg_label] = vals

    if not ctrl_dct or not patient_dcts:
        continue

    # Convert ΔCq lists to RQ (2^-ΔCt) for all statistical tests
    all_groups_dct  = [ctrl_dct] + list(patient_dcts.values())
    all_groups      = [list(2 ** (-np.array(g))) for g in all_groups_dct]
    all_group_names = ["Control"] + list(patient_dcts.keys())
    n_groups        = len(all_groups)

    if n_groups < 3:
        # 2-group: already handled above — just note it
        multigroup_results.append({
            "gene": gene_label,
            "n_groups": n_groups,
            "note": "2-group comparison — pairwise test already reported above.",
            "omnibus_test": "—", "omnibus_p": None,
            "posthoc": [], "correction": "—"
        })
        continue

    # ── Omnibus test selection ────────────────────────────────────────────────
    normality_ok  = all(
        (len(g) < 8 or stats.shapiro(g).pvalue > 0.05)
        for g in all_groups if len(g) >= 3
    )
    levene_p      = stats.levene(*all_groups).pvalue if n_groups >= 2 else 1.0
    variance_ok   = levene_p > 0.05

    if normality_ok and variance_ok:
        omnibus_stat, omnibus_p = stats.f_oneway(*all_groups)
        omnibus_test  = "One-way ANOVA"
        omnibus_type  = "parametric"
        posthoc_method = "Tukey HSD"
    elif normality_ok and not variance_ok:
        # Welch ANOVA (scipy ≥ 1.11) — fallback to regular ANOVA if unavailable
        try:
            from scipy.stats import alexandergovern
            result = alexandergovern(*all_groups)
            omnibus_p    = result.pvalue
            omnibus_stat = result.statistic
        except Exception:
            omnibus_stat, omnibus_p = stats.f_oneway(*all_groups)
        omnibus_test   = "Welch ANOVA (unequal variances)"
        omnibus_type   = "parametric"
        posthoc_method = "Games-Howell (approx. via pairwise Welch t-test + FDR)"
    else:
        omnibus_stat, omnibus_p = stats.kruskal(*all_groups)
        omnibus_test   = "Kruskal-Wallis"
        omnibus_type   = "non-parametric"
        posthoc_method = "Dunn (pairwise Mann-Whitney U)"

    omnibus_sig = _t.get('multigroup_significant', '') if omnibus_p < 0.05 else _t.get('multigroup_not_significant', '')

    # ── Post-hoc pairwise comparisons ────────────────────────────────────────
    pairs      = []
    raw_pvals  = []

    for a in range(n_groups):
        for b in range(a + 1, n_groups):
            g_a, g_b = all_groups[a], all_groups[b]
            if omnibus_type == "parametric" and variance_ok:
                p = stats.ttest_ind(g_a, g_b).pvalue
            elif omnibus_type == "parametric" and not variance_ok:
                p = stats.ttest_ind(g_a, g_b, equal_var=False).pvalue
            else:
                p = stats.mannwhitneyu(g_a, g_b, alternative="two-sided").pvalue
            pairs.append((all_group_names[a], all_group_names[b]))
            raw_pvals.append(p)

    # ── Multiple comparison correction ───────────────────────────────────────
    n_tests = len(raw_pvals)
    bonf_pvals = [min(p * n_tests, 1.0) for p in raw_pvals]

    # FDR Benjamini-Hochberg
    ranked     = sorted(range(n_tests), key=lambda k: raw_pvals[k])
    fdr_pvals  = [1.0] * n_tests
    for rank, idx in enumerate(ranked):
        fdr_pvals[idx] = min(raw_pvals[idx] * n_tests / (rank + 1), 1.0)
    # Enforce monotonicity
    for k in range(n_tests - 2, -1, -1):
        fdr_pvals[ranked[k]] = min(fdr_pvals[ranked[k]], fdr_pvals[ranked[k + 1]])

    posthoc_rows = []
    for idx, (pa, pb) in enumerate(pairs):
        posthoc_rows.append({
            "Comparison":        f"{pa} vs {pb}",
            "Raw p":             round(raw_pvals[idx], 4),
            "Bonferroni p":      round(bonf_pvals[idx], 4),
            "FDR p (B-H)":       round(fdr_pvals[idx], 4),
            "Sig (raw)":         "✅" if raw_pvals[idx]  < 0.05 else "—",
            "Sig (Bonferroni)":  "✅" if bonf_pvals[idx] < 0.05 else "—",
            "Sig (FDR)":         "✅" if fdr_pvals[idx]  < 0.05 else "—",
        })

    multigroup_results.append({
        "gene":          gene_label,
        "n_groups":      n_groups,
        "omnibus_test":  omnibus_test,
        "omnibus_type":  omnibus_type,
        "omnibus_p":     omnibus_p,
        "omnibus_sig":   omnibus_sig,
        "posthoc_method": posthoc_method,
        "posthoc_rows":  posthoc_rows,
        "normality_ok":  normality_ok,
        "variance_ok":   variance_ok,
        "note":          None
    })

# ─────────────────────────────────────────────────────────────────────────────

# ═══════════════════════════════════════════════════════════════════════════════
# SEKME 2: SONUÇLAR
# ═══════════════════════════════════════════════════════════════════════════════
with tab_results:

    # ── Multi-group display ───────────────────────────────────────────────────
    if any(r["n_groups"] >= 3 for r in multigroup_results):
        st.markdown("---")
        st.markdown(_t.get('multigroup_title', ''))

        with st.expander(_t.get('multigroup_expander', ''), expanded=False):
            st.markdown("""
**When is multi-group analysis applied?**  
Automatically activated when **≥ 3 groups** (control + 2 or more patient groups) are present for a target gene.  
This addresses the limitation of pairwise-only testing, which inflates Type I error when multiple comparisons are made without correction.

**Test selection logic (automatic):**

| Condition | Test |
|---|---|
| All groups normal + equal variances | One-way ANOVA → Tukey HSD |
| All groups normal + unequal variances | Welch ANOVA → Games-Howell |
| Any group non-normal | Kruskal-Wallis → Dunn (Mann-Whitney U) |

**Multiple comparison correction:**
- **Bonferroni**: conservative, controls family-wise error rate (FWER). Best when few comparisons.
- **FDR (Benjamini-Hochberg)**: controls false discovery rate. Better power for many comparisons.

**Recommendation:** Report both, discuss which is more appropriate for your study design.  
**Reference:** Dunn OJ. *J Am Stat Assoc* 1961; Benjamini & Hochberg. *J R Stat Soc B* 1995.
""")

        for res in multigroup_results:
            if res["n_groups"] < 3:
                continue

            st.markdown(f"### 🧬 {res['gene']} — {res['n_groups']} {_t.get('patient_group', "").replace('🩸 ', '')}")

            if res["normality_ok"] and res["variance_ok"]:
                st.success(_t.get('multigroup_decision_normal_equal', ''))
            elif res["normality_ok"] and not res["variance_ok"]:
                st.warning(_t.get('multigroup_decision_normal_unequal', ''))
            else:
                st.warning(_t.get('multigroup_decision_nonnormal', ''))

            omni_col1, omni_col2, omni_col3 = st.columns(3)
            omni_col1.metric(_t.get('multigroup_omnibus_test', ''), res["omnibus_test"])
            omni_col2.metric(_t.get('multigroup_pvalue', ''), f"{res['omnibus_p']:.4f}")
            omni_col3.metric(_t.get('multigroup_result', ''), res["omnibus_sig"])

            if res["omnibus_p"] >= 0.05:
                st.info(_t.get('multigroup_omnibus_ns', ''))

            st.markdown(f"{_t.get('multigroup_posthoc_label', "")} {res['posthoc_method']} — Bonferroni & FDR")
            ph_df = pd.DataFrame(res["posthoc_rows"])
            st.dataframe(ph_df, use_container_width=True)

            fig_ph = go.Figure()
            comparisons = [r["Comparison"] for r in res["posthoc_rows"]]
            fig_ph.add_trace(go.Bar(name="Raw p", x=comparisons, y=[r["Raw p"] for r in res["posthoc_rows"]], marker_color="#4C72B0"))
            fig_ph.add_trace(go.Bar(name="Bonferroni p", x=comparisons, y=[r["Bonferroni p"] for r in res["posthoc_rows"]], marker_color="#DD8452"))
            fig_ph.add_trace(go.Bar(name="FDR p (B-H)", x=comparisons, y=[r["FDR p (B-H)"] for r in res["posthoc_rows"]], marker_color="#55A868"))
            fig_ph.add_hline(y=0.05, line_dash="dash", line_color="red", annotation_text="a = 0.05", annotation_position="right")
            fig_ph.update_layout(barmode="group", title=f"{res['gene']} — Post-hoc p-values", yaxis_title="p-value", height=350)
            st.plotly_chart(fig_ph, use_container_width=True, key=f"posthoc_{res['gene']}")

            ph_csv = ph_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label=f"{_t.get('multigroup_dl_button', "")} {res['gene']}",
                data=ph_csv,
                file_name=f"posthoc_{res['gene'].replace(' ', '_')}.csv",
                mime="text/csv",
                key=f"ph_dl_{res['gene']}"
            )

    elif num_patient_groups >= 2 and multigroup_results:
        st.markdown("---")
        st.info(_t.get('multigroup_2group_note', ''))


    if input_values_table:
        st.subheader(f" {_t.get('gr_tbl', "")}")
        # Rename fixed keys to translated column headers for display
        _ivt_rename = {
            "__sample_num__":   _t.get("sample_number", "Sample #"),
            "__target_gene__":  _t.get("target_gene",   "Gene"),
            "Grup":             _t.get("Grup",          "Group"),
            "__target_ct__":    _t.get("target_ct",     "Target Cq"),
            "__ref_ct__":       _t.get("reference_ct",  "Ref Ct"),
            "__dct_ctrl__":     _t.get("delta_ct_control", "ΔCq Control"),
            "__dct_patient__":  _t.get("delta_ct_patient", "ΔCq Patient"),
            "Outlier Excluded": _t.get("pdf_outlier_col", "Outlier Excluded"),
        }
        input_df = pd.DataFrame(input_values_table).rename(columns=_ivt_rename)
        st.write(input_df)
        csv = input_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label=_t.get('download_csv', ''),
            data=csv, file_name="giris_verileri.csv", mime="text/csv",
            key="dl_input_csv")

    # Sonuçlar Tablosunu Göster
    if data:
        st.subheader(f" {_t.get('nil_mine', "")}")
        _data_rename = {
            "__target_gene__":  _t.get("target_gene",   "Gene"),
            "__patient_group__":_t.get("patient_group", "Group"),
            "__ddct__":         _t.get("delta_delta_ct","ΔΔCq"),
            "__fc__":           _t.get("gene_expression_change", "2^(-ΔΔCq)"),
            "__pfaffl__":       _t.get("pfaffl_ratio",  "Pfaffl"),
            "__regulation__":   _t.get("regulation_status", "Regulation"),
            "__dct_ctrl__":     _t.get("delta_ct_control", "ΔCq Control"),
            "__dct_patient__":  _t.get("delta_ct_patient", "ΔCq Patient"),
        }
        df = pd.DataFrame(data).rename(columns=_data_rename)
        st.write(df)

    # İstatistik Sonuçları
    if stats_data:
        st.subheader(f" {_t.get('statistical_results', "")}")
        _stats_rename = {
            "__target_gene__":  _t.get("target_gene",  "Gene"),
            "__patient_group__":_t.get("patient_group","Group"),
            "__test_type__":    _t.get("test_type",    "Test Type"),
            "__test_method__":  _t.get("test_method",  "Test Method"),
            "__pvalue__":       _t.get("test_pvalue",  "p-value"),
            "__significance__": _t.get("significance", "Significance"),
        }
        stats_df = pd.DataFrame(stats_data).rename(columns=_stats_rename)
        st.write(stats_df)
        csv_stats = stats_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label=_t.get('download_csv', ''),
            data=csv_stats,
            file_name="istatistik_sonuclari.csv",
            mime="text/csv",
            key="dl_stats_csv")

    # ─── MULTI-GENE P-VALUE CORRECTION ───────────────────────────────────────────
    if stats_data and num_target_genes >= 2:
        st.markdown("---")
        st.markdown(_t.get('multigene_title', ''))

        with st.expander(_t.get('multigene_expander', ''), expanded=False):
            st.markdown("""
When testing **multiple target genes** simultaneously, the probability of obtaining 
at least one false positive increases with the number of tests performed 
(family-wise error inflation). For example, testing 5 genes at α = 0.05 gives a 
~23% chance of at least one spurious significant result by chance alone.

**Standard practice in multi-gene expression studies requires correction:**

| Method | Controls | Best for |
|---|---|---|
| **Bonferroni** | Family-wise error rate (FWER) | Few genes, conservative |
| **FDR (Benjamini-Hochberg)** | False discovery rate | Many genes, more power |

**References:** Benjamini & Hochberg. *J R Stat Soc B* 1995;  
Ge Y et al. *Bioinformatics* 2003; Storey JD. *J R Stat Soc B* 2002.
""")

        pval_key  = "__pvalue__"
        gene_key  = "__target_gene__"
        group_key = "__patient_group__"

        correction_rows = [
            {
                "Gene":   r[gene_key],
                "Group":  r[group_key],
                "Raw p":  r[pval_key],
                "Test":   r.get("__test_method__", "—"),
            }
            for r in stats_data
            if r.get(pval_key) is not None
        ]

        if not correction_rows:
            st.info(_t.get('multigene_no_data', ''))
        else:
            n_tests   = len(correction_rows)
            raw_pvals = [r["Raw p"] for r in correction_rows]

            bonf = [min(p * n_tests, 1.0) for p in raw_pvals]

            ranked = sorted(range(n_tests), key=lambda k: raw_pvals[k])
            fdr    = [1.0] * n_tests
            for rank, idx in enumerate(ranked):
                fdr[idx] = min(raw_pvals[idx] * n_tests / (rank + 1), 1.0)
            for k in range(n_tests - 2, -1, -1):
                fdr[ranked[k]] = min(fdr[ranked[k]], fdr[ranked[k + 1]])

            for idx, row in enumerate(correction_rows):
                row["Bonferroni p"]     = round(bonf[idx], 4)
                row["FDR p (B-H)"]      = round(fdr[idx],  4)
                row["Sig (raw)"]        = "✅" if raw_pvals[idx] < 0.05 else "—"
                row["Sig (Bonferroni)"] = "✅" if bonf[idx]      < 0.05 else "—"
                row["Sig (FDR)"]        = "✅" if fdr[idx]        < 0.05 else "—"

            corr_df = pd.DataFrame(correction_rows)
            st.dataframe(corr_df, use_container_width=True)

            n_raw_sig  = sum(1 for p in raw_pvals if p < 0.05)
            n_bonf_sig = sum(1 for p in bonf       if p < 0.05)
            n_fdr_sig  = sum(1 for p in fdr         if p < 0.05)

            sum_col1, sum_col2, sum_col3 = st.columns(3)
            sum_col1.metric(_t.get('multigene_sig_raw', ''),  f"{n_raw_sig} / {n_tests}")
            sum_col2.metric(_t.get('multigene_sig_bonf', ''), f"{n_bonf_sig} / {n_tests}")
            sum_col3.metric(_t.get('multigene_sig_fdr', ''),  f"{n_fdr_sig} / {n_tests}")

            if n_raw_sig > n_fdr_sig:
                st.warning(_t.get('multigene_warning', '').format(lost=n_raw_sig - n_fdr_sig))
            elif n_raw_sig == n_fdr_sig and n_raw_sig > 0:
                st.success(_t.get('multigene_success', '').format(n=n_raw_sig))
            elif n_raw_sig == 0:
                st.info(_t.get('multigene_no_sig', ''))

            fig_corr = go.Figure()
            labels = [f"{r['Gene']} / {r['Group']}" for r in correction_rows]
            fig_corr.add_trace(go.Bar(name="Raw p",        x=labels, y=raw_pvals, marker_color="#4C72B0"))
            fig_corr.add_trace(go.Bar(name="Bonferroni p", x=labels, y=bonf,      marker_color="#DD8452"))
            fig_corr.add_trace(go.Bar(name="FDR p (B-H)",  x=labels, y=fdr,       marker_color="#55A868"))
            fig_corr.add_hline(y=0.05, line_dash="dash", line_color="red", annotation_text="a = 0.05", annotation_position="right")
            fig_corr.update_layout(
                barmode="group",
                title=_t.get('multigene_chart_title', ''),
                yaxis_title="p-value",
                xaxis_title=f"{_t.get('target_gene', "")} / {_t.get('patient_group', "")}",
                height=380
            )
            st.plotly_chart(fig_corr, use_container_width=True, key="multigene_corr_chart")

            corr_csv = corr_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label=_t.get('multigene_dl_button', ''),
                data=corr_csv,
                file_name="multi_gene_correction.csv",
                mime="text/csv",
                key="multigene_corr_dl"
            )

    elif stats_data and num_target_genes == 1:
        st.markdown("---")
        st.info(_t.get('multigene_1gene_note', ''))

    # ── Çoklu Gen Karşılaştırma Grafiği ──────────────────────────────────────
    st.markdown("---")
    if data and num_target_genes >= 2:
        st.subheader(f"📊 {_t.get('multigene_fc_chart_title', 'Multi-Gene Expression Comparison')}")

        # Collect fold changes per gene per group
        fc_key  = "__fc__"
        pf_key  = "__pfaffl__"
        tg_key2 = "__target_gene__"
        pg_key2 = "__patient_group__"
        reg_key = "__regulation__"

        method_choice = st.radio(
            "Method",
            ["2^(-ΔΔCq)", "Pfaffl"],
            horizontal=True,
            key="multigene_chart_method"
        )

        # Build matrix: genes × groups
        genes  = sorted(set(r[tg_key2] for r in data))
        groups = sorted(set(r[pg_key2] for r in data))
        palette = ['#3f51b5','#e91e63','#009688','#ff9800','#9c27b0','#795548']

        fig_multi = go.Figure()
        for gi, gene in enumerate(genes):
            y_vals = []
            for grp in groups:
                match = [r for r in data if r[tg_key2] == gene and r[pg_key2] == grp]
                if match:
                    val = match[0][fc_key] if method_choice == "2^(-ΔΔCq)" else match[0][pf_key]
                    y_vals.append(round(val, 4) if isinstance(val, float) else 0)
                else:
                    y_vals.append(0)
            fig_multi.add_trace(go.Bar(
                name=gene,
                x=groups,
                y=y_vals,
                marker_color=palette[gi % len(palette)],
                text=[f"{v:.3f}" for v in y_vals],
                textposition='outside',
            ))

        fig_multi.add_hline(y=1, line_dash="dash", line_color="black",
                            line_width=1, annotation_text="No change (1.0)",
                            annotation_position="right")
        fig_multi.update_layout(
            barmode='group',
            title=f"Gene Expression Fold Change — {method_choice}",
            xaxis_title=_t.get('patient_group', ''),
            yaxis_title=f"Fold Change ({method_choice})",
            legend_title=_t.get('target_gene', ''),
            height=420,
            plot_bgcolor='white',
            yaxis=dict(gridcolor='#eeeeee'),
        )
        st.plotly_chart(fig_multi, use_container_width=True, key="multigene_fc_chart")

        # Second chart: log2 fold change heatmap-style grouped bar
        if st.checkbox("Show log2 scale", key="multigene_log2"):
            import math
            fig_log = go.Figure()
            for gi, gene in enumerate(genes):
                y_log = []
                for grp in groups:
                    match = [r for r in data if r[tg_key2] == gene and r[pg_key2] == grp]
                    if match:
                        val = match[0][fc_key] if method_choice == "2^(-ΔΔCq)" else match[0][pf_key]
                        y_log.append(round(math.log2(val), 4) if isinstance(val, float) and val > 0 else 0)
                    else:
                        y_log.append(0)
                fig_log.add_trace(go.Bar(
                    name=gene, x=groups, y=y_log,
                    marker_color=palette[gi % len(palette)],
                    text=[f"{v:.3f}" for v in y_log],
                    textposition='outside',
                ))
            fig_log.add_hline(y=0, line_dash="dash", line_color="black", line_width=1)
            fig_log.update_layout(
                barmode='group',
                title=f"Gene Expression log2(Fold Change) — {method_choice}",
                xaxis_title=_t.get('patient_group', ''),
                yaxis_title="log2(Fold Change)",
                legend_title=_t.get('target_gene', ''),
                height=420, plot_bgcolor='white',
                yaxis=dict(gridcolor='#eeeeee', zeroline=True, zerolinecolor='black'),
            )
            st.plotly_chart(fig_log, use_container_width=True, key="multigene_fc_log2")
            st.caption("log2 > 0 = upregulated, log2 < 0 = downregulated, log2 = 0 = no change")

    # ── Dağılım Grafikleri ────────────────────────────────────────────────────
    st.markdown("---")

    # Allow user to choose which values to display in the distribution plot:
    # RQ (2^-ΔCq), raw ΔCt, or ΔΔCq (relative to control mean).
    plot_mode = st.radio(
        _t.get('dist_plot_mode_label', ''),
        options=[
            _t.get('dist_plot_rq', ''),
            _t.get('dist_plot_dct', ''),
            _t.get('dist_plot_ddct', ''),
        ],
        index=0,
        horizontal=True,
        key="dist_plot_mode",
        help=_t.get('dist_plot_help', '')
    )

    # Map selected option back to mode identifier
    if plot_mode == _t.get('dist_plot_rq', ''):
        _plot_mode_id = "RQ"
    elif plot_mode == _t.get('dist_plot_ddct', ''):
        _plot_mode_id = "DDCT"
    else:
        _plot_mode_id = "DCT"

    for i in range(num_target_genes):
        st.subheader(f"{_t.get('target_gene', "")} {i+1} - {_t.get('distribution_graph', "")}")

        control_target_ct_values = [
            d["__target_ct__"] 
            for d in input_values_table
            if d["Grup"] == "Control" and
               d["__target_gene__"] == f"Gene {i+1}" and
               d.get("__target_ct__") not in ("EXCLUDED", None) and
               d.get("Outlier Excluded", "No") == "No"
        ]
        control_reference_ct_values = [
            d["__ref_ct__"] 
            for d in input_values_table
            if d["Grup"] == "Control" and
               d["__target_gene__"] == f"Gene {i+1}" and
               d.get("__ref_ct__") not in ("EXCLUDED", None) and
               d.get("Outlier Excluded", "No") == "No"
        ]

        if len(control_target_ct_values) == 0 or len(control_reference_ct_values) == 0:
            st.error(f" {_t.get('error_missing_control_data', "").format(i=i+1)}")
            continue

        control_delta_ct = np.array(control_target_ct_values, dtype=float) - np.array(control_reference_ct_values, dtype=float)
        average_control_delta_ct = np.mean(control_delta_ct)

        # ── Convert values based on selected plot mode ────────────────────────
        def _transform(dct_array, mode, ctrl_mean):
            if mode == "RQ":
                return 2 ** (-np.array(dct_array))
            elif mode == "DDCT":
                return np.array(dct_array) - ctrl_mean
            else:
                return np.array(dct_array)

        def _yaxis_label(mode):
            if mode == "RQ":    return "RQ (2^-ΔCq)"
            elif mode == "DDCT": return "ΔΔCq (vs control mean)"
            else:                return "ΔCq"

        ctrl_plot_vals = _transform(control_delta_ct, _plot_mode_id, average_control_delta_ct)
        avg_ctrl_plot  = float(np.mean(ctrl_plot_vals))

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=[0.8, 1.2],
            y=[avg_ctrl_plot, avg_ctrl_plot],
            mode='lines',
            line=dict(color='black', width=4),
            name=_t.get('control_group_avg', '')
        ))

        for j in range(num_patient_groups):
            sample_dct_raw = [
                float(d["__dct_patient__"])
                for d in input_values_table
                if d["Grup"] == f"Group {j+1}" and
                   d["__target_gene__"] == f"Gene {i+1}" and
                   d.get("__dct_patient__") not in ("EXCLUDED", None) and
                   d.get("Outlier Excluded", "No") == "No"
            ]
            if not sample_dct_raw:
                continue
            smp_plot_vals   = _transform(sample_dct_raw, _plot_mode_id, average_control_delta_ct)
            avg_smp_plot    = float(np.mean(smp_plot_vals))
            fig.add_trace(go.Scatter(
                x=[(j + 1.8), (j + 2.2)],
                y=[avg_smp_plot, avg_smp_plot],
                mode='lines',
                line=dict(color='black', width=4),
                name=f"{_t.get('patient_group', "")} {j+1} {_t.get('avg', "")}"
            ))

        fig.add_trace(go.Scatter(
            x=np.ones(len(ctrl_plot_vals)) + np.random.uniform(-0.05, 0.05, len(ctrl_plot_vals)),
            y=ctrl_plot_vals,
            mode='markers',
            name="Control",
            marker=dict(color='blue'),
            text=[f"Control — {_yaxis_label(plot_mode)}={v:.4f}, replicate {idx+1}"
                  for idx, v in enumerate(ctrl_plot_vals)],
            hoverinfo='text'
        ))

        for j in range(num_patient_groups):
            sample_dct_raw = [
                float(d["__dct_patient__"])
                for d in input_values_table
                if d["Grup"] == f"Group {j+1}" and
                   d["__target_gene__"] == f"Gene {i+1}" and
                   d.get("__dct_patient__") not in ("EXCLUDED", None) and
                   d.get("Outlier Excluded", "No") == "No"
            ]
            if not sample_dct_raw:
                continue
            smp_plot_vals = _transform(sample_dct_raw, _plot_mode_id, average_control_delta_ct)
            fig.add_trace(go.Scatter(
                x=np.ones(len(smp_plot_vals)) * (j + 2) + np.random.uniform(-0.05, 0.05, len(smp_plot_vals)),
                y=smp_plot_vals,
                mode='markers',
                name=f"Group {j+1}",
                marker=dict(color='red'),
                text=[f"Group {j+1} — {_yaxis_label(plot_mode)}={v:.4f}, replicate {idx+1}"
                      for idx, v in enumerate(smp_plot_vals)],
                hoverinfo='text'
            ))

        fig.update_layout(
            title=f"{_t.get('target_gene', "")} {i+1} — {_yaxis_label(plot_mode)} Distribution",
            xaxis=dict(
                tickvals=[1] + [j + 2 for j in range(num_patient_groups)],
                ticktext=["Control"] + [f"Group {j+1}" for j in range(num_patient_groups)],
                title=_t.get('x_axis_title', "")
            ),
            yaxis=dict(title=_yaxis_label(plot_mode)),
            showlegend=True
        )
        st.plotly_chart(fig, use_container_width=True, key=f"dist_chart_{i}")

# ═══════════════════════════════════════════════════════════════════════════════
# SEKME 3: RAPOR
# ═══════════════════════════════════════════════════════════════════════════════

# ── PDF Font Sistemi ─────────────────────────────────────────────────────────
# Streamlit Cloud için: packages.txt'e fonts-noto ve fonts-noto-extra ekleyin
# requirements.txt'e: arabic-reshaper>=3.0.0  python-bidi>=0.4.2 ekleyin

def _find_font(candidates):
    """İlk bulunan geçerli font yolunu döndür."""
    import glob as _glob
    for p in candidates:
        if os.path.exists(p):
            return p
    # Sistem genelinde TTF ara
    all_ttf = _glob.glob('/usr/share/fonts/**/*.ttf', recursive=True)
    return all_ttf[0] if all_ttf else None

# Noto Sans: Türkçe, Fransızca, Almanca, İspanyolca
_NOTO_REGULAR = _find_font([
    '/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf',
    '/usr/share/fonts/opentype/noto/NotoSans-Regular.otf',
    '/usr/share/fonts/truetype/freefont/FreeSans.ttf',          # Streamlit fallback
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',          # son çare
])
_NOTO_BOLD = _find_font([
    '/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf',
    '/usr/share/fonts/opentype/noto/NotoSans-Bold.otf',
    '/usr/share/fonts/truetype/freefont/FreeSansBold.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
])
# Noto Sans Arabic: Arapça
_NOTO_ARABIC = _find_font([
    '/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf',
    '/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf',
    '/usr/share/fonts/opentype/noto/NotoSansArabic-Regular.otf',
    '/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf',      # fallback
    '/usr/share/fonts/truetype/freefont/FreeSans.ttf',
])
_NOTO_ARABIC_BOLD = _find_font([
    '/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf',
    '/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf',
    '/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf',
    '/usr/share/fonts/truetype/freefont/FreeSansBold.ttf',
])

from reportlab.pdfbase.pdfmetrics import registerFontFamily as _regFamily

try:
    pdfmetrics.registerFont(TTFont('NotoSans',      _NOTO_REGULAR))
    pdfmetrics.registerFont(TTFont('NotoSans-Bold', _NOTO_BOLD))
    _regFamily('NotoSans', normal='NotoSans', bold='NotoSans-Bold',
               italic='NotoSans', boldItalic='NotoSans-Bold')
    PDF_FONT      = 'NotoSans'
    PDF_FONT_BOLD = 'NotoSans-Bold'
except Exception:
    PDF_FONT      = 'Helvetica'
    PDF_FONT_BOLD = 'Helvetica-Bold'

# Arapça için ayrı font kaydı
_arabic_font_ok = False
if _NOTO_ARABIC and _NOTO_ARABIC != _NOTO_REGULAR:
    try:
        pdfmetrics.registerFont(TTFont('NotoArabic',      _NOTO_ARABIC))
        pdfmetrics.registerFont(TTFont('NotoArabic-Bold', _NOTO_ARABIC_BOLD or _NOTO_ARABIC))
        _regFamily('NotoArabic', normal='NotoArabic', bold='NotoArabic-Bold',
                   italic='NotoArabic', boldItalic='NotoArabic-Bold')
        ARABIC_FONT      = 'NotoArabic'
        ARABIC_FONT_BOLD = 'NotoArabic-Bold'
        _arabic_font_ok  = True
    except Exception:
        pass

if not _arabic_font_ok:
    ARABIC_FONT      = PDF_FONT        # fallback: NotoSans veya Helvetica
    ARABIC_FONT_BOLD = PDF_FONT_BOLD

# Eski kod uyumluluğu için alias
REGISTERED_FONT      = PDF_FONT
REGISTERED_FONT_BOLD = PDF_FONT_BOLD

# matplotlib da Noto kullan
try:
    import matplotlib as _mpl
    _noto_name = 'Noto Sans' if 'NotoSans' in PDF_FONT else 'DejaVu Sans'
    _mpl.rcParams['font.family'] = _noto_name
    _mpl.rcParams['axes.unicode_minus'] = False
except Exception:
    pass

def safe_str(text, lang='en'):
    """PDF için metni hazırla: XML kaçış + Arapça reshape/bidi."""
    if not isinstance(text, str):
        text = str(text)
    if lang == 'ar':
        try:
            import arabic_reshaper
            from bidi.algorithm import get_display
            text = get_display(arabic_reshaper.reshape(text))
        except ImportError:
            pass  # paket yoksa olduğu gibi bırak
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def get_pdf_fonts(lang):
    """Dile göre (normal_font, bold_font) döndür."""
    if lang == 'ar':
        return ARABIC_FONT, ARABIC_FONT_BOLD
    return PDF_FONT, PDF_FONT_BOLD

def create_pdf(results, stat_rows, input_df, language_code, multigroup_results=None):
    T   = translations[language_code]  # shorthand
    RTL = language_code == 'ar'        # sağdan sola dil mi?
    fn, fnb = get_pdf_fonts(language_code)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        leftMargin=50, rightMargin=50, topMargin=60, bottomMargin=50
    )
    elements = []
    styles = getSampleStyleSheet()

    # Metin hizalaması: Arapça için sağ, diğerleri için sol/orta
    _body_align  = 2 if RTL else 0   # 0=left, 1=center, 2=right
    _title_align = 1                  # başlıklar her zaman ortalı

    title_style   = ParagraphStyle('RT',  parent=styles['Title'],   fontName=fnb, fontSize=20, textColor=colors.HexColor('#1a237e'), spaceAfter=6,  alignment=_title_align)
    sub_style     = ParagraphStyle('RS',  parent=styles['Normal'],  fontName=fn,  fontSize=10, textColor=colors.HexColor('#555555'), spaceAfter=4,  alignment=_title_align)
    h1_style      = ParagraphStyle('H1',  parent=styles['Heading1'],fontName=fnb, fontSize=13, textColor=colors.HexColor('#1a237e'), spaceBefore=16,spaceAfter=5,  alignment=_body_align)
    h2_style      = ParagraphStyle('H2',  parent=styles['Heading2'],fontName=fnb, fontSize=11, textColor=colors.HexColor('#283593'), spaceBefore=10,spaceAfter=4,  alignment=_body_align)
    body_style    = ParagraphStyle('BD',  parent=styles['Normal'],  fontName=fn,  fontSize=9,  leading=13, spaceAfter=4, alignment=_body_align)
    small_style   = ParagraphStyle('SM',  parent=styles['Normal'],  fontName=fn,  fontSize=8,  leading=11, textColor=colors.HexColor('#444444'), alignment=_body_align)
    caption_style = ParagraphStyle('CA',  parent=styles['Normal'],  fontName=fn,  fontSize=8,  textColor=colors.HexColor('#666666'), alignment=1, spaceAfter=6)
    info_style    = ParagraphStyle('IN',  parent=styles['Normal'],  fontName=fn,  fontSize=9,  leading=13, backColor=colors.HexColor('#e8f4fd'), borderPad=6, leftIndent=8, rightIndent=8, spaceAfter=6, alignment=_body_align)
    warn_style    = ParagraphStyle('WN',  parent=styles['Normal'],  fontName=fn,  fontSize=9,  leading=13, backColor=colors.HexColor('#fff8e1'), borderPad=6, leftIndent=8, rightIndent=8, spaceAfter=6, alignment=_body_align)

    def hr():
        from reportlab.platypus import HRFlowable
        return HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#cccccc'), spaceAfter=8, spaceBefore=4)

    def s(key, **kw):
        """Get translated string, format with kwargs, make PDF-safe + Arabic reshape."""
        txt = T.get(key, key)
        if kw:
            try: txt = txt.format(**kw)
            except Exception: pass
        return safe_str(txt, lang=language_code)

    from reportlab.platypus import Flowable as _Flowable

    def make_table(rows, col_widths=None, header=True):
        if not rows: return Spacer(1,1)
        styled_rows = []
        _cell_align = 2 if RTL else 1
        for ri, row in enumerate(rows):
            styled_row = []
            for cell in row:
                # Hücre zaten ReportLab nesnesi ise (Paragraph vb.) olduğu gibi kullan
                if isinstance(cell, _Flowable):
                    styled_row.append(cell)
                    continue
                cell_str = safe_str(
                    str(cell) if not isinstance(cell, str) else cell,
                    lang=language_code
                )
                if ri == 0 and header:
                    p = Paragraph(cell_str, ParagraphStyle('TH', fontName=fnb, fontSize=7,
                                  textColor=colors.white, alignment=1))
                else:
                    p = Paragraph(cell_str, ParagraphStyle('TD', fontName=fn, fontSize=7,
                                  alignment=_cell_align))
                styled_row.append(p)
            styled_rows.append(styled_row)
        tbl = Table(styled_rows, colWidths=col_widths, repeatRows=1 if header else 0)
        tbl_style = [
            ('FONTNAME',    (0,0),(-1,-1), fn),
            ('ALIGN',       (0,0),(-1,-1), 'CENTER'),
            ('VALIGN',      (0,0),(-1,-1), 'MIDDLE'),
            ('GRID',        (0,0),(-1,-1), 0.3, colors.HexColor('#cccccc')),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white, colors.HexColor('#f5f7ff')]),
            ('TOPPADDING',  (0,0),(-1,-1), 4),
            ('BOTTOMPADDING',(0,0),(-1,-1), 4),
        ]
        if header:
            tbl_style += [('BACKGROUND',(0,0),(-1,0),colors.HexColor('#1a237e'))]
        tbl.setStyle(TableStyle(tbl_style))
        return tbl

    import datetime
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    # ── COVER PAGE ────────────────────────────────────────────────────────────
    elements.append(Spacer(1, 40))
    elements.append(Paragraph(safe_str("GeneQuantify"), title_style))
    elements.append(Paragraph(s('pdf_cover_subtitle'), sub_style))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph(s('pdf_generated', now=now), sub_style))
    elements.append(Paragraph(
        safe_str("Cite: Yalçınkaya B (2026). GeneQuantify. Mol Cell Biochem. https://doi.org/10.1007/s11010-026-05621-y"),
        sub_style
    ))
    elements.append(Spacer(1, 20))
    elements.append(hr())
    elements.append(Spacer(1, 10))

    n_genes    = len(set(r.get("__target_gene__", '') for r in results))
    n_groups   = len(set(r.get("__patient_group__", '') for r in results))
    n_samples  = len(input_df)
    n_excluded = sum(1 for _, row in input_df.iterrows()
                     if str(row.get('Outlier Excluded', 'No')).startswith('Yes'))
    norm_method = s('pdf_summary_norm_multi') if num_ref_genes > 1 else s('pdf_summary_norm_single')

    summary_rows = [
        [s('pdf_summary_param'), s('pdf_summary_val')],
        [s('pdf_summary_genes'),   str(n_genes)],
        [s('pdf_summary_groups'),  str(n_groups)],
        [s('pdf_summary_samples'), str(n_samples)],
        [s('pdf_summary_excluded'),str(n_excluded)],
        [s('pdf_summary_tests'),   f"{len(stat_rows)} {s('pdf_summary_tests')}"],
        [s('pdf_summary_norm'),    norm_method],
        [s('pdf_summary_methods'), s('pdf_summary_methods_val')],
    ]
    elements.append(make_table(summary_rows, col_widths=[260, 200]))
    elements.append(Spacer(1, 14))
    elements.append(Paragraph(s('pdf_disclaimer'), small_style))
    elements.append(PageBreak())

    # ── SECTION 1: METHODS ────────────────────────────────────────────────────
    elements.append(Paragraph(s('pdf_s1_title'), h1_style))
    elements.append(hr())

    elements.append(Paragraph(s('pdf_s1_calc'), h2_style))
    elements.append(Paragraph(s('pdf_s1_calc_body'), body_style))
    elements.append(Paragraph(s('pdf_s1_classic'), body_style))
    elements.append(Paragraph(s('pdf_s1_pfaffl'), body_style))

    elements.append(Paragraph(s('pdf_s1_norm'), h2_style))
    if num_ref_genes > 1:
        elements.append(Paragraph(s('pdf_s1_norm_multi', n=num_ref_genes), body_style))
    else:
        elements.append(Paragraph(s('pdf_s1_norm_single'), body_style))

    elements.append(Paragraph(s('pdf_s1_eff'), h2_style))
    eff_cols = T.get('pdf_eff_cols', ['Gene','E(t)','Eff%(t)','E(r)','Eff%(r)','Diff%','Status'])
    eff_rows = [eff_cols]
    for i, eff in gene_efficiencies.items():
        e_t = eff["target_E"]; e_r = eff["ref_E"]
        t_pct = (e_t-1)*100; r_pct = (e_r-1)*100; diff = abs(t_pct-r_pct)
        status = s('pdf_eff_ok') if diff <= efficiency_threshold else s('pdf_eff_warn')
        eff_rows.append([f"{T.get('target_gene','Gene')} {i+1}",
                         f"{e_t:.4f}", f"{t_pct:.1f}%",
                         f"{e_r:.4f}", f"{r_pct:.1f}%",
                         f"{diff:.1f}%", status])
    cw7 = (letter[0]-100)/7
    elements.append(make_table(eff_rows, col_widths=[cw7]*7))
    elements.append(Paragraph(s('pdf_s1_eff_range', thr=efficiency_threshold), small_style))

    elements.append(Paragraph(s('pdf_s1_outlier'), h2_style))
    if outlier_enabled:
        if outlier_method == "Grubbs":
            elements.append(Paragraph(s('pdf_s1_grubbs', alpha=grubbs_alpha, n=n_excluded), body_style))
        else:
            elements.append(Paragraph(s('pdf_s1_iqr', k=iqr_multiplier, n=n_excluded), body_style))
        if n_excluded > 0:
            elements.append(Paragraph(s('pdf_s1_outlier_warn'), warn_style))
    else:
        elements.append(Paragraph(s('pdf_s1_outlier_off'), body_style))
    elements.append(PageBreak())

    # ── SECTION 2: INPUT DATA ─────────────────────────────────────────────────
    elements.append(Paragraph(s('pdf_s2_title'), h1_style))
    elements.append(hr())
    elements.append(Paragraph(s('pdf_s2_body'), body_style))
    elements.append(Spacer(1, 6))

    if not input_df.empty:
        cols = input_df.columns.tolist()
        page_w = letter[0] - 100
        cw = page_w / max(len(cols), 1)

        # Header satırı
        tbl_rows = [cols]

        for _, row in input_df.iterrows():
            is_excl = str(row.get('Outlier Excluded', 'No')).startswith('Yes')
            row_cells = []
            for v in row.tolist():
                cell_str = safe_str(str(v) if v is not None else '', lang=language_code)
                style = ParagraphStyle(
                    'EX' if is_excl else 'TD',
                    fontName=fn, fontSize=7, alignment=1,
                    textColor=colors.HexColor('#cc0000') if is_excl else colors.black
                )
                row_cells.append(Paragraph(cell_str, style))
            tbl_rows.append(row_cells)

        elements.append(make_table(tbl_rows, col_widths=[cw]*len(cols)))
    elements.append(PageBreak())

    # ── SECTION 3: RESULTS ────────────────────────────────────────────────────
    elements.append(Paragraph(s('pdf_s3_title'), h1_style))
    elements.append(hr())
    elements.append(Paragraph(s('pdf_s3_body'), body_style))
    elements.append(Spacer(1, 6))

    res_cols = T.get('pdf_res_cols', ['Gene','Group','ΔCq Ctrl','ΔCq Sample','ΔΔCq','2^(-ΔΔCq)','Pfaffl','Reg','Et','Er'])
    res_rows = [res_cols]
    for r in results:
        ddc = r.get("__ddct__", '')
        fc  = r.get("__fc__", '')
        pf  = r.get("__pfaffl__", '')
        dcc = r.get("__dct_ctrl__", '')
        dcs = r.get("__dct_patient__", '')
        et  = r.get('E target', ''); er = r.get('E ref', '')
        res_rows.append([
            str(r.get("__target_gene__",'')),
            str(r.get("__patient_group__",'')),
            f"{dcc:.4f}" if isinstance(dcc, float) else str(dcc),
            f"{dcs:.4f}" if isinstance(dcs, float) else str(dcs),
            f"{ddc:.4f}" if isinstance(ddc, float) else str(ddc),
            f"{fc:.4f}"  if isinstance(fc,  float) else str(fc),
            f"{pf:.4f}"  if isinstance(pf,  float) else str(pf),
            str(r.get("__regulation__", s('pdf_nochange'))),
            str(et), str(er)
        ])
    cw10 = (letter[0]-100)/10
    elements.append(make_table(res_rows, col_widths=[cw10]*10))
    elements.append(Spacer(1, 8))

    # Fold change bar chart
    if results:
        try:
            fig_fc, ax_fc = plt.subplots(figsize=(7, 3.5))
            labels_fc = [f"{r.get("__target_gene__",'')} /\n{r.get("__patient_group__",'')}" for r in results]
            vals_2  = [r.get("__fc__", 0) for r in results]
            vals_pf = [r.get("__pfaffl__", 0) for r in results]
            xr = range(len(labels_fc)); w = 0.35
            b1 = ax_fc.bar([i-w/2 for i in xr], vals_2,  width=w, label='2^(-ΔΔCq)', color='#3f51b5', alpha=0.85)
            b2 = ax_fc.bar([i+w/2 for i in xr], vals_pf, width=w, label='Pfaffl',    color='#e91e63', alpha=0.85)
            ax_fc.axhline(y=1, color='black', linestyle='--', linewidth=0.8, alpha=0.6)
            ax_fc.set_xticks(list(xr)); ax_fc.set_xticklabels(labels_fc, fontsize=7)
            ax_fc.set_ylabel('Fold Change', fontsize=9)
            ax_fc.set_title('Gene Expression Fold Change', fontsize=10, fontweight='bold')
            ax_fc.legend(fontsize=8)
            ax_fc.spines['top'].set_visible(False); ax_fc.spines['right'].set_visible(False)
            for bar in [*b1, *b2]:
                ax_fc.text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.02,
                           f'{bar.get_height():.2f}', ha='center', va='bottom', fontsize=6)
            plt.tight_layout()
            ib = BytesIO(); plt.savefig(ib, format='png', dpi=150, bbox_inches='tight'); plt.close(); ib.seek(0)
            elements.append(RLImage(ib, width=460, height=230))
            elements.append(Paragraph(s('pdf_fig1'), caption_style))
        except Exception:
            pass
    elements.append(PageBreak())

    # ── SECTION 4: STATISTICS ─────────────────────────────────────────────────
    elements.append(Paragraph(s('pdf_s4_title'), h1_style))
    elements.append(hr())
    elements.append(Paragraph(s('pdf_s4_body'), body_style))
    elements.append(Spacer(1, 6))

    # Determine if any gene has 3+ groups (multigroup scenario)
    _has_multigroup = (
        multigroup_results is not None
        and any(r.get("n_groups", 0) >= 3 for r in multigroup_results)
    )

    if _has_multigroup:
        # ── 4a. Pairwise Control comparisons (t-test) for all genes ──────────
        # Still show pairwise tests for genes with only 2 groups
        _pairwise_rows = [r for r in stat_rows]
        _2group_genes = set()
        if multigroup_results:
            for _mg in multigroup_results:
                if _mg.get("n_groups", 0) < 3:
                    _2group_genes.add(_mg.get("gene", ""))

        _pairwise_show = [r for r in _pairwise_rows if r.get("__target_gene__", "") in _2group_genes]

        if _pairwise_show:
            elements.append(Paragraph(
                safe_str("4.1 Pairwise Comparisons (Control vs Group) — 2-Group Genes"),
                h2_style
            ))
            stat_cols = T.get('pdf_stat_cols', ['Gene','Comparison','Type','Method','p','Sig'])
            _pw_table = [stat_cols]
            for _r in _pairwise_show:
                _pw_table.append([
                    str(_r.get("__target_gene__", '')),
                    str(_r.get('Comparison', '')),
                    str(_r.get("__test_type__", '')),
                    str(_r.get("__test_method__", '')),
                    f"{_r.get('__pvalue__', 0):.4f}",
                    str(_r.get("__significance__", '')),
                ])
            cw6 = (letter[0]-100)/6
            elements.append(make_table(_pw_table, col_widths=[cw6]*6))
            elements.append(Spacer(1, 10))

        # ── 4b. Multi-group ANOVA/Kruskal-Wallis results ─────────────────────
        elements.append(Paragraph(
            safe_str("4.2 Multi-Group Comparison (≥3 Groups) — Omnibus + Post-hoc"),
            h2_style
        ))
        elements.append(Paragraph(
            safe_str(
                "All inferential tests are performed on RQ values (2^\u2212\u0394Cq). "
                "With \u22653 groups, an omnibus test (One-way ANOVA or Kruskal-Wallis) is applied first, "
                "followed by pairwise post-hoc comparisons with Bonferroni and FDR correction. "
                "Test selection is automatic based on normality (Shapiro-Wilk, n\u22658) and variance homogeneity (Levene)."
            ),
            body_style
        ))
        elements.append(Spacer(1, 6))

        for _mg in (multigroup_results or []):
            if _mg.get("n_groups", 0) < 3:
                continue
            _gene = _mg.get("gene", "")
            _omni_test = _mg.get("omnibus_test", "—")
            _omni_p    = _mg.get("omnibus_p", None)
            _omni_sig  = _mg.get("omnibus_sig", "—")
            _norm_ok   = _mg.get("normality_ok", True)
            _var_ok    = _mg.get("variance_ok", True)
            _posthoc   = _mg.get("posthoc_method", "—")

            # Decision pathway text
            if _norm_ok and _var_ok:
                _decision_txt = "Normal distribution + equal variances \u2192 One-way ANOVA + Tukey HSD"
            elif _norm_ok and not _var_ok:
                _decision_txt = "Normal distribution + unequal variances \u2192 Welch ANOVA + Games-Howell"
            else:
                _decision_txt = "Non-normal distribution \u2192 Kruskal-Wallis + Dunn (Mann-Whitney U)"

            elements.append(Paragraph(safe_str(f"\u25b6 {_gene}"), h2_style))
            elements.append(Paragraph(safe_str(f"Test selection: {_decision_txt}"), body_style))

            _omni_p_str = f"{_omni_p:.4f}" if _omni_p is not None else "—"
            _omni_table = [
                [safe_str("Omnibus Test"), safe_str("p-value"), safe_str("Result")],
                [safe_str(_omni_test), safe_str(_omni_p_str), safe_str(_omni_sig)],
            ]
            elements.append(make_table(_omni_table, col_widths=[240, 120, 100]))
            elements.append(Spacer(1, 6))

            # Post-hoc table
            _ph_rows = _mg.get("posthoc_rows", [])
            if _ph_rows:
                elements.append(Paragraph(
                    safe_str(f"Post-hoc comparisons ({_posthoc}) — RQ-based:"),
                    body_style
                ))
                _ph_header = [
                    safe_str("Comparison"),
                    safe_str("Raw p"),
                    safe_str("Bonferroni p"),
                    safe_str("FDR p (B-H)"),
                    safe_str("Sig (raw)"),
                    safe_str("Sig (FDR)"),
                ]
                _ph_table_rows = [_ph_header]
                # collect all pvals for chart
                _ph_labels_chart = []
                _ph_pvals_chart  = []
                for _ph in _ph_rows:
                    _raw_p = _ph.get("Raw p", 1)
                    _sig_raw = "Sig" if _raw_p < 0.05 else "n.s."
                    _fdr_p   = _ph.get("FDR p (B-H)", 1)
                    _sig_fdr = "Sig" if _fdr_p < 0.05 else "n.s."
                    _ph_table_rows.append([
                        safe_str(str(_ph.get("Comparison",""))),
                        safe_str(f"{_raw_p:.4f}"),
                        safe_str(f"{_ph.get('Bonferroni p', 1):.4f}"),
                        safe_str(f"{_fdr_p:.4f}"),
                        safe_str(_sig_raw),
                        safe_str(_sig_fdr),
                    ])
                    _ph_labels_chart.append(f"{_gene} / {_ph.get('Comparison','')}")
                    _ph_pvals_chart.append(_raw_p)

                cw6b = (letter[0]-100)/6
                elements.append(make_table(_ph_table_rows, col_widths=[cw6b]*6))
                elements.append(Spacer(1, 6))

                # p-value bar chart for this gene's post-hoc
                try:
                    _fig_mg, _ax_mg = plt.subplots(figsize=(7, max(2.5, 0.4 * len(_ph_labels_chart) + 1)))
                    _bar_c = ['#e53935' if p < 0.05 else '#90a4ae' for p in _ph_pvals_chart]
                    _ax_mg.barh(_ph_labels_chart, _ph_pvals_chart, color=_bar_c, alpha=0.85)
                    _ax_mg.axvline(x=0.05, color='black', linestyle='--', linewidth=0.9)
                    _ax_mg.set_xlabel('p-value (raw)', fontsize=9)
                    _ax_mg.set_title(f'Post-hoc p-values — {_gene}', fontsize=10, fontweight='bold')
                    for _ii, _vv in enumerate(_ph_pvals_chart):
                        _ax_mg.text(min(_vv + 0.002, 0.045), _ii, f'{_vv:.4f}', va='center', fontsize=7)
                    _ax_mg.spines['top'].set_visible(False); _ax_mg.spines['right'].set_visible(False)
                    plt.tight_layout()
                    _ib_mg = BytesIO()
                    plt.savefig(_ib_mg, format='png', dpi=150, bbox_inches='tight')
                    plt.close()
                    _ib_mg.seek(0)
                    _img_h = max(130, 40 * len(_ph_labels_chart) + 60)
                    elements.append(RLImage(_ib_mg, width=460, height=min(_img_h, 260)))
                    elements.append(Paragraph(
                        safe_str(
                            f"Figure. Post-hoc p-values for {_gene}. "
                            "Red bars = significant (p < 0.05). Dashed line = significance threshold."
                        ),
                        caption_style
                    ))
                except Exception:
                    pass

            elements.append(Spacer(1, 10))

    else:
        # ── Standard 2-group: pairwise stat table ─────────────────────────────
        stat_cols = T.get('pdf_stat_cols', ['Gene','Comparison','Type','Method','p','Sig'])
        stat_table_rows = [stat_cols]
        for st_row in stat_rows:
            stat_table_rows.append([
                str(st_row.get("__target_gene__", '')),
                str(st_row.get('Comparison', '')),
                str(st_row.get("__test_type__", '')),
                str(st_row.get("__test_method__", '')),
                f"{st_row.get('__pvalue__', 0):.4f}",
                str(st_row.get("__significance__", '')),
            ])
        cw6 = (letter[0]-100)/6
        elements.append(make_table(stat_table_rows, col_widths=[cw6]*6))
        elements.append(Spacer(1, 8))

        # p-value chart
        if stat_rows:
            try:
                fig_p, ax_p = plt.subplots(figsize=(7, max(2.5, 0.4 * len(stat_rows) + 1)))
                labels_p = [f"{sr.get('__target_gene__','')} / {sr.get('Comparison','')}" for sr in stat_rows]
                pvals = [sr.get("__pvalue__", 1) for sr in stat_rows]
                bar_colors = ['#e53935' if p < 0.05 else '#90a4ae' for p in pvals]
                ax_p.barh(labels_p, pvals, color=bar_colors, alpha=0.85)
                ax_p.axvline(x=0.05, color='black', linestyle='--', linewidth=0.9)
                ax_p.set_xlabel('p-value', fontsize=9)
                ax_p.set_title('Statistical Test p-values', fontsize=10, fontweight='bold')
                for i, v in enumerate(pvals):
                    ax_p.text(v+0.005, i, f'{v:.4f}', va='center', fontsize=7)
                ax_p.spines['top'].set_visible(False); ax_p.spines['right'].set_visible(False)
                plt.tight_layout()
                ib2 = BytesIO(); plt.savefig(ib2, format='png', dpi=150, bbox_inches='tight'); plt.close(); ib2.seek(0)
                elements.append(RLImage(ib2, width=460, height=200))
                elements.append(Paragraph(s('pdf_fig2'), caption_style))
            except Exception:
                pass

    elements.append(Spacer(1, 10))
    elements.append(Paragraph(s('pdf_s4_interp'), h2_style))
    elements.append(Paragraph(s('pdf_s4_interp_body'), body_style))
    elements.append(PageBreak())

    # ── SECTION 5: DELTA CT PLOTS ─────────────────────────────────────────────
    elements.append(Paragraph(s('pdf_s5_title'), h1_style))
    elements.append(hr())
    elements.append(Paragraph(s('pdf_s5_body'), body_style))
    elements.append(Spacer(1, 8))

    tg_key_  = "__target_gene__"
    dcp_key_ = "__dct_patient__"
    palette  = ['#3f51b5','#e91e63','#009688','#ff9800','#9c27b0']

    for i in range(num_target_genes):
        gene_label = f"Gene {i+1}"          # sabit değer — sütun adı değil
        try:
            fig_d, ax_d = plt.subplots(figsize=(6, 3.2))
            all_vals = []; all_labels = []
            ctrl_dct_vals = [
                float(d["__dct_ctrl__"]) for d in input_values_table
                if d.get(tg_key_) == gene_label
                and d.get("__dct_ctrl__") not in ("EXCLUDED", None)
                and d.get("Outlier Excluded", "No") == "No"
            ]
            # Convert ΔCq to RQ = 2^(-ΔCt) for visualization.
            # Plotting raw ΔCt is misleading because higher ΔCt = lower expression,
            # which is counter-intuitive. RQ values reflect actual expression levels.
            ctrl_vals = [2 ** (-v) for v in ctrl_dct_vals]
            if ctrl_vals:
                all_vals.append(ctrl_vals)
                all_labels.append(T['control_group'])
            for j in range(num_patient_groups):
                pg = f"Group {j+1}"
                smp_dct_vals = [float(d[dcp_key_]) for d in input_values_table
                      if d.get(tg_key_) == gene_label
                      and d.get("Grup") == pg
                      and d.get(dcp_key_) not in ("EXCLUDED", None)
                      and d.get("Outlier Excluded","No") == "No"]
                sv = [2 ** (-v) for v in smp_dct_vals]
                if sv:
                    all_vals.append(sv); all_labels.append(pg)
            for k, (vals, lbl) in enumerate(zip(all_vals, all_labels)):
                col = palette[k % len(palette)]
                jitter = np.random.uniform(-0.08, 0.08, len(vals))
                ax_d.scatter([k+1+j for j in jitter], vals, color=col, alpha=0.75, s=28, zorder=3)
                ax_d.hlines(np.mean(vals), k+0.75, k+1.25, colors='black', linewidths=2, zorder=4)
            ax_d.set_xticks(range(1, len(all_labels)+1))
            ax_d.set_xticklabels(all_labels, fontsize=8)
            ax_d.set_ylabel('RQ (2^-ΔCq)', fontsize=9)
            ax_d.set_title(f'{gene_label} — Relative Quantity (RQ)', fontsize=10, fontweight='bold')
            ax_d.spines['top'].set_visible(False); ax_d.spines['right'].set_visible(False)
            plt.tight_layout()
            ib3 = BytesIO(); plt.savefig(ib3, format='png', dpi=150, bbox_inches='tight'); plt.close(); ib3.seek(0)
            elements.append(RLImage(ib3, width=420, height=210))
            elements.append(Paragraph(s('pdf_fig3', gene=gene_label), caption_style))
            elements.append(Spacer(1, 10))
        except Exception:
            pass
    elements.append(PageBreak())

    # ── SECTION 6: INTERPRETATION ─────────────────────────────────────────────
    elements.append(Paragraph(s('pdf_s6_title'), h1_style))
    elements.append(hr())

    elements.append(Paragraph(s('pdf_s6_fc'), h2_style))
    fc_hdr  = T.get('pdf_fc_interp_header', ['FC','ΔΔCq','Interpretation','Significance'])
    fc_rows_data = T.get('pdf_fc_interp_rows', [])
    elements.append(make_table([fc_hdr] + fc_rows_data, col_widths=[(letter[0]-100)/4]*4))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph(s('pdf_stat_note'), info_style))

    elements.append(Paragraph(s('pdf_s6_choose'), h2_style))
    elements.append(Paragraph(s('pdf_s6_choose_body'), body_style))

    elements.append(Paragraph(s('pdf_s6_stat'), h2_style))
    elements.append(Paragraph(s('pdf_s6_stat_body'), body_style))
    elements.append(PageBreak())

    # ── SECTION 7: REFERENCES ─────────────────────────────────────────────────
    elements.append(Paragraph(s('pdf_s7_title'), h1_style))
    elements.append(hr())
    refs = [
        "Yalçınkaya B (2026). GeneQuantify: a web-based tool for qPCR gene expression and copy number variation analysis. Molecular and Cellular Biochemistry. https://doi.org/10.1007/s11010-026-05621-y",
        "Livak KJ & Schmittgen TD (2001). Methods, 25(4), 402-408. (ΔΔCq)",
        "Pfaffl MW (2001). Nucleic Acids Research, 29(9), e45. (Pfaffl)",
        "Vandesompele J et al. (2002). Genome Biology, 3(7). (geNorm)",
        "Bustin SA et al. (2009). Clinical Chemistry, 55(4), 611-622. (MIQE)",
        "Grubbs FE (1969). Technometrics, 11(1), 1-21.",
        "Tukey JW (1977). Exploratory Data Analysis. Addison-Wesley.",
        "Benjamini Y & Hochberg Y (1995). J Royal Stat Soc B, 57(1), 289-300. (FDR)",
    ]
    for ref in refs:
        elements.append(Paragraph(safe_str(f"• {ref}"), small_style))
        elements.append(Spacer(1, 3))

    elements.append(Spacer(1, 16))
    elements.append(hr())
    elements.append(Paragraph(
        safe_str(f"{s('pdf_footer')} | {s('pdf_generated', now=now)} | {s('pdf_contact')}"),
        small_style))

    doc.build(elements)
    buffer.seek(0)
    return buffer



with tab_report:
    st.markdown(f"### 📄 {_t.get('pdf_report', "")}")
    st.markdown("---")
    if not input_values_table:
        st.info(_t.get('error_no_data', ''))
    else:
        st.success('✅ ' + _t.get('pdf_ready', '{n} records ready').format(n=len(input_values_table)))
        if st.button(f"📥 {_t.get('generate_pdf', "")}", key="pdf_btn"):
            pdf_buffer = create_pdf(data, stats_data, pd.DataFrame(input_values_table), language_code, multigroup_results=multigroup_results)
            st.download_button(
                label=f"⬇️ {_t.get('pdf_report', "")}",
                data=pdf_buffer,
                file_name="gen_ekspresyon_raporu.pdf",
                mime="application/pdf",
                key="pdf_dl"
            )

st.sidebar.divider()
c1, c2 = st.sidebar.columns(2)
with c1:
    st.sidebar.link_button(
        "⬇️ Desktop",
        "https://drive.google.com/file/d/1zxmAKWm-cV_W2dCMCtb-momEau75UpXg/view?usp=sharing",
        use_container_width=True
    )
with c2:
    st.sidebar.link_button(
        "⭐ GitHub",
        "https://github.com/burhanettiny/GeneQuantify",
        use_container_width=True
    )
st.sidebar.caption("GeneQuantify — GPL-3.0 | [email removed]")

st.sidebar.link_button(
    "📄 How to Cite (Mol Cell Biochem)",
    "https://link.springer.com/article/10.1007/s11010-026-05621-y",
    use_container_width=True
)
st.sidebar.caption("Yalçınkaya B (2026). Mol Cell Biochem. doi:10.1007/s11010-026-05621-y")

st.sidebar.divider()
st.sidebar.markdown(
    f"<div style='font-size:12px;font-weight:600;color:#004d40;margin-bottom:2px;'>"
    f"{_t.get('sidebar_absolutegene_title', '🧪 Need absolute quantification?')}</div>",
    unsafe_allow_html=True
)
st.sidebar.caption(_t.get(
    'sidebar_absolutegene_caption',
    "For digital PCR (dPCR/ddPCR) — Poisson-based absolute quantification, "
    "CNV, VAF/mutation fraction — try AbsoluteGene, GeneQuantify's companion tool."
))
st.sidebar.link_button(
    _t.get('sidebar_absolutegene_btn', "🧪 Open AbsoluteGene (dPCR)"),
    "https://absolutegene.streamlit.app/",
    use_container_width=True
)
