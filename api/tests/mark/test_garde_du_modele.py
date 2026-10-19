"""[.mark] Chantier fiabilite-orchestration, lot 4 : la garde du modèle et le repli (F20, F26, C5).

| Test | La garantie |
|---|---|
| délai | le réglage de Models, sinon l'ancien réglage du mode panne, sinon 4 s |
| sans panne | la garde est armée pour tous : « le modèle tarde » puis une nouvelle tentative ; au-delà, des tentatives bornées, jamais d'appel coupé |
| repli | au premier dépassement, la tentative suivante part chez le repli (connexion et modèle), une seule fois, puis tout revient |
| sans repli | la tentative repart chez le même, comme avant |
| fond | le fond est gardé sans phrase ; sa relance rejoue son propre contexte |
| clés | les blocs de repli sont masqués à l'écran comme celui du fond |
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.services.configuration.masking import mask_workflow_configurations
from api.services.panne.delai_modele import DelaiModeleDepasse, DelaiModeleMixin
from api.services.panne.garde_modele import (
    TENTATIVES_SANS_PANNE,
    GardeDuModele,
    Repli,
    delai_de_garde,
    garder_le_fond,
)


def test_le_delai_de_garde_et_ses_replis_de_lecture():
    assert delai_de_garde({}) == 4.0
    assert delai_de_garde({"panne": {"actif": False, "delai_modele_s": 6}}) == 6.0
    assert delai_de_garde({"delai_garde_modele_s": 2.5, "panne": {"delai_modele_s": 6}}) == 2.5
    assert delai_de_garde({"delai_garde_modele_s": "x"}) == 4.0


def _moteur():
    moteur = SimpleNamespace(
        _gathered_context={},
        phrases=SimpleNamespace(dire=AsyncMock()),
        end_call_with_reason=AsyncMock(),
        is_call_disposed=lambda: False,
    )
    return moteur


@pytest.mark.asyncio
async def test_sans_mode_panne_la_garde_relance_sans_jamais_couper_l_appel():
    moteur = _moteur()
    relancer = AsyncMock()
    garde = GardeDuModele(moteur, SimpleNamespace(), relancer, parle=True)
    depasse = DelaiModeleDepasse("premier_morceau", 4.0)
    for _ in range(TENTATIVES_SANS_PANNE + 2):
        await garde._depasse(None, depasse)
    moteur.phrases.dire.assert_awaited_once()
    assert moteur.phrases.dire.await_args.args[0] == "modele_tarde"
    assert relancer.await_count == TENTATIVES_SANS_PANNE
    moteur.end_call_with_reason.assert_not_awaited()


@pytest.mark.asyncio
async def test_le_premier_depassement_envoie_la_tentative_chez_le_repli():
    moteur = _moteur()
    llm = SimpleNamespace(_mark_tentative_au_repli=False)
    repli = Repli(client="client-repli", modele="modele-repli", fournisseur="mistral")
    garde = GardeDuModele(moteur, llm, AsyncMock(), parle=True, repli=repli)
    await garde._depasse(None, DelaiModeleDepasse("premier_morceau", 4.0))
    assert llm._mark_tentative_au_repli is True
    sans = SimpleNamespace(_mark_tentative_au_repli=False)
    await GardeDuModele(moteur, sans, AsyncMock(), parle=True)._depasse(
        None, DelaiModeleDepasse("premier_morceau", 4.0)
    )
    assert sans._mark_tentative_au_repli is False


class _Base:
    def __init__(self):
        self._client = "client-principal"
        self._settings = SimpleNamespace(model="modele-principal")
        self.vus = []

    async def get_chat_completions(self, context):
        self.vus.append((self._client, self._settings.model))
        return "flux"


class _Service(DelaiModeleMixin, _Base):
    pass


@pytest.mark.asyncio
async def test_la_requete_de_repli_emprunte_le_service_une_seule_fois():
    service = _Service()
    service.mark_repli = Repli(client="client-repli", modele="modele-repli", fournisseur="x")
    service._mark_tentative_au_repli = True
    await service.get_chat_completions(None)
    await service.get_chat_completions(None)
    assert service.vus == [
        ("client-repli", "modele-repli"),
        ("client-principal", "modele-principal"),
    ]
    assert (service._client, service._settings.model) == ("client-principal", "modele-principal")


@pytest.mark.asyncio
async def test_le_fond_est_garde_sans_phrase_et_rejoue_son_contexte():
    from pipecat.processors.aggregators.llm_context import LLMContext

    moteur = _moteur()
    moteur._get_organization_id = AsyncMock(return_value=1)
    contexte = LLMContext()
    service = SimpleNamespace(
        queue_frame=AsyncMock(),
        mark_delai_modele_s=None,
        event_handler=lambda nom: (lambda f: f),
    )
    agent = SimpleNamespace(reglages={"delai_garde_modele_s": 3}, user_config=None)
    await garder_le_fond(moteur, agent, service, lambda: contexte)
    assert service.mark_delai_modele_s == 3.0
    garde = service._mark_garde
    await garde._depasse(None, DelaiModeleDepasse("en_cours", 3.0))
    moteur.phrases.dire.assert_not_awaited()
    trame = service.queue_frame.await_args.args[0]
    assert trame.context is contexte


def test_les_cles_des_replis_sont_masquees():
    configurations = {
        "cerveau_de_repli": {"provider": "openai", "model": "m", "api_key": "sk-secret-long-12345"},
        "travail_llm_repli": {"provider": "openai", "model": "m", "api_key": "sk-secret-long-67890"},
    }
    masque = mask_workflow_configurations(configurations)
    for cle in ("cerveau_de_repli", "travail_llm_repli"):
        assert "secret" not in masque[cle]["api_key"]

