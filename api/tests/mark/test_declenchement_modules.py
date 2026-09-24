"""[.mark] Lot 2 de « la fiche au fil de l'eau » : le déclenchement des modules, découplé (D9).

Plan : `Labo-agent-vocal/plans/2026-09-23-plan-fiche-au-fil-de-leau.md`.

| Test | Ce qu'il prouve |
|---|---|
| T2.1 | Interrupteur éteint : le déclenchement est IDENTIQUE à aujourd'hui, étape par étape |
| T2.2 | Interrupteur allumé : il suit la fiche de l'agent, quelles que soient les variables de l'étape |
| T2.3 | Le corpus des communes rend zéro perte (filet permanent : `test_corpus_communes_zero_perte.py`, rejoué tel quel) |

⛔ Ce lot est le préalable du lot 4 : sans lui, déclarer la fiche au niveau de l'agent
éteindrait les modules (leurs déclencheurs lisent les variables des étapes).

Le cas réel : run 799, l'adresse dite en pleine étape « panne », jamais vérifiée.
"""

from types import SimpleNamespace

import pytest
from pipecat.frames.frames import LLMContextFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pydantic import ValidationError

from api.schemas.organization_preferences import AdresseEtablissement
from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.pipecat.lecture_appelant import (
    VARIABLES_REFERENCE_PAR_DEFAUT,
    champs_de_la_fiche,
    creer_lecture_appelant,
    etape_reference,
    etape_vue_par_la_fiche,
    lire_message_tape,
    lire_texte,
    variables_reference,
)
from api.services.pipecat.verification_communes import (
    CLE_TRACE,
    VARIABLES_PAR_DEFAUT,
    etape_concernee,
)
from pipecat.tests import run_test

MAGASIN = AdresseEtablissement(
    code_postal="60740", code_insee="60589", commune="Saint-Maximin"
)
STT_FRANCAIS = SimpleNamespace(language="fr", language_hints=None)
DEMARRAGE_S = 15


def _etape(nom: str, *variables: str):
    return SimpleNamespace(
        name=nom, extraction_variables=[SimpleNamespace(name=v) for v in variables]
    )


# Les étapes de l'agent n° 20, à peu près : de quoi couvrir chaque forme de nom.
ETAPES = [
    _etape("accueil", "motif"),
    _etape("panne", "symptome", "marque_appareil"),
    _etape("adresse", "adresse_intervention", "commune", "code_postal"),
    _etape("chantier", "commune_chantier"),
    _etape("facture", "reference_facture", "montant"),
    _etape("suivi", "Reference_Commande "),
    _etape("ref courte", "ref", "numero_reference"),
    _etape("vide"),
    SimpleNamespace(name="sans variables", extraction_variables=None),
]


def _ancienne_regle_reference(noeud) -> bool:
    """La règle écrite dans le code jusqu'au lot 2, recopiée pour la comparaison."""
    for variable in getattr(noeud, "extraction_variables", None) or []:
        if (
            (getattr(variable, "name", None) or "")
            .strip()
            .lower()
            .startswith("reference")
        ):
            return True
    return False


class Registre:
    def __init__(self):
        self.entrees: dict[str, list] = {}

    def __call__(self, entree: dict, cle: str) -> None:
        self.entrees.setdefault(cle, []).append(entree)

    def lire(self, cle: str) -> list:
        return self.entrees.get(cle, [])


FICHE_ALLUMEE = {
    "verification_communes": True,
    "fiche_au_fil_de_leau": True,
    "fiche_champs": [
        {"nom": "commune"},
        {"nom": "adresse_intervention"},
        {"nom": "reference_facture"},
        {"nom": "motif", "origine": "deduit"},
    ],
}
FICHE_ETEINTE = {**FICHE_ALLUMEE, "fiche_au_fil_de_leau": False}
PHRASE_COMMUNE = "c'est à Creil 60100"


# --- T2.1 : éteint, identique à aujourd'hui ----------------------------------


@pytest.mark.parametrize("etape", ETAPES, ids=lambda e: e.name)
def test_T2_1_reference_par_defaut_identique_a_l_ancienne_regle(etape):
    assert etape_reference(etape) == _ancienne_regle_reference(etape)
    assert etape_reference(
        etape, variables_reference(None)
    ) == _ancienne_regle_reference(etape)


@pytest.mark.parametrize("etape", ETAPES, ids=lambda e: e.name)
def test_T2_1_eteint_l_etape_n_est_pas_remplacee(etape):
    assert etape_vue_par_la_fiche(etape, None) is etape
    assert champs_de_la_fiche(FICHE_ETEINTE) is None
    assert champs_de_la_fiche({}) is None


