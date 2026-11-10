import { useEffect, useRef, useState } from "react";
import type { AnalyzeResponse } from "../lib/types";
import ExonTrackGraph from "./ExonTrackGraph";

// Legend entries map 1:1 to the CSS color tokens the graph reads via var(--…).
// Overriding a token on the card element cascades to both the swatch and the track.
const LEGEND = [
  { token: "--conv", label: "EEJ-independent" },
  { token: "--eej", label: "EEJ-dependent" },
  { token: "--hard", label: "Infeasible" },
  { [secret removed], label: "Primer target site" },
  // The two primer strategies are drawn as brackets on the track, and each owns its colour:
  // the single-EEJ bracket used to borrow the EEJ-dependent tier's, so recolouring the tier
  // moved the marker too and neither could be set independently of the other.
  { [secret removed], label: "Single EEJ primer" },
  { [secret removed], label: "Double EEJ primer pair" },
] as const;

// Spare colors offered beyond the tiers' default colors. Chosen to be visually distinct
// from every tier default (both themes) so a pick can't create a near-duplicate.
const SPARES = ["#16A34A", "#0D9488", "#F97316", "#EC4899", "#7C3AED", "#B45309"];

// "What is this" hover text for the three design markers — on the key under the graph, where
// each marker is named beside the mark it explains (the legend above the graph names tiers only).
const HINTS: Record<string, string> = {
  "--amp-pair": "Primer target site — the exon region to put your primer(s): an EEJ-independent "
    + "exon pair, or a junction+exon combo's discriminating exon region. Only sequence that "
    + "DISTINGUISHES the transcript is a primer target site.",
  "--eej-single": "Single EEJ primer — the one exon–exon junction a primer must span to be "
    + "specific to this transcript; the bracket joins the two exons it is spliced from.",
  "--eej-combo": "Double EEJ primer pair — two exon–exon junctions that together isolate this "
    + "transcript; both are marked and both junction primers are needed.",
};

/**
 * The palette cells: every tier's DEFAULT color, then any color a tier is CURRENTLY showing
 * that the defaults do not already cover, then spares up to nine.
 *
 * Both groups are required, for different reasons.
 *
 * Defaults, because a tier's default is the only source of a color like the Needs-EEJ red —
 * no other tier has it and it is not a spare. Keying the palette off the current colors alone
 * dropped that red the moment Needs EEJ moved away from it, leaving no way back.
 *
 * Currents, because a color a tier wears must stay pickable: `pick` swaps two tiers by
 * matching a cell against a tier's color, and the grid marks the open tier's cell as
 * selected. Neither can happen for a color with no cell. Current is normally already a
 * default or a spare — the exception is an override made under the other theme, which the
 * theme's own defaults do not include.
 *
 * Both must be READ FROM THE CASCADE rather than hardcoded: a literal that differs from the
 * token by even one digit is never an exact match, and the swap silently stops.
 */
export function buildCells(
  defaults: Record<string, string>,
  current: Record<string, string> = {},
): string[] {
  const seen = new Set<string>();
  const cells: string[] = [];
  const add = (c: string) => {
    const u = (c || "").trim().toUpperCase();
    if (!u || seen.has(u)) return;
    seen.add(u);
    cells.push(u);
  };
  // Defaults and currents are never dropped; only spares are trimmed to reach nine.
  for (const c of Object.values(defaults)) add(c);
  for (const c of Object.values(current)) add(c);
  for (const c of SPARES) { if (cells.length >= 9) break; add(c); }
  return cells;
}

