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


def test_les_trois_temps_existent_et_les_deux_variables_de_contexte_n_existent_plus():
    source = PORTE.read_text(encoding="utf-8")
    for nom in ("async def _lire(", "async def _appliquer(", "async def _conclure(", "class Execution", "def refus_de_l_heure("):
        assert nom in source, nom
    for ancien in ("ContextVar", "_FINALISER_DE_LA_FICHE", "_CASES_FAITES", "finalise_deja_dans_la_fiche", "resultats[-1] ="):
        assert ancien not in source, ancien


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


def test_il_n_existe_plus_de_variable_demande_hesitations_ni_porteur_pour_porter_une_question():
    arbre = ast.parse(PORTE.read_text(encoding="utf-8"))
    champs = {n.target.id for c in ast.walk(arbre) if isinstance(c, ast.ClassDef) and c.name == "LaFiche" for n in c.body if isinstance(n, ast.AnnAssign)}
    assert not champs & {"hesitations", "porteur"}, champs
    ajouter = next(n for n in ast.walk(arbre) if isinstance(n, ast.AsyncFunctionDef) and n.name == "_case_ajouter")
    assert "demande" not in {x.id for x in ast.walk(ajouter) if isinstance(x, ast.Name)}
    assert "porteur" not in PORTE.read_text(encoding="utf-8").replace("porteur de", "")
