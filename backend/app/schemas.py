"""
Contrats de donnees du comite d'investissement / Investment committee data contracts.

Regle d'or: un agent LLM n'invente JAMAIS un chiffre. Tous les nombres qui
apparaissent ici sont produits par la couche deterministe (app/features).
L'agent ne fait qu'interpreter et remplir les champs narratifs.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------
# Enumerations
# --------------------------------------------------------------------------
class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"
    NO_TRADE = "NO_TRADE"


class RiskVerdict(str, Enum):
    APPROVED = "APPROVED"
    REDUCE = "REDUCE"
    REJECT = "REJECT"


class EventRisk(str, Enum):
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    HIGH = "HIGH_EVENT_RISK"


class AgentStatus(str, Enum):
    IDLE = "IDLE"          # jamais execute sur ce run
    RUNNING = "RUNNING"    # en cours
    DONE = "DONE"          # a rendu sa copie
    BLOCKED = "BLOCKED"    # halte en amont (donnees perimees)
    SKIPPED = "SKIPPED"    # non pertinent pour ce run
    FAILED = "FAILED"      # erreur technique


class Timeframe(str, Enum):
    M5 = "5m"
    M15 = "15m"
    H1 = "1H"
    H4 = "4H"
    D1 = "1D"


class MarketStructure(str, Enum):
    UPTREND = "UPTREND"            # HH / HL
    DOWNTREND = "DOWNTREND"        # LH / LL
    RANGE = "RANGE"
    TRANSITION = "TRANSITION"      # structure cassee, pas encore reformee


class TrendQuality(str, Enum):
    CLEAN = "CLEAN"
    CHOPPY = "CHOPPY"
    EXHAUSTED = "EXHAUSTED"


class VolRegime(str, Enum):
    COMPRESSED = "COMPRESSED"
    NORMAL = "NORMAL"
    EXPANDING = "EXPANDING"
    EXTREME = "EXTREME"


class MacroRegime(str, Enum):
    RISK_ON = "RISK_ON"
    RISK_OFF = "RISK_OFF"
    REFLATION = "REFLATION"
    DISINFLATION = "DISINFLATION"
    TIGHTENING = "TIGHTENING"
    EASING = "EASING"
    MIXED = "MIXED"


class RunTrigger(str, Enum):
    MANUAL = "MANUAL"              # bouton "Analyser maintenant"
    SETUP_CANDIDATE = "SETUP_CANDIDATE"  # detecte par la couche deterministe
    SCHEDULED = "SCHEDULED"
    EVENT_WINDOW = "EVENT_WINDOW"  # fenetre macro


class RunStage(str, Enum):
    DATA = "DATA"
    ANALYSIS = "ANALYSIS"
    RED_TEAM = "RED_TEAM"
    REBUTTAL = "REBUTTAL"
    RISK = "RISK"
    DECISION = "DECISION"
    COMPLETE = "COMPLETE"
    HALTED = "HALTED"


# --------------------------------------------------------------------------
# Primitives partagees
# --------------------------------------------------------------------------
class Localized(BaseModel):
    """Texte bilingue. L'UI choisit la langue, le contenu reste identique."""
    fr: str
    en: str


class Evidence(BaseModel):
    """
    Une preuve chiffree. `value` vient TOUJOURS de la couche deterministe.
    `reading` est l'interpretation de l'agent.
    """
    label: Localized
    value: str                      # deja formate: "2 412,80", "1,8x", "+0,42%"
    reading: Localized
    weight: int = Field(ge=1, le=5)  # poids accorde par l'agent
    supports: Direction


class DataSource(BaseModel):
    """Tracabilite: source + timestamp + fraicheur, exige par le PDF."""
    name: str
    kind: Literal["price", "macro", "futures", "calendar", "news", "positioning"]
    last_update: datetime
    age_seconds: int
    max_age_seconds: int
    is_stale: bool
    connected: bool = False         # V1: aucun outil n'est branche

    @property
    def health(self) -> str:
        if not self.connected:
            return "MOCK"
        return "STALE" if self.is_stale else "FRESH"


class PriceLevel(BaseModel):
    label: Localized
    price: float
    kind: Literal["support", "resistance", "vwap", "poc", "pivot", "invalidation", "target"]
    distance_pct: float             # distance au spot, signee
    touches: int = 0


class ToolSpec(BaseModel):
    """
    Outil dont l'agent AURA besoin. En V1 `connected=False` partout:
    les agents existent, leur cablage arrive a l'etape suivante.
    """
    name: str
    provider: str                   # apify | databento | fred | cftc | internal ...
    purpose: Localized
    connected: bool = False


