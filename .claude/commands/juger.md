---
description: Juger la file « À juger » du fork (vrais appels et tests) avec des sous-agents, sans le contexte du builder
argument-hint: [identifiant d'agent] [nombre d'éléments par lot]
allowed-tools: Agent, mcp__dograh__juge_a_faire, mcp__dograh__juge_lire, mcp__dograh__juge_ecrire
---

Juge ce qui attend dans la file « À juger » du fork .mark. Arguments : `$ARGUMENTS` (un agent pour ne juger que lui, puis la taille d'un lot, 5 par défaut).

1. Appelle `juge_a_faire` (avec `workflow_id` si un agent est donné). Si la file est vide, dis-le en une ligne et arrête-toi.
2. Découpe la file en lots. Pour chaque lot, lance UN sous-agent à la fois, **sans le contexte de cette conversation** (le juge ne doit pas voir le travail du builder) : donne-lui seulement les identifiants du lot et ces consignes.
3. Consignes du sous-agent, pour chaque identifiant :
   - `juge_lire(id)` : transcription numérotée, outils, fiche, critères, consigne du juge ;
   - un verdict par critère : `reussi`, `rate` ou `non_verifiable` ; la réplique citée (son numéro) et une preuve qui est une **citation exacte** de cette réplique ; la raison seule pour `non_verifiable` ;
   - `juge_ecrire(id, verdicts)`. Un verdict refusé revient avec sa raison : le corriger et renvoyer, sans inventer de citation.
4. À la fin, rends un compte rendu court : éléments jugés, réussis, ratés (ils sont déjà rangés dans « À améliorer » par `juge_ecrire`), refusés.

Rappel : sur Claude Code le juge est du même modèle que le builder, ce n'est pas un avis indépendant (la mention est portée par chaque verdict).
