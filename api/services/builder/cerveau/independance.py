"""[.mark] Builder, U6 (D9 du 03/11) : l'indépendance du juge.

Un juge qui note son propre travail ne juge plus. Règle :

* source **clé d'API** : le juge ne peut PAS être du même modèle que l'agent jugé, ni que le builder (refus, avec la raison) ;
* source **Claude Code** : exemption. Le juge et le builder sont alors du même modèle, c'est dit (« ! » du réglage) et une
  MENTION est portée par chaque verdict, pour que personne ne prenne l'avis pour celui d'un tiers.

Pur : aucune lecture de base ici.
"""

from __future__ import annotations

from dataclasses import dataclass

MENTION_CLAUDE_CODE = "Jugé par Claude Code : même modèle que le builder, pas un avis indépendant."


@dataclass(frozen=True)
class Independance:
    refus: str | None = None
    mention: str | None = None

    @property
    def refuse(self) -> bool:
        return self.refus is not None


def _nom(modele: str | None) -> str:
    return (modele or "").strip().lower().rpartition("/")[2]


def controler(
    *, source_juge: str, modele_juge: str, modele_builder: str | None = None, modele_agent: str | None = None
) -> Independance:
    if source_juge == "claude_code":
        return Independance(mention=MENTION_CLAUDE_CODE)
    juge = _nom(modele_juge)
    if juge and juge == _nom(modele_agent):
        return Independance(refus="The judge cannot be the same model as the judged agent: pick another model.")
    if juge and juge == _nom(modele_builder):
        return Independance(refus="The judge cannot be the same model as the builder: pick another model.")
    return Independance()


async def modele_du_builder(user) -> str | None:
    """Le modèle réglé pour le builder (``None`` s'il n'est pas réglé ou illisible : pas de refus sur ce motif)."""
    from api.services.builder.cerveau import reglages

    try:
        return (await reglages.lire(await reglages.organisation_des_reglages(user))).modele or None
    except Exception:  # noqa: BLE001
        return None
