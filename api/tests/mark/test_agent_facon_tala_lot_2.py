"""[.mark] agent-facon-tala, lot 2 (C8) : la fiche et les lectures sûres des modules, vues du cerveau d'un collègue.

Constat du lot 0 : dans les relevés de production (runs 2447, 2468) une requête sur vingt portait « [Fiche de l'appel… »,
contre quatorze sur quatorze dans l'agent unique. Cause trouvée : ce n'est pas le cerveau qui ne recevait pas la fiche, c'est
la TRACE qui ne la voyait pas. Au téléphone un agent appelé par passation est construit et tracé (``agent_runtime_factory``),
PUIS reçoit la fiche (``_porter_la_fiche``) : l'enveloppe de la trace se retrouvait SOUS celle de la fiche et photographiait la
requête avant l'état. Le premier agent (tracé après l'engin) et le clavier (un engin neuf par tour, fiche puis trace) n'avaient
pas ce défaut, d'où l'écart « groupe contre agent unique ». ``remettre_la_trace_en_dernier`` rend à la trace sa place.

| Test | Ce qu'il prouve |
|---|---|
| passation puis trois tours | la fiche et la lecture sûre des modules sont dans CHAQUE requête du collègue (vrai constructeur de requête) |
| trace, ordre du téléphone | trace posée avant la fiche : elle voit quand même l'état (et sans le correctif, elle ne le voit pas : cas rouge connu) |
| trace, ordre du clavier | fiche puis trace : inchangé |
| une seule photographie | la requête est tracée une fois, jamais deux, même avec les enveloppes posées plus tard |
| forme courte | case `fiche_forme_courte` : en-têtes réduits, lignes de données intactes ; éteinte, le bloc d'avant à l'octet |
"""

from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from api.services.pipecat import trace_modele
from api.services.pipecat.texte_du_cerveau import DEBUT_ENTETE_FICHE
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_FICHE_FORME_COURTE,
    CLE_INDICES_DES_MODULES,
    CLE_MODE,
    ENTETE_ETAT_COURT,
    ENTETE_ETAT_GREFFIER,
    MODE_GREFFIER,
    ReglagesFiche,
    en_forme_courte,
    montrer_la_fiche,
)
from api.services.workflow.indices_des_modules import ENTETE_INDICES_GREFFIER
from api.tests.mark.test_clavier_porte_la_fiche import FICHE
from api.tests.mark.test_indices_en_greffier import FICHE_DU_TOUR, PAROLE

GREFFIER_AVEC_INDICES = {**FICHE, CLE_MODE: MODE_GREFFIER, CLE_INDICES_DES_MODULES: True}
LA_FICHE = {**FICHE_DU_TOUR, "nom": "Lemaire"}


class _Modele:
    """Un cerveau minimal : la requête de conversation et ce que la trace en photographie."""

    mark_trace = None

    def __init__(self):
        self.envoye = None
        self.photographie: list = []

    def build_chat_completion_params(self, params):
        return dict(params)

    def _mark_tracer_parametres(self, params):
        self.photographie.append(copy.deepcopy(params))  # comme ``_en_clair`` : une copie prise à cet instant
        return params

    async def get_chat_completions(self, context):
        self.envoye = self.build_chat_completion_params({"messages": [{"role": "user", "content": PAROLE}]})
        return self.envoye


def _texte(params) -> str:
    return "\n".join(m["content"] for m in params["messages"])


def _tracer(modele):
    """La trace de l'appel, posée par le vrai ``brancher_la_trace`` (case allumée)."""
    moteur = SimpleNamespace(reglages_appel={trace_modele.CLE_TRACE_REQUETES: True}, _gathered_context={})
    assert trace_modele.brancher_la_trace(moteur, modele, {}, "collegue") is not None
    return modele


def _porter_la_fiche(modele, configuration=GREFFIER_AVEC_INDICES, forme_courte=None):
    assert montrer_la_fiche(
        modele,
        ReglagesFiche.depuis(configuration),
        lambda: LA_FICHE,
        forme_courte=forme_courte,
    )


@pytest.mark.asyncio
async def test_c8_apres_une_passation_la_fiche_et_la_lecture_sure_sont_dans_chaque_requete_du_collegue():
    accueil, collegue = _Modele(), _Modele()
    _porter_la_fiche(accueil)
    await accueil.get_chat_completions(None)  # le tour de l'accueil, avant la passation
    _porter_la_fiche(collegue)  # ce que fait ``_porter_la_fiche`` du moteur au collègue appelé
    for _ in range(3):
        await collegue.get_chat_completions(None)
        texte = _texte(collegue.envoye)
        assert DEBUT_ENTETE_FICHE in texte and "Lemaire" in texte
        assert ENTETE_INDICES_GREFFIER in texte and "07 50" in texte.replace("/", " ")  # la lecture sûre du numéro


