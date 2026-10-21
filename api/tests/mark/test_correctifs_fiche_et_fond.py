"""[.mark] Chantier correctifs-apres-banc-v4, lot 2 : refus, résultat du fond sans outil, lignes internes.

| Test | La garantie |
|---|---|
| refus par le greffier | le greffier écrit « refusé » sur un prénom, un mail ; la garde de l'étape le compte traité (6.3, run 1484) ; K4 révisé (21/10) : aussi sur une liste fermée et un numéro, sauf « obligatoire sans exception » |
| obligatoire sans exception | un champ qui porte la clé reste manquant refusé ; sans la clé, traité ; « Déjà connu » et « Encore attendu » suivent |
| outil du fond en échec | l'outil rend une erreur, le fond rend quand même un résultat : « Échec : rien n'a été fait. », trace `outil_en_echec`, règle de l'échec ; un fond qui dit « Échec » garde son texte (décision d'Evan 21/10) |
| fond sans outil | un fond qui a des outils et rend du texte sans en appeler un : résultat « Échec : rien n'a été fait. », trace `sans_outil`, texte gardé en trace, point d'appel du lot 4 appelé (6.4) |
| fond sans outils, fond qui appelle | rien ne change : « fait » (zéro perte) |
| lignes internes | une ligne qui commence par une étiquette du bloc n'est jamais dite, coupée en morceaux ou non ; une phrase normale avec « noté » reste (6.5) |
| étiquettes lues | la liste vient du code qui écrit le bloc : chaque ligne écrite par `etat_de_la_fiche` commence par l'une d'elles |
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from api.services.pipecat.texte_du_cerveau import FluxNettoye, sans_lignes_internes
from api.services.travail.agent import (
    STATUT_OUTIL_EN_ECHEC,
    STATUT_SANS_OUTIL,
    TravailDeLAgent,
    resultat_en_echec,
)
from api.services.travail.reglages import NOM_OUTIL
from api.services.travail.retour import TEXTE_SANS_OUTIL
from api.services.workflow.enveloppe_des_actions import garde_de_l_etape
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_MODE,
    MODE_GREFFIER,
    ReglagesFiche,
    etat_de_la_fiche,
    etiquettes_du_bloc,
)
from api.tests.mark.test_greffier import _Modele, _Montage
from api.tests.mark.test_texte_du_cerveau import _dit, _Flux, _m, _usage
from api.tests.mark.test_travail_de_fond import (  # noqa: F401 -- fixture
    DEMANDE,
    RESULTAT,
    PREFIXE_RESULTAT_DU_TRAVAIL,
    _appel_d_outil,
    _texte,
    appel,
    est_un_resultat_de_travail,
)

# --------------------------------------------------------------------------- #
# 6.3 : un refus est traité par la garde de l'étape
# --------------------------------------------------------------------------- #

CHAMPS = [
    {"nom": "prenom", "type": "string", "origine": "dicte", "description": "Prénom"},
    {"nom": "nom", "type": "string", "origine": "dicte", "description": "Nom"},
    {"nom": "email", "type": "string", "origine": "dicte", "description": "Adresse e-mail"},
    {"nom": "numero_dicte", "type": "string", "origine": "dicte", "chiffres": 10, "description": "Numéro"},
    {
        "nom": "urgence",
        "type": "string",
        "origine": "deduit",
        "valeurs": ["normal", "urgent"],
        "description": "Urgence",
    },
]
ETAPE = ("prenom", "nom", "email", "numero_dicte", "urgence")


def _config(champs=CHAMPS):
    return {
        "fiche_au_fil_de_leau": True,
        CLE_MODE: MODE_GREFFIER,
        "fiche_champs": champs,
        "fiche_deja_connu": True,
    }


def _garde(montage, champs_etape=ETAPE):
    moteur = SimpleNamespace(_fiche=montage.reglages, _gathered_context=montage.fiche)
    agent = SimpleNamespace(current_node=SimpleNamespace(champs_etape=champs_etape))
    return garde_de_l_etape(moteur, agent)


@pytest.mark.asyncio
async def test_le_prenom_refuse_est_traite_par_la_garde_de_l_etape():
    """Run 1484 : le prénom refusé deux fois, la garde rendait « incomplet : prenom » à chaque essai."""
    montage = _Montage(
        _Modele({"prenom": "refusé", "nom": "Petit", "numero_dicte": "0655443322"}, {"email": "refusé"}),
        _config(),
    )
    montage.messages = [{"role": "user", "content": "Petit, 06 55 44 33 22. Mon prénom, non."}]
    await montage.passe()
    assert montage.fiche["prenom"] == "refusé"
    # Avant le refus du mail et l'urgence : la garde ne demande que ce qui n'a pas de réponse.
    assert _garde(montage) == {"statut": "incomplet", "manque": ["email", "urgence"]}
    montage.messages.append({"role": "user", "content": "Pas de mail, non merci."})
    await montage.passe()
    assert montage.fiche["email"] == "refusé"
    assert _garde(montage) == {"statut": "incomplet", "manque": ["urgence"]}


@pytest.mark.asyncio
async def test_un_champ_sans_reponse_reste_manquant():
    """Le contrôle du test précédent : sans refus, rien n'est traité."""
    montage = _Montage(_Modele({"nom": "Petit"}), _config())
    montage.messages = [{"role": "user", "content": "Petit."}]
    await montage.passe()
    assert _garde(montage)["manque"] == ["prenom", "email", "numero dicte", "urgence"]


