"""[.mark] Une action trouve-t-elle les champs qu'elle lit, même quand la fiche a un tour de retard ?

La question de ce fichier, et elle seule :

    En mode greffier, quand une action a besoin d'un champ que la personne vient de dire,
    le code le trouve-t-il dans les traces des modules (sûres, au tour même), puis en
    attendant le greffier (borné), et dit-il au modèle ce qui manque encore -- avec la
    phrase de patience dite seulement au-delà du seuil ; le balayage de fin d'appel lit-il
    ces traces ; et une valeur de liste fermée n'est-elle plus prise pour une recopie (B2) ?

Pourquoi il existe
------------------
Chantier ``agent-leger-greffier``, lot D (schéma du lot A, cas 3 ; D6). Preuve sur une fiche
d'un AUTRE métier (un garage), par simple réglage : aucun nom de champ dans le code.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.services.fiche.traces import valeurs_des_traces
from api.services.integrations.connectors.champs_requis import Patience, resoudre
from api.services.integrations.connectors.execution import contexte_de
from api.services.workflow.fiche_au_fil_de_leau import (
    ReglagesFiche,
    _recopie_d_un_autre_champ,
    balayer_la_fiche,
)

CHAMPS = [
    {"nom": "nom_client", "type": "string", "origine": "dicte", "description": "Nom."},
    {
        "nom": "tel_client",
        "type": "string",
        "origine": "dicte",
        "description": "Téléphone.",
    },
    {
        "nom": "commune_garage",
        "type": "string",
        "origine": "dicte",
        "description": "Commune.",
    },
    {
        "nom": "cp_garage",
        "type": "string",
        "origine": "dicte",
        "description": "Code postal.",
    },
    {"nom": "motif", "type": "string", "origine": "deduit", "description": "Motif."},
    {
        "nom": "prestation",
        "type": "string",
        "origine": "deduit",
        "description": "Prestation.",
        "valeurs": ["vidange", "freins", "pneus"],
    },
]
RUN_CONFIGS = {
    "fiche_au_fil_de_leau": True,
    "fiche_champs": CHAMPS,
    "fiche_mode_de_note": "greffier",
}
TRACES = {
    "communes_verifiees": [
        {"statut": "a_confirmer", "commune_retenue": None, "entendu": "vidange"},
        {
            "statut": "sure",
            "entendu": "compiegne",
            "commune_retenue": {
                "nom": "Compiègne",
                "code_insee": "60159",
                "codes_postaux": ["60200"],
            },
        },
    ],
    "nombres_lus": [
        {"type": "code_postal", "statut": "sure", "retenu": "60200", "ecrit": "60200"},
        {"type": "telephone", "statut": None, "ecrit": "06 11 22 33 44"},
    ],
    "epellations_lues": [{"entendu": "M A R T I N", "epele": "Martin", "tour": 3}],
    "tour_appelant": 3,
}


def _reglages():
    return ReglagesFiche.depuis(RUN_CONFIGS)


def _moteur(fiche, greffier=None):
    return SimpleNamespace(
        _gathered_context=fiche,
        fiche=_reglages(),
        greffier=greffier,
        queue_text_message=AsyncMock(),
    )


def test_les_traces_donnent_les_valeurs_sures_par_les_reglages_de_l_agent():
    valeurs = valeurs_des_traces(_reglages(), dict(TRACES))
    assert valeurs == {
        "nom_client": "Martin",
        "tel_client": "0611223344",
        "commune_garage": "Compiègne",
        "cp_garage": "60200",
    }
    # Une commune « à confirmer » n'est jamais prise.
    seule = {"communes_verifiees": [TRACES["communes_verifiees"][0]]}
    assert "commune_garage" not in valeurs_des_traces(_reglages(), seule)


def test_une_epellation_seulement_au_tour_meme_et_pour_un_seul_champ_de_nom():
    """Revue du 10/10 : « D U P O N T » remplissait le nom ET le prénom, et une épellation
    d'il y a trois tours (une rue, une adresse électronique) partait dans le nom."""
    plus_tard = dict(TRACES, tour_appelant=6)
    assert "nom_client" not in valeurs_des_traces(_reglages(), plus_tard)
    deux_noms = ReglagesFiche.depuis(
        dict(
            RUN_CONFIGS,
            fiche_champs=CHAMPS
            + [
                {
                    "nom": "prenom_client",
                    "type": "string",
                    "origine": "dicte",
                    "description": "Prénom.",
                }
            ],
        )
    )
    valeurs = valeurs_des_traces(deux_noms, dict(TRACES))
    assert "nom_client" not in valeurs and "prenom_client" not in valeurs


