# Comité Or — dashboard de décision de trading

Huit agents d'analyse, une décision. Or (GC futures / XAU-USD), du 5 minutes au 4 heures.

> **Version 1.** Les huit agents existent, le pipeline tourne de bout en bout, l'interface
> est complète. **Aucun outil n'est branché** : les données sont simulées et aucun appel LLM
> n'est encore effectué. C'est volontaire — on valide la structure de décision avant de payer
> des données de marché.

---

## Ce que fait le système

Il répond à une seule question : **faut-il prendre une position sur l'or maintenant ?**
Réponse possible, et fréquente : **non**.

`NO TRADE` est une sortie de premier rang, pas un échec. Le système n'est jamais obligé de
produire un long ou un short.

---

## Les huit agents

| # | Agent | Rôle | Moteur | Veto |
|---|-------|------|--------|------|
| 1 | Données & État du marché | La fondation | **Python déterministe** | ✅ |
| 2 | Technique & Structure | Le trader technique | LLM économique | |
| 3 | Macro & Cross-Asset | Le cerveau macro de l'or | LLM raisonnement | |
| 4 | Futures & Positionnement | Le spécialiste du GC | LLM économique | |
| 5 | Événements & Catalyseurs | « Qu'est-ce qui peut faire exploser mon trade ? » | LLM raisonnement | |
| 6 | Red Team | L'avocat du diable | LLM raisonnement | |
| 7 | Risk Manager | Droit de veto | **Python** + veto LLM | ✅ |
| 8 | CIO / Décision | La décision finale | LLM raisonnement | |

### Pipeline

```
Données
   │  (halte si une source est périmée)
   ▼
┌─────────────────────────────────────────────┐
│  Technique │ Macro │ Futures │ Événements   │  ← en parallèle
└─────────────────────────────────────────────┘
   ▼
Red Team  ──►  un seul tour de réponse aux objections
   ▼
Risk Manager  (veto)
   ▼
CIO  ──►  Trade Ticket  ──►  journal shadow
```

---

## Décisions d'architecture

Ces choix ont été arbitrés lors d'un débat avec **Hermès**, l'agent qui tourne sur le VPS.
Ils ne sont pas cosmétiques : chacun corrige une façon connue de se tromper.

### 1. Aucun agent LLM ne calcule quoi que ce soit

Toute la trigonométrie du marché — ATR, VWAP, structure HH/HL/LH/LL, open interest, base,
spreads — est calculée en `pandas`/`numpy` dans [`app/features/`](backend/app/features/).
Les agents reçoivent un **feature vector** déjà chiffré et se contentent de l'interpréter.

Un LLM à qui l'on demande de calculer un ATR hallucine. Ce n'est pas une opinion, c'est
une propriété du modèle.

### 2. Le feature vector encode la sémantique, pas juste les nombres

```jsonc
// Non :
{ "basis": -3.2 }                    // le LLM peut le lire à l'envers

// Oui :
{ "basis": { "value": -3.2, "unit": "usd/oz",
             "meaning": "futures_discount_to_spot" } }
```

Les distances sont exprimées **en unités d'ATR**, pas en dollars, pour rester comparables
d'un régime de volatilité à l'autre. Et le schéma est **versionné** (`feature_schema_version`) :
changer la définition d'un champ entre deux runs contaminerait le backtest en silence.

### 3. Event-driven, pas de polling

Interroger les agents toutes les 5 minutes coûterait ~2 300 appels LLM par jour — et
surtout, le marché ne propose rien 80 % du temps. La couche Python tourne en continu
(gratuitement) et ne réveille le pipeline que sur un **candidat de setup déterministe** :
cassure de niveau testé, expansion d'ATR, test de VWAP, bascule de structure, fenêtre macro.

Chaque déclencheur porte une **clé de déduplication** et un **cooldown** : un prix collé à
un niveau pendant trente minutes ne doit pas relancer six fois la même analyse.

> C'est cette couche de détection qui constitue l'avantage réel du système, davantage que
> les prompts des analystes.

### 4. Fail-closed

Si un analyste échoue ou dépasse son délai, la sortie est **NO TRADE**. Jamais un vote
partiel qui passe quand même. En trading, l'ambiguïté n'est pas un signal faible, c'est
une absence de signal.

### 5. Le CIO n'a pas le droit de lisser un désaccord

Un vote 2-2 entre analystes déclenche un **circuit breaker déterministe** → NO TRADE.
Le comptage naïf (« 4 haussiers contre 1 baissier = acheter ») est explicitement interdit :
momentum, cassure et volume décrivent souvent le même phénomène. Le CIO affiche le vote
brut, puis explique pourquoi il ne s'en sert pas.

### 6. Le Risk Manager est scindé en deux

Le dimensionnement de position, les limites de drawdown et la distance de stop sont du
**Python déterministe** (`RiskEngine`). Le LLM ne fait que le veto qualitatif.
Un LLM qui décide d'une taille de position est une catastrophe qui attend de se produire.

### 7. Le journal est le vrai livrable

