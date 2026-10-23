"""[.mark] Lot 11 de correctifs-apres-banc-commun : les corrections décidées au formulaire (F-1 à F-14).

| Test | La garantie |
|---|---|
| F-2, portée de la case | vide : allumée seulement sur une étape qui écrit (fond, écriture, annulation) ; passations, transferts, fins : rien ; ``true`` / ``false`` décident ; une fin jamais |
| F-3, action faite | « bien prise en compte », « pris en charge », « fixé à 240 euros », « validé depuis 2019 » ne sont pas des actions ; « c'est réservé » l'est ; la liste réglée par agent remplace celle du code ; la consigne n'ordonne plus d'appeler un outil |
| F-1, dates (revue 4) | une date du prompt de l'étape est connue ; « mardi », « demain » dits par la personne aussi, pas les jours d'un prompt ; « 1/2 » n'est pas une date, « 3/11 » si |
| F-8, jour faux | « lundi 27 octobre » quand c'est un mardi : retenu, consigne avec le bon jour ; le bon jour passe |
| F-1, boucle (revue 3) | un appel forcé refusé par la garde de réservation est noté : Obligatoire ne reforce pas ; jamais deux forçages pour la même parole |
| F-7, question | Obligatoire laisse le tour libre quand la personne pose une question |
| revue 10 | le choix d'outil d'avant est remis, quel qu'il soit |
| F-1, annulation (revue 5) | une annulation passe sans les champs de l'étape ; une réservation, elle, reste gardée |
| F-1, menu (revue 7) | chercher + réserver + annuler : l'action d'écriture est armée ; deux écritures : rien |
| F-4, automatique | donnée corrigée après une réservation : avec annulation, le fond défait puis refait ; sans, rien ne repart |
| F-14, attente | plusieurs champs manquent : aucune attente du greffier ; un seul : attente |
| F-3, réglage | ``verite_formulations_d_action`` lu par les réglages de la fiche, vide = défaut |
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
from pipecat.utils.types import NOT_GIVEN

from api.schemas.fiche_agent import ChampFiche
from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.pipecat.reponse_avalee import ATTRIBUT_VERITE
from api.services.travail.reglages import NOM_OUTIL
from api.services.workflow import declenchement_de_l_action as declenchement
from api.services.workflow import enveloppe_des_actions as enveloppe
from api.services.workflow import verite_des_actions as verite
from api.services.workflow.declenchement_de_l_action import (
    AUTOMATIQUE,
    CONSIGNE_REFAIRE,
    OBLIGATOIRE,
    Declencheur,
    action_de_l_etape,
)
from api.services.workflow.fiche_au_fil_de_leau import ReglagesFiche
from api.services.workflow.verite_des_actions import (
    CONSIGNE_ACTION,
    RAISON_ACTION,
    RAISON_DATE,
    RAISON_JOUR,
    VerificateurDeReplique,
    brancher_la_verite_des_actions,
    case_de_l_etape,
    dates_dans,
    dates_relatives_dites,
    etape_qui_ecrit,
    jours_faux,
)

RESERVER = "reserver"
CHERCHER = "chercher"
ANNULER = "annuler"
MARDI = datetime(2026, 10, 27, 9, tzinfo=verite.FUSEAU)  # le 27 octobre 2026 est un mardi


def _reglages(annule=ANNULER, formulations=()):
    return ReglagesFiche(
        champs=(
            ChampFiche(nom="nom", origine="dicte"),
            ChampFiche(nom="adresse", origine="dicte"),
            ChampFiche(
                nom="rendez_vous",
                origine="deduit",
                valeurs=["confirme", "a_rappeler", "annule"],
                rempli_par_outil=RESERVER,
                annule_par_outil=annule,
            ),
        ),
        etiquettes=True,
        formulations_d_action=tuple(formulations),
    )


def _moteur(**reglages):
    return SimpleNamespace(_fiche=_reglages(**reglages), _gathered_context={}, notes_en_cours=set())


# --------------------------------------------------------------------------- #
# F-2 : la case allumée seulement sur une étape qui écrit
# --------------------------------------------------------------------------- #


def test_f2_une_etape_qui_ecrit_et_les_autres():
    moteur = _moteur()
    assert etape_qui_ecrit(moteur, {RESERVER}, False)
    assert etape_qui_ecrit(moteur, {ANNULER}, False)
    assert etape_qui_ecrit(moteur, set(), True)  # le travail de fond
    # une recherche seule, ou rien d'enveloppé (passations, transfert, fin : jamais dans les actions) : non
    assert not etape_qui_ecrit(moteur, {CHERCHER}, False)
    assert not etape_qui_ecrit(moteur, set(), False)


def test_f2_la_case_vide_suit_l_ecriture_la_case_reglee_decide():
    vide = SimpleNamespace(verite_des_actions=None)
    assert case_de_l_etape(vide, True) and not case_de_l_etape(vide, False)
    assert case_de_l_etape(SimpleNamespace(verite_des_actions=True), False)
    assert not case_de_l_etape(SimpleNamespace(verite_des_actions=False), True)


def test_f2_brancher_ne_pose_rien_sur_une_etape_de_passations_seulement():
    moteur = _moteur()
    llm = SimpleNamespace()
    accueil = SimpleNamespace(verite_des_actions=None, is_end=False)
    agent = SimpleNamespace(llm=llm, current_node=accueil)
    actif = brancher_la_verite_des_actions(moteur, agent, accueil, etape_qui_ecrit(moteur, set(), False))
    assert not actif and getattr(llm, ATTRIBUT_VERITE) is None
    accueil.verite_des_actions = True  # allumée à la main : posée
    assert brancher_la_verite_des_actions(moteur, agent, accueil, False)
    assert getattr(llm, ATTRIBUT_VERITE) is not None
    fin = SimpleNamespace(verite_des_actions=True, is_end=True)  # une fin, jamais
    assert not brancher_la_verite_des_actions(moteur, SimpleNamespace(llm=llm, current_node=fin), fin, True)


def test_f2_le_moteur_passe_l_ecriture_et_non_les_outils_de_l_etape():
    import inspect

    from api.services.workflow import pipecat_engine

    source = inspect.getsource(pipecat_engine)
    assert "etape_qui_ecrit(self, actions_offertes(self), etape_du_fond)" in source
    assert "bool(node.tool_uuids) or etape_du_fond" not in source


# --------------------------------------------------------------------------- #
# F-3 : « action faite », sans faux positif, réglable
# --------------------------------------------------------------------------- #


def _verif(**reglages):
    moteur = _moteur(**reglages)
    return VerificateurDeReplique(moteur, SimpleNamespace(current_node=SimpleNamespace(verite_des_actions=True)))


@pytest.mark.parametrize(
    "texte",
    [
        "Votre demande est bien prise en compte.",
        "Le déplacement est pris en charge par le magasin.",
        "Le tarif est fixé à 240 euros.",
        "Votre contrat est validé depuis 2019.",
    ],
)
def test_f3_un_etat_n_est_pas_une_action_faite(texte):
    assert _verif().controler(texte, []) is None


def test_f3_une_action_annoncee_sans_outil_est_retenue_sans_ordre_d_appel():
    retenue = _verif().controler("C'est réservé pour vous.", [])
    assert retenue is not None and retenue.raison == RAISON_ACTION
    assert retenue.consigne == CONSIGNE_ACTION and "Appelle" not in CONSIGNE_ACTION


def test_f3_la_liste_reglee_par_agent_remplace_celle_du_code():
    regle = _verif(formulations=("enregistré",))
    assert regle.controler("Votre demande est enregistrée.", []) is not None
    assert regle.controler("C'est réservé pour vous.", []) is None  # hors de la liste de cet agent


def test_f3_le_reglage_est_lu_par_les_reglages_de_la_fiche_vide_egal_defaut():
    base = {"fiche_au_fil_de_leau": True, "fiche_champs": [{"nom": "nom", "type": "string", "origine": "dicte"}]}
    assert ReglagesFiche.depuis(base).formulations_d_action == ()
    lu = ReglagesFiche.depuis({**base, "verite_formulations_d_action": ["enregistré", " ", "transmis"]})
    assert lu.formulations_d_action == ("enregistré", "transmis")
    assert WorkflowConfigurationDefaults().verite_formulations_d_action == []
    assert verite.regle_de_l_action_faite(()) is verite._ACTION_FAITE  # vide = la règle par défaut


# --------------------------------------------------------------------------- #
# F-1 (revue 4) : les dates connues ; F-8 : le jour faux
# --------------------------------------------------------------------------- #


def test_revue4_une_fraction_n_est_pas_une_date_une_barre_avec_mois_l_est():
    assert dates_dans("la moitié, 1/2") == set()
    assert dates_dans("le 3/11") == {(11, 3)}
    assert dates_dans("le 03/02/2027") == {(2, 3)}


def test_revue4_les_dates_du_prompt_de_l_etape_sont_connues():
    systeme = {"role": "system", "content": "Le magasin est fermé du 24 décembre au 2 janvier."}
    assert _verif().controler("Nous sommes fermés à partir du 24 décembre.", [systeme]) is None
    retenue = _verif().controler("Nous sommes fermés à partir du 24 décembre.", [])
    assert retenue is not None and retenue.raison == RAISON_DATE


def test_revue4_les_dates_relatives_de_la_personne_sont_connues_pas_les_jours_d_un_prompt():
    vues = dates_relatives_dites("Plutôt mardi prochain, ou demain.", MARDI)
    assert (10, 28) in vues  # demain
    assert {(11, 3), (11, 10)} <= vues  # les mardis à venir
    mardis = dates_relatives_dites("mardi")
    personne = {"role": "user", "content": "Mardi prochain, si possible."}
    assert mardis <= verite.dates_connues(_moteur(), [personne])
    # les jours d'ouverture d'un prompt ne rendent aucun mardi connu
    prompt = {"role": "system", "content": "Ouvert du lundi au samedi."}
    aujourd_hui = datetime.now(verite.FUSEAU)
    assert not (mardis - {(aujourd_hui.month, aujourd_hui.day)}) & verite.dates_connues(_moteur(), [prompt])


def _date_a_venir(jours: int) -> tuple[str, str, str]:
    """(bon jour, mauvais jour, « 3 novembre ») d'une date dans ``jours`` jours."""
    from datetime import timedelta

    d = datetime.now(verite.FUSEAU) + timedelta(days=jours)
    bon = verite.JOURS[d.weekday()]
    return bon, verite.JOURS[(d.weekday() + 1) % 7], f"{d.day} {verite.NOMS_DES_MOIS[d.month]}"


