"""[.mark] Builder partie 3, lot P (P1) : le banc enregistré d'une passation accueil → collègue.

Il rejoue une passation avec le VRAI coordinateur (``AgentTransferCoordinator._run``) et la VRAIE mesure découpée
(``groupe/mesure_passation.py``), sur un moteur scénarisé dont chaque geste dure ce que dit ``Delais`` : aucun appel
réel, aucun modèle, aucune voix, aucune base. L'horloge est **virtuelle** (``BoucleVirtuelle``) : une attente de 1,2 s
dure 1,2 s au banc sans qu'aucune seconde réelle passe, et deux jeux rendent les mêmes instants à la milliseconde.

Ce que le banc dit (questions n° 371 et VI.10, VI.11 de ``reference/08``) :

- **combien de passes du modèle se font à la suite** sur le chemin critique (passes de l'accueil, résumé, collègue) ;
- **où part le temps**, étape par étape, depuis la fin de parole de l'appelant : décision de l'accueil, annonce,
  attente, installation, première requête du collègue, premier mot, premier son ;
- **ligne par ligne** (ajout A2 d'Evan), ce que la passation refait à chaque fois pour un collègue de la réserve :
  chaque ligne du journal porte le geste du moteur qu'elle imite (fichier et fonction).

Les délais par défaut sont des hypothèses écrites, tirées des mesures du labo (VI.10, 18/10, run 1462 : premier mot du
cerveau 0,40 s médian, premier octet de la voix 0,09 s) ; ils se changent par scénario. ⚠️ Le banc mesure **l'ordre et
l'enchaînement** du code, pas un fournisseur : la mesure en production reste un geste d'Evan.
"""

from __future__ import annotations

import asyncio
import selectors
import time
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from api.services.groupe.mesure_passation import MesureDePassation
from api.services.workflow import agent_transfer
from api.services.workflow.agent_transfer import TransferRequest

COLLEGUE = 99
ACCUEIL = 1
ANNONCE = "Je vous passe ma collègue qui s'occupe des rendez-vous."


# --------------------------------------------------------------------------------------------------------------
# L'horloge virtuelle
# --------------------------------------------------------------------------------------------------------------


class _SelecteurVirtuel(selectors.DefaultSelector):
    """Au lieu d'attendre ``timeout`` secondes, avance l'horloge de la boucle d'autant et rend la main tout de suite."""

    def __init__(self) -> None:
        super().__init__()
        self.boucle: BoucleVirtuelle | None = None

    def select(self, timeout=None):
        if timeout is None:
            # Rien de prévu et rien de prêt : le banc attendrait pour toujours. Un banc bloqué est une faute du banc.
            raise RuntimeError("banc de passation bloqué : aucune attente prévue")
        if timeout > 0 and self.boucle is not None:
            self.boucle.avancer(timeout)
        return super().select(0)


class BoucleVirtuelle(asyncio.SelectorEventLoop):
    """Une boucle asyncio dont ``time()`` est virtuel : les attentes s'enchaînent sans durer."""

    def __init__(self) -> None:
        selecteur = _SelecteurVirtuel()
        self._maintenant = 0.0
        super().__init__(selecteur)
        selecteur.boucle = self

    def time(self) -> float:
        return self._maintenant

    def avancer(self, duree: float) -> None:
        self._maintenant += duree


# --------------------------------------------------------------------------------------------------------------
# Le scénario
# --------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Delais:
    """Ce que dure chaque geste au banc, en secondes (hypothèses écrites, voir l'en-tête)."""

    # Les passes de l'accueil avant l'appel d'outil : « note » (si l'accueil note lui-même au lieu du greffier,
    # n° 371) puis la passe qui appelle ``transfer_agent``.
    passe_note: float = 0.0
    passe_decision: float = 0.60
    # La voix de l'appel : premier octet, puis durée de l'annonce dite.
    voix_premier_octet: float = 0.09
    annonce: float = 1.80
    drain: float = 0.05
    # La préparation du collègue (``PipecatEngine.build_agent`` et ``prepare_agent``).
    ecrivains_de_fond: float = 0.05
    sessions_mcp: float = 0.30
    etape: float = 0.05
    activation: float = 0.02
    phrase_figee: float = 0.05
    resume: float = 1.00
    # Le collègue : premier mot de son modèle après le départ de sa requête.
    premier_mot_collegue: float = 0.40


