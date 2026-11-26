"""[.mark] Lot 8, PE-1, Q7-3 (Pierre, 26/11 : « rendre la case ; le second numéro est gardé et transmis au restaurant ») : la case ``second_numero`` de la fiche de la commande.

Elle s'ouvre avec les autres cases de fin (``CASES_DE_FIN``), est notée dans la commande (``client``) au tour où elle est dite, dite par le code tel que retenu (comme le numéro),
écrite en base et jointe à la commande envoyée. Ce sont les tests supprimés au lot 4 (D49), rendus sur la porte :
``test_le_second_numero_retenu_est_dit_aussi``, ``test_le_second_numero_est_garde_avec_qui_et_pourquoi_et_joint_a_la_commande`` (devenu « sans qui ni pourquoi » : la case est un numéro),
``test_e_second_numero_avec_le_numero_affiche_une_seule_question``.

Client « Et si je ne réponds pas, appelez le 07 11 22 33 44. » / Avant : rien n'est gardé, la case n'existe pas. / Après : le numéro est gardé, dit par le code, joint au ticket."""

from __future__ import annotations

from api.db.bases_clients.restauration_commande import commande_complete
from api.services.actions_communes import conversation as CONV
from api.services.commande import contrat
from api.services.gabarits.restauration import textes as TX
from api.services.mots_dits import numero_en_lettres
from api.services.phrases import catalogue as CAT
from api.services.phrases.regles import CLE_REGLES
from api.services.commande import porte as PORTE

from .aides_de_la_commande import jusqu_au_numero, jusqu_au_recapitulatif, premier_article, a_emporter, refuser_la_proposition

SECOND = "+33711223344"
DIT_SECOND = numero_en_lettres(SECOND)
DIT = numero_en_lettres("+33612345678")
DC10_ETEINT = {CLE_REGLES: [{"motif": CAT.NUMERO_DICTE_RELU, "portee": "agent", "active": False}]}


def test_la_case_est_une_case_de_fin_du_contrat_et_de_la_fiche_montree_au_modele():
    assert "second_numero" in contrat.CASES_DE_FIN and contrat.CASES_DE_FIN.index("telephone") < contrat.CASES_DE_FIN.index("second_numero")
    fiche = TX.contrat()["etapes"]["commande"]["outils"]
    cases = next(o["function"] for o in fiche if o["function"]["name"] == "fiche")["parameters"]["properties"]
    assert cases["second_numero"]["type"] == "string" and list(cases).index("second_numero") == list(cases).index("prenom") + 1, list(cases)


def test_les_autres_outils_qui_ont_un_prenom_n_ont_pas_la_case():
    """Le geste ne touche que sa cible (refus 15) : la réservation, l'accueil et le service n'ont pas gagné la case."""
    for etape, tous in TX.contrat()["etapes"].items():
        for o in tous["outils"]:
            proprietes = (o["function"].get("parameters") or {}).get("properties") or {}
            assert ("second_numero" in proprietes) == (etape == "commande" and o["function"]["name"] == "fiche" and "ajouter" in proprietes), (etape, o["function"]["name"])


async def test_le_second_numero_est_note_dit_par_le_code_et_joint_a_la_commande(essai_de):
    e = await jusqu_au_numero(await essai_de("casa-italia"), appelant=False, configurations=DC10_ETEINT)
    await e.tour("Léa, au zéro six douze trente-quatre cinquante-six soixante-dix-huit, et sinon le zéro sept onze vingt-deux trente-trois quarante-quatre",
                 telephone="0612345678", prenom="Léa", second_numero="0711223344")
    r = e.retours[-1]
    assert e.p.get("enregistree"), r
    assert e.p["client"]["second_numero"]["numero"] == SECOND
    textes = e.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE) or {}
    assert DIT in textes["suffixe"] and DIT_SECOND in textes["suffixe"], textes  # le numéro et le second, tels que retenus
    base = await commande_complete(e.monde.c, e.monde.a, e.p["enregistree"]["numero"])
    assert (base["client"]["second_numero"] or {}).get("numero") == SECOND, base["client"]
    envoyee = e.source.prise.recues[-1]
    assert SECOND in (envoyee.get("note") or "") or (envoyee["client"].get("second_numero") or {}).get("numero") == SECOND, envoyee  # la prise de test n'a qu'un téléphone : le second part dans la note


async def test_un_second_numero_illisible_est_refuse_seul_et_le_numero_reste(essai_de):
    e = await jusqu_au_numero(await essai_de("casa-italia"), appelant=False, configurations=DC10_ETEINT)
    await e.tour("Léa, au zéro six douze trente-quatre cinquante-six soixante-dix-huit", telephone="0612345678", second_numero="12 34")
    faits = [x.get("faits") or {} for x in e.retours[-1].get("resultats") or []]
    assert any(f.get("numero_illisible") for f in faits), e.retours[-1]
    assert e.p["client"].get("second_numero") is None and e.p["client"]["telephone"] == "+33612345678" and not e.p.get("enregistree")