async def test_l_action_prend_les_traces_sans_attendre_le_greffier():
    greffier = SimpleNamespace(rattraper=AsyncMock(return_value=True))
    fiche = dict(TRACES)
    complements, manquants = await resoudre(
        _moteur(fiche, greffier), {"champs_requis": ["commune_garage", "cp_garage"]}
    )
    assert complements == {"commune_garage": "Compiègne", "cp_garage": "60200"}
    assert manquants == []
    greffier.rattraper.assert_not_awaited()
    # La fiche n'est pas écrite : le greffier l'écrira, avec ses contrôles.
    assert "commune_garage" not in fiche


def test_l_action_lit_les_complements_sans_que_la_fiche_change():
    action = SimpleNamespace(reglages_par_defaut={})
    fiche = {"extracted_variables": {"nom": "Martin"}}
    ctx = contexte_de(
        action,
        None,
        fiche,
        complements={"commune": "Compiègne", "code_postal": "60200"},
    )
    assert (ctx.modele.adresse.commune, ctx.modele.adresse.code_postal) == (
        "Compiègne",
        "60200",
    )
    assert ctx.modele.contact.nom == "Martin"
    assert fiche == {"extracted_variables": {"nom": "Martin"}}


def test_une_commune_sure_a_code_postal_unique_donne_le_code_postal():
    seule = {"communes_verifiees": TRACES["communes_verifiees"]}
    assert valeurs_des_traces(_reglages(), seule)["cp_garage"] == "60200"


async def test_un_champ_absent_des_traces_attend_le_greffier_puis_manque():
    fiche: dict = {}

    async def rattraper(delai):
        fiche["motif"] = "vidange de la voiture"
        return True

    greffier = SimpleNamespace(rattraper=AsyncMock(side_effect=rattraper))
    complements, manquants = await resoudre(
        _moteur(fiche, greffier),
        {"champs_requis": ["motif", "prestation"], "attente_max_ms": 800},
    )
    greffier.rattraper.assert_awaited_once_with(0.8)
    assert complements == {} and manquants == ["prestation"]


async def test_sans_champ_requis_l_outil_se_joue_comme_avant():
    greffier = SimpleNamespace(rattraper=AsyncMock())
    assert await resoudre(_moteur({}, greffier), {}) == ({}, [])
    greffier.rattraper.assert_not_awaited()


async def test_la_patience_n_est_dite_qu_au_dela_du_seuil_et_une_fois():
    moteur = _moteur({})
    rapide = Patience(
        moteur, {"phrase_attente": "Un instant.", "seuil_patience_ms": 200}
    )
    rapide.demarrer()
    await asyncio.sleep(0.05)
    rapide.arreter()
    await asyncio.sleep(0.25)
    moteur.queue_text_message.assert_not_awaited()

    lente = Patience(moteur, {"phrase_attente": "Un instant.", "seuil_patience_ms": 50})
    lente.demarrer()
    await asyncio.sleep(0.15)
    lente.arreter()
    moteur.queue_text_message.assert_awaited_once_with("Un instant.", mute_user=True)

    vide = Patience(moteur, {"phrase_attente": "", "seuil_patience_ms": 0})
    vide.demarrer()
    await asyncio.sleep(0.05)
    assert moteur.queue_text_message.await_count == 1


async def test_le_balayage_ecrit_les_traces_d_abord_sans_les_demander_au_modele():
    fiche = dict(TRACES)
    demandes = []

    async def extraire(variables, consigne):
        demandes.extend(v.name for v in variables)
        return {}

    messages = [
        {
            "role": "user",
            "content": "Martin, M A R T I N, à Compiègne 60200, 06 11 22 33 44",
        }
    ]
    ecrits = await balayer_la_fiche(_reglages(), extraire, fiche, messages)
    assert ecrits["commune_garage"] == "Compiègne"
    assert ecrits["cp_garage"] == "60200"
    assert "commune_garage" not in demandes and "cp_garage" not in demandes
    assert any(e.get("source") == "traces" for e in fiche["fiche_journal"])


@pytest.mark.parametrize("valeur", ["vidange", "Vidange"])
def test_b2_une_valeur_de_la_liste_fermee_n_est_jamais_une_recopie(valeur):
    fiche = {"motif": "vidange"}
    assert _recopie_d_un_autre_champ(_reglages(), fiche, "prestation", valeur) is None
    # Un champ libre garde la garde.
    assert (
        _recopie_d_un_autre_champ(
            _reglages(), {"prestation": "vidange"}, "motif", "vidange"
        )
        == "prestation"
    )


def test_le_compteur_des_tours_est_celui_des_modules():
    from api.services.fiche import traces
    from api.services.pipecat.verification_communes import CLE_TOUR

    assert traces.CLE_TOUR == CLE_TOUR
