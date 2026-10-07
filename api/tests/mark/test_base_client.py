"""[.mark] Non-regression test for the client's own database (chantier l-agent-travaille, L3).

The questions this file answers (B1 to B6, R7):

    Does « Create database » make a database at the expected version, and does
    « Upgrade » apply nothing twice? Do the establishments, numbers, hours,
    sentences and team written by Dograh come back identical? Are the hours
    changed DIRECTLY in the database (the client, Metabase later) heard at the
    next pick-up? When the notification is missed, does the resync correct the
    copy (R7: proved on a red case, the trigger switched off)? Are hours that
    do not parse refused, the previous ones kept and the refusal reported?

Why it exists
-------------
🔴 Once a database is attached, it is the source (B2): a write that does not
reach the copy the calls read (B3) is a shop announced open when it is closed,
and nothing on the call says so. Only a REAL Postgres sees a trigger, a
notification, a transaction.

The database is made on the Postgres of the tests (``DATABASE_URL``), under a
throwaway name, and dropped after. No Postgres: the tests that need one are
skipped, the others run.

⚠️ What this file does NOT prove: that the screen shows the theme
(``ui/src/components/mark/parametres-organisation/``).
"""

import asyncio
import json
import os
import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import asyncpg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.db.bases_clients import connexion as schema
from api.db.bases_clients.equipe import EtablissementInconnu, ecrire_equipe, lire_equipe
from api.db.bases_clients.referentiel import ecrire_etablissements, ecrire_phrases
from api.routes import etablissements as route_etablissements
from api.schemas.annonce_ouverture import ReglagesAnnonceOuverture
from api.schemas.base_client import Equipe, Personne, Sujet
from api.schemas.etablissements import CatalogueEtablissements, Etablissement
from api.schemas.lexique_metier import TermeLexique
from api.schemas.organization_preferences import OrganizationPreferences
from api.schemas.phrases import CataloguePhrases, Phrase
from api.services.auth.depends import get_user_with_selected_organization
from api.services.base_client import rattachement, synchro
from api.services.base_client.referentiel import lire_referentiel
from api.services.etablissements import copie as module_copie
from api.services.etablissements import stockage as module_stockage
from api.services.workflow import text_chat_runner
from api.tests.mark.test_adresse_etablissement import ORGANISATION, _jouer_au_clavier

JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi")
HORAIRES = "\n".join([f"{j} : 9h-12h et 14h-18h" for j in JOURS] + ["dimanche : fermé"])
HORAIRES_DIMANCHE = "\n".join(
    [f"{j} : 9h-12h et 14h-18h" for j in JOURS] + ["dimanche : 10h-12h"]
)
DIMANCHE_11H = datetime(2026, 10, 4, 11, 0, tzinfo=ZoneInfo("Europe/Paris"))

CREIL = Etablissement(
    id="creil",
    nom="Site A",
    numeros=["+33344000001", "+33344000003"],
    second_numero="+33344000098",
    numero_transfert="+33344000099",
    horaires_ouverture=HORAIRES,
    adresse={
        "code_postal": "60300",
        "code_insee": "60612",
        "commune": "Senlis",
        "voie": "1 rue de la Gare",
    },
    annonce_fermeture="Le site est fermé[, nous rouvrons {reouverture}].",
    phrases={"accueil_site": "Bienvenue au site A."},
    termes_lexique=[TermeLexique(terme="Gamme Alpha")],
)
SENLIS = Etablissement(id="senlis", nom="Site B", numeros=["+33344000002"])
CATALOGUE = CatalogueEtablissements(etablissements=[CREIL, SENLIS])
PHRASES = CataloguePhrases(
    phrases=[
        Phrase(
            variable="accueil_site",
            description="Accueil",
            contenu="Bienvenue.",
            niveau="etablissement",
        ),
        Phrase(
            variable="mentions", description="Mentions", contenu="Cet appel est noté."
        ),
    ]
)


# --------------------------------------------------------------------------- #
# The throwaway database
# --------------------------------------------------------------------------- #


