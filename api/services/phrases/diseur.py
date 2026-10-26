"""[.mark] Chantier fiabilite-orchestration (F15, F23, F24, F25) puis correctifs-apres-banc-v4 (lot 4) :
le diseur des phrases du code.

Un diseur par appel (``moteur.phrases``). Il dit, par la voix et sans le modèle, la phrase en
vigueur d'un motif (``regles.resoudre``), et tient les verrous du mécanisme :

1. **jamais pendant que l'appelant parle** ;
2. famille *attente* : **une seule à la fois**, la première qui part gagne, puis
   ``REPOS_ATTENTE_S`` de repos ; famille *annonce* : passe toujours, **à la suite** de la phrase
   en cours ;
3. **variantes tournées** : jamais deux fois la même dans l'appel tant qu'une autre reste ;
4. **entrée dans l'historique** du modèle comme dite par l'agent (``historique=False`` seulement
   pendant la construction du résumé de passation, où le code l'interdit) ;
5. **visibilité** : chaque phrase dite est tracée dans la fiche de l'appel (``phrases_du_code`` :
   motif, agent, étape, niveau, texte, moment), lue par la fenêtre du run et la carte.

``veiller`` est la **veille générique** d'une attente (un outil, le travail de fond, une passation) :
premier délai, redites toutes les ``redite_s`` depuis la fin de la phrase précédente, plafonds par attente
et par appel, ordre « tournées » ou « dans l'ordre », puis la sortie de la règle. ``signaler_un_probleme``
est son pendant pour un fait (un outil, le travail de fond ou un transfert échoue) : un compteur dans
l'appel, la phrase tant qu'il est sous le plafond, la sortie quand il est atteint.

``attendre_le_systeme`` est l'horloge des motifs d'attente : elle ne court que pendant une attente
du système, s'annule dès que l'appelant reprend la parole et **repart à la fin de sa réplique** (F25).

⛔ Ne lève jamais dans l'appel : une phrase qui ne peut pas être dite n'est pas dite, journalisé.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from api.services.phrases.catalogue import FAMILLE_ANNONCE, FAMILLE_ATTENTE
from api.services.phrases.coupures import RegistreDesCoupures
from api.services.phrases.regles import PhraseResolue, resoudre

CLE_TRACE = "phrases_du_code"
REPOS_ATTENTE_S = 3.0
PAS_S = 0.1
# Une annonce attend la fin de la réplique de l'appelant au plus ce temps.
ATTENTE_MAX_ANNONCE_S = 15.0
# Un plancher pour attendre après la dernière redite avant la sortie, quand la règle n'a ni redite ni délai.
ATTENTE_AVANT_SORTIE_S = 5.0
# Le réglage commun : la pause minimale entre deux phrases d'attente (clé de l'agent principal).
CLE_REPOS = "phrases_repos_s"
REPOS_MIN_S = 1.0
REPOS_MAX_S = 10.0


async def _attendu(valeur: Any) -> None:
    """Un crochet de la veille peut être une fonction ou une coroutine."""
    if asyncio.iscoroutine(valeur):
        await valeur


@dataclass
class ResultatDeVeille:
    """Ce que la veille a fait : combien de phrases dites, et la sortie si elle est partie."""

    dites: int = 0
    sortie: Any = None  # ``IssueDeSortie`` ou ``None``


@dataclass
class Probleme:
    """Ce que le diseur a fait d'un fait (un échec) : le compte rendu et l'appelant le lisent."""

    dit: str | None = None
    issue: Any = None  # ``IssueDeSortie`` quand la sortie est partie
    incident: int = 0
    phrase: PhraseResolue | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def le_modele_reprend(self) -> bool:
        """Le résultat de l'outil va au modèle (sortie « le modèle reprend », ou aucune sortie posée)."""
        return self.issue is None or self.issue.le_modele_reprend


