"use client";

/*
  Le comite, rendu comme un pipeline et non comme une grille de cartes.

  La disposition porte l'architecture : un agent de donnees qui alimente
  tout le monde, quatre analystes qui travaillent EN PARALLELE (d'ou le
  groupe encadre), puis un Red Team, un Risk Manager avec droit de veto, et
  enfin le CIO. Une grille 4x2 aurait suggere huit avis equivalents, ce qui
  est exactement le raisonnement que le PDF interdit.
*/

import { useState } from "react";
import type { AgentCard, AgentOutput, Run } from "@/lib/api";
import { type Lang, type Mode, t, tr } from "@/lib/i18n";
import {
  ConvictionMeter, DirectionMark, Help, Pill, StatusDot, dirTone,
} from "./ui";

const STAGE_LABEL: Record<string, { fr: string; en: string }> = {
  DATA: { fr: "1 — Fondation", en: "1 — Foundation" },
  ANALYSIS: { fr: "2 — Analyse (en parallèle)", en: "2 — Analysis (in parallel)" },
  RED_TEAM: { fr: "3 — Contradiction", en: "3 — Challenge" },
  RISK: { fr: "4 — Contrôle du risque", en: "4 — Risk control" },
  DECISION: { fr: "5 — Décision", en: "5 — Decision" },
};

const ORDER: string[] = ["DATA", "ANALYSIS", "RED_TEAM", "RISK", "DECISION"];