def _serveur() -> str | None:
    brut = os.environ.get("DATABASE_URL", "").replace(
        "postgresql+asyncpg://", "postgresql://", 1
    )
    if not brut:
        return None
    m = urlsplit(brut)
    return urlunsplit((m.scheme, m.netloc, "", "", ""))


async def _postgres_joignable() -> bool:
    serveur = _serveur()
    if not serveur:
        return False
    try:
        connexion = await asyncpg.connect(f"{serveur}/postgres", timeout=3)
    except Exception:  # noqa: BLE001
        return False
    await connexion.close()
    return True


@pytest.fixture
async def base_essai(monkeypatch):
    if not await _postgres_joignable():
        pytest.skip("No Postgres for the tests (DATABASE_URL)")
    monkeypatch.setenv(schema.VARIABLE_ENV, _serveur())
    nom = f"mark_essai_{uuid.uuid4().hex[:10]}"
    try:
        yield nom
    finally:
        connexion = await asyncpg.connect(f"{_serveur()}/postgres", timeout=5)
        try:
            await connexion.execute(f'DROP DATABASE IF EXISTS "{nom}" WITH (FORCE)')
            for suffixe in ("direction", "interface", "ecriture"):
                await connexion.execute(f'DROP ROLE IF EXISTS "{nom}_{suffixe}"')
        finally:
            await connexion.close()


@pytest.fixture
async def base_prete(base_essai):
    await schema.creer_base(base_essai)
    return base_essai


class _RedisFactice:
    def __init__(self):
        self.valeurs = {}

    async def get(self, cle):
        return self.valeurs.get(cle)

    async def set(self, cle, valeur, nx=False, ex=None, **_options):
        if nx and cle in self.valeurs:
            return None
        self.valeurs[cle] = valeur
        return True


class _Miroir:
    """organization_configurations, in memory: the attachment and the mirror."""

    def __init__(self, nom_base=None):
        self.lignes = {}
        if nom_base:
            self.lignes["BASE_CLIENT"] = {"nom_base": nom_base}

    async def get_configuration(self, _organisation, cle):
        valeur = self.lignes.get(cle)
        return SimpleNamespace(value=valeur) if valeur is not None else None

    async def upsert_configuration(self, _organisation, cle, valeur):
        self.lignes[cle] = valeur

    async def get_all_configurations_by_key(self, cle):
        valeur = self.lignes.get(cle)
        return [{"organization_id": ORGANISATION, "value": valeur}] if valeur else []


def _rattachee(miroir, redis):
    return (
        patch.object(module_copie, "_redis", AsyncMock(return_value=redis)),
        patch.object(module_stockage, "db_client", miroir),
        patch.object(rattachement, "db_client", miroir),
    )


# --------------------------------------------------------------------------- #
# 1. Name, address, migrations (B4, B6)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "nom", ["", "A_majuscule", "1commence", "ab", "nom-tiret", 'x"; DROP', "postgres"]
)
def test_un_nom_de_base_hors_format_est_refuse(nom):
    with pytest.raises(schema.NomDeBaseInvalide):
        schema.verifier_nom(nom)


@pytest.mark.asyncio
async def test_le_mot_de_passe_ne_sort_jamais_dans_une_erreur(monkeypatch):
    monkeypatch.setenv(
        schema.VARIABLE_ENV, "postgresql://u:motdepasse-secret@127.0.0.1:1"
    )
    with pytest.raises(schema.BaseClientIndisponible) as erreur:
        await schema.connecter("mark_essai_absente")
    assert "motdepasse-secret" not in str(erreur.value) and "127.0.0.1" not in str(
        erreur.value
    )


@pytest.mark.asyncio
async def test_sans_serveur_configure_la_base_est_indisponible(monkeypatch):
    monkeypatch.delenv(schema.VARIABLE_ENV, raising=False)
    assert schema.serveur_configure() is False
    with pytest.raises(schema.BaseClientIndisponible):
        await schema.connecter("mark_essai_absente")


def test_les_migrations_sont_numerotees_sans_trou():
    versions = [m.version for m in schema.migrations()]
    assert (
        versions == list(range(1, len(versions) + 1)) and schema.version_attendue() >= 3
    )


