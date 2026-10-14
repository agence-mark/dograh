"""[.mark] Le filet des répliques inachevées (chantier repliques-coupees, lot 4, D2 et D10 du 14/10).

Plan `Labo-agent-vocal/plans/repliques-coupees/`, cas rouges dans `corpus.md`. Un modèle peut finir
sa réponse en pleine phrase avec un arrêt normal (run 1185 : « Parfait. Vous êtes dans quelle
commune, et quel est le », Qwen3.8 27B en réflexion coupée) ; gardée dans l'historique, la réplique
coupée est imitée aux tours suivants. Chaque cas a été vu ROUGE avant d'être vert (R7).

| Test | Ce qu'il prouve |
|---|---|
| fins de phrase | ``.``, ``?``, ``!``, ``…``, guillemet ou parenthèse fermants ; un reste sans ponctuation n'est pas fini |
| cas 1176 tour 7 | « C'est noté. » dit, « Avez-vous une adresse mail pour que » retenu, tracé, le modèle reparle |
| réplique finie | passe à l'identique, rien de tracé, aucune relance |
| porte seule, nombre en fin de phrase | ni l'une ni l'autre n'est un reste |
| porte + reste | la porte relance le modèle dans l'étape d'arrivée |
| une fois par réplique | une seconde réponse inachevée au même tour : finie dite, rien d'autre |
| ordre des frames | une phrase finie part sans attendre la suite (aucune latence) |
| réflexion de secours (D10) | la relance seule part en ``low`` ; la requête suivante reprend ``none`` ; ``run_inference`` jamais |
| branchement | valeur absente ou inconnue, service Mistral : rien |
| clavier (R1) | par les vraies routes : la réplique coupée n'est ni affichée ni gardée dans l'historique, la relance l'est |
"""

import pytest
from pipecat.frames.frames import (
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    TTSSpeakFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.tests.utils import SleepFrame

from api.services.pipecat.lecteur_de_portes import LecteurDePortes
from api.services.pipecat.replique_inachevee import (
    ATTRIBUT_RELANCE,
    CLE_REFLEXION_DE_RELANCE,
    TRACE_INACHEVEES,
    brancher_la_relance,
    est_finie,
    fin_de_la_derniere_phrase,
)
from api.services.pipecat.service_factory import DograhMistralLLMService
from api.services.workflow.fiche_au_fil_de_leau import CLE_TOUR, ReglagesFiche
from api.tests.mark.test_clavier_porte_la_fiche import _monter
from api.tests.mark.test_porte_parlee_consigne import _definition
from api.tests.mark.test_porte_parlee_processeur import _Moteur, _Ordre
from api.tests.mark.test_post_scriptum import DEMARRAGE_S
from api.tests.mark.test_trace_modele import (
    GREFFIER_PORTES,
    _contexte,
    _morceau,
    _service,
    _un_tour,
)
from pipecat.tests import run_test


class _MoteurRelance(_Moteur):
    """Le témoin du moteur, avec la relance d'une réponse muette (garde du moteur : une fois)."""

    def __init__(self):
        super().__init__()
        self.relances = 0

    async def relancer_une_reponse_muette(self):
        self.relances += 1
        return True


class _Secours:
    """Le témoin du service qui porte la réflexion de secours."""

    mark_reflexion_de_relance = "low"

    def __init__(self):
        self.armee = 0
        self.desarmee = 0

    def armer_la_relance(self):
        self.armee += 1

    def desarmer_la_relance(self):
        self.desarmee += 1


def _lecteur(fiche: dict, moteur, secours=None) -> LecteurDePortes:
    lecteur = LecteurDePortes(
        reglages=ReglagesFiche.depuis(GREFFIER_PORTES),
        fiche=lambda: fiche,
        messages=list,
        attendu=lambda: True,
        portes=moteur,
    )
    lecteur._relance_de_secours = secours
    return lecteur


async def _reponse(lecteur, *frames) -> _Ordre:
    ordre = _Ordre()
    await run_test(
        Pipeline([lecteur, ordre]),
        frames_to_send=[*frames, SleepFrame(sleep=0.3)],
        start_timeout=DEMARRAGE_S,
    )
    return ordre


def _morceaux(*textes):
    return [LLMFullResponseStartFrame(), *[LLMTextFrame(t) for t in textes], LLMFullResponseEndFrame()]


# --------------------------------------------------------------------------- #
# 1. Ce qu'est une phrase finie
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "texte",
    [
        "C'est noté.",
        "Avez-vous une adresse mail pour que nous puissions vous écrire ?",
        "Très bien !",
        "Je vois…",
        "Il m'a dit « merci. »",
        "C'est noté (merci.)",
        "Je relis : zéro six, douze, quarante-cinq. C'est bien ça ?  \n",
    ],
)
def test_une_phrase_finie_est_finie(texte):
    assert est_finie(texte)