export default function Committee({
  cards, run, lang, mode,
}: {
  cards: AgentCard[]; run: Run | null; lang: Lang; mode: Mode;
}) {
  const [open, setOpen] = useState<string | null>(null);

  const groups = ORDER.map((stage) => ({
    stage,
    label: STAGE_LABEL[stage][lang],
    agents: cards.filter((c) => c.stage === stage).sort((a, b) => a.order - b.order),
  })).filter((g) => g.agents.length > 0);

  return (
    <div className="space-y-3">
      {groups.map((g, gi) => (
        <div key={g.stage}>
          <div className="flex items-center gap-3 mb-2">
            <span className="text-[11px] uppercase tracking-[0.2em] text-bone-700">
              {g.label}
            </span>
            <span className="flex-1 border-t border-ink-700" />
          </div>

          <div
            className={
              g.agents.length > 1
                ? "grid gap-2 md:grid-cols-2 xl:grid-cols-4 border-l-2 border-brass-600/40 pl-3"
                : "grid gap-2"
            }
          >
            {g.agents.map((c) => (
              <AgentTile
                key={c.id}
                card={c}
                out={run?.outputs?.[c.id] ?? null}
                lang={lang}
                mode={mode}
                expanded={open === c.id}
                onToggle={() => setOpen(open === c.id ? null : c.id)}
              />
            ))}
          </div>

          {gi < groups.length - 1 && (
            <div className="flex justify-center py-1.5" aria-hidden>
              <svg width="12" height="16" viewBox="0 0 12 16">
                <path d="M6 0 V11 M2 8 L6 12 L10 8" stroke="#3a342c"
                      strokeWidth="1.5" fill="none" />
              </svg>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------
function AgentTile({
  card, out, lang, mode, expanded, onToggle,
}: {
  card: AgentCard; out: AgentOutput | null; lang: Lang; mode: Mode;
  expanded: boolean; onToggle: () => void;
}) {
  const status = out?.status ?? "IDLE";
  const tone = dirTone(out?.direction);
  const blocked = status === "BLOCKED" || status === "FAILED" || status === "SKIPPED";

  return (
    <div
      className={`card transition-colors ${
        expanded ? "border-brass-600" : "hover:border-ink-500"
      } ${blocked ? "opacity-65" : ""}`}
    >
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        className="w-full text-left p-3.5"
      >
        <div className="flex items-start gap-2.5">
          <span className="num text-[11px] text-bone-700 mt-[3px] w-4 shrink-0">
            {String(card.order).padStart(2, "0")}
          </span>

          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-semibold text-[15px] leading-tight">
                {t(card.name, lang)}
              </span>
              <StatusDot status={status} />
              {card.can_veto && (
                <span className="text-[10px] uppercase tracking-wider text-short-400
                                 border border-short-500 px-1.5 rounded-pill">
                  {tr("canVeto", lang)}
                </span>
              )}
            </div>

            <div className="text-[13px] text-bone-700 mt-0.5">
              {t(card.role, lang)}
            </div>

            {out?.headline && (
              <p className={`text-[14px] mt-2 leading-snug ${
                blocked ? "text-bone-500" : "text-bone-300"
              }`}>
                {t(out.headline, lang)}
              </p>
            )}

            {out?.conviction != null && out.conviction > 0 && (
              <div className="flex items-center gap-2.5 mt-2.5">
                <ConvictionMeter value={out.conviction} direction={out.direction} compact />
                <span className={`num text-[13px] ${tone.fg}`}>{out.conviction}</span>
              </div>
            )}

            {out?.warnings && out.warnings.length > 0 && (
              <div className="mt-2 text-[12px] text-warn-400">
                {out.warnings.length} {lang === "fr" ? "avertissement(s)" : "warning(s)"}
              </div>
            )}
          </div>

          <span className={`text-bone-700 text-[13px] shrink-0 transition-transform ${
            expanded ? "rotate-90" : ""
          }`} aria-hidden>
            ›
          </span>
        </div>
      </button>

      {expanded && <AgentDetail card={card} out={out} lang={lang} mode={mode} />}
    </div>
  );
}

// ---------------------------------------------------------------------
function AgentDetail({
  card, out, lang, mode,
}: { card: AgentCard; out: AgentOutput | null; lang: Lang; mode: Mode }) {
  return (
    <div className="px-3.5 pb-4 pt-1 border-t border-ink-600 space-y-4 rise">
      {/* En clair : toujours visible, c'est la porte d'entree des debutants */}
      <Field label={tr("plainWords", lang)}>
        <p className="text-[15px] text-bone-300 leading-relaxed">
          {t(card.plain, lang)}
        </p>
      </Field>

      {mode === "expert" && (
        <Field label={tr("mandate", lang)}>
          <p className="text-[14px] text-bone-500 leading-relaxed">
            {t(card.mandate, lang)}
          </p>
        </Field>
      )}

      {out?.detail && (
        <Field label={tr("reading", lang)}>
          <p className="text-[14px] text-bone-300 leading-relaxed">
            {t(out.detail, lang)}
          </p>
        </Field>
      )}

      {out?.evidence && out.evidence.length > 0 && (
        <Field label={tr("evidence", lang)}>
          <ul className="space-y-2">
            {out.evidence.map((e, i) => (
              <li key={i} className="grid grid-cols-[1fr_auto] gap-3 items-baseline
                                     border-b border-ink-700 pb-2 last:border-0">
                <div>
                  <div className="text-[14px] text-bone-100">{t(e.label, lang)}</div>
                  <div className="text-[13px] text-bone-500 leading-snug mt-0.5">
                    {t(e.reading, lang)}
                  </div>
                </div>
                <span className={`num text-[14px] ${dirTone(e.supports).fg}`}>
                  {e.value}
                </span>
              </li>
            ))}
          </ul>
        </Field>
      )}

      {out?.warnings && out.warnings.length > 0 && (
        <Field label={tr("warnings", lang)}>
          <ul className="space-y-1.5">
            {out.warnings.map((w, i) => (
              <li key={i} className="text-[14px] text-warn-400 leading-snug
                                     border-l-2 border-warn-500 pl-2.5">
                {t(w, lang)}
              </li>
            ))}
          </ul>
        </Field>
      )}

      {/* Les outils : declares mais pas branches. Le dire explicitement
          evite toute ambiguite sur ce que le systeme sait reellement. */}
      <Field label={`${tr("tools", lang)} · ${card.tools.length}`}>
        <ul className="space-y-1.5">
          {card.tools.map((tool) => (
            <li key={tool.name} className="flex items-start gap-2 text-[13px]">
              <span className="w-1.5 h-1.5 rounded-full bg-ink-500 mt-[7px] shrink-0" />
              <span className="flex-1">
                <span className="text-bone-300">{tool.name}</span>
                <span className="text-bone-700"> · {tool.provider}</span>
                <span className="block text-bone-700 text-[12px]">
                  {t(tool.purpose, lang)}
                </span>
              </span>
              <Pill label={tr("notConnected", lang)} tone="muted" />
            </li>
          ))}
        </ul>
      </Field>

      <div className="flex items-center gap-2 pt-1">
        <Pill
          label={card.model_hint.includes("déterministe")
            ? tr("deterministic", lang)
            : card.model_hint}
          tone={card.model_hint.includes("déterministe") ? "brass" : "neutral"}
        />
        {out?.duration_ms != null && (
          <span className="num text-[12px] text-bone-700">{out.duration_ms} ms</span>
        )}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-[0.16em] text-bone-700 mb-1.5">
        {label}
      </div>
      {children}
    </div>
  );
}
