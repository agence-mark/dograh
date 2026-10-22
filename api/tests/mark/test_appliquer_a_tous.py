"""[.mark] cloture-code, D152 (Evan, 22/10) : « Appliquer à tous les établissements », côté serveur.

La route ``POST /organizations/etablissements/{id}/appliquer-a-tous`` recopie UN réglage d'un
établissement dans tous les autres de l'organisation. Ce que ce fichier prouve, sur une VRAIE base du
client (Postgres des tests, sinon sautés) :

| # | Garantie | Test |
|---|---|---|
| 1 | trois établissements, une valeur : les trois la portent (règles, fenêtre, type, module, fiche, phrase) | ``test_1_*`` |
| 2 | un journal par établissement touché, au nom de l'auteur | ``test_2_*`` |
| 3 | une erreur au milieu n'en change aucun (une transaction) | ``test_3_*`` |
| 4 | une autre organisation est intacte | ``test_4_*`` |
| 5 | les refus : source inconnue, aucun autre établissement, réglage inconnu | ``test_5_*`` |

Le « au milieu » est fabriqué : un déclencheur de la base refuse l'écriture sur le dernier établissement,
après que les précédents ont été écrits.
"""

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest
from fastapi import HTTPException

from api.db.bases_clients import connexion as schema
from api.db.bases_clients.planificateur import ecrire_planificateur, lire_planificateur
from api.db.bases_clients.referentiel import ecrire_etablissements, ecrire_phrases
from api.routes import etablissements as route
from api.schemas.appliquer_a_tous import DemandeAppliquerATous
from api.schemas.etablissements import CatalogueEtablissements, Etablissement
from api.schemas.phrases import CataloguePhrases, Phrase
from api.schemas.planificateur import Planificateur, ReglagesPlanificateur, TypeRendezVous
from api.services.base_client import rattachement
from api.services.etablissements import copie as module_copie
from api.services.etablissements import stockage as module_stockage
from api.tests.mark.test_base_client import _RedisFactice, _serveur, base_essai, base_prete  # noqa: F401
from api.tests.mark.test_etablissements_heritage import HORAIRES_CREIL

ORGANISATION = 11
AUTRE_ORGANISATION = 12
AUTEUR = "dograh:appliquer"
HORAIRES_SUD = "\n".join(f"{jour} : 10h-12h" for jour in ("lundi", "mardi", "mercredi", "jeudi", "vendredi")) + "\nsamedi : fermé\ndimanche : fermé"
ADRESSE_NORD = {"code_postal": "60100", "code_insee": "60175", "commune": "Creil"}
ADRESSE_SUD = {"code_postal": "60300", "code_insee": "60612", "commune": "Senlis"}
PHRASES = CataloguePhrases(
    phrases=[Phrase(variable="phrase_acces", description="Accès", contenu="", niveau="etablissement")]
)
NORD = Etablissement(
    id="nord",
    nom="Nord",
    horaires_ouverture=HORAIRES_CREIL,
    adresse=ADRESSE_NORD,
    annonce_fermeture="Nord est fermé.",
    annonce_pause="Nord fait une pause.",
    phrases={"phrase_acces": "Derrière la gare."},
)
SUD = Etablissement(
    id="sud",
    nom="Sud",
    horaires_ouverture=HORAIRES_SUD,
    adresse=ADRESSE_SUD,
    annonce_fermeture="Sud est fermé.",
    phrases={"phrase_acces": "En centre-ville."},
)
EST = Etablissement(id="est", nom="Est")


class _Miroirs:
    """organization_configurations de plusieurs organisations, en mémoire : le rattachement et le miroir."""

    def __init__(self, bases: dict[int, str] | None = None):
        self.lignes = {(org, "BASE_CLIENT"): {"nom_base": nom} for org, nom in (bases or {}).items() if nom}

    async def get_configuration(self, organisation, cle):
        valeur = self.lignes.get((organisation, cle))
        return SimpleNamespace(value=valeur) if valeur is not None else None

    async def upsert_configuration(self, organisation, cle, valeur):
        self.lignes[(organisation, cle)] = valeur

    async def get_all_configurations_by_key(self, _cle):
        return []

    @asynccontextmanager
    async def verrou_des_ecritures_par_element(self, _organisation):
        yield


