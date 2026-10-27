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
"""

import asyncio
from types import SimpleNamespace

import pytest

from api.schemas.fiche_agent import ChampFiche
from api.services.travail.agent import CONSIGNE_DEJA_FAIT
from api.services.travail.demande import ENTETE_DES_VALEURS, demande_avec_la_fiche
from api.services.workflow.fiche_au_fil_de_leau import ReglagesFiche
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