@dataclass
class Ligne:
    """Une ligne du journal du banc : un geste, quand, et s'il pourrait se faire au décroché."""

    geste: str
    code: str
    debut: float
    fin: float
    a_chaque_passation: bool = True
    au_decroche_possible: bool = False

    @property
    def duree(self) -> float:
        return round(self.fin - self.debut, 3)


@dataclass
class Resultat:
    """Ce qu'un jeu du banc rend : instants depuis la fin de parole de l'appelant."""

    passes: list[str]
    lignes: list[Ligne]
    instants: dict[str, float]
    decoupe: dict[str, Any]
    segments_de_voix: list[tuple[str, float, float]]
    issue: str
    ordre_de_la_voix: list[str] = field(default_factory=list)

    def passes_a_la_suite(self) -> int:
        return len(self.passes)


class _Parole:
    """Une parole dite par la voix de l'appel au banc (l'interface utile de ``SpeechPlayback``)."""

    def __init__(self, fin: float) -> None:
        self._fin = fin

    @property
    def done(self) -> bool:
        return asyncio.get_running_loop().time() >= self._fin

    async def wait(self) -> bool:
        reste = self._fin - asyncio.get_running_loop().time()
        if reste > 0:
            await asyncio.sleep(reste)
        return True


class MoteurDeBanc:
    """Le moteur de l'appel, scénarisé : chaque geste du coordinateur dure ce que dit ``Delais``, et laisse une ligne.

    Les gestes imitent ceux du vrai moteur (``pipecat_engine.py``) ; la colonne ``code`` de chaque ligne le nomme."""

    def __init__(
        self,
        delais: Delais,
        *,
        reserve: bool,
        mcp: bool,
        groupe: bool,
        mcp_au_decroche: bool,
    ) -> None:
        self.d = delais
        self.boucle = asyncio.get_running_loop()
        self.lignes: list[Ligne] = []
        self.passes: list[str] = []
        self.segments: list[tuple[str, float, float]] = []
        self._voix_libre = 0.0
        self.sans_sortie_audio = False
        self.phrases = None
        self.reglages_appel = {"agents_specialises": [COLLEGUE]} if groupe else {}
        self._gathered_context: dict = {}
        self._transfer_outcomes: list[dict] = []
        self.call_monitor = SimpleNamespace(
            suspend=lambda: None, resume=lambda: None, cancel=lambda: None
        )
        self.mesure_passation = MesureDePassation(
            horloge=self.boucle.time, enregistrements=lambda: self._transfer_outcomes
        )
        self.context = SimpleNamespace(
            get_messages=lambda: list(self._messages),
            add_message=lambda m: self._messages.append(m),
        )
        self._messages: list[dict] = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"message {i}"}
            for i in range(6)
        ]
        self._reserve = reserve
        self._mcp = mcp
        self.source = self._agent("visite-accueil", ACCUEIL)
        self.collegue = self._agent("visite-collegue", COLLEGUE)
        if mcp and mcp_au_decroche:
            # Ouvertes à la mise en réserve (``_mettre_en_reserve``), au décroché : rien à rouvrir à la passation.
            self.collegue.mcp_sessions = {"outil-mcp": object()}
        self._actif = self.source
        self.premier_son = asyncio.Event()
        self.hold_audio_sample_rate = 8000
        self.transport_output_queue_frame = None

    # -- outils du banc ------------------------------------------------------------------------------------------

    def maintenant(self) -> float:
        return round(self.boucle.time(), 3)

    async def _geste(
        self, geste: str, code: str, duree: float, **options: bool
    ) -> None:
        debut = self.boucle.time()
        if duree > 0:
            await asyncio.sleep(duree)
        self.lignes.append(
            Ligne(geste, code, round(debut, 3), round(self.boucle.time(), 3), **options)
        )

    def _agent(self, visite: str, workflow_id: int):
        moteur = self

        async def rien(*_a, **_k):
            return None

        async def demarre():
            return True

        async def annuler_les_outils():
            await moteur._geste(
                "outils de l'accueil annulés", "AgentRuntime.cancel_tools", 0.0
            )

        return SimpleNamespace(
            visit_id=visite,
            workflow_id=workflow_id,
            llm=SimpleNamespace(),
            inference_llm=SimpleNamespace(),
            error=None,
            current_node=SimpleNamespace(id="debut", name="Début"),
            workflow=SimpleNamespace(start_node_id="debut"),
            mcp_sessions={},
            cancel_tools=annuler_les_outils,
            retire=rien,
            abort=rien,
            wait_until_started=demarre,
        )

    def _dire(self, qui: str, depuis: float, duree: float) -> tuple[float, float]:
        """La voix de l'appel est UNE : une parole commence quand la précédente est finie (jamais par-dessus)."""
        debut = max(depuis + self.d.voix_premier_octet, self._voix_libre)
        fin = debut + duree
        self._voix_libre = fin
        self.segments.append((qui, round(debut, 3), round(fin, 3)))
        return debut, fin

    # -- ce que le coordinateur lit et appelle ---------------------------------------------------------------------

    @property
    def active_agent(self):
        return self._actif

    def is_call_disposed(self) -> bool:
        return False

    def agent_can_act(self, agent) -> bool:
        return agent is self._actif

    def principal_chaud_pour(self, _workflow_id):
        return None

    def collegue_en_reserve(self, workflow_id) -> bool:
        return self._reserve and workflow_id == COLLEGUE

    def _get_otel_context(self):
        return None

    def garder_chaud(self, _source) -> bool:
        return bool(self.reglages_appel)

    def discard_pending_agent(self, _agent) -> None:
        return None

    def expect_response(self) -> None:
        return None

    async def queue_speech(self, text, **_options):
        debut, fin = self._dire(
            "annonce de l'accueil", self.boucle.time(), self.d.annonce
        )
        self.lignes.append(
            Ligne(
                "annonce dite par le code (message de l'outil)",
                "PipecatEngine.queue_speech",
                round(debut, 3),
                round(fin, 3),
            )
        )
        self.instants_annonce = (round(debut, 3), round(fin, 3))
        return _Parole(fin)

    async def drain_call_pipeline(self, timeout: float = 5.0) -> bool:
        await self._geste(
            "circuit de l'appel vidé", "PipecatEngine.drain_call_pipeline", self.d.drain
        )
        return True

    async def deactivate_agent(self, _agent) -> None:
        await self._geste(
            "accueil mis hors de la conversation", "PipecatEngine.deactivate_agent", 0.0
        )

    async def pause_background_context_writers(self) -> None:
        await self._geste(
            "écrivains de fond suspendus (extractions en vol attendues)",
            "PipecatEngine.pause_background_context_writers",
            self.d.ecrivains_de_fond,
        )

    async def build_agent(self, *, workflow_id, visit_id):
        debut = self.boucle.time()
        origine = "reserve" if self._reserve else "construit"
        if self._reserve:
            await self._geste(
                "collègue pris dans la réserve",
                "PipecatEngine._prendre_dans_la_reserve",
                0.0,
            )
            await self._geste(
                "cerveau de fond et garde du modèle (déjà posés à la mise en réserve : rien refait)",
                "preparer_le_travail, garder_l_agent",
                0.0,
            )
        else:
            await self._geste(
                "collègue construit (service de modèle, worker)",
                "AgentRuntimeFactory.build",
                1.0,
                au_decroche_possible=True,
            )
        await self._geste(
            "la fiche suit le collègue", "PipecatEngine._fusionner_la_fiche", 0.0
        )
        self.mesure_passation.installee(
            self.boucle.time() - debut, origine, None, self.collegue.visit_id
        )
        return self.collegue

    async def prepare_agent(self, agent) -> None:
        if self._mcp and not agent.mcp_sessions:
            await self._geste(
                "sessions MCP du collègue ouvertes",
                "PipecatEngine._open_mcp_sessions",
                self.d.sessions_mcp,
                au_decroche_possible=True,
            )
            agent.mcp_sessions = {"outil-mcp": object()}
        await self._geste(
            "consigne et outils de l'étape d'arrivée (la fiche du moment)",
            "PipecatEngine._prepare_node",
            self.d.etape,
        )

    async def activate_agent(self, _agent, *, timeout: float) -> bool:
        await self._geste(
            "collègue activé (message au worker, aucune connexion)",
            "PipecatEngine.activate_agent",
            self.d.activation,
        )
        return True

    async def transfert_fige_a_l_ouverture(self, _agent, _cible):
        await self._geste(
            "phrase figée de l'arrivée décidée (lectures en base)",
            "transfert_fige_a_l_ouverture",
            self.d.phrase_figee,
        )

    def commit_agent(self, agent, snapshot) -> None:
        self.mesure_passation.commise()
        self.lignes.append(
            Ligne(
                "collègue installé : consigne, outils, historique filtré (même contexte, aucune connexion)",
                "PipecatEngine.commit_agent",
                self.maintenant(),
                self.maintenant(),
            )
        )
        self._actif = agent

    async def notify_agent_entered(self, _agent) -> None:
        return None

    async def queue_node_opening(self, *, origin_visit_id=None, **_options):
        depart = self.boucle.time()
        self.passes.append("le collègue parle")
        self.mesure_passation.depart_de_requete(origin_visit_id, depart)
        self.boucle.create_task(self._reponse_du_collegue(depart))
        return SimpleNamespace(action="llm", playback=None)

    async def _reponse_du_collegue(self, depart: float) -> None:
        await asyncio.sleep(self.d.premier_mot_collegue)
        self.mesure_passation.premier_mot(self.collegue.visit_id)
        self.lignes.append(
            Ligne(
                "première requête du collègue → premier mot",
                "cerveau du collègue",
                round(depart, 3),
                self.maintenant(),
            )
        )
        debut, _fin = self._dire("réponse du collègue", self.boucle.time(), 2.0)
        reste = debut - self.boucle.time()
        if reste > 0:
            await asyncio.sleep(reste)
        resultat = self.mesure_passation.premier_octet()
        for enregistrement in self._transfer_outcomes:
            self.mesure_passation.completer(enregistrement)
        self.premier_son_a = self.maintenant()
        assert resultat is not None
        self.premier_son.set()

    def record_transfer_outcome(self, record: dict) -> None:
        self.mesure_passation.completer(record)
        self._transfer_outcomes.append(record)


