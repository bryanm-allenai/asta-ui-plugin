"""Radiowriter - la letteratura dietro un articolo Radiopaedia.

Tre fasi, che sono le tre schede:
  1. Ricerca   - interroga PubMed, da sola riga o componendo la query a
                 blocchi, ordina i risultati per influenza (Semantic Scholar) e
                 per prestigio della rivista (SCImago), e salva quelli scelti.
  2. Screening - sfoglia l'archivio, apre i full text via LibKey o Unpaywall,
                 marca letto/segnalato, raccoglie in liste.
  3. Scrittura - la bozza dell'articolo con la struttura che Radiopaedia
                 raccomanda per quel tipo, le citazioni risolte, il linter, e
                 l'HTML da incollare nel loro editor.
"""

from __future__ import annotations

import hashlib
import html
import math
import os
import sqlite3
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

from radiowriter import backup
from radiowriter import bench
from radiowriter import cards
from radiowriter import db
from radiowriter import draft_io
from radiowriter import editorial
from radiowriter import highlight
from radiowriter import highlights as hl
from radiowriter import issg
from radiowriter import journals as jr
from radiowriter import library
from radiowriter import lint
from radiowriter import modalities as md
from radiowriter import paths
from radiowriter import pubmed
from radiowriter import querybuilder as qb
from radiowriter import radiopaedia as rp
from radiowriter import semantic_scholar as s2
from radiowriter import strategies as stg
from radiowriter import structure as sx
from radiowriter import study
from radiowriter import theme
from radiowriter import unpaywall as upw
from radiowriter.cards import (abstract_html, citation_badge, clean, journal_badges,
                               number, oa_badge, useful_types)

SORT_OPTIONS = {
    "Influential citations (S2)": "influential_citations",
    "Total citations (S2)": "citation_count",
    "Citations per year": "citations_per_year",
    "Most recent": "year",
    "Journal SJR": "_sjr",
}
TODAY = date.today()
# Quanti record scaricare: 0 vuol dire tutti quelli che PubMed restituisce,
# cioe' fino al suo tetto di 9.999. Prima il default era 200 e il massimo
# 1000, e una ricerca ampia si fermava a meta' senza che uno lo decidesse.
MAX_RESULTS_OPTIONS = [0, 100, 200, 500, 1000, 2000, 5000]
SEARCH_PAGE_SIZE_OPTIONS = [10, 25, 50, 100]

# I filtri di ricerca hanno UN interruttore a tre posizioni, ed e' la posizione
# a decidere cosa va a PubMed (`effective_filters`): "Recent reviews" e "No
# filters" mandano il loro fascio e non disegnano nessun controllo, "Custom"
# disegna i controlli e manda quello che c'e' scritto. Prima i controlli erano
# sempre a schermo e la posizione era ricavata dai valori; adesso i valori dei
# controlli contano solo in "Custom", e una posizione non puo' dire una cosa
# mentre la query ne chiede un'altra.
SEARCH_MODES = {
    "reviews": "★ Recent reviews",
    "open": "No filters",
    "custom": "Custom",
}

# La voce del menu delle liste che ne fa nascere una nuova.
NEW_LIST = "＋ New list…"

# Il tipo di pubblicazione si chiede in UN modo solo. Le etichette NLM e i
# filtri ISSG sono due modi di chiedere la stessa cosa, e messi insieme non
# sommano: vanno in AND e restano solo i lavori che sono tutt'e due, molti meno
# di quanto uno si aspetti. Prima c'era un avviso; adesso non si puo' e basta.
TYPE_METHODS = {
    "none": "Any",
    "pt": "Publication type (NLM)",
    "issg": "Search filter (ISSG)",
}

# Nel fascio ci sono solo i FILTRI, cioe' quello che cambia la domanda fatta a
# PubMed. Quanti record scaricare, cosa saltare, se arricchire con le citazioni
# e con l'open access sono preferenze dell'app: stanno nella sidebar e non le
# tocca ne' il fascio ne' "No filters".
# I filtri che nessuno dei due fasci accende: stanno in tutt'e due spenti, cosi'
# `effective_filters` trova ogni chiave anche quando legge un fascio.
DATE_METHODS = {
    "years": "Last N years",
    "range": "Between two years",
}
_FILTERS_OFF = {
    "sf_date_by": "years",
    "sf_year_from": TODAY.year - 10,
    "sf_year_to": TODAY.year,
    "sf_abstract": False,
    "sf_freefulltext": False,
    "sf_data": False,
    "sf_animals": False,
    "sf_female": False,
    "sf_male": False,
    "sf_ages": [],
    "sf_nopreprints": False,
    "sf_medline": False,
}
SEARCH_FILTER_PRESETS = {
    "reviews": {
        **_FILTERS_OFF,
        "sf_years": 10,
        "sf_fulltext": True,
        "sf_languages": ["English"],
        "sf_humans": True,
        "sf_type_by": "pt",
        "sf_types": list(pubmed.REVIEW_TYPE_LABELS),
        "sf_issg": [],
    },
    # Tutto spento vuol dire tutto spento, compreso il limite di data: prima
    # "azzera" lasciava gli ultimi cinquant'anni, che e' un filtro travestito
    # da assenza di filtro.
    "open": {
        **_FILTERS_OFF,
        "sf_years": 0,
        "sf_fulltext": False,
        "sf_languages": [],
        "sf_humans": False,
        "sf_type_by": "none",
        "sf_types": [],
        "sf_issg": [],
    },
}

# Detto nell'aiuto dei filtri che leggono i MeSH: eta', sesso, altri animali,
# MEDLINE. Per "Humans" l'app ha una forma che non ha questo difetto; per
# questi non esiste, e allora va scritto.
MESH_WARNING = (" Uses MeSH indexing: records NLM has not indexed yet, which "
                "includes most papers of the last few months, are left out.")

# L'altezza dell'iframe dello Screening quando il CSS qui sotto non arriva:
# di norma lo porta all'altezza della finestra.
BENCH_HEIGHT = 900

# Ogni quanto la barra laterale rilegge i numeri dell'archivio.
ARCHIVE_REFRESH_SECONDS = 5

# Le preferenze, col loro valore di partenza.
SEARCH_PREFS = {
    "sf_max_results": 0,
    "sf_exclude": db.EXCLUDE_MODES["db"],
    "sf_s2": True,
    "sf_oa": False,
}

st.set_page_config(
    page_title="Radiowriter", layout="wide",
    page_icon=str(Path(__file__).parent / "web" / "icon.png"),
    # Il menu resta perche' e' li' che si sceglie il tema; le voci che
    # rimandano all'assistenza di Streamlit non riguardano chi usa l'app.
    menu_items={
        "Get help": None,
        "Report a bug": "https://github.com/gmadevs/Radiowriter/issues",
        "About": "**Radiowriter** searches PubMed, helps you screen the "
                 "results and write a Radiopaedia article from them. "
                 "Unofficial, not affiliated with Radiopaedia.org.",
    })

db.init_db()


@st.cache_resource
def boot_cleanup() -> int:
    """Girata una sola volta per avvio dell'app, non a ogni rerun di Streamlit."""
    return db.cleanup_read_articles()


removed_at_boot = boot_cleanup()


@st.cache_resource
def load_journal_metrics() -> dict:
    """Il file SCImago dentro il database, una volta sola per avvio.

    Si fa da se' al primo avvio invece di aspettare che qualcuno prema un
    pulsante: da quando il file viaggia dentro il pacchetto, aspettare
    vorrebbe dire mostrare un archivio senza quartili a chi non ha idea che ci
    sia un pulsante da premere. Trentamila righe si leggono in un secondo, una
    volta sola, e finiscono in una tabella del database.

    Se non c'e' nessun file non e' un guasto: l'app funziona senza quartili -
    ma vorrebbe dire che l'installazione e' incompleta, perche' uno ce n'e'
    sempre."""
    status = db.journal_metrics_status()
    if status["journals"]:
        return {"loaded": False, **status}
    path = jr.find_file()
    if path is None:
        return {"loaded": False, "missing": True, **status}
    try:
        n = db.import_journal_metrics(jr.read(path))
    except jr.JournalDataError as exc:
        return {"loaded": False, "error": str(exc), **status}
    db.match_journals()
    return {"loaded": True, "file": path.name, "n": n, **db.journal_metrics_status()}


journal_status = load_journal_metrics()

if "settings" not in st.session_state:
    st.session_state.settings = db.get_settings()
settings = st.session_state.settings

# I valori di partenza vanno messi PRIMA che qualunque widget nasca: un widget
# senza `value=` prende il proprio default (per un number_input, il minimo), e
# se la voce in session_state arrivasse dopo sarebbe troppo tardi - la sidebar
# mostrerebbe un filtro di zero anni invece di dieci.
#
# E vanno RISCRITTI a ogni giro, non solo messi la prima volta. Streamlit manda
# al browser il valore di sessione di un widget solo se e' stato scritto nello
# stesso giro in cui il widget nasce; scritto in un giro prima, lo usa lato
# server ma il browser disegna il default. Succedeva dopo la schermata del primo
# avvio, che si ferma prima dei widget: la ricerca partiva con dieci anni e il
# riquadro ne mostrava zero. Riscriverli costa niente e tiene anche le liste del
# metodo di pubblicazione non scelto, che Streamlit altrimenti butterebbe via
# nel giro in cui non sono disegnate.
# I titoli di Radiopaedia usati come filtro (`hd_*`) stanno qui per la stessa
# ragione: la loro riga e' chiusa finche' non la si apre, e quello che c'e'
# scelto deve restare in sessione anche mentre non e' disegnato.
try:
    _first_profile = next(iter(sx.profile_labels()), "")
except sx.StructureError:
    _first_profile = ""
_defaults = {**SEARCH_FILTER_PRESETS["reviews"], **SEARCH_PREFS, "sf_mode": "reviews",
             "hd_open": False, "hd_profile": _first_profile, "hd_picked": [],
             "hd_mode": "both",
             "abs_open_search": settings.get("abstracts_open") == "1"}


def keep_defaults(only: tuple[str, ...] | None = None) -> None:
    """Riscrive in sessione i valori qui sopra, per le ragioni dette sopra.
    E' una funzione perche' va chiamata due volte: qui, a ogni giro intero, e
    in testa alla scheda di ricerca, che da frammento gira anche da sola. Li'
    con `only`: le preferenze della barra laterale a quel punto sono widget
    gia' nati, e Streamlit non lascia riscrivere la voce di un widget nato."""
    for key, value in _defaults.items():
        if only is None or key in only:
            st.session_state[key] = st.session_state.get(key, value)


# Le voci che appartengono alla scheda di ricerca: i filtri, i titoli di
# Radiopaedia e l'interruttore degli abstract dei risultati.
SEARCH_TAB_KEYS = tuple(k for k in _defaults if k not in SEARCH_PREFS)

# "Abstracts open" e' una scelta sola per i risultati di ricerca e per lo
# Screening, e lo Screening la scrive nel database per conto suo (e' una pagina
# a parte: vedi `bench.py`). A ogni giro intero si guarda se e' cambiata la'.
_abstracts_now = db.get_settings().get("abstracts_open")
if _abstracts_now != settings.get("abstracts_open"):
    settings["abstracts_open"] = _abstracts_now
    st.session_state["abs_open_search"] = _abstracts_now == "1"

keep_defaults()


# ---------------------------------------------------------------------------
# helper
# ---------------------------------------------------------------------------

def libkey_url(pmid: str) -> str | None:
    lib = (settings.get("libkey_library_id") or "").strip()
    return f"https://libkey.io/libraries/{lib}/{pmid}" if lib else None


def unpaywall_email() -> str:
    """L'email che va nelle chiamate a Unpaywall.

    Se non se n'e' messa una apposta si usa quella dell'NCBI: sono due servizi
    che chiedono la stessa cosa per la stessa ragione - sapere chi sta
    chiamando, per poterlo avvisare se qualcosa va storto - e farla scrivere
    due volte sarebbe solo un modo di dimenticarne una."""
    return ((settings.get("unpaywall_email") or "").strip()
            or (settings.get("ncbi_email") or "").strip())


def http_session() -> requests.Session:
    if "http" not in st.session_state:
        st.session_state.http = requests.Session()
    return st.session_state.http


def lib_folder() -> Path:
    """La cartella dei PDF, quella scelta nelle impostazioni o quella di default."""
    return paths.pdf_folder(settings.get("pdf_folder") or "")


def attach_pdf(pmid: str, *, path: Path | None = None, data: bytes | None = None,
               source: str, move: bool = False) -> str | None:
    """Mette un PDF in libreria col nome della citazione, nella cartella
    scelta nelle impostazioni. Ritorna l'errore da mostrare, o None."""
    return bench.attach_pdf(pmid, lib_folder(), path=path, data=data,
                            source=source, move=move)


@st.cache_data(show_spinner=False, max_entries=500)
def identify_pdf(path: str, mtime: float, size: int) -> dict:
    """DOI, PMID, titoli e impronta di un PDF aggiunto. La chiave comprende
    data e dimensione: un file cambiato con lo stesso nome si rilegge."""
    found = library.identify(Path(path))
    found["sha256"] = library.sha256_of(Path(path))
    return found


@st.cache_data(show_spinner=False)
def radiopaedia_index(path: str, mtime: float) -> list[dict]:
    return study.read_index(Path(path))


def on_highlight_toggle(highlight_id: int, widget_key: str) -> None:
    """La spunta di un'evidenziazione, dalla scheda Library. E' la stessa
    della finestra di studio: quella la rilegge da sola entro pochi secondi."""
    try:
        db.set_highlight_done(highlight_id, st.session_state[widget_key])
    except sqlite3.Error as e:
        st.session_state[widget_key] = not st.session_state[widget_key]
        st.error(f"Could not save the tick: {e}")


def on_pick(pmid: str, widget_key: str) -> None:
    """Riporta la spunta 'Save' di una scheda dei risultati nella selezione."""
    st.session_state.setdefault("search_selection", {})[pmid] = bool(
        st.session_state[widget_key])


def effective_filters(state) -> dict:
    """I filtri come arrivano davvero a PubMed.

    Con l'interruttore su un fascio contano i valori del fascio, e quelli dei
    controlli di "Custom" restano in sessione per quando ci si torna. La lista
    del metodo di pubblicazione non scelto resta anche lei in sessione, ma non
    conta: qui sparisce."""
    state = SEARCH_FILTER_PRESETS.get(state.get("sf_mode"), state)
    by = state.get("sf_type_by", "none")
    types = list(state.get("sf_types") or []) if by == "pt" else []
    in_range = state.get("sf_date_by") == "range"
    return {
        "years": 0 if in_range else int(state.get("sf_years") or 0),
        "year_from": int(state.get("sf_year_from") or 0) if in_range else 0,
        "year_to": int(state.get("sf_year_to") or 0) if in_range else 0,
        "abstract": bool(state.get("sf_abstract")),
        "free_full_text": bool(state.get("sf_freefulltext")),
        "full_text": bool(state.get("sf_fulltext")),
        "associated_data": bool(state.get("sf_data")),
        "languages": sorted(state.get("sf_languages") or []),
        "humans": bool(state.get("sf_humans")),
        "other_animals": bool(state.get("sf_animals")),
        "sexes": [label for label, key in (("Female", "sf_female"), ("Male", "sf_male"))
                  if state.get(key)],
        "ages": [a for a in pubmed.AGE_LABELS if a in (state.get("sf_ages") or [])],
        "exclude_preprints": bool(state.get("sf_nopreprints")),
        "medline": bool(state.get("sf_medline")),
        "types": sorted(types),
        "issg": sorted(state.get("sf_issg") or []) if by == "issg" else [],
    }


def reviews_help() -> str:
    """Cosa aggiunge "Recent reviews" alla query, scritto dai valori del
    fascio: se il fascio cambia, il riquadro del punto di domanda lo segue."""
    preset = SEARCH_FILTER_PRESETS["reviews"]
    return (
        f"**{SEARCH_MODES['reviews']}** adds these filters to your search "
        "terms:\n\n"
        f"- published in the last {preset['sf_years']} years "
        f"(since {TODAY.year - preset['sf_years']})\n"
        "- with a link to a full text\n"
        f"- in {' or '.join(preset['sf_languages'])}\n"
        "- without the records indexed as animal studies and not as human "
        "ones. Records too recent to be indexed are kept.\n"
        "- with one of these NLM publication types: "
        + ", ".join(preset["sf_types"]) + "\n\n"
        f"To change any of them, choose **{SEARCH_MODES['custom']}**.")


def on_heading_profile() -> None:
    """Cambiato il tipo di articolo, i titoli scelti si svuotano: quelli di
    prima possono non esistere nel tipo nuovo, e un multiselect con un valore
    che non e' fra le sue opzioni va in errore."""
    st.session_state.hd_picked = []


def describe_filters(f: dict) -> str:
    """In parole quello che la query chiedera'. Scritto dai valori e non da
    una frase fissa: la frase fissa era il modo in cui la schermata diceva
    "ultimi dieci anni" mentre i filtri erano gia' spenti."""
    bits = []
    if f["years"]:
        bits.append(f"since {TODAY.year - f['years']}")
    if f["year_from"] or f["year_to"]:
        bits.append(f"published {f['year_from']}–{f['year_to']}")
    if f["abstract"]:
        bits.append("abstract")
    if f["free_full_text"]:
        bits.append("free full text")
    if f["full_text"]:
        bits.append("full text")
    if f["associated_data"]:
        bits.append("associated data")
    if f["languages"]:
        bits.append(" or ".join(f["languages"]))
    if f["humans"] and f["other_animals"]:
        bits.append("humans or other animals")
    elif f["humans"]:
        bits.append("no animal-only studies")
    elif f["other_animals"]:
        bits.append("other animals")
    if f["sexes"]:
        bits.append(" or ".join(f["sexes"]).lower())
    if f["ages"]:
        bits.append("age: " + " or ".join(f["ages"]))
    if f["medline"]:
        bits.append("MEDLINE")
    if f["exclude_preprints"]:
        bits.append("no preprints")
    if f["types"]:
        shown = ", ".join(f["types"][:4]) + ("…" if len(f["types"]) > 4 else "")
        bits.append(f"{len(f['types'])} publication types ({shown})")
    if f["issg"]:
        bits.append("ISSG: " + " or ".join(f["issg"]))
    if not bits:
        return "Nothing but your search terms goes to PubMed."
    text = " · ".join(bits)
    return text[0].upper() + text[1:] + "."


def on_abstracts_open(key: str) -> None:
    """Abstract aperti o chiusi: un'abitudine di lettura, quindi una scelta
    sola che vale per i risultati e per lo Screening e resta al riavvio. Lo
    Screening la legge dal database ogni volta che torna in vista."""
    value = bool(st.session_state[key])
    db.save_settings({"abstracts_open": "1" if value else "0"})
    st.session_state.settings = db.get_settings()


def fmt_int(value) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "–"
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "–"


# ---------------------------------------------------------------------------
# stile
# ---------------------------------------------------------------------------

def setting_float(key: str, default: float) -> float:
    try:
        return float(settings.get(key) or default)
    except ValueError:
        return default


title_rem = setting_float("title_font_rem", 1.35)
reading_rem = setting_float("reading_font_rem", 1.05)
reading_font = theme.READING_FONTS.get(settings.get("reading_font") or "serif",
                                       theme.READING_FONTS["serif"])

