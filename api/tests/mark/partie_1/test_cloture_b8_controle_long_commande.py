"""[.mark] Clôture de la Partie 1, correctifs du contrôle long (23/11), agent « commande », lot 3 : les familles RC1, RC9, M9, RC6, RC7 et les restes de RC4 et RC10.

Chaque cas est une suite que le test des combinaisons a vue rouge (état, gestes), rejouée par le MÊME juge (``combinaisons.jouer``, règles RC1 à RC15 inchangées) :
elle doit rendre zéro faute. Aucune règle n'est assouplie ; un cas est ajouté par défaut trouvé, jamais retiré.

T12 (26/11, coordinateur 10 h 45) : trois cas de RC4 (la même fiche rejouée dans le tour sur une commande enregistrée). Une fiche rejouée qui ne change rien, une fois
la relance du tour faite, est une relance ratée : le code dit la suite réglée (la phrase réglée gardée, M108) s'il en reste une, sinon la phrase réglée « pas compris »
(P3) ; jamais « C'est noté. » (la phrase du modèle écrite avant l'exécution) dite seule. Ils reviennent dans ``CAS`` (RC4 inchangée) ;
``test_la_fiche_rejouee_apres_la_relance_est_une_relance_ratee`` dit ce que la personne entend.
"""

from __future__ import annotations

import pytest

from api.services.actions_communes import parole as PAROLE
from api.services.actions_communes.du import RIEN_CHANGE
from api.services.phrases.catalogue import APRES_ENREGISTREMENT, MOTIFS, REPONSE_PERDUE
from api.tests.mark.partie_1 import combinaisons as C

CAS = {
    # RC1 : « annulez ma commande » (ou un détour) + un changement sur une commande enregistrée : une seule question dans le tour
    "rc1_annuler_et_ajouter": ("E16", ("G1+G22",)),
    "rc1_annuler_et_adresse": ("E16", ("G16+G22",)),
    "rc1_annuler_et_heure": ("E16", ("G18+G22",)),
    "rc1_annuler_et_heure_e18": ("E18", ("G18+G22",)),
    "rc1_annuler_et_mode_e18": ("E18", ("G16+G22",)),
    "rc1_doute_ouvert_puis_changement": ("E16", ("G4", "G8")),
    # RC4 : reste, vider + ajouter sur une commande enregistrée
    "rc4_ajouter_et_vider_enregistree": ("E16", ("G6+G12",)),
    "rc4_fiche_rejouee_deux_fois_e16": ("E16", ("G31", "G31")),
    "rc4_fiche_rejouee_deux_fois_e10": ("E10", ("G31", "G31")),
    "rc4_mode_puis_fiche_rejouee_e18": ("E18", ("G15", "G31")),
    "rc4_fiche_vide_puis_rejouee_e18": ("E18", ("G30", "G31")),  # PE-2 Q3 : le juge laisse la phrase du modèle sur une fiche vide sans rien de dû (``test_p1f_lot8_pe_juge_rc4``)
    "rc1_vider_puis_ajouter_e18": ("E18", ("G12", "G1")),
    # RC9 : la même question reposée garde son numéro
    "rc9_hesitation_redite_avec_non": ("E6", ("G4+G24",)),
    # M9 : aucune valeur nulle là où le retour donne un prix
    "m9_retirer_et_oui_en_livraison": ("E10", ("G7+G23",)),
    "m9_remplacer_et_oui_en_livraison": ("E10", ("G11+G23",)),
    # RC6 : trois fois la même chose sans sortie
    "rc6_annulee_trois_fois": ("E17", ("G18", "G32", "G4", "G12")),
    "rc6_relecture_trois_fois": ("E14", ("G18", "G26", "G24")),
    "rc6_taille_trois_fois": ("E5", ("G16", "G15", "G34")),
    "rc6_doute_trois_fois": ("E10", ("G4", "G16", "G23")),
    "rc6_numero_trois_fois": ("E14", ("G30", "G3", "G25")),
    # RC7 : « pardon ? » après une commande finie
    "rc7_pardon_apres_annulation": ("E11", ("G13+G7", "G21", "G24", "G35")),
    "rc7_pardon_apres_annulation_2": ("E12", ("G11+G13", "G12", "G2+G28", "G8", "G28", "G35")),
    # Restes des 2 000 suites tirées (graine 20261122), réduits par le test lui-même
    "tirees_rc9_taille_autre_ligne": ("E5", ("G2", "G9")),
    "tirees_rc6_doute_taille_doute": ("E10", ("G4", "G9", "G18")),
    "tirees_rc6_relecture_fiche_mal_formee": ("E15", ("G9+G20", "G34", "G34")),
    "tirees_rc4_vider_enregistree_puis_oui_et_ajout": ("E18", ("G12", "G2+G23")),
    "tirees_rc2_rc8_vider_ajouter_enregistree_puis_retirer": ("E18", ("G12+G2", "G7")),
    "tirees_rc2_rc8_oui_nouvelle_commande": ("E7", ("G14+G21", "G33", "G1+G23")),
    "tirees_rc2_rc8_oui_nouvelle_commande_e17": ("E17", ("G2", "G5+G23")),
    "tirees_rc2_adresse_horszone_oui": ("E17", ("G19", "G23+G17")),
    # RC10 : relecture marquée faite sans être dite (changement d'heure après l'accord, un article en doute ouvert)
    "rc10_heure_apres_accord_avec_un_doute": ("E13", ("G4", "G18")),
}


