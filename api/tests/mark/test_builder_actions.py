"""[.mark] builder-agent-vocal, lots 1 et 2 : les actions (fiche, réglages .mark B33, lexique B41, bibliothèque).

Ce qui doit tenir : une ligne de fiche sans source n'entre pas, le builder ne valide pas la fiche ; les phrases du
code ne prennent QUE les motifs du catalogue (jamais un nouveau) et se rangent dans le brouillon ; un réglage sale
(clé secrète, valeur refusée par l'enregistrement de l'écran) est refusé ; le lexique vient de la fiche VALIDÉE et
n'écrase rien ; le builder lit, applique, crée des candidats et propose, mais ne touche pas une recette.
"""

from __future__ import annotations

import pytest

from api.schemas.lexique_metier import LexiqueMetier
from api.services.builder import contexte, fiche
from api.services.builder.actions.registre import Contexte, executer
from api.services.builder.bibliotheque import propositions, service
from api.services.builder.bibliotheque.modele import Banc, Statut
from api.services.lexique import stockage as lexique
from api.services.phrases.catalogue import MOTIFS
from api.tests.mark.builder_commun import AGENT, ORG_CLIENT, utilisateur

EQUIPE = Contexte(user=utilisateur(1), workflow_id=AGENT)
CLIENT = Contexte(user=utilisateur(2), workflow_id=AGENT)  # pas de l'organisation .mark
MOTIF = next(iter(MOTIFS))


def regle(texte="Un instant, je regarde.", motif=MOTIF, portee="agent"):
    return {"motif": motif, "portee": portee, "variantes": [texte]}


# --- la fiche ----------------------------------------------------------------------------------------------------------


async def test_une_ligne_sans_source_n_entre_pas_dans_la_fiche(monde):
    sans_source = await executer("fiche_ecrire", {"champs": {"horaires": {"valeur": "9h-18h"}}}, EQUIPE)
    vide = await executer("fiche_ecrire", {"champs": {"horaires": {"valeur": "9h-18h", "source": ""}}}, EQUIPE)
    assert sans_source["ok"] is False and vide["ok"] is False
    assert (await fiche.lire(ORG_CLIENT, AGENT)).champs == {}


async def test_un_trou_est_une_question_qui_se_ferme_quand_une_ligne_sourcee_le_comble(monde):
    resultat = await executer(
        "fiche_ecrire",
        {
            "champs": {"adresse": {"valeur": "1 rue X", "source": "audit.pdf p.1"}},
            "trous": [{"champ": "horaires", "question": "Quels horaires ?", "reponse_suggeree": "9h-18h"}],
        },
        EQUIPE,
    )
    assert resultat["trous_ouverts"] == ["horaires"] and resultat["carte"]["type"] == "fiche"
    comble = await executer("fiche_ecrire", {"champs": {"horaires": {"valeur": "9h-17h", "source": "site, page contact"}}}, EQUIPE)
    assert comble["trous_ouverts"] == []


async def test_le_builder_ne_valide_pas_la_fiche_et_une_personne_ne_le_peut_qu_sans_trou(monde):
    await executer("fiche_ecrire", {"champs": {"a": {"valeur": 1, "source": "s"}}, "trous": [{"champ": "b", "question": "Quoi ?"}]}, EQUIPE)
    assert (await fiche.lire(ORG_CLIENT, AGENT)).validee is False
    with pytest.raises(fiche.ErreurFiche):
        await fiche.valider(ORG_CLIENT, AGENT, "evan")
    await executer("fiche_ecrire", {"champs": {"b": {"valeur": 2, "source": "s"}}}, EQUIPE)
    assert (await fiche.valider(ORG_CLIENT, AGENT, "evan")).validee is True
    # Modifier une ligne retire la validation : il faut la redonner.
    await executer("fiche_ecrire", {"champs": {"b": {"valeur": 3, "source": "s"}}}, EQUIPE)
    assert (await fiche.lire(ORG_CLIENT, AGENT)).validee is False


# --- B33 : les phrases du code et les réglages .mark ---------------------------------------------------------------------


