"""[.mark] Une conversion de document dans un processus à part, qu'on peut ARRÊTER (constat C11, revue R3 de la partie 1).

Avant : la conversion PDF / Word tournait dans un fil (``asyncio.to_thread``) ; au-delà du délai, on cessait de l'attendre mais
le fil, lui, ne se tue pas : il continuait de consommer le processeur de l'API jusqu'à la fin. Ici, la fonction tourne dans un
processus enfant ; au-delà du délai, il est **arrêté** (``terminate`` puis ``kill``) et le délai est dit en clair.

La fonction et ses arguments doivent pouvoir passer d'un processus à l'autre (fonction de module, octets, textes). Une erreur
levée dans l'enfant est relevée dans le parent avec son type d'origine quand c'est une ``ValueError`` (la raison d'un fichier
illisible), et en ``RuntimeError`` sinon (jamais de trace de l'enfant renvoyée telle quelle).
"""

from __future__ import annotations

import asyncio
import multiprocessing
import time
from collections.abc import Callable
from typing import Any

ARRET_DOUX_S = 2.0


class DelaiDepasse(Exception):
    pass


def _contexte():
    # « forkserver » quand il existe (Linux, la production) : jamais un « fork » d'un processus qui a des fils (l'API en a),
    # et le serveur de départ garde les imports d'une fois sur l'autre. Sinon « spawn » (Windows, le poste).
    methodes = multiprocessing.get_all_start_methods()
    return multiprocessing.get_context("forkserver" if "forkserver" in methodes else "spawn")


def _enfant(sortie, fonction: Callable[..., Any], args: tuple[Any, ...]) -> None:
    try:
        sortie.send(("ok", fonction(*args)))
    except ValueError as erreur:
        sortie.send(("valeur", str(erreur)))
    except BaseException as erreur:  # noqa: BLE001 -- tout ce qui sort de l'enfant devient une erreur lisible du parent
        sortie.send(("erreur", type(erreur).__name__))
    finally:
        sortie.close()


def _arreter(processus) -> None:
    processus.terminate()
    processus.join(ARRET_DOUX_S)
    if processus.is_alive():
        processus.kill()
        processus.join(ARRET_DOUX_S)


def executer_arretable(fonction: Callable[..., Any], *args: Any, delai_s: float) -> Any:
    """Exécute ``fonction(*args)`` dans un processus enfant. Au-delà de ``delai_s`` : l'enfant est arrêté, ``DelaiDepasse``."""
    ctx = _contexte()
    lecture, ecriture = ctx.Pipe(duplex=False)
    processus = ctx.Process(target=_enfant, args=(ecriture, fonction, args), daemon=True)
    processus.start()
    ecriture.close()
    fin = time.monotonic() + delai_s
    try:
        while True:
            reste = fin - time.monotonic()
            if reste <= 0:
                raise DelaiDepasse(f"{delai_s:g}")
            if lecture.poll(min(reste, 0.2)):
                try:
                    genre, valeur = lecture.recv()
                except EOFError:
                    raise RuntimeError("the conversion process stopped without an answer") from None
                break
            if not processus.is_alive() and not lecture.poll():
                raise RuntimeError("the conversion process stopped without an answer")
    finally:
        if processus.is_alive():
            _arreter(processus)
        else:
            processus.join(ARRET_DOUX_S)
        lecture.close()
    if genre == "ok":
        return valeur
    if genre == "valeur":
        raise ValueError(valeur)
    raise RuntimeError(f"the conversion failed ({valeur})")


async def executer_arretable_async(fonction: Callable[..., Any], *args: Any, delai_s: float) -> Any:
    """La même chose sans geler la boucle : l'attente (pas le calcul) se fait dans un fil."""
    return await asyncio.to_thread(executer_arretable, fonction, *args, delai_s=delai_s)
