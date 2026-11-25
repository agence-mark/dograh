"""[.mark] SA-47, lot 1 (essais au clavier du 17/11, appels 2592 et 2593, Casa Italia) : la fin d'une commande, et le geste rappelé sans rien de nouveau.

- M108 : ``finaliser`` rendait ENREGISTREE (« Votre commande est enregistrée pour dix-neuf heures. », dit par le code) et le modèle appelait la
  fin dans la même réponse : « … Au revoir. » sans « autre chose ? ». La confirmation dite par le code finit maintenant par une question (motif
  ``apres_enregistrement``, réglable), qui rend la parole (M92) ; la fin d'appel lancée dans la même réponse attend la réponse de la personne.
- M106/M107 : pendant la relecture, « c'est quel numéro que vous avez ? » ; le modèle rappelait ``finaliser`` sans rien de nouveau et le code
  disait une relecture tronquée « Cela fait maintenant dix euros quatre-vingt-dix. C'est bon ? ». Un rappel sans rien de nouveau ne dit plus
  rien et rend les faits au modèle ; la relecture reste valable. Réservation : même défaut (la relecture entière redite), corrigé dans son module.

| Test | Ce qu'il prouve |
|---|---|
| motif | au catalogue, texte par défaut, réglable (agent, étape), éteint = rien |
| commande enregistrée | la confirmation finit par la question réglée ; éteinte : la phrase seule ; « déjà fait » sans question |
| la question rend la parole | le texte du code qui finit par la question : modèle non relancé, question notée pour ce tour |
| fin d'appel | refusée dans le tour de la question (même réponse, autre appel encore en cours compris), passe au tour suivant |
| porte de fin du moteur | la porte vers un nœud de fin est refusée sans relancer le modèle, l'étape ne change pas |
| rappel sans rien de nouveau | aucun texte, pas de relecture « maintenant », faits rendus (numéro affiché compris), même jeton, puis « oui » enregistre |
| vraie correction | ce qui change est toujours relu ; un autre moyen de règlement refait la relecture |
| réservation | même logique dans son module, non dite par le code |
"""

from __future__ import annotations

import pytest
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from api.services.commande import moteur
from api.services.commande.moteur import Reglages
from api.services.commande.resultat import question_apres_enregistrement
from api.services.mots_dits import numero_en_lettres
from api.services.outils_mark.pour_la_voix import (
    noter_une_question_du_code,
    question_du_code_en_attente,
)
from api.services.phrases.catalogue import APRES_ENREGISTREMENT, MOTIFS
from api.services.workflow.fiche_au_fil_de_leau import CLE_TOUR
from api.services.workflow.fin_apres_question_du_code import (
    STATUT_REFUS,
    refus_de_fin_si_question_en_attente,
)
from api.tests.mark import commande_sur_la_fiche as F
from api.tests.mark.commande_sur_la_fiche import article as A
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_question_du_code_rend_la_parole import (
    _dit_par_le_code,
    _Moteur,
    _rendu,
)
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: F401
from api.tests.mark.test_restauration_commande_finaliser import TEL, Appel
from api.tests.mark.test_restauration_reservation import salle  # noqa: F401

QUESTION = "Puis-je faire autre chose pour vous ?"


# --------------------------------------------------------------------------- #
# M108 : la phrase du code réglable
# --------------------------------------------------------------------------- #


def _regle(**plus):
    return {"motif": APRES_ENREGISTREMENT, "portee": "agent", "variantes": ["Autre chose pour vous ?"], **plus}


def test_m108_le_motif_est_au_catalogue_et_se_regle():
    from api.schemas.phrases_du_code import ReglePhrase

    motif = MOTIFS[APRES_ENREGISTREMENT]
    assert motif.variantes_defaut == (QUESTION,) and motif.actif_par_defaut and motif.libelle_en and motif.quand_en
    ReglePhrase.model_validate(_regle())
    assert Reglages().question_apres_enregistrement == QUESTION
    assert question_apres_enregistrement(None) == QUESTION
    assert question_apres_enregistrement(SimpleNamespace(configurations={"phrases_regles": [_regle()]})) == "Autre chose pour vous ?"
    assert question_apres_enregistrement(SimpleNamespace(configurations={"phrases_regles": [_regle(active=False, variantes=[])]})) is None