async def test_le_catalogue_des_motifs_est_celui_du_code(monde):
    resultat = await executer("phrases_catalogue", {}, EQUIPE)
    assert {m["id"] for m in resultat["motifs"]} == set(MOTIFS)


async def test_les_phrases_du_code_se_rangent_dans_le_brouillon_et_un_motif_inconnu_est_refuse(monde):
    refus = await executer("phrases_regler", {"regles": [regle(motif="motif_invente")]}, EQUIPE)
    assert refus["ok"] is False and "unknown cause" in refus["erreur"] and not monde.ecritures_de_reglages
    ok = await executer("phrases_regler", {"regles": [regle()]}, EQUIPE)
    assert ok["ok"] is True
    ecrit = monde.ecritures_de_reglages[-1]["configurations"]["phrases_regles"]
    assert ecrit[0]["motif"] == MOTIF and ecrit[0]["variantes"] == ["Un instant, je regarde."]
    assert monde.workflows[AGENT].released_definition.version_number == 1  # brouillon seulement
    # Une règle de même motif et même portée REMPLACE l'ancienne ; une autre portée s'ajoute.
    await executer("phrases_regler", {"regles": [regle("Je vérifie."), regle("Pour tout le groupe.", portee="groupe")]}, EQUIPE)
    regles = monde.ecritures_de_reglages[-1]["configurations"]["phrases_regles"]
    assert sorted(r["variantes"][0] for r in regles) == ["Je vérifie.", "Pour tout le groupe."]


async def test_phrases_regler_exige_des_regles_ou_un_element_pas_les_deux(monde):
    assert (await executer("phrases_regler", {}, EQUIPE))["ok"] is False
    assert (await executer("phrases_regler", {"regles": [regle()], "depuis": "x"}, EQUIPE))["ok"] is False


async def test_les_reglages_mark_passent_par_les_validateurs_de_l_ecran_et_refusent_les_secrets(monde):
    ok = await executer("reglages_regler", {"valeurs": {"relecture_des_numeros": True}}, EQUIPE)
    assert ok["ok"] is True and monde.ecritures_de_reglages[-1]["configurations"]["relecture_des_numeros"] is True
    lu = await executer("reglages_lire", {"cles": ["relecture_des_numeros"]}, EQUIPE)
    assert lu["reglages"] == {"relecture_des_numeros": True}
    avant = len(monde.ecritures_de_reglages)
    for valeurs in ({"cle_inconnue": 1}, {"max_call_duration": -5}, {"elevenlabs_api_key": "sk-x"}):
        refus = await executer("reglages_regler", {"valeurs": valeurs}, EQUIPE)
        assert refus["ok"] is False, valeurs
    assert len(monde.ecritures_de_reglages) == avant


# --- B41 : le lexique vient de la fiche validée ---------------------------------------------------------------------------


async def preparer_la_fiche(termes, valider=True):
    await fiche.ecrire(ORG_CLIENT, AGENT, {"lexique": fiche.ChampFiche(valeur=termes, source="audit.pdf p.4")})
    if valider:
        await fiche.valider(ORG_CLIENT, AGENT, "evan")


async def test_le_lexique_se_remplit_depuis_la_fiche_validee_sans_ecraser_l_existant(monde):
    await lexique.enregistrer_lexique(ORG_CLIENT, LexiqueMetier.model_validate({"termes": [{"terme": "Alpha", "prononciation": "alfa", "propose": True}]}))
    await preparer_la_fiche(["Alpha", {"terme": "Beta", "variantes": ["Bêta"]}, "Gamma"])
    resultat = await executer("lexique_remplir_depuis_fiche", {}, EQUIPE)
    assert (resultat["ajoutes"], resultat["deja_presents"]) == (2, 1)
    termes = {t.terme: t for t in (await lexique.lire_lexique_strict(ORG_CLIENT)).termes}
    assert set(termes) == {"Alpha", "Beta", "Gamma"}
    assert termes["Alpha"].prononciation == "alfa" and termes["Alpha"].a_ecouter is False  # l'existant n'a pas bougé
    assert termes["Beta"].a_ecouter is True and termes["Gamma"].a_ecouter is True  # mots-clés de la reconnaissance
    again = await executer("lexique_remplir_depuis_fiche", {}, EQUIPE)
    assert again["ajoutes"] == 0


