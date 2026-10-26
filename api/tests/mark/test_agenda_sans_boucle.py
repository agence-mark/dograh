"""[.mark] fiabilite-de-la-conversation, lot B : l'agenda sans boucle (B1 à B4).

Les boucles des runs 1526, 1813 et 1950 sont rejouées avec des données de jeu : dans chacune le fond n'échouait pas, l'agent lui
renvoyait la MÊME demande, dans la même étape. Les tests passent par le vrai ``TravailDeLAgent`` de l'appel monté sur le banc
de l'amont (``Appel``), le vrai déclencheur et la vraie enveloppe des actions.

| Test | La garantie |
|---|---|
| B1, la règle | casse, ponctuation, espaces ne comptent pas ; le bloc de la fiche non plus ; un autre jour dans le texte = une autre demande ; une autre étape aussi |
| B2, run 1813 | la même recherche renvoyée six fois : lancée une fois, les cinq autres rendent le résultat connu, sans appel du fond |
| B2, run 1526 | la même réservation qui répond « Manque » : un seul nouvel essai, la troisième est bloquée avec « déjà essayé » |
| B2, run 1950 | demande identique alors que la fiche change : pas relancée ; autre jour dans le texte : lancée |
| B2, périmé | une écriture ou une annulation réussie depuis rend la demande identique permise (l'appelant change d'avis) |
| B2, automatique | le déclenchement automatique passe par la même règle et ne marque pas la trace d'avant |
| B2, automatique, notice (décision d'Evan, 26/10) | une demande bloquée par B2 en position Automatique est dite au modèle dans la requête du tour (résultat connu, ou déjà essayé sans succès), jamais dans l'historique ; la requête d'après est inchangée |
| B3 | écriture en vigueur : le déclencheur ne s'arme plus, quoi que la fiche note ; après une annulation réussie, il repart |
| B4 | le quatrième appel d'outil de l'agent dans un tour est refusé ; le tour suivant repart ; une annulation passe ; le fond n'est pas compté ; sans compteur de tour, rien n'est compté |
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.services.travail.demande import ENTETE_DES_VALEURS
from api.services.travail.demande_identique import (
    CONSIGNE_DEJA_CONNU,
    CONSIGNE_DEJA_ESSAYE,
    DEJA_CONNU,
    DEJA_ESSAYE,
    cle_de_la_demande,
    demandes_deja_faites,
    demandes_identiques,
)
from api.services.travail.reglages import NOM_OUTIL
from api.services.workflow import enveloppe_des_actions as enveloppe
from api.services.workflow import verite_des_actions as verite
from api.services.workflow.plafond_d_outils import (
    APPELS_D_OUTIL_PAR_TOUR,
    STATUT_PLAFOND,
    compter_un_appel,
)
from api.tests.mark.test_corrections_du_formulaire import (
    ANNULER,
    CHERCHER,
    RESERVER,
    _banc_automatique,
    _moteur,
)
from api.tests.mark.test_travail_de_fond import _texte, appel  # noqa: F401 -- fixture

RECHERCHE = "Cherche deux dates de passage pour un entretien, sur deux jours différents."
DATES = "Résultat : Dates possibles, le matin : mardi 27 octobre ou jeudi 29 octobre."
RESERVATION = "Réserver le passage pour un entretien, le mardi 27 octobre, pour Marc Henry."


def _avec_la_fiche(demande: str, **valeurs: str) -> str:
    """La demande telle que le code la stocke : le texte de l'agent, puis le bloc des valeurs de la fiche."""
    lignes = "\n".join(f"- {nom} : {valeur}" for nom, valeur in valeurs.items())
    return f"{demande}\n\n{ENTETE_DES_VALEURS}\n{lignes}" if lignes else demande


async def _fond_scenarise(appel, resultats):
    """Un appel monté dont le fond rend, demande après demande, les résultats donnés (le dernier se répète).
    Rend (le travail de l'agent, la liste des demandes que le fond a vraiment reçues)."""
    await appel.monter(source_etapes=[_texte("rien")], fond_etapes=[_texte("rien")], outils_du_fond=False)
    travail = appel.engine.active_agent.travail
    travail._remise = AsyncMock(return_value=True)
    recues: list[str] = []

    async def executeur(_travail, demande):
        recues.append(demande)
        resultat = resultats[min(len(recues), len(resultats)) - 1]
        if isinstance(resultat, Exception):
            raise resultat
        return resultat

    travail._executeur = executeur
    return travail, recues


