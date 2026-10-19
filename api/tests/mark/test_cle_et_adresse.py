"""[.mark] La bibliothèque de clés : protocole, fournisseur libre et adresse rattachée à la clé
(fiabilite-orchestration, lot 10, F10).

Le menu d'avant devient « Protocole » (la clé ``fournisseur`` des données, inchangée) ; un champ
« Fournisseur » en texte libre s'ajoute ; l'adresse du fournisseur est rattachée à la clé. Une clé
qui a une adresse ne part que vers CETTE adresse, sans quoi le réglage le dit. Les clés d'avant
(fournisseur vide, adresse vide) se comportent exactement comme avant.

| Test | Ce qu'il prouve |
|---|---|
| clés d'avant | données rangées identiques à celles d'avant, vue sans fournisseur libre ni adresse, résolution inchangée |
| création | fournisseur libre et adresse rangés (adresse sans barre finale), rendus par la liste, la clé jamais renvoyée |
| adresse refusée | pas de http(s), pas d'hôte, identifiants / paramètres / ancre : 422, sans écho de la clé |
| rattachement | une clé d'avant reçoit un fournisseur et une adresse, les retire ; la clé ne bouge pas ; une clé hors bibliothèque ou d'une autre organisation : 404 |
| adresse concordante | la clé part (chemin ignoré, hôte et port comptent) |
| adresse discordante (R1) | par la vraie résolution : enregistrement refusé en le disant ; à l'appel, journal d'erreur, la clé ne part jamais |
| service sans adresse réglable | un service qui n'a pas de ``base_url`` (transcription AssemblyAI) vise celle de son fournisseur : rien à comparer, la clé part |
| bloc du greffier | la référence d'un bloc annexe est refusée si son ``base_url`` n'est pas l'adresse de la clé |
| après l'appel, appelant simulé | ils visent l'adresse de leur fournisseur : une clé qui a la sienne y est refusée |
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from api.schemas.ai_model_configuration import EffectiveAIModelConfiguration
from api.services import bibliotheque_cles as bibliotheque
from api.services import cles_reference
from api.services.bibliotheque_cles_adresse import (
    AdresseInvalide,
    meme_serveur,
    normaliser_l_adresse,
    origine_de,
)
from api.tests.mark.boucle_isolee import (
    executer_sans_toucher_la_boucle_courante as executer,
)
from api.tests.mark.test_bibliotheque_cles import (  # noqa: F401  (fixtures et aides partagées)
    ORG,
    _configuration,
    base,
    ecran,
)

ADRESSE = "https://api.fournisseur-test.example/v1"


@pytest.fixture
def coffre(base):
    """Le faux coffre, avec la mise à jour des données (``update_credential`` du vrai client)."""

    async def update_credential(uuid, organization_id, name=None, credential_data=None):
        ligne = await base.coffre.get_credential_by_uuid(uuid, organization_id)
        if ligne is not None and name is not None:
            ligne.name = name
        if ligne is not None and credential_data is not None:
            ligne.credential_data = credential_data
        return ligne

    base.db.update_credential = update_credential
    return base.coffre


def _poser_une_cle_a_adresse(coffre, adresse=ADRESSE):
    coffre.poser(
        "cle-a-adresse",
        ORG,
        "Mistral chez le fournisseur",
        bibliotheque.donnees_d_une_cle("mistral", "SECRET-ADR", "Fournisseur test", adresse),
    )


def test_les_cles_d_avant_ne_changent_pas(ecran, base):
    assert bibliotheque.donnees_d_une_cle("mistral", "SECRET") == {
        "token": "SECRET",
        "fournisseur": "mistral",
        "mark_bibliotheque": True,
    }
    liste = ecran.get("/cles").json()
    assert liste and all(c["nom_fournisseur"] is None and c["adresse"] is None for c in liste)
    # Résolue comme avant, sans comparer d'adresse.
    resolue = executer(
        cles_reference.resoudre_les_cles(
            _configuration("mark-cle:cle-mistral", "x"), ORG, strict=True
        )
    )
    assert resolue.llm.api_key == "SECRET-M"


def test_la_creation_range_le_fournisseur_libre_et_l_adresse(ecran, base):
    reponse = ecran.post(
        "/cles",
        json={
            "fournisseur": "mistral",
            "nom": "Scaleway Mistral",
            "cle": "SECRET-SCW-1",
            "nom_fournisseur": " Scaleway ",
            "adresse": f" {ADRESSE}/ ",
        },
    )
    assert reponse.status_code == 201
    corps = reponse.json()
    assert corps["nom_fournisseur"] == "Scaleway" and corps["adresse"] == ADRESSE
    assert corps["fournisseur"] == "mistral"
    assert "SECRET" not in str(corps) and "SECRET" not in str(ecran.get("/cles").json())
    rangee = base.coffre.lignes[corps["uuid"]].credential_data
    assert rangee["nom_fournisseur"] == "Scaleway" and rangee["adresse"] == ADRESSE
    assert rangee["token"] == "SECRET-SCW-1"
    # Sans l'un ni l'autre : rien de plus que la clé d'avant.
    sans = ecran.post(
        "/cles", json={"fournisseur": "mistral", "nom": "Simple", "cle": "SECRET-SIMPLE"}
    ).json()
    assert set(base.coffre.lignes[sans["uuid"]].credential_data) == {
        "token",
        "fournisseur",
        "mark_bibliotheque",
    }


@pytest.mark.parametrize(
    "adresse",
    [
        "ftp://serveur.example/v1",
        "api.fournisseur-test.example/v1",
        "https://",
        "https://utilisateur:motdepasse@api.example/v1",
        "https://api.example/v1?key=abc",
        "https://api.example/v1#ancre",
        "https://api.example:port/v1",
    ],
)
def test_une_adresse_inutilisable_est_refusee_sans_echo_de_la_cle(ecran, adresse):
    reponse = ecran.post(
        "/cles",
        json={"fournisseur": "mistral", "nom": "Mauvaise", "cle": "SECRET-ECHO-1", "adresse": adresse},
    )
    assert reponse.status_code == 422
    assert "SECRET-ECHO" not in reponse.text
    with pytest.raises(AdresseInvalide):
        normaliser_l_adresse(adresse)


def test_une_cle_d_avant_recoit_puis_perd_son_fournisseur_et_son_adresse(ecran, coffre):
    avant = dict(coffre.lignes["cle-mistral"].credential_data)
    reponse = ecran.patch(
        "/cles/cle-mistral", json={"nom_fournisseur": "Chez nous", "adresse": ADRESSE + "/"}
    )
    assert reponse.status_code == 200
    assert reponse.json()["adresse"] == ADRESSE and reponse.json()["nom_fournisseur"] == "Chez nous"
    donnees = coffre.lignes["cle-mistral"].credential_data
    assert donnees["token"] == "SECRET-M" and donnees["fournisseur"] == "mistral"
    assert "SECRET" not in reponse.text
    # Vider retire : la clé redevient celle d'avant, à l'octet.
    retiree = ecran.patch("/cles/cle-mistral", json={"nom_fournisseur": "", "adresse": None})
    assert retiree.status_code == 200
    assert coffre.lignes["cle-mistral"].credential_data == avant


def test_le_rattachement_refuse_ce_qui_n_est_pas_une_cle_de_la_bibliotheque(ecran, coffre):
    for uuid in ("outil-http", "cle-autre-org", "jamais-vue"):
        assert ecran.patch(f"/cles/{uuid}", json={"adresse": ADRESSE}).status_code == 404
    assert "adresse" not in coffre.lignes["outil-http"].credential_data
    assert ecran.patch("/cles/cle-mistral", json={"adresse": "ftp://x.example"}).status_code == 422


def test_la_comparaison_des_adresses_ne_regarde_que_le_serveur():
    assert origine_de("https://API.exemple.test/v1") == ("https", "api.exemple.test", 443)
    assert meme_serveur(None, "https://n-importe.example")  # clé d'avant
    assert meme_serveur(ADRESSE, "https://api.fournisseur-test.example/autre/chemin/")
    assert meme_serveur(ADRESSE, "https://api.fournisseur-test.example:443/v1")
    assert not meme_serveur(ADRESSE, "https://api.fournisseur-test.example:8443/v1")
    assert not meme_serveur(ADRESSE, "http://api.fournisseur-test.example/v1")
    assert not meme_serveur(ADRESSE, "https://api.autre.example/v1")
    assert not meme_serveur(ADRESSE, "")
    assert not meme_serveur(ADRESSE, None)


def _configuration_a_adresse(adresse_du_service):
    configuration = _configuration("mark-cle:cle-a-adresse", "x")
    return configuration.model_copy(
        update={"llm": configuration.llm.model_copy(update={"base_url": adresse_du_service})}
    )


def test_une_cle_part_vers_son_adresse(coffre, base):
    _poser_une_cle_a_adresse(coffre)
    resolue = executer(
        cles_reference.resoudre_les_cles(
            _configuration_a_adresse(ADRESSE + "/chat"), ORG, strict=True
        )
    )
    assert resolue.llm.api_key == "SECRET-ADR"


def test_une_cle_ne_part_jamais_vers_une_autre_adresse_sans_le_dire(coffre, base):
    _poser_une_cle_a_adresse(coffre)
    discordante = "https://api.mistral.ai/v1"
    with pytest.raises(cles_reference.CleIntrouvable, match="belongs to the address") as erreur:
        executer(
            cles_reference.resoudre_les_cles(
                _configuration_a_adresse(discordante), ORG, strict=True
            )
        )
    assert "SECRET" not in str(erreur.value)
    assert discordante in str(erreur.value) and ADRESSE in str(erreur.value)
    with patch.object(cles_reference.logger, "error") as journal:
        resolue = executer(
            cles_reference.resoudre_les_cles(
                _configuration_a_adresse(discordante), ORG, strict=False
            )
        )
    assert resolue.llm.api_key == "mark-cle:cle-a-adresse"  # la référence reste : jamais la clé
    assert "SECRET" not in str(resolue) and "belongs to the address" in journal.call_args.args[0]


def test_un_service_sans_adresse_reglable_vise_celle_de_son_fournisseur(coffre, base):
    """La transcription AssemblyAI n'a pas de ``base_url`` à régler : rien à comparer, la clé part."""
    coffre.poser(
        "cle-stt-a-adresse",
        ORG,
        "Transcription à adresse",
        bibliotheque.donnees_d_une_cle("assemblyai", "SECRET-STT", None, ADRESSE),
    )
    configuration = EffectiveAIModelConfiguration.model_validate(
        {
            "llm": {"provider": "mistral", "model": "mistral-small-latest", "api_key": "x"},
            "stt": {"provider": "assemblyai", "api_key": "mark-cle:cle-stt-a-adresse"},
        }
    )
    assert "base_url" not in type(configuration.stt).model_fields
    resolue = executer(cles_reference.resoudre_les_cles(configuration, ORG, strict=True))
    assert resolue.stt.get_all_api_keys() == ["SECRET-STT"]


