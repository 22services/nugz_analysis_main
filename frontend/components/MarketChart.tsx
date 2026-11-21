"use client";

/*
  Graphique de marché en SVG pur, dimensionné à son conteneur.

  Mode interactif (onglet Graphique) :
    - glisser (souris ou doigt) pour se déplacer dans le temps ;
    - pincer (2 doigts), Ctrl + molette, ou boutons +/− pour zoomer ;
    - molette horizontale / flèches du clavier pour se déplacer ;
    - le profil de volume est recalculé sur la fenêtre VISIBLE.

  Calques, tous optionnels : bougies + volume, VWAP et bandes, profil de
  volume, structure (pivots, BOS / CHoCH), patterns (bougies, FVG, chasses
  aux stops, doubles sommets/creux), lignes de ticket.

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
const MONO = "\"IBM Plex Mono\", monospace";

const PAD_R = 64;
const PAD_T = 14;
const PAD_B = 22;
const MIN_BARS = 15;

const CODE: Record<string, string> = {
  engulfing_bull: "E", engulfing_bear: "E", hammer: "H", shooting_star: "S",
  sweep_bull: "$", sweep_bear: "$", double_bottom: "DB", double_top: "DT",
};

const TXT = {
  fr: {
    hint: "Glissez pour déplacer · pincez ou Ctrl + molette pour zoomer",
    zoomIn: "Zoomer", zoomOut: "Dézoomer", older: "Plus ancien", newer: "Plus récent",
    latest: "Dernières barres", shown: "bougies affichées",
  },
  en: {
    hint: "Drag to move · pinch or Ctrl + wheel to zoom",
    zoomIn: "Zoom in", zoomOut: "Zoom out", older: "Earlier", newer: "Later",
    latest: "Latest bars", shown: "candles shown",
  },
} as const;

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

export default function MarketChart({
  candles: allCandles, interval = "15m", decimals = 2, vwap: allVwap,
  sessionBreaks: allBreaks, profile: backendProfile, swings: allSwings,
  events: allEvents, fvgs: allFvgs, meta, lines, layers, height = 420, lang,
  interactive = false, defaultCount, resetKey, focus,
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
  interactive?: boolean;
  defaultCount?: number;
  resetKey?: string;
  focus?: { i: number; nonce: number } | null;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [W, setW] = useState(900);
  const [hover, setHover] = useState<number | null>(null);
  const [dragging, setDragging] = useState(false);

  // ---- Fenêtre visible : `count` barres, décalée de `off` barres vers le passé
  const N = allCandles.length;
  const [count, setCount] = useState(defaultCount ?? N);
  const [off, setOff] = useState(0);
  const minBars = Math.min(MIN_BARS, N);
  const cnt = interactive ? clamp(count, minBars, N) : N;
  const offc = interactive ? clamp(off, 0, N - cnt) : 0;
  const s = N - cnt - offc;
  const e = s + cnt;

  const plotW = W - PAD_R;
  const slot = plotW / Math.max(cnt, 1);
  const live = useRef({ N, cnt, offc, slot, minBars });
  live.current = { N, cnt, offc, slot, minBars };

  useEffect(() => {
    setCount(defaultCount ?? live.current.N);
    setOff(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetKey, defaultCount]);

  useEffect(() => {
    if (!focus) return;
    const L = live.current;
    setOff(clamp(L.N - focus.i - Math.floor(L.cnt / 2), 0, Math.max(0, L.N - L.cnt)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus?.nonce]);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([en]) => setW(Math.max(300, Math.round(en.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Molette : Ctrl/Cmd = zoom ; défilement horizontal = déplacement.
  // La molette verticale seule reste réservée au défilement de la page.
  useEffect(() => {
    const el = box.current;
    if (!el || !interactive) return;
    const onWheel = (ev: WheelEvent) => {
      const L = live.current;
      if (ev.ctrlKey || ev.metaKey) {
        ev.preventDefault();
        const f = Math.exp(ev.deltaY * 0.0025);
        setCount((c) => clamp(Math.round(c * f), L.minBars, L.N));
      } else if (Math.abs(ev.deltaX) > Math.abs(ev.deltaY)) {
        ev.preventDefault();
        const bars = Math.max(1, Math.round(Math.abs(ev.deltaX) / L.slot));
        setOff((o) => clamp(o - Math.sign(ev.deltaX) * bars, 0, L.N - L.cnt));
      }
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [interactive]);

  // ---- Données de la fenêtre (indices ramenés à la fenêtre)
  const candles = useMemo(() => allCandles.slice(s, e), [allCandles, s, e]);
  const n = candles.length;
  const vwap = useMemo(() => allVwap ? {
    vwap: allVwap.vwap.slice(s, e), u1: allVwap.u1.slice(s, e), l1: allVwap.l1.slice(s, e),
    u2: allVwap.u2.slice(s, e), l2: allVwap.l2.slice(s, e),
  } : null, [allVwap, s, e]);
  const sessionBreaks = useMemo(
    () => allBreaks?.filter((i) => i > s && i < e).map((i) => i - s), [allBreaks, s, e]);
  const events = useMemo(() => allEvents?.filter((ev) => ev.i >= s && ev.i < e).map((ev) => ({
    ...ev, i: ev.i - s,
    from_i: ev.from_i != null ? ev.from_i - s : undefined,
    p1: ev.p1 != null ? ev.p1 - s : undefined,
    p2: ev.p2 != null ? ev.p2 - s : undefined,
  })), [allEvents, s, e]);
  const swings = useMemo(
    () => allSwings?.filter((w) => w.i >= s && w.i < e).map((w) => ({ ...w, i: w.i - s })),
    [allSwings, s, e]);
  const fvgs = useMemo(() => allFvgs?.filter((g) => g.i < e && (g.filled_at == null || g.filled_at >= s))
    .map((g) => ({ ...g, i: g.i - s, filled_at: g.filled_at == null ? null : g.filled_at - s })),
  [allFvgs, s, e]);
  const profile = useMemo(
    () => (interactive ? computeProfile(candles) : backendProfile ?? null),
    [interactive, candles, backendProfile]);

  const on = (l: Layer) => !layers || layers.has(l);
  const H = height;
  const VOL_H = Math.round(H * 0.13);
  const plotH = H - PAD_T - PAD_B - VOL_H - 8;

  // Échelle de prix : bougies visibles + calques visibles proches.
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

  // ---- Gestes
  const pts = useRef(new Map<number, number>());
  const gest = useRef<{ x0: number; off0: number; moved: boolean; d0?: number; cnt0?: number }>(
    { x0: 0, off0: 0, moved: false });

  const hoverAt = (ev: React.PointerEvent<SVGSVGElement>) => {
    const r = ev.currentTarget.getBoundingClientRect();
    const i = Math.floor((((ev.clientX - r.left) / r.width) * W) / slot);
    setHover(i >= 0 && i < n ? i : null);
  };
  const onDown = (ev: React.PointerEvent<SVGSVGElement>) => {
    if (!interactive) { hoverAt(ev); return; }
    ev.currentTarget.setPointerCapture(ev.pointerId);
    pts.current.set(ev.pointerId, ev.clientX);
    const g = gest.current;
    if (pts.current.size === 1) {
      Object.assign(g, { x0: ev.clientX, off0: offc, moved: false, d0: undefined });
      if (ev.pointerType !== "mouse") hoverAt(ev);
    } else if (pts.current.size === 2) {
      const [a, b] = [...pts.current.values()];
      Object.assign(g, { d0: Math.abs(a - b) || 1, cnt0: cnt, moved: true });
      setHover(null);
    }
  };
  const onMove = (ev: React.PointerEvent<SVGSVGElement>) => {
    const g = gest.current;
    if (interactive && pts.current.has(ev.pointerId)) {
      pts.current.set(ev.pointerId, ev.clientX);
      if (pts.current.size >= 2 && g.d0) {
        const [a, b] = [...pts.current.values()];
        const d = Math.abs(a - b) || 1;
        setCount(clamp(Math.round((g.cnt0 ?? cnt) * g.d0 / d), minBars, N));
        return;
      }
      const dx = ev.clientX - g.x0;
      if (!g.moved && Math.abs(dx) > 5) { g.moved = true; setDragging(true); setHover(null); }
      if (g.moved) { setOff(clamp(g.off0 + Math.round(dx / slot), 0, N - cnt)); return; }
    }
    if (ev.pointerType === "mouse") hoverAt(ev);
  };
  const onUp = (ev: React.PointerEvent<SVGSVGElement>) => {
    pts.current.delete(ev.pointerId);
    const g = gest.current;
    if (pts.current.size === 1) {            // un doigt reste après un pincement
      const [x] = [...pts.current.values()];
      Object.assign(g, { x0: x, off0: live.current.offc, d0: undefined, moved: true });
    }
    if (pts.current.size === 0) setDragging(false);
  };

  const zoom = (f: number) => setCount((c) => clamp(Math.round(c * f), minBars, N));
  const pan = (bars: number) => setOff((o) => clamp(o + bars, 0, N - cnt));
  const onKey = (ev: React.KeyboardEvent) => {
    if (!interactive) return;
    const k = ev.key;
    if (k === "ArrowLeft") { pan(Math.max(1, Math.round(cnt / 8))); ev.preventDefault(); }
    else if (k === "ArrowRight") { pan(-Math.max(1, Math.round(cnt / 8))); ev.preventDefault(); }
    else if (k === "+" || k === "=") zoom(1 / 1.4);
    else if (k === "-") zoom(1.4);
  };

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
  const T = TXT[lang];

  const byBar = new Map<number, PatternEvent[]>();
  events?.forEach((ev) => byBar.set(ev.i, [...(byBar.get(ev.i) ?? []), ev]));
  const visible = (ev: PatternEvent) => {
    const g = meta?.[ev.kind]?.group;
    if (!g) return false;
    if (g === "structure") return on("structure");
    if (g === "candle") return on("candle");
    if (g === "sweep") return on("sweep");
    if (g === "chart") return on("chart");
    return false;                                 // FVG : dessinés en zones
  };
  const btn = `num min-w-[38px] h-[34px] px-2 text-[14px] rounded-pill border border-ink-500
               text-bone-300 hover:text-bone-100 hover:border-brass-500 disabled:opacity-35`;

  // ------------------------------------------------------------------
  return (
    <div ref={box} className="relative w-full select-none outline-none" tabIndex={interactive ? 0 : -1}
         onKeyDown={onKey}>
      {interactive && (
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 mb-2">
          <span className="text-[12px] text-bone-700">{T.hint}</span>
          <div className="flex items-center gap-1.5">
            <span className="num text-[11px] text-bone-700 mr-1 hidden sm:inline">
              {cnt}/{N} {T.shown}
            </span>
            <button type="button" className={btn} aria-label={T.older} title={T.older}
                    disabled={offc >= N - cnt} onClick={() => pan(Math.max(1, Math.round(cnt / 3)))}>◀</button>
            <button type="button" className={btn} aria-label={T.newer} title={T.newer}
                    disabled={offc <= 0} onClick={() => pan(-Math.max(1, Math.round(cnt / 3)))}>▶</button>
            <button type="button" className={btn} aria-label={T.zoomOut} title={T.zoomOut}
                    disabled={cnt >= N} onClick={() => zoom(1.4)}>−</button>
            <button type="button" className={btn} aria-label={T.zoomIn} title={T.zoomIn}
                    disabled={cnt <= minBars} onClick={() => zoom(1 / 1.4)}>+</button>
            <button type="button" className={`${btn} text-[12px] font-sans`}
                    disabled={offc === 0 && cnt === (defaultCount ?? N)}
                    onClick={() => { setOff(0); setCount(defaultCount ?? N); }}>{T.latest}</button>
          </div>
        </div>
      )}
      <svg
        width={W} height={H} viewBox={`0 0 ${W} ${H}`}
        className={`block ${interactive ? (dragging ? "cursor-grabbing" : "cursor-grab") : ""}`}
        style={{ touchAction: "pan-y" }}
        role="img" aria-label={`${n} bougies, dernier ${fmt(last.c)}`}
        onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp}
        onPointerCancel={onUp} onPointerLeave={(ev) => ev.pointerType === "mouse" && setHover(null)}
      >
        <defs>
          <clipPath id="plot-clip"><rect x={0} y={0} width={plotW} height={H} /></clipPath>
        </defs>

        {/* Graduations */}
        {ticks.map((p) => (
          <g key={p}>
            <line x1={0} x2={plotW} y1={y(p)} y2={y(p)} stroke={GRID} />
            <text x={plotW + 6} y={y(p) + 4} fill={AXIS} fontSize="11" fontFamily={MONO}>{fmt(p)}</text>
          </g>
        ))}
        {timeTicks(candles, interval, clamp(Math.floor(plotW / 110), 2, 6)).map(({ i, label }) => (
          <text key={i} x={x(i)} y={H - 6} fill={AXIS} fontSize="10.5" fontFamily={MONO}
                textAnchor="middle">{label}</text>
        ))}

        <g clipPath="url(#plot-clip)">
          {/* Séparateurs de séance */}
          {on("vwap") && sessionBreaks?.map((i) => (
            <line key={`sb${i}`} x1={i * slot} x2={i * slot} y1={PAD_T} y2={volTop + VOL_H}
                  stroke="#2b2620" strokeDasharray="2 4" />
          ))}

          {/* Profil de volume (derrière les bougies) */}
          {on("profile") && profile && <ProfileLayer profile={profile} y={y} plotW={plotW}
            min={min} max={max} fmt={fmt} />}

          {/* FVG : les gaps comblés restent en filigrane ; seuls les 6 derniers
              gaps encore ouverts sont prolongés jusqu'au bord droit. */}
          {on("fvg") && fvgs?.filter((g, _k, all) =>
            g.filled_at != null || all.filter((h) => h.filled_at == null && h.i > g.i).length < 6,
          ).map((g, k) => {
            const x0 = Math.max(0, x(g.i - 1));
            const x1 = g.filled_at != null ? Math.min(plotW, x(g.filled_at)) : plotW;
            if (!inView(g.top) && !inView(g.bottom)) return null;
            const col = g.dir > 0 ? UP : DOWN;
            const yt = y(Math.min(max, g.top));
            return (
              <rect key={`f${k}`} x={x0} width={Math.max(2, x1 - x0)} y={yt}
                    height={Math.max(1, y(Math.max(min, g.bottom)) - yt)}
                    fill={col} opacity={g.filled_at != null ? 0.05 : 0.1}
                    stroke={col} strokeOpacity={g.filled_at != null ? 0.2 : 0.4}
                    strokeDasharray={g.filled_at != null ? "2 3" : undefined} />
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
              <g key={i}>
                <line x1={x(i)} x2={x(i)} y1={y(c.h)} y2={y(c.l)} stroke={col} strokeOpacity={0.8} />
                <rect x={x(i) - bw / 2} y={top} width={bw} height={h} fill={col} />
              </g>
            );
          })}

          {/* Structure : BOS / CHoCH puis pivots */}
          {on("structure") && events?.filter((ev) => ev.kind.startsWith("bos") || ev.kind.startsWith("choch"))
            .map((ev, k) => {
              if (ev.level == null || !inView(ev.level)) return null;
              const col = ev.dir > 0 ? UP : DOWN;
              const x0 = x(Math.max(0, ev.from_i ?? ev.i - 5));
              const choch = ev.kind.startsWith("choch");
              return (
                <g key={`s${k}`}>
                  <line x1={x0} x2={x(ev.i)} y1={y(ev.level)} y2={y(ev.level)} stroke={col}
                        strokeWidth={choch ? 1.6 : 1.1} strokeDasharray={choch ? undefined : "4 3"} />
                  <text x={(x0 + x(ev.i)) / 2} y={y(ev.level) + (ev.dir > 0 ? -4 : 11)} fill={col}
                        fontSize="10" fontFamily={MONO} textAnchor="middle" fontWeight={choch ? 600 : 400}>
                    {choch ? "CHoCH" : "BOS"}
                  </text>
                </g>
              );
            })}
          {on("structure") && swings?.map((w, k) => w.label && inView(w.price) && (
            <text key={`w${k}`} x={x(w.i)} y={w.kind === "H" ? y(w.price) - 6 : y(w.price) + 14}
                  fill={w.label === "HH" || w.label === "HL" ? UP : DOWN} fontSize="9.5"
                  fontFamily={MONO} textAnchor="middle" opacity={0.85}>{w.label}</text>
          ))}

          {/* Doubles sommets / creux */}
          {on("chart") && events?.filter((ev) => ev.kind.startsWith("double")).map((ev, k) => {
            if (ev.p1 == null || ev.p2 == null || ev.level == null || ev.neckline == null) return null;
            const col = ev.dir > 0 ? UP : DOWN;
            return (
              <g key={`d${k}`}>
                <line x1={x(Math.max(0, ev.p1))} x2={x(ev.p2)} y1={y(ev.level)} y2={y(ev.level)}
                      stroke={col} strokeWidth={2} strokeOpacity={0.8} />
                <line x1={x(Math.max(0, ev.p1))} x2={x(ev.i)} y1={y(ev.neckline)} y2={y(ev.neckline)}
                      stroke={col} strokeDasharray="3 3" strokeOpacity={0.7} />
              </g>
            );
          })}

          {/* Chasses aux stops : trait du pivot pris à la mèche */}
          {on("sweep") && events?.filter((ev) => ev.kind.startsWith("sweep")).map((ev, k) => {
            if (ev.level == null || !inView(ev.level)) return null;
            const col = ev.dir > 0 ? UP : DOWN;
            return (
              <line key={`sw${k}`} x1={x(Math.max(0, ev.from_i ?? ev.i))} x2={x(ev.i)}
                    y1={y(ev.level)} y2={y(ev.level)} stroke={col} strokeOpacity={0.55}
                    strokeDasharray="1 3" />
            );
          })}

          {/* Marqueurs de patterns : triangle + code, sous/au-dessus de la bougie */}
          {Array.from(byBar.entries()).map(([i, evs]) => {
            const shown = evs.filter((ev) => visible(ev) && CODE[ev.kind]);
            if (!shown.length || i < 0 || i >= n) return null;
            const c = candles[i];
            return shown.map((ev, k) => {
              const bull = ev.dir > 0;
              const col = bull ? UP : DOWN;
              const yy = bull ? y(c.l) + 8 + k * 15 : y(c.h) - 8 - k * 15;
              const tri = bull ? `M${x(i)},${yy} l-4,6 l8,0 Z` : `M${x(i)},${yy} l-4,-6 l8,0 Z`;
              return (
                <g key={`m${i}-${k}`}>
                  <path d={tri} fill={col} />
                  <text x={x(i)} y={bull ? yy + 16 : yy - 9} fill={col} fontSize="9.5"
                        fontFamily={MONO} textAnchor="middle" fontWeight={600}>{CODE[ev.kind]}</text>
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
        </g>

        {/* Prix courant (dernière barre VISIBLE) */}
        <line x1={0} x2={plotW} y1={y(last.c)} y2={y(last.c)} stroke={lastCol} strokeOpacity={0.45} />
        <rect x={plotW + 2} y={y(last.c) - 10} width={PAD_R - 4} height={20} rx={2} fill={lastCol} />
        <text x={plotW + 6} y={y(last.c) + 4} fill="#100e0b" fontSize="11.5" fontWeight={600}
              fontFamily={MONO}>{fmt(last.c)}</text>
      </svg>

      {hover != null && candles[hover] && (
        <HoverCard c={candles[hover]} evs={byBar.get(hover) ?? []} meta={meta} lang={lang}
                   fmt={fmt} interval={interval} left={x(hover) < W / 2}
                   top={interactive ? 46 : 8} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------
/** Profil de volume de la fenêtre visible (volume réparti uniformément dans chaque barre). */
function computeProfile(cs: Candle[]): Profile | null {
  if (cs.length < 3) return null;
  let lo = Infinity, hi = -Infinity, tv = 0;
  for (const c of cs) { lo = Math.min(lo, c.l); hi = Math.max(hi, c.h); tv += c.v; }
  if (!(tv > 0) || hi <= lo) return null;
  const nb = 48, size = (hi - lo) / nb;
  const vol = new Array<number>(nb).fill(0);
  for (const c of cs) {
    if (c.v <= 0) continue;
    const b0 = Math.min(nb - 1, Math.floor((c.l - lo) / size));
    const b1 = Math.min(nb - 1, Math.floor((c.h - lo) / size));
    const span = c.h - c.l;
    for (let b = b0; b <= b1; b++) {
      if (span <= 0) { vol[b] += c.v / (b1 - b0 + 1); continue; }
      const bl = lo + b * size;
      const ov = Math.min(c.h, bl + size) - Math.max(c.l, bl);
      if (ov > 0) vol[b] += (c.v * ov) / span;
    }
  }
  let poc = 0;
  vol.forEach((v, i) => { if (v > vol[poc]) poc = i; });
  let a = poc, b = poc, acc = vol[poc];
  const total = vol.reduce((p, q) => p + q, 0);
  while (acc < 0.7 * total && (a > 0 || b < nb - 1)) {
    const up = b < nb - 1 ? vol[b + 1] : -1;
    const dn = a > 0 ? vol[a - 1] : -1;
    if (up >= dn) { b++; acc += up; } else { a--; acc += dn; }
  }
  return {
    poc: lo + (poc + 0.5) * size, vah: lo + (b + 1) * size, val: lo + a * size,
    bin_size: size, bins: vol.map((v, i) => [lo + i * size, v] as [number, number]),
  };
}

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
  c, evs, meta, lang, fmt, interval, left, top,
}: {
  c: Candle; evs: PatternEvent[]; meta?: Record<string, PatternMeta>; lang: Lang;
  fmt: (p: number) => string; interval: string; left: boolean; top: number;
}) {
  const d = new Date(c.t);
  const intraday = ["5m", "15m", "1h"].includes(interval);
  const loc = lang === "fr" ? "fr-FR" : "en-GB";
  const when = intraday
    ? d.toLocaleString(loc, { weekday: "short", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })
    : d.toLocaleDateString(loc, { day: "2-digit", month: "short", year: "numeric" });
  const chg = ((c.c - c.o) / c.o) * 100;
  const L = lang === "fr"
    ? { o: "Ouv.", h: "Haut", l: "Bas", c: "Clôt.", v: "Vol." }
    : { o: "Open", h: "High", l: "Low", c: "Close", v: "Vol." };
  return (
    <div style={{ top }} className={`absolute ${left ? "right-[70px]" : "left-2"} z-10 card-raised
                     px-3 py-2 text-[12px] leading-snug pointer-events-none max-w-[260px] shadow-xl`}>
      <div className="text-bone-500 mb-1">{when}</div>
      <div className="num grid grid-cols-[auto_1fr] gap-x-3 text-bone-300">
        <span className="text-bone-700">{L.o}</span><span>{fmt(c.o)}</span>
        <span className="text-bone-700">{L.h}</span><span>{fmt(c.h)}</span>
        <span className="text-bone-700">{L.l}</span><span>{fmt(c.l)}</span>
        <span className="text-bone-700">{L.c}</span>
        <span className={chg >= 0 ? "text-long-400" : "text-short-400"}>
          {fmt(c.c)} ({chg >= 0 ? "+" : "−"}{Math.abs(chg).toFixed(2)} %)
        </span>
        {c.v > 0 && (<><span className="text-bone-700">{L.v}</span>
          <span>{new Intl.NumberFormat(loc, { notation: "compact" }).format(c.v)}</span></>)}
      </div>
      {evs.length > 0 && meta && (
        <ul className="mt-1.5 pt-1.5 border-t border-ink-500 space-y-0.5">
          {evs.map((ev, k) => (
            <li key={k} className={ev.dir > 0 ? "text-long-400" : "text-short-400"}>
              {ev.dir > 0 ? "▲" : "▼"} {meta[ev.kind]?.[lang] ?? ev.kind}
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