@pytest.mark.parametrize("nom", list(CAS))
async def test_le_juge_ne_voit_plus_la_faute(faire_monde, monkeypatch, nom):
    etat, suite = CAS[nom]
    monde = await faire_monde("casa-italia")
    res = await C.jouer(monde, monkeypatch, etat, suite)
    assert res.atteint, f"{etat} non atteint"
    assert not res.fautes, "\n".join(f"[{g}] {r} : {d}" for g, r, d in res.fautes)


# T12 : la commande est enregistrée ; le modèle joue dans le tour une fiche qui ne change rien, puis la rejoue. Ce que la personne entend à la fin du tour :
# la suite réglée gardée (M108), ou la phrase réglée « pas compris » de l'agent (P3, ``None`` : dite par la voix, ``REPONSE_PERDUE``)
M108 = MOTIFS[APRES_ENREGISTREMENT].variantes_defaut[0]
CAS_APRES_LA_RELANCE = {
    "rc4_fiche_rejouee_deux_fois_e16": ("E16", ("G31", "G31"), M108),
    "rc4_mode_puis_fiche_rejouee_e18": ("E18", ("G15", "G31"), None),
}


@pytest.mark.parametrize("nom", list(CAS_APRES_LA_RELANCE))
async def test_la_fiche_rejouee_apres_la_relance_est_une_relance_ratee(faire_monde, monkeypatch, nom):
    """Client « Léa. » (E16 : commande enregistrée, M108 posée après la phrase du modèle) ou « Finalement en livraison. » / « D'accord. » (E18 : rien ne change).
    La première fiche qui ne change rien est retenue : la relance du tour (une seule). La fiche rejouée ne change rien non plus : relance ratée. Avant (``5328f550``) :
    « C'est noté. » seul, M108 perdue (E16 : le tour finit sans question). Après : E16 « Puis-je faire autre chose pour vous ? » ; E18 : P3. Coordinateur 26/11 10 h 45."""
    etat, suite, attendu = CAS_APRES_LA_RELANCE[nom]
    partie = C.Partie(await faire_monde("casa-italia"), monkeypatch)
    assert await partie.recette(etat), f"{etat} non atteint"
    vues = []
    for pas in suite:
        o = await partie.geste(pas)
        assert o is not None, f"{pas} sans objet dans {etat}"
        vues.append(o)
    premiere, seconde = vues
    assert C.lignes_de(premiere.avant) == C.lignes_de(seconde.apres), "la fiche a changé le panier"
    assert (premiere.decision.mode, premiere.decision.motif) == (PAROLE.SECOND_PASSAGE, RIEN_CHANGE), premiere.decision  # la relance du tour
    assert seconde.decision.mode == PAROLE.A_DIRE_SEUL, seconde.decision  # jamais une seconde relance
    assert seconde.decision.a_dire != C.ANNONCE, seconde.decision  # jamais « C'est noté. » seul quand rien n'est noté
    if attendu is None:
        assert (seconde.decision.a_dire, seconde.decision.motif) == (None, REPONSE_PERDUE), seconde.decision  # P3, dite par la voix (jamais un tour muet)
    else:
        assert (seconde.decision.a_dire or "").endswith(attendu), seconde.decision  # la question en dernier
    assert not (seconde.textes or {}).get("fait_accompli"), seconde.textes  # le code ne redit pas le fait accompli


