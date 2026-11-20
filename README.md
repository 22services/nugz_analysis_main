# Comité Or — une décision toutes les 15 minutes

Or (GC=F, COMEX). Quatre outils, du contexte réel, une décision par barre de 15 minutes close.
Réponse possible, et fréquente : **pas de trade**.

| Onglet | Contenu |
|--------|---------|
| **Décision 15m** | Le verdict, le ticket (entrée, stop, objectifs, taille GC/MGC), les cinq voix du comité, le raisonnement du CIO, la Red Team, le Risk Manager, le graphique 15m et le **journal** qui note chaque décision |
| **OpenBB** | Terminal façon Bloomberg en données réelles : graphique, surveillance cross-asset, fiche, courbe des Treasuries, actualités |
| **Graphique** | Bougies avec VWAP, profil de volume, structure et patterns surlignés — chaque pattern **mesuré contre le hasard** |

---

## Le comité

Aucun LLM. Tout est calculé en `pandas` / `numpy` ([`backend/app/`](backend/app/)), à partir des
seules barres **closes et diffusées** à l'instant de la décision.

| Voix | Outil | Groupe | Ce qu'elle dit |
|------|-------|--------|----------------|
| Structure | pivots HH/HL/LH/LL, BOS/CHoCH sur 15m · 1H · 4H | Tendance | Dans quel sens va le marché, à quelle échelle |
| VWAP | VWAP de séance (18 h NY) + bandes ±1σ ±2σ | Tendance | Qui contrôle la séance, et si le prix est étiré |
| Profil de volume | POC, VAH, VAL de la veille + POC du jour | Localisation | Équilibre (rotation vers le POC) ou acceptation hors valeur (tendance) |
| Volatilité | ATR 15m (percentile ~60 j) + ATR journalier | Filtre | Régime, carburant restant, unité du stop, taille |
| Cross-asset | Dollar Index, US 10 ans, VIX via OpenBB | Contexte | Vent arrière ou de face pour l'or (pondéré par la corrélation réelle or/dollar) |

Puis :

- **CIO** — score pondéré par **groupes indépendants** (tendance 45 %, localisation 35 %, contexte 20 %).
  Structure et VWAP mesurent souvent la même chose : elles ne comptent que pour une voix.
  Le vote naïf est affiché puis écarté. Disjoncteur si la tendance et la localisation se
  contredisent franchement.
- **Red Team** — « suppose que ce trade perd : pourquoi ? ». Objections notées 1-5 (contre-tendance
  4H, obstacle trop proche, prix étiré, ATR journalier consommé, séance asiatique, contexte
  contraire…) ; elles réduisent la conviction.
- **Risk Manager (veto)** — stop derrière le dernier pivot 15m (0,8 à 2,5 ATR), objectif 1 = premier
  niveau majeur, ratio ≥ 1 obligatoire, données fraîches, marché ouvert. Taille calculée pour
  `RISK_PER_TRADE_USD` (GC 100 $/pt, MGC 10 $/pt).

## Mesurer au lieu de croire

- **Journal** : chaque décision est notée sur les barres suivantes. Entrée à la clôture de la barre
  d'après (délai réaliste), « ne pas courir après » au-delà de 0,3 ATR, stop ou objectif touché en
  premier (les deux dans la même barre = perte), stop temporel 4 h, coûts déduits, **une position
  à la fois** (sinon un même mouvement compterait vingt fois).
- **Rejeu** : au démarrage, le même moteur est rejoué barre par barre sur les 10 derniers jours,
  sans voir le futur. Les statistiques live et rejeu ne sont jamais mélangées.
- **Patterns** (avalement, marteau, étoile filante, FVG, chasse aux stops, BOS, CHoCH, double
  sommet/creux) : taux de réussite comparé au **hasard** sur le même horizon, IC de Wilson,
  correction de Bonferroni pour 14 tests simultanés, découpage in/out-of-sample.
  Étiquettes : *échantillon insuffisant*, *non prouvé*, *plausible*. Jamais « validé » :
  60 jours de données gratuites ne le permettent pas.

> Premier constat honnête (20/11/2026) : sur ~3 900 bougies 15m, **aucun** des 14 patterns ne
> bat le hasard. Le rejeu du comité sur 10 jours donne 39 trades indépendants, espérance
> +0,03 R, IC 95 % [−0,36 ; +0,42] : **aucun avantage prouvé**. C'est précisément ce que le
> journal sert à établir avant de risquer un dollar.

## Limites connues

- **Données Yahoo gratuites, différées ~10 min** : chaque décision est publiée ~12 min après la
  clôture de sa barre. Pour trader en temps réel, il faut un flux payant (Databento, etc.).
- 60 jours d'historique 15m au maximum : trop court pour valider un edge sur plusieurs régimes.
- Aide à la décision uniquement : aucun ordre n'est passé.

---

## Lancer en local

```bash
# API (OpenBB + comité + journal) — port 8020
cd backend
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --port 8020

# Tests (aucun appel réseau)
DISABLE_SCHEDULER=1 .venv/bin/python -m pytest -q

# Front — http://localhost:3000
cd frontend && npm install
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8020 npm run dev
```

Variables utiles (API) : `DECISION_SYMBOL` (GC=F), `RISK_PER_TRADE_USD` (500),
`DATA_DELAY_S` (720), `REPLAY_DAYS` (10), `DATA_DIR` (dossier du journal).

## Déployer sur le VPS

```bash
docker compose -p nugz -f docker-compose.yml -f docker-compose.prod.yml up -d --build --remove-orphans
```

`--remove-orphans` supprime l'ancien conteneur `terminal` de la v1 (fusionné dans `api`).
Le journal vit dans le volume Docker `journal` et survit aux redéploiements.

## API

| Route | Rôle |
|-------|------|
| `GET /api/decision` | Décision sur la dernière barre 15m close (+ prochaine réunion) |
| `POST /api/decision/refresh` | Relance le comité (sans effet si la barre est déjà décidée) |
| `GET /api/decision/history?source=live\|replay` | Journal et statistiques |
| `GET /api/chart?symbol=&interval=&bars=` | Bougies, VWAP, profil, structure, patterns et leur statistique |
| `GET /api/terminal/watchlist · history · news · curve` | Terminal OpenBB |
| `GET /api/health` | État, planificateur, rejeu |
