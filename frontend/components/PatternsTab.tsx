"use client";

/*
  Onglet 3 — graphique avec les patterns surlignés.

  Chaque type de pattern est accompagné de sa statistique sur l'historique
  chargé, comparée au hasard. Montrer un pattern sans dire s'il fonctionne
  serait de la décoration.
*/

import { useEffect, useState } from "react";
import MarketChart, { type Layer } from "@/components/MarketChart";
import { Help } from "@/components/ui";
import { api, type ChartData, type ChartInterval, type PatternStat } from "@/lib/api";
import { type DictKey, type Lang, tr } from "@/lib/i18n";

const INTERVALS: ChartInterval[] = ["5m", "15m", "1h", "1d"];
const QUICK = ["GC=F", "SI=F", "CL=F", "^NDX", "^GSPC", "EURUSD=X", "BTC-USD"];
const ZOOM = [60, 120, 200];
const LAYERS: { id: Layer; key: DictKey }[] = [
  { id: "vwap", key: "ovVwap" }, { id: "profile", key: "ovProfile" },
  { id: "structure", key: "ovStructure" }, { id: "candle", key: "ovCandles" },
  { id: "fvg", key: "ovFvg" }, { id: "sweep", key: "ovSweep" }, { id: "chart", key: "ovChart" },
];
const GROUP_LAYER: Record<string, Layer> = {
  candle: "candle", fvg: "fvg", sweep: "sweep", structure: "structure", chart: "chart",
};

