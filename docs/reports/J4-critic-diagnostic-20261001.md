# Diagnostic du critique SAC — 1er octobre 2026

Suite : les corrections ont ensuite été approuvées et implémentées ; voir le [rapport J4-15](J4-critic-corrections-20261001.md). Ce document conserve le diagnostic avant correction.

## Conclusion et niveau de preuve

Le run `20261001-132246-a01_sac_hybrid4_v3c_h095` hérite d'un critique qui
surestime déjà fortement certains échecs rares. L'erreur s'aggrave pendant le
run. Changer le learning rate et agrandir le buffer ne répare pas ces valeurs.
La reprise réintroduit aussi 2 000 actions aléatoires : c'est un défaut distinct,
confirmé par le code et les actions enregistrées.

Le mécanisme observé est une mauvaise estimation des échecs entretenue par
l'apprentissage avec des cibles calculées à partir du critique cible. Un essai
hors jeu confirme que la distribution de replay influence fortement cette
erreur. **Il ne démontre pas une cause unique de l'effondrement en course ni
une correction durable.** Le rôle de l'abandon avec compteur caché reste une
hypothèse structurelle, pas une causalité isolée expérimentalement.

Aucun code de production, checkpoint, configuration d'entraînement ou plugin
n'a été modifié pendant ce diagnostic. Aucun accès au jeu. Les essais ont
entraîné uniquement des copies temporaires en mémoire, sans sauvegarder leurs
poids. Le run utilisateur est passé à `stopped/stop_file` à 100 871 transitions ;
le diagnostic n'a pas demandé cet arrêt.

## Run, filiation et dégradation

Les fichiers `incidents.jsonl` donnent la filiation exacte :

1. v3 part de v2 `02254519` (2 254 519 transitions locales v2).
2. v3b part de v3 `00660037` (660 037 transitions locales v3).
3. v3c part de v3b `00050195` (50 195 transitions locales v3b).

Les compteurs des nouveaux runs repartent de zéro. Le modèle dit « 600K »
n'est donc pas un modèle ayant seulement 600K transitions cumulées. La reprise
charge acteur, critiques, critiques cibles, optimiseurs, températures et buffer.

Dans v3c, le learning rate effectivement enregistré est `1e-4`, la capacité du
buffer est 1 000 000, avec **100 000 transitions seulement au départ**. Le
checkpoint final contient 200 871 transitions. Le ratio réalisé est 0,49974
mise à jour par transition éligible. Le statut final indique zéro transition
invalide, zéro reset échoué, 73 arrivées sur 179 épisodes. Les problèmes de
protocole documentés auparavant ne sont pas observés dans ce run.

| Transitions locales v3c | Arrivées / épisodes terminés |
| --- | --- |
| 2K–10K | 8 / 13 |
| 10K–20K | 14 / 17 |
| 20K–40K | 33 / 35 |
| 40K–60K | 16 / 38 |
| 60K–80K | 0 / 41 |
| 80K–fin | 2 / 33 |

Ce sont des courses stochastiques d'entraînement, pas une évaluation D28.

## Preuve sur les valeurs du critique

Recalcul hors jeu de la cible SAC utilisée dans `hybrid_sac.py`, sur toutes les
transitions des buffers sauvegardés : récompense, masque terminal, gamma,
critique cible, politique et températures du checkpoint. Les valeurs Q
ci-dessous sont les moyennes des deux critiques. Pour une transition terminale,
la cible égale exactement la récompense ; elle ne dépend pas du tirage de
l'action suivante.

Un même abandon se retrouve dans plusieurs checkpoints. Il provient de v3,
épisode 1089, transition locale 633 927, à 42,10 s et 26,06 % du parcours.
La voiture est presque immobile, retournée : composante verticale de son axe
haut −0,979, aucun contact roue. Récompense terminale **−0,0498872**.

| Checkpoint | Q prédit pour cette même transition | Cible |
| --- | ---: | ---: |
| v3 / `00660037` | 21,25 | −0,0498872 |
| v3 / `00710153` | 136,80 | −0,0498872 |
| v3b / `00050195`, source de v3c | 94,18 | −0,0498872 |
| v3c / `best-027480ms-00031201` | 183,76 | −0,0498872 |
| v3c / `00100871` | 245,67 | −0,0498872 |

