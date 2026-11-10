# Inject custom CSS to make sidebar wider and force it open by default
import streamlit as st
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from typing import Optional, Dict, Any
from pathlib import Path
from io import BytesIO
import pandas as pd
import urllib.parse
import subprocess
import datetime
import tempfile
import requests
import yaml
import html

import src.streamlit_pandas as streamlit_pandas
from src.css_styles import apply_custom_css

# ─── CONSTANTS & HELPERS ─────────────────────────────────────────────────────
GITHUB_BLOB_BASE = "blob"
NOT_AVAILABLE = "_not available_"

def get_repo_branch(repo_path: Path) -> str:
    """Return the current branch name for the cloned repository."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        branch = result.stdout.strip()
        return branch or "main"
    except Exception:
        return "main"


def normalize_repo_url(url: str) -> str:
    """Strip trailing slashes and .git from a GitHub repository URL."""
    cleaned = url.strip()
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]
    return cleaned.rstrip("/")

# ─── PAGE CONFIG ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="LabChronicle | Lab Database",
    layout="wide",
    page_icon="🔬",
    initial_sidebar_state="auto",
    menu_items={
        'Get Help': 'https://www.extremelycoolapp.com/help',
        'Report a bug': "https://www.extremelycoolapp.com/bug",
        'About': "# This is a header. This is an *extremely* cool app!"
    }
)

# Apply the CSS function
apply_custom_css()

# ─── HEADER MARKDOWN ────────────────────────────────────────────────────────
st.markdown("""
<div class="gradient-header">
  <h1>
    LabChronicle <span style="font-size:0.7em;font-weight:300;">| Database Visualizer</span>
  </h1>
  <span style="color:#e0ecff;font-size:1.1em;">
    🔬 All your lab databases (experiments, reagents, cell lines, etc.), in one place
  </span>