def test_le_bloc_annexe_est_refuse_si_son_adresse_n_est_pas_celle_de_la_cle(coffre, base):
    _poser_une_cle_a_adresse(coffre)
    reference = "mark-cle:cle-a-adresse"
    ok = executer(
        cles_reference.cle_d_une_reference(
            reference, "mistral", ORG, "clerk", adresse_cible=ADRESSE
        )
    )
    assert ok == "SECRET-ADR"
    with patch.object(cles_reference.logger, "error") as journal:
        for cible in (None, "", "https://api.mistral.ai/v1"):
            assert (
                executer(
                    cles_reference.cle_d_une_reference(
                        reference, "mistral", ORG, "clerk", adresse_cible=cible
                    )
                )
                is None
            )
    assert journal.call_count == 3 and "SECRET" not in str(journal.call_args_list)
    # Une clé d'avant : jamais comparée.
    assert (
        executer(
            cles_reference.cle_d_une_reference(
                "mark-cle:cle-mistral", "mistral", ORG, "clerk", adresse_cible=None
            )
        )
        == "SECRET-M"
    )


def test_l_apres_appel_et_l_appelant_simule_n_envoient_pas_une_cle_a_adresse_ailleurs(coffre, base):
    """Ces deux usages visent l'adresse de leur fournisseur : une clé qui a la sienne y est refusée."""
    from api.services.apres_appel.reglages import CleManquante, secret
    from api.services.appel_simule.serie import cle_d_identifiant

    _poser_une_cle_a_adresse(coffre)
    with pytest.raises(CleManquante, match="does not send to a chosen address") as erreur:
        executer(secret("mark-cle:cle-a-adresse", ORG, "mistral", "the summary"))
    assert "SECRET" not in str(erreur.value)
    assert executer(cle_d_identifiant(ORG, "cle-a-adresse")) is None
    # Une clé d'avant : inchangée.
    assert executer(secret("mark-cle:cle-mistral", ORG, "mistral", "the summary")) == "SECRET-M"
    assert executer(cle_d_identifiant(ORG, "cle-mistral")) == "SECRET-M"
