"""[.mark] Lot 7b-C1 (point 3 de l'audit C0) : un catalogue de secours n'est lu que par le repli.

Un texte de secours est ce que le code dit quand le modèle se tait deux fois sur un refus (R = A) : il ne revient JAMAIS au modèle. Pour chaque fichier ``textes_de_secours*.py`` et
``phrases_du_manque.py``, la liste de ceux qui importent ses fonctions de texte est fermée : le repli, le chemin du fait bloquant, et chaque module qui refuse pour SA suggestion.
``Manque`` (la valeur fermée de ce qui manque) reste libre. Un importeur de plus rougit ce test ; les trois qui donnent encore le texte au modèle sont en échec attendu strict, nommés,
et la sous-tranche C4 les retire (un échec attendu qui passe est rouge).
"""

from __future__ import annotations

import ast
import re

import pytest

from api.outils import inventaire_rustines as I

CATALOGUE = re.compile(r"(?:^|/)(?:textes_de_secours[^/]*|phrases_du_manque)\.py$")
LIBRES = frozenset({"Manque", "MODE", "PORTEES_PAR_UNE_QUESTION"})  # la valeur fermée de ce qui manque : pas un texte

TOUS = "*"
# (catalogue, importeur, nom importé ou ``*``) : ce que chaque catalogue laisse lire, et par qui.
PERMIS = {
    ("services/commande/phrases_du_manque.py", "services/actions_communes/repli.py", "texte_a_dire"),  # le repli : ce qui manque ensuite
    ("services/commande/phrases_du_manque.py", "services/commande/porte.py", "phrase_du_manque"),  # le chemin du fait bloquant (``phrase_du_fait_bloquant_de``)
    ("services/commande/phrases_du_manque.py", "services/commande/moteur/enregistrement.py", "phrase_du_manque"),  # le module qui refuse écrit le manque (téléphone, prénom) : la phrase du catalogue, mot pour mot
    ("services/commande/phrases_du_manque.py", "services/commande/moteur/reglement.py", "phrase_du_manque"),  # idem : le moyen de paiement qui manque
    ("services/commande/phrases_du_manque.py", "services/commande/moteur/changement.py", "phrase_du_manque"),  # idem : l'adresse qui manque à un changement
    *{("services/commande/textes_de_secours.py", f"services/commande/moteur/{m}.py", TOUS)
      for m in ("articles", "changement", "enregistrement", "lecture", "mode_et_adresse", "prealables", "reglement")},
    ("services/commande/textes_de_secours.py", "services/commande/porte.py", TOUS),  # la porte refuse elle-même une heure proposée sans autre heure (``_repondre_a_l_heure_proposee``)
    # C2 : la base de la commande et sa source refusent elles-mêmes, avec leurs catalogues de secours
    ("db/bases_clients/textes_de_secours_commande.py", "db/bases_clients/restauration_commande.py", TOUS),  # la base qui refuse écrit le texte de secours de son refus
    ("db/bases_clients/textes_de_secours_commande.py", "services/restauration/source_commande.py", TOUS),  # la fermeture de l'état et l'envoi indisponible : texte de secours de la source
    ("services/commande/phrases_du_manque.py", "db/bases_clients/restauration_commande.py", "phrase_du_manque"),  # le manque que la base relaie, mot pour mot du catalogue
    ("services/commande/phrases_du_manque.py", "services/restauration/source_commande.py", "phrase_du_manque"),  # idem pour la source
    ("services/commande/textes_de_secours.py", "db/bases_clients/restauration_commande.py", TOUS),  # une seule source des textes en double (rupture, moyen refusé)
    ("services/commande/textes_de_secours.py", "db/bases_clients/textes_de_secours_commande.py", TOUS),  # la fermeture sans heure de reprise dit la phrase de la commande
    # C3 : la réservation et l'allergie refusent elles-mêmes ; la feuille de la réservation est lue par le moteur, la porte, la base et le catalogue du manque
    *{("services/reservation/textes_de_secours.py", f"services/reservation/{m}.py", TOUS) for m in ("moteur", "porte", "phrases_du_manque")},
    ("services/reservation/textes_de_secours.py", "db/bases_clients/restauration_reservation.py", TOUS),  # la base qui refuse écrit le texte de secours de son refus
    *{("services/restauration/carte_et_allergenes/textes_de_secours.py", f"services/restauration/carte_et_allergenes/{m}.py", TOUS) for m in ("allergie_de_la_commande", "voir_un_article")},
}
# Les importeurs qui donnent encore le texte au modèle : en échec attendu strict, nommés ; C4 les retire.
A_RETIRER_EN_C4 = {
    ("services/commande/phrases_du_manque.py", "services/commande/porte.py", "texte_a_dire"),  # ``DU.constater`` : ``texte_a_dire`` du retour
    ("services/reservation/phrases_du_manque.py", "services/reservation/porte.py", "texte_a_dire"),
    ("services/reservation/phrases_du_manque.py", "services/integrations/connectors/actions/reservation.py", "texte_a_dire"),
}