Le record 27,48 s ne garantit donc pas un critique sain. Sur le buffer source
v3b, 13 abandons terminaux parmi 100 000 transitions représentent **51,1 %**
de l'erreur quadratique totale. Une seule transition représente environ 42 %.
La MSE globale recalculée est 0,2114 ; une perte faible sur un minibatch ne
détecte pas nécessairement ces cas. Avec un batch uniforme de 256, environ
96,7 % des batchs ne contiennent aucun des 13 abandons terminaux.

Au checkpoint final v3c, la MSE globale recalculée atteint 1,4139. La
dégradation touche aussi les transitions ordinaires et les arrivées : il ne
s'agit plus seulement d'un pic isolé de la courbe.

## Essai causal borné, hors jeu

Checkpoint source v3b `00050195`, buffer fixe de 100 000 transitions, learning
rate `1e-4`, batch 256, seed NumPy/PyTorch 123, un thread CPU, 1 000 mises à jour
par bras. Aucun nouvel échantillon du jeu. Aucune dépendance ajoutée.

| Variante | Q initial du cas précédent | Q après 1 000 mises à jour |
| --- | ---: | ---: |
| Replay uniforme actuel | 94,18 | 100,57 |
| Replay uniforme, acteur et températures figés | 94,18 | 100,56 |
| 8 abandons terminaux par batch de 256, reste uniforme | 94,18 | 7,21 |

Le gel de l'acteur ne suffit pas dans cet essai. Mieux présenter les échecs
réduit nettement leur surestimation. **Le troisième bras est une sonde de
diagnostic biaisée, sans pondération d'importance ; ce n'est pas une version
validée de Prioritized Experience Replay, ni une configuration à déployer telle
quelle.** Les métriques de loss des batchs de ces bras ne sont pas directement
comparables. Les scripts et leurs résultats complets sont conservés.

Une seconde exécution, avec une mesure uniforme sur tout le buffer avant et
après, montre la limite de cette sonde : la MSE globale passe de 0,2115 à
0,6365 avec 8 abandons forcés par batch, contre 0,2221 pour le replay uniforme.
L'erreur moyenne sur les abandons chute de 831,0 à 7,63, mais celle des
transitions ordinaires monte de 0,1028 à 0,6350. **Le rééchantillonnage brut
déplace donc aussi l'erreur ; il ne constitue pas une solution validée.**

Un troisième essai isole le critique (acteur et températures fixes) et compare
un replay uniforme à une priorisation TD avec pondération d'importance complète.
Priorités `(sqrt(MSE) + 0,001)^0,6`, mélange 20 % uniforme / 80 % priorisé,
priorités recalculées tous les 250 updates, poids `1 / (N * P(i))`, seed 123,
1 000 updates par bras. Q du cas témoin finit à 98,40 en uniforme et 98,08 en
priorisé ; MSE globale 0,2185 contre 0,2153. **Cette variante ne répare pas
la surestimation dans cet essai court.** Elle ne doit pas être présentée comme
la solution démontrée. Cela motive de traiter aussi la représentation de l'état
et les cibles, plutôt que de changer seulement l'échantillonnage.

## Défaut de reprise confirmé

`Trainer._init_from` remet `num_timesteps` à zéro tout en conservant
`learning_starts=2000` du checkpoint. `HybridSAC._sample_action` produit alors
des actions uniformément aléatoires et l'ordonnanceur attend 2 000 transitions
avant de réapprendre, malgré le buffer déjà rempli.

Sur les 2 000 premières transitions de v3c : coast 24,2 %, gaz 25,75 %, frein
24,7 %, gaz+frein 25,35 %, amplitude moyenne de direction 0,5013. Entre 2 000
et 4 000 : gaz 78,5 %. Ce changement confirme l'activation tardive du pilote.
Ce défaut ne suffit pas à expliquer l'instabilité antérieure dans v3.

Modifier uniquement `sac.learning_starts` dans une nouvelle configuration ne
suffit actuellement pas : `_init_from` ne surcharge que `learning_rate` et
`buffer_size` lors du chargement. Le correctif doit porter sur ce chemin.

## Solution recommandée, à implémenter et valider

