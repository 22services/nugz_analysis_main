"use client";

/*
  Onglet 3 — graphique avec les patterns surlignés.

  Pensé pour être compris sans connaître le vocabulaire : un encadré
  « Lecture en clair » décrit en phrases ce que montre le graphique, trois
  préréglages d'affichage évitent la surcharge, et chaque pattern est
  accompagné de sa statistique contre le hasard. Le graphique se déplace
  au doigt ou à la souris.
*/

import { useEffect, useMemo, useState } from "react";
import MarketChart, { type Layer } from "@/components/MarketChart";
import { Help } from "@/components/ui";
import { api, type ChartData, type ChartInterval, type PatternStat } from "@/lib/api";
import { type DictKey, type Lang, tr } from "@/lib/i18n";

const INTERVALS: ChartInterval[] = ["5m", "15m", "1h", "1d"];
const QUICK = ["GC=F", "SI=F", "CL=F", "^NDX", "^GSPC", "EURUSD=X", "BTC-USD"];
const ALL: Layer[] = ["vwap", "profile", "structure", "candle", "fvg", "sweep", "chart"];
const PRESETS: Record<string, Layer[]> = {
  essential: ["vwap", "candle", "sweep", "chart"],
  structure: ["vwap", "structure", "profile", "fvg"],
  all: ALL,
};
const LAYER_LABEL: Record<Layer, DictKey> = {
  vwap: "ovVwap", profile: "ovProfile", structure: "ovStructure", candle: "ovCandles",
  fvg: "ovFvg", sweep: "ovSweep", chart: "ovChart",
};
const GROUP_LAYER: Record<string, Layer> = {
  candle: "candle", fvg: "fvg", sweep: "sweep", structure: "structure", chart: "chart",
};
const BARS = 400;

