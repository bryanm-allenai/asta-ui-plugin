import { useState } from "react";
import {
  api,
  type CompareResult,
  type DatasetData,
  type Organization,
  type RecordRow,
  type ScanResult,
} from "./api";
import { Header, type View } from "./components/Header";
import { Footer } from "./components/Footer";
import { SpectrumPlot } from "./components/SpectrumPlot";
import { Heatmap } from "./components/Heatmap";
import { MatrixSliceViewer } from "./components/MatrixSliceViewer";
import { NMRPanel } from "./components/NMRPanel";
import { NotebookMenu } from "./components/NotebookMenu";
import { RepoSearch } from "./components/RepoSearch";
import { LayoutTabs } from "./components/LayoutTabs";
import { MoleculeViewer } from "./components/MoleculeViewer";
import { CompoundViewer } from "./components/CompoundViewer";
import { guessCompound } from "./compound";
import { WaveformPlayer } from "./components/WaveformPlayer";
import { CompareView } from "./components/CompareView";
import { ExportMenu } from "./components/ExportMenu";
import { ConnectGuide } from "./components/ConnectGuide";
import { ProviderIcon } from "./components/ProviderIcon";
import { DataWorkspace } from "./components/DataWorkspace";
import { Diagnostics } from "./components/Diagnostics";

const DEFAULT_REPO = "https://github.com/yargerlab/Data";

function PanelBrand({ label }: { label: string }) {
  return (
    <div className="panel-brand">
      <span className="psi">Ψ</span>
      {label}
    </div>
  );
}

export default function App() {
  const [view, setView] = useState<View>("QUICK");
  return (
    <>
      <Header view={view} onNav={setView} />
      <main className="main">
        {/* keep QUICK mounted (hidden) so scan/plot state survives tab switches */}
        <div hidden={view !== "QUICK"}>
          <Quick onNav={setView} />
        </div>
        <div hidden={view !== "DATA"}>
          <DataWorkspace />
        </div>
        {view !== "QUICK" && view !== "DATA" && <Coming view={view} />}
      </main>
      <Footer />
    </>
  );
}

function Coming({ view }: { view: View }) {
  return (
    <div className="card">
      <p className="coming">
        <span className="psi">Ψ</span>
        <span className="ket">|Viz⟩</span> — advanced, interactive visualization & analysis are coming
        soon (NMRium-style NMR, DSC glass-transition/enthalpy, spectrum overlays, subplots).
        <br />
        For now, start from <b>QUICK</b> to point at a data source, overlay datasets, and compare
        formats. <span className="muted">({view})</span>
      </p>
    </div>
  );
}

type Preset = { label: string; provider: string; url: string };
// Two ways to bring data in: storage you host yourself, vs. open FAIR repositories you access (and could
// publish into). See https://www.go-fair.org / https://fairsharing.org for the FAIR principles.
const SOURCE_GROUPS: { key: string; title: string; blurb: string; presets: Preset[] }[] = [
  {
    key: "host",
    title: "Host your own data",
    blurb: "Point PsiDataViz at a public folder you control.",
    presets: [
      { label: "yargerlab/Data", provider: "github", url: "https://github.com/yargerlab/Data" },
      {
        label: "Google Drive — Psi_Data",
        provider: "gdrive",
        url: "https://drive.google.com/drive/folders/16VQhcRbCHkzhH2cq8T5DwyhTUBj2BrO4",
      },
      { label: "Codeberg — PsiData", provider: "codeberg", url: "https://codeberg.org/jyarger/PsiData" },
      { label: "Box — PsiData", provider: "box", url: "https://app.box.com/s/yigbg0fd5xj5n1hkxf8rcsemrkz7qgsx" },
    ],
  },
  {
    key: "repo",
    title: "Open FAIR repositories",
    blurb: "Visualize published, DOI-minted data from open repositories.",
    presets: [
      { label: "Chemotion — published data", provider: "chemotion", url: "https://www.chemotion-repository.net/" },
    ],
  },
];

// A record's `key` (base name) repeats across techniques and sub-folders, so identify a selected row
// by its source-unique `uid` (folder + base name).
const rid = (r: RecordRow) => r.uid;