def test_f8_un_jour_faux_est_retenu_le_bon_jour_passe():
    assert jours_faux("le lundi 27 octobre", MARDI) == [("lundi 27 octobre", "mardi 27 octobre")]
    assert jours_faux("le mardi 27 octobre", MARDI) == []
    bon, mauvais, date = _date_a_venir(10)
    connue = [{"role": "tool", "content": date}]
    retenue = _verif().controler(f"Je vous propose le {mauvais} {date}.", connue)
    assert retenue is not None and retenue.raison == RAISON_JOUR and f"{bon} {date}" in retenue.consigne
    assert _verif().controler(f"Je vous propose le {bon} {date}.", connue) is None


# --------------------------------------------------------------------------- #
# F-1 (revue 3), F-7, revue 10 : la position Obligatoire
# --------------------------------------------------------------------------- #


class _Contexte:
    def __init__(self, messages):
        self.messages = messages
        self.tool_choice = NOT_GIVEN
        self.poses = []

    def set_tool_choice(self, choix):
        self.poses.append(choix)
        self.tool_choice = choix


def _banc_obligatoire():
    moteur = _moteur()
    moteur._gathered_context.update({"nom": "Durand", "adresse": "8 rue Pasteur"})
    noeud = SimpleNamespace(
        id="n1", name="Étape", champs_etape=("nom", "adresse"), conditions_de_champs=(),
        declenchement_de_l_action=OBLIGATOIRE, demande_type=None, verite_des_actions=None, is_end=False,
    )
    agent = SimpleNamespace(current_node=noeud, llm=SimpleNamespace(), travail=None)
    return moteur, noeud, agent, Declencheur(moteur, agent, noeud, OBLIGATOIRE, RESERVER)