async def _resume_au_banc(moteur: MoteurDeBanc):
    async def instantane(context, llm, *, resumer=True, **_options):
        if resumer:
            moteur.passes.append("résumé de la conversation")
            await moteur._geste(
                "résumé de la conversation par le modèle",
                "build_handoff_snapshot",
                moteur.d.resume,
            )
        else:
            await moteur._geste(
                "historique filtré, sans modèle", "build_handoff_snapshot", 0.0
            )
        messages = context.get_messages()
        return SimpleNamespace(
            messages=messages, boundary=len(messages), summarized=resumer
        )

    return instantane


async def _jouer(
    delais: Delais,
    *,
    reserve: bool,
    mcp: bool,
    groupe: bool,
    annonce: str | None,
    mcp_au_decroche: bool,
) -> Resultat:
    boucle = asyncio.get_running_loop()
    moteur = MoteurDeBanc(
        delais, reserve=reserve, mcp=mcp, groupe=groupe, mcp_au_decroche=mcp_au_decroche
    )

    async def attente_sans_son(*, stop_event, **_options):
        debut = boucle.time()
        await stop_event.wait()
        moteur.lignes.append(
            Ligne(
                "son d'attente",
                "play_hold_audio_loop",
                round(debut, 3),
                moteur.maintenant(),
            )
        )

    coordinateur = agent_transfer.AgentTransferCoordinator(moteur)
    moteur.transfer_coordinator = coordinateur
    horloge = SimpleNamespace(monotonic=boucle.time, time=time.time)
    with (
        patch.object(agent_transfer, "time", horloge),
        patch.object(agent_transfer, "play_hold_audio_loop", attente_sans_son),
        patch.object(
            agent_transfer, "build_handoff_snapshot", await _resume_au_banc(moteur)
        ),
    ):
        # Fin de parole de l'appelant : t = 0. Les passes de l'accueil jusqu'à l'appel de ``transfer_agent``.
        if delais.passe_note:
            moteur.passes.append("l'accueil note")
            await moteur._geste(
                "passe de l'accueil : il note",
                "cerveau de l'accueil",
                delais.passe_note,
            )
        moteur.passes.append("l'accueil passe la main (outil, annonce comprise)")
        moteur.mesure_passation.depart_de_requete(moteur.source.visit_id, boucle.time())
        await moteur._geste(
            "passe de l'accueil : appel de transfer_agent (l'annonce est le message de l'outil, sans passe)",
            "cerveau de l'accueil",
            delais.passe_decision,
        )
        demande = TransferRequest(
            destination_workflow_id=COLLEGUE,
            destination_label="Passer aux rendez-vous",
            origin_visit_id=moteur.source.visit_id,
            announcement=annonce,
        )
        demandee_a = moteur.maintenant()
        assert coordinateur.accept(demande)
        pret = asyncio.Event()
        pret.set()
        assert coordinateur.start(demande, context_ready=pret)
        await coordinateur._task
        await asyncio.wait_for(moteur.premier_son.wait(), 30)
    enregistrement = coordinateur.completed[-1]
    instants = {
        "demande": demandee_a,
        "premier_son_du_collegue": moteur.premier_son_a,
        "demande_vers_premier_son": round(moteur.premier_son_a - demandee_a, 3),
    }
    if annonce:
        debut, fin = moteur.instants_annonce
        instants.update(
            {
                "annonce_debut": debut,
                "annonce_fin": fin,
                "silence_apres_l_annonce": round(moteur.premier_son_a - fin, 3),
            }
        )
    return Resultat(
        passes=list(moteur.passes),
        lignes=sorted(moteur.lignes, key=lambda ligne: (ligne.debut, ligne.fin)),
        instants=instants,
        decoupe={
            k: v
            for k, v in enregistrement.items()
            if k not in ("request_id", "from_visit_id", "to_visit_id")
        },
        segments_de_voix=list(moteur.segments),
        issue=enregistrement["outcome"],
        ordre_de_la_voix=[qui for qui, _d, _f in moteur.segments],
    )