# --------------------------------------------------------------------------
# Sortie generique d'un agent
# --------------------------------------------------------------------------
class AgentOutput(BaseModel):
    agent_id: str
    status: AgentStatus = AgentStatus.IDLE
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None

    headline: Localized | None = None      # une phrase, lisible par un debutant
    detail: Localized | None = None        # le paragraphe pour l'expert
    evidence: list[Evidence] = Field(default_factory=list)

    # "conviction interne du modele, PAS une probabilite reelle de gain" (PDF)
    conviction: int | None = Field(default=None, ge=0, le=100)
    direction: Direction | None = None
    horizon: Localized | None = None

    warnings: list[Localized] = Field(default_factory=list)
    payload: dict = Field(default_factory=dict)   # sortie specialisee de l'agent


# --------------------------------------------------------------------------
# Sorties specialisees (payload de chaque agent)
# --------------------------------------------------------------------------
class MarketStatePayload(BaseModel):
    """Agent 1 - la fondation. Il a le droit de tout arreter."""
    instrument: str                       # "GC" + mois de contrat
    contract: str
    spot: float
    change_pct: float
    session: Literal["ASIA", "LONDON", "NY", "CLOSED"]
    sources: list[DataSource]
    all_fresh: bool
    halt: bool = False
    halt_reason: Localized | None = None
    roll_warning: Localized | None = None  # calendrier des rolls


class TimeframeRead(BaseModel):
    timeframe: Timeframe
    structure: MarketStructure
    quality: TrendQuality
    momentum: int = Field(ge=-100, le=100)
    above_vwap: bool
    atr: float
    atr_percentile: int = Field(ge=0, le=100)
    note: Localized


class TechnicalPayload(BaseModel):
    """Agent 2 - sortie normalisee Direction|Conviction|Horizon|Evidence|Levels|Invalidation."""
    reads: list[TimeframeRead]
    alignment: int = Field(ge=0, le=100)      # coherence entre timeframes
    vol_regime: VolRegime
    key_levels: list[PriceLevel]
    invalidation: PriceLevel | None = None
    setup_type: Localized | None = None       # breakout, mean reversion, ...


class CrossAssetRead(BaseModel):
    asset: str                                # libelle FR
    asset_en: str | None = None               # libelle EN, sinon `asset`
    value: str
    change: str
    normal_correlation: float = Field(ge=-1, le=1)
    live_correlation: float = Field(ge=-1, le=1)
    relationship_active: bool                 # la relation historique tient-elle ?
    impact_on_gold: Direction


class MacroPayload(BaseModel):
    """Agent 3 - Macro regime | Gold impact | Strength | Horizon | Contradictions."""
    regime: MacroRegime
    gold_impact: Direction
    strength: int = Field(ge=0, le=100)
    cross_assets: list[CrossAssetRead]
    contradictions: list[Localized]
    fed_expectation: Localized


class FuturesPayload(BaseModel):
    """Agent 4 - ce qui differencie le systeme d'un bot TradingView."""
    volume: float
    volume_vs_avg: float                      # 1.0 = moyenne
    open_interest: int
    oi_change: int
    oi_price_signal: Localized                # OI up + prix up = nouvelle position longue
    basis: float
    curve_state: Literal["CONTANGO", "BACKWARDATION", "FLAT"]
    calendar_spread: float
    liquidity_score: int = Field(ge=0, le=100)
    cot_net_positioning: int | None = None
    cot_as_of: datetime | None = None
    cot_lag_warning: Localized | None = None  # ne pas traiter du retarde comme de l'instantane


class CalendarEvent(BaseModel):
    name: Localized
    scheduled_at: datetime
    minutes_until: int
    importance: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    exposed_variables: list[Localized]   # bilingue : sinon le FR fuit en EN
    consensus: str | None = None
    previous: str | None = None


class EventPayload(BaseModel):
    """Agent 5 - NORMAL / ELEVATED / HIGH EVENT RISK."""
    level: EventRisk
    next_event: CalendarEvent | None = None
    upcoming: list[CalendarEvent]
    reason: Localized
    blackout_active: bool = False             # trop proche d'une publication


