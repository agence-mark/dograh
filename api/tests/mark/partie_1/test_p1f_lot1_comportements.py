"""[.mark] Plan final Partie 1, lot 1 (n° 154) : des tests de comportement à la place de tests qui cherchaient une chaîne dans le code source.

Un test qui lit ``"configurations=configurations_de_l_etape(manager)" in code`` fige l'écriture : le premier lot de ménage le casse sans rien changer au
comportement. Ici, on joue la chose : le réglage lu à l'étape qui porte l'outil arrive à l'action et à la question « sans tiers » ; l'appel au clavier
charge ses listes ; le moteur de l'appel branche le flux vérifié.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from api.services.integrations.connectors import outil as O

REGLAGES_DE_L_ETAPE = {"commande_vente_en_plus": True, "agent_principal_id": 299}
REGLAGES_DE_L_APPEL = {"commande_vente_en_plus": False, "agents_specialises": [300]}


def _manager():
    moteur = SimpleNamespace(configurations_des_modules=REGLAGES_DE_L_APPEL, _workflow_run_id=7, _call_context_vars={"caller_number": "+33612345678"},
                             _gathered_context={}, greffier=None)
    return SimpleNamespace(_engine=moteur, _agent=SimpleNamespace(reglages=REGLAGES_DE_L_ETAPE), get_organization_id=AsyncMock(return_value=1))


def _outil():
    return SimpleNamespace(tool_uuid="u", name="Agenda", definition={"type": "integration", "config": {
        "connecteur": "google_agenda", "action": "find_free_slots", "delai_ms": 2000}})


async def test_l_action_recoit_le_reglage_de_l_etape_qui_porte_l_outil(monkeypatch):
    """L06-16 (S09) : la configuration passée à l'action est celle de l'agent dont l'étape porte l'outil, pas celle du premier agent de l'appel."""
    vu = {}

    async def executer(*args, **kw):
        vu.update(kw)
        return SimpleNamespace(statut="erreur", duree_ms=1, message="x", donnees={})

    monkeypatch.setattr(O, "executer", executer)
    monkeypatch.setattr(O, "resoudre", AsyncMock(return_value=({}, [])))
    recu = []
    params = SimpleNamespace(arguments={}, result_callback=AsyncMock(side_effect=lambda r, **k: recu.append(r)), tool_call_id="t")
    await O.creer_gestionnaire(_manager(), _outil(), "agenda")(params)
    assert vu["configurations"] == REGLAGES_DE_L_ETAPE, vu


async def test_la_question_de_la_prise_est_posee_avec_le_reglage_de_l_etape(monkeypatch):
    """Lot 6 : « cet appel écrit-il chez un client ? » est posée au connecteur avec les réglages de l'étape, au moment du geste."""
    vues = []

    async def sans_tiers(ctx):
        vues.append(ctx.configurations)
        return True

    monkeypatch.setattr(O, "connecteur_interne", lambda tool: SimpleNamespace(sans_tiers=sans_tiers))
    lire = O.sans_tiers_de(_manager(), _outil())
    assert await lire() is True and vues == [REGLAGES_DE_L_ETAPE]


async def test_un_connecteur_qui_ne_sait_pas_sa_prise_laisse_l_outil_simule(monkeypatch):
    monkeypatch.setattr(O, "connecteur_interne", lambda tool: SimpleNamespace(sans_tiers=None))
    assert O.sans_tiers_de(_manager(), _outil()) is None


async def test_le_tour_au_clavier_charge_l_appel_avant_d_enregistrer_le_contexte(monkeypatch):
    """Appel 4 du chantier : au clavier, la fiche partait sans ses listes fermées. Le tour, joué jusqu'au moteur, charge l'appel de l'organisation."""
    from api.schemas.organization_preferences import OrganizationPreferences
    from api.services.restauration.appel_et_memoire import memoire_de_l_appel as MEM
    from api.tests.mark.test_adresse_etablissement import ORGANISATION, _jouer_au_clavier

    charger = AsyncMock()
    monkeypatch.setattr(MEM, "charger_au_clavier", charger)
    await _jouer_au_clavier({}, {"direction": "inbound"}, OrganizationPreferences())
    charger.assert_awaited_once()
    assert charger.await_args.args[:2] == (ORGANISATION, 7)


# --------------------------------------------------------------------------- le cerveau et son flux (par le vrai mixin, sur un faux fournisseur de Pipecat)

async def _flux_du_cerveau(reponse: str, verificateur=None) -> str:
    from pipecat.processors.aggregators.llm_context import LLMContext
    from pipecat.tests import MockLLMService

    from api.services.pipecat.reponse_avalee import ATTRIBUT_VERITE, RepriseSansFluxMixin

    class Cerveau(RepriseSansFluxMixin, MockLLMService):
        pass

    cerveau = Cerveau(mock_steps=[MockLLMService.create_text_chunks(reponse, chunk_size=4)], chunk_delay=0)
    if verificateur is not None:
        setattr(cerveau, ATTRIBUT_VERITE, verificateur)
    contexte = LLMContext(messages=[{"role": "user", "content": "bonjour"}])
    return "".join(m.choices[0].delta.content or "" for m in [m async for m in await cerveau.get_chat_completions(contexte)] if m.choices)


async def test_le_flux_du_cerveau_ne_laisse_passer_aucune_balise_de_reflexion():
    dit = await _flux_du_cerveau("C'est l'IA.\n\n<thought\n>\n\nC'est noté.")
    assert "<" not in dit and dit.split() == ["C'est", "l'IA.", "C'est", "noté."], dit


# --------------------------------------------------------------------------- la forme de la requête, branchée par le moteur

async def test_l_agent_porte_la_preparation_de_la_forme_de_son_moteur_et_la_requete_y_passe(monkeypatch):
    """Lot 6 : une requête lancée directement au cerveau (ouverture d'étape, relance) reçoit la même forme que celle qui traverse les processeurs."""
    from api.services.pipecat import avant_la_requete as AV
    from api.services.workflow import passage_sur_la_fiche as passage

    appels = []

    async def preparer(moteur, llm, trame):
        appels.append((moteur, llm, trame))
        return "trame préparée"

    monkeypatch.setattr(AV, "preparer_la_forme", preparer)
    monkeypatch.setattr(passage, "agent_reclame_le_code", lambda agent: True)
    moteur, llm = object(), object()
    agent = SimpleNamespace(llm=llm, visit_id="a")
    avant, montante = AV.autour_du_cerveau(moteur, agent)
    assert avant is not None and montante is not None
    assert await agent.preparer_la_forme("trame") == "trame préparée" and appels == [(moteur, llm, "trame")]

    # la requête qui traverse les processeurs se termine par la même préparation
    monkeypatch.setattr(passage, "_derniere_parole_de_la_personne", lambda contexte: None)
    monkeypatch.setattr(passage, "avant_la_requete", AsyncMock(return_value=True))
    trame = SimpleNamespace(speculation=False, context=object())
    assert await AV.preparer_la_requete(moteur, llm, trame) == "trame préparée" and appels[-1] == (moteur, llm, trame)
