# `tests/mark/` — les tests de non-régression du fork .mark

**Convention .mark. Ce dossier n'existe pas dans le dépôt d'origine.**

> ⛔ **La règle d'entrée du registre des forks : pas une ligne de modification sans son test.**
> Registre : `agence-mark/socle-agent-vocal`, `forks/REGISTRE.md`.

## Pourquoi ces tests existent

Git ne signale un conflit que si l'amont touche **nos lignes**. S'il **déplace ailleurs** le code
que nous modifions, tout fusionne en silence, le service continue de répondre normalement, **et
notre modification ne sert plus à rien sans que personne ne l'apprenne.**

**Aucune relecture de diff n'attrape ça. Le test est le seul mécanisme qui passe au rouge tout seul.**

## Les trois règles

| Règle | Ce qu'elle impose |
|---|---|
| **Un fichier par ligne du registre** | Le nom du fichier dit quelle garantie il protège |
| **Une seule question, oui ou non** | « Ce que ma modification garantissait est-il encore vrai ? » |
| **Il doit avoir été ROUGE** | Un test qui n'a jamais échoué sur le code non patché ne prouve rien |

## Quand ils tournent

À **chaque montée de version du fork** (étape 7 de `dograh/mise-a-jour-du-fork.md` dans le socle),
et avant tout déploiement.

```bash
cd api && python -m pytest tests/mark -q
```

## L'inventaire

| Fichier | La garantie protégée | Question du labo |
|---|---|---|
| `test_pas_dappel_vers_lediteur.py` | Aucune requête ne part vers `services.dograh.com` quand les services managés sont coupés | n° 60 |
| `test_multi_organisation.py` | Une même personne peut détenir plusieurs organisations et basculer de l'une à l'autre | n° 59 |
| `test_deepgram_en_europe_sans_entrainement.py` | L'audio de l'appelant part sur `api.eu.deepgram.com` et refuse le programme d'amélioration des modèles, **sur les trois chemins Deepgram** (STT classique, STT Flux, TTS) | n° 78 |
| `test_mistral_provider.py` | Mistral reste un fournisseur **de plein droit** (raisonnement et voix Voxtral) et non un `openai` détourné : sans sa propre classe, le filtre anti-double-exécution des appels d'outils disparaît et **un SMS partirait deux fois**. Protège aussi l'adresse `api.eu.mistral.ai` par défaut | n° 74 |
