"""[.mark] Clôture de la Partie 1, lot B2 : ce qui est dû à la personne (audit du code M3), la phrase du code dans l'historique (IC5), DC4.

* Règle 1 : la phrase du modèle n'est dite seule que si rien n'est dû ; une phrase qui ne demande pas ce qui manque est jetée et le modèle repasse
  avec lui (RC1, 140 cas) ; le code ne pose jamais la question à sa place (Evan, 17/11).
* Règle 2 : une fiche qui ne change rien est une phrase sans outil : retenue une fois, puis dite avec la question en attente (RC4, trace 508).
* Faits accomplis dits par le code : enregistrée, changée avec son nouveau total (TF2, test du lot A2), annulée (DC4, second temps).
* DC4 (Evan, 22/11) : annuler une commande enregistrée se fait en deux temps, le montant dit ; « non » la laisse enregistrée.
* IC5 : ce que le code dit entre dans l'historique du modèle (``append_to_context``).
"""

from __future__ import annotations

from api.services.actions_communes.du import CLE_DU
from api.services.actions_communes import parole as PAROLE
from api.services.actions_communes import conversation as CONV
from api.services.commande import etape as ETAPE_
from api.services.commande import registre as RQ
from api.services.commande.porte import CLE_TEXTES_DU_CODE, RIEN_CHANGE
from api.services.workflow import parole_de_la_fiche as PF
from api.tests.mark.partie_1.test_cloture_a2_regles_inversees import _jusqu_a_l_enregistrement

ANNONCE = "C'est noté."


def _dit_par_le_code(e) -> str:
    return " ".join((e.fiche_de_l_appel.get(CLE_TEXTES_DU_CODE) or {}).values())


async def _sans_question(e) -> None:
    """Un article pris, la proposition refusée : plus aucune question ; ce qui manque est « autre chose ? »."""
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une margherita normale", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    q = CONV.question_de(e.p)
    await e.tour("non merci", reponse={"question_id": q["id"], "sens": "refuse"})
    assert not CONV.question_de(e.p), CONV.question_de(e.p)


async def test_regle_1_une_phrase_qui_ne_demande_pas_ce_qui_manque_repasse(essai_de):
    e = await essai_de()
    await _sans_question(e)
    cases = {"ajouter": [{"article": "regina", "quantite": 1, "variante": "Normale"}]}
    r = await e.tour("et une regina normale", **cases)
    assert (r.get(CLE_DU) or {}).get("manque") and not CONV.question_de(e.p), r  # le retour porte ce qui manque : le modèle le demande avec ses mots
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": ANNONCE, **cases})
    assert d.mode == PAROLE.SECOND_PASSAGE and d.motif == PAROLE.MANQUE, d


async def test_regle_1_la_question_du_modele_est_dite(essai_de):
    e = await essai_de()
    await _sans_question(e)
    cases = {"ajouter": [{"article": "regina", "quantite": 1, "variante": "Normale"}]}
    r = await e.tour("et une regina normale", **cases)
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "C'est noté, une Regina. Autre chose ?", **cases})
    assert d.mode == PAROLE.A_DIRE_SEUL and d.a_dire == "C'est noté, une Regina. Autre chose ?", d


async def test_ce_qui_manque_est_dans_le_retour_d_une_fiche_refusee(essai_de):
    """M4 : une seule place pour ce qui manque, à la sortie de toute fiche (avant : seulement une fiche exécutée sans refus ; RC1, 42 cas)."""
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    r = await e.tour("oui", reponse={"question_id": "Q-9", "sens": "accepte"})  # une réponse sans question : refusée
    assert (r.get(CLE_DU) or {}).get("manque") == "les articles", r  # lot 7b-C5 : la valeur fermée de ce qui manque, jamais sa phrase


