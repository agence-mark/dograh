"""[.mark] builder partie 2, D1 (U4, E45) : les modèles de réglages sont des éléments de la bibliothèque.

| Test | Ce qu'il prouve |
|---|---|
| stockage | un modèle gelé depuis un agent est un élément ``modeles-reglages`` (Candidat, auteur = le compte), au même contenu ``valeurs`` que lit le builder |
| renommer | le titre change, ni la version ni le statut (une Recette renommée reste une Recette) |
| supprimer | l'élément et son historique partent ; les agents déjà réglés gardent leur mention |
| rejeté | un modèle rejeté par une personne ne s'applique pas |
| versement | un fichier ``contenu/modeles-reglages/*.json`` est versé, listé et appliqué comme un modèle |
| reprise | les modèles déjà en base (par organisation) deviennent des éléments ; idempotente ; deux modèles de même nom ne s'écrasent pas ; une version écrite par une personne n'est jamais touchée ; les lignes d'origine restent |
| reprise, bornes | bibliothèque non réglée : rien et dit ; modèle trop gros pour la bibliothèque : nommé, non repris |
"""

import json

from api.enums import OrganizationConfigurationKey
from api.services.builder import versement
from api.services.builder.bibliotheque import service as bib
from api.services.builder.bibliotheque.modele import Banc, Statut
from api.services.modeles_reglages import bibliotheque as lib
from api.services.modeles_reglages import service as modeles
from api.tests.mark.test_modeles_de_reglages import CLE_SECRETE_A, ROUTE, _creer, monde  # noqa: F401

CLE_STOCK = OrganizationConfigurationKey.MODELES_REGLAGES.value


async def test_un_modele_gele_est_un_element_de_la_bibliotheque(monde, test_client_factory):  # noqa: F811
    async with test_client_factory(monde.user_a) as client:
        modele = await _creer(client, "Reglage de reference", monde.agent_a.id)
    assert modele["statut"] == "candidat" and modele["version"] == 1
    element = await bib.lire_element(lib.FAMILLE, modele["id"])
    assert element.titre == "Reglage de reference"
    assert element.courante.statut is Statut.CANDIDAT
    assert element.courante.auteur
    # Le contenu est celui que le builder applique : ``valeurs``, sans une seule clé d'accès.
    assert element.courante.contenu["valeurs"]["max_call_duration"] == 600
    assert CLE_SECRETE_A not in json.dumps(element.model_dump(mode="json"))
    assert "api_key" not in json.dumps(element.courante.contenu)
    # La liste commune de la bibliothèque le montre aussi (rubrique Bibliothèque › Modèles de réglages).
    assert [r.slug for r in await bib.lister(lib.FAMILLE)] == [modele["id"]]


async def test_renommer_ne_change_ni_la_version_ni_le_statut(monde, test_client_factory):  # noqa: F811
    async with test_client_factory(monde.user_a) as client:
        modele = await _creer(client, "Avant", monde.agent_a.id)
        await bib.marquer(lib.FAMILLE, modele["id"], 1, Statut.RECETTE, "personne", banc=Banc(description="joué au banc"))
        reponse = await client.patch(f"{ROUTE}/{modele['id']}", json={"nom": "Apres"})
    assert reponse.status_code == 200
    assert (reponse.json()["nom"], reponse.json()["statut"], reponse.json()["version"]) == ("Apres", "recette", 1)
    element = await bib.lire_element(lib.FAMILLE, modele["id"])
    assert len(element.versions) == 1 and element.slug == modele["id"]


async def test_supprimer_retire_l_element_mais_pas_la_mention_des_agents(monde, test_client_factory):  # noqa: F811
    async with test_client_factory(monde.user_a) as client:
        modele = await _creer(client, "A retirer", monde.agent_a.id)
        corps = {"workflow_id": monde.agent_a2.id, "sections": ["tour"], "a_blanc": False}
        assert (await client.post(f"{ROUTE}/{modele['id']}/appliquer", json=corps)).status_code == 200
        assert (await client.delete(f"{ROUTE}/{modele['id']}")).status_code == 204
        mention = (await client.get(f"{ROUTE}/agent/{monde.agent_a2.id}")).json()["mention"]
    assert mention["nom"] == "A retirer"
    assert await bib.element_ou_none(lib.FAMILLE, modele["id"]) is None


async def test_un_modele_rejete_ne_s_applique_pas(monde, test_client_factory, db_session):  # noqa: F811
    async with test_client_factory(monde.user_a) as client:
        modele = await _creer(client, "Mauvais", monde.agent_a.id)
        await bib.marquer(lib.FAMILLE, modele["id"], 1, Statut.REJETE, "personne", raison="trop lent")
        corps = {"workflow_id": monde.agent_a2.id, "sections": ["tour"], "a_blanc": False}
        reponse = await client.post(f"{ROUTE}/{modele['id']}/appliquer", json=corps)
    assert reponse.status_code == 422 and "trop lent" in reponse.text
    assert await db_session.get_draft_version(monde.agent_a2.id) is None


