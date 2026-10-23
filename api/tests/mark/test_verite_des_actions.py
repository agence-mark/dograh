"""[.mark] Lot 5 de correctifs-apres-banc-commun : la vérité des actions (K7, K11, V4).

| Test | La garantie |
|---|---|
| dates | « 3 novembre », « le 3 et le 7 novembre », ISO, « 3/11 » se lisent ; un numéro de téléphone n'est pas une date |
| K11 | la demande confiée au fond porte les valeurs de la fiche (par la vraie route : moteur, confier, fond) ; sans fiche, demande intacte |
| K7 garde | une réservation avec une date que la recherche n'a pas donnée n'est pas exécutée (« incomplet ») ; une date donnée passe ; sans date trouvée, ou case éteinte, ou autre outil : comme avant |
| K7 règle de l'humain | la recherche d'un autre jour passe toujours |
| V4 | la même réservation déjà confirmée rend le résultat connu, l'outil n'est pas rappelé |
| V4 règle de l'humain | autre date, donnée corrigée, annulation puis même créneau, échec d'avant : l'outil est toujours rappelé |
| K7 réplique | une date non trouvée, ou « c'est réservé » sans action réussie, est retenue puis relancée UNE fois (par le vrai mixin) ; l'appel d'outil, la date connue, la case éteinte passent tels quels |
| branchement | l'étape qui offre un outil d'action porte le contrôle, case allumée par défaut ; case éteinte ou étape sans outil : rien |
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from openai.types.chat import ChatCompletion
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk, Choice, ChoiceDelta

from api.schemas.fiche_agent import ChampFiche
from api.services.pipecat.reponse_avalee import ATTRIBUT_VERITE, RepriseSansFluxMixin
from api.services.travail.demande import ENTETE_DES_VALEURS, joindre_la_fiche
from api.services.travail.reglages import NOM_OUTIL
from api.services.workflow.enveloppe_des_actions import envelopper_l_action
from api.services.workflow.fiche_au_fil_de_leau import ReglagesFiche
from api.services.workflow.verite_des_actions import (
    CONSIGNE_ACTION,
    CONSIGNE_DATE,
    RAISON_ACTION,
    RAISON_DATE,
    VerificateurDeReplique,
    brancher_la_verite_des_actions,
    dates_dans,
)

RESERVER = "reserver"
CHERCHER = "chercher"
ANNULER = "annuler"
TROUVEES = {"creneaux": ["2026-11-03T10:00:00+01:00", "2026-11-05T14:00:00+01:00"]}


# --------------------------------------------------------------------------- #
# Les dates
# --------------------------------------------------------------------------- #


def test_les_dates_se_lisent_sous_toutes_les_formes():
    assert dates_dans("mardi 3 novembre") == {(11, 3)}
    assert dates_dans("le 1er décembre") == {(12, 1)}
    assert dates_dans("entre le 3 et le 7 novembre") == {(11, 3), (11, 7)}
    assert dates_dans("du 3 au 7 novembre") == {(11, 3), (11, 7)}
    assert dates_dans("le 3, le 5 ou le 7 novembre") == {(11, 3), (11, 5), (11, 7)}
    assert dates_dans("2026-11-03T10:00:00+01:00") == {(11, 3)}
    assert dates_dans({"debut": "2026-11-05", "x": ["2026-11-03"]}) == {(11, 5), (11, 3)}
    assert dates_dans("le 3/11") == {(11, 3)}


def test_ce_qui_n_est_pas_une_date_n_en_est_pas_une():
    assert dates_dans("jeudi prochain") == set()
    assert dates_dans("mon numéro est le 07/50/857872") == set()
    assert dates_dans("07 55 12 34 56") == set()
    assert dates_dans("2026-13-45") == set()
    assert dates_dans("j'ai mai soif, pas le 45 mai") == set()


# --------------------------------------------------------------------------- #
# K11 : la demande porte les valeurs de la fiche
# --------------------------------------------------------------------------- #


def _reglages_fiche():
    return ReglagesFiche(
        champs=(
            ChampFiche(nom="nom", origine="dicte"),
            ChampFiche(nom="adresse", origine="dicte"),
            ChampFiche(nom="commune", origine="dicte"),
            ChampFiche(
                nom="rendez_vous",
                origine="deduit",
                valeurs=["confirme", "a_rappeler", "annule"],
                rempli_par_outil=RESERVER,
            ),
        )
    )


def test_k11_les_valeurs_de_la_fiche_sont_jointes_sans_les_champs_vides_ni_refuses():
    demande = joindre_la_fiche(
        "Cherche deux dates avec l'adresse, la commune.",
        _reglages_fiche(),
        {"nom": "Durand", "adresse": "8 rue Pasteur", "commune": "refusé", "rendez_vous": ""},
    )
    assert demande.startswith("Cherche deux dates avec l'adresse, la commune.\n\n" + ENTETE_DES_VALEURS)
    assert "- nom : Durand" in demande and "- adresse : 8 rue Pasteur" in demande
    assert "commune :" not in demande and "rendez_vous" not in demande


def test_k11_sans_valeur_ou_sans_fiche_la_demande_est_intacte():
    assert joindre_la_fiche("Cherche.", _reglages_fiche(), {}) == "Cherche."
    assert joindre_la_fiche("Cherche.", None, {"nom": "Durand"}) == "Cherche."
    assert joindre_la_fiche("  ", _reglages_fiche(), {"nom": "Durand"}) == "  "
    assert joindre_la_fiche(None, _reglages_fiche(), {"nom": "Durand"}) is None


@pytest.fixture
async def appel():
    from api.tests.mark.test_travail_de_fond import Appel

    a = Appel()
    try:
        yield a
    finally:
        await a.arreter()


async def test_k11_par_la_vraie_route_le_fond_recoit_la_demande_avec_les_valeurs(appel):
    """Run 1519 : le modèle envoie « avec l'adresse, la commune… » sans valeur. Moteur, outil « confier », trace."""
    from api.tests.mark.test_travail_de_fond import RESULTAT, _appel_d_outil, _texte

    await appel.monter(
        source_etapes=[
            _appel_d_outil(NOM_OUTIL, {"demande": "Cherche deux dates avec l'adresse, la commune."}, "call_confier"),
            _texte("Je regarde."),
            _texte("Voilà."),
        ],
        fond_etapes=[_texte(RESULTAT)],
        outils_du_fond=False,
    )
    appel.engine._fiche = _reglages_fiche()
    appel.engine._gathered_context.update(nom="Durand", adresse="8 rue Pasteur", commune="Beauvais")
    await appel.ouvrir()
    await appel.attendre(lambda: appel.travaux() and appel.travaux()[0]["remis"])
    demande = appel.travaux()[0]["demande"]
    assert demande.startswith("Cherche deux dates avec l'adresse, la commune.")
    for ligne in ("- nom : Durand", "- adresse : 8 rue Pasteur", "- commune : Beauvais"):
        assert ligne in demande


