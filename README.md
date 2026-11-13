# TrackMania RL — pilote spécialisé, apprentissage réutilisable

> Archive du 13 novembre 2026 : périmètre, artefacts et restauration dans [ARCHIVE](docs/ARCHIVE.md).

## État actuel

**J5 (2 octobre 2026)** : pilote appris qui termine A01 régulièrement, avec 39/40 arrivées pour la politique figée `a01-v4-obs2b/00100000` à ×1 ; critère D33 fixé avant la campagne et satisfait deux fois. Voir le [rapport J5](docs/reports/J5-fiabilite.md).

Le dépôt contient le pont TMInterface, les observations, l’environnement et une première chaîne SAC CPU avec checkpoints réels. **J4 reste partiel** : bras SAC hybride et outillage livrés et exercés ; comparaison contrôlée D25 et chrono officiel D28 non validés. Le run `20260930-104918-a01_sac_hybrid4_v2_ent05` a produit des arrivées apprises ; son checkpoint 953949 a réalisé 29,50 s au mieux sur 5 évaluations à ×1, dont 3 arrivées et 2 erreurs de protocole près de l’arrivée. Ces essais ne prouvent ni une fiabilité suffisante ni un chrono officiel. Un correctif ajusté après cette évaluation passe les tests hors jeu ; il doit encore être confirmé dans TMNF. Voir le [rapport J4](docs/reports/J4-apprentissage.md) et le [guide utilisateur](docs/GUIDE-J4.md).

Le projet vise un pilote neuronal qui observe la télémétrie et décide pendant la course. Il ne génère pas une séquence de commandes à rejouer. Aucun LLM n'est prévu dans la boucle de conduite.

Correction du critique (1er octobre 2026, J4-15) : warmup de reprise corrigé, observations v2 avec contexte d'abandon, migration explicite depuis le checkpoint à 660 037 transitions et diagnostics fixes. **130 tests hors jeu passent**, migration vérifiée sur le vrai checkpoint. La stabilité en jeu reste à valider. Configuration et commandes : [guide J4](docs/GUIDE-J4.md#v4--correction-du-critique-et-observations-v2-j4-15), [rapport](docs/reports/J4-critic-corrections-20261001.md).

## Objectif

- Entraîner d'abord un spécialiste d'**A01**, dans **TrackMania Nations Forever**, sous **Linux**, avec **TMInterface**.
- Obtenir d'abord un chrono local comparable au **top 1 000 mondial**, puis au **top 50**, puis poursuivre la recherche.
- Réutiliser la procédure sur d'autres maps en entraînant un spécialiste par map ; ne pas exiger un modèle généraliste.
- Ne pas imposer de comportement humain. Les mouvements brusques, la glisse et les contacts ne sont pas interdits par principe.
- Rester en local. Un chrono comparable ne constitue pas une inscription à un classement officiel.

Ces objectifs de performance sont des ambitions de recherche, pas des garanties ni des résultats acquis.

## Lire dans cet ordre

1. [ARCHITECTURE](docs/ARCHITECTURE.md) : périmètre, composants et trajectoire technique.
2. [OBSERVATIONS](docs/OBSERVATIONS.md) : données du modèle, référence de parcours et contrats.
3. [REWARDS](docs/REWARDS.md) : objectifs de récompense et tests contre les comportements indésirables.
4. [DECISIONS](docs/DECISIONS.md) : choix validés, propositions et questions ouvertes.
5. [ROADMAP](docs/ROADMAP.md) : jalons et preuves de validation.
6. [GOAL](GOAL.md) : checklist à compléter et objectif borné à confier à Hermes.
7. [EXPERIMENTS](docs/EXPERIMENTS.md) : protocole d'évaluation et fiche d'expérience.
8. [AGENTS](AGENTS.md) et [skill TrackMania RL](skills/trackmania-rl/SKILL.md) : règles de travail des agents.

## Ce qui existe réellement

- `TelemetrieVoiture.as` : plugin de démonstration. Dans `Render()`, il envoie `WAIT` ou `DATA speed gear rpm sliding` sur une socket locale, avec un intervalle minimal de 200 ms entre envois.
- `telemetrie.py` : client d'affichage sur `127.0.0.1:8478`, avec reconnexion.
- `main.py` : programme d'accueil, pas un point d'entrée RL.
- `pyproject.toml` et `uv.lock` : projet uv, Python `>=3.13`, dépendances SAC CPU, Gymnasium et TensorBoard.
- `src/trackmania_rl/` et `scripts/tm.py` : environnement, apprentissage, reprise, évaluation et tableau de bord J4. Interface web locale : `./scripts/atelier` depuis la racine, puis `http://127.0.0.1:8765` (voir le guide J4).
- `TMLoader-1.0.1-win32.exe` : fichier préexistant ; sa présence ne prouve ni son usage ni la version de TMInterface exécutée.

La lecture des sources ne valide pas une connexion au jeu. Le protocole du démonstrateur ne transporte ni les observations complètes demandées, ni une synchronisation action/observation, ni les commandes de conduite. Le pont RL distinct est décrit dans les rapports J1 à J4.

Commande existante, uniquement pour la démonstration avec le jeu et le plugin déjà prêts :

```bash
uv run python telemetrie.py
```

Commandes J4 disponibles : `uv run python scripts/tm.py train --config configs/training/a01_sac_threshold_v1.json`, ou `a01_sac_hybrid4_v1.json`, puis `status`, `stop`, `resume`, `eval`, `compare` et `dashboard` selon le [guide](docs/GUIDE-J4.md). `resume --until-stopped` poursuit un run sans plafond de transitions jusqu’à l’arrêt demandé par l’utilisateur ; les checkpoints restent périodiques. Les entraînements longs sont lancés par l’utilisateur. Commandes J2 réellement exécutées (enregistrement de référence, construction, analyse des conventions) : voir [le rapport J2](docs/reports/J2-observations.md). Environnement J3 (`src/trackmania_rl/env.py`, `reward.py`) et épisodes réels avec contrôleurs de test scriptés non appris : voir [le rapport J3](docs/reports/J3-environnement.md). Tests hors jeu : `PYTHONPATH=src:tests uv run python -m unittest discover -s tests`.

## Organisation proposée

Commencer par **un agent coordinateur et un `/goal` borné par jalon**. Utiliser des assistants ponctuels pour des tâches réellement indépendantes. Ne pas créer immédiatement une flotte de bots permanents.

Les entraînements sont lancés et suivis par l'utilisateur (D37). Les goals livrent les commandes, le tableau de bord et les données de diagnostic, puis expliquent comment s'en servir.

**J5 validé le 2 octobre 2026** sur demande de l'utilisateur ([GOAL.md](GOAL.md), [rapport J5](docs/reports/J5-fiabilite.md)). Le checkpoint figé `a01-v4-obs2b/00100000` termine 39 courses sur 40 à ×1 depuis le départ normal, dans deux campagnes de 20 tentatives : meilleur 26,97 s, médiane 27,06 s. Ce ne sont pas des records officiels vérifiés. J4 reste partiel (D25, D22/D23) ; aucun objectif de classement n'est validé.

## Maintenance

Les décisions durables vont dans `docs/DECISIONS.md`, les résultats dans des fiches d'expérience et les critères accomplis dans `docs/ROADMAP.md`, avec leurs preuves. Le skill conserve la procédure de travail, pas le journal des essais. Les données lourdes et modèles ne seront pas ajoutés à Git par défaut.
