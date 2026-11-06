"""[.mark] Builder partie 3, N1 (SA-N1a) : les familles d'actions, les quatre modes du chat et la demande ponctuelle.

| Test | Ce qu'il prouve |
|---|---|
| inventaire | chaque action du registre a sa famille (liste fermée), la table n'a pas de ligne sans action, chaque permission existe |
| famille x mode | pour chacune des neuf familles et chacun des quatre modes : passe, demande (carte), ou refusé (Plan) — côté serveur |
| le rôle borne | une personne sans la permission de la famille ne la fait pas faire au builder, même en « Tout permettre » |
| l'agent ouvert | « Demander » et « Tout permettre sur cet agent » ne passent que sur l'agent ouvert (et son groupe) |
| une fois / pour ce chat | « une fois » vaut pour CET appel une seule fois ; « pour ce chat » pour ce type d'action sur cet objet, et pas dans un autre chat |
| rien sans clic | une demande n'exécute rien ; une suppression montre « Définitif » ; aucun secret sur la carte |
| porte MCP | Claude Code n'a ni publication, ni irréversible, ni appels réels ; ses actions d'aujourd'hui passent |
| dépense | le mode ou la carte vaut l'accord de dépense, pour cette action seulement |

Monde en mémoire (``monde``), actions espions : aucune base, aucun appel réel.
"""

from __future__ import annotations

import dataclasses

import pytest
from pydantic import BaseModel

from api.services.builder import modes
from api.services.builder.actions import registre
from api.services.builder.actions.familles_actions import FAMILLE_DES_ACTIONS, FAMILLES, PERMISSION_DE_LA_FAMILLE, permission_de
from api.services.builder.actions.registre import PORTE_MCP, Action, Contexte
from api.services.equipe_mark.permissions import PERMISSIONS
from api.tests.mark.builder_commun import AGENT, utilisateur

AUTRE_AGENT = 77


class _Params(BaseModel):
    workflow_id: int | None = None
    api_key: str | None = None


def _espion(appels: list):
    async def fonction(contexte, parametres):
        appels.append(parametres.model_dump())
        return {"ok": True}

    return fonction


@pytest.fixture
def essais(monkeypatch):
    """Une action d'essai par famille (``essai_<famille>``), écran et MCP, qui note ses appels."""
    appels: dict[str, list] = {}
    for famille in FAMILLES:
        appels[famille] = []
        nom = f"essai_{famille}"
        monkeypatch.setitem(
            registre.REGISTRE,
            nom,
            Action(nom=nom, description="essai", parametres=_Params, fonction=_espion(appels[famille]), ecriture=famille != "lecture", famille=famille),
        )
    return appels


def _chat(mode: str | None = None, permissions=frozenset(PERMISSIONS)) -> Contexte:
    conversation = {"messages": []} if mode is None else {"messages": [], "mode": mode}
    return Contexte(user=utilisateur(1), workflow_id=AGENT, conversation=conversation, permissions=frozenset(permissions))


# --- l'inventaire ------------------------------------------------------------------------------------------------------------------


def test_chaque_action_du_registre_a_sa_famille_et_la_table_n_a_pas_de_ligne_orpheline():
    sans = [n for n, a in registre.REGISTRE.items() if a.famille not in FAMILLES]
    assert not sans, f"Actions sans famille (ajouter une ligne à familles_actions.py) : {sans}"
    assert set(FAMILLE_DES_ACTIONS) == set(registre.REGISTRE), set(FAMILLE_DES_ACTIONS) ^ set(registre.REGISTRE)
    assert set(PERMISSION_DE_LA_FAMILLE) == set(FAMILLES)
    for nom, action in registre.REGISTRE.items():
        permission = permission_de(nom, action.famille)
        assert permission is None or permission in PERMISSIONS, (nom, permission)


