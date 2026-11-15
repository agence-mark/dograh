"""[.mark] Module Restauration, lot 24, étape 3 : le chiffre sans source et le fait avant le résultat (W15), deux signes de plus de la vérité des actions.

Par le vrai flux du cerveau (``RepriseSansFluxMixin``, ``RepliqueVerifiee``) comme les tests de la vérité des actions.

| Test | Ce qu'il prouve |
|---|---|
| lecture | montants et heures lus en chiffres et en toutes lettres (« treize euros quarante et un », « à vingt heures et quart », « 20h30 », ISO) ; « dans deux heures » n'est pas une heure |
| éteint par défaut | sans la clé, un chiffre inventé passe comme avant |
| chiffre sans source | un montant ou une heure qu'aucun résultat d'outil, aucune parole de la personne ne donne est retenu, le modèle relancé UNE fois avec la consigne |
| zéro déclenchement | sur un appel sain (ce que l'outil a rendu est redit en chiffres ou en lettres ; l'heure dite par l'appelant ; un résultat en centimes) : aucune retenue |
| avant l'outil | le texte dit avant un appel d'outil : un chiffre sans source ou « c'est enregistré » est retenu ; une phrase d'attente passe ; sans la clé, tel quel |
| rouge | chaque garde débranchée laisse passer le cas rouge connu |
"""

from __future__ import annotations

import json

from api.services.pipecat.reponse_avalee import ATTRIBUT_VERITE, RepliqueVerifiee
from api.services.workflow import chiffres_sans_source as c
from api.services.workflow.verite_des_actions import VerificateurDeReplique
from api.tests.mark.test_verite_des_actions import (  # noqa: F401
    Banc,
    _jouer,
    _morceau,
    _reponse,
    _service,
    _Service,
    _texte,
)


def test_lecture_des_montants_et_des_heures_en_chiffres_et_en_toutes_lettres():
    assert c.montants_dits("Cela fait treize euros quarante et un.") == {1341}
    assert c.montants_dits("12,90 € et 3 euros") == {1290, 300}
    assert c.montants_dits("douze euros cinquante") == {1250} and c.montants_dits("un euro") == {100} and c.montants_dits("cinq euros") == {500}
    assert c.montants_dits("Dans deux minutes, vers 20 h") == set() and c.montants_dits("quatre pizzas") == set()
    assert c.heures_dites("à 20 h 30") == {(20, 30)} and c.heures_dites("prête à 20h") == {(20, 0)}
    assert c.heures_dites("à vingt heures et quart") == {(20, 15)} and c.heures_dites("vers vingt et une heures trente") == {(21, 30)}
    assert c.heures_dites("pour dix-neuf heures et demie") == {(19, 30)} and c.heures_dites("2026-11-14T20:00:00+01:00") == {(20, 0)}
    assert c.heures_dites("dans deux heures") == set() and c.heures_dites("ça dure trois heures") == set()
    assert c.heures_dites(None) == set() and c.montants_dits({"total": 1341}) == set()


def test_sources_resultats_en_centimes_parole_de_la_personne_et_consigne():
    messages = [
        {"role": "system", "content": "La Reine coûte 12,90 €. Ouvert de 19 h à 22 h."},
        {"role": "user", "content": "Plutôt à vingt heures trente"},
        {"role": "tool", "content": json.dumps({"statut": "OK", "faits": {"total": 1341, "heure_voulue": "2026-11-14T20:15:00+01:00"}})},
        {"role": "assistant", "content": "Je dis un chiffre : 99 euros à 23 h"},     # une réplique de l'agent ne fonde rien
    ]
    s = c.sources_de(messages)
    assert 1290 in s.montants and 1341 in s.montants and 9900 not in s.montants
    assert {(19, 0), (22, 0), (20, 30), (20, 15)} <= s.heures and (23, 0) not in s.heures
    assert c.chiffres_sans_source("Cela fait 13,41 euros, à 20 h 15.", s) == []
    assert c.chiffres_sans_source("Cela fait 14 euros, à 21 h 45.", s) == ["14 euros", "21 h 45"]


async def test_eteint_par_defaut_un_chiffre_invente_passe_comme_avant():
    banc = Banc()
    service = _service([_morceau("Cela fait douze euros, à vingt heures."), _morceau(fin="stop")], banc, _reponse("jamais"))
    assert _texte(await _jouer(service)) == "Cela fait douze euros, à vingt heures." and service.requetes == []


