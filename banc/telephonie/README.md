# Banc de téléphonie

Le banc des lots 0 et 1 du plan « téléphonie et mise en service » : un Asterisk, un simulateur d'appels (SIPp) et une
sonde, pour faire arriver un appel simulé jusqu'au fork et mesurer la coupure de parole. Aucun appel réel, aucun
fournisseur, aucune dépense.

## Ce que le banc garantit

- **Un compose à part** (`compose.yaml`, projet `banc-telephonie-mark`). Il ne lit, n'étend et ne modifie aucun autre
  compose du dépôt, et a ses propres conteneurs, volumes et réseau.
- **Rien ne sort.** Le réseau du banc est interne (`internal: true`) et aucun port n'est publié sur le poste : pas
  d'appel vers l'extérieur, pas de fournisseur, pas de télémesure. Les constructions d'images, elles, téléchargent.
- **Aucun secret dans le dépôt.** Les mots de passe locaux sont tirés au hasard dans `.env` (ignoré par git) par
  `./banc.sh preparer`. `.env.example` n'en donne que les noms.
- **Rien dans l'image de production.** `api/Dockerfile` ne copie que `api/`, `simulateur/`, `docs/` et quelques
  scripts : ce dossier n'y entre pas.

## Ce qu'il contient

| Dossier | Rôle |
|---|---|
| `asterisk/` | Asterisk 22.12.0 construit depuis les sources officielles (empreinte contrôlée), et ses six fichiers de configuration |
| `sipp/` | Le simulateur : un scénario d'appel entrant, et la capture des paquets de son reçus |
| `sonde/` | Un petit serveur qui tient la place du fork pour mesurer la commande de vidage, et l'analyseur des captures |
| `fork/` | La préparation des données du fork par ses propres routes (compte, configuration Asterisk, agent, extensions) |
| `essais/` | L'image des tests Python du fork (pytest, mutmut), pour un poste sans Python 3.13 |
| `resultats/` | Ce que le banc produit en tournant : captures, journaux, mesures. Ignoré par git |

Pourquoi Asterisk **22.8.0 au minimum** : le fork passe `transport_data` à `externalMedia`
(`api/services/telephony/ari_manager.py:850`), ajouté dans cette version. Le banc prend la dernière 22 publiée.

## S'en servir

```bash
./banc.sh preparer          # une fois : écrit .env
./banc.sh demarrer          # Asterisk, la sonde, SIPp
./banc.sh etat              # version et modules d'Asterisk

./banc.sh sonder 9111 5     # cinq appels de mesure sur la variante 9111
./banc.sh analyser          # le tableau des mesures

./banc.sh demarrer-fork     # en plus : l'API du dépôt, sa base et Redis
./banc.sh preparer-fork     # compte, configuration Asterisk, agent, extensions
./banc.sh appeler 8000 essai

./banc.sh tester tests/mark/test_x.py   # pytest sur l'arbre de travail, depuis api/

./banc.sh arreter           # arrête, garde les données
./banc.sh supprimer         # supprime conteneurs, volumes et réseau du banc
```

## Ce que le banc ne fait pas

- **L'agent ne parle pas.** Aucun fournisseur de transcription, de modèle ni de voix n'est configuré : l'appel arrive
  jusqu'au démarrage de l'agent, puis le fork raccroche (`stt-unknown`). Aller plus loin demande des clés de test.
- **Pas de stockage.** L'image MinIO que le dépôt référence (`quay.io/minio/minio`) est refusée au téléchargement
  (401, relevé le 19/11/2026). L'API démarre sans elle, l'envoi des enregistrements est coupé sur le banc.

## Les extensions du banc

| Extension | Va vers | Sert à |
|---|---|---|
| `9100` à `9115` | La sonde | Une variante de mesure par extension (table dans `sonde/sonde.py`) |
| `8000` | Le fork | Extension avec agent |
| `8001` | Le fork | Extension sans agent |
| Toute autre | Le fork | Extension inconnue |

Le plan d'appels (`asterisk/conf/extensions.conf`) n'a pas de `Answer()` avant `Stasis()` : le fork prend un canal déjà
décroché pour un appel sortant et l'abandonne (`ari_manager.py:535-566`).

## Ce que mesure la sonde

Asterisk garde en file le son qu'on lui envoie et le joue au rythme du téléphone. Quand l'appelant coupe la parole, le
son déjà en file continue d'être joué, sauf si on demande à Asterisk de vider sa file.

La sonde prend l'appel avec les mêmes paramètres que le fork, envoie un son continu, s'arrête à un instant T0 et
envoie, ou non, une commande. L'analyseur lit ensuite, sur les paquets reçus par SIPp, le moment où le son cesse.

| Variante | Envoi | À T0 | Format demandé |
|---|---|---|---|
| `9100` | Au rythme réel, comme le fork | Rien | Par défaut (texte brut) |
| `9101` | Au rythme réel | `FLUSH_MEDIA` | Par défaut |
| `9110` | En rafale : 5 s d'un coup | Rien | Par défaut |
| `9111` | En rafale | `FLUSH_MEDIA` | Par défaut |
| `9112` | En rafale | `MEDIA_FLUSH` | Par défaut |
| `9113` | En rafale | `{"command":"FLUSH_MEDIA"}` | Par défaut |
| `9114` | En rafale | `{"command":"FLUSH_MEDIA"}` | JSON, par `f(json)` |
| `9115` | En rafale | `FLUSH_MEDIA` | JSON, par `f(json)` |

Les deux premières disent si la correction s'entend dans les conditions du fork. Les six autres disent quel nom et
quel format Asterisk accepte : en rafale, la différence se compte en secondes et ne laisse pas de doute.