@pytest.mark.asyncio
async def test_k4_revise_un_numero_et_une_liste_fermee_refuses_sont_traites():
    """K4 révisé (décision d'Evan, 21/10) : « refusé » s'écrit aussi sur une liste fermée et sur un numéro à
    chiffres fixes ; la garde de l'étape les compte traités (l'agent avance, il ne boucle plus)."""
    montage = _Montage(_Modele({"numero_dicte": "refusé"}, {"urgence": "refusé"}), _config())
    montage.messages = [{"role": "user", "content": "Je ne donne pas mon numéro."}]
    await montage.passe()
    montage.messages.append({"role": "user", "content": "Et l'urgence, je ne veux pas le dire."})
    await montage.passe()
    assert montage.fiche["numero_dicte"] == "refusé" and montage.fiche["urgence"] == "refusé"
    assert not {"numero dicte", "urgence"} & set(_garde(montage)["manque"])


@pytest.mark.asyncio
async def test_k4_revise_un_numero_obligatoire_sans_exception_refuse_reste_manquant():
    champs = [{**c, "obligatoire_sans_exception": True} if c["nom"] == "numero_dicte" else c for c in CHAMPS]
    montage = _Montage(_Modele({"numero_dicte": "refusé"}), _config(champs))
    montage.messages = [{"role": "user", "content": "Je ne donne pas mon numéro."}]
    await montage.passe()
    assert montage.fiche["numero_dicte"] == "refusé"
    assert "numero dicte" in _garde(montage)["manque"]


@pytest.mark.asyncio
async def test_un_champ_obligatoire_sans_exception_refuse_reste_manquant():
    champs = [{**c, "obligatoire_sans_exception": True} if c["nom"] == "nom" else c for c in CHAMPS]
    montage = _Montage(_Modele({"nom": "refusé"}, {"prenom": "refusé"}), _config(champs))
    montage.messages = [{"role": "user", "content": "Je ne donne pas mon nom."}]
    await montage.passe()
    assert montage.fiche["nom"] == "refusé"
    assert "nom" in _garde(montage)["manque"]
    montage.messages.append({"role": "user", "content": "Ni mon prénom."})
    await montage.passe()
    manque = _garde(montage)["manque"]
    assert "prenom" not in manque and "nom" in manque
    # Les lignes du bloc suivent la garde : le nom refusé reste « attendu », jamais « déjà connu ».
    texte = etat_de_la_fiche(montage.reglages, montage.fiche) or ""
    assert "nom = « refusé »" in texte  # la fiche dit ce qu'elle tient
    from api.services.groupe.notes import ligne_deja_connu, ligne_encore_attendu

    assert "nom" in (ligne_encore_attendu(montage.reglages, montage.fiche, ETAPE) or "").split(": ", 1)[1].split(", ")
    assert "prenom" in (ligne_deja_connu(montage.reglages, montage.fiche, ETAPE) or "")
    assert "nom," not in (ligne_deja_connu(montage.reglages, montage.fiche, ETAPE) or "") + ","