async def test_un_chiffre_sans_source_est_retenu_et_le_modele_relance_une_fois():
    banc = Banc()
    banc.agent.reglages = {c.CLE_CHIFFRE_SANS_SOURCE: True}
    service = _service([_morceau("Cela fait douze euros quarante."), _morceau(fin="stop")], banc, _reponse("Je vérifie le total."))
    assert _texte(await _jouer(service)) == "Je vérifie le total."
    [requete] = service.requetes
    assert any("12 euros 40" in (m.get("content") or "") and "EXACT" in m["content"] for m in requete["messages"])
    # le contrôle nomme la raison
    verificateur = VerificateurDeReplique(banc.moteur, banc.agent)
    retenue = verificateur.controler("Votre commande sera prête à 20 h 45.", [])
    assert (retenue.raison, retenue.detail) == (c.RAISON_CHIFFRE, "20 h 45")


async def test_zero_declenchement_sur_un_appel_sain():
    banc = Banc()
    banc.agent.reglages = {c.CLE_CHIFFRE_SANS_SOURCE: True}
    verificateur = VerificateurDeReplique(banc.moteur, banc.agent)
    messages = [
        {"role": "user", "content": "Je voudrais une Reine à emporter pour vingt heures trente"},
        {"role": "tool", "content": json.dumps({"statut": "INCOMPLETE", "faits": {"total": 1290}, "suggestion": "Je vous relis : une Reine. Cela fait douze euros quatre-vingt-dix. C'est bon ?"})},
        {"role": "tool", "content": json.dumps({"statut": "ENREGISTREE", "faits": {"heure_annoncee": "2026-11-12T20:30:00+01:00", "total": 1290}})},
    ]
    sains = [
        "Je vous relis : une Reine. Cela fait douze euros quatre-vingt-dix. C'est bon ?",
        "Cela fait 12,90 euros.",
        "C'est noté, ce sera prêt à vingt heures trente.",
        "Parfait, je garde le numéro qui s'affiche. Dans deux minutes, c'est enregistré.",
        "Vous avez une pizza et une boisson.",           # une quantité de un n'est pas contrôlée ; deux ou plus l'est (test_restauration_quantites_sans_source)
        "Souhaitez-vous ajouter quelque chose ?",
    ]
    for texte in sains:
        assert verificateur.controler(texte, messages) is None, texte


async def test_le_texte_dit_avant_un_outil_un_chiffre_ou_un_fait_est_retenu_une_phrase_d_attente_passe():
    banc = Banc()
    banc.agent.reglages = {c.CLE_FAIT_AVANT_OUTIL: True}
    verificateur = VerificateurDeReplique(banc.moteur, banc.agent)
    assert verificateur.controler_avant_outil("Un instant, je regarde ça pour vous.", []) is None
    assert verificateur.controler_avant_outil("Je note.", []) is None
    r = verificateur.controler_avant_outil("Cela fait quatorze euros, je l'enregistre.", [])
    assert r.raison == c.RAISON_FAIT_AVANT and "14 euros" in r.detail
    r = verificateur.controler_avant_outil("C'est parfait, votre rendez-vous est bien pris.", [])
    assert r is not None and r.raison == c.RAISON_FAIT_AVANT
    # une question avant l'outil passe
    assert verificateur.controler_avant_outil("Votre rendez-vous est bien pris ?", []) is None
    # sans la clé : jamais
    eteint = Banc()
    assert VerificateurDeReplique(eteint.moteur, eteint.agent).controler_avant_outil("Cela fait quatorze euros.", []) is None


async def test_par_le_vrai_flux_un_fait_avant_l_outil_relance_une_fois_et_sans_la_cle_passe_tel_quel():
    banc = Banc()
    banc.agent.reglages = {c.CLE_FAIT_AVANT_OUTIL: True}
    flux = [_morceau("Cela fait quatorze euros, je l'enregistre."), _morceau(outil="enregistrer"), _morceau(fin="tool_calls")]

    def brancher(service):
        verificateur = VerificateurDeReplique(banc.moteur, banc.agent)
        setattr(service, ATTRIBUT_VERITE, verificateur)
        return service

    service = brancher(_Service(flux, reprise=_reponse("Je lance l'enregistrement.")))
    assert _texte(await _jouer(service)) == "Je lance l'enregistrement."
    [requete] = service.requetes
    assert any("avant d'en avoir le résultat" in (m.get("content") or "") for m in requete["messages"])
    # une phrase d'attente avant l'outil : le flux passe tel quel, dans son ordre
    attente = [_morceau("Un instant, je m'en occupe."), _morceau(outil="enregistrer"), _morceau(fin="tool_calls")]
    service = brancher(_Service(attente, reprise=_reponse("jamais")))
    assert await _jouer(service) == attente and service.requetes == []
    # sans la clé : tel quel
    sans = Banc()
    service = _Service(flux, reprise=_reponse("jamais"))
    setattr(service, ATTRIBUT_VERITE, VerificateurDeReplique(sans.moteur, sans.agent))
    assert await _jouer(service) == flux and service.requetes == []
    assert RepliqueVerifiee  # la classe qui porte le contrôle