async def test_k11_sans_fiche_la_demande_reste_celle_du_modele(appel):
    from api.tests.mark.test_travail_de_fond import DEMANDE, RESULTAT, _appel_d_outil, _texte

    await appel.monter(
        source_etapes=[_appel_d_outil(NOM_OUTIL, {"demande": DEMANDE}, "call_confier"), _texte("Je regarde."), _texte("Voilà.")],
        fond_etapes=[_texte(RESULTAT)],
        outils_du_fond=False,
    )
    await appel.ouvrir()
    await appel.attendre(lambda: appel.travaux() and appel.travaux()[0]["remis"])
    assert appel.travaux()[0]["demande"] == DEMANDE


# --------------------------------------------------------------------------- #
# K7 garde de réservation et V4 : l'enveloppe des actions
# --------------------------------------------------------------------------- #


class Banc:
    """Un moteur, un agent (étape), et trois actions enveloppées : chercher, réserver, annuler."""

    def __init__(self, case=None):
        self.fiche = {}
        self.moteur = SimpleNamespace(_fiche=_reglages_fiche(), _gathered_context=self.fiche)
        self.agent = SimpleNamespace(current_node=SimpleNamespace(verite_des_actions=case, champs_etape=()))
        self.executions = {CHERCHER: [], RESERVER: [], ANNULER: []}
        self.reponses = {
            CHERCHER: TROUVEES,
            RESERVER: {"statut": "confirme", "rendez_vous": "confirme"},
            ANNULER: {"statut": "annule", "rendez_vous": "annule"},
        }
        self.enveloppes = {nom: self._envelopper(nom) for nom in self.executions}

    def _envelopper(self, nom):
        async def action(params):
            self.executions[nom].append(dict(params.arguments))
            reponse = self.reponses[nom]
            await params.result_callback(reponse() if callable(reponse) else reponse)

        return envelopper_l_action(self.moteur, nom, action, self.agent)

    async def appeler(self, outil, /, **arguments):
        rendus = []

        async def rendre(resultat, **_):
            rendus.append(resultat)

        await self.enveloppes[outil](SimpleNamespace(result_callback=rendre, arguments=arguments))
        assert len(rendus) == 1
        return rendus[0]