# Tutto il CSS e' scritto per andare bene su tutt'e due i temi senza
# sapere quale c'e': grigi fatti di trasparenza (`rgba(128,128,128,...)`) e
# testo secondario fatto di opacita', che su un fondo chiaro scuriscono e su uno
# scuro schiariscono da soli.
st.markdown(
    f"""
    <style>
      /* Il titolo come quello di Radiouploader: il nome, e accanto cosa fa. */
      .app-title {{
        display: flex; align-items: baseline; gap: .6rem; flex-wrap: wrap;
        font-size: 1.35rem; font-weight: 700; letter-spacing: -.01em;
        margin: 0 0 .35rem 0;
      }}
      .app-title .sub {{ font-size: .9rem; font-weight: 400; opacity: .7; }}
      /* La freccia che riapre la barra laterale, da sola, non dice cosa c'e'
         dietro: impostazioni, backup, import. Accanto ci va scritto. */
      [data-testid="stExpandSidebarButton"] {{ width: auto; }}
      [data-testid="stExpandSidebarButton"]::after {{
        content: "Options"; font-size: .9rem; font-weight: 500;
        margin: 0 .5rem 0 .25rem; white-space: nowrap;
      }}
      /* Le tre schede come i passi di Radiouploader: pillole numerate, quella
         attiva su un fondo piu' marcato. La lineetta colorata sotto la scheda
         di Streamlit diceva la stessa cosa in un'altra lingua. */
      div[role="tablist"] {{
        gap: 6px; padding-bottom: .55rem;
        border-bottom: 1px solid rgba(128,128,128,.22);
      }}
      div[data-testid="stTab"] {{
        padding: .3rem .9rem; border-radius: 999px; height: auto; opacity: .75;
      }}
      /* la lineetta sotto la scheda attiva: e' il figlio senza testo */
      div[data-testid="stTab"] > div:not([data-testid]) {{ display: none; }}
      div[data-testid="stTab"]:hover {{ opacity: 1; background: rgba(128,128,128,.10); }}
      div[data-testid="stTab"][aria-selected="true"] {{
        opacity: 1; background: rgba(128,128,128,.18);
      }}
      div[data-testid="stTab"] p {{ font-size: .95rem; }}
      /* Denso apposta: si sfogliano centinaia di record, e ogni riga di aria
         in piu' e' un articolo in meno per schermata. Si stringe lo spazio fra
         i blocchi e dentro le schede, non il testo - quello resta leggibile. */
      div[data-testid="stVerticalBlock"] {{ gap: .55rem; }}
      div[data-testid="stExpander"] summary {{ padding: .3rem .6rem; }}
      div[data-testid="stExpander"] details {{ border-radius: 10px; }}
      div[data-testid="stLayoutWrapper"] > div[data-testid="stVerticalBlock"] {{
        border-radius: 10px;
      }}
      {cards.css(title_rem, reading_rem, reading_font)}
      /* Lo Screening e' una pagina sua dentro un iframe (vedi `bench.py`), e
         scorre li' dentro: l'iframe arriva al fondo della finestra, cosi' di
         barre di scorrimento ce n'e' una sola. */
      iframe[data-testid="stIFrame"] {{
        height: calc(100vh - 13rem) !important; min-height: 28rem;
        border: 0; border-radius: 10px;
      }}
      /* titolo degli expander (abstract) leggermente piu' grande del default */
      div[data-testid="stExpander"] summary p {{ font-size: {max(0.95, title_rem - 0.3):.2f}rem; }}
    </style>
    """,
    unsafe_allow_html=True,
)