async def test_revue3_un_appel_force_refuse_est_note_et_ne_se_reforce_pas():
    moteur, _noeud, agent, declencheur = _banc_obligatoire()
    contexte = _Contexte([{"role": "user", "content": "Le jeudi 6 novembre."}])
    remettre = await declencheur.avant_le_tour(contexte)
    assert remettre is not None and contexte.tool_choice == declenchement.choix_de_l_outil(RESERVER)
    remettre()
    # le modèle appelle réserver, la garde de réservation le refuse (une recherche a donné d'autres dates)
    verite.noter_l_action(moteur, CHERCHER, {}, {"dates": ["3 novembre"]}, {})
    executions = []

    async def action(params):
        executions.append(params.arguments)
        await params.result_callback({"statut": "confirme"})

    rendus = []

    async def rendre(resultat, **_):
        rendus.append(resultat)

    await enveloppe.envelopper_l_action(moteur, RESERVER, action, agent)(
        SimpleNamespace(result_callback=rendre, arguments={"date": "6 novembre"})
    )
    assert rendus[0]["statut"] == "incomplet" and executions == []
    # Pipecat relance le modèle dans le même tour : rien n'est reforcé
    assert await declencheur.avant_le_tour(_Contexte(contexte.messages)) is None


async def test_revue3_jamais_deux_forcages_pour_la_meme_parole():
    _m, _n, _a, declencheur = _banc_obligatoire()
    messages = [{"role": "user", "content": "Voilà mes coordonnées."}]
    assert await declencheur.avant_le_tour(_Contexte(messages)) is not None
    assert await declencheur.avant_le_tour(_Contexte(messages)) is None
    suite = [*messages, {"role": "assistant", "content": "…"}, {"role": "user", "content": "Et donc ?"}]
    # une nouvelle parole, mais c'est une question : tour libre (F-7)
    assert await declencheur.avant_le_tour(_Contexte(suite)) is None


