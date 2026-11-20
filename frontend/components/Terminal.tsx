"use client";

/*
  Terminal de marché, façon Bloomberg.

  Données RÉELLES via OpenBB. Le dollar, le taux 10 ans et le VIX affichés
  ici alimentent aussi la voix « Cross-asset » du comité des 15 minutes.

  Grammaire empruntée au terminal : une barre de commande (symbole + Entrée),
  des panneaux denses titrés par leur mnémonique (GP, WEI, DES, GC, CN),
  chiffres en mono tabulaire, et la couleur doublée d'un signe +/−.
*/

import { useCallback, useEffect, useRef, useState } from "react";
import MarketChart from "@/components/MarketChart";
import { Sparkline } from "@/components/ui";
import { type Lang, tr } from "@/lib/i18n";
import {
  terminal, type CurvePoint, type History, type Interval, type NewsItem,
  type WatchItem,
} from "@/lib/terminal";

const INTERVALS: Interval[] = ["5m", "15m", "1h", "1d", "1W"];
const GROUP_LABEL: Record<WatchItem["group"], [string, string]> = {
  metals: ["Métaux", "Metals"],
  fx: ["Changes", "FX"],
  rates: ["Taux", "Rates"],
  equity: ["Actions", "Equity"],
  energy: ["Énergie", "Energy"],
  crypto: ["Crypto", "Crypto"],
};

