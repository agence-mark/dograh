"""[.mark] Lot 2 d'orchestrateur-trois-cerveaux (D2, D3, D4) : les notes de passation écrites par le code.

Plan `Labo-agent-vocal/plans/orchestrateur-trois-cerveaux/` (§ 2.1, § 2.2). À la passation, ce qui
voyage est écrit par le code depuis la fiche : une note à l'aller (première étape du collègue), une
note au retour (étape de retour de l'accueil), jamais par un modèle ; et une ligne « Déjà connu »
collée à la question. Les tests de moteur passent par le VRAI moteur et le VRAI coordinateur (banc
fendu de `test_agent_transfer.py`) ; ils ne demandent ni Postgres ni Redis.

| Test | Ce qu'il prouve |
|---|---|
| note de retour | le format validé, rempli depuis la fiche : motif, fait, en attente, déjà connu ; rien sans collègue |
| note d'aller | le format validé ; motif = outil appelé (et champ « motif » s'il existe) |
| jamais la valeur | aucune valeur de la fiche, aucun crochet |
| à l'aller (R1) | la première étape du collègue reçoit la note dans son prompt ; la même note est recalculée depuis la fiche (clavier) |
| aucun résumé | une passation de groupe n'appelle jamais le modèle de résumé, même sur une longue conversation, et garde les N derniers messages |
| agent seul | le résumé d'avant, à l'octet ; une limite posée à 0 le garde aussi |
| déjà connu | la ligne : noms lisibles, complément du souffle, rien sans champ connu |
"""

from unittest.mock import AsyncMock, patch

import pytest

from api.services.groupe.notes import (
    CLE_CHAMPS_DES_AGENTS,
    CONSIGNE_ALLER,
    CONSIGNE_RETOUR,
    ligne_deja_connu,
    note_d_aller,
    note_de_retour,
    noter_les_champs_de_l_agent,
    outil_de_passation_vers,
)
from api.services.groupe.reglages_passation import dernieres_a_garder
from api.services.workflow.fiche_au_fil_de_leau import ReglagesFiche
from api.tests.mark.test_passation_rapide_groupe import (
    GROUPE,
    PATCH_OUTILS,
    _monter_groupe,
    _passer,
    _sonnerie,
)
from api.tests.test_agent_transfer import TransferAgentTool

PRINCIPAL = 7
COLLEGUE = 12

FICHE = ReglagesFiche.depuis(
    {
        "fiche_au_fil_de_leau": True,
        "fiche_champs": [
            {"nom": "nom", "origine": "dicte", "description": "Nom"},
            {"nom": "code_postal", "origine": "dicte", "description": "Code postal"},
            {"nom": "objet", "origine": "dicte", "description": "L'objet"},
            {"nom": "detail", "origine": "dicte", "description": "Un détail"},
            {"nom": "autre_detail", "origine": "dicte", "description": "Un autre détail"},
        ],
    }
)


def _fiche_remplie() -> dict:
    return {
        "nom": "Dupont",
        "code_postal": "60000",
        "objet": "une fuite",
        "passations": [
            {"de": PRINCIPAL, "vers": COLLEGUE, "raison": "Passer à Support", "issue": "completed"}
        ],
        "parcours_etapes": [
            {"agent": "Accueil", "agent_id": PRINCIPAL, "etape": "Accueil"},
            {"agent": "Support", "agent_id": COLLEGUE, "etape": "Qualification"},
            {"agent": "Support", "agent_id": COLLEGUE, "etape": "Coordonnées"},
            {"agent": "Support", "agent_id": COLLEGUE, "etape": "Retour au principal"},
        ],
    }


# --------------------------------------------------------------------------- #
# La note de retour
# --------------------------------------------------------------------------- #


def test_la_note_de_retour_a_le_format_valide():
    gathered = _fiche_remplie()
    note = note_de_retour(FICHE, gathered, principal_id=PRINCIPAL)
    assert note == "\n".join(
        [
            "# Retour du collègue « Support »",
            "Motif de départ : Passer à Support",
            "Fait : étapes traversées : Qualification › Coordonnées ; champs remplis : objet",
            "En attente : detail, autre detail",
            "Déjà connu : nom, code postal, objet",
            CONSIGNE_RETOUR,
        ]
    )