async def test_k7_une_date_que_la_recherche_n_a_pas_donnee_n_est_pas_reservee():
    banc = Banc()
    await banc.appeler(CHERCHER, jour="semaine du 3 novembre")
    refus = await banc.appeler(RESERVER, debut="2026-11-07T10:00:00+01:00", nom="Durand")
    assert refus["statut"] == "incomplet" and "7 novembre" in refus["manque"][0]
    assert "cherche d'abord" in refus["consigne"]
    assert banc.executions[RESERVER] == []
    assert "rendez_vous" not in banc.fiche


async def test_k7_une_date_donnee_par_la_recherche_est_reservee():
    banc = Banc()
    await banc.appeler(CHERCHER, jour="semaine du 3 novembre")
    resultat = await banc.appeler(RESERVER, debut="2026-11-05T14:00:00+01:00", nom="Durand")
    assert resultat["statut"] == "confirme" and banc.executions[RESERVER]
    assert banc.fiche["rendez_vous"] == "confirme"


async def test_k7_sans_aucune_date_trouvee_ou_sans_date_dans_la_demande_comme_avant():
    banc = Banc()
    await banc.appeler(RESERVER, debut="2026-11-07T10:00:00+01:00", nom="Durand")
    assert len(banc.executions[RESERVER]) == 1  # aucune recherche dans l'appel : zero perte
    banc = Banc()
    await banc.appeler(CHERCHER, jour="x")
    await banc.appeler(RESERVER, nom="Durand")  # aucune date en argument
    assert len(banc.executions[RESERVER]) == 1


async def test_k7_la_regle_de_l_humain_la_recherche_d_un_autre_jour_passe_toujours():
    banc = Banc()
    await banc.appeler(CHERCHER, jour="2026-11-03")
    banc.reponses[CHERCHER] = {"creneaux": ["2026-11-12T09:00:00+01:00"]}
    await banc.appeler(CHERCHER, jour="2026-11-12")  # l'appelant change de jour
    assert len(banc.executions[CHERCHER]) == 2
    resultat = await banc.appeler(RESERVER, debut="2026-11-12T09:00:00+01:00")
    assert resultat["statut"] == "confirme"


async def test_k7_case_eteinte_la_garde_et_le_v4_se_taisent():
    banc = Banc(case=False)
    await banc.appeler(CHERCHER, jour="x")
    await banc.appeler(RESERVER, debut="2026-11-07T10:00:00+01:00")
    await banc.appeler(RESERVER, debut="2026-11-07T10:00:00+01:00")
    assert len(banc.executions[RESERVER]) == 2


async def test_k7_l_agent_du_fond_suit_la_case_de_l_etape_qui_a_confie():
    """Le fond n'a pas d'étape : sa case est celle de l'agent qui lui a confié le travail."""
    banc = Banc()
    fond = SimpleNamespace(current_node=None, agent_qui_confie=banc.agent)
    nom = RESERVER
    executions = []

    async def action(params):
        executions.append(1)
        await params.result_callback({"statut": "confirme"})

    enveloppe = envelopper_l_action(banc.moteur, nom, action, fond)
    rendus = []

    async def rendre(resultat, **_):
        rendus.append(resultat)

    await banc.appeler(CHERCHER, jour="x")
    await enveloppe(SimpleNamespace(result_callback=rendre, arguments={"debut": "2026-11-07"}))
    assert executions == [] and rendus[0]["statut"] == "incomplet"
    banc.agent.current_node.verite_des_actions = False
    await enveloppe(SimpleNamespace(result_callback=rendre, arguments={"debut": "2026-11-07"}))
    assert executions == [1]


