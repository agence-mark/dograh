"""[.mark] Chantier modules-et-cerveaux, lot 2 (M1, M5) : les indices des modules en greffier.

Pourquoi : run vocal 1462 (18/10). En greffier, nos modules servaient la fiche et rien d'autre ;
le cerveau de conversation relisait la phrase brute. Les indices valent maintenant aussi en
greffier, sous l'en-tête fixé par Evan (M5), le téléphone par paires.

| Test | Ce qu'il prouve |
|---|---|
| défauts | greffier sans la clé : éteints (zéro perte) ; clé allumée : allumés ; Post-scriptum inchangé |
| requête (R1) | par le vrai habillage de la requête de conversation : case allumée, la ligne M5 et le numéro par paires y sont ; éteinte, absents |
| Post-scriptum | l'en-tête d'avant, le numéro tel que lu |
"""

from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_INDICES_DES_MODULES,
    CLE_MODE,
    CLE_TOUR,
    MODE_GREFFIER,
    MODE_POST_SCRIPTUM,
    ReglagesFiche,
    montrer_la_fiche,
)
from api.services.workflow.indices_des_modules import ENTETE_INDICES, ENTETE_INDICES_GREFFIER
from api.tests.mark.test_clavier_porte_la_fiche import FICHE

GREFFIER = {**FICHE, CLE_MODE: MODE_GREFFIER}
POST_SCRIPTUM = {**FICHE, CLE_MODE: MODE_POST_SCRIPTUM}
PAROLE = "Le 07/50/857872."
FICHE_DU_TOUR = {
    CLE_TOUR: 5,
    "nombres_lus": [
        {"tour": 5, "type": "telephone", "ecrit": "07/50/857872", "entendu": "07/50/857872"},
    ],
}


class _Modele:
    """Juste ce que ``montrer_la_fiche`` habille : la requête de conversation."""

    def __init__(self):
        self.envoye = None

    def build_chat_completion_params(self, params):
        return dict(params)

    async def get_chat_completions(self, context):
        self.envoye = self.build_chat_completion_params(
            {"messages": [{"role": "user", "content": PAROLE}]}
        )
        return self.envoye


async def _requete(configuration: dict) -> str:
    modele = _Modele()
    assert montrer_la_fiche(modele, ReglagesFiche.depuis(configuration), lambda: FICHE_DU_TOUR)
    await modele.get_chat_completions(None)
    return "\n".join(m["content"] for m in modele.envoye["messages"])


def test_les_defauts_en_greffier():
    assert ReglagesFiche.depuis(GREFFIER).indices_des_modules is False
    assert (
        ReglagesFiche.depuis({**GREFFIER, CLE_INDICES_DES_MODULES: True}).indices_des_modules
        is True
    )
    assert (
        ReglagesFiche.depuis({**GREFFIER, CLE_INDICES_DES_MODULES: False}).indices_des_modules
        is False
    )


async def test_en_greffier_case_allumee_la_requete_porte_lindice_m5_par_paires():
    requete = await _requete({**GREFFIER, CLE_INDICES_DES_MODULES: True})
    assert f"{ENTETE_INDICES_GREFFIER}téléphone = 07 50 85 78 72" in requete
    assert "PAS encore dans la fiche" not in requete


async def test_en_greffier_case_eteinte_aucun_indice():
    requete = await _requete(GREFFIER)
    assert ENTETE_INDICES_GREFFIER not in requete
    assert ENTETE_INDICES not in requete


async def test_en_postscriptum_lindice_dit_comme_avant():
    requete = await _requete({**POST_SCRIPTUM, CLE_INDICES_DES_MODULES: True})
    assert f"{ENTETE_INDICES}téléphone = 07/50/857872" in requete
    assert ENTETE_INDICES_GREFFIER not in requete
