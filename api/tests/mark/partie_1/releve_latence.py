"""[.mark] Chantier Partie 1, lot 5 : le relevé des requêtes et du temps par opération (le tableau « avant, après » du journal).

Pas un test du registre : une aide de mesure, jouée par ``test_l05_latence.py::test_releve_des_operations`` (marqueur ``latence``). Chaque
opération passe par la vraie porte et la vraie source (montage du banc A), sur la connexion chronométrée : requêtes, temps dans la base,
temps total, et le texte de chaque requête (pour voir ce qui est relu).
"""

from __future__ import annotations

import time
from collections import Counter
from typing import Any

from api.tests.mark.banc_a.commun import Appel


class ConnexionTracee:
    """La connexion vue par la source : compte, chronomètre et garde le début de chaque requête."""

    COMPTEES = ("fetch", "fetchrow", "fetchval", "execute", "executemany")

    def __init__(self, c):
        self._c = c
        self.requetes = 0
        self.secondes = 0.0
        self.textes: Counter = Counter()

    def remettre(self) -> None:
        self.requetes, self.secondes, self.textes = 0, 0.0, Counter()

    def __getattr__(self, nom):
        attribut = getattr(self._c, nom)
        if nom not in self.COMPTEES:
            return attribut

        async def mesure(*a, **k):
            debut = time.perf_counter()
            try:
                return await attribut(*a, **k)
            finally:
                self.requetes += 1
                self.secondes += time.perf_counter() - debut
                self.textes[" ".join(str(a[0]).split())[:90] if a else nom] += 1

        return mesure


def premier_article(monde) -> tuple[str, str]:
    """Un article de la carte sans choix obligatoire, et sa première déclinaison (le relevé ne joue pas les choix)."""
    groupes = {g.get("ref") or g.get("id"): g for g in monde.carte.get("groupes") or []}
    for p in monde.carte["produits"]:
        refs = p.get("groupes") or p.get("groupes_refs") or []
        if all(int((groupes.get(r) or {}).get("min") or 0) == 0 for r in refs) and p.get("declinaisons"):
            return p["nom"], p["declinaisons"][0]["nom"]
    p = monde.carte["produits"][0]
    return p["nom"], p["declinaisons"][0]["nom"]


async def relever(a: Appel, trace: ConnexionTracee) -> list[dict[str, Any]]:
    """Joue une commande type et rend, par opération, ``{operation, requetes, ms, ms_base, textes}``."""
    lignes: list[dict[str, Any]] = []
    nom, variante = premier_article(a.monde)

    async def op(operation: str, dit: str, **cases: Any) -> dict:
        trace.remettre()
        debut = time.perf_counter()
        r = await a.tour(dit, **cases)
        lignes.append({"operation": operation, "requetes": trace.requetes, "ms": round((time.perf_counter() - debut) * 1000, 1),
                       "ms_base": round(trace.secondes * 1000, 1), "textes": dict(trace.textes)})
        return r

    def question() -> dict:
        return a.p.get("question") or {}

    if hasattr(a, "charger"):  # le chargement de l'appel (lot 5), mesuré à part : il tourne au décroché, pendant la phrase d'accueil
        trace.remettre()
        debut = time.perf_counter()
        await a.charger()
        lignes.append({"operation": "chargement", "requetes": trace.requetes, "ms": round((time.perf_counter() - debut) * 1000, 1),
                       "ms_base": round(trace.secondes * 1000, 1), "textes": dict(trace.textes)})
    await op("mode", "à emporter", mode_de_retrait="emporter")
    await op("ajouter", f"une {nom}", ajouter=[{"article": nom, "quantite": 1, "variante": variante}])
    if question().get("type") == "proposition":
        await op("reponse", "non merci", reponse={"question_id": question()["id"], "sens": "refuse"})
    await op("ajouter_second", f"une autre {nom}", ajouter=[{"article": nom, "quantite": 1, "variante": variante}])
    if a.p["lignes"]:
        await op("changer", "finalement trois", changer_quantite=[{"ligne": a.p["lignes"][0]["n"], "quantite": 3}])
    for _ in range(3):
        q = question()
        if q.get("type") == "relecture":
            break
        await op("recapitulatif", "c'est tout", c_est_tout=True, **({"reponse": {"question_id": q["id"], "sens": "refuse"}} if q.get("id") else {}))
    q = question()
    if q.get("type") == "relecture":
        await op("accord_et_paiement", "oui c'est bon, par carte", reponse={"question_id": q["id"], "sens": "accepte"}, moyen_de_paiement="carte_bancaire")
        await op("telephone", "zéro six douze trente-quatre cinquante-six soixante-dix-huit", telephone="0612345678")
        await op("enregistrement", "Léa", prenom="Léa")
    lignes.append({"operation": "_enregistree", "requetes": int(bool(a.p.get("enregistree"))), "ms": 0, "ms_base": 0, "textes": {}})
    return lignes