def _montage(miroirs):
    return (
        patch.object(module_copie, "_redis", AsyncMock(return_value=_RedisFactice())),
        patch.object(module_stockage, "db_client", miroirs),
        patch.object(rattachement, "db_client", miroirs),
    )


def _utilisateur(organisation: int = ORGANISATION):
    return SimpleNamespace(id=1, provider_id="appliquer", selected_organization_id=organisation, email="essai@exemple.invalid")


async def _installer(base: str, avec_module: bool = True) -> None:
    """Trois établissements aux valeurs distinctes : « nord » est la source, « sud » a ses propres valeurs,
    « est » n'a rien."""
    connexion = await schema.connecter(base)
    try:
        await ecrire_phrases(connexion, PHRASES, "essai")
        await ecrire_etablissements(connexion, CatalogueEtablissements(etablissements=[NORD, SUD, EST]), "essai", preremplir=False)
        await ecrire_planificateur(
            connexion,
            Planificateur(
                par_etablissement={
                    "nord": ReglagesPlanificateur(pas_min=45, fenetre_equite_jours=14, repartition="tour_de_role"),
                    "sud": ReglagesPlanificateur(pas_min=15, nombre_creneaux=5),
                },
                types=[
                    TypeRendezVous(code="visite", etablissement="nord", libelle="Visite", duree_min=90),
                    TypeRendezVous(code="visite", etablissement="sud", libelle="Visite courte", duree_min=30),
                    TypeRendezVous(code="examen", etablissement="sud", libelle="Examen", duree_min=20),
                ],
            ),
            "essai",
        )
        if avec_module:
            await connexion.execute(
                "INSERT INTO mark.module (code, libelle, reglages_terrain) VALUES ('essai', 'Essai', $1::jsonb)",
                json.dumps([{"cle": "seuil", "lieu": "module_reglage"}]),
            )
            await connexion.execute(
                "INSERT INTO mark.module_reglage (module_code, site_id, cle, valeur) "
                "SELECT 'essai', id, 'seuil', '5' FROM mark.site WHERE cle = 'nord'"
            )
            await connexion.execute(
                "INSERT INTO mark.module_reglage (module_code, site_id, cle, valeur) "
                "SELECT 'essai', id, 'seuil', '9' FROM mark.site WHERE cle = 'sud'"
            )
    finally:
        await connexion.close()


async def _appliquer(reglage: str, cle: str, source: str = "nord", organisation: int = ORGANISATION):
    return await route.appliquer_a_tous_les_etablissements(
        source, DemandeAppliquerATous(reglage=reglage, cle=cle), _utilisateur(organisation)
    )


async def _fiches(organisation: int = ORGANISATION) -> dict[str, Etablissement]:
    catalogue = await module_stockage.lire_etablissements_strict(organisation)
    return {e.id: e for e in catalogue.etablissements}


async def _regles(base: str) -> dict[str, dict]:
    connexion = await schema.connecter(base)
    try:
        lu = await lire_planificateur(connexion)
        return {k: v.model_dump() for k, v in lu.par_etablissement.items()}
    finally:
        await connexion.close()


async def _types(base: str) -> dict[tuple[str, str], tuple[str, int]]:
    connexion = await schema.connecter(base)
    try:
        return {
            (r["site"], r["code"]): (r["libelle"], r["duree_min"])
            for r in await connexion.fetch(
                "SELECT s.cle AS site, t.code, t.libelle, t.duree_min FROM mark.type_rendez_vous t "
                "JOIN mark.site s ON s.id = t.site_id"
            )
        }
    finally:
        await connexion.close()


