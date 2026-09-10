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

## Comment se lit le rouge

**Constaté le 10/09/2026**, en retirant le patch pour vérifier que ces tests protègent vraiment
quelque chose. **Un patch perdu ne se présente pas toujours comme un échec de test.**

| Ce que la console affiche | Ce que ça veut dire |
|---|---|
| `X failed` | Le code est encore là mais ne fait plus ce qu'on garantissait |
| 🔴 `Interrupted: 1 error during collection` | **Le code a DISPARU.** Le test ne peut plus importer ce qu'il vérifie, donc pytest s'arrête **avant de jouer quoi que ce soit** |

⛔ **Le second cas est le plus dangereux, parce qu'il ressemble à une panne d'environnement.**
Retirer le patch Mistral donne exactement ça :

```
ImportError: cannot import name 'MistralLLMConfiguration' from 'api.services.configuration.registry'
Interrupted: 1 error during collection
```

🔑 **Et l'interruption masque le reste de la suite** : les autres fichiers ne sont même pas joués.
Un seul patch perdu peut donc faire croire que toute la suite est cassée. Pour voir l'état réel :

```bash
python -m pytest tests/mark -q --continue-on-collection-errors
```

**La mesure de référence, au 10/09/2026 :** 47 tests, tous verts avec les patchs.
Sans les patchs de `registry.py`, `check_validity.py` et `service_factory.py` :
**1 erreur de collecte (les 19 de Mistral), 7 échecs (Deepgram), 21 verts.**
