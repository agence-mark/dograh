"""[.mark] Lot 7b-C6, commit 10 (décision d'Evan 25/11 9 h 30, § 8 bis : le numéro reste au code) : « Quel numéro je note ? » et la proposition du numéro qui s'affiche passent au
modèle ; le numéro retenu est dit par le code avec le motif réglé ``numero_retenu`` (« Je note le {numero}. »), jamais composé dans le résultat d'un outil.

Avant : code « Je note le numéro qui s'affiche, c'est bon ? » / après : modèle « Je garde le numéro qui s'affiche ? ».
DC10 allumé : code « Je note le zéro six …, c'est bon ? » (motif ``numero_dicte_relu`` : le numéro, puis la question). DC10 éteint : code « Je note le zéro six … . » (``numero_retenu``),
dit après la phrase du modèle, avant la suite du code (le total, le rendu, M108). Sur la vraie source et la vraie porte, sans modèle.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes import parole as PAROLE
from api.services.actions_communes.resultat import Resultat, avec_numeros_retenus
from api.services.commande import porte as PORTE
from api.services.mots_dits import numero_en_lettres
from api.services.phrases import catalogue as CAT
from api.services.phrases.regles import CLE_REGLES
from api.services.workflow import parole_de_la_fiche as PF

from .aides_de_la_commande import a_emporter, jusqu_au_recapitulatif, premier_article, refuser_la_proposition

E164 = "+33612345678"
DIT = numero_en_lettres(E164)
DC10_ETEINT = {CLE_REGLES: [{"motif": CAT.NUMERO_DICTE_RELU, "portee": "agent", "active": False}]}


def _retenus() -> list[str]:
    return [v.replace("{numero}", DIT) for v in CAT.MOTIFS["numero_retenu"].variantes_defaut]


def _manques(r: dict) -> list:
    return [x.get("manque") for x in r.get("resultats") or []]


async def _jusqu_au_numero(essai_de, appelant: bool, configurations: dict | None = None):
    e = await essai_de("casa-italia")
    if not appelant:
        e.ctx.appel = {}
    if configurations:
        e.ctx.configurations = configurations
    await a_emporter(e)
    await premier_article(e)
    await refuser_la_proposition(e)
    q = await jusqu_au_recapitulatif(e)
    await e.tour("oui c'est bon, par carte", reponse={"question_id": q["id"], "sens": "accepte"}, moyen_de_paiement="carte_bancaire")
    return e


def test_le_motif_numero_retenu_est_une_phrase_du_code_reglable_jamais_eteinte():
    m = CAT.MOTIFS.get("numero_retenu")
    assert m is not None and m.variables == ("numero",) and m.verrouille, m
    assert "numero_retenu" in CAT.PHRASES_DU_CODE
    assert len(m.variantes_defaut) >= 2 and all("{numero}" in v and not v.rstrip().endswith("?") for v in m.variantes_defaut), m.variantes_defaut


def test_le_resultat_d_un_outil_porte_le_numero_retenu_en_fait_sans_phrase():
    r = avec_numeros_retenus(Resultat("INCOMPLETE", {}, "", "prenom"), E164)
    assert r.faits["numero_retenu_dit"] == DIT and r.suggestion == "", r


async def test_la_proposition_du_numero_qui_s_affiche_est_dite_par_le_modele(essai_de):
    """Avant : code « Je note le numéro qui s'affiche, c'est bon ? » / après : le modèle la pose d'après la question née (type ``numero_affiche``), sans texte du code."""
    e = await _jusqu_au_numero(essai_de, appelant=True)
    r = e.retours[-1]
    assert "confirmer_numero" in _manques(r), r
    assert "s'affiche, c'est bon" not in json.dumps(r, ensure_ascii=False), r
    posee = CONV.question_de(e.p) or {}
    assert posee.get("type") == "numero_affiche" and posee.get("texte") == "", posee  # le registre ne garde plus de phrase du code pour cette question
    textes = e.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE) or {}
    assert not textes.get("avant") and not textes.get("suffixe"), textes


async def test_dc10_allume_le_code_relit_le_numero_dicte_avec_sa_question(essai_de):
    e = await _jusqu_au_numero(essai_de, appelant=False)
    await e.tour("Léa, au zéro six douze trente-quatre cinquante-six soixante-dix-huit", telephone="0612345678", prenom="Léa")
    r = e.retours[-1]
    assert "confirmer_numero_dicte" in _manques(r), r
    textes = e.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE) or {}
    attendue = CAT.MOTIFS[CAT.NUMERO_DICTE_RELU].variantes_defaut[0].replace("{numero}", DIT)
    assert textes.get("avant") == attendue and not any(x in str(textes) for x in _retenus()), textes  # le numéro n'est dit qu'une fois


async def test_dc10_eteint_le_code_dit_le_numero_retenu_apres_la_confirmation_du_modele_avant_m108(essai_de):
    """DC10 éteint : client « Léa, au zéro six, douze… » / modèle « C'est enregistré, prête {quand}. » + code « Je note le zéro six, douze… . » + code M108 (ordre : modèle → numéro → question)."""
    e = await _jusqu_au_numero(essai_de, appelant=False, configurations=DC10_ETEINT)
    await e.tour("Léa, au zéro six douze trente-quatre cinquante-six soixante-dix-huit", telephone="0612345678", prenom="Léa")
    r = e.retours[-1]
    assert e.p.get("enregistree"), r
    textes = e.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE) or {}
    m108 = CAT.MOTIFS[CAT.APRES_ENREGISTREMENT].variantes_defaut[0]
    assert textes.get("suffixe") in [f"{x} {m108}" for x in _retenus()], textes
    phrase = f"C'est enregistré, prête {e.p['enregistree']['quand_dit']}."
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": phrase})
    dit = d.a_dire if d.mode == PAROLE.A_DIRE_SEUL else PF.VerificateurDeLaFiche(SimpleNamespace(_gathered_context=e.fiche_de_l_appel)).controler(phrase)
    dit = dit if isinstance(dit, str) or dit is None else dit.a_dire
    assert dit == f"{phrase} {textes['suffixe']}", dit
