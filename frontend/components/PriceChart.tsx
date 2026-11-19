"use client";

/*
  Graphique en chandeliers, en SVG pur.

  Aucune librairie de charting : le rendu est simple, et une dépendance de
  plus sur le VPS pour dessiner des rectangles ne se justifie pas.

  Ce qui est tracé, et rien d'autre :
    - les bougies 5 minutes,
    - la VWAP de séance (ligne dorée),
    - les niveaux réellement testés, avec leur nombre de touches,
    - le volume en bas, qui sert à juger si un mouvement est soutenu.

  Pas de grille chargée, pas d'axes redondants : sur un graphique de prix,
  chaque trait en trop est du bruit qui masque la structure.
*/

import type { Candle, Level } from "@/lib/api";
import { type Lang, tr } from "@/lib/i18n";

const W = 1000;
const H = 300;
const VOL_H = 54;
const PAD_R = 74;      // place pour l'étiquette de prix courant
const PAD_T = 12;
const PAD_B = 8;

export default function PriceChart({
  candles, levels, vwap, lang,
}: {
  candles: Candle[];
  levels: Level[];
  vwap: number | null;
  lang: Lang;
}) {
  if (candles.length < 2) return null;

  const plotW = W - PAD_R;
  const plotH = H - PAD_T - PAD_B - VOL_H;

  // Échelle de prix : on inclut la VWAP et les niveaux proches pour qu'ils
  // ne sortent jamais du cadre.
  const relevant = levels.filter((l) => Math.abs(l.distance_pct) < 1.6);
  const prices = [
    ...candles.map((c) => c.h),
    ...candles.map((c) => c.l),
    ...(vwap ? [vwap] : []),
    ...relevant.map((l) => l.price),
  ];
  const rawMin = Math.min(...prices);
  const rawMax = Math.max(...prices);
  const margin = (rawMax - rawMin) * 0.08 || 1;
  const min = rawMin - margin;
  const max = rawMax + margin;

  const x = (i: number) => (i / (candles.length - 1)) * plotW;
  const y = (p: number) => PAD_T + plotH - ((p - min) / (max - min)) * plotH;

  const bw = Math.max(1.5, (plotW / candles.length) * 0.62);
  const maxVol = Math.max(...candles.map((c) => c.v)) || 1;
  const volTop = PAD_T + plotH + 16;

  const last = candles[candles.length - 1];
  const first = candles[0];
  const up = last.c >= first.c;
  const lastColor = last.c >= last.o ? "#4fb286" : "#d1614f";

  const vwapPts = vwap
    ? `0,${y(vwap).toFixed(1)} ${plotW.toFixed(1)},${y(vwap).toFixed(1)}`
    : "";

  // Quelques graduations de prix, calées sur des valeurs rondes.
  const ticks = buildTicks(min, max, 4);

  return (
    <figure className="m-0">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full h-auto block"
        role="img"
        aria-label={`${tr("priceChart", lang)} — ${candles.length} bougies`}
      >
        {/* Graduations horizontales, très discrètes */}
        {ticks.map((p) => (
          <g key={p}>
            <line
              x1={0} x2={plotW} y1={y(p)} y2={y(p)}
              stroke="#221e19" strokeWidth="1"
            />
            <text
              x={plotW + 8} y={y(p) + 4}
              fill="#6b6358" fontSize="11"
              fontFamily="var(--font-plex-mono), monospace"
            >
              {p.toFixed(1)}
            </text>
          </g>
        ))}

        {/* Niveaux testés : trait tireté + nombre de touches */}
        {relevant.map((l, i) => {
          const c = l.kind === "resistance" ? "#d1614f" : "#4fb286";
          return (
            <g key={`${l.price}-${i}`}>
              <line
                x1={0} x2={plotW} y1={y(l.price)} y2={y(l.price)}
                stroke={c} strokeWidth="1" strokeDasharray="5 5" opacity="0.55"
              />
              <text
                x={6} y={y(l.price) - 5}
                fill={c} fontSize="10" opacity="0.9"
                fontFamily="var(--font-plex-mono), monospace"
              >
                {l.price.toFixed(1)} · {l.touches}×
              </text>
            </g>
          );
        })}

        {/* Bougies */}
        {candles.map((c, i) => {
          const isUp = c.c >= c.o;
          const col = isUp ? "#4fb286" : "#d1614f";
          const cx = x(i);
          const top = y(Math.max(c.o, c.c));
          const bot = y(Math.min(c.o, c.c));
          const h = Math.max(1, bot - top);
          return (
            <g key={i}>
              <line
                x1={cx} x2={cx} y1={y(c.h)} y2={y(c.l)}
                stroke={col} strokeWidth="1" opacity="0.75"
              />
              <rect
                x={cx - bw / 2} y={top} width={bw} height={h}
                fill={col} opacity={isUp ? 0.85 : 0.9}
              />
            </g>
          );
        })}

        {/* VWAP : le repère que tous les intervenants regardent */}
        {vwap && (
          <>
            <polyline
              points={vwapPts}
              fill="none" stroke="#c8a055" strokeWidth="1.5"
              strokeDasharray="1 0" opacity="0.85"
            />
            <text
              x={plotW + 8} y={y(vwap) + 4}
              fill="#c8a055" fontSize="11"
              fontFamily="var(--font-plex-mono), monospace"
            >
              VWAP
            </text>
          </>
        )}

        {/* Prix courant : étiquette pleine, impossible à rater */}
        <line
          x1={0} x2={plotW} y1={y(last.c)} y2={y(last.c)}
          stroke={lastColor} strokeWidth="1" opacity="0.5"
        />
        <rect
          x={plotW + 4} y={y(last.c) - 10}
          width={PAD_R - 8} height={20} rx="2" fill={lastColor}
        />
        <text
          x={plotW + 10} y={y(last.c) + 4}
          fill="#100e0b" fontSize="12" fontWeight="600"
          fontFamily="var(--font-plex-mono), monospace"
        >
          {last.c.toFixed(2)}
        </text>

        {/* Volume */}
        {candles.map((c, i) => {
          const h = (c.v / maxVol) * VOL_H;
          return (
            <rect
              key={`v${i}`}
              x={x(i) - bw / 2}
              y={volTop + (VOL_H - h)}
              width={bw}
              height={h}
              fill={c.c >= c.o ? "#4fb286" : "#d1614f"}
              opacity="0.28"
            />
          );
        })}
        <line
          x1={0} x2={plotW} y1={volTop + VOL_H} y2={volTop + VOL_H}
          stroke="#2b2620" strokeWidth="1"
        />
        <text
          x={plotW + 8} y={volTop + VOL_H}
          fill="#6b6358" fontSize="10"
          fontFamily="var(--font-plex-mono), monospace"
        >
          VOL
        </text>
      </svg>
    </figure>
  );
}

/** Graduations sur des valeurs rondes plutôt que sur des bornes brutes. */
function buildTicks(min: number, max: number, count: number): number[] {
  const span = max - min;
  const raw = span / count;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? mag * 10;
  const start = Math.ceil(min / step) * step;
  const out: number[] = [];
  for (let p = start; p <= max; p += step) out.push(Number(p.toFixed(4)));
  return out;
}
