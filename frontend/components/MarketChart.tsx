"use client";

/*
  Graphique de marché en SVG pur, dimensionné à son conteneur (texte net sur
  mobile comme sur grand écran).

  Calques, tous optionnels :
    - bougies + volume
    - VWAP de séance et bandes ±1σ / ±2σ (coupées à chaque nouvelle séance)
    - profil de volume du range visible (POC, zone de valeur)
    - structure : pivots HH/HL/LH/LL, BOS / CHoCH
    - patterns : bougies, FVG, chasses aux stops, doubles sommets/creux
    - lignes de ticket (entrée, stop, objectifs)

  Survol / toucher : réticule + fiche de la bougie et des patterns détectés.
  La couleur n'est jamais seule : chaque marqueur porte aussi une forme et
  un libellé.
*/

import { useEffect, useMemo, useRef, useState } from "react";
import type {
  Candle, ChartData, ChartInterval, Fvg, PatternEvent, PatternMeta, Profile, Swing,
} from "@/lib/api";
import type { Lang } from "@/lib/i18n";

export type Layer = "vwap" | "profile" | "structure" | "candle" | "fvg" | "sweep" | "chart";

export interface ChartLine {
  price: number; label: string; color: string; dash?: string;
}

const UP = "#4fb286";
const DOWN = "#d1614f";
const BRASS = "#c8a055";
const GRID = "#221e19";
const AXIS = "#6b6358";
const MONO = "var(--font-plex-mono), monospace";

const PAD_R = 64;
const PAD_T = 14;
const PAD_B = 22;

const CODE: Record<string, string> = {
  engulfing_bull: "E", engulfing_bear: "E", hammer: "H", shooting_star: "S",
  sweep_bull: "$", sweep_bear: "$", double_bottom: "DB", double_top: "DT",
};

