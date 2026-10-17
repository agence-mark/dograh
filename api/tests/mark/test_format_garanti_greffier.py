"""[.mark] Le format garanti du greffier (chantier orchestrateur-trois-cerveaux, lot 5 bis).

Plan `Labo-agent-vocal/plans/orchestrateur-trois-cerveaux/2026-10-16-plan-format-garanti-greffier.md`,
D1 à D11 (lots A à D). Un FAUX FOURNISSEUR, sur les deux API (chat completions et Responses), joue
la vraie passe du greffier (``Greffier.une_passe``) : il accepte, refuse en 422, ou rend hors schéma.

| Test | Ce qu'il prouve |
|---|---|
| schéma | généré depuis les champs de la fiche (noms neutres), tous requis, ``additionalProperties`` faux, ``null`` = rien, liste fermée en ``enum`` (pas pour un cumulatif) |
| case décochée | une seule requête, en mode JSON d'avant, aucun schéma ; la trace dit ``json`` (D2) |
| accepte | la requête porte le schéma strict (``response_format`` / ``text.format``), la fiche est écrite, ``garanti`` |
| refuse en 422 | repli immédiat en mode JSON, ``repli``, couple retenu ; la 2e passe du même couple ne retente pas ; un 400 qui ne cite pas le format replie sans retenir le couple |
| hors schéma | clé inconnue ou type inattendu : repli, couple retenu ; jetons des deux requêtes comptés |
| 429, autre erreur | jamais prises pour un refus du format : la passe est sautée / en échec comme avant |
| trace des écartés | inconnus, vides non nuls, refus groupés tracés dans ``ecartes`` ; ``null`` n'est pas un écart ; dans les deux modes |
| réglage | ``greffier_llm.format_garanti`` accepté (booléen seulement) par la route, lu par ``format_garanti_du_bloc``, jamais passé au fournisseur |
"""

import json
from types import SimpleNamespace

import pytest

from api.services.pipecat import greffier as module
from api.services.pipecat.greffier import (
    FORMAT_GARANTI,
    FORMAT_JSON,
    FORMAT_REPLI,
    NE_GARANTISSENT_PAS,
    Greffier,
    champs_a_noter,
    champs_a_noter_et_ecartes,
    configuration_du_greffier,
    consigne_du_greffier,
    format_garanti_du_bloc,
    hors_schema,
    schema_de_la_fiche,
)
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_MODE,
    MODE_GREFFIER,
    Notices,
    ReglagesFiche,
    attendre_les_notes,
)
from api.tests.mark.test_fournisseur_responses import CLE, SCALEWAY, _config
from api.tests.mark.test_horaires_ouverture_reglage import _enregistrer
from api.services.pipecat.service_factory import create_llm_service

FICHE = {
    "fiche_au_fil_de_leau": True,
    CLE_MODE: MODE_GREFFIER,
    "fiche_champs": [
        {"nom": "champ_a", "origine": "dicte", "description": "Un texte dit"},
        {"nom": "champ_b", "origine": "deduit", "description": "Un choix", "valeurs": ["x", "y"]},
        {"nom": "champ_c", "origine": "deduit", "type": "number", "description": "Un nombre"},
        {"nom": "champ_d", "origine": "deduit", "type": "boolean", "description": "Un oui/non"},
        {
            "nom": "champ_e",
            "origine": "deduit",
            "description": "Plusieurs choix",
            "valeurs": ["p", "q"],
            "cumulatif": True,
        },
        {"nom": "champ_f", "origine": "deduit", "description": "Un autre texte"},
    ],
}
PAROLE = "Bonjour, c'est Dupont"


@pytest.fixture(autouse=True)
def _memoire_vide():
    NE_GARANTISSENT_PAS.clear()
    yield
    NE_GARANTISSENT_PAS.clear()


class ErreurHttp(Exception):
    def __init__(self, statut: int, message: str = "response_format json_schema is not supported"):
        super().__init__(f"http {statut}: {message}")
        self.status_code = statut