export default function GraphCard({ result, onSelect }: {
  result: AnalyzeResponse;
  /** Clicking an accession in the graph re-targets the analysis to that transcript. */
  onSelect?: (accession: string) => void;
}) {
  const { gene, transcripts, target_accession, meta, primer_design } = result;
  const k = Number(meta.k) || 20;
  // exon that holds the target's conventional forward primer (for the "★ primer here" badge)
  let primerExon: number | null = null;
  const f = primer_design.forward;
  if (f && f.kind === "conventional") {
    const m = f.anchor.match(/exon (\d+)/);
    if (m) primerExon = Number(m[1]);
  }

  // Live, per-session color overrides keyed by token; applied as CSS custom properties.
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  // "legend:--eej" | "key:--eej" — the token alone would open both copies at once.
  const [openToken, setOpenToken] = useState<string | null>(null);
  // Each token's current effective color (override or CSS default), captured when a palette opens.
  const [effective, setEffective] = useState<Record<string, string>>({});
  // Each token's DEFAULT color, i.e. what it would show with no override — the palette's base.
  const [defaults, setDefaults] = useState<Record<string, string>>({});
  const legendRef = useRef<HTMLDivElement>(null);
  // The overrides live on the card, and both the legend and the key sit inside it — so the
  // card is what resolves current colours and what "outside" means for a click.
  const cardRef = useRef<HTMLElement>(null);

  /** Resolve every token from the cascade at `el`. Both reads happen when a palette opens,
   *  so a theme switch between opens is picked up. */
  const readTokens = (el: Element | null): Record<string, string> => {
    const out: Record<string, string> = {};
    if (el) {
      const cs = getComputedStyle(el);
      for (const { token } of LEGEND) out[token] = cs.getPropertyValue(token).trim().toUpperCase();
    }
    return out;
  };

  const openPalette = (id: string) =>
    setOpenToken((t) => {
      if (t === id) return null;
      // Effective from inside the card (overrides apply there); defaults from the root, which
      // the overrides never touch — reading both off the same element would return the same
      // thing and put the palette back to following the current colors.
      setEffective(readTokens(cardRef.current));
      setDefaults(readTokens(document.documentElement));
      return id;
    });

  // Close the palette on outside click or Escape.
  useEffect(() => {
    if (!openToken) return;
    const onDown = (e: MouseEvent) => {
      if (cardRef.current && !cardRef.current.contains(e.target as Node)) setOpenToken(null);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpenToken(null); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDown); document.removeEventListener("keydown", onKey); };
  }, [openToken]);

  const pick = (token: string, color: string) => {
    const target = color.toUpperCase();
    // Colors stay unique per section: if another section already shows this color, swap —
    // that section takes this one's current color instead of two sections sharing it.
    const clash = LEGEND.find((l) => l.token !== token && effective[l.token] === target);
    setOverrides((o) => {
      const next = { ...o, [token]: color };
      if (clash) next[clash.token] = effective[token];
      return next;
    });
    setOpenToken(null);
  };

  const palette = (token: string, label: string, up = false) => (
    <div className={`sw-pop${up ? " up" : ""}`} role="dialog" aria-label={`${label} color`}>
      <div className="sw-grid">
        {buildCells(defaults, effective).map((c) => (
          <button
            type="button"
            key={c}
            className={`sw-cell${effective[token] === c ? " on" : ""}`}
            style={{ background: c }}
            aria-label={c}
            onClick={() => pick(token, c)}
          />
        ))}
      </div>
    </div>
  );

  /** A key entry: the glyph as it is drawn on the track, and clicking it recolours it. */
  const keyItem = (token: string, label: string, glyph: React.ReactNode) => (
    <span className="g-key" key={token}>
      <button type="button" className="g-key-btn"
        aria-label={`Change ${label} color`} title={HINTS[token]}
        aria-expanded={openToken === `key:${token}`}
        onClick={() => openPalette(`key:${token}`)}>
        {glyph} {label}
      </button>
      {openToken === `key:${token}` && palette(token, label, true)}
    </span>
  );

  const legendItem = ({ token, label }: { token: string; label: string }) => (
    <span className="lg" key={token} style={{ position: "relative" }}>
      <button
        type="button"
        className="sw sw-btn"
        style={{ background: `var(${token})` }}
        aria-label={`Change ${label} color`}
        aria-expanded={openToken === `legend:${token}`}
        onClick={() => openPalette(`legend:${token}`)}
      />
      {label}
      {openToken === `legend:${token}` && palette(token, label)}
    </span>
  );

  return (
    <section className="card" ref={cardRef} style={overrides as React.CSSProperties}>
      <div className="card-head">
        <div>
          <h3 className="card-title">
            Exon structure — all {gene.symbol} isoforms <StrandBadge strand={gene.strand} />
          </h3>
          <p className="sub">{gene.assembly} · colored by amplification tier</p>
        </div>
        {/* The three tiers only. The three design markers are named — and recoloured — in the
            key under the graph, beside the marks themselves; a second row here said the same
            thing twice. */}
        <div className="legend" ref={legendRef}>{LEGEND.slice(0, 3).map(legendItem)}</div>
      </div>
      <ExonTrackGraph transcripts={transcripts} targetAccession={target_accession} primerExon={primerExon} chromosome={gene.chromosome} strand={gene.strand} mrna={result.target_mrna} excluded={result.excluded} onSelect={onSelect} />
      {/* A key, not a paragraph: each marker gets the short name of what it means, drawn in
          the same ink it uses on the track. The long explanation of WHY a bracket marks a
          range rather than a spot lives in the marker's own hover text on the graph. */}
      {/* Each entry is drawn in the ink it uses on the track AND recolours it: the key is
          where a reader is already looking at the mark they want to change, so making them
          go back up to the legend swatch for the same token is a detour. */}
      <p className="g-note">
        {keyItem("--eej-single", "Single EEJ primer", <BracketGlyph />)}
        <span className="g-sep">·</span>
        {keyItem("--eej-combo", "Double EEJ primer pair", <BracketGlyph combo />)}
        <span className="g-sep">·</span>
        {keyItem("--amp-pair", "Primer target site", <TargetGlyph />)}
        <span className="g-sep">·</span>
        window size k={k}
      </p>
    </section>
  );
}

