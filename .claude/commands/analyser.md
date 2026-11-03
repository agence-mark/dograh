---
description: Analyser les vrais appels d'un agent du fork par le MCP (lecture seule)
argument-hint: <identifiant d'agent> [nombre d'appels, 10 par défaut]
allowed-tools: mcp__dograh__appels_lister, mcp__dograh__appel_lire, mcp__dograh__a_ameliorer_lire, mcp__dograh__qualite_lire
---

Analyse les appels récents d'un agent du fork .mark, sans rien écrire. Arguments : `$ARGUMENTS` (l'agent, puis le nombre d'appels à lire).

1. `qualite_lire` pour le contexte (taux d'impasse et de reprise de l'agent).
2. `appels_lister(workflow_id, limite)` puis `appel_lire(run_id)` pour chaque appel : transcription numérotée, outils, fiche, avis du juge s'il existe.
3. `a_ameliorer_lire(workflow_id)` pour ne pas redire ce qui est déjà signalé.
4. Rends : les motifs qui reviennent (avec les numéros de réplique cités), ce qui marche, et au plus cinq propositions d'amélioration classées par effet attendu. Cite toujours l'appel et la réplique. N'invente rien qui n'est pas dans une transcription.
