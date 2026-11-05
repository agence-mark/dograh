"""[.mark] Builder partie 3, sous-lot 6 (SE-11 = D-3, audit 12 § 3) : le SERVICE D'ALERTES UNIQUE d'un agent, et le rejeu planifié.

Un seul endroit où une alerte « d'agent » (au sens d'un agent en ligne dans la durée, pas d'un appel) naît, se règle, se range, se
notifie : ``types`` (les types, leurs seuils par défaut), ``reglages`` (les réglages de l'agent), ``service`` (évaluer, ranger,
notifier). Le premier type est « une version fait moins bien que la précédente » (``regression``). Les autres types prévus par
l'audit (hausse des échecs du juge, des transferts, des garde-fous, des pannes, de la latence) s'ajouteront au registre ``TYPES``,
sans mécanisme de plus. Les alertes d'UN appel (``services/tri/alertes.py``) restent à part : elles disent le problème du client.

Jamais de bascule automatique : une alerte dit et pointe, elle ne publie, ne retire ni ne change rien d'un agent.
"""
