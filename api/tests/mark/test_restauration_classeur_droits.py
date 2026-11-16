"""[.mark] Module Restauration, lot 1 : les droits du classeur (RLS par établissement) et ses déclencheurs.

Chaque test passe par une VRAIE connexion : le portail se connecte pour de bon avec son compte (``<base>_portail_c``)
et pose la variable de session, comme en production ; le fork se connecte en ``<base>_ecriture``.

| Test | Ce qu'il prouve |
|---|---|
| lecture par établissement | le portail de A (de B, de A et B, de tous) ne lit que ses lignes, sur CHAQUE table du module ; sans variable : rien ; la carte d'enseigne se lit dès qu'on voit un lieu |
| écriture | le portail écrit chez lui, jamais chez B (ni en déplaçant sa ligne) ; les tables qu'il ne fait que lire refusent toute écriture ; deux tables lui sont fermées |
| rôles fermés | PUBLIC, l'interface, les salariés et la direction n'ont aucun droit ; le fork lit tout |
| journal et version | auteur et source posés, écriture sans effet non journalisée, source du portail déduite, version de la carte augmentée (enseigne : tous) |
"""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from urllib.parse import urlsplit

import asyncpg
import pytest

from api.db.bases_clients import connexion as schema
from api.tests.mark.test_base_client import _serveur, base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_tables import TOUTES

MOT_DE_PASSE = "essai-resto-" + uuid.uuid4().hex[:8]

ENSEIGNE = ["resto_categorie", "resto_produit", "resto_declinaison", "resto_groupe_choix", "resto_option", "resto_formule", "resto_surcouche"]
# Ce que le portail peut faire de chaque table (contrat portail § 1, § 4).
PORTAIL_ECRIT = ENSEIGNE + ["resto_reglage_type", "resto_zone", "resto_client", "resto_remise", "resto_envoi", "resto_reglage",
                            "resto_salle", "resto_table", "resto_service", "resto_duree_groupe", "resto_regle_reservation", "resto_temps_recurrent", "resto_plan_soir"]
PORTAIL_LIT = ["resto_rupture", "resto_etat_caisse", "resto_commande", "resto_commande_ligne", "resto_liaison", "resto_reservation",
               "resto_journal", "resto_recap_jour", "resto_recap_jour_taux", "resto_remise_offre", "resto_version_carte", "resto_ticket"]
PORTAIL_RIEN = ["resto_message_recu", "resto_compteur_jour", "resto_liaison_acces", "resto_imprimante"]
assert sorted(PORTAIL_ECRIT + PORTAIL_LIT + PORTAIL_RIEN) == sorted(TOUTES)