def _chemin(f) -> str:
    return str(f.relative_to(I.RACINE_API)).replace("\\", "/")


def _catalogues() -> list[str]:
    return sorted(_chemin(f) for d in ("services", "db") for f in (I.RACINE_API / d).rglob("*.py") if CATALOGUE.search(_chemin(f)))


def _module(chemin: str) -> str:
    return "api." + chemin[:-3].replace("/", ".")


def importeurs_des_textes() -> set[tuple[str, str, str]]:
    """Chaque ``(catalogue, importeur, nom)`` du code hors tests : ``nom`` est la fonction importée, ou ``*`` quand le module entier est importé."""
    modules = {_module(c): c for c in _catalogues()}
    trouves: set[tuple[str, str, str]] = set()
    for d in ("services", "db", "routes", "tasks", "mcp_server", "utils"):
        if not (I.RACINE_API / d).exists():
            continue
        for f in (I.RACINE_API / d).rglob("*.py"):
            importeur = _chemin(f)
            for noeud in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
                if isinstance(noeud, ast.ImportFrom) and noeud.module:
                    for alias in noeud.names:
                        direct = modules.get(noeud.module)
                        if direct and alias.name not in LIBRES:
                            trouves.add((direct, importeur, alias.name))
                        entier = modules.get(f"{noeud.module}.{alias.name}")
                        if entier:
                            trouves.add((entier, importeur, TOUS))
                elif isinstance(noeud, ast.Import):
                    trouves.update((modules[a.name], importeur, TOUS) for a in noeud.names if a.name in modules)
    return trouves


def test_la_liste_des_importeurs_d_un_catalogue_de_secours_est_fermee():
    inconnus = sorted(
        (c, i, n) for c, i, n in importeurs_des_textes()
        if (c, i, n) not in A_RETIRER_EN_C4 and (c, i, n) not in PERMIS and (c, i, TOUS) not in PERMIS
    )
    assert not inconnus, "un texte de secours n'est lu que par le repli, le fait bloquant, ou le module qui refuse : " + "; ".join(map(str, inconnus))


def test_chaque_catalogue_de_secours_a_ses_importeurs_declares():
    """Un nouveau catalogue (``textes_de_secours*.py``) déclare ses importeurs ici, avec le module qui refuse pour sa suggestion."""
    declares = {c for c, _, _ in PERMIS} | {c for c, _, _ in A_RETIRER_EN_C4}
    assert not [c for c in _catalogues() if c not in declares], sorted(set(_catalogues()) - declares)


@pytest.mark.parametrize("trio", sorted(A_RETIRER_EN_C4), ids=lambda t: f"{t[1]}:{t[2]}")
@pytest.mark.xfail(strict=True, reason="le texte arrive encore au modèle par cet importeur (7b-C4 le retire)")
def test_importeur_qui_donne_encore_le_texte_au_modele(trio):
    assert trio not in importeurs_des_textes()
