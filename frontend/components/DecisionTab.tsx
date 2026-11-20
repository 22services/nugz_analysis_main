"use client";

/*
  Onglet 1 — la décision des 15 minutes.

  Ordre de lecture voulu : le verdict d'abord (lisible en 5 secondes), le
  ticket ensuite, puis le POURQUOI (les cinq voix, le CIO, la Red Team, le
  Risk Manager), et enfin le journal qui dit ce que valent ces décisions.
*/

import { useCallback, useEffect, useMemo, useState } from "react";
import MarketChart, { type ChartLine } from "@/components/MarketChart";
import { ConvictionMeter, DirectionMark, Help, Pill, Toggle, dirTone } from "@/components/ui";
import {
  api, type Agent, type ChartData, type Decision, type History, type JournalStats,
} from "@/lib/api";
import { type DictKey, type Lang, t, tr } from "@/lib/i18n";

export default function DecisionTab({ lang, onPrice }: {
  lang: Lang; onPrice?: (d: Decision) => void;
}) {
  const [d, setD] = useState<Decision | null>(null);
  const [warming, setWarming] = useState(false);
  const [down, setDown] = useState(false);
  const [hist, setHist] = useState<History | null>(null);
  const [src, setSrc] = useState<"live" | "replay" | null>(null);
  const [chart, setChart] = useState<ChartData | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const dec = await api.decision();
      setD(dec); setWarming(false); setDown(false); onPrice?.(dec);
    } catch (e) {
      if (String(e).includes("503")) setWarming(true); else setDown(true);
    }
    api.history(src ?? "live", 400).then((h) => {
      setHist(h);
      if (src == null) setSrc(h.stats.live.closed >= 10 ? "live" : "replay");
    }).catch(() => {});
    api.chart("GC=F", "15m", 96).then(setChart).catch(() => {});
  }, [src, onPrice]);

  useEffect(() => {
    load();
    const id = window.setInterval(load, 60_000);
    return () => window.clearInterval(id);
  }, [load]);

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  // Recharge dès que la prochaine réunion du comité a eu lieu.
  const nextAt = d?.schedule?.next_run_at ? new Date(d.schedule.next_run_at).getTime() : null;
  useEffect(() => {
    if (nextAt && now > nextAt + 20_000 && now < nextAt + 22_000) load();
  }, [now, nextAt, load]);

  const refresh = async () => {
    setBusy(true);
    try { setD(await api.refresh()); } catch { /* conservé : dernier état */ }
    setBusy(false);
  };

  const lines = useMemo<ChartLine[]>(() => {
    if (!d) return [];
    const r = d.risk;
    const traded = d.decision !== "NO_TRADE";
    const op = traded ? "" : "88";
    return [
      { price: r.entry, label: tr("entry", lang), color: `#c9c1b4${op}`, dash: "2 3" },
      { price: r.stop, label: tr("stop", lang), color: `#d1614f${op}` },
      { price: r.t1, label: "T1", color: `#4fb286${op}` },
    ];
  }, [d, lang]);

  if (!d) {
    return (
      <div className="card p-8 text-center text-[15px] rise">
        <p className={down ? "text-short-400" : "text-bone-500 pulse-soft"}>
          {down ? tr("backendDown", lang) : warming ? tr("warmingUp", lang) : tr("loading", lang)}
        </p>
      </div>
    );
  }

  const tone = dirTone(d.decision);
  const loc = lang === "fr" ? "fr-FR" : "en-GB";
  const hm = (iso: string) => new Date(iso).toLocaleTimeString(loc, { hour: "2-digit", minute: "2-digit" });
  const left = nextAt ? Math.max(0, Math.round((nextAt - now) / 1000)) : null;
  const traded = d.decision !== "NO_TRADE";

  return (
    <div className="space-y-4 rise">
      {/* ================= Verdict + ticket ================= */}
      <div className="grid lg:grid-cols-[1.35fr_1fr] gap-4">
        <section className={`card p-6 sm:p-7 border-l-[3px] ${tone.bd} relative overflow-hidden`}>
          <div aria-hidden className="absolute -top-24 -right-16 w-80 h-80 rounded-full pointer-events-none"
               style={{ background: `radial-gradient(circle, ${tone.raw}22 0%, transparent 68%)` }} />
          <div className="relative flex items-start gap-4">
            <DirectionMark d={d.decision} size={40} />
            <div className="min-w-0 flex-1">
              <div className="text-[11px] uppercase tracking-[0.2em] text-bone-700 mb-1.5">
                {tr("theDecision", lang)} · {d.symbol}
              </div>
              <div className={`text-[44px] sm:text-[52px] leading-[1] font-bold tracking-tight ${tone.fg}`}>
                {d.decision === "LONG" ? tr("longLabel", lang)
                  : d.decision === "SHORT" ? tr("shortLabel", lang) : tr("noTradeTitle", lang)}
              </div>
              <p className="serif text-[17px] sm:text-[18px] leading-relaxed text-bone-300 mt-4 max-w-2xl">
                {t(d.rationale, lang)}
              </p>
              {!traded && (
                <p className="text-[14px] text-bone-500 mt-3 border-l-2 border-hold-500 pl-3 leading-relaxed max-w-2xl">
                  {tr("noTradeGood", lang)}
                </p>
              )}
              {traded && (
                <div className="mt-5">
                  <div className="text-[11px] uppercase tracking-[0.16em] text-bone-700 mb-2">
                    {tr("conviction", lang)}<Help text={tr("convictionHelp", lang)} />
                  </div>
                  <div className="flex items-center gap-3.5">
                    <ConvictionMeter value={d.conviction} direction={d.decision} />
                    <span className={`num text-[26px] leading-none ${tone.fg}`}>
                      {d.conviction}<span className="text-bone-700 text-[14px]">/100</span>
                    </span>
                  </div>
                </div>
              )}
              <div className="flex flex-wrap items-center gap-x-5 gap-y-2 mt-5 text-[13px]">
                <span className="text-bone-500">
                  {tr("forBar", lang)}{" "}
                  <span className="num text-bone-300">{hm(d.bar_start)}–{hm(d.bar_end)}</span>
                </span>
                {left != null && (
                  <span className="text-bone-500">
                    {tr("nextDecision", lang)} {tr("inMinutes", lang)}{" "}
                    <span className="num text-brass-400">
                      {Math.floor(left / 60)}:{String(left % 60).padStart(2, "0")}
                    </span>
                  </span>
                )}
                <Pill label={t(d.market.session_label, lang)} tone="muted" />
                <button type="button" onClick={refresh} disabled={busy}
                  className="text-[12px] px-2.5 py-1 rounded-pill border border-ink-500 text-bone-500
                             hover:text-bone-100 hover:border-brass-500 disabled:opacity-50">
                  {busy ? "…" : tr("refresh", lang)}
                </button>
              </div>
              <p className="text-[12px] text-bone-700 mt-3 leading-snug max-w-2xl">{tr("delayNote", lang)}</p>
            </div>
          </div>
        </section>

        <TicketCard d={d} lang={lang} />
      </div>

      {/* ================= Les cinq voix ================= */}
      <section>
        <h2 className="text-[12px] uppercase tracking-[0.16em] text-bone-500 mb-3">
          {tr("committee", lang)}<Help text={tr("committeeHelp", lang)} />
        </h2>
        <div className="grid sm:grid-cols-2 xl:grid-cols-5 gap-3">
          {d.agents.map((a) => <AgentCard key={a.id} a={a} lang={lang} />)}
        </div>
      </section>

      {/* ================= CIO, Red Team, Risk ================= */}
      <div className="grid lg:grid-cols-3 gap-3">
        <CioPanel d={d} lang={lang} />
        <RedTeamPanel d={d} lang={lang} />
        <RiskPanel d={d} lang={lang} />
      </div>

      {/* ================= Graphique ================= */}
      <section className="card p-4 sm:p-5">
        <h2 className="text-[12px] uppercase tracking-[0.16em] text-bone-500 mb-3">
          {tr("marketNow", lang)}<Help text={tr("marketNowHelp", lang)} />
        </h2>
        {chart ? (
          <MarketChart candles={chart.candles} interval="15m" decimals={chart.decimals}
            vwap={chart.vwap} sessionBreaks={chart.session_breaks} profile={chart.profile}
            swings={chart.swings} events={chart.events} meta={chart.meta} lines={lines}
            layers={new Set(["vwap", "profile", "structure"])} height={380} lang={lang} />
        ) : (
          <div className="h-[380px] grid place-items-center text-bone-700 pulse-soft">{tr("loading", lang)}</div>
        )}
      </section>

      {/* ================= Journal ================= */}
      {hist && src && <JournalPanel hist={hist} src={src} setSrc={setSrc} lang={lang} />}
    </div>
  );
}