async def test_f7_une_question_de_la_personne_laisse_le_tour_libre():
    _m, _n, _a, declencheur = _banc_obligatoire()
    contexte = _Contexte([{"role": "user", "content": "Vous êtes ouverts samedi ?"}])
    assert await declencheur.avant_le_tour(contexte) is None and contexte.poses == []


async def test_revue10_le_choix_d_avant_est_remis_quel_qu_il_soit():
    _m, _n, _a, declencheur = _banc_obligatoire()
    contexte = _Contexte([{"role": "user", "content": "C'est tout bon."}])
    contexte.tool_choice = None
    remettre = await declencheur.avant_le_tour(contexte)
    remettre()
    assert contexte.tool_choice is None and contexte.poses[-1] is None


# --------------------------------------------------------------------------- #
# F-1 (revue 5) : l'annulation sans les champs de l'étape ; (revue 7) : l'action d'écriture armée
# --------------------------------------------------------------------------- #


async def test_revue5_une_annulation_passe_sans_les_champs_de_l_etape():
    moteur = _moteur()
    noeud = SimpleNamespace(champs_etape=("nom", "adresse"), conditions_de_champs=(), verite_des_actions=None)
    agent = SimpleNamespace(current_node=noeud)
    faits = []

    async def action(params):
        faits.append(params.arguments)
        await params.result_callback({"statut": "annule"})

    rendus = []

    async def rendre(resultat, **_):
        rendus.append(resultat)

    await enveloppe.envelopper_l_action(moteur, ANNULER, action, agent)(
        SimpleNamespace(result_callback=rendre, arguments={"nom": "Durand"})
    )
    assert faits == [{"nom": "Durand"}] and rendus[0]["statut"] == "annule"
    # la réservation, elle, reste gardée (l'adresse manque)
    rendus.clear()
    await enveloppe.envelopper_l_action(moteur, RESERVER, action, agent)(
        SimpleNamespace(result_callback=rendre, arguments={"nom": "Durand"})
    )
    assert rendus[0]["statut"] == "incomplet"