async def _modules(base: str) -> dict[str, object]:
    connexion = await schema.connecter(base)
    try:
        return {
            r["site"]: json.loads(r["valeur"])
            for r in await connexion.fetch(
                "SELECT s.cle AS site, r.valeur FROM mark.module_reglage r JOIN mark.site s ON s.id = r.site_id"
            )
        }
    finally:
        await connexion.close()


async def _refuser_ecriture_sur(base: str, table: str, cle_du_lieu: str) -> None:
    """Un déclencheur qui refuse toute écriture sur ``table`` pour ce lieu : l'erreur « au milieu »."""
    connexion = await schema.connecter_proprietaire(base)
    try:
        await connexion.execute(
            f"""
            CREATE FUNCTION mark.refus_essai() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF {"NEW.id" if table == "site" else "NEW.site_id"} = (SELECT id FROM mark.site WHERE cle = '{cle_du_lieu}') THEN
                    RAISE EXCEPTION 'refus d''essai';
                END IF;
                RETURN NEW;
            END $$;
            CREATE TRIGGER refus_essai BEFORE INSERT OR UPDATE ON mark.{table}
                FOR EACH ROW EXECUTE FUNCTION mark.refus_essai();
            """
        )
    finally:
        await connexion.close()


@pytest.fixture
async def base_autre(base_essai):  # noqa: F811
    """Une seconde base du client, celle d'une autre organisation."""
    nom = f"{base_essai}_b"
    await schema.creer_base(nom)
    try:
        yield nom
    finally:
        connexion = await asyncpg.connect(f"{_serveur()}/postgres", timeout=5)
        try:
            await connexion.execute(f'DROP DATABASE IF EXISTS "{nom}" WITH (FORCE)')
            for role in await connexion.fetch("SELECT rolname FROM pg_roles WHERE rolname LIKE $1", rf"{nom}\_p\_%"):
                await connexion.execute(f'DROP ROLE IF EXISTS "{role["rolname"]}"')
            await connexion.execute(f'DROP ROLE IF EXISTS "{nom}_portail_c"')
            for suffixe in ("portail", "salarie", "direction", "interface", "ecriture"):
                await connexion.execute(f'DROP ROLE IF EXISTS "{nom}_{suffixe}"')
        finally:
            await connexion.close()


# --------------------------------------------------------------------------- #
# 1. Trois établissements, une valeur : les trois la portent
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_1_un_champ_des_regles_et_la_fenetre_sont_recopies_dans_tous_les_autres(base_prete):  # noqa: F811
    await _installer(base_prete)
    a, b, c = _montage(_Miroirs({ORGANISATION: base_prete}))
    with a, b, c:
        resultat = await _appliquer("planificateur", "pas_min")
        await _appliquer("planificateur", "fenetre_equite_jours")
    assert resultat.source == "nord" and [e.id for e in resultat.etablissements] == ["sud", "est"]
    assert [e.nom for e in resultat.etablissements] == ["Sud", "Est"]
    regles = await _regles(base_prete)
    assert {k: (v["pas_min"], v["fenetre_equite_jours"]) for k, v in regles.items()} == {
        "nord": (45, 14), "sud": (45, 14), "est": (45, 14)}
    # Only the named field moves: « sud » keeps its other values, « nord » its own, « est » gets nothing else.
    assert regles["sud"]["nombre_creneaux"] == 5 and regles["sud"]["repartition"] is None
    assert regles["nord"]["repartition"] == "tour_de_role" and regles["est"]["repartition"] is None


@pytest.mark.asyncio
async def test_1_une_valeur_vide_est_recopiee_aussi(base_prete):  # noqa: F811
    await _installer(base_prete)
    a, b, c = _montage(_Miroirs({ORGANISATION: base_prete}))
    with a, b, c:
        await _appliquer("planificateur", "nombre_creneaux")  # « nord » has none: « sud »'s 5 goes back to the default
    assert (await _regles(base_prete))["sud"]["nombre_creneaux"] is None