@pytest.mark.asyncio
async def test_T2_1_eteint_la_commune_n_est_lue_qu_a_l_etape_adresse():
    for etape, attendu in [(ETAPES[0], False), (ETAPES[2], True)]:
        registre = Registre()
        await lire_message_tape(
            PHRASE_COMMUNE, FICHE_ETEINTE, STT_FRANCAIS, MAGASIN, etape, registre
        )
        assert bool(registre.lire(CLE_TRACE)) is attendu, etape.name


def test_reglage_reference_vide_ou_invalide():
    assert (
        variables_reference({"variables_reference": ""})
        == VARIABLES_REFERENCE_PAR_DEFAUT
    )
    # Un réglage illisible (posé à la main en base) : le défaut, et l'appel continue.
    assert (
        variables_reference({"variables_reference": "a*"})
        == VARIABLES_REFERENCE_PAR_DEFAUT
    )
    assert variables_reference({"variables_reference": "numero_dossier, ref_*"}) == (
        "numero_dossier",
        "ref_*",
    )
    with pytest.raises(ValidationError):
        WorkflowConfigurationDefaults.model_validate({"variables_reference": "a*"})


# --- T2.2 : allumé, le déclenchement suit la fiche ---------------------------


@pytest.mark.parametrize("etape", ETAPES, ids=lambda e: e.name)
def test_T2_2_allume_les_declencheurs_suivent_la_fiche(etape):
    vue = etape_vue_par_la_fiche(etape, champs_de_la_fiche(FICHE_ALLUMEE))
    assert etape_concernee(vue, VARIABLES_PAR_DEFAUT) is True
    assert etape_reference(vue) is True
    assert vue.name == etape.name  # les traces gardent le nom de la vraie étape


def test_T2_2_allume_sans_champ_commune_la_commune_ne_se_declenche_nulle_part():
    vue = etape_vue_par_la_fiche(ETAPES[2], ("nom", "motif"))
    assert etape_concernee(vue, VARIABLES_PAR_DEFAUT) is False
    assert etape_reference(vue) is False


@pytest.mark.asyncio
async def test_T2_2_run_799_la_commune_dite_en_pleine_panne_est_lue():
    """Par la vraie route du clavier du labo (R5) : réglages -> fiche -> déclencheur."""
    registre = Registre()
    await lire_message_tape(
        PHRASE_COMMUNE, FICHE_ALLUMEE, STT_FRANCAIS, MAGASIN, ETAPES[1], registre
    )
    traces = registre.lire(CLE_TRACE)
    assert traces and traces[0]["etape"] == "panne"


@pytest.mark.asyncio
async def test_T2_2_par_le_processeur_monte_depuis_les_reglages():
    """La route de l'appel : `creer_lecture_appelant` lit la fiche dans les réglages."""
    registre = Registre()
    processeur = creer_lecture_appelant(
        FICHE_ALLUMEE, STT_FRANCAIS, MAGASIN, lambda: ETAPES[1], registre
    )
    contexte = LLMContext(messages=[{"role": "user", "content": PHRASE_COMMUNE}])
    await run_test(
        processeur,
        frames_to_send=[LLMContextFrame(context=contexte)],
        start_timeout=DEMARRAGE_S,
    )
    assert registre.lire(CLE_TRACE)


@pytest.mark.asyncio
async def test_T2_2_eteint_par_le_processeur_rien_en_pleine_panne():
    registre = Registre()
    processeur = creer_lecture_appelant(
        FICHE_ETEINTE, STT_FRANCAIS, MAGASIN, lambda: ETAPES[1], registre
    )
    contexte = LLMContext(messages=[{"role": "user", "content": PHRASE_COMMUNE}])
    await run_test(
        processeur,
        frames_to_send=[LLMContextFrame(context=contexte)],
        start_timeout=DEMARRAGE_S,
    )
    assert not registre.lire(CLE_TRACE)


@pytest.mark.asyncio
async def test_lire_texte_sans_fiche_rend_la_meme_chose():
    for etape in ETAPES:
        sans = await lire_texte(
            PHRASE_COMMUNE,
            conversion=True,
            verification=True,
            langue_francaise=True,
            adresse=MAGASIN,
            noeud=etape,
            consigner=None,
        )
        avec_none = await lire_texte(
            PHRASE_COMMUNE,
            conversion=True,
            verification=True,
            langue_francaise=True,
            adresse=MAGASIN,
            noeud=etape,
            consigner=None,
            champs_fiche=None,
        )
        assert sans == avec_none, etape.name