def test_une_action_sans_famille_est_traitee_comme_la_plus_fermee(monkeypatch):
    action = Action(nom="essai_sans_famille", description="", parametres=_Params, fonction=None)
    assert action.famille is None
    # ``enregistrer`` la lit dans la table ; absente de la table, elle reste ``None`` et le test d'inventaire ci-dessus rougit.
    monkeypatch.setattr(registre, "REGISTRE", dict(registre.REGISTRE))
    assert registre.enregistrer(action).famille is None


# --- famille x mode ---------------------------------------------------------------------------------------------------------------

# Ce qui passe sans demander, sur l'agent ouvert (05, tableau des modes) ; « plan » : tout le reste est refusé, sans carte.
ATTENDU = {
    "demander": {"lecture", "brouillon"},
    "agent": {"lecture", "brouillon", "reglages", "publication", "autre_agent"},
    "tout": set(FAMILLES),
    "plan": {"lecture"},
}


@pytest.mark.parametrize("mode", list(ATTENDU))
@pytest.mark.parametrize("famille", list(FAMILLES))
async def test_chaque_famille_dans_chaque_mode_passe_demande_ou_est_refusee(famille, mode, monde, essais):
    contexte = _chat(mode)
    resultat = await registre.executer(f"essai_{famille}", {"workflow_id": AGENT}, contexte)
    if famille in ATTENDU[mode]:
        assert resultat == {"ok": True} and len(essais[famille]) == 1
    elif mode == "plan":
        assert resultat["code"] == "mode_plan" and not essais[famille]
        assert not contexte.conversation.get("autorisations")  # le mode Plan ne pose pas de carte : il rédige un plan
    else:
        assert resultat["code"] == "autorisation_requise" and not essais[famille]  # rien n'est exécuté sans clic
        assert resultat["carte"]["type"] == "autorisation" and resultat["carte"]["famille"] == famille


async def test_un_nouveau_chat_est_en_mode_demander(monde, essais):
    assert modes.mode_de(None) == modes.mode_de({}) == modes.mode_de({"mode": "inconnu"}) == "demander"
    assert (await registre.executer("essai_reglages", {}, _chat()))["code"] == "autorisation_requise"


# --- le rôle borne tout ------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("famille", [f for f in FAMILLES if PERMISSION_DE_LA_FAMILLE[f]])
async def test_le_builder_ne_donne_jamais_plus_de_droits_que_la_personne(famille, monde, essais):
    sans = frozenset(PERMISSIONS) - {PERMISSION_DE_LA_FAMILLE[famille]}
    resultat = await registre.executer(f"essai_{famille}", {}, _chat("tout", sans))
    assert resultat["code"] == "droits" and not essais[famille]


async def test_les_permissions_sont_lues_cote_serveur_d_apres_le_role_de_la_personne(monde, essais):
    monde.permissions_des_comptes = {1: {"builder.lancer"}, 2: None}
    lu = Contexte(user=utilisateur(1), workflow_id=AGENT, conversation={"mode": "tout"})
    assert (await registre.executer("essai_publication", {}, lu))["code"] == "droits"
    assert lu.permissions == frozenset({"builder.lancer"})
    sans_role = Contexte(user=utilisateur(2), workflow_id=AGENT, conversation={"mode": "tout"})
    assert (await registre.executer("essai_brouillon", {}, sans_role))["code"] == "droits"
    assert (await registre.executer("essai_lecture", {}, sans_role)) == {"ok": True}  # lire n'exige rien


async def test_un_vrai_geste_publier_est_borne_par_le_role(monde, monkeypatch):
    vus = []
    monkeypatch.setitem(registre.REGISTRE, "agent_publier", dataclasses.replace(registre.REGISTRE["agent_publier"], fonction=_espion(vus)))
    sans_publier = frozenset(PERMISSIONS) - {"agents.publier"}
    assert (await registre.executer("agent_publier", {}, _chat("tout", sans_publier)))["code"] == "droits"
    assert (await registre.executer("agent_publier", {}, _chat("agent"))) == {"ok": True} and len(vus) == 1