async def test_une_fiche_vide_rejouee_sans_rien_de_du_dit_la_phrase_du_modele(faire_monde, monkeypatch):
    """PE-2 Q3 (BILAN:271) : E18 (rien n'attend), « D'accord. » : la fiche est vide, rejouée dans le tour. Avant (T12) : P3 « Pardon, je n'ai pas bien saisi ». Après : la phrase du modèle,
    dite seule (« Ah merci. » / « Avec plaisir. »). Le prix : « C'est noté. » aussi, sur une fiche vide sans rien de dû (le code ne lit pas les mots). La fiche du mode changé (``G15``)
    reste sur P3 (``CAS_APRES_LA_RELANCE``), la question qui attend aussi (``test_cloture_b2_du``)."""
    partie = C.Partie(await faire_monde("casa-italia"), monkeypatch)
    assert await partie.recette("E18")
    premiere = await partie.geste("G30")
    seconde = await partie.geste("G31")
    assert (premiere.decision.mode, premiere.decision.motif) == (PAROLE.SECOND_PASSAGE, RIEN_CHANGE), premiere.decision  # la relance du tour
    assert (seconde.decision.mode, seconde.decision.a_dire, seconde.decision.motif) == (PAROLE.A_DIRE_SEUL, C.ANNONCE, "fait"), seconde.decision


async def test_la_relance_ratee_sans_suite_dit_p3_a_la_voix(monkeypatch):
    """T12 : la table rend P3 sans texte (``REPONSE_PERDUE``) ; la voix dit la phrase réglée « pas compris » de l'agent, et le modèle ne repasse pas. Jamais un tour muet."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from api.services.groupe import passations as PA
    from api.services.pipecat.reponse_avalee import ATTRIBUT_PHRASE_DE_REPLI
    from api.services.workflow import parole_de_la_fiche as PF

    monkeypatch.setattr(PF, "decider_apres_la_fiche", lambda *_a, **_k: PAROLE.Decision(PAROLE.A_DIRE_SEUL, motif=REPONSE_PERDUE))
    monkeypatch.setattr(PA, "noter_le_porteur", lambda *_a, **_k: None)
    llm = SimpleNamespace(**{ATTRIBUT_PHRASE_DE_REPLI: lambda: "Pardon, je n'ai pas bien saisi. Vous pouvez répéter ?"})
    engine = SimpleNamespace(active_agent=SimpleNamespace(llm=llm), queue_text_message=AsyncMock())
    params = SimpleNamespace(arguments={"a_dire": C.ANNONCE}, result_callback=AsyncMock())
    assert await PF.dire_le_retour(engine, {}, {"statut": "OK"}, params, None, None)
    engine.queue_text_message.assert_awaited_once()
    assert engine.queue_text_message.await_args.args[0] == "Pardon, je n'ai pas bien saisi. Vous pouvez répéter ?"
    assert params.result_callback.await_args.kwargs["properties"].run_llm is False