# $1 site, $2 salle, $3 numéro de commande, $4 marque (unique par ligne)
SEMER = {
    "resto_categorie": "INSERT INTO mark.resto_categorie (site_id, portee, ref, nom) VALUES ($1, 'etablissement', 'c' || $4, 'Pizzas')",
    "resto_produit": "INSERT INTO mark.resto_produit (site_id, portee, ref, nom) VALUES ($1, 'etablissement', 'p' || $4, 'Margherita')",
    "resto_declinaison": "INSERT INTO mark.resto_declinaison (site_id, portee, ref, produit_ref, nom, code_caisse, prix) VALUES ($1, 'etablissement', 'd' || $4, 'p', 'Normale', 'K' || $4, 1000)",
    "resto_groupe_choix": "INSERT INTO mark.resto_groupe_choix (site_id, portee, ref, nom) VALUES ($1, 'etablissement', 'g' || $4, 'Sauce')",
    "resto_option": "INSERT INTO mark.resto_option (site_id, portee, ref, groupe_ref, nom) VALUES ($1, 'etablissement', 'o' || $4, 'g', 'Ketchup')",
    "resto_formule": "INSERT INTO mark.resto_formule (site_id, portee, ref, nom, prix) VALUES ($1, 'etablissement', 'f' || $4, 'Menu', 990)",
    "resto_surcouche": "INSERT INTO mark.resto_surcouche (site_id, objet, ref) VALUES ($1, 'produit', 'p' || $4)",
    "resto_rupture": "INSERT INTO mark.resto_rupture (site_id, code_caisse) VALUES ($1, 'K' || $4)",
    "resto_etat_caisse": "INSERT INTO mark.resto_etat_caisse (site_id) VALUES ($1)",
    "resto_reglage_type": "INSERT INTO mark.resto_reglage_type (site_id, type) VALUES ($1, 'emporter')",
    "resto_zone": "INSERT INTO mark.resto_zone (site_id, nom, forme) VALUES ($1, 'Z' || $4, 'communes')",
    "resto_commande": "INSERT INTO mark.resto_commande (numero, numero_court, site_id, mode, total) VALUES ($3, '1', $1, 'emporter', 1000)",
    "resto_commande_ligne": "INSERT INTO mark.resto_commande_ligne (numero, site_id, rang, code_caisse, nom, prix_unitaire, quantite) VALUES ($3, $1, 1, 'K', 'x', 1000, 1)",
    "resto_message_recu": "INSERT INTO mark.resto_message_recu (fournisseur, identifiant, site_id) VALUES ('hubrise', 'm' || $4, $1)",
    "resto_liaison": "INSERT INTO mark.resto_liaison (site_id, prise) VALUES ($1, 'hubrise')",
    "resto_liaison_acces": "INSERT INTO mark.resto_liaison_acces (site_id, credential_uuid) VALUES ($1, 'u' || $4)",
    "resto_imprimante": "INSERT INTO mark.resto_imprimante (site_id, jeton_empreinte) VALUES ($1, md5($4) || md5($4))",
    "resto_ticket": "INSERT INTO mark.resto_ticket (numero, site_id) VALUES ($3, $1)",
    "resto_compteur_jour": "INSERT INTO mark.resto_compteur_jour (site_id, jour) VALUES ($1, current_date + $4::text::int)",
    "resto_client": "INSERT INTO mark.resto_client (site_id, telephone) VALUES ($1, '+3360000' || lpad($4, 4, '0'))",
    "resto_remise": "INSERT INTO mark.resto_remise (site_id, nom, mecanisme) VALUES ($1, 'R', 'pourcentage')",
    "resto_remise_offre": "INSERT INTO mark.resto_remise_offre (site_id, remise_id, dite_le) VALUES ($1, (SELECT id FROM mark.resto_remise WHERE site_id = $1 LIMIT 1), now())",
    "resto_envoi": "INSERT INTO mark.resto_envoi (site_id, type, declencheur, texte) VALUES ($1, 'sms', 'commande', 'txt')",
    "resto_reglage": "INSERT INTO mark.resto_reglage (site_id) VALUES ($1)",
    "resto_salle": "INSERT INTO mark.resto_salle (site_id, nom) VALUES ($1, 'S')",
    "resto_table": "INSERT INTO mark.resto_table (site_id, salle_id, nom, couverts_max) VALUES ($1, $2, 'T', 4)",
    "resto_service": "INSERT INTO mark.resto_service (site_id, nom, debut, fin) VALUES ($1, 'midi', '11:00', '14:00')",
    "resto_duree_groupe": "INSERT INTO mark.resto_duree_groupe (site_id, couverts_min, couverts_max, duree_minutes) VALUES ($1, 1, 4, 60)",
    "resto_regle_reservation": "INSERT INTO mark.resto_regle_reservation (site_id) VALUES ($1)",
    "resto_reservation": "INSERT INTO mark.resto_reservation (numero, site_id, debut, duree_minutes, couverts) VALUES (gen_random_uuid(), $1, now(), 60, 2)",
    "resto_temps_recurrent": "INSERT INTO mark.resto_temps_recurrent (site_id, type, jours, debut, fin, minutes_ajoutees) VALUES ($1, 'emporter', '{1}', '19:00', '21:00', 10)",
    "resto_plan_soir": "INSERT INTO mark.resto_plan_soir (site_id, jour) VALUES ($1, current_date + $4::text::int)",
    "resto_recap_jour_taux": "INSERT INTO mark.resto_recap_jour_taux (site_id, jour, mode, taux) VALUES ($1, current_date + $4::text::int, 'emporter', 10000)",
    "resto_recap_jour": "INSERT INTO mark.resto_recap_jour (site_id, jour, mode) VALUES ($1, current_date, 'emporter')",
}
UNE_PAR_ETABLISSEMENT = {"resto_reglage_type", "resto_reglage", "resto_regle_reservation"}
# Écrites par déclencheur, jamais semées à la main.
PAR_DECLENCHEUR = {"resto_journal", "resto_version_carte"}
# La commande avant ses lignes.
ORDRE = sorted((t for t in TOUTES if t not in PAR_DECLENCHEUR), key=lambda t: 0 if t == "resto_commande" else 1)