@pytest.mark.asyncio
async def test_creer_puis_mettre_a_niveau_napplique_rien_deux_fois(base_essai):
    assert await schema.creer_base(base_essai) == list(
        range(1, schema.version_attendue() + 1)
    )
    connexion = await schema.connecter(base_essai)
    try:
        assert await schema.version_de(connexion) == schema.version_attendue()
        assert await schema.appliquer_migrations(connexion) == []
        # 003: no CONNECT for PUBLIC, roles named after THIS database.
        public = await connexion.fetchval(
            "SELECT has_database_privilege('public', current_database(), 'CONNECT')"
        )
        assert public is False
        roles = {
            r["rolname"]
            for r in await connexion.fetch(
                "SELECT rolname FROM pg_roles WHERE rolname LIKE $1", f"{base_essai}_%"
            )
        }
        assert roles == {
            f"{base_essai}_ecriture",
            f"{base_essai}_interface",
            f"{base_essai}_direction",
        }
    finally:
        await connexion.close()


# --------------------------------------------------------------------------- #
# 2. The referential written by Dograh comes back identical (B2)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_le_referentiel_ecrit_revient_identique_et_journalise(base_prete):
    connexion = await schema.connecter(base_prete)
    try:
        await ecrire_phrases(connexion, PHRASES, "dograh:essai")
        await ecrire_etablissements(connexion, CATALOGUE, "dograh:essai")
        lu = await lire_referentiel(connexion)
        assert lu.refus == []
        assert lu.etablissements.model_dump(mode="json") == CATALOGUE.model_dump(
            mode="json"
        )
        assert lu.phrases.model_dump(mode="json") == PHRASES.model_dump(mode="json")
        auteurs = {
            r["auteur"]
            for r in await connexion.fetch("SELECT auteur FROM mark.journal_modif")
        }
        assert auteurs == {"dograh:essai"}

        # « Save » with nothing changed writes nothing to the journal.
        avant = await connexion.fetchval("SELECT count(*) FROM mark.journal_modif")
        await ecrire_phrases(connexion, PHRASES, "dograh:essai")
        await ecrire_etablissements(connexion, CATALOGUE, "dograh:essai")
        assert (
            await connexion.fetchval("SELECT count(*) FROM mark.journal_modif") == avant
        )

        # Removed on screen = deactivated, never deleted.
        await ecrire_etablissements(
            connexion, CatalogueEtablissements(etablissements=[CREIL]), "dograh:essai"
        )
        assert (
            await connexion.fetchval("SELECT actif FROM mark.site WHERE cle = 'senlis'")
            is False
        )
        assert [
            e.id
            for e in (await lire_referentiel(connexion)).etablissements.etablissements
        ] == ["creil"]
    finally:
        await connexion.close()


@pytest.mark.asyncio
async def test_lequipe_ecrite_revient_identique(base_prete):
    connexion = await schema.connecter(base_prete)
    equipe = Equipe(
        personnes=[
            Personne(
                cle="p1",
                prenom="Alice",
                etablissement="creil",
                mail="alice@example.org",
                destinataire_defaut=True,
            ),
            Personne(cle="p2", prenom="Bruno", telephone="+33 6 12 34 56 78"),
        ],
        sujets=[
            Sujet(
                code="devis",
                libelle="Devis",
                mots_declencheurs=["prix"],
                destinataires=["p2", "p1"],
            )
        ],
    )
    try:
        await ecrire_etablissements(connexion, CATALOGUE, "dograh:essai")
        await ecrire_equipe(connexion, equipe, "dograh:essai")
        assert (await lire_equipe(connexion)).model_dump() == equipe.model_dump()

        # A subject removed is hidden (deactivated); a person removed is kept, inactive.
        await ecrire_equipe(
            connexion, Equipe(personnes=equipe.personnes[:1]), "dograh:essai"
        )
        relue = await lire_equipe(connexion)
        assert relue.sujets == [] and [(p.cle, p.actif) for p in relue.personnes] == [
            ("p1", True),
            ("p2", False),
        ]

        with pytest.raises(EtablissementInconnu):
            await ecrire_equipe(
                connexion,
                Equipe(
                    personnes=[Personne(cle="p3", prenom="C", etablissement="ailleurs")]
                ),
                "dograh:essai",
            )
    finally:
        await connexion.close()