const ORG_INFO: Record<Organization["kind"], { icon: string; title: string; detail: string; warn?: boolean }> = {
  technique: { icon: "📂", title: "Organized by technique",
    detail: "top folders are instruments/techniques (Raman, NMR, XRD …)." },
  sample: { icon: "🧪", title: "Organized by sample / compound",
    detail: "one folder per compound; the technique is read from each filename." },
  mixed: { icon: "🧩", title: "Mixed organization", warn: true,
    detail: "some data is in technique folders, some in sample folders." },
  unstructured: { icon: "⚠️", title: "Looks unstructured", warn: true,
    detail: "files aren't in recognizable technique or sample folders." },
  empty: { icon: "—", title: "Nothing recognized", warn: true, detail: "no data files matched." },
};

// First-pass report of how the source is laid out, with a prompt when PsiDataViz is unsure.
function OrgBanner({ org }: { org: Organization }) {
  const m = ORG_INFO[org.kind] ?? ORG_INFO.mixed;
  const uncertain =
    org.kind === "unstructured" || org.kind === "mixed" || org.unstructured > 0.15 * (org.total || 1);
  return (
    <div className={"org-banner" + (m.warn ? " warn" : "")}>
      <span className="org-icon">{m.icon}</span>
      <span>
        <b>{m.title}</b> — {m.detail}{" "}
        <span className="muted">
          ({org.by_technique} by technique · {org.by_sample} by sample
          {org.unstructured ? ` · ${org.unstructured} unplaced` : ""})
        </span>
        {uncertain && (
          <div className="org-uncertain">
            PsiDataViz couldn't confidently place {org.unstructured || "some"} dataset
            {org.unstructured === 1 ? "" : "s"} — focus the scan with a keyword filter above, or{" "}
            <a className="link" href="mailto:[email removed]?subject=PsiDataViz%20data%20structure">
              tell us how your data is organized
            </a>
            .
          </div>
        )}
      </span>
    </div>
  );
}