1. **Corriger la reprise.** Lorsque le checkpoint a déjà appris et que le replay
   contient un batch, utiliser la politique dès la première action et supprimer
   le nouveau warmup. Conserver le warmup pour un modèle réellement neuf ou un
   checkpoint encore insuffisamment entraîné. Tester actions, calendrier des
   gradients et reprise d'un checkpoint écrit après cette correction.
2. **Rendre cohérentes les cibles d'abandon et l'état observé.** La piste
   structurelle prioritaire est d'exposer l'état de la règle des 5 secondes
   si l'abandon reste une terminaison. Cette modification est détaillée plus
   bas et exige l'accord utilisateur pour D31. Elle doit être évaluée dans une
   expérience distincte ; les essais actuels n'ont pas établi qu'elle suffira
   à supprimer l'effondrement. La priorisation du replay peut rester une
   ablation ultérieure, mais les deux variantes testées ici ne fournissent pas
   une solution globale démontrée. Ne pas déployer la sonde 8/256 telle quelle.
3. **Partir d'un checkpoint antérieur et audité dans un nouveau run**, conserver
   tous les originaux. Ne pas considérer `v3b/00050195` comme sain sur la seule
   perte médiane. `v3/00660037` est moins dégradé sur les cas audités, mais pas
   exempt d'erreur. Garder horizon 0,95/s, LR et capacité fixes pendant la
   comparaison ; ne pas réinitialiser aveuglément les critiques sous un acteur
   déjà entraîné.
4. **Ajouter les mesures manquantes.** MSE sur un échantillon uniforme fixe,
   erreurs séparées arrivées/abandons/continuations, quantiles élevés de l'erreur
   TD et Q sur les échecs conservés. Suivre aussi les arrivées par fenêtre. Le
   seuil universel « loss > 0,2 » ne suffit pas à décider si un modèle est sain.
   Faire ensuite une comparaison en jeu pilotée par l'utilisateur, puis une
   évaluation D28 : le test sur replay seul ne prouve pas la stabilité.

Une faiblesse structurelle reste à traiter séparément : `env.py` termine après
5 secondes sans nouveau maximum de progression, alors que `observation.py`
n'inclut ni ce délai ni le maximum historique. Cela rend la règle terminale
partiellement observable. Si l'abandon doit rester terminal, une proposition
serait d'exposer le délai restant et l'écart au maximum pertinent. Cela change
le schéma D31 et exige l'accord utilisateur. Transformer silencieusement tous
les abandons en troncatures changerait aussi le problème appris ; ce n'est pas
un correctif automatique. Aucun de ces changements n'a été appliqué.

## Reproduction et artefacts

Dossier : `runs/diagnostics/20261001-critic/`.

- `td_audit.json` : huit audits de checkpoints, contributions à la loss et
  transitions responsables ; `inspect_td.py` les reproduit.
- `failure_detail.txt`, `inspect_failures.py` : état physique, valeurs autour
  de l'abandon et commandes des 4 000 premières transitions de v3c.
- `offline_ablation.json`, `offline_ablation.py` : essai des trois bras.
- `offline_ablation_uniform_audit.json` et script associé : comparaison
  complémentaire avec mesure uniforme sur le buffer complet.
- `prioritized_probe.json` et script associé : résultat négatif de la
  priorisation avec pondération complète, critique seul.
- `run_summary.json` : comptages des épisodes par fenêtre.
- `manifest.json` : versions, seeds et SHA-256 des modèles, buffers et sources.

Exemple de reproduction, sans connexion au jeu :

```bash
PYTHONPATH=src UV_CACHE_DIR=/tmp/trackmania-uv-cache uv run --offline python runs/diagnostics/20261001-critic/inspect_td.py
PYTHONPATH=src UV_CACHE_DIR=/tmp/trackmania-uv-cache uv run --offline python runs/diagnostics/20261001-critic/offline_ablation.py
```

Références primaires : les [cibles SAC](https://spinningup.openai.com/en/latest/algorithms/sac.html)
expliquent le rôle du bootstrap ; [Prioritized Experience Replay](https://arxiv.org/html/1511.05952v4)
présente la priorisation par erreur TD et la correction du biais ;
[Gymnasium](https://gymnasium.farama.org/tutorials/gymnasium_basics/handling_time_limits/)
distingue terminaison et troncature et rappelle l'importance d'observer le temps
pour une tâche à horizon terminal. L'application au compteur de non-progression
est une analyse du code local, pas une conclusion spécifique de ces sources.