async def test_le_lexique_exige_une_fiche_validee_avec_une_ligne_lexique(monde):
    await preparer_la_fiche(["Alpha"], valider=False)
    assert (await executer("lexique_remplir_depuis_fiche", {}, EQUIPE))["ok"] is False
    await fiche.valider(ORG_CLIENT, AGENT, "evan")
    assert (await executer("lexique_remplir_depuis_fiche", {}, EQUIPE))["ok"] is True
    await fiche.ecrire(ORG_CLIENT, AGENT, {"autre": fiche.ChampFiche(valeur=1, source="s")})  # ligne changée : validation retirée
    assert (await executer("lexique_remplir_depuis_fiche", {}, EQUIPE))["ok"] is False


# --- la bibliothèque ---------------------------------------------------------------------------------------------------


async def test_lire_un_candidat_le_signale_et_une_famille_se_liste(monde):
    await service.creer("moules-etape", "q", "Q", {"texte": "t"}, "alice")
    familles = await executer("bibliotheque_lister", {}, CLIENT)
    assert len(familles["familles"]) >= 30 and {"phrases-du-code", "lexiques", "methode-builder"} <= {f["slug"] for f in familles["familles"]}
    lu = await executer("bibliotheque_lire", {"famille": "moules-etape", "slug": "q"}, CLIENT)  # lue par une autre organisation
    assert lu["statut"] == "candidat" and "not proven" in lu["avertissement"] and lu["contenu"] == {"texte": "t"}
    assert (await executer("bibliotheque_lire", {"famille": "moules-etape", "slug": "absent"}, CLIENT))["ok"] is False


async def test_appliquer_des_phrases_du_code_depuis_la_bibliotheque_ecrit_et_compte_l_usage(monde):
    await service.creer("phrases-du-code", "attente", "Attente", {"regles": [regle("Un instant.")]}, "alice")
    resultat = await executer("bibliotheque_appliquer", {"famille": "phrases-du-code", "slug": "attente"}, EQUIPE)
    assert resultat["ok"] and resultat["applique"] and resultat["statut"] == "candidat"
    assert monde.ecritures_de_reglages[-1]["configurations"]["phrases_regles"][0]["variantes"] == ["Un instant."]
    assert (await service.utilisation("phrases-du-code", "attente"))[0]["agent"] == AGENT
    # Le même chemin par phrases_regler(depuis=...).
    via = await executer("phrases_regler", {"depuis": "attente"}, EQUIPE)
    assert via["ok"] and len(monde.ecritures_de_reglages) == 2
    # Un candidat utilisé est noté sur l'agent : « contient des candidats ».
    assert (await contexte.lire_contexte_agent(ORG_CLIENT, AGENT))["candidats"] == [{"famille": "phrases-du-code", "slug": "attente", "version": 1}]
    assert "contient des candidats" in (await contexte.etat_du_disque(ORG_CLIENT, AGENT))


async def test_appliquer_un_modele_de_reglages_et_un_lexique_de_la_bibliotheque(monde):
    await service.creer("modeles-reglages", "base", "Base", {"valeurs": {"relecture_des_numeros": True}}, "alice")
    await service.marquer("modeles-reglages", "base", 1, Statut.RECETTE, "alice", banc=Banc(description="banc"))
    resultat = await executer("bibliotheque_appliquer", {"famille": "modeles-reglages", "slug": "base"}, EQUIPE)
    assert resultat["statut"] == "recette" and monde.ecritures_de_reglages[-1]["configurations"]["relecture_des_numeros"] is True
    assert "candidats" not in await contexte.lire_contexte_agent(ORG_CLIENT, AGENT) or not (await contexte.lire_contexte_agent(ORG_CLIENT, AGENT))["candidats"]
    await service.creer("lexiques", "commun", "Commun", {"termes": [{"terme": "Delta"}]}, "alice")
    lex = await executer("bibliotheque_appliquer", {"famille": "lexiques", "slug": "commun"}, EQUIPE)
    assert lex["ecrit"]["ajoutes"] == 1
    assert [t.terme for t in (await lexique.lire_lexique_strict(ORG_CLIENT)).termes] == ["Delta"]