export default function MarketChart({
  candles, interval = "15m", decimals = 2, vwap, sessionBreaks, profile,
  swings, events, fvgs, meta, lines, layers, height = 420, lang,
}: {
  candles: Candle[];
  interval?: ChartInterval | string;
  decimals?: number;
  vwap?: ChartData["vwap"];
  sessionBreaks?: number[];
  profile?: Profile | null;
  swings?: Swing[];
  events?: PatternEvent[];
  fvgs?: Fvg[];
  meta?: Record<string, PatternMeta>;
  lines?: ChartLine[];
  layers?: Set<Layer>;
  height?: number;
  lang: Lang;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [W, setW] = useState(900);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(300, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const on = (l: Layer) => !layers || layers.has(l);
  const n = candles.length;
  const H = height;
  const VOL_H = Math.round(H * 0.13);
  const plotW = W - PAD_R;
  const plotH = H - PAD_T - PAD_B - VOL_H - 8;
  const slot = plotW / Math.max(n, 1);

  // Échelle de prix : bougies + calques visibles proches.
  const { min, max } = useMemo(() => {
    if (!n) return { min: 0, max: 1 };
    let lo = Math.min(...candles.map((c) => c.l));
    let hi = Math.max(...candles.map((c) => c.h));
    const span0 = hi - lo || 1;
    const near = (p: number | null | undefined) =>
      p != null && p > lo - span0 * 0.35 && p < hi + span0 * 0.35;
    const extra: number[] = [];
    if (vwap && on("vwap")) {
      for (const k of ["vwap", "u1", "l1"] as const) vwap[k].forEach((v) => near(v) && extra.push(v!));
    }
    lines?.forEach((l) => near(l.price) && extra.push(l.price));
    if (extra.length) {
      lo = Math.min(lo, ...extra);
      hi = Math.max(hi, ...extra);
    }
    const m = (hi - lo) * 0.06 || 1;
    return { min: lo - m, max: hi + m };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candles, vwap, lines, layers]);

  if (n < 2) return null;

  const x = (i: number) => (i + 0.5) * slot;
  const y = (p: number) => PAD_T + plotH - ((p - min) / (max - min)) * plotH;
  const bw = Math.max(1, slot * 0.64);
  const maxVol = Math.max(...candles.map((c) => c.v)) || 1;
  const volTop = PAD_T + plotH + 8;
  const ticks = buildTicks(min, max, H < 360 ? 4 : 6);
  const fmt = (p: number) => p.toFixed(decimals);
  const last = candles[n - 1];
  const lastCol = last.c >= last.o ? UP : DOWN;
  const inView = (p: number) => p >= min && p <= max;

  // Index -> patterns pour la fiche de survol.
  const byBar = new Map<number, PatternEvent[]>();
  events?.forEach((e) => byBar.set(e.i, [...(byBar.get(e.i) ?? []), e]));
  const visible = (e: PatternEvent) => {
    const g = meta?.[e.kind]?.group;
    if (!g) return false;
    if (g === "structure") return on("structure");
    if (g === "candle") return on("candle");
    if (g === "sweep") return on("sweep");
    if (g === "chart") return on("chart");
    return false;                                 // FVG : dessinés en zones
  };

  const onMove = (ev: React.PointerEvent<SVGSVGElement>) => {
    const r = ev.currentTarget.getBoundingClientRect();
    const px = ((ev.clientX - r.left) / r.width) * W;
    const i = Math.floor(px / slot);
    setHover(i >= 0 && i < n ? i : null);
  };

  // ------------------------------------------------------------------
  return (
    <div ref={box} className="relative w-full select-none">
      <svg
        width={W} height={H} viewBox={`0 0 ${W} ${H}`} className="block touch-pan-y"
        role="img" aria-label={`${n} bougies, dernier ${fmt(last.c)}`}
        onPointerMove={onMove} onPointerLeave={() => setHover(null)}
      >
        {/* Graduations */}
        {ticks.map((p) => (
          <g key={p}>
            <line x1={0} x2={plotW} y1={y(p)} y2={y(p)} stroke={GRID} />
            <text x={plotW + 6} y={y(p) + 4} fill={AXIS} fontSize="11" fontFamily={MONO}>
              {fmt(p)}
            </text>
          </g>
        ))}
        {timeTicks(candles, interval, H < 360 ? 3 : 6).map(({ i, label }) => (
          <text key={i} x={x(i)} y={H - 6} fill={AXIS} fontSize="10.5" fontFamily={MONO}
                textAnchor="middle">{label}</text>
        ))}

        {/* Séparateurs de séance */}
        {on("vwap") && sessionBreaks?.map((i) => (
          <line key={`sb${i}`} x1={i * slot} x2={i * slot} y1={PAD_T} y2={volTop + VOL_H}
                stroke="#2b2620" strokeDasharray="2 4" />
        ))}

        {/* Profil de volume (derrière les bougies) */}
        {on("profile") && profile && <ProfileLayer profile={profile} y={y} plotW={plotW}
          min={min} max={max} fmt={fmt} />}

        {/* FVG */}
        {on("fvg") && fvgs?.filter((g, k, all) =>
          // Les gaps comblés restent en filigrane ; seuls les 6 derniers
          // gaps encore ouverts sont prolongés jusqu'au bord droit.
          g.filled_at != null || all.filter((h) => h.filled_at == null && h.i > g.i).length < 6,
        ).map((g, k) => {
          const x0 = x(g.i - 1);
          const x1 = g.filled_at != null ? x(g.filled_at) : plotW;
          if (!inView(g.top) && !inView(g.bottom)) return null;
          const col = g.dir > 0 ? UP : DOWN;
          return (
            <rect key={`f${k}`} x={x0} width={Math.max(2, x1 - x0)}
                  y={y(Math.min(max, g.top))} height={Math.max(1, y(Math.max(min, g.bottom)) - y(Math.min(max, g.top)))}
                  fill={col} opacity={g.filled_at != null ? 0.05 : 0.1}
                  stroke={col} strokeOpacity={g.filled_at != null ? 0.2 : 0.4} strokeDasharray={g.filled_at != null ? "2 3" : undefined} />
          );
        })}

        {/* VWAP + bandes */}
        {on("vwap") && vwap && (
          <g>
            {(["u2", "l2"] as const).map((k) => (
              <path key={k} d={seriesPath(vwap[k], x, y, sessionBreaks)} fill="none"
                    stroke={BRASS} strokeOpacity={0.28} strokeDasharray="2 4" />
            ))}
            {(["u1", "l1"] as const).map((k) => (
              <path key={k} d={seriesPath(vwap[k], x, y, sessionBreaks)} fill="none"
                    stroke={BRASS} strokeOpacity={0.45} strokeDasharray="5 4" />
            ))}
            <path d={seriesPath(vwap.vwap, x, y, sessionBreaks)} fill="none" stroke={BRASS}
                  strokeWidth={1.8} />
          </g>
        )}

        {/* Bougies */}
        {candles.map((c, i) => {
          const col = c.c >= c.o ? UP : DOWN;
          const top = y(Math.max(c.o, c.c));
          const h = Math.max(1, y(Math.min(c.o, c.c)) - top);
          return (
            <g key={i} opacity={hover != null && hover !== i ? 0.92 : 1}>
              <line x1={x(i)} x2={x(i)} y1={y(c.h)} y2={y(c.l)} stroke={col} strokeOpacity={0.8} />
              <rect x={x(i) - bw / 2} y={top} width={bw} height={h} fill={col} />
            </g>
          );
        })}

        {/* Structure : BOS / CHoCH puis pivots */}
        {on("structure") && events?.filter((e) => e.kind.startsWith("bos") || e.kind.startsWith("choch"))
          .map((e, k) => {
            if (e.level == null || !inView(e.level)) return null;
            const col = e.dir > 0 ? UP : DOWN;
            const x0 = x(Math.max(0, e.from_i ?? e.i - 5));
            const choch = e.kind.startsWith("choch");
            return (
              <g key={`s${k}`}>
                <line x1={x0} x2={x(e.i)} y1={y(e.level)} y2={y(e.level)} stroke={col}
                      strokeWidth={choch ? 1.6 : 1.1} strokeDasharray={choch ? undefined : "4 3"} />
                <text x={(x0 + x(e.i)) / 2} y={y(e.level) + (e.dir > 0 ? -4 : 11)} fill={col}
                      fontSize="10" fontFamily={MONO} textAnchor="middle" fontWeight={choch ? 600 : 400}>
                  {choch ? "CHoCH" : "BOS"}
                </text>
              </g>
            );
          })}
        {on("structure") && swings?.map((s, k) => s.label && inView(s.price) && (
          <text key={`w${k}`} x={x(s.i)} y={s.kind === "H" ? y(s.price) - 6 : y(s.price) + 14}
                fill={s.label === "HH" || s.label === "HL" ? UP : DOWN} fontSize="9.5"
                fontFamily={MONO} textAnchor="middle" opacity={0.85}>{s.label}</text>
        ))}

        {/* Doubles sommets / creux */}
        {on("chart") && events?.filter((e) => e.kind.startsWith("double")).map((e, k) => {
          if (e.p1 == null || e.p2 == null || e.level == null || e.neckline == null) return null;
          const col = e.dir > 0 ? UP : DOWN;
          return (
            <g key={`d${k}`}>
              <line x1={x(Math.max(0, e.p1))} x2={x(e.p2)} y1={y(e.level)} y2={y(e.level)}
                    stroke={col} strokeWidth={2} strokeOpacity={0.8} />
              <line x1={x(Math.max(0, e.p1))} x2={x(e.i)} y1={y(e.neckline)} y2={y(e.neckline)}
                    stroke={col} strokeDasharray="3 3" strokeOpacity={0.7} />
            </g>
          );
        })}

        {/* Chasses aux stops : trait du pivot pris à la mèche */}
        {on("sweep") && events?.filter((e) => e.kind.startsWith("sweep")).map((e, k) => {
          if (e.level == null || !inView(e.level)) return null;
          const col = e.dir > 0 ? UP : DOWN;
          return (
            <line key={`sw${k}`} x1={x(Math.max(0, e.from_i ?? e.i))} x2={x(e.i)}
                  y1={y(e.level)} y2={y(e.level)} stroke={col} strokeOpacity={0.55}
                  strokeDasharray="1 3" />
          );
        })}

        {/* Marqueurs de patterns : triangle + code, sous/au-dessus de la bougie */}
        {Array.from(byBar.entries()).map(([i, evs]) => {
          const shown = evs.filter((e) => visible(e) && CODE[e.kind]);
          if (!shown.length || i < 0 || i >= n) return null;
          const c = candles[i];
          return shown.map((e, k) => {
            const bull = e.dir > 0;
            const col = bull ? UP : DOWN;
            const yy = bull ? y(c.l) + 8 + k * 15 : y(c.h) - 8 - k * 15;
            const tri = bull
              ? `M${x(i)},${yy} l-4,6 l8,0 Z`
              : `M${x(i)},${yy} l-4,-6 l8,0 Z`;
            return (
              <g key={`m${i}-${k}`}>
                <path d={tri} fill={col} />
                <text x={x(i)} y={bull ? yy + 16 : yy - 9} fill={col} fontSize="9.5"
                      fontFamily={MONO} textAnchor="middle" fontWeight={600}>{CODE[e.kind]}</text>
              </g>
            );
          });
        })}

        {/* Lignes du ticket */}
        {lines?.map((l, k) => inView(l.price) && (
          <g key={`l${k}`}>
            <line x1={0} x2={plotW} y1={y(l.price)} y2={y(l.price)} stroke={l.color}
                  strokeDasharray={l.dash ?? "6 4"} strokeWidth={1.2} />
            <text x={6} y={y(l.price) - 4} fill={l.color} fontSize="10.5" fontFamily={MONO}>
              {l.label} {fmt(l.price)}
            </text>
          </g>
        ))}

        {/* Prix courant */}
        <line x1={0} x2={plotW} y1={y(last.c)} y2={y(last.c)} stroke={lastCol} strokeOpacity={0.45} />
        <rect x={plotW + 2} y={y(last.c) - 10} width={PAD_R - 4} height={20} rx={2} fill={lastCol} />
        <text x={plotW + 6} y={y(last.c) + 4} fill="#100e0b" fontSize="11.5" fontWeight={600}
              fontFamily={MONO}>{fmt(last.c)}</text>

        {/* Volume */}
        {candles.map((c, i) => {
          const h = (c.v / maxVol) * VOL_H;
          return <rect key={`v${i}`} x={x(i) - bw / 2} y={volTop + VOL_H - h} width={bw}
                       height={h} fill={c.c >= c.o ? UP : DOWN} opacity={0.3} />;
        })}
        <line x1={0} x2={plotW} y1={volTop + VOL_H} y2={volTop + VOL_H} stroke="#2b2620" />

        {/* Réticule */}
        {hover != null && (
          <line x1={x(hover)} x2={x(hover)} y1={PAD_T} y2={volTop + VOL_H}
                stroke="#9a9184" strokeOpacity={0.5} strokeDasharray="3 3" />
        )}
      </svg>

      {hover != null && (
        <HoverCard c={candles[hover]} evs={byBar.get(hover) ?? []} meta={meta} lang={lang}
                   fmt={fmt} interval={interval} left={x(hover) < W / 2} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------
function ProfileLayer({
  profile, y, plotW, min, max, fmt,
}: {
  profile: Profile; y: (p: number) => number; plotW: number;
  min: number; max: number; fmt: (p: number) => string;
}) {
  const maxV = Math.max(...profile.bins.map((b) => b[1])) || 1;
  const width = plotW * 0.22;
  return (
    <g>
      {profile.bins.map(([p, v], k) => {
        const top = p + profile.bin_size;
        if (top < min || p > max) return null;
        const inVA = p >= profile.val - 1e-9 && top <= profile.vah + 1e-9;
        const w = (v / maxV) * width;
        const y0 = y(Math.min(top, max));
        const h = Math.max(0.5, y(Math.max(p, min)) - y0 - 0.5);
        return <rect key={k} x={plotW - w} y={y0} width={w} height={h}
                     fill={BRASS} opacity={inVA ? 0.22 : 0.09} />;
      })}
      {[["POC", profile.poc, 0.9], ["VAH", profile.vah, 0.5], ["VAL", profile.val, 0.5]].map(
        ([lab, p, op]) => (p as number) >= min && (p as number) <= max && (
          <g key={lab as string}>
            <line x1={plotW - width} x2={plotW} y1={y(p as number)} y2={y(p as number)}
                  stroke={BRASS} strokeOpacity={op as number}
                  strokeDasharray={lab === "POC" ? undefined : "3 3"} />
            <text x={plotW - width - 4} y={y(p as number) + 3.5} fill={BRASS}
                  fillOpacity={op as number} fontSize="9.5" fontFamily={MONO} textAnchor="end">
              {lab} {fmt(p as number)}
            </text>
          </g>
        ))}
    </g>
  );
}

function HoverCard({
  c, evs, meta, lang, fmt, interval, left,
}: {
  c: Candle; evs: PatternEvent[]; meta?: Record<string, PatternMeta>; lang: Lang;
  fmt: (p: number) => string; interval: string; left: boolean;
}) {
  const d = new Date(c.t);
  const intraday = ["5m", "15m", "1h"].includes(interval);
  const loc = lang === "fr" ? "fr-FR" : "en-GB";
  const when = intraday
    ? d.toLocaleString(loc, { weekday: "short", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })
    : d.toLocaleDateString(loc, { day: "2-digit", month: "short", year: "numeric" });
  const chg = ((c.c - c.o) / c.o) * 100;
  return (
    <div className={`absolute top-2 ${left ? "right-[70px]" : "left-2"} z-10 card-raised
                     px-3 py-2 text-[12px] leading-snug pointer-events-none max-w-[260px] shadow-xl`}>
      <div className="text-bone-500 mb-1">{when}</div>
      <div className="num grid grid-cols-[auto_1fr] gap-x-3 text-bone-300">
        <span className="text-bone-700">O</span><span>{fmt(c.o)}</span>
        <span className="text-bone-700">H</span><span>{fmt(c.h)}</span>
        <span className="text-bone-700">L</span><span>{fmt(c.l)}</span>
        <span className="text-bone-700">C</span>
        <span className={chg >= 0 ? "text-long-400" : "text-short-400"}>
          {fmt(c.c)} ({chg >= 0 ? "+" : "−"}{Math.abs(chg).toFixed(2)} %)
        </span>
        {c.v > 0 && (<><span className="text-bone-700">V</span>
          <span>{new Intl.NumberFormat(loc, { notation: "compact" }).format(c.v)}</span></>)}
      </div>
      {evs.length > 0 && meta && (
        <ul className="mt-1.5 pt-1.5 border-t border-ink-500 space-y-0.5">
          {evs.map((e, k) => (
            <li key={k} className={e.dir > 0 ? "text-long-400" : "text-short-400"}>
              {e.dir > 0 ? "▲" : "▼"} {meta[e.kind]?.[lang] ?? e.kind}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------
function seriesPath(
  vals: (number | null)[], x: (i: number) => number, y: (p: number) => number,
  breaks?: number[],
): string {
  const br = new Set(breaks ?? []);
  let d = "";
  let pen = false;
  vals.forEach((v, i) => {
    if (v == null || br.has(i)) pen = false;
    if (v == null) return;
    d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
    pen = true;
  });
  return d;
}

function buildTicks(min: number, max: number, count: number): number[] {
  const raw = (max - min) / count;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? mag * 10;
  const out: number[] = [];
  for (let p = Math.ceil(min / step) * step; p <= max; p += step) out.push(Number(p.toFixed(6)));
  return out;
}

function timeTicks(candles: Candle[], interval: string, count: number) {
  const n = candles.length;
  const every = Math.max(1, Math.round(n / count));
  const intraday = ["5m", "15m", "1h"].includes(interval);
  const out: { i: number; label: string }[] = [];
  for (let i = Math.floor(every / 2); i < n; i += every) {
    const d = new Date(candles[i].t);
    const label = intraday
      ? `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`
      : `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}/${String(d.getFullYear()).slice(2)}`;
    out.push({ i, label });
  }
  return out;
}
