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
