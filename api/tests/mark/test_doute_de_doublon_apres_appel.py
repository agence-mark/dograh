"""[.mark] Builder partie 3, SA-17d : l'après-appel pose le doute de doublon et le mail déclaré (migration 024).

Vraie base du client, vrai chemin ``mark.recevoir_appel`` (le même que l'après-appel du fork).

| Test | Ce qu'il prouve |
|---|---|
| numéro connu | un numéro connu retrouve sa fiche, sans doute, sans fiche de plus |
| même mail, autre numéro | une NOUVELLE fiche « à vérifier » (doublon_de, raison) ; la fiche existante est inchangée |
| même mail, fiche sans numéro | la fiche est retrouvée par le mail et reçoit le numéro, sans doute |
| même nom, autre mail | doute « même nom » ; même nom et même mail = la même personne |
| mail déclaré | un mail laissé sur le site est marqué ; au téléphone il ne l'est pas |
| rien d'écrasé | un mail, un nom, un prénom déjà connus ne bougent pas ; seuls les champs vides se complètent |
| rejeu | rejouer un appel ne crée rien ; un second appel du numéro d'un doublon retrouve le doublon |
| dossier de l'agent | un doublon à vérifier n'est pas mémorisé (D209) tant que le doute tient |
| cloisonnement | le doute d'un client ne voit jamais les fiches d'un autre |
| migration | la descente remet la fonction de la 022 (plus de doute), la montée la rétablit, rejouable |
"""

from __future__ import annotations

import uuid
from pathlib import Path

import asyncpg
import pytest

from api.db.bases_clients import apres_appel as sql
from api.db.bases_clients import connexion as schema
from api.db.bases_clients import dossier as sql_dossier
from api.tests.mark.test_apres_appel import _envoi
from api.tests.mark.test_base_client import _serveur, base_essai, base_prete  # noqa: F401

DESCENTE = Path(schema.__file__).parent / "migrations" / "descentes" / "024-descente.sql"


async def _appeler(base, *envois):
    c = await schema.connecter(base)
    try:
        return [await sql.recevoir_appel(c, e) for e in envois]
    finally:
        await c.close()


async def _fiche(base, contact_id):
    c = await schema.connecter(base)
    try:
        ligne = await c.fetchrow(
            "SELECT nom, prenom, mail, mail_declare, doublon_de, doublon_raison, "
            "(SELECT array_agg(numero ORDER BY numero) FROM mark.telephone WHERE contact_id = c.id) AS numeros "
            "FROM mark.contact c WHERE id = $1",
            contact_id,
        )
        return dict(ligne)
    finally:
        await c.close()


async def _nb_contacts(base):
    c = await schema.connecter(base)
    try:
        return await c.fetchval("SELECT count(*) FROM mark.contact")
    finally:
        await c.close()


def _site(run, mail, nom=None, **plus):
    contact = {"mail": mail, **({"nom": nom} if nom else {})}
    return _envoi(run, numero=None, canal="site", contact=contact, demande=None, **plus)


async def test_un_numero_connu_retrouve_sa_fiche(base_prete):
    (a,) = await _appeler(base_prete, _envoi(1, numero="+33611111111", contact={"nom": "Dupont"}))
    (b,) = await _appeler(base_prete, _envoi(2, numero="+33611111111", contact={"nom": "Dupont"}))
    assert b["contact_id"] == a["contact_id"]
    assert await _nb_contacts(base_prete) == 1
    fiche = await _fiche(base_prete, a["contact_id"])
    assert fiche["doublon_de"] is None and fiche["doublon_raison"] is None


async def test_meme_mail_autre_numero_est_un_doublon_a_verifier(base_prete):
    (a,) = await _appeler(
        base_prete, _envoi(1, numero="+33611111111", contact={"nom": "Dupont", "mail": "Alex@Exemple.fr"})
    )
    avant = await _fiche(base_prete, a["contact_id"])
    (b,) = await _appeler(
        base_prete, _envoi(2, numero="+33622222222", contact={"nom": "Autre", "mail": " alex@exemple.FR "})
    )
    assert b["contact_id"] != a["contact_id"]
    doute = await _fiche(base_prete, b["contact_id"])
    assert doute["doublon_de"] == a["contact_id"] and doute["doublon_raison"] == "même mail, autre numéro"
    assert doute["numeros"] == ["+33622222222"]
    # La fiche existante n'a rien reçu : ni numéro, ni doute, ni champ changé.
    assert await _fiche(base_prete, a["contact_id"]) == avant
    # L'appel suivant du même numéro retrouve le doublon (pas de troisième fiche).
    (c,) = await _appeler(base_prete, _envoi(3, numero="+33622222222", contact={"mail": "alex@exemple.fr"}))
    assert c["contact_id"] == b["contact_id"] and await _nb_contacts(base_prete) == 2