class FauxFournisseur:
    """Un fournisseur imité dans les deux API. Chaque requête reçoit la réponse suivante : un
    texte, ou une exception levée telle quelle. Les paramètres reçus sont gardés dans ``vus``."""

    def __init__(self, api: str, *reponses):
        self.api = api
        self._reponses = list(reponses)
        self.vus: list[dict] = []

        async def repondre(**params):
            self.vus.append(params)
            rep = self._reponses.pop(0)
            if isinstance(rep, BaseException):
                raise rep
            if api == "responses":
                return SimpleNamespace(
                    output_text=rep,
                    usage=SimpleNamespace(input_tokens=100, output_tokens=10),
                )
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=rep))],
                usage=SimpleNamespace(prompt_tokens=100, completion_tokens=10),
            )

        self.client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=repondre)),
            responses=SimpleNamespace(create=repondre),
            base_url=SCALEWAY,
        )

    @property
    def formats(self) -> list:
        """Le format demandé à chaque requête, dans la forme de l'API."""
        if self.api == "responses":
            return [v["text"]["format"] for v in self.vus]
        return [v["response_format"] for v in self.vus]


def _service(api: str, *reponses):
    service = create_llm_service(_config("responses" if api == "responses" else "chat_completions"))
    faux = FauxFournisseur(api, *reponses)
    service._client = faux.client
    return service, faux


class _Montage:
    def __init__(self, service, format_garanti: bool, config: dict = FICHE):
        self.reglages = ReglagesFiche.depuis(config)
        self.fiche: dict = {}
        self.messages = [{"role": "user", "content": PAROLE}]
        self.notes: set = set()
        self.greffier = Greffier(
            service=service,
            reglages=self.reglages,
            fiche=lambda: self.fiche,
            messages=lambda: self.messages,
            notices=Notices(),
            notes_en_cours=self.notes,
            format_garanti=format_garanti,
        )

    async def passe(self):
        self.greffier.declencher()
        await attendre_les_notes(self.notes, delai=5)

    @property
    def traces(self) -> list[dict]:
        return self.fiche.get(module.TRACE_GREFFIER) or []


def _rendue(**champs) -> str:
    """Une fiche rendue au format garanti : tous les champs présents, null = rien."""
    base = {nom: None for nom in ("champ_a", "champ_b", "champ_c", "champ_d", "champ_e", "champ_f")}
    return json.dumps({**base, **champs})


API = pytest.mark.parametrize("api", ["chat", "responses"])


# --------------------------------------------------------------------------- #
# Le schéma, généré depuis la fiche
# --------------------------------------------------------------------------- #


def test_le_schema_est_genere_depuis_les_champs_de_la_fiche():
    reglages = ReglagesFiche.depuis(FICHE)
    schema = schema_de_la_fiche(reglages)
    assert schema["type"] == "object" and schema["additionalProperties"] is False
    assert schema["required"] == ["champ_a", "champ_b", "champ_c", "champ_d", "champ_e", "champ_f"]
    p = schema["properties"]
    assert p["champ_a"] == {"anyOf": [{"type": "string"}, {"type": "null"}]}
    assert p["champ_b"] == {"anyOf": [{"type": "string", "enum": ["x", "y"]}, {"type": "null"}]}
    assert p["champ_c"]["anyOf"][0] == {"type": "number"}
    assert p["champ_d"]["anyOf"][0] == {"type": "boolean"}
    # Un champ cumulatif s'écrit « p ; q » : jamais une énumération.
    assert p["champ_e"]["anyOf"][0] == {"type": "string"}
    json.dumps(schema)


def test_aucun_mot_de_metier_dans_le_schema_ni_dans_la_reponse_demandee():
    schema = json.dumps(schema_de_la_fiche(ReglagesFiche.depuis(FICHE)))
    assert set(json.loads(schema)["properties"]) == {f"champ_{c}" for c in "abcdef"}
    consigne = consigne_du_greffier(ReglagesFiche.depuis(FICHE), None, format_garanti=True)
    assert "null" in consigne and "respecte le schéma" in consigne
    # Case décochée : la consigne d'avant, inchangée.
    assert consigne_du_greffier(ReglagesFiche.depuis(FICHE), None) == consigne_du_greffier(
        ReglagesFiche.depuis(FICHE), None, format_garanti=False
    )
    assert "est absent" in consigne_du_greffier(ReglagesFiche.depuis(FICHE), None)


def test_hors_schema():
    reglages = ReglagesFiche.depuis(FICHE)
    assert not hors_schema({"champ_a": "x", "champ_b": None, "champ_c": 3, "champ_d": True}, reglages)
    assert not hors_schema({"champ_a": "x"}, reglages)  # un champ absent = rien
    assert hors_schema({"inconnu": "x"}, reglages)
    assert hors_schema({"champ_c": "trois"}, reglages)
    assert hors_schema({"champ_d": "oui"}, reglages)
    assert hors_schema({"champ_b": "z"}, reglages)  # hors de la liste fermée
    assert hors_schema({"champ_c": True}, reglages)  # un booléen n'est pas un nombre


