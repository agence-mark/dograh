# Banc de téléphonie

Le banc du plan « téléphonie et mise en service » : un Asterisk, un simulateur d'appels (SIPp), une sonde et trois
faux fournisseurs, pour faire parler l'agent du fork de bout en bout sur un appel simulé, mesurer la coupure de parole
et la latence côté appelant. Aucun appel réel, aucun vrai fournisseur, aucune clé, aucune dépense.

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
| `sipp/` | Le simulateur : l'appel entrant (muet ou avec une voix d'appelant fabriquée par programme), le poste qui reçoit appels sortants et transferts, et la capture des paquets de son |
| `sonde/` | La sonde qui tient la place du fork pour mesurer la commande de vidage, le relais qui lit la file d'Asterisk pendant un appel du fork, et les analyseurs (`analyser.py`, `latence.py`, `coupures.py`) |
| `faux/` | Les faux fournisseurs : transcription (protocole de Soniox), modèle (API compatible OpenAI), voix (protocole d'ElevenLabs). Délais réglables, zéro par défaut |
| `fork/` | La préparation des données du fork par ses propres routes (compte, fournisseurs, configuration Asterisk, agents, outils, extensions) et le relevé de l'analyse d'un run |
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
./banc.sh appeler-sortant 1000   # appel sortant du fork, SIPp en réception décroche

./banc.sh voix tours-3 s4000,v1000,s3000,v1000,s3000,v1000,s3000   # une voix d'appelant
./banc.sh appeler-en-parlant 8000 essai tours-3 17000              # l'appelant parle, l'agent répond
./banc.sh analyse-run essai                                        # le chronomètre du fork (M2)
./banc.sh latence essai                                            # latence côté appelant, tour par tour
./banc.sh regler-faux '{"delai_modele_ms": 400}'                   # délais des faux fournisseurs (zero : défauts)

./banc.sh relais on                     # le flux audio passe par le relais qui lit la file d'Asterisk
./banc.sh coupures essai                # coupures de parole : son après la coupure, file d'Asterisk
./banc.sh relais off
./banc.sh construire-sans db4b79af sans-lot1   # image de l'API sans un commit, depuis une copie exportée
./banc.sh api-image sans-lot1                  # l'API du banc tourne sur cette image (local : l'arbre de travail)

./banc.sh tester tests/mark/test_x.py   # pytest sur l'arbre de travail, depuis api/
./banc.sh passage base d4990b89         # la suite tests/mark sur un commit exporté
./banc.sh passage branche HEAD
./banc.sh comparer                      # échecs de la branche comparés à ceux de la base

./banc.sh arreter           # arrête, garde les données
./banc.sh supprimer         # supprime conteneurs, volumes et réseau du banc
```

## Les faux fournisseurs

L'organisation du banc règle l'adresse de ses trois fournisseurs sur le service `faux`, par la route de l'écran
« Modèles ». Aucun code de `api/` ne change : ce sont trois fournisseurs dont le fork laisse régler l'adresse.

| Rôle | Protocole imité | Ce que rend le faux |
|---|---|---|
| Transcription | WebSocket de Soniox | Il regarde le niveau du son : un bloc sonore ouvre un tour, le premier bloc de silence le ferme, et le texte rendu est celui du tour |
| Modèle | `POST /v1/chat/completions` en flux | La phrase du tour. Un appel d'outil quand l'appelant dit « outil <motif> » et qu'un outil de la requête porte ce motif |
| Voix | WebSocket d'ElevenLabs | Un ton pur de durée connue (1 200 ms par défaut) pour chaque texte reçu, au format demandé (le fork demande du PCM et fabrique lui-même la loi mu) |

- Même appel, même résultat : rien n'est tiré au hasard.
- Cinq délais réglables sans redémarrer, tous à zéro par défaut : premier mot provisoire, fin de tour, premier morceau
  du modèle, écart entre morceaux, premier son de la voix. À zéro, le banc mesure le plancher du fork.
- Chaque événement est écrit, horodaté, dans `resultats/faux.jsonl`, à la même horloge que la capture de SIPp.
- La vérification de clé de Soniox vise une adresse fixe (`api.soniox.com`) qui ne suit pas l'adresse réglée. Sur le
  réseau fermé du banc, ce nom mène au faux fournisseur (`compose.yaml`), qui présente un certificat signé par une
  autorité fabriquée au démarrage (`faux/certificat.py`).

⚠️ Une latence mesurée sur ces faux fournisseurs n'est pas la latence d'un vrai appel : leurs délais sont réglés, pas
mesurés. Ce que le banc mesure vraiment, c'est ce que le fork et Asterisk ajoutent autour.

## La mesure de latence

De la fin de parole de l'appelant (dernier paquet sonore envoyé par SIPp) au premier paquet sonore de l'agent reçu par
SIPp, lus dans la même capture. `./banc.sh latence` découpe chaque tour en sept temps grâce au journal des faux
fournisseurs (aller, fin de tour, fork avant le modèle, modèle, fork avant la voix, voix, retour) et met à côté la
mesure M2 du chronomètre du fork, relevée par `./banc.sh analyse-run`.

Trois choses à savoir sur le chronomètre du fork :

- il ne mesure un tour que si le détecteur de voix local a vu la parole : la voix de synthèse de l'appelant (`v` dans
  le plan de `./banc.sh voix`) est prise pour de la parole, le ton pur (`t`) ne l'est pas ;
- il ne mesure pas un tour dont la réponse arrive en moins de 0,2 s : avec les faux à délai zéro, il reste vide ;
- l'analyse d'un run n'est lisible qu'après sa clôture, quelques secondes après le raccrochage : le relevé attend.

## Ce que le banc ne fait pas

- **Aucun vrai fournisseur.** L'agent parle, mais ce qu'il entend et ce qu'il dit sont écrits d'avance. Le banc ne dit
  rien de la qualité d'une transcription, d'un modèle ou d'une voix.
- **Pas de stockage.** L'image MinIO que le dépôt référence (`quay.io/minio/minio`) est refusée au téléchargement
  (401, relevé le 19/11/2026). L'API démarre sans elle, l'envoi des enregistrements est coupé sur le banc.

## Les extensions du banc

| Extension | Va vers | Sert à |
|---|---|---|
| `9100` à `9115` | La sonde | Une variante de mesure par extension (table dans `sonde/sonde.py`) |
| `8000` | Le fork | Extension avec agent |
| `8001` | Le fork | Extension sans agent |
| `8002` | Le fork | Agent avec deux outils de transfert : vers le poste `1000` (décroche) et le poste `1001` (sonne sans décrocher) |
| `8003` | Le fork | Agent avec un outil HTTP pointé sur le banc : le tour à appel d'outil |
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
| `9116` | En rafale | `FLUSH_MEDIA` | Texte brut, par `f(plain-text)` |
| `9120` | En continu, 10 coupures de parole | Rien | Par défaut |
| `9121` | En continu, 10 coupures de parole | `FLUSH_MEDIA` à chaque coupure | Par défaut |

Les deux dernières rejouent le flux continu du fork (son mixeur de sortie comble les silences de l'agent) et
demandent à Asterisk la longueur de sa file après chaque coupure (`GET_STATUS`).

Les deux premières disent si la correction s'entend dans les conditions du fork. Les six autres disent quel nom et
quel format Asterisk accepte : en rafale, la différence se compte en secondes et ne laisse pas de doute.