async def _ecrire(c, table, site, salle, numero, marque):
    """Exécute la ligne semée de ``table`` : seuls les paramètres que l'ordre emploie sont passés."""
    ordre = SEMER[table]
    valeurs = (site, salle, numero, marque)
    pris = [valeurs[i] for i in range(4) if f"${i + 1}" in ordre]
    # les paramètres présents gardent leur rang : on renumérote
    for nouveau, i in enumerate([i for i in range(4) if f"${i + 1}" in ordre], start=1):
        ordre = ordre.replace(f"${i + 1}", f"$@{nouveau}")
    return await c.execute(ordre.replace("$@", "$"), *pris)


@pytest.fixture
async def classeur(base_prete):
    """Deux établissements ; chaque table du module a une ligne pour A, une pour B (+ une ligne d'enseigne)."""
    fork = await schema.connecter(base_prete)
    proprietaire = await schema.connecter_proprietaire(base_prete)
    try:
        await fork.execute("INSERT INTO mark.entreprise (raison_sociale) VALUES ('Entreprise')")
        graines = {}
        for cle, marque in (("site-a", "1"), ("site-b", "2")):
            site = await fork.fetchval(
                "INSERT INTO mark.site (entreprise_id, cle, nom, fuseau) SELECT id, $1, $1, 'Europe/Paris' FROM mark.entreprise RETURNING id", cle
            )
            salle = await fork.fetchval("INSERT INTO mark.resto_salle (site_id, nom) VALUES ($1, 'S0') RETURNING id", site)
            numero = uuid.uuid4()
            for t in ORDRE:
                await _ecrire(fork, t, site, salle, numero, marque)
            graines[cle] = SimpleNamespace(site=site, salle=salle, numero=numero, marque=marque)
        for t in ENSEIGNE:  # une ligne d'enseigne par table de la carte
            ordre = SEMER[t].replace("$1", "NULL").replace("'etablissement'", "'enseigne'").replace("$4", "'E'")
            await fork.execute(ordre)
        role = await proprietaire.fetchval("SELECT mark.donner_connexion_portail($1)", MOT_DE_PASSE)
        assert role == f"{base_prete}_portail_c"
        yield SimpleNamespace(base=base_prete, fork=fork, proprietaire=proprietaire, a=graines["site-a"], b=graines["site-b"])
    finally:
        await fork.close()
        await proprietaire.close()


async def _portail(base, sites):
    m = urlsplit(_serveur())
    hote = m.netloc.rsplit("@", 1)[-1]
    c = await asyncpg.connect(f"postgresql://{base}_portail_c:{MOT_DE_PASSE}@{hote}/{base}", timeout=5)
    if sites is not None:
        await c.execute("SELECT set_config('mark.sites_portail', $1, false)", sites)
    return c