def test_revue7_l_action_d_ecriture_est_armee_a_cote_d_une_recherche_et_d_une_annulation():
    moteur = _moteur()
    assert action_de_l_etape(frozenset({CHERCHER, RESERVER, ANNULER}), False, moteur) == RESERVER
    assert action_de_l_etape(frozenset({CHERCHER, RESERVER, ANNULER}), True, moteur) == NOM_OUTIL
    deux = SimpleNamespace(
        _fiche=ReglagesFiche(
            champs=(
                ChampFiche(nom="a", origine="deduit", rempli_par_outil="x"),
                ChampFiche(nom="b", origine="deduit", rempli_par_outil="y"),
            )
        )
    )
    assert action_de_l_etape(frozenset({"x", "y"}), False, deux) is None
    assert action_de_l_etape(frozenset({CHERCHER}), False, moteur) == CHERCHER  # une seule action : comme avant


# --------------------------------------------------------------------------- #
# F-4 : Automatique et la donnée corrigée après une réservation
# --------------------------------------------------------------------------- #


class _Travail:
    def __init__(self):
        self.demandes = []

    async def confier(self, demande):
        self.demandes.append(demande)
        return {"statut": "confie"}


def _banc_automatique(annule=ANNULER):
    moteur = _moteur(annule=annule)
    moteur._gathered_context.update({"nom": "Durand", "adresse": "8 rue Pasteur"})
    moteur.travaux = []
    noeud = SimpleNamespace(
        id="n1", name="Étape", champs_etape=("nom", "adresse"), conditions_de_champs=(),
        declenchement_de_l_action=AUTOMATIQUE, demande_type=None, verite_des_actions=None, is_end=False,
    )
    travail = _Travail()
    agent = SimpleNamespace(current_node=noeud, llm=SimpleNamespace(), travail=travail)
    return moteur, Declencheur(moteur, agent, noeud, AUTOMATIQUE, NOM_OUTIL), travail


async def test_f4_avec_annulation_le_fond_defait_puis_refait():
    moteur, declencheur, travail = _banc_automatique()
    assert await declencheur.lancer_automatiquement()
    verite.noter_l_action(moteur, RESERVER, {"adresse": "8 rue Pasteur"}, {"statut": "confirme"}, {"rendez_vous": "confirme"})
    moteur._gathered_context["adresse"] = "10 rue Pasteur"  # l'appelant corrige
    assert await declencheur.lancer_automatiquement()
    assert len(travail.demandes) == 2
    premiere = CONSIGNE_REFAIRE.split("(")[0]
    assert premiere not in travail.demandes[0] and travail.demandes[1].startswith(premiere)


async def test_f4_sans_annulation_rien_ne_repart_apres_une_ecriture():
    moteur, declencheur, travail = _banc_automatique(annule=None)
    assert await declencheur.lancer_automatiquement()
    verite.noter_l_action(moteur, RESERVER, {}, {"statut": "confirme"}, {"rendez_vous": "confirme"})
    moteur._gathered_context["adresse"] = "10 rue Pasteur"
    assert not await declencheur.lancer_automatiquement()
    assert len(travail.demandes) == 1


async def test_f4_apres_une_annulation_reussie_la_nouvelle_demande_part_normalement():
    moteur, declencheur, travail = _banc_automatique()
    verite.noter_l_action(moteur, RESERVER, {}, {"statut": "confirme"}, {"rendez_vous": "confirme"})
    verite.noter_l_action(moteur, ANNULER, {}, {"statut": "annule"}, {"rendez_vous": "annule"})
    assert verite.ecriture_en_vigueur(moteur) is None
    assert await declencheur.lancer_automatiquement()
    assert not travail.demandes[0].startswith(CONSIGNE_REFAIRE.split("(")[0])