# --------------------------------------------------------------------------- #
# 3. Hours changed DIRECTLY in the database, heard at the next pick-up (B3)
# --------------------------------------------------------------------------- #


async def _decroche_au_clavier(contexte):
    from api.services.pipecat import etat_ouverture

    reel = etat_ouverture.injecter_etat_ouverture
    with (
        patch.object(
            text_chat_runner,
            "injecter_etat_ouverture",
            lambda ctx, cfg, **kw: reel(ctx, cfg, maintenant=DIMANCHE_11H, **kw),
        ),
        patch.object(
            text_chat_runner,
            "lire_annonce_ouverture",
            AsyncMock(return_value=ReglagesAnnonceOuverture()),
        ),
    ):
        return await _jouer_au_clavier({}, contexte, OrganizationPreferences())


async def _attendre(condition, delai=10.0):
    fin = asyncio.get_running_loop().time() + delai
    while asyncio.get_running_loop().time() < fin:
        if await condition():
            return True
        await asyncio.sleep(0.1)
    return False


@pytest.mark.asyncio
async def test_horaires_changes_en_base_entendus_au_decroche_suivant(base_prete):
    miroir, redis = _Miroir(base_prete), _RedisFactice()
    a, b, c = _rattachee(miroir, redis)
    ecoute = synchro.Ecoute()
    with a, b, c:
        await module_stockage.enregistrer_phrases(ORGANISATION, PHRASES, "dograh:essai")
        await module_stockage.enregistrer_etablissements(
            ORGANISATION, CATALOGUE, "dograh:essai"
        )
        contexte = {"direction": "inbound", "etablissement_id": "creil"}
        avant = await _decroche_au_clavier(contexte)
        assert avant["etat_ouverture"] == "FERME"
        assert avant["runtime_configuration"]["etablissement"]["lu_depuis"] == "copie"

        await ecoute.actualiser()
        try:
            client = await asyncpg.connect(f"{_serveur()}/{base_prete}")
            try:
                await client.execute(
                    "UPDATE mark.site SET horaires_texte = $1 WHERE cle = 'creil'",
                    HORAIRES_DIMANCHE,
                )
            finally:
                await client.close()

            async def copie_a_jour():
                return (await module_copie.lire_copie(ORGANISATION))[0].etablissements[
                    0
                ].horaires_ouverture == HORAIRES_DIMANCHE

            assert await _attendre(copie_a_jour), (
                "the notification did not reach the copy"
            )
        finally:
            await ecoute.fermer()

        apres = await _decroche_au_clavier(contexte)
        assert apres["horaires_ouverture"] == HORAIRES_DIMANCHE
        assert apres["etat_ouverture"] == "OUVERT"
        # The mirror follows: the fallback when the database does not answer.
        assert (
            miroir.lignes["ETABLISSEMENTS"]["etablissements"][0]["horaires_ouverture"]
            == HORAIRES_DIMANCHE
        )


# --------------------------------------------------------------------------- #
# 4. R7: the resync, proved on a red case; invalid hours refused
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_la_resynchronisation_rattrape_une_notification_manquee(base_prete):
    miroir, redis = _Miroir(base_prete), _RedisFactice()
    a, b, c = _rattachee(miroir, redis)
    with a, b, c:
        await module_stockage.enregistrer_etablissements(
            ORGANISATION, CATALOGUE, "dograh:essai"
        )
        assert await synchro.resynchroniser(ORGANISATION) == "identique"

        client = await asyncpg.connect(f"{_serveur()}/{base_prete}")
        try:
            # 🔴 The red case: a write the notification never announces.
            await client.execute(
                "ALTER TABLE mark.site DISABLE TRIGGER site_referentiel"
            )
            await client.execute(
                "UPDATE mark.site SET horaires_texte = $1 WHERE cle = 'creil'",
                HORAIRES_DIMANCHE,
            )
            await client.execute(
                "ALTER TABLE mark.site ENABLE TRIGGER site_referentiel"
            )
        finally:
            await client.close()
        perime = (await module_copie.lire_copie(ORGANISATION))[0]
        assert perime.etablissements[0].horaires_ouverture == HORAIRES, (
            "the copy was already right: no red case"
        )

        assert await synchro.resynchroniser(ORGANISATION) == "corrigee"
        assert (await module_copie.lire_copie(ORGANISATION))[0].etablissements[
            0
        ].horaires_ouverture == HORAIRES_DIMANCHE
        assert await synchro.resynchroniser(ORGANISATION) == "identique"