async def _confier(travail, demande):
    retour = await travail.confier(demande)
    await travail.attendre()
    return retour


# --------------------------------------------------------------------------- #
# B1 : la règle « demande identique »
# --------------------------------------------------------------------------- #


def test_b1_casse_ponctuation_et_espaces_ne_comptent_pas():
    assert demandes_identiques(RECHERCHE, "  cherche DEUX dates de passage pour un entretien,\nsur deux jours différents ")
    assert demandes_identiques(RECHERCHE, RECHERCHE.rstrip(".") + " !")


def test_b1_le_bloc_de_la_fiche_n_entre_pas_dans_la_regle():
    # run 1950 : la fiche change (« Oui, j'attends » noté comme jour souhaité) sans que la demande change
    avant = _avec_la_fiche(RECHERCHE, nom="Henry")
    apres = _avec_la_fiche(RECHERCHE, nom="Henry", jour_souhaite="Oui, j'attends")
    assert demandes_identiques(avant, apres)
    assert cle_de_la_demande(apres) == cle_de_la_demande(RECHERCHE)


def test_b1_un_autre_jour_dans_le_texte_est_une_autre_demande():
    assert not demandes_identiques(RECHERCHE, RECHERCHE.rstrip(".") + ", autre jour que mardi 27 octobre.")
    assert not demandes_identiques(RESERVATION, RESERVATION.replace("mardi 27", "jeudi 29"))
    assert not demandes_identiques("", "")  # deux textes vides ne sont jamais identiques


@pytest.mark.asyncio
async def test_b1_la_meme_demande_dans_une_autre_etape_est_une_autre_demande(appel):
    travail, recues = await _fond_scenarise(appel, [DATES])
    from api.services.travail.demande_identique import identifiant_de_l_etape

    travail._etape = lambda: SimpleNamespace(id="etape-1", name="Une")
    await _confier(travail, RECHERCHE)
    une = identifiant_de_l_etape(SimpleNamespace(id="etape-1"), travail.agent)
    deux = identifiant_de_l_etape(SimpleNamespace(id="etape-2"), travail.agent)
    assert len(demandes_deja_faites(appel.engine, RECHERCHE, une)) == 1
    assert demandes_deja_faites(appel.engine, RECHERCHE, deux) == []
    travail._etape = lambda: SimpleNamespace(id="etape-2", name="Deux")
    retour = await _confier(travail, RECHERCHE)
    assert retour == {"statut": "lancé"} and len(recues) == 2


@pytest.mark.asyncio
async def test_b1_la_meme_etape_chez_un_autre_agent_du_groupe_est_une_autre_etape(appel):
    # Revue du 26/10 (R-1) : les agents d'un groupe, copiés du même squelette, ont les mêmes numéros d'étape.
    from api.services.travail.demande_identique import identifiant_de_l_etape

    travail, recues = await _fond_scenarise(appel, [DATES])
    etape = SimpleNamespace(id="2", name="Rendez-vous")
    travail.agent = SimpleNamespace(workflow_id=20, current_node=etape)
    await _confier(travail, RECHERCHE)
    travail.agent = SimpleNamespace(workflow_id=21, current_node=etape)
    retour = await _confier(travail, RECHERCHE)
    assert retour == {"statut": "lancé"} and len(recues) == 2
    assert identifiant_de_l_etape(etape, travail.agent) == "21:2"
    assert len(demandes_deja_faites(appel.engine, RECHERCHE, "20:2")) == 1


# --------------------------------------------------------------------------- #
# B2 : avant de confier
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_b2_run_1813_la_meme_recherche_six_fois_n_est_lancee_qu_une_fois(appel):
    travail, recues = await _fond_scenarise(appel, [DATES])
    retours = []
    for tour in range(6):
        retours.append(await _confier(travail, _avec_la_fiche(RECHERCHE, nom="Lefèvre", tour=str(tour))))
    assert len(recues) == 1
    assert retours[0] == {"statut": "lancé"}
    for retour in retours[1:]:
        assert retour["statut"] == DEJA_CONNU and retour["resultat"] == DATES
        assert retour["consigne"] == CONSIGNE_DEJA_CONNU
    assert [t["statut"] for t in appel.travaux()] == ["fait"]
    assert appel.travaux()[0]["redemandes"] == 5


