"""[.mark] Lot 8 de correctifs-apres-banc-commun : annuler un rendez-vous (K16, D-1), côté fork.

Un outil d'annulation est une action comme chercher et réserver (outil HTTP du catalogue, nom et description en
données). Le fork lui donne : le champ de la fiche qu'il défait (``annule_par_outil``), l'issue RÉELLE dite au modèle
(annulé, échec, non confirmé), et le droit de passer toujours (ni garde de réservation ni réservation identique).

| Test | Preuve |
|---|---|
| succès | la fiche passe ``rendez_vous`` à ce que le service dit (« annulé ») ; le modèle lit ``issue = annule`` |
| échec | rien n'est écrit, le modèle lit ``issue = echec`` et « elle n'a PAS eu lieu » |
| sans confirmation | jamais la première valeur permise (celle de la réservation) : rien écrit, ``non_confirme`` |
| résultat emballé | la réponse HTTP emballée (``data``) est lue, un résultat texte reste un texte |
| règle de l'humain | l'annulation d'une date que la recherche n'a pas donnée passe ; deux annulations identiques s'exécutent ; on peut reprendre le même créneau après |
| répliques | « c'est annulé » est retenu si l'annulation a échoué ou n'a pas été faite, passe si elle a réussi ; sans outil d'annulation déclaré : comme avant |
| données | ``annule_par_outil`` : nom lisible, vide = éteint, aller-retour ; l'empreinte du lot 6 ignore le champ qu'elle écrit |
"""

from __future__ import annotations

import pytest

from api.schemas.fiche_agent import ChampFiche
from api.services.workflow.enveloppe_des_actions import (
    CONSIGNE_ANNULATION,
    ISSUE_ANNULE,
    ISSUE_ECHEC,
    ISSUE_NON_CONFIRME,
    avec_l_issue_d_annulation,
    envelopper_l_action,
)
from api.services.workflow.fiche_au_fil_de_leau import ReglagesFiche
from api.services.workflow.verite_des_actions import VerificateurDeReplique

from types import SimpleNamespace

RESERVER = "reserver"
CHERCHER = "chercher"
ANNULER = "annuler"
TROUVEES = {"creneaux": ["2026-11-03T10:00:00+01:00", "2026-11-05T14:00:00+01:00"]}
RESERVEE = {"statut": "confirme", "rendez_vous": "confirme", "debut": "2026-11-05T14:00:00+01:00"}


def _reglages(annule=ANNULER):
    return ReglagesFiche(
        champs=(
            ChampFiche(nom="nom", origine="dicte"),
            ChampFiche(
                nom="rendez_vous",
                origine="deduit",
                valeurs=["confirme", "a_rappeler", "annule"],
                rempli_par_outil=RESERVER,
                annule_par_outil=annule,
            ),
        )
    )


class Banc:
    """Un moteur, une étape, trois actions enveloppées par la vraie enveloppe (écriture dans la fiche comprise)."""

    def __init__(self, annule=ANNULER):
        self.fiche = {}
        self.moteur = SimpleNamespace(_fiche=_reglages(annule), _gathered_context=self.fiche)
        self.agent = SimpleNamespace(current_node=SimpleNamespace(verite_des_actions=None, champs_etape=()))
        self.executions = {CHERCHER: [], RESERVER: [], ANNULER: []}
        self.reponses = {CHERCHER: TROUVEES, RESERVER: RESERVEE, ANNULER: {"statut": "annule"}}
        self.enveloppes = {nom: self._envelopper(nom) for nom in self.executions}

    def _envelopper(self, nom):
        async def action(params):
            self.executions[nom].append(dict(params.arguments))
            await params.result_callback(self.reponses[nom])

        return envelopper_l_action(self.moteur, nom, action, self.agent)

    async def appeler(self, outil, /, **arguments):
        rendus = []

        async def rendre(resultat, **_):
            rendus.append(resultat)

        await self.enveloppes[outil](SimpleNamespace(result_callback=rendre, arguments=arguments))
        assert len(rendus) == 1
        return rendus[0]

    async def reserver(self):
        await self.appeler(CHERCHER, jour="semaine du 3 novembre")
        return await self.appeler(RESERVER, debut="2026-11-05T14:00:00+01:00", nom="Durand")