# --------------------------------------------------------------------------- #
# 6.4 : le fond qui a des outils rend du texte sans en avoir appelé aucun
# --------------------------------------------------------------------------- #

CONFIER = _appel_d_outil(NOM_OUTIL, {"demande": DEMANDE}, "call_confier")


@pytest.mark.asyncio
async def test_un_fond_qui_rend_du_texte_sans_appeler_d_outil_rend_l_echec(appel):  # noqa: F811
    """Run 1480 : « réservation faite » sans aucun appel. L'agent lit l'échec, pas l'annonce."""
    signales = []
    original = TravailDeLAgent.signaler_l_echec_du_fond

    async def espion(self, entree, statut):
        signales.append((entree["statut"], statut))
        await original(self, entree, statut)

    with patch.object(TravailDeLAgent, "signaler_l_echec_du_fond", espion):
        await appel.monter(
            source_etapes=[CONFIER, _texte("Je regarde."), _texte("Je n'ai pas pu.")],
            fond_etapes=[_texte("Réservation faite pour demain à 14 h.")],
        )
        await appel.ouvrir()
        await appel.attendre(lambda: appel.travaux() and appel.travaux()[0]["remis"])
        await appel.attendre(lambda: any(est_un_resultat_de_travail(m) for m in appel.messages()))
    trace = appel.travaux()[0]
    assert trace["statut"] == STATUT_SANS_OUTIL
    assert trace["outils"] == []
    assert trace["resultat"] == "Réservation faite pour demain à 14 h."  # la trace garde ce que le fond a écrit
    resultats = [m for m in appel.messages() if est_un_resultat_de_travail(m)]
    assert [m["content"] for m in resultats] == [f"{PREFIXE_RESULTAT_DU_TRAVAIL} {TEXTE_SANS_OUTIL}]"]
    assert "Réservation" not in resultats[0]["content"]
    assert signales == [(STATUT_SANS_OUTIL, STATUT_SANS_OUTIL)]  # le point d'appel du lot 4, une fois


@pytest.mark.asyncio
@pytest.mark.parametrize("texte_du_fond", ["Manque : la date du passage.", "Échec : aucun outil pour cette demande."])
async def test_un_fond_qui_dit_manque_ou_echec_sans_outil_garde_son_texte(appel, texte_du_fond):  # noqa: F811
    """Revue M1 : « Manque : … » rendu sans outil (lot 0 : demande sans date) se garde ; jamais « rien n'a été fait »."""
    await appel.monter(
        source_etapes=[CONFIER, _texte("Je regarde."), _texte("Voilà.")],
        fond_etapes=[_texte(texte_du_fond)],
    )
    await appel.ouvrir()
    await appel.attendre(lambda: appel.travaux() and appel.travaux()[0]["remis"])
    await appel.attendre(lambda: any(est_un_resultat_de_travail(m) for m in appel.messages()))
    assert appel.travaux()[0]["statut"] == "fait"
    resultat = next(m for m in appel.messages() if est_un_resultat_de_travail(m))
    assert texte_du_fond in resultat["content"]


@pytest.mark.asyncio
async def test_un_fond_qui_appelle_son_outil_reste_un_travail_fait(appel):  # noqa: F811
    await appel.monter(
        source_etapes=[CONFIER, _texte("Je regarde."), _texte("Voilà.")],
        fond_etapes=[_appel_d_outil("chercher_creneau", {"jour": "demain"}, "call_fond"), _texte(RESULTAT)],
    )
    await appel.ouvrir()
    await appel.attendre(lambda: appel.travaux() and appel.travaux()[0]["remis"])
    await appel.attendre(lambda: any(est_un_resultat_de_travail(m) for m in appel.messages()))
    assert appel.travaux()[0]["statut"] == "fait"
    resultat = next(m for m in appel.messages() if est_un_resultat_de_travail(m))
    assert resultat["content"] == f"{PREFIXE_RESULTAT_DU_TRAVAIL} {RESULTAT}]"


