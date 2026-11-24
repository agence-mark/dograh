"""[.mark] Lot 20 : la file d'attente des questions (Evan, 21/11 : « j'aime beaucoup ce concept de file d'attente, il va falloir le tester sur plusieurs
cas ») et le restaurant fermé annoncé dès le début (« il faut lui indiquer dès le début de l'appel que le magasin est fermé et lui demander si elle veut
planifier une commande pour l'ouverture à 18 h »).

Une seule question est posée à la fois ; celle qui naît pendant qu'une autre attend sa réponse attend son tour ; la taille d'une ligne qui attend se lit
dans l'état du panier, jamais perdue (appel 450 : le mode redit dans la même fiche rendait le dernier résultat, la taille des deux pizzas disparaissait).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from api.services.actions_communes import conversation as CONV
from api.tests.mark.partie_1.aides_briques import brique, fait
from api.tests.mark.partie_1.test_l19bis_parole import _carte_de_perles


async def _fermer(e, monkeypatch) -> datetime:
    """Casa fermée jusqu'au service du soir, commande pour plus tard permise (le réglage du type) ; rend l'heure de la réouverture."""
    from api.services.restauration import source_commande as SC

    vrai_etat = e.source.etat
    maintenant = (await SC.maintenant(e.source.c)).astimezone()
    dix_huit = maintenant.replace(hour=18, minute=0, second=0, microsecond=0)
    reouverture = dix_huit if maintenant.hour < 17 else dix_huit + timedelta(days=1)

    async def ferme(mode):
        etat = dict(await vrai_etat(mode))
        return {**etat, "ouvert": False, "statut": "FERME", "raison": "ferme_horaires", "planifiee_permise": True, "prochaine_ouverture": reouverture}

    monkeypatch.setattr(e.source, "etat", ferme)
    return reouverture


def _dit_par_le_code(e) -> str:
    from api.services.commande.porte import CLE_TEXTES_DU_CODE

    textes = e.fiche_de_l_appel.get(CLE_TEXTES_DU_CODE) or {}
    return f"{textes.get('prefixe') or ''} {textes.get('avant') or ''}"


async def _repondre_aux_tailles(e) -> list[str]:
    """Répond « Normale » à chaque question de taille posée, une par une ; rend les articles demandés, dans l'ordre."""
    demandes = []
    for _ in range(6):
        q = CONV.question_de(e.p) or {}
        if q.get("type") != "variante":
            break
        demandes.append(q.get("texte"))
        await e.tour("normale", reponse={"question_id": q["id"], "sens": "autre", "valeurs": ["Normale"]})
    return demandes


async def test_ferme_annonce_au_debut_et_propose_l_ouverture(essai_de, monkeypatch):
    """Cas 1 (appel 450) : fermé, planifiable. Le mode dit, le code annonce la fermeture et propose l'ouverture, dès le début ; « oui, une Margherita et une
    Regina » pose l'heure, prend les deux pizzas, et leurs deux tailles sont demandées l'une après l'autre ; aucune relecture avant « c'est tout »."""
    e = await essai_de("casa-italia")
    reouverture = await _fermer(e, monkeypatch)
    await e.tour("à emporter", mode_de_retrait="emporter")
    q = CONV.question_de(e.p) or {}
    assert q.get("type") == "heure_proposee", (q, e.retours[-1])
    assert "Voulez-vous que je prépare votre commande pour" in _dit_par_le_code(e), _dit_par_le_code(e)
    r = await e.tour("oui, une margherita et une regina", reponse={"question_id": q["id"], "sens": "accepte"},
                     ajouter=[{"article": "Margherita", "quantite": 1}, {"article": "Regina", "quantite": 1}])
    assert e.p.get("heure_voulue") and datetime.fromisoformat(e.p["heure_voulue"]) == reouverture, e.p.get("heure_voulue")
    assert (CONV.question_de(e.p) or {}).get("type") == "variante" and r["statut"] == "A_PRECISER", (CONV.question_de(e.p), fait(r))
    demandes = await _repondre_aux_tailles(e)
    assert len(demandes) == 2 and "Margherita" in demandes[0] and "Regina" in demandes[1], demandes
    assert len(e.p["lignes"]) == 2 and not [l for l in e.p["lignes"] if l.get("attente")], e.p["lignes"]
    assert (CONV.question_de(e.p) or {}).get("type") != "relecture", CONV.question_de(e.p)