async def test_le_portail_d_un_etablissement_ne_lit_que_les_lignes_de_cet_etablissement(classeur):
    for t in ORDRE:  # chaque table a une ligne pour chacun
        assert await classeur.fork.fetchval(f"SELECT count(DISTINCT site_id) FROM mark.{t} WHERE site_id IS NOT NULL") == 2, t
    a, b = classeur.a.site, classeur.b.site
    for sites, attendus in ((str(a), {a}), (str(b), {b}), (f"{a},{b}", {a, b}), ("*", {a, b})):
        c = await _portail(classeur.base, sites)
        try:
            for t in PORTAIL_ECRIT + PORTAIL_LIT:
                vus = {r["site_id"] for r in await c.fetch(f"SELECT DISTINCT site_id FROM mark.{t}")}
                assert vus - {None} == attendus, (sites, t, vus)
                if t not in ENSEIGNE and t != "resto_journal":
                    assert None not in vus, (sites, t)
        finally:
            await c.close()
    # variable absente ou vide : rien de lisible, nulle part (la carte d'enseigne non plus)
    for sites in (None, "", " "):
        c = await _portail(classeur.base, sites)
        try:
            for t in PORTAIL_ECRIT + PORTAIL_LIT:
                assert await c.fetchval(f"SELECT count(*) FROM mark.{t}") == 0, (sites, t)
        finally:
            await c.close()
    # la carte d'enseigne se lit dès qu'on voit un lieu
    c = await _portail(classeur.base, str(a))
    try:
        for t in ENSEIGNE:
            assert await c.fetchval(f"SELECT count(*) FROM mark.{t} WHERE site_id IS NULL") == 1, t
    finally:
        await c.close()


async def test_le_portail_n_ecrit_pas_chez_un_autre_etablissement_ni_dans_les_tables_en_lecture(classeur):
    a, b = classeur.a, classeur.b
    c = await _portail(classeur.base, str(a.site))
    try:
        for t in PORTAIL_ECRIT:
            # chez lui : permis (marque neuve, pour ne heurter aucun index unique) ...
            if t in UNE_PAR_ETABLISSEMENT:  # une seule ligne par établissement : il efface la sienne, puis la récrit
                assert (await c.execute(f"DELETE FROM mark.{t} WHERE site_id = $1", a.site)) == "DELETE 1"
            await _ecrire(c, t, a.site, a.salle, uuid.uuid4(), "9")
        for t in PORTAIL_ECRIT:
            # ... chez B : refusé par la politique de la table
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await _ecrire(c, t, b.site, b.salle, uuid.uuid4(), "8")
            # modifier ou effacer une ligne de B n'atteint rien
            assert (await c.execute(f"UPDATE mark.{t} SET maj_le = now() WHERE site_id = $1", b.site)) == "UPDATE 0", t
            assert (await c.execute(f"DELETE FROM mark.{t} WHERE site_id = $1", b.site)) == "DELETE 0", t
            # et il ne peut pas déplacer sa ligne chez B
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await c.execute(f"UPDATE mark.{t} SET site_id = $2 WHERE site_id = $1", a.site, b.site)
        for t in PORTAIL_LIT:  # il LIT : toute écriture est refusée, même chez lui
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await c.execute(f"DELETE FROM mark.{t}")
            if t in SEMER:
                with pytest.raises(asyncpg.InsufficientPrivilegeError):
                    await _ecrire(c, t, a.site, a.salle, uuid.uuid4(), "7")
        for t in PORTAIL_RIEN:  # il n'y a rien à voir
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await c.fetchval(f"SELECT count(*) FROM mark.{t}")
    finally:
        await c.close()
    for t in PORTAIL_ECRIT:  # B est intact
        assert await classeur.fork.fetchval(f"SELECT count(*) FROM mark.{t} WHERE site_id = $1", b.site) >= 1, t