async def test_les_familles_qui_se_construisent_rendent_leur_contenu_au_builder(monde):
    await service.creer("moules-etape", "q", "Q", {"texte": "Moule"}, "alice")
    resultat = await executer("bibliotheque_appliquer", {"famille": "moules-etape", "slug": "q"}, EQUIPE)
    assert resultat["applique"] is False and resultat["contenu"] == {"texte": "Moule"} and not monde.ecritures_de_reglages
    assert (await service.utilisation("moules-etape", "q"))[0]["version"] == 1


async def test_un_element_rejete_ne_s_applique_pas(monde):
    await service.creer("phrases-du-code", "vieux", "Vieux", {"regles": [regle()]}, "alice")
    await service.marquer("phrases-du-code", "vieux", 1, Statut.REJETE, "alice", raison="trop long")
    resultat = await executer("bibliotheque_appliquer", {"famille": "phrases-du-code", "slug": "vieux"}, EQUIPE)
    assert resultat["ok"] is False and "trop long" in resultat["erreur"] and not monde.ecritures_de_reglages


async def test_le_builder_cree_des_candidats_et_propose_mais_ne_touche_pas_une_recette(monde):
    cree = await executer("bibliotheque_ecrire_candidat", {"famille": "moules-etape", "slug": "n", "titre": "N", "contenu": {"t": 1}}, EQUIPE)
    assert cree["ok"] and cree["statut"] == "candidat"
    element = await service.lire_element("moules-etape", "n")
    assert element.courante.auteur.startswith("builder pour ")
    await service.marquer("moules-etape", "n", 1, Statut.RECETTE, "alice", banc=Banc(description="banc"))
    refus = await executer("bibliotheque_ecrire_candidat", {"famille": "moules-etape", "slug": "n", "titre": "N", "contenu": {"t": 2}}, EQUIPE)
    assert refus["ok"] is False and (await service.lire_element("moules-etape", "n")).courante.contenu == {"t": 1}
    proposition = await executer(
        "bibliotheque_proposer", {"type": "version", "famille": "moules-etape", "slug": "n", "justification": "Plus court", "contenu": {"t": 2}}, EQUIPE
    )
    assert proposition["ok"] and proposition["carte"]["type"] == "proposition"
    assert [p.id for p in await propositions.lister()] == [proposition["proposition"]]
    assert (await service.lire_element("moules-etape", "n")).courante.contenu == {"t": 1}  # il a proposé, rien n'est écrit


async def test_l_ecriture_du_builder_est_reservee_aux_membres_de_l_equipe_mark(monde):
    for nom, args in (
        ("bibliotheque_ecrire_candidat", {"famille": "moules-etape", "slug": "n", "titre": "N", "contenu": {}}),
        ("bibliotheque_proposer", {"type": "version", "famille": "moules-etape", "slug": "n", "justification": "x", "contenu": {"t": 1}}),
    ):
        resultat = await executer(nom, args, CLIENT)
        assert resultat["ok"] is False and resultat["code"] == "bibliotheque_403", nom
    assert await service.lister() == [] and await propositions.lister() == []


async def test_les_contextes_de_l_agent_sont_lus_et_ecrits(monde):
    await executer("contexte_ecrire", {"notes": "Ouvert le lundi."}, EQUIPE)
    assert (await executer("contexte_lire", {}, EQUIPE))["notes"] == "Ouvert le lundi."
    await contexte.ecrire_preferences(1, "Réponses courtes.")
    assert await contexte.preferences(1) == "Réponses courtes." and await contexte.preferences(2) == ""
