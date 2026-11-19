"use client";

/*
  Journal shadow + courbe de calibration.

  Le PDF est clair : c'est le journal, pas le dashboard, qui est le vrai
  livrable de la V1. Il repond a la seule question qui compte au bout de
  quelques mois : est-ce que ce systeme apporte quelque chose, et quels
  agents contribuent reellement ?

  La calibration compare la conviction annoncee au resultat obtenu. Tant que
  l'echantillon est insuffisant, on affiche l'absence de mesure plutot qu'un
  pourcentage rassurant calcule sur trois trades.
*/

import type { JournalResponse } from "@/lib/api";
import { type Lang, t, tr } from "@/lib/i18n";
import { DirectionMark, Help, Stat, dirTone } from "./ui";

export default function Journal({
  data, lang,
}: { data: JournalResponse; lang: Lang }) {
  const { stats, calibration, entries } = data;

  return (
    <div className="grid lg:grid-cols-[1fr_1.1fr] gap-4">
      {/* -- Chiffres de synthese ------------------------------------- */}
      <div className="space-y-4">
        <div className="card p-5 grid grid-cols-2 gap-5">
          <Stat
            label={tr("totalRuns", lang)}
            value={String(stats.total_runs)}
          />
          <Stat
            label={tr("decisions", lang)}
            value={String(stats.decisions)}
          />
          <Stat
            label={tr("noTradeRate", lang)}
            value={`${stats.no_trade_rate} %`}
            sub={tr("noTradeRateSub", lang)}
          />
          <Stat
            label={tr("avgConviction", lang)}
            value={stats.avg_conviction != null ? String(stats.avg_conviction) : "—"}
          />
        </div>

        {/* -- Calibration ------------------------------------------- */}
        <div className="card p-5">
          <div className="text-[12px] uppercase tracking-[0.14em] text-bone-700 mb-1">
            {tr("calibration", lang)}
            <Help text={tr("calibrationHelp", lang)} />
          </div>

          {!stats.sample_sufficient && (
            <p className="text-[14px] text-warn-400 border-l-2 border-warn-500
                          pl-3 my-3 leading-snug">
              {tr("notEnoughData", lang)}{" "}
              {lang === "fr"
                ? `${stats.closed} ${tr("closedOf", lang)}`
                : `${stats.closed} ${tr("closedOf", lang)}`}
            </p>
          )}

          <div className="space-y-2.5 mt-4">
            {calibration.map((b) => (
              <div key={b.lower} className="grid grid-cols-[62px_1fr_46px]
                                            gap-3 items-center">
                <span className="num text-[12px] text-bone-700">
                  {b.lower}–{b.upper === 101 ? 100 : b.upper}
                </span>
                <div className="h-5 bg-ink-700 rounded-[2px] overflow-hidden relative">
                  {b.observed_rate != null ? (
                    <div
                      className="h-full bg-brass-500"
                      style={{ width: `${b.observed_rate * 100}%` }}
                    />
                  ) : (
                    <div className="h-full w-full opacity-40"
                         style={{
                           backgroundImage:
                             "repeating-linear-gradient(45deg, #2b2620 0 6px, #221e19 6px 12px)",
                         }} />
                  )}
                </div>
                <span className="num text-[12px] text-bone-500 text-right">
                  {b.observed_rate != null
                    ? `${Math.round(b.observed_rate * 100)} %`
                    : `n=${b.n_trades}`}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* -- Fiabilite par agent ------------------------------------- */}
      <div className="card p-5 lg:col-span-2">
        <div className="text-[12px] uppercase tracking-[0.14em] text-bone-700 mb-1">
          {tr("perAgent", lang)}
          <Help text={tr("perAgentHelp", lang)} />
        </div>

        {data.by_agent.length === 0 ? (
          <p className="text-[14px] text-bone-500 mt-3 leading-snug">
            {tr("noAgentData", lang)}
          </p>
        ) : (
          <div className="mt-4 space-y-3">
            {data.by_agent.map((a) => (
              <div key={a.agent_id}
                   className="grid grid-cols-[150px_1fr_auto] gap-4 items-center">
                <span className="text-[14px] text-bone-300 truncate">
                  {a.agent_id}
                </span>
                <div className="flex gap-1">
                  {a.buckets.map((b) => (
                    <div key={b.lower} className="flex-1 h-6 relative
                                                  bg-ink-700 rounded-[2px]
                                                  overflow-hidden"
                         title={`${b.lower}-${b.upper} · n=${b.n_trades}`}>
                      {b.observed_rate != null && b.reliable ? (
                        <div
                          className="absolute bottom-0 inset-x-0 bg-brass-500"
                          style={{ height: `${b.observed_rate * 100}%` }}
                        />
                      ) : (
                        <div className="absolute inset-0 opacity-30"
                             style={{
                               backgroundImage:
                                 "repeating-linear-gradient(45deg, #2b2620 0 4px, #221e19 4px 8px)",
                             }} />
                      )}
                    </div>
                  ))}
                </div>
                <span className="num text-[13px] text-bone-500 w-24 text-right">
                  {a.sample_sufficient && a.hit_rate != null
                    ? `${Math.round(a.hit_rate * 100)} %`
                    : `n=${a.n_trades}`}
                </span>
              </div>
            ))}
            <p className="text-[12px] text-bone-700 pt-1">
              {tr("hatchedHelp", lang)}
            </p>
          </div>
        )}
      </div>

      {/* -- Historique --------------------------------------------- */}
      <div className="card overflow-hidden lg:col-span-2">
        <div className="px-5 py-3 border-b border-ink-600 text-[12px]
                        uppercase tracking-[0.14em] text-bone-700">
          {tr("recordedDecisions", lang)}
        </div>
        <div className="max-h-[420px] overflow-y-auto">
          {entries.length === 0 && (
            <p className="p-5 text-[14px] text-bone-700">
              {tr("noDecision", lang)}
            </p>
          )}
          {entries.map((e) => {
            const tone = dirTone(e.decision);
            const d = new Date(e.timestamp);
            return (
              <div
                key={e.run_id}
                className="px-5 py-3 border-b border-ink-700 last:border-0
                           grid grid-cols-[auto_1fr_auto] gap-3 items-center"
              >
                <DirectionMark d={e.decision} size={14} />
                <div className="min-w-0">
                  <div className={`text-[14px] font-medium ${tone.fg}`}>
                    {e.decision === "NO_TRADE"
                      ? tr("noTradeTitle", lang)
                      : e.decision}
                    <span className="num text-bone-700 font-normal ml-2">
                      {e.spot.toFixed(2)}
                    </span>
                  </div>
                  <div className="text-[12px] text-bone-700 truncate">
                    {d.toLocaleTimeString(lang === "fr" ? "fr-FR" : "en-GB", {
                      hour: "2-digit", minute: "2-digit", second: "2-digit",
                    })}
                    {e.notes && ` · ${t(e.notes, lang)}`}
                  </div>
                </div>
                <div className="text-right">
                  <div className="num text-[13px] text-bone-300">
                    {e.conviction > 0 ? e.conviction : "—"}
                  </div>
                  <div className="text-[11px] uppercase tracking-wider text-bone-700">
                    {tr(`verdict${e.risk_verdict}` as never, lang)}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
