"""[.mark] Mécanisme commun : les montants dits en toutes lettres et les petites phrases proposées par la commande.

Les phrases sont PROPOSÉES (``suggestion``) : le réglage de l'outil dit si le modèle les prononce mot pour mot ou les reformule
(T-01). Les montants sont toujours dits en toutes lettres (« vingt-trois euros quatre-vingts »), jamais en chiffres à lire.
"""

from __future__ import annotations


def _lettres(n: int) -> str:
    try:
        from num2words import num2words  # dépendance de Pipecat, chargée à la demande comme ``services/nombres/voix.py``

        return num2words(n, lang="fr")
    except Exception:  # noqa: BLE001 -- un nombre qu'on ne sait pas écrire reste en chiffres plutôt que de casser l'appel
        return str(n)


def montant_en_lettres(centimes: int) -> str:
    """``2380`` -> « vingt-trois euros quatre-vingts » ; ``1000`` -> « dix euros » ; ``50`` -> « cinquante centimes »."""
    euros, reste = divmod(max(int(centimes), 0), 100)
    morceaux = []
    if euros or not reste:
        morceaux.append(f"{_lettres(euros)} euro{'s' if euros > 1 else ''}")
    if reste:
        morceaux.append(_lettres(reste) if euros else f"{_lettres(reste)} centimes")
    return " ".join(morceaux)


def heure_en_lettres(heure: int, minute: int) -> str:
    """``(20, 15)`` -> « vingt heures quinze » ; ``(12, 0)`` -> « douze heures »."""
    base = f"{_lettres(heure)} heure{'s' if heure > 1 else ''}"
    return f"{base} {_lettres(minute)}" if minute else base


def liste_dite(elements: list[str]) -> str:
    """``["a", "b", "c"]`` -> « a, b ou c »."""
    if len(elements) <= 1:
        return "".join(elements)
    return ", ".join(elements[:-1]) + " ou " + elements[-1]


def liste_dite_et(elements: list[str]) -> str:
    """``["a", "b", "c"]`` -> « a, b et c »."""
    if len(elements) <= 1:
        return "".join(elements)
    return ", ".join(elements[:-1]) + " et " + elements[-1]
