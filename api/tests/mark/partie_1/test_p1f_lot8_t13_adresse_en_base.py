"""[.mark] Lot 7c, second passage de l'audit (coordinateur 26/11 14 h 25) : R2 (l'adresse et la note d'une commande enregistrée partent en caisse), R3 (la question
d'étape d'une formule tombe avec elle) et le juge ``rc_base`` renforcé (a) à (d), vu rouge sur R1 et R2 remis par mutation."""

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


async def test_r2_une_adresse_changee_sur_une_commande_enregistree_part_en_caisse(faire_monde, monkeypatch):
    """Audit 7c, R2 (RC2) : l'empreinte ne lit pas l'adresse ; la porte n'envoyait le changement que si l'empreinte changeait. Client (commande enregistrée, livrée au 12 rue de la
    République à Senlis) « Non, c'est au 3 rue de Paris. » / avant : le panier a la nouvelle adresse, le retour dit FAIT, la base et la caisse gardent le 12 / après : le changement part
    en caisse, la base et la caisse ont le 3 rue de Paris."""
    C, partie = await _livree_au_12(faire_monde, monkeypatch)
    o = await partie._executer("A", "non, c'est au 3 rue de Paris à Senlis", ADRESSE_2, C._inchange)
    assert "3 rue de Paris" in _voie(o.apres.get("adresse")), o.apres.get("adresse")
    assert "3 rue de Paris" in _voie((o.base or {}).get("adresse")), (o.base or {}).get("adresse")
    assert "3 rue de Paris" in _voie((o.prise or {}).get("adresse")), (o.prise or {}).get("adresse")


async def test_r2_une_note_changee_sur_une_commande_enregistree_part_en_caisse(faire_monde, monkeypatch):
    """R2, la note : Client (commande enregistrée) « Bien cuite, s'il vous plaît. » / avant : la note reste au panier, la caisse ne la reçoit pas / après : la base et la caisse l'ont."""
    C, partie = await _livree_au_12(faire_monde, monkeypatch)
    o = await partie._executer("N", "bien cuite s'il vous plaît", {"note_generale": "bien cuite"}, C._inchange)
    assert "bien cuite" in str(o.apres.get("note") or ""), o.apres.get("note")
    assert "bien cuite" in str((o.base or {}).get("note") or ""), (o.base or {}).get("note")
    assert "bien cuite" in str((o.prise or {}).get("note") or ""), (o.prise or {}).get("note")


async def test_r2_une_consigne_au_livreur_changee_sur_une_commande_enregistree_part_en_caisse(faire_monde, monkeypatch):
    """R2, la consigne pour le livreur (envoyée à la caisse avec la note) : Client « Sonnez deux fois. » / après : la base l'a."""
    C, partie = await _livree_au_12(faire_monde, monkeypatch)
    o = await partie._executer("CL", "sonnez deux fois", {"consigne_livreur": "sonnez deux fois"}, C._inchange)
    assert "sonnez deux fois" in str((o.base or {}).get("consigne_livreur") or "") + str((o.base or {}).get("note") or ""), o.base


async def test_r2_une_adresse_changee_refusee_par_la_caisse_revient_et_le_dit(faire_monde, monkeypatch):
    """R2, le refus : la caisse ne sait pas annuler. Client « Non, c'est au 3 rue de Paris. » / avant : FAIT, le panier au 3, la caisse au 12 / après : le panier revient au 12 (ce
    que la caisse a), le retour dit le changement refusé (jamais fait sans la caisse)."""
    C, partie = await _livree_au_12(faire_monde, monkeypatch)
    partie.e.source.permet_l_annulation = lambda: False
    o = await partie._executer("A", "non, c'est au 3 rue de Paris à Senlis", ADRESSE_2, C._inchange)
    ops = {x.get("operation"): x for x in (o.retour or {}).get("resultats") or []}
    assert (ops.get("changer_la_commande_enregistree") or {}).get("faits", {}).get("raison") == "changement_impossible", ops
    assert "12" in _voie(o.apres.get("adresse")) and "12" in _voie((o.base or {}).get("adresse")), (o.apres.get("adresse"), (o.base or {}).get("adresse"))