@pytest.mark.asyncio
async def test_1_un_type_est_copie_sur_chaque_lieu_sans_toucher_les_autres_types(base_prete):  # noqa: F811
    await _installer(base_prete)
    a, b, c = _montage(_Miroirs({ORGANISATION: base_prete}))
    with a, b, c:
        await _appliquer("type", "visite")
    assert await _types(base_prete) == {
        ("nord", "visite"): ("Visite", 90),
        ("sud", "visite"): ("Visite", 90),  # replaced by « nord »'s
        ("est", "visite"): ("Visite", 90),  # created
        ("sud", "examen"): ("Examen", 20),  # untouched
    }


@pytest.mark.asyncio
async def test_1_un_reglage_terrain_de_module_est_recopie(base_prete):  # noqa: F811
    await _installer(base_prete)
    a, b, c = _montage(_Miroirs({ORGANISATION: base_prete}))
    with a, b, c:
        await _appliquer("module", "essai.seuil")
    assert await _modules(base_prete) == {"nord": 5, "sud": 5, "est": 5}


@pytest.mark.asyncio
@pytest.mark.parametrize("champ", ["horaires_ouverture", "adresse", "annonce_fermeture", "annonce_pause"])
async def test_1_un_champ_de_la_fiche_est_recopie_dans_la_base_et_dans_le_miroir(base_prete, champ):  # noqa: F811
    await _installer(base_prete)
    miroirs = _Miroirs({ORGANISATION: base_prete})
    a, b, c = _montage(miroirs)
    with a, b, c:
        await _appliquer("fiche", champ)
        fiches = await _fiches()
    voulu = NORD.model_dump()[champ]
    assert {k: f.model_dump()[champ] for k, f in fiches.items()} == {"nord": voulu, "sud": voulu, "est": voulu}
    # The others' other fields are kept; the mirror (the fallback of the calls) follows.
    assert fiches["sud"].annonce_fermeture == ("Nord est fermé." if champ == "annonce_fermeture" else "Sud est fermé.")
    assert fiches["sud"].phrases == {"phrase_acces": "En centre-ville."}
    miroir = miroirs.lignes[(ORGANISATION, "ETABLISSEMENTS")]["etablissements"]
    assert {e["id"]: e[champ] for e in miroir} == {k: f.model_dump(mode="json")[champ] for k, f in fiches.items()}


@pytest.mark.asyncio
async def test_1_une_phrase_est_recopiee_et_une_phrase_vide_efface(base_prete):  # noqa: F811
    await _installer(base_prete)
    a, b, c = _montage(_Miroirs({ORGANISATION: base_prete}))
    with a, b, c:
        await _appliquer("phrase", "phrase_acces")
        fiches = await _fiches()
        assert {k: f.phrases for k, f in fiches.items()} == {k: {"phrase_acces": "Derrière la gare."} for k in ("nord", "sud", "est")}
        # The source says nothing: the others say nothing either (the value copied is « nothing »).
        connexion = await schema.connecter(base_prete)
        try:
            await ecrire_etablissements(
                connexion,
                CatalogueEtablissements(etablissements=[NORD.model_copy(update={"phrases": {}}), fiches["sud"], fiches["est"]]),
                "essai",
                preremplir=False,
            )
        finally:
            await connexion.close()
        await _appliquer("phrase", "phrase_acces")
        assert {k: f.phrases for k, f in (await _fiches()).items()} == {"nord": {}, "sud": {}, "est": {}}


@pytest.mark.asyncio
async def test_1_sans_base_rattachee_un_champ_de_la_fiche_s_ecrit_dans_le_miroir():
    miroirs = _Miroirs()
    miroirs.lignes[(ORGANISATION, "ETABLISSEMENTS")] = CatalogueEtablissements(etablissements=[NORD, SUD, EST]).model_dump(mode="json")
    a, b, c = _montage(miroirs)
    with a, b, c:
        resultat = await _appliquer("fiche", "horaires_ouverture")
        assert [e.id for e in resultat.etablissements] == ["sud", "est"]
        assert {k: f.horaires_ouverture for k, f in (await _fiches()).items()} == {k: HORAIRES_CREIL for k in ("nord", "sud", "est")}
        # The settings that live in the client's database need one.
        with pytest.raises(HTTPException) as refus:
            await _appliquer("planificateur", "pas_min")
        assert refus.value.status_code == 409