async def test_un_fichier_du_depot_est_verse_liste_et_applique_comme_un_modele(monde, test_client_factory, tmp_path):  # noqa: F811
    dossier = tmp_path / "modeles-reglages"
    dossier.mkdir()
    (dossier / "tour-court.json").write_text(
        json.dumps(
            {
                "titre": "Tour court",
                "contenu": {"valeurs": {"turn_start_strategy": "min_words", "turn_start_min_words": 3}, "sections": ["tour"]},
            }
        ),
        encoding="utf-8",
    )
    rapport = await versement.verser(tmp_path)
    assert rapport.crees == ["modeles-reglages/tour-court"] and not rapport.erreurs
    async with test_client_factory(monde.user_a) as client:
        liste = (await client.get(ROUTE)).json()["modeles"]
        assert [(m["id"], m["nom"], m["nombre_de_reglages"]) for m in liste] == [("tour-court", "Tour court", 2)]
        corps = {"workflow_id": monde.agent_a2.id, "sections": ["tour"], "a_blanc": False}
        assert (await client.post(f"{ROUTE}/tour-court/appliquer", json=corps)).status_code == 200
    # Rejoué : rien de plus.
    assert (await versement.verser(tmp_path)).inchanges == ["modeles-reglages/tour-court"]


async def _ligne_d_organisation(db_session, org: int, modeles_a_ranger: list[dict]):
    await db_session.upsert_configuration(org, CLE_STOCK, {"version": 1, "modeles": modeles_a_ranger, "applications": {}})


def _ancien(identifiant: str, nom: str, **valeurs):
    return {
        "id": identifiant,
        "nom": nom,
        "cree_le": "2026-10-01T10:00:00+00:00",
        "origine": {"workflow_id": 1, "agent_nom": "Agent", "version_number": 2, "version_status": "published"},
        "sections": ["tour"],
        "valeurs": valeurs or {"turn_start_min_words": 4},
    }


async def test_la_reprise_recopie_les_modeles_existants_sans_rien_ecraser(monde, db_session):  # noqa: F811
    await _ligne_d_organisation(db_session, monde.org_a.id, [_ancien("aaa111", "Standard", turn_start_min_words=4)])
    await _ligne_d_organisation(db_session, monde.org_b.id, [_ancien("bbb222", "Standard", turn_start_min_words=6)])
    premier = await lib.reprendre_les_existants()
    assert len(premier.repris) == 2 and not premier.gardes and not premier.trop_gros
    titres = sorted(e.titre for e in await lib.lister_les_elements())
    # Deux modèles de même nom ne s'écrasent pas : le second prend l'organisation d'origine.
    assert titres == sorted(["Standard", f"Standard (org. {monde.org_b.id})"])
    standard = next(e for e in await lib.lister_les_elements() if e.titre == "Standard")
    assert standard.courante.contenu["valeurs"] == {"turn_start_min_words": 4}
    assert standard.courante.auteur.startswith("reprise:")
    assert standard.courante.contenu["origine"]["agent_nom"] == "Agent"
    # Idempotente : rejouée, rien de plus.
    second = await lib.reprendre_les_existants()
    assert not second.repris and len(second.deja_repris) == 2
    assert len(await lib.lister_les_elements()) == 2
    # Les lignes d'origine restent intactes (rien ne se supprime).
    ligne = await db_session.get_configuration(monde.org_a.id, CLE_STOCK)
    assert [m["id"] for m in ligne.value["modeles"]] == ["aaa111"]


async def test_la_reprise_ne_touche_jamais_ce_qu_une_personne_a_ecrit(monde, db_session):  # noqa: F811
    cree = await modeles.creer_un_modele(monde.org_a.id, "Standard", monde.agent_a.id, "user:42")
    avant = (await bib.lire_element(lib.FAMILLE, cree.id)).model_dump(mode="json")
    await _ligne_d_organisation(db_session, monde.org_b.id, [_ancien("bbb222", "Standard", turn_start_min_words=6)])
    rapport = await lib.reprendre_les_existants()
    # Le nom « Standard » est celui de la personne : la reprise prend un titre à elle, et l'élément de la personne reste tel quel.
    assert rapport.repris == [f"{monde.org_b.id}:Standard"]
    assert (await bib.lire_element(lib.FAMILLE, cree.id)).model_dump(mode="json") == avant


async def test_la_reprise_dit_ce_qu_elle_ne_peut_pas_faire(monde, db_session, monkeypatch):  # noqa: F811
    gros = {f"tts_replacements_{i}": "x" * 100 for i in range(150)}
    await _ligne_d_organisation(db_session, monde.org_a.id, [_ancien("ggg333", "Enorme", **gros)])
    rapport = await lib.reprendre_les_existants()
    assert rapport.trop_gros == [f"{monde.org_a.id}:Enorme"] and not rapport.repris
    monkeypatch.delenv("MARK_BIBLIOTHEQUE_ORGANISATION_ID")
    sans = await lib.reprendre_les_existants()
    assert sans.non_configure and not sans.repris


async def test_la_reprise_est_branchee_au_demarrage():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "scripts/mark/verser.py").read_text(encoding="utf-8")
    assert "reprendre_les_existants" in source


def test_chaque_section_du_serveur_a_son_titre_a_l_ecran():
    """Une section que le serveur range et que l'écran ne nomme pas s'afficherait sous son identifiant (cas d'« interventions »)."""
    import re
    from pathlib import Path

    from api.services.modeles_reglages import classement as cl

    source = (
        Path(__file__).resolve().parents[3] / "ui/src/components/mark/reglages-agent/modeles-de-reglages/ModaleModeles.tsx"
    ).read_text(encoding="utf-8")
    bloc = source.split("export const TITRES_DES_SECTIONS", 1)[1].split("\n};", 1)[0]
    titres = re.findall(r"^\s{4}(\w+):", bloc, re.M)
    assert sorted(titres) == sorted(cl.SECTIONS)
