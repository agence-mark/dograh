"""[.mark] Chantier fiabilite-orchestration (F15, F23, F24, F25) : le diseur des phrases du code.

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

``attendre_le_systeme`` est l'horloge des motifs d'attente : elle ne court que pendant une attente
du système, s'annule dès que l'appelant reprend la parole et **repart à la fin de sa réplique** (F25).

⛔ Ne lève jamais dans l'appel : une phrase qui ne peut pas être dite n'est pas dite, journalisé.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

from loguru import logger

from api.services.phrases.catalogue import FAMILLE_ANNONCE, FAMILLE_ATTENTE
from api.services.phrases.regles import PhraseResolue, resoudre

CLE_TRACE = "phrases_du_code"
REPOS_ATTENTE_S = 3.0
PAS_S = 0.1
# Une annonce attend la fin de la réplique de l'appelant au plus ce temps.
ATTENTE_MAX_ANNONCE_S = 15.0


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
        # Le texte de la phrase du code en train d'être dite (``None`` sinon) : le filet des
        # répliques coupées ne la reprend jamais (F25).
        self.texte_en_cours: str | None = None

    # -- ce qui est en vigueur ---------------------------------------------------

    def _agent(self, agent: Any | None) -> Any:
        return agent if agent is not None else getattr(self._moteur, "active_agent", None)

    def phrase(
        self, motif_id: str, agent: Any | None = None, etape: str | None = None
    ) -> PhraseResolue | None:
        """La phrase en vigueur de ``motif_id`` pour ``agent`` (l'agent qui a la main par défaut),
        à ``etape`` (son étape en cours par défaut)."""
        agent = self._agent(agent)
        if etape is None:
            noeud = getattr(agent, "current_node", None)
            etape = getattr(noeud, "name", None)
        return resoudre(
            motif_id,
            reglages_agent=getattr(agent, "reglages", None),
            reglages_principal=getattr(self._moteur, "reglages_appel", None),
            etape=etape,
        )

    def _choisir(self, phrase: PhraseResolue) -> str:
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
    ) -> Any | None:
        """Comme ``dire``, mais rend la lecture (``SpeechPlayback``, son ``text`` est la phrase
        dite) pour qui doit l'attendre ; ``None`` : rien n'est dit. ``texte`` : une phrase posée
        sur l'action elle-même (le repli propre d'un connecteur), dite à la place des variantes,
        sous les mêmes verrous et la même trace.

        ⛔ ``mute_user`` toujours faux (F25) : l'appelant peut couper toute phrase du code, qui
        s'arrête net ; rien ne la relance."""
        try:
            agent = self._agent(agent)
            if etape is None:
                etape = getattr(getattr(agent, "current_node", None), "name", None)
            phrase = phrase or self.phrase(motif_id, agent, etape)
            if phrase is None or not (phrase.dite or (texte and phrase.active)):
                return None
            if self._moteur.is_call_disposed():
                return None
            if phrase.motif.famille == FAMILLE_ATTENTE:
                # Une attente se dit à la voix seulement : au clavier, la réponse arrive à l'écran.
                if getattr(self._moteur, "sans_sortie_audio", False) is True:
                    return None
                if _appelant_parle(self._moteur) or self._attente_en_cours:
                    return None
                if (
                    self._fin_derniere_attente is not None
                    and self._horloge() - self._fin_derniere_attente < REPOS_ATTENTE_S
                ):
                    return None
                self._attente_en_cours = True
            elif phrase.motif.famille == FAMILLE_ANNONCE:
                await self._attendre_la_place()
            dite = self._texte(phrase, texte, variables)
            self._tracer(phrase, dite, agent, etape)
            self.texte_en_cours = dite
            try:
                parole = await self._moteur.queue_speech(
                    dite,
                    append_to_context=historique,
                    persist_to_logs=True,
                    mute_user=False,
                )
            except Exception:
                self._fini(phrase)
                raise
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
            texte = self._texte(phrase, None, variables)
            self._tracer(phrase, texte, agent, etape)
            logger.info(f"[phrases] {phrase.motif.id} ({phrase.niveau}) : {texte!r}")
            return texte
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[phrases] {motif_id} non prise : {erreur!r}")
            return None

    def _texte(
        self, phrase: PhraseResolue, texte: str | None, variables: dict[str, str] | None
    ) -> str:
        dite = texte.strip() if isinstance(texte, str) and texte.strip() else self._choisir(phrase)
        for nom, valeur in (variables or {}).items():
            dite = dite.replace("{{" + nom + "}}", str(valeur))
        self._dites.setdefault(phrase.motif.id, []).append(dite)
        return dite

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

    def _tracer(self, phrase: PhraseResolue, texte: str, agent: Any, etape: str | None) -> None:
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
                }
            )
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[phrases] trace non écrite : {erreur!r}")
