"""[.mark] Plan final Partie 1, lot 7b-C, L2 : inventaire des phrases du code. Un fichier du lot ne contient aucune phrase dite au client : un morceau de texte à lire par une
personne (deux mots ou plus, ou une phrase courte qui finit par ``?``, ``!`` ou ``.``), en majuscule, ou en minuscule quand il continue une phrase (il commence par une espace ou
une ponctuation). Sont lus les morceaux d'une f-string un par un, les chaînes courtes et celles qui commencent par une minuscule ; ne comptent pas : les docstrings, les messages
des journaux et des exceptions, les consignes au modèle (elles commencent par un verbe, jamais par une espace), les catalogues de secours (``textes_de_secours*.py`` et
``phrases_du_manque.py``, lus par le repli seul) les requêtes SQL et les textes pour l'équipe (``ENVOIS_POUR_L_EQUIPE``, liste blanche). Exceptions du § 2 : ``commande/phrases_dites_par_le_code.py``
(chacune nommée) ; le module d'information commun dont les phrases sont des propositions faites au modèle, jamais dites telles quelles.

Chaque fichier est joué à part. Tant qu'il porte des phrases à rendre, son test est un xfail strict : le commit qui rend ses phrases au modèle le retire de ``A_RENDRE``
(un xfail strict qui passe est rouge, donc l'oubli se voit)."""

from __future__ import annotations

import ast
import re

import pytest

from api.outils import inventaire_rustines as I

FICHIERS_DU_LOT = (
    "db/bases_clients/restauration_commande.py",
    "db/bases_clients/restauration_reservation.py",
    "services/actions_communes/parole.py",
    "services/actions_communes/repli.py",
    "services/commande/moteur/articles.py",
    "services/commande/moteur/changement.py",
    "services/commande/moteur/enregistrement.py",
    "services/commande/moteur/lecture.py",
    "services/commande/moteur/mode_et_adresse.py",
    "services/commande/moteur/prealables.py",
    "services/commande/moteur/reglement.py",
    "services/commande/porte.py",
    "services/commande/registre.py",
    "services/reservation/lire.py",
    "services/reservation/moteur.py",
    "services/reservation/porte.py",
    "services/restauration/carte_et_allergenes/allergie_de_la_commande.py",
    "services/restauration/carte_et_allergenes/voir_un_article.py",
    "services/restauration/source_commande.py",
)

# Un catalogue de secours n'est lu que par le repli (le texte que le code dit quand le modèle se tait deux fois sur un refus, jamais donné au modèle) : ses phrases sont permises.
# Il s'exempte par son nom, jamais par une liste de phrases : ranger une phrase au catalogue ailleurs ne la rend pas permise (I-7).
CATALOGUES_DE_SECOURS = ("services/commande/phrases_du_manque.py", "services/commande/textes_de_secours.py", "services/reservation/phrases_du_manque.py")
NOM_D_UN_CATALOGUE_DE_SECOURS = re.compile(r"(?:^|/)(?:textes_de_secours[^/]*|phrases_du_manque)\.py$")

# Textes écrits pour l'équipe du restaurant (ticket, SMS au gérant), jamais dits à la personne au téléphone : un morceau passé à l'un de ces envois est permis (liste blanche,
# chaque envoi nommé). Un envoi à l'équipe de plus entre ici avec sa raison, jamais par une phrase écrite autrement.
ENVOIS_POUR_L_EQUIPE = frozenset({"secours_par_defaut", "secours_de_la_commande"})  # source_commande.py : le ticket et le SMS « risque de doublon en cuisine »
_SQL = re.compile(r"\s*(?:SELECT|INSERT|UPDATE|DELETE|WITH|CREATE|ALTER)\s")

# Les fichiers qui portent encore des phrases du code à rendre au modèle (``outils/phrases-a-rendre-au-modele.md``), en trois blocs, un par sous-tranche de la 7b-C : chaque agent
# ne touche que le sien et retire son fichier de son bloc au commit qui rend ses phrases. Rien n'est retiré d'avance : toutes les phrases encore à rendre y sont listées.
# Les fichiers du lot hors de tout bloc (``parole.py``, ``repli.py``, ``commande/registre.py``, et chaque fichier retiré de son bloc) n'ont aucune phrase dite : leur test passe tel
# quel, et c'est lui qui garde qu'une phrase n'y entre pas.

# C1 commande : ``services/commande/*``
A_RENDRE_C1 = frozenset({
    "services/commande/moteur/lecture.py",
})

# C2 base et source de la commande : ``db/bases_clients/restauration_commande.py`` et ``restauration/source_commande.py``
A_RENDRE_C2 = frozenset({
    "db/bases_clients/restauration_commande.py",
    "services/restauration/source_commande.py",
})

