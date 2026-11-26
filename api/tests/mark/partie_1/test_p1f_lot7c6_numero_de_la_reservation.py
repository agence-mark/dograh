"""[.mark] Lot 7b-C6, reprise R4 de l'audit (§ 8 bis, décision d'Evan 25/11 9 h 30 : le numéro reste au code ; aligné sur la commande du n° 10) : réservation, DC10 éteint.

Le numéro dicté et retenu est porté jusqu'à l'enregistrement ; le code dit le motif réglé ``numero_retenu`` après le fait accompli du modèle. Avant : modèle « C'est réservé samedi à
vingt heures pour quatre. » sans numéro (jamais dit de l'appel) / après : + code « Je note le zéro six, dix… ». DC10 allumé : la question réglée l'a déjà relu, il n'est pas redit.
Vraie source, vraie porte, sans modèle.
"""

from __future__ import annotations

from api.services.actions_communes import parole as PAROLE
from api.services.mots_dits import numero_en_lettres
from api.services.phrases import catalogue as CAT
from api.services.phrases.regles import CLE_REGLES
from api.services.reservation import porte as PORTE
from api.services.workflow import parole_de_la_fiche as PF
from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.partie_1.aides_de_la_reservation import salle  # noqa: F401

MOTS = "une table pour quatre samedi à vingt heures au nom de Paul"
DC10_ETEINT = {CLE_REGLES: [{"motif": CAT.NUMERO_DICTE_RELU, "portee": "agent", "active": False}]}
DIT = numero_en_lettres("+33610203040")
RESERVEE = "C'est noté, je vous attends samedi à vingt heures pour quatre."


def _retenus() -> list[str]:
    return [v.replace("{numero}", DIT) for v in CAT.MOTIFS[CAT.NUMERO_RETENU].variantes_defaut]


async def _reservee(salle, monkeypatch, configurations: dict | None = None, appelant: str | None = None) -> tuple[EssaiReservation, dict]:
    essai = EssaiReservation(salle, monkeypatch, appelant=appelant)
    if configurations:
        essai.ctx.configurations = configurations
    await essai.tour(MOTS, personnes=4, jour="samedi", heure="vingt heures", nom="Paul")
    r = await essai.tour("au zéro six dix vingt trente quarante", telephone="0610203040")
    assert (r.get("question") or {}).get("type") == "recapitulatif", r
    r = await essai.tour("oui", reponse={"question_id": r["question"]["id"], "sens": "accepte"})
    assert r["statut"] == "ENREGISTREE", r
    return essai, r


def _textes(essai) -> dict:
    return dict(essai.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE) or {})


async def test_dc10_eteint_le_numero_dicte_est_dit_apres_le_fait_accompli_du_modele(salle, monkeypatch):
    essai, r = await _reservee(salle, monkeypatch, DC10_ETEINT)
    suffixe = _textes(essai).get("suffixe")
    assert suffixe in _retenus(), _textes(essai)
    d = PF.decider_apres_la_fiche(essai.fiche_de_l_appel, r, {"a_dire": RESERVEE}, connecteur="reservation")
    assert d.mode == PAROLE.A_DIRE_SEUL and d.a_dire == f"{RESERVEE} {suffixe}", d  # l'ordre : modèle, puis numéro


async def test_voisin_dc10_allume_le_numero_deja_relu_n_est_pas_redit(salle, monkeypatch):
    essai, _ = await _reservee(salle, monkeypatch)
    assert not _textes(essai).get("suffixe"), _textes(essai)


async def test_voisin_le_numero_qui_s_affiche_n_est_jamais_dit(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    essai.ctx.configurations = DC10_ETEINT
    r = await essai.tour(MOTS, personnes=4, jour="samedi", heure="vingt heures", nom="Paul")
    r = await essai.tour("oui", reponse={"question_id": r["question"]["id"], "sens": "accepte"})
    assert r["statut"] == "ENREGISTREE", r
    assert not _textes(essai).get("suffixe"), _textes(essai)
