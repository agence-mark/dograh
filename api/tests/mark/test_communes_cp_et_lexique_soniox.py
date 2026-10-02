"""[.mark] Chantier communes-cp-et-lexique-soniox.
Plan : ``Labo-agent-vocal/plans/communes-cp-et-lexique-soniox/2026-10-02-plan-communes-cp-et-lexique-soniox.md``.

Chaque test de la fiche appelle le VRAI gestionnaire de ``noter_information``
(``creer_gestionnaire``) comme le modèle l'appelle, sur une fiche où les traces des
modules sont écrites comme les modules les écrivent.

| Test | Lot | Preuve (run) |
|---|---|---|
| un oui à une commune proposée depuis le code postal l'écrit | C1 | 1019 |
"""

import pytest

from api.services.communes.base import charger_base
from api.tests.mark.test_fiche_correctifs_modules import Appel, _a_faire_confirmer, _reglages

COMMUNE = {"nom": "commune", "origine": "dicte"}
CODE_POSTAL = {"nom": "code_postal", "origine": "dicte"}


# --- C1 : une option proposée par la fiche se confirme, quelle que soit sa source ---


async def _sainte_maxence_proposee() -> Appel:
    """Run 1019 : « Sainte-Maxence » n'est pas une commune ; le code postal 60700, lu par le
    module des nombres, fait proposer ses communes, Pont-Sainte-Maxence en premier."""
    charger_base()
    appel = Appel(_reglages(COMMUNE, CODE_POSTAL))
    appel.dit("je suis au circuit dentaire 60700, pour Sainte-Maxence.")
    appel.trace("nombres_lus", type="code_postal", retenu="60700")
    r = await appel.note(commune="Sainte-Maxence", code_postal="60700")
    proposees = [p for p in r.get("a_proposer") or [] if p["champ"] == "commune"]
    assert proposees and proposees[0]["options"][0] == "Pont-Sainte-Maxence (Oise)", r
    assert not appel.sure("commune")
    return appel


@pytest.mark.asyncio
async def test_C1_run_1019_un_oui_a_la_commune_proposee_depuis_le_code_postal_l_ecrit():
    appel = await _sainte_maxence_proposee()
    appel.dit("Oui, oui.", agent_avant="Est-ce que vous êtes bien sur Pont-Sainte-Maxence ?")
    r = await appel.note(commune="Pont-Sainte-Maxence")
    assert "commune" not in _a_faire_confirmer(r), r
    assert appel.sure("commune") and appel.fiche["commune"] == "Pont-Sainte-Maxence", r


@pytest.mark.asyncio
async def test_C1_l_option_renvoyee_avec_son_departement_est_aussi_reconnue():
    appel = await _sainte_maxence_proposee()
    appel.dit("Oui.", agent_avant="Vous êtes à Pont-Sainte-Maxence, dans l'Oise ?")
    r = await appel.note(commune="Pont-Sainte-Maxence (Oise)")
    assert appel.sure("commune") and appel.fiche["commune"] == "Pont-Sainte-Maxence", r


@pytest.mark.asyncio
async def test_C1_temoin_un_non_ne_confirme_rien():
    appel = await _sainte_maxence_proposee()
    appel.dit("Non, pas du tout.", agent_avant="Est-ce que vous êtes bien sur Pont-Sainte-Maxence ?")
    await appel.note(commune="Pont-Sainte-Maxence")
    assert not appel.sure("commune")


@pytest.mark.asyncio
async def test_C1_temoin_une_commune_hors_des_propositions_n_est_pas_confirmee_par_un_oui():
    appel = await _sainte_maxence_proposee()
    appel.dit("Oui, oui.", agent_avant="Est-ce que vous êtes bien sur Compiègne ?")
    await appel.note(commune="Compiègne")
    assert not appel.sure("commune")
