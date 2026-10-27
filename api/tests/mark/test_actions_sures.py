"""[.mark] Le fond ne fait que ce qu'on lui demande (chantier actions-sures-et-parite-clavier, lot B).

Plan `Labo-agent-vocal/plans/actions-sures-et-parite-clavier/`. Banc de fin du 27/10 : pour dire au revoir, l'agent
confiait « Au revoir » au fond ; « confier » y joignait TOUTE la fiche, dont la demande d'origine de la personne et
« rendez-vous : confirmé », sous un en-tête qui en faisait des ordres ; le fond réservait (7 appels sur 26). Et
« annuler » arrivé après une réservation répondait « aucun travail en cours » : l'agent réservait une seconde date.

| Test | Ce qu'il prouve |
|---|---|
| adieu du run 2061 | à l'étape du rendez-vous, la demande d'adieu ne porte ni la demande d'origine ni l'état du rendez-vous |
| vraie demande | « Réserver … lundi 2 novembre » porte toujours les coordonnées que l'étape attend |
| étape sans champ | rien n'est joint : la demande part telle que le modèle l'a écrite |
| en-tête | les valeurs jointes sont dites « pas des demandes » |
| annuler après coup | sans travail en cours, le dernier travail qui a agi est rendu au modèle avec la consigne de le défaire |
| annuler pendant | un travail annulé après avoir appelé ses outils le dit |
| changement de date (lot F, runs 2086, 2087) | l'annulation de l'ancien rendez-vous (par sa date) laisse « confirme » et dite faite, dans les deux ordres, même pour un rendez-vous d'un appel précédent ; une réservation refusée ne tient pas ; « une écriture est en vigueur » lit le même suivi |
| actions qui tiennent (lot F, banc local, E11) | une demande au fond porte la réservation encore tenue de l'appel, sous un en-tête d'état ; plus rien quand elle est défaite ; rien sans action |
| journal au clavier (lot F) | le journal des actions survit au moteur refait à chaque réplique (fiche de l'appel), son nom de clé est réservé |
| une réservation tient déjà (lot F, E11) | une nouvelle réservation rend la question « remplacer ou ajouter » ; le réessai dans le même tour est retenu ; après une parole de la personne elle part (deux rendez-vous possibles) ; défaire l'ancienne la libère tout de suite |
| deux demandes d'une même réplique (lot F, E11) | la seconde attend la fin de la première au lieu de l'arrêter ; une demande d'un tour suivant reste une modification ; annuler vide la suite |
| outil « annuler » (lot F) | sa description dit qu'il arrête un travail en cours et ne défait pas une action faite |
"""

import asyncio
from types import SimpleNamespace

import pytest

from api.schemas.fiche_agent import ChampFiche
from api.services.travail.agent import CONSIGNE_DEJA_FAIT, DESCRIPTION_ANNULER
from api.services.travail.demande import (
    ENTETE_DES_ACTIONS,
    ENTETE_DES_VALEURS,
    demande_avec_la_fiche,
)
from api.services.workflow.enveloppe_des_actions import ISSUE_ANNULE
from api.services.workflow.fiche_au_fil_de_leau import ReglagesFiche
from api.services.workflow.verite_des_actions import ecriture_en_vigueur
from api.tests.mark.test_annulation_d_un_rendez_vous import ANNULER, RESERVER, Banc
from api.tests.mark.test_travail_de_fond import DEMANDE, RESULTAT, Appel, _texte

CHAMPS = (
    "numero_dicte", "nom", "motif", "verbatim_demande", "commune", "code_postal", "adresse_intervention",
    "jour_souhaite", "rendez_vous", "prenom", "email",
)
# La fiche du run 2061 au tour de l'adieu (après l'annulation, « confirme » y était resté).
FICHE_2061 = {
    "numero_dicte": "0761453210",
    "nom": "Girard",
    "motif": "réserver l'entretien de mon poêle à granulés Klover",
    "verbatim_demande": "je voudrais réserver l'entretien de mon poêle à granulés Klover, je suis sous contrat",
    "commune": "Senlis",
    "code_postal": "60300",
    "adresse_intervention": "14 Rue de Beauvais",
    "jour_souhaite": "lundi 2 novembre",
    "rendez_vous": "confirme",
    "prenom": "Paul",
}
# L'étape du rendez-vous de l'agent 224.
ETAPE_RENDEZ_VOUS = SimpleNamespace(
    champs_etape=("nom", "prenom", "numero_dicte", "adresse_intervention", "commune", "code_postal", "email"),
    conditions_de_champs=(),
)


def _moteur(fiche=FICHE_2061):
    return SimpleNamespace(
        _fiche=ReglagesFiche(champs=tuple(ChampFiche(nom=n, origine="dicte") for n in CHAMPS)),
        _gathered_context=dict(fiche),
    )