# --- l'agent ouvert -----------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("mode,famille", [("demander", "brouillon"), ("agent", "brouillon"), ("agent", "publication"), ("agent", "autre_agent")])
async def test_un_autre_agent_que_l_agent_ouvert_demande(mode, famille, monde, essais):
    resultat = await registre.executer(f"essai_{famille}", {"workflow_id": AUTRE_AGENT}, _chat(mode))
    assert resultat["code"] == "autorisation_requise" and resultat["carte"]["objet"] == f"agent:{AUTRE_AGENT}"
    assert (await registre.executer(f"essai_{famille}", {"workflow_id": AUTRE_AGENT}, _chat("tout"))) == {"ok": True}


async def test_tout_permettre_sur_cet_agent_couvre_son_groupe(monde, essais, monkeypatch):
    from api.services.groupe import groupe

    async def lire_groupe(workflow_id, organization_id):
        return {"principal": {"id": AGENT}, "specialises": [{"id": AUTRE_AGENT}]}

    monkeypatch.setattr(groupe, "lire_groupe", lire_groupe)
    assert (await registre.executer("essai_publication", {"workflow_id": AUTRE_AGENT}, _chat("agent"))) == {"ok": True}
    # « Demander » ne s'étend pas au groupe : seulement le brouillon de l'agent ouvert.
    assert (await registre.executer("essai_brouillon", {"workflow_id": AUTRE_AGENT}, _chat("demander")))["code"] == "autorisation_requise"


# --- une fois, pour ce chat ---------------------------------------------------------------------------------------------------------


async def test_autoriser_une_fois_vaut_pour_cet_appel_une_seule_fois(monde, essais):
    contexte = _chat()
    demande = await registre.executer("essai_reglages", {"workflow_id": AGENT}, contexte)
    contexte.conversation["autorisations"][demande["demande"]]["statut"] = "une_fois"
    # d'autres arguments : la carte redemande
    assert (await registre.executer("essai_reglages", {"workflow_id": AGENT, "api_key": "[key-hidden]"}, contexte))["code"] == "autorisation_requise"
    assert (await registre.executer("essai_reglages", {"workflow_id": AGENT}, contexte)) == {"ok": True}
    assert (await registre.executer("essai_reglages", {"workflow_id": AGENT}, contexte))["code"] == "autorisation_requise"
    assert len(essais["reglages"]) == 1


async def test_autoriser_pour_ce_chat_vaut_pour_ce_type_d_action_sur_cet_objet_et_ne_survit_pas_au_chat(monde, essais):
    contexte = _chat()
    demande = await registre.executer("essai_reglages", {"workflow_id": AGENT}, contexte)
    contexte.conversation["autorisations"][demande["demande"]]["statut"] = "pour_ce_chat"
    assert (await registre.executer("essai_reglages", {"workflow_id": AGENT, "api_key": "[key-hidden]"}, contexte)) == {"ok": True}
    assert (await registre.executer("essai_reglages", {"workflow_id": AGENT}, contexte)) == {"ok": True}
    # un autre objet, une autre action : redemande
    assert (await registre.executer("essai_reglages", {"workflow_id": AUTRE_AGENT}, contexte))["code"] == "autorisation_requise"
    assert (await registre.executer("essai_depense", {"workflow_id": AGENT}, contexte))["code"] == "autorisation_requise"
    # un autre chat ne voit pas cette autorisation
    assert (await registre.executer("essai_reglages", {"workflow_id": AGENT}, _chat()))["code"] == "autorisation_requise"
    # retirée (ou refusée), elle ne vaut plus
    contexte.conversation["autorisations"][demande["demande"]]["statut"] = "retiree"
    assert (await registre.executer("essai_reglages", {"workflow_id": AGENT}, contexte))["code"] == "autorisation_requise"