# --------------------------------------------------------------------------- #
# La vraie passe, avec le faux fournisseur, sur les deux API
# --------------------------------------------------------------------------- #


@API
@pytest.mark.asyncio
async def test_case_decochee_une_seule_requete_en_mode_json_et_la_trace_le_dit(api):
    service, faux = _service(api, json.dumps({"champ_a": "Dupont"}))
    montage = _Montage(service, format_garanti=False)
    await montage.passe()
    assert faux.formats == [{"type": "json_object"}]
    assert montage.fiche["champ_a"] == "Dupont"
    assert montage.traces[-1]["format"] == FORMAT_JSON
    assert montage.traces[-1]["ecartes"] == []
    assert not NE_GARANTISSENT_PAS


@API
@pytest.mark.asyncio
async def test_le_fournisseur_accepte_le_schema_part_strict_et_la_fiche_est_ecrite(api):
    service, faux = _service(api, _rendue(champ_a="Dupont"))
    montage = _Montage(service, format_garanti=True)
    await montage.passe()
    [demande] = faux.formats
    schema = schema_de_la_fiche(montage.reglages)
    if api == "responses":
        assert demande == {"type": "json_schema", "name": "fiche", "schema": schema, "strict": True}
    else:
        assert demande == {
            "type": "json_schema",
            "json_schema": {"name": "fiche", "schema": schema, "strict": True},
        }
    assert montage.fiche["champ_a"] == "Dupont"
    trace = montage.traces[-1]
    assert trace["format"] == FORMAT_GARANTI and trace["etat"] == module.ECRIT
    # Les champs « null » sont lus comme rien : ni écartés, ni écrits.
    assert trace["ecartes"] == [] and trace["champs"] == ["champ_a"]
    assert not NE_GARANTISSENT_PAS


@API
@pytest.mark.asyncio
async def test_un_refus_422_replie_en_mode_json_et_le_couple_est_retenu(api):
    service, faux = _service(
        api,
        ErreurHttp(422),
        json.dumps({"champ_a": "Dupont"}),
        json.dumps({"champ_a": "Dupont"}),
    )
    montage = _Montage(service, format_garanti=True)
    await montage.passe()
    # Le schéma d'abord, puis la même requête en mode JSON.
    assert [f["type"] for f in faux.formats] == ["json_schema", "json_object"]
    assert montage.fiche["champ_a"] == "Dupont"
    assert montage.traces[-1]["format"] == FORMAT_REPLI
    assert len(NE_GARANTISSENT_PAS) == 1

    # Deuxième passe du même couple : plus de tentative du schéma.
    montage.messages = [*montage.messages, {"role": "user", "content": "et voilà"}]
    await montage.passe()
    assert [f["type"] for f in faux.formats] == ["json_schema", "json_object", "json_object"]
    assert montage.traces[-1]["format"] == FORMAT_JSON


@API
@pytest.mark.asyncio
async def test_un_400_sans_rapport_avec_le_format_replie_sans_retenir_le_couple(api):
    """Relecture du lot 6 : un 400 qui ne cite pas le format (contexte trop long) replie la passe,
    mais le couple n'est pas retenu : la passe suivante retente le schéma."""
    service, faux = _service(
        api,
        ErreurHttp(400, "maximum context length exceeded"),
        json.dumps({"champ_a": "Dupont"}),
        json.dumps({"champ_a": "Dupont"}),
    )
    montage = _Montage(service, format_garanti=True)
    await montage.passe()
    assert montage.traces[-1]["format"] == FORMAT_REPLI
    assert len(NE_GARANTISSENT_PAS) == 0
    montage.messages = [*montage.messages, {"role": "user", "content": "et voilà"}]
    await montage.passe()
    assert [f["type"] for f in faux.formats] == ["json_schema", "json_object", "json_schema"]


@API
@pytest.mark.asyncio
async def test_une_reponse_hors_schema_replie_et_compte_les_jetons_des_deux_requetes(api):
    service, faux = _service(
        api, json.dumps({"champ_inconnu": "x", "champ_a": "Dupont"}), json.dumps({"champ_a": "Dupont"})
    )
    montage = _Montage(service, format_garanti=True)
    await montage.passe()
    assert [f["type"] for f in faux.formats] == ["json_schema", "json_object"]
    trace = montage.traces[-1]
    assert trace["format"] == FORMAT_REPLI
    assert trace["jetons_entree"] == 200 and trace["jetons_sortie"] == 20
    assert montage.fiche["champ_a"] == "Dupont"
    assert len(NE_GARANTISSENT_PAS) == 1


