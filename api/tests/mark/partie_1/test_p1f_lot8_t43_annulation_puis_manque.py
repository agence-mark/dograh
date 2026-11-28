"""[.mark] Lot 8, T43 (registre, 28/11) : annulée dans la fiche, la commande continue (un mode, une adresse, une heure) : ce qui manque est demandé.

Né de R3 de l'audit 8b-2 (``422db242``) : quand l'annulation faite dans la fiche laisse le panier vide, le fait gardé est l'annulation (C6 n° 7). La parole le traite comme un fait
accompli (``table_de_parole._fait_accompli``), qui ne regardait que la question en attente, jamais le manque : la phrase du modèle partait seule. Pierre (27/11 7 h 23) : « Annulez,
finalement en livraison » / le modèle « C'est annulé. En livraison, qu'est-ce que je vous mets ? ».
Client « Annulez tout, finalement en livraison. » / Avant : « C'est noté. » seul (l'adresse jamais demandée) / Après : le modèle repasse avec le retour et demande l'adresse.
Et l'annulation d'un panier déjà vide n'est pas un fait de plus : « je répète : annulez, finalement en livraison » ne fait pas redire l'annulation (RC3), l'adresse reste demandée."""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes import parole as PAROLE
from api.services.actions_communes.du import CLE_DU
from api.services.commande.porte import CLE_TEXTES_DU_CODE
from api.services.workflow import parole_de_la_fiche as PF

MARGHERITA = {"article": "margherita", "quantite": 1, "variante": "Normale"}
ANNONCE = "C'est noté."  # la phrase du modèle des combinaisons (``combinaisons.ANNONCE``), écrite avant l'exécution


async def _une_margherita_sans_proposition(e) -> None:
    """L'état E4 des combinaisons : à emporter, une margherita, la proposition refusée (« non ») : plus aucune question n'attend."""
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une margherita normale", ajouter=[MARGHERITA])
    q = CONV.question_de(e.p)
    if q:
        await e.tour("non", reponse={"question_id": q["id"], "sens": "refuse"})
    assert e.p.get("lignes") and not CONV.question_de(e.p), e.p


def _manque(r: dict) -> str | None:
    return (r.get(CLE_DU) or {}).get("manque")


def _fait_du_code(e) -> dict:
    return (e.fiche_de_l_appel.get(CLE_TEXTES_DU_CODE) or {}).get("fait_accompli") or {}


async def test_annulee_puis_livraison_l_adresse_qui_manque_est_demandee(essai_de):
    e = await essai_de()
    await _une_margherita_sans_proposition(e)
    cases = {"annuler_la_commande": True, "mode_de_retrait": "livraison"}
    r = await e.tour("annulez tout, finalement en livraison", **cases)
    assert not e.p.get("lignes") and e.p.get("mode") == "livraison" and _manque(r), (e.p, r)
    assert _fait_du_code(e) == {"fait": "annulee_en_cours"}, _fait_du_code(e)  # R3 de 8b-2 tenu : le client entend l'annulation
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": ANNONCE, **cases})
    assert d.mode == PAROLE.SECOND_PASSAGE, d  # l'adresse est due : le modèle repasse avec le retour, jamais « C'est noté. » seul


async def test_videe_et_annulee_avec_une_heure_les_articles_qui_manquent_sont_demandes(essai_de):
    e = await essai_de()
    await _une_margherita_sans_proposition(e)
    cases = {"vider_le_panier": True, "annuler_la_commande": True, "heure": "dix-neuf heures"}
    r = await e.tour("on vide et on annule, pour dix-neuf heures", **cases)
    assert not e.p.get("lignes") and _manque(r), (e.p, r)
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": ANNONCE, **cases})
    assert d.mode == PAROLE.SECOND_PASSAGE, d


async def test_la_phrase_qui_dit_l_annulation_et_demande_ce_qui_manque_est_dite(essai_de):
    """Le voisin, et R1 de l'audit de T43 : la phrase du modèle dit l'annulation (décision du 27/11 7 h 23) puis pose la question de ce qui manque : elle part telle quelle.
    Le mode qui suit efface la marque « annulée » du dossier ; l'annulation reste le fait dit de ce tour, « C'est annulé. » n'est pas une annonce sans fondement."""
    e = await essai_de()
    await _une_margherita_sans_proposition(e)
    cases = {"annuler_la_commande": True, "mode_de_retrait": "livraison"}
    r = await e.tour("annulez tout, finalement en livraison", **cases)
    phrase = "C'est annulé. En livraison, à quelle adresse ?"
    assert not PF.annonce_non_fondee("La commande est annulée.", e.p), e.p  # la même règle juge la phrase du second passage
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": phrase, **cases})
    assert (d.mode, d.a_dire) == (PAROLE.A_DIRE_SEUL, phrase), d


