"use client";

/*
  Composition du dashboard.

  Structure en onglets : la version précédente empilait tout sur une seule
  colonne, ce qui noyait la décision sous le détail. On arrive maintenant sur
  la décision, et on ne creuse que si on le veut.

  Un utilisateur qui ouvre cette page pour la première fois doit comprendre
  quoi faire en cinq secondes ; un trader professionnel doit pouvoir descendre
  jusqu'à la base de calcul. Le bascule Simple / Expert fait tenir les deux
  publics dans la même page.
*/

import { useCallback, useEffect, useState } from "react";
import Committee from "@/components/Committee";
import Journal from "@/components/Journal";
import PriceChart from "@/components/PriceChart";
import Terminal from "@/components/Terminal";
import Ticket from "@/components/Ticket";
import {
  BigStat, ConvictionMeter, DirectionMark, Help, Pill, Sparkline,
  Tabs, Toggle, VerdictBadge, dirTone,
} from "@/components/ui";
import {
  api, type AgentsResponse, type JournalResponse, type MarketState,
  type Run, type Scenario,
} from "@/lib/api";
import { type Lang, type Mode, type TabId, t, tr } from "@/lib/i18n";

export default function Page() {
  const [lang, setLang] = useState<Lang>("fr");
  const [mode, setMode] = useState<Mode>("simple");
  const [tab, setTab] = useState<TabId>("decision");

  const [agents, setAgents] = useState<AgentsResponse | null>(null);
  const [market, setMarket] = useState<MarketState | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [journal, setJournal] = useState<JournalResponse | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenario, setScenario] = useState("long");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [a, m, s, j, r] = await Promise.all([
          api.agents(), api.market(scenario), api.scenarios(),
          api.journal(), api.runs(),
        ]);
        setAgents(a); setMarket(m); setScenarios(s.scenarios); setJournal(j);
        if (r.runs.length) setRun(await api.runDetail(r.runs[0].run_id));
      } catch {
        setError(tr("backendDown", lang));
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Changer de scénario reconstruit l'état de marché affiché en en-tête.
  useEffect(() => {
    if (!market) return;
    api.market(scenario).then(setMarket).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenario]);

  const analyse = useCallback(async () => {
    setBusy(true); setError(null);
    try {
      const r = await api.run(scenario);
      setRun(r);
      const [j, m] = await Promise.all([api.journal(), api.market(scenario)]);
      setJournal(j); setMarket(m);
    } catch {
      setError(tr("runFailed", lang));
    } finally {
      setBusy(false);
    }
  }, [scenario, lang]);

  if (error) {
    return (
      <main className="min-h-dvh grid place-items-center p-8">
        <div className="card p-8 max-w-lg text-center">
          <p className="text-[16px] text-short-400 mb-3">{error}</p>
          <code className="num text-[13px] text-bone-500">
            uvicorn app.main:app --port 8020
          </code>
        </div>
      </main>
    );
  }

  if (!agents || !market) {
    return (
      <main className="min-h-dvh grid place-items-center">
        <div className="text-bone-700 text-[15px] pulse-soft">
          {tr("loading", lang)}
        </div>
      </main>
    );
  }

  const fv = market.features;
  const decision = run?.decision ?? null;
  const tone = dirTone(decision);
  const staleCount = market.sources.filter((s) => s.is_stale).length;
  const closes = market.candles.map((c) => c.c);
  const vwap5 = market.reads.find((r) => r.timeframe === "5m")?.vwap ?? null;

  const tabs = [
    { id: "decision" as TabId, label: tr("tabDecision", lang) },
    { id: "marche" as TabId, label: tr("tabMarche", lang) },
    { id: "terminal" as TabId, label: tr("tabTerminal", lang) },
    { id: "comite" as TabId, label: tr("tabComite", lang), badge: agents.total },
    ...(mode === "expert"
      ? [{ id: "ticket" as TabId, label: tr("tabTicket", lang) }]
      : []),
    {
      id: "journal" as TabId,
      label: tr("tabJournal", lang),
      badge: journal?.stats.total_runs ?? 0,
    },
  ];

  return (
    <main className="min-h-dvh relative z-10">
      {/* ======================= En-tête ======================= */}
      <header className="sticky top-0 z-40 bg-ink-900/95 backdrop-blur-sm
                         border-b border-ink-600">
        <div className="mx-auto max-w-[1360px] px-5 lg:px-8 pt-3
                        flex flex-wrap items-center gap-x-7 gap-y-3">
          <div className="flex items-center gap-3">
            <GoldMark />
            <div>
              <div className="text-[15px] font-semibold leading-none">
                {tr("appTitle", lang)}
              </div>
              <div className="text-[12px] text-bone-700 leading-none mt-1">
                {fv.contract.symbol} · {tr("instrument", lang)}
              </div>
            </div>
          </div>

          <div className="flex items-baseline gap-2.5">
            <span className="num text-[26px] leading-none">
              {fv.spot.toLocaleString(lang === "fr" ? "fr-FR" : "en-US", {
                minimumFractionDigits: 2,
              })}
            </span>
            <span className={`num text-[14px] ${
              market.change_pct >= 0 ? "text-long-400" : "text-short-400"
            }`}>
              {market.change_pct >= 0 ? "+" : ""}{market.change_pct} %
            </span>
            <span className="hidden sm:block opacity-70 ml-1">
              <Sparkline
                values={closes} width={84} height={24}
                stroke={market.change_pct >= 0 ? "#4fb286" : "#d1614f"}
              />
            </span>
          </div>

          <div className="hidden xl:flex items-center gap-2.5 text-[13px] text-bone-500">
            <span>{tr("session", lang)} {fv.session.session}</span>
            <span className="text-ink-500">|</span>
            <span className={staleCount ? "text-short-400" : "text-bone-500"}>
              {market.sources.length - staleCount}/{market.sources.length}{" "}
              {tr("sources", lang)}
            </span>
          </div>

          <div className="flex-1" />

          <div className="flex flex-wrap items-center gap-2.5">
            <Pill label={tr("mvpShort", lang)} tone="warn" />
            <Toggle
              ariaLabel="Langue" value={lang} onChange={setLang}
              options={[{ id: "fr", label: "FR" }, { id: "en", label: "EN" }]}
            />
            <Toggle
              ariaLabel="Mode" value={mode}
              onChange={(m) => {
                setMode(m);
                if (m === "simple" && tab === "ticket") setTab("decision");
              }}
              options={[
                { id: "simple", label: tr("modeSimple", lang) },
                { id: "expert", label: tr("modeExpert", lang) },
              ]}
            />
            <Help text={tr("modeHelp", lang)} />
          </div>
        </div>

        {/* Onglets, collés au bas de l'en-tête */}
        <div className="mx-auto max-w-[1360px] px-5 lg:px-8 mt-2">
          <Tabs tabs={tabs} value={tab} onChange={setTab} />
        </div>
      </header>

      <div className="mx-auto max-w-[1360px] px-5 lg:px-8 pb-24 pt-6">
        {/* ==================== Onglet Décision ==================== */}
        {tab === "decision" && (
          <div className="space-y-4 rise">
            <div className="grid lg:grid-cols-[1.45fr_1fr] gap-4">
              {/* Verdict */}
              <div className={`card p-7 border-l-[3px] ${tone.bd} relative overflow-hidden`}>
                {/* Halo discret dans la couleur de la décision : donne du
                    poids au verdict sans tomber dans le dégradé décoratif. */}
                <div
                  aria-hidden
                  className="absolute -top-24 -right-16 w-80 h-80 rounded-full
                             pointer-events-none"
                  style={{
                    background: `radial-gradient(circle, ${tone.raw}22 0%, transparent 68%)`,
                  }}
                />
                <div className="relative flex items-start gap-4">
                  <DirectionMark d={decision} size={42} />
                  <div className="min-w-0 flex-1">
                    <div className="text-[11px] uppercase tracking-[0.2em]
                                    text-bone-700 mb-1.5">
                      {tr("theDecision", lang)}
                    </div>
                    <div className={`text-[52px] leading-[1] font-bold
                                     tracking-tight ${tone.fg}`}>
                      {decision === "NO_TRADE" || !decision
                        ? tr("noTradeTitle", lang)
                        : decision === "LONG"
                        ? tr("longLabel", lang)
                        : tr("shortLabel", lang)}
                    </div>

                    {run?.ticket && (
                      <p className="serif text-[18px] leading-relaxed
                                    text-bone-300 mt-4 max-w-2xl">
                        {t(run.ticket.decision_rationale, lang)}
                      </p>
                    )}

                    {decision === "NO_TRADE" && (
                      <p className="text-[15px] text-bone-500 mt-3 border-l-2
                                    border-hold-500 pl-3 leading-relaxed max-w-2xl">
                        {tr("noTradeGood", lang)}
                      </p>
                    )}

                    {decision !== "NO_TRADE" && run?.conviction != null && (
                      <div className="mt-6">
                        <div className="text-[11px] uppercase tracking-[0.16em]
                                        text-bone-700 mb-2">
                          {tr("conviction", lang)}
                          <Help text={tr("convictionHelp", lang)} />
                        </div>
                        <div className="flex items-center gap-3.5">
                          <ConvictionMeter value={run.conviction} direction={decision} />
                          <span className={`num text-[28px] leading-none ${tone.fg}`}>
                            {run.conviction}
                            <span className="text-bone-700 text-[15px]">/100</span>
                          </span>
                        </div>
                      </div>
                    )}

                    <div className="flex flex-wrap items-center gap-2.5 mt-6">
                      {run?.risk_verdict && (
                        <VerdictBadge v={run.risk_verdict} lang={lang} />
                      )}
                      {run?.event_risk && (
                        <Pill
                          label={`${tr("eventRisk", lang)} · ${tr(`risk${run.event_risk}` as never, lang)}`}
                          tone={run.event_risk === "NORMAL" ? "neutral" : "warn"}
                        />
                      )}
                      {run?.halted && (
                        <Pill label={tr("pipelineHalted", lang)} tone="bad" />
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {/* Commande */}
              <div className="card p-6 flex flex-col">
                <button
                  type="button" onClick={analyse} disabled={busy}
                  className="relative overflow-hidden w-full py-4 rounded-card
                             bg-brass-500 text-ink-900 font-semibold text-[16px]
                             hover:bg-brass-400 disabled:opacity-60
                             disabled:cursor-wait transition-colors"
                >
                  {busy ? tr("analysing", lang) : tr("analyseNow", lang)}
                  {busy && <span className="sweep absolute inset-0" />}
                </button>

                <div className="mt-5">
                  <label htmlFor="scenario"
                         className="block text-[11px] uppercase tracking-[0.16em]
                                    text-bone-700 mb-2">
                    {tr("scenario", lang)}
                  </label>
                  <select
                    id="scenario" value={scenario}
                    onChange={(e) => setScenario(e.target.value)}
                    className="w-full bg-ink-700 border border-ink-500 rounded-card
                               px-3 py-2.5 text-[15px] text-bone-100"
                  >
                    {scenarios.map((s) => (
                      <option key={s.id} value={s.id}>{s[lang]}</option>
                    ))}
                  </select>
                  <p className="text-[13px] text-bone-700 mt-2.5 leading-snug">
                    {tr("scenarioHelp", lang)}
                  </p>
                </div>

                <div className="rule my-5" />

                <dl className="space-y-2 text-[13px]">
                  {[
                    [tr("lastRun", lang), run
                      ? new Date(run.started_at).toLocaleTimeString(
                          lang === "fr" ? "fr-FR" : "en-GB")
                      : "—"],
                    [tr("pipeline", lang),
                      run ? tr(`stage${run.stage}` as never, lang) : "—"],
                    ["Schema", fv.schema_version],
                    [tr("series", lang),
                      tr(fv.contract.series_type === "front_month"
                        ? "seriesFront" : "seriesCont", lang)],
                  ].map(([k, v]) => (
                    <div key={k} className="flex justify-between gap-3">
                      <dt className="text-bone-700">{k}</dt>
                      <dd className="num text-bone-300">{v}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            </div>

            {/* Chiffres clés + graphique */}
            <div className="card p-6">
              <div className="grid sm:grid-cols-3 gap-8 mb-7">
                <BigStat
                  label={tr("coherence", lang)}
                  value={String(fv.alignment.value)} unit="%"
                  tone={fv.alignment.value >= 60 ? "text-long-400"
                        : fv.alignment.value >= 40 ? "text-bone-100"
                        : "text-short-400"}
                  help={tr("coherenceHelp", lang)}
                />
                <BigStat
                  label={tr("volatility", lang)}
                  value={String(fv.atr_percentile.value)}
                  unit={lang === "fr" ? "e perc." : "th perc."}
                />
                <BigStat
                  label="VWAP"
                  value={`${fv.vwap_distance_atr.value > 0 ? "+" : ""}${fv.vwap_distance_atr.value}`}
                  unit="ATR"
                  tone={fv.vwap_distance_atr.value >= 0
                    ? "text-long-400" : "text-short-400"}
                />
              </div>

              <div className="flex items-center gap-2 mb-3">
                <span className="text-[11px] uppercase tracking-[0.16em] text-bone-700">
                  {tr("priceChart", lang)}
                </span>
                <Help text={tr("chartHelp", lang)} />
              </div>
              <PriceChart
                candles={market.candles} levels={market.levels}
                vwap={vwap5} lang={lang}
              />
            </div>
          </div>
        )}

        {/* ==================== Onglet Marché ==================== */}
        {tab === "marche" && (
          <div className="grid lg:grid-cols-[1.4fr_1fr] gap-4 rise">
            <div className="space-y-4">
              <Panel title={tr("structure", lang)}>
                <div className="space-y-1.5">
                  {market.reads.map((r) => (
                    <div key={r.timeframe}
                         className="grid grid-cols-[46px_1fr_auto_auto] gap-3
                                    items-center py-2 border-b border-ink-700
                                    last:border-0">
                      <span className="num text-[13px] text-bone-500">
                        {r.timeframe}
                      </span>
                      <span className="text-[14px] text-bone-300">
                        {structureLabel(r.structure, lang)}
                        <span className="text-bone-700 text-[13px]">
                          {" "}· {qualityLabel(r.quality, lang)}
                        </span>
                      </span>
                      <MomentumBar value={r.momentum} />
                      <span className="num text-[13px] w-11 text-right text-bone-500">
                        {r.momentum > 0 ? "+" : ""}{r.momentum}
                      </span>
                    </div>
                  ))}
                </div>
              </Panel>

              <Panel title={tr("keyLevels", lang)}>
                <ul className="space-y-2">
                  {market.levels.map((l, i) => (
                    <li key={i}
                        className="flex justify-between gap-3 items-baseline text-[14px]">
                      <span className={l.kind === "resistance"
                        ? "text-short-400" : "text-long-400"}>
                        {l.kind === "resistance"
                          ? tr("resistance", lang) : tr("support", lang)}
                        <span className="text-bone-700">
                          {" "}· {l.touches} {tr("touches", lang)}
                        </span>
                      </span>
                      <span className="num text-bone-300">
                        {l.price.toFixed(2)}
                        <span className="text-bone-700 ml-2">
                          {l.distance_pct > 0 ? "+" : ""}{l.distance_pct} %
                        </span>
                      </span>
                    </li>
                  ))}
                </ul>
              </Panel>
            </div>

            <div className="space-y-4">
              <Panel title={tr("triggers", lang)} help={tr("triggersHelp", lang)}>
                {market.triggers.length === 0 ? (
                  <p className="text-[14px] text-bone-500 leading-snug">
                    {tr("noTriggers", lang)}
                  </p>
                ) : (
                  <ul className="space-y-3">
                    {market.triggers.map((tg) => (
                      <li key={tg.dedup_key} className="border-l-2 border-brass-600 pl-3">
                        <div className="num text-[11px] text-brass-400 uppercase
                                        tracking-wider">
                          {tg.kind} · {tg.timeframe}
                        </div>
                        <div className="text-[14px] text-bone-300 leading-snug mt-0.5">
                          {t(tg.reason, lang)}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>

              <Panel title={tr("nextEvent", lang)}>
                <ul className="space-y-2.5">
                  {market.calendar.map((e, i) => (
                    <li key={i} className="flex justify-between gap-3 items-baseline">
                      <span className="text-[14px] text-bone-300 truncate">
                        {t(e.name, lang)}
                        {(e.importance === "CRITICAL" || e.importance === "HIGH") && (
                          <span className="text-warn-400 ml-1.5">●</span>
                        )}
                      </span>
                      <span className="num text-[13px] text-bone-500 shrink-0">
                        {fmtMinutes(e.minutes_until, lang)}
                      </span>
                    </li>
                  ))}
                </ul>
              </Panel>

              {mode === "expert" && (
                <Panel title={tr("sourcesTitle", lang)}>
                  <ul className="space-y-1.5">
                    {market.sources.map((s) => (
                      <li key={s.name}
                          className="flex justify-between gap-3 items-baseline text-[13px]">
                        <span className="text-bone-300 truncate">{s.name}</span>
                        <span className={`num shrink-0 ${
                          s.is_stale ? "text-short-400" : "text-bone-700"
                        }`}>
                          {fmtAge(s.age_seconds, lang)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </Panel>
              )}
            </div>
          </div>
        )}

        {/* =================== Onglet Terminal ==================== */}
        {tab === "terminal" && <Terminal lang={lang} />}

        {/* ==================== Onglet Comité ==================== */}
        {tab === "comite" && (
          <div className="rise">
            <p className="text-[15px] text-bone-500 max-w-3xl mb-2 leading-relaxed">
              {tr("committeeIntro", lang)}
            </p>
            <p className="text-[13px] text-bone-700 mb-6">
              {agents.tools_connected}/{agents.tools_total} {tr("toolsConnected", lang)}
            </p>
            <Committee cards={agents.agents} run={run} lang={lang} mode={mode} />
          </div>
        )}

        {/* ==================== Onglet Ticket ==================== */}
        {tab === "ticket" && (
          <div className="rise">
            {run?.ticket ? (
              <Ticket ticket={run.ticket} lang={lang} />
            ) : (
              <p className="card p-8 text-[15px] text-bone-500">
                {tr("ticketEmpty", lang)}
              </p>
            )}
          </div>
        )}

        {/* ==================== Onglet Journal ==================== */}
        {tab === "journal" && journal && (
          <div className="rise">
            <p className="text-[15px] text-bone-500 max-w-3xl mb-6 leading-relaxed">
              {tr("journalIntro", lang)}
            </p>
            <Journal data={journal} lang={lang} />
          </div>
        )}

        {/* Bandeau V1 : présent, mais plus au-dessus du verdict */}
        <div className="mt-10 border border-warn-500/30 bg-warn-900/25 rounded-card
                        px-4 py-2.5 text-[13px] text-warn-400 leading-snug">
          {tr("mvpBanner", lang)}
        </div>

        <footer className="mt-5 pt-5 rule text-[13px] text-bone-700
                           flex flex-wrap justify-between gap-3">
          <span>
            {agents.total} agents · {agents.deterministic_agents}{" "}
            {lang === "fr" ? "déterministe" : "deterministic"} ·{" "}
            {agents.llm_agents} LLM
          </span>
          <span className="num">feature_schema {fv.schema_version}</span>
        </footer>
      </div>
    </main>
  );
}

// ---------------------------------------------------------------------
function Panel({
  title, help, children,
}: { title: string; help?: string; children: React.ReactNode }) {
  return (
    <div className="card p-5">
      <div className="text-[11px] uppercase tracking-[0.16em] text-bone-700 mb-3">
        {title}
        {help && <Help text={help} />}
      </div>
      {children}
    </div>
  );
}

function GoldMark() {
  return (
    <svg width="30" height="30" viewBox="0 0 30 30" aria-hidden>
      <rect x="1" y="1" width="28" height="28" rx="3"
            fill="none" stroke="#a8843f" strokeWidth="1.5" />
      <path d="M8 20 L15 8 L22 20 Z" fill="none" stroke="#c8a055" strokeWidth="1.5" />
      <circle cx="15" cy="16.5" r="2" fill="#d9b26a" />
    </svg>
  );
}

function MomentumBar({ value }: { value: number }) {
  const pct = Math.min(Math.abs(value), 100) / 2;
  const pos = value >= 0;
  return (
    <div className="w-24 h-2 bg-ink-700 rounded-[1px] relative overflow-hidden"
         role="img" aria-label={`momentum ${value}`}>
      <span className="absolute inset-y-0 left-1/2 w-px bg-ink-500" />
      <span
        className={`absolute inset-y-0 ${pos ? "bg-long-500" : "bg-short-500"}`}
        style={{ left: pos ? "50%" : `${50 - pct}%`, width: `${pct}%` }}
      />
    </div>
  );
}

function structureLabel(s: string, lang: Lang): string {
  const map: Record<string, [string, string]> = {
    UPTREND: ["Tendance haussière", "Uptrend"],
    DOWNTREND: ["Tendance baissière", "Downtrend"],
    RANGE: ["Sans direction", "Range-bound"],
    TRANSITION: ["En transition", "In transition"],
  };
  const v = map[s] ?? [s, s];
  return lang === "fr" ? v[0] : v[1];
}

function qualityLabel(q: string, lang: Lang): string {
  const map: Record<string, [string, string]> = {
    CLEAN: ["nette", "clean"],
    CHOPPY: ["hachée", "choppy"],
    EXHAUSTED: ["essoufflée", "exhausted"],
  };
  const v = map[q] ?? [q, q];
  return lang === "fr" ? v[0] : v[1];
}

function fmtMinutes(m: number, lang: Lang): string {
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  if (h < 24) return lang === "fr" ? `${h} h` : `${h}h`;
  return lang === "fr" ? `${Math.floor(h / 24)} j` : `${Math.floor(h / 24)}d`;
}

function fmtAge(sec: number, lang: Lang): string {
  if (sec < 60) return `${sec} s`;
  if (sec < 3600) return `${Math.floor(sec / 60)} min`;
  if (sec < 86400) return lang === "fr" ? `${Math.floor(sec / 3600)} h` : `${Math.floor(sec / 3600)}h`;
  return lang === "fr" ? `${Math.floor(sec / 86400)} j` : `${Math.floor(sec / 86400)}d`;
}