function Quick({ onNav }: { onNav: (v: View) => void }) {
  const [repo, setRepo] = useState(DEFAULT_REPO);
  const [keyword, setKeyword] = useState(""); // optional path keyword to limit a large scan
  const [src, setSrc] = useState(DEFAULT_REPO); // the source URL backing the current scan
  const [scan, setScan] = useState<ScanResult | null>(null);
  const [technique, setTechnique] = useState<string | null>(null);
  const [records, setRecords] = useState<RecordRow[]>([]);
  const [selected, setSelected] = useState<string[]>([]); // ordered record keys
  const [datasets, setDatasets] = useState<Record<string, DatasetData>>({});
  const [compare, setCompare] = useState<CompareResult | null>(null);
  const [filter, setFilter] = useState("");
  const [compoundFilter, setCompoundFilter] = useState<string | null>(null);
  const [normalize, setNormalize] = useState(false);
  const [peak, setPeak] = useState<{ freq: number; label: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showGuide, setShowGuide] = useState(false);

  async function run<T>(what: string, fn: () => Promise<T>): Promise<T | undefined> {
    setBusy(what);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  function clearSelection() {
    setSelected([]);
    setDatasets({});
    setCompare(null);
  }

  async function doScan(target?: string) {
    const url = (target ?? repo).trim();
    setRepo(url);
    setSrc(url);
    setScan(null);
    setTechnique(null);
    setRecords([]);
    clearSelection();
    const result = await run("Scanning data source…", () => api.scan(url, keyword));
    if (result) {
      setScan(result);
      const first = result.techniques.find((t) => t.n_supported > 0)?.technique;
      if (first) void pickTechnique(first, url);
    }
  }

  async function pickTechnique(t: string, source: string = src) {
    setTechnique(t);
    clearSelection();
    const rows = await run("Loading datasets…", () => api.records(source, t, keyword));
    if (rows) setRecords(rows);
  }

  async function toggleRecord(r: RecordRow) {
    setCompare(null);
    if (selected.includes(rid(r))) {
      setSelected(selected.filter((k) => k !== rid(r)));
      setDatasets((d) => {
        const next = { ...d };
        delete next[rid(r)];
        return next;
      });
      return;
    }
    const ds = await run("Parsing dataset…", () =>
      api.dataset(r.url, r.name, r.technique, r.sidecar_url),
    );
    if (ds) {
      setSelected((s) => [...s, rid(r)]);
      setDatasets((d) => ({ ...d, [rid(r)]: ds }));
    }
  }

  // switch which dataset of a multi-dataset zip is shown (reloads under the same record)
  async function loadMember(r: RecordRow, member: string | null) {
    const ds = await run("Loading dataset…", () =>
      api.dataset(r.url, r.name, r.technique, r.sidecar_url, member),
    );
    if (ds) setDatasets((d) => ({ ...d, [rid(r)]: ds }));
  }

  async function doCompare() {
    const r = selected.length === 1 ? records.find((x) => rid(x) === selected[0]) : null;
    if (!r) return;
    const res = await run("Comparing formats…", () => api.compare(src, r.technique, r.key));
    if (res) setCompare(res);
  }

  const selectedDatasets = selected.map((k) => datasets[k]).filter(Boolean);
  const audioDatasets = selectedDatasets.filter((d) => d.audio);
  // NMR (1D spectra + 2D contours) gets its own NMRium-style tabbed panel, grouped by nucleus
  const nmrDatasets = selectedDatasets.filter((d) => d.technique === "NMR");
  // audio carries waveform + FFT as signals, but they go to the player, not the overlay plot
  const signalDatasets = selectedDatasets.filter(
    (d) => d.signals?.length > 0 && !d.audio && d.technique !== "NMR",
  );
  const imageDatasets = selectedDatasets.filter((d) => d.images?.length > 0 && d.technique !== "NMR");
  const structureDatasets = selectedDatasets.filter((d) => d.structure);
  // datasets without a computed 3D structure can still get a molecule view from a guessed compound
  // Prefer a structure the source already knows (e.g. a Chemotion molecule's SMILES) over guessing
  // the compound from the filename — so every repository dataset shows its real structure.
  const knownSmiles = selected
    .map((id) => records.find((r) => rid(r) === id)?.smiles)
    .find((s): s is string => !!s);
  const compoundSeed =
    structureDatasets.length > 0
      ? ""
      : knownSmiles ??
        guessCompound(
          ((signalDatasets[0] ?? imageDatasets[0] ?? selectedDatasets[0])?.metadata.sample_name as string) ??
            (signalDatasets[0] ?? imageDatasets[0] ?? selectedDatasets[0])?.filename ??
            "",
        );
  // datasets to reproduce in a notebook: each selected record's source URL + name + technique (+ the
  // current archive member, for a multi-dataset zip)
  const notebookDatasets = selected
    .map((id) => {
      const r = records.find((x) => rid(x) === id);
      return r
        ? { name: r.name, url: r.url, technique: r.technique, member: datasets[id]?.bundle?.current }
        : null;
    })
    .filter((d): d is NonNullable<typeof d> => !!d);
  const soleRecord = selected.length === 1 ? records.find((r) => rid(r) === selected[0]) : null;
  const canCompare = !!soleRecord && soleRecord.formats.length > 1;
  const needle = filter.trim().toLowerCase();
  const shown = records.filter(
    (r) =>
      (!needle || r.description.toLowerCase().includes(needle) || (r.date ?? "").includes(needle)) &&
      (!compoundFilter || r.compound === compoundFilter),
  );

  return (
    <>
      <div className="hero">
        <div className="hero-mark" aria-label="Psi DataViz">
          <span className="bra">⟨Data|</span>
          <span className="psi">Ψ</span>
          <span className="ket">|Viz⟩</span>
        </div>
        <h1>Point at a data source</h1>
      </div>
      <p className="subtitle">
        Scan a public repository, overlay datasets, and compare formats —{" "}
        <span className="link" style={{ fontWeight: 600 }}>QUICK</span>.
      </p>
      <p className="nav-hint">
        Want advanced filtering and multi-source views, or richer plots and analysis? Continue to{" "}
        <a className="link" onClick={() => onNav("DATA")}>Ψ|Data⟩</a> and{" "}
        <a className="link" onClick={() => onNav("VIZ")}>Ψ|Viz⟩</a>.
      </p>

      <div className="row">
        <input
          type="text"
          value={repo}
          onChange={(e) => setRepo(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && doScan()}
          placeholder="GitHub repo (owner/repo) or a public Google Drive folder URL"
        />
        <input
          type="text"
          className="filter kw"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && doScan()}
          placeholder="keyword filter (optional)"
          title="Only scan files whose path contains this — useful for very large repos"
        />
        <button className="btn" onClick={() => doScan()} disabled={!!busy}>
          Scan
        </button>
      </div>
      <div className="source-groups">
        {SOURCE_GROUPS.map((g) => (
          <div className="source-group" key={g.key}>
            <div className="source-group-head">
              <b>{g.title}</b>
              <span className="muted">{g.blurb}</span>
            </div>
            <div className="presets">
              {g.presets.map((p) => (
                <button
                  key={p.url}
                  className="src-chip"
                  onClick={() => doScan(p.url)}
                  disabled={!!busy}
                  title={p.url}
                >
                  <ProviderIcon id={p.provider} size={18} />
                  {p.label}
                </button>
              ))}
              {g.key === "host" && (
                <a className="link" style={{ marginLeft: "auto" }} onClick={() => setShowGuide(true)}>
                  How to share a public link?
                </a>
              )}
            </div>
          </div>
        ))}
      </div>
      <p className="tested-note">
        PsiDataViz promotes <b>FAIR</b> data (Findable, Accessible, Interoperable, Reusable) — browse
        repositories and resources at{" "}
        <a className="link" href="https://fairsharing.org/" target="_blank" rel="noreferrer">
          fairsharing.org
        </a>
        . <span className="muted">More open repositories &amp; private sources are in the works.</span>
      </p>

      <div className="card repo-search-card">
        <div className="repo-search-head">
          <b>🔎 Search open FAIR repositories</b>
          <span className="muted">Find published, DOI-minted datasets and visualize them directly.</span>
        </div>
        <RepoSearch onPick={(url) => doScan(url)} busy={!!busy} />
      </div>

      {busy && <p className="spinner">{busy}</p>}
      {error && <p className="error">{error}</p>}

      {showGuide && (
        <div className="modal-overlay" onClick={() => setShowGuide(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <h2><span className="psi">Ψ</span> Connect a data source</h2>
              <button className="modal-close" onClick={() => setShowGuide(false)} aria-label="Close">
                ×
              </button>
            </div>
            <ConnectGuide
              onTryExample={(url) => {
                setShowGuide(false);
                doScan(url);
              }}
            />
          </div>
        </div>
      )}

      {scan && (
        <div className="card">
          <p>
            <b>{scan.n_data_records.toLocaleString()}</b> datasets from{" "}
            {scan.n_files.toLocaleString()} files —{" "}
            <span className="muted">
              files sharing a base name across formats count as one dataset.
            </span>
          </p>
          <OrgBanner org={scan.organization} />
          <div className="dim-section">
            <div className="dim-head">
              <span className="bra">⟨Data|</span><span className="psi">Ψ</span>
              <span className="ket">|Technique⟩</span>
            </div>
            <div className="chips">
              {scan.techniques
                .filter((t) => t.n_supported > 0)
                .map((t) => (
                  <span
                    key={t.technique}
                    className={"chip" + (t.technique === technique ? " active" : "")}
                    onClick={() => pickTechnique(t.technique)}
                  >
                    {t.technique}
                    <span className="count">{t.n_supported}</span>
                  </span>
                ))}
            </div>
          </div>
          {scan.compounds.length > 0 && (
            <div className="dim-section">
              <div className="dim-head">
                <span className="bra">⟨Data|</span><span className="psi">Ψ</span>
                <span className="ket">|Compound⟩</span>
              </div>
              <div className="chips compounds">
                {scan.compounds.map((c) => (
                  <span
                    key={c.compound}
                    className={"chip compound" + (c.compound === compoundFilter ? " active" : "")}
                    onClick={() => setCompoundFilter(compoundFilter === c.compound ? null : c.compound)}
                    title="Filter the table to this compound"
                  >
                    {c.compound}
                    <span className="count">{c.n_supported}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {scan && <Diagnostics d={scan.diagnostics} />}

      {records.length > 0 && (
        <div className="card with-brand">
          <PanelBrand label="PsiData" />
          <div className="toolbar">
            <span className="section-title" style={{ margin: 0 }}>
              {technique} datasets ({needle ? `${shown.length} of ${records.length}` : records.length}){" "}
              <span className="muted">— click to overlay</span>
            </span>
            <input
              type="text"
              className="filter"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="filter by sample or date…"
            />
          </div>
          <div className="scroll">
            <table>
              <thead>
                <tr>
                  <th style={{ width: 28 }}></th>
                  <th>Date</th>
                  <th>Compound</th>
                  <th>Sample / description</th>
                  <th>Formats</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((r) => (
                  <tr
                    key={rid(r)}
                    className={selected.includes(rid(r)) ? "selected" : ""}
                    onClick={() => toggleRecord(r)}
                  >
                    <td>
                      <input type="checkbox" readOnly checked={selected.includes(rid(r))} />
                    </td>
                    <td>{r.date ?? ""}</td>
                    <td>{r.compound ? <span className="compound-tag">{r.compound}</span> : ""}</td>
                    <td>{r.description}</td>
                    <td className="fmt">
                      {r.formats.join(", ")}
                      {r.extras.length > 0 && <span className="extra"> (+{r.extras.join(", ")})</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {selectedDatasets.length > 0 && (
        <div className="card with-brand">
          <PanelBrand label="PsiViz" />
          <div className="toolbar">
            <span className="section-title" style={{ margin: 0 }}>
              {selectedDatasets.length} dataset{selectedDatasets.length === 1 ? "" : "s"} overlaid
            </span>
            <div className="row" style={{ gap: 12 }}>
              <label className="toggle">
                <input
                  type="checkbox"
                  checked={normalize}
                  onChange={(e) => setNormalize(e.target.checked)}
                />
                Normalize
              </label>
              {canCompare && (
                <button className="btn ghost" onClick={doCompare} disabled={!!busy}>
                  Compare formats
                </button>
              )}
              <NotebookMenu datasets={notebookDatasets} />
              <button className="btn ghost" onClick={clearSelection}>
                Clear
              </button>
            </div>
          </div>
          {nmrDatasets.length > 0 && (
            <NMRPanel
              datasets={nmrDatasets}
              normalize={normalize}
              onPeak={(freq, label) => setPeak({ freq, label })}
            />
          )}
          {signalDatasets.length > 0 && (
            <SpectrumPlot
              datasets={signalDatasets}
              normalize={normalize}
              onPeakClick={(freq, label) => setPeak({ freq, label })}
            />
          )}
          <LayoutTabs
            items={imageDatasets.map((ds) => {
              const matrix = ds.images.find((im) => im.kind === "matrix");
              return {
                key: ds.filename,
                label: (ds.metadata.sample_name as string) || ds.filename,
                node: matrix ? (
                  <MatrixSliceViewer dataset={ds} image={matrix} />
                ) : (
                  <Heatmap dataset={ds} />
                ),
              };
            })}
          />
          {structureDatasets.map((ds) => (
            <MoleculeViewer
              key={`mol-${ds.filename}`}
              structure={ds.structure!}
              title={(ds.metadata.sample_name as string) || ds.filename}
              peak={peak}
            />
          ))}
          {structureDatasets.length === 0 && selectedDatasets.length > 0 && (
            <CompoundViewer key={`cmp-${compoundSeed}`} initialQuery={compoundSeed} />
          )}
          {audioDatasets.map((ds) => (
            <WaveformPlayer key={`wav-${ds.filename}`} dataset={ds} />
          ))}
          {compare && (
            <div className="cmp-panel">
              <CompareView result={compare} />
            </div>
          )}
          {soleRecord && datasets[rid(soleRecord)] && (
            <>
              {datasets[rid(soleRecord)].bundle && (
                <div className="bundle-row">
                  <span className="muted">
                    {datasets[rid(soleRecord)].bundle!.members.length} datasets in this archive — show:
                  </span>
                  {datasets[rid(soleRecord)].bundle!.members.map((m) => (
                    <button
                      key={m.member ?? m.key}
                      className={`chip ${
                        m.member === datasets[rid(soleRecord)].bundle!.current ? "active" : ""
                      }`}
                      onClick={() => loadMember(soleRecord, m.member)}
                      title={m.formats.join(" · ")}
                    >
                      {m.key}
                    </button>
                  ))}
                </div>
              )}
              <div className="export-row">
                <span className="muted">Convert to standard format:</span>
                <ExportMenu
                  url={soleRecord.url}
                  name={soleRecord.name}
                  technique={soleRecord.technique}
                  dataset={datasets[rid(soleRecord)]}
                />
              </div>
              <Metadata meta={datasets[rid(soleRecord)].metadata} />
            </>
          )}
        </div>
      )}
    </>
  );
}

function Metadata({ meta }: { meta: Record<string, unknown> }) {
  const rows = Object.entries(meta).filter(([, v]) => typeof v !== "object");
  if (rows.length === 0) return null;
  return (
    <dl className="meta">
      {rows.map(([k, v]) => (
        <div style={{ display: "contents" }} key={k}>
          <dt>{k.replace(/_/g, " ")}</dt>
          <dd>{String(v)}</dd>
        </div>
      ))}
    </dl>
  );
}