class RedTeamHypothesis(BaseModel):
    """'Suppose que ce trade va perdre. Pourquoi ?'"""
    rank: int
    kind: Literal[
        "contradictory_data", "misleading_correlation", "already_priced",
        "wrong_regime", "event_proximity", "fragile_breakout",
        "missing_information", "signal_dependency",
    ]
    claim: Localized
    argument: Localized
    severity: int = Field(ge=1, le=5)
    targets: list[str]                        # agents vises
    rebuttal: Localized | None = None         # reponse de l'analyste
    rebuttal_holds: bool | None = None        # l'objection tient-elle apres reponse ?


class RedTeamPayload(BaseModel):
    hypotheses: list[RedTeamHypothesis]
    correlated_signals: list[Localized]       # momentum+breakout+volume = meme phenomene
    unresolved_count: int


class RiskCheck(BaseModel):
    name: Localized
    passed: bool
    detail: Localized
    is_hard_limit: bool = False               # un echec ici = REJECT automatique


class RiskPayload(BaseModel):
    """Agent 6 - independant, droit de veto absolu."""
    verdict: RiskVerdict
    checks: list[RiskCheck]
    risk_budget_pct: float
    suggested_size: float
    size_unit: str = "contrats"
    max_loss_currency: float
    currency: str = "USD"
    daily_loss_used_pct: float
    invalidation_distance_atr: float
    veto_reason: Localized | None = None


class TicketSection(BaseModel):
    title: Localized
    rows: list[tuple[str, str]] = Field(default_factory=list)


class TradeTicket(BaseModel):
    """Le livrable institutionnel decrit dans le PDF."""
    instrument: str
    contract: str
    timestamp: datetime
    horizon: Literal["Intraday", "Swing", "Intraday / Swing"]

    # MARKET REGIME
    trend: Localized
    volatility: Localized
    macro_regime: Localized
    event_risk: Localized

    # INVESTMENT THESIS
    direction: Direction
    conviction: int = Field(ge=0, le=100)
    expected_horizon: Localized
    thesis: Localized

    # Blocs d'analyse
    technical: TicketSection
    macro: TicketSection
    futures: TicketSection
    catalysts: TicketSection

    bull_case: list[Localized]
    bear_case: list[Localized]
    invalidation: list[Localized]

    # TRADE STRUCTURE
    entry_zone: Localized
    stop_logic: Localized
    target_logic: Localized
    time_stop: Localized

    # RISK
    risk_budget: Localized
    liquidity: Localized
    event_exposure: Localized
    risk_verdict: RiskVerdict

    final_decision: Direction
    decision_rationale: Localized
    monitoring: list[Localized]


class CIOPayload(BaseModel):
    """Agent 8 - le seul autorise a assembler la proposition finale."""
    ticket: TradeTicket | None = None
    contradictions_found: list[Localized]
    independent_signals: int                  # apres deduplication des signaux correles
    naive_vote: str                           # "4 bullish / 1 bearish" - montre puis rejete
    why_not_naive: Localized


# --------------------------------------------------------------------------
# Run + journal
# --------------------------------------------------------------------------
class AgentCard(BaseModel):
    """Fiche d'identite d'un agent, affichee dans le dashboard."""
    id: str
    order: int
    name: Localized
    role: Localized
    mandate: Localized                 # ce qu'il a le droit de faire
    plain: Localized                   # explication pour un non-trader
    can_veto: bool = False
    tools: list[ToolSpec] = Field(default_factory=list)
    model_hint: str                    # modele LLM prevu pour ce role
    stage: RunStage


class RunSummary(BaseModel):
    run_id: str
    started_at: datetime
    finished_at: datetime | None = None
    trigger: RunTrigger
    stage: RunStage
    decision: Direction | None = None
    conviction: int | None = None
    risk_verdict: RiskVerdict | None = None
    event_risk: EventRisk | None = None
    spot_at_decision: float | None = None
    halted: bool = False


class Run(RunSummary):
    outputs: dict[str, AgentOutput] = Field(default_factory=dict)
    ticket: TradeTicket | None = None
    # Point-in-time correctness: on fige ce qui etait disponible a T.
    input_snapshot: dict = Field(default_factory=dict)


class JournalEntry(BaseModel):
    """
    Le vrai livrable de la V1 selon le PDF: le journal shadow/paper.
    C'est lui qui permettra de dire si le systeme apporte quelque chose.
    """
    run_id: str
    timestamp: datetime
    decision: Direction
    conviction: int
    risk_verdict: RiskVerdict
    spot: float
    theoretical_entry: float | None = None
    theoretical_stop: float | None = None
    theoretical_target: float | None = None
    outcome: Literal["OPEN", "WIN", "LOSS", "SCRATCH", "NO_TRADE"] = "OPEN"
    pnl_points: float | None = None
    mfe: float | None = None           # maximum favorable excursion
    mae: float | None = None           # maximum adverse excursion
    agent_contributions: dict[str, int] = Field(default_factory=dict)
    notes: Localized | None = None