@pytest.mark.asyncio
async def test_c8_la_trace_posee_avant_la_fiche_ordre_du_telephone_voit_quand_meme_l_etat():
    collegue = _tracer(_Modele())  # construit et tracé par la fabrique d'agent…
    _porter_la_fiche(collegue)  # …puis la fiche lui est donnée
    await collegue.get_chat_completions(None)
    assert len(collegue.photographie) == 1
    assert DEBUT_ENTETE_FICHE in _texte(collegue.photographie[0])


@pytest.mark.asyncio
async def test_c8_cas_rouge_sans_le_correctif_la_trace_ne_voyait_pas_l_etat(monkeypatch):
    # R7 : l'outil de vérification s'éprouve sur le cas connu. Sans le rappel, la photographie est prise sous la fiche.
    monkeypatch.setattr(trace_modele, "remettre_la_trace_en_dernier", lambda llm: False)
    collegue = _tracer(_Modele())
    _porter_la_fiche(collegue)
    await collegue.get_chat_completions(None)
    assert len(collegue.photographie) == 1
    assert DEBUT_ENTETE_FICHE not in _texte(collegue.photographie[0])  # la requête, elle, la portait
    assert DEBUT_ENTETE_FICHE in _texte(collegue.envoye)


@pytest.mark.asyncio
async def test_c8_ordre_du_clavier_fiche_puis_trace_inchange():
    modele = _Modele()
    _porter_la_fiche(modele)
    _tracer(modele)
    await modele.get_chat_completions(None)
    assert len(modele.photographie) == 1 and DEBUT_ENTETE_FICHE in _texte(modele.photographie[0])


@pytest.mark.asyncio
async def test_c8_une_enveloppe_posee_plus_tard_ne_double_pas_la_photographie():
    from api.services.workflow.sortie_d_impasse import montrer_l_impasse

    modele = _tracer(_Modele())
    _porter_la_fiche(modele)
    assert montrer_l_impasse(SimpleNamespace(_gathered_context={}), modele)  # une enveloppe de plus, après la trace
    await modele.get_chat_completions(None)
    assert len(modele.photographie) == 1
    assert DEBUT_ENTETE_FICHE in _texte(modele.photographie[0])


@pytest.mark.asyncio
async def test_c8_forme_courte_en_tete_reduit_lignes_de_donnees_intactes():
    long = _Modele()
    _porter_la_fiche(long)
    await long.get_chat_completions(None)
    court = _Modele()
    _porter_la_fiche(court, forme_courte=lambda: True)
    await court.get_chat_completions(None)
    texte_long, texte_court = _texte(long.envoye), _texte(court.envoye)
    assert ENTETE_ETAT_GREFFIER in texte_long and ENTETE_INDICES_GREFFIER in texte_long
    assert ENTETE_ETAT_COURT in texte_court
    assert ENTETE_ETAT_GREFFIER not in texte_court and ENTETE_INDICES_GREFFIER not in texte_court
    assert "à ne pas redemander" not in texte_court and "fais alors choisir" not in texte_court
    # Les lignes de données sont exactement celles d'avant.
    donnees = lambda t: [ligne for ligne in t.splitlines() if ligne.startswith(("Noté", "À confirmer"))]  # noqa: E731
    assert donnees(texte_long) == donnees(texte_court) and donnees(texte_court)
    assert "07 50" in texte_court.replace("/", " ")


@pytest.mark.asyncio
async def test_c8_forme_courte_eteinte_le_bloc_est_celui_d_avant_a_l_octet():
    sans = _Modele()
    _porter_la_fiche(sans)
    await sans.get_chat_completions(None)
    eteinte = _Modele()
    _porter_la_fiche(eteinte, forme_courte=lambda: False)
    await eteinte.get_chat_completions(None)
    assert sans.envoye == eteinte.envoye
    assert en_forme_courte(None) is None and en_forme_courte("rien à réduire") == "rien à réduire"


def test_c8_la_case_est_eteinte_par_defaut_et_dans_les_reglages_d_agent():
    from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
    from api.services.groupe.reglages import CLES_THEME_DONNEES

    assert WorkflowConfigurationDefaults().fiche_forme_courte is False
    assert CLE_FICHE_FORME_COURTE in CLES_THEME_DONNEES


def test_c8_le_moteur_lit_la_case_de_l_agent_qui_parle():
    import inspect

    from api.services.workflow.pipecat_engine import PipecatEngine

    source = inspect.getsource(PipecatEngine._porter_la_fiche)
    assert "forme_courte=" in source and CLE_FICHE_FORME_COURTE in source