async def test_le_mode_redit_ne_perd_plus_la_taille(essai_de, monkeypatch):
    """Cas 1 bis (appel 450, tour 4, tel quel) : fermé, l'heure acceptée ; la fiche remet le mode avec les deux pizzas sans taille : le résultat du mode
    vient après celui de l'ajout ; la question de taille reste posée (avant : retour FAIT, aucune question, puis les deux pizzas ajoutées deux fois)."""
    e = await essai_de("casa-italia")
    await _fermer(e, monkeypatch)
    await e.tour("à emporter", mode_de_retrait="emporter")
    q = CONV.question_de(e.p)
    await e.tour("oui", reponse={"question_id": q["id"], "sens": "accepte"})
    r = await e.tour("une margherita et une regina", mode_de_retrait="emporter",
                     ajouter=[{"article": "Margherita", "quantite": 1}, {"article": "Regina", "quantite": 1}])
    assert (CONV.question_de(e.p) or {}).get("type") == "variante" and r["statut"] == "A_PRECISER", (CONV.question_de(e.p), fait(r))


async def test_deux_pizzas_sans_taille_restaurant_ouvert(essai_de):
    """Cas 2 : ouvert, deux pizzas sans taille dans la même fiche que le mode : les deux tailles sont demandées, l'une après l'autre, aucune perdue."""
    e = await essai_de("casa-italia")
    r = await e.tour("une margherita et une regina à emporter", mode_de_retrait="emporter",
                     ajouter=[{"article": "Margherita", "quantite": 1}, {"article": "Regina", "quantite": 1}])
    assert (CONV.question_de(e.p) or {}).get("type") == "variante", (CONV.question_de(e.p), fait(r))
    demandes = await _repondre_aux_tailles(e)
    assert len(demandes) == 2 and not [l for l in e.p["lignes"] if l.get("attente")], (demandes, e.p["lignes"])


async def test_l_heure_proposee_en_attente_garde_la_taille_pour_apres(essai_de, monkeypatch):
    """Cas 3 : la proposition de l'heure est posée ; elle dit ses pizzas sans y répondre : la question de l'heure reste posée (une seule à la fois) ; à
    son « oui », la taille, gardée dans l'état, est demandée à son tour."""
    e = await essai_de("casa-italia")
    await _fermer(e, monkeypatch)
    await e.tour("à emporter", mode_de_retrait="emporter")
    q = CONV.question_de(e.p)
    await e.tour("une regina", reponse={"question_id": q["id"], "sens": "autre"}, ajouter=[{"article": "Regina", "quantite": 1}])
    assert (CONV.question_de(e.p) or {}).get("id") == q["id"] and len(e.p["lignes"]) == 1, (CONV.question_de(e.p), e.retours[-1])
    await e.tour("oui", reponse={"question_id": q["id"], "sens": "accepte"})
    q2 = CONV.question_de(e.p) or {}
    assert q2.get("type") == "variante" and "Regina" in (q2.get("texte") or ""), (q2, e.p["lignes"], e.retours[-2:])


async def test_hesitation_nee_pendant_une_question_attend_son_tour(essai_de):
    """Cas 4 : une précision est demandée (quelles perles) ; elle ajoute un second article en doute sans répondre : le second doute n'est pas perdu, il est
    posé après la réponse à la première (avant : la question née pendant qu'une autre attendait disparaissait, l'article avec elle)."""
    e = await brique(essai_de, "OPT3", carte=_carte_de_perles())
    await e.tour("un bubble tea avec des perles", ajouter=[{"article": "bubble tea", "quantite": 1, "composition": ["perles"]}])
    q = CONV.question_de(e.p) or {}
    assert q.get("type") == "ambiguite", q
    r = await e.tour("et un autre avec des perles", reponse={"question_id": q["id"], "sens": "autre"},
                     ajouter=[{"article": "bubble tea", "quantite": 1, "composition": ["perles"]}])
    assert (CONV.question_de(e.p) or {}).get("id") == q["id"], (CONV.question_de(e.p), fait(r))
    await e.tour("tapioca", reponse={"question_id": q["id"], "sens": "autre", "valeurs": ["Perles de tapioca"]})
    q2 = CONV.question_de(e.p) or {}
    assert q2.get("type") == "ambiguite" and q2["id"] != q["id"] and len(e.p["lignes"]) == 1, (q2, e.p["lignes"])
    await e.tour("coco", reponse={"question_id": q2["id"], "sens": "autre", "valeurs": ["Perles de coco"]})
    assert len(e.p["lignes"]) == 2, e.p["lignes"]


# B1 (clôture) : « une question en file n'entre pas deux fois » testait la file, retirée ; le registre tient une question par objet (registre.objet).

async def test_allergie_dite_pendant_une_question_la_garde(essai_de):
    """Cas 6 : une taille est demandée ; elle dit une allergie sans répondre : les faits de l'allergie sont donnés et la taille reste la question posée."""
    e = await essai_de("casa-italia")
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une regina", ajouter=[{"article": "Regina", "quantite": 1}])
    q = CONV.question_de(e.p) or {}
    assert q.get("type") == "variante", q
    await e.tour("je suis allergique au gluten", reponse={"question_id": q["id"], "sens": "autre"}, note_generale="allergie au gluten")
    assert (CONV.question_de(e.p) or {}).get("type") == "variante" and len(e.p["lignes"]) == 1, (CONV.question_de(e.p), e.p["lignes"])
