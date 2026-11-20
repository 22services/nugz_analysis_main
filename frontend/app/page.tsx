"use client";

/*
  Trois onglets, rien de plus :

    1. Décision 15 min  — le comité (VWAP, profil de volume, ATR, structure,
                          contexte OpenBB) tranche à chaque barre close
    2. OpenBB           — le terminal de marché en données réelles
    3. Graphique        — les patterns surlignés, chacun avec sa statistique

  On arrive sur la décision ; on ne creuse que si on le veut.
*/

import { useState } from "react";
import DecisionTab from "@/components/DecisionTab";
import PatternsTab from "@/components/PatternsTab";
import Terminal from "@/components/Terminal";
import { DirectionMark, Tabs, Toggle, dirTone } from "@/components/ui";
import type { Decision } from "@/lib/api";
import { type Lang, type TabId, t, tr } from "@/lib/i18n";

export default function Page() {
  const [lang, setLang] = useState<Lang>("fr");
  const [tab, setTab] = useState<TabId>("decision");
  const [d, setD] = useState<Decision | null>(null);

  const tone = dirTone(d?.decision);
  const tabs = [
    { id: "decision" as TabId, label: tr("tabDecision", lang) },
    { id: "openbb" as TabId, label: tr("tabOpenBB", lang) },
    { id: "chart" as TabId, label: tr("tabChart", lang) },
  ];

  return (
    <main className="min-h-dvh relative z-10">
      <header className="sticky top-0 z-40 bg-ink-900/95 backdrop-blur-sm border-b border-ink-600">
        <div className="mx-auto max-w-[1360px] px-4 sm:px-5 lg:px-8 pt-3
                        flex flex-wrap items-center gap-x-6 gap-y-2">
          <div className="flex items-center gap-3">
            <GoldMark />
            <div>
              <div className="text-[15px] font-semibold leading-none">{tr("appTitle", lang)}</div>
              <div className="text-[12px] text-bone-700 leading-none mt-1 hidden sm:block">
                {tr("instrument", lang)}
              </div>
            </div>
          </div>

          {d && (
            <div className="flex items-baseline gap-2.5">
              <span className="num text-[22px] sm:text-[24px] leading-none">
                {d.market.price.toLocaleString(lang === "fr" ? "fr-FR" : "en-US", { minimumFractionDigits: 2 })}
              </span>
              <span className={`flex items-center gap-1.5 text-[13px] font-semibold ${tone.fg}`}>
                <DirectionMark d={d.decision} size={13} />
                {d.decision === "LONG" ? tr("longLabel", lang)
                  : d.decision === "SHORT" ? tr("shortLabel", lang) : tr("noTradeTitle", lang)}
              </span>
              <span className="hidden md:inline text-[12px] text-bone-700">
                {t(d.market.session_label, lang)}
              </span>
            </div>
          )}

          <div className="flex-1" />

          <div className="flex items-center gap-3">
            <span className="hidden sm:flex items-center gap-1.5 text-[12px] text-long-400 num">
              <span aria-hidden className="w-1.5 h-1.5 rounded-full bg-long-500 pulse-soft" />
              {tr("liveData", lang)}
            </span>
            <Toggle ariaLabel="Langue" value={lang} onChange={setLang}
              options={[{ id: "fr", label: "FR" }, { id: "en", label: "EN" }]} />
          </div>
        </div>
        <div className="mx-auto max-w-[1360px] px-4 sm:px-5 lg:px-8 mt-1">
          <Tabs tabs={tabs} value={tab} onChange={setTab} />
        </div>
      </header>

      <div className="mx-auto max-w-[1360px] px-4 sm:px-5 lg:px-8 pb-20 pt-5">
        {/* La décision reste montée : le compte à rebours et le prix de
            l'en-tête continuent de vivre quand on change d'onglet. */}
        <div hidden={tab !== "decision"}><DecisionTab lang={lang} onPrice={setD} /></div>
        {tab === "openbb" && <Terminal lang={lang} />}
        {tab === "chart" && <PatternsTab lang={lang} />}

        <footer className="mt-10 pt-5 rule text-[12px] text-bone-700 flex flex-wrap justify-between gap-3">
          <span>{tr("footer", lang)}</span>
          {d && <span className="num">engine {d.engine_version}</span>}
        </footer>
      </div>
    </main>
  );
}

function GoldMark() {
  return (
    <svg width="30" height="30" viewBox="0 0 30 30" aria-hidden>
      <rect x="1" y="1" width="28" height="28" rx="3" fill="none" stroke="#a8843f" strokeWidth="1.5" />
      <path d="M8 20 L15 8 L22 20 Z" fill="none" stroke="#c8a055" strokeWidth="1.5" />
      <circle cx="15" cy="16.5" r="2" fill="#d9b26a" />
    </svg>
  );
}
