"""[.mark] Non-regression test for the team known to the agent (chantier l-agent-collegue, L1).

The questions this file answers (C1 to C6, R1, X2):

    With « Team known to the agent » on, does a call -- the keyboard path RUN up to the
    engine, and the phone path in the same order -- receive ``{{equipe}}``: one line per
    active person of the establishment served and of the whole company, with the role and
    what the person takes care of? Is a phone number or an e-mail on a line ONLY when the
    client allowed it for that person (asserted both ways)? Is a description changed
    DIRECTLY in the client's database heard at the next pick-up? With the switch off, is
    the call EXACTLY the call of before (zero loss, not even the stamp)? Does the summary
    receive the team's names only when the switch is on?

Why it exists
-------------
🔴 Every line of this feature is wrapped so that it never stops a call: a team that does
not reach the context, or a copy that stops carrying it, fails in silence (R1). Only a
test that plays the real pick-up and asserts what the agent receives sees it.

⚠️ What this file does NOT prove: what the model does with the lines (bench), the screen
(``ui/src/components/mark/``).
"""

from __future__ import annotations

import inspect
import re
from unittest.mock import AsyncMock, patch

import asyncpg
import httpx
import pytest

from api.schemas.annonce_ouverture import ReglagesAnnonceOuverture
from api.schemas.apres_appel import ReglagesSynthese
from api.schemas.base_client import Equipe, Personne, Sujet
from api.schemas.organization_preferences import OrganizationPreferences
from api.schemas.phrases import CataloguePhrases
from api.services.apres_appel import synthese
from api.services.equipe.appel import (
    injecter_equipe,
    ligne,
    noms_pour_la_synthese,
    personnes_de_lappel,
)
from api.services.etablissements import copie as module_copie
from api.services.workflow import text_chat_runner
from api.tests.mark.test_adresse_etablissement import _jouer_au_clavier
from api.tests.mark.test_base_client import (  # noqa: F401 -- fixtures
    ORGANISATION,
    _attendre,
    _Miroir,
    _rattachee,
    _RedisFactice,
    _serveur,
    base_essai,
    base_prete,
)
from api.tests.mark.test_base_client import CATALOGUE as CATALOGUE_BASE
from api.tests.mark.test_etablissements_heritage import CATALOGUE

# Neutral people (X5): no trade, no brand.
ACCUEIL = Personne(
    cle="camille",
    prenom="Camille",
    nom="Martin",
    role="Accueil",
    description="Prend les demandes de rendez-vous et les réclamations.",
    telephone="+33611111111",
    mail="camille@example.org",
    etablissement="creil",
    divulguer_telephone=True,
)
COMPTA = Personne(
    cle="sacha",
    prenom="Sacha",
    nom="Bernard",
    role="Comptabilité",
    description="Répond aux questions de facture.",
    telephone="+33622222222",
    mail="sacha@example.org",
    divulguer_mail=True,
)
AILLEURS = Personne(cle="noa", prenom="Noa", role="Planning", etablissement="senlis")
PARTI = Personne(cle="eden", prenom="Eden", etablissement="creil", actif=False)
EQUIPE = Equipe(
    personnes=[ACCUEIL, COMPTA, AILLEURS, PARTI],
    sujets=[Sujet(code="facture", libelle="Facture", destinataires=["sacha"])],
)


# --------------------------------------------------------------------------- #
# 1. The line the agent reads (C4): no coordinate unless allowed
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("tel", [False, True])
@pytest.mark.parametrize("mail", [False, True])
def test_une_coordonnee_n_apparait_que_si_sa_divulgation_est_autorisee(tel, mail):
    personne = ACCUEIL.model_copy(
        update={"divulguer_telephone": tel, "divulguer_mail": mail}
    )
    texte = ligne(personne)
    assert ("+33611111111" in texte) is tel
    assert ("camille@example.org" in texte) is mail
    assert "Camille Martin, Accueil : Prend les demandes" in texte
    assert texte.endswith("[clé : camille]")