async def test_meme_mail_sur_une_fiche_sans_numero_la_retrouve(base_prete):
    (v,) = await _appeler(base_prete, _site(1, "visiteur@exemple.fr", nom="Visiteur"))
    (t,) = await _appeler(base_prete, _envoi(2, numero="+33633333333", contact={"mail": "VISITEUR@exemple.fr"}))
    assert t["contact_id"] == v["contact_id"] and await _nb_contacts(base_prete) == 1
    fiche = await _fiche(base_prete, v["contact_id"])
    assert fiche["numeros"] == ["+33633333333"] and fiche["doublon_de"] is None


async def test_meme_nom_autre_mail_est_un_doute_et_meme_mail_non(base_prete):
    (a,) = await _appeler(
        base_prete, _envoi(1, numero="+33611111111", contact={"nom": "Martin", "mail": "m1@exemple.fr"})
    )
    (b,) = await _appeler(
        base_prete, _envoi(2, numero="+33622222222", contact={"nom": " martin ", "mail": "m2@exemple.fr"})
    )
    doute = await _fiche(base_prete, b["contact_id"])
    assert doute["doublon_de"] == a["contact_id"] and doute["doublon_raison"] == "même nom"
    # Un visiteur du site de même nom, autre mail : un doute aussi.
    (s,) = await _appeler(base_prete, _site(3, "m3@exemple.fr", nom="Martin"))
    assert (await _fiche(base_prete, s["contact_id"]))["doublon_de"] == a["contact_id"]
    # Même nom et même mail, autre numéro : le mail l'emporte, c'est le doute du mail (pas du nom).
    (d,) = await _appeler(
        base_prete, _envoi(4, numero="+33644444444", contact={"nom": "Martin", "mail": "m1@exemple.fr"})
    )
    assert (await _fiche(base_prete, d["contact_id"]))["doublon_raison"] == "même mail, autre numéro"


async def test_meme_nom_sans_mail_de_part_et_d_autre_n_est_pas_un_doute(base_prete):
    (a,) = await _appeler(base_prete, _envoi(1, numero="+33611111111", contact={"nom": "Durand"}))
    (b,) = await _appeler(base_prete, _envoi(2, numero="+33622222222", contact={"nom": "Durand"}))
    assert b["contact_id"] != a["contact_id"]
    assert (await _fiche(base_prete, b["contact_id"]))["doublon_de"] is None


async def test_le_mail_laisse_sur_le_site_est_declare_pas_celui_dicte_au_telephone(base_prete):
    (s,) = await _appeler(base_prete, _site(1, "Site@Exemple.fr"))
    (t,) = await _appeler(base_prete, _envoi(2, numero="+33611111111", contact={"mail": "tel@exemple.fr"}))
    fiche_site = await _fiche(base_prete, s["contact_id"])
    assert fiche_site["mail"] == "site@exemple.fr" and fiche_site["mail_declare"] is True
    assert (await _fiche(base_prete, t["contact_id"]))["mail_declare"] is False


async def test_un_contact_existant_n_a_jamais_de_champ_ecrase(base_prete):
    (a,) = await _appeler(
        base_prete, _envoi(1, numero="+33611111111", contact={"nom": "Dupont", "prenom": "Alex", "mail": "a@exemple.fr"})
    )
    avant = await _fiche(base_prete, a["contact_id"])
    # Le même numéro revient depuis le site avec un autre nom, un autre prénom, un autre mail.
    await _appeler(
        base_prete,
        _envoi(2, numero="+33611111111", canal="site",
               contact={"nom": "Autre", "prenom": "Bob", "mail": "b@exemple.fr"}),
    )
    assert await _fiche(base_prete, a["contact_id"]) == avant
    # Ce qui manque se complète, une fois, et le mail du site est alors déclaré.
    (v,) = await _appeler(base_prete, _envoi(3, numero="+33622222222", contact={"nom": "Vide"}))
    await _appeler(
        base_prete,
        _envoi(4, numero="+33622222222", canal="site", contact={"nom": "Changé", "prenom": "Zoé", "mail": "z@exemple.fr"}),
    )
    fiche = await _fiche(base_prete, v["contact_id"])
    assert (fiche["nom"], fiche["prenom"], fiche["mail"], fiche["mail_declare"]) == ("Vide", "Zoé", "z@exemple.fr", True)
    await _appeler(
        base_prete, _envoi(5, numero="+33622222222", canal="site", contact={"mail": "autre@exemple.fr"})
    )
    assert (await _fiche(base_prete, v["contact_id"]))["mail"] == "z@exemple.fr"