export default function PatternsTab({ lang }: { lang: Lang }) {
  const fr = lang === "fr";
  const [symbol, setSymbol] = useState("GC=F");
  const [input, setInput] = useState("");
  const [interval, setIv] = useState<ChartInterval>("15m");
  const [preset, setPreset] = useState<string>("essential");
  const [layers, setLayers] = useState<Set<Layer>>(() => new Set(PRESETS.essential));
  const [data, setData] = useState<ChartData | null>(null);
  const [err, setErr] = useState(false);
  const [narrow, setNarrow] = useState(false);
  const [focus, setFocus] = useState<{ i: number; nonce: number } | null>(null);

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 640px)");
    const apply = () => setNarrow(mq.matches);
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);

  useEffect(() => {
    let alive = true;
    setErr(false);
    const load = () => api.chart(symbol, interval, BARS)
      .then((d) => alive && setData(d))
      .catch(() => alive && setErr(true));
    load();
    const id = window.setInterval(load, 60_000);
    return () => { alive = false; window.clearInterval(id); };
  }, [symbol, interval]);

  const pick = (p: string) => { setPreset(p); setLayers(new Set(PRESETS[p])); };
  const toggle = (l: Layer) => {
    setPreset("custom");
    setLayers((s) => { const n = new Set(s); if (n.has(l)) n.delete(l); else n.add(l); return n; });
  };

  const shown = data && data.symbol === symbol && data.interval === interval ? data : null;
  const recent = useMemo(() => shown
    ? shown.events.filter((e) => layers.has(GROUP_LAYER[shown.meta[e.kind]?.group])).slice(-8).reverse()
    : [], [shown, layers]);
  const loc = fr ? "fr-FR" : "en-GB";

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
            {QUICK.map((s) => <Chip key={s} on={s === symbol} onClick={() => setSymbol(s)}>{s}</Chip>)}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          <div role="group" aria-label="Interval" className="flex gap-1">
            {INTERVALS.map((iv) => (
              <Chip key={iv} on={iv === interval} onClick={() => setIv(iv)}>{iv.toUpperCase()}</Chip>
            ))}
          </div>
          <div role="group" aria-label={tr("overlays", lang)} className="flex items-center gap-1 overflow-x-auto">
            <span className="text-[11px] uppercase tracking-wider text-bone-700 mr-1 shrink-0">{tr("overlays", lang)}</span>
            {(["essential", "structure", "all"] as const).map((p) => (
              <Chip key={p} on={preset === p} onClick={() => pick(p)}>
                {tr(`preset_${p}` as DictKey, lang)}
              </Chip>
            ))}
          </div>
        </div>
        <details className="group">
          <summary className="cursor-pointer text-[12px] text-brass-400 hover:text-brass-500 list-none">
            <span className="group-open:hidden">+ {tr("customize", lang)}</span>
            <span className="hidden group-open:inline">− {tr("customize", lang)}</span>
          </summary>
          <div className="flex flex-wrap gap-1.5 mt-2">
            {ALL.map((l) => (
              <Chip key={l} on={layers.has(l)} onClick={() => toggle(l)} check>{tr(LAYER_LABEL[l], lang)}</Chip>
            ))}
          </div>
        </details>
      </div>

      {/* ---- Lecture en clair ---- */}
      {shown && <Reading data={shown} lang={lang} />}

      {/* ---- Graphique ---- */}
      <section className="card p-3 sm:p-4">
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 mb-2 px-1">
          <span className="num text-[14px] text-brass-400">{symbol}</span>
          {shown && (
            <>
              <span className="num text-[22px]">{shown.candles.at(-1)?.c.toFixed(shown.decimals)}</span>
              <span className="text-[12px] text-bone-700">{tr("localTime", lang)}</span>
            </>
          )}
        </div>
        {shown ? (
          <>
            <MarketChart candles={shown.candles} interval={interval} decimals={shown.decimals}
              vwap={shown.vwap} sessionBreaks={shown.session_breaks} profile={shown.profile}
              swings={shown.swings} events={shown.events} fvgs={shown.fvgs} meta={shown.meta}
              layers={layers} height={narrow ? 360 : 480} lang={lang}
              interactive defaultCount={narrow ? 60 : 120} resetKey={`${symbol}|${interval}`}
              focus={focus} />
            {!shown.has_volume && (
              <p className="text-[12px] text-bone-700 mt-2 px-1">{tr("noVolume", lang)}</p>
            )}
          </>
        ) : (
          <div className={`h-[420px] grid place-items-center text-[14px] ${err ? "text-short-400" : "text-bone-700 pulse-soft"}`}>
            {err ? tr("termError", lang) : tr("loading", lang)}
          </div>
        )}
        <Legend lang={lang} layers={layers} />
      </section>

      {shown && (
        <div className="grid lg:grid-cols-[1.6fr_1fr] gap-3">
          <StatsTable data={shown} lang={lang} />
          <section className="card p-4 sm:p-5">
            <h2 className="text-[12px] uppercase tracking-[0.16em] text-bone-500 mb-1">{tr("recentPatterns", lang)}</h2>
            <p className="text-[12px] text-bone-700 mb-3">{fr ? "Touchez un pattern pour le voir sur le graphique." : "Tap a pattern to see it on the chart."}</p>
            {recent.length === 0 ? (
              <p className="text-[14px] text-bone-500">{tr("noPattern", lang)}</p>
            ) : (
              <ul className="space-y-2">
                {recent.map((e, k) => {
                  const m = shown.meta[e.kind];
                  const st = shown.stats.find((s) => s.kind === e.kind);
                  const c = shown.candles[e.i];
                  return (
                    <li key={k}>
                      <button type="button" onClick={() => setFocus({ i: e.i, nonce: Date.now() })}
                        className={`w-full text-left border-l-2 pl-3 py-1 hover:bg-ink-700 rounded-r ${e.dir > 0 ? "border-long-500" : "border-short-500"}`}>
                        <span className="flex flex-wrap justify-between gap-2 text-[13px]">
                          <span className={e.dir > 0 ? "text-long-400" : "text-short-400"}>
                            {e.dir > 0 ? "▲" : "▼"} {m?.[lang]}
                          </span>
                          <span className="num text-bone-700">
                            {c && new Date(c.t).toLocaleString(loc, { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}
                          </span>
                        </span>
                        <span className="block text-[13px] text-bone-500 leading-snug mt-0.5">
                          {fr ? m?.plain_fr : m?.plain_en}
                        </span>
                        {st && <LabelPill s={st} lang={lang} />}
                      </button>
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
/** Décrit en phrases ce que montre le graphique. Une description, pas une prévision. */
function Reading({ data, lang }: { data: ChartData; lang: Lang }) {
  const fr = lang === "fr";
  const price = data.candles.at(-1)!.c;
  const lastOf = (a?: (number | null)[]) => {
    for (let i = (a?.length ?? 0) - 1; i >= 0; i--) if (a![i] != null) return a![i]!;
    return null;
  };
  const vw = lastOf(data.vwap?.vwap);
  const lines: { icon: string; tone: string; text: string }[] = [];

  const t = data.structure.trend;
  lines.push(t === "UPTREND"
    ? { icon: "▲", tone: "text-long-400", text: fr
        ? "Structure haussière : la dernière cassure importante est allée vers le haut (sommets et creux de plus en plus hauts)."
        : "Uptrend structure: the last important break went upward (higher highs and higher lows)." }
    : t === "DOWNTREND"
    ? { icon: "▼", tone: "text-short-400", text: fr
        ? "Structure baissière : la dernière cassure importante est allée vers le bas (sommets et creux de plus en plus bas)."
        : "Downtrend structure: the last important break went downward (lower highs and lower lows)." }
    : { icon: "▬", tone: "text-bone-300", text: fr
        ? "Pas de direction claire : le prix oscille sans enchaîner de sommets ni de creux dans le même sens."
        : "No clear direction: price swings without chaining highs and lows the same way." });

  if (vw != null && data.atr) {
    const d = (price - vw) / data.atr;
    lines.push(Math.abs(d) < 0.3
      ? { icon: "▬", tone: "text-bone-300", text: fr
          ? "Le prix est collé à la VWAP (le prix moyen de la séance, pondéré par les volumes) : acheteurs et vendeurs s'équilibrent."
          : "Price sits on the VWAP (the session's volume-weighted average price): buyers and sellers are balanced." }
      : d > 0
      ? { icon: "▲", tone: "text-long-400", text: fr
          ? "Le prix est au-dessus de la VWAP (le prix moyen de la séance, pondéré par les volumes) : les acheteurs ont l'avantage aujourd'hui."
          : "Price is above the VWAP (the session's volume-weighted average price): buyers have the upper hand today." }
      : { icon: "▼", tone: "text-short-400", text: fr
          ? "Le prix est sous la VWAP (le prix moyen de la séance, pondéré par les volumes) : les vendeurs ont l'avantage aujourd'hui."
          : "Price is below the VWAP (the session's volume-weighted average price): sellers have the upper hand today." });
  }

  const ps = data.prior_session;
  if (ps) {
    lines.push(price > ps.vah
      ? { icon: "▲", tone: "text-long-400", text: fr
          ? "Le prix est au-dessus de la zone où s'est échangé l'essentiel du volume hier : le marché accepte des prix plus élevés."
          : "Price is above the zone where most of yesterday's volume traded: the market accepts higher prices." }
      : price < ps.val
      ? { icon: "▼", tone: "text-short-400", text: fr
          ? "Le prix est sous la zone où s'est échangé l'essentiel du volume hier : le marché accepte des prix plus bas."
          : "Price is below the zone where most of yesterday's volume traded: the market accepts lower prices." }
      : { icon: "▬", tone: "text-bone-300", text: fr
          ? "Le prix est dans la zone où s'est échangé l'essentiel du volume hier : marché équilibré, il tourne souvent autour du prix le plus échangé."
          : "Price is inside the zone where most of yesterday's volume traded: a balanced market that often rotates around the most traded price." });
  }

  const n = data.candles.length;
  const last = [...data.events].reverse().find((e) =>
    ["candle", "sweep", "chart", "structure"].includes(data.meta[e.kind]?.group) && n - 1 - e.i <= 12);
  if (last) {
    const m = data.meta[last.kind];
    const st = data.stats.find((s) => s.kind === last.kind);
    const ago = n - 1 - last.i;
    const verdict = st?.label === "PLAUSIBLE"
      ? (fr ? "il a un peu mieux marché que le hasard sur cet échantillon" : "it did slightly better than chance on this sample")
      : (fr ? "mais ce type de signal n'a pas prouvé qu'il bat le hasard" : "but this kind of signal has not been shown to beat chance");
    lines.push({ icon: last.dir > 0 ? "▲" : "▼", tone: last.dir > 0 ? "text-long-400" : "text-short-400",
      text: fr
        ? `Dernier signal : ${m[lang].toLowerCase()}, il y a ${ago === 0 ? "0 bougie" : `${ago} bougie${ago > 1 ? "s" : ""}`} — ${verdict}.`
        : `Latest signal: ${m[lang].toLowerCase()}, ${ago} candle${ago === 1 ? "" : "s"} ago — ${verdict}.` });
  } else {
    lines.push({ icon: "▬", tone: "text-bone-300", text: fr
      ? "Aucun pattern récent (12 dernières bougies) : rien de particulier à signaler."
      : "No recent pattern (last 12 candles): nothing in particular to report." });
  }

  return (
    <section className="card p-4 sm:p-5 border-l-[3px] border-brass-600">
      <h2 className="text-[12px] uppercase tracking-[0.16em] text-bone-500 mb-3">{tr("readTitle", lang)}</h2>
      <ul className="space-y-2">
        {lines.map((l, k) => (
          <li key={k} className="flex gap-2.5 text-[14.5px] leading-snug text-bone-300">
            <span aria-hidden className={`shrink-0 w-4 text-center ${l.tone}`}>{l.icon}</span>
            <span>{l.text}</span>
          </li>
        ))}
      </ul>
      <p className="text-[12px] text-bone-700 mt-3">{tr("readNote", lang)}</p>
    </section>
  );
}

// ---------------------------------------------------------------------
function Chip({ on, onClick, children, check }: {
  on: boolean; onClick: () => void; children: React.ReactNode; check?: boolean;
}) {
  return (
    <button type="button" onClick={onClick} aria-pressed={on}
      className={`num text-[12px] px-2.5 py-1.5 rounded-pill border transition-colors shrink-0 whitespace-nowrap ${
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
  const fr = lang === "fr";
  const pct = (v?: number | null) => (v == null ? "—" : `${Math.round(v * 100)}`);
  const rows = [...data.stats].sort((a, b) => b.n - a.n);
  const good = rows.filter((s) => s.label === "PLAUSIBLE").length;
  return (
    <section className="card p-4 sm:p-5">
      <h2 className="text-[12px] uppercase tracking-[0.16em] text-bone-500 mb-2">
        {tr("patternStats", lang)}<Help text={tr("patternStatsHelp", lang)} />
      </h2>
      <p className={`text-[14px] leading-snug mb-2 border-l-2 pl-3 ${good ? "border-long-500 text-bone-300" : "border-warn-500 text-bone-300"}`}>
        {good
          ? (fr ? `${good} type(s) de pattern font un peu mieux que le hasard sur cet échantillon. À confirmer sur plus de données.`
                : `${good} pattern type(s) do slightly better than chance on this sample. To be confirmed on more data.`)
          : (fr ? "Aucun pattern ne bat clairement le hasard sur cet échantillon : prenez-les comme des repères visuels, pas comme des signaux d'achat ou de vente."
                : "No pattern clearly beats chance on this sample: treat them as visual landmarks, not as buy or sell signals.")}
      </p>
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
                  <td className="px-1 text-bone-700 hidden sm:table-cell">{s.ci ? `${pct(s.ci[0])}–${pct(s.ci[1])}` : "—"}</td>
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
        {fr
          ? "% ✓ : part des cas où le prix est allé dans le sens du pattern. Hasard : la même mesure sur n'importe quelle bougie. Gain moyen en ATR, coûts déduits."
          : "% ✓: share of cases where price moved the pattern's way. Chance: the same measure on any candle. Average gain in ATR, after costs."}
      </p>
    </section>
  );
}

/** Légende en mots simples, limitée à ce qui est affiché. */
function Legend({ lang, layers }: { lang: Lang; layers: Set<Layer> }) {
  const fr = lang === "fr";
  const items: [string, string][] = [];
  items.push(["▲ ▼", fr ? "vert = haussier, rouge = baissier" : "green = bullish, red = bearish"]);
  if (layers.has("vwap")) items.push(["━", fr ? "ligne dorée = VWAP (prix moyen du jour), pointillés = ses bandes" : "gold line = VWAP (day's average price), dotted = its bands"]);
  if (layers.has("profile")) items.push(["▮", fr ? "barres dorées à droite = où le volume s'est échangé (POC = prix le plus échangé)" : "gold bars on the right = where volume traded (POC = most traded price)"]);
  if (layers.has("candle")) items.push(["E H S", fr ? "E avalement · H marteau · S étoile filante (formes de bougies)" : "E engulfing · H hammer · S shooting star (candle shapes)"]);
  if (layers.has("sweep")) items.push(["$", fr ? "chasse aux stops : le prix perce un ancien sommet/creux puis repart en sens inverse" : "liquidity sweep: price pokes past an old high/low then reverses"]);
  if (layers.has("chart")) items.push(["DT DB", fr ? "double sommet / double creux" : "double top / double bottom"]);
  if (layers.has("structure")) items.push(["BOS CHoCH", fr ? "BOS = la tendance continue · CHoCH = premier signe de retournement · HH/HL/LH/LL = sommets et creux plus hauts ou plus bas" : "BOS = trend continues · CHoCH = first sign of reversal · HH/HL/LH/LL = higher/lower highs and lows"]);
  if (layers.has("fvg")) items.push(["▭", fr ? "zone colorée = trou de prix laissé par un mouvement rapide (FVG)" : "shaded zone = price gap left by a fast move (FVG)"]);
  return (
    <ul className="mt-3 px-1 grid sm:grid-cols-2 gap-x-6 gap-y-1 text-[12px] text-bone-500">
      {items.map(([k, v]) => (
        <li key={k} className="flex gap-2"><span className="num text-bone-300 shrink-0 w-[72px]">{k}</span><span>{v}</span></li>
      ))}
    </ul>
  );
}
