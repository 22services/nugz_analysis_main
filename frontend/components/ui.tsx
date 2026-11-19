"use client";

/*
  Primitives partagees.

  Regle d'accessibilite tenue partout dans ce fichier : la couleur ne porte
  jamais seule une information. Chaque etat a aussi un libelle et une forme.
  Un utilisateur daltonien, ou qui lit l'ecran de loin, doit pouvoir decider.
*/

import { useState, type ReactNode } from "react";
import type { Direction, RiskVerdict, AgentStatus } from "@/lib/api";
import type { Lang } from "@/lib/i18n";

// ---------------------------------------------------------------------
export function Section({
  title, intro, right, children,
}: {
  title: string; intro?: string; right?: ReactNode; children: ReactNode;
}) {
  return (
    <section className="mt-14">
      <div className="flex items-end justify-between gap-6 mb-1">
        <h2 className="text-[13px] font-semibold uppercase tracking-[0.18em] text-bone-500">
          {title}
        </h2>
        {right}
      </div>
      <div className="rule mb-5" />
      {intro && (
        <p className="text-[15px] text-bone-500 max-w-3xl mb-6 leading-relaxed">
          {intro}
        </p>
      )}
      {children}
    </section>
  );
}

// ---------------------------------------------------------------------
/** Petite aide contextuelle. Indispensable pour un public non initie. */
export function Help({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline-block align-middle">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        onBlur={() => setOpen(false)}
        aria-label={text}
        aria-expanded={open}
        className="ml-1.5 w-[18px] h-[18px] rounded-full border border-ink-500
                   text-bone-700 text-[11px] leading-none hover:border-brass-500
                   hover:text-brass-400 transition-colors"
      >
        ?
      </button>
      {open && (
        <span
          role="tooltip"
          className="absolute left-0 top-7 z-50 w-80 card-raised p-3.5 text-[14px]
                     leading-relaxed text-bone-300 font-normal normal-case
                     tracking-normal shadow-xl rise"
        >
          {text}
        </span>
      )}
    </span>
  );
}

// ---------------------------------------------------------------------
export const dirTone = (d: Direction | null | undefined) => {
  switch (d) {
    case "LONG":
      return { fg: "text-long-400", bg: "bg-long-900", bd: "border-long-500", raw: "#4fb286" };
    case "SHORT":
      return { fg: "text-short-400", bg: "bg-short-900", bd: "border-short-500", raw: "#d1614f" };
    default:
      return { fg: "text-hold-400", bg: "bg-hold-900", bd: "border-hold-500", raw: "#8b8578" };
  }
};

/** Marque geometrique : monte / descend / barre horizontale. */
export function DirectionMark({ d, size = 20 }: { d: Direction | null; size?: number }) {
  const tone = dirTone(d);
  const s = size;
  return (
    <svg width={s} height={s} viewBox="0 0 20 20" aria-hidden className="shrink-0">
      {d === "LONG" && <path d="M10 3 L17 14 L3 14 Z" fill={tone.raw} />}
      {d === "SHORT" && <path d="M10 17 L3 6 L17 6 Z" fill={tone.raw} />}
      {(d === "NO_TRADE" || d === "NEUTRAL" || !d) && (
        <rect x="3" y="8.5" width="14" height="3" fill={tone.raw} />
      )}
    </svg>
  );
}

// ---------------------------------------------------------------------
export function Pill({
  label, tone = "neutral", mono = false,
}: {
  label: string;
  tone?: "neutral" | "good" | "bad" | "warn" | "brass" | "muted";
  mono?: boolean;
}) {
  const tones = {
    neutral: "border-ink-500 text-bone-300",
    good: "border-long-500 text-long-400 bg-long-900",
    bad: "border-short-500 text-short-400 bg-short-900",
    warn: "border-warn-500 text-warn-400 bg-warn-900",
    brass: "border-brass-600 text-brass-400",
    muted: "border-ink-600 text-bone-700",
  }[tone];
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-[3px] border rounded-pill
                  text-[12px] font-medium uppercase tracking-wider ${tones}
                  ${mono ? "num" : ""}`}
    >
      {label}
    </span>
  );
}

// ---------------------------------------------------------------------
/**
 * Jauge de conviction segmentee.
 *
 * Deliberement en segments plutot qu'en barre continue : une barre pleine
 * suggere une mesure continue et fiable. Vingt crans disent "estimation
 * graduee", ce qui est exactement ce qu'est ce score.
 */
export function ConvictionMeter({
  value, direction, compact = false,
}: { value: number; direction: Direction | null; compact?: boolean }) {
  const tone = dirTone(direction);
  const segs = 20;
  const filled = Math.round((value / 100) * segs);
  return (
    <div className="flex items-center gap-[3px]" role="img" aria-label={`${value} / 100`}>
      {Array.from({ length: segs }, (_, i) => (
        <span
          key={i}
          className={`block rounded-[1px] ${compact ? "w-[4px] h-3" : "w-[7px] h-5"}`}
          style={{
            background: i < filled ? tone.raw : "#2b2620",
            opacity: i < filled ? 1 - (i / segs) * 0.35 : 1,
          }}
        />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------
export function StatusDot({ status }: { status: AgentStatus }) {
  const map: Record<AgentStatus, { c: string; anim: string }> = {
    IDLE: { c: "#3a342c", anim: "" },
    RUNNING: { c: "#c8a055", anim: "pulse-soft" },
    DONE: { c: "#4fb286", anim: "" },
    BLOCKED: { c: "#d1614f", anim: "" },
    SKIPPED: { c: "#6b6358", anim: "" },
    FAILED: { c: "#d1614f", anim: "" },
  };
  const s = map[status];
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full shrink-0 ${s.anim}`}
      style={{ background: s.c }}
      aria-hidden
    />
  );
}