async def test_m108_la_confirmation_de_la_commande_finit_par_la_question(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret()
    await a.jusqu_a_la_relecture()
    r = await a.confirmer()
    assert r.statut == "ENREGISTREE" and r.suggestion.startswith("Votre commande est enregistrée") and r.suggestion.endswith(". " + QUESTION)
    assert r.suggestion.count("?") == 1
    deja = await a.confirmer()
    assert deja.statut == "DEJA_FAIT" and "?" not in deja.suggestion


async def test_m108_la_question_reglee_ou_eteinte(commerce):
    a = await Appel(commerce, vente_en_plus=False, question_apres_enregistrement="Autre chose pour vous ?").pret()
    await a.jusqu_a_la_relecture()
    assert (await a.confirmer()).suggestion.endswith(". Autre chose pour vous ?")
    b = await Appel(commerce, vente_en_plus=False, affiche="+33699999999", question_apres_enregistrement=None).pret(A("coca", 2))
    await b.jusqu_a_la_relecture()
    r = await b.confirmer()
    assert r.statut == "ENREGISTREE" and r.suggestion.endswith(".") and "?" not in r.suggestion


async def test_m108_la_confirmation_dite_par_le_code_rend_la_parole_et_note_la_question():
    m = _Moteur()
    texte = f"Votre commande est enregistrée pour dix-neuf heures. {QUESTION}"
    _sortie, proprietes = await _rendu(m, _dit_par_le_code(texte, statut="ENREGISTREE"))
    assert m.dites == [texte] and proprietes.run_llm is False
    assert question_du_code_en_attente(m)
    m._gathered_context[CLE_TOUR] += 1  # la personne a répondu
    assert not question_du_code_en_attente(m)


# --------------------------------------------------------------------------- #
# M108 : la fin d'appel attend la réponse
# --------------------------------------------------------------------------- #


async def test_m108_la_fin_attend_l_autre_appel_de_la_meme_reponse_puis_est_refusee():
    m = SimpleNamespace(_gathered_context={CLE_TOUR: 5})

    async def finaliser_qui_pose_sa_question():
        await asyncio.sleep(0.05)
        noter_une_question_du_code(m)

    tache = asyncio.ensure_future(finaliser_qui_pose_sa_question())
    params = SimpleNamespace(llm=SimpleNamespace(_function_call_tasks={tache: None}))
    refus = await refus_de_fin_si_question_en_attente(m, params)
    assert refus is not None and refus["status"] == STATUT_REFUS
    m._gathered_context[CLE_TOUR] = 6  # la personne a répondu : la fin passe
    assert await refus_de_fin_si_question_en_attente(m, params) is None


async def test_m108_sans_question_du_code_la_fin_passe():
    m = SimpleNamespace(_gathered_context={CLE_TOUR: 2})
    assert await refus_de_fin_si_question_en_attente(m, SimpleNamespace()) is None
    assert await refus_de_fin_si_question_en_attente(SimpleNamespace(), SimpleNamespace(llm=None)) is None


async def test_m108_la_porte_de_fin_du_moteur_est_refusee_sans_relancer_le_modele():
    from api.tests.mark.test_outil_noter import CONFIG_ALLUMEE
    from api.tests.mark.test_transfert_garanti import _moteur

    engine = await _moteur(config=CONFIG_ALLUMEE, etape="etape")
    engine._gathered_context[CLE_TOUR] = 4
    noter_une_question_du_code(engine)
    agent = engine.active_agent
    fonction = await engine._create_transition_func("vers_fin", "end", agent=agent)
    rappel = AsyncMock()
    await fonction(SimpleNamespace(arguments={}, tool_call_id="t1", result_callback=rappel, llm=None))
    rappel.assert_awaited_once()
    (resultat,), kwargs = rappel.await_args
    assert resultat["status"] == STATUT_REFUS and kwargs["properties"].run_llm is False
    assert agent.current_node.id == "etape"


# --------------------------------------------------------------------------- #
# M106/M107 : le rappel sans rien de nouveau
# --------------------------------------------------------------------------- #


async def test_m106_m107_rappel_sans_rien_de_nouveau_ne_redit_rien_puis_oui_enregistre(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret()
    premiere = await a.jusqu_a_la_relecture()
    jeton = a.p["relecture"]["jeton"]
    # 2593 : « C'est quel numéro que vous avez ? » ; le modèle rappelle finaliser avec les mêmes arguments
    r = await a.finaliser(prenom="Alice", moyen="carte")
    assert r.suggestion == "" and r.manque != "relecture" and "maintenant" not in r.suggestion
    assert r.faits["relecture_deja_dite"] is True and r.faits["a_confirmer"] is True and r.faits["total"] == premiere.faits["total"]
    # lot 4 (M38, D49) : le numéro qui s'affiche n'est plus dit dans la relecture, il a sa question après le règlement (test_numero_telephone_m98.py)
    assert a.p["relecture"]["jeton"] == jeton and await a.commandes() == []
    r = await a.confirmer()
    assert r.statut == "ENREGISTREE", r


async def test_m106_une_vraie_correction_relit_toujours_ce_qui_change(commerce):
    a = await Appel(commerce, vente_en_plus=False).pret()
    await a.jusqu_a_la_relecture()
    await F.ajouter(a.source, a.p, a.regles, "tiramisu")  # lot 4 (D49) : par la case ``ajouter`` de la fiche
    await F.repondre(a.source, a.p, a.regles, "classic")  # le parfum est une question du code : sa réponse
    r = await a.finaliser()
    # C6 n° 4 (décision d'Evan 25/11 9 h 30) : ce qui a changé est un fait que le modèle dit ; le code dira la phrase réglée du nouveau total
    assert r.manque == "relecture" and any(c["geste"] == "ajoutee" and "iramisu" in c["nom"] for c in r.faits["ce_qui_a_change"]), r
    assert a.p["relecture"]["motif_du_total"] == "total_apres_correction"
    # lot 4 (M38, M39, D49) : le règlement vient après la relecture, un autre moyen ne la refait plus ; sens repris par partie_1/test_l04_cuisine.py::test_une_seule_relecture


async def test_m106_m107_reservation_rappel_sans_rien_de_nouveau(salle):
    from api.tests.mark.test_restauration_reservation_outils import Appel as AppelResa

    a = AppelResa(salle)
    dit = {"jour": "samedi", "heure": "20h", "personnes": 2, "prenom": "Alice"}
    assert (await a.reserver(**dit)).manque == "relecture"
    r = await a.reserver(**dit)
    assert r.statut == "INCOMPLETE" and r.suggestion == "" and r.faits["relecture_deja_dite"] is True and r.faits["numero_affiche_dit"]
    autre = await a.reserver(personnes=3)  # une vraie correction : relue
    assert autre.manque == "relecture" and "trois personnes" in autre.suggestion
    assert (await a.reserver(confirmer=True)).statut == "ENREGISTREE"