@API
@pytest.mark.asyncio
async def test_un_type_inattendu_replie_aussi(api):
    service, faux = _service(api, _rendue(champ_c="trois"), json.dumps({"champ_a": "Dupont"}))
    montage = _Montage(service, format_garanti=True)
    await montage.passe()
    assert montage.traces[-1]["format"] == FORMAT_REPLI
    assert len(faux.vus) == 2


@API
@pytest.mark.asyncio
async def test_une_reponse_illisible_replie_aussi(api):
    service, faux = _service(api, "pas du json", json.dumps({"champ_a": "Dupont"}))
    montage = _Montage(service, format_garanti=True)
    await montage.passe()
    assert montage.traces[-1]["format"] == FORMAT_REPLI
    assert montage.fiche["champ_a"] == "Dupont"


@API
@pytest.mark.asyncio
async def test_un_429_n_est_jamais_un_refus_du_format(api):
    service, faux = _service(api, ErreurHttp(429))
    montage = _Montage(service, format_garanti=True)
    await montage.passe()
    assert montage.traces[-1]["etat"] == module.SAUTE
    assert len(faux.vus) == 1 and not NE_GARANTISSENT_PAS


@API
@pytest.mark.asyncio
async def test_une_erreur_d_acces_n_est_pas_non_plus_un_refus_du_format(api):
    service, faux = _service(api, ErreurHttp(401))
    montage = _Montage(service, format_garanti=True)
    await montage.passe()
    assert montage.traces[-1]["etat"] == module.ECHEC
    assert len(faux.vus) == 1 and not NE_GARANTISSENT_PAS


@pytest.mark.asyncio
async def test_sans_client_au_format_openai_le_schema_est_sans_effet():
    """D5 : un service sans client (voie ``run_inference``) reste dans le mode d'avant."""
    from api.tests.mark.test_greffier import _Modele

    modele = _Modele({"champ_a": "Dupont"})
    montage = _Montage(modele, format_garanti=True)
    await montage.passe()
    assert montage.traces[-1]["format"] == FORMAT_JSON
    assert montage.fiche["champ_a"] == "Dupont"


@pytest.mark.asyncio
async def test_deux_fournisseurs_ne_se_retiennent_pas_l_un_l_autre():
    refuse, _ = _service("chat", ErreurHttp(422), json.dumps({}))
    montage = _Montage(refuse, format_garanti=True)
    await montage.passe()
    accepte, faux = _service("responses", _rendue(champ_a="Dupont"))
    suivant = _Montage(accepte, format_garanti=True)
    await suivant.passe()
    assert suivant.traces[-1]["format"] == FORMAT_GARANTI
    assert [f["type"] for f in faux.formats] == ["json_schema"]


# --------------------------------------------------------------------------- #
# La trace des champs écartés (dans les deux modes)
# --------------------------------------------------------------------------- #


def test_les_champs_ecartes_sont_traces_et_null_n_est_pas_un_ecart():
    reglages = ReglagesFiche.depuis(FICHE)
    a_noter, ecartes = champs_a_noter_et_ecartes(
        reglages,
        {},
        {"champ_a": "Dupont", "inconnu": "x", "champ_b": "", "champ_c": "trois", "champ_d": None},
    )
    # Zéro perte (relecture du lot 6) : le type inattendu de ``champ_c`` est transmis comme avant
    # (``champs_a_noter`` décide), seuls l'inconnu et le vide sont écartés d'office.
    rendue_lisible = {"champ_a": "Dupont", "champ_c": "trois"}
    assert a_noter == champs_a_noter(reglages, {}, rendue_lisible)
    assert "champ_a" in a_noter
    assert {"champ_b", "inconnu"} <= set(ecartes)


