"""[.mark] Builder partie 2 (§ 6 bis) : le module de versement de la bibliothèque.

| Test | Ce qu'il prouve |
|---|---|
| fichiers du dépôt | chaque fichier de ``versement/contenu`` est lisible, dans une famille connue, sous le plafond de taille |
| idempotent | deux versements de suite : créé, puis inchangé ; une seule version |
| mise à jour | un contenu changé dans le dépôt entre comme version suivante, Candidat, si la courante vient du versement |
| jamais contre une personne | une version écrite par une personne n'est pas écrasée (``gardes``) |
| sans bibliothèque | rien n'est versé, et c'est dit |
| démarrage | le script de démarrage du conteneur joue le versement après les migrations, sans bloquer |
"""

from __future__ import annotations

import json
from pathlib import Path

from api.services.builder import versement
from api.services.builder.bibliotheque import service
from api.services.builder.bibliotheque.modele import Statut, verifier_contenu

RACINE = Path(__file__).resolve().parents[3]


def _ecrire(dossier: Path, famille: str, slug: str, contenu: dict, titre: str = "Titre") -> None:
    (dossier / famille).mkdir(parents=True, exist_ok=True)
    (dossier / famille / f"{slug}.json").write_text(json.dumps({"titre": titre, "contenu": contenu}), encoding="utf-8")


def test_les_fichiers_du_depot_sont_lisibles_et_bornes():
    fichiers = versement.lire_les_fichiers()
    assert any(f.famille == "methode-builder" and f.slug == "methode" for f in fichiers)
    for f in fichiers:
        verifier_contenu(f.contenu)


async def test_deux_versements_de_suite_ne_creent_qu_une_version(monde, tmp_path):
    _ecrire(tmp_path, "methode-builder", "essai", {"texte": "a"})
    assert (await versement.verser(tmp_path)).crees == ["methode-builder/essai"]
    assert (await versement.verser(tmp_path)).inchanges == ["methode-builder/essai"]
    assert len((await service.lire_element("methode-builder", "essai")).versions) == 1


async def test_un_contenu_change_dans_le_depot_entre_comme_version_suivante(monde, tmp_path):
    _ecrire(tmp_path, "methode-builder", "essai", {"texte": "a"})
    await versement.verser(tmp_path)
    _ecrire(tmp_path, "methode-builder", "essai", {"texte": "b"})
    assert (await versement.verser(tmp_path)).mis_a_jour == ["methode-builder/essai"]
    element = await service.lire_element("methode-builder", "essai")
    assert element.courante.contenu == {"texte": "b"} and element.statut is Statut.CANDIDAT and len(element.versions) == 2


async def test_une_version_ecrite_par_une_personne_n_est_jamais_ecrasee(monde, tmp_path):
    _ecrire(tmp_path, "methode-builder", "essai", {"texte": "a"})
    await versement.verser(tmp_path)
    await service.ajouter_version("methode-builder", "essai", {"texte": "corrigé par Evan"}, "evan")
    _ecrire(tmp_path, "methode-builder", "essai", {"texte": "c"})
    rapport = await versement.verser(tmp_path)
    assert rapport.gardes == ["methode-builder/essai"]
    assert (await service.lire_element("methode-builder", "essai")).courante.contenu == {"texte": "corrigé par Evan"}


async def test_sans_bibliotheque_rien_n_est_verse_et_c_est_dit(monde, monkeypatch, tmp_path):
    monkeypatch.delenv("MARK_BIBLIOTHEQUE_ORGANISATION_ID")
    _ecrire(tmp_path, "methode-builder", "essai", {"texte": "a"})
    rapport = await versement.verser(tmp_path)
    assert rapport.non_configure is True and not rapport.crees


def test_une_famille_inconnue_est_refusee(tmp_path):
    import pytest

    _ecrire(tmp_path, "famille-inventee", "x", {"texte": "a"})
    with pytest.raises(ValueError, match="famille inconnue"):
        versement.lire_les_fichiers(tmp_path)


def test_le_demarrage_du_conteneur_joue_le_versement_apres_les_migrations_sans_bloquer():
    script = (RACINE / "scripts" / "start_services_docker.sh").read_text(encoding="utf-8")
    migrations = script.index("upgrade head")
    ligne = script.index("python -m api.scripts.mark.verser ||")
    assert migrations < ligne


async def test_au_demarrage_le_labo_marque_en_base_est_lu_avant_de_verser(monde, monkeypatch, tmp_path):
    """Lancé dans un processus neuf (script du conteneur), le cache du Labo est vide : le versement lit la base (C8)."""
    from unittest.mock import AsyncMock

    from api.services.equipe_mark import espaces
    from api.tests.mark.builder_commun import ORG_MARK

    monkeypatch.delenv("MARK_BIBLIOTHEQUE_ORGANISATION_ID")
    espaces.reinitialiser_cache()
    monkeypatch.setattr(espaces.db_client, "organisation_marquee_labo", AsyncMock(return_value=ORG_MARK))
    _ecrire(tmp_path, "methode-builder", "essai", {"texte": "a"})
    try:
        rapport = await versement.verser(tmp_path)
    finally:
        espaces.reinitialiser_cache()
    assert rapport.non_configure is False and rapport.crees
