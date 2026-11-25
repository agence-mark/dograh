"""[.mark] Lot 7b-C6, commit 3b (décision d'Evan 25/11 9 h 30, § 8 bis ; Q2 et Q3 = A, réponses de Pierre 25/11 ~17 h 25) : la relecture de la commande passe au modèle.

Avant : code « Je vous relis : trois Margherita, à emporter. Cela fait trente euros. C'est bon ? ».
Après : modèle « Alors trois Margherita à emporter. » + code « Cela fait trente euros, c'est bon pour vous ? » (motif réglé ``total_relecture``). Le « oui » ne vaut accord que si la
phrase du total a été DITE (journal du dit, au jeton de la relecture) ; sinon la relecture reste posée et se repose. Sur la vraie source et la vraie porte, sans modèle.
"""

from __future__ import annotations

from types import SimpleNamespace

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes import parole as PAROLE
from api.services.commande import etape as ETAPE
from api.services.commande import moteur
from api.services.commande import porte as PORTE
from api.services.mots_dits import montant_en_lettres
from api.services.phrases.catalogue import MOTIFS, TOTAL_RELECTURE
from api.services.workflow import parole_de_la_fiche as PF

RELUE_PAR_LE_MODELE = "Alors trois Margherita à emporter."


async def _jusqu_a_la_relecture(essai_de):
    e = await essai_de("casa-italia")
    e.voix = False  # ce qui part à la voix est jugé ici, par la parole (``_dire``)
    r = await e.dit("trois margherita à emporter").fiche(ajouter=[{"article": "margherita", "quantite": 3, "variante": "Normale"}], mode_de_retrait="emporter")
    for _ in range(3):
        q = CONV.question_de(e.p) or {}
        if q.get("type") == "relecture":
            break
        r = await e.dit("non merci, c'est tout").fiche(c_est_tout=True, **({"reponse": {"question_id": q["id"], "sens": "refuse"}} if q else {}))
    assert (CONV.question_de(e.p) or {}).get("type") == "relecture", (CONV.question_de(e.p), r["resultats"])
    return e, r


def _phrase_du_total(e) -> str:
    total = montant_en_lettres(e.p["relecture"]["total"])
    return [v.replace("{total}", total) for v in MOTIFS[TOTAL_RELECTURE].variantes_defaut]


def _dire(e, r, phrase: str) -> str | None:
    """Ce qui part à la voix quand le modèle écrit ``phrase`` avec la fiche : dite seule, ou au second passage (le contrôle de la phrase libre)."""
    textes = dict(e.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE) or {})
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": phrase})
    e.fiche_de_l_appel[PORTE.CLE_TEXTES_DU_CODE] = textes  # gardé pour les assertions
    if d.mode == PAROLE.A_DIRE_SEUL:
        return d.a_dire
    retenue = PF.VerificateurDeLaFiche(SimpleNamespace(_gathered_context=e.fiche_de_l_appel)).controler(phrase)
    return retenue.a_dire if retenue is not None else phrase


async def test_la_relecture_rend_des_faits_et_le_code_ne_dit_que_la_phrase_du_total(essai_de):
    e, r = await _jusqu_a_la_relecture(essai_de)
    textes = e.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE) or {}
    assert not textes.get("avant"), textes  # le code ne relit plus la commande
    assert textes.get("suffixe") in _phrase_du_total(e), textes  # la phrase réglée du total, {total} remplacé, rien d'autre
    assert "Je vous relis" not in str(r), r
    assert PORTE.A_FAIRE_DE_LA_RELECTURE in str(r.get("a_faire")), r.get("a_faire")
    lignes = [l for x in r["resultats"] for l in (x.get("faits") or {}).get("lignes") or []]
    assert any(l.get("nom") and l.get("quantite") == 3 for l in lignes), r["resultats"]