export default function PatternsTab({ lang }: { lang: Lang }) {
  const [symbol, setSymbol] = useState("GC=F");
  const [input, setInput] = useState("");
  const [interval, setIv] = useState<ChartInterval>("15m");
  const [bars, setBars] = useState(120);
  const [layers, setLayers] = useState<Set<Layer>>(
    () => new Set<Layer>(["vwap", "profile", "structure", "candle", "fvg", "sweep", "chart"]));
  const [data, setData] = useState<ChartData | null>(null);
  const [err, setErr] = useState(false);
  const [narrow, setNarrow] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 640px)");
    const apply = () => setNarrow(mq.matches);
    apply();
    if (mq.matches) setBars(60);           // une seule fois, à l'ouverture
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);

  useEffect(() => {
    let alive = true;
    setErr(false);
    const load = () => api.chart(symbol, interval, bars)
      .then((d) => alive && setData(d))
      .catch(() => alive && setErr(true));
    load();
    const id = window.setInterval(load, 60_000);
    return () => { alive = false; window.clearInterval(id); };
  }, [symbol, interval, bars]);

  const toggle = (l: Layer) => setLayers((s) => {
    const n = new Set(s);
    if (n.has(l)) n.delete(l); else n.add(l);
    return n;
  });

  const shown = data && data.symbol === symbol && data.interval === interval ? data : null;
  const recent = shown
    ? shown.events.filter((e) => layers.has(GROUP_LAYER[shown.meta[e.kind]?.group])).slice(-8).reverse()
    : [];
  const loc = lang === "fr" ? "fr-FR" : "en-GB";

  return (
    <div className="space-y-3 rise">
      {/* ---- Commandes ---- */}
      <div className="card px-4 py-3 space-y-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <form onSubmit={(e) => {
            e.preventDefault();
            const s = input.trim().toUpperCase();
            if (s) setSymbol(s);
            setInput("");
          }} className="flex items-center gap-2">
            <label htmlFor="pt-sym" className="num text-[12px] uppercase tracking-[0.18em] text-brass-400">
              {tr("symbol", lang)} &gt;
            </label>
            <input id="pt-sym" value={input} onChange={(e) => setInput(e.target.value)}
              placeholder={symbol} autoComplete="off" spellCheck={false}
              className="num w-28 bg-transparent text-[17px] uppercase text-bone-100 placeholder:text-bone-500 outline-none" />
          </form>
          <div className="flex gap-1 overflow-x-auto max-w-full sm:flex-wrap">
            {QUICK.map((s) => (
              <Chip key={s} on={s === symbol} onClick={() => setSymbol(s)}>{s}</Chip>
            ))}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          <div role="group" aria-label="Interval" className="flex gap-1">
            {INTERVALS.map((iv) => (
              <Chip key={iv} on={iv === interval} onClick={() => setIv(iv)}>{iv.toUpperCase()}</Chip>
            ))}
          </div>
          <div role="group" aria-label={tr("bars", lang)} className="flex items-center gap-1">
            <span className="text-[11px] uppercase tracking-wider text-bone-700 mr-1">{tr("bars", lang)}</span>
            {ZOOM.map((z) => (
              <Chip key={z} on={z === bars} onClick={() => setBars(z)}>{z}</Chip>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-1.5 overflow-x-auto sm:flex-wrap">
          <span className="text-[11px] uppercase tracking-wider text-bone-700 mr-1 shrink-0">{tr("overlays", lang)}</span>
          {LAYERS.map((l) => (
            <Chip key={l.id} on={layers.has(l.id)} onClick={() => toggle(l.id)} check>{tr(l.key, lang)}</Chip>
          ))}
        </div>
      </div>

      {/* ---- Graphique ---- */}
      <section className="card p-3 sm:p-4">
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 mb-2 px-1">
          <span className="num text-[14px] text-brass-400">{symbol}</span>
          {shown && (
            <>
              <span className="num text-[22px]">{shown.candles.at(-1)?.c.toFixed(shown.decimals)}</span>
              <span className="text-[13px] text-bone-500">
                ATR {shown.atr} · {lang === "fr" ? "structure" : "structure"}{" "}
                <span className={shown.structure.trend === "UPTREND" ? "text-long-400"
                  : shown.structure.trend === "DOWNTREND" ? "text-short-400" : "text-bone-300"}>
                  {shown.structure.trend === "UPTREND" ? (lang === "fr" ? "haussière" : "up")
                    : shown.structure.trend === "DOWNTREND" ? (lang === "fr" ? "baissière" : "down")
                    : (lang === "fr" ? "indéterminée" : "undetermined")}
                </span>
              </span>
              <span className="text-[12px] text-bone-700">{tr("localTime", lang)}</span>
            </>
          )}
        </div>
        {shown ? (
          <>
            <MarketChart candles={shown.candles} interval={interval} decimals={shown.decimals}
              vwap={shown.vwap} sessionBreaks={shown.session_breaks} profile={shown.profile}
              swings={shown.swings} events={shown.events} fvgs={shown.fvgs} meta={shown.meta}
              layers={layers} height={narrow ? 360 : 480} lang={lang} />
            {!shown.has_volume && (
              <p className="text-[12px] text-bone-700 mt-2 px-1">{tr("noVolume", lang)}</p>
            )}
          </>
        ) : (
          <div className={`h-[420px] grid place-items-center text-[14px] ${err ? "text-short-400" : "text-bone-700 pulse-soft"}`}>
            {err ? tr("termError", lang) : tr("loading", lang)}
          </div>
        )}
        <Legend lang={lang} />
      </section>

      {shown && (
        <div className="grid lg:grid-cols-[1.6fr_1fr] gap-3">
          <StatsTable data={shown} lang={lang} />
          <section className="card p-4 sm:p-5">
            <h2 className="text-[12px] uppercase tracking-[0.16em] text-bone-500 mb-3">{tr("recentPatterns", lang)}</h2>
            {recent.length === 0 ? (
              <p className="text-[14px] text-bone-500">{tr("noPattern", lang)}</p>
            ) : (
              <ul className="space-y-3">
                {recent.map((e, k) => {
                  const m = shown.meta[e.kind];
                  const st = shown.stats.find((s) => s.kind === e.kind);
                  const c = shown.candles[e.i];
                  return (
                    <li key={k} className={`border-l-2 pl-3 ${e.dir > 0 ? "border-long-500" : "border-short-500"}`}>
                      <div className="flex flex-wrap justify-between gap-2 text-[13px]">
                        <span className={e.dir > 0 ? "text-long-400" : "text-short-400"}>
                          {e.dir > 0 ? "▲" : "▼"} {m?.[lang]}
                        </span>
                        <span className="num text-bone-700">
                          {c && new Date(c.t).toLocaleString(loc, { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}
                        </span>
                      </div>
                      <p className="text-[13px] text-bone-500 leading-snug mt-0.5">
                        {lang === "fr" ? m?.plain_fr : m?.plain_en}
                      </p>
                      {st && <LabelPill s={st} lang={lang} />}
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------
function Chip({ on, onClick, children, check }: {
  on: boolean; onClick: () => void; children: React.ReactNode; check?: boolean;
}) {
  return (
    <button type="button" onClick={onClick} aria-pressed={on}
      className={`num text-[12px] px-2 py-1 rounded-pill border transition-colors shrink-0 whitespace-nowrap ${
        on ? "bg-brass-500 text-ink-900 border-brass-500"
           : "border-ink-500 text-bone-500 hover:text-bone-100"}`}>
      {check && <span aria-hidden className="mr-1">{on ? "■" : "□"}</span>}
      {children}
    </button>
  );
}

function LabelPill({ s, lang }: { s: PatternStat; lang: Lang }) {
  const tone = s.label === "PLAUSIBLE" ? "text-long-400 border-long-500"
    : s.label === "NOT_PROVEN" ? "text-warn-400 border-warn-500" : "text-bone-500 border-ink-500";
  return (
    <span className={`inline-block mt-1 text-[10.5px] uppercase tracking-wider border px-1.5 py-[1px] rounded-pill ${tone}`}>
      {tr(`label${s.label}` as DictKey, lang)}
      {s.hit_rate != null && <span className="num normal-case"> · {Math.round(s.hit_rate * 100)} % vs {Math.round(s.baseline * 100)} %</span>}
    </span>
  );
}

function StatsTable({ data, lang }: { data: ChartData; lang: Lang }) {
  const pct = (v?: number | null) => (v == null ? "—" : `${Math.round(v * 100)}`);
  const rows = [...data.stats].sort((a, b) => b.n - a.n);
  return (
    <section className="card p-4 sm:p-5">
      <h2 className="text-[12px] uppercase tracking-[0.16em] text-bone-500 mb-1">
        {tr("patternStats", lang)}<Help text={tr("patternStatsHelp", lang)} />
      </h2>
      <p className="text-[12px] text-bone-700 mb-3">
        {tr("sample", lang)} : <span className="num">{data.sample.bars}</span> {tr("candlesWord", lang)} ·{" "}
        {tr("horizon", lang)} <span className="num">{data.horizon}</span> {tr("candlesWord", lang)}
      </p>
      <div className="overflow-x-auto -mx-1">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="text-[11px] uppercase tracking-[0.1em] text-bone-700 text-right">
              <th className="text-left font-normal py-1 px-1">{tr("pattern", lang)}</th>
              <th className="font-normal px-1">{tr("events", lang)}</th>
              <th className="font-normal px-1">% ✓</th>
              <th className="font-normal px-1">{tr("chance", lang)}</th>
              <th className="font-normal px-1 hidden sm:table-cell">{tr("ci95", lang)}</th>
              <th className="font-normal px-1 hidden md:table-cell">{tr("avgGain", lang)}</th>
              <th className="text-left font-normal px-1"></th>
            </tr>
          </thead>
          <tbody className="num">
            {rows.map((s) => {
              const m = data.meta[s.kind];
              const better = s.hit_rate != null && s.hit_rate > s.baseline;
              return (
                <tr key={s.kind} className="border-t border-ink-700 text-right">
                  <td className={`text-left py-1.5 px-1 font-sans ${m?.dir > 0 ? "text-long-400" : "text-short-400"}`}>
                    {m?.dir > 0 ? "▲" : "▼"} <span className="text-bone-300">{m?.[lang]}</span>
                  </td>
                  <td className="px-1 text-bone-500">{s.n}</td>
                  <td className={`px-1 ${better ? "text-bone-100" : "text-bone-500"}`}>{pct(s.hit_rate)}</td>
                  <td className="px-1 text-bone-500">{pct(s.baseline)}</td>
                  <td className="px-1 text-bone-700 hidden sm:table-cell">
                    {s.ci ? `${pct(s.ci[0])}–${pct(s.ci[1])}` : "—"}
                  </td>
                  <td className={`px-1 hidden md:table-cell ${s.avg_gain_atr == null ? "text-bone-700"
                    : s.avg_gain_atr > 0 ? "text-long-400" : "text-short-400"}`}>
                    {s.avg_gain_atr == null ? "—" : `${s.avg_gain_atr > 0 ? "+" : ""}${s.avg_gain_atr.toFixed(2)}`}
                  </td>
                  <td className="text-left px-1 font-sans"><LabelPill s={{ ...s, hit_rate: undefined }} lang={lang} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-[12px] text-bone-700 mt-3 leading-snug">
        {lang === "fr"
          ? "% ✓ : part des cas où le prix est allé dans le sens du pattern. Hasard : la même mesure sur n'importe quelle bougie. Gain moyen en ATR, coûts déduits."
          : "% ✓: share of cases where price moved the pattern's way. Chance: the same measure on any candle. Average gain in ATR, after costs."}
      </p>
    </section>
  );
}

function Legend({ lang }: { lang: Lang }) {
  const fr = lang === "fr";
  const items: [string, string][] = [
    ["E", fr ? "avalement" : "engulfing"], ["H", fr ? "marteau" : "hammer"],
    ["S", fr ? "étoile filante" : "shooting star"], ["$", fr ? "chasse aux stops" : "liquidity sweep"],
    ["DT/DB", fr ? "double sommet/creux" : "double top/bottom"],
    ["BOS", fr ? "cassure de structure" : "break of structure"],
    ["CHoCH", fr ? "changement de caractère" : "change of character"],
    ["HH/HL/LH/LL", fr ? "sommets/creux plus hauts ou plus bas" : "higher/lower highs and lows"],
  ];
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 px-1 text-[12px] text-bone-500">
      <span><span className="text-long-400">▲</span>/<span className="text-short-400">▼</span> {fr ? "haussier / baissier" : "bullish / bearish"}</span>
      {items.map(([k, v]) => (
        <span key={k}><span className="num text-bone-300">{k}</span> {v}</span>
      ))}
      <span><span className="inline-block w-3 h-2 bg-long-500/30 align-middle" /> FVG</span>
      <span><span className="inline-block w-4 h-[2px] bg-brass-500 align-middle" /> VWAP</span>
    </div>
  );
}