def jouer(
    delais: Delais | None = None,
    *,
    reserve: bool = True,
    mcp: bool = True,
    groupe: bool = True,
    annonce: str | None = ANNONCE,
    mcp_au_decroche: bool = False,
) -> Resultat:
    """Un jeu du banc, sur une boucle virtuelle neuve (déterministe)."""
    boucle = BoucleVirtuelle()
    try:
        return boucle.run_until_complete(
            _jouer(
                delais or Delais(),
                reserve=reserve,
                mcp=mcp,
                groupe=groupe,
                annonce=annonce,
                mcp_au_decroche=mcp_au_decroche,
            )
        )
    finally:
        boucle.close()


def tableau(resultat: Resultat) -> str:
    """Le journal en tableau Markdown (pour la fiche d'état)."""
    lignes = [
        "| Début (s) | Fin (s) | Durée (s) | Geste | Code | Refait à chaque passation | Au décroché possible |",
        "|---|---|---|---|---|---|---|",
    ]
    for ligne in resultat.lignes:
        lignes.append(
            f"| {ligne.debut:.2f} | {ligne.fin:.2f} | {ligne.duree:.2f} | {ligne.geste} | `{ligne.code}` | "
            f"{'oui' if ligne.a_chaque_passation else 'non'} | {'oui' if ligne.au_decroche_possible else 'non'} |"
        )
    return "\n".join(lignes)