def test_un_type_inattendu_n_est_jamais_perdu_case_decochee():
    """Relecture du lot 6, défaut bloquant : avant le lot 5 bis, une valeur de liste à la mauvaise
    casse et un nombre rendu pour un champ texte passaient à l'écriture ; ils y passent toujours."""
    reglages = ReglagesFiche.depuis(
        {
            "fiche_au_fil_de_leau": True,
            CLE_MODE: MODE_GREFFIER,
            "fiche_champs": [
                {"nom": "champ_l", "origine": "deduit", "description": "l", "valeurs": ["Aa", "Bb"]},
                {"nom": "champ_n", "origine": "dicte", "description": "n", "chiffres": 5},
            ],
        }
    )
    rendue = {"champ_l": "aa", "champ_n": 60000}
    a_noter, ecartes = champs_a_noter_et_ecartes(reglages, {}, rendue)
    assert a_noter == champs_a_noter(reglages, {}, rendue)
    assert set(a_noter) == {"champ_l", "champ_n"}
    assert ecartes == []
    assert not module.hors_schema({"champ_l": "aa"}, reglages)


def test_un_champ_identique_a_la_fiche_n_est_pas_un_ecart():
    reglages = ReglagesFiche.depuis(FICHE)
    a_noter, ecartes = champs_a_noter_et_ecartes(reglages, {"champ_a": "Dupont"}, {"champ_a": "Dupont"})
    assert a_noter == {} and ecartes == []


def test_les_refus_groupes_sont_des_ecarts():
    reglages = ReglagesFiche.depuis(FICHE)
    a_noter, ecartes = champs_a_noter_et_ecartes(
        reglages, {}, {"champ_a": "refusé", "champ_f": "Refusé", "champ_c": 4}
    )
    assert a_noter == {"champ_c": 4}
    assert ecartes == ["champ_a", "champ_f"]


@pytest.mark.asyncio
async def test_la_passe_trace_les_ecartes_en_mode_json_comme_en_mode_garanti():
    service, _ = _service("chat", json.dumps({"champ_a": "Dupont", "inconnu": "x", "champ_b": ""}))
    montage = _Montage(service, format_garanti=False)
    await montage.passe()
    assert montage.traces[-1]["ecartes"] == ["champ_b", "inconnu"]
    assert montage.traces[-1]["format"] == FORMAT_JSON


# --------------------------------------------------------------------------- #
# Le réglage : greffier_llm.format_garanti
# --------------------------------------------------------------------------- #


def test_la_case_se_lit_dans_le_bloc_du_greffier():
    assert format_garanti_du_bloc({"greffier_llm": {"format_garanti": True}}) is True
    assert format_garanti_du_bloc({"greffier_llm": {"format_garanti": False}}) is False
    assert format_garanti_du_bloc({"greffier_llm": {"provider": "openai"}}) is False
    assert format_garanti_du_bloc({"greffier_llm": {"format_garanti": "oui"}}) is False
    assert format_garanti_du_bloc({}) is False and format_garanti_du_bloc(None) is False


def test_la_case_n_est_jamais_passee_au_fournisseur():
    """Le bloc ne porte que la case : le greffier prend le cerveau de conversation, sans surcharge ;
    avec un modèle, la case n'entre pas dans la configuration du fournisseur."""
    from api.tests.mark.test_greffier import _conversation

    seule = configuration_du_greffier(_conversation(), {"format_garanti": True})
    sans = configuration_du_greffier(_conversation(), None)
    assert seule.llm.model == sans.llm.model == "mistral-small-2603"
    avec_modele = configuration_du_greffier(
        _conversation(), {"model": "mistral-small-2603", "format_garanti": True}
    )
    assert avec_modele.llm.model == "mistral-small-2603"
    assert not hasattr(avec_modele.llm, "format_garanti")


def test_la_route_accepte_la_case_booleenne_et_refuse_le_reste():
    base = {
        "fiche_au_fil_de_leau": True,
        "fiche_mode_de_note": "greffier",
        "fiche_champs": [{"nom": "nom", "origine": "dicte", "description": "Nom"}],
    }
    reponse, ecrit = _enregistrer({**base, "greffier_llm": {"format_garanti": True}})
    assert reponse.status_code == 200, reponse.text
    assert ecrit["greffier_llm"] == {"format_garanti": True}
    reponse, ecrit = _enregistrer({**base, "greffier_llm": {"format_garanti": "oui"}})
    assert reponse.status_code == 422 and ecrit is None
    # Le cerveau de fond n'a pas cette case : elle reste au greffier.
    reponse, ecrit = _enregistrer({**base, "travail_llm": {"format_garanti": True}})
    assert reponse.status_code == 422 and ecrit is None


def test_les_jetons_et_l_adresse_du_couple_ne_contiennent_jamais_la_cle():
    service, _ = _service("chat", "{}")
    NE_GARANTISSENT_PAS.add(module._cle_du_couple(service))
    assert CLE not in json.dumps(sorted(NE_GARANTISSENT_PAS))
