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
from api.tests.mark import test_base_client as _BASE
from api.tests.mark.partie_1 import aides_de_la_reservation as _RESA

base_essai, base_prete, salle = _BASE.base_essai, _BASE.base_prete, _RESA.salle  # les fixtures de la base et de la salle, reprises sans import nu

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


async def test_numero_dicte_a_l_enregistrement_le_numero_qui_s_affiche_n_est_pas_tenu_pour_garde(salle, monkeypatch):
    """Risque 6 des reprises de C6 : à l'enregistrement, le brouillon est retiré de l'état ; ``reserver`` le relisait vide et tenait le numéro qui s'affiche pour gardé alors qu'un
    autre numéro a été dicté. Défaut sans effet entendu aujourd'hui (``avec_numero_affiche`` ne touche pas un statut final) : le test regarde ce que ``reserver`` tient pour gardé."""
    from api.services.reservation import moteur

    gardes: list[tuple[str, str | None]] = []
    vrai = moteur.avec_numero_affiche

    def espion(r, affiche):
        gardes.append((r.statut, affiche))
        return vrai(r, affiche)

    monkeypatch.setattr(moteur, "avec_numero_affiche", espion)
    await _reservee(salle, monkeypatch, DC10_ETEINT, appelant="+33699887766")
    assert [s for s, _ in gardes if s == "ENREGISTREE"] == [], gardes  # gardé au premier tour (rien de dicté), jamais après la dictée


async def test_voisin_sans_numero_dicte_le_numero_qui_s_affiche_reste_garde(salle, monkeypatch):
    from api.services.reservation import moteur

    gardes: list[str] = []
    vrai = moteur.avec_numero_affiche
    monkeypatch.setattr(moteur, "avec_numero_affiche", lambda r, affiche: (gardes.append(r.statut), vrai(r, affiche))[1])
    essai = EssaiReservation(salle, monkeypatch, appelant="+33699887766")
    r = await essai.tour(MOTS, personnes=4, jour="samedi", heure="vingt heures", nom="Paul")
    assert r["faits"].get("numero_affiche_dit"), r["faits"]  # M98 : gardé, porté dans les faits de la relecture
    r = await essai.tour("oui", reponse={"question_id": r["question"]["id"], "sens": "accepte"})
    assert r["statut"] == "ENREGISTREE" and gardes, (r, gardes)