Le dashboard est l'interface ; le **journal** est l'instrument. Il enregistre, pour chaque
décision, les données disponibles à l'instant T avec source, horodatage et fraîcheur
(*point-in-time correctness*), afin de pouvoir dire objectivement, dans quelques mois,
si le comité apporte quelque chose.

**Calibration par agent.** La conviction affichée est « la conviction interne du modèle,
pas une probabilité réelle de gain ». Tant qu'on ne la mesure pas, c'est un nombre
décoratif. Le journal stocke donc le bucket de conviction **par agent** et l'issue réelle.

La ventilation par agent est essentielle : si l'agent technique est bien calibré
(conviction 80 → 78 % de réussite) et l'agent macro mal calibré (80 → 53 %), la moyenne
des deux masque exactement l'information utile — *écouter la technique, ignorer la macro*.
En dessous de 10 trades par bucket, l'interface affiche « échantillon insuffisant » plutôt
qu'un pourcentage rassurant.

---

## Interface

L'interface est organisée en **onglets**, pour que la décision ne soit pas noyée sous
le détail :

| Onglet | Contenu |
|--------|---------|
| **Décision** | Le verdict en grand, la conviction, le bouton d'analyse, et le graphique en chandeliers avec VWAP et niveaux testés |
| **Marché** | Structure par unité de temps, niveaux clés, déclencheurs détectés, calendrier macro |
| **Comité** | Les 8 agents disposés selon le pipeline réel — un dépliant par agent |
| **Ticket** | Le Trade Ticket institutionnel complet (mode Expert uniquement) |
| **Journal** | Statistiques, calibration globale et **fiabilité par agent** |

Deux publics, une seule page :

- **Mode Simple** — la décision en grand, une phrase en français courant, aucun jargon
  non expliqué. Chaque agent a une description « en clair ».
- **Mode Expert** — le détail chiffré, les niveaux, les sources, et le ticket complet.

Bascule **FR / EN** sur tout le contenu, y compris les sorties d'agents (bilingues côté
API). Aucun libellé technique n'est affiché brut : les états du pipeline, les verdicts de
risque et les niveaux de risque événementiel sont traduits.

Le graphique est en **SVG pur**, sans librairie de charting : bougies 5 minutes, VWAP de
séance, niveaux réellement testés avec leur nombre de touches, et volume en bas pour juger
si un mouvement est soutenu.

Choix d'accessibilité tenus partout : corps de texte à 17 px, contrastes élevés, `prefers-reduced-motion`
respecté, focus clavier visible, et **la couleur ne porte jamais seule une information** —
chaque état a aussi un libellé et une forme géométrique.

---

## Lancer en local

**Backend**

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
.venv/Scripts/python -m uvicorn app.main:app --port 8020
```

**Frontend**

```bash
cd frontend
npm install
npm run dev
```

L'interface écoute sur `http://localhost:3000`, l'API sur `http://127.0.0.1:8020`.
L'URL de l'API se règle dans `frontend/.env.local` (`NEXT_PUBLIC_API_BASE`).

---

## Déployer sur le VPS

Le VPS (Ubuntu 24.04, 8 vCPU EPYC Genoa, 15 Go RAM, 437 Go libres, **pas de GPU**) fait déjà
tourner Coolify + Traefik + l'infra 22edges. Le projet se déploie comme une application
Coolify à partir de [`docker-compose.yml`](docker-compose.yml) : Traefik assure déjà le
routage et TLS, aucun port n'est republié sur l'hôte.

```bash
docker compose build
docker compose up -d
```

L'absence de GPU n'est pas un problème : la charge est I/O bound (appels LLM à venir), pas
compute bound.

---

## Points d'entrée de l'API

| Route | Rôle |
|-------|------|
| `GET /api/health` | État et version du schéma |
| `GET /api/agents` | Fiche des 8 agents, mandats, outils prévus |
| `GET /api/market` | État de marché déterministe (aucun LLM) |
| `POST /api/run` | Lance un run complet du comité |
| `GET /api/runs/{id}` | Run complet avec sorties d'agents et ticket |
| `GET /api/journal` | Journal, stats, calibration globale et par agent |
| `GET /api/stream` | Avancement du pipeline en direct (SSE) |

---

## Étape suivante

Ce qui reste à brancher, par ordre de valeur :

1. **Le détecteur de candidats sur données réelles** — c'est là qu'est l'avantage.
2. **Le feed OHLCV.** Databento est conçu pour l'immutabilité des barres, ce qui est la
   condition du point-in-time correctness. Polygon.io ou TwelveData sont les alternatives
   pragmatiques. À éviter en production : Yahoo (révisions silencieuses des barres).
3. **Rolls de contrat et calendrier de session.** GC roule tous les mois ; mélanger une
   série continue et le front-month casse la détection de structure en silence.
4. **Apify** pour le calendrier macro, le COT (CFTC) et les news.
5. **Les appels LLM**, avec le modèle épinglé par version dans chaque run.
6. **TimescaleDB** dans un conteneur dédié — jamais dans le PG15 de Coolify.

Le CIO n'est volontairement **pas** connecté à l'exécution. Le système tourne en shadow
jusqu'à ce que le journal démontre qu'il apporte quelque chose.