@pytest.mark.parametrize(
    "texte",
    [
        "C'est noté. Avez-vous une adresse mail pour que",
        "Parfait. Vous êtes dans quelle commune, et quel est le",
        "Pas de souci",
        "Est-ce qu'il y",
        "Je relis :",
        "",
    ],
)
def test_un_reste_sans_ponctuation_n_est_pas_fini(texte):
    assert not est_finie(texte)


@pytest.mark.parametrize(
    "texte",
    ["Je note jean.dupont@gmail.com", "Notre site est www.nuances-de-feu.fr", "Il fait 1.5 kilowatt"],
)
def test_un_point_dans_une_adresse_ou_un_nombre_n_est_pas_une_fin(texte):
    """Revue du 14/10, retenue par Evan : « com » n'est jamais jeté après « gmail. »."""
    assert fin_de_la_derniere_phrase(texte) == 0
    assert not est_finie(texte)
    assert est_finie(texte + ".")


def test_pendant_la_reponse_un_point_tout_au_bout_attend_la_suite():
    assert fin_de_la_derniere_phrase("Je note jean.dupont@gmail.", texte_complet=False) == 0
    assert fin_de_la_derniere_phrase("Parfait.", texte_complet=False) == 0
    assert fin_de_la_derniere_phrase("Parfait. ", texte_complet=False) == len("Parfait. ")
    assert fin_de_la_derniere_phrase("Parfait.") == len("Parfait.")


def test_la_coupe_tombe_apres_la_derniere_phrase_finie():
    texte = "C'est noté. Avez-vous une adresse mail pour que"
    assert texte[: fin_de_la_derniere_phrase(texte)] == "C'est noté. "
    assert fin_de_la_derniere_phrase("Pas de souci") == 0


# --------------------------------------------------------------------------- #
# 2. Le lecteur de portes
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_cas_1176_tour_7_le_reste_est_retenu_et_le_modele_reparle():
    fiche = {CLE_TOUR: 7}
    moteur, secours = _MoteurRelance(), _Secours()
    ordre = await _reponse(
        _lecteur(fiche, moteur, secours),
        *_morceaux("C'est noté.", " Avez-vous une adresse", " mail pour", " que"),
    )
    assert ordre.dit.strip() == "C'est noté."
    assert "pour que" not in ordre.dit
    assert fiche[TRACE_INACHEVEES] == [
        {
            "tour": 7,
            "reste": "Avez-vous une adresse mail pour que",
            "relance": True,
            "reflexion": "low",
        }
    ]
    assert moteur.relances == 1
    assert (secours.armee, secours.desarmee) == (1, 0)


@pytest.mark.asyncio
async def test_une_reponse_entierement_inachevee_ne_dit_rien_et_reparle():
    fiche = {CLE_TOUR: 8}
    moteur = _MoteurRelance()
    ordre = await _reponse(_lecteur(fiche, moteur), *_morceaux("Pas de", " souci"))
    assert ordre.dit == ""
    assert fiche[TRACE_INACHEVEES][0]["reste"] == "Pas de souci"
    assert "reflexion" not in fiche[TRACE_INACHEVEES][0]
    # Une seule relance : celle du filet, pas en plus celle de la réponse muette.
    assert moteur.relances == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "morceaux",
    [
        ["C'est noté.", " Avez-vous une adresse mail pour que", " nous puissions vous écrire ?"],
        ["Je relis : zéro six, douze, ", "quarante-cinq, soixante-dix-huit, quatre-vingt-dix.", " C'est bien ça ?"],
        ["Votre demande est bien enregistrée.", " Bonne journée."],
    ],
    ids=["1176-entiere", "numero-relu", "deux-phrases"],
)
async def test_une_reponse_finie_passe_a_l_identique(morceaux):
    fiche = {CLE_TOUR: 7}
    moteur = _MoteurRelance()
    ordre = await _reponse(_lecteur(fiche, moteur), *_morceaux(*morceaux))
    assert ordre.dit == "".join(morceaux)
    assert TRACE_INACHEVEES not in fiche
    assert moteur.relances == 0


