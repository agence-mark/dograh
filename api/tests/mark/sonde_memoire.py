"""[.mark] Sonde mémoire de la CI comparée : plafond par processus, arrêt net en nommant le test.

Plugin pytest, chargé à la demande par ``-p sonde_memoire`` (la CI met ``api/tests/mark`` du
checkout de la BRANCHE dans ``PYTHONPATH`` : le passage joué sur la base ne contient pas ce fichier).

Pourquoi (20/10/2026) : une veille de tâche de fond sur un faux moteur, jamais close, a tourné à
vide sous un ``asyncio.sleep`` remplacé par un test de l'amont et porté le processus à plus de
100 Go ; le runner a été coupé à 21 min sans dire pourquoi. Ici, un fil lit ``VmRSS`` dans
``/proc/self/status`` toutes les 0,5 s ; au-delà du plafond (6 Go, décision D4), il écrit le test en
cours dans le fichier d'état puis tue le processus (``os._exit``) : un fil indépendant, parce qu'une
boucle asyncio saturée ne laisse plus la main à un crochet pytest.

Le fichier d'état est lu par ``api/scripts/mark/comparer_echecs.py`` (lecture indépendante du code
de sortie de pytest et du rapport JUnit, réflexe R7) : plafond dépassé, session non terminée ou
moins de tests relus que de tests collectés = « passage incomplet », jamais un vert par défaut.

Hors Linux (Windows, macOS) il n'existe pas de ``/proc`` : la sonde s'ignore, sans rien écrire.

Réglages (variables d'environnement) : ``MARK_SONDE_PLAFOND_MO`` (défaut 6144),
``MARK_SONDE_FICHIER`` (défaut ``sonde-memoire.json`` dans le dossier courant).
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from collections.abc import Callable

PLAFOND_PAR_DEFAUT_MO = 6144
INTERVALLE_S = 0.5
# Écriture périodique de l'état : si le runner tue le processus de l'extérieur (mémoire du
# système, délai), la dernière écriture nomme encore le test en cours.
ECRITURE_TOUTES_LES_S = 2.0
CODE_SORTIE_PLAFOND = 86
FICHIER_PAR_DEFAUT = "sonde-memoire.json"
STATUT_PROC = "/proc/self/status"


def actif(plateforme: str | None = None) -> bool:
    """Vrai seulement sous Linux : ``/proc/self/status`` n'existe pas ailleurs."""
    return (plateforme if plateforme is not None else sys.platform).startswith("linux")


def lire_rss_mo(chemin: str = STATUT_PROC) -> float | None:
    """Mémoire résidente (``VmRSS``) en Mo, ou ``None`` si elle ne se lit pas."""
    try:
        with open(chemin, encoding="utf-8") as f:
            for ligne in f:
                if ligne.startswith("VmRSS:"):
                    # « VmRSS:     123456 kB »
                    return int(ligne.split()[1]) / 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


class Sonde:
    """État de la session et surveillance du plafond. ``lire`` et ``sortir`` sont injectables."""

    def __init__(
        self,
        plafond_mo: float = PLAFOND_PAR_DEFAUT_MO,
        fichier: str = FICHIER_PAR_DEFAUT,
        lire: Callable[[], float | None] = lire_rss_mo,
        sortir: Callable[[int], None] = os._exit,
    ) -> None:
        self.plafond_mo = plafond_mo
        self.fichier = fichier
        self._lire = lire
        self._sortir = sortir
        self.test_en_cours: str | None = None
        self.collecte: int | None = None
        self.pic_mo = 0.0
        self.plafond_depasse = False
        self.termine = False
        self.statut_pytest: int | None = None
        self._arret = threading.Event()
        self._fil: threading.Thread | None = None
        self._verrou = threading.Lock()

    def etat(self) -> dict:
        return {
            "plafond_mo": self.plafond_mo,
            "pic_mo": round(self.pic_mo, 1),
            "plafond_depasse": self.plafond_depasse,
            "test_en_cours": self.test_en_cours,
            "collecte": self.collecte,
            "termine": self.termine,
            "statut_pytest": self.statut_pytest,
        }

    def ecrire(self) -> None:
        """Écriture atomique (fichier voisin puis remplacement) : jamais un état à moitié écrit."""
        with self._verrou:
            temporaire = f"{self.fichier}.tmp"
            try:
                with open(temporaire, "w", encoding="utf-8") as f:
                    json.dump(self.etat(), f)
                os.replace(temporaire, self.fichier)
            except OSError:
                pass  # une sonde ne fait jamais tomber la suite

    def echantillonner(self) -> bool:
        """Une lecture. Rend vrai (et arrête le processus) si le plafond est dépassé."""
        rss = self._lire()
        if rss is None:
            return False
        self.pic_mo = max(self.pic_mo, rss)
        if rss <= self.plafond_mo:
            return False
        self.plafond_depasse = True
        self.ecrire()
        message = (
            f"\n[sonde memoire] PLAFOND DEPASSE : {rss:.0f} Mo > {self.plafond_mo:.0f} Mo "
            f"pendant le test {self.test_en_cours or '(hors test : collecte ou fin de session)'}. "
            "Arret net du processus.\n"
        )
        try:
            os.write(2, message.encode("utf-8", "replace"))
        except OSError:
            pass
        self._sortir(CODE_SORTIE_PLAFOND)
        return True

    def _boucle(self) -> None:
        derniere_ecriture = 0.0
        while not self._arret.wait(INTERVALLE_S):
            if self.echantillonner():
                return
            maintenant = time.monotonic()
            if maintenant - derniere_ecriture >= ECRITURE_TOUTES_LES_S:
                self.ecrire()
                derniere_ecriture = maintenant

    def demarrer(self) -> None:
        self.echantillonner()  # une première lecture tout de suite : une session courte a un pic
        self.ecrire()
        self._fil = threading.Thread(
            target=self._boucle, name="sonde-memoire", daemon=True
        )
        self._fil.start()

    def arreter(self) -> None:
        self.echantillonner()  # dernière lecture : le pic compte jusqu'à la fin de la session
        self._arret.set()
        if self._fil is not None:
            self._fil.join(timeout=2)


_SONDE: Sonde | None = None


def pytest_configure(config) -> None:
    global _SONDE
    if not actif():
        return
    plafond = float(os.environ.get("MARK_SONDE_PLAFOND_MO", PLAFOND_PAR_DEFAUT_MO))
    fichier = os.environ.get("MARK_SONDE_FICHIER", FICHIER_PAR_DEFAUT)
    _SONDE = Sonde(plafond_mo=plafond, fichier=fichier)
    _SONDE.demarrer()


def pytest_collection_finish(session) -> None:
    if _SONDE is not None:
        _SONDE.collecte = len(session.items)
        _SONDE.ecrire()


def pytest_runtest_logstart(nodeid, location) -> None:
    if _SONDE is not None:
        _SONDE.test_en_cours = nodeid


def pytest_sessionfinish(session, exitstatus) -> None:
    if _SONDE is not None:
        _SONDE.statut_pytest = int(exitstatus)


def pytest_unconfigure(config) -> None:
    """Dernier crochet : le rapport JUnit est écrit (``sessionfinish`` de ``junitxml`` est passé)."""
    global _SONDE
    if _SONDE is None:
        return
    _SONDE.arreter()
    _SONDE.termine = True
    _SONDE.ecrire()
    _SONDE = None
