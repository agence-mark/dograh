"""[.mark] Chantier Partie 1, lot 17 : le gabarit restauration (D10, D11, D21, D22, D23, D27, D28, D30, D32, D56, D59).

Gabarit figé et versionné, gabarit de réglages sans clé ni lexique, formulaire en trois niveaux prouvé complet, installation par le script,
lexique généré et régénéré, tests obligatoires générés depuis la carte qui bloquent la publication par le contrôle existant, rodage, verrou et
retouches, diffusion, styles en liste fermée. Aucun appel à un modèle : le banc des styles et des conversations est au journal du lot.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import re
import uuid
from types import SimpleNamespace
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from api.db import db_client
from api.db.bases_clients import connexion as schema
from api.enums import OrganizationConfigurationKey
from api.services.gabarits import formulaire as F
from api.services.gabarits import installation as I
from api.services.gabarits import tests_generes as TG
from api.services.gabarits import gabarit as G
from api.services.gabarits import styles as ST
from api.services.gabarits import trous as T
from api.services.gabarits.restauration import textes as TX
from api.services.modeles_reglages import classement as cl
from api.tests.mark.banc_a.commun import carte_de
from api.tests.mark.equipe_commun import creer_compte, creer_organisation
from api.tests.mark.test_base_client import base_essai  # noqa: F401

RACINE = Path(__file__).resolve().parents[4]
MIGRATION = RACINE / "api" / "alembic" / "versions" / "a7c3e9f1b2d4_mark_gabarits.py"

# Les valeurs de chaque carte versée au lot 2 (identité de l'établissement, lieu) : celles qui rendent les textes prouvés.
CASA = {"prenom_assistante": "Giulia", "nom_etablissement": "Casa Italia", "type_d_etablissement": "une pizzeria", "adresse": {"commune": "Senlis"},
        "style": "chaleureux", "lieu_des_tables": "terrasse", "services": ["emporter", "livraison", "sur_place"],
        "missions": ["prise_de_commande", "prise_de_reservation", "suivi_reclamation_message", "renseignements"]}
IDENTITES = {
    "300": CASA,
    "300b": CASA,
    "305f": {**CASA, "prenom_assistante": "Lina", "nom_etablissement": "L'Étoile d'Or", "type_d_etablissement": "un restaurant asiatique", "adresse": {"commune": "Pont-Sainte-Maxence"}},
    "307b": {**CASA, "prenom_assistante": "Samia", "nom_etablissement": "Kebab de démo", "type_d_etablissement": "un kebab", "adresse": {"commune": "Pont-Sainte-Maxence"}},
    "307c": {**CASA, "prenom_assistante": "Samia", "nom_etablissement": "Kebab de démo", "type_d_etablissement": "un kebab", "adresse": {"commune": "Pont-Sainte-Maxence"}},
}


def _trous(formulaire: dict) -> dict[str, str]:
    g = G.charger()
    return T.valeurs_des_trous(g.trous, F.completer(formulaire), ST.textes())


# --------------------------------------------------------------------------- #
# Le gabarit figé et ses trous (L17-01)
# --------------------------------------------------------------------------- #


def test_trous_cites_egal_liste():
    """Les textes citent exactement la liste des trous et des variables d'appel ; rouge sur un texte qui cite un trou inconnu."""
    g = G.charger()
    assert G.ecarts_des_trous(g) == {"cites_hors_liste": [], "trous_jamais_cites": [], "variables_jamais_citees": []}
    abime = G.Gabarit(g.nom, g.version, {**g.definition, "trous": {**g.trous, "fantome": {"donnee": "x"}}}, {**g.textes, "commande": g.textes["commande"] + "{{inconnu}}"}, g.reglages, "x")
    assert G.ecarts_des_trous(abime) == {"cites_hors_liste": ["inconnu"], "trous_jamais_cites": ["fantome"], "variables_jamais_citees": []}


