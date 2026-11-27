"""[.mark] Plan final Partie 1, lot 8b-1b (T13, R2 de l'audit 7c ; E-2) : l'adresse, la note et la consigne au livreur changées après le « oui » réécrivent la commande
en base au tour même ; la caisse ne reçoit rien pendant l'appel (§ 17 l.404) et reçoit, à la fin de l'appel, UN envoi qui les porte. Un changement d'adresse donne au modèle
l'adresse dans les faits du changement et l'exige de sa phrase (E-2 ; aucun nouvel accord). Report du test rouge de ``a24c06c0``, adapté au § 17 ; son 4ᵉ test (caisse qui ne
sait pas annuler) est sans objet (§ 17 l.404)."""

from __future__ import annotations

ADRESSE_1 = {"adresse": "12 rue de la République", "commune": "Senlis"}
ADRESSE_2 = {"adresse": "3 rue de Paris", "commune": "Senlis"}


def _voie(adresse) -> str:
    return str((adresse or {}).get("voie") or (adresse or {}).get("adresse") or adresse or "") if isinstance(adresse, dict) else str(adresse or "")


async def _livree_au_12(faire_monde, monkeypatch):
    from api.tests.mark.partie_1 import combinaisons as C

    monde = await faire_monde("casa-italia")
    partie = C.Partie(monde, monkeypatch)
    assert await partie.recette("E16")
    o = await partie._executer("L", "finalement en livraison au 12 rue de la République à Senlis", {"mode_de_retrait": "livraison", **ADRESSE_1}, C._inchange)
    assert o.base and o.base.get("mode") == "livraison" and "12" in _voie(o.base.get("adresse")), (o.base or {}).get("adresse")
    return C, partie


async def _un_envoi_a_la_fin(partie) -> dict:
    assert partie.e.source.prise.recues == [], "rien en caisse pendant l'appel (§ 17)"
    assert await partie.finir_l_appel() == []
    recues = partie.e.source.prise.recues
    assert len(recues) == 1, recues
    return recues[0]


async def test_r2_une_adresse_changee_sur_une_commande_enregistree_est_reecrite_en_base_et_part_a_la_fin(faire_monde, monkeypatch):
    """Client (commande enregistrée, livrée au 12 rue de la République à Senlis) « Non, c'est au 3 rue de Paris. » / avant : le panier a la nouvelle adresse, la base et la caisse
    gardent le 12, le livreur va au 12 / après : la base a le 3 rue de Paris au tour même, le modèle dit l'adresse (« C'est noté, au 3 rue de Paris. »), la caisse reçoit le 3 à la fin."""
    C, partie = await _livree_au_12(faire_monde, monkeypatch)
    o = await partie._executer("A", "non, c'est au 3 rue de Paris à Senlis", ADRESSE_2, C._inchange)
    assert "3 rue de Paris" in _voie(o.apres.get("adresse")), o.apres.get("adresse")
    assert "3 rue de Paris" in _voie((o.base or {}).get("adresse")), (o.base or {}).get("adresse")
    assert "3 rue de Paris" in str((o.textes or {}).get("fait_accompli")), o.textes  # E-2 : les faits du changement portent l'adresse
    assert "3" in str(((o.textes or {}).get("chiffres_exiges") or {}).get("adresse") or ""), o.textes  # E-2 : exigée de la phrase du modèle
    recue = await _un_envoi_a_la_fin(partie)
    assert "3 rue de Paris" in _voie(recue.get("adresse")), recue.get("adresse")


async def test_r2_une_note_changee_sur_une_commande_enregistree_est_reecrite_en_base_et_part_a_la_fin(faire_monde, monkeypatch):
    """R2, la note : Client (commande enregistrée) « Bien cuite, s'il vous plaît. » / avant : la note reste au panier, la caisse ne la reçoit pas / après : la base l'a au tour
    même, la caisse la reçoit à la fin."""
    C, partie = await _livree_au_12(faire_monde, monkeypatch)
    o = await partie._executer("N", "bien cuite s'il vous plaît", {"note_generale": "bien cuite"}, C._inchange)
    assert "bien cuite" in str(o.apres.get("note") or ""), o.apres.get("note")
    assert "bien cuite" in str((o.base or {}).get("note") or ""), (o.base or {}).get("note")
    recue = await _un_envoi_a_la_fin(partie)
    assert "bien cuite" in str(recue.get("note") or ""), recue.get("note")


async def test_r2_une_consigne_au_livreur_changee_sur_une_commande_enregistree_est_reecrite_en_base_et_part_a_la_fin(faire_monde, monkeypatch):
    """R2, la consigne pour le livreur (envoyée à la caisse avec la note) : Client « Sonnez deux fois. » / après : la base l'a au tour même, la caisse à la fin."""
    C, partie = await _livree_au_12(faire_monde, monkeypatch)
    o = await partie._executer("CL", "sonnez deux fois", {"consigne_livreur": "sonnez deux fois"}, C._inchange)
    assert "sonnez deux fois" in str((o.base or {}).get("consigne_livreur") or "") + str((o.base or {}).get("note") or ""), o.base
    recue = await _un_envoi_a_la_fin(partie)
    assert "sonnez deux fois" in str(recue.get("consigne_livreur") or "") + str(recue.get("note") or ""), recue