@pytest.mark.asyncio
async def test_une_ligne_de_porte_seule_n_est_pas_un_reste():
    fiche = {CLE_TOUR: 3}
    moteur = _MoteurRelance()
    await _reponse(_lecteur(fiche, moteur), *_morceaux("→ vers_panne"))
    assert TRACE_INACHEVEES not in fiche
    assert [p["nom"] for p in moteur.prises] == ["vers_panne"]
    # Rien n'a été dit : la porte relance le modèle dans l'étape d'arrivée (comme avant).
    assert moteur.prises[0]["relancer"] is True
    assert moteur.relances == 0


@pytest.mark.asyncio
async def test_une_porte_avec_une_phrase_coupee_relance_dans_l_etape_d_arrivee():
    fiche = {CLE_TOUR: 9}
    moteur, secours = _MoteurRelance(), _Secours()
    ordre = await _reponse(
        _lecteur(fiche, moteur, secours),
        *_morceaux("→ vers_fin\nPas de souci.", " Est-ce qu'il y"),
    )
    assert ordre.dit.strip() == "Pas de souci."
    assert [p["nom"] for p in moteur.prises] == ["vers_fin"]
    # La phrase finie est partie, mais la réplique est inachevée : la porte relance.
    assert moteur.prises[0]["relancer"] is True
    assert moteur.relances == 0
    assert fiche[TRACE_INACHEVEES][0]["relance"] is True
    assert secours.armee == 1


@pytest.mark.asyncio
async def test_une_seule_relance_par_replique_de_l_appelant():
    fiche = {CLE_TOUR: 5}
    moteur, secours = _MoteurRelance(), _Secours()
    lecteur = _lecteur(fiche, moteur, secours)
    ordre = await _reponse(
        lecteur,
        *_morceaux("Parfait. Vous êtes dans quelle commune, et quel est le"),
        *_morceaux("Parfait. Vous êtes dans quelle"),
    )
    # Le premier reste est retenu ; à la deuxième coupure (revue du 14/10, retenue par Evan),
    # le reste est dit plutôt qu'un silence jusqu'à ce que la personne reparle.
    assert ordre.dit.replace(" ", "") == "Parfait.Parfait.Vousêtesdansquelle"
    assert moteur.relances == 1
    assert [t["relance"] for t in fiche[TRACE_INACHEVEES]] == [True, False]
    assert fiche[TRACE_INACHEVEES][1]["dit"] is True
    assert secours.armee == 1


@pytest.mark.asyncio
async def test_une_adresse_coupee_entre_deux_morceaux_est_dite_entiere():
    """Le point de « gmail. » arrive en bout de morceau : il n'est pas une fin de phrase."""
    fiche = {CLE_TOUR: 3}
    moteur = _MoteurRelance()
    ordre = await _reponse(
        _lecteur(fiche, moteur),
        *_morceaux("Je relis : jean.dupont@gmail.", "com. C'est bien ça ?"),
    )
    assert ordre.dit.replace("  ", " ").strip() == "Je relis : jean.dupont@gmail.com. C'est bien ça ?"
    assert TRACE_INACHEVEES not in fiche
    assert moteur.relances == 0