</div>
""", unsafe_allow_html=True)

# ─── PDF EXPORTER ────────────────────────────────────────────────────────────

def df_to_pdf(df):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        leftMargin=0.5*inch,
        rightMargin=0.5*inch,
        topMargin=0.5*inch,
        bottomMargin=0.5*inch
    )
    styles = getSampleStyleSheet()
    base_style = styles["Normal"]
    style = ParagraphStyle(
        name="ExportBody",
        parent=base_style,
        fontSize=8,
        leading=10,
    )
    link_style = ParagraphStyle(
        name="ExportLink",
        parent=style,
        textColor=colors.blue,
        underline=True,
    )

    def make_paragraph(value: Any) -> Paragraph:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            text = ""
            return Paragraph(text, style)

        text = str(value)
        if text.startswith("http://") or text.startswith("https://"):
            safe_url = html.escape(text, quote=True)
            display_text = html.escape(text, quote=True)
            return Paragraph(f'<link href="{safe_url}">{"Link"}</link>', link_style)

        safe_text = html.escape(text)
        return Paragraph(safe_text, style)

    # Prepare table data with wrapped text
    data = [[Paragraph(html.escape(str(col)), style) for col in df.columns]]
    for _, row in df.iterrows():
        data.append([make_paragraph(cell) for cell in row])

    num_cols = len(df.columns)
    page_width = landscape(letter)[0] - doc.leftMargin - doc.rightMargin
    col_width = page_width / num_cols if num_cols else page_width

    # repeatRows=1 ensures the header row is repeated on each page
    table = Table(data, colWidths=[col_width]*num_cols, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.whitesmoke),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))

    doc.build([table])
    buffer.seek(0)
    return buffer.getvalue()

# ─── CONFIGS ────────────────────────────────────────────────────────────────
DESKTOP_CONFIG = {
    "animal_models": {
        "animal_model_name": "text",
        "organism": "multiselect",
        "background": "text",
        "strain": "text",
        "genotype": "text",
        "source": "text",
        "catalogue_number": "text",
        "website": "text",
        "sex": "multiselect",
        "notes": "text"
    },
    "antibodies": {
        "antibody_name": "text",
        "protein_target": "text",
        "antibody_target": "multiselect",
        "location": "multiselect",
        "clonality": "multiselect",
        "host_species": "multiselect",
        "species_reactivity": "multiselect",
        "catalog_id": "text",
        "source": "text",
        "applications": "multiselect",
        "dilutions.Immunofluorescence": 'text',
        "dilutions.Western Blot": 'text',
        "dilutions.IHC": 'text',
        "dilutions.IP": 'text',
        "dilutions.Flow Cytometry": 'text',
        "validation.Immunofluorescence": "boolean",
        "validation.Western Blot": "boolean",
        "validation.IHC": "boolean",
        "validation.IP": "boolean",
        "validation.Flow Cytometry": "boolean",
        "notes": "-",
        "website": "-",
        "status.tube": "multiselect",
        "status.reorder": "multiselect",
        "status.last_checked": "date"
    },
    "cell_lines": {
        "cell_line_name": "text",
        "organism": "text",
        "tissue": "text",
        "type": "text",
        "derived_from": "text",
        "resistance": "text",
        "modifications": "text",
        "notes": "-",
        "source": "text",
        "catalog_id": "text",
        "publication": "text",
        "authentication": "text",
        "storage.location": "multiselect",
    },
    "plasmids": {
        "plasmid_name": "text",
        "backbone": "text",
        "promoter": "text",
        "tag": "text",
        "origin": "text",
        "catalog_id": "text",
        "website": "-",
        "expression_host": "text",
        "sequencing_validation": "text",
        "location": "multiselect",
        "notes": "text",
        "status": "text",
        "MTA": "text",
        "publications": "text"
    },
    "dyes": {
        "dye_target": "text",
        "dye_name": "text",
        "dye_type": "multiselect",
        "company": "multiselect",
        "catalog_id": "text",
        "website": "-",
        "live_imaging": "multiselect",
        "fixed_sample": "multiselect",
        "light_sensitive": "multiselect",
        "solvent": "text",
        "stock_concentration": "text",
        "working_concentration": "text",
        "location": "multiselect",
        "date": "date",
        "status.tube": "multiselect",
        "status.reorder": "multiselect",
        "status.last_checked": "date",
        "notes": "-"
    },
    "small_molecules": {
        # "compound": "text",
        "small_molecule_name": "text",
        "company": "multiselect",
        "aliases": "text",
        "catalog_id": "text",
        "website": "-",
        "cas": "text",
        "solvent": "text",
        "stock_concentration": "text",
        "working_concentration": "text",
        "location": "multiselect",
        "storage": "text",
        "light_sensitive": "multiselect",
        "date": "date",
        "status.tube": "multiselect",
        "status.reorder": "multiselect",
        "status.last_checked": "date",
        "notes": "-"
    },
    "sirnas": {
        "gene": "text",
        "sirna_name": "text",
        "species": "text",
        "sequence": "text",
        "company": "multiselect",
        "catalog_id": "text",
        # "efficiency": "text",
        # "time": "text",
        "notes": "-",
        "location": "multiselect",
        "date": "date",
        "status.tube": "multiselect",
        "status.reorder": "multiselect",
        "status.last_checked": "date"
    },
    "experiments": {
        "experiment_name": "text",
        "date_started": "text",
        "performed_by": "text",
        "primary_method": "text",
        "cell_lines": "text",
        "animal_models": "text",
        "global_metadata.Microscope": "text",
        "global_metadata.Live Imaging": "text",
        "conditions": "text",
        "device_name": "text",
        "location": "text",
        "lab_chronicle_version": "text",
        "experiment_description": "text"
    },
    "publications": {
        "title": "text",
        "stage": "multiselect",
        "num_figures": "number",
        "experiment_sources": "multiselect"
    }
}

IGNORE_FILTER_COLUMNS = {
    "animal_models": ["source_file", "website", "notes"],
    "antibodies": ["source_file", "website", "notes"],
    "cell_lines": ["source_file", "publication", "notes"],
    "plasmids": ["source_file", "website", "notes"],
    "dyes": ["source_file", "website", "notes"],
    "small_molecules": ["source_file", "website", "notes"],
    "sirnas": ["source_file", "notes"],
    "experiments": ["lab_chronicle_version", "location", "experiment_description"],
    "publications": ["publication_id"]
}

temp_mobile_config = {
    "antibodies":      ["antibody_target", "antibody_name", "location"],
    "cell_lines":      ["cell_line_name", "modifications"],
    "plasmids":        ["plasmid_name", "location"],
    "animal_models":   ["animal_model_name", "organism"],
    "dyes":            ["dye_name", "location"],
    "small_molecules":      ["compound", "location"],
    "sirnas":          ["sirna_name", "location"],
    "experiments": [
        "experiment_name",
        "date_started",
        "performed_by",
        "device_name",
        "location",
        "experiment_description"
    ],
    "publications": [
        "title",
        "stage",
        "num_figures",
        "experiment_sources"
    ]
}

MOBILE_CONFIG = {}
for k, v in temp_mobile_config.items():
    MOBILE_CONFIG[k] = {col: DESKTOP_CONFIG[k][col] for col in v if col in DESKTOP_CONFIG[k]}

PRETTY_DATABASES = {
    "antibodies": "Antibodies",
    "cell_lines": "Cell Lines",
    "plasmids": "Plasmids",
    "animal_models": "Animal Models",
    "dyes": "Dyes",
    "small_molecules": "Small Molecules",
    "sirnas": "siRNAs",
    "experiments": "Experiments",
    "publications": "Publications"
}

def prettify_col(col: str) -> str:
    manual = {
        "antibody_target": "Antibody Target",
        "protein_target": "Protein Target",
        "antibody_name": "Antibody Name",
        "host_species": "Host Species",
        "species_reactivity": "Species Reactivity",
        "catalog_id": "Catalog ID",
        "cell_line_name": "Cell Line Name",
        "derived_from": "Derived From",
        "source_file": "Source YAML File",
        "applications": "Manufacurer Application",
        "dilutions.Immunofluorescence": 'Immunofluorescence Dilutions',
        "dilutions.Western Blot": 'Western Blot Dilutions',
        "dilutions.IHC": 'IHC Dilutions',
        "dilutions.IP": 'IP Dilutions',
        "dilutions.Flow Cytometry": 'Flow Cytometry Dilutions',
        "validation.Immunofluorescence": "Immunofluorescence Validated",
        "validation.Western Blot": "Western Blot Validated",
        "validation.IHC": "IHC Validated",
        "validation.IP": "IP Validated",
        "validation.Flow Cytometry": "Flow Cytometry Validated",
        "selection_marker": "Selection Marker",
        "amplification_host": "Amplification Host",
        "sequencing_validation": "Sequencing Validated",
        "expression_host": "Expression Host",
        "publications": "Publication DOI(s)",
        "publication": "Publication DOI",
        "animal_model_name": "Model Name",
        "catalogue_number": "Catalogue #",
        # Dye related
        # Small Molecule related
        "cas": "CAS Number",
        # siRNA related
        "sirna_name": "siRNA Name",
        # Cell Line related
        "storage.location": "Location",
        # General
        "status.tube": "Tube's status",
        "status.reorder": "Reorder?",
        "status.last_checked": "Last Time Checked",
        # Experiment related
        "experiment_name": "Experiment Name",
        "date_started": "Start Date",
        "performed_by": "Performed By",
        "primary_method": "Primary Method",
        "cell_lines": "Cell Lines",
        "animal_models": "Animal Models",
        "global_metadata.Microscope": "Microscope",
        "global_metadata.Live Imaging": "Live Imaging",
        "conditions": "Experimental Conditions",
        "device_name": "Device Name",
        "location": "Location",
        "lab_chronicle_version": "LabChronicle Version",
        # Publication related
        "num_figures": "Number of Figures",
        "experiment_sources": "Involved Experiment"
    }
    return manual.get(col, col.replace("_", " ").title())

def pretty_val(v: Any) -> Any:
    # This function bolds keys for dictionaries, which is generally desired for other dicts.
    # The 'status' field for antibodies will now be pre-flattened in flatten_antibody.
    if isinstance(v, dict):
        return "; ".join(f"**{k}**: {v[k]}" for k in v)
    if isinstance(v, list):
        return ", ".join(map(str, v))
    return v

# ─── Location related functions ─────────────────────────────────────────────────────

def load_boxes(boxes_folder: Path) -> Dict[str, str]:
    """Map every Box_ID in the boxes folder to its human-readable Box_name.

    LabChronicle writes boxes either as a list of box dictionaries or as a
    mapping keyed by Box_ID; both shapes are supported.
    """
    if not boxes_folder.is_dir():
        return {}

    processed_boxes_data = {}
    for boxes_file in sorted(boxes_folder.glob("*.yaml")):
        boxes_data = yaml.safe_load(boxes_file.read_text(encoding="utf-8")) or {}
        boxes = boxes_data.get("boxes", []) if isinstance(boxes_data, dict) else boxes_data

        if isinstance(boxes, dict):
            boxes = [
                {"Box_ID": box_id, **box}
                for box_id, box in boxes.items()
                if isinstance(box, dict)
            ]

        for box in boxes if isinstance(boxes, list) else []:
            if not isinstance(box, dict):
                continue
            box_id = str(box.get("Box_ID") or "").strip()
            if box_id:
                box_name = str(box.get("Box_name") or "").strip()
                processed_boxes_data[box_id] = box_name or box_id

    return processed_boxes_data

def translate_box_ids(value: Any, boxes_dictionary: Dict[str, str]) -> Any:
    """Replace stored Box_IDs (also inside lists) with their box names."""
    if isinstance(value, list):
        return [translate_box_ids(item, boxes_dictionary) for item in value]
    if isinstance(value, str):
        return boxes_dictionary.get(value.strip(), value)
    return value

# ─── YAML → DataFrame LOADER ─────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_dataset(dataset: str, database_root_path: Path) -> pd.DataFrame:

    if dataset == "experiments":
        database_folder = database_root_path / "experiment_database"
    elif dataset == "publications":
        database_folder = database_root_path / "publication_database"
    else:
        database_folder = database_root_path / "lab_database" / dataset

    if not database_folder.exists():
        return pd.DataFrame()

    records = []

    if dataset == "experiments":
        database_file = database_folder / "experiment_database.yaml"
        if database_file.exists():
            database = yaml.safe_load(database_file.read_text())

            for hard_drive_idx, hard_drive_info in database.items():
                hard_drive_file = database_folder / hard_drive_idx / "drive_metadata.yaml"
                hard_drive_content = yaml.safe_load(hard_drive_file.read_text()) or {}
                for exp_idx, exp_metadata in hard_drive_content["experiments"].items():
                    exp_info = extract_experiment_info(database_folder / hard_drive_idx / exp_idx,
                                                    experiment_id=exp_idx,
                                                    experiment_info=exp_metadata,
                                                    hard_drive_id=hard_drive_idx,
                                                    hard_drive_info=hard_drive_content.get("hard_drive_info", {}))
                    exp_info.update({k:v for k,v in exp_metadata.items() if k not in ["experiment_checksum"]})  # Merge dictionaries
                    exp_info.update({k:v for k,v in hard_drive_info.items() if k not in ["physical_serial_number",
                                                                                        "volume_serial_number"]})  # Merge dictionaries
                    records.append(exp_info)
    elif dataset == "publications":
        for publication_path in database_folder.iterdir():
            for stage_path in publication_path.iterdir():
                summary_file = stage_path / "summary.yaml"
                if summary_file.exists():
                    summary_information = yaml.safe_load(summary_file.read_text()) or {}

                    num_figures = len(summary_information.keys()) - 1  # Exclude 'publication_name'

                    experiment_sources = []
                    for key, value in summary_information.items():
                        if key != "publication_name":
                            panel_list = value.get("panels", [])
                            for panel in panel_list:
                                source_exp = panel.get("experiment_sources", [])
                                experiment_sources.extend(source_exp)

                    entry = {
                        "publication_id": publication_path.name,
                        "stage": stage_path.name,
                        "title": summary_information.get("publication_name", ""),
                        "num_figures": num_figures,
                        "experiment_sources": experiment_sources
                    }

                    records.append(entry)
    else:
        for file in database_folder.glob("*.yaml"):
            raw = yaml.safe_load(file.read_text()) or {}
            if dataset == "antibodies":
                tgt = raw.get("antibody_target","")
                for entry in raw.get("antibodies", []):
                    # Call the new flatten_antibody function
                    rec = flatten_antibody(entry.copy(), tgt, file.name)
                    records.append(rec)
            elif dataset == "dyes":
                tgt = raw.get("dye_target","")
                for entry in raw.get("dyes", []):
                    # Call the new flatten_dye function
                    rec = flatten_dye(entry.copy(), tgt, file.name)
                    records.append(rec)
            elif dataset == "sirnas":
                tgt = raw.get("gene","")
                for entry in raw.get("sirnas", []):
                    # Call the new flatten_sirna function
                    rec = flatten_sirna(entry.copy(), tgt, file.name)
                    records.append(rec)
            else:
                # Determine which entries to process based on the dataset type
                if dataset == "plasmids" or dataset == "animal_models":
                    if dataset == "plasmids":
                        entries = raw.get("plasmids", raw)
                    elif dataset == "animal_models":
                        entries = raw.get("models", [])

                    for entry in entries:
                        rec = {}

                        if dataset=="plasmids":
                            rec = flatten_plasmid(entry, file.name)
                        elif dataset=="animal_models":
                            rec = flatten_animal_model({**entry, "organism": raw.get("organism",file.stem)}, file.name)
                        records.append(rec)
                else:
                    if dataset=="cell_lines":
                        rec = flatten_cell_line(raw.copy(), file.name)
                    elif dataset=="small_molecules":
                        rec = flatten_small_molecule(raw.copy(), file.name)
                    records.append(rec)
    df = pd.DataFrame(records)
    return df

# ─── FLATTEN HELPERS ─────────────────────────────────────────────────────────
def extract_experiment_info(src,
                            experiment_id=None, experiment_info={},
                            hard_drive_id=None, hard_drive_info={}):

    # Load experiment metadata
    experiment_metadata_file = src / "metadata.yaml"
    if not experiment_metadata_file.exists():
        return {}

    metadata = yaml.safe_load(experiment_metadata_file.read_text()) or {}

    filtered_metadata = {}

    for key, value in metadata.items():
        filtered_metadata.update(flatten_experiment_metadata(key, value))

    # Build description text
    cell_lines = filtered_metadata.get("cell_lines", []) if isinstance(filtered_metadata, dict) else []
    if cell_lines:
        cell_lines_text = f"The following cell lines were used: **{cell_lines}**."
    else:
        cell_lines_text = "No cell lines were specified."

    animal_models = filtered_metadata.get("animal_models", []) if isinstance(filtered_metadata, dict) else []
    if animal_models:
        animal_models_text = f"The following animal models were used: **{animal_models}**."
    else:
        animal_models_text = "No animal models were specified."

    conditions = filtered_metadata.get("conditions", []) if isinstance(filtered_metadata, dict) else []
    if conditions:
        # conditions may be a mapping; support both shapes
        try:
            conditions_text = f"{len(conditions.split(','))} conditions were tested: **{conditions}**."
        except Exception:
            conditions_text = "Some conditions were specified."
    else:
        conditions_text = "No specific conditions were specified."

    description = f'''
            The experiment **{experiment_id}** was done by **{filtered_metadata.get("performed_by", NOT_AVAILABLE)}**.
            Started the **{filtered_metadata.get("date_started", NOT_AVAILABLE)}**,
            it uses **{filtered_metadata.get("primary_method", NOT_AVAILABLE)}** as primary method.
            {cell_lines_text}
            {animal_models_text}
            {conditions_text}
            The experiment is stored on hard-drive **{hard_drive_info.get("device_name", NOT_AVAILABLE)}**,
            on the folder **{experiment_info.get("location", NOT_AVAILABLE)}**.
            See more details about the experiment [here]({st.session_state.get("repo_url") or "#"}/{GITHUB_BLOB_BASE}/{st.session_state.get("repo_branch", "main")}/experiment_database/{hard_drive_id}/{experiment_id}/metadata.yaml).
            See more details about the hard-drive [here]({st.session_state.get("repo_url") or "#"}/{GITHUB_BLOB_BASE}/{st.session_state.get("repo_branch", "main")}/experiment_database/{hard_drive_id}/drive_metadata.yaml).
            '''
    filtered_metadata["experiment_description"] = description

    return filtered_metadata

def flatten_experiment_metadata(key, value):

    # First do a checking of specific key values
    if key == "conditions":
        return {key: ",\n".join([v["name"] for k, v in value.items()])}
    elif key in ["repeats", "experiment_id"]:
        return {}

    if not isinstance(value, dict) and not isinstance(value, list):
        return {key: value}
    elif isinstance(value, dict):
        output_dict = {}
        for sub_key, sub_value in value.items():
            output_dict.update(flatten_experiment_metadata(f"{key}.{sub_key}", sub_value))
        return output_dict
    elif isinstance(value, list):
        any_list_dict = any(isinstance(item, list) or isinstance(item, dict) for item in value)

        if any_list_dict:
            output_dict = {}
            for i, item in enumerate(value):
                output_dict.update(flatten_experiment_metadata(f"{key}.{i}", item))
            return output_dict
        else:
            return {key: ",\n".join(value)}
    return {}


def flatten_antibody(d, target, src):
    """Flattens antibody data, specifically handling status and website fields."""
    d["antibody_target"] = target
    d["source_file"] = src

    # If 'status' is a dictionary, flatten it into a string without bolding its internal keys.
    if isinstance(d.get("status"), dict):
        # Expand the status dictionary
        for k,v in d["status"].items():
            d[f"status.{k}"] = v
        # Pop the original status field
        d.pop("status", None)

    # Ensure website URLs are formatted consistently with the rest of the app for display
    web = d.get("website", "")
    if isinstance(web, str) and web.startswith("http"):
        # Store as raw URL here; make_all_links_clickable will create the <strong><a>Link</a></strong>
        d["website"] = web
    else:
        d["website"] = html.escape(str(web))

    return d


def flatten_cell_line(d, src):

    storage = d.get("storage",[])

    h = d.get("history",{})
    mod = "; ".join(f"{m['category'].capitalize()}: {m['description']}"
                     for m in d.get("modifications",[]))
    res = ", ".join(d.get("resistance",[])) if isinstance(d.get("resistance",[]),list) else d.get("resistance","")
    pub = h.get("publication","")
    if "/" in pub:
        pub = f'https://doi.org/{pub}' # Store as raw URL

    raw_cell_line = {
            "cell_line_name": d.get("cell_line_name",""),
            "organism": d.get("organism",""),
            "sex": d.get("sex",""),
            "tissue": d.get("tissue",""),
            "type": d.get("type",""),
            "derived_from": h.get("derived_from",""),
            "resistance": res,
            "modifications": mod,
            "notes": d.get("notes",""),
            "source": h.get("source",""),
            "catalog_id": h.get("catalog_id",""),
            "publication": pub,
            "authentication": (d.get("authentication") or {}).get("method",""),
            "source_file": src,
            "storage.location": [],
    }

    for stored_cell_line in storage:
        location = stored_cell_line.get("location","")
        if location:
            raw_cell_line["storage.location"].append(location)

    return raw_cell_line

def flatten_plasmid(d, src):
    status = ", ".join(f"{k}: {v}" for k, v in (d.get("status") or {}).items())

    # publications → bold “Link”
    pubs = d.get("publications", d.get("publication", ""))
    if isinstance(pubs, list):
        # Store raw URLs first, make_all_links_clickable handles HTML formatting later
        pubs = [str(p) if not str(p).startswith("http") else f'https://doi.org/{p}' for p in pubs]
        pubs = ", ".join(pubs) # Join into a single string for pretty_val
    elif isinstance(pubs, str) and "/" in pubs:
        pubs = f'https://doi.org/{pubs}' # Store raw URL
    else:
        pubs = html.escape(str(pubs))

    # website → raw URL
    web = d.get("website", "")
    if isinstance(web, str) and web.startswith("http"):
        web = web # Store as raw URL
    else:
        web = html.escape(str(web))

    return {
        **d,
        "status": status,
        "publications": pubs,
        "website": web,
        "source_file": src
    }

def flatten_animal_model(d, src):
    # For animal models, ensure website is handled as a raw URL similar to other flatten functions
    web = d.get("website", "")
    if isinstance(web, str) and web.startswith("http"):
        d["website"] = web
    else:
        d["website"] = html.escape(str(web))
    return {**d, "source_file": src}

def flatten_dye(d, target, src):
    """Flattens dye data, specifically handling status and website fields."""
    d["dye_target"] = target
    d["source_file"] = src

    # If 'status' is a dictionary, flatten it into a string without bolding its internal keys.
    if isinstance(d.get("status"), dict):
        # Expand the status dictionary
        for k,v in d["status"].items():
            d[f"status.{k}"] = v
        # Pop the original status field
        d.pop("status", None)

    # For dyes, ensure website is handled as a raw URL similar to other flatten functions
    web = d.get("website", "")
    if isinstance(web, str) and web.startswith("http"):
        d["website"] = web
    else:
        d["website"] = html.escape(str(web))
    return d

def flatten_small_molecule(d, src):
    d["source_file"] = src

    aliases = d.get("aliases","")
    aliases = ", ".join(aliases) if isinstance(aliases, list) else aliases
    d["aliases"] = aliases

    web = d.get("website", "")
    if isinstance(web, str) and web.startswith("http"):
        d["website"] = web
    else:
        d["website"] = html.escape(str(web))

    target_list = d.get("targets",[])
    targets = []
    for target in target_list:
        # Get the name of the target and store the rest as strings
        name = target.get("name","")
        for k,v in target.items():
            if k != "name":
                name += f"; {k}: {v}"
        targets.append(name)
    targets = ", ".join(targets)
    d["targets"] = targets

    # If 'status' is a dictionary, flatten it into a string without bolding its internal keys.
    if isinstance(d.get("status"), dict):
        # Expand the status dictionary
        for k,v in d["status"].items():
            d[f"status.{k}"] = v
        # Pop the original status field
        d.pop("status", None)

    return d

def flatten_sirna(d, target, src):
    """Flattens sirna data, specifically handling status and website fields."""
    d["gene"] = target
    d["source_file"] = src

    # If 'status' is a dictionary, flatten it into a string without bolding its internal keys.
    if isinstance(d.get("status"), dict):
        # Expand the status dictionary
        for k,v in d["status"].items():
            d[f"status.{k}"] = v
        # Pop the original status field
        d.pop("status", None)

    # For sirnas, ensure website is handled as a raw URL similar to other flatten functions
    web = d.get("website", "")
    if isinstance(web, str) and web.startswith("http"):
        d["website"] = web
    else:
        d["website"] = html.escape(str(web))
    return d

# ─── GIT CLONE HELPER ────────────────────────────────────────────────────────
def clone_repo(repo_url: str, private: bool, token: str) -> Optional[Path]:
    try:
        owner, name = repo_url.rstrip("/").split("/")[-2:]
    except:
        st.error("Invalid GitHub URL")
        return None
    headers = {"Accept":"application/vnd.github.v3+json"}
    if private:
        if not token:
            st.error("Token required for private repos")
            return None
        headers["Authorization"] = f"token {token}"

    check = requests.get(f"https://api.github.com/repos/{owner}/{name}/contents", headers=headers)
    if check.status_code != 200:
        st.error(f"Cannot access repo ({check.status_code})")
        return None

    if "tmpdir" not in st.session_state:
        st.session_state.tmpdir_obj = tempfile.TemporaryDirectory()
        st.session_state.tmpdir = st.session_state.tmpdir_obj.name

    path = Path(st.session_state.tmpdir)/name
    if not path.exists():
        with st.spinner("Cloning repository…"):
            url = repo_url
            if private:
                p = urllib.parse.urlparse(repo_url)
                token_safe = urllib.parse.quote(token)
                url = f"https://{token_safe}@{p.netloc}{p.path}"
            res = subprocess.run(["git","clone",url,str(path)], capture_output=True, text=True)
            if res.returncode:
                st.error(f"Git clone failed: {res.stderr}")
                return None
    return path

# ─── APP LOGIC ───────────────────────────────────────────────────────────────
# Initialize mobile_view_checkbox in session_state if not already present
if 'mobile_view_checkbox' not in st.session_state:
    st.session_state.mobile_view_checkbox = False

if "repo_path" not in st.session_state:
    # Show download form
    st.markdown("### Option 1: Load the bundled example database")
    st.caption(
        "This environment has no outbound network access for the app server, so cloning a "
        "GitHub repository below will not work. Use the bundled example database instead to "
        "explore the interface (reagents, cell lines, experiments, publications)."
    )
    if st.button("📂 Load bundled example database"):
        st.session_state.repo_path = Path(__file__).resolve().parent
        st.session_state.repo_url = ""
        st.session_state.repo_branch = "main"
        st.rerun()

    st.markdown("### Option 2: Load a GitHub repository (requires network)")
    owner = st.text_input("GitHub Repository URL", help="e.g., https://github.com/user/repo")
    private = st.checkbox("Private repo?")
    token = st.text_input("Personal Access Token", type="password", disabled=not private)

    # Mobile view checkbox on the first screen
    # Use a different key for this instance to avoid StreamlitAPIException
    st.session_state.mobile_view_checkbox = st.checkbox(
        "📱 Mobile view (Fewer columns)",
        value=st.session_state.mobile_view_checkbox, # Read from session state
        key='mobile_view_checkbox_initial_screen'
    )

    # Determine config based on the current mobile_view_checkbox state
    cfg = MOBILE_CONFIG if st.session_state.mobile_view_checkbox else DESKTOP_CONFIG

    # prettified_field_config needs to be defined here for the initial load, using the current cfg
    prettified_field_config = {
        k: [prettify_col(c) for c in cols.keys()]
        for k, cols in cfg.items()
    }

    if st.button("🔄 Load Database"):
        if owner:
            rp = clone_repo(owner, private, token)
            if rp:
                st.session_state.repo_path = rp
                st.session_state.repo_url = normalize_repo_url(owner)
                st.session_state.repo_branch = get_repo_branch(rp)
                st.rerun()
        else:
            st.warning("Please enter a GitHub repository URL.")
else:

    if 'last_added' not in st.session_state:
        st.session_state.last_added = None
    if 'selected_database' not in st.session_state:
        st.session_state.selected_database = None

    repo_path = st.session_state.repo_path
    if "repo_branch" not in st.session_state:
        st.session_state.repo_branch = get_repo_branch(repo_path)
    if "repo_url" not in st.session_state:
        st.session_state.repo_url = ""

    if 'boxes_dictionary' not in st.session_state:
        # Load the boxes database
        st.session_state.boxes_dictionary = load_boxes(repo_path / "lab_database" / "boxes")

    # Determine which config to use based on the current mobile_view_checkbox state
    cfg = MOBILE_CONFIG if st.session_state.mobile_view_checkbox else DESKTOP_CONFIG

    # Re-calculate prettified_field_config based on the chosen cfg
    prettified_field_config = {
        k: [prettify_col(c) for c in cols.keys()]
        for k, cols in cfg.items()
    }

    st.success(f"Loaded: {repo_path.name}")

    # Define existing database paths
    lab_database = repo_path / "lab_database"
    experiment_database = repo_path / "experiment_database"
    publication_database = repo_path / "publication_database"

    if not experiment_database.exists() and not lab_database.exists() and not publication_database.exists():
        st.warning("No database found.")
        st.stop()

    # Prepare choices for the database selection
    choices = [k for k in DESKTOP_CONFIG if (lab_database/k).is_dir()] # Use DESKTOP_CONFIG keys for initial choices
    choices.insert(0, "experiments")
    choices.insert(0, "publications")
    choices.sort()
    pretty_choices = [PRETTY_DATABASES.get(c, c) for c in choices]

    # Choose and load the database
    st.subheader("Choose the database to explore")
    ds = st.selectbox("Database options:", pretty_choices)
    ds = choices[pretty_choices.index(ds)]

    if st.session_state.selected_database != ds:
        st.session_state.selected_database = ds
        st.session_state.last_added = None
        selection_state_key = f"selected_rows__{ds}"
        if selection_state_key not in st.session_state:
            st.session_state[selection_state_key] = set()
        st.rerun()

    df = load_dataset(ds, repo_path)

    # Show box names instead of the stored Box_IDs. Experiment "location" is a
    # folder path, not a box, so only lab-database resources are translated.
    if ds not in ("experiments", "publications"):
        for location_column in ("location", "storage.location"):
            if location_column in df.columns:
                df[location_column] = df[location_column].apply(
                    lambda value: translate_box_ids(value, st.session_state.boxes_dictionary)
                )

    with st.sidebar:
        st.markdown("## Options")  # Sidebar title

    if not df.empty:
        # Remove duplicates for cell lines based on cell_line_name
        if ds == "cell_lines":
            df = df.drop_duplicates(subset=["cell_line_name"])

        # Clean the configuration keys to the actual columns present in the dataframe
        dataframe_columns = set(df.columns)
        relevant_columns = [col for col in cfg[ds].keys() if col in dataframe_columns]

        # Only take relevant columns
        temp_df = df[relevant_columns].copy()

        # Load the filtering options and create the sidebar widget for filtering
        ignore_columns = [e for e in IGNORE_FILTER_COLUMNS.get(ds, []) if e in cfg.get(ds, {}).keys()]
        create_data = cfg[ds]

        # For experiments, remove the experiment_description column from display
        if ds == "experiments":
            if "experiment_description" in temp_df.columns:
                temp_df = temp_df.drop(columns=["experiment_description"])
            if "experiment_description" in ignore_columns:
                ignore_columns.remove("experiment_description")

        with st.sidebar:
            with st.expander("Filter Options"):
               all_widgets = streamlit_pandas.create_widgets(temp_df,
                                                             create_data,
                                                             ignore_columns=ignore_columns,
                                                             prettify_function=prettify_col)

        # Filter the dataframe
        filtered_df = streamlit_pandas.filter_df(df[relevant_columns].copy(),
                                                 all_widgets)
        pretty_cols_mapping = {col: prettify_col(col) for col in filtered_df.columns}

        # Create a general search bar that filters across all columns
        search_term = st.text_input("🔍 Global search",
                                    placeholder="Type here...",
                                    help="Type to search across all fields. If you want to search for multiple terms, separate them with commas.",
                                    key="global_search",
                                    on_change=(st.rerun if hasattr(st, "rerun") else st.experimental_rerun),
                                    )
        term = st.session_state.get("global_search", "").strip()

        if term:
            if "," in term:
                terms = [t.strip() for t in term.split(",") if t.strip()]
                mask = filtered_df.apply(
                    lambda row: any(row.astype(str).str.contains(t, case=False, na=False).any() for t in terms),
                    axis=1
                )
            else:
                mask = filtered_df.apply(lambda row: row.astype(str).str.contains(search_term, case=False, na=False).any(), axis=1)
            filtered_df = filtered_df[mask]


        # Display the filtered dataframe
        display_df = filtered_df.rename(columns=pretty_cols_mapping)

        st.info(f"Showing {len(display_df)} records")

        SELECTED_COL = "Selected"
        selection_state_key = f"selected_rows__{ds}"
        stored_selection = set(st.session_state.get(selection_state_key, set()))

        visible_indices = list(display_df.index)
        visible_index_set = set(visible_indices)

        table_df = display_df.copy()
        table_df.insert(0, SELECTED_COL, table_df.index.to_series().isin(stored_selection))

        select_column_width: Any = 25
        if st.session_state.mobile_view_checkbox:
            select_column_width = 5

        column_config = {
            SELECTED_COL: st.column_config.CheckboxColumn(
                "Select",
                help="Mark rows for export",
                width=select_column_width,
            )
        }
        if "Website" in table_df.columns:
            column_config["Website"] = st.column_config.LinkColumn("Website", display_text="Link")
        if "Publication DOI" in table_df.columns:
            column_config["Publication DOI"] = st.column_config.LinkColumn("Publication DOI", display_text="Link")

        disabled_columns = [col for col in table_df.columns if col != SELECTED_COL]

        edited_df = st.data_editor(
            table_df,
            height="auto",
            hide_index=True,
            column_config=column_config,
            disabled=disabled_columns,
            key=f"data_editor__{ds}"
        )

        updated_selection = set(stored_selection)
        if isinstance(edited_df, pd.DataFrame) and SELECTED_COL in edited_df.columns:
            visible_selected = set(edited_df.index[edited_df[SELECTED_COL].astype(bool)])
            non_visible_selected = updated_selection - visible_index_set
            updated_selection = non_visible_selected | visible_selected

        if updated_selection != stored_selection:
            if len(updated_selection) > len(stored_selection):
                st.session_state.last_added = (updated_selection - stored_selection).pop()
            else:
                st.session_state.last_added = None
            valid_indices = set(df.index)
            updated_selection = {idx for idx in updated_selection if idx in valid_indices}
            st.session_state[selection_state_key] = updated_selection
            st.rerun()

        # Include buttons for "Select All" and "Clear Selection"
        info_col, select_button_col, clear_button_col = st.columns([0.3, 0.35, 0.35], gap="small")
        info_col.markdown(f"**Selected rows:** {len(updated_selection)}")
        if select_button_col.button("Select all rows", use_container_width=True, key=f"select_all_{ds}"):
            st.session_state[selection_state_key] = updated_selection | visible_index_set
            st.session_state.last_added = None
            st.rerun()
        if clear_button_col.button("Clear selection", use_container_width=True, key=f"clear_selection_{ds}"):
            st.session_state[selection_state_key] = set()
            st.session_state.last_added = None
            st.rerun()

        # Display export buttons in a horizontal layout
        with st.container():
            col1, col2, col3, col4 = st.columns([0.22, 0.2, 0.2, 1.5], gap="small")
            with col1:
                st.markdown("**Export selected rows:**")
                selected_indices_sorted = [idx for idx in df.index if idx in updated_selection]
                selected_export_df = pd.DataFrame()
                export_columns = [
                    col
                    for col in list(cfg[ds].keys()) + ["source_file"]
                    if col in df.columns
                ]
                export_pretty_mapping = {
                    col: pretty_cols_mapping.get(col, prettify_col(col))
                    for col in export_columns
                }

                if selected_indices_sorted:
                    selected_export_df = df.loc[
                        selected_indices_sorted, export_columns
                    ].copy()

                    if "source_file" in selected_export_df.columns:

                        repo_url = st.session_state.get("repo_url", "")
                        branch = st.session_state.get("repo_branch", "main")
                        if ds == "experiments":
                            dataset_folder = "experiment_database"
                        elif ds == "publications":
                            dataset_folder = "publication_database"
                        else:
                            dataset_folder = f"lab_database/{ds}"

                        def build_source_link(value: Any) -> Any:
                            if value is None or (isinstance(value, float) and pd.isna(value)):
                                return ""
                            value_str = str(value)
                            if not value_str:
                                return value_str
                            if value_str.startswith("http"):
                                return value_str
                            if not repo_url:
                                return value_str
                            relative_path = f"{dataset_folder}/{value_str}".replace("\\", "/")
                            return f"{repo_url}/{GITHUB_BLOB_BASE}/{branch}/{relative_path}"

                        selected_export_df["source_file"] = selected_export_df[
                            "source_file"
                        ].apply(build_source_link)

                    selected_export_df = selected_export_df.rename(
                        columns=export_pretty_mapping
                    )

                csv_data = selected_export_df.to_csv(index=False) if not selected_export_df.empty else ""
                pdf_data = df_to_pdf(selected_export_df) if not selected_export_df.empty else b""
            with col2:
                st.download_button(
                    label="CSV",
                    data=csv_data,
                    file_name="selected_rows.csv",
                    mime="text/csv",
                    disabled=selected_export_df.empty
                )
            with col3:
                st.download_button(
                    label="PDF",
                    data=pdf_data,
                    file_name="selected_rows.pdf",
                    mime="application/pdf",
                    disabled=selected_export_df.empty
                )

    else:
        st.warning("No matching records found for the selected dataset or filters.")


    # Mobile view checkbox in the sidebar
    with st.sidebar:
        with st.expander("Display Options"):
            st.session_state.mobile_view_checkbox = st.checkbox(
                "📱 Mobile view (Fewer columns)",
                value=st.session_state.mobile_view_checkbox, # Read from session state
                key='mobile_view_checkbox_sidebar' # Different key for sidebar instance
            )
            if st.button("🔁 Reset / Load another"):
                del st.session_state.repo_path
                # Boxes belong to the loaded repository.
                st.session_state.pop("boxes_dictionary", None)
                # Reset mobile view checkbox state
                st.session_state.mobile_view_checkbox = False
                st.rerun()

    # --- Detail Card ---
    # Moved the detail card selection to only appear when data is available
    if not df.empty and not filtered_df.empty:
        st.divider() # Use a divider for better separation

        # Use st.expander for a cleaner detail card display
        with st.expander("Show Full Record Details", expanded=False):
            # Ensure label_col uses the full DESKTOP_CONFIG field to always get a good label
            label_col = "experiment_name" if "experiment_name" in filtered_df.columns else filtered_df.columns[0]
            sel_index = st.selectbox(
                label="Select a record to view details:",
                options=filtered_df.index,
                index = list(filtered_df.index).index(st.session_state.last_added) if st.session_state.last_added is not None else 0,
                format_func=lambda i: filtered_df.loc[i].get(label_col, f"Row {i}"),
                key="details_select"
            )

            # Use columns to display key-value pairs
            sel_record = filtered_df.loc[sel_index]

            # A more robust way to display the detail card using Streamlit
            st.markdown(f"### Details for: {sel_record.get(label_col, 'Record')}")
            with st.container():

                if ds == "experiments":
                    with st.container(border=True):
                        st.markdown("#### Short description:")
                        st.markdown(sel_record.get("experiment_description", "No description available."))

                # Using st.columns for better alignment without raw HTML dl/dt/dd
                # These columns will automatically stack on mobile due to default Streamlit behavior
                detail_cols = st.columns(2)

                # Create a list of items to display
                # Display all details for the selected record, regardless of mobile/desktop table view
                details_to_show = [(k, pretty_val(v)) for k, v in sel_record.items() if k != "experiment_description"]

                # Distribute items across the columns
                mid_point = len(details_to_show) // 2
                col1_items = details_to_show[:mid_point]
                col2_items = details_to_show[mid_point:]

                with detail_cols[0]:
                    for key, value in col1_items:
                        if isinstance(value, str) and ",\n" in value:
                            items = value.split(",\n")
                            value = "\n".join([f"- {item}" for item in items])
                            st.markdown(f"**{prettify_col(key)}:**\n{value}")
                        else:
                            st.markdown(f"**{prettify_col(key)}:** {value}")

                with detail_cols[1]:
                    for key, value in col2_items:
                        if isinstance(value, str) and ",\n" in value:
                            items = value.split(",\n")
                            value = "\n".join([f"- {item}" for item in items])
                            st.markdown(f"**{prettify_col(key)}:**\n{value}")
                        else:
                            st.markdown(f"**{prettify_col(key)}:** {value}")

                # Include a button to select this record in the main table
                if st.button("Select this record in the main table", key="select_in_main_table"):
                    current_selection = set(st.session_state.get(selection_state_key, set()))
                    current_selection.add(sel_index)
                    st.session_state[selection_state_key] = current_selection
                    st.session_state.last_added = sel_index
                    st.rerun()