async def test_ni_public_ni_l_interface_ni_les_salaries_n_ont_de_droit_sur_le_module(classeur):
    p = classeur.proprietaire
    assert await p.fetchval(
        "SELECT count(*) FROM information_schema.role_table_grants WHERE table_schema='mark' AND table_name LIKE 'resto\\_%' AND grantee='PUBLIC'"
    ) == 0
    for role in ("interface", "salarie", "direction"):
        for t in TOUTES:
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                async with p.transaction():
                    await p.execute(f'SET LOCAL ROLE "{classeur.base}_{role}"')
                    await p.fetchval(f"SELECT count(*) FROM mark.{t}")
    # le fork (rôle d'écriture) lit tout
    for t in TOUTES:
        assert await classeur.fork.fetchval(f"SELECT count(*) FROM mark.{t}") >= 1, t


async def test_le_journal_garde_qui_quoi_et_la_source_et_la_version_de_la_carte_monte(classeur):
    fork, a, b = classeur.fork, classeur.a, classeur.b
    assert await fork.fetchval("SELECT count(*) FROM mark.resto_journal") > 0  # le décor est déjà journalisé
    # fork : auteur et source posés par la session
    async with fork.transaction():
        await fork.execute("SELECT set_config('mark.auteur', 'agent-7', true), set_config('mark.source', 'agent', true)")
        await fork.execute("UPDATE mark.resto_rupture SET disponible = true WHERE site_id = $1", a.site)
    ligne = await fork.fetchrow(
        "SELECT * FROM mark.resto_journal WHERE objet = 'resto_rupture' AND operation = 'update' AND site_id = $1 ORDER BY id DESC LIMIT 1", a.site
    )
    assert (ligne["auteur"], ligne["source"]) == ("agent-7", "agent")
    assert json.loads(ligne["avant"])["disponible"] is False and json.loads(ligne["apres"])["disponible"] is True
    # une écriture qui ne change rien ne journalise rien
    avant = await fork.fetchval("SELECT count(*) FROM mark.resto_journal")
    await fork.execute("UPDATE mark.resto_rupture SET disponible = true WHERE site_id = $1", a.site)
    assert await fork.fetchval("SELECT count(*) FROM mark.resto_journal") == avant
    # portail : la source se déduit du rôle, l'auteur est la connexion
    c = await _portail(classeur.base, str(a.site))
    try:
        await c.execute("UPDATE mark.resto_zone SET nom = 'Zone nouvelle' WHERE site_id = $1", a.site)
        lu = await c.fetchrow("SELECT source, auteur FROM mark.resto_journal WHERE objet = 'resto_zone' ORDER BY id DESC LIMIT 1")
        assert lu["source"] == "portail" and lu["auteur"] == f"{classeur.base}_portail_c"
        assert await c.fetchval("SELECT count(*) FROM mark.resto_journal WHERE site_id = $1", b.site) == 0  # pas le journal de B
    finally:
        await c.close()
    # version de la carte : chaque changement de la carte, toute source, l'augmente ; une rupture non
    async def v(site):
        return await fork.fetchval("SELECT version FROM mark.resto_version_carte WHERE site_id = $1", site)

    va, vb = await v(a.site), await v(b.site)
    await fork.execute("UPDATE mark.resto_produit SET nom = 'Reine' WHERE site_id = $1", a.site)
    assert (await v(a.site), await v(b.site)) == (va + 1, vb)
    c = await _portail(classeur.base, str(a.site))
    try:
        await c.execute("UPDATE mark.resto_option SET prix = 50 WHERE site_id = $1", a.site)  # le portail, maître de la carte
    finally:
        await c.close()
    assert await v(a.site) == va + 2
    await fork.execute("UPDATE mark.resto_rupture SET disponible = false WHERE site_id = $1", a.site)
    assert await v(a.site) == va + 2
    # un changement de la carte d'enseigne touche tous les établissements
    await fork.execute("UPDATE mark.resto_categorie SET nom = 'Commun 2' WHERE site_id IS NULL")
    assert (await v(a.site), await v(b.site)) == (va + 3, vb + 1)