@pytest.mark.asyncio
async def test_deux_ecritures_rapprochees_la_copie_garde_la_plus_recente(
    base_prete, monkeypatch
):
    """Revue 9: two notifications close together start two resyncs; the one that read the
    OLDER state must never publish over the newer one."""
    horaires_3 = chr(10).join([f"{j} : 10h-12h" for j in JOURS] + ["dimanche : fermé"])
    miroir, redis = _Miroir(base_prete), _RedisFactice()
    a, b, c = _rattachee(miroir, redis)
    with a, b, c:
        await module_stockage.enregistrer_etablissements(
            ORGANISATION, CATALOGUE, "dograh:essai"
        )
        await synchro.resynchroniser(ORGANISATION)

        vraie = synchro.lire_depuis_la_base
        feu = asyncio.Event()
        appels = {"n": 0}

        async def lente_la_premiere_fois(*args, **kwargs):
            appels["n"] += 1
            premiere = appels["n"] == 1
            copie = await vraie(*args, **kwargs)
            if premiere:
                await feu.wait()  # held between its read and its publication
            return copie

        monkeypatch.setattr(synchro, "lire_depuis_la_base", lente_la_premiere_fois)

        async def ecrire(horaires):
            client = await asyncpg.connect(f"{_serveur()}/{base_prete}")
            try:
                await client.execute(
                    "UPDATE mark.site SET horaires_texte = $1 WHERE cle = 'creil'",
                    horaires,
                )
            finally:
                await client.close()

        await ecrire(HORAIRES_DIMANCHE)
        premiere = asyncio.create_task(synchro.resynchroniser(ORGANISATION))
        await asyncio.sleep(0.3)  # the first one has read write 1
        await ecrire(horaires_3)
        seconde = asyncio.create_task(synchro.resynchroniser(ORGANISATION))
        await asyncio.sleep(0.5)
        feu.set()
        await asyncio.gather(premiere, seconde)
        copie = await module_copie.lire_copie_complete(ORGANISATION)
        assert copie.etablissements.etablissements[0].horaires_ouverture == horaires_3


@pytest.mark.asyncio
async def test_une_copie_plus_ancienne_ne_remplace_jamais_la_publiee():
    """Revue 9, across processes (no shared lock): the journal line read decides."""
    redis = _RedisFactice()
    with patch.object(module_copie, "_redis", AsyncMock(return_value=redis)):
        recente = module_copie.CopieOrganisation(
            etablissements=CATALOGUE, source="base_client", journal_id=5
        )
        ancienne = module_copie.CopieOrganisation(source="base_client", journal_id=4)
        assert await module_copie.publier_copie(ORGANISATION, recente) is True
        assert await module_copie.publier_copie(ORGANISATION, ancienne) is False
        document = json.loads(redis.valeurs[module_copie.cle_copie(ORGANISATION)])
        assert document["journal_id"] == 5 and document["catalogue"]["etablissements"]


@pytest.mark.asyncio
async def test_des_horaires_illisibles_sont_refuses_et_les_precedents_gardes(
    base_prete,
):
    miroir, redis = _Miroir(base_prete), _RedisFactice()
    a, b, c = _rattachee(miroir, redis)
    with a, b, c:
        await module_stockage.enregistrer_etablissements(
            ORGANISATION, CATALOGUE, "dograh:essai"
        )
        await synchro.resynchroniser(ORGANISATION)
        client = await asyncpg.connect(f"{_serveur()}/{base_prete}")
        try:
            await client.execute(
                "UPDATE mark.site SET horaires_texte = 'ouvert quand on est là' WHERE cle = 'creil'"
            )
        finally:
            await client.close()
        await synchro.resynchroniser(ORGANISATION)
        copie = await module_copie.lire_copie_complete(ORGANISATION)
        assert copie.etablissements.etablissements[0].horaires_ouverture == HORAIRES
        assert len(copie.refus) == 1 and "hours refused" in copie.refus[0]
        document = json.loads(redis.valeurs[module_copie.cle_copie(ORGANISATION)])
        assert document["source"] == "base_client" and document["refus"] == copie.refus