@pytest.mark.asyncio
@pytest.mark.parametrize("texte_du_fond", ["Résultat : rendez-vous réservé le jeudi.", "C'est fait."])
async def test_un_outil_en_echec_suivi_d_un_resultat_rend_l_echec(appel, texte_du_fond):  # noqa: F811
    """Décision d'Evan (21/10) : l'outil a rendu une erreur, le fond rend quand même un résultat. Le code ne le
    croit pas : l'agent lit l'échec, et la règle « le travail de fond échoue » part."""
    signales = []
    original = TravailDeLAgent.signaler_l_echec_du_fond

    async def espion(self, entree, statut):
        signales.append(statut)
        await original(self, entree, statut)

    with patch.object(TravailDeLAgent, "signaler_l_echec_du_fond", espion):
        await appel.monter(
            source_etapes=[CONFIER, _texte("Je regarde."), _texte("Voilà.")],
            fond_etapes=[_appel_d_outil("chercher_creneau", {"jour": "demain"}, "call_fond"), _texte(texte_du_fond)],
            resultat_outil={"status": "error", "status_code": 503, "data": "Service Unavailable"},
        )
        await appel.ouvrir()
        await appel.attendre(lambda: appel.travaux() and appel.travaux()[0]["remis"])
        await appel.attendre(lambda: any(est_un_resultat_de_travail(m) for m in appel.messages()))
    assert appel.travaux()[0]["statut"] == STATUT_OUTIL_EN_ECHEC
    resultat = next(m for m in appel.messages() if est_un_resultat_de_travail(m))
    assert resultat["content"] == f"{PREFIXE_RESULTAT_DU_TRAVAIL} {TEXTE_SANS_OUTIL}]"
    assert signales == [STATUT_OUTIL_EN_ECHEC]


@pytest.mark.asyncio
async def test_un_outil_en_echec_que_le_fond_dit_lui_meme_reste_son_texte(appel):  # noqa: F811
    """Le fond honnête (« Échec : … », mesuré 24/24 au lot 0) garde son texte : le code n'intervient pas."""
    await appel.monter(
        source_etapes=[CONFIER, _texte("Je regarde."), _texte("Voilà.")],
        fond_etapes=[_appel_d_outil("chercher_creneau", {"jour": "demain"}, "call_fond"), _texte("Échec : l'agenda ne répond pas.")],
        resultat_outil={"status": "error", "error": "Request timed out after 5 seconds"},
    )
    await appel.ouvrir()
    await appel.attendre(lambda: appel.travaux() and appel.travaux()[0]["remis"])
    await appel.attendre(lambda: any(est_un_resultat_de_travail(m) for m in appel.messages()))
    assert appel.travaux()[0]["statut"] == "fait"
    resultat = next(m for m in appel.messages() if est_un_resultat_de_travail(m))
    assert "l'agenda ne répond pas" in resultat["content"]


@pytest.mark.parametrize(
    "contenu, attendu",
    [
        ('{"status": "error", "error": "Request timed out after 5 seconds"}', True),
        ('{"status": "success", "data": {"creneau": "14h"}}', False),
        ('{"statut": "échec"}', True),
        ('{"status": "transfer_failed", "reason": "no_answer"}', True),
        ('{"creneau": "14h"}', False),
        ("texte libre", False),
        ("", False),
        ('["error"]', False),
    ],
)
def test_ce_qui_est_un_resultat_d_outil_en_echec(contenu, attendu):
    assert resultat_en_echec(contenu) is attendu


@pytest.mark.asyncio
async def test_un_fond_sans_outils_rend_son_texte_comme_avant(appel):  # noqa: F811
    await appel.monter(
        source_etapes=[CONFIER, _texte("Je regarde."), _texte("Voilà.")],
        fond_etapes=[_texte("Une réponse sans outil.")],
        outils_du_fond=False,
    )
    await appel.ouvrir()
    await appel.attendre(lambda: appel.travaux() and appel.travaux()[0]["remis"])
    await appel.attendre(lambda: any(est_un_resultat_de_travail(m) for m in appel.messages()))
    assert appel.travaux()[0]["statut"] == "fait"
    resultat = next(m for m in appel.messages() if est_un_resultat_de_travail(m))
    assert "Une réponse sans outil." in resultat["content"]