async def test_la_phrase_du_modele_part_suivie_de_la_phrase_du_total_puis_le_oui_vaut_accord(essai_de):
    """Client « C'est tout. » / modèle « Alors trois Margherita à emporter. » + code « Cela fait …, c'est bon pour vous ? » / « Oui. » → accord."""
    e, r = await _jusqu_a_la_relecture(essai_de)
    dit = _dire(e, r, RELUE_PAR_LE_MODELE) or ""
    assert dit.startswith(RELUE_PAR_LE_MODELE) and any(dit.endswith(t) for t in _phrase_du_total(e)), dit
    assert moteur.relecture_entendue(e.p)
    q = CONV.question_de(e.p)
    r = await e.dit("oui").fiche(reponse={"question_id": q["id"], "sens": "accepte"})
    assert ETAPE.accord(e.p) or ETAPE.enregistree(e.p), (ETAPE.courante(e.p), r["resultats"])
    assert (CONV.question_de(e.p) or {}).get("type") != "relecture", CONV.question_de(e.p)


async def test_un_oui_sans_la_phrase_du_total_dite_ne_vaut_pas_accord(essai_de):
    """Relance échouée, phrase réglée « pas compris » : la phrase du total n'est pas partie ; le « oui » ne ferme pas la relecture."""
    e, _ = await _jusqu_a_la_relecture(essai_de)
    assert not moteur.relecture_entendue(e.p)
    q = CONV.question_de(e.p)
    r = await e.dit("oui").fiche(reponse={"question_id": q["id"], "sens": "accepte"})
    assert (CONV.question_de(e.p) or {}).get("type") == "relecture", (CONV.question_de(e.p), r["resultats"])
    assert not ETAPE.accord(e.p) and not e.p.get("enregistree"), (ETAPE.courante(e.p), r["resultats"])


async def test_une_autre_relecture_posee_demande_que_sa_phrase_du_total_soit_dite(essai_de):
    """Le total dit d'une relecture n'entend pas la suivante (un autre jeton) : un article ajouté après, le « oui » attend la nouvelle phrase du total."""
    e, r = await _jusqu_a_la_relecture(essai_de)
    _dire(e, r, RELUE_PAR_LE_MODELE)
    assert moteur.relecture_entendue(e.p)
    e.p["relecture"] = {**e.p["relecture"], "jeton": "autre"}
    assert not moteur.relecture_entendue(e.p)


def test_le_total_n_est_note_dit_que_si_sa_phrase_part_a_la_voix():
    etat = PAROLE.EtatDuTour(tour=1, total_a_dire={"jeton": "j", "texte": "Cela fait trente euros, c'est bon pour vous ?"})
    p: dict = {}
    PAROLE.noter_le_total_dit(p, etat, "Avec ça, un Coca ? Il est à deux euros.")  # un autre suffixe du tour : rien
    assert not PAROLE.total_dit(p, "j")
    PAROLE.noter_le_total_dit(p, etat, "Alors trois Margherita. Cela fait trente euros, c'est bon pour vous ?")
    assert PAROLE.total_dit(p, "j") and not PAROLE.total_dit(p, "k")


def test_la_relecture_n_est_plus_une_question_dite_par_le_code_pour_ses_lecteurs():
    """Les lecteurs de ``QUESTIONS_DITES_PAR_LE_CODE`` bougent avec elle : la relance et l'état donnent la relecture par son type, jamais par un texte ; son identité est son jeton."""
    from api.services.actions_communes.enveloppe import QUESTIONS_DITES_PAR_LE_CODE
    from api.services.actions_communes.repli import question_pour_la_relance
    from api.services.commande import etat_pour_le_modele as ETAT

    q = {"id": "Q-3", "type": "relecture", "texte": "Je vous relis : un texte d'avant.", "jeton": "j"}
    assert "relecture" not in QUESTIONS_DITES_PAR_LE_CODE
    assert "texte" not in question_pour_la_relance(q)
    assert "Je vous relis" not in ETAT._question(q)
    assert CONV.identite_de_la_question(q) != CONV.identite_de_la_question({**q, "jeton": "k"})