def test_seules_les_personnes_actives_de_letablissement_et_de_lentreprise():
    assert [p.cle for p in personnes_de_lappel(EQUIPE, "creil")] == ["camille", "sacha"]
    assert [p.cle for p in personnes_de_lappel(EQUIPE, "senlis")] == ["sacha", "noa"]
    # No establishment served: the whole-company people only.
    assert [p.cle for p in personnes_de_lappel(EQUIPE, None)] == ["sacha"]


def test_interrupteur_eteint_le_contexte_revient_identique_sans_estampille():
    contexte = {"direction": "inbound"}
    assert injecter_equipe(contexte, {}, EQUIPE, "creil") == (contexte, None)
    assert injecter_equipe(contexte, {"equipe_connue": False}, EQUIPE, "creil") == (
        contexte,
        None,
    )


def test_une_valeur_deja_la_est_gardee():
    """A replay or a pre-call fetch that already gave ``equipe`` wins (like the others)."""
    enrichi, _ = injecter_equipe(
        {"equipe": "donnée par l'appel"}, {"equipe_connue": True}, EQUIPE, "creil"
    )
    assert enrichi["equipe"] == "donnée par l'appel"
    assert enrichi["equipe_cles"] == ["camille", "sacha"]


def test_la_liste_fermee_n_est_jamais_celle_qu_un_autre_a_ecrite():
    """``equipe_cles`` decides who the tool may reach: a list already in the context (a replay,
    the client's pre-call fetch) never survives the injection; after a fetch it is put back."""
    from api.services.equipe.appel import reaffirmer_equipe

    enrichi, estampille = injecter_equipe(
        {"equipe_cles": ["noa", "inconnu"]}, {"equipe_connue": True}, EQUIPE, "creil"
    )
    assert enrichi["equipe_cles"] == ["camille", "sacha"]
    contexte = {**enrichi, "runtime_configuration": {"equipe": estampille}}
    # The pre-call fetch is merged over the context after the injection.
    empoisonne = {**contexte, "equipe_cles": ["noa"]}
    assert reaffirmer_equipe(empoisonne)["equipe_cles"] == ["camille", "sacha"]
    # Nothing stamped (switch off): a list that came from elsewhere is removed.
    assert "equipe_cles" not in reaffirmer_equipe({"equipe_cles": ["noa"], "runtime_configuration": {}})
    assert reaffirmer_equipe({"direction": "inbound"}) == {"direction": "inbound"}


def test_la_description_est_bornee_et_ramenee_a_une_ligne():
    with pytest.raises(ValueError):
        Personne(cle="x", prenom="X", description="a" * 301)
    assert Personne(cle="x", prenom="X", description="  un\n  deux ").description == "un deux"
    assert Personne(cle="x", prenom="X", description="   ").description is None


# --------------------------------------------------------------------------- #
# 2. R1: the keyboard pick-up, RUN up to the engine
# --------------------------------------------------------------------------- #


async def _clavier(configurations, equipe=EQUIPE, contexte=None):
    with (
        patch.object(
            module_copie,
            "lire_copie_complete",
            AsyncMock(
                return_value=module_copie.CopieOrganisation(
                    etablissements=CATALOGUE,
                    phrases=CataloguePhrases(),
                    equipe=equipe,
                    lu_depuis="copie",
                )
            ),
        ),
        patch.object(
            text_chat_runner,
            "lire_annonce_ouverture",
            AsyncMock(return_value=ReglagesAnnonceOuverture()),
        ),
    ):
        return await _jouer_au_clavier(
            configurations,
            contexte or {"direction": "inbound", "etablissement_id": "creil"},
            OrganizationPreferences(),
        )