@pytest.mark.parametrize(
    "adieu",
    [
        "Au revoir, et bonne journée !",
        "Rien",
        "aucune",
        "fermer l'appel",
        "Clore l'appel.",
        "Transmettre la demande au magasin.",
        "Au revoir, Monsieur Henry, et à bientôt chez Nuances de Feu !",
    ],
)
def test_l_adieu_ne_porte_ni_la_demande_d_origine_ni_l_etat_de_l_action(adieu):
    demande = demande_avec_la_fiche(_moteur(), adieu, ETAPE_RENDEZ_VOUS)
    assert demande.startswith(adieu)
    for absent in ("réserver", "motif", "verbatim_demande", "rendez_vous", "confirme", "jour_souhaite"):
        assert absent not in demande, (absent, demande)


def test_une_vraie_demande_porte_les_coordonnees_que_l_etape_attend():
    demande = demande_avec_la_fiche(
        _moteur(), "Réserver le passage du technicien le lundi 2 novembre.", ETAPE_RENDEZ_VOUS
    )
    for present in ("- nom : Girard", "- prenom : Paul", "- numero_dicte : 0761453210",
                    "- adresse_intervention : 14 Rue de Beauvais", "- commune : Senlis", "- code_postal : 60300"):
        assert present in demande, (present, demande)
    assert ENTETE_DES_VALEURS in demande


def test_une_etape_sans_champ_ne_joint_rien():
    etape = SimpleNamespace(champs_etape=None, conditions_de_champs=())
    assert demande_avec_la_fiche(_moteur(), "Au revoir.", etape) == "Au revoir."
    assert demande_avec_la_fiche(_moteur(), "Au revoir.", None) == "Au revoir."


def test_l_en_tete_dit_que_les_valeurs_ne_sont_pas_des_demandes():
    assert "ce ne sont pas des demandes" in ENTETE_DES_VALEURS
    assert "à utiliser telles quelles" not in ENTETE_DES_VALEURS


@pytest.fixture
async def appel():
    a = Appel()
    try:
        yield a
    finally:
        await a.arreter()


RENDEZ_VOUS = ChampFiche(
    nom="rendez_vous",
    origine="deduit",
    valeurs=["confirme", "a_rappeler", "annule"],
    rempli_par_outil="reserver_entretien",
    annule_par_outil="annuler_entretien",
)


async def _monte(appel, travaux=None):
    await appel.monter(source_etapes=[_texte("rien")], fond_etapes=[_texte(RESULTAT)], outils_du_fond=False)
    appel.engine._fiche = ReglagesFiche(champs=(RENDEZ_VOUS,))
    if travaux is not None:
        appel.engine._gathered_context["travaux"] = travaux
    return appel.engine.active_agent.travail


@pytest.mark.asyncio
async def test_annuler_apres_coup_rend_ce_que_le_dernier_travail_a_ecrit(appel):
    travail = await _monte(appel, [
        {"statut": "fait", "outils": ["chercher_dates_entretien", "reserver_entretien"],
         "resultat": "Réservation confirmée : lundi 2 novembre."}
    ])
    retour = await travail.annuler()
    assert retour["statut"] == "aucun travail en cours"
    assert retour["dernier_travail"] == {
        "outils": ["reserver_entretien"],
        "resultat": "Réservation confirmée : lundi 2 novembre.",
    }
    assert retour["consigne"] == CONSIGNE_DEJA_FAIT


@pytest.mark.parametrize(
    "outils",
    [[], ["chercher_dates_entretien"], ["annuler_entretien"]],
    ids=["sans outil", "recherche seule", "annulation seule"],
)
@pytest.mark.asyncio
async def test_annuler_apres_un_travail_qui_n_a_rien_ecrit_reste_aucun_travail(appel, outils):
    """Revue du 27/10 : une recherche n'a rien à défaire, et « défaire » une annulation serait refaire l'action."""
    travail = await _monte(appel, [{"statut": "fait", "outils": outils, "resultat": "…"}])
    assert await travail.annuler() == {"statut": "aucun travail en cours"}


async def _pendant(appel, outils):
    travail = await _monte(appel)
    portail = asyncio.Event()

    async def bloque(_travail, _demande):
        await portail.wait()
        return RESULTAT

    travail._executeur = bloque
    assert await travail.confier(DEMANDE) == {"statut": "lancé"}
    for nom in outils:
        travail._noter_l_outil(nom)
    return await travail.annuler()


