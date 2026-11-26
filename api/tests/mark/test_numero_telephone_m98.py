"""[.mark] M98 : le numéro de téléphone, régression du chantier Restauration (appel de production 2569). Mécanisme commun, aucun mot de métier.

Cause : la personne dit « Dix-neuf heures. » ; la garde du chiffre sans source ne lisait une heure dans les paroles de la personne que précédée de
« à, pour, vers… » : la relecture qui disait « pour dix-neuf heures » et le numéro dicté était retenue, et régénérée sans le numéro.

| Test | Ce qu'il prouve |
|---|---|
| garde, 2569 rejoué | une heure, un montant, un nombre dits par la personne sous n'importe quelle forme comptent comme donnés |
| garde, numéro | un numéro de téléphone (réplique ou sources) n'est jamais contrôlé, ni ses paires prises pour une heure, une quantité ou un montant |
| garde, invention | un montant, une heure, une quantité que personne n'a dits restent retenus : la garde n'est pas éteinte |
| commande, affiché | la relecture finit par UNE question qui dit le numéro gardé (réglable), aucune relecture du numéro, ``numero_affiche_dit`` dans les faits, un « oui » enregistre |
| commande, dicté | dicté une fois : relu une fois par le code ; corrigé : le nouveau relu, seul ; un autre numéro dit avec « oui » ne s'enregistre pas sans relecture |
| commande, autre numéro | « non, plutôt le 06… » après la question : le nouveau relu par paires, la question du numéro affiché n'est plus posée |
| phrase réglée | la règle de phrase (agent, étape) remplace le texte par défaut ; éteinte : « C'est bon ? » |
| réservation | même logique |
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from api.schemas.phrases_du_code import ReglePhrase
from api.services.commande.resultat import question_du_numero_affiche
from api.services.mots_dits import numero_en_lettres
from api.services.phrases.catalogue import MOTIFS, NUMERO_AFFICHE_GARDE
from api.services.phrases.regles import resoudre
from api.services.workflow import chiffres_sans_source as c
from api.services.workflow.verite_des_actions import VerificateurDeReplique
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401
from api.tests.mark.test_restauration_commande_finaliser import TEL, Appel
from api.tests.mark.test_restauration_reservation import salle  # noqa: F401
from api.tests.mark.test_verite_des_actions import Banc

QUESTION = "Je note ce numéro de téléphone pour vous joindre en cas de problème, c'est bon ?"
DIT_2569 = "zéro six, dix, vingt, trente, quarante"


def _sources(*paroles: str):
    return c.sources_de([{"role": "user", "content": p} for p in paroles])


# --------------------------------------------------------------------------- #
# La garde du chiffre sans source
# --------------------------------------------------------------------------- #


def test_2569_rejoue_l_heure_dite_sans_preposition_et_le_numero_relu_ne_retiennent_rien():
    banc = Banc()
    banc.agent.reglages = {c.CLE_CHIFFRE_SANS_SOURCE: True}
    verificateur = VerificateurDeReplique(banc.moteur, banc.agent)
    relecture = f"Je note le {DIT_2569}. Je vous relis : une Regina, à emporter, pour dix-neuf heures. Cela fait douze euros. C'est bon ?"
    messages = [
        {"role": "user", "content": "Dix-neuf heures."},
        {"role": "user", "content": "Zéro six, dix, vingt, trente, quarante"},
        {"role": "tool", "content": json.dumps({"statut": "INCOMPLETE", "faits": {"total": 1200}, "suggestion": "Quel est votre numéro de téléphone ?"})},
    ]
    assert verificateur.controler(relecture, messages) is None
    assert _sources("Dix-neuf heures.").heures == {(19, 0)}


@pytest.mark.parametrize(
    "dit, replique",
    [
        ("Dix-neuf heures.", "C'est noté pour dix-neuf heures."),
        ("19 heures", "C'est noté pour 19 h."),
        ("19h", "C'est noté pour dix-neuf heures."),
        ("Vingt heures trente.", "C'est noté pour vingt heures trente."),
        ("sept heures et demie", "Ce sera prêt à sept heures et demie."),
        ("Vingt et une heures et quart", "C'est noté pour vingt et une heures et quart."),
        ("midi", "Ce sera prêt à 12 h."),
    ],
)
def test_une_heure_dite_par_la_personne_sous_toute_forme_compte(dit, replique):
    assert c.chiffres_sans_source(replique, _sources(dit)) == [], (dit, replique)


@pytest.mark.parametrize("dit", ["trente-deux euros quatre-vingts", "Trente-deux quatre-vingts.", "32,80", "j'ai un billet de cinquante"])
def test_un_montant_dit_par_la_personne_sous_toute_forme_compte(dit):
    replique = "Cela fait cinquante euros." if "cinquante" in dit else "Vous réglez trente-deux euros quatre-vingts."
    assert c.chiffres_sans_source(replique, _sources(dit)) == [], dit


@pytest.mark.parametrize(
    "replique",
    [
        f"Je note le {DIT_2569} comme numéro.",
        "Le numéro zéro six, douze, trente-quatre, cinquante-six, soixante-dix-huit est bien noté.",
        "Je note le 06 12 34 56 78 pour vous joindre, trois pizzas.",
        "Votre numéro, le +33 6 10 20 30 40, est gardé.",
        "Je note le 0610203040 dans trois cartons.",
    ],
)
def test_un_numero_de_telephone_dans_la_replique_n_est_jamais_controle(replique):
    sources = _sources("trois")
    assert c.chiffres_sans_source(replique, sources) == [], replique


def test_les_paires_d_un_numero_des_sources_ne_donnent_ni_heure_ni_montant():
    sources = _sources(DIT_2569)
    assert sources.heures == set() and not {1020, 2030, 3040, 1000, 2000} & sources.montants
    assert c.chiffres_sans_source("Cela fait dix euros vingt, pour vingt heures trente.", sources) == ["10 euros 20", "20 h 30"]


def test_une_vraie_invention_reste_retenue():
    sources = _sources("Dix-neuf heures.", "Zéro six, dix, vingt, trente, quarante", "deux pizzas")
    assert c.chiffres_sans_source("Cela fait treize euros quarante et un.", sources) == ["13 euros 41"]
    assert c.chiffres_sans_source("Ce sera prêt à vingt heures quinze.", sources) == ["20 h 15"]
    assert c.chiffres_sans_source("Vous avez trois pizzas.", sources) == ["3 pizzas"]
    # la réplique garde sa lecture stricte : « dans deux heures » n'est pas une heure
    assert c.heures_dites("dans deux heures") == set()


# --------------------------------------------------------------------------- #
# La phrase du code réglable (motif du catalogue)
# --------------------------------------------------------------------------- #


def _regle(**plus):
    return {"motif": NUMERO_AFFICHE_GARDE, "portee": "agent", "variantes": ["Je garde ce numéro pour vous joindre, ça vous va ?"], **plus}


def test_le_motif_est_au_catalogue_avec_son_texte_par_defaut_et_se_regle():
    motif = MOTIFS[NUMERO_AFFICHE_GARDE]
    assert motif.variantes_defaut == (QUESTION,) and motif.actif_par_defaut and motif.libelle_en
    ReglePhrase.model_validate(_regle())  # la règle se pose comme les autres (``regler_phrases`` n'accepte que les motifs du catalogue)
    assert question_du_numero_affiche(None) == QUESTION
    assert question_du_numero_affiche(SimpleNamespace(configurations={"phrases_regles": [_regle()]})) == "Je garde ce numéro pour vous joindre, ça vous va ?"
    assert question_du_numero_affiche(SimpleNamespace(configurations={"phrases_regles": [_regle(active=False, variantes=[])]})) is None
    # l'endroit de l'appel (une règle d'étape résolue par le moteur) passe avant la configuration
    etape = {"phrases_regles": [_regle(portee="etape", etape="Commande", variantes=["À l'étape : ce numéro vous va ?"])]}
    resolue = resoudre(NUMERO_AFFICHE_GARDE, reglages_agent=etape, reglages_principal=etape, etape="Commande")
    ctx = SimpleNamespace(configurations={"phrases_regles": [_regle()]}, phrase_du_code=lambda motif: resolue)
    assert question_du_numero_affiche(ctx) == "À l'étape : ce numéro vous va ?"


def test_l_outil_recoit_la_resolution_du_moteur():
    from api.services.integrations.connectors import outil
    from api.services.integrations.connectors.catalogue import connecteur
    from api.services.integrations.connectors.execution import contexte_de

    vue = []
    engine = SimpleNamespace(phrases=SimpleNamespace(phrase=lambda motif, *a, **k: vue.append(motif) or "résolue"))
    trouve = outil._phrase_du_code(engine)
    action = connecteur("commande").actions[0]
    ctx = contexte_de(action, {}, {}, phrase_du_code=trouve)
    assert ctx.phrase_du_code(NUMERO_AFFICHE_GARDE) == "résolue" and vue == [NUMERO_AFFICHE_GARDE]
    assert outil._phrase_du_code(SimpleNamespace()) is None and contexte_de(action, {}, {}).phrase_du_code is None


# --------------------------------------------------------------------------- #
# La commande
# --------------------------------------------------------------------------- #


async def test_a_numero_affiche_une_seule_question_apres_le_reglement_qui_le_dit(commerce):
    """Lot 4 (M38, M39, D49) : la relecture ne porte plus le numéro ; la fin est relecture, règlement, puis UNE question qui dit le numéro gardé
    (réglable) ; C7 (lot 19 bis) : son « oui » est la réponse à cette question, puis la fiche enregistre."""
    from api.services.commande import moteur

    a = await Appel(commerce, vente_en_plus=False).pret()
    r = await a.jusqu_a_la_relecture()
    assert r.suggestion == "" and a.p["relecture"]["motif_du_total"] == "total_relecture"  # C6 (décision d'Evan 25/11 9 h 30) : le modèle relit, le code dit le total et la question
    assert (await a.finaliser(confirmer=True, prenom="Alice")).manque == "paiement"
    r = await a.finaliser(moyen="carte", prenom="Alice")
    assert r.manque == "confirmer_numero" and r.suggestion == "", r.suggestion  # C6 n° 10 (décision d'Evan 25/11 9 h 30) : le modèle propose le numéro qui s'affiche, le code ne dit rien
    moteur.repondre_au_numero_affiche(a.p, "accepte", a.appelant)
    r = await a.finaliser(confirmer=True, prenom="Alice", moyen="carte")
    assert r.statut == "ENREGISTREE"
    assert (await a.commandes())[0]["telephone"] == TEL


# Les tests b, c, d : DC10 (Evan, 22/11) tranche l'écart du nettoyeur (passage 2) : le numéro dicté est relu par paires avant l'enregistrement
# (motif « numero_dicte_relu », allumé par défaut) et attend son « oui », donné par la réponse à la question (comme le numéro qui s'affiche, C7).


async def test_b_numero_dicte_une_fois_relu_une_fois_par_le_code(commerce):
    from api.services.commande import moteur

    a = await Appel(commerce, affiche=None, vente_en_plus=False).pret()
    await a.jusqu_a_la_relecture()
    assert (await a.finaliser(confirmer=True, prenom="Alice", moyen="carte")).manque == "telephone"
    r = await a.finaliser(telephone="0610203040", prenom="Alice", moyen="carte")
    assert r.manque == "confirmer_numero_dicte" and r.suggestion == f"Je note le {DIT_2569}, c'est bon ?", r.suggestion
    assert (await a.finaliser(confirmer=True, prenom="Alice", moyen="carte")).manque == "confirmer_numero_dicte"  # un « confirmer » ne vaut pas son « oui »
    moteur.repondre_au_numero_dicte(a.p, "accepte")
    assert (await a.finaliser(confirmer=True, prenom="Alice", moyen="carte")).statut == "ENREGISTREE"


async def test_c_numero_dicte_puis_corrige_seul_le_nouveau_est_relu_et_un_oui_ne_passe_pas_sans_relecture(commerce):
    a = await Appel(commerce, affiche=None, vente_en_plus=False).pret()
    await a.jusqu_a_la_relecture()
    await a.finaliser(confirmer=True, prenom="Alice", moyen="carte")
    await a.finaliser(telephone="0610203040", prenom="Alice", moyen="carte")
    r = await a.finaliser(telephone="0610203041", prenom="Alice", moyen="carte")
    assert r.suggestion == f"Je note le {numero_en_lettres('+33610203041')}, c'est bon ?", r.suggestion


async def test_d_numero_affiche_puis_un_autre_dit_relu_par_paires_sans_reposer_la_question(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret()
    await a.jusqu_a_la_relecture()
    await a.finaliser(confirmer=True, prenom="Alice")
    r = await a.finaliser(moyen="carte", prenom="Alice")
    assert r.manque == "confirmer_numero" and r.suggestion == ""  # C6 n° 10 (décision d'Evan 25/11 9 h 30) : le numéro qui s'affiche est proposé par le modèle
    r = await a.finaliser(telephone="zéro six, quatre-vingt-dix-huit, soixante-seize, cinquante-quatre, trente-deux", prenom="Alice", moyen="carte")
    dit = numero_en_lettres("+33698765432")
    assert r.manque == "confirmer_numero_dicte" and r.suggestion == f"Je note le {dit}, c'est bon ?" and QUESTION not in r.suggestion, r.suggestion


# test_e_second_numero_avec_le_numero_affiche_une_seule_question : supprimé au lot 4 (D49), rendu au lot 8 (PE-1, Q7-3 : la case est revenue) sur la porte : ``partie_1/test_p1f_lot8_pe_second_numero.py``


async def test_f_la_phrase_reglee_remplace_le_texte_par_defaut(commerce):
    reglee = question_du_numero_affiche(SimpleNamespace(configurations={"phrases_regles": [_regle()]}))
    assert reglee == "Je garde ce numéro pour vous joindre, ça vous va ?"
    a = await Appel(commerce, vente_en_plus=False).pret()
    await a.jusqu_a_la_relecture()
    await a.finaliser(confirmer=True, prenom="Alice")
    r = await a.finaliser(moyen="carte", prenom="Alice")
    assert r.manque == "confirmer_numero" and r.suggestion == ""  # C6 n° 10 (décision d'Evan 25/11 9 h 30) : le numéro qui s'affiche est proposé par le modèle ; le réglage ne vaut plus que pour la relecture de la réservation


@pytest.mark.xfail(strict=True, reason="À trancher (a-trancher.md, nettoyeur passage 2) : la règle de phrase du numéro éteinte ne supprime plus la question (``moteur.py`` retombe sur « Je note le numéro qui s'affiche, c'est bon ? »)")
async def test_f_eteinte_la_question_du_numero_n_est_pas_posee(commerce):
    eteinte = question_du_numero_affiche(SimpleNamespace(configurations={"phrases_regles": [_regle(active=False, variantes=[])]}))
    assert eteinte is None
    b = await Appel(commerce, vente_en_plus=False).pret()
    await b.jusqu_a_la_relecture()
    await b.finaliser(confirmer=True, prenom="Alice")
    r = await b.finaliser(moyen="carte", prenom="Alice")
    assert r.manque != "confirmer_numero" and QUESTION not in r.suggestion


# --------------------------------------------------------------------------- #
# La réservation
# --------------------------------------------------------------------------- #


async def test_reservation_numero_affiche_une_question_et_dicte_relu_une_fois(salle):
    from api.tests.mark.test_restauration_reservation import TEL as TEL_RESA
    from api.tests.mark.test_restauration_reservation_outils import Appel as AppelResa

    base = {"jour": "samedi", "heure": "20h", "personnes": 2, "prenom": "Alice"}
    a = AppelResa(salle)
    from types import SimpleNamespace

    from api.services.phrases.catalogue import MOTIFS, NUMERO_DICTE_RELU
    from api.services.reservation.porte import question_du_code

    # C6 n° 8 (décision d'Evan 25/11 9 h 30 ; Q2 = A) : la relecture est dite par le modèle ; la porte dit après elle la question réglée du numéro, seule question, à la fin
    ctx = SimpleNamespace()
    r = await a.reserver(**base)
    assert r.manque == "relecture" and not r.suggestion and question_du_code(ctx, r) == QUESTION, r
    assert r.faits["numero_affiche_dit"] == numero_en_lettres(TEL_RESA)
    r = await a.reserver(telephone="0698765432")  # « non, plutôt le 06… »
    relu = MOTIFS[NUMERO_DICTE_RELU].variantes_defaut[0].replace("{numero}", numero_en_lettres("+33698765432"))
    assert question_du_code(ctx, r) == relu and QUESTION not in relu, r
    assert "numero_affiche_dit" not in r.faits
    assert (await a.reserver(confirmer=True)).statut == "ENREGISTREE"

    d = AppelResa(salle, affiche=None)
    r = await d.reserver(**base, telephone="0610203040")
    assert question_du_code(ctx, r).count(DIT_2569) == 1 and r.faits["numero_retenu_dit"] == DIT_2569, r