@pytest.mark.parametrize("carte", sorted(IDENTITES))
def test_textes_a_trous_rendent_les_textes_prouves(carte):
    """Aucun mot changé : les textes à trous, remplis avec les valeurs de la carte versée, redonnent le texte prouvé au caractère près (les
    variables d'appel valent ce qu'elles valaient au banc)."""
    g = G.charger()
    valeurs = _trous(IDENTITES[carte])
    fichiers = [f for f in ("accueil", "accueil_repris", "commande", "reservation", "service") if (TX.DOSSIER / TX.TEMOIN / "prompts" / f"{f}-{carte}.txt").exists()]
    assert fichiers
    for f in fichiers:
        verse = TX.prompt(f, carte).replace("\r\n", "\n")
        assert verse.endswith("\n\n{{etat}}")
        rempli = G.texte_rempli(g, f, valeurs).rstrip("\n")
        motif = "".join(re.escape(m) if i % 2 == 0 else "(.*?)" for i, m in enumerate(re.split(r"(\{\{[^{}]+\}\})", rempli)))
        assert re.fullmatch(motif, verse[: -len("\n\n{{etat}}")], re.S), f"{f}-{carte}"


def test_gabarit_versionne_et_empreinte():
    """Un mot changé change l'empreinte ; la version est un entier écrit à part."""
    g = G.charger()
    assert g.version >= 1 and len(g.empreinte) == 64
    autre = G._empreinte(g.definition, {**g.textes, "commande": g.textes["commande"] + " "}, g.reglages, g.version)
    assert autre != g.empreinte


def test_outils_du_gabarit_contre_le_rendu_verse():
    """Chaque outil du rendu versé de chaque étape est soit un outil du gabarit, soit un outil du moteur ; un outil sans action au catalogue
    est dit (capacité manquante), jamais inventé (a-trancher.md, SA-1 lot 3)."""
    g = G.charger()
    for etape, e in g.definition["etapes"].items():
        etat = {"accueil": "accueil", "commande": "vide", "reservation": "vide", "service": "service"}[etape]
        rendus = {o["function"]["name"] for o in TX.rendu(etape, etat)}
        portes = {nom for n in e["noeuds"] for nom in n.get("outils", [])}
        assert rendus - {"voir_produit"} <= portes | set(g.definition["outils_du_moteur"]), etape
    manquants = G.outils_sans_action(g)
    assert set(manquants) == {"ouverture_en_ce_moment", "heure_annoncee", "envoyer_un_sms", "remises_disponibles"}


# --------------------------------------------------------------------------- #
# Le gabarit de réglages (L17-02, L17-03)
# --------------------------------------------------------------------------- #


def test_gabarit_de_reglages_sans_cles_ni_lexique():
    g = G.charger()
    tout = {**g.reglages["modele"], **g.reglages["agent"]}
    assert cl.premiere_cle_trouvee(tout) is None  # aucune clé d'accès, même sous un autre nom (M3)
    assert "dictionary" not in tout and "tts_replacements" not in tout and "etablissement_id" not in tout  # ni lexique ni donnée du client
    assert set(g.reglages["modele"]) <= set(cl.cles_du_modele())  # seulement des réglages qu'un modèle peut porter
    # Rouge connu (R7) : une clé glissée dans le gabarit est vue.
    assert cl.premiere_cle_trouvee({**tout, "greffier_llm": {"api_key": "sk-x"}}) is not None


def test_reglages_du_chantier_dans_le_gabarit():
    """P06 et G04 dans le gabarit de réglages (l'agent installé est vérifié par ``test_reglages_du_chantier_appliques``)."""
    m = G.charger().reglages["modele"]
    assert m["relecture_des_numeros"] is False and m["fiche_dans_le_systeme"] is True


# --------------------------------------------------------------------------- #
# Le formulaire en trois niveaux (L17-04 à L17-07)
# --------------------------------------------------------------------------- #


def _tables_lues_par_le_code() -> set[str]:
    tables: set[str] = set()
    for chemin in F.MODULES_LUS:
        tables |= set(re.findall(r"mark\.([a-z_]+)", (RACINE / chemin).read_text(encoding="utf-8")))
    return tables