@pytest.mark.asyncio
async def test_annuler_pendant_un_travail_qui_a_deja_ecrit_le_dit(appel):
    retour = await _pendant(appel, ["chercher_dates_entretien", "reserver_entretien"])
    assert retour == {"statut": "annulé", "outils_deja_appeles": ["reserver_entretien"], "consigne": CONSIGNE_DEJA_FAIT}


@pytest.mark.asyncio
async def test_annuler_pendant_une_recherche_reste_un_simple_annule(appel):
    assert await _pendant(appel, ["chercher_dates_entretien"]) == {"statut": "annulé"}


ANCIEN = "2026-11-05"  # la date que rend la première réservation du banc
NOUVEAU = {"statut": "confirme", "rendez_vous": "confirme", "debut": "2026-11-02T08:00:00+01:00"}


async def _nouvelle_date(banc):
    banc.reponses[RESERVER] = NOUVEAU
    await banc.appeler(RESERVER, nom="Durand")


@pytest.mark.asyncio
async def test_run_2086_reserver_la_nouvelle_date_puis_annuler_l_ancienne_laisse_le_rendez_vous_tenu():
    banc = Banc()
    banc.fiche["tour_appelant"] = 1
    await banc.reserver()
    banc.fiche["tour_appelant"] = 2  # la personne a dit « plutôt lundi » : la nouvelle date est réservée d'abord
    banc.reponses[RESERVER] = NOUVEAU
    assert (await banc.appeler(RESERVER, nom="Durand"))["statut"] == "incomplet"  # remplacer ou ajouter ?
    banc.fiche["tour_appelant"] = 3  # elle a répondu
    await _nouvelle_date(banc)
    rendu = await banc.appeler(ANNULER, nom="Durand", date=ANCIEN)
    assert banc.fiche["rendez_vous"] == "confirme"
    # revue du lot F : l'annulation faite est dite faite au modèle, jamais « non confirmée »
    assert rendu["issue"] == ISSUE_ANNULE
    # une seule vérité : la règle « une écriture est en vigueur » voit le nouveau rendez-vous
    tenue = ecriture_en_vigueur(banc.moteur)
    assert tenue is not None and (11, 2) in tenue.dates


@pytest.mark.asyncio
async def test_run_2087_les_deux_ordres_d_un_meme_travail_finissent_confirme():
    banc = Banc()
    await banc.reserver()
    await banc.appeler(ANNULER, nom="Durand", date=ANCIEN)
    assert banc.fiche["rendez_vous"] == "annule"
    await _nouvelle_date(banc)
    assert banc.fiche["rendez_vous"] == "confirme"


@pytest.mark.asyncio
async def test_rendez_vous_d_un_appel_precedent_deplace_la_nouvelle_date_tient():
    """Revue du lot F : « je rappelle pour décaler », l'ancien rendez-vous n'est pas une écriture de cet appel."""
    banc = Banc()
    await _nouvelle_date(banc)
    rendu = await banc.appeler(ANNULER, nom="Durand", date="2026-10-29")
    assert banc.fiche["rendez_vous"] == "confirme"
    assert rendu["issue"] == ISSUE_ANNULE


@pytest.mark.asyncio
async def test_une_reservation_refusee_ne_tient_pas_l_annulation_de_la_seule_vraie_ecrit_annule():
    banc = Banc()
    await banc.reserver()
    banc.reponses[RESERVER] = {"statut": "indisponible"}
    await banc.appeler(RESERVER, nom="Durand")
    await banc.appeler(ANNULER, nom="Durand", date=ANCIEN)
    assert banc.fiche["rendez_vous"] == "annule"
    assert ecriture_en_vigueur(banc.moteur) is None


@pytest.mark.asyncio
async def test_annuler_le_seul_rendez_vous_sans_date_ecrit_toujours_annule():
    banc = Banc()
    await banc.reserver()
    await banc.appeler(ANNULER, nom="Durand")
    assert banc.fiche["rendez_vous"] == "annule"
    await banc.appeler(RESERVER, nom="Durand")
    assert banc.fiche["rendez_vous"] == "confirme"


def test_la_description_d_annuler_dit_qu_elle_ne_defait_pas_une_action_faite():
    assert "ne défait rien de ce qu'un travail terminé a déjà fait" in DESCRIPTION_ANNULER
    assert "confie une demande qui la défait" in DESCRIPTION_ANNULER
    assert "ne veut plus de sa demande" not in DESCRIPTION_ANNULER


