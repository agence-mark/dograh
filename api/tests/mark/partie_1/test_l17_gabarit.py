"""[.mark] Chantier Partie 1, lot 17 : le gabarit restauration (D10, D11, D21, D22, D23, D27, D28, D30, D32, D56, D59).

Gabarit figé et versionné, gabarit de réglages sans clé ni lexique, formulaire en trois niveaux prouvé complet, installation par le script,
lexique généré et régénéré, tests obligatoires générés depuis la carte qui bloquent la publication par le contrôle existant, rodage, verrou et
retouches, diffusion, styles en liste fermée. Aucun appel à un modèle : le banc des styles et des conversations est au journal du lot.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from api.services.gabarits import formulaire as F
from api.services.gabarits import gabarit as G
from api.services.gabarits import styles as ST
from api.services.gabarits import trous as T
from api.services.gabarits.restauration import textes as TX
from api.services.modeles_reglages import classement as cl

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
    "horaires": "lundi : 11:00-14:00 et 18:00-22:30\nmardi : 11:00-14:00 et 18:00-22:30",
    "temps_de_preparation": {"emporter": 20, "livraison": 40},
    "moyens_paiement": ["carte", "especes"],
    "reservation": {"capacite": 20, "duree_minutes": 90, "creneaux": [{"nom": "Soir", "jours": [1, 2, 3, 4, 5, 6, 7], "debut": "19:00", "fin": "22:00", "pas_minutes": 30}]},
    "allergenes": "renvoyer_vers_le_restaurant",
    "carte": {"slug": "kebab-demo"},
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