@pytest.mark.asyncio
async def test_une_phrase_finie_part_sans_attendre_la_suite():
    """Latence : la voix reçoit « C'est noté. » avant que la suite de la réponse arrive."""
    fiche = {CLE_TOUR: 7}
    ordre = await _reponse(
        _lecteur(fiche, _MoteurRelance()),
        LLMFullResponseStartFrame(),
        LLMTextFrame("C'est noté. Avez-vous"),
        # Une phrase figée traverse le lecteur intacte : elle marque l'instant.
        TTSSpeakFrame("REPERE"),
        LLMTextFrame(" une adresse mail ?"),
        LLMFullResponseEndFrame(),
    )
    genres = [(g, t.strip()) for g, t in ordre.suite]
    assert genres.index(("dite", "C'est noté.")) < genres.index(("figee", "REPERE"))
    assert ordre.dit.replace("  ", " ").strip() == "C'est noté. Avez-vous une adresse mail ?"


# --------------------------------------------------------------------------- #
# 3. La réflexion de secours (D10)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_seule_la_relance_part_avec_la_reflexion_de_secours():
    service, envoyes = _service(reasoning_effort="none")
    moteur = SimpleMoteur()
    brancher_la_relance(moteur, service, {CLE_REFLEXION_DE_RELANCE: "low"})
    assert getattr(moteur, ATTRIBUT_RELANCE) is service

    await service.get_chat_completions(_contexte())
    service.armer_la_relance()
    await service.get_chat_completions(_contexte())
    await service.get_chat_completions(_contexte())
    assert [e.get("reasoning_effort") for e in envoyes] == ["none", "low", "none"]


@pytest.mark.asyncio
async def test_un_appel_ponctuel_n_emporte_jamais_la_relance():
    service, envoyes = _service(reasoning_effort="none")
    brancher_la_relance(SimpleMoteur(), service, {CLE_REFLEXION_DE_RELANCE: "low"})
    service.armer_la_relance()

    async def create(**params):
        envoyes.append(params)
        from types import SimpleNamespace

        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="oui"))])

    service._client.chat.completions.create = create
    await service.run_inference(_contexte())
    assert envoyes[-1].get("reasoning_effort") == "none"


def test_sans_reflexion_de_secours_rien_n_est_branche():
    service, _ = _service(reasoning_effort="none")
    moteur = SimpleMoteur()
    brancher_la_relance(moteur, service, {})
    brancher_la_relance(moteur, service, {CLE_REFLEXION_DE_RELANCE: "beaucoup"})
    assert service.mark_reflexion_de_relance is None
    assert not hasattr(moteur, ATTRIBUT_RELANCE)
    service.armer_la_relance()
    assert service._mark_relance_armee is False
    mistral = DograhMistralLLMService(api_key="cle-de-test", model="mistral-large-2512")
    brancher_la_relance(moteur, mistral, {CLE_REFLEXION_DE_RELANCE: "low"})
    assert not hasattr(moteur, ATTRIBUT_RELANCE)


class SimpleMoteur:
    pass


# --------------------------------------------------------------------------- #
# 4. Au clavier, par les vraies routes (R1)
# --------------------------------------------------------------------------- #


def _texte(texte: str, *, arret: str | None = "stop"):
    return [_morceau(texte), _morceau(None, arret=arret)]


@pytest.mark.asyncio
async def test_au_clavier_la_replique_coupee_n_est_ni_affichee_ni_gardee(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(db_session, async_session, GREFFIER_PORTES, _definition())
    charge = await _un_tour(
        test_client_factory,
        user,
        workflow,
        [
            _texte("C'est noté. Avez-vous une adresse mail pour que"),
            _texte("Avez-vous une adresse mail pour que nous puissions vous écrire ?"),
        ],
    )
    affiche = repr([(t.get("assistant_message") or {}).get("text") for t in charge["session_data"]["turns"]])
    assert "pour que'" not in affiche and "pour que\"" not in affiche, affiche
    assert "nous puissions vous écrire ?" in affiche, affiche
    point = charge["checkpoint"]
    gardes = " ".join(
        str(m.get("content")) for m in point["messages"] if m.get("role") == "assistant"
    )
    assert "pour que nous" in gardes, gardes
    assert "mail pour que\n" not in gardes and not gardes.rstrip().endswith("pour que"), gardes
    assert point["gathered_context"][TRACE_INACHEVEES][0]["relance"] is True