async def test_inventaire_du_formulaire(base_prete):
    """Toute colonne de configuration lue par le module est rangée en A, B ou C (ou dite hors du formulaire, avec sa raison) ; toute table
    lue par le code est rangée ; chaque donnée citée existe. Rouge connu : une colonne ajoutée sans rang."""
    from api.db.bases_clients import connexion as schema

    lues = _tables_lues_par_le_code()
    assert lues <= set(F.INVENTAIRE) | set(F.TABLES_D_EXPLOITATION) | {"site"}, sorted(lues - set(F.INVENTAIRE) - set(F.TABLES_D_EXPLOITATION))
    c = await schema.connecter(base_prete)
    try:
        lignes = await c.fetch("SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = 'mark' AND table_name = ANY($1::text[])", list(F.INVENTAIRE))
    finally:
        await c.close()
    reelles: dict[str, set[str]] = {}
    for l in lignes:
        reelles.setdefault(l["table_name"], set()).add(l["column_name"])
    assert set(reelles) == set(F.INVENTAIRE)
    sans_rang = sorted(f"{t}.{col}" for t, cols in reelles.items() for col in cols if col not in F.INVENTAIRE[t])
    assert sans_rang == [], sans_rang
    perimees = sorted(f"{t}.{col}" for t, cols in F.INVENTAIRE.items() for col in cols if col not in reelles[t])
    assert perimees == [], perimees
    for t, cols in F.INVENTAIRE.items():
        for col, (niveau, cle) in cols.items():
            if niveau != "-":
                assert F.niveau_de(cle) == niveau, f"{t}.{col}"
    # Rouge connu (R7) : une colonne de plus, sans rang, est vue.
    reelles["resto_zone"].add("colonne_neuve")
    assert [col for col in reelles["resto_zone"] if col not in F.INVENTAIRE["resto_zone"]] == ["colonne_neuve"]


FORMULAIRE_COMPLET = {
    "missions": ["prise_de_commande", "prise_de_reservation", "suivi_reclamation_message", "renseignements"],
    "nom_etablissement": "Chez Essai",
    "adresse": {"voie": "5 rue Louis Boilet", "code_postal": "60700", "commune": "Pont-Sainte-Maxence", "insee": "60509"},
    "services": ["emporter", "livraison", "sur_place"],
    "zones": [{"nom": "Pont", "communes": ["60509"], "minimum": 1500, "frais": 0, "delai": 30}],
    "horaires": {str(j): [["00:00", "23:59"]] for j in range(1, 8)},
    "temps_de_preparation": {"emporter": 20, "livraison": 40},
    "moyens_paiement": ["carte", "especes"],
    "reservation": {"capacite": 20, "duree_minutes": 90, "creneaux": [{"nom": "Soir", "jours": [1, 2, 3, 4, 5, 6, 7], "debut": "19:00", "fin": "22:00", "pas_minutes": 30}]},
    "allergenes": "renvoyer_vers_le_restaurant",
    "carte": carte_de("kebab-demo"),
}


def test_creation_bloquee_seulement_par_a():
    sans_commune = {**FORMULAIRE_COMPLET, "adresse": {"voie": "5 rue Louis Boilet", "code_postal": "60700"}}
    c = F.controler(sans_commune)
    assert not c.creation_permise and c.a_manquer == ["adresse"]
    sans_horaires = {k: v for k, v in FORMULAIRE_COMPLET.items() if k != "horaires"}
    c = F.controler(sans_horaires)
    assert c.creation_permise and c.b_manquer == ["horaires"]
    assert F.controler(FORMULAIRE_COMPLET).b_manquer == []


def test_missions_decident_le_niveau_b():
    reservation_seule = {**{k: v for k, v in FORMULAIRE_COMPLET.items() if k not in ("carte", "moyens_paiement", "allergenes", "temps_de_preparation")},
                         "missions": ["prise_de_reservation", "renseignements"], "services": ["sur_place"]}
    c = F.controler(reservation_seule)
    assert c.creation_permise and "carte" not in c.b_manquer and c.b_manquer == []
    commande = {**reservation_seule, "missions": ["prise_de_commande"], "services": ["emporter"]}
    assert {"carte", "moyens_paiement", "allergenes", "temps_de_preparation"} <= set(F.controler(commande).b_manquer)
    transfert = {**reservation_seule, "missions": ["transfert_d_appel"]}
    assert F.controler(transfert).b_manquer == ["transfert"]


def test_allergenes_ou_renvoi_en_b():
    sans = {k: v for k, v in FORMULAIRE_COMPLET.items() if k != "allergenes"}
    assert "allergenes" in F.controler(sans).b_manquer
    assert "allergenes" not in F.controler({**sans, "allergenes": "renseignes"}).b_manquer
    assert "allergenes" not in F.controler({**sans, "allergenes": "renvoyer_vers_le_restaurant"}).b_manquer
    assert "allergenes" in F.controler({**sans, "allergenes": "peut-etre"}).b_manquer