async def test_k7_une_action_qui_ne_remplit_aucun_champ_n_est_jamais_gardee():
    banc = Banc()
    banc.moteur._fiche = ReglagesFiche(champs=(ChampFiche(nom="nom", origine="dicte"),))
    await banc.appeler(CHERCHER, jour="x")
    await banc.appeler(RESERVER, debut="2026-11-07")
    assert len(banc.executions[RESERVER]) == 1


# --- V4 ---------------------------------------------------------------------------------------------------------


async def test_v4_la_meme_reservation_confirmee_rend_le_resultat_connu_sans_rappeler_l_outil():
    banc = Banc()
    await banc.appeler(CHERCHER, jour="x")
    premier = await banc.appeler(RESERVER, debut="2026-11-05T14:00:00+01:00", nom="Durand")
    deuxieme = await banc.appeler(RESERVER, debut="2026-11-05T14:00:00+01:00", nom="durand ")
    troisieme = await banc.appeler(RESERVER, nom="Durand", debut="2026-11-05T14:00:00+01:00")
    assert len(banc.executions[RESERVER]) == 1
    assert premier == {"statut": "confirme", "rendez_vous": "confirme"}
    assert deuxieme == troisieme == {**premier, "deja_confirme": True}


async def test_v4_regle_de_l_humain_une_autre_date_passe_toujours():
    banc = Banc()
    await banc.appeler(CHERCHER, jour="x")
    await banc.appeler(RESERVER, debut="2026-11-05T14:00:00+01:00", nom="Durand")
    await banc.appeler(RESERVER, debut="2026-11-03T10:00:00+01:00", nom="Durand")
    assert len(banc.executions[RESERVER]) == 2


async def test_v4_regle_de_l_humain_une_donnee_corrigee_passe_toujours():
    banc = Banc()
    await banc.appeler(CHERCHER, jour="x")
    await banc.appeler(RESERVER, debut="2026-11-05T14:00:00+01:00", nom="Durand", telephone="0612345678")
    await banc.appeler(RESERVER, debut="2026-11-05T14:00:00+01:00", nom="Durand", telephone="0612345679")
    assert len(banc.executions[RESERVER]) == 2


async def test_v4_regle_de_l_humain_apres_une_annulation_le_meme_creneau_se_reserve_a_nouveau():
    banc = Banc()
    await banc.appeler(CHERCHER, jour="x")
    await banc.appeler(RESERVER, debut="2026-11-05T14:00:00+01:00", nom="Durand")
    banc.reponses[ANNULER] = {"statut": "annule"}  # une annulation qui n'écrit aucun champ de la fiche
    await banc.appeler(ANNULER, nom="Durand")
    await banc.appeler(RESERVER, debut="2026-11-05T14:00:00+01:00", nom="Durand")
    assert len(banc.executions[RESERVER]) == 2


async def test_v4_regle_de_l_humain_un_champ_de_la_fiche_defait_par_ailleurs_rend_la_main():
    banc = Banc()
    await banc.appeler(CHERCHER, jour="x")
    await banc.appeler(RESERVER, debut="2026-11-05T14:00:00+01:00", nom="Durand")
    banc.fiche["rendez_vous"] = "annule"  # le rendez-vous a été annulé (fiche)
    await banc.appeler(RESERVER, debut="2026-11-05T14:00:00+01:00", nom="Durand")
    assert len(banc.executions[RESERVER]) == 2


