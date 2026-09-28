"""[.mark] Chantier correctifs-modules, lot 4 : la passe de fin d'appel (D9).

Plan : ``Labo-agent-vocal/plans/correctifs-modules/2026-09-28-plan-correctifs-modules.md``.
La passe passe par le point d'écriture unique (``ecrire_dans_la_fiche``), la route de
``noter_information`` : ces tests appellent ``balayer_la_fiche`` telle quelle, seule
l'extraction du modèle est remplacée.

| Test | Preuve (runs) |
|---|---|
| une valeur déjà notée dans un autre champ n'est jamais recopiée | 864, 870, 879, 880, 881 |
| un champ lu par le lexique ne reçoit qu'un terme du lexique | 865 |
| un champ de commune ne reçoit qu'une commune reconnue | 880 |
| la passe reçoit les valeurs des listes fermées | 866 |
| ce qui passait passe encore | — |
"""

import pytest

from api.schemas.lexique_metier import LexiqueMetier
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_JOURNAL,
    CLE_TOUR,
    ReglagesFiche,
    balayer_la_fiche,
)

LEXIQUE = LexiqueMetier.model_validate({"termes": [{"terme": "Edilkamin", "type": "nom"}]})
CHAMPS = [
    {"nom": "reference_facture", "origine": "dicte"},
    {"nom": "reference_commande", "origine": "dicte"},
    {"nom": "marque", "origine": "dicte", "lecteur": "lexique"},
    {"nom": "commune", "origine": "dicte"},
    {"nom": "code_postal", "origine": "dicte"},
    {"nom": "urgence", "origine": "deduit", "valeurs": ["faible", "forte"]},
]
CREIL = {"nom": "Creil", "code_insee": "60175", "departement": "Oise", "codes_postaux": ["60100"]}


def _reglages() -> ReglagesFiche:
    return ReglagesFiche.depuis({"fiche_au_fil_de_leau": True, "fiche_champs": CHAMPS}, lexique=LEXIQUE)


class Extracteur:
    def __init__(self, reponse: dict):
        self.reponse = reponse
        self.variables = []

    async def __call__(self, variables, consigne):
        self.variables = list(variables)
        return dict(self.reponse)


def _messages(*paroles: str) -> list[dict]:
    return [{"role": "user", "content": p} for p in paroles]


def _refus(fiche: dict, champ: str) -> str | None:
    return next(
        (e["raison"] for e in fiche.get(CLE_JOURNAL) or [] if e["champ"] == champ and e["statut"] == "refuse"),
        None,
    )


@pytest.mark.asyncio
async def test_une_reference_deja_notee_n_est_pas_recopiee_dans_un_autre_champ():
    """Runs 864, 870, 879 à 881 : la référence de facture dans la commande."""
    fiche = {"reference_facture": "FA20457"}
    ecrits = await balayer_la_fiche(
        _reglages(),
        Extracteur({"reference_commande": "FA20457"}),
        fiche,
        _messages("c'est la facture f a deux zéro quatre cinq sept", "FA20457"),
    )
    assert ecrits == {} and "reference_commande" not in fiche
    assert _refus(fiche, "reference_commande") == "recopie_de_reference_facture"


@pytest.mark.asyncio
async def test_un_code_postal_deja_note_n_est_pas_recopie_dans_la_commune():
    """Run 880 : `commune` = « 60700 »."""
    fiche = {"code_postal": "60700"}
    ecrits = await balayer_la_fiche(
        _reglages(), Extracteur({"commune": "60700"}), fiche, _messages("60700")
    )
    assert ecrits == {} and "commune" not in fiche


@pytest.mark.asyncio
async def test_un_champ_lu_par_le_lexique_ne_recoit_qu_un_terme_du_lexique():
    """Run 865 : `marque_appareil` = « insert » (dit, mais pas une marque)."""
    fiche: dict = {}
    ecrits = await balayer_la_fiche(
        _reglages(), Extracteur({"marque": "insert"}), fiche, _messages("mon insert fait de la fumée")
    )
    assert ecrits == {} and "marque" not in fiche
    assert _refus(fiche, "marque") == "hors_de_sa_liste"


@pytest.mark.asyncio
async def test_un_champ_de_commune_ne_recoit_qu_une_commune_reconnue():
    fiche: dict = {}
    ecrits = await balayer_la_fiche(
        _reglages(), Extracteur({"commune": "la maison"}), fiche, _messages("c'est à la maison")
    )
    assert ecrits == {} and _refus(fiche, "commune") == "hors_de_sa_liste"


@pytest.mark.asyncio
async def test_la_passe_recoit_les_valeurs_des_listes_fermees():
    extracteur = Extracteur({})
    await balayer_la_fiche(_reglages(), extracteur, {}, _messages("bonjour"))
    urgence = next(v for v in extracteur.variables if v.name == "urgence")
    assert "Valeurs permises : faible, forte." in urgence.prompt


@pytest.mark.asyncio
async def test_ce_qui_passait_passe_encore():
    """Un terme du lexique dit, une commune reconnue par le module, une référence neuve."""
    fiche = {
        CLE_TOUR: 1,
        "communes_verifiees": [
            {"entendu": "Creil", "statut": "sure", "commune_retenue": CREIL, "propositions": [CREIL], "tour": 1}
        ],
    }
    ecrits = await balayer_la_fiche(
        _reglages(),
        Extracteur({"marque": "Edilkamin", "commune": "Creil", "reference_commande": "CO123"}),
        fiche,
        _messages("un Edilkamin, à Creil, la commande CO123"),
    )
    assert ecrits == {"marque": "Edilkamin", "commune": "Creil", "reference_commande": "CO123"}
