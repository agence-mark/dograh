"""[.mark] Module Restauration, SA-32 lot 1 (W17) : le texte critique est DIT PAR LE CODE, jamais par le modèle.

Mécanisme commun, aucun mot de métier : un outil réglé « Dit par le code » (``restitution``) voit son texte envoyé directement à la
voix ; le modèle reçoit à la place la consigne de ne pas le redire.

| Test | Ce qu'il prouve |
|---|---|
| texte tel quel | le texte de l'outil arrive intact à la voix (``queue_speech``), coupable par l'appelant, dans l'historique et le journal |
| le modèle | le résultat rendu au modèle ne porte ni ``suggestion`` ni ``texte_a_dire`` (ni dans ``data``) et dit « déjà dit, ne le répète pas, ne le défends pas » |
| historique | par le VRAI processeur du clavier : le texte entre dans le contexte comme une réplique de l'agent et dans les sorties affichées |
| échec | un outil en échec n'est jamais « dit par le code » : rien n'est envoyé à la voix |
| pas de voix | voix absente ou refusée : le texte reste au modèle, mot pour mot (jamais perdu) |
| enveloppe | par le VRAI chemin des outils d'un agent : le journal des actions lit le résultat entier, le modèle reçoit le résultat sans le texte |
| défaut des outils internes | relecture et confirmation de la commande et de la réservation : « dit par le code » ; les autres retours : rien |
| schémas | le réglage accepte la nouvelle valeur |
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from api.schemas.tool import ComportementOutil, IntegrationToolConfig
from api.services.commande.resultat import Resultat
from api.services.outils_mark.pour_la_voix import avec_restitution, dire_par_le_code
from api.services.reservation import action as action_reservation
from api.services.workflow.enveloppe_des_actions import envelopper_l_action

RELECTURE = "Je récapitule : une pizza Regina Normale et deux Ice Tea ; à emporter. Le total est de seize euros quatre-vingt-dix. Est-ce bien ça ?"


class Lecture:
    def __init__(self, nom: str = "PENDING") -> None:
        self.outcome = SimpleNamespace(name=nom)


class Moteur:
    """Un moteur qui note ce qu'on envoie à la voix."""

    def __init__(self, issue: str = "PENDING") -> None:
        self.dites: list[tuple[str, dict[str, Any]]] = []
        self.coupures: list[tuple[str, Any]] = []
        self.issue = issue
        self.phrases = SimpleNamespace(coupures=SimpleNamespace(noter=lambda texte, mots, parole, historique=True: self.coupures.append((texte, parole))))
        self._gathered_context: dict[str, Any] = {}

    async def queue_speech(self, text=None, **options):
        self.dites.append((text, options))
        return Lecture(self.issue)


def _propose(**plus: Any) -> dict[str, Any]:
    return {"statut": "INCOMPLETE", "manque": "relecture", "faits": {"total": 1690}, "suggestion": RELECTURE, **plus}


def _dit_par_le_code(resultat: dict[str, Any]) -> dict[str, Any]:
    return avec_restitution(resultat, {"restitution": "dit_par_le_code"})


async def test_le_texte_arrive_tel_quel_a_la_voix_coupable_dans_l_historique_et_le_journal():
    moteur = Moteur()
    await dire_par_le_code(moteur, _dit_par_le_code(_propose()))
    assert len(moteur.dites) == 1
    texte, options = moteur.dites[0]
    assert texte == RELECTURE
    assert options["append_to_context"] is True and options["persist_to_logs"] is True  # historique, transcription, journal de l'appel
    assert options["mute_user"] is False  # l'appelant peut couper, comme toute réplique
    assert [t for t, _ in moteur.coupures] == [RELECTURE]  # l'interruption se traite comme pour toute phrase du code