@pytest.mark.asyncio
async def test_b2_run_1526_une_reservation_qui_manque_est_retentee_une_fois_puis_bloquee(appel):
    travail, recues = await _fond_scenarise(appel, ["Manque : date"])
    retours = [await _confier(travail, _avec_la_fiche(RESERVATION, nom="Henry")) for _ in range(4)]
    assert len(recues) == 2  # le premier essai et UN nouvel essai
    assert retours[0] == {"statut": "lancé"} and retours[1] == {"statut": "lancé"}
    for retour in retours[2:]:
        assert retour["statut"] == DEJA_ESSAYE and retour["consigne"] == CONSIGNE_DEJA_ESSAYE


@pytest.mark.asyncio
async def test_b2_un_echec_d_outil_ou_un_delai_compte_comme_un_echec(appel):
    travail, recues = await _fond_scenarise(appel, [RuntimeError("panne"), TimeoutError("timed out"), DATES])
    await _confier(travail, RECHERCHE)
    await _confier(travail, RECHERCHE)
    retour = await _confier(travail, RECHERCHE)
    assert retour["statut"] == DEJA_ESSAYE and len(recues) == 2
    assert [t["statut"] for t in appel.travaux()] == ["echec", "delai"]


@pytest.mark.asyncio
async def test_b2_run_1950_la_fiche_change_la_demande_non_un_autre_jour_est_nouveau(appel):
    travail, recues = await _fond_scenarise(appel, [DATES])
    autre = RECHERCHE.rstrip(".") + ", autre jour que mardi 27 octobre ou jeudi 29 octobre."
    await _confier(travail, _avec_la_fiche(autre, nom="Henry"))
    retour = await _confier(travail, _avec_la_fiche(autre, nom="Henry", jour_souhaite="Oui, j'attends"))
    assert retour["statut"] == DEJA_CONNU and len(recues) == 1
    plus = autre.rstrip(".") + " ou mardi 3 novembre."
    retour = await _confier(travail, _avec_la_fiche(plus, nom="Henry", jour_souhaite="Oui, j'attends"))
    assert retour == {"statut": "lancé"} and len(recues) == 2


@pytest.mark.asyncio
async def test_b2_une_ecriture_ou_une_annulation_reussie_depuis_perime_le_resultat_connu(appel):
    travail, recues = await _fond_scenarise(appel, [DATES])
    moteur = appel.engine
    moteur._fiche = _moteur()._fiche  # réserver écrit, annuler défait
    await _confier(travail, RECHERCHE)
    assert (await _confier(travail, RECHERCHE))["statut"] == DEJA_CONNU
    verite.noter_l_action(moteur, RESERVER, {}, {"statut": "confirme"}, {"rendez_vous": "confirme"})
    verite.noter_l_action(moteur, ANNULER, {}, {"statut": "annule"}, {"rendez_vous": "annule"})
    # l'appelant a réservé puis annulé : la même recherche repart (les créneaux ont pu changer)
    assert (await _confier(travail, RECHERCHE)) == {"statut": "lancé"}
    assert len(recues) == 2
    # une simple recherche réussie depuis ne périme rien
    verite.noter_l_action(moteur, CHERCHER, {}, {"dates": ["3 novembre"]}, {})
    assert (await _confier(travail, RECHERCHE))["statut"] == DEJA_CONNU


@pytest.mark.asyncio
async def test_b2_une_demande_identique_encore_en_cours_n_est_pas_relancee(appel):
    await appel.monter(source_etapes=[_texte("rien")], fond_etapes=[_texte("rien")], outils_du_fond=False)
    travail = appel.engine.active_agent.travail
    travail._remise = AsyncMock(return_value=True)
    portail = asyncio.Event()
    vues = []

    async def bloque(_travail, demande):
        vues.append(demande)
        await portail.wait()
        return DATES

    travail._executeur = bloque
    await travail.confier(RECHERCHE)
    await appel.attendre(lambda: len(vues) == 1)
    retour = await travail.confier(RECHERCHE)
    assert retour == {"statut": "lancé", "deja_en_cours": True}
    assert travail.occupe and len(vues) == 1
    portail.set()
    await travail.attendre()
    assert [t["statut"] for t in appel.travaux()] == ["fait"]