async def test_une_annulation_reussie_ecrit_la_fiche_et_dit_son_issue():
    banc = Banc()
    await banc.reserver()
    assert banc.fiche["rendez_vous"] == "confirme"
    rendu = await banc.appeler(ANNULER, nom="Durand")
    assert banc.fiche["rendez_vous"] == "annule"
    assert rendu["issue"] == ISSUE_ANNULE and rendu["consigne"] == CONSIGNE_ANNULATION[ISSUE_ANNULE]
    assert rendu["statut"] == "annule"  # le résultat du service est gardé tel quel


async def test_une_annulation_en_echec_n_ecrit_rien_et_le_modele_lit_qu_elle_n_a_pas_eu_lieu():
    banc = Banc()
    await banc.reserver()
    banc.reponses[ANNULER] = {"statut": "echec", "error": "agenda injoignable"}
    rendu = await banc.appeler(ANNULER, nom="Durand")
    assert banc.fiche["rendez_vous"] == "confirme"
    assert rendu["issue"] == ISSUE_ECHEC and "PAS eu lieu" in rendu["consigne"]
    assert rendu["error"] == "agenda injoignable"


async def test_une_annulation_sans_confirmation_n_ecrit_jamais_la_premiere_valeur_permise():
    """La première valeur permise est celle de la réservation (« confirme ») : l'annulation ne la prend jamais."""
    banc = Banc()
    await banc.reserver()
    banc.fiche["rendez_vous"] = "a_rappeler"
    banc.reponses[ANNULER] = {"accuse": "recu"}
    rendu = await banc.appeler(ANNULER, nom="Durand")
    assert banc.fiche["rendez_vous"] == "a_rappeler"
    assert rendu["issue"] == ISSUE_NON_CONFIRME and "pas confirmé" in rendu["consigne"].replace("n'a pas confirmé", "pas confirmé")


async def test_la_reponse_http_emballee_est_lue_et_un_resultat_texte_reste_un_texte():
    import json

    banc = Banc()
    await banc.reserver()
    banc.reponses[ANNULER] = json.dumps({"status": "success", "status_code": 200, "data": {"statut": "annule"}})
    rendu = await banc.appeler(ANNULER, nom="Durand")
    assert banc.fiche["rendez_vous"] == "annule"
    assert isinstance(rendu, str) and json.loads(rendu)["issue"] == ISSUE_ANNULE
    assert json.loads(rendu)["data"] == {"statut": "annule"}


def test_un_resultat_qui_n_est_pas_un_dictionnaire_est_emballe_sans_rien_perdre():
    assert avec_l_issue_d_annulation("fait", ["rendez_vous"])["resultat"] == "fait"
    assert avec_l_issue_d_annulation(None, [])["issue"] == ISSUE_NON_CONFIRME


async def test_un_autre_outil_n_ecrit_pas_le_champ_et_sans_champ_declare_rien_ne_change():
    banc = Banc()
    banc.reponses[CHERCHER] = {**TROUVEES, "statut": "annule"}
    rendu = await banc.appeler(CHERCHER, jour="x")
    assert "rendez_vous" not in banc.fiche and "issue" not in rendu
    sans = Banc(annule=None)
    await sans.reserver()
    rendu = await sans.appeler(ANNULER, nom="Durand")
    assert sans.fiche["rendez_vous"] == "confirme" and "issue" not in rendu


# --------------------------------------------------------------------------- #
# Règle de l'humain : l'appelant peut toujours annuler, puis reprendre
# --------------------------------------------------------------------------- #


async def test_l_annulation_d_une_date_que_la_recherche_n_a_pas_donnee_passe():
    """La garde de réservation retient une RÉSERVATION ; une annulation (rendez-vous pris un autre jour) passe."""
    banc = Banc()
    await banc.reserver()
    rendu = await banc.appeler(ANNULER, debut="2026-12-18T10:00:00+01:00", nom="Durand")
    assert rendu.get("statut") != "incomplet" and banc.executions[ANNULER] == [
        {"debut": "2026-12-18T10:00:00+01:00", "nom": "Durand"}
    ]


async def test_deux_annulations_identiques_s_executent_toutes_les_deux():
    banc = Banc()
    await banc.reserver()
    await banc.appeler(ANNULER, nom="Durand")
    await banc.appeler(ANNULER, nom="Durand")
    assert len(banc.executions[ANNULER]) == 2