def _appelant_parle(moteur: Any) -> bool:
    try:
        moniteur = getattr(moteur, "call_monitor", None)
        return bool(moniteur is not None and moniteur.appelant_parle)
    except Exception:  # noqa: BLE001
        return False


def _robot_parle(moteur: Any) -> bool:
    try:
        moniteur = getattr(moteur, "call_monitor", None)
        return bool(moniteur is not None and moniteur.robot_parle)
    except Exception:  # noqa: BLE001
        return False


class DiseurDePhrases:
    def __init__(self, moteur: Any, *, horloge: Callable[[], float] = time.monotonic):
        self._moteur = moteur
        self._horloge = horloge
        self._debut = horloge()
        self._attente_en_cours = False
        self._fin_derniere_attente: float | None = None
        self._en_vol: asyncio.Task | None = None
        self._dites: dict[str, list[str]] = {}
        # Combien de fois chaque règle a parlé dans l'appel, et combien d'incidents ont eu lieu.
        self._compte_appel: dict[tuple, int] = {}
        self._incidents: dict[tuple, int] = {}
        self._nb_dites: dict[str, int] = {}
        self._sorties: set[asyncio.Task] = set()
        # Le texte de la phrase du code en train d'être dite (``None`` sinon) : le filet des
        # répliques coupées ne la reprend jamais (F25).
        self.texte_en_cours: str | None = None
        # D20 (voix-soniox) : chaque phrase dite et son minutage, pour dire au modèle, à la requête
        # suivante, ce que l'appelant a réellement entendu d'une phrase coupée (``coupures.py``).
        self.coupures = RegistreDesCoupures()

    # -- ce qui est en vigueur ---------------------------------------------------

    def _agent(self, agent: Any | None) -> Any:
        return agent if agent is not None else getattr(self._moteur, "active_agent", None)

    def repos_s(self) -> float:
        """La pause minimale entre deux phrases d'attente : le réglage commun du principal, sinon la
        valeur d'avant (``REPOS_ATTENTE_S``)."""
        try:
            brut = (getattr(self._moteur, "reglages_appel", None) or {}).get(CLE_REPOS)
            if isinstance(brut, (int, float)) and not isinstance(brut, bool):
                return min(max(float(brut), REPOS_MIN_S), REPOS_MAX_S)
        except Exception:  # noqa: BLE001
            pass
        return REPOS_ATTENTE_S

    def _endroit(self, agent: Any, etape: str | None, etape_id: str | None) -> tuple[str | None, str | None]:
        """Le nom et l'identifiant de l'étape : ceux de l'étape en cours de ``agent`` par défaut."""
        noeud = getattr(agent, "current_node", None)
        if etape is None:
            etape = getattr(noeud, "name", None)
        if etape_id is None and noeud is not None and getattr(noeud, "name", None) == etape:
            etape_id = getattr(noeud, "id", None)
        return etape, (etape_id if isinstance(etape_id, str) else None)

    def phrase(
        self,
        motif_id: str,
        agent: Any | None = None,
        etape: str | None = None,
        outil: str | None = None,
        etape_id: str | None = None,
    ) -> PhraseResolue | None:
        """La phrase en vigueur de ``motif_id`` pour ``agent`` (l'agent qui a la main par défaut),
        à ``etape`` (son étape en cours par défaut), pour ``outil`` (un motif qui vise un outil)."""
        agent = self._agent(agent)
        etape, etape_id = self._endroit(agent, etape, etape_id)
        return resoudre(
            motif_id,
            reglages_agent=getattr(agent, "reglages", None),
            reglages_principal=getattr(self._moteur, "reglages_appel", None),
            etape=etape,
            etape_id=etape_id,
            outil=outil,
        )

    def _choisir(self, phrase: PhraseResolue, rang: int | None = None) -> str:
        if phrase.ordre == "dans_l_ordre" and phrase.variantes:
            ordinal = rang if rang is not None else self._nb_dites.get(phrase.motif.id, 0)
            return phrase.variantes[min(max(ordinal, 0), len(phrase.variantes) - 1)]
        dites = self._dites.setdefault(phrase.motif.id, [])
        for variante in phrase.variantes:
            if variante not in dites:
                return variante
        # Toutes dites : on repart, jamais la même que la dernière s'il y en a une autre.
        derniere = dites[-1] if dites else None
        dites.clear()
        for variante in phrase.variantes:
            if variante != derniere:
                return variante
        return phrase.variantes[0]

    # -- l'horloge des attentes ----------------------------------------------------

    async def attendre_le_systeme(
        self,
        delai_s: float,
        tant_que: Callable[[], bool],
        *,
        pas_s: float = PAS_S,
    ) -> bool:
        """Attend ``delai_s`` d'attente du système. Le temps ne court pas pendant que l'appelant
        parle, et repart de zéro à la fin de sa réplique. ``True`` : le délai est écoulé et
        ``tant_que()`` est encore vrai ; ``False`` : la condition est tombée ou l'appel est fini."""
        ecoule = 0.0
        precedent = self._horloge()
        while True:
            await asyncio.sleep(pas_s)
            if self._moteur.is_call_disposed() or not tant_que():
                return False
            maintenant = self._horloge()
            if _appelant_parle(self._moteur):
                ecoule = 0.0
            else:
                ecoule += maintenant - precedent
            precedent = maintenant
            if ecoule >= delai_s:
                return True

    # -- dire -----------------------------------------------------------------------

    @property
    def en_cours(self) -> bool:
        return self.texte_en_cours is not None

    async def dire(self, motif_id: str, agent: Any | None = None, **options: Any) -> bool:
        """Dit la phrase en vigueur de ``motif_id``. ``True`` si elle part à la voix. Une attente
        refusée par un verrou n'est pas reportée : la première qui part gagne. Options : celles de
        ``dire_la_parole``."""
        return await self.dire_la_parole(motif_id, agent, **options) is not None

    async def dire_la_parole(
        self,
        motif_id: str,
        agent: Any | None = None,
        *,
        etape: str | None = None,
        historique: bool = True,
        variables: dict[str, str] | None = None,
        phrase: PhraseResolue | None = None,
        texte: str | None = None,
        rang: int | None = None,
        outil: str | None = None,
        etape_id: str | None = None,
        sortie: bool = False,
    ) -> Any | None:
        """Comme ``dire``, mais rend la lecture (``SpeechPlayback``, son ``text`` est la phrase
        dite) pour qui doit l'attendre ; ``None`` : rien n'est dit. ``texte`` : une phrase posée
        sur l'action elle-même (le repli propre d'un connecteur), dite à la place des variantes,
        sous les mêmes verrous et la même trace. ``rang`` : le numéro de la fois dans cette attente
        (ordre « dans l'ordre »). ``sortie`` : une phrase de sortie, qui passe comme une annonce (ni le
        repos ni l'attente en cours ne la retiennent).

        ⛔ ``mute_user`` toujours faux (F25) : l'appelant peut couper toute phrase du code, qui
        s'arrête net ; rien ne la relance."""
        try:
            agent = self._agent(agent)
            etape, etape_id = self._endroit(agent, etape, etape_id)
            phrase = phrase or self.phrase(motif_id, agent, etape, outil, etape_id)
            if phrase is None or not (phrase.dite or (texte and phrase.active) or (sortie and phrase.active)):
                return None
            if self._moteur.is_call_disposed():
                return None
            # Le plafond « au plus M fois dans l'appel » d'une règle (une sortie n'y est pas soumise).
            if (
                not sortie
                and phrase.max_par_appel is not None
                and self._compte_appel.get((phrase.motif.id, phrase.cle), 0) >= phrase.max_par_appel
            ):
                return None
            if sortie:
                await self._attendre_la_place()
            elif phrase.motif.famille == FAMILLE_ATTENTE:
                # Une attente se dit à la voix seulement : au clavier, la réponse arrive à l'écran.
                if getattr(self._moteur, "sans_sortie_audio", False) is True:
                    return None
                if _appelant_parle(self._moteur) or self._attente_en_cours:
                    return None
                if (
                    self._fin_derniere_attente is not None
                    and self._horloge() - self._fin_derniere_attente < self.repos_s()
                ):
                    return None
                self._attente_en_cours = True
            elif phrase.motif.famille == FAMILLE_ANNONCE:
                await self._attendre_la_place()
            dite = self._texte(phrase, texte, variables, rang)
            self._tracer(phrase, dite, agent, etape, rang=rang, sortie=sortie)
            self.texte_en_cours = dite
            try:
                parole = await self._dire_a_la_voix(dite, historique)
            except BaseException:
                # Revue du 19/10 : une annulation (la seconde phrase arrêtée quand le travail rend
                # son résultat) libère aussi le verrou, sinon plus aucune attente ne serait dite.
                self._fini(phrase)
                raise
            self._compter(phrase, sortie)
            self._en_vol = asyncio.get_running_loop().create_task(
                self._suivre(parole, phrase), name=f"phrase:{phrase.motif.id}"
            )
            logger.info(f"[phrases] {phrase.motif.id} ({phrase.niveau}) : {dite!r}")
            return parole
        except asyncio.CancelledError:
            raise
        except Exception as erreur:  # noqa: BLE001 -- une phrase ne coûte jamais l'appel
            logger.warning(f"[phrases] {motif_id} non dite : {erreur!r}")
            return None

    async def _dire_a_la_voix(self, texte: str, historique: bool) -> Any:
        """Le son fabriqué au décroché s'il existe (lot 4 ter, F22 : joué sans solliciter la voix,
        transcription jointe) ; sinon la voix de l'appel, comme avant."""
        from api.services.phrases.sons import fabrique_de

        fabrique = fabrique_de(self._moteur)
        son = fabrique.son(texte) if fabrique is not None else None
        if son is not None:
            parole = await self._moteur.queue_speech(
                audio=son.audio,
                transcript=texte,
                append_to_context=historique,
                persist_to_logs=True,
                mute_user=False,
            )
            if getattr(getattr(parole, "outcome", None), "name", None) != "FAILED":
                self.coupures.noter(texte, son.mots, parole, historique)
                return parole
            logger.warning(f"[phrases] son fabriqué non joué, dit par la voix : {texte!r}")
        parole = await self._moteur.queue_speech(
            texte,
            append_to_context=historique,
            persist_to_logs=True,
            mute_user=False,
        )
        # Dite par la voix de l'appel : Pipecat raccourcit lui-même l'historique, mais le compte rendu
        # ne sait pas jusqu'où (aucun minutage gardé ici).
        self.coupures.noter(texte, (), parole, historique)
        return parole

    def prendre(
        self,
        motif_id: str,
        agent: Any | None = None,
        *,
        etape: str | None = None,
        variables: dict[str, str] | None = None,
    ) -> str | None:
        """Le texte en vigueur de ``motif_id``, choisi et tracé, pour une phrase qui part dans le
        flux du modèle lui-même (la réponse perdue : le texte remplace la réponse vide, il entre
        donc dans l'historique comme une réplique de l'agent). ``None`` : phrase éteinte.
        ⛔ Ne lève jamais."""
        try:
            agent = self._agent(agent)
            if etape is None:
                etape = getattr(getattr(agent, "current_node", None), "name", None)
            phrase = self.phrase(motif_id, agent, etape)
            if phrase is None or not phrase.dite:
                return None
            # Un incident de plus : la phrase tant qu'il est sous le plafond de l'appel, la sortie de la
            # règle quand il l'atteint (au premier si la règle n'a pas de plafond).
            cle = (phrase.motif.id, phrase.cle)
            self._incidents[cle] = self._incidents.get(cle, 0) + 1
            n = self._incidents[cle]
            plafond = phrase.max_par_appel
            texte = None
            if plafond is None or n <= plafond:
                texte = self._texte(phrase, None, variables, n - 1)
                self._tracer(phrase, texte, agent, etape, rang=n - 1)
                self._compter(phrase, False)
                logger.info(f"[phrases] {phrase.motif.id} ({phrase.niveau}) : {texte!r}")
            if phrase.sortie_posee and n >= (plafond or 1):
                self._lancer_la_sortie(phrase, agent, etape, n - 1)
            return texte
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[phrases] {motif_id} non prise : {erreur!r}")
            return None

    def _lancer_la_sortie(
        self, phrase: PhraseResolue, agent: Any, etape: str | None, rang: int
    ) -> None:
        """La sortie d'une règle dont le texte part dans le flux du modèle (la réponse perdue) : en
        tâche, derrière ce texte (la phrase de sortie passe après la phrase en cours et la réplique de
        l'appelant). ⛔ Ne lève jamais."""
        try:
            from api.services.phrases.sorties import executer

            tache = asyncio.get_running_loop().create_task(
                executer(self._moteur, self, phrase, agent=agent, etape=etape, rang=rang),
                name=f"sortie:{phrase.motif.id}",
            )
            self._sorties.add(tache)
            tache.add_done_callback(self._sorties.discard)
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[phrases] sortie de {phrase.motif.id} non lancée : {erreur!r}")

    def _texte(
        self,
        phrase: PhraseResolue,
        texte: str | None,
        variables: dict[str, str] | None,
        rang: int | None = None,
    ) -> str:
        dite = (
            texte.strip()
            if isinstance(texte, str) and texte.strip()
            else self._choisir(phrase, rang)
        )
        for nom, valeur in (variables or {}).items():
            dite = dite.replace("{{" + nom + "}}", str(valeur))
        self._dites.setdefault(phrase.motif.id, []).append(dite)
        return dite

    def _sous_le_plafond(self, phrase: PhraseResolue) -> bool:
        """La règle peut encore parler dans cet appel (« au plus M fois dans l'appel »)."""
        return (
            phrase.max_par_appel is None
            or self._compte_appel.get((phrase.motif.id, phrase.cle), 0) < phrase.max_par_appel
        )

    def _compter(self, phrase: PhraseResolue, sortie: bool) -> None:
        """Une phrase dite de plus : pour le plafond de la règle dans l'appel, et l'ordre des phrases.
        Une phrase de sortie ne compte pas."""
        if sortie:
            return
        self._nb_dites[phrase.motif.id] = self._nb_dites.get(phrase.motif.id, 0) + 1
        cle = (phrase.motif.id, phrase.cle)
        self._compte_appel[cle] = self._compte_appel.get(cle, 0) + 1

    async def _attendre_la_place(self) -> None:
        """Une annonce passe après la phrase du code en cours et après la réplique de l'appelant."""
        en_vol = self._en_vol
        if en_vol is not None and not en_vol.done():
            await asyncio.gather(asyncio.shield(en_vol), return_exceptions=True)
        limite = self._horloge() + ATTENTE_MAX_ANNONCE_S
        while _appelant_parle(self._moteur) and self._horloge() < limite:
            await asyncio.sleep(PAS_S)

    async def _suivre(self, parole: Any, phrase: PhraseResolue) -> None:
        try:
            await parole.wait()
        except Exception as erreur:  # noqa: BLE001
            logger.debug(f"[phrases] fin de lecture illisible : {erreur!r}")
        finally:
            self._fini(phrase)

    def _fini(self, phrase: PhraseResolue) -> None:
        self.texte_en_cours = None
        if phrase.motif.famille == FAMILLE_ATTENTE:
            self._attente_en_cours = False
            self._fin_derniere_attente = self._horloge()

    async def attendre_la_fin(self) -> None:
        en_vol = self._en_vol
        if en_vol is not None and not en_vol.done():
            await asyncio.gather(asyncio.shield(en_vol), return_exceptions=True)

    # -- la veille générique d'une attente -------------------------------------------

    async def veiller(
        self,
        motif_id: str,
        tant_que: Callable[[], bool],
        *,
        agent: Any | None = None,
        etape: str | None = None,
        outil: str | None = None,
        phrase: PhraseResolue | None = None,
        premiere: str | Callable[[], str | None] | None = None,
        historique: bool = True,
        au_depart: Callable[[], None] | None = None,
        avant_chaque: Callable[[], Any] | None = None,
        apres_chaque: Callable[[Any], Any] | None = None,
        pas_s: float = PAS_S,
    ) -> ResultatDeVeille:
        """La veille d'une attente (un outil, le travail de fond, une passation) tant que ``tant_que()``
        est vrai : la phrase au bout de ``delai_s`` d'attente du système, puis ses redites toutes les
        ``redite_s`` **depuis la fin de la phrase précédente**, au plus ``max_par_attente`` fois (la
        première comprise) et ``max_par_appel`` dans l'appel ; l'ordre est celui de la règle ; puis la
        sortie de la règle si l'attente dure encore (une règle qui n'en pose pas ne fait rien de plus).

        ``premiere`` : le texte de la première phrase quand il vient d'ailleurs (l'annonce que l'agent
        écrit en confiant le travail) ; les redites restent les phrases de la règle. ``au_depart`` est
        appelé quand la première phrase est partie ; ``avant_chaque()`` avant de dire chaque phrase et
        ``apres_chaque(parole)`` quand elle est finie (l'un et l'autre peuvent être des coroutines).

        Une attente refusée par un verrou n'est pas reportée (la première qui part gagne). Le temps ne
        court qu'en attente du système : jamais pendant que l'appelant parle. ⛔ Ne lève jamais."""
        resultat = ResultatDeVeille()
        try:
            agent = self._agent(agent)
            etape, etape_id = self._endroit(agent, etape, None)
            phrase = phrase or self.phrase(motif_id, agent, etape, outil, etape_id)
            if phrase is None or not phrase.active:
                return resultat
            premier_texte = premiere() if callable(premiere) else premiere
            if not (phrase.dite or premier_texte):
                return resultat
            if not await self.attendre_le_systeme(phrase.delai_s or 0.0, tant_que, pas_s=pas_s):
                return resultat
            rang = 0
            while True:
                if rang > 0 and self._fin_derniere_attente is not None:
                    # Une redite plus courte que la pause minimale attend la fin de la pause (elle ne
                    # finit pas l'attente) : elle part « toutes les » max(intervalle, pause).
                    reste = self.repos_s() - (self._horloge() - self._fin_derniere_attente)
                    if reste > 0 and not await self.attendre_le_systeme(reste, tant_que, pas_s=pas_s):
                        return resultat
                texte = (premier_texte if rang == 0 else None) or None
                if avant_chaque is not None:
                    await _attendu(avant_chaque())
                parole = await self.dire_la_parole(
                    motif_id,
                    agent,
                    etape=etape,
                    etape_id=etape_id,
                    outil=outil,
                    phrase=phrase,
                    historique=historique,
                    texte=texte,
                    rang=rang,
                )
                if parole is None:
                    # Un verrou la refuse (la première qui part gagne) ou le plafond de l'appel est
                    # atteint : l'attente n'est pas reportée.
                    if rang == 0 or not self._sous_le_plafond(phrase):
                        return resultat
                    # Une redite refusée un instant (l'appelant parle) compte comme dite : la suivante
                    # est à l'intervalle de la règle, jamais une boucle sans fin.
                    rang += 1
                    if rang >= phrase.max_par_attente:
                        break
                    if not await self.attendre_le_systeme(phrase.redite_s or 0.0, tant_que, pas_s=pas_s):
                        return resultat
                    continue
                resultat.dites += 1
                if rang == 0 and au_depart is not None:
                    au_depart()
                try:
                    await parole.wait()
                except Exception as erreur:  # noqa: BLE001
                    logger.debug(f"[phrases] fin de lecture illisible : {erreur!r}")
                if apres_chaque is not None:
                    await _attendu(apres_chaque(parole))
                rang += 1
                if rang >= phrase.max_par_attente or phrase.redite_s is None:
                    break
                if not await self.attendre_le_systeme(phrase.redite_s, tant_que, pas_s=pas_s):
                    return resultat
            sortie_a_faire = bool(
                phrase.ensuite.phrases
                or phrase.ensuite.noter
                or (phrase.ensuite.action and phrase.ensuite.action != "continuer")
            )
            if sortie_a_faire:
                # Après la dernière phrase, si l'attente dure encore une fois l'intervalle de la règle.
                pause = phrase.redite_s or phrase.delai_s or ATTENTE_AVANT_SORTIE_S
                if await self.attendre_le_systeme(max(pause, pas_s), tant_que, pas_s=pas_s):
                    from api.services.phrases.sorties import executer

                    resultat.sortie = await executer(
                        self._moteur, self, phrase, agent=agent, etape=etape, rang=rang
                    )
        except asyncio.CancelledError:
            raise
        except Exception as erreur:  # noqa: BLE001 -- une veille ne coûte jamais l'appel
            logger.warning(f"[phrases] veille de {motif_id} : {erreur!r}")
        return resultat

    def lancer_la_veille(
        self, motif_id: str, tant_que: Callable[[], bool], *, nom: str | None = None, **options: Any
    ) -> asyncio.Task:
        """Lance ``veiller`` en tâche. La tâche porte ``mark_phrase_partie`` dès que la première
        phrase est partie : ``arreter_la_veille`` ne la coupe alors pas (une phrase commencée se
        termine ; ses redites s'arrêtent d'elles-mêmes quand ``tant_que`` tombe)."""
        tache_ref: dict[str, asyncio.Task] = {}

        def au_depart() -> None:
            tache = tache_ref.get("t")
            if tache is not None:
                tache.mark_phrase_partie = True  # type: ignore[attr-defined]

        async def corps() -> ResultatDeVeille:
            return await self.veiller(motif_id, tant_que, au_depart=au_depart, **options)

        tache = asyncio.get_running_loop().create_task(corps(), name=nom or f"phrase:{motif_id}")
        tache_ref["t"] = tache
        return tache

    @staticmethod
    def arreter_la_veille(tache: asyncio.Task | None) -> None:
        """Le résultat est arrivé : coupe la veille qui n'a encore rien dit ; une phrase commencée
        finit, puis la veille s'arrête (sa condition est tombée)."""
        if tache is None or tache.done() or tache is asyncio.current_task():
            return
        if not getattr(tache, "mark_phrase_partie", False):
            tache.cancel()

    # -- un fait (un échec) -------------------------------------------------------

    async def signaler_un_probleme(
        self,
        motif_id: str,
        agent: Any | None = None,
        *,
        etape: str | None = None,
        outil: str | None = None,
        texte: str | None = None,
        historique: bool = True,
        seulement_si_posee: bool = False,
        differer: bool = True,
    ) -> Probleme:
        """Un fait (l'échec d'un outil, du travail de fond, d'un transfert) : le n-ième incident de
        l'appel pour cette règle. La phrase est dite tant que l'incident est sous le plafond « au plus M
        fois dans l'appel » ; quand il l'atteint (au premier si la règle n'en pose pas), la sortie de la
        règle part : dire, noter dans la fiche, puis l'action finale. Éteinte : rien de dit, le modèle
        lit l'échec. ``seulement_si_posee`` : une règle du défaut du catalogue ne parle pas (un outil
        HTTP qui échoue ne disait rien avant). ``texte`` : la phrase propre de l'action, dite à la place
        des variantes. ``differer`` faux : appelé hors d'un appel de fonction (le garde-fou de sortie d'impasse),
        l'action finale est lancée par l'appelant. ⛔ Ne lève jamais."""
        probleme = Probleme()
        try:
            agent = self._agent(agent)
            etape, etape_id = self._endroit(agent, etape, None)
            phrase = self.phrase(motif_id, agent, etape, outil, etape_id)
            if phrase is None or not phrase.active:
                return probleme
            if seulement_si_posee and not phrase.posee:
                return probleme
            probleme.phrase = phrase
            cle = (phrase.motif.id, phrase.cle)
            self._incidents[cle] = self._incidents.get(cle, 0) + 1
            n = probleme.incident = self._incidents[cle]
            plafond = phrase.max_par_appel
            if phrase.dite or texte:
                if plafond is None or n <= plafond:
                    parole = await self.dire_la_parole(
                        motif_id,
                        agent,
                        etape=etape,
                        etape_id=etape_id,
                        outil=outil,
                        phrase=phrase,
                        historique=historique,
                        texte=texte,
                        rang=n - 1,
                    )
                    if parole is not None:
                        probleme.dit = getattr(parole, "text", None)
                        self.coupures.marquer_compte_rendu(parole)
            if (phrase.sortie_posee or phrase.motif.sortie_par_le_code) and n >= (plafond or 1):
                from api.services.phrases.sorties import executer

                # Appelé pendant un appel de fonction : l'action finale (transférer, raccrocher) part
                # après la remise du résultat, jamais attendue dans l'échéance de l'appel.
                probleme.issue = await executer(
                    self._moteur, self, phrase, agent=agent, etape=etape, rang=n - 1, differer=differer
                )
                probleme.notes = list(probleme.issue.notes)
        except asyncio.CancelledError:
            raise
        except Exception as erreur:  # noqa: BLE001 -- un échec ne coûte jamais l'appel
            logger.warning(f"[phrases] problème {motif_id} : {erreur!r}")
        return probleme

    async def dire_la_sortie(
        self, phrase: PhraseResolue, agent: Any | None = None, *, etape: str | None = None, rang: int = 0
    ) -> Any | None:
        """Dit la phrase de sortie d'une règle (une de ses variantes « Ensuite », tournées), sous la
        même trace. Elle passe comme une annonce : après la phrase en cours et la réplique de l'appelant."""
        from dataclasses import replace

        sortie = replace(
            phrase,
            variantes=tuple(phrase.ensuite.phrases),
            ordre="tournees",
            active=True,
            max_par_appel=None,
            cle=(*(phrase.cle or ()), "sortie"),
        )
        return await self.dire_la_parole(
            phrase.motif.id, agent, etape=etape, phrase=sortie, rang=rang, sortie=True
        )

    def _tracer(
        self,
        phrase: PhraseResolue,
        texte: str,
        agent: Any,
        etape: str | None,
        *,
        rang: int | None = None,
        sortie: bool = False,
    ) -> None:
        try:
            fiche = getattr(self._moteur, "_gathered_context", None)
            if not isinstance(fiche, dict):
                return
            from api.services.workflow.fiche_au_fil_de_leau import CLE_TOUR

            fiche.setdefault(CLE_TRACE, []).append(
                {
                    "motif": phrase.motif.id,
                    "agent": getattr(agent, "workflow_id", None),
                    "etape": etape,
                    "niveau": phrase.niveau,
                    "texte": texte,
                    "tour": fiche.get(CLE_TOUR),
                    "moment_s": round(self._horloge() - self._debut, 2),
                    # Lot 4 : la fois dans l'attente (0 = la première phrase, 1 = la première redite…),
                    # et la phrase de sortie. Lues par la fenêtre du run ; une phrase du code se
                    # reconnaît à ``du_code`` (au clavier, la transcription l'affiche en gris).
                    **({"redite": rang} if rang else {}),
                    **({"sortie": True} if sortie else {}),
                    "du_code": True,
                }
            )
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[phrases] trace non écrite : {erreur!r}")
