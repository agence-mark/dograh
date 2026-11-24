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
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une margherita normale", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    await e.tour("non", reponse={"question_id": e.p["question"]["id"], "sens": "refuse"})
    await e.tour("c'est tout", c_est_tout=True)
    par_tour: list[int] = []
    for propos, fiche in (("oui par carte", {"reponse": {"question_id": e.p["question"]["id"], "sens": "accepte"}, "moyen_de_paiement": "carte_bancaire"}),
                          ("pour dix-neuf heures", {"heure": "dix-neuf heures"})):
        avant = len(appels)
        await e.tour(propos, **fiche)
        par_tour.append(len(appels) - avant)
    assert max(par_tour) == 1 and all(n <= 1 for n in par_tour), par_tour


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


def test_la_fin_est_menee_en_un_seul_endroit_decide_en_fin_de_fiche():
    """R2 : ``moteur.finaliser`` n'est appelé que par ``mener_a_la_fin``, elle-même appelée par la seule ``_mener_a_la_fin_de_la_fiche`` ; plus de mémo ``ex.fin``."""
    source = PORTE.read_text(encoding="utf-8")
    assert source.count("moteur.finaliser(") == 1 and source.count("await mener_a_la_fin(") == 1 and "ex.fin" not in source


def test_la_fin_ne_redit_pas_la_question_du_reglement_que_regler_pose_deja():
    """R6 : la question « Vous réglez comment ? » est celle de ``regler`` ; ``_finaliser`` n'a pas de seconde branche pour elle."""
    assert "Vous réglez comment" not in (API / "services" / "commande" / "moteur" / "enregistrement.py").read_text(encoding="utf-8")


def test_le_cycle_prealables_articles_est_casse_sans_branchement_a_l_import_et_la_facade_ne_garde_que_le_public():
    """R7 : ``prealables`` n'importe pas ``articles`` ; ce qui reprend les articles dits (le mode, l'adresse) vit dans ``mode_et_adresse``, qui importe ``articles`` ; aucun global rempli à l'import ;
    la façade ``moteur`` ne re-exporte aucun nom privé."""
    dossier = API / "services" / "commande" / "moteur"
    texte = {p.stem: p.read_text(encoding="utf-8") for p in dossier.glob("*.py")}
    assert "moteur.articles" not in texte["prealables"] and "moteur.mode_et_adresse" not in texte["articles"] and "moteur.mode_et_adresse" not in texte["prealables"]
    assert "moteur.articles import" in texte["mode_et_adresse"]
    assert "brancher_la_reprise" not in "".join(texte.values()) and "global " not in texte["socle"]
    facade = ast.parse(texte["__init__"])
    prives = [a.name for n in facade.body if isinstance(n, ast.ImportFrom) for a in n.names if a.name.startswith("_")]
    assert not prives, prives