def test_le_motif_vient_du_champ_motif_de_l_organisation_puis_de_la_demande_close_puis_de_l_outil():
    gathered = _fiche_remplie()
    gathered["motif_du_client"] = "fuite sous l'évier"
    assert "Motif de départ : fuite sous l'évier" in note_de_retour(
        FICHE, gathered, principal_id=PRINCIPAL, champ_motif="motif_du_client"
    )
    del gathered["motif_du_client"]
    gathered["demandes"] = [{"agent_id": COLLEGUE, "motif": "fuite close", "champs": {}}]
    assert "Motif de départ : fuite close" in note_de_retour(
        FICHE, gathered, principal_id=PRINCIPAL, champ_motif="motif_du_client"
    )
    del gathered["demandes"]
    assert "Motif de départ : Passer à Support" in note_de_retour(
        FICHE, gathered, principal_id=PRINCIPAL, champ_motif="motif_du_client"
    )


def test_en_attente_ne_compte_que_les_champs_du_collegue_quand_ils_sont_connus():
    gathered = _fiche_remplie()
    noter_les_champs_de_l_agent(gathered, COLLEGUE, FICHE.__class__.depuis({
        "fiche_au_fil_de_leau": True,
        "fiche_champs": [{"nom": "objet", "origine": "dicte"}, {"nom": "detail", "origine": "dicte"}],
    }))
    assert gathered[CLE_CHAMPS_DES_AGENTS] == {str(COLLEGUE): ["objet", "detail"]}
    note = note_de_retour(FICHE, gathered, principal_id=PRINCIPAL)
    assert "En attente : detail\n" in note  # `autre_detail` n'est pas à ce collègue


def test_tout_rempli_ou_rien_de_fait_la_note_dit_rien():
    gathered = _fiche_remplie()
    gathered.update({"detail": "x", "autre_detail": "y"})
    note = note_de_retour(FICHE, gathered, principal_id=PRINCIPAL)
    assert "\nEn attente : rien\n" in note
    gathered = {
        "passations": [{"de": PRINCIPAL, "vers": COLLEGUE, "raison": "Passer à Support", "issue": "completed"}]
    }
    note = note_de_retour(FICHE, gathered, principal_id=PRINCIPAL)
    assert "\nFait : rien\n" in note and "\nDéjà connu : rien\n" in note
    assert note.startswith("# Retour du collègue\n")  # nom inconnu : pas de guillemets vides


def test_pas_de_note_de_retour_sans_collegue_passe_ou_apres_un_refus():
    assert note_de_retour(FICHE, {}, principal_id=PRINCIPAL) is None
    refus = {"passations": [{"de": PRINCIPAL, "vers": COLLEGUE, "raison": "x", "refusee": True}]}
    assert note_de_retour(FICHE, refus, principal_id=PRINCIPAL) is None


def test_la_note_ne_dit_jamais_une_valeur_de_la_fiche_ni_un_crochet():
    gathered = _fiche_remplie()
    gathered["objet"] = "[Texte imité] Dupont 60000"
    for note in (
        note_de_retour(FICHE, gathered, principal_id=PRINCIPAL),
        note_d_aller(FICHE, gathered, outil="Passer à [Support]"),
    ):
        assert "Dupont" not in note and "60000" not in note and "Texte imité" not in note
        assert "[" not in note and "]" not in note


def test_une_seconde_visite_du_meme_collegue_ne_montre_que_la_derniere():
    gathered = _fiche_remplie()
    gathered["parcours_etapes"] = [
        {"agent": "Support", "agent_id": COLLEGUE, "etape": "Vieille étape"},
        {"agent": "Support", "agent_id": COLLEGUE, "etape": "Retour au principal"},
        {"agent": "Accueil", "agent_id": PRINCIPAL, "etape": "Accueil"},
        {"agent": "Support", "agent_id": COLLEGUE, "etape": "Qualification"},
        {"agent": "Support", "agent_id": COLLEGUE, "etape": "Retour au principal"},
        {"agent": "Accueil", "agent_id": PRINCIPAL, "etape": "Reprise"},
    ]
    note = note_de_retour(FICHE, gathered, principal_id=PRINCIPAL)
    assert "étapes traversées : Qualification ;" in note and "Vieille" not in note