@pytest.mark.asyncio
async def test_copie_absente_et_base_lente_le_decroche_n_attend_pas(
    base_prete, monkeypatch
):
    """Revue 10: no copy in memory and a client database slow to answer: the pick-up reads
    the mirror within a short delay instead of waiting for the database ; the copy is then
    rebuilt from the database in the background (B3)."""
    import time

    miroir, redis = _Miroir(base_prete), _RedisFactice()
    miroir.lignes["ETABLISSEMENTS"] = CATALOGUE.model_dump(mode="json")
    vraie = synchro.connecter

    async def lente(nom):
        await asyncio.sleep(2)
        return await vraie(nom)

    monkeypatch.setattr(synchro, "connecter", lente)
    a, b, c = _rattachee(miroir, redis)
    with a, b, c:
        debut = time.monotonic()
        copie = await module_copie.lire_copie_complete(ORGANISATION)
        assert time.monotonic() - debut < 1.2
        assert copie.etablissements == CATALOGUE and copie.lu_depuis == "stockage"
        for _ in range(40):
            brut = redis.valeurs.get(module_copie.cle_copie(ORGANISATION))
            if brut and json.loads(brut)["source"] == "base_client":
                break
            await asyncio.sleep(0.1)
        assert (
            json.loads(redis.valeurs[module_copie.cle_copie(ORGANISATION)])["source"]
            == "base_client"
        )


@pytest.mark.asyncio
async def test_terme_et_phrase_refuses_gardent_leur_valeur_precedente(base_prete):
    """Revue 11: like the hours, a refused lexicon term or sentence keeps its previous value
    (never silently dropped), and the refusal is reported."""
    from api.schemas.phrases import MAX_LONGUEUR_CONTENU

    miroir, redis = _Miroir(base_prete), _RedisFactice()
    a, b, c = _rattachee(miroir, redis)
    with a, b, c:
        await module_stockage.enregistrer_etablissements(
            ORGANISATION, CATALOGUE, "dograh:essai"
        )
        await module_stockage.enregistrer_phrases(ORGANISATION, PHRASES, "dograh:essai")
        await synchro.resynchroniser(ORGANISATION)
        client = await asyncpg.connect(f"{_serveur()}/{base_prete}")
        try:
            await client.execute(
                "UPDATE mark.site SET termes_lexique = '[{\"terme\": \"\"}]' WHERE cle = 'creil'"
            )
            await client.execute(
                "UPDATE mark.phrase SET contenu = $1 WHERE variable = 'mentions'",
                "x" * (MAX_LONGUEUR_CONTENU + 1),
            )
        finally:
            await client.close()
        await synchro.resynchroniser(ORGANISATION)
        copie = await module_copie.lire_copie_complete(ORGANISATION)
        creil = copie.etablissements.etablissements[0]
        assert [t.terme for t in creil.termes_lexique] == ["Gamme Alpha"]
        assert {p.variable: p.contenu for p in copie.phrases.phrases}["mentions"] == (
            "Cet appel est noté."
        )
        assert any("term refused" in r for r in copie.refus)
        assert any("mentions" in r for r in copie.refus)


@pytest.mark.asyncio
async def test_base_injoignable_lappel_lit_le_miroir(monkeypatch):
    """The call never depends on the client's database answering: no copy in memory and
    the database down, the mirror (last values known good) is read."""
    monkeypatch.setenv(schema.VARIABLE_ENV, "postgresql://u:p@127.0.0.1:1")
    miroir, redis = _Miroir("mark_essai_absente"), _RedisFactice()
    miroir.lignes["ETABLISSEMENTS"] = CATALOGUE.model_dump(mode="json")
    a, b, c = _rattachee(miroir, redis)
    with a, b, c:
        catalogue, origine = await module_copie.lire_copie(ORGANISATION)
        assert catalogue == CATALOGUE and origine == "stockage"
        assert await synchro.resynchroniser(ORGANISATION) == "indisponible"