async def test_regle_2_une_fiche_qui_ne_change_rien_vaut_une_phrase_sans_outil(essai_de):
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une margherita", ajouter=[{"article": "margherita", "quantite": 1}])
    q = CONV.question_de(e.p)
    assert q["type"] == "variante", q
    r = await e.tour("d'accord")  # fiche vide : « autre » pour la taille, rien ne change
    assert r.get(RIEN_CHANGE) and CONV.question_de(e.p)["id"] == q["id"], r
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": ANNONCE})
    assert d.mode == PAROLE.SECOND_PASSAGE and d.motif == RIEN_CHANGE, d  # « C'est noté » n'est jamais dit sur une fiche qui ne fait rien
    # décision d'Evan 25/11 8 h 45 (lot 7b-C5) : le code ne redit plus la question en attente après la phrase du modèle ; le modèle repasse une fois, puis sa phrase est dite seule
    r = await e.fiche()  # le second passage rend encore une fiche vide dans le même tour : sa phrase oublie la question, le modèle repasse
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "D'accord."})
    assert d.mode == PAROLE.SECOND_PASSAGE and d.motif == PAROLE.MANQUE, d
    r = await e.fiche()
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "D'accord."})
    assert d.mode == PAROLE.A_DIRE_SEUL and d.a_dire == "D'accord.", d


async def test_regle_2_trois_fois_la_meme_fiche_dans_un_tour_la_derniere_porte_la_question(essai_de):
    """M1 (RC4, profondeur 2 : E1, fiche corrigée puis rejouée) : une fiche a changé quelque chose dans le tour, puis deux fiches vides : la phrase
    dite au bout du rattrapage est celle du modèle relancé une fois avec la question en attente (lot 7b-C5), jamais « C'est noté » complété par le code."""
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    cases = {"ajouter": [{"article": "regina", "quantite": 1, "variante": "Normale"}]}
    r = await e.tour("une regina normale", telephone="0699999999", **cases)  # refusée en partie : l'article entre, une proposition naît
    q = CONV.question_de(e.p)
    assert q["type"] == "proposition", q
    PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": ANNONCE, **cases})
    r = await e.fiche(**cases)
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": ANNONCE, **cases})
    assert r.get(RIEN_CHANGE) and d.mode == PAROLE.SECOND_PASSAGE and d.motif == RIEN_CHANGE, d
    # décision d'Evan 25/11 8 h 45 (lot 7b-C5) : le code ne redit plus la proposition après la phrase du modèle ; le modèle repasse une fois, puis sa phrase est dite seule
    r = await e.fiche(**cases)
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": ANNONCE, **cases})
    assert r.get(RIEN_CHANGE) and d.mode == PAROLE.SECOND_PASSAGE and d.motif == PAROLE.MANQUE, d
    r = await e.fiche(**cases)
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": ANNONCE, **cases})
    assert r.get(RIEN_CHANGE) and d.mode == PAROLE.A_DIRE_SEUL and d.a_dire == ANNONCE, d


async def test_une_fiche_qui_change_quelque_chose_n_est_pas_rien(essai_de):
    e = await essai_de()
    r = await e.tour("à emporter", mode_de_retrait="emporter")
    assert not r.get(RIEN_CHANGE), r


async def test_tf2_un_changement_d_une_commande_enregistree_se_dit_par_le_code(essai_de):
    e = await essai_de()
    await _jusqu_a_l_enregistrement(e)
    r = await e.tour("en fait deux", changer_quantite=[{"ligne": 1, "quantite": 2}])
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": ANNONCE, "changer_quantite": [{"ligne": 1, "quantite": 2}]})
    assert d.motif == "texte_du_code" and "vingt et un euros quatre-vingts" in d.a_dire, d