@pytest.mark.asyncio
async def test_e11_la_demande_au_fond_porte_la_reservation_qui_tient_encore():
    banc = Banc()
    banc.moteur._gathered_context = banc.fiche
    assert ENTETE_DES_ACTIONS not in demande_avec_la_fiche(banc.moteur, "Réserver lundi 2 novembre.", ETAPE_RENDEZ_VOUS)
    await banc.reserver()
    demande = demande_avec_la_fiche(banc.moteur, "Réserver lundi 2 novembre.", ETAPE_RENDEZ_VOUS)
    assert demande.startswith("Réserver lundi 2 novembre.")
    assert ENTETE_DES_ACTIONS in demande and f"- {RESERVER} :" in demande and "2026-11-05" in demande
    assert "pas une demande" in ENTETE_DES_ACTIONS
    await banc.appeler(ANNULER, nom="Durand", date=ANCIEN)
    assert ENTETE_DES_ACTIONS not in demande_avec_la_fiche(banc.moteur, "Réserver lundi.", ETAPE_RENDEZ_VOUS)


@pytest.mark.asyncio
async def test_clavier_le_journal_des_actions_survit_au_moteur_refait_a_chaque_replique():
    """Banc local du 27/10 : au clavier, le moteur est refait à chaque tour ; seule la fiche de l'appel passe."""
    banc = Banc()
    await banc.reserver()
    moteur_du_tour_suivant = SimpleNamespace(_fiche=banc.moteur._fiche, _gathered_context=banc.fiche)
    tenue = ecriture_en_vigueur(moteur_du_tour_suivant)
    assert tenue is not None and tenue.nom == RESERVER
    assert ENTETE_DES_ACTIONS in demande_avec_la_fiche(moteur_du_tour_suivant, "Réserver lundi.", ETAPE_RENDEZ_VOUS)
    import json

    json.dumps(banc.fiche)  # la fiche se sauvegarde telle quelle


def test_le_nom_du_journal_est_reserve():
    from api.schemas.fiche_agent import verifier_champs

    with pytest.raises(ValueError, match="reserved"):
        verifier_champs([ChampFiche(nom="mark_journal_des_actions")])


@pytest.mark.asyncio
async def test_e11_une_seconde_reservation_demande_remplacer_ou_ajouter_sans_l_interdire():
    banc = Banc()
    banc.fiche["tour_appelant"] = 4
    await banc.reserver()
    banc.reponses[RESERVER] = NOUVEAU
    rendu = await banc.appeler(RESERVER, nom="Durand")
    assert rendu["statut"] == "incomplet" and rendu["garde"] == "ecriture_qui_tient"
    assert rendu["tient_deja"] and "remplace" in rendu["consigne"]
    assert len(banc.executions[RESERVER]) == 1  # rien n'est parti
    banc.fiche["tour_appelant"] = 5  # la personne a répondu : elle veut les deux
    assert (await banc.appeler(RESERVER, nom="Durand"))["statut"] == "confirme"
    assert len(banc.executions[RESERVER]) == 2


@pytest.mark.asyncio
async def test_e11_defaire_l_ancienne_libere_la_nouvelle_tout_de_suite():
    banc = Banc()
    banc.fiche["tour_appelant"] = 4
    await banc.reserver()
    await banc.appeler(ANNULER, nom="Durand", date=ANCIEN)
    await _nouvelle_date(banc)
    assert len(banc.executions[RESERVER]) == 2
    assert banc.fiche["rendez_vous"] == "confirme"


async def _deux_demandes(appel, tour_de_la_seconde):
    travail = await _monte(appel)
    appel.engine._gathered_context["tour_appelant"] = 3
    portail, faites = asyncio.Event(), []

    async def executeur(_travail, demande):
        faites.append(demande.splitlines()[0])
        if len(faites) == 1:
            await portail.wait()
        return RESULTAT

    travail._executeur = executeur
    assert (await travail.confier("Annuler le jeudi."))["statut"] == "lancé"
    await asyncio.sleep(0)
    appel.engine._gathered_context["tour_appelant"] = tour_de_la_seconde
    second = await travail.confier("Réserver le lundi.")
    portail.set()
    for _ in range(50):
        await asyncio.sleep(0.01)
        if len(faites) == 2 and not travail.occupe:
            break
    return travail, second, faites


@pytest.mark.asyncio
async def test_e11_deux_demandes_de_la_meme_replique_se_suivent(appel):
    travail, second, faites = await _deux_demandes(appel, 3)
    assert second == {"statut": "lancé", "apres": "le travail en cours"}
    assert faites == ["Annuler le jeudi.", "Réserver le lundi."]
    assert [t["statut"] for t in appel.engine._gathered_context["travaux"]][:2] == ["fait", "fait"]


@pytest.mark.asyncio
async def test_une_demande_d_un_tour_suivant_reste_une_modification(appel):
    travail, second, faites = await _deux_demandes(appel, 4)
    assert second == {"statut": "lancé", "demande_precedente": "annulée"}
    assert appel.engine._gathered_context["travaux"][0]["statut"] == "annule"  # la trace du travail arrêté