# --------------------------------------------------------------------------- #
# 2. Un journal par établissement touché
# --------------------------------------------------------------------------- #


async def _journal(base: str, requete: str, *arguments) -> list:
    connexion = await schema.connecter(base)
    try:
        return [tuple(r.values()) for r in await connexion.fetch(requete, *arguments)]
    finally:
        await connexion.close()


@pytest.mark.asyncio
async def test_2_chaque_etablissement_touche_a_sa_ligne_de_journal_au_nom_de_l_auteur(base_prete):  # noqa: F811
    await _installer(base_prete)
    a, b, c = _montage(_Miroirs({ORGANISATION: base_prete}))
    with a, b, c:
        await _appliquer("planificateur", "pas_min")
        await _appliquer("type", "visite")
        await _appliquer("module", "essai.seuil")
        await _appliquer("fiche", "horaires_ouverture")
        await _appliquer("phrase", "phrase_acces")
    sites = {cle: i for i, cle in await _journal(base_prete, "SELECT id, cle FROM mark.site WHERE cle IS NOT NULL")}
    voulus = {sites["sud"], sites["est"]}  # the two others; « nord » (the source) is not written
    # The rules: a row per place (« sud » updated, « est » created).
    assert {int(i) for (i,) in await _journal(
        base_prete, "SELECT ligne_id FROM mark.journal_modif WHERE table_nom = 'reglage_planificateur' AND auteur = $1", AUTEUR
    )} == {int(r[0]) for r in await _journal(
        base_prete, "SELECT id FROM mark.reglage_planificateur WHERE site_id = ANY($1::bigint[])", list(voulus))}
    # The types: one line per place, none for « nord » nor for « sud »'s other type.
    assert await _journal(
        base_prete,
        "SELECT s.cle FROM mark.journal_modif j JOIN mark.type_rendez_vous t ON t.id::text = j.ligne_id "
        "JOIN mark.site s ON s.id = t.site_id WHERE j.table_nom = 'type_rendez_vous' AND j.auteur = $1 ORDER BY s.cle",
        AUTEUR,
    ) == [("est",), ("sud",)]
    # The module's setting: the history of the module names each place.
    assert sorted(await _journal(
        base_prete, "SELECT site_id FROM mark.module_reglage_historique WHERE auteur = $1", AUTEUR
    )) == sorted((i,) for i in voulus)
    # The fiche: a line per place for the hours, and one per sentence written (two).
    assert sorted({int(i) for (i,) in await _journal(
        base_prete, "SELECT ligne_id FROM mark.journal_modif WHERE table_nom = 'site' AND auteur = $1", AUTEUR)}) == sorted(voulus)
    assert len(await _journal(
        base_prete, "SELECT 1 FROM mark.journal_modif WHERE table_nom = 'phrase_site' AND auteur = $1", AUTEUR)) == 2  # « sud » changed, « est » created


# --------------------------------------------------------------------------- #
# 3. Une erreur au milieu n'en change aucun
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reglage", "cle", "table"),
    [
        ("planificateur", "pas_min", "reglage_planificateur"),
        ("type", "visite", "type_rendez_vous"),
        ("module", "essai.seuil", "module_reglage"),
        ("fiche", "horaires_ouverture", "site"),
    ],
)
async def test_3_une_erreur_au_dernier_lieu_ne_change_aucun_etablissement(base_prete, reglage, cle, table):  # noqa: F811
    await _installer(base_prete)
    miroirs = _Miroirs({ORGANISATION: base_prete})
    a, b, c = _montage(miroirs)
    with a, b, c:
        # Mirror of the last values known good, as the screen's saves leave it.
        await module_stockage.enregistrer_miroir(ORGANISATION, etablissements=await module_stockage.lire_etablissements_strict(ORGANISATION))
        avant = (await _regles(base_prete), await _types(base_prete), await _modules(base_prete), await _fiches(), dict(miroirs.lignes))
        await _refuser_ecriture_sur(base_prete, table, "est")
        with pytest.raises(asyncpg.PostgresError, match="refus d'essai"):
            await _appliquer(reglage, cle)
        # « sud » comes before « est »: it was written first, and is back as it was.
        apres = (await _regles(base_prete), await _types(base_prete), await _modules(base_prete), await _fiches(), dict(miroirs.lignes))
    assert apres == avant