async def test_v4_une_recherche_entre_deux_n_empeche_pas_le_resultat_connu_un_echec_d_avant_est_retente():
    banc = Banc()
    banc.reponses[RESERVER] = {"statut": "echec"}
    await banc.appeler(RESERVER, debut="2026-11-05T14:00:00+01:00", nom="Durand")
    banc.reponses[RESERVER] = {"statut": "confirme", "rendez_vous": "confirme"}
    await banc.appeler(RESERVER, debut="2026-11-05T14:00:00+01:00", nom="Durand")  # l'échec n'est jamais rendu connu
    assert len(banc.executions[RESERVER]) == 2
    await banc.appeler(CHERCHER, jour="2026-11-05")
    await banc.appeler(RESERVER, debut="2026-11-05T14:00:00+01:00", nom="Durand")
    assert len(banc.executions[RESERVER]) == 2


# --------------------------------------------------------------------------- #
# K7 étendu : la réplique retenue
# --------------------------------------------------------------------------- #

COMMUN = {"id": "c", "created": 0, "model": "m", "object": "chat.completion.chunk"}


def _morceau(contenu=None, fin=None, outil=None):
    from openai.types.chat.chat_completion_chunk import ChoiceDeltaToolCall, ChoiceDeltaToolCallFunction

    appels = None
    if outil:
        appels = [
            ChoiceDeltaToolCall(
                index=0, id="t1", type="function", function=ChoiceDeltaToolCallFunction(name=outil, arguments="{}")
            )
        ]
    return ChatCompletionChunk(
        **COMMUN, choices=[Choice(index=0, delta=ChoiceDelta(content=contenu, tool_calls=appels), finish_reason=fin)]
    )


def _reponse(texte):
    return ChatCompletion.model_validate(
        {
            "id": "r", "created": 0, "model": "m", "object": "chat.completion",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": texte}, "finish_reason": "stop"}],
            "usage": {"completion_tokens": 10, "prompt_tokens": 5, "total_tokens": 15},
        }
    )


class _Base:
    def __init__(self, morceaux, reprise=None):
        self._morceaux = morceaux
        self.requetes = []

        async def create(**requete):
            self.requetes.append(requete)
            return reprise

        self._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        self._settings = SimpleNamespace(system_instruction="consigne")
        self.supports_developer_role = True

    async def get_chat_completions(self, context):
        async def flux():
            for m in self._morceaux:
                yield m

        return flux()

    def get_llm_adapter(self):
        return SimpleNamespace(get_llm_invocation_params=lambda context, **k: {"messages": list(context.messages)})

    def build_chat_completion_params(self, params):
        return {"model": "m", "stream": True, "stream_options": {"include_usage": True}, **params}


class _Service(RepriseSansFluxMixin, _Base):
    pass


class _Contexte:
    def __init__(self, messages):
        self.messages = messages


def _texte(morceaux):
    return "".join(m.choices[0].delta.content or "" for m in morceaux if m.choices)


def _service(morceaux, banc, reprise=None, offre=True):
    service = _Service(morceaux, reprise=reprise)
    brancher_la_verite_des_actions(banc.moteur, banc.agent, banc.agent.current_node, offre)
    # le branchement pose le contrôle sur l'agent : on le recopie sur le service de test
    setattr(service, ATTRIBUT_VERITE, VerificateurDeReplique(banc.moteur, banc.agent) if offre else None)
    return service


async def _jouer(service, messages=None):
    contexte = _Contexte(messages or [{"role": "user", "content": "Bonjour"}])
    return [m async for m in await service.get_chat_completions(contexte)]


async def test_k7_une_date_inventee_est_retenue_et_le_modele_relance_une_fois():
    banc = Banc()
    service = _service([_morceau("Je vous propose le 3 novembre ou le 5 novembre."), _morceau(fin="stop")], banc, _reponse("Je vérifie."))
    morceaux = await _jouer(service)
    assert _texte(morceaux) == "Je vérifie."
    [requete] = service.requetes
    assert requete["stream"] is False
    assert any(CONSIGNE_DATE == m.get("content") for m in requete["messages"])