def test_regle_inconnue_signalee_jamais_bloquante():
    c = F.controler({**FORMULAIRE_COMPLET, "regles_inconnues": ["une pizza offerte le jour de l'anniversaire"]})
    assert c.creation_permise and c.signalements and c.b_manquer == []


# --------------------------------------------------------------------------- #
# Les styles (L17-23, L17-27)
# --------------------------------------------------------------------------- #


def test_style_liste_fermee():
    assert ST.valider(None) == "chaleureux"
    with pytest.raises(ST.StyleInconnu):
        ST.valider("poétique")
    with pytest.raises(ST.StyleInconnu):
        T.valeurs_des_trous(G.charger().trous, F.completer({**CASA, "style": "prose libre du restaurateur"}), ST.textes())


# --------------------------------------------------------------------------- #
# La migration (L17-25)
# --------------------------------------------------------------------------- #


def _charger_migration():
    spec = importlib.util.spec_from_file_location("migration_a7c3e9f1b2d4", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCHEMA = "lot17_essai_migration"
TABLES = {"mark_gabarits", "mark_gabarit_applications", "mark_gabarit_diffusions"}


def _tables(c):
    return set(c.execute(sa.text("SELECT table_name FROM information_schema.tables WHERE table_schema = :s"), {"s": SCHEMA}).scalars())


async def test_migration_gabarits_montee_descente(test_engine):
    """Une seule tête ; montée, descente, remontée ; une version figée ne se double pas."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    tetes = ScriptDirectory.from_config(Config(str(RACINE / "api" / "alembic.ini"))).get_heads()
    assert tetes == ["a7c3e9f1b2d4"]

    def cas(c):
        c.execute(sa.text(f"CREATE SCHEMA {SCHEMA}"))
        c.execute(sa.text(f"SET LOCAL search_path TO {SCHEMA}"))
        c.execute(sa.text("CREATE TABLE organizations (id serial PRIMARY KEY)"))
        c.execute(sa.text("CREATE TABLE workflows (id serial PRIMARY KEY)"))
        with Operations.context(MigrationContext.configure(c)):
            m = _charger_migration()
            m.upgrade()
            montees = _tables(c)
            c.execute(sa.text("INSERT INTO mark_gabarits (nom, version, contenu, empreinte) VALUES ('r', 1, '{}', 'e')"))
            point = c.begin_nested()
            try:
                c.execute(sa.text("INSERT INTO mark_gabarits (nom, version, contenu, empreinte) VALUES ('r', 1, '{}', 'f')"))
                double = True
            except sa.exc.IntegrityError:
                double = False
            point.rollback()
            m.downgrade()
            descendues = _tables(c)
            m.upgrade()
            remontees = _tables(c)
            return montees, double, descendues, remontees

    async with test_engine.connect() as connexion:
        transaction = await connexion.begin()
        try:
            montees, double, descendues, remontees = await connexion.run_sync(cas)
        finally:
            await transaction.rollback()
    assert TABLES <= montees and TABLES <= remontees
    assert not TABLES & descendues
    assert double is False


# --------------------------------------------------------------------------- #
# L'installation par le script (L17-03, L17-08 à L17-14, L17-17, L17-29)
# --------------------------------------------------------------------------- #


async def _client_avec_sa_base(db, base: str, role: str = "Administrateur"):
    await schema.creer_base(base)
    org = await creer_organisation(db, f"l17-{uuid.uuid4().hex[:8]}")
    await db.upsert_configuration(org, OrganizationConfigurationKey.BASE_CLIENT.value, {"nom_base": base})
    user, jeton = await creer_compte(db, f"l17-{uuid.uuid4().hex[:8]}@example.com", role=role, organisations=[org])
    user.selected_organization_id = org
    return SimpleNamespace(org=org, user=user, jeton=jeton, base=base)


@pytest.fixture
async def installe(db_session, base_essai):  # noqa: F811
    """Un restaurant de test installé par le script et le formulaire seuls (la carte de démo du kebab)."""
    cas = await _client_avec_sa_base(db_session, base_essai)
    resultat = await I.installer_un_restaurant(cas.user, cas.org, FORMULAIRE_COMPLET, nom_base=base_essai)
    assert resultat["echec"] is None, resultat["echec"]
    cas.resultat = resultat
    cas.application = resultat["application"]
    cas.agents = {k: v for k, v in cas.application["agents"].items() if not k.startswith("_")}
    return cas


async def _brouillon(wid: int):
    return await db_client.get_draft_version(wid)


async def test_installation_par_script(installe):
    """Le formulaire seul installe un groupe complet : l'accueil et un collègue par mission, les textes remplis (aucun trou restant, les
    variables d'appel laissées au code), les outils de l'étape, les sorties ; l'installation du client est terminée."""
    assert set(installe.agents) == {"accueil", "commande", "reservation", "service"}
    assert installe.resultat["installation"]["etat"] == "terminee"
    g = G.charger()
    for etape, wid in installe.agents.items():
        definition = (await _brouillon(wid)).workflow_json
        textes = " ".join(str((n.get("data") or {}).get("prompt") or "") + str((n.get("data") or {}).get("greeting") or "") for n in definition["nodes"])
        assert "Chez Essai" in textes and "Pont-Sainte-Maxence" in textes, etape
        assert not set(T.noms_cites(textes)) & set(g.trous), etape  # aucun trou laissé
        assert "{{initial_context.date_appel}}" in textes  # les variables d'appel restent au code
        assert {a["data"]["identifiant"] for a in definition["edges"]} >= {"fin"}
    accueil = (await _brouillon(installe.agents["accueil"])).workflow_json
    debut = next(n for n in accueil["nodes"] if n["type"] == "startCall")
    assert debut["data"]["greeting"].startswith("Chez Essai bonjour, je suis Léa")
    passages = await db_client.get_tools_by_uuids(debut["data"]["tool_uuids"][:3], installe.org)
    assert sorted(((o.definition or {}).get("config") or {}).get("cible") for o in passages) == ["commande", "reservation", "service"]
    commande = (await _brouillon(installe.agents["commande"])).workflow_json
    sortie_fin = next(a for a in commande["edges"] if a["data"]["identifiant"] == "fin")
    assert sortie_fin["data"].get("fermee_si_action_ouverte") is True


async def test_reglages_du_chantier_appliques(installe):
    """Sur l'agent INSTALLÉ (la création pose la relecture allumée, CONFIGURATION_DE_CREATION) : relecture éteinte (P06), fiche dans
    l'instruction système (G04), passage unique, établissement de l'agent ; aucune clé."""
    for etape, wid in installe.agents.items():
        r = (await _brouillon(wid)).workflow_configurations
        assert r.get("relecture_des_numeros") is False and r.get("fiche_dans_le_systeme") is True, etape
        assert r.get("etablissement_id") == installe.application["formulaire"]["cle"]
        assert cl.premiere_cle_trouvee({k: v for k, v in r.items() if k in G.charger().reglages["modele"]}) is None
    assert (await _brouillon(installe.agents["accueil"])).workflow_configurations.get("passage_unique") is True


async def test_version_gabarit_et_fork_notees(installe):
    a = installe.application
    g = G.charger()
    assert (a["gabarit_nom"], a["gabarit_version"]) == (g.nom, g.version)
    assert a["commit_fork"] and len(a["commit_fork"]) >= 7
    fige = await db_client.lire_le_gabarit(g.nom, g.version)
    assert fige["empreinte"] == g.empreinte
    for wid in installe.agents.values():
        assert (await db_client.application_de(installe.org, wid))["id"] == a["id"]


async def test_lexique_genere_depuis_la_carte(installe):
    from api.services.lexique.stockage import lire_lexique

    noms = {t.terme for t in (await lire_lexique(installe.org)).termes}
    attendus = {p["nom"] for p in FORMULAIRE_COMPLET["carte"]["produits"]}
    assert len(attendus & noms) >= len(attendus) // 2, sorted(attendus - noms)[:5]


async def test_lexique_regenere_a_la_synchro(installe):
    """Une nouvelle carte importée par la caisse : le lexique suit (``importer_la_caisse`` le régénère)."""
    from api.services.lexique.stockage import lire_lexique
    from api.services.restauration import synchro_caisse

    etab = installe.application["formulaire"]["etablissement_id"]
    carte = json.loads(json.dumps(FORMULAIRE_COMPLET["carte"]))
    carte["produits"][0]["nom"] = "Tacos Zorglub"  # la caisse renomme un article

    class Prise:
        capacites = SimpleNamespace(carte="lue", ruptures="non", lit_l_etat=False)

        async def lire_carte(self):
            return carte

    c = await schema.connecter(installe.base)
    try:
        bilan = await synchro_caisse.importer_la_caisse(Prise(), c, installe.org, etab)
    finally:
        await c.close()
    assert bilan["carte"] is not None and bilan["erreur"] is None
    assert "Tacos Zorglub" in {t.terme for t in (await lire_lexique(installe.org)).termes}


async def test_tests_obligatoires_generes_depuis_la_carte(installe):
    """Chaque article, brique employée, zone et mode de la carte a son test obligatoire, rangé à part (dossier des tests générés), par le
    mécanisme existant des tests de l'agent (D56) ; les conversations et la série de base aussi."""
    from api.services.builder.tests_agent import stockage

    tests = await stockage.lister(installe.org, installe.agents["commande"])
    genres: dict[str, set[str]] = {}
    for t in tests:
        assert t["obligatoire"] and t["dossier"] == TG.DOSSIER and t["origine"] == "code"
        genres.setdefault(t["genere"]["genre"], set()).add(t["genere"]["sujet"])
    carte = FORMULAIRE_COMPLET["carte"]
    assert {p["id"] for p in carte["produits"]} | {f["id"] for f in carte.get("formules") or []} <= genres["article"]
    assert set(TG.briques_de_la_carte(carte)) <= genres["brique"]
    assert genres["mode"] == set(FORMULAIRE_COMPLET["services"])
    assert len(genres["zone"]) == len(FORMULAIRE_COMPLET["zones"])
    assert genres["conversation"] and genres["serie_de_base"]


async def test_tests_generes_passent_du_premier_coup(installe):
    """Critère de fin : les tests générés sans modèle (banc de la carte, données) passent du premier coup sur le restaurant installé."""
    r = await TG.jouer_les_tests_du_code(installe.org, installe.application)
    assert r["rouges"] == [] and r["verts"] > 0


async def test_echec_range_donnee_ou_capacite(installe):
    """Un échec est rangé : donnée (une zone sans commune ni rayon) ou capacité (une brique sans règle)."""
    from api.services.commande.briques import registre

    c = await schema.connecter(installe.base)
    try:
        await c.execute("UPDATE mark.resto_zone SET communes = '{}' WHERE site_id = $1", installe.application["formulaire"]["etablissement_id"])
    finally:
        await c.close()
    TG._charger_les_briques()
    code = TG.briques_de_la_carte(FORMULAIRE_COMPLET["carte"])[0]
    vraie = registre.BRIQUES[code]
    registre.BRIQUES[code] = registre.Brique(code=code, famille=vraie.famille)  # une brique sans règle
    try:
        r = await TG.jouer_les_tests_du_code(installe.org, installe.application)
    finally:
        registre.BRIQUES[code] = vraie
    familles = {x["slug"].split("-")[1]: x["famille"] for x in r["rouges"]}
    assert familles == {"zone": "donnee", "brique": "capacite"}
    with pytest.raises(ValueError):
        TG.ranger_l_echec("autre chose")


ATTENDUS_LIBELLES = {
    "tests_obligatoires", "bilan_du_prompt", "liste_vocale", "attaques", "garde_fous", "variables", "briques", "outils", "sans_effet",
    "sortie_d_impasse", "deux_webhooks", "valeur_en_dur", "verbe_ecran", "action_sans_outil", "sortie_non_citee", "poids_agent",
    "systeme_sans_outil", "description_d_outil", "annonce_ia", "etiquettes", "blocs_a_jour",
}


async def test_tests_generes_bloquent_par_le_controle_existant(installe):
    """Un test généré rouge : la publication est refusée par « Tests obligatoires » (``_tests``) ; aucun contrôle neuf dans ``LIBELLES``."""
    from api.services.builder.tests_agent import publication as garde
    from api.services.publication import controles

    assert set(controles.LIBELLES) == ATTENDUS_LIBELLES
    wid = installe.agents["commande"]
    agent = await db_client.get_workflow(wid, organization_id=installe.org)
    brouillon = await _brouillon(wid)
    avant = await controles._tests(agent, brouillon, installe.org)
    assert any("Mode ouvert : emporter" in str(p) for p in avant)  # jamais joué : bloquant
    await TG.jouer_les_tests_du_code(installe.org, installe.application)
    apres = await controles._tests(agent, brouillon, installe.org)
    assert not any("Mode ouvert" in str(p) or "Article de la carte" in str(p) for p in apres)  # verts : ne bloquent plus
    c = await schema.connecter(installe.base)
    try:
        await c.execute("UPDATE mark.resto_reglage_type SET ouvert = false WHERE site_id = $1 AND type = 'emporter'", installe.application["formulaire"]["etablissement_id"])
    finally:
        await c.close()
    await TG.jouer_les_tests_du_code(installe.org, installe.application)
    rouges = await garde.problemes_des_tests_obligatoires(installe.org, wid, brouillon.version_number, garde.empreinte_du_brouillon_publie(brouillon))
    assert any(p["slug"] == "genere-mode-emporter" and p["code"] == "test_echoue" for p in rouges)


async def test_installation_reprenable(db_session, base_essai, monkeypatch):  # noqa: F811
    """Une coupure au milieu (après la création du groupe) : la reprise finit l'installation sans doubler ni l'établissement, ni un agent,
    ni un outil."""
    from api.services.installation_client import moteur

    cas = await _client_avec_sa_base(db_session, base_essai)
    vraie = I.appliquer_les_reglages

    async def coupee(*a, **k):
        raise asyncio.CancelledError()

    monkeypatch.setattr(I, "appliquer_les_reglages", coupee)
    with pytest.raises(asyncio.CancelledError):
        await I.installer_un_restaurant(cas.user, cas.org, FORMULAIRE_COMPLET, nom_base=base_essai)
    monkeypatch.setattr(I, "appliquer_les_reglages", vraie)
    monkeypatch.setattr(moteur, "BAIL_S", 0)  # le bail de l'étape coupée est écoulé
    resultat = await I.installer_un_restaurant(cas.user, cas.org, FORMULAIRE_COMPLET, nom_base=base_essai)
    assert resultat["echec"] is None
    agents = await db_client.get_all_workflows_for_listing(organization_id=cas.org, status="active")
    assert len(agents) == 4
    actions = [(((o.definition or {}).get("config") or {}).get("connecteur"), ((o.definition or {}).get("config") or {}).get("action"))
               for o in await db_client.get_tools_for_organization(cas.org, status="active", category="integration")]
    assert len(actions) == len(set(actions)) == 6  # fiche et lecture de la commande et de la réservation, fiche et infos pratiques du service
    assert len(await db_client.get_tools_for_organization(cas.org, status="active", category="transfer_agent")) == 3
    c = await schema.connecter(base_essai)
    try:
        assert await c.fetchval("SELECT count(*) FROM mark.site WHERE cle IS NOT NULL") == 1
    finally:
        await c.close()


async def test_gabarit_verrouille(installe):
    """La principale de chaque agent installé est protégée : une retouche passe par une branche de brouillon (versions gardées). La version
    figée du gabarit ne se réécrit pas."""
    from api.db.gabarits_client import GabaritDejaFige
    from api.services.branches import service as branches

    wid = installe.agents["commande"]
    with pytest.raises(Exception) as refus:
        await db_client.exiger_la_principale_modifiable(wid)
    assert type(refus.value).__name__ == "PrincipaleProtegee"
    agent = await db_client.get_workflow(wid, organization_id=installe.org)
    branche = await branches.creer(installe.org, agent, "Retouche", depuis_version=None, user_id=installe.user.id, protegee=False)
    assert branche["id"]
    g = G.charger()
    with pytest.raises(GabaritDejaFige):
        await db_client.figer_le_gabarit(g.nom, g.version, g.contenu(), "0" * 64)


async def test_creation_refusee_sans_a_par_le_moteur(db_session, base_essai):  # noqa: F811
    """Sans commune : l'étape « L'agent » échoue avec une phrase précise ; aucun agent n'est créé."""
    cas = await _client_avec_sa_base(db_session, base_essai)
    sans = {**FORMULAIRE_COMPLET, "adresse": {"voie": "5 rue Louis Boilet", "code_postal": "60700"}}
    r = await I.installer_un_restaurant(cas.user, cas.org, sans, nom_base=base_essai)
    assert r["echec"]["code"] == "gabarit_formulaire_incomplet" and "A:adresse" in r["echec"]["precisions"]
    assert await db_client.get_all_workflows_for_listing(organization_id=cas.org, status="active") == []
