"""[.mark] Chantier modules-et-cerveaux, lot 3 (M1) : la fiche montrée dans sa forme lisible.

Pourquoi : run vocal 1462 (18/10). L'état de la fiche montrait ``numero_dicte = « 0750857872 »``,
dix chiffres collés, et l'agent relisait la phrase brute de l'appelant. Un champ de téléphone
(``variables_telephone`` de l'agent) est montré par paires ; la valeur stockée, celle qui part
au portail et dans l'après-appel, ne change pas.
"""

import copy

from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_ETAT,
    CLE_MODE,
    MODE_GREFFIER,
    ReglagesFiche,
    etat_de_la_fiche,
    montrer_la_fiche,
)

CONFIGURATION = {
    "fiche_au_fil_de_leau": True,
    CLE_MODE: MODE_GREFFIER,
    "variables_telephone": "telephone*, tel_*, numero_dicte",
    "fiche_champs": [
        {
            "nom": "numero_dicte",
            "origine": "dicte",
            "description": "Numéro de rappel",
            "chiffres": 10,
        },
        {"nom": "reference_facture", "origine": "dicte", "description": "Référence"},
    ],
}
FICHE = {
    "numero_dicte": "0750857872",
    "reference_facture": "0612345678",
    CLE_ETAT: {"numero_dicte": {"sure": True}, "reference_facture": {"sure": True}},
}


def test_un_champ_de_telephone_est_montre_par_paires():
    etat = etat_de_la_fiche(ReglagesFiche.depuis(CONFIGURATION), FICHE)
    assert "numero_dicte = « 07 50 85 78 72 »" in etat


def test_un_champ_qui_nest_pas_un_telephone_reste_tel_quel():
    etat = etat_de_la_fiche(ReglagesFiche.depuis(CONFIGURATION), FICHE)
    assert "reference_facture = « 0612345678 »" in etat


def test_la_valeur_stockee_ne_change_pas():
    fiche = copy.deepcopy(FICHE)
    etat_de_la_fiche(ReglagesFiche.depuis(CONFIGURATION), fiche)
    assert fiche == FICHE
    assert fiche["numero_dicte"] == "0750857872"


def test_sans_le_nom_parmi_les_telephones_la_valeur_reste_collee():
    configuration = {**CONFIGURATION, "variables_telephone": "telephone*"}
    etat = etat_de_la_fiche(ReglagesFiche.depuis(configuration), FICHE)
    assert "numero_dicte = « 0750857872 »" in etat


class _Modele:
    def __init__(self):
        self.envoye = None

    def build_chat_completion_params(self, params):
        return dict(params)

    async def get_chat_completions(self, context):
        self.envoye = self.build_chat_completion_params(
            {"messages": [{"role": "user", "content": "oui c'est ça"}]}
        )
        return self.envoye


async def test_la_requete_du_cerveau_de_conversation_montre_la_forme_par_paires():
    modele = _Modele()
    fiche = copy.deepcopy(FICHE)
    assert montrer_la_fiche(modele, ReglagesFiche.depuis(CONFIGURATION), lambda: fiche)
    await modele.get_chat_completions(None)
    requete = "\n".join(m["content"] for m in modele.envoye["messages"])
    assert "07 50 85 78 72" in requete
    assert fiche["numero_dicte"] == "0750857872"
