"""[.mark] SA-18, lot B (C8) : « commande enregistrée » n'est dit que si un outil a ENREGISTRÉ.

Aux essais du 17/11, l'agent disait « votre commande est enregistrée » après des outils qui n'avaient fait que prendre des articles
(statut « OK »), sans jamais appeler l'outil qui enregistre. La garde de la vérité des actions ne le retenait pas : « enregistré »
n'était pas une formulation d'action, et n'importe quel outil réussi fondait l'annonce.

| Test | Ce qu'il prouve |
|---|---|
| sans aucun outil | « votre commande est enregistrée » est retenu, le modèle relancé une fois |
| outils qui prennent des données | après un outil « OK » (une prise d'articles), « enregistrée » est retenu |
| outil qui enregistre | après un résultat « ENREGISTREE », l'annonce passe |
| aucun statut fermé dans l'appel | la règle d'avant s'applique : un outil réussi fonde l'annonce |
"""

from api.services.workflow.verite_des_actions import CONSIGNE_ACTION
from api.tests.mark.test_verite_des_actions import (  # noqa: F401
    Banc,
    _horloge_figee,
    _jouer,
    _morceau,
    _reponse,
    _service,
    _texte,
)

PHRASE = "Votre commande est enregistrée, elle sera prête dans vingt minutes."


def _avec_outils_de_commande(banc: Banc) -> Banc:
    for nom, reponse in (
        ("ajouter", {"statut": "OK", "faits": {"ajoutes": ["Regina Normale"]}}),
        ("finaliser", {"statut": "ENREGISTREE", "faits": {"numero_court": "C1"}}),
    ):
        banc.executions[nom] = []
        banc.reponses[nom] = reponse
        banc.enveloppes[nom] = banc._envelopper(nom)
    return banc


async def _dit(banc: Banc) -> tuple[str, list]:
    service = _service([_morceau(PHRASE), _morceau(fin="stop")], banc, _reponse("Je finalise la commande."))
    texte = _texte(await _jouer(service))
    return texte, service.requetes


async def test_enregistree_sans_aucun_outil_est_retenue():
    texte, requetes = await _dit(_avec_outils_de_commande(Banc()))
    assert texte == "Je finalise la commande."
    assert any(CONSIGNE_ACTION == m.get("content") for m in requetes[0]["messages"])


async def test_enregistree_apres_une_simple_prise_d_articles_est_retenue():
    banc = _avec_outils_de_commande(Banc())
    await banc.appeler("ajouter", articles="une regina")
    texte, requetes = await _dit(banc)
    assert texte == "Je finalise la commande." and len(requetes) == 1


async def test_enregistree_apres_l_outil_qui_enregistre_passe():
    banc = _avec_outils_de_commande(Banc())
    await banc.appeler("ajouter", articles="une regina")
    await banc.appeler("finaliser", confirmer=True)
    texte, requetes = await _dit(banc)
    assert texte == PHRASE and requetes == []


async def test_sans_statut_ferme_dans_l_appel_un_outil_reussi_fonde_l_annonce():
    banc = Banc()
    banc.reponses["chercher"] = {"info": "x"}  # un résultat réussi, sans statut et sans date : la règle d'avant
    await banc.appeler("chercher", jour="x")
    texte, requetes = await _dit(banc)
    assert texte == PHRASE and requetes == []