export default function Terminal({ lang }: { lang: Lang }) {
  const [symbol, setSymbol] = useState("GC=F");
  const [interval, setInterval_] = useState<Interval>("1d");
  const [watch, setWatch] = useState<WatchItem[] | null>(null);
  const [asOf, setAsOf] = useState<string | null>(null);
  const [hist, setHist] = useState<History | null>(null);
  const [histErr, setHistErr] = useState(false);
  const [news, setNews] = useState<NewsItem[] | null>(null);
  const [curve, setCurve] = useState<{ as_of: string; points: CurvePoint[] } | null>(null);
  const [failed, setFailed] = useState(false);
  const [cmd, setCmd] = useState("");
  const cmdRef = useRef<HTMLInputElement>(null);

  // Liste de surveillance : rafraîchie toutes les 30 s (cache serveur aligné).
  useEffect(() => {
    let alive = true;
    const load = () => terminal.watchlist()
      .then((d) => { if (alive) { setWatch(d.items); setAsOf(d.as_of); setFailed(false); } })
      .catch(() => alive && setFailed(true));
    load();
    const id = window.setInterval(load, 30_000);
    return () => { alive = false; window.clearInterval(id); };
  }, []);

  useEffect(() => {
    terminal.curve().then(setCurve).catch(() => {});
  }, []);

  useEffect(() => {
    let alive = true;
    setHistErr(false);
    const load = () => terminal.history(symbol, interval)
      .then((d) => { if (alive) { setHist(d); setHistErr(d.candles.length < 2); } })
      .catch(() => alive && setHistErr(true));
    load();
    const id = window.setInterval(load, 60_000);
    return () => { alive = false; window.clearInterval(id); };
  }, [symbol, interval]);

  useEffect(() => {
    let alive = true;
    const syms = symbol === "GC=F" ? "GC=F,GLD" : symbol;
    terminal.news(syms).then((d) => alive && setNews(d.items)).catch(() => alive && setNews([]));
    return () => { alive = false; };
  }, [symbol]);

  // Raccourci clavier facon terminal : "/" donne le focus a la commande.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "/" && document.activeElement?.tagName !== "INPUT") {
        e.preventDefault();
        cmdRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const submit = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    const s = cmd.trim().toUpperCase().replace(/\s*<?GO>?$/, "");
    if (s) setSymbol(s);
    setCmd("");
  }, [cmd]);

  const sel = watch?.find((w) => w.symbol === symbol) ?? null;
  const candles = hist?.symbol === symbol ? hist.candles : [];
  const last = sel?.last ?? candles.at(-1)?.c ?? null;
  const first = candles[0]?.c ?? null;
  const periodChg = last != null && first ? ((last - first) / first) * 100 : null;
  const loc = lang === "fr" ? "fr-FR" : "en-US";

  return (
    <div className="space-y-3 rise">
      {/* ---- Barre de commande ---- */}
      <form onSubmit={submit}
            className="card flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5">
        <label htmlFor="term-cmd"
               className="num text-[12px] uppercase tracking-[0.18em] text-brass-400">
          {tr("termCommand", lang)} &gt;
        </label>
        <input
          id="term-cmd" ref={cmdRef} value={cmd}
          onChange={(e) => setCmd(e.target.value)}
          placeholder={`${symbol} <GO>`}
          autoComplete="off" spellCheck={false}
          aria-describedby="term-cmd-help"
          className="num flex-1 min-w-[140px] bg-transparent text-[18px] uppercase
                     text-bone-100 placeholder:text-bone-700 outline-none"
        />
        <span id="term-cmd-help" className="text-[13px] text-bone-700 hidden md:block">
          {tr("termCommandHelp", lang)}
        </span>
        <span className="flex items-center gap-1.5 text-[12px] text-long-400 num">
          <span aria-hidden className="w-1.5 h-1.5 rounded-full bg-long-500 pulse-soft" />
          {tr("termLive", lang)}
          {asOf && (
            <span className="text-bone-700">
              · {new Date(asOf).toLocaleTimeString(loc, { hour: "2-digit", minute: "2-digit" })}
            </span>
          )}
        </span>
      </form>

      {failed && !watch && (
        <p className="card p-5 text-[15px] text-short-400">{tr("termError", lang)}</p>
      )}

      <div className="grid lg:grid-cols-[minmax(0,1.65fr)_minmax(0,1fr)] gap-3">
        <div className="space-y-3 min-w-0">
          {/* ---- GP : graphique ---- */}
          <TPanel code="GP" title={hist?.name ?? symbol}
            right={
              <div role="group" aria-label="Interval" className="flex gap-1">
                {INTERVALS.map((iv) => (
                  <button key={iv} type="button" onClick={() => setInterval_(iv)}
                    aria-pressed={iv === interval}
                    className={`num text-[12px] px-2 py-0.5 rounded-pill border ${
                      iv === interval
                        ? "bg-brass-500 text-ink-900 border-brass-500"
                        : "border-ink-500 text-bone-500 hover:text-bone-100"
                    }`}>
                    {iv.toUpperCase()}
                  </button>
                ))}
              </div>
            }>
            <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 mb-3">
              <span className="num text-[13px] text-brass-400">{symbol}</span>
              <span className="num text-[30px] leading-none">{fmt(last)}</span>
              {sel?.change_pct != null && (
                <Chg value={sel.change_pct} suffix=" %" className="text-[15px]" />
              )}
              {periodChg != null && (
                <span className="num text-[13px] text-bone-700">
                  {interval.toUpperCase()} · {periodChg >= 0 ? "+" : "−"}
                  {Math.abs(periodChg).toFixed(2)} % {lang === "fr" ? "sur la période" : "over period"}
                </span>
              )}
            </div>
            {candles.length >= 2 ? (
              <MarketChart candles={candles} interval={interval} decimals={dp(last)} height={320} lang={lang} />
            ) : (
              <div className={`h-[300px] grid place-items-center text-[14px] ${
                histErr ? "text-short-400" : "text-bone-700 pulse-soft"
              }`}>
                {histErr ? tr("termError", lang) : tr("loading", lang)}
              </div>
            )}
          </TPanel>

          {/* ---- WEI : surveillance ---- */}
          <TPanel code="WEI" title={tr("termWatchlist", lang)}>
            {!watch ? (
              <div className="text-bone-700 text-[14px] pulse-soft py-6">{tr("loading", lang)}</div>
            ) : (
              <div className="overflow-x-auto -mx-1">
                <table className="w-full text-[14px] num">
                  <thead>
                    <tr className="text-[11px] uppercase tracking-[0.12em] text-bone-700 text-right">
                      <th className="text-left font-normal py-1.5 px-1">Ticker</th>
                      <th className="text-left font-normal px-1 hidden sm:table-cell">
                        {lang === "fr" ? "Nom" : "Name"}
                      </th>
                      <th className="font-normal px-1">{lang === "fr" ? "Dernier" : "Last"}</th>
                      <th className="font-normal px-1">Var.</th>
                      <th className="font-normal px-1">%</th>
                      <th className="font-normal px-1 hidden md:table-cell">1M</th>
                    </tr>
                  </thead>
                  <tbody>
                    {watch.map((w, i) => {
                      const newGroup = i === 0 || watch[i - 1].group !== w.group;
                      const active = w.symbol === symbol;
                      const up = (w.change_pct ?? 0) >= 0;
                      return (
                        <tr key={w.symbol}
                            onClick={() => setSymbol(w.symbol)}
                            className={`cursor-pointer text-right ${
                              newGroup && i > 0 ? "border-t border-ink-600" : ""
                            } ${active ? "bg-ink-700" : "hover:bg-ink-850"}`}>
                          <td className="text-left py-1.5 px-1">
                            <button type="button" onClick={() => setSymbol(w.symbol)}
                              aria-pressed={active}
                              className={active ? "text-brass-400" : "text-bone-300"}>
                              {w.symbol}
                            </button>
                            {newGroup && (
                              <span className="ml-2 text-[10px] uppercase tracking-wider text-bone-700 font-sans">
                                {GROUP_LABEL[w.group][lang === "fr" ? 0 : 1]}
                              </span>
                            )}
                          </td>
                          <td className="text-left px-1 text-bone-500 font-sans hidden sm:table-cell truncate max-w-[150px]">
                            {w.name}
                          </td>
                          <td className="px-1 text-bone-100">{fmt(w.last)}</td>
                          <td className="px-1"><Chg value={w.change} digits={dp(w.last)} /></td>
                          <td className="px-1"><Chg value={w.change_pct} suffix="%" /></td>
                          <td className="px-1 hidden md:table-cell">
                            <span className="inline-block align-middle opacity-80">
                              <Sparkline values={w.spark} width={70} height={18}
                                stroke={up ? "#4fb286" : "#d1614f"} />
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </TPanel>
        </div>

        <div className="space-y-3 min-w-0">
          {/* ---- DES : fiche ---- */}
          <TPanel code="DES" title={tr("termSecurity", lang)}>
            {sel ? (
              <>
                <dl className="grid grid-cols-2 gap-x-5 gap-y-1.5 text-[13px]">
                  {([
                    ["Open", sel.open], ["High", sel.high], ["Low", sel.low],
                    ["Bid", sel.bid], ["Ask", sel.ask],
                    ["Vol.", sel.volume],
                    ["MA 50", sel.ma_50d], ["MA 200", sel.ma_200d],
                  ] as [string, number | null][]).map(([k, v]) => (
                    <div key={k} className="flex justify-between gap-2 border-b border-ink-700 py-0.5">
                      <dt className="text-bone-700">{k}</dt>
                      <dd className="num text-bone-300">
                        {k === "Vol." ? fmtVol(v, loc) : fmt(v)}
                      </dd>
                    </div>
                  ))}
                </dl>
                <Range52 lo={sel.year_low} hi={sel.year_high} last={sel.last} lang={lang} />
              </>
            ) : !watch ? (
              <div className="text-bone-700 text-[14px] pulse-soft py-4">{tr("loading", lang)}</div>
            ) : (
              <p className="text-[14px] text-bone-500">
                {symbol} — {lang === "fr"
                  ? "hors liste de surveillance : graphique et actualités seulement."
                  : "not in the watchlist: chart and news only."}
              </p>
            )}
          </TPanel>

          {/* ---- GC : courbe des taux ---- */}
          <TPanel code="GC" title={tr("termCurve", lang)}
            right={curve && <span className="num text-[11px] text-bone-700">{curve.as_of}</span>}>
            {curve ? <Curve points={curve.points} lang={lang} />
              : <div className="h-[150px] grid place-items-center text-bone-700 text-[14px] pulse-soft">
                  {tr("loading", lang)}
                </div>}
          </TPanel>

          {/* ---- CN : actualités ---- */}
          <TPanel code="CN" title={tr("termNews", lang)}>
            {!news ? (
              <div className="text-bone-700 text-[14px] pulse-soft py-4">{tr("loading", lang)}</div>
            ) : news.length === 0 ? (
              <p className="text-[14px] text-bone-500">—</p>
            ) : (
              <ul className="max-h-[420px] overflow-y-auto -mr-2 pr-2 divide-y divide-ink-700">
                {news.map((n) => (
                  <li key={n.url} className="py-2">
                    <div className="num text-[11px] text-bone-700 flex gap-2">
                      <span className="text-brass-500">{ago(n.date, lang)}</span>
                      <span className="truncate">{n.source}</span>
                    </div>
                    <a href={n.url} target="_blank" rel="noopener noreferrer"
                       className="text-[14px] leading-snug text-bone-100 hover:text-brass-400">
                      {n.title}
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </TPanel>
        </div>
      </div>

      <p className="text-[12px] text-bone-700 leading-snug">{tr("termSourceNote", lang)}</p>
    </div>
  );
}

// ---------------------------------------------------------------------
function TPanel({
  code, title, right, children,
}: { code: string; title: string; right?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="card overflow-hidden" aria-label={title}>
      <header className="flex items-center gap-3 px-4 py-2 bg-ink-850 border-b border-ink-600">
        <span className="num text-[11px] font-semibold px-1.5 py-[1px] rounded-pill
                         bg-brass-500 text-ink-900">{code}</span>
        <h2 className="text-[12px] uppercase tracking-[0.16em] text-bone-500 truncate">{title}</h2>
        <div className="flex-1" />
        {right}
      </header>
      <div className="p-4">{children}</div>
    </section>
  );
}

function Chg({
  value, suffix = "", digits = 2, className = "",
}: { value: number | null; suffix?: string; digits?: number; className?: string }) {
  if (value == null) return <span className="text-bone-700">—</span>;
  const up = value >= 0;
  return (
    <span className={`num ${up ? "text-long-400" : "text-short-400"} ${className}`}>
      {up ? "+" : "−"}{Math.abs(value).toFixed(digits)}{suffix}
    </span>
  );
}

function Range52({
  lo, hi, last, lang,
}: { lo: number | null; hi: number | null; last: number | null; lang: Lang }) {
  if (lo == null || hi == null || last == null || hi <= lo) return null;
  const pos = Math.min(100, Math.max(0, ((last - lo) / (hi - lo)) * 100));
  return (
    <div className="mt-4">
      <div className="text-[11px] uppercase tracking-[0.14em] text-bone-700 mb-1.5">
        {tr("termRange52", lang)} · <span className="num">{pos.toFixed(0)} %</span>
      </div>
      <div className="relative h-2 bg-ink-700 rounded-[1px]" role="img"
           aria-label={`${pos.toFixed(0)} % of 52-week range`}>
        <span className="absolute inset-y-0 left-0 bg-brass-600/40" style={{ width: `${pos}%` }} />
        <span className="absolute -top-1 w-[3px] h-4 bg-brass-400" style={{ left: `calc(${pos}% - 1px)` }} />
      </div>
      <div className="flex justify-between num text-[12px] text-bone-500 mt-1">
        <span>{fmt(lo)}</span><span>{fmt(hi)}</span>
      </div>
    </div>
  );
}

function Curve({ points, lang }: { points: CurvePoint[]; lang: Lang }) {
  const pts = points.filter((p) => p.now != null);
  if (pts.length < 2) return null;
  const vals = pts.flatMap((p) => [p.now!, ...(p.prev != null ? [p.prev] : [])]);
  const min = Math.min(...vals) - 0.05, max = Math.max(...vals) + 0.05;
  const W = 400, H = 150, PL = 34, PB = 20, PT = 8;
  const x = (i: number) => PL + (i / (pts.length - 1)) * (W - PL - 8);
  const y = (v: number) => PT + (1 - (v - min) / (max - min)) * (H - PT - PB);
  const line = (k: "now" | "prev") =>
    pts.map((p, i) => (p[k] != null ? `${x(i).toFixed(1)},${y(p[k]!).toFixed(1)}` : null))
      .filter(Boolean).join(" ");
  const ten = pts.find((p) => p.tenor === "10Y"), two = pts.find((p) => p.tenor === "2Y");
  const spread = ten?.now != null && two?.now != null ? (ten.now - two.now) * 100 : null;

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img"
           aria-label={pts.map((p) => `${p.tenor} ${p.now}%`).join(", ")}>
        {[min + 0.05, (min + max) / 2, max - 0.05].map((v) => (
          <g key={v}>
            <line x1={PL} x2={W - 8} y1={y(v)} y2={y(v)} stroke="#2b2620" />
            <text x={PL - 6} y={y(v) + 4} textAnchor="end" fontSize="10"
                  fill="#6b6358" className="num">{v.toFixed(2)}</text>
          </g>
        ))}
        <polyline points={line("prev")} fill="none" stroke="#6b6358"
                  strokeWidth="1.5" strokeDasharray="4 3" />
        <polyline points={line("now")} fill="none" stroke="#d9b26a" strokeWidth="2" />
        {pts.map((p, i) => (
          <g key={p.tenor}>
            <circle cx={x(i)} cy={y(p.now!)} r="2.5" fill="#d9b26a" />
            <text x={x(i)} y={H - 5} textAnchor="middle" fontSize="10"
                  fill="#9a9184" className="num">{p.tenor}</text>
          </g>
        ))}
      </svg>
      <div className="flex flex-wrap justify-between gap-2 text-[12px] mt-1">
        <span className="flex items-center gap-3 text-bone-500">
          <span className="flex items-center gap-1.5">
            <span className="w-4 h-[2px] bg-brass-400" />{lang === "fr" ? "Actuelle" : "Current"}
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-4 border-t-[1.5px] border-dashed border-bone-700" />
            {tr("termCurvePrev", lang)}
          </span>
        </span>
        {spread != null && (
          <span className="num text-bone-300">
            2s10s {spread >= 0 ? "+" : "−"}{Math.abs(spread).toFixed(0)} bp
          </span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------
/** Décimales selon l'ordre de grandeur : 4 pour le change, 2 sinon. */
function dp(v: number | null): number {
  if (v == null) return 2;
  const a = Math.abs(v);
  return a < 10 ? 4 : a < 1000 ? 2 : a < 100000 ? 2 : 0;
}

function fmt(v: number | null): string {
  if (v == null) return "—";
  const d = dp(v);
  return v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
}

function fmtVol(v: number | null, loc: string): string {
  if (!v) return "—";
  return new Intl.NumberFormat(loc, { notation: "compact", maximumFractionDigits: 1 }).format(v);
}

function ago(iso: string | null, lang: Lang): string {
  if (!iso) return "";
  const m = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  if (h < 24) return lang === "fr" ? `${h} h` : `${h}h`;
  return lang === "fr" ? `${Math.floor(h / 24)} j` : `${Math.floor(h / 24)}d`;
}