# C3 réservation et allergie : ``services/reservation/*``, ``db/bases_clients/restauration_reservation.py``, ``restauration/carte_et_allergenes/*``
A_RENDRE_C3 = frozenset({
    "db/bases_clients/restauration_reservation.py",
    "services/reservation/lire.py",
    "services/reservation/moteur.py",
    "services/reservation/porte.py",
    "services/restauration/carte_et_allergenes/allergie_de_la_commande.py",
    "services/restauration/carte_et_allergenes/voir_un_article.py",
})

A_RENDRE = A_RENDRE_C1 | A_RENDRE_C2 | A_RENDRE_C3

_MOT = re.compile(r"[^\W\d_]+")
_S_ADRESSE_AU_MODELE = re.compile(r"\b(?:tu|ton|ta|tes|toi)\b|-lui\b")  # le tutoiement et « dis-lui » : une consigne au modèle, jamais une phrase dite au client (qui se vouvoie)
CLES_DES_CONSIGNES = ("a_faire",)  # la consigne que le retour d'une fiche donne au modèle
_APPELS_QUI_NE_SE_DISENT_PAS = {"debug", "info", "warning", "error", "exception", "critical", "opt", "log", "trace", "success"}


CONTINUATIONS = (" ", chr(9), chr(10), ",", ";", ":", ".", ")", "»", "?", "!")  # le début d'un morceau qui continue une phrase écrite en plusieurs morceaux


def _est_une_phrase(texte: str) -> bool:
    """Vrai pour un morceau de texte à lire par une personne : deux mots ou plus (ou une phrase courte qui finit par ``?``, ``!`` ou ``.``), en majuscule, ou en minuscule quand
    il continue une phrase. Une consigne au modèle (``dis-lui…``, un verbe en minuscule, sans espace devant) et un nom de clé n'en sont pas."""
    net = texte.strip()
    mots = [m for m in net.split() if _MOT.search(m) and "_" not in m and chr(92) not in m]
    if not mots or net.startswith("[.mark]") or _S_ADRESSE_AU_MODELE.search(net) or _SQL.match(texte):
        return False
    if len(mots) < 2 and not (net.endswith(("?", "!", ".")) and len(_MOT.findall(mots[0])[0]) >= 3):
        return False
    if texte.startswith(CONTINUATIONS):
        return True
    return net[0].isupper()


def _ne_se_dit_pas(noeud: ast.AST, parents: dict[int, ast.AST]) -> bool:
    """Le morceau est dans un message de journal (``logger.error(...)``) ou d'exception (``raise``), ou dans la consigne que le retour donne au modèle (``a_faire=...`` ou
    ``{"a_faire": ...}``) : lu par l'équipe technique ou par le modèle, jamais dit tel quel à la personne."""
    enfant = noeud
    while id(enfant) in parents:
        parent = parents[id(enfant)]
        if isinstance(parent, ast.Raise):
            return True
        if isinstance(parent, ast.Call) and isinstance(parent.func, ast.Attribute) and parent.func.attr in _APPELS_QUI_NE_SE_DISENT_PAS:
            return True
        if isinstance(parent, ast.Call) and (getattr(parent.func, "id", None) or getattr(parent.func, "attr", None)) in ENVOIS_POUR_L_EQUIPE:
            return True
        if isinstance(parent, ast.keyword) and parent.arg in CLES_DES_CONSIGNES:
            return True
        if isinstance(parent, ast.Dict):
            cles = [k.value for k, v in zip(parent.keys, parent.values) if v is enfant and isinstance(k, ast.Constant)]
            if any(c in CLES_DES_CONSIGNES for c in cles):
                return True
        enfant = parent
    return False


def phrases_du_fichier(chemin: str) -> list[tuple[int, str]]:
    """Les phrases dites au client écrites dans le fichier (voir la tête du module) ; un catalogue de secours n'en a aucune qui compte."""
    if NOM_D_UN_CATALOGUE_DE_SECOURS.search(chemin):
        return []
    arbre = ast.parse((I.RACINE_API / chemin).read_text(encoding="utf-8"))
    parents = {id(enfant): noeud for noeud in ast.walk(arbre) for enfant in ast.iter_child_nodes(noeud)}
    docstrings = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and noeud.body:
            premier = noeud.body[0]
            if isinstance(premier, ast.Expr) and isinstance(premier.value, ast.Constant) and isinstance(premier.value.value, str):
                docstrings.add(id(premier.value))
    trouvees = []
    for noeud in ast.walk(arbre):
        if not (isinstance(noeud, ast.Constant) and isinstance(noeud.value, str)) or id(noeud) in docstrings:
            continue
        if _est_une_phrase(noeud.value) and not _ne_se_dit_pas(noeud, parents):
            trouvees.append((noeud.lineno, noeud.value.strip()[:60]))
    return trouvees