# --------------------------------------------------------------------------
# Feature vector : le contrat entre la couche Python et les LLM
#
# Issu du debat avec Hermes. Trois regles:
#   1. On envoie des valeurs DERIVEES, pas des chiffres bruts. Le LLM ne doit
#      jamais avoir a re-deriver "est-ce au-dessus de la VWAP ?".
#   2. On encode la SEMANTIQUE, pas juste le nombre. `basis: -3.2` peut etre
#      lu a l'envers; `{value:-3.2, unit:"usd/oz", meaning:"futures_discount"}`
#      ne le peut pas.
#   3. On VERSIONNE le schema. Changer la definition d'un champ entre deux runs
#      contamine le backtest en silence.
# --------------------------------------------------------------------------
FEATURE_SCHEMA_VERSION = "1.0.0"


class SemanticValue(BaseModel):
    """Un nombre qui porte son sens avec lui."""
    value: float
    unit: str                       # "usd/oz", "atr", "pct", "ratio", "contracts"
    meaning: str                    # "futures_discount_to_spot", "above_vwap"
    direction_if_high: Direction | None = None


class ModelTier(str, Enum):
    NONE = "NONE"        # agent deterministe, aucun appel LLM
    CHEAP = "CHEAP"      # lecture contrainte par schema
    STRONG = "STRONG"    # raisonnement, contradiction, decision


class TriggerPriority(int, Enum):
    LOW = 1              # test de VWAP
    MEDIUM = 2           # cassure de niveau mineur
    HIGH = 3             # expansion ATR, cassure structurelle
    CRITICAL = 4         # fenetre macro


class TriggerCandidate(BaseModel):
    """
    Produit par la couche deterministe. C'est elle qui decide quand reveiller
    les LLM. Hermes: "cette couche de détection EST ton alpha."
    """
    kind: Literal[
        "level_break", "atr_expansion", "vwap_test",
        "structure_shift", "macro_window", "manual",
    ]
    priority: TriggerPriority
    dedup_key: str                  # symbole + timeframe + kind + index de barre
    timeframe: Timeframe
    detected_at: datetime
    reason: Localized
    cooldown_until: datetime | None = None


class ContractContext(BaseModel):
    """
    Le piege signale par Hermes: GC roule tous les mois. Melanger une serie
    continue et le front-month casse la detection de structure en silence.
    """
    symbol: str                     # "GCZ5"
    is_front_month: bool
    expiry: datetime
    roll_date: datetime
    days_to_roll: int
    series_type: Literal["front_month", "continuous_adjusted"]
    roll_warning: Localized | None = None


class SessionContext(BaseModel):
    """GC suit les horaires CME, XAU/USD est 24/5."""
    session: Literal["ASIA", "LONDON", "NY", "CLOSED"]
    is_liquid_hours: bool
    minutes_since_open: int
    minutes_to_close: int


class FeatureVector(BaseModel):
    """Ce que chaque agent LLM recoit reellement. Rien d'autre."""
    schema_version: str = FEATURE_SCHEMA_VERSION
    as_of: datetime
    contract: ContractContext
    session: SessionContext

    spot: float
    # Distances exprimees en ATR: comparables d'un regime de vol a l'autre.
    vwap_distance_atr: SemanticValue
    nearest_resistance_atr: SemanticValue
    nearest_support_atr: SemanticValue
    atr_percentile: SemanticValue

    structure_by_tf: dict[str, str]           # {"5m": "UPTREND", ...}
    momentum_by_tf: dict[str, int]
    alignment: SemanticValue

    extras: dict[str, SemanticValue] = Field(default_factory=dict)

    # Resume d'etat transmis avec le trigger, pour que l'agent reveille
    # n'ait pas a relire tout l'historique.
    state_summary: Localized | None = None


class CalibrationBucket(BaseModel):
    """
    Ma contribution au debat: sans mesure, la conviction est decorative.
    On stocke le bucket des le jour 1 pour tracer conviction vs reussite reelle.
    """
    lower: int
    upper: int
    n_trades: int = 0
    n_wins: int = 0

    @property
    def observed_rate(self) -> float | None:
        return round(self.n_wins / self.n_trades, 3) if self.n_trades else None