async def test_apres_une_annulation_qui_cite_une_date_le_meme_creneau_se_reserve_a_nouveau():
    """Le résultat d'une annulation cite la date du rendez-vous : il ne suffisait pas qu'elle « n'ait pas de date »."""
    banc = Banc()
    await banc.reserver()
    banc.reponses[ANNULER] = {"accuse": "ok", "debut": "2026-11-05T14:00:00+01:00"}  # n'écrit aucun champ
    await banc.appeler(ANNULER, nom="Durand")
    banc.fiche["rendez_vous"] = "confirme"  # rien ne l'a changé : seule l'annulation défait la réservation connue
    await banc.appeler(RESERVER, debut="2026-11-05T14:00:00+01:00", nom="Durand")
    assert len(banc.executions[RESERVER]) == 2


async def test_une_annulation_echouee_ne_defait_pas_la_reservation_connue():
    banc = Banc()
    await banc.reserver()
    banc.reponses[ANNULER] = {"statut": "echec"}
    await banc.appeler(ANNULER, nom="Durand")
    rendu = await banc.appeler(RESERVER, debut="2026-11-05T14:00:00+01:00", nom="Durand")
    assert rendu.get("deja_confirme") is True and len(banc.executions[RESERVER]) == 1


# --------------------------------------------------------------------------- #
# Les répliques : « c'est annulé » seulement si l'outil l'a fait
# --------------------------------------------------------------------------- #


async def test_c_est_annule_n_est_dit_que_si_l_annulation_a_reussi():
    banc = Banc()
    await banc.reserver()
    verif = VerificateurDeReplique(banc.moteur, banc.agent)
    # Jamais appelée : le rendez-vous est réservé, pas annulé.
    retenue = verif.controler("C'est bon, votre rendez-vous est annulé.")
    assert retenue is not None and "PAS eu lieu" in retenue.consigne
    banc.reponses[ANNULER] = {"statut": "echec"}
    await banc.appeler(ANNULER, nom="Durand")
    assert verif.controler("Votre rendez-vous est bien annulé.") is not None
    banc.reponses[ANNULER] = {"statut": "annule"}
    await banc.appeler(ANNULER, nom="Durand")
    assert verif.controler("Votre rendez-vous est bien annulé.") is None


async def test_sans_outil_d_annulation_declare_la_regle_d_avant_ne_change_pas():
    banc = Banc(annule=None)
    await banc.reserver()
    verif = VerificateurDeReplique(banc.moteur, banc.agent)
    assert verif.controler("Votre rendez-vous est annulé.") is None  # une action a réussi : comme avant


# --------------------------------------------------------------------------- #
# Les données
# --------------------------------------------------------------------------- #


def test_annule_par_outil_est_un_nom_lisible_vide_ou_absent_il_est_eteint():
    assert ChampFiche(nom="a").annule_par_outil is None
    assert ChampFiche(nom="a", annule_par_outil="  ").annule_par_outil is None
    assert ChampFiche(nom="a", annule_par_outil=" annuler_rdv ").annule_par_outil == "annuler_rdv"
    with pytest.raises(ValueError):
        ChampFiche(nom="a", annule_par_outil="annuler le rendez-vous")
    champ = ChampFiche(nom="a", annule_par_outil="annuler_rdv")
    assert ChampFiche.model_validate(champ.model_dump()).annule_par_outil == "annuler_rdv"


async def test_l_empreinte_du_declenchement_ignore_le_champ_que_l_annulation_ecrit():
    from api.services.workflow.declenchement_de_l_action import empreinte

    banc = Banc(annule=ANNULER)
    banc.moteur._fiche = ReglagesFiche(
        champs=(
            ChampFiche(nom="nom", origine="dicte"),
            ChampFiche(nom="rendez_vous", origine="deduit", valeurs=["a", "annule"], annule_par_outil=ANNULER),
        )
    )
    noeud = SimpleNamespace(champs_etape=("nom", "rendez_vous"))
    banc.fiche["nom"] = "Durand"
    avant = empreinte(banc.moteur, noeud)
    banc.fiche["rendez_vous"] = "annule"
    assert empreinte(banc.moteur, noeud) == avant