/**
 * Which genomic strand the gene is transcribed from. Worth stating next to the graph
 * because the axis is genomic-ascending in both cases: on a minus-strand gene exon 1 is
 * the RIGHTMOST block, so a reader who assumes left-to-right reads the structure backwards.
 * Renders nothing when NCBI states no orientation.
 */
function StrandBadge({ strand }: { strand?: string }) {
  if (strand !== "+" && strand !== "-") return null;
  const minus = strand === "-";
  const label = minus
    ? "Minus strand — transcribed right to left across this graph, so exon 1 is the rightmost block."
    : "Plus strand — transcribed left to right across this graph, so exon 1 is the leftmost block.";
  return (
    <span className={`strand-badge${minus ? " minus" : ""}`} title={label} aria-label={label}>
      <span className="mono">{strand}</span> strand {minus ? "←" : "→"}
    </span>
  );
}

/* The graph marker, drawn the same way in the key as on the track — a text glyph (⌐¬)
   renders too inconsistently across fonts to stand in for it. The bracket takes
   the colour of the design it marks: one junction (red) or a two-junction pair (magenta),
   matching the tokens the track itself strokes them with. */
export function BracketGlyph({ combo = false }: { combo?: boolean }) {
  return (
    <svg className="g-glyph" width="20" height="9" viewBox="0 0 20 9" role="img"
      aria-label={combo ? "double EEJ bracket" : "single EEJ bracket"}>
      <path d="M2 8 L2 2 L18 2 L18 8" fill="none"
        stroke={combo ? "var(--eej-combo)" : "var(--eej-single)"} strokeWidth="2"
        strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** The target-site box, in the same yellow the track fills an exon region with. */
export function TargetGlyph() {
  return (
    <svg className="g-glyph" width="14" height="10" viewBox="0 0 14 10" role="img"
      aria-label="yellow box">
      <rect x="1" y="1" width="12" height="8" rx="2" fill="var(--amp-pair)" />
    </svg>
  );
}