async def test_avant_l_accord_a_la_relecture_la_case_est_refusee_comme_les_autres_cases_de_fin(essai_de):
    e = await essai_de("casa-italia")
    await a_emporter(e)
    await premier_article(e)
    await refuser_la_proposition(e)
    await jusqu_au_recapitulatif(e)
    r = await e.tour("et sinon le zéro sept onze vingt-deux trente-trois quarante-quatre", second_numero="0711223344")
    assert r.get("raison") == "recapitulatif_pas_accepte" and "second_numero" in (r.get("cases_refusees") or []) and e.p["client"].get("second_numero") is None, r


async def test_sur_une_commande_accordee_la_case_declenche_l_enregistrement_et_le_numero_qui_s_affiche_garde_sa_seule_question(essai_de):
    """Risque de la fiche : ``second_numero`` dans ``CASES_DE_FIN`` fait tenter l'enregistrement d'une commande accordée (voulu). Client : numéro qui s'affiche, « oui » à la relecture, puis
    « et le 07… » : la question du numéro qui s'affiche reste la seule posée (test_e_second_numero_avec_le_numero_affiche_une_seule_question), le second est noté."""
    e = await jusqu_au_numero(await essai_de("casa-italia"), appelant=True)
    q = CONV.question_de(e.p) or {}
    assert q.get("type") == "numero_affiche", q
    await e.tour("et sinon le zéro sept onze vingt-deux trente-trois quarante-quatre", second_numero="0711223344")
    assert e.p["client"]["second_numero"]["numero"] == SECOND
    assert (CONV.question_de(e.p) or {}).get("type") == "numero_affiche" and (CONV.question_de(e.p) or {}).get("id") == q["id"]
    assert not e.p.get("enregistree")


async def test_un_second_numero_que_la_personne_n_a_pas_dit_est_refuse_comme_le_telephone(essai_de):
    """Reprise R1 de l'audit (D57) : le second numéro suit la règle de ses chiffres comme ``telephone`` (les 9 derniers chiffres se retrouvent dans ses mots) ; un numéro inventé par le modèle
    n'est ni gardé, ni dit, ni envoyé au restaurant. Le numéro, lui, reste noté (la case refusée seule)."""
    e = await jusqu_au_numero(await essai_de("casa-italia"), appelant=False, configurations=DC10_ETEINT)
    r = await e.tour("Léa, au zéro six douze trente-quatre cinquante-six soixante-dix-huit", telephone="0612345678", second_numero="0799999999")
    assert r.get("raison") == "valeur_pas_dans_ses_mots" and "second_numero" in (r.get("cases_refusees") or []), r
    assert not (e.p["client"].get("second_numero") or {}).get("numero"), e.p["client"]


async def test_un_second_numero_egal_au_premier_n_est_pas_garde_deux_fois(essai_de):
    """Non bloquant 3 de l'audit : le même numéro dit comme second n'est ni dit deux fois par le code ni envoyé en double au restaurant."""
    e = await jusqu_au_numero(await essai_de("casa-italia"), appelant=False, configurations=DC10_ETEINT)
    await e.tour("Léa, au zéro six douze trente-quatre cinquante-six soixante-dix-huit, et sinon le même", telephone="0612345678", prenom="Léa", second_numero="0612345678")
    assert e.p["client"]["telephone"] == "+33612345678" and not e.p["client"].get("second_numero"), e.p["client"]
    textes = e.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE) or {}
    assert (textes.get("suffixe") or "").count(DIT) <= 1, textes


async def test_la_seule_case_du_second_numero_sur_une_commande_accordee_sans_question_declenche_l_enregistrement(essai_de):
    """Non bloquant 7 de l'audit : accord donné, aucune question en attente, seule la case du second numéro est remplie : l'enregistrement part (il demande ce qui manque : le numéro) et le
    second numéro est noté."""
    e = await jusqu_au_numero(await essai_de("casa-italia"), appelant=False, configurations=DC10_ETEINT)
    assert CONV.question_de(e.p) is None, CONV.question_de(e.p)
    r = await e.tour("et sinon le zéro sept onze vingt-deux trente-trois quarante-quatre", second_numero="0711223344")
    assert e.p["client"]["second_numero"]["numero"] == SECOND and not e.p.get("enregistree"), e.p["client"]
    assert "telephone" in [x.get("manque") for x in r.get("resultats") or []], r
