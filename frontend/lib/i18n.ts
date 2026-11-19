/*
  Dictionnaire FR / EN.

  Le contenu produit par les agents est déjà bilingue côté backend (chaque
  champ est un objet {fr, en}). Ce dictionnaire ne couvre que l'habillage de
  l'interface : libellés, titres, aides.

  Les textes sont volontairement écrits sans jargon : le dashboard doit être
  compréhensible par quelqu'un qui n'a jamais tradé.
*/

export type Lang = "fr" | "en";
export type Mode = "simple" | "expert";
export type TabId = "decision" | "marche" | "terminal" | "comite" | "ticket" | "journal";

export interface Localized {
  fr: string;
  en: string;
}

export const t = (v: Localized | undefined | null, lang: Lang): string =>
  v ? v[lang] : "";

const dict = {
  // -- Habillage ------------------------------------------------------
  appTitle: { fr: "Comité Or", en: "Gold Committee" },
  appSubtitle: {
    fr: "Huit agents d'analyse, une décision",
    en: "Eight analysis agents, one decision",
  },
  instrument: { fr: "Or — contrat à terme", en: "Gold — futures contract" },
  session: { fr: "Session", en: "Session" },
  modeSimple: { fr: "Simple", en: "Simple" },
  modeExpert: { fr: "Expert", en: "Expert" },
  modeHelp: {
    fr: "Le mode Simple explique tout sans jargon. Le mode Expert affiche le détail chiffré et le ticket institutionnel complet.",
    en: "Simple mode explains everything without jargon. Expert mode shows the full numeric detail and the institutional ticket.",
  },

  // -- Onglets --------------------------------------------------------
  tabDecision: { fr: "Décision", en: "Decision" },
  tabMarche: { fr: "Marché", en: "Market" },
  tabTerminal: { fr: "Terminal", en: "Terminal" },
  tabComite: { fr: "Comité", en: "Committee" },
  tabTicket: { fr: "Ticket", en: "Ticket" },
  tabJournal: { fr: "Journal", en: "Journal" },

  // -- Décision -------------------------------------------------------
  theDecision: { fr: "La décision", en: "The decision" },
  analyseNow: { fr: "Analyser maintenant", en: "Analyse now" },
  analysing: { fr: "Analyse en cours…", en: "Analysing…" },
  conviction: { fr: "Conviction", en: "Conviction" },
  convictionHelp: {
    fr: "Ce score mesure à quel point le système est sûr de sa lecture. Ce n'est PAS une probabilité de gagner de l'argent — tant que le journal n'a pas assez de trades pour le vérifier, traitez-le comme un avis, pas comme une statistique.",
    en: "This score measures how confident the system is in its reading. It is NOT a probability of making money — until the journal has enough trades to verify it, treat it as an opinion, not a statistic.",
  },
  noTradeTitle: { fr: "Pas de trade", en: "No trade" },
  noTradeGood: {
    fr: "Ne rien faire est une décision valide. Le système n'est pas obligé de trouver une opportunité à chaque fois.",
    en: "Doing nothing is a valid decision. The system is not required to find an opportunity every time.",
  },
  longLabel: { fr: "Acheter", en: "Buy" },
  shortLabel: { fr: "Vendre", en: "Sell" },
  horizon: { fr: "Horizon", en: "Horizon" },
  lastRun: { fr: "Dernier run", en: "Last run" },
  scenario: { fr: "Scénario de démonstration", en: "Demo scenario" },
  scenarioHelp: {
    fr: "Tant que les données réelles ne sont pas branchées, ces scénarios montrent comment le comité réagit à différents états de marché.",
    en: "Until live data is connected, these scenarios show how the committee reacts to different market states.",
  },
  whoDecided: { fr: "Qui a tranché", en: "Who decided" },
  keyNumbers: { fr: "Chiffres clés", en: "Key numbers" },

  // -- Comité ---------------------------------------------------------
  committee: { fr: "Le comité", en: "The committee" },
  committeeIntro: {
    fr: "Chaque agent a un mandat précis et un droit de parole limité à son domaine. Deux d'entre eux peuvent bloquer la décision à eux seuls.",
    en: "Each agent has a precise mandate and may only speak within its domain. Two of them can block the decision on their own.",
  },
  mandate: { fr: "Mandat", en: "Mandate" },
  plainWords: { fr: "En clair", en: "In plain words" },
  reading: { fr: "Lecture", en: "Reading" },
  evidence: { fr: "Éléments retenus", en: "Evidence" },
  warnings: { fr: "Avertissements", en: "Warnings" },
  canVeto: { fr: "Droit de veto", en: "Veto power" },
  tools: { fr: "Outils", en: "Tools" },
  notConnected: { fr: "Non branché", en: "Not connected" },
  deterministic: { fr: "Calcul déterministe", en: "Deterministic" },
  toolsConnected: { fr: "outils branchés", en: "tools connected" },

  // -- Statuts --------------------------------------------------------
  statusIDLE: { fr: "En attente", en: "Idle" },
  statusRUNNING: { fr: "En cours", en: "Running" },
  statusDONE: { fr: "Terminé", en: "Done" },
  statusBLOCKED: { fr: "Bloqué", en: "Blocked" },
  statusSKIPPED: { fr: "Ignoré", en: "Skipped" },
  statusFAILED: { fr: "Échec", en: "Failed" },

  // -- Marché ---------------------------------------------------------
  marketState: { fr: "État du marché", en: "Market state" },
  priceChart: { fr: "Prix — 5 minutes", en: "Price — 5 minutes" },
  chartHelp: {
    fr: "Chaque bougie couvre 5 minutes. Le corps va du prix d'ouverture au prix de clôture ; les traits fins montrent les extrêmes atteints. La ligne dorée est le prix moyen pondéré par les volumes de la séance.",
    en: "Each candle covers 5 minutes. The body runs from open to close; the thin wicks show the extremes reached. The gold line is the session's volume-weighted average price.",
  },
  structure: { fr: "Structure", en: "Structure" },
  momentum: { fr: "Momentum", en: "Momentum" },
  volatility: { fr: "Volatilité", en: "Volatility" },
  keyLevels: { fr: "Niveaux clés", en: "Key levels" },
  coherence: { fr: "Cohérence multi-unités", en: "Cross-timeframe agreement" },
  coherenceHelp: {
    fr: "Mesure si les différentes échelles de temps racontent la même histoire. Sous 40 %, le marché part dans tous les sens et le signal ne vaut pas grand-chose.",
    en: "Measures whether the different time scales tell the same story. Below 40%, the market is going nowhere and the signal is worth little.",
  },
  dataFreshness: { fr: "Fraîcheur des données", en: "Data freshness" },
  sources: { fr: "sources", en: "sources" },
  sourcesTitle: { fr: "Sources de données", en: "Data sources" },
  eventRisk: { fr: "Risque événementiel", en: "Event risk" },
  riskNORMAL: { fr: "normal", en: "normal" },
  riskELEVATED: { fr: "élevé", en: "elevated" },
  riskHIGH_EVENT_RISK: { fr: "majeur", en: "high" },
  nextEvent: { fr: "Prochains événements", en: "Upcoming events" },
  triggers: { fr: "Déclencheurs détectés", en: "Detected triggers" },
  noTriggers: {
    fr: "Aucun déclencheur : le marché ne propose rien en ce moment. C'est le cas le plus fréquent.",
    en: "No trigger: the market is offering nothing right now. This is the most common case.",
  },
  triggersHelp: {
    fr: "Le système ne réveille les agents que lorsqu'il repère une situation qui mérite une analyse. Le reste du temps, il observe sans rien coûter.",
    en: "The system only wakes the agents when it spots a situation worth analysing. The rest of the time it watches at no cost.",
  },
  resistance: { fr: "Résistance", en: "Resistance" },
  support: { fr: "Support", en: "Support" },
  touches: { fr: "touches", en: "touches" },

  // -- Ticket ---------------------------------------------------------
  ticket: { fr: "Ticket de trade", en: "Trade ticket" },
  ticketEmpty: {
    fr: "Aucun ticket : le comité n'a pas produit de proposition sur ce run.",
    en: "No ticket: the committee produced no proposal on this run.",
  },
  thesis: { fr: "Thèse d'investissement", en: "Investment thesis" },
  bullCase: { fr: "Arguments pour la hausse", en: "Bull case" },
  bearCase: { fr: "Arguments pour la baisse", en: "Bear case" },
  invalidation: {
    fr: "Ce qui rendrait cette thèse fausse",
    en: "What would make this thesis wrong",
  },
  tradeStructure: { fr: "Structure du trade", en: "Trade structure" },
  entryZone: { fr: "Zone d'entrée", en: "Entry zone" },
  stopLogic: { fr: "Logique de stop", en: "Stop logic" },
  targetLogic: { fr: "Logique d'objectif", en: "Target logic" },
  timeStop: { fr: "Stop temporel", en: "Time stop" },
  riskSection: { fr: "Risque", en: "Risk" },
  monitoring: { fr: "À surveiller", en: "To monitor" },
  riskBudget: { fr: "Budget de risque", en: "Risk budget" },
  liquidity: { fr: "Liquidité", en: "Liquidity" },
  trend: { fr: "Tendance", en: "Trend" },
  macroRegime: { fr: "Régime macro", en: "Macro regime" },

  // -- Red Team -------------------------------------------------------
  objections: { fr: "Objections", en: "Objections" },
  redTeamIntro: {
    fr: "Cet agent part du principe que le trade va perdre et cherche pourquoi. Plus il trouve d'objections sérieuses, plus la conviction finale est réduite.",
    en: "This agent assumes the trade will lose and looks for why. The more serious objections it finds, the more the final conviction is cut.",
  },
  rebuttal: { fr: "Réponse de l'analyste", en: "Analyst rebuttal" },
  stillStands: { fr: "L'objection tient toujours", en: "Objection still stands" },
  resolved: { fr: "Objection levée", en: "Objection resolved" },
  severity: { fr: "Gravité", en: "Severity" },

  // -- Journal --------------------------------------------------------
  journal: { fr: "Journal", en: "Journal" },
  journalIntro: {
    fr: "Le système tourne à blanc : aucune position n'est envoyée au marché. Ce journal enregistre chaque décision pour pouvoir dire, dans quelques mois, si le comité apporte vraiment quelque chose.",
    en: "The system runs in shadow mode: no position is ever sent to the market. This journal records every decision so that, in a few months, we can tell whether the committee actually adds anything.",
  },
  calibration: { fr: "Calibration de la conviction", en: "Conviction calibration" },
  calibrationHelp: {
    fr: "Compare la conviction annoncée au résultat réellement obtenu. Tant qu'il n'y a pas au moins 30 trades clôturés, cette courbe ne veut rien dire — et le dashboard vous le dira plutôt que d'afficher un chiffre rassurant.",
    en: "Compares announced conviction with the result actually achieved. Until at least 30 trades are closed this curve means nothing — and the dashboard will say so rather than show a reassuring number.",
  },
  perAgent: { fr: "Fiabilité par agent", en: "Reliability by agent" },
  perAgentHelp: {
    fr: "La courbe globale ne suffit pas. Si l'agent technique est bien calibré et l'agent macro mal calibré, la moyenne des deux ne veut rien dire. Ce tableau répond à la vraie question : QUI faut-il écouter, et à partir de quel niveau de conviction.",
    en: "The overall curve is not enough. If the technical agent is well calibrated and the macro agent is not, averaging the two means nothing. This table answers the real question: WHO should you listen to, and above what conviction level.",
  },
  noAgentData: {
    fr: "La fiabilité par agent apparaîtra ici dès que des trades seront clôturés.",
    en: "Per-agent reliability will appear here once trades start closing.",
  },
  hatchedHelp: {
    fr: "Barres hachurées = échantillon insuffisant pour conclure.",
    en: "Hatched bars = sample too small to conclude.",
  },
  notEnoughData: {
    fr: "Pas encore assez de trades clôturés pour mesurer quoi que ce soit.",
    en: "Not enough closed trades yet to measure anything.",
  },
  closedOf: { fr: "trade(s) clôturé(s) sur les 30 nécessaires.", en: "closed trade(s) out of the 30 required." },
  totalRuns: { fr: "Analyses", en: "Runs" },
  noTradeRate: { fr: "Taux de « pas de trade »", en: "No-trade rate" },
  noTradeRateSub: {
    fr: "S'abstenir est le résultat le plus fréquent, et c'est normal.",
    en: "Abstaining is the most frequent outcome, and that is normal.",
  },
  avgConviction: { fr: "Conviction moyenne", en: "Average conviction" },
  decisions: { fr: "Décisions", en: "Decisions" },
  recordedDecisions: { fr: "Décisions enregistrées", en: "Recorded decisions" },
  verdictAPPROVED: { fr: "approuvé", en: "approved" },
  verdictREDUCE: { fr: "taille réduite", en: "size cut" },
  verdictREJECT: { fr: "rejeté", en: "rejected" },
  noDecision: { fr: "Aucune décision enregistrée.", en: "No decision recorded." },

  // -- Bandeau V1 -----------------------------------------------------
  mvpBanner: {
    fr: "Version 1 — les huit agents existent et le pipeline tourne, mais aucun outil n'est encore branché. Les données affichées sont simulées.",
    en: "Version 1 — the eight agents exist and the pipeline runs, but no tool is connected yet. The data shown is simulated.",
  },
  mvpShort: { fr: "Données simulées", en: "Simulated data" },
  pipeline: { fr: "Pipeline", en: "Pipeline" },
  stageDATA: { fr: "Données", en: "Data" },
  stageANALYSIS: { fr: "Analyse", en: "Analysis" },
  stageRED_TEAM: { fr: "Contradiction", en: "Challenge" },
  stageREBUTTAL: { fr: "Réponses", en: "Rebuttal" },
  stageRISK: { fr: "Risque", en: "Risk" },
  stageDECISION: { fr: "Décision", en: "Decision" },
  stageCOMPLETE: { fr: "Terminé", en: "Complete" },
  stageHALTED: { fr: "Interrompu", en: "Halted" },
  seriesFront: { fr: "contrat proche", en: "front month" },
  seriesCont: { fr: "série continue", en: "continuous" },
  series: { fr: "Série", en: "Series" },
  loading: { fr: "Chargement…", en: "Loading…" },
  backendDown: {
    fr: "Backend injoignable. Lancez l'API sur le port 8020.",
    en: "Backend unreachable. Start the API on port 8020.",
  },
  runFailed: { fr: "L'analyse a échoué.", en: "The analysis failed." },
  pipelineHalted: { fr: "Pipeline arrêté", en: "Pipeline halted" },

  // -- Terminal (données réelles OpenBB) -------------------------------
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
    fr: "Données réelles via OpenBB (Yahoo Finance, Réserve fédérale), différées de 10 à 20 min selon le marché. Elles n'alimentent pas encore les agents du comité.",
    en: "Real data via OpenBB (Yahoo Finance, Federal Reserve), delayed 10–20 min depending on the market. Not yet fed to the committee agents.",
  },
  termError: {
    fr: "Source de données indisponible pour le moment.",
    en: "Data source unavailable right now.",
  },
} as const;

export type DictKey = keyof typeof dict;

export const tr = (key: DictKey, lang: Lang): string => dict[key][lang];

export default dict;