def test_base_injoignable_lecran_nenregistre_rien_et_le_dit(monkeypatch):
    monkeypatch.setenv(schema.VARIABLE_ENV, "postgresql://u:p@127.0.0.1:1")
    miroir = _Miroir("mark_essai_absente")
    app = FastAPI()
    app.include_router(route_etablissements.router)
    app.include_router(route_etablissements.routeur_phrases)
    app.dependency_overrides[get_user_with_selected_organization] = lambda: (
        SimpleNamespace(id=1, provider_id="p", selected_organization_id=ORGANISATION)
    )
    with (
        patch.object(module_stockage, "db_client", miroir),
        patch.object(rattachement, "db_client", miroir),
        patch.object(
            route_etablissements.db_client,
            "lister_numeros_de_lorganisation",
            AsyncMock(return_value=[]),
        ),
    ):
        client = TestClient(app)
        assert client.get("/organizations/etablissements").status_code == 503
        reponse = client.put(
            "/organizations/phrases", json=PHRASES.model_dump(mode="json")
        )
        assert (
            reponse.status_code == 503
            and "Nothing was changed" in reponse.json()["detail"]
        )
        assert "PHRASES" not in miroir.lignes


# --------------------------------------------------------------------------- #
# 5. The routes of the « Client data » and « Team and routing » themes
# --------------------------------------------------------------------------- #


def test_creer_a_lecran_verse_lexistant_puis_rattache(base_essai):
    from api.routes import base_client as route_base_client

    miroir, redis = _Miroir(), _RedisFactice()
    miroir.lignes["ETABLISSEMENTS"] = CATALOGUE.model_dump(mode="json")
    miroir.lignes["PHRASES"] = PHRASES.model_dump(mode="json")
    app = FastAPI()
    app.include_router(route_base_client.router)
    app.include_router(route_base_client.routeur_equipe)
    app.dependency_overrides[get_user_with_selected_organization] = lambda: (
        SimpleNamespace(id=1, provider_id="p", selected_organization_id=ORGANISATION)
    )
    a, b, c = _rattachee(miroir, redis)
    with a, b, c:
        client = TestClient(app)
        # No database yet: the team cannot be edited, the state says so.
        assert client.get("/organizations/equipe").status_code == 409
        etat = client.get("/organizations/base-client").json()
        assert etat["nom_base"] is None and etat["serveur_configure"] is True

        reponse = client.post(
            "/organizations/base-client/creer", json={"nom_base": base_essai}
        )
        assert reponse.status_code == 200, reponse.text
        etat = reponse.json()
        assert (etat["nom_base"], etat["joignable"], etat["version"]) == (
            base_essai,
            True,
            etat["version_attendue"],
        )
        assert etat["derniere_ecriture"] is not None and etat["conservation"]
        assert miroir.lignes["BASE_CLIENT"]["nom_base"] == base_essai

        # What was set on screen before is now in the database (and the copy reads it).
        assert (
            json.loads(redis.valeurs[module_copie.cle_copie(ORGANISATION)])["source"]
            == "base_client"
        )

        equipe = {
            "personnes": [{"cle": "p1", "prenom": "Alice"}],
            "sujets": [{"code": "devis", "libelle": "Devis", "destinataires": ["p1"]}],
        }
        assert client.put("/organizations/equipe", json=equipe).status_code == 200
        assert client.get("/organizations/equipe").json()["sujets"][0][
            "destinataires"
        ] == ["p1"]

        table = etat["conservation"][0]["table_nom"]
        reponse = client.put(
            "/organizations/base-client/conservation",
            json=[{"table_nom": table, "duree_jours": 42}],
        )
        assert reponse.status_code == 200
        assert {
            c["table_nom"]: c["duree_jours"] for c in reponse.json()["conservation"]
        }[table] == 42
        refus = client.put(
            "/organizations/base-client/conservation",
            json=[{"table_nom": "inconnue", "duree_jours": 5}],
        )
        assert refus.status_code == 422

        # A second create on an attached organization is refused; a bad name too.
        assert (
            client.post(
                "/organizations/base-client/creer", json={"nom_base": base_essai}
            ).status_code
            == 422
        )
        assert (
            client.put(
                "/organizations/base-client", json={"nom_base": "Pas-Un-Nom"}
            ).status_code
            == 422
        )
        assert (
            client.post("/organizations/base-client/mettre-a-niveau").json()["version"]
            == etat["version_attendue"]
        )


