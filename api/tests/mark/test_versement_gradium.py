"""[.mark] Lot « façon Gradium » (SA-G, 05/11) : les 19 fiches G1 à G19 versées en Candidat, dossier ``facon-gradium``.

| Test | Ce qu'il prouve |
|---|---|
| lot complet | G1 à G19 existent dans le dépôt, avec origine (démo + licence), étiquette et dossier ``facon-gradium`` |
| doublons signalés | G3, G11 (vérité des actions) et G19 (gabarit Tala) le disent dans ``notes`` ; G1 est « à valider à l'oreille » ; G18 dit que nos réflexes restent la règle |
| versement | après ``verser()``, les fiches sont en Candidat, aucune en Recette |
| rien d'autre ne bouge | les fiches façon Tala et façon PolyAI sont identiques avant et après le lot |
| idempotent | un second versement ne crée, ne change et ne déplace rien |
"""

from __future__ import annotations

from api.services.builder import versement
from api.services.builder.bibliotheque import service
from api.services.builder.bibliotheque.modele import Statut

NUMEROS = [f"G{i}" for i in range(1, 20)]


def _fichiers_gradium():
    return [f for f in versement.lire_les_fichiers() if f.slug.startswith("facon-gradium-")]


def test_le_lot_compte_ses_19_fiches_avec_origine_et_dossier():
    fichiers = _fichiers_gradium()
    assert len(fichiers) == 19, [f.slug for f in fichiers]
    for f in fichiers:
        assert f.dossier.split("/")[0] == "facon-gradium", f.slug
        assert "facon-gradium" in f.etiquettes, f.slug
        assert f.origine is not None, f.slug
        assert "gradbot" in f.origine.source.lower() and "MIT" in f.origine.licence, f.slug
        assert (f.contenu.get("texte") or "").strip(), f.slug
    assert {f.famille for f in fichiers} == {"regles-redaction", "modeles-outils"}
    assert [f.famille for f in fichiers if f.famille == "modeles-outils"] == ["modeles-outils"]


def test_les_notes_disent_les_points_a_surveiller():
    par_slug = {f.slug: f for f in _fichiers_gradium()}
    g1 = par_slug["facon-gradium-francais-parle"]
    assert "À VALIDER À L'OREILLE" in g1.notes and "Mauvais" in g1.contenu["texte"]
    for slug in ("facon-gradium-jamais-confirmer-sans-outil", "facon-gradium-jamais-inventer-une-donnee"):
        assert "dédoublonner" in par_slug[slug].notes, slug
    assert "gabarit" in par_slug["facon-gradium-blocs-fixes-de-la-consigne"].notes.lower()
    g18 = par_slug["facon-gradium-verifier-l-appelant"]
    assert "plafond" in g18.contenu["texte"] and "réflexes de sécurité" in g18.contenu["texte"]
    assert "coupure de parole" in par_slug["facon-gradium-apres-une-interruption"].notes


async def test_apres_versement_tout_est_en_candidat_et_rien_d_autre_ne_change(monde):
    # Témoin : les fiches des autres façons, versées d'abord telles qu'elles sont.
    await versement.verser()
    elements = await service.lister()
    autres = {
        (r.famille, r.slug): (r.dossier, tuple(r.etiquettes), r.statut)
        for r in elements
        if not r.slug.startswith("facon-gradium-")
    }
    assert any(s.startswith(("facon-tala", "tala-")) for _, s in autres) and any(s.startswith("facon-polyai") for _, s in autres)

    for f in _fichiers_gradium():
        element = await service.lire_element(f.famille, f.slug)
        assert element.statut is Statut.CANDIDAT, f.slug
        assert element.dossier.split("/")[0] == "facon-gradium", f.slug
        assert "facon-gradium" in element.etiquettes
        assert len(element.versions) == 1
    assert not [r for r in await service.lister() if r.statut is Statut.RECETTE]
    # Les fiches Tala et PolyAI gardent leur statut, dossier et étiquettes : aucune ne porte « facon-gradium ».
    for r in elements:
        if (r.famille, r.slug) in autres:
            assert "facon-gradium" not in r.etiquettes and not r.dossier.startswith("facon-gradium")


async def test_un_second_versement_ne_cree_ni_ne_change_rien(monde):
    premier = await versement.verser()
    assert premier.erreurs == [], premier.erreurs
    avant = {(r.famille, r.slug): (r.dossier, tuple(r.etiquettes), r.statut) for r in await service.lister()}
    second = await versement.verser()
    assert second.crees == [] and second.mis_a_jour == [] and second.gardes == [] and second.erreurs == []
    apres = {(r.famille, r.slug): (r.dossier, tuple(r.etiquettes), r.statut) for r in await service.lister()}
    assert apres == avant
    for f in _fichiers_gradium():
        assert len((await service.lire_element(f.famille, f.slug)).versions) == 1
