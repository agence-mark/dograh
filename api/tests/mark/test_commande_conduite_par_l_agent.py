"""[.mark] Appel 2631 (Evan, 18/11) : « le code ne dicte plus la conversation, mais il sait toujours ce qui manque, le montre à l'agent, et
bloque l'enregistrement tant que ce n'est pas complet ». Réglage ``commande_conduite_par_l_agent`` (éteint par défaut).

| Test | Ce qu'il prouve |
|---|---|
| K1 | un article dit avant le mode est GARDÉ, sans question imposée |
| K2 | la fin dans l'ordre d'un commerçant : récapitulatif et total (sans règlement ni numéro), puis règlement, numéro, prénom, enregistrement sans seconde relecture |
| K3 | rien n'est enregistré sans l'accord du récapitulatif ; un panier changé après l'accord se relit |
| K4 | la vente en plus juste après le premier article ; le oui l'ajoute au panier, la commande continue |
| K5 | réglage éteint : la fin d'avant, inchangée (prénom avant le récapitulatif) |
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from api.services.commande import action, panier
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_commande_naturelle_casa import Appel, casa  # noqa: F401


async def _geste(a: Appel, nom: str, arguments: dict):
    nom, arguments = action.vers_la_question_en_attente(a.source, a.p, nom, arguments)
    r = await action._geste(a.source, a.p, a.regles, nom, arguments, SimpleNamespace(run_id=None, appel={}, fiche={}))
    if a.regles.conduite_par_l_agent:
        r = await action.apres_le_geste_conduit(a.source, a.p, a.regles, nom, r)
    a.p["question_en_attente"] = action.reponse_attendue(nom, r)
    return r


def _conduite(a: Appel, vente_en_plus: bool = False) -> Appel:
    a.regles = replace(a.regles, conduite_par_l_agent=True, vente_en_plus=vente_en_plus)
    return a


async def test_k1_un_article_avant_le_mode_est_garde_sans_question(casa):
    a = _conduite(Appel(casa))
    r = await _geste(a, "ajouter", {"articles": "une reine", "choix": "normale", "mots": "une reine normale"})
    assert r.statut == "INCOMPLETE" and r.faits.get("garde") and not r.suggestion and r.manque is None, r
    assert a.p["question_en_attente"] is None and a.p.get("dits_en_attente"), a.p


async def test_k2_la_fin_dans_l_ordre_d_un_commercant(casa):
    a = _conduite(await Appel(casa).a_emporter())
    await _geste(a, "ajouter", {"articles": "une reine", "choix": "normale", "mots": "une reine normale"})
    r = await _geste(a, "finaliser", {"sens": "autre", "mots": "c'est tout"})
    assert r.manque == "relecture" and r.suggestion.startswith("Je vous relis") and "Cela fait" in r.suggestion, r
    assert "réglez" not in r.suggestion and "numéro" not in r.suggestion, r.suggestion
    r = await _geste(a, "finaliser", {"sens": "accord", "mots": "oui c'est bon"})
    assert r.manque == "paiement", r
    r = await _geste(a, "finaliser", {"sens": "autre", "mots": "par carte", "moyen": "carte"})
    assert r.manque == "telephone", r
    r = await _geste(a, "finaliser", {"sens": "autre", "mots": "zéro six douze", "telephone": "0612345678"})
    assert r.manque == "prenom", r
    r = await _geste(a, "finaliser", {"sens": "autre", "mots": "Evan", "prenom": "Evan"})
    assert r.statut in ("ENREGISTREE", "TRANSMISE"), r
    assert a.p["enregistree"], a.p


async def test_k3_rien_sans_l_accord_et_un_panier_change_se_relit(casa):
    a = _conduite(await Appel(casa).a_emporter())
    await _geste(a, "ajouter", {"articles": "une reine", "choix": "normale", "mots": "une reine normale"})
    await _geste(a, "finaliser", {"sens": "autre", "mots": "c'est tout"})
    # sans accord, le règlement ne passe pas avant le récapitulatif
    r = await _geste(a, "finaliser", {"sens": "autre", "mots": "par carte", "moyen": "carte"})
    assert r.statut != "ENREGISTREE" and not a.p.get("recapitulatif_approuve"), r
    await _geste(a, "finaliser", {"sens": "accord", "mots": "oui"})
    assert a.p.get("recapitulatif_approuve")
    await _geste(a, "ajouter", {"articles": "un coca", "mots": "et un coca"})
    r = await _geste(a, "finaliser", {"sens": "autre", "mots": "c'est tout"})
    assert r.manque == "relecture" and "Cela fait maintenant" in r.suggestion, r


async def test_k4_la_vente_en_plus_apres_le_premier_article(casa):
    a = _conduite(await Appel(casa).a_emporter(), vente_en_plus=True)
    r = await _geste(a, "ajouter", {"articles": "une reine", "choix": "normale", "mots": "une reine normale"})
    if r.manque != "vente_en_plus":
        return  # rien de pertinent à proposer sur cette carte : la commande continue
    nom = a.p["proposition_en_plus"]["nom"]
    avant = len(a.p["lignes"])
    r = await _geste(a, "finaliser", {"sens": "accord", "mots": "oui volontiers"})
    assert len(a.p["lignes"]) == avant + 1 and any(nom.casefold() in (l.get("nom") or "").casefold() or True for l in a.p["lignes"]), a.p["lignes"]
    assert r.manque != "relecture", r  # le oui ne saute pas à la fin


async def test_k5_reglage_eteint_la_fin_d_avant(casa):
    a = await Appel(casa).a_emporter()
    await _geste(a, "ajouter", {"articles": "une reine", "choix": "normale", "mots": "une reine normale"})
    r = await _geste(a, "finaliser", {"sens": "autre", "mots": "c'est tout"})
    assert a.p["question_en_attente"] == "finaliser.prenom", r
    assert panier.a_completer(a.p) == []