class _MiroirMulti:
    """organization_configurations of SEVERAL organizations, in memory."""

    def __init__(self):
        self.lignes = {}

    async def get_configuration(self, organisation, cle):
        valeur = self.lignes.get((organisation, cle))
        return SimpleNamespace(value=valeur) if valeur is not None else None

    async def upsert_configuration(self, organisation, cle, valeur):
        self.lignes[(organisation, cle)] = valeur

    async def get_all_configurations_by_key(self, cle):
        return [
            {"organization_id": org, "value": valeur}
            for (org, c), valeur in self.lignes.items()
            if c == cle and valeur
        ]


def test_une_base_dune_autre_organisation_ne_se_rattache_ni_ne_se_recree(base_essai):
    """Revue 1 (cloisonnement) : the name of a database attached to organization A is refused
    to organization B, by « attach » and by « create » ; « create » refuses a database that
    already exists on the server, even unattached."""
    from api.routes import base_client as route_base_client

    autre = ORGANISATION + 1
    miroir, redis = _MiroirMulti(), _RedisFactice()
    app = FastAPI()
    app.include_router(route_base_client.router)
    qui = {"org": ORGANISATION}
    app.dependency_overrides[get_user_with_selected_organization] = lambda: (
        SimpleNamespace(id=1, provider_id="p", selected_organization_id=qui["org"])
    )
    a, b, c = _rattachee(miroir, redis)
    with a, b, c:
        client = TestClient(app)
        cree = client.post(
            "/organizations/base-client/creer", json={"nom_base": base_essai}
        )
        assert cree.status_code == 200, cree.text

        qui["org"] = autre
        rattache = client.put(
            "/organizations/base-client", json={"nom_base": base_essai}
        )
        assert rattache.status_code == 409, rattache.text
        assert "another organization" in rattache.json()["detail"]
        recree = client.post(
            "/organizations/base-client/creer", json={"nom_base": base_essai}
        )
        assert recree.status_code == 409, recree.text
        assert miroir.lignes.get((autre, "BASE_CLIENT")) in (
            None,
            {"nom_base": None, "rattachee_le": None},
        )

        # Detached from A, the database still exists: « create » still refuses it, « attach » now works.
        qui["org"] = ORGANISATION
        assert (
            client.put(
                "/organizations/base-client", json={"nom_base": None}
            ).status_code
            == 200
        )
        qui["org"] = autre
        assert (
            client.post(
                "/organizations/base-client/creer", json={"nom_base": base_essai}
            ).status_code
            == 409
        )
        assert (
            client.put(
                "/organizations/base-client", json={"nom_base": base_essai}
            ).status_code
            == 200
        )


# --------------------------------------------------------------------------- #
# 6. Branched (R1): the routes are published, the worker runs the resync
# --------------------------------------------------------------------------- #


def test_les_routes_figurent_dans_la_spec_publiee():
    from api.app import app

    chemins = app.openapi()["paths"]
    for chemin in (
        "",
        "/creer",
        "/mettre-a-niveau",
        "/resynchroniser",
        "/conservation",
    ):
        assert f"/api/v1/organizations/base-client{chemin}" in chemins
    assert "/api/v1/organizations/equipe" in chemins


def test_le_worker_ecoute_et_resynchronise_au_demarrage_puis_regulierement():
    from api.tasks.arq import WorkerSettings

    taches = [
        t for t in WorkerSettings.cron_jobs if t.coroutine is synchro.tic_de_synchro
    ]
    assert len(taches) == 1 and taches[0].run_at_startup
    assert len(taches[0].minute) >= 12  # at least every five minutes
