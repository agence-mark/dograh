"""[.mark] Chantier fiabilite-orchestration, lot 3 (F5, F6, R17) : le préchauffage hybride.

Au 1464, la passation construisait le collègue (service de modèle, worker) pendant que l'appelant
attendait : environ 1 s (outil 42,73 → agent installé 43,80), alors que le préchauffage d'avant
annonçait « 6/6 agents chargés à l'avance » (il chargeait les définitions, pas les services).

Deux mécanismes, et le libre choix des cerveaux reste entier :

1. **La réserve** (``Precharge.prets``, sur le cache de l'appel ; ``PipecatEngine._mettre_en_reserve``) : au décroché, pendant l'accueil,
   chaque collègue du graphe est **construit à l'avance** (son service de modèle, son worker inactif
   sous l'appel, son cerveau de fond s'il est allumé : F6). La passation le prend dans la réserve au
   lieu de le construire ; un collègue pris est reconstruit en fond pour la passation suivante.
   Échec de la construction : la passation construit comme avant.
2. **Le poste partagé** (``Postes``, posé sur la fabrique) : un service de modèle ne peut tenir que
   dans un seul circuit (un processeur Pipecat n'a qu'une place) ; ce qui se partage entre deux
   agents au même cerveau, c'est **la connexion** au fournisseur (le client HTTP, son pool déjà
   ouvert). Deux services qui visent la même adresse avec la même clé gardent le même client : la
   première requête d'un collègue ne rouvre aucune connexion. Contexte, outils et réglages restent
   propres à chaque agent (chacun a son service).

La mémoire du processus est relevée à chaque passation (``memoire_du_processus_mo``).
⛔ Ne lève jamais : un préchauffage ne coûte jamais l'appel. Aucun mot de métier.
"""

from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

from loguru import logger


def cle_du_poste(llm: Any) -> tuple[str, str, str] | None:
    """(classe du client, adresse, empreinte de la clé) du client HTTP de ``llm`` ; ``None`` sans
    client lisible. La clé n'est jamais gardée en clair."""
    try:
        client = getattr(llm, "_client", None)
        if client is None:
            return None
        adresse = str(getattr(client, "base_url", "") or "")
        cle = str(getattr(client, "api_key", "") or "")
        empreinte = hashlib.sha256(cle.encode("utf-8")).hexdigest()[:16] if cle else ""
        return (type(client).__name__, adresse, empreinte)
    except Exception:  # noqa: BLE001
        return None


class Postes:
    """Les connexions ouvertes de l'appel, une par (adresse, clé)."""

    def __init__(self, noter: Callable[[dict], None] | None = None) -> None:
        self._clients: dict[tuple[str, str, str], Any] = {}
        self.partages = 0
        # Lot 9 de fiabilite-orchestration (F11) : chaque connexion ouverte ou reprise est notée
        # (``noter``), pour lire dans le run lesquelles ont servi. Jamais la clé : l'hôte seulement.
        self._noter = noter
        self._depart = time.monotonic()

    def _noter_la_connexion(self, evenement: str, cle: tuple[str, str, str], agent: str | None) -> None:
        if self._noter is None:
            return
        try:
            self._noter(
                {
                    "event": evenement,
                    "agent": agent,
                    "host": urlparse(cle[1]).hostname or None,
                    "after_secs": round(time.monotonic() - self._depart, 3),
                }
            )
        except Exception:  # noqa: BLE001 -- une mesure n'emporte pas l'appel
            pass

    def enregistrer(self, llm: Any, agent: str | None = None) -> None:
        cle = cle_du_poste(llm)
        if cle is not None and cle not in self._clients:
            self._clients[cle] = llm._client
            self._noter_la_connexion("opened", cle, agent)

    def partager(self, llm: Any, agent: str | None = None) -> bool:
        """Donne à ``llm`` le client déjà ouvert pour la même adresse et la même clé, sinon
        l'enregistre. ``True`` si une connexion a été partagée. ⛔ Ne lève jamais."""
        try:
            cle = cle_du_poste(llm)
            if cle is None:
                return False
            client = self._clients.get(cle)
            if client is None:
                self._clients[cle] = llm._client
                self._noter_la_connexion("opened", cle, agent)
                return False
            if client is not llm._client:
                llm._client = client
                self.partages += 1
                self._noter_la_connexion("reused", cle, agent)
                return True
            return False
        except Exception as erreur:  # noqa: BLE001
            logger.warning(f"[prechauffage] poste non partagé : {erreur!r}")
            return False


def postes_de(moteur: Any) -> Postes | None:
    """Les postes de l'appel (sur la fabrique d'agents), ``None`` sans fabrique."""
    try:
        fabrique = (getattr(moteur, "__dict__", None) or {}).get("_agent_factory")
        postes = (getattr(fabrique, "__dict__", None) or {}).get("postes")
        return postes if isinstance(postes, Postes) else None
    except Exception:  # noqa: BLE001
        return None


def memoire_du_processus_mo() -> float | None:
    """La mémoire résidente du processus, en Mo (Linux : ``/proc/self/statm``). ``None`` ailleurs."""
    try:
        with open("/proc/self/statm", encoding="ascii") as statm:
            pages = int(statm.read().split()[1])
        return round(pages * os.sysconf("SC_PAGE_SIZE") / (1024 * 1024), 1)
    except Exception:  # noqa: BLE001
        return None
