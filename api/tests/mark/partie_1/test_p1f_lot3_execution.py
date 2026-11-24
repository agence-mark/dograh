"""[.mark] Plan final Partie 1, lot 3 : l'exécution d'une fiche en trois temps (lire, appliquer, conclure), un seul ``finaliser`` par fiche, une surface publique du moteur,
aucune erreur avalée sans journal."""

from __future__ import annotations

import ast

from api.outils import inventaire_rustines as I
from api.services.commande import moteur

API = I.RACINE_API
PORTE = API / "services" / "commande" / "porte.py"


async def test_un_seul_finaliser_par_fiche_meme_quand_plusieurs_cases_menent_a_la_fin(essai_de, monkeypatch):
    """Espion (n° 14) : une fiche qui répond « oui » à la relecture ET donne le règlement, puis une qui change l'heure sous un accord, ne mènent la commande à sa fin qu'UNE fois."""
    appels: list[int] = []
    original = moteur.finaliser

    async def espion(*a, **k):
        appels.append(1)
        return await original(*a, **k)

    monkeypatch.setattr(moteur, "finaliser", espion)
    e = await essai_de()
    par_tour: list[int] = []

    async def jouer(propos: str, **fiche):
        avant = len(appels)
        await e.tour(propos, **fiche)
        par_tour.append(len(appels) - avant)
        assert par_tour[-1] <= 1, f"{propos!r} : {par_tour[-1]} finaliser dans un seul tour"  # vu tout de suite, avant que la suite du scénario ne dépende de l'état

    await jouer("à emporter", mode_de_retrait="emporter")
    await jouer("une margherita normale", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    await jouer("non", reponse={"question_id": e.p["question"]["id"], "sens": "refuse"})
    await jouer("c'est tout", c_est_tout=True)
    await jouer("oui par carte", reponse={"question_id": e.p["question"]["id"], "sens": "accepte"}, moyen_de_paiement="carte_bancaire")
    await jouer("pour dix-neuf heures", heure="dix-neuf heures")
    assert max(par_tour) <= 1 and sum(par_tour) >= 1, par_tour  # au plus une fin par fiche, et la fin a bien eu lieu au moins une fois


def test_la_porte_n_appelle_aucun_nom_prive_du_moteur_et_prealables_n_importe_pas_articles():
    """M2 : une surface publique du moteur, nommée ; le cycle prealables / articles est cassé."""
    arbre = ast.parse(PORTE.read_text(encoding="utf-8"))
    prives = [f"{n.lineno} moteur.{n.attr}" for n in ast.walk(arbre) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "moteur" and n.attr.startswith("_")]
    assert not prives, prives
    prealables = ast.parse((API / "services" / "commande" / "moteur" / "prealables.py").read_text(encoding="utf-8"))
    importes = [n.module for n in ast.walk(prealables) if isinstance(n, ast.ImportFrom) and n.module]
    assert not [m for m in importes if m.endswith("moteur.articles")], importes


def test_aucune_erreur_n_est_avalee_sans_journal_dans_la_commande_la_reservation_et_le_du():
    """M3 : un ``except Exception`` dont le corps n'est que ``pass`` n'existe plus ; une clé fausse y lèverait sans rien dire."""
    fautes = []
    for chemin in ("services/commande/porte.py", "services/reservation/porte.py", "services/actions_communes/du.py"):
        for n in ast.walk(ast.parse((API / chemin).read_text(encoding="utf-8"))):
            if isinstance(n, ast.ExceptHandler) and all(isinstance(x, ast.Pass) for x in n.body):
                fautes.append(f"{chemin}:{n.lineno}")
    assert not fautes, fautes


def test_aucune_fonction_de_la_porte_ne_depasse_quatre_vingts_lignes():
    """G1 : la fonction de 350 lignes est devenue lire, appliquer, conclure."""
    longues = [f"{n.name}:{n.end_lineno - n.lineno + 1}" for n in ast.walk(ast.parse(PORTE.read_text(encoding="utf-8")))
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.end_lineno - n.lineno + 1 > 80]
    assert not longues, longues


async def test_une_fiche_qui_echoue_ne_laisse_rien_a_la_suivante(essai_de, monkeypatch):
    """Rien ne reste d'une fiche à la suivante (plus de variable de contexte) : « c'est tout » échoue dans la caisse, la fiche d'après mène la commande à sa fin UNE fois et la relecture est posée."""
    appels: list[int] = []
    original = moteur.finaliser

    async def tombe_une_fois(*a, **k):
        appels.append(1)
        if len(appels) == 1:
            raise RuntimeError("panne simulée")
        return await original(*a, **k)

    monkeypatch.setattr(moteur, "finaliser", tombe_une_fois)
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une margherita normale", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    await e.tour("non", reponse={"question_id": e.p["question"]["id"], "sens": "refuse"})
    try:
        await e.tour("c'est tout", c_est_tout=True)
    except RuntimeError:
        pass
    avant = len(appels)
    await e.tour("c'est tout", c_est_tout=True)
    assert len(appels) - avant == 1 and (e.p.get("question") or {}).get("type") == "relecture", (appels, e.p.get("question"))


async def test_hors_zone_puis_une_proposition_le_refus_reste_le_fait_et_la_proposition_est_posee(essai_de):
    """n° 11 (B12, conversation 2) : « en livraison à Compiègne » (hors zone) et un article dans la même fiche : le refus de la zone reste le fait de la fiche ; la proposition en
    plus n'est pas perdue, sa question est au registre (plus de variable qui la porte à la place du dernier résultat)."""
    e = await essai_de()
    r = await e.tour("une regina en livraison au 8 rue Solférino à Compiègne", mode_de_retrait="livraison", adresse="8 rue Solférino", commune="Compiègne",
                     ajouter=[{"article": "regina", "quantite": 1, "variante": "Normale"}])
    hors = [x for x in r.get("resultats") or [] if x.get("statut_du_module") == "HORS_ZONE"]
    assert hors and r["statut"] == "PARTIEL", r
    assert (e.p.get("question") or {}).get("type") == "proposition", e.p.get("question")  # la proposition en plus est posée malgré le refus


async def test_le_premier_article_en_doute_n_est_pas_perdu_derriere_le_second(essai_de):
    """n° 10 (D25, note de Pierre du 20/11, famille de 2643) : le doute sur le premier article d'une case de plusieurs ouvre SA question au registre ; le second article, pris,
    ne l'écrase pas (plus de variable qui garde « le premier résultat qui demande »)."""
    from api.services.commande import registre as RQ

    from .test_l11_briques import brique

    e = await brique(essai_de, "OPT3")
    await e.tour("x", ajouter=[{"article": "bubble tea avec des perles", "quantite": 1}, {"article": "bubble tea", "quantite": 1, "composition": ["perles"]}])
    assert (e.p.get("question") or {}).get("type") == "ambiguite", e.p.get("question")
    assert any(q.get("type") == "ambiguite" for q in (e.p.get(RQ.CLE_DES_QUESTIONS) or {}).values())


async def test_un_article_en_doute_n_ouvre_qu_une_question(essai_de):
    """R1 : la fiche « [une salmone] » (deux candidats) ne donne qu'UNE question au registre, comptée une fois ; la fin de fiche ne rouvre pas ce que la case a ouvert,"""
    from api.services.commande import registre as RQ

    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une salmone", ajouter=[{"article": "salmone", "quantite": 1}])
    ouvertes = [q for q in (e.p.get(RQ.CLE_DES_QUESTIONS) or {}).values() if q.get("type") == "ambiguite"]
    assert len(ouvertes) == 1 and e.p.get("hesitations_nees") == 1, (ouvertes, e.p.get("hesitations_nees"))


async def test_deux_articles_en_doute_deux_questions_posees_dans_l_ordre_dit(essai_de):
    """R9 : deux articles en doute dans la même fiche : deux questions au registre, la première posée est celle du premier article dit, la seconde l'est après sa réponse."""
    from api.services.commande import registre as RQ

    from .test_l19bis_parole import _carte_de_perles
    from .test_l11_briques import brique

    e = await brique(essai_de, "OPT3", carte=_carte_de_perles())
    await e.tour("deux bubble tea", ajouter=[{"article": "bubble tea", "quantite": 1, "composition": ["perles"]}, {"article": "bubble tea", "quantite": 2, "composition": ["perles"]}])
    ouvertes = [q for q in (e.p.get(RQ.CLE_DES_QUESTIONS) or {}).values() if q.get("type") == "ambiguite"]
    assert len(ouvertes) == 2, ouvertes
    premiere = e.p["question"]
    assert (premiere.get("article_dit") or {}).get("quantite") == 1, premiere  # le premier dit est posé d'abord
    await e.tour("tapioca", reponse={"question_id": premiere["id"], "valeurs": ["Perles de tapioca"]})
    seconde = e.p.get("question") or {}
    assert seconde.get("type") == "ambiguite" and seconde["id"] != premiere["id"] and (seconde.get("article_dit") or {}).get("quantite") == 2, seconde


# R2, R6 et R7 ne lisent plus le code source : leurs preuves de comportement sont dans test_p1f_lot3_preuves.py (et le premier test de ce fichier pour R2).


async def test_un_article_en_doute_et_un_article_refuse_dans_la_meme_fiche_le_modele_dit_le_refus_et_pose_la_question(essai_de):
    """B (Evan, 24/11) : un article flou et un article refusé dans la même fiche : le code ne dit rien mot pour mot ; il donne au modèle le refus (lu sur l'ensemble des résultats de
    la fiche, avec l'article refusé) ET la question ouverte du registre ; le modèle dit les deux avec ses mots (« on ne l'a pas. Et la salmone, pizza ou bruschetta ? »)."""
    from api.services.actions_communes.parole import CLE_TEXTES_DU_CODE
    from api.services.commande import registre as RQ

    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    r = await e.tour("deux articles", ajouter=[{"article": "salmone", "quantite": 1}, {"article": "zzzquoi", "quantite": 1}])
    textes = e.fiche_de_l_appel.get(CLE_TEXTES_DU_CODE) or {}
    assert not textes.get("prefixe") and not textes.get("avant"), textes  # le code ne dit pas le refus
    assert not r.get("dit_avant_ta_phrase") and "sans le redire" not in r["a_faire"], r  # et ne dit pas au modèle que c'est dit
    refus = (r.get("faits") or {}).get("refus_de_la_fiche") or []
    assert len(refus) == 1 and refus[0]["faits"]["dit"] == "zzzquoi", refus  # le modèle sait QUOI est refusé
    assert (e.p.get("question") or {}).get("type") == "ambiguite" and (r.get("question") or {}).get("type") == "ambiguite", (e.p.get("question"), r.get("question"))
    assert r["statut"] == "PARTIEL" and "refus_de_la_fiche" in r["a_faire"], r
    assert any(q.get("type") == "ambiguite" for q in (e.p.get(RQ.CLE_DES_QUESTIONS) or {}).values())


async def test_l_heure_refusee_est_dite_par_le_code_et_le_modele_recoit_le_refus_d_article_et_la_question(essai_de, monkeypatch):
    """D33 + B (Evan, 24/11) : un article refusé, un article flou et une heure refusée dans la même fiche : le code dit l'heure (D33) ; le refus de l'article et la question sont des faits
    donnés au modèle, avec une consigne qui combine les deux : l'heure est dite (ne la redis pas), dis les autres refus puis pose la question."""
    from api.services.actions_communes.parole import CLE_TEXTES_DU_CODE
    from api.services.commande import porte

    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    phrase = "Je ne prends pas de commande pour plus tard."

    async def refusee(_source, p, _texte):
        return moteur.socle._avec(moteur.Resultat("ARGUMENT_INVALIDE", {}, phrase, "heure_voulue"), p)

    monkeypatch.setattr(moteur, "poser_l_heure", refusee)
    r = await e.tour("une salmone et un zzzquoi pour vingt-trois heures trente", ajouter=[{"article": "salmone", "quantite": 1}, {"article": "zzzquoi", "quantite": 1}], heure="vingt-trois heures trente")
    textes = e.fiche_de_l_appel.get(CLE_TEXTES_DU_CODE) or {}
    assert phrase in f"{textes.get('prefixe') or ''} {textes.get('avant') or ''}" and "zzzquoi" not in str(textes), textes  # le code dit l'heure, rien d'autre
    refus = [x for x in (r.get("faits") or {}).get("refus_de_la_fiche") or [] if x["manque"] != "heure_voulue"]
    assert len(refus) == 1 and refus[0]["faits"]["dit"] == "zzzquoi", r  # le modèle sait QUOI est refusé
    assert (r.get("question") or {}).get("type") == "ambiguite", r.get("question")
    assert r.get("dit_avant_ta_phrase") and porte.A_FAIRE_DU_REFUS_DIT in r["a_faire"] and porte.A_FAIRE_DES_REFUS_A_DIRE in r["a_faire"], r["a_faire"]  # les deux consignes, ensemble


async def test_un_refus_dit_par_le_modele_est_au_journal_et_le_second_echec_propose_une_issue_puis_la_sortie(essai_de):
    """B3 : le refus que le MODÈLE dit (né avec une question) entre au journal de ce qui est dit : la même demande refusée au tour suivant n'est pas redite en entier comme une
    première fois ; une issue est proposée, puis, au second échec, la sortie vers l'équipe."""
    from api.services.actions_communes import journal_du_dit as J
    from api.services.commande import porte

    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    r1 = await e.tour("une salmone et un zzzquoi", ajouter=[{"article": "salmone", "quantite": 1}, {"article": "zzzquoi", "quantite": 1}])
    assert porte.A_FAIRE_DES_REFUS_A_DIRE in r1["a_faire"], r1["a_faire"]  # tour 1 : le modèle dit le refus, en entier
    r2 = await e.tour("un zzzquoi quand même", ajouter=[{"article": "zzzquoi", "quantite": 1}])
    assert J.A_FAIRE_ISSUE in r2["a_faire"] and not r2.get("dit_avant_ta_phrase"), r2["a_faire"]  # tour 2 : déjà dit, une issue
    r3 = await e.tour("encore un zzzquoi", ajouter=[{"article": "zzzquoi", "quantite": 1}])
    assert J.A_FAIRE_SORTIE in r3["a_faire"], r3["a_faire"]  # tour 3 (second échec) : la sortie


async def test_au_second_refus_avec_une_question_nee_l_issue_est_donnee_et_la_question_reste_a_poser(essai_de):
    """B3 + B : au second refus, la consigne d'issue ne remplace pas celle de poser la question née dans ce tour : les deux se combinent."""
    from api.services.actions_communes import journal_du_dit as J
    from api.services.commande import porte

    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("un zzzquoi", ajouter=[{"article": "zzzquoi", "quantite": 1}])  # le refus est dit une première fois, aucune question ouverte
    r2 = await e.tour("un zzzquoi et une salmone", ajouter=[{"article": "zzzquoi", "quantite": 1}, {"article": "salmone", "quantite": 1}])  # le second refus naît avec une question
    assert (r2.get("question") or {}).get("type") == "ambiguite", r2.get("question")
    assert J.A_FAIRE_ISSUE in r2["a_faire"] and porte.A_FAIRE_DE_LA_QUESTION in r2["a_faire"], r2["a_faire"]


async def test_deux_articles_refuses_dans_la_meme_fiche_les_deux_refus_sont_donnes(essai_de):
    """B : deux refus dans la même fiche sont donnés tous les deux (lus sur l'ensemble des résultats), même quand un article accepté suit le premier refus."""
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    r = await e.tour("des articles", ajouter=[{"article": "zzzuno", "quantite": 1}, {"article": "margherita", "quantite": 1, "variante": "Normale"}, {"article": "zzzdeux", "quantite": 1}])
    refus = (r.get("faits") or {}).get("refus_de_la_fiche") or []
    assert sorted(x["faits"]["dit"] for x in refus) == ["zzzdeux", "zzzuno"] and r["statut"] == "PARTIEL", r


async def test_un_article_en_doute_puis_c_est_tout_la_commande_n_est_pas_conclue_et_la_question_est_reposee(essai_de):
    """A (Evan, 24/11) : un article en doute, puis « c'est tout » : on ne conclut pas, la relecture ne se pose pas, la question de l'article est reposée ; la fiche dit pourquoi (a_finir_avant)."""
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une salmone", ajouter=[{"article": "salmone", "quantite": 1}])
    q = e.p["question"]
    r = await e.tour("c'est tout", c_est_tout=True)
    assert (e.p.get("question") or {}).get("type") == "ambiguite" and e.p["question"]["id"] == q["id"], e.p.get("question")
    assert not (e.p.get("relecture") or {}).get("recapitulatif") and not e.p.get("enregistree"), e.p.get("relecture")
    assert "a_finir_avant" in str(r), r