// ---------------------------------------------------------------------
function TicketCard({ d, lang }: { d: Decision; lang: Lang }) {
  const r = d.risk;
  const traded = d.decision !== "NO_TRADE";
  const f = (p: number) => p.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const v = r.verdict;
  return (
    <section className={`card p-5 sm:p-6 ${traded ? "" : "opacity-[0.88]"}`}>
      <div className="flex items-center justify-between gap-3 mb-4">
        <h2 className="text-[12px] uppercase tracking-[0.16em] text-bone-500">
          {traded ? tr("ticket", lang) : tr("hypothetical", lang)}
          {!traded && <Help text={tr("hypotheticalHelp", lang)} />}
        </h2>
        <Pill label={tr(`verdict${v}` as DictKey, lang)}
              tone={v === "APPROVED" ? "good" : v === "REDUCE" ? "warn" : "bad"} />
      </div>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-3">
        <Row k={tr("entry", lang)} v={f(r.entry)} />
        <Row k={tr("stop", lang)} v={f(r.stop)} sub={`${r.stop_atr} ATR · ${t(r.stop_source, lang)}`} tone="text-short-400" />
        <Row k={tr("target1", lang)} v={f(r.t1)} sub={`${r.rr1.toFixed(2)} R · ${t(r.t1_name, lang)}`} tone="text-long-400" />
        <Row k={tr("target2", lang)} v={f(r.t2)} sub={`${r.rr2.toFixed(2)} R · ${t(r.t2_name, lang)}`} tone="text-long-400" />
      </dl>
      <div className="rule my-4" />
      <div className="flex flex-wrap items-baseline justify-between gap-2 text-[13px]">
        <span className="text-bone-500">{tr("chaseLimit", lang)}</span>
        <span className="num text-warn-400">{f(r.chase_limit)}</span>
      </div>
      <div className="flex flex-wrap items-baseline justify-between gap-2 text-[13px] mt-2">
        <span className="text-bone-500">{tr("size", lang)}<Help text={tr("sizeHelp", lang)} /></span>
        <span className="num text-bone-300">
          {traded ? `${r.contracts.GC} GC · ${r.contracts.MGC} MGC` : "—"}
          <span className="text-bone-700"> / {r.risk_usd} $</span>
        </span>
      </div>
      <p className="text-[12px] text-bone-700 mt-3 leading-snug">{tr("timeStop", lang)}</p>
    </section>
  );
}