async def test_le_modele_ne_recoit_pas_le_texte_comme_un_texte_a_dire():
    moteur = Moteur()
    sortie = await dire_par_le_code(moteur, _dit_par_le_code(_propose()))
    assert "suggestion" not in sortie and "texte_a_dire" not in sortie
    assert RELECTURE not in repr(sortie)
    assert sortie["restitution"] == "dit_par_le_code" and sortie["deja_dit_par_le_code"] is True
    consigne = sortie["consigne_de_restitution"]
    assert "déjà été dit" in consigne and "mot pour mot" in consigne and "ne le répète pas" in consigne
    assert "ne le défends pas" in consigne and "rappelle-le" in consigne
    assert sortie["faits"] == {"total": 1690}  # l'état reste lisible par le modèle


async def test_la_suggestion_d_un_outil_http_dans_data_n_arrive_pas_non_plus_au_modele():
    moteur = Moteur()
    brut = _dit_par_le_code({"status": "success", "data": {"suggestion": RELECTURE, "autre": 1}})
    sortie = await dire_par_le_code(moteur, brut)
    assert moteur.dites[0][0] == RELECTURE
    assert sortie["data"] == {"autre": 1}


async def test_un_outil_en_echec_n_est_jamais_dit_par_le_code():
    moteur = Moteur()
    echec = {"status": "error", "error": "500", "suggestion": RELECTURE}
    assert _dit_par_le_code(echec) == echec  # le mode n'est même pas posé
    forcé = {**echec, "restitution": "dit_par_le_code", "texte_a_dire": RELECTURE}
    assert await dire_par_le_code(moteur, forcé) == forcé
    assert moteur.dites == []


@pytest.mark.parametrize("issue", ["SKIPPED", "FAILED", "CLOSED"])
async def test_sans_voix_le_texte_reste_au_modele_mot_pour_mot(issue):
    moteur = Moteur(issue)
    sortie = await dire_par_le_code(moteur, _dit_par_le_code(_propose()))
    assert sortie["restitution"] == "mot_pour_mot" and sortie["texte_a_dire"] == RELECTURE
    assert "deja_dit_par_le_code" not in sortie


async def test_une_voix_qui_leve_laisse_le_texte_au_modele():
    class Casse(Moteur):
        async def queue_speech(self, text=None, **options):
            raise RuntimeError("voix coupée")

    sortie = await dire_par_le_code(Casse(), _dit_par_le_code(_propose()))
    assert sortie["restitution"] == "mot_pour_mot" and sortie["texte_a_dire"] == RELECTURE


async def test_les_autres_modes_ne_disent_rien_par_le_code():
    moteur = Moteur()
    for mode in ("mot_pour_mot", "reformule"):
        brut = avec_restitution(_propose(), {"restitution": mode})
        assert await dire_par_le_code(moteur, brut) == brut
    assert await dire_par_le_code(moteur, _propose()) == _propose()
    assert moteur.dites == []


# --------------------------------------------------------------------------- #
# L'historique, par le VRAI processeur du clavier
# --------------------------------------------------------------------------- #


async def test_au_clavier_le_texte_est_une_replique_de_l_agent_dans_le_contexte():
    from pipecat.frames.frames import TTSSpeakFrame
    from pipecat.processors.frame_processor import FrameDirection

    from api.services.workflow.text_chat_runner import _ResponseWindowState, _TextChatCaptureProcessor

    messages: list[dict[str, Any]] = []
    contexte = SimpleNamespace(add_message=messages.append)

    class Lecteur:
        def __init__(self) -> None:
            self.speech_playback = SimpleNamespace(
                before_output=_rien, after_output=lambda *a, **k: None, note_output=lambda: None
            )

        async def should_mute_user(self, frame):
            return False

    async def _rien(*a, **k):
        return None

    fenetre = _ResponseWindowState()
    processeur = _TextChatCaptureProcessor(fenetre, contexte, Lecteur())

    async def sans_super(self, frame, direction):
        return None

    # la vraie méthode du processeur est appelée ; seule la plomberie du pipeline (``super().process_frame``) est neutralisée
    from pipecat.processors.frame_processor import FrameProcessor

    original = FrameProcessor.process_frame
    FrameProcessor.process_frame = sans_super  # type: ignore[assignment]
    try:
        await processeur.process_frame(TTSSpeakFrame(RELECTURE, append_to_context=True, persist_to_logs=True), FrameDirection.DOWNSTREAM)
    finally:
        FrameProcessor.process_frame = original  # type: ignore[assignment]
    assert messages == [{"role": "assistant", "content": RELECTURE}]
    assert fenetre.outputs == [RELECTURE]  # ce que le clavier affiche comme réponse de l'agent