async def test_c_est_annule_sans_annulation_dans_la_fiche_reste_refusee(essai_de):
    """Le témoin de R1 : rien n'est annulé dans ce tour (un mode seul) : « C'est annulé. » est une annonce sans fondement, le modèle repasse."""
    e = await essai_de()
    await _une_margherita_sans_proposition(e)
    cases = {"mode_de_retrait": "livraison"}
    r = await e.tour("finalement en livraison", **cases)
    assert e.p.get("lignes") and PF.annonce_non_fondee("C'est annulé.", e.p), e.p
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "C'est annulé.", **cases})
    assert d.mode == PAROLE.SECOND_PASSAGE, d


async def test_annuler_un_panier_deja_vide_ne_redit_pas_l_annulation(essai_de):
    """« Je répète » rejoue la même fiche au tour suivant : rien n'est plus à annuler, l'annulation n'est pas un fait de plus (RC3) ; l'adresse reste demandée."""
    e = await essai_de()
    await _une_margherita_sans_proposition(e)
    cases = {"mode_de_retrait": "livraison", "annuler_la_commande": True}
    r = await e.tour("finalement en livraison, annulez tout", **cases)
    PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": ANNONCE, **cases})
    r = await e.tour("je répète : finalement en livraison, annulez tout", **cases)
    assert _fait_du_code(e) == {}, _fait_du_code(e)
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": ANNONCE, **cases})
    assert d.mode == PAROLE.SECOND_PASSAGE, d


async def test_videe_puis_annulee_le_client_entend_l_annulation(essai_de):
    """M2 de l'audit de T43 : « on vide et on annule, pour 19 h » : le vidage passe avant l'annulation, qui trouve un panier déjà vide. La fiche a pourtant vidé une commande :
    l'annulation est le fait dit de ce tour (décision du 27/11 7 h 23), et la phrase du modèle qui la dit puis demande ce qui manque part telle quelle."""
    e = await essai_de()
    await _une_margherita_sans_proposition(e)
    cases = {"vider_le_panier": True, "annuler_la_commande": True, "heure": "dix-neuf heures"}
    r = await e.tour("on vide et on annule, pour dix-neuf heures", **cases)
    assert _fait_du_code(e) == {"fait": "annulee_en_cours"}, _fait_du_code(e)
    phrase = "C'est annulé. Qu'est-ce que je vous mets ?"
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": phrase, **cases})
    assert (d.mode, d.a_dire) == (PAROLE.A_DIRE_SEUL, phrase), d


async def test_une_phrase_renvoyee_de_toute_facon_ne_prend_pas_la_relance_du_tour(essai_de):
    """M3 de l'audit de T43 : la phrase vide (ou qui porte un chiffre) repasse de toute façon : elle ne prend pas la relance du tour (C5, une par tour). Au passage suivant du même
    tour, une nouvelle fiche dont la phrase oublie ce qui manque (l'adresse) est encore relancée, jamais « C'est noté. » seul."""
    e = await essai_de()
    await _une_margherita_sans_proposition(e)
    cases = {"annuler_la_commande": True, "mode_de_retrait": "livraison"}
    r = await e.tour("annulez tout, finalement en livraison", **cases)
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "", **cases})
    assert d.mode == PAROLE.SECOND_PASSAGE, d
    assert not PAROLE.etat_du_tour(e.fiche_de_l_appel).relance_du_fait  # rien n'a été relancé pour le manque : la relance du tour reste à prendre
    r = await e.fiche(heure="dix-neuf heures")  # le second passage du même tour remplit la fiche (une heure) sans l'adresse
    assert _manque(r), r
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": ANNONCE, "heure": "dix-neuf heures"})
    assert d.mode == PAROLE.SECOND_PASSAGE, d


async def test_le_journal_du_tour_est_ecrit_avant_le_jugement(essai_de):
    """L'ordre dont dépend R1 : la porte écrit le fait du tour au journal au retour de la fiche, avant que la parole juge la phrase du modèle
    (``parole_de_la_fiche._annulation_dite_ce_tour`` le relit). Au tour suivant, le même fait est d'un tour d'avant : « C'est annulé. » redevient sans fondement (RC3)."""
    from api.services.actions_communes import journal_du_dit as J

    e = await essai_de()
    await _une_margherita_sans_proposition(e)
    cases = {"annuler_la_commande": True, "mode_de_retrait": "livraison"}
    r = await e.tour("annulez tout, finalement en livraison", **cases)
    assert J.fait_accompli(e.p) == {"fait": "annulee_en_cours"} and not J.dit_a_un_tour_d_avant(e.p, J.FAIT_ACCOMPLI), e.p  # écrit avant tout jugement
    assert not PF.annonce_non_fondee("C'est annulé.", e.p)
    PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "C'est annulé. En livraison, à quelle adresse ?", **cases})
    r = await e.tour("au 3 rue de la Paix", adresse="3 rue de la Paix")
    assert PF.annonce_non_fondee("C'est annulé.", e.p), e.p