@pytest.mark.asyncio
async def test_b2_le_declenchement_automatique_passe_par_la_meme_regle(appel):
    from api.services.workflow.declenchement_de_l_action import AUTOMATIQUE, Declencheur

    travail, recues = await _fond_scenarise(appel, [DATES])
    moteur = appel.engine
    moteur._fiche = _moteur()._fiche
    moteur._gathered_context.update({"nom": "Lefèvre", "adresse": "8 rue Pasteur"})
    noeud = SimpleNamespace(
        id="n1", name="Étape", champs_etape=("nom", "adresse"), conditions_de_champs=(),
        declenchement_de_l_action=AUTOMATIQUE, demande_type=RECHERCHE, verite_des_actions=None, is_end=False,
    )
    agent = SimpleNamespace(current_node=noeud, llm=SimpleNamespace(), travail=travail)
    travail.agent = agent
    declencheur = Declencheur(moteur, agent, noeud, AUTOMATIQUE, NOM_OUTIL)
    assert await declencheur.lancer_automatiquement()
    await travail.attendre()
    # le greffier note autre chose : l'empreinte change, le déclencheur s'arme de nouveau (run 1813)
    moteur._gathered_context["jour_souhaite"] = "Oui, j'attends"
    for essai in range(3):
        moteur._gathered_context["adresse"] = f"8 rue Pasteur, Creil {essai}"
        await declencheur.lancer_automatiquement()
        await travail.attendre()
    assert len(recues) == 1
    trace = appel.travaux()
    assert len(trace) == 1 and trace[0]["declenche_par"] == AUTOMATIQUE and trace[0]["redemandes"] == 3


# --------------------------------------------------------------------------- #
# B3 : pas de relance après une écriture réussie
# --------------------------------------------------------------------------- #


async def test_b3_une_ecriture_en_vigueur_le_declencheur_ne_s_arme_plus():
    moteur, declencheur, travail = _banc_automatique()
    assert await declencheur.armer()
    verite.noter_l_action(moteur, RESERVER, {}, {"statut": "confirme"}, {"rendez_vous": "confirme"})
    assert not await declencheur.armer()
    moteur._gathered_context["jour_souhaite"] = "Oui, j'attends"  # le greffier note autre chose
    moteur._gathered_context["adresse"] = "10 rue Pasteur"  # ou l'appelant corrige : le modèle gère, avec ses outils
    assert not await declencheur.lancer_automatiquement()
    assert travail.demandes == []


async def test_b3_une_ecriture_faite_dans_une_autre_etape_ne_bloque_pas_ce_declencheur():
    # Revue du 26/10 (R-4, décision d'Evan) : seule l'étape où l'écriture a été faite ne se relance plus d'elle-même.
    moteur, declencheur, travail = _banc_automatique()
    verite.noter_l_action(moteur, RESERVER, {}, {"statut": "confirme"}, {"rendez_vous": "confirme"}, etape="20:7")
    assert await declencheur.armer(), "une autre étape (ou un autre collègue) : rien ne bloque"
    verite.noter_l_action(moteur, RESERVER, {}, {"statut": "confirme"}, {"rendez_vous": "confirme"}, etape="n1")
    assert not await declencheur.armer(), "l'étape de l'écriture : bloquée"


def test_b3_l_etape_d_une_action_du_fond_est_celle_de_l_agent_qui_a_confie():
    etape = SimpleNamespace(id="7")
    conversation = SimpleNamespace(workflow_id=20, current_node=etape)
    fond = SimpleNamespace(workflow_id=20, current_node=None, agent_qui_confie=conversation)
    assert verite.etape_de_l_action(conversation) == verite.etape_de_l_action(fond) == "20:7"


async def test_b3_apres_une_annulation_reussie_changer_de_date_repart():
    moteur, declencheur, travail = _banc_automatique()
    verite.noter_l_action(moteur, RESERVER, {}, {"statut": "confirme"}, {"rendez_vous": "confirme"})
    assert not await declencheur.armer()
    verite.noter_l_action(moteur, ANNULER, {}, {"statut": "annule"}, {"rendez_vous": "annule"})
    assert verite.ecriture_en_vigueur(moteur) is None
    assert await declencheur.lancer_automatiquement()
    assert len(travail.demandes) == 1


# --------------------------------------------------------------------------- #
# B4 : le plafond d'appels d'outil par tour
# --------------------------------------------------------------------------- #


def _moteur_au_tour(tour):
    moteur = _moteur()
    moteur._gathered_context["tour_appelant"] = tour
    return moteur