// ---------------------------------------------------------------------
export function VerdictBadge({ v, lang }: { v: RiskVerdict; lang: Lang }) {
  const label = {
    APPROVED: { fr: "Approuvé", en: "Approved" },
    REDUCE: { fr: "Taille réduite", en: "Size reduced" },
    REJECT: { fr: "Rejeté", en: "Rejected" },
  }[v][lang];
  const tone = v === "APPROVED" ? "good" : v === "REDUCE" ? "warn" : "bad";
  return <Pill label={label} tone={tone as "good" | "warn" | "bad"} />;
}

// ---------------------------------------------------------------------
/** Etiquette + valeur, alignee en colonnes. Le motif de base du tableau. */
export function Stat({
  label, value, sub, tone, help,
}: {
  label: string; value: string; sub?: string; tone?: string; help?: string;
}) {
  return (
    <div>
      <div className="text-[12px] uppercase tracking-[0.14em] text-bone-700 mb-1.5">
        {label}
        {help && <Help text={help} />}
      </div>
      <div className={`num text-[22px] leading-none ${tone ?? "text-bone-100"}`}>
        {value}
      </div>
      {sub && <div className="text-[13px] text-bone-500 mt-1.5">{sub}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------
export function Toggle<T extends string>({
  options, value, onChange, ariaLabel,
}: {
  options: { id: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  ariaLabel: string;
}) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className="inline-flex border border-ink-600 rounded-pill overflow-hidden"
    >
      {options.map((o) => (
        <button
          key={o.id}
          type="button"
          onClick={() => onChange(o.id)}
          aria-pressed={value === o.id}
          className={`px-3 py-1.5 text-[13px] font-medium transition-colors ${
            value === o.id
              ? "bg-brass-500 text-ink-900"
              : "text-bone-500 hover:text-bone-300 hover:bg-ink-700"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------
/** Sparkline sobre : pas d'axes, pas de grille, juste la forme du prix. */
export function Sparkline({
  values, stroke = "#c8a055", width = 160, height = 40,
}: { values: number[]; stroke?: string; width?: number; height?: number }) {
  if (values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pts = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * width;
      const y = height - ((v - min) / span) * height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <svg width={width} height={height} aria-hidden className="overflow-visible">
      <polyline points={pts} fill="none" stroke={stroke} strokeWidth="1.5"
                strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

// ---------------------------------------------------------------------
/**
 * Barre d'onglets.
 *
 * Le dashboard montrait tout sur une seule colonne, ce qui noyait la
 * décision sous le détail. Les onglets rendent la hiérarchie explicite :
 * on arrive sur la décision, on creuse si on veut.
 */
export function Tabs<T extends string>({
  tabs, value, onChange,
}: {
  tabs: { id: T; label: string; badge?: string | number }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <nav
      role="tablist"
      aria-label="Sections"
      className="flex gap-1 overflow-x-auto -mb-px"
    >
      {tabs.map((tab) => {
        const active = tab.id === value;
        return (
          <button
            key={tab.id}
            role="tab"
            type="button"
            aria-selected={active}
            onClick={() => onChange(tab.id)}
            className={`relative shrink-0 px-4 py-3 text-[15px] font-medium
                        border-b-[3px] transition-colors whitespace-nowrap ${
              active
                ? "border-brass-500 text-bone-100"
                : "border-transparent text-bone-700 hover:text-bone-300"
            }`}
          >
            {tab.label}
            {tab.badge != null && (
              <span className={`num ml-2 text-[12px] px-1.5 py-[1px] rounded-pill ${
                active ? "bg-brass-500 text-ink-900" : "bg-ink-700 text-bone-700"
              }`}>
                {tab.badge}
              </span>
            )}
          </button>
        );
      })}
    </nav>
  );
}

// ---------------------------------------------------------------------
/** Grand chiffre, pour les indicateurs qui doivent se lire de loin. */
export function BigStat({
  label, value, unit, tone, help, sub,
}: {
  label: string; value: string; unit?: string;
  tone?: string; help?: string; sub?: string;
}) {
  return (
    <div className="min-w-0">
      <div className="text-[11px] uppercase tracking-[0.16em] text-bone-700 mb-2">
        {label}
        {help && <Help text={help} />}
      </div>
      <div className="flex items-baseline gap-1.5">
        <span className={`num text-[34px] leading-none ${tone ?? "text-bone-100"}`}>
          {value}
        </span>
        {unit && <span className="num text-[15px] text-bone-700">{unit}</span>}
      </div>
      {sub && (
        <div className="text-[13px] text-bone-500 mt-2 leading-snug">{sub}</div>
      )}
    </div>
  );
}
