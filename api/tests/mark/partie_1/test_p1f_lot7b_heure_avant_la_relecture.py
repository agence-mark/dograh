"""[.mark] Lot 7b, ligne 12 (Q1 = A) : une heure refusée reste un manque qui passe avant la relecture, le code ne la colle plus devant.

Avant : « Je ne prends pas de commande pour plus tard. Je vous relis : trois Margherita, à emporter. C'est bon ? » dit d'un bloc par le code (la relecture dite seule, le modèle ne repasse pas).
Après : l'heure refusée est la question posée (``heure_proposee``, avant la relecture dans l'ordre du registre) ; le modèle dit le refus avec ses mots et demande l'heure ; la relecture
vient une fois l'heure posée.
"""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes import du as DU
from api.services.actions_communes import parole as PAROLE
from api.services.actions_communes.repli import faits_du_fait_bloquant
from api.services.commande import moteur
from api.services.commande import porte as PORTE
from api.services.commande import registre as RQ
from api.services.commande.moteur import socle as _socle
from api.services.workflow import parole_de_la_fiche as PF

REFUS = "Je ne prends pas de commande pour plus tard."


async def _commande_et_heure_refusee(essai_de, monkeypatch):
    e = await essai_de("casa-italia")
    await e.dit("trois margherita à emporter").fiche(ajouter=[{"article": "margherita", "quantite": 3, "variante": "Normale"}], mode_de_retrait="emporter")
    q = CONV.question_de(e.p) or {}

    poser = moteur.poser_l_heure

    async def refusee(source, p, texte):
        if "vingt-trois" in str(texte):  # seule cette heure est refusée par son créneau ; les autres passent par le moteur
            return _socle._avec(moteur.Resultat("ARGUMENT_INVALIDE", {}, REFUS, "heure_voulue"), p)
        return await poser(source, p, texte)

    monkeypatch.setattr(moteur, "poser_l_heure", refusee)
    r = await e.dit("non merci, mettez-les pour vingt-trois heures, c'est tout").fiche(
        c_est_tout=True, heure="vingt-trois heures", **({"reponse": {"question_id": q["id"], "sens": "refuse"}} if q else {}))
    return e, r


async def test_l_heure_refusee_passe_avant_la_relecture_et_le_modele_la_dit(essai_de, monkeypatch):
    """Client « C'est tout, pour 23 h » : la question posée est l'heure, la relecture n'est pas dite par le code, le modèle repasse sur le refus."""
    e, r = await _commande_et_heure_refusee(essai_de, monkeypatch)
    q = CONV.question_de(e.p) or {}
    assert q.get("type") == "heure_proposee", (q, r["resultats"])
    textes = e.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE) or {}
    assert not textes.get("avant") and not textes.get("prefixe"), textes  # le code ne dit ni le refus ni la relecture
    # lot 7b-C4 (R = A) : le refus est donné au modèle en faits, sans sa phrase ; les mêmes faits sont tenus pour la relance du modèle muet
    assert r["faits"]["refus_de_la_fiche"][0]["manque"] == "heure_voulue" and "explication" not in r["faits"]["refus_de_la_fiche"][0], r["faits"]
    assert faits_du_fait_bloquant(e.fiche_de_l_appel) == r["faits"]["refus_de_la_fiche"], e.fiche_de_l_appel  # C5 : le refus tenu pour la relance du modèle est celui que le modèle a reçu
    assert PORTE.A_FAIRE_DES_REFUS_A_DIRE in r["a_faire"], r["a_faire"]
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "Pour vingt-trois heures ce n'est pas possible ; pour quelle heure la voulez-vous ?"})
    assert d.mode != PAROLE.A_DIRE_SEUL, d  # le modèle a la parole sur ce tour


async def test_la_relecture_vient_une_fois_l_heure_posee(essai_de, monkeypatch):
    """Suite : « plutôt vingt heures » pose l'heure, puis la commande va à sa relecture (celle du code, dite seule)."""
    e, _ = await _commande_et_heure_refusee(essai_de, monkeypatch)
    q = CONV.question_de(e.p) or {}
    r = await e.dit("plutôt vingt heures").fiche(heure="vingt heures", reponse={"question_id": q["id"], "sens": "autre", "valeurs": ["vingt heures"]})
    assert e.p.get("heure_voulue"), (e.p.get("heure_voulue"), r["resultats"])
    assert (CONV.question_de(e.p) or {}).get("type") == "relecture", (CONV.question_de(e.p), r["resultats"])


async def test_la_question_de_l_heure_ne_change_pas_le_verdict_de_la_commande(essai_de, monkeypatch):
    """R1 : la question de l'heure écrite sous la conversation n'est pas « un changement » de la commande ; la rouvrir à l'identique ne bouge pas ``ce_qui_se_voit``."""
    e, _ = await _commande_et_heure_refusee(essai_de, monkeypatch)
    vu = DU.ce_qui_se_voit(e.p)
    q = CONV.question_de(e.p)
    RQ.ouvrir(e.p, {k: v for k, v in q.items() if k != "id"})
    assert DU.ce_qui_se_voit(e.p) == vu


async def test_ferme_le_modele_dit_la_fermeture_et_demande_le_jour_et_l_heure(essai_de, monkeypatch):
    """Ligne 13. Client « Deux reines à emporter » (restaurant fermé, commande pour plus tard permise) : le code ne dit pas « Nous sommes fermés… Pour quel jour et à quelle heure ? » ;
    le fait (fermé, planifiable, heure de réouverture) et la consigne vont au modèle, qui répond avec ses mots ; le texte du module reste le texte de secours du repli."""
    phrase = "Nous sommes fermés pour le moment, nous rouvrons à dix-huit heures. Pour quel jour et à quelle heure ?"
    e = await essai_de("casa-italia")
    await e.dit("deux reines à emporter").fiche(ajouter=[{"article": "regina", "quantite": 2, "variante": "Normale"}], mode_de_retrait="emporter")
    q = CONV.question_de(e.p) or {}

    async def ferme(_source, p, _regles, _appelant, confirmer=False):
        faits = {"raison": "ferme_horaires", "a_planifier": True, "ouvre_a": "18:00"}
        return _socle._avec(moteur.Resultat("FERME_PLANIFIABLE", faits, phrase, "heure_voulue"), p)

    monkeypatch.setattr(PORTE, "mener_a_la_fin", ferme)
    r = await e.dit("c'est tout").fiche(c_est_tout=True, **({"reponse": {"question_id": q["id"], "sens": "refuse"}} if q else {}))
    assert phrase not in str(e.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE) or {}), e.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE)
    fait = r["faits"]["heure_a_dire"][0]
    assert fait["faits"]["a_planifier"] is True and PORTE.A_FAIRE_DE_L_HEURE in r["a_faire"], r
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "Nous sommes fermés, on rouvre à dix-huit heures ; pour quel jour et quelle heure ?"})
    assert d.mode != PAROLE.A_DIRE_SEUL, d
