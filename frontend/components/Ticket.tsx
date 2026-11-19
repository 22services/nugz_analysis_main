"use client";

/*
  Le Trade Ticket, rendu comme la note de comite qu'il est.

  D'ou le serif pour la these et le contre-argumentaire : ce bloc se LIT,
  il ne se scanne pas. Le reste du document reste en mono/sans parce que
  ce sont des donnees, pas de la prose.
*/

import type { TradeTicket, TicketSection } from "@/lib/api";
import { type Lang, t, tr } from "@/lib/i18n";
import { DirectionMark, Pill, VerdictBadge, dirTone } from "./ui";

export default function Ticket({ ticket, lang }: { ticket: TradeTicket; lang: Lang }) {
  const tone = dirTone(ticket.final_decision);
  const ts = new Date(ticket.timestamp);

  return (
    <article className="card overflow-hidden">
      {/* En-tete : identification du document */}
      <header className="px-6 py-4 border-b border-ink-600 flex flex-wrap
                         items-center justify-between gap-4 bg-ink-850">
        <div>
          <div className="text-[11px] uppercase tracking-[0.2em] text-brass-500">
            {lang === "fr"
              ? "Or — Comité d'investissement"
              : "Gold — Investment Committee"}
          </div>
          <div className="num text-[15px] text-bone-100 mt-1">
            {ticket.instrument} {ticket.contract} · {ticket.horizon}
          </div>
        </div>
        <div className="text-right">
          <div className="num text-[13px] text-bone-500">
            {ts.toLocaleDateString(lang === "fr" ? "fr-FR" : "en-GB")}{" "}
            {ts.toLocaleTimeString(lang === "fr" ? "fr-FR" : "en-GB", {
              hour: "2-digit", minute: "2-digit",
            })}{" "}
            UTC
          </div>
          <div className="mt-1.5">
            <VerdictBadge v={ticket.risk_verdict} lang={lang} />
          </div>
        </div>
      </header>

      {/* Regime de marche */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 border-b border-ink-600">
        {[
          [tr("trend", lang), t(ticket.trend, lang)],
          [tr("volatility", lang), t(ticket.volatility, lang)],
          [tr("macroRegime", lang), t(ticket.macro_regime, lang)],
          [tr("eventRisk", lang), t(ticket.event_risk, lang)],
        ].map(([label, value], i) => (
          <div key={i} className="px-5 py-3.5 border-r border-ink-700 last:border-r-0">
            <div className="text-[11px] uppercase tracking-[0.14em] text-bone-700 mb-1">
              {label}
            </div>
            <div className="text-[14px] text-bone-300 leading-snug">{value}</div>
          </div>
        ))}
      </div>

      {/* These : le coeur du document */}
      <div className="px-6 py-5 border-b border-ink-600">
        <div className="flex items-center gap-3 mb-3">
          <DirectionMark d={ticket.final_decision} size={18} />
          <span className={`text-[15px] font-semibold uppercase tracking-wider ${tone.fg}`}>
            {ticket.final_decision === "NO_TRADE"
              ? tr("noTradeTitle", lang)
              : ticket.final_decision}
          </span>
          <span className="text-[11px] uppercase tracking-[0.16em] text-bone-700">
            {tr("thesis", lang)}
          </span>
        </div>
        <p className="serif text-[18px] leading-relaxed text-bone-100 max-w-3xl">
          {t(ticket.thesis, lang)}
        </p>
      </div>

      {/* Blocs d'analyse */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 border-b border-ink-600">
        {[ticket.technical, ticket.macro, ticket.futures, ticket.catalysts].map(
          (s: TicketSection, i) => (
            <div key={i} className="px-5 py-4 border-r border-ink-700 last:border-r-0">
              <div className="text-[11px] uppercase tracking-[0.14em] text-brass-500 mb-2.5">
                {t(s.title, lang)}
              </div>
              <dl className="space-y-1.5">
                {s.rows.map(([k, v], j) => (
                  <div key={j} className="flex justify-between gap-3 items-baseline">
                    <dt className="text-[13px] text-bone-700 truncate">{k}</dt>
                    <dd className="num text-[13px] text-bone-300 shrink-0">{v}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )
        )}
      </div>

      {/* Pour / contre : deliberement cote a cote, a poids visuel egal */}
      <div className="grid md:grid-cols-2 border-b border-ink-600">
        <Argument
          title={tr("bullCase", lang)}
          items={ticket.bull_case.map((x) => t(x, lang))}
          accent="border-long-500"
        />
        <Argument
          title={tr("bearCase", lang)}
          items={ticket.bear_case.map((x) => t(x, lang))}
          accent="border-short-500"
          bordered
        />
      </div>

      {/* Invalidation */}
      <div className="px-6 py-5 border-b border-ink-600">
        <div className="text-[11px] uppercase tracking-[0.16em] text-warn-400 mb-3">
          {tr("invalidation", lang)}
        </div>
        <ol className="space-y-2">
          {ticket.invalidation.map((x, i) => (
            <li key={i} className="flex gap-3 text-[15px] text-bone-300 leading-snug">
              <span className="num text-bone-700 shrink-0">{i + 1}.</span>
              <span>{t(x, lang)}</span>
            </li>
          ))}
        </ol>
      </div>

      {/* Structure du trade + risque */}
      <div className="grid md:grid-cols-2">
        <div className="px-6 py-5 border-b md:border-b-0 md:border-r border-ink-600">
          <div className="text-[11px] uppercase tracking-[0.16em] text-bone-700 mb-3">
            {tr("tradeStructure", lang)}
          </div>
          <Rows
            rows={[
              [tr("entryZone", lang), t(ticket.entry_zone, lang)],
              [tr("stopLogic", lang), t(ticket.stop_logic, lang)],
              [tr("targetLogic", lang), t(ticket.target_logic, lang)],
              [tr("timeStop", lang), t(ticket.time_stop, lang)],
            ]}
          />
        </div>
        <div className="px-6 py-5">
          <div className="text-[11px] uppercase tracking-[0.16em] text-bone-700 mb-3">
            {tr("riskSection", lang)}
          </div>
          <Rows
            rows={[
              [tr("riskBudget", lang), t(ticket.risk_budget, lang)],
              [tr("liquidity", lang), t(ticket.liquidity, lang)],
              [tr("eventRisk", lang), t(ticket.event_exposure, lang)],
            ]}
          />
        </div>
      </div>

      {/* Surveillance */}
      <footer className="px-6 py-5 border-t border-ink-600 bg-ink-850">
        <div className="text-[11px] uppercase tracking-[0.16em] text-bone-700 mb-2.5">
          {tr("monitoring", lang)}
        </div>
        <div className="flex flex-wrap gap-2">
          {ticket.monitoring.map((m, i) => (
            <span key={i} className="text-[13px] text-bone-500 border border-ink-600
                                     px-2.5 py-1 rounded-pill">
              {t(m, lang)}
            </span>
          ))}
        </div>
      </footer>
    </article>
  );
}

function Argument({
  title, items, accent, bordered,
}: { title: string; items: string[]; accent: string; bordered?: boolean }) {
  return (
    <div className={`px-6 py-5 ${bordered ? "md:border-l border-ink-600" : ""}`}>
      <div className="text-[11px] uppercase tracking-[0.16em] text-bone-700 mb-3">
        {title}
      </div>
      <ul className="space-y-2.5">
        {items.map((x, i) => (
          <li key={i} className={`serif text-[16px] leading-relaxed text-bone-300
                                  border-l-2 ${accent} pl-3`}>
            {x}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Rows({ rows }: { rows: [string, string][] }) {
  return (
    <dl className="space-y-2.5">
      {rows.map(([k, v], i) => (
        <div key={i}>
          <dt className="text-[12px] uppercase tracking-[0.12em] text-bone-700">{k}</dt>
          <dd className="text-[14px] text-bone-300 leading-snug mt-0.5">{v}</dd>
        </div>
      ))}
    </dl>
  );
}