def _cas(chemin: str):
    marques = [pytest.mark.xfail(strict=True, reason="phrases du code à rendre au modèle (lot 7b-C, outils/phrases-a-rendre-au-modele.md)")] if chemin in A_RENDRE else []
    return pytest.param(chemin, marks=marques, id=chemin)


@pytest.mark.parametrize("chemin", [_cas(c) for c in FICHIERS_DU_LOT])
def test_aucune_phrase_dite_par_le_code_hors_des_exceptions(chemin):
    trouvees = phrases_du_fichier(chemin)
    assert not trouvees, chr(10).join(f"{chemin}:{ligne} {texte}" for ligne, texte in trouvees)


SOURCE_D_ESSAI = '''"""Docstring qui ne compte pas du tout dans ce détecteur de phrases."""
CLE = "une_cle_tres_longue_sans_majuscule_du_tout_ici"
STATUT = "CHOIX_OBLIGATOIRE"
PHRASE = "Nous ne livrons pas à cette adresse pour le moment."
COURTE = "Combien exactement ?"
PIECE = f"{nom} n'est plus disponible."
SUITE = f"Il reste{n}, c'est tout pour la soirée"
CONSIGNE = "dis-lui avec tes mots que la commande est enregistrée"
RETOUR = {"a_faire": f"propose-lui {x} en une question", "raison": "x"}
LOG = logger.error(f"[.mark] La commande {n} n'a pas pu être lue")
SQL = "SELECT * FROM mark.resto_table WHERE site_id = $1"
EQUIPE = await secours_par_defaut(org, f"Commande {n} : risque", f"La commande {n} a été changée par le client")
'''


def test_le_detecteur_voit_les_phrases_courtes_et_les_morceaux_en_minuscule_et_ignore_le_reste(tmp_path, monkeypatch):
    """Vu rouge du détecteur : une phrase, une phrase courte et un morceau de phrase qui commence par une minuscule sont comptés ; un docstring, une clé, un statut, une consigne
    au modèle, un journal, du SQL et un texte pour l'équipe non."""
    source = tmp_path / "x.py"
    source.write_text(SOURCE_D_ESSAI, encoding="utf-8")
    monkeypatch.setattr(I, "RACINE_API", tmp_path)
    assert [t for _, t in phrases_du_fichier("x.py")] == [
        "Nous ne livrons pas à cette adresse pour le moment.", "Combien exactement ?", "n'est plus disponible.", "Il reste", ", c'est tout pour la soirée".strip(),
    ]


def test_un_catalogue_de_secours_est_exempte_par_son_nom_et_les_deux_connus_existent(tmp_path, monkeypatch):
    """Ce qui est exempté, c'est le fichier nommé ``textes_de_secours*.py`` ou ``phrases_du_manque.py`` (lu par le repli seul), jamais une phrase rangée ailleurs."""
    for chemin in CATALOGUES_DE_SECOURS:
        assert (I.RACINE_API / chemin).exists() and phrases_du_fichier(chemin) == [], chemin
    trouves = sorted(str(f.relative_to(I.RACINE_API)).replace("\\", "/") for dossier in ("services", "db") for f in (I.RACINE_API / dossier).rglob("*.py") if NOM_D_UN_CATALOGUE_DE_SECOURS.search(f.name))
    assert trouves == sorted(CATALOGUES_DE_SECOURS), "un nouveau catalogue de secours s'ajoute ici, avec sa raison"
    monkeypatch.setattr(I, "RACINE_API", tmp_path)
    (tmp_path / "phrases_rangees.py").write_text('P = "Nous ne livrons pas à cette adresse."', encoding="utf-8")
    assert phrases_du_fichier("phrases_rangees.py") != [], "ranger une phrase dans un fichier de n'importe quel nom ne l'exempte pas"


def test_la_liste_a_rendre_ne_nomme_que_des_fichiers_du_lot():
    assert A_RENDRE <= set(FICHIERS_DU_LOT)


def test_les_trois_blocs_a_rendre_se_partagent_les_fichiers_du_lot_sans_recouvrement():
    """Un fichier à rendre est dans UN bloc (C1, C2 ou C3) ; chaque bloc ne nomme que les fichiers de sa zone (la fiche de la 7b-C, § 6) : un agent ne touche que le sien."""
    blocs = (A_RENDRE_C1, A_RENDRE_C2, A_RENDRE_C3)
    assert sum(len(b) for b in blocs) == len(A_RENDRE), "un fichier est dans deux blocs"
    assert all(f.startswith("services/commande/") for f in A_RENDRE_C1)
    assert A_RENDRE_C2 <= {"db/bases_clients/restauration_commande.py", "services/restauration/source_commande.py"}
    assert all(f.startswith(("services/reservation/", "services/restauration/carte_et_allergenes/")) or f == "db/bases_clients/restauration_reservation.py" for f in A_RENDRE_C3)
