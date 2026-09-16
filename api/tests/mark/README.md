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
| `test_reglages_pipecat_voix.py` | Les réglages de la **voix** partent par un point de collecte UNIQUE vers les **17** branches de fournisseurs, et non branche par branche : une assertion porte sur le texte source, parce que c'est la seule façon d'affirmer « aucune branche ne construit sa propre liste » plutôt que « les quatre que j'ai testées ne le font pas ». Protège le filtre de balisage, le découpage du texte, les remplacements de prononciation (⛔ **littéraux**, pas des expressions régulières), et le fait qu'**un agent sans réglage reçoit exactement la liste d'avant** | n° 116 |
| `test_reglages_pipecat_tour_de_parole.py` | Les **15 réglages du tour de parole** arrivent dans les objets que le pipeline CONSTRUIT (stratégies, détecteur, Smart Turn, agrégateur), et **un agent sans réglage construit les mêmes objets qu'avant, paramètre par paramètre**, comparés à des littéraux mesurés. 🔑 Porte **deux gardes de dérive** : nos constantes contre les défauts de la version de Pipecat embarquée (rouge le jour d'une montée de version qui déplace un défaut), et **les défauts de l'écran contre ceux du schéma Python** (l'écran en porte forcément sa propre copie) | n° 116 |
| `test_filtre_de_bruit_rnnoise.py` | Le filtre de bruit atteint les **huit** transports (le navigateur et les sept téléphonies), et l'import de `pyrnnoise` reste **paresseux** — vérifié sur l'ARBRE SYNTAXIQUE et non par un essai d'import, le paquet étant installé ici : un import au sommet passerait inaperçu et ne tomberait que sur une image construite sans l'extra, où il empêche **l'API de démarrer**, pour tous les clients | n° 77, 116 |
| `test_relance_inactivite.py` | Les consignes de relance et leur nombre sont ceux de l'agent, et **un agent sans réglage envoie les deux mêmes textes anglais, au même moment, et raccroche au même silence**. ⛔ Protège le **zéro** : lu avec `or`, un agent réglé pour raccrocher au premier silence relancerait quand même | n° 116 |
| `test_coupure_du_micro.py` | Les stratégies qui coupent le micro de l'appelant, **dans leur ORDRE** : Pipecat parcourt la liste et la première qui répond « couper » l'emporte, donc une comparaison d'ensembles dirait égales deux listes qui ne se comportent pas pareil. Protège aussi que c'est bien **la règle du workflow** qui est branchée, et non un remplaçant | n° 116 |
| `test_estampille_reglages_pipecat.py` | Chaque appel **vocal** enregistre les 27 réglages Pipecat **avec lesquels il a été joué, valeurs par défaut comprises** — sans quoi un résultat d'A/B est illisible dès qu'un patch déplace un défaut. Protège **dans les deux sens** : aucun réglage exposé n'échappe à l'estampille, et l'estampille n'emporte pas toute la configuration (surcharges, secrets). ⛔ Le banc au clavier n'estampille rien de tout cela | n° 104, 116 |
| `test_transmission_de_la_configuration.py` | 🚨 **Le pipeline DONNE-t-il la configuration de l'agent à chacun de ses points de collecte ?** Mesuré trois fois le 14/09 : retirer `run_configs` à un point d'appel laisse **tous les autres tests verts**, les points de collecte étant testés directement — ils répondent très bien sur une configuration que le pipeline ne leur donne plus, et l'agent tourne alors sur les défauts quoi qu'affiche l'écran. Assertions sur le texte source, avec **ce qu'elles ne couvrent pas écrit dedans** | n° 116 |
| `test_duplication_agent.py` | La copie d'un agent garde son `workflow_configurations` **à l'identique** — marqueur de surcharge par service et réglages Pipecat compris — et c'est une copie **profonde**. 🔑 Une branche d'A/B EST une copie : deux branches qui partagent un dictionnaire bougeraient ensemble, et le banc comparerait un agent avec lui-même sans que rien n'ait l'air anormal. Rien ne gardait ce chemin d'écriture avant le 14/09 | n° 116 |
| `test_conversion_nombres_transcription.py` | Les nombres dictés arrivent au modèle **en chiffres** quand l'interrupteur de l'agent est allumé, et **seulement dans les transcriptions finales françaises** : la phrase du 15/09 sort en « le 07 88 26 14 09 », les phrases ordinaires, les provisoires et l'anglais sortent intacts, une conversion qui échoue rend le texte d'origine. 🔒 **La phrase d'origine n'est jamais modifiée** : la conversion pousse une copie qui garde son identifiant, sinon le fil en direct afficherait tantôt des lettres, tantôt des chiffres. ✅ **Vérifié sur ce que le direct AFFICHE**, avec le vrai observateur du fil en direct branché : une seule phrase finale, en lettres 🔒 **Éteint, la liste des processeurs est identique à avant** ; allumé, l'étape est **juste avant l'agrégateur**, et absente du pipeline temps réel | n° 148 |
| `test_etat_ouverture.py` | Depuis des horaires saisis au format lisible, **l'état du magasin** (`OUVERT`, `PAUSE`, `FERME`, `SUR_RENDEZ_VOUS`) **et la phrase de réouverture** sont exacts : les 17 situations de l'épreuve du 15/09 (pause déjeuner, jours fériés, congés, horaires réduits, changement d'heure), la traduction, les refus avec numéro de ligne, la priorité des exceptions, les jours fériés 2027 à 2030, et **chaque instant d'une semaine a exactement un état, compté et asserté dans les deux sens**. 🔒 **Un agent sans horaires reçoit le contexte d'avant, à l'identique** ; une valeur déjà fournie n'est jamais écrasée ; des horaires invalides arrivés jusqu'à l'appel ne lèvent rien. ⚠️ Ligne `jours fériés` absente = fériés **fermés** (le prototype les laissait ouverts) | n° 151 |
| `test_horaires_ouverture_reglage.py` | La route qui **enregistre** les réglages de l'agent écrit les horaires **tels que saisis**, **refuse en 422** une saisie fautive avec son numéro de ligne (rien n'est écrit), accepte le vide, et publie le champ dans la spec. ⛔ **La grammaire est vérifiée par la ROUTE, pas par le schéma** : le schéma est aussi lu sur toute la configuration au montage de l'appel, et un refus à la lecture tuait l'appel (relecture du 15/09, prouvé rouge) ; le test appelle les deux chemins de montage sur des horaires invalides, et sur des valeurs hors bornes écrites en base (5000 caractères, un nombre, `max_call_duration=0`) : `creer_conversion_nombres` ne relit plus que son interrupteur (contre-relecture, prouvé rouge). 🔑 **Et un agent sans horaires ne journalise AUCUNE erreur** : avant la déclaration du champ, le contexte était juste mais une erreur partait à chaque appel — vert pour une mauvaise raison, prouvé rouge | n° 151 |
| `test_etat_ouverture_branchement.py` | 🚨 **L'injection est-elle APPELÉE**, et au bon moment ? Voix : motif sur le source, **dans l'ordre** lecture de la configuration < injection < persistance < pre-call fetch. Clavier : **exécuté** jusqu'au moteur, base simulée, heure fixée — le contexte persisté porte les trois variables et **la consigne rendue dit « État : PAUSE »**, pas « État : . » (l'appel réel du 15/09). Le pre-call fetch gagne ; une valeur injectée au rejeu reste ; l'état du premier tour reste aux tours suivants ; sans horaires, dictionnaire persisté exact (depuis le 16/09, avec la date et l'heure de l'appel et rien d'autre). ⚠️ Ne couvre pas un moteur qui rendrait depuis un autre dictionnaire | n° 151 |
| `test_cle_de_cache_mistral.py` | 🚨 **Chaque requête de conversation vers Mistral porte la clé de cache de l'agent** (`mark-wf-<id>`), sans quoi Mistral ne sert rien depuis son cache (0 jeton mesuré le 15/09, 8 % en appel réel). ✅ **Vérifié sur le corps RÉELLEMENT ENVOYÉ** : client OpenAI du service, seule sa couche réseau remplacée, `prompt_cache_key` et `random_seed` à la racine du JSON. Graine et clé ensemble ; requête acceptée par le client. 🔒 **Sans clé, requête Mistral identique** au constructeur amont ; **OpenAI identique avec ou sans clé**. Branchement **dans les deux sens et compté** : seul l'appel de conversation reçoit la clé (voix : pas le canal realtime, ni l'extraction, ni la messagerie ; clavier : pas l'extraction). Estampille `llm_prompt_cache_key` sur un run clavier Mistral, **absente** ailleurs (dictionnaire exact). ⚠️ **Ne couvre pas, par construction** : pour Mistral, l'extraction et le résumé réutilisent le service de la conversation, leurs requêtes portent aussi la clé (sans effet sur les réponses) | n° 89 |
| `test_date_heure_appel.py` | **La date et l'heure de l'appel sont figées au décroché** (`date_appel` « mardi 15 septembre 2026 », `heure_appel` « 14 heures 32 », heure de Paris), **pour tous les agents** : une consigne qui lit l'heure à la seconde change son propre début à chaque nœud et casse le cache. Formats exacts sur minuit, « minuit 30 », midi pile, 9 h 05, 1 heure, le 1er du mois, le 31 décembre et le passage à l'an neuf, **les deux changements d'heure** ; valeur fournie conservée ; entrée non modifiée ; **ne lève jamais**. Voix : motif dans l'ordre état d'ouverture < date < persistance < pre-call fetch. Clavier : **exécuté**, la consigne rendue dit « Nous sommes le mardi 15 septembre 2026, il est 14 heures 32 » ; l'heure du premier tour reste aux tours suivants | n° 89 |
| `test_politique_derreur_pipecat.py` | 🚨 **Quelle panne de fournisseur TERMINE l'appel, et laquelle laisse l'agent debout et muet ?** Depuis Pipecat 1.8 une erreur ne porte plus son verdict : elle est classée, une catégorie **permanente** coûte au service son utilisabilité, et le pipeline applique sa politique — Dograh pose `CANCEL`, assertée sur le worker **construit** (le défaut de Pipecat est `CONTINUE`, sur lequel une clé refusée laisserait l'agent muet tout l'appel). ⛔ **La machinerie est à l'amont ; ce qui est protégé ici, c'est notre DÉPENDANCE** et surtout la **frontière** : 400, 401, 403, 404, 422 raccrochent ; 🔴 **402, 429 et les 5xx NON** — c'est exactement ce qui laisse le chantier `delai-modele` nécessaire. Frontière assertée **dans les deux sens et comptée** (une catégorie ajoutée en amont passe au rouge), code inconnu non permanent, et l'entonnoir de terminaison rend le même verdict. ⚠️ Sur la version d'avant le 16/09 ce fichier **ne s'importe même pas** : c'est un rouge pour la mauvaise raison, écrit ici plutôt que revendiqué | n° 154, n° 157 |
| `test_aucun_asyncio_run_dans_nos_tests.py` | **Aucun de nos tests n'appelle `asyncio.run()`**, qui modifie en sortant un réglage du processus hérité par tous les tests suivants. Lu dans l'arbre syntaxique de `tests/mark/`, pas par recherche de texte, et prouvé rouge sur un faux fichier. ⛔ **Ce qu'il ne prétend pas** : protéger à lui seul les tests d'amont. Le 16/09, un test d'amont tombait sur « no current event loop » ; nos `asyncio.run()` n'étaient qu'un déclencheur parmi trois, et la cause racine était le test d'amont lui-même, corrigé à la source. Né de la première CI jouée sur nos branches |
| `test_enveloppe_coupure_du_micro.py` | 🚨 **L'enveloppe de compatibilité rend-elle EXACTEMENT ce que rendait la fonction de l'amont qu'elle remplace** — mêmes stratégies, même ordre, même longueur, dans les deux états (supervision de décroché active ou non) ? ⛔ Elle n'existe que parce que **deux fichiers de tests de l'amont l'importent par son nom** : l'avoir retirée les faisait échouer à la **COLLECTE**, soit une seizaine de tests muets — et c'étaient ceux qui avaient vu un `NameError` que nos 523 tests ne voyaient pas. 🔑 **Sa fidélité repose sur deux défauts de schéma à `False`** (`mute_first_speech`, `mute_always`) et **rien ne l'assertait** ; leur test d'amont ne regarde que l'élément `[0]`, donc le jour où un réglage d'écran fait passer l'un des deux à `True`, l'enveloppe rendrait 4 ou 5 stratégies contre 3 promises **et leur test resterait vert**. L'ordre est asserté (Pipecat parcourt la liste, la première qui répond « couper » gagne), le rappel du moteur est asserté **par identité** et non par type, et les deux défauts sont épinglés | n° 116 |
| `test_base_communes.py` | La **base nationale des communes** embarquée se charge (34 000 à 36 000 communes, Saint-Maximin 60589 en 60740), **hors de la boucle d'événements et une seule fois**, et 🔴 **les clés sonores du fichier sont celles que le code calcule aujourd'hui** (200 communes tirées + les noms du banc) : changer `normaliser` ou `cle_sonore` sans régénérer le fichier ferait comparer la clé d'aujourd'hui de ce que dit l'appelant à la clé d'hier des communes, sans aucun échec visible. Codes postaux partagés triés par population | n° 142 |
| `test_analyse_communes.py` | **Le banc de l'essai du 16/09 rejoué** (56 phrases, magasin « Saint-Maximin (60) », textes seuls) : **0 commune annoncée sûre et fausse**, ≥ 48 sûres et justes, **compté** ; sans magasin, les 2 sûres fausses du prototype **nommées** ; sur 25 adresses et 64 phrases du labo, les fausses « sûres » connues **nommées une à une** (« à la campagne » → Campagne, « avant-hier » → Deuillet) — ⛔ une de plus est une régression, pas un ajout à la liste. La recherche reste **ancrée** (« avec deux personnes » ne donne rien) et **la mention au mot près** (sûre, incertaine, code postal dit conservé, orthographe de la transcription) | n° 142 |
| `test_adresse_etablissement.py` | L'**adresse de l'établissement** : les deux routes d'enregistrement (organisation, agent) l'écrivent et **refusent en 422** une commune inconnue ou qui ne porte pas ce code postal, avec le **nom officiel** stocké ; route des communes d'un code postal ; résolution **agent > organisation > rien** ; ⛔ **une adresse écrite à la main hors bornes ne fait jamais tomber l'appel** (celle de l'organisation reprend) ; injection au texte exact, valeur fournie conservée, pre-call fetch gagnant. Branchement **dans l'ordre** au téléphone, et chemin clavier **exécuté** jusqu'au moteur | n° 142 |
| `test_verification_communes_branchement.py` | 🚨 **La vérification des communes est-elle BRANCHÉE, au bon endroit ?** Éteinte, **liste des processeurs identique** ; allumée (le défaut), **juste avant le modèle, après la porte du superviseur**, absente du temps réel. Annote le **dernier** message de l'appelant, **une seule fois**, contexte provisoire compris, **seulement** aux étapes qui recueillent `commune`/`adresse…` ; trace `communes_verifiees` ; échec sans effet. 🔑 **Vérifié au niveau de la fonctionnalité** avec le **vrai agrégateur utilisateur et les vrais gestionnaires d'enregistrement** : le verbatim garde « c'est à Beauvet », le modèle et l'historique d'extraction lisent la mention — c'est le fait sur lequel repose D1. Boucle non retenue, **mesurée par comparaison** (battements en tâche de fond contre sur la boucle), pas par seuil. Chat texte **exécuté** jusqu'au modèle. ⚠️ `run_test` y reçoit un délai de démarrage de 15 s : sur un poste lent, le premier démarrage d'un processus dépasse la seconde par défaut et fige ensuite le démontage | n° 142 |

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

**La mesure de référence, au 16/09/2026 sur `chantier/verification-communes` (vérification des
communes, avant fusion) : 615 tests sur 31 fichiers, tous verts avec les patchs.** 537 sur
`mark/deploiement` à `f62b9a58` avant ce chantier (le 527 de la montée de version, plus le garde
`asyncio.run` et un test d'amont cité). 483 sur `mark/deploiement`
(fusion `d59c3788`, état d'ouverture) avant ces deux chantiers.
⚠️ **Elle change à chaque chantier** : 47 avant l'exposition des réglages Mistral, 105 le 10/09 au
soir, **113 après la réparation de la graine**, 234 après l'exposition des réglages de la
transcription, **350 après l'exposition des réglages Pipecat** (14/09), 359 après la réparation de
l'écran, **380 avec la conversion des nombres dictés** (15/09), **483 avec l'état d'ouverture** (15/09, branche, après relecture, contre-relecture et « minuit 30 »), **516 avec la clé de cache et la date de l'appel** (16/09, branche), **527 après la montée de version amont `23d22b95`** (16/09, branche : deux fichiers neufs, 6 pour la politique d'erreur de Pipecat et 4 pour l'enveloppe de coupure du micro), **615 avec la vérification des communes** (16/09, branche : quatre fichiers neufs). C'est ce nombre-là que la procédure de montée de version prend comme base —
**une mesure de référence périmée fait passer une perte de patch pour un changement de compte.**

⚠️ **Depuis Pipecat 1.10, la suite complète (`pytest tests/mark`) se FIGE au démontage**, sans aucun
test rouge : le compte de 527 ci-dessus est mesuré **module par module** (26 fichiers, un processus
par fichier, minuterie de 120 s). 🔑 **Ce n'est pas une méthode strictement plus fine** : un module
joué seul peut aussi **fabriquer un rouge** qui n'existe pas dans la suite entière (constaté sur
`api/tests/test_camb_tts_integration.py`, un test de l'amont qui dépend d'un état posé par un autre fichier). Les deux modes se
relisent l'un avec l'autre, aucun ne fait foi seul.

**Le rouge de référence, mesuré le matin sur les 47 :** sans les patchs de `registry.py`,
`check_validity.py` et `service_factory.py` : **1 erreur de collecte (les 19 de Mistral),
7 échecs (Deepgram), 21 verts.**