@pytest.mark.asyncio
async def test_clavier_interrupteur_allume_lagent_recoit_lequipe():
    persiste = await _clavier({"equipe_connue": True})
    lignes = persiste["equipe"].split("\n")
    assert lignes == [ligne(ACCUEIL), ligne(COMPTA)]
    assert persiste["equipe_cles"] == ["camille", "sacha"]
    # C4: the allowed coordinate only (Camille's phone, Sacha's mail), never the others.
    assert "+33611111111" in persiste["equipe"] and "camille@example.org" not in persiste["equipe"]
    assert "sacha@example.org" in persiste["equipe"] and "+33622222222" not in persiste["equipe"]
    assert "Noa" not in persiste["equipe"] and "Eden" not in persiste["equipe"]
    estampille = persiste["runtime_configuration"]["equipe"]
    assert estampille == {
        "personnes": 2,
        "cles": ["camille", "sacha"],
        "etablissement": "creil",
        "lu_depuis": "copie",
    }


@pytest.mark.asyncio
async def test_clavier_interrupteur_eteint_lappel_davant_a_lidentique():
    """🔒 X2: the same team in the copy, the switch off: the persisted context is exactly
    the one of a copy that holds no team at all."""
    avec = await _clavier({})
    sans = await _clavier({}, equipe=Equipe())
    assert avec == sans
    assert "equipe" not in avec and "equipe_cles" not in avec
    assert "equipe" not in avec["runtime_configuration"]


@pytest.mark.asyncio
async def test_clavier_allume_sans_equipe_le_dit_dans_lestampille():
    persiste = await _clavier({"equipe_connue": True}, equipe=Equipe())
    assert persiste["equipe"] == "" and persiste["equipe_cles"] == []
    assert persiste["runtime_configuration"]["equipe"]["personnes"] == 0


def test_le_telephone_injecte_lequipe_avant_la_persistance_et_lestampille():
    from api.services.pipecat import run_pipeline

    source = inspect.getsource(run_pipeline)
    position = lambda motif: re.search(motif, source).start()  # noqa: E731
    phrases = position(r"merged_call_context_vars = injecter_phrases\(")
    equipe = position(r"merged_call_context_vars, estampille_equipe = injecter_equipe\(")
    estampille = position(r'runtime_configuration\["equipe"\] = estampille_equipe')
    persistance = position(
        r"await db_client\.update_workflow_run\(\s*workflow_run_id, initial_context"
    )
    assert phrases < equipe < estampille < persistance
    assert "lecture_de_lappel.equipe" in source[equipe : equipe + 400]


# --------------------------------------------------------------------------- #
# 3. C2, C3: a change made DIRECTLY in the client's database, heard at the next pick-up
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_description_changee_en_base_entendue_au_decroche_suivant(base_prete):
    from api.db.bases_clients import connexion as schema
    from api.db.bases_clients.equipe import ecrire_equipe, lire_equipe
    from api.services.base_client import synchro
    from api.services.etablissements import stockage as module_stockage

    miroir, redis = _Miroir(base_prete), _RedisFactice()
    a, b, c = _rattachee(miroir, redis)
    equipe = Equipe(
        personnes=[
            Personne(cle="camille", prenom="Camille", etablissement="creil", description="Accueil.")
        ]
    )
    ecoute = synchro.Ecoute()
    with a, b, c:
        await module_stockage.enregistrer_etablissements(
            ORGANISATION, CATALOGUE_BASE, "dograh:essai"
        )
        connexion = await schema.connecter(base_prete)
        try:
            await ecrire_equipe(connexion, equipe, "dograh:essai")
            assert (await lire_equipe(connexion)).personnes[0].description == "Accueil."
        finally:
            await connexion.close()
        await module_copie.publier_copie(ORGANISATION)
        lue = await module_copie.lire_copie_complete(ORGANISATION)
        assert lue.lu_depuis == "copie" and lue.equipe.personnes[0].description == "Accueil."

        await ecoute.actualiser()
        try:
            client = await asyncpg.connect(f"{_serveur()}/{base_prete}")
            try:
                await client.execute(
                    "UPDATE mark.personne SET description = 'Planning et devis.', "
                    "joignable_par_transfert = true WHERE cle = 'camille'"
                )
            finally:
                await client.close()

            async def copie_a_jour():
                p = (await module_copie.lire_copie_complete(ORGANISATION)).equipe.personnes
                return bool(p) and p[0].description == "Planning et devis."

            assert await _attendre(copie_a_jour), "the notification did not reach the copy"
        finally:
            await ecoute.fermer()
        assert (
            await module_copie.lire_copie_complete(ORGANISATION)
        ).equipe.personnes[0].joignable_par_transfert is True


