"""[.mark] Chantier agent-fiable-une-passe (Evan, 17/11) : le minimum de livraison de la zone est dit dès que l'adresse est vérifiée,
pas seulement à la fin. Règle métier : la personne sait tout de suite ce qu'il faut pour être livrée, l'échange se fait en une fois.

| Test | Ce qu'il prouve |
|---|---|
| M1 | adresse retenue, panier vide, zone avec minimum : la phrase dit le minimum |
| M2 | zone sans minimum : rien n'est ajouté à la phrase |
"""

from __future__ import annotations

from api.services.commande import moteur
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_commande_kebab_sa52 import ADRESSE, Appel, kebab  # noqa: F401


async def test_m1_le_minimum_est_dit_des_l_adresse(kebab):
    await kebab.c.execute("UPDATE mark.resto_zone SET minimum = 1500 WHERE site_id = $1", kebab.a)
    a = await Appel(kebab).charger()
    await moteur.choisir_mode(a.source, a.p, a.regles, "livraison")
    r = await moteur.verifier_adresse(a.source, a.p, a.regles, ADRESSE)
    assert r.statut == "RETENU", r
    assert r.faits["minimum_dit"] == "quinze euros", r.faits  # C7a : un fait, le modèle le dit


async def test_m2_sans_minimum_rien_n_est_ajoute(kebab):
    a = await Appel(kebab).charger()
    await moteur.choisir_mode(a.source, a.p, a.regles, "livraison")
    r = await moteur.verifier_adresse(a.source, a.p, a.regles, ADRESSE)
    assert r.statut == "RETENU", r
    assert "minimum_dit" not in r.faits and "minimum" not in (r.suggestion or ""), r.faits
