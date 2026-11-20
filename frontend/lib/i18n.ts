/*
  Dictionnaire FR / EN de l'habillage. Le contenu produit par le comité est
  déjà bilingue côté API (objets {fr, en}).

  Écrit sans jargon non expliqué : chaque terme technique a son aide.
*/

export type Lang = "fr" | "en";
export type TabId = "decision" | "openbb" | "chart";

export interface Localized {
  fr: string;
  en: string;
}

export const t = (v: Localized | string | undefined | null, lang: Lang): string =>
  v == null ? "" : typeof v === "string" ? v : v[lang];

const dict = {
  appTitle: { fr: "Comité Or", en: "Gold Committee" },
  instrument: { fr: "Or — COMEX, décision toutes les 15 min", en: "Gold — COMEX, decision every 15 min" },

  tabDecision: { fr: "Décision 15m", en: "15m decision" },
  tabOpenBB: { fr: "OpenBB", en: "OpenBB" },
  tabChart: { fr: "Graphique", en: "Chart" },

  liveData: { fr: "Données réelles", en: "Live data" },
  loading: { fr: "Chargement…", en: "Loading…" },
  warmingUp: {
    fr: "Le comité se réunit pour la première fois (chargement des données OpenBB)…",
    en: "The committee is meeting for the first time (loading OpenBB data)…",
  },
  backendDown: {
    fr: "API injoignable pour le moment. Nouvel essai automatique.",
    en: "API unreachable right now. Retrying automatically.",
  },

  // -- Décision --------------------------------------------------------
  theDecision: { fr: "La décision", en: "The decision" },
  longLabel: { fr: "Acheter", en: "Buy" },
  shortLabel: { fr: "Vendre", en: "Sell" },
  noTradeTitle: { fr: "Pas de trade", en: "No trade" },
  noTradeGood: {
    fr: "Ne rien faire est une décision valide. Le système n'est jamais obligé de trouver une opportunité.",
    en: "Doing nothing is a valid decision. The system is never forced to find an opportunity.",
  },
  forBar: { fr: "Barre décidée", en: "Decided bar" },
  nextDecision: { fr: "Prochaine décision", en: "Next decision" },
  inMinutes: { fr: "dans", en: "in" },
  delayNote: {
    fr: "Données gratuites différées d'environ 10 min : chaque décision est publiée ~12 min après la clôture de sa barre. Ne pas courir après le prix.",
    en: "Free data is delayed ~10 min: each decision is published ~12 min after its bar closes. Do not chase price.",
  },
  conviction: { fr: "Conviction", en: "Conviction" },
  convictionHelp: {
    fr: "À quel point le comité est sûr de sa lecture. Ce n'est PAS une probabilité de gain : le journal ci-dessous dit ce que valent réellement ces décisions.",
    en: "How sure the committee is of its reading. It is NOT a probability of winning: the journal below shows what these decisions are actually worth.",
  },
  refresh: { fr: "Réactualiser", en: "Refresh" },

  ticket: { fr: "Ticket", en: "Ticket" },
  hypothetical: { fr: "Ticket hypothétique (non validé)", en: "Hypothetical ticket (not approved)" },
  hypotheticalHelp: {
    fr: "Ce que serait le trade si le comité l'avait validé. Affiché pour comprendre le refus, pas pour être pris.",
    en: "What the trade would be had the committee approved it. Shown to explain the refusal, not to be taken.",
  },
  entry: { fr: "Entrée", en: "Entry" },
  stop: { fr: "Stop", en: "Stop" },
  target1: { fr: "Objectif 1", en: "Target 1" },
  target2: { fr: "Objectif 2", en: "Target 2" },
  chaseLimit: { fr: "Ne pas entrer au-delà de", en: "Do not enter beyond" },
  size: { fr: "Taille", en: "Size" },
  sizeHelp: {
    fr: "Nombre de contrats pour risquer au plus le budget par trade. GC = 100 onces (100 $ par point), MGC = micro, 10 onces (10 $ par point).",
    en: "Contracts to risk at most the per-trade budget. GC = 100 oz ($100 per point), MGC = micro, 10 oz ($10 per point).",
  },
  timeStop: {
    fr: "Stop temporel : sortir si l'objectif 1 n'est pas atteint en 4 heures.",
    en: "Time stop: exit if target 1 is not reached within 4 hours.",
  },
  verdictAPPROVED: { fr: "Approuvé", en: "Approved" },
  verdictREDUCE: { fr: "Taille réduite", en: "Size reduced" },
  verdictREJECT: { fr: "Veto", en: "Vetoed" },

  committee: { fr: "Le comité", en: "The committee" },
  committeeHelp: {
    fr: "Cinq voix, calculées sans IA ni opinion : uniquement VWAP, profil de volume, ATR, structure, et le contexte OpenBB. Structure et VWAP mesurent souvent la même tendance : elles ne comptent que pour une voix.",
    en: "Five voices, computed with no AI and no opinion: only VWAP, volume profile, ATR, structure, and OpenBB context. Structure and VWAP often measure the same trend: together they count as one voice.",
  },
  groupTrend: { fr: "Tendance", en: "Trend" },
  groupLocation: { fr: "Localisation", en: "Location" },
  groupContext: { fr: "Contexte", en: "Context" },
  groupFilter: { fr: "Filtre", en: "Filter" },
  unavailable: { fr: "Indisponible", en: "Unavailable" },
  details: { fr: "Détails", en: "Details" },

  howDecided: { fr: "Comment le CIO a tranché", en: "How the CIO decided" },
  naiveVote: { fr: "Vote naïf", en: "Naive vote" },
  naiveVoteHelp: {
    fr: "Compter les voix (« 3 contre 1 ») est trompeur : des signaux corrélés comptent plusieurs fois. Affiché, puis écarté au profit des groupes indépendants.",
    en: "Counting votes (\"3 against 1\") is misleading: correlated signals get counted several times. Shown, then discarded in favour of independent groups.",
  },
  weightedScore: { fr: "Score pondéré", en: "Weighted score" },
  threshold: { fr: "Seuil", en: "Threshold" },
  redTeam: { fr: "Red Team — pourquoi ce trade perdrait", en: "Red Team — why this trade would lose" },
  noObjection: { fr: "Aucune objection sérieuse.", en: "No serious objection." },
  severity: { fr: "Gravité", en: "Severity" },
  penalty: { fr: "Pénalité de conviction", en: "Conviction penalty" },
  riskManager: { fr: "Risk Manager — droit de veto", en: "Risk Manager — veto power" },
  hardLimit: { fr: "limite dure", en: "hard limit" },

  marketNow: { fr: "Le marché en 15 minutes", en: "The market on 15 minutes" },
  marketNowHelp: {
    fr: "Ligne dorée : VWAP de la séance, avec ses bandes à 1 et 2 écarts-types. À droite : profil de volume (où l'or s'est échangé). Pointillés : objectifs et stop du ticket.",
    en: "Gold line: session VWAP with its 1 and 2 standard-deviation bands. Right side: volume profile (where gold traded). Dotted lines: ticket targets and stop.",
  },

  journal: { fr: "Journal — ce que valent ces décisions", en: "Journal — what these decisions are worth" },
  journalHelp: {
    fr: "Chaque décision est notée sur les barres suivantes : entrée à la clôture de la barre d'après (délai réaliste), stop ou objectif 1 touché en premier, coûts déduits, une seule position à la fois. Le rejeu applique exactement le même moteur à l'historique, barre par barre, sans voir le futur.",
    en: "Each decision is scored on the following bars: entry at the next bar's close (realistic delay), stop or target 1 hit first, costs deducted, one position at a time. The replay runs the exact same engine on history, bar by bar, without seeing the future.",
  },
  sourceLive: { fr: "En direct", en: "Live" },
  sourceReplay: { fr: "Rejeu historique", en: "Historical replay" },
  replayRunning: { fr: "Rejeu en cours", en: "Replay running" },
  decisions: { fr: "Décisions", en: "Decisions" },
  noTradeRate: { fr: "Abstention", en: "No-trade rate" },
  trades: { fr: "Trades indépendants", en: "Independent trades" },
  hitRate: { fr: "Réussite", en: "Hit rate" },
  expectancy: { fr: "Espérance / trade", en: "Expectancy / trade" },
  profitFactor: { fr: "Facteur de profit", en: "Profit factor" },
  worstStreak: { fr: "Pire série de pertes", en: "Worst losing streak" },
  insufficient: {
    fr: "Échantillon insuffisant : moins de 30 trades clôturés. Aucune conclusion possible.",
    en: "Sample too small: fewer than 30 closed trades. No conclusion possible.",
  },
  noEdgeYet: {
    fr: "L'intervalle de confiance couvre le hasard : aucun avantage prouvé à ce stade.",
    en: "The confidence interval covers chance: no proven edge at this stage.",
  },
  recent: { fr: "Dernières décisions", en: "Recent decisions" },
  outcomeWIN: { fr: "Gagné", en: "Win" },
  outcomeLOSS: { fr: "Perdu", en: "Loss" },
  outcomeSCRATCH: { fr: "Sortie au temps", en: "Time exit" },
  outcomeMISSED: { fr: "Raté (prix parti)", en: "Missed (price ran)" },
  outcomeOPEN: { fr: "En cours", en: "Open" },
  outcomeNO_TRADE: { fr: "—", en: "—" },
  inPosition: { fr: "déjà en position", en: "already in position" },

  // -- Graphique -------------------------------------------------------
  symbol: { fr: "Symbole", en: "Symbol" },
  bars: { fr: "Barres", en: "Bars" },
  overlays: { fr: "Afficher", en: "Show" },
  ovVwap: { fr: "VWAP + bandes", en: "VWAP + bands" },
  ovProfile: { fr: "Profil de volume", en: "Volume profile" },
  ovStructure: { fr: "Structure", en: "Structure" },
  ovCandles: { fr: "Bougies", en: "Candlesticks" },
  ovFvg: { fr: "FVG", en: "FVG" },
  ovSweep: { fr: "Chasses aux stops", en: "Liquidity sweeps" },
  ovChart: { fr: "Doubles sommets/creux", en: "Double tops/bottoms" },
  patternStats: { fr: "Ces patterns battent-ils le hasard ?", en: "Do these patterns beat chance?" },
  patternStatsHelp: {
    fr: "Pour chaque pattern : entrée à la clôture de la bougie de détection, sortie N bougies plus tard, coûts déduits, événements qui se chevauchent écartés. Comparé au hasard : la même mesure sur une bougie quelconque. Seuil corrigé pour 14 tests simultanés (Bonferroni). « Validé » est impossible ici : il faudrait plusieurs années de données hors échantillon.",
    en: "For each pattern: entry at the detection candle's close, exit N candles later, costs deducted, overlapping events removed. Compared with chance: the same measure on any candle. Threshold corrected for 14 simultaneous tests (Bonferroni). \"Validated\" is impossible here: it would take years of out-of-sample data.",
  },
  pattern: { fr: "Pattern", en: "Pattern" },
  events: { fr: "Évén.", en: "Events" },
  chance: { fr: "Hasard", en: "Chance" },
  ci95: { fr: "IC 95 %", en: "95% CI" },
  avgGain: { fr: "Gain moy.", en: "Avg gain" },
  labelINSUFFICIENT: { fr: "Échantillon insuffisant", en: "Sample too small" },
  labelNOT_PROVEN: { fr: "Non prouvé", en: "Not proven" },
  labelPLAUSIBLE: { fr: "Plausible", en: "Plausible" },
  recentPatterns: { fr: "Patterns récents", en: "Recent patterns" },
  noPattern: { fr: "Aucun pattern dans la fenêtre affichée.", en: "No pattern in the visible window." },
  noVolume: {
    fr: "Pas de volume pour ce symbole : VWAP et profil indisponibles.",
    en: "No volume for this symbol: VWAP and profile unavailable.",
  },
  horizon: { fr: "Horizon", en: "Horizon" },
  candlesWord: { fr: "bougies", en: "candles" },
  sample: { fr: "Échantillon", en: "Sample" },
  localTime: { fr: "heure locale", en: "local time" },

  // -- Terminal --------------------------------------------------------
  termCommand: { fr: "Symbole", en: "Symbol" },
  termCommandHelp: {
    fr: "Tapez un symbole Yahoo (GC=F, AAPL, EURUSD=X, ^GSPC…) puis Entrée.",
    en: "Type a Yahoo symbol (GC=F, AAPL, EURUSD=X, ^GSPC…) then Enter.",
  },
  termWatchlist: { fr: "Surveillance cross-asset", en: "Cross-asset monitor" },
  termSecurity: { fr: "Fiche instrument", en: "Security" },
  termCurve: { fr: "Courbe des Treasuries US", en: "US Treasury curve" },
  termCurvePrev: { fr: "il y a 1 mois", en: "1 month ago" },
  termNews: { fr: "Fil d'actualité", en: "News wire" },
  termRange52: { fr: "Fourchette 52 sem.", en: "52-week range" },
  termLive: { fr: "Données réelles", en: "Live data" },
  termSourceNote: {
    fr: "Données réelles via OpenBB (Yahoo Finance, Réserve fédérale), différées de 10 à 20 min selon le marché. Le dollar, le taux 10 ans et le VIX de cette page alimentent la voix « Cross-asset » du comité.",
    en: "Real data via OpenBB (Yahoo Finance, Federal Reserve), delayed 10–20 min depending on the market. The dollar, 10-year yield and VIX on this page feed the committee's \"Cross-asset\" voice.",
  },
  termError: {
    fr: "Source de données indisponible pour le moment.",
    en: "Data source unavailable right now.",
  },
  footer: {
    fr: "Aide à la décision, pas un conseil en investissement. Aucun ordre n'est passé automatiquement.",
    en: "Decision support, not investment advice. No order is ever placed automatically.",
  },
} as const;

export type DictKey = keyof typeof dict;

export const tr = (key: DictKey, lang: Lang): string => dict[key][lang];

export default dict;
