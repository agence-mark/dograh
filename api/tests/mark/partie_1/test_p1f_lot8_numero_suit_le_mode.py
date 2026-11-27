"""[.mark] Plan final Partie 1, reprise R1 de l'audit de 8b-1b : avec ``numero_mode = "type"``, la commande ``retenue`` réécrite après le « oui » dans un autre mode garde
son compteur et prend le préfixe de son nouveau mode (L, E, S) ; le numéro ayant changé, le code dit le nouveau avec la phrase réglée du numéro de commande (choix prudent du
coordinateur, 27/11 1 h 54, à confirmer par Pierre). Un changement qui garde le mode ne dit aucun numéro.

| Test | Ce qu'il prouve |
|---|---|
| à emporter puis livraison | base et ``faits.numero_court`` passent de E à L, même compteur ; le code dit le nouveau numéro ; la caisse reçoit L à la fin |
| même mode | le numéro ne bouge pas et le code ne dit aucun numéro |
"""

from __future__ import annotations

from api.tests.mark.partie_1 import combinaisons as C

ADRESSE = {"adresse": "3 rue de Paris", "commune": "Senlis"}


async def _a_emporter_numerote_par_type(faire_monde, monkeypatch) -> tuple[C.Partie, str]:
    monde = await faire_monde("casa-italia")
    await monde.c.execute("UPDATE mark.resto_reglage SET numero_mode = 'type' WHERE site_id = $1", monde.a)
    partie = C.Partie(monde, monkeypatch)
    assert await partie.recette("E16")
    numero = str((partie.p.get("enregistree") or {}).get("numero_court") or "")
    assert numero.startswith("E"), numero
    return partie, numero


async def test_r1_a_emporter_puis_livre_le_numero_prend_le_prefixe_de_la_livraison_et_le_code_le_dit(faire_monde, monkeypatch):
    """Client « Oui, c'est bon. » (à emporter, E12) … « Finalement, livrez-moi au 3 rue de Paris. » / avant : le ticket dit E12 pour une livraison, le client garde E12 /
    après : modèle « C'est noté, livré au 3 rue de Paris. » puis code « Votre numéro de commande devient L12. » ; base, faits et caisse portent L12."""
    partie, numero = await _a_emporter_numerote_par_type(faire_monde, monkeypatch)
    nouveau = "L" + numero[1:]
    o = await partie._executer("L", "finalement livrez-moi au 3 rue de Paris à Senlis", {"mode_de_retrait": "livraison", **ADRESSE}, C._inchange)
    assert (o.base or {}).get("mode") == "livraison", (o.base or {}).get("mode")
    assert (o.base or {}).get("numero_court") == nouveau, (o.base or {}).get("numero_court")
    assert (o.apres.get("enregistree") or {}).get("numero_court") == nouveau, o.apres.get("enregistree")
    assert nouveau in o.dit_par_le_code, o.textes
    assert await partie.finir_l_appel() == []
    recues = partie.e.source.prise.recues
    assert [r.get("numero_court") for r in recues] == [nouveau], recues


async def test_r1_un_changement_dans_le_meme_mode_garde_le_numero_et_ne_le_redit_pas(faire_monde, monkeypatch):
    """Voisin : Client (à emporter, E12) « Encore une margherita normale. » / le numéro reste E12, le code ne dit aucun numéro (rien n'a changé pour le client)."""
    partie, numero = await _a_emporter_numerote_par_type(faire_monde, monkeypatch)
    o = await partie.geste("G6")
    assert o is not None and (o.base or {}).get("numero_court") == numero, (o.base or {}).get("numero_court") if o else None
    assert numero not in o.dit_par_le_code, o.textes


async def test_le_numero_change_la_consigne_dit_au_modele_de_ne_pas_le_dire_le_code_le_dit_une_seule_fois(faire_monde, monkeypatch):
    """Audit 8b-1b, mineur 1 (8b-2) : Client (à emporter, E12) « Finalement, livrez-moi au 3 rue de Paris. » / avant : la consigne « dis que la commande est changée » ne défendait pas
    au modèle de dire le numéro, qui pouvait le redire avant le code : « L12 » entendu deux fois / après : la consigne dit « sans numéro de commande », le code dit L12 une fois."""
    partie, numero = await _a_emporter_numerote_par_type(faire_monde, monkeypatch)
    o = await partie._executer("L", "finalement livrez-moi au 3 rue de Paris à Senlis", {"mode_de_retrait": "livraison", **ADRESSE}, C._inchange)
    assert "sans numéro de commande" in str((o.retour or {}).get("a_faire") or ""), (o.retour or {}).get("a_faire")
    assert o.dit_par_le_code.count("L" + numero[1:]) == 1, o.dit_par_le_code


async def test_le_numero_ne_change_pas_la_consigne_ne_parle_pas_du_numero(faire_monde, monkeypatch):
    partie, _ = await _a_emporter_numerote_par_type(faire_monde, monkeypatch)
    o = await partie.geste("G6")
    assert "numéro de commande" not in str((o.retour or {}).get("a_faire") or ""), (o.retour or {}).get("a_faire")