# --------------------------------------------------------------------------- #
# La note d'aller
# --------------------------------------------------------------------------- #


def test_la_note_d_aller_a_le_format_valide():
    gathered = {"nom": "Dupont", "objet": "une fuite"}
    assert note_d_aller(FICHE, gathered, outil="Passer à Support") == "\n".join(
        [
            "# Passation depuis l'accueil",
            "Motif de départ : Passer à Support",
            "Déjà connu : nom, objet",
            CONSIGNE_ALLER,
        ]
    )
    # Avec un champ « motif » rempli : l'outil et le motif.
    gathered["motif_du_client"] = "fuite sous l'évier"
    assert "Motif de départ : Passer à Support (fuite sous l'évier)" in note_d_aller(
        FICHE, gathered, outil="Passer à Support", champ_motif="motif_du_client"
    )
    assert "Déjà connu : rien" in note_d_aller(FICHE, {}, outil="Passer à Support")


def test_l_outil_de_la_derniere_passation_aboutie_se_relit_dans_la_fiche():
    gathered = _fiche_remplie()
    assert outil_de_passation_vers(gathered, COLLEGUE) == "Passer à Support"
    assert outil_de_passation_vers(gathered, 999) is None
    assert outil_de_passation_vers({}, COLLEGUE) is None


# --------------------------------------------------------------------------- #
# La ligne « Déjà connu »
# --------------------------------------------------------------------------- #


def test_la_ligne_deja_connu_est_le_complement_des_champs_manquants_de_l_etape():
    gathered = {"nom": "Dupont", "objet": "une fuite"}
    # L'étape demande nom, code postal, objet : deux sont connus, le code postal manque.
    assert ligne_deja_connu(FICHE, gathered, ["nom", "code_postal", "objet"]) == "Déjà connu : nom, objet."
    # Un champ lu par un module au tour même compte comme obtenu (comme pour le souffle).
    assert (
        ligne_deja_connu(FICHE, gathered, ["nom", "code_postal"], deja_lus=["code_postal"])
        == "Déjà connu : nom, code postal."
    )
    # Une étape qui ne déclare aucun champ : tous les champs remplis de la fiche.
    assert ligne_deja_connu(FICHE, gathered, []) == "Déjà connu : nom, objet."
    # Rien de connu : pas de ligne. Un nom inconnu de la fiche est ignoré.
    assert ligne_deja_connu(FICHE, {}, ["nom"]) is None
    assert ligne_deja_connu(FICHE, gathered, ["inconnu"]) == "Déjà connu : nom, objet."
    assert ligne_deja_connu(None, gathered, ["nom"]) is None


# --------------------------------------------------------------------------- #
# À l'aller : la vraie route de passation (R1)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_la_premiere_etape_du_collegue_recoit_la_note_d_aller(monkeypatch):
    _sonnerie(monkeypatch)
    harness = await _monter_groupe(GROUPE)
    engine = harness.engine
    engine._fiche = FICHE
    engine._gathered_context.update({"nom": "Dupont", "objet": "une fuite"})
    try:
        with patch(PATCH_OUTILS, AsyncMock(return_value=[TransferAgentTool()])):
            assert (await _passer(harness, 99, raison="Passer à Support"))["outcome"] == "completed"
        agent = engine.active_agent
        prompt = agent.system_prompt
        assert "# Passation depuis l'accueil" in prompt
        assert "Motif de départ : Passer à Support" in prompt
        assert "Déjà connu : nom, objet" in prompt
        assert CONSIGNE_ALLER in prompt
        assert "Dupont" not in prompt
        # Au clavier, chaque tour refait le moteur : la note se recalcule depuis la fiche, à l'identique
        # (la passation est maintenant écrite dans la fiche, la demande en cours n'existe plus).
        assert engine.transfer_coordinator._request is None
        assert engine._note_de_passation(agent, agent.current_node) in prompt
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_un_agent_seul_n_a_aucune_note_d_aller(monkeypatch):
    _sonnerie(monkeypatch)
    harness = await _monter_groupe(None)
    try:
        with patch(PATCH_OUTILS, AsyncMock(return_value=[TransferAgentTool()])):
            assert (await _passer(harness, 99, raison="Passer à Support"))["outcome"] == "completed"
        assert "Passation depuis l'accueil" not in harness.engine.active_agent.system_prompt
    finally:
        await harness.stop()


