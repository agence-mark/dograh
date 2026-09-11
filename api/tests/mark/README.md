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
| `test_reglages_mistral_exposes.py` | Les six réglages d'échantillonnage de Mistral sont **déclarés** (donc affichés à l'écran, qui se fabrique depuis le schéma) et **transmis** jusqu'à la requête, graine comprise. Protège aussi l'inverse : sans réglage renseigné, la requête reste celle d'avant, pour Mistral comme pour les treize autres fournisseurs | n° 96, 104, 107, 108 |
| `test_graine_random_seed.py` | La graine **arrive jusqu'à Mistral au lieu de rendre l'agent muet** : elle voyage dans `extra_body`, que la bibliothèque cliente transmet, et non à la racine des paramètres où cette bibliothèque **refuse le mot-clé et rejette la requête avant l'envoi** — erreur non fatale, donc agent debout et silencieux. Protège aussi **la graine à 0** (ignorée en silence alors que l'écran l'accepte), et surtout **la configuration SANS graine, celle de tous les clients** : rien ne doit s'ajouter à sa requête, sentinelle compris | n° 112 |
| `test_configuration_estampillee_sur_lappel.py` | Chaque exécution enregistre les réglages d'échantillonnage **avec lesquels elle a été jouée**, sur les **deux** chemins : l'appel téléphonique et le banc au clavier. Sans ça, deux essais joués à deux températures sont indiscernables après coup | n° 104 |
| `test_surcharge_par_service_sur_client_v2.py` | Un agent remplace **un seul service** et hérite du reste de son client, **y compris quand le client change de modèle**. Protège aussi le marqueur sans lequel l'enregistrement de la configuration du client convertit la surcharge en copie figée, en silence | n° 59 |
| `test_reglages_transcription_exposes.py` | Les **19 réglages de la transcription** — 14 pour le connecteur Deepgram classique, 5 pour Flux — sont **déclarés** (donc affichés, l'écran se fabriquant depuis le schéma), **bornés sur la documentation de Deepgram**, et **transmis** jusqu'aux paramètres de connexion. Protège surtout l'inverse : **sans aucun réglage rempli, la requête est exactement celle d'avant le chantier**, comparée à un littéral mesuré. Protège aussi que `keyterm` **n'est pas** déclaré (il appartient au Dictionnaire de l'agent) et que la copie du schéma côté écran ne dérive pas | n° 115 |
| `test_surcharge_par_service_survit_a_lenregistrement.py` | La route qui **enregistre** une surcharge par service ne la convertit pas en copie figée au passage. ⛔ **Le fichier voisin ne protégeait pas ça** : il s'arrêtait à la fonction, et la route porte sa propre conversion — neuf tests verts sur une fonctionnalité qui ne survivait pas à son propre enregistrement | n° 59 |

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

**La mesure de référence, au 11/09/2026 au SOIR : 234 tests, tous verts avec les patchs.**
⚠️ **Elle change à chaque chantier** : 47 avant l'exposition des réglages Mistral, 105 le 10/09 au
soir, **113 après la réparation de la graine**, 234 après l'exposition des réglages de la
transcription. C'est ce nombre-là que la procédure de montée de version prend comme base —
**une mesure de référence périmée fait passer une perte de patch pour un changement de compte.**

**Le rouge de référence, mesuré le matin sur les 47 :** sans les patchs de `registry.py`,
`check_validity.py` et `service_factory.py` : **1 erreur de collecte (les 19 de Mistral),
7 échecs (Deepgram), 21 verts.**