function Row({ k, v, sub, tone }: { k: string; v: string; sub?: string; tone?: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] uppercase tracking-[0.14em] text-bone-700">{k}</dt>
      <dd className={`num text-[20px] leading-tight ${tone ?? "text-bone-100"}`}>{v}</dd>
      {sub && <dd className="text-[12px] text-bone-500 leading-snug">{sub}</dd>}
    </div>
  );
}

// ---------------------------------------------------------------------
const GROUP_KEY: Record<Agent["group"], DictKey> = {
  trend: "groupTrend", location: "groupLocation", context: "groupContext", filter: "groupFilter",
};

function ScoreBar({ value, muted }: { value: number; muted?: boolean }) {
  const pct = Math.min(Math.abs(value), 100) / 2;
  const pos = value >= 0;
  return (
    <div className="h-2 bg-ink-700 rounded-[1px] relative overflow-hidden" role="img"
         aria-label={`score ${value}`}>
      <span className="absolute inset-y-0 left-1/2 w-px bg-ink-500" />
      {!muted && (
        <span className={`absolute inset-y-0 ${pos ? "bg-long-500" : "bg-short-500"}`}
              style={{ left: pos ? "50%" : `${50 - pct}%`, width: `${pct}%` }} />
      )}
    </div>
  );
}