@pytest.mark.asyncio
async def test_un_sujet_change_en_base_est_notifie(base_prete):
    """008: the subjects and the routing notify like the rest of the referential."""
    from api.db.bases_clients import connexion as schema
    from api.db.bases_clients.equipe import ecrire_equipe

    connexion = await schema.connecter(base_prete)
    try:
        await connexion.execute(
            "INSERT INTO mark.entreprise (raison_sociale) VALUES ('Entreprise')"
        )
        await ecrire_equipe(
            connexion,
            Equipe(
                personnes=[Personne(cle="a", prenom="A")],
                sujets=[Sujet(code="facture", libelle="Facture", destinataires=["a"])],
            ),
            "dograh:essai",
        )
        tables = {
            r["table_nom"]
            for r in await connexion.fetch("SELECT table_nom FROM mark.journal_modif")
        }
        assert {"personne", "sujet", "personne_sujet"} <= tables
        lignes = await connexion.fetch(
            "SELECT ligne_id FROM mark.journal_modif WHERE table_nom = 'personne_sujet'"
        )
        assert all(re.fullmatch(r"\d+:\d+", r["ligne_id"]) for r in lignes)
    finally:
        await connexion.close()


@pytest.mark.asyncio
async def test_une_copie_v2_nest_plus_lue():
    redis = _RedisFactice()
    redis.valeurs[f"mark:etablissements:v2:{ORGANISATION}"] = "{}"
    with patch.object(module_copie, "_redis", AsyncMock(return_value=redis)):
        assert module_copie.cle_copie(ORGANISATION).startswith("mark:etablissements:v3:")


# --------------------------------------------------------------------------- #
# 4. C6: the summary receives the names, only with the switch on
# --------------------------------------------------------------------------- #


def test_les_noms_actifs_vont_a_la_synthese():
    assert noms_pour_la_synthese(EQUIPE) == ["Camille Martin", "Sacha Bernard", "Noa"]


@pytest.mark.asyncio
async def test_la_synthese_recoit_les_noms_dans_sa_requete():
    corps = []

    def modele(requete: httpx.Request) -> httpx.Response:
        import json

        corps.append(json.loads(requete.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "Résumé."}}]})

    lignes = [{"speaker": "caller", "text": "Je voudrais parler à Kamil pour ma facture."}]
    async with httpx.AsyncClient(transport=httpx.MockTransport(modele)) as client:
        await synthese.resumer("cle", ReglagesSynthese(), lignes, {}, client=client,
                               noms_equipe=["Camille Martin"])
        await synthese.resumer("cle", ReglagesSynthese(), lignes, {}, client=client)
    avec, sans = (c["messages"][1]["content"] for c in corps)
    assert "Camille Martin" in avec and "exactement ainsi" in avec
    assert "Camille Martin" not in sans and "exactement ainsi" not in sans


@pytest.mark.asyncio
async def test_les_noms_ne_partent_que_si_linterrupteur_est_allume():
    from types import SimpleNamespace

    from api.services.apres_appel import chaine

    def ctx(configurations):
        return SimpleNamespace(
            organization_id=ORGANISATION,
            run=SimpleNamespace(definition=SimpleNamespace(workflow_configurations=configurations)),
        )

    lecture = AsyncMock(return_value=module_copie.CopieOrganisation(equipe=EQUIPE))
    with patch.object(module_copie, "lire_copie_complete", lecture):
        assert await chaine._noms_de_lequipe(ctx({})) == []
        assert lecture.await_count == 0
        assert await chaine._noms_de_lequipe(ctx({"equipe_connue": True})) == [
            "Camille Martin",
            "Sacha Bernard",
            "Noa",
        ]
