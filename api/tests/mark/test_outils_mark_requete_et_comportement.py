"""[.mark] Builder partie 2, U3 sexies points 2 et 3 (E74) : la requête HTTP et le comportement commun des outils.

| Test | Ce qu'il prouve |
|---|---|
| emplacements | un paramètre placé dans le chemin, la requête, le corps et l'en-tête arrive au bon endroit de la vraie requête |
| avant | sans emplacement déclaré, rien ne change (corps pour POST, requête pour GET) |
| valeurs permises | une valeur hors liste est refusée avant d'envoyer ; le défaut est appliqué ; la liste est montrée au modèle |
| en-têtes | texte, variable et secret ; le secret vient de l'identifiant chiffré de l'organisation et n'est jamais montré |
| filtrage et copie | la fiche reçoit la réponse entière, le modèle ne lit que les chemins gardés |
| réponses simulées | servies seulement avec ``simuler=True`` ; un appel réel contacte le service |
| phrase avant | toujours / auto / jamais ; sans réglage, comme avant |
| mode d'exécution | arrière-plan : réponse immédiate puis résultat dans la fiche ; refusé pour un outil qui écrit |
| patience et repli | la phrase d'attente passe le seuil ; le repli est dit à l'échec |
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from pydantic import ValidationError

from api.schemas.tool import HttpApiConfig
from api.services.outils_mark import comportement, parametres, reponse, simulation
from api.services.outils_mark.comportement import executer_avec_comportement
from api.services.workflow.tools.custom_tool import execute_http_tool, tool_to_function_schema

MODULE = "api.services.workflow.tools.custom_tool"


def _outil(**config):
    return SimpleNamespace(
        tool_uuid="u-test",
        name="Chercher",
        description="Cherche.",
        category="http_api",
        definition={
            "schema_version": 1,
            "type": "http_api",
            "config": {"method": "POST", "url": "https://agenda.example.test/clients/{{id}}", "timeout_ms": 5000, **config},
        },
    )


def _reponse(code=200, corps=None):
    r = Mock(status_code=code, text="")
    r.json.return_value = corps if corps is not None else {"ok": True}
    return r


async def _envoyer(config, arguments, *, reponse_http=None, **options):
    with patch(f"{MODULE}.httpx.AsyncClient") as client:
        session = AsyncMock()
        session.request.return_value = reponse_http or _reponse()
        client.return_value.__aenter__.return_value = session
        resultat = await execute_http_tool(_outil(**config), arguments, **options)
    return resultat, session


PARAMETRES = [
    {"name": "id", "type": "string", "description": "Client.", "emplacement": "chemin"},
    {"name": "page", "type": "number", "description": "Page.", "emplacement": "requete"},
    {"name": "nom", "type": "string", "description": "Nom.", "emplacement": "corps"},
    {"name": "cle", "type": "string", "description": "Clé.", "emplacement": "en_tete"},
]
ARGUMENTS = {"id": "42", "page": 2, "nom": "Dupont", "cle": "abc"}


@pytest.mark.asyncio
async def test_chaque_parametre_arrive_au_bon_endroit():
    resultat, session = await _envoyer({"parameters": PARAMETRES}, ARGUMENTS)
    appel = session.request.call_args.kwargs
    assert resultat["status"] == "success"
    assert appel["url"] == "https://agenda.example.test/clients/42"  # chemin
    assert appel["params"] == {"page": 2}  # requête
    assert appel["json"] == {"nom": "Dupont"}  # corps, sans les autres
    assert appel["headers"]["cle"] == "abc"  # en-tête


@pytest.mark.asyncio
async def test_un_parametre_du_corps_d_un_get_part_dans_la_requete():
    _, session = await _envoyer(
        {"method": "GET", "parameters": PARAMETRES}, {"id": "1", "nom": "Dupont", "page": 3}
    )
    appel = session.request.call_args.kwargs
    assert appel["json"] is None and appel["params"] == {"page": 3, "nom": "Dupont"}


@pytest.mark.asyncio
async def test_sans_emplacement_le_comportement_d_avant_est_gardé():
    params = [{"name": "id", "type": "string", "description": "x"}, {"name": "jour", "type": "string", "description": "x"}]
    _, session = await _envoyer({"parameters": params}, {"id": "7", "jour": "demain"})
    assert session.request.call_args.kwargs["json"] == {"id": "7", "jour": "demain"}
    _, session = await _envoyer({"method": "GET", "parameters": params}, {"id": "7", "jour": "demain"})
    assert session.request.call_args.kwargs["params"] == {"id": "7", "jour": "demain"}


@pytest.mark.asyncio
async def test_valeur_hors_liste_refusee_defaut_applique_liste_montree_au_modele():
    params = [
        {"name": "id", "type": "string", "description": "x", "emplacement": "chemin"},
        {"name": "ton", "type": "string", "description": "x", "valeurs_permises": ["court", "long"], "defaut": "court"},
    ]
    resultat, session = await _envoyer({"parameters": params}, {"id": "1", "ton": "moyen"})
    assert resultat["status"] == "error" and "court, long" in resultat["error"]
    assert session.request.call_count == 0  # rien n'est parti
    _, session = await _envoyer({"parameters": params}, {"id": "1"})
    assert session.request.call_args.kwargs["json"] == {"ton": "court"}  # défaut
    schema = tool_to_function_schema(_outil(parameters=params))["function"]["parameters"]
    assert schema["properties"]["ton"]["enum"] == ["court", "long"]
    assert "ton" not in schema["required"]  # un paramètre à défaut n'est pas exigé du modèle


def test_un_defaut_hors_liste_est_refuse_a_l_enregistrement():
    with pytest.raises(ValidationError):
        HttpApiConfig(
            method="GET",
            url="https://a.example.test",
            parameters=[{"name": "t", "type": "string", "description": "x", "valeurs_permises": ["a"], "defaut": "b"}],
        )


@pytest.mark.asyncio
async def test_en_tetes_texte_variable_et_secret():
    credential = SimpleNamespace(credential_type="custom_header", credential_data={"header_name": "X", "header_value": "s3cret-valeur"})
    entrees = [
        {"nom": "X-Texte", "sorte": "texte", "valeur": "fixe"},
        {"nom": "X-Variable", "sorte": "variable", "valeur": "{{initial_context.canal}}"},
        {"nom": "X-Secret", "sorte": "secret", "identifiant_uuid": "cred-1"},
    ]
    with patch("api.services.outils_mark.en_tetes.db_client.get_credential_by_uuid", AsyncMock(return_value=credential)):
        resultat, session = await _envoyer(
            {"en_tetes_ext": entrees},
            {"id": "1"},
            call_context_vars={"canal": "telephone"},
            organization_id=5,
            include_request_headers=True,
        )
    envoyes = session.request.call_args.kwargs["headers"]
    assert envoyes["X-Texte"] == "fixe" and envoyes["X-Variable"] == "telephone" and envoyes["X-Secret"] == "s3cret-valeur"
    apercu = resultat["request_headers"]
    assert apercu["X-Secret"] != "s3cret-valeur" and "s3cret-valeur" not in str(apercu)  # masqué à l'écran


@pytest.mark.asyncio
async def test_un_secret_disparu_arrete_la_requete():
    with patch("api.services.outils_mark.en_tetes.db_client.get_credential_by_uuid", AsyncMock(return_value=None)):
        resultat, session = await _envoyer(
            {"en_tetes_ext": [{"nom": "X-S", "sorte": "secret", "identifiant_uuid": "c"}]}, {"id": "1"}, organization_id=5
        )
    assert resultat["status"] == "error" and session.request.call_count == 0


def test_un_en_tete_secret_ne_porte_pas_de_valeur():
    with pytest.raises(ValidationError):
        HttpApiConfig(method="GET", url="https://a.example.test", en_tetes_ext=[{"nom": "X", "sorte": "secret", "identifiant_uuid": "c", "valeur": "oups"}])


@pytest.mark.asyncio
async def test_la_fiche_recoit_la_reponse_entiere_le_modele_ne_lit_que_les_chemins_gardes():
    corps = {"client": {"id": 9, "nom": "Dupont", "iban": "FR76"}, "items": [{"n": "a"}, {"n": "b"}]}
    fiche: dict = {}
    resultat, _ = await _envoyer(
        {
            "chemins_gardes": ["client.nom", "items.1.n"],
            "copies_dans_la_fiche": [{"chemin": "client.id", "cle": "client_id"}, {"chemin": "absent.x", "cle": "rien"}],
        },
        {"id": "1"},
        reponse_http=_reponse(200, corps),
        fiche_cible=fiche,
    )
    assert fiche == {"client_id": 9}  # copié depuis la réponse entière, une valeur absente ne copie rien
    assert resultat["data"] == {"client": {"nom": "Dupont"}, "items": {"1": {"n": "b"}}}
    assert "iban" not in str(resultat["data"])


@pytest.mark.asyncio
async def test_une_erreur_n_est_ni_filtree_ni_copiee():
    fiche: dict = {}
    resultat, _ = await _envoyer(
        {"chemins_gardes": ["a"], "copies_dans_la_fiche": [{"chemin": "motif", "cle": "m"}]},
        {"id": "1"},
        reponse_http=_reponse(500, {"motif": "panne"}),
        fiche_cible=fiche,
    )
    assert resultat["status"] == "error" and resultat["data"] == {"motif": "panne"} and fiche == {}


@pytest.mark.asyncio
async def test_une_reponse_simulee_n_est_jamais_servie_hors_essai():
    simulees = [{"nom": "ok", "quand": {"id": "1"}, "statut": 200, "donnees": {"simule": True}}]
    # Appel réel (simuler non passé) : le service est contacté, la simulation est ignorée.
    resultat, session = await _envoyer({"reponses_simulees": simulees}, {"id": "1"}, reponse_http=_reponse(200, {"vrai": 1}))
    assert session.request.call_count == 1 and resultat["data"] == {"vrai": 1} and "simulee" not in resultat
    # Essai ou banc : la réponse enregistrée est servie, rien ne part.
    resultat, session = await _envoyer({"reponses_simulees": simulees}, {"id": "1"}, simuler=True)
    assert session.request.call_count == 0 and resultat["data"] == {"simule": True} and resultat["simulee"] is True
    # Une simulation qui ne correspond pas aux paramètres : le service est contacté.
    _, session = await _envoyer({"reponses_simulees": simulees}, {"id": "2"}, simuler=True)
    assert session.request.call_count == 1


def test_la_selection_d_une_reponse_simulee():
    config = {"reponses_simulees": [{"quand": {"a": "1"}, "statut": 404, "donnees": {"m": "non"}}, {"statut": 200, "donnees": {}}]}
    assert simulation.en_reponse(simulation.choisir(config, {"a": "1"}))["status"] == "error"
    assert simulation.choisir(config, {"a": "2"})["statut"] == 200


def test_les_chemins_de_lecture():
    assert reponse.lire_le_chemin({"a": [{"b": 1}]}, "a.0.b") == 1
    assert reponse.lire_le_chemin({"a": []}, "a.0") is reponse.ABSENT
    assert parametres.verifier_les_valeurs({"parameters": []}, {"x": 1}) is None


# ---- Comportement ------------------------------------------------------------------------------------------------


class FauxMoteur:
    def __init__(self):
        self.dit: list[tuple] = []
        self._fetch_recording_audio = object()

    async def queue_text_message(self, texte, *, append_to_context=False, mute_user=False):
        self.dit.append(("texte", texte, mute_user))
        return True

    async def queue_speech(self, texte=None, *, recording_pk=None, mute_user=False, **_):
        self.dit.append(("parole", texte or recording_pk, mute_user))
        return SimpleNamespace(wait=AsyncMock())


def _appel(resultat=None, retard=0.0, ordre=None):
    async def appel():
        if ordre is not None:
            ordre.append("outil")
        if retard:
            await asyncio.sleep(retard)
        return resultat if resultat is not None else {"status": "success"}

    return appel


def test_mode_de_la_phrase_sans_reglage_comme_avant():
    assert comportement.mode_de_la_phrase({"customMessage": "Un instant"}) == "toujours"
    assert comportement.mode_de_la_phrase({}) == "jamais"
    assert comportement.mode_de_la_phrase({"customMessage": "x", "phrase_avant_mode": "jamais"}) == "jamais"


@pytest.mark.asyncio
async def test_phrase_avant_toujours_jamais_et_auto():
    moteur = FauxMoteur()
    await executer_avec_comportement(moteur, {"customMessage": "Je regarde", "phrase_avant_mode": "toujours"}, "t", _appel())
    assert moteur.dit == [("parole", "Je regarde", True)]  # muet par défaut : l'appelant ne coupe pas

    moteur = FauxMoteur()
    await executer_avec_comportement(moteur, {"customMessage": "Je regarde", "phrase_avant_mode": "jamais"}, "t", _appel())
    assert moteur.dit == []

    # Auto : un outil rapide ne dit rien, un outil lent dit la phrase.
    moteur = FauxMoteur()
    await executer_avec_comportement(moteur, {"customMessage": "Je regarde", "phrase_avant_mode": "auto"}, "t", _appel())
    assert moteur.dit == []
    moteur = FauxMoteur()
    with patch.object(comportement, "SEUIL_AUTO_S", 0.01):
        await executer_avec_comportement(moteur, {"customMessage": "Je regarde", "phrase_avant_mode": "auto"}, "t", _appel(retard=0.1))
    assert moteur.dit == [("parole", "Je regarde", True)]


@pytest.mark.asyncio
async def test_l_appelant_peut_couper_quand_l_interruption_est_permise():
    moteur = FauxMoteur()
    await executer_avec_comportement(
        moteur, {"customMessage": "Je regarde", "interruption_appelant": True}, "t", _appel()
    )
    assert moteur.dit == [("parole", "Je regarde", False)]


@pytest.mark.asyncio
async def test_une_phrase_enregistree_est_jouee():
    moteur = FauxMoteur()
    await executer_avec_comportement(
        moteur, {"customMessageType": "audio", "customMessageRecordingId": "12"}, "t", _appel()
    )
    assert moteur.dit == [("parole", 12, True)]


@pytest.mark.asyncio
async def test_apres_la_phrase_l_outil_attend_la_fin_de_la_phrase():
    ordre: list[str] = []
    moteur = FauxMoteur()
    attente = AsyncMock(side_effect=lambda: ordre.append("phrase finie"))

    async def parole(texte=None, **_):
        return SimpleNamespace(wait=attente)

    moteur.queue_speech = parole
    await executer_avec_comportement(
        moteur, {"customMessage": "Un instant", "mode_execution": "apres_la_phrase"}, "t", _appel(ordre=ordre)
    )
    assert ordre == ["phrase finie", "outil"]


@pytest.mark.asyncio
async def test_arriere_plan_repond_tout_de_suite_et_le_resultat_arrive_dans_la_fiche():
    fiche: dict = {}
    sortie = await executer_avec_comportement(
        FauxMoteur(), {"mode_execution": "arriere_plan"}, "chercher", _appel({"status": "success", "data": 1}, retard=0.05), fiche=fiche
    )
    assert sortie["status"] == "en_cours" and fiche == {}
    await asyncio.sleep(0.15)
    assert fiche == {"resultat_chercher": {"status": "success", "data": 1}}


def test_arriere_plan_refuse_pour_un_outil_qui_ecrit():
    with pytest.raises(ValidationError):
        HttpApiConfig(method="POST", url="https://a.example.test", mode_execution="arriere_plan")
    HttpApiConfig(method="GET", url="https://a.example.test", mode_execution="arriere_plan")
    HttpApiConfig(method="POST", url="https://a.example.test", mode_execution="arriere_plan", sans_risque_de_doublon=True)


@pytest.mark.asyncio
async def test_phrase_d_attente_et_son_au_dela_du_seuil_pas_en_dessous():
    config = {"phrase_attente": "Toujours là", "seuil_patience_ms": 30, "son_pendant_enregistrement_id": 7}
    moteur = FauxMoteur()
    await executer_avec_comportement(moteur, config, "t", _appel(retard=0.15))
    assert ("texte", "Toujours là", True) in moteur.dit and ("parole", 7, True) in moteur.dit
    moteur = FauxMoteur()
    await executer_avec_comportement(moteur, {**config, "seuil_patience_ms": 2000}, "t", _appel())
    assert moteur.dit == []  # un outil rapide ne dit rien


@pytest.mark.asyncio
async def test_phrase_de_repli_dite_a_l_echec_et_signalee_au_modele():
    moteur = FauxMoteur()
    sortie = await executer_avec_comportement(
        moteur, {"phrase_repli": "Je note votre demande"}, "t", _appel({"status": "error", "error": "panne"})
    )
    assert moteur.dit == [("texte", "Je note votre demande", True)]
    assert sortie["said_to_caller"] == "Je note votre demande" and sortie["status"] == "error"
    # Un succès ne dit pas le repli.
    moteur = FauxMoteur()
    await executer_avec_comportement(moteur, {"phrase_repli": "Je note"}, "t", _appel())
    assert moteur.dit == []