function AgentCard({ a, lang }: { a: Agent; lang: Lang }) {
  const [open, setOpen] = useState(false);
  const off = a.status !== "OK";
  const filter = a.group === "filter";
  const tone = dirTone(a.direction === "NEUTRAL" ? null : a.direction);
  return (
    <article className={`card p-4 flex flex-col ${off ? "opacity-60" : ""}`}>
      <div className="flex items-center gap-2 mb-1">
        <DirectionMark d={filter || off ? null : a.direction} size={16} />
        <h3 className="text-[15px] font-semibold">{t(a.name, lang)}</h3>
        <span className="flex-1" />
        <span className="text-[10px] uppercase tracking-wider text-bone-700">
          {tr(GROUP_KEY[a.group], lang)}
        </span>
      </div>
      <p className="text-[12px] text-bone-700 leading-snug mb-3">{t(a.role, lang)}</p>
      {filter ? (
        <div className="num text-[13px] text-bone-500 mb-2">× {a.multiplier?.toFixed(1)}</div>
      ) : (
        <div className="flex items-center gap-2.5 mb-2">
          <div className="flex-1"><ScoreBar value={a.score} muted={off} /></div>
          <span className={`num text-[14px] w-10 text-right ${off ? "text-bone-700" : tone.fg}`}>
            {off ? "—" : `${a.score > 0 ? "+" : ""}${a.score}`}
          </span>
        </div>
      )}
      <p className="text-[14px] text-bone-300 leading-snug flex-1">
        {off && <span className="text-short-400">{tr("unavailable", lang)} · </span>}
        {t(a.headline, lang)}
      </p>
      {a.warnings.map((w, k) => (
        <p key={k} className="text-[12px] text-warn-400 leading-snug mt-2">⚠ {t(w, lang)}</p>
      ))}
      {a.evidence.length > 0 && (
        <>
          <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open}
            className="mt-3 self-start text-[12px] text-brass-400 hover:text-brass-500">
            {open ? "−" : "+"} {tr("details", lang)}
          </button>
          {open && (
            <dl className="mt-2 space-y-2">
              {a.evidence.map((e, k) => (
                <div key={k} className="border-t border-ink-700 pt-1.5">
                  <div className="flex justify-between gap-2 text-[12px]">
                    <dt className="text-bone-500">{t(e.label, lang)}</dt>
                    <dd className={`num text-right ${e.supports > 0 ? "text-long-400"
                      : e.supports < 0 ? "text-short-400" : "text-bone-300"}`}>{t(e.value, lang)}</dd>
                  </div>
                  {e.reading && <p className="text-[12px] text-bone-700 leading-snug">{t(e.reading, lang)}</p>}
                </div>
              ))}
            </dl>
          )}
        </>
      )}
    </article>
  );
}

// ---------------------------------------------------------------------
function Panel({ title, help, children }: { title: string; help?: string; children: React.ReactNode }) {
  return (
    <section className="card p-4 sm:p-5">
      <h2 className="text-[12px] uppercase tracking-[0.16em] text-bone-500 mb-3">
        {title}{help && <Help text={help} />}
      </h2>
      {children}
    </section>
  );
}

function CioPanel({ d, lang }: { d: Decision; lang: Lang }) {
  const c = d.cio;
  const nv = c.naive_vote;
  const groups: [DictKey, number | null, number][] = [
    ["groupTrend", c.groups.trend, c.weights.trend],
    ["groupLocation", c.groups.location, c.weights.location],
    ["groupContext", c.groups.context, c.weights.context],
  ];
  return (
    <Panel title={tr("howDecided", lang)}>
      <div className="text-[13px] text-bone-500 mb-3">
        {tr("naiveVote", lang)} <Help text={tr("naiveVoteHelp", lang)} />
        <span className="num text-bone-300 ml-1">
          {nv.long} ▲ · {nv.short} ▼ · {nv.neutral} ▬
        </span>
        <span className="text-bone-700"> — {lang === "fr" ? "écarté" : "discarded"}</span>
      </div>
      <ul className="space-y-2.5">
        {groups.map(([k, v, w]) => (
          <li key={k}>
            <div className="flex justify-between text-[13px] mb-1">
              <span className="text-bone-300">{tr(k, lang)} <span className="text-bone-700 num">× {w}</span></span>
              <span className="num text-bone-300">{v == null ? "—" : `${v > 0 ? "+" : ""}${v}`}</span>
            </div>
            <ScoreBar value={v ?? 0} muted={v == null} />
          </li>
        ))}
      </ul>
      <div className="rule my-3" />
      <div className="flex justify-between items-baseline text-[14px]">
        <span className="text-bone-500">{tr("weightedScore", lang)}</span>
        <span className={`num text-[20px] ${c.raw_score > 0 ? "text-long-400" : c.raw_score < 0 ? "text-short-400" : ""}`}>
          {c.raw_score > 0 ? "+" : ""}{c.raw_score}
        </span>
      </div>
      <div className="text-[12px] text-bone-700 mt-1">
        {tr("threshold", lang)} ±{c.threshold} · {tr("conviction", lang).toLowerCase()} ≥ {c.min_conviction}
      </div>
    </Panel>
  );
}