async def test_k7_une_date_donnee_par_un_outil_ou_dite_par_l_appelant_passe():
    banc = Banc()
    await banc.appeler(CHERCHER, jour="x")
    flux = [_morceau("Je peux vous proposer le 3 novembre."), _morceau(fin="stop")]
    service = _service(flux, banc, _reponse("jamais"))
    assert _texte(await _jouer(service)) == "Je peux vous proposer le 3 novembre."
    assert service.requetes == []
    # une date dite par l'appelant, ou celle d'un résultat de travail
    banc2 = Banc()
    service = _service([_morceau("D'accord, le 12 novembre."), _morceau(fin="stop")], banc2, _reponse("jamais"))
    assert _texte(await _jouer(service, [{"role": "user", "content": "Plutôt le 12 novembre"}])) == "D'accord, le 12 novembre."
    assert service.requetes == []
    service = _service([_morceau("Le 20 novembre, alors."), _morceau(fin="stop")], banc2, _reponse("jamais"))
    resultat = {"role": "user", "content": "[Résultat du travail : créneaux le 20 novembre]"}
    assert _texte(await _jouer(service, [resultat])) == "Le 20 novembre, alors."
    assert service.requetes == []


async def test_k7_une_action_annoncee_faite_sans_resultat_d_outil_est_retenue():
    banc = Banc()
    service = _service([_morceau("C'est parfait, votre rendez-vous est bien pris."), _morceau(fin="stop")], banc, _reponse("Je lance la réservation."))
    assert _texte(await _jouer(service)) == "Je lance la réservation."
    [requete] = service.requetes
    assert any(CONSIGNE_ACTION == m.get("content") for m in requete["messages"])


async def test_k7_une_recherche_ne_fonde_pas_c_est_reserve_mais_une_reservation_reussie_oui():
    banc = Banc()
    await banc.appeler(CHERCHER, jour="x")
    flux = [_morceau("C'est réservé."), _morceau(fin="stop")]
    service = _service(flux, banc, _reponse("Je lance la réservation."))
    assert _texte(await _jouer(service)) == "Je lance la réservation."
    await banc.appeler(RESERVER, debut="2026-11-05T14:00:00+01:00")
    service = _service(flux, banc, _reponse("jamais"))
    assert _texte(await _jouer(service)) == "C'est réservé."
    assert service.requetes == []


async def test_k7_une_question_ou_une_phrase_sans_annonce_passe():
    banc = Banc()
    service = _service([_morceau("Souhaitez-vous que ce soit confirmé ? Je regarde."), _morceau(fin="stop")], banc, _reponse("jamais"))
    assert _texte(await _jouer(service)) == "Souhaitez-vous que ce soit confirmé ? Je regarde."
    assert service.requetes == []


async def test_k7_une_reponse_avec_appel_d_outil_passe_telle_quelle_dans_son_ordre():
    banc = Banc()
    flux = [_morceau("Je vous propose le 9 novembre."), _morceau(outil=CHERCHER), _morceau(fin="tool_calls")]
    service = _service(flux, banc, _reponse("jamais"))
    assert await _jouer(service) == flux
    assert service.requetes == []


async def test_k7_la_relance_n_est_faite_qu_une_fois_elle_est_rendue_quoi_qu_elle_dise():
    banc = Banc()
    service = _service([_morceau("Le 9 novembre."), _morceau(fin="stop")], banc, _reponse("Alors le 10 novembre."))
    assert _texte(await _jouer(service)) == "Alors le 10 novembre."
    assert len(service.requetes) == 1


async def test_k7_une_relance_vide_ou_en_erreur_laisse_passer_la_replique_d_origine():
    banc = Banc()
    flux = [_morceau("Le 9 novembre."), _morceau(fin="stop")]
    service = _service(flux, banc, None)
    assert _texte(await _jouer(service)) == "Le 9 novembre."
    service = _service(flux, banc, _reponse(""))
    assert _texte(await _jouer(service)) == "Le 9 novembre."


async def test_k7_case_eteinte_ou_etape_sans_outil_d_action_le_flux_est_celui_d_avant():
    flux = [_morceau("Le 9 novembre, c'est réservé."), _morceau(fin="stop")]
    banc = Banc(case=False)
    service = _service(flux, banc, _reponse("jamais"))
    assert await _jouer(service) == flux and service.requetes == []
    banc = Banc()
    service = _service(flux, banc, _reponse("jamais"), offre=False)
    assert await _jouer(service) == flux and service.requetes == []
    service = _Service(flux, reprise=_reponse("jamais"))  # aucun contrôle posé
    assert await _jouer(service) == flux and service.requetes == []


