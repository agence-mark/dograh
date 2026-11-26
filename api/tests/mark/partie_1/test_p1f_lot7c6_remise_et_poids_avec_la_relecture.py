"""[.mark] Lot 7b-C6, reprise R1 de l'audit réservation-prix (ordre de « C6 révisée » : la phrase du modèle, puis la phrase réglée du total, la question toujours la dernière) : une
remise (OFF3) ou un prix au poids (QTE1) rendu dans le même retour que la relecture est un fait que le modèle dit ; il le fait repasser, et la phrase du total suit sa phrase.

Avant : Client « C'est tout, et j'ai le code BIENVENUE. » / modèle « C'est noté pour le code. Alors une margherita et une reine à emporter. » seul (ni total ni question) ; « Oui. »
→ relecture pas entendue, reposée. Après : + code la phrase réglée du total (« Ça fait …, c'est bon ? ») ; « Oui. » est la réponse à la relecture.
Vraie source, vraie porte, vraie parole et ``RepliqueVerifiee``, sans modèle.
"""

from __future__ import annotations

from types import SimpleNamespace

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes import parole as PAROLE
from api.services.commande import contrat
from api.services.mots_dits import montant_en_lettres
from api.services.pipecat.reponse_avalee import RepliqueVerifiee
from api.services.workflow import parole_de_la_fiche as PF
from api.tests.mark.partie_1.aides_briques import preparer

REGLEE = "Pardon, je n'ai pas bien saisi. Vous pouvez répéter ?"


def _morceau(texte):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=texte, tool_calls=None), finish_reason=None)], usage=None)


def _reprise(texte: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=texte, tool_calls=None), finish_reason="stop")], usage=None)


async def _voix(e, retour, phrase: str, reponse: str) -> str:
    """Ce qui part à la voix : la phrase de la fiche dite seule ; sinon le modèle repasse et répond ``reponse`` (chaque relance la rend aussi)."""
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, retour, {"a_dire": phrase})
    if d.mode == PAROLE.A_DIRE_SEUL:
        return str(d.a_dire)
    verificateur = PF.VerificateurDeLaFiche(SimpleNamespace(_gathered_context=e.fiche_de_l_appel))

    async def flux():
        yield _morceau(reponse)

    async def relancer(_retenue):
        return _reprise(reponse)

    verifie = RepliqueVerifiee(flux(), verificateur.controler, relancer, None, verificateur.controler_la_relance,
                               lambda *a, **k: verificateur.controler_le_silence(None, **k), lambda: REGLEE)
    return "".join(m.choices[0].delta.content or "" for m in [m async for m in verifie])


async def _essai(essai_de, code: str):
    """L'essai de la brique, sa remise posée avant le chargement de l'appel ; le dit noté par la voix (``_voix``), jamais par l'essai."""
    e = await essai_de(f"briques/{code}")
    await preparer(code, e, True)
    await e.charger()
    e.fiche_de_l_appel[contrat.CLE_DES_OBJETS] = (await e.source.charger_pour_l_appel())[1]
    e.voix = False
    await e.tour("à emporter", mode_de_retrait="emporter")
    return e


async def _jusqu_a_la_relecture(e, parole: str, **cases) -> dict:
    """Le client finit sa commande (les propositions refusées en route) ; le dernier retour pose la relecture avec ``cases`` dans le même appel."""
    r: dict = {}
    for _ in range(4):
        q = CONV.question_de(e.p) or {}
        if q.get("type") == "relecture":
            break
        r = await e.tour(parole, c_est_tout=True, **cases, **({"reponse": {"question_id": q["id"], "sens": "refuse"}} if q else {}))
    assert (CONV.question_de(e.p) or {}).get("type") == "relecture", r
    return r


def _total_suit(e, phrase: str, dit: str) -> None:
    """La phrase du modèle part, puis la phrase réglée du total (le montant de la relecture), qui finit sur la question."""
    reste = dit[len(phrase):] if dit.startswith(phrase) else ""
    assert montant_en_lettres(e.p["relecture"]["total"]) in reste and reste.endswith("?"), dit


async def _oui_entendu(e) -> None:
    """« Oui. » répond à la relecture : elle n'est pas reposée."""
    q = CONV.question_de(e.p) or {}
    await e.tour("oui", reponse={"question_id": q["id"], "sens": "accepte"})
    assert (CONV.question_de(e.p) or {}).get("type") != "relecture", CONV.question_de(e.p)


async def test_remise_et_relecture_dans_le_meme_retour_le_total_suit_la_phrase(essai_de):
    e = await _essai(essai_de, "OFF3")
    await e.tour("une margherita et une reine", ajouter=[{"article": "margherita", "quantite": 1}, {"article": "reine", "quantite": 1}])
    r = await _jusqu_a_la_relecture(e, "c'est tout, et j'ai le code BIENVENUE", code_de_remise="BIENVENUE")
    assert r["faits"].get("remises_a_dire"), r["faits"]
    assert "remise" in str(r.get("a_faire")) and "relis" in str(r.get("a_faire")), r.get("a_faire")  # les deux consignes sont données ensemble
    phrase = "C'est noté pour le code. Alors une margherita et une reine à emporter."
    dit = await _voix(e, r, "C'est noté.", phrase)
    _total_suit(e, phrase, dit)
    await _oui_entendu(e)


async def test_voisin_prix_au_poids_et_relecture_dans_le_meme_retour_le_total_suit_la_phrase(essai_de):
    e = await _essai(essai_de, "QTE1")
    await e.tour("une pita", ajouter=[{"article": "pita", "quantite": 1}])
    r = await _jusqu_a_la_relecture(e, "et trois cents grammes de houmous, c'est tout", ajouter=[{"article": "houmous", "quantite": 1, "poids": "trois cents grammes"}])
    assert r["faits"].get("prix_au_poids"), r["faits"]
    phrase = "Trois cents grammes de houmous, ça fait cinq euros quarante. Alors une pita et le houmous à emporter."
    dit = await _voix(e, r, "C'est noté.", phrase)
    _total_suit(e, phrase, dit)
    await _oui_entendu(e)