function RedTeamPanel({ d, lang }: { d: Decision; lang: Lang }) {
  const o = d.red_team.objections;
  return (
    <Panel title={tr("redTeam", lang)}>
      {o.length === 0 ? (
        <p className="text-[14px] text-bone-500">{tr("noObjection", lang)}</p>
      ) : (
        <ul className="space-y-2.5">
          {o.map((x, k) => (
            <li key={k} className="flex gap-2.5">
              <span className="num text-[11px] shrink-0 mt-0.5 flex gap-[2px]" role="img"
                    aria-label={`${tr("severity", lang)} ${x.severity}/5`}>
                {Array.from({ length: 5 }, (_, i) => (
                  <span key={i} className={`block w-1.5 h-3 rounded-[1px] ${
                    i < x.severity ? (x.severity >= 4 ? "bg-short-500" : x.severity >= 3 ? "bg-warn-500" : "bg-bone-500")
                    : "bg-ink-600"}`} />
                ))}
              </span>
              <span className="text-[13px] text-bone-300 leading-snug">{t(x.claim, lang)}</span>
            </li>
          ))}
        </ul>
      )}
      <div className="rule my-3" />
      <div className="flex justify-between text-[13px]">
        <span className="text-bone-500">{tr("penalty", lang)}</span>
        <span className="num text-short-400">−{d.red_team.penalty}</span>
      </div>
    </Panel>
  );
}