def test_k7_le_controle_nomme_la_raison():
    banc = Banc()
    verificateur = VerificateurDeReplique(banc.moteur, banc.agent)
    assert verificateur.controler("Le 9 novembre.", []).raison == RAISON_DATE
    assert verificateur.controler("Votre rendez-vous est confirmé.", []).raison == RAISON_ACTION
    assert verificateur.controler("J'ai bien réservé.", []).raison == RAISON_ACTION
    assert verificateur.controler("J'ai bien noté votre numéro. J'ai pris votre nom.", []) is None


# --------------------------------------------------------------------------- #
# Le branchement sur l'étape (vrai moteur)
# --------------------------------------------------------------------------- #


async def test_le_moteur_branche_le_controle_sur_l_etape_qui_offre_confier(appel):
    from api.tests.mark.test_travail_de_fond import DEMANDE, RESULTAT, _appel_d_outil, _texte as texte_mock

    await appel.monter(
        source_etapes=[_appel_d_outil(NOM_OUTIL, {"demande": DEMANDE}, "call_confier"), texte_mock("Je regarde."), texte_mock("Voilà.")],
        fond_etapes=[texte_mock(RESULTAT)],
        outils_du_fond=False,
    )
    await appel.ouvrir()
    await appel.attendre(lambda: appel.travaux() and appel.travaux()[0]["remis"])
    assert isinstance(getattr(appel.engine.active_agent.llm, ATTRIBUT_VERITE, None), VerificateurDeReplique)


async def test_le_moteur_ne_branche_rien_quand_la_case_est_eteinte(appel):
    from api.tests.mark.test_travail_de_fond import DEMANDE, RESULTAT, _appel_d_outil, _texte as texte_mock

    await appel.monter(
        source_etapes=[_appel_d_outil(NOM_OUTIL, {"demande": DEMANDE}, "call_confier"), texte_mock("Je regarde."), texte_mock("Voilà.")],
        fond_etapes=[texte_mock(RESULTAT)],
        outils_du_fond=False,
    )
    appel.engine.active_agent.workflow.nodes["start"].verite_des_actions = False
    await appel.ouvrir()
    await appel.attendre(lambda: appel.travaux() and appel.travaux()[0]["remis"])
    assert getattr(appel.engine.active_agent.llm, ATTRIBUT_VERITE, None) is None


def test_la_case_d_une_etape_sans_outil_d_action_ne_branche_rien():
    banc = Banc()
    banc.agent.llm = SimpleNamespace()
    assert brancher_la_verite_des_actions(banc.moteur, banc.agent, banc.agent.current_node, False) is False
    assert getattr(banc.agent.llm, ATTRIBUT_VERITE) is None
    assert brancher_la_verite_des_actions(banc.moteur, banc.agent, banc.agent.current_node, True) is True
    banc.agent.current_node.verite_des_actions = False
    assert brancher_la_verite_des_actions(banc.moteur, banc.agent, banc.agent.current_node, True) is False
    assert getattr(banc.agent.llm, ATTRIBUT_VERITE) is None


def test_le_champ_de_l_etape_est_vide_par_defaut_et_pas_dans_le_formulaire():
    from api.services.workflow.dto import AgentNodeData, StartCallNodeData
    from api.services.workflow.dto import _sanitize_node

    assert AgentNodeData(name="a", prompt="p").verite_des_actions is None
    assert StartCallNodeData(name="a", prompt="p").verite_des_actions is None
    nettoye = _sanitize_node({"type": "agentNode", "data": {"name": "a", "prompt": "p", "verite_des_actions": None}})
    assert "verite_des_actions" not in nettoye["data"]
    garde = _sanitize_node({"type": "agentNode", "data": {"name": "a", "prompt": "p", "verite_des_actions": False}})
    assert garde["data"]["verite_des_actions"] is False
    assert asyncio  # le module est utilisé par les tests asynchrones