# --------------------------------------------------------------------------- #
# F-14 : l'attente du greffier seulement pour le dernier champ
# --------------------------------------------------------------------------- #


async def test_f14_plusieurs_champs_manquent_aucune_attente_un_seul_attente():
    moteur = _moteur()
    noeud = SimpleNamespace(champs_etape=("nom", "adresse"), conditions_de_champs=())
    passe = asyncio.get_running_loop().create_future()
    moteur.notes_en_cours = {passe}
    debut = asyncio.get_running_loop().time()
    refus = await enveloppe.garde_du_noeud_apres_les_notes(moteur, noeud, dernier_seulement=True)
    assert refus is not None and len(refus["manque"]) == 2
    assert asyncio.get_running_loop().time() - debut < 0.2  # aucune attente
    moteur._gathered_context["nom"] = "Durand"
    asyncio.get_running_loop().call_later(0.05, lambda: (moteur._gathered_context.update(adresse="8 rue"), passe.set_result(None)))
    assert await enveloppe.garde_du_noeud_apres_les_notes(moteur, noeud, dernier_seulement=True) is None


# --------------------------------------------------------------------------- #
# F-9 : « ne sait pas » n'est pas « refuse », pour toutes les façons de noter
# --------------------------------------------------------------------------- #


def test_f9_l_outil_de_notes_et_le_post_scriptum_portent_la_regle():
    from api.services.workflow import fiche_au_fil_de_leau as fiche

    assert fiche.REGLE_REFUS_ET_IGNORANCE in fiche.DESCRIPTION_OUTIL
    reglages = ReglagesFiche.depuis(
        {
            "fiche_au_fil_de_leau": True,
            "fiche_mode_de_note": "post_scriptum",
            "fiche_champs": [{"nom": "dernier_entretien", "type": "string", "origine": "dicte"}],
        }
    )
    assert fiche.REGLE_REFUS_ET_IGNORANCE in fiche.consigne_du_mode(reglages)
    note_d_abord = ReglagesFiche.depuis(
        {
            "fiche_au_fil_de_leau": True,
            "fiche_mode_de_note": "post_scriptum",
            "ordre_de_la_reponse": "porte_note_phrase",
            "fiche_champs": [{"nom": "dernier_entretien", "type": "string", "origine": "dicte"}],
        }
    )
    assert fiche.REGLE_REFUS_ET_IGNORANCE in fiche.consigne_du_mode(note_d_abord)
    assert "jamais « refusé »" in fiche.REGLE_REFUS_ET_IGNORANCE


# --------------------------------------------------------------------------- #
# F-11 : le numéro sans zéro de tête ou avec l'indicatif
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "valeur, attendu",
    [
        ("612345678", "0612345678"),
        ("6 12 34 56 78", "0612345678"),
        ("+33 6 12 34 56 78", "0612345678"),
        ("+33612345678", "0612345678"),
        ("0033 6 12 34 56 78", "0612345678"),
        ("06 12 34 56 78", "06 12 34 56 78"),  # déjà national : inchangé
        ("0612345", "0612345"),  # incomplet : inchangé (K10 et C1 le refusent)
    ],
)
def test_f11_forme_nationale(valeur, attendu):
    from api.services.workflow.fiche_au_fil_de_leau import numero_en_forme_nationale

    assert numero_en_forme_nationale(valeur, 10) == attendu


def test_f11_un_code_postal_ne_recoit_jamais_de_zero():
    from api.services.workflow.fiche_au_fil_de_leau import numero_en_forme_nationale

    assert numero_en_forme_nationale("6010", 5) == "6010"


@pytest.mark.parametrize(
    "parole, ecrit",
    [
        ("six douze trente-quatre cinquante-six soixante-dix-huit", "612345678"),
        ("plus trente-trois six douze trente-quatre cinquante-six soixante-dix-huit", "+33 6 12 34 56 78"),
    ],
)
async def test_f11_le_numero_dit_ainsi_est_ecrit_par_le_vrai_point_d_ecriture(parole, ecrit):
    from api.tests.mark.test_correctifs_fiche_et_fond import _config
    from api.tests.mark.test_greffier import _Modele, _Montage

    montage = _Montage(_Modele({"numero_dicte": ecrit}), _config())
    montage.messages = [{"role": "user", "content": parole}]
    await montage.passe()
    assert montage.fiche.get("numero_dicte") == "0612345678"


