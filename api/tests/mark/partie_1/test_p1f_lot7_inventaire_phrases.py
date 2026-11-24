"""[.mark] Plan final Partie 1, lot 7b, L2 : inventaire des phrases du code. Un fichier du lot ne contient aucune chaîne de plus de 25 lettres qui commence par une
majuscule (une phrase dite au client), sauf ``commande/phrases_dites_par_le_code.py`` (les exceptions du § 2, chacune nommée) et le module d'information commun, dont
les phrases sont des propositions faites au modèle, jamais dites telles quelles.

Chaque fichier est joué à part. Tant qu'il porte des phrases à rendre, son test est un xfail strict : le commit qui rend ses phrases au modèle le retire de ``A_RENDRE``
(un xfail strict qui passe est rouge, donc l'oubli se voit). Les docstrings et les noms de clés ne comptent pas."""

from __future__ import annotations

import ast
import re

import pytest

from api.outils import inventaire_rustines as I

SEUIL_DE_LETTRES = 25

FICHIERS_DU_LOT = (
    "db/bases_clients/restauration_commande.py",
    "services/actions_communes/parole.py",
    "services/actions_communes/repli.py",
    "services/commande/moteur/articles.py",
    "services/commande/moteur/enregistrement.py",
    "services/commande/moteur/lecture.py",
    "services/commande/moteur/prealables.py",
    "services/commande/moteur/reglement.py",
    "services/commande/porte.py",
    "services/commande/registre.py",
    "services/reservation/moteur.py",
    "services/reservation/porte.py",
    "services/restauration/carte_et_allergenes/allergie_de_la_commande.py",
    # reprise 3 de l'audit : ses phrases (l. 113-117) sont montées d'une constante du module commun (``INFO.SOURCE_FICHE``…) en tête de f-string : aucune lettre en dur à
    # compter, le détecteur ne les voit pas, elles sont suivies dans ``outils/phrases-a-rendre-au-modele.md``. Le fichier est gardé contre une phrase écrite en dur.
    "services/restauration/carte_et_allergenes/voir_un_article.py",
    "services/restauration/source_commande.py",
)

# Les fichiers qui portent encore des phrases du code à rendre au modèle (``outils/phrases-a-rendre-au-modele.md``). Un commit de 7b-B ou 7b-C retire ici son fichier.
# Les autres fichiers du lot (``parole.py``, ``repli.py``, ``commande/registre.py``, ``reservation/porte.py``) n'ont aucune phrase en majuscule : leurs lignes du
# ``.md`` sont des consignes au modèle en minuscule ; leur test passe tel quel, et c'est lui qui garde qu'une phrase n'y entre pas.
A_RENDRE = frozenset(FICHIERS_DU_LOT) - {
    "services/actions_communes/parole.py",
    "services/actions_communes/repli.py",
    "services/commande/registre.py",
    "services/reservation/porte.py",
    "services/restauration/carte_et_allergenes/voir_un_article.py",  # propre pour le détecteur (phrases montées de constantes), voir plus haut
}


def phrases_du_fichier(chemin: str) -> list[tuple[int, str]]:
    """Les chaînes qui commencent par une majuscule et comptent plus de 25 lettres, hors docstrings."""
    arbre = ast.parse((I.RACINE_API / chemin).read_text(encoding="utf-8"))
    docstrings = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and noeud.body:
            premier = noeud.body[0]
            if isinstance(premier, ast.Expr) and isinstance(premier.value, ast.Constant) and isinstance(premier.value.value, str):
                docstrings.add(id(premier.value))
    # une f-string est recomposée d'un bloc (une variable compte pour une lettre) : ses morceaux ne sont jamais lus à part
    morceaux_de_f_string = {id(m) for n in ast.walk(arbre) if isinstance(n, ast.JoinedStr) for m in ast.walk(n) if m is not n}
    trouvees = []
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.JoinedStr) and id(noeud) not in morceaux_de_f_string:
            texte = "".join(p.value if isinstance(p, ast.Constant) else "x" for p in noeud.values).lstrip()
        elif isinstance(noeud, ast.Constant) and isinstance(noeud.value, str) and id(noeud) not in docstrings and id(noeud) not in morceaux_de_f_string:
            texte = noeud.value.lstrip()
        else:
            continue
        if texte[:1].isupper() and len(re.findall(r"[^\W\d_]", texte)) > SEUIL_DE_LETTRES:
            trouvees.append((noeud.lineno, texte[:60]))
    return trouvees


def _cas(chemin: str):
    marques = [pytest.mark.xfail(strict=True, reason="phrases du code à rendre au modèle (lot 7b-B/7b-C, outils/phrases-a-rendre-au-modele.md)")] if chemin in A_RENDRE else []
    return pytest.param(chemin, marks=marques, id=chemin)


@pytest.mark.parametrize("chemin", [_cas(c) for c in FICHIERS_DU_LOT])
def test_aucune_phrase_dite_par_le_code_hors_des_exceptions(chemin):
    trouvees = phrases_du_fichier(chemin)
    assert not trouvees, "\n".join(f"{chemin}:{ligne} {texte}" for ligne, texte in trouvees)


def test_le_detecteur_voit_une_phrase_et_ignore_le_reste(tmp_path, monkeypatch):
    """Vu rouge du détecteur : une phrase en dur est comptée, un docstring, une clé et une consigne en minuscule non."""
    source = tmp_path / "x.py"
    source.write_text('"""Docstring qui ne compte pas du tout dans ce détecteur de phrases."""\nCLE = "une_cle_tres_longue_sans_majuscule_du_tout_ici"\nPHRASE = "Nous ne livrons pas à cette adresse pour le moment."\nPHRASE2 = f"Il est déjà plus de {h} : pour quel jour ?"\nPHRASE3 = f"Prêt à {h}."\n', encoding="utf-8")
    monkeypatch.setattr(I, "RACINE_API", tmp_path)
    # reprise 3 de l'audit : une phrase construite avec une variable est recomposée (la variable compte pour une lettre), jamais lue morceau par morceau ; une f-string courte reste ignorée
    assert phrases_du_fichier("x.py") == [(3, "Nous ne livrons pas à cette adresse pour le moment."), (4, "Il est déjà plus de x : pour quel jour ?")]


def test_la_liste_a_rendre_ne_nomme_que_des_fichiers_du_lot():
    assert A_RENDRE <= set(FICHIERS_DU_LOT)
