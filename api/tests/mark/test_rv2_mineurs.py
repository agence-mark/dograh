"""[.mark] Partie 3, seconde revue (RV2), points mineurs M-1, M-2, M-3 et M-6 (le I-1 est dans ``test_rv_portail_ecrire.py``).

| Test | Ce qu'il prouve |
|---|---|
| M-1 | l'accord de dépense n'est pas consommé quand le mode ou une autorisation existante couvre déjà l'action |
| M-2 | l'accord de dépense (et l'autorisation « une fois ») est rendu quand l'action est refusée après ``decider`` : sauvegarde, journal |
| M-3 | pour une clé, le journal de l'accès porte la permission réellement requise (``portail.ecrire``), pas celle de la session |
| M-6 | accepter / refuser des changements, l'interrupteur et l'arrêt des sous-agents, écrire dans le chat : refusés (403) à un autre compte ; un fil sans auteur reste ouvert |
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from api.services.builder import journal, modes, sauvegarde
from api.services.builder.actions import registre
from api.services.builder.actions.registre import Action, ErreurAction
from api.services.equipe_mark.acces import appliquer_acces
from api.tests.mark.builder_commun import monde  # noqa: F401
from api.tests.mark.equipe_commun import client_http, creer_compte, entetes, sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.test_builder_c2 import B, decor, fil_de
from api.tests.mark.test_builder_familles_et_modes import _Params, _chat


def _poser_une_depense(monkeypatch, lancees: list) -> None:
    async def depense(contexte, parametres):
        lancees.append(1)
        return {"ok": True}

    monkeypatch.setitem(
        registre.REGISTRE,
        "attaques_lancer_essai",
        Action(nom="attaques_lancer_essai", description="", parametres=_Params, fonction=depense, ecriture=True, famille="depense"),
    )


def _avec_un_accord(mode: str | None):
    contexte = _chat(mode)
    contexte.conversation["depenses"] = {"d1": {"motif": "x", "montant_estime": 1, "statut": "accordee", "utilisee": False}}
    return contexte


# --- M-1 : l'accord n'est pris que si rien d'autre ne couvre l'action ---------------------------------------------------------------


async def test_m1_le_mode_tout_permettre_ne_consomme_pas_l_accord_de_depense(monde, monkeypatch):  # noqa: F811
    _poser_une_depense(monkeypatch, [])
    contexte = _avec_un_accord("tout")
    assert (await registre.executer("attaques_lancer_essai", {}, contexte)) == {"ok": True}
    assert contexte.conversation["depenses"]["d1"]["utilisee"] is False


async def test_m1_une_autorisation_existante_ne_consomme_pas_l_accord_de_depense(monde, monkeypatch):  # noqa: F811
    _poser_une_depense(monkeypatch, [])
    contexte = _avec_un_accord(None)
    objet = modes.objet_de("attaques_lancer_essai", {}, contexte)
    contexte.conversation["autorisations"] = {"a1": {"nom": "attaques_lancer_essai", "statut": "pour_ce_chat", "objet": objet}}
    assert (await registre.executer("attaques_lancer_essai", {}, contexte)) == {"ok": True}
    assert contexte.conversation["depenses"]["d1"]["utilisee"] is False


async def test_m1_sans_rien_d_autre_l_accord_est_consomme_une_fois(monde, monkeypatch):  # noqa: F811
    _poser_une_depense(monkeypatch, [])
    contexte = _avec_un_accord(None)
    assert (await registre.executer("attaques_lancer_essai", {}, contexte)) == {"ok": True}
    assert contexte.conversation["depenses"]["d1"]["utilisee"] is True


# --- M-2 : l'accord est rendu quand l'action est refusée après decider ---------------------------------------------------------------


async def test_m2_un_refus_de_sauvegarde_rend_l_accord_de_depense(monde, monkeypatch):  # noqa: F811
    lancees: list = []
    _poser_une_depense(monkeypatch, lancees)

    async def refuse(nom, parametres, contexte):
        raise ErreurAction("sauvegarde_impossible", "no backup")

    monkeypatch.setattr(sauvegarde, "garde", refuse)
    contexte = _avec_un_accord(None)
    refus = await registre.executer("attaques_lancer_essai", {}, contexte)
    assert refus["ok"] is False and not lancees
    assert contexte.conversation["depenses"]["d1"]["utilisee"] is False


async def test_m2_une_panne_du_journal_rend_l_accord_de_depense_et_l_autorisation_une_fois(monde, monkeypatch):  # noqa: F811
    lancees: list = []
    _poser_une_depense(monkeypatch, lancees)

    async def panne(*args, **kwargs):
        raise journal.ErreurJournal("down")

    monkeypatch.setattr(journal, "ouvrir", panne)
    contexte = _avec_un_accord(None)
    refus = await registre.executer("attaques_lancer_essai", {}, contexte)
    assert refus["code"] == "journal" and not lancees
    assert contexte.conversation["depenses"]["d1"]["utilisee"] is False

    # même geste pour une carte « une fois » : rendue, pas perdue
    contexte2 = _chat(None)
    contexte2.conversation["autorisations"] = {
        "a1": {"nom": "attaques_lancer_essai", "statut": "une_fois", "utilisee": False, "empreinte": modes.empreinte("attaques_lancer_essai", {})}
    }
    refus2 = await registre.executer("attaques_lancer_essai", {}, contexte2)
    assert refus2["code"] == "journal"
    assert contexte2.conversation["autorisations"]["a1"]["utilisee"] is False


# --- M-3 : le journal d'accès d'une clé porte la permission requise -------------------------------------------------------------------


async def test_m3_le_journal_d_une_cle_porte_portail_ecrire_et_celui_d_une_session_agents_modifier():
    async def appeler(par_cle_api: bool):
        connexion = SimpleNamespace(
            headers={}, scope={"route": SimpleNamespace(path_format="/api/v1/organizations/equipe"), "type": "http", "method": "PUT"}
        )
        utilisateur = SimpleNamespace(id=1, selected_organization_id=5)
        acces = None if par_cle_api else SimpleNamespace(permissions=frozenset({"agents.modifier"}), labo_ouvert=True, tous_les_clients=True, organisations=frozenset({5}))
        journaliser = AsyncMock()
        with (
            patch("api.services.equipe_mark.espaces.rafraichir_labo", AsyncMock()),
            patch("api.services.equipe_mark.acces.acces_de", AsyncMock(return_value=acces)),
            patch("api.services.equipe_mark.acces.detacher_de_sa_session", lambda u: None),
            patch("api.services.equipe_mark.acces.journaliser", journaliser),
        ):
            await appliquer_acces(connexion, utilisateur, par_cle_api=par_cle_api)
        return journaliser.await_args.args[1]

    assert await appeler(True) == "portail.ecrire"
    assert await appeler(False) == "agents.modifier"


# --- M-6 : le chat est à son auteur, jusqu'à ses changements, ses sous-agents et ses messages ----------------------------------------


async def test_m6_les_gestes_du_chat_d_un_autre_sont_refuses_et_un_fil_sans_auteur_reste_ouvert(db_session, sans_preparation_des_organisations):  # noqa: F811
    org, auteur, jeton, agent = await decor(db_session, "rv2m6")
    _, autre_jeton = await creer_compte(db_session, "rv2m6-autre@example.test", role="Administrateur", organisations=[org])
    fil = await fil_de(org, auteur, agent)
    gestes = [
        ("POST", f"{B}/fils/{fil.id}/changements/accepter", {"rangs": []}),
        ("POST", f"{B}/fils/{fil.id}/changements/refuser", {"rangs": []}),
        ("PUT", f"{B}/fils/{fil.id}/sous-agents/interrupteur", {"actif": False}),
        ("POST", f"{B}/fils/{fil.id}/sous-agents/arreter", None),
        ("POST", f"{B}/fils/{fil.id}/messages", {"message": "bonjour"}),
        ("POST", f"{B}/fils/{fil.id}/modifier-dernier", {"message": "bonjour"}),
        ("POST", f"{B}/fils/{fil.id}/reprendre", None),
    ]
    async with client_http() as c:
        for methode, chemin, corps in gestes:
            reponse = await c.request(methode, chemin, json=corps, headers=entetes(autre_jeton, org))
            assert reponse.status_code == 403, (chemin, reponse.status_code, reponse.text)
        # l'auteur n'est pas refusé
        moi = await c.put(f"{B}/fils/{fil.id}/sous-agents/interrupteur", json={"actif": False}, headers=entetes(jeton, org))
        assert moi.status_code == 200
        # un fil sans auteur reste ouvert à l'organisation
        sans_auteur = await fil_de(org, SimpleNamespace(id=None), agent)
        ouvert = await c.put(f"{B}/fils/{sans_auteur.id}/sous-agents/interrupteur", json={"actif": False}, headers=entetes(autre_jeton, org))
        assert ouvert.status_code == 200