# --------------------------------------------------------------------------- #
# Par le vrai chemin des outils d'un agent
# --------------------------------------------------------------------------- #


async def test_l_enveloppe_envoie_a_la_voix_et_rend_au_modele_le_resultat_sans_le_texte():
    moteur = Moteur()
    rendus: list[dict[str, Any]] = []

    async def rendre(resultat, **kwargs):
        rendus.append(resultat)

    async def action(params):
        await params.result_callback(_dit_par_le_code(_propose()))

    params = SimpleNamespace(result_callback=rendre, arguments={})
    await envelopper_l_action(moteur, "finaliser", action)(params)
    assert [t for t, _ in moteur.dites] == [RELECTURE]
    assert len(rendus) == 1 and RELECTURE not in repr(rendus[0]) and rendus[0]["deja_dit_par_le_code"] is True


async def test_l_enveloppe_ne_dit_rien_d_un_echec():
    moteur = Moteur()
    rendus: list[Any] = []

    async def rendre(resultat, **kwargs):
        rendus.append(resultat)

    async def action(params):
        await params.result_callback({"status": "error", "error": "boom", "restitution": "dit_par_le_code", "texte_a_dire": RELECTURE})

    await envelopper_l_action(moteur, "finaliser", action)(SimpleNamespace(result_callback=rendre, arguments={}))
    assert moteur.dites == [] and len(rendus) == 1


# --------------------------------------------------------------------------- #
# Le défaut des outils internes
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("geste", "resultat", "attendu"),
    [
        ("reserver", Resultat("INCOMPLETE", {"a_confirmer": True}, "Je vous réserve ... C'est bon ?", "relecture"), True),
        ("reserver", Resultat("ENREGISTREE", {"numero": "R1"}, "C'est noté pour vingt heures.", None), True),
        ("modifier_reservation", Resultat("INCOMPLETE", {"a_confirmer": True}, "Je change ... C'est bon ?", "relecture"), True),
        ("modifier_reservation", Resultat("OK", {}, "C'est modifié, à vingt heures trente.", None), True),
        ("annuler_reservation", Resultat("INCOMPLETE", {"a_confirmer": True}, "Vous voulez annuler ... ?", "confirmation"), True),
        ("annuler_reservation", Resultat("OK", {}, "C'est annulé.", None), True),
        ("reserver", Resultat("REFUSEE", {}, "Nous sommes complets.", None), False),
        ("reserver", Resultat("INCOMPLETE", {}, "Pour combien de personnes ?", "personnes"), False),
        ("disponibilites", Resultat("OK", {}, "Nous avons de la place à vingt heures.", None), False),
        ("retrouver_reservation", Resultat("OK", {}, "Votre réservation est confirmée.", None), False),
    ],
)
def test_le_defaut_de_la_reservation_est_dit_par_le_code_pour_la_relecture_et_la_confirmation(geste, resultat, attendu):
    retour = action_reservation._retour(resultat, geste)
    assert (retour.get("_restitution") == "dit_par_le_code") is attendu




def test_les_schemas_acceptent_la_nouvelle_valeur():
    assert ComportementOutil(restitution="dit_par_le_code").restitution == "dit_par_le_code"
    assert IntegrationToolConfig(connecteur="commande", action="finaliser", restitution="dit_par_le_code").restitution == "dit_par_le_code"