# --------------------------------------------------------------------------- #
# 6.5 : les lignes internes ne sont jamais dites
# --------------------------------------------------------------------------- #


async def _lire(morceaux):
    return [m async for m in FluxNettoye(_Flux(morceaux), [], False)]


@pytest.mark.asyncio
async def test_chaque_etiquette_du_bloc_est_retiree_en_debut_de_ligne():
    etiquettes = etiquettes_du_bloc()
    assert len(etiquettes) >= 6
    for nom in etiquettes:
        sorties = await _lire([_m(), _m(f"{nom} : nom, prénom.\nVotre numéro ?"), _m(fin="stop")])
        assert _dit(sorties) == "Votre numéro ?", nom
        sorties = await _lire([_m(f"D'accord.\n{nom}: nom."), _m(fin="stop")])
        assert _dit(sorties) == "D'accord.\n", nom


@pytest.mark.asyncio
async def test_une_etiquette_coupee_en_morceaux_n_est_jamais_dite_et_la_fin_survit():
    sorties = await _lire(
        [_m(), _m("Enc"), _m("ore att"), _m("endu"), _m(" : numé"), _m("ro dicté.\n"), _m("Votre"), _m(" numéro ?"), _m(fin="stop"), _usage()]
    )
    assert _dit(sorties) == "Votre numéro ?"
    assert sorties[-1].usage.completion_tokens == 9
    assert any(m.choices and m.choices[0].finish_reason == "stop" for m in sorties)


@pytest.mark.asyncio
async def test_une_phrase_normale_qui_contient_note_reste_dite():
    for phrase in (
        "C'est noté, merci.",
        "Noté, je regarde les créneaux.",
        "Notez que je suis là.",
        "Votre prénom est noté : Marie.",
        "Fait, je m'en occupe.",
        "Attention au verglas, c'est glissant.",
        "Encore un instant.",
    ):
        for morceaux in ([phrase], [phrase[:3], phrase[3:9], phrase[9:]]):
            sorties = await _lire([_m(), *[_m(t) for t in morceaux], _m(fin="stop")])
            assert _dit(sorties) == phrase, (phrase, morceaux)


@pytest.mark.asyncio
async def test_un_debut_d_etiquette_reste_ambigu_a_la_fin_du_flux_est_rendu():
    sorties = await _lire([_m("Noté"), _m(fin="stop")])
    assert _dit(sorties) == "Noté"
    sorties = await _lire([_m("Bonjour.\nFait"), _m(fin="stop")])
    assert _dit(sorties) == "Bonjour.\nFait"


@pytest.mark.asyncio
async def test_une_ligne_interne_au_milieu_de_la_replique_est_retiree_seule():
    sorties = await _lire(
        [_m("Très bien.\nNoté : prénom = « Marie »\nÀ confirmer : commune"), _m(" = « Creil »\nQuel est votre nom ?"), _m(fin="stop")]
    )
    assert _dit(sorties) == "Très bien.\nQuel est votre nom ?"


def test_le_texte_complet_perd_ses_lignes_internes():
    assert sans_lignes_internes("Bien.\nDéjà connu : nom.\nEncore attendu : prénom.\nVotre prénom ?") == "Bien.\nVotre prénom ?"
    assert sans_lignes_internes("C'est noté.") == "C'est noté."


def test_les_etiquettes_viennent_du_code_qui_ecrit_le_bloc():
    """Chaque ligne que le code écrit au modèle commence par une des étiquettes lues : le jour où
    une ligne change de nom, ce test rougit (R1)."""
    reglages = ReglagesFiche.depuis(_config())
    fiche = {
        "nom": "Petit",
        "email": "a@b.fr",
        "fiche_etat": {"nom": {"sure": True}, "email": {"sure": False}},
    }
    texte = etat_de_la_fiche(reglages, fiche) or ""
    etiquettes = etiquettes_du_bloc()
    lignes = [l for l in texte.splitlines() if " : " in l]
    assert lignes, texte
    ecrites = {l.split(" : ", 1)[0] for l in lignes if l.split(" : ", 1)[0] in etiquettes}
    assert {"Noté", "À confirmer"} <= ecrites
    assert {"Déjà connu", "Encore attendu", "Attention"} <= set(etiquettes)