async def test_dc4_annuler_une_commande_enregistree_en_deux_temps(essai_de):
    e = await essai_de()
    await _jusqu_a_l_enregistrement(e)
    await e.tour("annulez ma commande", annuler_une_commande_enregistree=True)
    q = CONV.question_de(e.p)
    assert q["type"] == RQ.TYPE_ANNULATION and e.p.get("enregistree") and not e.p.get("annulee"), e.p  # rien n'est annulé avant le « oui »
    # lot 7b, DC4 (fiche relue, Q2 = A) : l'ancienne attente (le code pose la question mot pour mot) contredit Q2 ; le modèle la pose, son texte reste celui du repli
    assert _dit_par_le_code(e) == "" and q["texte"] == "Vous êtes sûr de vouloir annuler votre commande de dix euros quatre-vingt-dix ?", (_dit_par_le_code(e), q)
    await e.tour("oui", reponse={"question_id": q["id"], "sens": "accepte"})
    assert e.p.get("annulee") and ETAPE_.courante(e.p) == RQ.ANNULEE, e.p
    assert _dit_par_le_code(e) == RQ.TEXTE_ANNULATION_CONFIRMEE


async def test_dc4_non_laisse_la_commande_enregistree(essai_de):
    e = await essai_de()
    await _jusqu_a_l_enregistrement(e)
    await e.tour("annulez ma commande", annuler_une_commande_enregistree=True)
    q = CONV.question_de(e.p)
    await e.tour("non finalement", reponse={"question_id": q["id"], "sens": "refuse"})
    assert e.p.get("enregistree") and not e.p.get("annulee") and not CONV.question_de(e.p), e.p


async def test_ic5_la_phrase_du_code_entre_dans_l_historique(monkeypatch):
    """La phrase dite seule (un passage) et le préfixe du code passent ``append_to_context`` : le modèle sait ce que la personne a entendu."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from api.services.integrations.connectors import outil
    from api.services.integrations.connectors.execution import Resultat as ResultatDeLAction

    async def executer(*a, **k):
        return ResultatDeLAction(statut="ok", donnees={"statut": "FAIT", "resultats": []}, duree_ms=1, message="")

    class Patience:
        def __init__(self, *a, **k): ...
        def demarrer(self): ...
        def arreter(self): ...

    monkeypatch.setattr(outil, "executer", executer)
    monkeypatch.setattr(outil, "resoudre", AsyncMock(return_value=({}, [])))
    monkeypatch.setattr(outil, "Patience", Patience)
    fiche = {"tour_de_la_personne": 2}
    engine = SimpleNamespace(_gathered_context=fiche, _call_context_vars={}, _workflow_run_id=1, greffier=None, queue_text_message=AsyncMock(return_value=True))
    manager = SimpleNamespace(_engine=engine, _agent=None, get_organization_id=AsyncMock(return_value=1))
    tool = SimpleNamespace(name="fiche", definition={"config": {"connecteur": "commande", "action": "fiche"}})
    gestionnaire = outil.creer_gestionnaire(manager, tool, "fiche")

    async def rappel(resultat, *, properties=None): ...

    await gestionnaire(SimpleNamespace(arguments={"mode_de_retrait": "emporter", "a_dire": "Très bien."}, tool_call_id="t", result_callback=rappel))
    (texte,), options = engine.queue_text_message.call_args
    assert texte == "Très bien." and options.get("append_to_context") is True, engine.queue_text_message.call_args


async def test_regle_3_le_repli_redit_le_fait_accompli(essai_de):
    """C5, DF5 : après l'enregistrement, « pardon ? » : ni question ni manque ; la confirmation est le fait accompli que le code a dit (§ 2 du plan, jusqu'à C6), jamais « je n'ai pas bien saisi »."""
    e = await essai_de()
    await _jusqu_a_l_enregistrement(e)
    from api.services.actions_communes import journal_du_dit as J

    confirmation = (J.fait_accompli(e.p) or "")
    assert confirmation.startswith("Votre commande est enregistrée"), e.p
    from types import SimpleNamespace

    e.montrer()
    silence = PF.VerificateurDeLaFiche(SimpleNamespace(_gathered_context=e.fiche_de_l_appel)).controler_le_silence()
    assert silence is not None and silence.a_dire == confirmation  # décision d'Evan 25/11 8 h 45 (lot 7b-C5) : rien n'est dû, le modèle muet : le fait accompli, jamais une phrase composée