async def test_la_carte_dit_definitif_pour_l_irreversible_et_ne_montre_aucun_secret(monde, essais):
    # N1 (sous-lot 6) : un secret en clair est refusé AVANT la carte (garde des secrets) ; une référence masquée passe, sans jamais être montrée.
    refus = await registre.executer("essai_irreversible", {"workflow_id": AGENT, "api_key": "sk-ne-pas-montrer"}, _chat("agent"))
    assert refus["code"] == "secret" and "carte" not in refus and "sk-ne-pas-montrer" not in str(refus)
    carte = (await registre.executer("essai_irreversible", {"workflow_id": AGENT, "api_key": "[key-hidden]"}, _chat("agent")))["carte"]
    assert carte["definitif"] is True and carte["depense"] is False
    assert "sk-ne-pas-montrer" not in str(carte)
    carte = (await registre.executer("essai_depense", {"workflow_id": AGENT}, _chat("agent")))["carte"]
    assert carte["depense"] is True and carte["definitif"] is False


async def test_la_consigne_du_cerveau_dit_le_mode():
    assert "Plan" in modes.consigne({"mode": "plan"}) and "aucune écriture" in modes.consigne({"mode": "plan"})
    assert modes.CODE_DEMANDE in modes.consigne({})


# --- les deux portes ----------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("famille", list(FAMILLES))
async def test_la_porte_claude_code_garde_ses_actions_et_n_a_ni_publication_ni_irreversible_ni_appels_reels(famille, monde, essais):
    contexte = Contexte(user=utilisateur(1), workflow_id=None, porte=PORTE_MCP)
    resultat = await registre.executer(f"essai_{famille}", {}, contexte)
    if famille in modes.HORS_PORTE_MCP:
        assert resultat["code"] == "porte_mcp" and not essais[famille]
    else:
        assert resultat == {"ok": True}


async def test_la_personne_qui_agit_elle_meme_par_une_route_n_est_pas_freinee(monde, essais):
    """Hors chat (``conversation`` absente), c'est une route de l'écran : sa permission y est déjà vérifiée par ``appliquer_acces``."""
    for famille in FAMILLES:
        assert (await registre.executer(f"essai_{famille}", {}, Contexte(user=utilisateur(1), workflow_id=AGENT))) == {"ok": True}


# --- la dépense ---------------------------------------------------------------------------------------------------------------------


async def test_le_mode_ou_la_carte_vaut_l_accord_de_depense_pour_cette_action_seulement(monde, monkeypatch):
    from api.services.builder.actions.rapport_et_tests import consommer_un_accord

    vus = []

    async def depense(contexte, parametres):
        consommer_un_accord(contexte)
        vus.append(contexte.accord_donne)
        return {"ok": True}

    monkeypatch.setitem(
        registre.REGISTRE, "essai_payant", Action(nom="essai_payant", description="", parametres=_Params, fonction=depense, ecriture=True, famille="depense")
    )
    contexte = _chat("tout")
    assert (await registre.executer("essai_payant", {}, contexte)) == {"ok": True}
    assert vus == [False] and contexte.accord_donne is False  # consommé, et jamais gardé pour l'action suivante
    # Sans le mode ni la carte, l'accord manque : la porte pose la carte avant même la fonction.
    assert (await registre.executer("essai_payant", {}, _chat()))["code"] == "autorisation_requise"


async def test_un_accord_de_depense_ne_vaut_qu_une_fois(monde, monkeypatch):
    """Revue : un accord accordé laissait passer toute action « dépense » sans être marqué utilisé (RV, point 1)."""
    lancees = []

    async def depense(contexte, parametres):
        lancees.append(1)
        return {"ok": True}

    monkeypatch.setitem(
        registre.REGISTRE, "attaques_lancer_essai", Action(nom="attaques_lancer_essai", description="", parametres=_Params, fonction=depense, ecriture=True, famille="depense")
    )
    contexte = _chat()
    contexte.conversation["depenses"] = {"d1": {"motif": "x", "montant_estime": 1, "statut": "accordee", "utilisee": False}}
    assert (await registre.executer("attaques_lancer_essai", {}, contexte)) == {"ok": True}
    assert contexte.conversation["depenses"]["d1"]["utilisee"] is True
    seconde = await registre.executer("attaques_lancer_essai", {}, contexte)
    assert seconde["code"] == "autorisation_requise" and len(lancees) == 1