function RiskPanel({ d, lang }: { d: Decision; lang: Lang }) {
  return (
    <Panel title={tr("riskManager", lang)}>
      <ul className="space-y-2">
        {d.risk.checks.map((c, k) => (
          <li key={k} className="flex gap-2.5 text-[13px] leading-snug">
            <span aria-hidden className={`shrink-0 font-bold ${c.passed ? "text-long-400" : c.hard ? "text-short-400" : "text-warn-400"}`}>
              {c.passed ? "✓" : "✕"}
            </span>
            <span>
              <span className={c.passed ? "text-bone-300" : "text-bone-100"}>{t(c.name, lang)}</span>
              {c.hard && !c.passed && <span className="text-short-400 text-[11px] uppercase ml-1.5">{tr("hardLimit", lang)}</span>}
              {c.detail && <span className="block text-[12px] text-bone-700">{t(c.detail, lang)}</span>}
            </span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

// ---------------------------------------------------------------------
function JournalPanel({
  hist, src, setSrc, lang,
}: {
  hist: History; src: "live" | "replay"; setSrc: (s: "live" | "replay") => void; lang: Lang;
}) {
  const s: JournalStats = hist.stats[src];
  const items = hist.items.filter((e) => e.source === src);
  const pct = (v: number | null) => (v == null ? "—" : `${Math.round(v * 100)} %`);
  const loc = lang === "fr" ? "fr-FR" : "en-GB";
  const strip = items.slice(0, 96).reverse();
  const trades = items.filter((e) => e.taken).slice(0, 10);
  const noEdge = s.expectancy_ci != null && s.expectancy_ci[0] <= 0;
  return (
    <section className="card p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h2 className="text-[12px] uppercase tracking-[0.16em] text-bone-500">
          {tr("journal", lang)}<Help text={tr("journalHelp", lang)} />
        </h2>
        <div className="flex items-center gap-3">
          {hist.replay.status === "running" && (
            <span className="text-[12px] text-bone-700 pulse-soft num">
              {tr("replayRunning", lang)} {hist.replay.done}/{hist.replay.total}
            </span>
          )}
          <Toggle ariaLabel="source" value={src} onChange={setSrc}
            options={[{ id: "live", label: tr("sourceLive", lang) },
                      { id: "replay", label: tr("sourceReplay", lang) }]} />
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4 mb-4">
        <Stat k={tr("decisions", lang)} v={String(s.decisions)}
              sub={s.from ? `${new Date(s.from).toLocaleDateString(loc)} → ${new Date(s.to!).toLocaleDateString(loc)}` : undefined} />
        <Stat k={tr("noTradeRate", lang)} v={pct(s.no_trade_rate)} />
        <Stat k={tr("trades", lang)} v={String(s.closed)}
              sub={`${s.missed} ${lang === "fr" ? "ratés" : "missed"} · ${s.in_position_skipped} ${tr("inPosition", lang)}`} />
        <Stat k={tr("hitRate", lang)} v={pct(s.hit_rate)}
              sub={s.hit_ci ? `${tr("ci95", lang)} ${pct(s.hit_ci[0])}–${pct(s.hit_ci[1])}` : undefined} />
        <Stat k={tr("expectancy", lang)}
              v={s.expectancy_r == null ? "—" : `${s.expectancy_r > 0 ? "+" : ""}${s.expectancy_r.toFixed(2)} R`}
              tone={s.expectancy_r == null ? undefined : s.expectancy_r > 0 ? "text-long-400" : "text-short-400"}
              sub={[s.expectancy_ci && `${tr("ci95", lang)} ${s.expectancy_ci[0].toFixed(2)} → ${s.expectancy_ci[1].toFixed(2)}`,
                    s.profit_factor != null && `${tr("profitFactor", lang)} ${s.profit_factor}`]
                    .filter(Boolean).join(" · ") || undefined} />
        <Stat k={tr("worstStreak", lang)} v={String(s.worst_losing_streak)} />
      </div>

      {!s.sample_sufficient ? (
        <p className="text-[13px] text-warn-400 border-l-2 border-warn-500 pl-3 mb-4">{tr("insufficient", lang)}</p>
      ) : noEdge ? (
        <p className="text-[13px] text-warn-400 border-l-2 border-warn-500 pl-3 mb-4">{tr("noEdgeYet", lang)}</p>
      ) : null}

      {/* Frise des dernières décisions */}
      <div className="flex flex-wrap gap-[3px] mb-4" role="list" aria-label={tr("recent", lang)}>
        {strip.map((e) => {
          const col = e.decision === "LONG" ? "bg-long-500" : e.decision === "SHORT" ? "bg-short-500" : "bg-ink-600";
          const ring = e.taken ? (e.outcome === "WIN" ? "ring-1 ring-long-400"
            : e.outcome === "LOSS" ? "ring-1 ring-short-400" : "ring-1 ring-bone-500") : "";
          return (
            <span key={e.bar_start} role="listitem"
                  title={`${new Date(e.bar_start).toLocaleString(loc)} · ${e.decision} · ${tr(`outcome${e.outcome}` as DictKey, lang)}`}
                  className={`block w-2.5 h-4 rounded-[1px] ${col} ${ring}`} />
          );
        })}
      </div>

      {trades.length > 0 && (
        <div className="overflow-x-auto -mx-1">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="text-[11px] uppercase tracking-[0.12em] text-bone-700 text-left">
                <th className="font-normal py-1 px-1">{lang === "fr" ? "Barre" : "Bar"}</th>
                <th className="font-normal px-1">{lang === "fr" ? "Sens" : "Side"}</th>
                <th className="font-normal px-1 text-right">{tr("entry", lang)}</th>
                <th className="font-normal px-1 text-right hidden sm:table-cell">{tr("stop", lang)}</th>
                <th className="font-normal px-1 text-right hidden sm:table-cell">T1</th>
                <th className="font-normal px-1">{lang === "fr" ? "Issue" : "Outcome"}</th>
                <th className="font-normal px-1 text-right">R</th>
              </tr>
            </thead>
            <tbody className="num">
              {trades.map((e) => (
                <tr key={e.bar_start} className="border-t border-ink-700">
                  <td className="py-1.5 px-1 text-bone-500">
                    {new Date(e.bar_start).toLocaleString(loc, { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}
                  </td>
                  <td className={`px-1 ${e.decision === "LONG" ? "text-long-400" : "text-short-400"}`}>
                    {e.decision === "LONG" ? "▲" : "▼"} {e.decision}
                  </td>
                  <td className="px-1 text-right text-bone-300">{(e.entry ?? e.entry_ref).toFixed(2)}</td>
                  <td className="px-1 text-right text-bone-500 hidden sm:table-cell">{e.stop.toFixed(2)}</td>
                  <td className="px-1 text-right text-bone-500 hidden sm:table-cell">{e.t1.toFixed(2)}</td>
                  <td className="px-1 font-sans text-bone-300">{tr(`outcome${e.outcome}` as DictKey, lang)}</td>
                  <td className={`px-1 text-right ${e.pnl_r == null ? "text-bone-700" : e.pnl_r > 0 ? "text-long-400" : "text-short-400"}`}>
                    {e.pnl_r == null ? "—" : `${e.pnl_r > 0 ? "+" : ""}${e.pnl_r.toFixed(2)}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function Stat({ k, v, sub, tone }: { k: string; v: string; sub?: string; tone?: string }) {
  return (
    <div className="min-w-0">
      <div className="text-[11px] uppercase tracking-[0.14em] text-bone-700 mb-1">{k}</div>
      <div className={`num text-[22px] leading-none ${tone ?? "text-bone-100"}`}>{v}</div>
      {sub && <div className="text-[12px] text-bone-500 mt-1 leading-snug">{sub}</div>}
    </div>
  );
}