def test_b4_le_quatrieme_appel_du_tour_est_refuse_le_tour_suivant_repart():
    moteur, agent = _moteur_au_tour(5), SimpleNamespace(current_node=None)
    assert [compter_un_appel(moteur, agent) for _ in range(APPELS_D_OUTIL_PAR_TOUR)] == [None] * 3
    refus = compter_un_appel(moteur, agent)
    assert refus is not None and refus["statut"] == STATUT_PLAFOND and refus["consigne"]
    assert compter_un_appel(moteur, agent) is not None  # il reste refusé dans ce tour
    moteur._gathered_context["tour_appelant"] = 6
    assert compter_un_appel(moteur, agent) is None


def test_b4_le_fond_n_est_pas_compte_et_sans_compteur_de_tour_rien_n_est_compte():
    moteur = _moteur_au_tour(1)
    agent = SimpleNamespace(current_node=None)
    fond = SimpleNamespace(current_node=None, agent_qui_confie=agent)
    assert all(compter_un_appel(moteur, fond) is None for _ in range(10))
    assert compter_un_appel(moteur, agent) is None  # le fond n'a rien consommé
    sans_tour = _moteur()
    assert all(compter_un_appel(sans_tour, agent) is None for _ in range(10))


async def _appeler(moteur, agent, nom, executions):
    rendus = []

    async def action(params):
        executions.append(nom)
        await params.result_callback({"statut": "ok", "outil": nom})

    async def rendre(resultat, **_):
        rendus.append(resultat)

    noeud_libre = agent
    await enveloppe.envelopper_l_action(moteur, nom, action, noeud_libre)(
        SimpleNamespace(result_callback=rendre, arguments={})
    )
    return rendus[0]


@pytest.mark.asyncio
async def test_b4_par_l_enveloppe_quatre_appels_le_dernier_est_refuse_sans_etre_execute():
    moteur = _moteur_au_tour(3)
    agent = SimpleNamespace(current_node=SimpleNamespace(champs_etape=(), verite_des_actions=False))
    executions: list[str] = []
    rendus = [await _appeler(moteur, agent, f"outil_{i}", executions) for i in range(4)]
    assert [r["statut"] for r in rendus[:3]] == ["ok"] * 3
    assert rendus[3]["statut"] == STATUT_PLAFOND and executions == ["outil_0", "outil_1", "outil_2"]


@pytest.mark.asyncio
async def test_b4_changer_de_date_passe_toujours_l_annulation_ne_compte_pas():
    moteur = _moteur_au_tour(3)
    agent = SimpleNamespace(current_node=SimpleNamespace(champs_etape=(), verite_des_actions=False))
    executions: list[str] = []
    for nom in ("recherche_a", "recherche_b", "recherche_c"):
        await _appeler(moteur, agent, nom, executions)
    # le plafond est atteint : une annulation passe quand même, l'appelant change d'avis
    assert (await _appeler(moteur, agent, ANNULER, executions))["statut"] == "ok"
    assert (await _appeler(moteur, agent, "recherche_d", executions))["statut"] == STATUT_PLAFOND


@pytest.mark.asyncio
async def test_b4_le_travail_de_fond_change_de_date_malgre_le_plafond():
    moteur = _moteur_au_tour(3)
    agent = SimpleNamespace(current_node=SimpleNamespace(champs_etape=(), verite_des_actions=False))
    fond = SimpleNamespace(current_node=None, agent_qui_confie=agent, llm=object())
    executions: list[str] = []
    for nom in (ANNULER, RESERVER, CHERCHER, "autre_recherche"):
        rendu = await _appeler(moteur, fond, nom, executions)
        assert rendu["statut"] != STATUT_PLAFOND
    assert len(executions) == 4
    # et l'agent qui parle garde ses trois appels du tour
    assert (await _appeler(moteur, agent, "un", executions))["statut"] == "ok"


@pytest.mark.asyncio
async def test_b4_confier_compte_dans_le_plafond_de_l_agent(appel):
    travail, recues = await _fond_scenarise(appel, [DATES])
    moteur = appel.engine
    agent = moteur.active_agent
    moteur._gathered_context["tour_appelant"] = 9
    from api.services.travail.agent import brancher_confier_le_travail

    brancher_confier_le_travail(moteur, travail, agent)
    gestionnaire = agent.llm._functions[NOM_OUTIL].handler
    rendus = []

    async def rendre(resultat, **_):
        rendus.append(resultat)

    # deux autres appels d'outil dans le même tour, puis « confier » en troisième, puis un quatrième refusé
    assert compter_un_appel(moteur, agent) is None and compter_un_appel(moteur, agent) is None
    await gestionnaire(SimpleNamespace(arguments={"demande": RECHERCHE}, result_callback=rendre, tool_call_id="1", function_name=NOM_OUTIL))
    await travail.attendre()
    await gestionnaire(SimpleNamespace(arguments={"demande": RESERVATION}, result_callback=rendre, tool_call_id="2", function_name=NOM_OUTIL))
    assert rendus[0]["statut"] == "lancé"
    assert rendus[1]["statut"] == STATUT_PLAFOND
    assert len(recues) == 1