# `st.title` occupa due righe su una finestra normale e le ruba a quello che
# si sta guardando. In un'app che si tiene aperta tutto il giorno il titolo
# serve a sapere dove sei, non a fare da copertina.
st.markdown(
    '<div class="app-title">Radiowriter'
    '<span class="sub">Literature and drafting for Radiopaedia articles</span></div>',
    unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# il primo avvio
# ---------------------------------------------------------------------------

# Chi apre l'app la prima volta non sa che deve dare un'email, e soprattutto non
# sa perche': senza una ragione detta, chiedere un indirizzo appena aperta una
# cosa sembra la solita raccolta di contatti. Non lo e', e vale la pena dirlo -
# nessuno dei tre servizi manda posta, nessuno chiede di registrarsi, e l'email
# resta su questo computer, in un file SQLite.

SERVICES = [
    ("PubMed (NCBI E-utilities)", True,
     "Searches PubMed and downloads the records. **Requires an email "
     "address in every request**, which NCBI uses to contact you if your "
     "requests cause a problem. No registration is needed and no mail is "
     "sent."),
    ("Unpaywall", True,
     "Reports whether a paper has a legal free copy, and where. It requires "
     "an email address in every request, for the same reason. No key or "
     "registration is needed."),
    ("Semantic Scholar", False,
     "Citation counts, used to sort the results. It works without a key, "
     "more slowly."),
    ("LibKey", False,
     "Direct links to the full text through your library's subscription. "
     "It needs your library's ID."),
]


def setup_screen() -> None:
    """La schermata del primo avvio: un campo obbligatorio e il perche'."""
    # Il titolo lo stampa gia' il modulo, qualche riga sopra.
    st.subheader("Set your email address")

    st.markdown(
        "This app sends requests to a few public services. Two of them "
        "require **an email address in every request**, so that they can "
        "contact you if your requests cause a problem. You do not have to "
        "register anywhere, and the address is stored only on this computer, "
        "in the app's database file."
    )

    with st.form("first_run"):
        email = st.text_input(
            "Your email address", placeholder="[email removed]",
            help="It goes to PubMed and to Unpaywall as the caller's address.")

        st.caption("**What each service is for**")
        for name, required, why in SERVICES:
            st.markdown(
                f"- **{name}** ({'*required*' if required else '*optional*'}). {why}")

        with st.expander("Optional keys and IDs (you can add them later)",
                         expanded=False):
            api_key = st.text_input(
                "NCBI API key", type="password",
                help="Raises the rate limit from 3 to 10 requests a second. "
                     "Free, from your NCBI account settings.")
            s2_key = st.text_input(
                "Semantic Scholar API key", type="password",
                help="Makes the citation lookup faster. Free, on request.")
            libkey = st.text_input(
                "LibKey library ID",
                help="Your library's Third Iron ID. It appears in the URL "
                     "libkey.io/libraries/<ID>/…")

        go, skip = st.columns([1, 1])
        started = go.form_submit_button("Save and start", type="primary",
                                        width="stretch")
        skipped = skip.form_submit_button(
            "Skip (read the archive only)", width="stretch")

    if started:
        if "@" not in email or "." not in email.split("@")[-1]:
            st.error("That does not look like an email address. PubMed rejects "
                     "the request if it is not a real one.")
            return
        db.save_settings({
            "ncbi_email": email.strip(),
            "unpaywall_email": email.strip(),
            "ncbi_api_key": api_key.strip(),
            "s2_api_key": s2_key.strip(),
            "libkey_library_id": libkey.strip(),
        })
        st.session_state.settings = db.get_settings()
        st.rerun()

    if skipped:
        # Non si salva niente: la prossima volta la schermata ritorna, ed e'
        # giusto - senza email la ricerca non parte, e scoprirlo al primo
        # tentativo sarebbe peggio che rivedere questa pagina.
        st.session_state.setup_skipped = True
        st.rerun()

    st.caption("You can change all of this later under ⚙️ Settings in the sidebar.")


if (not (settings.get("ncbi_email") or "").strip()
        and not st.session_state.get("setup_skipped")):
    setup_screen()
    st.stop()


# ---------------------------------------------------------------------------
# sidebar: impostazioni + import manuale
# ---------------------------------------------------------------------------

with st.sidebar:
    # Dove sta l'archivio, sempre a schermo. Prima non lo diceva nessuno, e
    # l'unico modo di sapere quale dei possibili file si stesse usando era
    # aprire un terminale: chi si e' trovato davanti un archivio inatteso ha
    # dovuto chiedersi se fosse un residuo del pacchetto invece di leggerlo.
    _db_file, _db_origin = paths.db_origin()

    # I numeri si rileggono da soli ogni pochi secondi. Le schede girano
    # ognuna per conto suo e lo Screening e' una pagina a parte: salvare o
    # eliminare un articolo non fa piu' rigirare la barra laterale, e senza
    # questo il conto restava quello dell'ultimo giro intero.
    @st.fragment(run_every=ARCHIVE_REFRESH_SECONDS)
    def archive_counts() -> None:
        counts = db.archive_summary()
        st.markdown(
            f"**🗄 Archive** · {counts['articles']:,} articles"
            + (f" · {counts['lists']} list(s)" if counts["lists"] else "")
            + (f" · {counts['drafts']} draft(s)" if counts["drafts"] else "")
            + (f" · {counts['pdfs']} PDF(s)" if counts["pdfs"] else ""))

    archive_counts()
    st.caption(f"`{paths.short(_db_file)}`")
    # Il caso normale non si commenta; gli altri due si', in una riga sola. La
    # ragione per esteso sta nelle docs: qui serve solo che nessuno debba
    # chiedersi da dove sia uscito questo archivio.
    if _db_origin == paths.FROM_SOURCE:
        st.caption(
            "Next to the source code, not in the data folder "
            "([why](https://gmadevs.github.io/Radiowriter/internals/storage))")
    elif _db_origin == paths.FROM_ENV:
        st.caption("Set by `RADIOPAEDIA_DB`.")
    st.divider()

    if removed_at_boot:
        st.info(f"🧹 {removed_at_boot} already-read articles were purged at startup.")

    with st.expander("⚙️ Settings", expanded=not settings.get("ncbi_email")):
        with st.form("settings_form"):
            ncbi_email = st.text_input(
                "NCBI email", value=settings.get("ncbi_email", ""),
                help="Required by the E-utilities to identify the caller.")
            ncbi_key = st.text_input(
                "NCBI API key (optional)", value=settings.get("ncbi_api_key", ""),
                type="password", help="Raises the limit from 3 to 10 requests/second.")
            s2_key = st.text_input(
                "Semantic Scholar API key (optional)", value=settings.get("s2_api_key", ""),
                type="password", help="Without a key, enrichment is slower (~1 batch/sec).")
            libkey_id = st.text_input(
                "LibKey library ID", value=settings.get("libkey_library_id", ""),
                help="Your library's 'Third Iron library ID': it appears in the "
                     "URL libkey.io/libraries/<ID>/...")
            upw_email = st.text_input(
                "Unpaywall email", value=settings.get("unpaywall_email", ""),
                help="Unpaywall requires an email address in every request. It "
                     "is not a key and no registration is needed. If empty, "
                     "the NCBI email above is used.")
            pdf_dir = st.text_input(
                "PDF library folder", value=settings.get("pdf_folder", ""),
                placeholder=paths.short(paths.home(create=False) / "PDFs"),
                help="Where the PDFs are kept, named after their citation. "
                     "Empty = the data folder. An existing folder can be moved: "
                     "only the file names are in the database.")
            font_rem = st.slider(
                "Title size (rem)", 1.0, 2.2, title_rem, 0.05)
            # Il carattere degli abstract si sceglie a parte perche' e' la
            # sola cosa che si legge per paragrafi: il resto si scorre.
            read_font = st.radio(
                "Abstract typeface", list(theme.READING_FONTS),
                index=list(theme.READING_FONTS).index(
                    settings.get("reading_font") if settings.get("reading_font")
                    in theme.READING_FONTS else "serif"),
                format_func={"serif": "Serif (for long reading)",
                             "sans": "Sans, like the rest"}.get,
                horizontal=True)
            read_rem = st.slider(
                "Abstract size (rem)", 0.9, 1.4, reading_rem, 0.05)
            st.caption("Light or dark: menu ⋮ at the top right → Settings.")
            if st.form_submit_button("Save settings", width="stretch"):
                values = {
                    "ncbi_email": ncbi_email.strip(),
                    "ncbi_api_key": ncbi_key.strip(),
                    "s2_api_key": s2_key.strip(),
                    "libkey_library_id": libkey_id.strip(),
                    "unpaywall_email": upw_email.strip(),
                    "pdf_folder": pdf_dir.strip(),
                    "title_font_rem": f"{font_rem:.2f}",
                    "reading_font": read_font,
                    "reading_font_rem": f"{read_rem:.2f}",
                }
                db.save_settings(values)
                st.session_state.settings = db.get_settings()
                st.rerun()

    # Queste quattro non sono filtri della ricerca, sono il modo in cui l'app si
    # comporta: si scelgono una volta e si lasciano stare. Stavano in mezzo ai
    # filtri, dove costringevano a scorrere ogni volta oltre roba che non si
    # tocca mai. Sono qui, sempre visibili, e la scheda di ricerca resta breve.
    st.markdown("**⚙ Search behaviour**")
    max_results = st.selectbox(
        "Records to download", MAX_RESULTS_OPTIONS, key="sf_max_results",
        format_func=lambda n: (f"All (PubMed's limit is {pubmed.ESEARCH_CAP:,})"
                               if n == 0 else f"First {n:,}"),
        help="PubMed is queried in full regardless: this only caps how many "
             "records are downloaded in detail. A few thousand take a few "
             "minutes, more with citations and open access switched on.")
    exclude_label = st.selectbox(
        "Skip what is already known", list(db.EXCLUDE_MODES.values()),
        key="sf_exclude",
        help="Applied right after esearch: a discarded PMID costs neither a "
             "PubMed nor a Semantic Scholar call.")
    exclude_mode = next(k for k, v in db.EXCLUDE_MODES.items() if v == exclude_label)
    use_s2 = st.checkbox("Citations (Semantic Scholar)", key="sf_s2")
    use_oa = st.checkbox("Open access (Unpaywall)", key="sf_oa")
    st.divider()

    with st.expander("📊 Journal metrics", expanded=False):
        st.caption(
            "Quartiles and SJR come from SCImago. **These are not the Journal "
            "Impact Factor**, which is published by Clarivate in the JCR. SJR "
            "weights citations by the rank of the citing journal. *Cites/doc "
            "(2y)* is calculated like an impact factor, but on Scopus data."
        )
        found_file, file_origin = paths.journal_csv_origin()
        if found_file is None:
            st.warning(
                "No journal metrics file was found, including the one "
                "included with the app. The installation looks incomplete.")
        else:
            status = db.journal_metrics_status()
            st.caption(f"`{found_file.name}`: **{status['journals']:,}** journals · "
                       f"**{status['matched']:,}** of {status['articles']:,} "
                       f"articles matched to one.")
            if file_origin == paths.FROM_BUNDLE:
                st.caption(
                    "This is the copy included with the app. For a newer "
                    "year, click *Download data* on "
                    "[scimagojr.com](https://www.scimagojr.com/journalrank.php), "
                    "put the CSV in the data folder, then click the button "
                    "below. A file whose name starts with `scimagojr` is "
                    "used in place of this copy.")
            else:
                st.caption("Your own download. It is used in place of the copy "
                           "included with the app.")
            if st.button("↻ Reload the file and re-match", width="stretch"):
                with st.status("Reading the SCImago file…", expanded=True) as box:
                    try:
                        rows = jr.read(found_file)
                    except jr.JournalDataError as exc:
                        box.update(label="Could not read it", state="error")
                        st.error(str(exc))
                    else:
                        box.write(f"{len(rows):,} journals read.")
                        db.import_journal_metrics(rows)
                        box.write("Matching the archive by ISSN…")
                        matched, seen = db.match_journals()
                        box.update(
                            label=f"{matched:,} of {seen:,} articles matched.",
                            state="complete")
                        load_journal_metrics.clear()
            st.caption(
                "Articles are matched by ISSN. The unmatched ones are in "
                "journals that SCImago does not list. They show no quartile.")

    with st.expander("⇅ Export and backup", expanded=False):
        st.caption(
            "**`.nbib`** is PubMed's export format. It contains only the "
            "articles. Reference managers can read it, and so can the import "
            "below. **`.json`** contains the archive: read and flagged "
            "states, lists and drafts. Use it to move to another computer. "
            "It does not contain the PDFs."
        )

        scopes = {"Everything": ("all", None),
                  "Flagged only": ("flagged", None),
                  "Still to read": ("unread", None)}
        for row in db.list_lists():
            scopes[f"List: {row['name']}"] = ("list", row["id"])
        picked = st.selectbox("What to export", list(scopes), key="exp_scope")
        scope, scope_list = scopes[picked]
        # `data` e' una funzione: i file si costruiscono al clic, non a ogni
        # giro dell'app. Qui serve solo il numero per l'etichetta.
        n_export = db.count_for_export(scope, scope_list)
        st.download_button(
            f"⤓ {n_export} article(s) as .nbib",
            data=lambda: backup.to_medline(db.articles_for_export(scope, scope_list)),
            file_name=backup.medline_filename(picked.replace("List: ", "")),
            mime="text/plain", width="stretch", disabled=not n_export,
            key="exp_medline")
        st.caption("Read, flagged, lists and drafts are not in a `.nbib`: "
                   "MEDLINE has no field for them.")

        st.divider()
        n = backup.quick_counts()
        st.download_button(
            "⤓ Full backup (.json)", data=lambda: backup.to_json(backup.bundle()),
            file_name=backup.json_filename(), mime="application/json",
            width="stretch", key="exp_json")
        st.caption(
            f"{n['articles']:,} articles · {n['lists']} list(s) · "
            f"{n['drafts']} draft(s) · {n['citations']} resolved citation(s). "
            "**Settings are not included**, so the file does not contain "
            "your email address or keys."
        )

        st.divider()
        st.caption("**Restore a backup.** Nothing is overwritten: whatever is "
                   "already here is kept, and only what is missing is added.")
        incoming = st.file_uploader("Backup file", type=["json"],
                                    key="restore_file", label_visibility="collapsed")
        if incoming is not None:
            try:
                parsed = backup.read_bundle(incoming.getvalue())
            except backup.BackupError as exc:
                st.error(str(exc))
            else:
                got = backup.counts(parsed)
                st.caption(f"Written {str(parsed.get('exported'))[:10]}. "
                           f"{got['articles']:,} articles, {got['lists']} list(s), "
                           f"{got['drafts']} draft(s).")
                if st.button("Restore it", type="primary", width="stretch",
                             key="restore_go"):
                    with st.spinner("Putting it back…"):
                        report = backup.restore(parsed)
                    st.success(
                        f"Added {report['articles']:,} articles, "
                        f"{report['lists']} list(s) with {report['list_items']} "
                        f"entries, {report['drafts']} draft(s).")
                    st.rerun()

    with st.expander("📥 Import PubMed export", expanded=False):
        import_type = st.radio(
            "Method:", ["Upload a file", "Paste raw text"],
            help="Imports records in PubMed's MEDLINE format, in which every "
                 "record starts with a `PMID-` line. On PubMed, click **Save** "
                 "and choose the format **PubMed** (a `.txt` file), or click "
                 "**Send to**, then **Citation manager** (a `.nbib` file). "
                 "The Summary, Abstract, PMID and CSV formats cannot be "
                 "imported.")
        input_text = ""
        if import_type == "Upload a file":
            uploaded = st.file_uploader(
                "PubMed export file", type=["txt", "nbib"],
                help="A `.txt` file saved from PubMed in the format PubMed, or "
                     "a `.nbib` file.")
            if uploaded is not None:
                input_text = uploaded.read().decode("utf-8", errors="replace")
        else:
            input_text = st.text_area("PubMed text (MEDLINE format):", height=200)

        # La lista si sceglie PRIMA di importare: dopo, i record di questo file
        # sono mescolati agli altri dell'archivio e non si ritrovano piu'.
        NO_LIST = "No list"
        import_list = st.selectbox(
            "Add to list",
            [NO_LIST] + [r["name"] for r in db.list_lists()] + [NEW_LIST],
            key="import_list",
            help="The reading list the imported articles are added to. With "
                 "No list they are saved in the archive only.")
        if import_list == NEW_LIST:
            import_list = " ".join(st.text_input(
                "New list name", key="import_list_new",
                label_visibility="collapsed",
                placeholder="Name of the new list").split())

        if st.button("Import into database", width="stretch", key="import_go",
                     disabled=not import_list):
            if input_text.strip():
                parsed = pubmed.parse_medline_text(input_text)
                added, skipped_screened, already = db.insert_articles(parsed)
                message = (
                    f"Found {len(parsed)} articles. Imported {added} new ones "
                    f"({already} already in the archive, {skipped_screened} read and "
                    f"discarded in the past).")
                if import_list != NO_LIST:
                    list_id = db.create_list(import_list, "Filled by Import PubMed export")
                    if list_id is None:
                        list_id = next(r["id"] for r in db.list_lists()
                                       if r["name"] == import_list)
                    # solo quelli che in archivio ci sono: un lavoro letto e
                    # scartato in passato non rientra, e in lista sarebbe un
                    # PMID di cui non si sa piu' niente
                    in_db, _ = db.classify_pmids([r["pmid"] for r in parsed])
                    in_list = db.add_to_list(
                        list_id, [r["pmid"] for r in parsed if r["pmid"] in in_db],
                        note=f"imported {date.today():%Y-%m-%d}")
                    message += f" {in_list} added to the list “{import_list}”."
                st.success(message)
            else:
                st.warning("Nothing to import.")


# ---------------------------------------------------------------------------
# paginazione, condivisa da ricerca e screening
# ---------------------------------------------------------------------------

def render_pager(n_pages: int, key: str, *, compact: bool,
                 state_key: str = "screen_page") -> None:
    """Barra di paginazione. `compact` = prec/succ + salto diretto; altrimenti
    elenco numerato delle pagine. `state_key` dice quale contatore di pagina
    muovere: le schede della ricerca e quelle dello screening ne hanno uno
    per uno."""
    page = st.session_state.get(state_key, 1)

    if compact:
        c_prev, c_jump, c_next = st.columns([1, 2, 1])
        if c_prev.button("‹ Previous", disabled=page <= 1, key=f"{key}_prev",
                         width="stretch"):
            st.session_state[state_key] = page - 1
            st.rerun()
        with c_jump:
            # la chiave include la pagina corrente: senza, il widget conserva il
            # proprio vecchio valore e "rimanda indietro" i salti fatti con i
            # pulsanti numerati in fondo alla lista
            target = st.number_input(
                f"Page (of {n_pages})", 1, n_pages, page, 1,
                key=f"{key}_num_{page}_{n_pages}", label_visibility="collapsed")
            if target != page:
                st.session_state[state_key] = int(target)
                st.rerun()
        if c_next.button("Next ›", disabled=page >= n_pages, key=f"{key}_next",
                         width="stretch"):
            st.session_state[state_key] = page + 1
            st.rerun()
        return

    # elenco numerato: finestra di 7 pagine attorno a quella corrente, con i
    # bordi sempre raggiungibili
    window = {1, n_pages, page}
    window.update(range(max(1, page - 3), min(n_pages, page + 3) + 1))
    numbers = sorted(window)

    items: list[int | None] = []
    previous = 0
    for n in numbers:
        if previous and n - previous > 1:
            items.append(None)  # separatore
        items.append(n)
        previous = n

    cols = st.columns(len(items) + 2)
    if cols[0].button("«", disabled=page <= 1, key=f"{key}_first",
                      width="stretch"):
        st.session_state[state_key] = 1
        st.rerun()
    for col, item in zip(cols[1:-1], items):
        if item is None:
            col.markdown("<div style='text-align:center'>…</div>", unsafe_allow_html=True)
            continue
        if col.button(str(item), key=f"{key}_p{item}", width="stretch",
                      type="primary" if item == page else "secondary"):
            st.session_state[state_key] = item
            st.rerun()
    if cols[-1].button("»", disabled=page >= n_pages, key=f"{key}_last",
                       width="stretch"):
        st.session_state[state_key] = n_pages
        st.rerun()


# ---------------------------------------------------------------------------
# le faccette sui risultati gia' scaricati
# ---------------------------------------------------------------------------

def results_filters(records: list[dict], metric_of, status_by_pmid: dict,
                    gen: int) -> list[dict]:
    """Restringe i risultati SENZA rifare la ricerca.

    E' un'altra cosa dai filtri della query, e vale la pena tenerle separate:
    quelli decidono cosa PubMed spedisce e costano una ricerca ogni volta che
    li tocchi; questi decidono cosa guardi adesso, sono immediati e si
    ripensano venti volte. Un tipo di articolo tolto qui puo' essere rimesso
    subito dopo senza aspettare niente.

    Le chiavi dei widget portano dentro `gen`, che cambia a ogni ricerca nuova:
    un filtro dimenticato acceso nasconderebbe i risultati della ricerca
    seguente senza che si capisca perche'.
    """
    if not records:
        return records

    def counted(options: dict[str, int]) -> tuple[list[str], object]:
        return list(options), (lambda o: f"{o} ({options[o]})")

    # --- quello che c'e' davvero in questi risultati ---------------------
    status_counts: dict[str, int] = {}
    for state in status_by_pmid.values():
        status_counts[state] = status_counts.get(state, 0) + 1

    type_counts: dict[str, int] = {}
    for rec in records:
        for kind in {t.strip() for t in clean(rec.get("pub_types")).split(";") if t.strip()}:
            type_counts[kind] = type_counts.get(kind, 0) + 1
    type_options = dict(sorted(type_counts.items(), key=lambda kv: -kv[1]))

    NO_METRIC = "Not in SCImago"
    quartile_counts: dict[str, int] = {}
    for rec in records:
        metric = metric_of(rec)
        key = (metric["quartile"] if metric is not None else None) or NO_METRIC
        quartile_counts[key] = quartile_counts.get(key, 0) + 1
    quartile_options = {q: quartile_counts[q]
                        for q in jr.QUARTILES + [NO_METRIC] if q in quartile_counts}

    n_free = sum(1 for rec in records
                 if clean(rec.get("oa_status")) not in ("", "closed", "unknown"))
    asked_oa = any(clean(rec.get("oa_fetched_at")) for rec in records)

    years = sorted({int(y) for y in (clean(r.get("year")) for r in records)
                    if y.isdigit()})
    has_cites = any(rec.get("citation_count") is not None for rec in records)

    key = lambda name: f"rf_{name}_{gen}"    # noqa: E731

    def clear() -> None:
        for name in ("status", "types", "quartile", "oa", "years", "cites", "text"):
            st.session_state.pop(key(name), None)

    active = any(st.session_state.get(key(n)) for n in
                 ("status", "types", "quartile", "oa", "cites", "text"))

    with st.expander("⚙ Filter these results" + (" (on)" if active else ""),
                     expanded=active):
        st.caption("Narrows what is shown below. PubMed is not queried again.")

        c1, c2 = st.columns(2)
        with c1:
            opts, fmt = counted(status_counts)
            f_status = st.multiselect("Status", opts, format_func=fmt,
                                      key=key("status"))
            opts, fmt = counted(type_options)
            f_types = st.multiselect(
                "Article type", opts, format_func=fmt, key=key("types"),
                help="The publication types NLM assigned to these very records.")
        with c2:
            opts, fmt = counted(quartile_options)
            f_quartile = st.multiselect("Journal quartile", opts, format_func=fmt,
                                        key=key("quartile"))
            f_text = st.text_input(
                "Words in title or abstract", key=key("text"),
                placeholder="e.g. paediatric")

        c3, c4 = st.columns(2)
        with c3:
            if asked_oa:
                f_oa = st.checkbox(f"Only free full text ({n_free})",
                                   key=key("oa"))
            else:
                f_oa = False
                st.caption("Open access: not looked up for these records. "
                           "Tick *Open access (Unpaywall)* in the sidebar "
                           "before searching.")
            f_cites = st.number_input(
                "At least this many citations", 0, 10000, step=1,
                key=key("cites"), disabled=not has_cites,
                help=None if has_cites else
                "No citation data: enrich with Semantic Scholar first.")
        with c4:
            if len(years) > 1:
                f_years = st.slider("Published between", years[0], years[-1],
                                    (years[0], years[-1]), key=key("years"))
            else:
                f_years = None
            st.write("")
            st.button("✕ Clear these filters", on_click=clear,
                      key=f"rf_clear_{gen}", width="stretch")

    def keep(rec: dict) -> bool:
        if f_status and status_by_pmid.get(rec["pmid"]) not in f_status:
            return False
        if f_types:
            mine = {t.strip() for t in clean(rec.get("pub_types")).split(";")}
            if not mine & set(f_types):
                return False
        if f_quartile:
            metric = metric_of(rec)
            quartile = (metric["quartile"] if metric is not None else None) or NO_METRIC
            if quartile not in f_quartile:
                return False
        if f_oa and clean(rec.get("oa_status")) in ("", "closed", "unknown"):
            return False
        if f_cites:
            got = rec.get("citation_count")
            if got is None or got < f_cites:
                return False
        if f_years:
            year = clean(rec.get("year"))
            # Un record senza anno non si butta via: e' un dato che manca, non
            # un articolo fuori dall'intervallo.
            if year.isdigit() and not (f_years[0] <= int(year) <= f_years[1]):
                return False
        if f_text:
            needle = f_text.strip().lower()
            haystack = (clean(rec.get("title")) + " "
                        + clean(rec.get("abstract"))).lower()
            if needle and needle not in haystack:
                return False
        return True

    return [rec for rec in records if keep(rec)]


# ---------------------------------------------------------------------------
# il compositore di ricerche a blocchi
# ---------------------------------------------------------------------------

# I blocchi vivono in session_state come dizionari, non come dataclass: ogni
# riga ha un `id` che non viene mai riusato, e la chiave dei widget si costruisce
# da li'. Senza, togliere il secondo di tre termini farebbe scalare le chiavi di
# uno e il testo del terzo comparirebbe nella casella del secondo - Streamlit
# tiene il valore per chiave, non per posizione.

def qb_next_id() -> int:
    st.session_state.qb_seq = st.session_state.get("qb_seq", 0) + 1
    return st.session_state.qb_seq


def qb_new_term(text: str = "", field: str = "tiab") -> dict:
    return {"id": qb_next_id(), "text": text, "field": field}


def qb_new_block(join: str = "AND", terms: list[dict] | None = None,
                 label: str = "") -> dict:
    return {"id": qb_next_id(), "label": label, "join": join, "inner": "OR",
            "enabled": True, "terms": terms if terms is not None else [qb_new_term()]}


def qb_state() -> list[dict]:
    if "qb_blocks" not in st.session_state:
        st.session_state.qb_blocks = [qb_new_block()]
    return st.session_state.qb_blocks


def qb_model(raw: list[dict]) -> list[qb.Block]:
    """Dai dizionari della UI ai blocchi che `querybuilder` sa comporre."""
    return [
        qb.Block(
            label=b.get("label", ""),
            terms=[qb.Term(t.get("text", ""), t.get("field", "tiab"))
                   for t in b.get("terms", [])],
            inner=b.get("inner", "OR"),
            join=b.get("join", "AND"),
            enabled=bool(b.get("enabled", True)),
        )
        for b in raw
    ]


def qb_block_name(n: int, block: dict) -> str:
    return block.get("label") or f"Block {n}"


def strategy_panel(blocks: list[dict]) -> None:
    """Termini di ricerca ricavati dai titoli di un articolo Radiopaedia.

    I titoli di un articolo sono gia' la scaletta della ricerca da fare: se
    nella bozza c'e' `Epidemiology` la ricerca vuole prevalenza e incidenza, se
    c'e' `MRI` vuole la risonanza. Qui si sceglie da dove prendere i titoli - la
    bozza vera, o la struttura che Radiopaedia raccomanda per quel tipo di
    articolo - e ogni titolo diventa un pezzo di query.

    Vanno tutti in UN blocco solo, in OR fra loro. Metterli in blocchi diversi
    li legherebbe in AND, e chiederebbe a PubMed un lavoro che parla insieme di
    epidemiologia, risonanza e prognosi: quasi sempre zero risultati."""
    st.caption(
        "Each heading is turned into search terms: controlled vocabulary "
        "(MeSH), words from the title and abstract, or both."
    )

    source = st.radio(
        "Take the headings from", ["A draft", "An article type"],
        horizontal=True, key="stg_source", label_visibility="collapsed")

    titles: list[str] = []
    if source == "A draft":
        drafts = db.list_drafts()
        if not drafts:
            st.caption("No drafts yet. Write one in the Write tab, or take the "
                       "headings from an article type.")
            return
        # Si sceglie per id e non per riga: un widget con `key` finisce in
        # session_state, che Streamlit copia in profondita', e una sqlite3.Row
        # non e' copiabile - la pagina intera andrebbe in errore.
        by_id = {r["id"]: r for r in drafts}
        chosen_id = st.selectbox(
            "Draft", list(by_id), format_func=lambda i: by_id[i]["title"],
            key="stg_draft")
        if chosen_id is None:
            return
        titles = [h.title for h in sx.headings_in(by_id[chosen_id]["body_md"] or "")]
        if not titles:
            st.caption("That draft has no headings yet.")
            return
    else:
        try:
            labels = sx.profile_labels()
        except sx.StructureError as exc:
            st.warning(str(exc))
            return
        names = list(labels)
        profile = st.selectbox(
            "Kind of article", names, format_func=lambda n: labels[n],
            key="stg_profile")
        titles = [r.title for r in sx.rows_for(profile)]

    mode_key = st.radio(
        "Terms", list(stg.MODES), horizontal=True, key="stg_mode",
        format_func=lambda k: stg.MODES[k])

    pairs = stg.suggest(titles, mode_key)
    if not pairs:
        st.caption("None of these headings has a search strategy. They are "
                   "sections of an article, not search topics.")
        return

    st.caption(f"{len(pairs)} of the {len(set(titles))} headings have one.")
    # Nella chiave c'e' un contatore, come per la casella del testo della bozza:
    # dopo aver aggiunto le strategie la scelta va svuotata, e Streamlit non
    # lascia scrivere la voce di un widget gia' creato. Cambiando la chiave il
    # widget successivo e' un widget nuovo, e riparte vuoto.
    stamp = st.session_state.get("stg_gen", 0)
    picked = st.multiselect(
        "Headings", [name for name, _ in pairs], key=f"stg_picked_{stamp}",
        placeholder="Choose the headings to turn into terms…")

    if picked:
        by_name = dict(pairs)
        with st.container(height=150, border=True):
            for name in picked:
                st.caption(f"**{name}** → `{by_name[name]}`")

    targets = ["A new block, joined with AND"] + [
        f"Into {qb_block_name(n, b)}" for n, b in enumerate(blocks, 1)]
    # anche qui la chiave si muove con le opzioni: se un blocco viene tolto,
    # la scelta di prima non esiste piu' fra quelle possibili
    target = st.selectbox("Where do they go", targets,
                          key=f"stg_target_{len(blocks)}_{stamp}")

    if st.button(f"Add {len(picked)} strateg{'y' if len(picked) == 1 else 'ies'}",
                 disabled=not picked, key="stg_add", type="primary"):
        by_name = dict(pairs)
        # `raw`: sono gia' scritte in sintassi PubMed, tag di campo compresi,
        # e appiccicargliene un altro le romperebbe
        terms = [qb_new_term(by_name[name], "raw") for name in picked]
        if target == targets[0]:
            blocks.append(qb_new_block(join="AND", terms=terms,
                                       label="Radiopaedia headings"))
        else:
            blocks[targets.index(target) - 1]["terms"].extend(terms)
        st.session_state.stg_gen = stamp + 1
        st.rerun()


def modality_panel(blocks: list[dict]) -> None:
    """Le modalita' di imaging, scelte da un elenco invece che scritte a mano.

    La modalita' e' uno dei tre concetti di una ricerca seria, ed e' quello che
    si sbaglia piu' spesso: ogni tecnica ha tre o quattro nomi e nessuno li usa
    tutti. Qui si scelgono e ci pensa `modalities` a scriverle in tutte le
    forme, sigle e varianti britanniche comprese.

    Vanno in UN blocco solo, in OR fra loro, per la stessa ragione delle
    strategie: chiedere TC E ecografia nello stesso lavoro e' quasi sempre il
    modo di non trovare niente. Chi le vuole tutte e due davvero aggiunge due
    blocchi, che e' un gesto esplicito."""
    st.caption(
        "Each modality adds its MeSH descriptor, full name, abbreviation and "
        "British spelling. If you pick several, they are joined by **OR**."
    )

    stamp = st.session_state.get("mod_gen", 0)
    picked = st.multiselect(
        "Modalities", md.covered(), key=f"mod_picked_{stamp}",
        format_func=lambda n: f"{md.group_of(n)} › {n}",
        placeholder="Choose the imaging modalities…")

    mode_key = st.radio(
        "Terms", list(md.MODES), horizontal=True, key="mod_mode",
        format_func=lambda k: md.MODES[k])

    if picked:
        with st.container(height=150, border=True):
            for name in picked:
                st.caption(f"**{name}** → `{md.fragment(name, mode_key)}`")

    targets = ["A new block, joined with AND"] + [
        f"Into {qb_block_name(n, b)}" for n, b in enumerate(blocks, 1)]
    target = st.selectbox("Where do they go", targets,
                          key=f"mod_target_{len(blocks)}_{stamp}")

    if st.button(f"Add {len(picked)} modalit{'y' if len(picked) == 1 else 'ies'}",
                 disabled=not picked, key="mod_add", type="primary"):
        # `raw`: sono gia' in sintassi PubMed, e una per riga invece di una riga
        # sola con tutto dentro - cosi' si vede quale modalita' e' quale e se ne
        # puo' togliere una senza rifare il blocco
        terms = [qb_new_term(md.fragment(name, mode_key), "raw") for name in picked]
        if target == targets[0]:
            blocks.append(qb_new_block(join="AND", terms=terms,
                                       label="Imaging modality"))
        else:
            blocks[targets.index(target) - 1]["terms"].extend(terms)
        st.session_state.mod_gen = stamp + 1
        st.rerun()


def search_builder() -> str:
    """Il compositore. Ritorna la stringa di ricerca che ne esce."""
    blocks = qb_state()

    st.caption(
        "**One block per concept**, for example the disease, the modality, the "
        "finding. The kind of publication is not a block: set it in the "
        "filters below. Inside a block, write the concept in each of the ways "
        "papers write it. These lines are joined by **OR**. The blocks are "
        "joined by **AND**. The query shown below is the one PubMed receives."
    )

    to_drop: int | None = None
    for n, block in enumerate(blocks, 1):
        with st.container(border=True):
            head_op, head_name, head_del = st.columns([1, 4, 0.6])
            if n == 1:
                head_op.caption("")
            else:
                block["join"] = head_op.selectbox(
                    "Joined by", qb.OPERATORS,
                    index=qb.OPERATORS.index(block.get("join", "AND")),
                    key=f"qbj_{block['id']}", label_visibility="collapsed")
            block["label"] = head_name.text_input(
                "Block name", value=block.get("label", ""),
                key=f"qbl_{block['id']}", label_visibility="collapsed",
                placeholder=f"Block {n} (optional name)")
            head_del.write("")
            if head_del.button("🗑", key=f"qbd_{block['id']}",
                               disabled=len(blocks) == 1,
                               help="Remove this block"):
                to_drop = n - 1

            drop_term: int | None = None
            for m, term in enumerate(block["terms"]):
                c_text, c_field, c_del = st.columns([4, 1.6, 0.6])
                term["text"] = c_text.text_input(
                    "Term", value=term.get("text", ""),
                    key=f"qbt_{block['id']}_{term['id']}",
                    label_visibility="collapsed",
                    placeholder="one wording of this concept")
                term["field"] = c_field.selectbox(
                    "Field", list(qb.FIELDS),
                    index=list(qb.FIELDS).index(term.get("field", "tiab")),
                    format_func=lambda k: qb.FIELD_LABELS[k],
                    key=f"qbf_{block['id']}_{term['id']}",
                    label_visibility="collapsed")
                c_del.write("")
                if c_del.button("✕", key=f"qbx_{block['id']}_{term['id']}",
                                disabled=len(block["terms"]) == 1,
                                help="Remove this term"):
                    drop_term = m
            if drop_term is not None:
                block["terms"].pop(drop_term)
                st.rerun()

            b_add, b_inner, b_prev = st.columns([1.2, 1.2, 3])
            if b_add.button("＋ Another wording", key=f"qba_{block['id']}",
                            width="stretch",
                            help="Another way of writing the same concept, for example "
                                 "“myocardial infarction”, “MI”, “heart "
                                 "attack”. The lines are joined by OR, so a paper "
                                 "matching any one of them is found."):
                block["terms"].append(qb_new_term())
                st.rerun()
            block["inner"] = b_inner.selectbox(
                "Joined by", ["OR", "AND", "NOT"],
                index=["OR", "AND", "NOT"].index(block.get("inner", "OR")),
                key=f"qbi_{block['id']}", label_visibility="collapsed",
                help="How the lines inside this block are joined. Use OR for a "
                     "list of synonyms.")
            rendered = qb.render_block(qb_model([block])[0])
            b_prev.caption(f"`{rendered}`" if rendered else "empty (no terms yet)")

    if to_drop is not None:
        blocks.pop(to_drop)
        st.rerun()

    add_col, clear_col, _ = st.columns([1, 1, 3])
    if add_col.button("＋ Add a block", width="stretch", key="qb_add_block"):
        blocks.append(qb_new_block())
        st.rerun()
    if clear_col.button("↺ Start over", width="stretch", key="qb_reset"):
        st.session_state.qb_blocks = [qb_new_block()]
        st.rerun()

    with st.expander("⌗ Terms from the Radiopaedia headings", expanded=False):
        strategy_panel(blocks)

    with st.expander("🩻 Imaging modalities", expanded=False):
        modality_panel(blocks)

    for msg in qb.problems(qb_model(blocks)):
        if not msg.startswith("No terms yet"):
            st.warning(msg)

    return qb.compose(qb_model(blocks))


# Le quattro schede sono definite qui sotto come frammenti e disegnate in fondo
# al file. Un clic dentro una scheda fa rigirare solo quella: senza, ogni
# spunta rieseguiva tutto il file e ridisegnava la barra laterale e le altre
# tre schede, circa un secondo per clic su un archivio di quattromila
# articoli. Un `st.rerun()` dentro una scheda fa ancora un giro intero, ed e'
# giusto: lo chiamano le azioni che cambiano l'archivio, e i numeri della barra
# laterale e delle altre schede devono seguirle.


# ---------------------------------------------------------------------------
# TAB 1 - ricerca
# ---------------------------------------------------------------------------

@st.fragment
def search_tab() -> None:
    keep_defaults(SEARCH_TAB_KEYS)
    def run_search(label: str, query: str, *, highlight_terms: str,
                   limit: int, skip: str) -> list[dict] | None:
        """Manda una query a PubMed e mette i record fra i risultati.

        La usano la ricerca normale e "Fetch recent literature": cambia come
        nasce la query, non quello che le succede dopo. `label` e' la riga che
        resta nello storico, `highlight_terms` le parole da evidenziare nei
        risultati (nessuna, per una ricerca fatta di ISSN). Ritorna i record
        nuovi, o None se la ricerca non e' andata."""
        email = (settings.get("ncbi_email") or "").strip()
        if not email:
            st.error("Set the NCBI email in the sidebar first (⚙️ Settings).")
            return None
        api_key = (settings.get("ncbi_api_key") or "").strip()
        params = pubmed.ncbi_params(email, api_key)
        params["_pause"] = pubmed.pause(api_key)
        session = http_session()
        status = st.status("Querying PubMed...", expanded=True)
        try:
            already = db.known_pmids(skip)
            unmatched: list[str] = []
            total, pmids, n_excluded = pubmed.esearch(
                query, session, params,
                max_results=limit,
                exclude=already,
                progress=lambda n, exc, seen, tot: status.write(
                    f"PMIDs examined {seen}/{tot}: {n} new, {exc} already known and skipped"),
                warn=unmatched.extend)
            if unmatched:
                # non e' un errore: PubMed le nomina solo quando il totale e'
                # zero, e le stringhe pubblicate dell'ISSG ne contengono
                status.write(
                    "ℹ️ Nothing in PubMed matches these pieces of the query: "
                    + ", ".join(f"`{u}`" for u in dict.fromkeys(unmatched))
                    + ". The rest of the query ran normally.")
            status.write(
                f"PubMed reports **{total}** results. "
                f"Skipped **{n_excluded}** already in the database, "
                f"downloading **{len(pmids)}**."
            )
            if total > pubmed.ESEARCH_CAP:
                status.write(
                    f"⚠️ PubMed returns at most {pubmed.ESEARCH_CAP:,} "
                    "records per search, the most recent first. To get the "
                    "older ones, narrow the search, for example by years.")
            records = pubmed.efetch(
                pmids, session, params,
                progress=lambda n, t: status.write(f"Details downloaded: {n}/{t}"))
            status.write(f"Complete records: {len(records)}.")

            if use_s2 and records:
                status.write("Fetching citation data from Semantic Scholar...")
                try:
                    enrich = s2.enrich(
                        [r["pmid"] for r in records],
                        api_key=(settings.get("s2_api_key") or "").strip(),
                        progress=lambda n, t: status.write(f"Semantic Scholar: {n}/{t}"))
                except s2.SemanticScholarError as exc:
                    enrich = {}
                    status.write(f"⚠️ Semantic Scholar unavailable: {exc}")
                for rec in records:
                    rec.update(enrich.get(rec["pmid"], {}))
                found = sum(1 for v in enrich.values() if v.get("s2_paper_id"))
                status.write(
                    f"Citation data found for {found} of {len(enrich)} records.")

            if use_oa and records:
                email = unpaywall_email()
                with_doi = {clean(r.get("doi")).lower(): r for r in records
                            if clean(r.get("doi"))}
                if not email:
                    status.write("⚠️ Unpaywall skipped: no email set in the "
                                 "sidebar settings.")
                elif not with_doi:
                    status.write("No DOIs among these records: nothing to "
                                 "ask Unpaywall.")
                else:
                    status.write(f"Asking Unpaywall about {len(with_doi)} DOIs…")
                    oa = upw.enrich(
                        list(with_doi), email, session,
                        progress=lambda n, t: status.write(f"Unpaywall: {n}/{t}"))
                    for doi, found in oa.items():
                        rec = with_doi.get(doi)
                        if rec:
                            rec["oa_status"] = found["oa_status"]
                            rec["oa_url"] = found["oa_url"]
                            rec["oa_fetched_at"] = found["oa_fetched_at"]
                    free = sum(1 for v in oa.values()
                               if v["oa_status"] not in ("closed", "unknown"))
                    status.write(f"{free} of {len(oa)} have a free full text.")

            for rec in records:
                rec["source_query"] = query

            search_id = db.log_search(label, query, total, len(records))
            st.session_state.search_results = records
            # i termini della ricerca FATTA, non di quella che si sta
            # scrivendo: sono loro che si evidenziano nei risultati
            st.session_state.search_terms_used = highlight_terms
            st.session_state.search_id = search_id
            st.session_state.search_total = total
            st.session_state.search_excluded = n_excluded
            st.session_state.search_selection = {}
            st.session_state.search_gen = st.session_state.get("search_gen", 0) + 1
            status.update(
                label=(f"Search complete: {len(records)} new records."
                       if records else
                       f"No new results: all {n_excluded} matches found are "
                       f"already in the database."),
                state="complete", expanded=not records)
            return records
        except (pubmed.PubMedError, requests.RequestException) as exc:
            status.update(label="Search failed", state="error", expanded=True)
            st.error(f"Error during the search: {exc}")
            return None

    # ----------------------------------------------------------------------
    # la letteratura recente di un gruppo editoriale
    # ----------------------------------------------------------------------
    # Non parte dai termini ma dalle riviste: quelle del gruppo, prese dal file
    # SCImago. Quello che trova si salva da solo in una lista, perche' e' una
    # rassegna da sfogliare nello screening e non una ricerca da cui scegliere.
    # Il pannello si apre col pulsante: chi viene per cercare non lo vede.
    if st.button("📰 Fetch recent literature", key="recent_open_btn",
                 help="Fetches the recent reviews, meta-analyses and guidelines "
                      "from the journals of a Radiopaedia editorial group. "
                      "Click to choose the group and the list they are saved in."):
        st.session_state.recent_open = not st.session_state.get("recent_open", False)

    fetch_recent = False
    if st.session_state.get("recent_open", False):
        with st.container(border=True):
            g_pick, g_list, g_go = st.columns([1, 1.6, 1], vertical_alignment="bottom")
            group = editorial.GROUPS[g_pick.selectbox(
                "Editorial group", list(editorial.GROUPS), key="recent_group",
                format_func=lambda k: editorial.GROUPS[k].label,
                help="A Radiopaedia editorial group. Each group has its own set of "
                     "journals, taken from the SCImago file: the Q1 journals of "
                     "its categories, and the journals of its field found by "
                     "title.")]
            # la lista del gruppo per prima, cosi' chi non sceglie finisce li'
            other_lists = [r["name"] for r in db.list_lists()
                           if r["name"] != group.list_name]
            recent_list = g_list.selectbox(
                "Save in list", [group.list_name] + other_lists + [NEW_LIST],
                key=f"recent_list_{group.key}",
                help="The reading list the articles are added to. The first "
                     "choice is the list of the group, created at the first run.")
            if recent_list == NEW_LIST:
                recent_list = " ".join(st.text_input(
                    "New list name", key="recent_list_new",
                    label_visibility="collapsed",
                    placeholder="Name of the new list").split())
            last_run = (settings.get(editorial.setting_key(group)) or "")[:10]
            recent_since = editorial.since_for(last_run)
            fetch_recent = g_go.button(
                "Fetch", key="recent_go", type="primary", width="stretch",
                disabled=not recent_list,
                help="Searches the journals of the group for reviews, "
                     "meta-analyses and guidelines in English. The first run "
                     f"covers the last {editorial.FIRST_RUN_DAYS} days. Later runs "
                     f"start {editorial.OVERLAP_DAYS} days before the previous "
                     "run, because PubMed adds the publication type to some "
                     "records a few days after they appear.")
            st.caption(
                (f"Last run: {last_run}. " if last_run else "Never run. ")
                + f"Fetches what PubMed added since {recent_since:%Y-%m-%d}"
                + (f" and saves it in the list “{recent_list}”."
                   if recent_list else ". Give the new list a name."))

    if fetch_recent:
        recent_query = editorial.build_query(group, db.journal_rows(), recent_since)
        if not recent_query:
            st.error("No journals found for this group. Open 📊 Journal metrics "
                     "in the sidebar and reload the SCImago file.")
        else:
            got = run_search(
                f"Recent literature: {group.label}, since {recent_since:%Y-%m-%d}",
                recent_query, highlight_terms="", limit=pubmed.ESEARCH_CAP,
                skip="db")
            if got is not None:
                added, _, _ = db.insert_articles(got)
                list_id = db.create_list(
                    recent_list, "Filled by Fetch recent literature")
                if list_id is None:
                    list_id = next(r["id"] for r in db.list_lists()
                                   if r["name"] == recent_list)
                in_list = db.add_to_list(
                    list_id, [r["pmid"] for r in got],
                    note=f"fetched {date.today():%Y-%m-%d}")
                db.bump_search_saved(st.session_state.get("search_id"), added)
                # La data si scrive solo a ricerca riuscita: se PubMed non
                # risponde, la prossima volta si riparte dallo stesso giorno.
                db.save_settings(
                    {editorial.setting_key(group): date.today().isoformat()})
                st.session_state.settings = db.get_settings()
                st.success(
                    f"{added} article(s) saved in the archive, {in_list} added "
                    f"to the list “{recent_list}”. Screen them in the "
                    "Screening tab, with that list selected under In list.")

    how = st.segmented_control(
        "How to search", ["✎ One line", "⛁ Blocks"], default="✎ One line",
        key="search_how", label_visibility="collapsed",
        help="One line takes PubMed syntax as you write it. Blocks builds the "
             "query one concept at a time (synonyms in OR, concepts in AND) "
             "and can turn the headings of a Radiopaedia article into terms.")

    if how == "⛁ Blocks":
        terms = search_builder()
        if terms:
            st.caption("The search terms this builds:")
            st.code(terms, language="text")
    else:
        terms = st.text_input(
            "Search terms",
            key="search_terms",
            placeholder='e.g. "Joubert syndrome" OR "molar tooth sign"',
            help="Accepts native PubMed syntax (AND/OR/NOT, [Title/Abstract], [MeSH Terms]...).",
        )

    # I controlli si disegnano solo in "Custom". Streamlit butta via lo stato
    # dei widget che non disegna, ma i valori `sf_*` vengono riscritti in
    # sessione a ogni giro (vedi `_defaults`), quindi chi torna a "Custom"
    # ritrova quello che aveva lasciato.
    with st.container(horizontal=True, vertical_alignment="center"):
        mode = st.segmented_control(
            "Filters", list(SEARCH_MODES), key="sf_mode", required=True,
            format_func=SEARCH_MODES.get, label_visibility="collapsed")
        if mode == "reviews":
            with st.popover("?", help="What Recent reviews filters"):
                st.markdown(reviews_help())
    filters_now = effective_filters(st.session_state)

    # I titoli che Radiopaedia chiede per un tipo di articolo, come filtro. Sono
    # le stesse strategie del pannello nei blocchi, ma qui valgono anche per la
    # ricerca su una riga: i titoli scelti vanno in OR fra loro e il gruppo in
    # AND col resto. La riga e' chiusa finche' non la si apre; il numero sul
    # pulsante dice quanti titoli sono nella query anche da chiusa.
    heading_clause = ""
    if mode != "open":
        n_headings = len(st.session_state.hd_picked)
        if st.button(
                "⌗ Radiopaedia headings"
                + (f" ({n_headings})" if n_headings else ""), key="hd_open_btn",
                help="Limits the search to the topics of the headings "
                     "Radiopaedia asks for in an article, for example "
                     "Epidemiology or Treatment and prognosis. Each heading "
                     "adds its MeSH terms and its title and abstract words."):
            st.session_state.hd_open = not st.session_state.hd_open
        if st.session_state.hd_open:
            with st.container(border=True):
                try:
                    kinds = sx.profile_labels()
                except sx.StructureError as exc:
                    kinds = {}
                    st.warning(str(exc))
                if kinds:
                    h_kind, h_terms = st.columns([1.4, 2], vertical_alignment="bottom")
                    kind = h_kind.selectbox(
                        "Kind of article", list(kinds), key="hd_profile",
                        format_func=lambda n: kinds[n],
                        on_change=on_heading_profile,
                        help="The headings offered are the ones Radiopaedia "
                             "asks for in this kind of article. Changing it "
                             "clears the headings chosen.")
                    h_terms.radio(
                        "Terms", list(stg.MODES), key="hd_mode", horizontal=True,
                        format_func=lambda k: stg.MODES[k],
                        help="MeSH terms find only the records NLM has "
                             "indexed. Keywords are words in the title and "
                             "abstract, and also find recent records.")
                    st.multiselect(
                        "Headings",
                        [name for name, _ in stg.suggest(
                            [r.title for r in sx.rows_for(kind)])],
                        key="hd_picked",
                        placeholder="Choose headings (several are joined by OR)")
                    chosen = stg.suggest(st.session_state.hd_picked,
                                         st.session_state.hd_mode)
                    if chosen:
                        with st.container(height=150, border=True):
                            for name, frag in chosen:
                                st.caption(f"**{name}** → `{frag}`")
        heading_clause = stg.clause(st.session_state.hd_picked,
                                    st.session_state.hd_mode)
        if heading_clause and not st.session_state.hd_open:
            st.caption("Headings in the query: "
                       + ", ".join(st.session_state.hd_picked) + ".")

    if mode == "custom":
        with st.container(border=True):
            # I gruppi sono quelli della colonna dei filtri di PubMed, nello
            # stesso ordine. Dentro un gruppo le scelte vanno in OR, i gruppi
            # fra loro in AND.
            d_by, d_a, d_b = st.columns([2, 1, 1], vertical_alignment="bottom")
            date_by = d_by.radio(
                "Publication date", list(DATE_METHODS), key="sf_date_by",
                format_func=DATE_METHODS.get, horizontal=True)
            if date_by == "range":
                d_a.number_input("From year", 1800, TODAY.year, step=1,
                                 key="sf_year_from")
                d_b.number_input("To year", 1800, TODAY.year, step=1,
                                 key="sf_year_to")
            else:
                # zero e' un valore legittimo e vuol dire "nessun limite di
                # data". Prima il minimo era 1: non c'era modo di dire "tutta
                # la letteratura", e cinquant'anni sembravano quello senza
                # esserlo.
                d_a.number_input(
                    "Last N years", 0, 100, step=1, key="sf_years",
                    help="0 = no date limit at all.")

            st.caption("Text availability and article attribute")
            t1, t2, t3, t4 = st.columns(4)
            t1.checkbox("Abstract", key="sf_abstract",
                        help="Only records that have an abstract.")
            t2.checkbox("Free full text", key="sf_freefulltext",
                        help="Only records that link to a full text free to read.")
            t3.checkbox("Full text", key="sf_fulltext",
                        help="Only records that link to a full text, free or not.")
            t4.checkbox("Associated data", key="sf_data",
                        help="Only records that link to data, for example a "
                             "data repository or a trial registry.")

            l_lang, l_age = st.columns(2)
            l_lang.multiselect(
                "Article language", pubmed.LANGUAGE_LABELS, key="sf_languages",
                placeholder="Any language (several are joined by OR)")
            l_age.multiselect(
                "Age", pubmed.AGE_LABELS, key="sf_ages",
                placeholder="Any age (several are joined by OR)",
                help="The age groups of the people studied." + MESH_WARNING)

            st.caption("Species, sex and other")
            # Non `s1..s4`: `s2` e' il modulo di Semantic Scholar, e una colonna
            # con quel nome lo copriva per il resto del giro.
            sp1, sp2, sp3, sp4 = st.columns(4)
            sp1.checkbox("Humans", key="sf_humans",
                        help="Leaves out what is indexed as an animal study and "
                             "not as a human one. Papers too recent to be "
                             "indexed yet are kept. With Other animals also "
                             "ticked, PubMed's own two filters are used, joined "
                             "by OR, and papers not yet indexed are left out.")
            sp2.checkbox("Other animals", key="sf_animals",
                        help="Only records indexed as animal studies." + MESH_WARNING)
            sp3.checkbox("Female", key="sf_female",
                        help="Only records indexed with female subjects." + MESH_WARNING)
            sp4.checkbox("Male", key="sf_male",
                        help="Only records indexed with male subjects." + MESH_WARNING)
            o1, o2, _, _ = st.columns(4)
            o1.checkbox("Exclude preprints", key="sf_nopreprints")
            o2.checkbox("MEDLINE", key="sf_medline",
                        help="Only records with the status MEDLINE, that is, "
                             "indexed by NLM." + MESH_WARNING)

            type_by = st.radio(
                "Kind of publication", list(TYPE_METHODS), key="sf_type_by",
                format_func=TYPE_METHODS.get, horizontal=True,
                help="One way or the other, not both. NLM publication types are "
                     "the labels an indexer gave the record; ISSG filters catch a "
                     "kind of publication by the words the paper uses. Combined "
                     "they would be joined with AND and keep far fewer papers "
                     "than either.")
            if type_by == "pt":
                st.multiselect(
                    "Article type", pubmed.DEFAULT_TYPE_LABELS, key="sf_types",
                    label_visibility="collapsed",
                    placeholder="Choose publication types (several are joined by OR)",
                    help="PubMed's own publication types, as NLM assigned them.")
            elif type_by == "issg":
                # I filtri ISSG non dicono DI COSA parla un lavoro, dicono CHE
                # GENERE di lavoro e': sono le stringhe con cui gli information
                # specialist intercettano linee guida e revisioni sistematiche.
                issg_picked = st.multiselect(
                    "Study design filters (ISSG)", list(issg.LABELS.values()),
                    key="sf_issg", label_visibility="collapsed",
                    placeholder="Choose ISSG filters (several are joined by OR)",
                    help="Published search filters from the InterTASC Information "
                         "Specialists' Sub-Group. They catch a kind of publication "
                         "by the words it uses, not by a subject.")
                for label in issg_picked:
                    st.caption(f"· **{label}**: {issg.FILTERS[issg.BY_LABEL[label]][2]}")

            st.caption(describe_filters(filters_now))

    issg_clause = issg.clause(filters_now["issg"])
    query_preview = ""
    if terms.strip():
        try:
            query_preview = pubmed.build_query(
                terms, type_labels=filters_now["types"], english=False,
                filters=[issg_clause, heading_clause],
                **{k: v for k, v in filters_now.items()
                   if k not in ("types", "issg")})
        except pubmed.PubMedError as exc:
            st.warning(str(exc))
        else:
            # con un filtro ISSG dentro la query supera i tremila caratteri:
            # stamparla per intero seppellirebbe il pulsante di ricerca
            if len(query_preview) > 700:
                with st.expander(f"The query PubMed receives "
                                 f"({len(query_preview):,} characters)",
                                 expanded=False):
                    st.code(query_preview, language="text")
            else:
                st.code(query_preview, language="text")

    if st.button("🔎 Search PubMed", type="primary", disabled=not query_preview):
        run_search(terms.strip(), query_preview, highlight_terms=terms.strip(),
                   limit=int(max_results) or pubmed.ESEARCH_CAP, skip=exclude_mode)

    results = st.session_state.get("search_results") or []

    if results:
        in_db, screened = db.classify_pmids([r["pmid"] for r in results])
        selection = st.session_state.setdefault("search_selection", {})
        gen = st.session_state.get("search_gen", 0)

        # Lo stato di ogni record - nuovo, gia' in archivio, gia' screenato -
        # si sa prima di disegnare: serve alle faccette, che ci filtrano sopra.
        status_by_pmid = {
            rec["pmid"]: ("screened" if rec["pmid"] in screened else
                          "in archive" if rec["pmid"] in in_db else "new")
            for rec in results
        }

        st.divider()
        head_l, head_r = st.columns([2, 1])
        with head_l:
            st.subheader(
                f"{len(results)} records downloaded "
                f"(out of {st.session_state.get('search_total', len(results))} found)")
            n_excluded = st.session_state.get("search_excluded", 0)
            if n_excluded:
                st.caption(f"🚫 {n_excluded} results excluded: already in the database.")
        with head_r:
            sort_label = st.selectbox("Sort by", list(SORT_OPTIONS), index=0)
        sort_col = SORT_OPTIONS[sort_label]

        # Le metriche delle riviste di QUESTA pagina di risultati, in due query.
        # I record non sono ancora in archivio, quindi un aggancio salvato non
        # ce l'hanno: si chiedono le poche riviste che compaiono qui.
        def journal_key(rec) -> str:
            return jr.norm_title(rec.get("journal_title") or rec.get("journal") or "")

        by_issn, by_title = db.metrics_for(
            [i for rec in results for i in (rec.get("issn") or "").split("; ")],
            [journal_key(rec) for rec in results])

        def metric_of(rec):
            for issn in (rec.get("issn") or "").split("; "):
                if issn in by_issn:
                    return by_issn[issn]
            return by_title.get(journal_key(rec))

        shown = results_filters(results, metric_of, status_by_pmid, gen)

        def sort_key(rec):
            if sort_col == "_sjr":
                metric = metric_of(rec)
                v = metric["sjr"] if metric is not None else None
            else:
                v = rec.get(sort_col)
            try:
                return -float(v)
            except (TypeError, ValueError):
                return float("inf")  # i record senza dato finiscono in fondo

        ordered = sorted(shown, key=sort_key)
        if len(shown) != len(results):
            st.caption(f"**Showing {len(shown)} of {len(results)}**. "
                       f"{len(results) - len(shown)} hidden by the filters above.")

        rows = []
        for rec in ordered:
            pmid = rec["pmid"]
            state = status_by_pmid[pmid]
            metric = metric_of(rec)
            rows.append({
                "Save": selection.get(pmid, state == "new"),
                "Status": state,
                "PMID": pmid,
                "Q": (metric["quartile"] if metric is not None else None) or "",
                "SJR": number(metric["sjr"]) if metric is not None else None,
                "Year": clean(rec.get("year")),
                "Cites": rec.get("citation_count"),
                "Infl.": rec.get("influential_citations"),
                "Cites/yr": rec.get("citations_per_year"),
                "Title": clean(rec.get("title")),
                "Journal": clean(rec.get("journal")),
                "Type": clean(rec.get("pub_types")),
                "PubMed": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "LibKey": libkey_url(pmid) or "",
            })
        table = pd.DataFrame(rows)

        b1, b2, b3, b4, b5, b6 = st.columns([1, 1, 1, 1.4, 1.6, 1.5],
                                            vertical_alignment="center")
        if b1.button("Select all"):
            st.session_state.search_selection = {r["PMID"]: True for r in rows}
            st.session_state.search_gen = gen + 1
            st.rerun()
        if b2.button("Clear selection"):
            st.session_state.search_selection = {r["PMID"]: False for r in rows}
            st.session_state.search_gen = gen + 1
            st.rerun()
        if b3.button("New ones only"):
            st.session_state.search_selection = {
                r["PMID"]: r["Status"] == "new" for r in rows}
            st.session_state.search_gen = gen + 1
            st.rerun()
        with b4:
            view = st.radio("View", ["Cards", "Table"], horizontal=True,
                            key="search_view", label_visibility="collapsed")
        with b5:
            per_page = st.selectbox(
                "Cards per page", SEARCH_PAGE_SIZE_OPTIONS, index=1,
                key="search_per_page", label_visibility="collapsed",
                format_func=lambda n: f"{n} per page",
                disabled=view == "Table")
        b6.toggle("Abstracts open", key="abs_open_search",
                  on_change=on_abstracts_open, args=("abs_open_search",),
                  disabled=view == "Table",
                  help="Show every abstract already open, to read down the "
                       "page without a click per record. The same choice "
                       "applies to Screening, and is remembered.")
        search_rx = highlight.pattern(highlight.terms_of(
            st.session_state.get("search_terms_used", "")))

        if view == "Table":
            edited = st.data_editor(
                table,
                key=f"results_editor_{gen}_{sort_col}",
                hide_index=True,
                width="stretch",
                height=520,
                disabled=[c for c in table.columns if c != "Save"],
                column_config={
                    "Save": st.column_config.CheckboxColumn("Save", width="small"),
                    "Status": st.column_config.TextColumn("Status", width="small"),
                    "PMID": st.column_config.TextColumn("PMID", width="small"),
                    "Q": st.column_config.TextColumn(
                        "Q", width="small",
                        help="SCImago's best quartile for the journal"),
                    "SJR": st.column_config.NumberColumn("SJR", width="small",
                                                         format="%.2f"),
                    "Year": st.column_config.TextColumn("Year", width="small"),
                    "Cites": st.column_config.NumberColumn("Cites", width="small",
                                                           help="Total citations (Semantic Scholar)"),
                    "Infl.": st.column_config.NumberColumn("Infl.", width="small",
                                                           help="Influential citations (Semantic Scholar)"),
                    "Cites/yr": st.column_config.NumberColumn("Cites/yr", width="small",
                                                              format="%.2f"),
                    "Title": st.column_config.TextColumn("Title", width="large"),
                    "Journal": st.column_config.TextColumn("Journal", width="medium"),
                    "Type": st.column_config.TextColumn("Type", width="medium"),
                    "PubMed": st.column_config.LinkColumn("PubMed", display_text="open",
                                                          width="small"),
                    "LibKey": st.column_config.LinkColumn("LibKey", display_text="full text",
                                                          width="small"),
                },
            )

            for pmid, keep in zip(edited["PMID"], edited["Save"]):
                selection[str(pmid)] = bool(keep)
        else:
            # stessa resa della scheda Screening: e' li' che si legge davvero, e
            # scorrere una tabella senza abstract non dice quasi niente
            n_pages = max(1, -(-len(ordered) // per_page))
            fingerprint = (gen, sort_col, per_page)
            if st.session_state.get("search_fingerprint") != fingerprint:
                st.session_state.search_fingerprint = fingerprint
                st.session_state.search_page = 1
            page = min(max(1, st.session_state.get("search_page", 1)), n_pages)
            st.session_state.search_page = page
            st.caption(f"Page {page} of {n_pages}, showing "
                       f"{min(per_page, len(ordered) - (page - 1) * per_page)} "
                       f"of {len(ordered)} records.")
            if n_pages > 1:
                render_pager(n_pages, "search_top", compact=True,
                             state_key="search_page")

            for rec in ordered[(page - 1) * per_page: page * per_page]:
                pmid = rec["pmid"]
                state = status_by_pmid.get(pmid, "new")
                # la spunta di default finisce subito nella selezione, altrimenti
                # il contatore "Save N selected" direbbe zero senza un click
                checked = selection.setdefault(pmid, state == "new")

                with st.container(border=True):
                    col_meta, col_actions = st.columns([5, 1.3])

                    with col_meta:
                        mark = {"new": "🆕 ", "in archive": "📥 ",
                                "screened": "✅ "}[state]
                        st.markdown(
                            f'<div class="art-title">{mark}'
                            f'{highlight.mark(clean(rec.get("title")) or "No title available", search_rx)}</div>',
                            unsafe_allow_html=True,
                        )
                        meta_bits = [b for b in [
                            html.escape(clean(rec.get("authors"))),
                            html.escape(clean(rec.get("journal"))),
                            html.escape(clean(rec.get("pub_date")) or clean(rec.get("year"))),
                            f"PMID {pmid}",
                        ] if b]
                        st.markdown(f'<div class="art-meta">{" · ".join(meta_bits)}</div>',
                                    unsafe_allow_html=True)

                        badges = journal_badges(metric_of(rec))
                        free_badge = oa_badge(rec.get("oa_status"))
                        if free_badge:
                            badges.append(free_badge)
                        badges.extend(html.escape(t)
                                      for t in useful_types(rec.get("pub_types")))
                        cites = citation_badge(rec.get("citation_count"),
                                               rec.get("influential_citations"),
                                               rec.get("citations_per_year"))
                        if cites:
                            badges.append(cites)
                        if badges:
                            st.markdown(
                                '<div class="art-badges">'
                                + "".join(b if b.startswith("<span") else f"<span>{b}</span>"
                                          for b in badges)
                                + "</div>",
                                unsafe_allow_html=True,
                            )

                        links = [f"[PubMed](https://pubmed.ncbi.nlm.nih.gov/{pmid}/)"]
                        lk = libkey_url(pmid)
                        if lk:
                            links.append(f"[🔓 LibKey full text]({lk})")
                        doi = clean(rec.get("doi"))
                        if doi:
                            links.append(f"[DOI](https://doi.org/{doi})")
                        free = clean(rec.get("oa_url")) or clean(rec.get("oa_pdf_url"))
                        if free:
                            links.append(f"[Free full text]({free})")
                        st.markdown(" · ".join(links))

                    with col_actions:
                        # la chiave porta dentro `gen`: i pulsanti Select all /
                        # Clear selection lo incrementano, e cosi' le spunte si
                        # ricreano invece di restare ferme sul valore vecchio
                        pick_key = f"pick_{gen}_{pmid}"
                        st.checkbox("💾 Save", value=checked, key=pick_key,
                                    on_change=on_pick, args=(pmid, pick_key))
                        st.caption(state)

                    with st.expander("Abstract", expanded=st.session_state.abs_open_search):
                        st.html(abstract_html(rec.get("abstract"), search_rx))

            if n_pages > 1:
                st.divider()
                render_pager(n_pages, "search_bottom", compact=False,
                             state_key="search_page")

        # Solo quello che si vede. Col filtro per quartile acceso, una spunta
        # lasciata su un record ora nascosto non deve finire in un salvataggio
        # che nessuno ha piu' davanti agli occhi.
        visible = [r for r in ordered if selection.get(r["pmid"])]
        n_selected = len(visible)
        save_col, list_col, draft_col = st.columns([1.2, 2, 2])
        with save_col:
            if st.button(f"💾 Save {n_selected} selected", type="primary",
                         disabled=n_selected == 0):
                chosen = visible
                added, skipped_screened, already = db.insert_articles(chosen)
                db.bump_search_saved(st.session_state.get("search_id"), added)
                st.success(
                    f"Saved {added} new articles "
                    f"({already} already in the archive, {skipped_screened} read and "
                    f"discarded in the past). Go to the Screening tab."
                )
        with list_col:
            # Una lista non e' uno stato dell'articolo: e' un raccoglitore che
            # decidi tu, e lo stesso lavoro puo' stare in piu' liste. Per finirci
            # deve pero' essere in archivio, altrimenti la lista conterrebbe un
            # PMID di cui non si sa piu' niente: si salva e si mette in lista in
            # un gesto solo.
            existing = db.list_lists()
            names = [r["name"] for r in existing]
            NEW = NEW_LIST
            target_name = st.selectbox(
                "Add to list", [NEW] + names, index=None,
                label_visibility="collapsed",
                placeholder="Add selected to a list…", key="search_list_pick")
            fresh_name = ""
            if target_name == NEW:
                fresh_name = st.text_input(
                    "New list name", key="search_list_new",
                    label_visibility="collapsed", placeholder="Name of the new list")
            if target_name is not None and st.button(
                    f"🗂 Add {n_selected} to list", disabled=n_selected == 0,
                    key="search_list_add", width="stretch"):
                if target_name == NEW:
                    list_id = db.create_list(fresh_name)
                    if list_id is None:
                        st.error("Give the list a name that no other list has.")
                        list_id = None
                else:
                    list_id = next(r["id"] for r in existing if r["name"] == target_name)
                if list_id is not None:
                    chosen = visible
                    added, _, _ = db.insert_articles(chosen)
                    db.bump_search_saved(st.session_state.get("search_id"), added)
                    n_in = db.add_to_list(list_id, [r["pmid"] for r in chosen],
                                          note="from a search")
                    label = fresh_name if target_name == NEW else target_name
                    st.success(f"{n_in} article(s) added to “{label}” "
                               f"({added} of them new to the archive).")

        with draft_col:
            # la stessa selezione serve due scopi: entrare in coda di screening
            # e diventare bibliografia di un articolo che stai scrivendo
            open_drafts = db.list_drafts()
            if open_drafts:
                target = st.selectbox(
                    "Add to draft", open_drafts, index=None,
                    format_func=lambda r: r["title"], label_visibility="collapsed",
                    placeholder="Add selected to a draft…")
                if target is not None and st.button(
                        f"✍️ Add {n_selected} as references", disabled=n_selected == 0):
                    pmids = [r["pmid"] for r in visible]
                    n_added = db.add_draft_refs(target["id"], pmids, note="from a search")
                    if st.session_state.get("search_id"):
                        db.attach_search(target["id"], st.session_state["search_id"])
                    st.success(f"Added {n_added} reference(s) to “{target['title']}” "
                               f"and attached this search to it.")

        if not libkey_url("0"):
            st.caption("💡 Set the LibKey library ID in the sidebar to get "
                       "direct full-text links.")

    with st.expander("🕘 Recent searches", expanded=False):
        history = db.recent_searches()
        if history:
            st.dataframe(
                pd.DataFrame([dict(r) for r in history])[
                    ["run_at", "terms", "n_found", "n_fetched", "n_saved"]
                ].rename(columns={"run_at": "When", "terms": "Terms",
                                  "n_found": "Found", "n_fetched": "Downloaded",
                                  "n_saved": "Saved"}),
                hide_index=True, width="stretch",
            )
        else:
            st.caption("No searches recorded yet.")


# ---------------------------------------------------------------------------
# TAB 2 - screening
# ---------------------------------------------------------------------------

@st.cache_resource
def screening_bench() -> bench.Bench:
    """Il server del banco, avviato una volta per processo."""
    return bench.start()


def screen_tab() -> None:
    """Lo Screening e' una pagina web servita da `bench.py`, mostrata qui in
    un iframe. Non e' un frammento e non ha widget: Streamlit non rigira
    quando si clicca la' dentro, ed e' il motivo per cui esiste.

    Nell'indirizzo vanno il tema e le misure del testo, che la pagina riceve
    solo all'apertura: quando cambiano l'indirizzo cambia, e l'iframe si
    ricarica da solo. A indirizzo uguale Streamlit lascia l'iframe com'e', e
    la pagina tiene filtri e selezione."""
    stamp = hashlib.sha256("|".join(
        settings.get(k) or "" for k in
        ("title_font_rem", "reading_font_rem", "reading_font")).encode()).hexdigest()[:8]
    try:
        theme_name = st.context.theme.type or "auto"
    except AttributeError:
        theme_name = "auto"
    st.iframe(screening_bench().url(theme_name, stamp), height=BENCH_HEIGHT)


# ---------------------------------------------------------------------------
# TAB 3 - la libreria dei PDF
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False, max_entries=500)
def pubmed_for_pdf(sha256: str, dois: tuple, titles: tuple, article_like: bool) -> dict | None:
    """L'articolo PubMed di un PDF, chiesto una volta per file (la chiave e'
    l'impronta): ogni giro dell'app ridisegna la scheda, e PubMed non va
    richiamato a ogni clic."""
    # Un errore di rete non finisce in cache (st.cache_data non tiene le
    # eccezioni): chi chiama lo prende, e al giro dopo si riprova.
    email = settings["ncbi_email"].strip()
    api_key = (settings.get("ncbi_api_key") or "").strip()
    params = pubmed.ncbi_params(email, api_key)
    params["_pause"] = pubmed.pause(api_key)
    return library.lookup_pubmed(
        {"dois": list(dois), "titles": list(titles), "article_like": article_like},
        http_session(), params)


def adopt_pdf(path: Path, pmid: str, record: dict | None) -> str | None:
    """Porta in libreria un PDF aggiunto. Con `record` l'articolo non e'
    ancora in archivio e ce lo si mette prima, anche se era fra quelli letti
    e scartati: prenderne il PDF e' una decisione di tenerlo."""
    if record is not None and db.article_row(pmid) is None:
        db.unscreen(pmid)
        db.insert_articles([record])
    return attach_pdf(pmid, path=path, source="added", move=True)


def read_pdf(pmid: str, path: Path) -> None:
    """Il PDF nel lettore dell'app, da solo, grande: si legge, si evidenzia,
    si spunta. E' la finestra di studio senza Radiopaedia."""
    missing = study.available()
    if missing:
        st.error(missing)
        return
    study.launch(None, path, settings.get("study_layout") or "lr", pmid=pmid)
    st.toast("The reader opens in a separate window.")


def incoming_pdfs() -> None:
    """I PDF trascinati nella scheda: per ognuno si cerca l'articolo, prima in
    archivio (DOI, PMID, titolo nella prima pagina) e poi su PubMed (DOI, poi
    titolo), come fa Zotero con "Retrieve metadata".

    Il file caricato si scrive in una cartella di passaggio col nome della sua
    impronta: cosi' `identify_pdf` lo apre una volta sola, e a PubMed si chiede
    una volta per file (`pubmed_for_pdf` e' in cache). Quando entra in
    libreria lo si sposta, e dalla cartella di passaggio sparisce."""
    turn = st.session_state.setdefault("incoming_turn", 0)
    uploads = st.file_uploader(
        "📎 Add PDFs (drop them here)", type=["pdf"], accept_multiple_files=True,
        key=f"incoming_{turn}",
        help="Each one is matched to its article by the DOI in the text, or by "
             "its title on PubMed, and renamed after the citation.")
    if not uploads:
        return
    staging = paths.home() / "incoming"
    staging.mkdir(parents=True, exist_ok=True)

    rows = []
    for up in uploads:
        data = up.getvalue()
        if not library.is_pdf(data[:1024]):
            st.error(f"{up.name} is not a PDF.")
            continue
        path = staging / f"{hashlib.sha256(data).hexdigest()[:20]}.pdf"
        if not path.exists():
            path.write_bytes(data)
        stat = path.stat()
        info = identify_pdf(str(path), stat.st_mtime, stat.st_size)
        already = db.pdf_by_sha(info["sha256"])
        rows.append([up.name, path, info, None, "", None, already])

    # in archivio: DOI prima, PMID poi, titolo per ultimo
    ids = db.articles_by_ids([d for r in rows for d in r[2]["dois"]],
                             [p for r in rows for p in r[2]["pmids"]])
    titles = None
    for r in rows:
        info = r[2]
        for doi in info["dois"]:
            if doi in ids:
                r[3], r[4] = ids[doi], f"DOI {doi}"
                break
        if r[3] is None:
            for p in info["pmids"]:
                if p in ids:
                    r[3], r[4] = ids[p], f"PMID {p}"
                    break
        if r[3] is None and info["text"]:
            if titles is None:
                conn = db.get_connection()
                try:
                    titles = {x["pmid"]: x["title"] or "" for x in
                              conn.execute("SELECT pmid, title FROM articles")}
                finally:
                    conn.close()
            r[3] = library.match_title(info["text"], titles)
            r[4] = "title on the first page" if r[3] else ""

    # su PubMed, per quelli che in archivio non ci sono. Senza l'email NCBI
    # non si chiede niente: e' la stessa regola della ricerca.
    to_ask = [r for r in rows if r[3] is None and r[6] is None
              and (r[2]["dois"] or r[2].get("article_like"))
              and (settings.get("ncbi_email") or "").strip()]
    if to_ask:
        with st.spinner(f"Asking PubMed about {len(to_ask)} PDF(s)…"):
            for r in to_ask:
                info = r[2]
                try:
                    hit = pubmed_for_pdf(info["sha256"], tuple(info["dois"]),
                                         tuple(info.get("titles", [])),
                                         bool(info.get("article_like")))
                except (requests.RequestException, pubmed.PubMedError, ValueError):
                    hit = None
                if hit:
                    r[5] = hit["record"]
                    r[3] = str(hit["record"]["pmid"])
                    r[4] = hit["how"]

    def done() -> None:
        # tutto sistemato: si svuota il riquadro dei file, che altrimenti li
        # ripresenterebbe al giro dopo
        if all(r[1].exists() is False or r[6] is not None for r in rows):
            st.session_state.incoming_turn = turn + 1
        st.rerun()

    matched = [r for r in rows if r[3] and r[6] is None]
    if len(matched) > 1 and st.button(
            f"Add all {len(matched)} recognised PDFs", type="primary", key="incoming_all"):
        problems = [f"{name}: {e}" for name, path, _, pm, _, rec, _ in matched
                    if (e := adopt_pdf(path, pm, rec))]
        for msg in problems:
            st.error(msg)
        if not problems:
            st.session_state.incoming_turn = turn + 1
            st.rerun()

    for i, (name, path, info, pmid, how, record, already) in enumerate(rows):
        with st.container(border=True):
            left, right = st.columns([4, 1.3])
            with left:
                st.markdown(f"`{name}`")
                if already is not None:
                    st.caption(f"Already in the library as `{already['filename']}`.")
                elif pmid:
                    rec = record if record is not None else db.article_row(pmid)
                    new = record is not None and db.article_row(pmid) is None
                    st.caption(f"→ **{clean(rec['title'])}** (PMID {pmid}), matched "
                               f"by {how}" + ("; not in the archive yet, it will be "
                                              "added." if new else "."))
                    st.caption(f"Will be saved as `{library.filename_for(rec)}`")
                else:
                    st.caption("No DOI, PMID or title that leads to a PubMed "
                               "article. If it is one, type its PMID.")
                    pmid = st.text_input("PMID", key=f"incoming_pmid_{i}_{turn}",
                                         label_visibility="collapsed",
                                         placeholder="PMID").strip() or None
            with right:
                if already is None:
                    new = record is not None and db.article_row(pmid or "") is None
                    if st.button("Add to archive and library" if new else "Add to library",
                                 key=f"incoming_go_{i}_{turn}", width="stretch",
                                 type="primary", disabled=not pmid):
                        problem = adopt_pdf(path, pmid, record)
                        if problem:
                            st.error(problem)
                        else:
                            done()


@st.fragment
def library_tab() -> None:
    st.subheader("📄 PDF library")
    folder = lib_folder()
    top_l, top_r = st.columns([4, 1])
    top_l.caption(
        f"`{paths.short(folder)}`. One PDF per article, named "
        "*Author Year - Journal - Title [PMID n]*. Articles with a PDF are not "
        "deleted at startup, even when marked read.")
    if top_r.button("Show folder", width="stretch", key="lib_reveal"):
        library.reveal(folder)

    incoming_pdfs()

    st.divider()
    f_text, f_list, f_draft = st.columns([2, 1, 1])
    lib_q = f_text.text_input("Find", placeholder="title, author, PMID…",
                              key="lib_q", label_visibility="collapsed")
    lib_lists = {"Any list": None, **{r["name"]: r["id"] for r in db.list_lists()}}
    lib_list = lib_lists[f_list.selectbox("List", list(lib_lists), key="lib_list",
                                          label_visibility="collapsed")]
    lib_drafts = {"Any draft": None, **{f"Cited in: {r['title']}": r["id"]
                                        for r in db.list_drafts()}}
    lib_draft = lib_drafts[f_draft.selectbox("Draft", list(lib_drafts), key="lib_draft",
                                             label_visibility="collapsed")]
    shelf = db.library_rows(lib_q, lib_list, lib_draft)
    st.caption(f"**{len(shelf)}** PDF(s)")

    for row in shelf:
        pmid = row["pmid"]
        path = folder / row["filename"]
        with st.container(border=True):
            left, right = st.columns([4, 1.3])
            with left:
                st.markdown(f"**{html.escape(clean(row['title']) or row['filename'])}**")
                exists = path.exists()
                st.caption(f"`{row['filename']}`"
                           + ("" if exists else " (**missing from the folder**)")
                           + f" · {row['source'] or ''} · {str(row['added_at'])[:10]}")
                # Le evidenziazioni si rileggono solo se il file e' cambiato
                # dall'ultima volta: di solito costa una `stat`, non l'apertura
                # del PDF.
                if exists:
                    hl.sync(pmid, path)
                marks = db.highlights_for(pmid)
                if marks:
                    n_done = sum(m["done"] for m in marks)
                    with st.expander(f"🖍 {len(marks)} highlight(s) · {n_done} done"):
                        for m in marks:
                            key_hl = f"hl_{m['id']}_{int(m['done'])}"
                            text = m["text"] or m["note"] or "(no text)"
                            st.checkbox(
                                f"p. {m['page']}: {text}", value=m["done"],
                                key=key_hl, on_change=on_highlight_toggle,
                                args=(m["id"], key_hl))
                if row["title"] is not None:
                    wanted = library.filename_for(row)
                    if wanted != row["filename"] and exists and st.button(
                            "Rename to the citation", key=f"lib_ren_{pmid}"):
                        try:
                            os.replace(path, folder / wanted)
                        except OSError as exc:
                            st.error(str(exc))
                        else:
                            db.rename_pdf(pmid, wanted)
                            st.rerun()
            with right:
                if exists and st.button("📖 Read", key=f"lib_open_{pmid}", width="stretch",
                                        type="primary",
                                        help="Opens it in the app's reader, where you "
                                             "highlight by selecting text."):
                    read_pdf(pmid, path)
                if exists and st.button("Show in folder", key=f"lib_show_{pmid}",
                                        width="stretch"):
                    library.reveal(path)
                if st.session_state.get("lib_confirm") == pmid:
                    if st.button("Yes, delete the file", key=f"lib_del_yes_{pmid}",
                                 type="primary", width="stretch"):
                        path.unlink(missing_ok=True)
                        db.forget_pdf(pmid)
                        st.session_state.lib_confirm = None
                        st.rerun()
                    if st.button("Cancel", key=f"lib_del_no_{pmid}", width="stretch"):
                        st.session_state.lib_confirm = None
                        st.rerun()
                elif st.button("🗑 Remove", key=f"lib_del_{pmid}", width="stretch"):
                    st.session_state.lib_confirm = pmid
                    st.rerun()


# ---------------------------------------------------------------------------
# TAB 4 - scrittura di un articolo Radiopaedia
# ---------------------------------------------------------------------------

def rich_copy_box(html_body: str, *, label: str, height: int, key: str) -> None:
    """Riquadro con l'HTML gia' reso e un pulsante che lo copia FORMATTATO.

    E' il punto centrale di tutta la scheda. L'editor di Radiopaedia e'
    WYSIWYG: incollargli testo semplice perde grassetti, titoli ed elenchi.
    Quello che invece accetta e' il flavour `text/html` degli appunti.

    Due vie, in quest'ordine, e l'ordine conta:

    1. `navigator.clipboard.write` con un Blob `text/html`. Mette negli
       appunti ESATTAMENTE l'HTML dato: `<h3>`, `<strong>`, `<sup>` e nulla
       piu'.
    2. `document.execCommand('copy')` su una selezione, per i browser che
       negano l'API. In questo caso il browser serializza i nodi
       selezionati e ci INLINEA lo stile calcolato: per questo la selezione
       cade su una copia nuda e fuori schermo del contenuto, non sul riquadro
       di anteprima - copiare quello si porterebbe dentro l'articolo i font e
       i colori dell'anteprima.
    """
    payload = html_body or "<p><em>Nothing to copy yet.</em></p>"
    st.html(
        f"""
        <style>
          .rc-wrap {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                      Roboto, sans-serif; }}
          .rc-bar {{ display: flex; gap: .5rem; align-items: center;
                     margin-bottom: .5rem; }}
          .rc-btn {{ font: inherit; font-size: .85rem; padding: .35rem .9rem;
                     border-radius: .5rem; border: 1px solid rgba(128,128,128,.4);
                     background: transparent; color: inherit; cursor: pointer; }}
          .rc-btn:hover {{ border-color: {theme.PRIMARY}; }}
          .rc-msg {{ font-size: .8rem; opacity: .75; }}
          .rc-body {{ border: 1px solid rgba(128,128,128,.3); border-radius: .5rem;
                      padding: .9rem 1.1rem; overflow: auto; background: #fff;
                      color: #111; height: {max(80, height - 60)}px; }}
          .rc-body h3 {{ font-size: 1.15rem; margin: .9rem 0 .4rem; }}
          .rc-body h4 {{ font-size: 1rem; margin: .8rem 0 .35rem; }}
          .rc-body p {{ margin: .5rem 0; line-height: 1.5; }}
          .rc-body sup {{ color: #0b6; font-weight: 600; }}
          .rc-body ol, .rc-body ul {{ margin: .5rem 0 .5rem 1.3rem; }}
          /* la sorgente della copia: fuori schermo e senza una sola regola
             di stile, cosi' non c'e' niente da inlineare */
          #raw-{key} {{ position: absolute; left: -10000px; top: 0; width: 700px; }}
        </style>
        <div class="rc-wrap">
          <div class="rc-bar">
            <button class="rc-btn" id="btn-{key}">{html.escape(label)}</button>
            <span class="rc-msg" id="msg-{key}"></span>
          </div>
          <div class="rc-body" id="src-{key}">{payload}</div>
        </div>
        <div id="raw-{key}" aria-hidden="true">{payload}</div>
        <script>
        (function () {{
          const btn = document.getElementById("btn-{key}");
          const raw = document.getElementById("raw-{key}");
          const msg = document.getElementById("msg-{key}");
          function say(t) {{ msg.textContent = t;
                             setTimeout(() => {{ msg.textContent = ""; }}, 5000); }}

          function bySelection() {{
            const range = document.createRange();
            range.selectNodeContents(raw);
            const sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
            let done = false;
            try {{ done = document.execCommand("copy"); }} catch (e) {{ done = false; }}
            sel.removeAllRanges();
            return done;
          }}

          /* L'API clipboard. Da quando questo blocco vive nella pagina vera
             (`st.html`) e non piu' nell'iframe di un componente, la
             permission policy non la nega piu' - ed e' l'unica via che mette
             negli appunti l'HTML esatto. L'altra lo fa serializzare al
             browser, che ci inlinea lo stile calcolato (`font-family: Times`,
             `color: rgb(0,0,0)`) e se lo porterebbe dentro l'articolo. */
          async function viaClipboardAPI(w) {{
            if (!w || !w.navigator || !w.navigator.clipboard || !w.ClipboardItem) return false;
            await w.navigator.clipboard.write([new w.ClipboardItem({{
              "text/html": new w.Blob([raw.innerHTML], {{ type: "text/html" }}),
              "text/plain": new w.Blob([raw.innerText], {{ type: "text/plain" }}),
            }})]);
            return true;
          }}

          btn.addEventListener("click", async () => {{
            btn.dataset.route = "";
            try {{
              if (await viaClipboardAPI(window)) {{
                btn.dataset.route = "clipboard-api";
                return say("Copied ✓ (clean HTML)");
              }}
            }} catch (e) {{
              btn.dataset.err = (e && e.name ? e.name : "?") + ": " +
                                (e && e.message ? e.message : e);
            }}
            if (bySelection()) {{
              btn.dataset.route = "exec-command";
              // onesto: per questa via il browser inlinea lo stile calcolato,
              // e se l'editor di Radiopaedia non lo scarta finisce nel testo
              return say("Copied ✓ (via selection: your browser added inline styling)");
            }}
            btn.dataset.route = "failed";
            say("The browser refused the copy. Select the box and press ⌘C.");
          }});
        }})();
        </script>
        """,
        unsafe_allow_javascript=True,
    )


# ---------------------------------------------------------------------------
# la struttura dei titoli
# ---------------------------------------------------------------------------

def body_key_for(draft_id: int) -> str:
    """La chiave della casella del testo, con dentro un contatore.

    Streamlit tiene il contenuto di un widget in `session_state` e da li' lo
    rimette dopo il rerun, ignorando il `value=` che gli passi; e non lascia
    scrivere quella voce dopo che il widget e' stato creato - solleva, ed e'
    giusto, perche' significherebbe cambiare sotto il naso una casella che
    l'utente sta usando.

    Quindi quando siamo NOI a cambiare il testo si cambia la chiave: il widget
    successivo e' un widget nuovo, e un widget nuovo il suo `value=` lo legge.
    Il contatore e' quello che rende la chiave nuova."""
    return f"body_{draft_id}_{st.session_state.get(f'bodyn_{draft_id}', 0)}"


def set_body(draft_id: int, body_md: str) -> None:
    """Il testo nuovo nel database, e la casella buttata via e rifatta."""
    db.save_draft(draft_id, body_md=body_md)
    st.session_state[f"bodyn_{draft_id}"] = st.session_state.get(f"bodyn_{draft_id}", 0) + 1


def heading_panel(draft, body_md: str) -> None:
    """I titoli che questo tipo di articolo dovrebbe avere.

    Il canone risponde a due domande diverse: quali sezioni MANCANO a un
    articolo che c'e' gia', e quali dovrebbero esserci in assoluto. La seconda
    e' quella utile adesso, con la bozza ancora quasi vuota.

    Tutti, quelli che scegli, o uno solo a una riga precisa. L'ultimo e'
    l'unico che puo' andare storto, e la gerarchia e' come: `Microscopic
    appearance` messo in mezzo a `Radiographic features` e' il sottotitolo
    della cosa sbagliata, e sembra tale e quale a uno finito al posto giusto.
    Quindi la riga chiesta si confronta con la sezione in cui cade davvero, e
    dove le due non vanno d'accordo si dice - senza rifiutare."""
    try:
        labels = sx.profile_labels()
    except sx.StructureError as exc:
        st.warning(str(exc))
        return

    names = list(labels)
    saved = draft["profile"] if "profile" in draft.keys() else None
    current = saved or sx.guess_profile(draft["title"])
    if current not in names:
        current = sx.canon().fallback

    profile_key = f"profile_{draft['id']}"

    def remember(did=draft["id"], key=profile_key):
        """Si salva solo quello che hai scelto tu.

        Scrivere anche quello indovinato lo trasformerebbe in una decisione: la
        volta dopo sarebbe indistinguibile da una scelta, e la riga che dice
        "tirato a indovinare dal titolo" sparirebbe proprio quando serve."""
        db.save_draft(did, profile=st.session_state.get(key))

    pick, opts = st.columns([2, 1])
    with pick:
        chosen = st.selectbox(
            "Kind of article", names, index=names.index(current),
            format_func=lambda n: labels[n], key=profile_key, on_change=remember,
            help="Radiopaedia has 23 article structures. This chooses the one "
                 "the headings come from. It is guessed from the title until "
                 "you choose one, and your choice is saved.")
    if not saved:
        st.caption("Guessed from the title. Change it if it is wrong.")

    canon_name = sx.canon().profiles[chosen]["canon"]
    rows = sx.rows_for(chosen)
    present = sx.present_entries(body_md, canon_name)
    missing = [r for r in rows if r.entry not in present]

    with opts:
        pending = st.checkbox(
            "with `content pending`", key=f"pending_{draft['id']}",
            help="Radiopaedia's placeholder text for an empty section. The "
                 "linter has a rule that finds these placeholders.")

    if not missing:
        st.success("Every heading this structure names is already in the draft.")
        return

    st.caption(f"{len(rows) - len(missing)} of {len(rows)} already in the draft · "
               f"**bold** are the ones this kind of article must have")

    # Le caselle. Le obbligatorie partono spuntate perche' sono quelle che
    # Radiopaedia chiede, non quelle che di solito si vogliono.
    #
    # Nella chiave c'e' lo stesso contatore della casella del testo, per lo
    # stesso motivo: appena il testo cambia queste caselle sono widget nuovi e
    # ripartono da capo. Senza, quelle appena inserite resterebbero spuntate -
    # e spuntarle a mano dopo non si puo', perche' Streamlit non lascia toccare
    # la voce di un widget gia' creato.
    stamp = st.session_state.get(f"bodyn_{draft['id']}", 0)
    pick_key = lambda row: f"pick_{draft['id']}_{stamp}_{row.entry}"   # noqa: E731

    box = st.container(height=260, border=True)
    picked: list[sx.Row] = []
    with box:
        for row in missing:
            key = pick_key(row)
            if key not in st.session_state:
                st.session_state[key] = row.required
            indent = "\u2003" * (row.level - 1)
            label = f"{indent}**{row.title}**" if row.required else f"{indent}{row.title}"
            if st.checkbox(label, key=key):
                picked.append(row)

    def set_all(how: str) -> None:
        # Gira come callback, cioe' PRIMA che i widget di questo giro esistano:
        # e' l'unico momento in cui scrivere in quelle voci e' permesso.
        for row in missing:
            st.session_state[pick_key(row)] = (
                how == "all" or (how == "required" and row.required))

    c1, c2, c3, c4 = st.columns([1, 1, 1, 2.2])
    c1.button("Required", key=f"req_{draft['id']}", on_click=set_all, args=("required",),
              width="stretch")
    c2.button("All", key=f"all_{draft['id']}", on_click=set_all, args=("all",),
              width="stretch")
    c3.button("None", key=f"none_{draft['id']}", on_click=set_all, args=("none",),
              width="stretch")
    if c4.button(f"Insert {len(picked)} heading(s)", type="primary", disabled=not picked,
                 key=f"ins_{draft['id']}", width="stretch"):
        # Nell'ordine del canone, non in quello in cui li hai spuntati: si
        # piazzano a vicenda, e un sottotitolo ha bisogno che il proprio
        # genitore sia entrato prima.
        new_md, added = sx.insert_rows(body_md, picked, canon_name, pending=pending)
        set_body(draft["id"], new_md)
        st.toast(f"{len(added)} heading(s) inserted, in the structure's order.")
        st.rerun()

    # ------------------------------------------------------------------
    # uno solo, a una riga precisa
    # ------------------------------------------------------------------
    with st.expander("Put one on a line of my choosing", expanded=False):
        n_lines = len(body_md.splitlines())
        one, where = st.columns([2, 1])
        row = one.selectbox(
            "Heading", missing, format_func=lambda r: "  " * (r.level - 1) + r.title,
            key=f"one_{draft['id']}", label_visibility="collapsed")
        line = where.number_input("Line", min_value=1, max_value=max(1, n_lines + 1),
                                  value=max(1, n_lines + 1), step=1,
                                  key=f"line_{draft['id']}",
                                  help="The line of the Markdown box above that "
                                       "the heading goes in front of.")
        if row is not None:
            plan = sx.check_one(body_md, row, int(line), canon_name)
            if plan.conflict:
                st.warning(plan.conflict + f" The structure puts it on line "
                                           f"{plan.canon_line}.")
            a, b = st.columns(2)
            if a.button(f"Put it on line {plan.canon_line} (the structure's place)",
                        key=f"canon_{draft['id']}", width="stretch"):
                set_body(draft["id"],
                         sx.insert_at(body_md, row, plan.canon_line, pending=pending))
                st.rerun()
            if b.button(f"Put it on line {int(line)} anyway", key=f"here_{draft['id']}",
                        width="stretch"):
                set_body(draft["id"],
                         sx.insert_at(body_md, row, int(line), pending=pending))
                st.rerun()


# ---------------------------------------------------------------------------
# il lint della bozza
# ---------------------------------------------------------------------------

SEVERITY_MARK = {"error": "🔴", "warning": "🟠", "suggestion": "🔵"}


def lint_panel(draft, body_md: str, numbers: dict) -> None:
    """Le regole del linter Radiopaedia, sulla bozza, prima di pubblicarla.

    Si linta l'HTML e non il markdown: meta' delle regole parlano di `<sup>`,
    `<strong>`, `<em>` e dei titoli, e nel markdown quei tag non ci sono
    ancora. E lo si rende alla profondita' a cui l'articolo verra' PUBBLICATO,
    non a quella in cui si incolla: le regole sono scritte contro la pagina di
    Radiopaedia, dove una sezione e' un `h4`."""
    st.caption(
        "The linter at radiopaedia.work checks published articles, so it "
        "cannot check a draft. These are its rules, transcribed on "
        f"{lint.transcribed_on()} and run on this computer. Nothing is sent. "
        "Radiopaedia has registered exceptions that are not available here. "
        "Where the two disagree, follow Radiopaedia's."
    )

    if st.button("Lint the draft", type="primary", key=f"lint_{draft['id']}"):
        st.session_state[f"lintrun_{draft['id']}"] = True

    if not st.session_state.get(f"lintrun_{draft['id']}"):
        return

    try:
        html_for_lint = rp.to_html(body_md, numbers, top_heading=lint.LINT_TOP_HEADING)
        findings = lint.attach_lines(lint.lint_html(html_for_lint), body_md)
    except lint.LintError as exc:
        st.error(str(exc))
        return

    shown = [f for f in findings if not f.hushed]
    hushed = [f for f in findings if f.hushed]
    counts = lint.tally(findings)

    if not shown:
        st.success("Nothing to fix." + (
            f" ({len(hushed)} set aside by the shared lists.)" if hushed else ""))
        return

    st.markdown(
        f"**{counts['error']}** error(s) · **{counts['warning']}** warning(s) · "
        f"**{counts['suggestion']}** suggestion(s)")

    only = st.multiselect(
        "Show", ["error", "warning", "suggestion"], default=["error", "warning", "suggestion"],
        key=f"sev_{draft['id']}", label_visibility="collapsed")

    for finding in shown:
        if finding.severity not in only:
            continue
        where = f"line {finding.line}" if finding.line else f"block {finding.block + 1}"
        with st.container(border=True):
            st.markdown(
                f"{SEVERITY_MARK.get(finding.severity, '⚪')} **{finding.check}** · {where}"
                + (f" · [style guide](https://radiopaedia.org{finding.link})"
                   if finding.link else ""))
            st.write(finding.message)
            # Il pezzo di testo in questione, con dentro segnato cosa lo ha
            # fatto scattare: il messaggio dice cosa non va, questo dice dove.
            snippet = finding.snippet
            if not finding.whole and finding.length:
                a, b = finding.at, finding.at + finding.length
                snippet = f"{snippet[:a]}⟦{snippet[a:b]}⟧{snippet[b:]}"
            st.caption(snippet[:400] + ("…" if len(snippet) > 400 else ""))

    if hushed:
        with st.expander(f"{len(hushed)} set aside by the shared lists", expanded=False):
            st.caption(
                "Proper nouns that can start a list item, and acronyms that "
                "need no expansion. The two lists are in `radiowriter/data/`.")
            for finding in hushed:
                st.caption(f"· **{finding.matched}**: {finding.check} "
                           f"(covered by “{finding.known}”)")


# ---------------------------------------------------------------------------
# la barra di formattazione
# ---------------------------------------------------------------------------

# I bottoni NON stanno dentro l'iframe del componente, e non e' un dettaglio.
# Cliccare dentro un iframe sposta il fuoco, quindi la casella del testo lo
# perde, quindi Streamlit manda il valore e fa ripartire lo script: ogni
# grassetto sarebbe un giro di server, e la nostra modifica correrebbe contro
# il rerun che lei stessa ha provocato. Cosi' invece l'iframe fa solo da
# innesco - inietta la barra nella pagina vera e si nasconde - e li' il
# `preventDefault` sul mousedown impedisce al fuoco di muoversi: nessun blur,
# nessun rerun, il cursore resta dov'era.
#
# Che si possa fare lo dimostra `rich_copy_box`, che usa `window.parent` per la
# stessa ragione: l'iframe di un componente e' same-origin con la pagina.

TOOLBAR_JS = r"""
<span id="mdanchor-__KEY__" style="display:none"></span>
<script>
(function () {
  /* `st.html` inietta nella pagina vera, non in un iframe: `P` e `doc` sono
     quelli del documento dove sta anche la casella di testo. Al posto
     dell'elemento iframe si usa come segnaposto lo span qui sopra.
     NOTA: dentro questo script non si scrivono tag in chiaro, nemmeno nei
     commenti - il sanificatore di `st.html` butta via tutto il blocco. */
  const P = window, doc = document, me = doc.getElementById("mdanchor-__KEY__");
  if (!doc || !me) return;
  const ID = "mdbar-__KEY__";

  /* La casella e' il primo textarea che nel documento viene DOPO questo
     segnaposto. Cercarla per etichetta la legherebbe a come e' scritta;
     cosi' invece la si trova per posizione, che e' quella che decidiamo noi. */
  function area() {
    const all = doc.querySelectorAll("textarea");
    for (let i = 0; i < all.length; i++) {
      if (me.compareDocumentPosition(all[i]) & Node.DOCUMENT_POSITION_FOLLOWING) return all[i];
    }
    return null;
  }

  /* React non ascolta l'assegnazione, ascolta il setter nativo: senza questo
     la modifica si vedrebbe sullo schermo e Streamlit non la riceverebbe mai. */
  const nativeSet = Object.getOwnPropertyDescriptor(
      P.HTMLTextAreaElement.prototype, "value").set;

  function commit(ta, value, from, to) {
    nativeSet.call(ta, value);
    ta.dispatchEvent(new P.Event("input", { bubbles: true }));
    ta.focus();
    ta.setSelectionRange(from, to);
  }

  function wrap(ta, open, close, holder) {
    const v = ta.value, a = ta.selectionStart, b = ta.selectionEnd;
    const inside = v.slice(a, b);
    /* gia' avvolto: si toglie, invece di raddoppiare i marcatori */
    if (inside && v.slice(a - open.length, a) === open && v.slice(b, b + close.length) === close) {
      return commit(ta, v.slice(0, a - open.length) + inside + v.slice(b + close.length),
                    a - open.length, b - open.length);
    }
    const text = inside || holder;
    const from = a + open.length;
    commit(ta, v.slice(0, a) + open + text + close + v.slice(b), from, from + text.length);
  }

  function link(ta) {
    const v = ta.value, a = ta.selectionStart, b = ta.selectionEnd;
    const text = v.slice(a, b) || "text";
    const from = a + text.length + 3;          /* subito dopo "](" */
    commit(ta, v.slice(0, a) + "[" + text + "](url)" + v.slice(b), from, from + 3);
  }

  /* I marcatori di riga - titoli ed elenchi - valgono su tutte le righe
     toccate dalla selezione. Si toglie sempre quello che c'e' gia', altrimenti
     un titolo diventa "## # Titolo" e un elenco si annida da solo. */
  const MARKER = /^[ \t]*(#{1,6}[ \t]+|[-+*][ \t]+|\d+\.[ \t]+)/;

  function prefix(ta, mark, numbered) {
    const v = ta.value;
    const a = v.lastIndexOf("\n", ta.selectionStart - 1) + 1;
    let b = v.indexOf("\n", ta.selectionEnd);
    if (b < 0) b = v.length;
    const lines = v.slice(a, b).split("\n");
    const bare = lines.map(l => l.replace(MARKER, ""));
    const of = (i) => numbered ? (i + 1) + ". " : mark;
    /* se ce l'hanno gia' tutte, il bottone lo toglie */
    const on = lines.every((l, i) => l === of(i) + bare[i]) && lines.some(l => l.trim());
    const text = bare.map((l, i) => (on || !l.trim()) ? l : of(i) + l).join("\n");
    commit(ta, v.slice(0, a) + text + v.slice(b), a, a + text.length);
  }

  const TOOLS = [
    ["B",    "Bold  ⌘B",                        ta => wrap(ta, "**", "**", "bold")],
    ["I",    "Italic  ⌘I",                      ta => wrap(ta, "*", "*", "italic")],
    ["H1",   "Section heading (h3 on Radiopaedia)", ta => prefix(ta, "# ", false)],
    ["H2",   "Subheading (h4)",                 ta => prefix(ta, "## ", false)],
    ["H3",   "Sub-subheading (h5)",             ta => prefix(ta, "### ", false)],
    ["•",    "Bulleted list",                   ta => prefix(ta, "- ", false)],
    ["1.",   "Numbered list",                   ta => prefix(ta, "", true)],
    ["🔗",   "Link  ⌘K",                        ta => link(ta)],
    ["[@]",  "Citation (by identifier, numbered at export)",
                                                ta => wrap(ta, "[@", "]", "27859258")],
  ];

  function style() {
    if (doc.getElementById("mdbar-style")) return;
    const css = doc.createElement("style");
    css.id = "mdbar-style";
    css.textContent =
      ".mdbar{display:flex;flex-wrap:wrap;gap:.25rem;margin:0 0 .35rem 0}" +
      ".mdbar button{font:inherit;font-size:.8rem;line-height:1;min-width:2rem;" +
        "padding:.4rem .55rem;border-radius:.4rem;cursor:pointer;" +
        "border:1px solid rgba(128,128,128,.35);background:transparent;color:inherit}" +
      ".mdbar button:hover{border-color:#2563eb}" +
      ".mdbar button.b{font-weight:700}.mdbar button.i{font-style:italic}" +
      ".mdbar .sep{width:1px;margin:.15rem .3rem;background:rgba(128,128,128,.3)}";
    doc.head.appendChild(css);
  }

  function build() {
    const ta = area();
    if (!ta) return null;
    const old = doc.getElementById(ID);
    if (old) old.remove();

    const bar = doc.createElement("div");
    bar.className = "mdbar";
    bar.id = ID;
    TOOLS.forEach(([label, tip, run], n) => {
      if (n === 2 || n === 5 || n === 7) bar.appendChild(
        Object.assign(doc.createElement("div"), { className: "sep" }));
      const b = doc.createElement("button");
      b.type = "button";
      b.textContent = label;
      b.title = tip;
      if (label === "B") b.className = "b";
      if (label === "I") b.className = "i";
      /* il fuoco non si muove: senza questo la casella lo perde, Streamlit
         manda il valore e fa ripartire lo script sotto le nostre mani */
      b.addEventListener("mousedown", e => e.preventDefault());
      b.addEventListener("click", e => {
        e.preventDefault();
        const now = area();
        if (now) run(now);
      });
      bar.appendChild(b);
    });

    const host = ta.closest('[data-testid="stTextArea"]') || ta.parentElement;
    host.parentElement.insertBefore(bar, host);

    if (!ta.dataset.mdbar) {
      ta.dataset.mdbar = "1";
      ta.addEventListener("keydown", e => {
        if (!(e.metaKey || e.ctrlKey) || e.altKey) return;
        const k = e.key.toLowerCase();
        if (k === "b") { e.preventDefault(); wrap(ta, "**", "**", "bold"); }
        else if (k === "i") { e.preventDefault(); wrap(ta, "*", "*", "italic"); }
        else if (k === "k") { e.preventDefault(); link(ta); }
      });
    }
    return bar;
  }

  style();
  build();

  /* Streamlit ridisegna, e quando ridisegna si porta via anche la barra:
     la si rimette. Un osservatore solo, sostituito a ogni giro, altrimenti
     se ne accumulerebbe uno per rerun. */
  P.__mdbars = P.__mdbars || {};
  if (P.__mdbars[ID]) { try { P.__mdbars[ID].disconnect(); } catch (e) {} }
  let waiting = false;
  const watch = new P.MutationObserver(() => {
    if (waiting || doc.getElementById(ID)) return;
    waiting = true;
    P.setTimeout(() => { waiting = false; build(); }, 60);
  });
  watch.observe(doc.body, { childList: true, subtree: true });
  P.__mdbars[ID] = watch;
})();
</script>
"""


def markdown_toolbar(key: str) -> None:
    """La barra sopra la casella del testo."""
    st.html(TOOLBAR_JS.replace("__KEY__", key), unsafe_allow_javascript=True)


# ---------------------------------------------------------------------------
# l'anteprima
# ---------------------------------------------------------------------------

PREVIEW_CSS = """
<style>
  .mdprev { border: 1px solid rgba(128,128,128,.3); border-radius: .5rem;
            padding: 1rem 1.25rem; min-height: 460px; }
  .mdprev h3 { font-size: 1.2rem; margin: 1rem 0 .4rem; font-weight: 600; }
  .mdprev h4 { font-size: 1.05rem; margin: .9rem 0 .35rem; font-weight: 600; }
  .mdprev h5 { font-size: .95rem; margin: .8rem 0 .3rem; font-weight: 600; }
  .mdprev h3:first-child, .mdprev h4:first-child { margin-top: 0; }
  .mdprev p { margin: .5rem 0; line-height: 1.6; }
  .mdprev ul, .mdprev ol { margin: .5rem 0 .5rem 1.4rem; }
  .mdprev li { margin: .2rem 0; line-height: 1.55; }
  .mdprev sup { opacity: .75; font-weight: 600; padding-left: .1rem; }
  .mdprev table { border-collapse: collapse; margin: .6rem 0; }
  .mdprev th, .mdprev td { border: 1px solid rgba(128,128,128,.35);
                           padding: .3rem .55rem; }
  .mdprev .empty { opacity: .6; font-style: italic; }
  .mdprev .refs { margin-top: 1.4rem; padding-top: .8rem;
                  border-top: 1px solid rgba(128,128,128,.25); }
  .mdprev .refs .ref { font-size: .85rem; opacity: .85; margin: .3rem 0;
                       line-height: 1.5; }
  .mdprev .refs .none { font-size: .85rem; opacity: .7; font-style: italic; }
</style>
"""


def preview_box(article_html: str, reference_lines: list[str]) -> None:
    """L'articolo come sara', numeri di citazione compresi.

    Non e' l'anteprima di un markdown qualunque: e' lo STESSO HTML che il
    bottone di copia mette negli appunti, quindi quello che si vede qui e'
    quello che l'editor di Radiopaedia ricevera'. E ci sono sotto le
    referenze, perche' e' li' che si vede se un numero e' finito storto."""
    body = article_html or '<p class="empty">Nothing written yet.</p>'
    # Le righe arrivano gia' numerate e gia' nella forma `N. testo`, che e' la
    # riga esatta di un box dell'editor: si mostrano com'e', non dentro un
    # elenco che ci rimetterebbe davanti un secondo numero.
    refs = ("".join(f'<div class="ref">{line}</div>' for line in reference_lines)
            if reference_lines else
            '<p class="none">No references cited yet.</p>')
    st.html(
        PREVIEW_CSS
        + f'<div class="mdprev">{body}'
        + f'<div class="refs"><strong>References</strong>{refs}</div></div>'
    )


def study_panel(draft) -> None:
    """La pagina Radiopaedia e il PDF da aprire nella finestra di studio."""
    missing = study.available()
    if missing:
        st.warning(missing)
        return

    did = draft["id"]
    saved = clean(draft["radiopaedia_url"])
    how = st.segmented_control(
        "Radiopaedia page", ["From the article list", "Radiopaedia search", "URL"],
        default="From the article list", key=f"study_how_{did}")
    page = saved or study.HOME_URL
    if how == "From the article list":
        index_file = paths.radiopaedia_index()
        if index_file is None:
            st.caption(
                "No article list in the data folder. Export it as CSV from the "
                "Radiopaedia article search and drop it into "
                f"`{paths.short(paths.home(create=False))}` as "
                "`radiopaedia-articles-<date>.csv`. You can also use the other two options.")
        else:
            index = radiopaedia_index(str(index_file), index_file.stat().st_mtime)
            text = st.text_input(
                "Find an article", value=draft["title"] if draft["title"] !=
                "Untitled article" else "", key=f"study_find_{did}",
                help=f"{len(index):,} articles, from `{index_file.name}`.")
            hits = study.find(index, text)
            if hits:
                options = {h["url"]: h for h in hits}
                start = list(options).index(saved) if saved in options else 0
                page = st.selectbox(
                    "Article", list(options), index=start, key=f"study_pick_{did}",
                    format_func=lambda u: (f"{options[u]['title']}  ·  "
                                           f"{options[u]['systems']}"),
                    label_visibility="collapsed")
            elif text.strip():
                st.caption("Nothing in the list. Try the Radiopaedia search: "
                           "the list is only as recent as its export.")
    elif how == "Radiopaedia search":
        text = st.text_input("Search Radiopaedia for", value=draft["title"],
                             key=f"study_q_{did}")
        page = study.search_url(text) if text.strip() else study.HOME_URL
        st.caption("The window opens on their search results; pick the article there.")
    else:
        page = st.text_input("Radiopaedia URL", value=saved,
                             key=f"study_url_{did}",
                             placeholder="https://radiopaedia.org/articles/…").strip()

    # I PDF citati nella bozza per primi, poi il resto della libreria.
    cited = db.library_rows(draft_id=did)
    others = [r for r in db.library_rows() if r["pmid"] not in {c["pmid"] for c in cited}]
    pdfs = {"": "No PDF (Radiopaedia only)"}
    for r in cited:
        pdfs[r["pmid"]] = "★ " + r["filename"]
    for r in others:
        pdfs[r["pmid"]] = r["filename"]
    pick = st.selectbox("PDF next to it", list(pdfs), format_func=pdfs.get,
                        key=f"study_pdf_{did}",
                        help="★ = cited in this draft. PDFs come from the Library tab.")
    layout = st.radio(
        "Layout", ["lr", "tb"], horizontal=True, key=f"study_layout_{did}",
        index=0 if settings.get("study_layout", "lr") != "tb" else 1,
        format_func={"lr": "◫ Side by side", "tb": "⬒ One above the other"}.get)

    if st.button("🪟 Open study window", type="primary", key=f"study_go_{did}",
                 disabled=not study.is_radiopaedia(page)):
        if study.is_radiopaedia(page, article=True) and page != saved:
            db.set_draft_page(did, page)
        if layout != settings.get("study_layout"):
            db.save_settings({"study_layout": layout})
            st.session_state.settings = db.get_settings()
        pdf_path = None
        if pick:
            row = db.pdfs_for([pick]).get(pick)
            pdf_path = lib_folder() / row["filename"] if row else None
        study.launch(page, pdf_path, layout, pmid=pick or None)
        st.toast("The study window opens separately. Look behind the browser "
                 "if it does not come to the front.")
    st.caption("Radiopaedia opens in a separate browser window with its own "
               "login, which is kept between sessions. Sign in there once to "
               "edit. With a PDF, the other window lists its highlights with a "
               "checkbox each. Highlights you add in another program appear "
               "there after you save the file.")


@st.fragment
def write_tab() -> None:
    drafts = db.list_drafts()

    head, new_col, del_col = st.columns([3, 1, 1])
    with head:
        if drafts:
            labels = {f"{r['title']}  ·  {r['n_refs']} refs": r["id"] for r in drafts}
            ids = list(labels.values())
            current = st.session_state.get("draft_id")
            index = ids.index(current) if current in ids else 0
            chosen = st.selectbox("Draft", list(labels), index=index)
            st.session_state.draft_id = labels[chosen]
        else:
            st.session_state.draft_id = None
            st.info("No drafts yet. Create one to start writing.")
    with new_col:
        st.write("")
        if st.button("＋ New draft", width="stretch"):
            st.session_state.draft_id = db.create_draft("Untitled article")
            st.rerun()
    with del_col:
        st.write("")
        if st.session_state.get("draft_id") and st.button(
                "🗑 Delete", width="stretch"):
            st.session_state.confirm_delete = st.session_state.draft_id
            st.rerun()

    if st.session_state.get("confirm_delete"):
        target = db.get_draft(st.session_state.confirm_delete)
        if target:
            st.warning(f"Delete the draft “{target['title']}” and its reference list? "
                       "This cannot be undone.")
            yes, no = st.columns([1, 5])
            if yes.button("Yes, delete", type="primary"):
                db.delete_draft(st.session_state.confirm_delete)
                st.session_state.confirm_delete = None
                st.session_state.draft_id = None
                st.rerun()
            if no.button("Cancel"):
                st.session_state.confirm_delete = None
                st.rerun()
        else:
            st.session_state.confirm_delete = None

    # ----------------------------------------------------------------------
    # una bozza che arriva da un file
    # ----------------------------------------------------------------------
    with st.expander("⇅ Import a draft from a file", expanded=False):
        st.caption(
            "A `.json` file written by Export, on this computer or another. "
            "It restores the text, the kind of article, the reference list and "
            "the resolved citations. It is always imported as a new draft, and "
            "no existing draft is overwritten."
        )
        picked_file = st.file_uploader(
            "Draft file", type=["json"], key="draft_import",
            label_visibility="collapsed")
        if picked_file is not None:
            try:
                incoming = draft_io.read_bundle(picked_file.getvalue())
            except draft_io.DraftIOError as exc:
                st.error(str(exc))
            else:
                st.caption(
                    f"**{incoming['title']}**: "
                    f"{len(incoming['body_md'].splitlines())} lines, "
                    f"{len(incoming['references'])} reference(s)"
                    + (f", exported {incoming['exported'][:10]}"
                       if incoming["exported"] else ""))
                if st.button("Import as a new draft", type="primary"):
                    st.session_state.draft_id = draft_io.create_from(incoming)
                    st.rerun()

    draft_id = st.session_state.get("draft_id")
    draft = db.get_draft(draft_id) if draft_id else None

    if draft:
        with st.expander("🪟 Study window: the Radiopaedia page next to a PDF",
                         expanded=False):
            study_panel(draft)

        # ------------------------------------------------------------------
        # editor + pannello laterale
        # ------------------------------------------------------------------
        # Le citazioni e la numerazione si calcolano PRIMA di disegnare, perche'
        # ora servono anche sopra: l'anteprima mostra l'articolo coi numeri al
        # loro posto, e i numeri non si sanno finche' non si sono lette le
        # citazioni - e' da DOI e PMID che si capisce quando due token diversi
        # sono lo stesso lavoro.
        title_key = f"title_{draft['id']}"
        body_key = body_key_for(draft["id"])
        body_md = st.session_state.get(body_key, draft["body_md"] or "")

        cited = rp.cited_identifiers(body_md)
        listed = db.draft_identifiers(draft["id"])
        wanted = sorted(set(cited) | set(listed))
        citations = db.cached_citations(wanted)
        numbers = rp.numbering(body_md, citations)
        merged = rp.merged_groups(numbers)

        cited_not_listed = [i for i in cited if i not in listed]
        listed_not_cited = [i for i in listed if i not in numbers]
        unresolved = [i for i in wanted if not (citations.get(i) or {}).get("citation")]

        col_edit, col_side = st.columns([2.2, 1])

        with col_edit:
            def autosave(did=draft["id"], tkey=title_key, bkey=body_key):
                """Salva quando il campo perde il fuoco: una bozza persa
                perche' si e' cambiata scheda non e' un rischio accettabile."""
                db.save_draft(did, title=st.session_state.get(tkey),
                              body_md=st.session_state.get(bkey))

            st.text_input("Article title", value=draft["title"], key=title_key,
                          on_change=autosave)

            def switched(did=draft["id"]):
                """Cambiando vista la casella va rifatta da capo.

                In anteprima la casella non viene disegnata, e Streamlit butta
                via lo stato dei widget che non disegna piu'. Cambiare il
                contatore la fa rinascere come widget nuovo, che il proprio
                `value=` lo legge - e lo legge dal database, dove il salvataggio
                al blur ha appena scritto. Senza, tornando in scrittura si
                rischia di rivedere il testo di prima."""
                st.session_state[f"bodyn_{did}"] = st.session_state.get(f"bodyn_{did}", 0) + 1

            mode = st.segmented_control(
                "View", ["✎ Markdown", "◫ Formatted"], default="✎ Markdown",
                key=f"mode_{draft['id']}", on_change=switched,
                label_visibility="collapsed",
                help="The formatted view shows the HTML that the copy button "
                     "puts on the clipboard, which is what the Radiopaedia "
                     "editor receives.")

            if mode == "◫ Formatted":
                preview_box(
                    rp.to_html(body_md, numbers, top_heading=draft["top_heading"] or 3),
                    rp.reference_lines(numbers, citations))
                st.caption(
                    "Read-only. Switch back to Markdown to edit. "
                    "Citation numbers come from the order of first appearance."
                )
            else:
                markdown_toolbar(f"body{draft['id']}")
                st.text_area(
                    "Body (Markdown)", value=draft["body_md"] or "", key=body_key,
                    height=460, on_change=autosave,
                    help="Cite with [@27859258], using the identifier (PMID, DOI, "
                         "PMCID, ISBN). Numbers are assigned at export, in "
                         "order of first appearance.",
                )
                st.caption(
                    "`#` → h3 (section) · `##` → h4 · `**bold**` · `*italic*` · "
                    "`- list` · `[text](url)` · `[@27859258]` cites. "
                    "⌘B bold · ⌘I italic · ⌘K link. "
                    "Saved when a field loses focus."
                )

            with st.expander("⌗ Headings for this kind of article",
                             expanded=False):
                heading_panel(draft, body_md)

        with col_side:
            st.markdown("**References**")
            st.caption(f"{len(set(numbers.values()))} cited in the text · "
                       f"{len(listed)} in the list")
            for n, idents in sorted(merged.items()):
                st.caption(f"↳ {' and '.join(idents)} are the same paper: "
                           f"both are reference {n}.")

            if cited_not_listed:
                st.warning(f"{len(cited_not_listed)} cited but not in the list.")
                if st.button("Add them to the list", width="stretch"):
                    db.add_draft_refs(draft["id"], cited_not_listed, note="from the text")
                    st.rerun()

            if unresolved:
                if st.button(f"🔎 Resolve {len(unresolved)} citation(s)",
                             type="primary", width="stretch"):
                    bar = st.progress(0.0, "Asking radiopaedia.work/cite…")
                    session = http_session()
                    failed = []
                    for i, ident in enumerate(unresolved, 1):
                        try:
                            db.store_citation(rp.fetch_citation(ident, session))
                        except rp.CiteError as exc:
                            failed.append(f"{ident}: {exc}")
                        bar.progress(i / len(unresolved), f"{i}/{len(unresolved)}")
                        if i < len(unresolved):
                            time.sleep(0.4)
                    if failed:
                        st.error("Not resolved:\n\n" + "\n\n".join(failed))
                    else:
                        st.rerun()

            with st.form(f"add_ref_{draft['id']}", clear_on_submit=True):
                raw = st.text_input("Add by identifier",
                                    placeholder="PMID, DOI, PMCID, ISBN or URL")
                if st.form_submit_button("Add reference", width="stretch"):
                    ident = rp.normalise_identifier(raw)
                    if ident:
                        db.add_draft_refs(draft["id"], [ident], note="added by hand")
                        st.rerun()

            # Da dove pesca la bibliografia: i segnalati, o una delle liste.
            # Sono due modi diversi di aver gia' deciso che un lavoro serve, e
            # una lista fatta per una sezione dell'articolo e' esattamente la
            # bibliografia di quella sezione.
            with st.expander("From the archive", expanded=False):
                reading_lists = db.list_lists()
                FLAGGED = "★ Flagged"
                sources = [FLAGGED] + [f"🗂 {r['name']}" for r in reading_lists]
                source = st.selectbox(
                    "Source", sources, key=f"refsrc_{draft['id']}",
                    label_visibility="collapsed")

                if source == FLAGGED:
                    rows = db.flagged_articles()
                    note = "from the archive"
                else:
                    chosen_list = reading_lists[sources.index(source) - 1]
                    rows = db.list_articles(chosen_list["id"])
                    note = f"from the list “{chosen_list['name']}”"

                already = set(listed)
                available = [r for r in rows if r["pmid"] not in already]
                if not rows:
                    st.caption("Nothing here yet.")
                elif not available:
                    st.caption(f"All {len(rows)} of them are already in the list.")
                else:
                    titles = {r["pmid"]: clean(r["title"]) for r in rows}
                    picked = st.multiselect(
                        "Articles", [r["pmid"] for r in available],
                        format_func=lambda p: f"{p}: {titles[p][:60]}",
                        label_visibility="collapsed",
                        placeholder=f"Choose from {len(available)}…",
                        key=f"refpick_{draft['id']}_{source}")
                    # Uno sotto l'altro, non affiancati: questa colonna e'
                    # stretta, e due pulsanti in fila ci finiscono a capo in
                    # mezzo alla parola.
                    if st.button(f"Add {len(picked)}", disabled=not picked,
                                 key=f"refadd_{draft['id']}", width="stretch"):
                        db.add_draft_refs(draft["id"], picked, note=note)
                        st.rerun()
                    if st.button(f"Add all {len(available)}",
                                 key=f"refall_{draft['id']}", width="stretch"):
                        db.add_draft_refs(
                            draft["id"], [r["pmid"] for r in available], note=note)
                        st.rerun()
                    if len(rows) != len(available):
                        st.caption(f"{len(rows) - len(available)} already in the list.")

            st.divider()
            st.markdown("**Searches**")
            history = db.recent_searches(30)
            attached = db.draft_search_list(draft["id"])
            attached_ids = {r["id"] for r in attached}
            for row in attached:
                c1, c2 = st.columns([5, 1])
                c1.caption(f"**{row['terms']}**: {row['n_found']} found, "
                           f"{row['n_saved']} saved")
                if c2.button("✕", key=f"detach_{draft['id']}_{row['id']}"):
                    db.detach_search(draft["id"], row["id"])
                    st.rerun()
            free = [r for r in history if r["id"] not in attached_ids]
            if free:
                pick = st.selectbox(
                    "Attach a search", free,
                    format_func=lambda r: f"{r['terms']} ({r['n_found']} found)",
                    index=None, placeholder="Choose a search…")
                if pick is not None and st.button("Attach", width="stretch"):
                    db.attach_search(draft["id"], pick["id"])
                    st.rerun()
            elif not attached:
                st.caption("No searches recorded yet. Run one in the PubMed search tab.")

        # ------------------------------------------------------------------
        # anteprima ed export
        # ------------------------------------------------------------------
        st.divider()
        st.subheader("Paste into the Radiopaedia editor")
        st.caption(
            "Radiopaedia's editor is a rich-text editor, and plain text loses "
            "its formatting. These two boxes copy rich text, so headings, bold "
            "and the <sup> markers are kept. Paste the article into the body, "
            "and each reference line into its own reference box."
        )

        article_html = rp.to_html(body_md, numbers, top_heading=draft["top_heading"] or 3)
        lines = rp.reference_lines(numbers, citations)
        refs_html = "<br>".join(lines) if lines else ""

        ex_left, ex_right = st.columns([2.2, 1])
        with ex_left:
            rich_copy_box(article_html, label="📋 Copy article (formatted)",
                          height=430, key=f"art{draft['id']}")
        with ex_right:
            rich_copy_box(refs_html, label=f"📋 Copy {len(lines)} reference(s)",
                          height=430, key=f"ref{draft['id']}")

        if listed_not_cited:
            st.caption(
                f"⚠️ {len(listed_not_cited)} reference(s) in the list are never cited "
                f"in the text and are therefore not numbered: "
                + ", ".join(listed_not_cited[:6])
                + (" …" if len(listed_not_cited) > 6 else "")
            )

        with st.expander("HTML source", expanded=False):
            st.caption(
                "What the button puts on the clipboard. Useful to check what "
                "the editor received, or to paste somewhere that takes HTML."
            )
            st.code(article_html, language="html")

        with st.expander("Reference list, one line per box", expanded=False):
            for line in lines:
                st.code(line, language="text")
            for ident in listed_not_cited:
                rec = citations.get(ident) or {}
                c1, c2 = st.columns([5, 1.3])
                c1.caption(f"not cited: {rec.get('title') or ident}")
                if c2.button("✕", key=f"drop_{draft['id']}_{ident}"):
                    db.remove_draft_ref(draft["id"], ident)
                    st.rerun()

        # ------------------------------------------------------------------
        # la bozza come file
        # ------------------------------------------------------------------
        st.divider()
        st.subheader("Keep a copy")
        st.caption(
            "The `.json` file contains the draft: text, kind of article, "
            "references with their notes, and resolved citations. Import "
            "reads this file. The `.md` file contains only the text and opens "
            "in any text editor. It cannot be imported."
        )
        bundle = draft_io.bundle(draft["id"])
        dl_json, dl_md, _ = st.columns([1, 1, 2])
        dl_json.download_button(
            "⤓ Export .json", data=draft_io.to_json(bundle),
            file_name=draft_io.filename(bundle, ".json"), mime="application/json",
            width="stretch", key=f"dljson_{draft['id']}")
        dl_md.download_button(
            "⤓ Export .md", data=draft_io.to_markdown(bundle),
            file_name=draft_io.filename(bundle, ".md"), mime="text/markdown",
            width="stretch", key=f"dlmd_{draft['id']}")

        # ------------------------------------------------------------------
        # il lint
        # ------------------------------------------------------------------
        st.divider()
        st.subheader("Lint the draft")
        lint_panel(draft, body_md, numbers)


tab_search, tab_screen, tab_library, tab_write = st.tabs(
    ["1  PubMed search", "2  Screening", "3  Library", "4  Write"])
with tab_search:
    search_tab()
with tab_screen:
    screen_tab()
with tab_library:
    library_tab()
with tab_write:
    write_tab()