# --------------------------------------------------------------------------- #
# 4. Une autre organisation est intacte
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_4_une_autre_organisation_n_est_jamais_touchee(base_prete, base_autre):  # noqa: F811
    await _installer(base_prete)
    await _installer(base_autre)  # same names, same values: a leak would show
    miroirs = _Miroirs({ORGANISATION: base_prete, AUTRE_ORGANISATION: base_autre})
    a, b, c = _montage(miroirs)
    with a, b, c:
        for org, base in ((ORGANISATION, base_prete), (AUTRE_ORGANISATION, base_autre)):
            await module_stockage.enregistrer_miroir(org, etablissements=await module_stockage.lire_etablissements_strict(org))
        avant_autre = (await _regles(base_autre), await _types(base_autre), await _modules(base_autre), await _fiches(AUTRE_ORGANISATION),
                       miroirs.lignes[(AUTRE_ORGANISATION, "ETABLISSEMENTS")])
        for reglage, cle in (("planificateur", "pas_min"), ("type", "visite"), ("module", "essai.seuil"),
                             ("fiche", "horaires_ouverture"), ("phrase", "phrase_acces")):
            await _appliquer(reglage, cle)
        apres_autre = (await _regles(base_autre), await _types(base_autre), await _modules(base_autre), await _fiches(AUTRE_ORGANISATION),
                       miroirs.lignes[(AUTRE_ORGANISATION, "ETABLISSEMENTS")])
        # The operation did happen for the organization of the account…
        assert (await _regles(base_prete))["sud"]["pas_min"] == 45
        assert (await _fiches())["sud"].horaires_ouverture == HORAIRES_CREIL
    # …and the other organization's establishments, rules, types, settings and mirror are as they were.
    assert apres_autre == avant_autre
    assert (await _regles(base_autre))["sud"]["pas_min"] == 15


# --------------------------------------------------------------------------- #
# 5. Les refus (rien n'est écrit)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source", "reglage", "cle", "code"),
    [
        ("absent", "planificateur", "pas_min", 404),
        ("nord", "planificateur", "inconnu", 422),
        ("nord", "type", "inconnu", 422),
        ("nord", "module", "essai.autre", 422),
        ("nord", "module", "essai", 422),
        ("nord", "fiche", "nom", 422),
        ("nord", "fiche", "etat_force", 422),
        ("nord", "phrase", "inconnue", 422),
    ],
)
async def test_5_un_reglage_ou_un_lieu_inconnu_est_refuse_sans_rien_ecrire(base_prete, source, reglage, cle, code):  # noqa: F811
    await _installer(base_prete)
    a, b, c = _montage(_Miroirs({ORGANISATION: base_prete}))
    with a, b, c:
        avant = (await _regles(base_prete), await _types(base_prete), await _modules(base_prete), await _fiches())
        with pytest.raises(HTTPException) as refus:
            await _appliquer(reglage, cle, source=source)
        assert refus.value.status_code == code
        assert (await _regles(base_prete), await _types(base_prete), await _modules(base_prete), await _fiches()) == avant


@pytest.mark.asyncio
async def test_5_un_seul_etablissement_n_a_personne_a_qui_appliquer():
    miroirs = _Miroirs()
    miroirs.lignes[(ORGANISATION, "ETABLISSEMENTS")] = CatalogueEtablissements(etablissements=[NORD]).model_dump(mode="json")
    a, b, c = _montage(miroirs)
    with a, b, c:
        with pytest.raises(HTTPException) as refus:
            await _appliquer("fiche", "adresse")
    assert refus.value.status_code == 409