async def test_rejouer_un_appel_ne_cree_rien_de_plus(base_prete):
    await _appeler(base_prete, _envoi(1, numero="+33611111111", contact={"nom": "Dupont", "mail": "a@exemple.fr"}))
    envoi = _envoi(2, numero="+33622222222", contact={"nom": "X", "mail": "a@exemple.fr"})
    (premier,) = await _appeler(base_prete, envoi)
    (rejoue,) = await _appeler(base_prete, envoi)
    assert rejoue["doublon"] is True and rejoue["contact_id"] == premier["contact_id"]
    assert await _nb_contacts(base_prete) == 2
    assert (await _fiche(base_prete, premier["contact_id"]))["doublon_de"] is not None


async def test_un_doublon_a_verifier_n_est_pas_memorise_jusqu_a_ce_qu_il_soit_tranche(base_prete):
    await _appeler(base_prete, _envoi(1, numero="+33611111111", contact={"nom": "Dupont", "mail": "a@exemple.fr"}))
    (b,) = await _appeler(
        base_prete, _envoi(2, numero="+33622222222", contact={"nom": "X", "mail": "a@exemple.fr"})
    )
    c = await schema.connecter(base_prete)
    try:
        dossier = await sql_dossier.lire_dossier(c, b["contact_id"])
        assert dossier["demandes"] == [] and dossier["references"] == []
        # Tranché (« ce n'est pas la même personne ») : la fiche est de nouveau mémorisée.
        await c.execute("UPDATE mark.contact SET doublon_de = NULL, doublon_raison = NULL WHERE id = $1", b["contact_id"])
        assert len((await sql_dossier.lire_dossier(c, b["contact_id"]))["demandes"]) == 1
    finally:
        await c.close()


async def test_le_doute_ne_traverse_pas_les_clients(base_prete, base_essai):  # noqa: F811
    seconde = f"mark_essai_{uuid.uuid4().hex[:10]}"
    await schema.creer_base(seconde)
    try:
        await _appeler(base_prete, _envoi(1, numero="+33611111111", contact={"nom": "Martin", "mail": "m@exemple.fr"}))
        # Même mail, même nom, autre numéro, mais chez un AUTRE client : aucun doute, aucune fiche partagée.
        (b,) = await _appeler(seconde, _envoi(2, numero="+33622222222", contact={"nom": "Martin", "mail": "m@exemple.fr"}))
        assert (await _fiche(seconde, b["contact_id"]))["doublon_de"] is None
        assert await _nb_contacts(seconde) == 1 and await _nb_contacts(base_prete) == 1
    finally:
        c = await asyncpg.connect(f"{_serveur()}/postgres", timeout=5)
        try:
            await c.execute(f'DROP DATABASE IF EXISTS "{seconde}" WITH (FORCE)')
            for suffixe in ("portail", "salarie", "direction", "interface", "ecriture", "portail_c"):
                await c.execute(f'DROP ROLE IF EXISTS "{seconde}_{suffixe}"')
        finally:
            await c.close()


async def test_la_migration_024_monte_et_descend(base_prete):
    assert schema.version_attendue() >= 24
    corps = next(m for m in schema.migrations() if m.version == 24).sql
    corps = corps[: corps.index("INSERT INTO schema_version")]
    proprietaire = await schema.connecter_proprietaire(base_prete)
    c = await schema.connecter(base_prete)
    try:
        # Montée : le doute existe.
        assert await schema.version_de(c) == schema.version_attendue()
        # Descente : la fonction de la 022 revient, plus aucun doute posé, la version 24 est oubliée.
        async with proprietaire.transaction():
            await proprietaire.execute(DESCENTE.read_text(encoding="utf-8"))
        assert await c.fetchval("SELECT count(*) FROM mark.schema_version WHERE version = 24") == 0
        assert await c.fetchval("SELECT to_regclass('mark.contact_nom_minuscules_idx')") is None
        await sql.recevoir_appel(c, _envoi(1, numero="+33611111111", contact={"nom": "A", "mail": "a@exemple.fr"}))
        b = await sql.recevoir_appel(c, _envoi(2, numero="+33622222222", contact={"nom": "B", "mail": "a@exemple.fr"}))
        assert await c.fetchval("SELECT doublon_de FROM mark.contact WHERE id = $1", b["contact_id"]) is None
        # Remontée, deux fois (rejouable) : le doute revient.
        for _ in range(2):
            async with proprietaire.transaction():
                await proprietaire.execute(corps)
        d = await sql.recevoir_appel(c, _envoi(3, numero="+33633333333", contact={"nom": "C", "mail": "a@exemple.fr"}))
        assert await c.fetchval("SELECT doublon_de FROM mark.contact WHERE id = $1", d["contact_id"]) is not None
    finally:
        await c.close()
        await proprietaire.close()