# --------------------------------------------------------------------------- #
# Aucun résumé rédigé par un modèle
# --------------------------------------------------------------------------- #

LONGUE_CONVERSATION = [
    {"role": "user" if i % 2 == 0 else "assistant", "content": f"message {i}"} for i in range(100)
]


async def _passation_longue(reglages):
    harness = await _monter_groupe(reglages, messages=LONGUE_CONVERSATION)
    llm = harness.engine.active_agent.inference_llm
    llm._generate_summary = AsyncMock(return_value=("Résumé anglais.", 3))
    try:
        with patch(PATCH_OUTILS, AsyncMock(return_value=[TransferAgentTool()])):
            assert (await _passer(harness, 99))["outcome"] == "completed"
        textes = [str(m.get("content")) for m in harness.engine.context.messages]
        return llm._generate_summary.await_count, textes
    finally:
        await harness.stop()


def test_le_nombre_de_messages_gardes():
    assert dernieres_a_garder(GROUPE) == 40
    assert dernieres_a_garder({**GROUPE, "passation_sans_resume_jusqua": 12}) == 12
    # Un agent seul, ou un groupe qui a posé 0 : le résumé d'avant.
    assert dernieres_a_garder(None) is None and dernieres_a_garder({}) is None
    assert dernieres_a_garder({**GROUPE, "passation_sans_resume_jusqua": 0}) is None
    assert dernieres_a_garder({"passation_sans_resume_jusqua": 12}) is None


@pytest.mark.asyncio
async def test_une_passation_de_groupe_n_appelle_jamais_le_modele_de_resume(monkeypatch):
    _sonnerie(monkeypatch)
    appels, textes = await _passation_longue(GROUPE)
    assert appels == 0
    assert not any("Résumé anglais" in t or "Handover note" in t for t in textes)
    # Les 40 derniers messages de la conversation, pas les 100.
    assert "message 99" in textes and "message 60" in textes
    assert "message 59" not in textes
    assert sum(t.startswith("message ") for t in textes) == 40


@pytest.mark.asyncio
async def test_le_seuil_du_groupe_fixe_combien_de_messages_sont_gardes(monkeypatch):
    _sonnerie(monkeypatch)
    appels, textes = await _passation_longue({**GROUPE, "passation_sans_resume_jusqua": 12})
    assert appels == 0
    assert sum(t.startswith("message ") for t in textes) == 12 and "message 99" in textes


@pytest.mark.asyncio
async def test_un_agent_seul_garde_le_resume_d_avant(monkeypatch):
    _sonnerie(monkeypatch)
    appels, textes = await _passation_longue(None)
    assert appels == 1
    assert any("Résumé anglais." in t for t in textes)
    appels, _ = await _passation_longue({**GROUPE, "passation_sans_resume_jusqua": 0})
    assert appels == 1


# --------------------------------------------------------------------------- #
# La ligne « Déjà connu » dans la requête (R1 : la vraie requête de conversation)
# --------------------------------------------------------------------------- #

from api.services.workflow.fiche_au_fil_de_leau import etat_avec_les_indices, montrer_la_fiche  # noqa: E402
from api.tests.mark.boucle_isolee import executer_sans_toucher_la_boucle_courante  # noqa: E402

CHAMPS_GARAGE = [
    {"nom": "immatriculation", "type": "string", "origine": "dicte", "description": "Plaque."},
    {"nom": "kilometrage", "type": "string", "origine": "dicte", "description": "Km."},
    {"nom": "commune_garage", "type": "string", "origine": "dicte", "description": "Commune."},
]
ETAPE_GARAGE = ("immatriculation", "kilometrage", "commune_garage")


def _reglages_garage(*, deja_connu: bool, etiquettes: bool = False, mode: str = "greffier"):
    return ReglagesFiche.depuis(
        {
            "fiche_au_fil_de_leau": True,
            "fiche_champs": CHAMPS_GARAGE,
            "fiche_mode_de_note": mode,
            "etiquettes_des_etapes": etiquettes,
            "fiche_deja_connu": deja_connu,
        }
    )