async def test_f11_des_chiffres_jamais_dits_restent_refuses():
    from api.tests.mark.test_correctifs_fiche_et_fond import _config
    from api.tests.mark.test_greffier import _Modele, _Montage

    montage = _Montage(_Modele({"numero_dicte": "612345678"}), _config())
    montage.messages = [{"role": "user", "content": "six douze trente-quatre"}]
    await montage.passe()
    assert "numero_dicte" not in montage.fiche


# --------------------------------------------------------------------------- #
# F-13 : les filets au format Responses aussi (vrai service, faux fournisseur)
# --------------------------------------------------------------------------- #


def _f13():
    from api.tests.mark import test_fournisseur_responses as fr

    return fr


@pytest.mark.parametrize("api", ["chat_completions", "responses"])
async def test_f13_une_action_inventee_est_retenue_et_relancee_dans_les_deux_formats(api):
    fr = _f13()
    from api.services.pipecat.reponse_avalee import ATTRIBUT_VERITE

    service, faux = fr._service(api, [fr.Rep(texte="C'est réservé pour vous."), fr.Rep(texte="Je vérifie la date.")])
    setattr(service, ATTRIBUT_VERITE, _verif())
    texte, _ = await fr._jouer(service)
    assert texte == "Je vérifie la date."
    assert len(faux.vus) == 2 and faux.vus[1]["stream"] is False
    assert any(CONSIGNE_ACTION in str(m.get("content")) for m in fr._entrees(api, faux.vus[1]) if isinstance(m, dict))


@pytest.mark.parametrize("api", ["chat_completions", "responses"])
async def test_f13_une_replique_juste_passe_sans_relance_dans_les_deux_formats(api):
    fr = _f13()
    from api.services.pipecat.reponse_avalee import ATTRIBUT_VERITE

    service, faux = fr._service(api, [fr.Rep(texte="Je cherche des dates pour vous.")])
    setattr(service, ATTRIBUT_VERITE, _verif())
    texte, _ = await fr._jouer(service)
    assert texte == "Je cherche des dates pour vous." and len(faux.vus) == 1


async def test_f13_l_appel_obligatoire_part_au_format_responses():
    fr = _f13()
    service, faux = fr._service("responses", [fr.Rep(texte="D'accord.")])
    contexte = fr._contexte()
    contexte.set_tool_choice(declenchement.choix_de_l_outil("meteo_du_jour"))
    await fr._jouer(service, contexte)
    assert faux.vus[0]["tool_choice"] == {"type": "function", "name": "meteo_du_jour"}
    sans, faux_sans = fr._service("responses", [fr.Rep(texte="D'accord.")])
    await fr._jouer(sans)
    assert "tool_choice" not in faux_sans.vus[0] or faux_sans.vus[0]["tool_choice"] in (None, "auto")


def test_f13_les_arguments_illisibles_sont_deja_executes_comme_vides_au_format_responses():
    """Pipecat 1.12 (``services/openai/responses/llm.py``) : arguments illisibles = ``{}``, l'appel part."""
    import inspect

    from pipecat.services.openai.responses import llm

    source = inspect.getsource(llm)
    assert 'arguments = json.loads(fc["arguments"]) if fc["arguments"] else {}' in source
    assert "arguments = {}" in source


def test_f13_le_choix_d_outil_se_traduit_au_format_responses():
    from api.services.pipecat.responses_llm import choix_d_outil_responses

    assert choix_d_outil_responses({"type": "function", "function": {"name": "x"}}) == {"type": "function", "name": "x"}
    assert choix_d_outil_responses(NOT_GIVEN) is None
    assert choix_d_outil_responses("required") == "required"
