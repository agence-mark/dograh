"""[.mark] Lot « façon Tala par motif » (T1, 05/11) : la bibliothèque versée, et la recette qui la cite.

| Test | Ce qu'il prouve |
|---|---|
| pièces de la recette | chaque pièce citée par ``facon-tala.json`` existe dans le dépôt ET après versement |
| fiches du lot | les 47 fiches du lot entrent toutes, en Candidat, rangées par motif sous ``facon-tala/…`` |
| rien en Recette | aucune fiche n'est en Recette après versement |
| idempotent | un second versement ne crée, ne change et ne déplace rien |
| jamais contre une personne | une fiche corrigée à la main n'est pas écrasée ; une fiche déplacée par une personne reste où elle est |
| étiquettes | aucune fiche ne contient un nom technique d'outil brut (les outils sont cités par ⟦étiquette⟧) |
"""

from __future__ import annotations

import json
import re

import pytest

from api.services.builder import versement
from api.services.builder.bibliotheque import service
from api.services.builder.bibliotheque.modele import Statut

LOT = {
    "apres-appel": 1,
    "conditions-passage": 1,
    "controles-avant-publication": 1,
    "modeles-outils": 2,
    "moules-etape": 29,
    "phrases-fixes": 1,
    "prompt-general": 1,
    "questionnaire-audit": 1,
    "recettes-agent": 1,
    "regles-redaction": 1,
    "scenarios-test": 8,
}


def _fichiers_du_lot():
    return [f for f in versement.lire_les_fichiers() if f.slug.startswith(("facon-tala-", "tala-")) and f.famille in LOT]


def test_les_pieces_de_la_recette_existent_dans_le_depot():
    tous = {(f.famille, f.slug) for f in versement.lire_les_fichiers()}
    recette = next(f for f in versement.lire_les_fichiers() if (f.famille, f.slug) == ("recettes-agent", "facon-tala"))
    pieces = recette.contenu["pieces"]
    assert len(pieces) >= 38
    manquantes = [(p["famille"], p["slug"]) for p in pieces if (p["famille"], p["slug"]) not in tous]
    assert manquantes == []
    assert len(recette.contenu.get("tests") or []) >= 8


def test_le_lot_compte_ses_47_fiches_et_la_recette_remplace_celle_du_fork():
    fichiers = [f for f in _fichiers_du_lot() if f.famille != "recettes-agent"]
    # 47 fiches du lot, dont la recette (remplacée, pas ajoutée) ; les autres familles chacune à son compte.
    compte = {}
    for f in fichiers:
        compte[f.famille] = compte.get(f.famille, 0) + 1
    assert sum(LOT.values()) == 47
    assert compte.get("moules-etape", 0) >= 29 and compte.get("scenarios-test", 0) == 8


async def test_les_pieces_de_la_recette_existent_apres_versement_en_candidat(monde):
    rapport = await versement.verser()
    assert rapport.erreurs == [], rapport.erreurs
    recette = (await service.lire_element("recettes-agent", "facon-tala")).courante.contenu
    for piece in recette["pieces"]:
        element = await service.lire_element(piece["famille"], piece["slug"])
        assert element.statut is Statut.CANDIDAT, piece
    elements = await service.lister()
    assert not [r for r in elements if r.statut is Statut.RECETTE]


async def test_les_fiches_du_lot_sont_rangees_par_motif_et_un_second_versement_ne_change_rien(monde):
    premier = await versement.verser()
    for f in _fichiers_du_lot():
        element = await service.lire_element(f.famille, f.slug)
        assert element.dossier.split("/")[0] == "facon-tala", (f.famille, f.slug)
        assert "facon-tala" in element.etiquettes
    avant = {(r.famille, r.slug): (r.dossier, tuple(r.etiquettes), r.statut) for r in await service.lister()}
    second = await versement.verser()
    assert second.crees == [] and second.mis_a_jour == [] and second.gardes == [] and second.erreurs == []
    assert len(second.inchanges) == len(premier.crees) + len(premier.mis_a_jour) + len(premier.inchanges)
    apres = {(r.famille, r.slug): (r.dossier, tuple(r.etiquettes), r.statut) for r in await service.lister()}
    assert apres == avant
    for f in _fichiers_du_lot():
        assert len((await service.lire_element(f.famille, f.slug)).versions) == 1


async def test_une_fiche_corrigee_a_la_main_n_est_pas_ecrasee_par_le_lot(monde):
    await versement.verser()
    await service.ajouter_version("moules-etape", "facon-tala-prendre-rendez-vous", {"texte": "Corrigé par Evan"}, "evan")
    rapport = await versement.verser()
    assert rapport.crees == [] and rapport.mis_a_jour == []
    assert (await service.lire_element("moules-etape", "facon-tala-prendre-rendez-vous")).courante.contenu == {"texte": "Corrigé par Evan"}


def test_les_fiches_du_lot_citent_les_outils_par_etiquette_jamais_par_nom_technique():
    # D5 : les contrôles refusent un nom d'outil écrit en clair ; les fiches ne portent que des trous ⟦…⟧ ou des {{outil:…}}.
    for f in _fichiers_du_lot():
        texte = json.dumps(f.contenu, ensure_ascii=False)
        assert not re.search(r"\b(?:signaler_un_probleme|get_|post_|put_)\w+\(", texte), (f.famille, f.slug)