# --------------------------------------------------------------------------- #
# B2 en Automatique : la notice au modèle (décision d'Evan, 26/10)
# --------------------------------------------------------------------------- #


class _CerveauFactice:
    """Un cerveau qui construit sa requête comme Pipecat (``build_chat_completion_params`` dans ``get_chat_completions``)."""

    def __init__(self):
        self.requetes: list[list[dict]] = []

    async def get_chat_completions(self, context):
        params = self.build_chat_completion_params({"messages": list(context.messages)})
        self.requetes.append(params["messages"])
        return None

    def build_chat_completion_params(self, params):
        return dict(params)


async def _automatique_branche(appel, resultats):
    from api.services.pipecat.reponse_avalee import ATTRIBUT_DECLENCHEUR
    from api.services.workflow.declenchement_de_l_action import AUTOMATIQUE, Declencheur, _brancher_les_tours

    travail, recues = await _fond_scenarise(appel, resultats)
    moteur = appel.engine
    moteur._fiche = _moteur()._fiche
    moteur._gathered_context.update({"nom": "Lefèvre", "adresse": "8 rue Pasteur"})
    noeud = SimpleNamespace(
        id="n1", name="Étape", champs_etape=("nom", "adresse"), conditions_de_champs=(),
        declenchement_de_l_action=AUTOMATIQUE, demande_type=RECHERCHE, verite_des_actions=None, is_end=False,
    )
    cerveau = _CerveauFactice()
    agent = SimpleNamespace(current_node=noeud, llm=cerveau, travail=travail)
    travail.agent = agent
    setattr(cerveau, ATTRIBUT_DECLENCHEUR, Declencheur(moteur, agent, noeud, AUTOMATIQUE, NOM_OUTIL))
    assert _brancher_les_tours(cerveau)
    contexte = SimpleNamespace(messages=[{"role": "assistant", "content": "Bonjour."}, {"role": "user", "content": "Oui."}])

    async def un_tour(essai):
        moteur._gathered_context["adresse"] = f"8 rue Pasteur, Creil {essai}"
        await cerveau.get_chat_completions(contexte)
        await travail.attendre()
        return cerveau.requetes[-1]

    return un_tour, recues, contexte


def _notices(requete):
    return [m["content"] for m in requete if m["role"] == "user" and m["content"] != "Oui."]


@pytest.mark.asyncio
async def test_b2_automatique_un_resultat_connu_est_dit_au_modele_dans_la_requete_du_tour(appel):
    from api.services.travail.demande_identique import NOTICE_AUTOMATIQUE_DEJA_CONNU

    un_tour, recues, contexte = await _automatique_branche(appel, [DATES])
    assert _notices(await un_tour(0)) == []
    requete = await un_tour(1)
    assert len(recues) == 1
    assert _notices(requete) == [NOTICE_AUTOMATIQUE_DEJA_CONNU.format(resultat=DATES)]
    assert requete[-1] == {"role": "user", "content": "Oui."}, "juste avant la dernière parole"
    assert len(contexte.messages) == 2, "rien dans l'historique"


@pytest.mark.asyncio
async def test_b2_automatique_deja_essaye_sans_succes_est_dit_au_modele_puis_la_requete_d_apres_est_inchangee(appel):
    from api.services.travail.demande_identique import NOTICE_AUTOMATIQUE_DEJA_ESSAYE

    un_tour, recues, _ = await _automatique_branche(appel, ["Manque : date"])
    for essai in range(2):
        assert _notices(await un_tour(essai)) == []
    assert len(recues) == 2, "un seul nouvel essai"
    assert _notices(await un_tour(2)) == [NOTICE_AUTOMATIQUE_DEJA_ESSAYE]
    assert len(recues) == 2
    # même fiche, même empreinte : le déclencheur ne s'arme plus, la requête d'après ne porte plus la notice
    assert _notices(await un_tour(2)) == []