class _FauxModele:
    """Le service de conversation, réduit à ce que ``montrer_la_fiche`` enveloppe."""

    def __init__(self, cle="messages"):
        self.cle = cle

    async def get_chat_completions(self, context):
        return self.build_chat_completion_params({self.cle: context})

    def build_chat_completion_params(self, p):
        return {self.cle: list(p[self.cle])}


def _requete(reglages, fiche, champs_etape=ETAPE_GARAGE, cle="messages"):
    llm = _FauxModele(cle)
    montrer_la_fiche(llm, reglages, lambda: fiche, None, lambda: champs_etape)
    return executer_sans_toucher_la_boucle_courante(
        llm.get_chat_completions([{"role": "user", "content": "bonjour"}])
    )[cle]


def test_la_requete_porte_la_ligne_deja_connu_avant_la_derniere_parole_de_l_appelant():
    fiche = {"immatriculation": "AB-123-CD", "commune_garage": "Compiègne"}
    messages = _requete(_reglages_garage(deja_connu=True), fiche)
    assert messages[-1] == {"role": "user", "content": "bonjour"}
    bloc = messages[-2]["content"]
    assert "Déjà connu : immatriculation, commune garage." in bloc
    # Jamais la valeur, seulement le nom lisible.
    assert "AB-123-CD" not in bloc.split("Déjà connu")[1]
    assert "Compiègne" not in bloc.split("Déjà connu")[1]


def test_la_ligne_deja_connu_suit_la_meme_requete_en_api_responses():
    fiche = {"immatriculation": "AB-123-CD"}
    messages = _requete(_reglages_garage(deja_connu=True), fiche, cle="input")
    assert "Déjà connu : immatriculation." in messages[-2]["content"]


def test_case_eteinte_ou_rien_de_connu_la_requete_est_celle_d_avant():
    fiche = {"immatriculation": "AB-123-CD"}
    eteinte = _requete(_reglages_garage(deja_connu=False), fiche)
    assert not any("Déjà connu" in str(m["content"]) for m in eteinte)
    # La case éteinte ne change rien à la requête d'avant, à l'octet.
    assert eteinte == _requete(ReglagesFiche.depuis({
        "fiche_au_fil_de_leau": True, "fiche_champs": CHAMPS_GARAGE, "fiche_mode_de_note": "greffier",
    }), fiche)
    # Allumée mais rien de connu : pas de ligne.
    vide = _requete(_reglages_garage(deja_connu=True), {})
    assert not any("Déjà connu" in str(m["content"]) for m in vide)
    assert etat_avec_les_indices(_reglages_garage(deja_connu=True), {}, None, [], ()) is None


def test_la_ligne_est_independante_des_etiquettes_et_vient_apres_le_souffle():
    fiche = {"immatriculation": "AB-123-CD"}
    seule = _requete(_reglages_garage(deja_connu=True, etiquettes=False), fiche)
    assert not any("Il manque encore" in str(m["content"]) for m in seule)
    assert any("Déjà connu : immatriculation." in str(m["content"]) for m in seule)
    avec = _requete(_reglages_garage(deja_connu=True, etiquettes=True), fiche)
    bloc = next(m["content"] for m in avec if "Déjà connu" in str(m["content"]))
    # Le souffle (ce qu'il manque) puis son complément (ce qui est connu), l'un contre l'autre.
    assert bloc.index("Il manque encore") < bloc.index("Déjà connu")


def test_tous_les_modes_de_prise_de_notes():
    fiche = {"kilometrage": "120000"}
    for mode in ("outil", "post_scriptum", "greffier"):
        messages = _requete(_reglages_garage(deja_connu=True, mode=mode), fiche)
        assert any("Déjà connu : kilometrage." in str(m["content"]) for m in messages), mode


def test_la_cle_est_lue_strictement_et_eteinte_par_defaut():
    base = {"fiche_au_fil_de_leau": True, "fiche_champs": CHAMPS_GARAGE}
    assert ReglagesFiche.depuis(base).deja_connu is False
    assert ReglagesFiche.depuis({**base, "fiche_deja_connu": "oui"}).deja_connu is False
    assert ReglagesFiche.depuis({**base, "fiche_deja_connu": True}).deja_connu is True
