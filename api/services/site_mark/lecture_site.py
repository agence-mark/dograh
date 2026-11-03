"""[.mark] S2 / D203 : « Couleur de mon site », une lecture côté serveur BORNÉE.

Un serveur qui lit une adresse fournie peut être détourné pour lire des adresses internes. Ici :

* seulement les domaines DÉJÀ autorisés du site (``*`` seul ne donne aucun droit de lecture), en https, port 443 ;
* l'adresse est résolue AVANT l'appel et refusée si elle tombe sur une adresse privée, de bouclage, de lien local,
  réservée ou de métadonnées ; la connexion se fait sur l'adresse vérifiée (pas de seconde résolution) ;
* les redirections ne sont suivies que vers un domaine autorisé, résolu et vérifié de la même façon (3 au plus) ;
* délai de 5 s pour l'ensemble, réponse lue jusqu'à 1 Mo, type HTML seulement ;
* on n'en tire que ``theme-color``, les variables CSS de couleur des balises ``<style>`` et l'adresse du logo
  (jamais de script exécuté) ; rien n'est gardé : la route rend, le client enregistre ou non.

Le réseau est injecté (``resoudre`` et ``ouvrir``) : les tests rejouent des réponses enregistrées en fichier.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from dataclasses import dataclass, field
from typing import AsyncIterator, Awaitable, Callable
from urllib.parse import urljoin, urlsplit

from api.services.workflow.embed_session_service import validate_embed_origin

DELAI_S = 5.0
TAILLE_MAX = 1_000_000
REDIRECTIONS_MAX = 3
LECTURES_PAR_HEURE = 10


class LectureRefusee(Exception):
    """Refus propre : ``code`` pour la machine, le message pour l'humain (jamais un détail interne)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class ReponseHttp:
    statut: int
    entetes: dict[str, str]
    corps: AsyncIterator[bytes]


Resoudre = Callable[[str], Awaitable[list[str]]]
Ouvrir = Callable[[str, str, str], Awaitable[ReponseHttp]]  # (adresse ip vérifiée, hôte, chemin+requête)


@dataclass
class CouleurLue:
    couleur: str | None = None
    logo_url: str | None = None
    sources: list[str] = field(default_factory=list)


def adresse_publique(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if getattr(a, "ipv4_mapped", None) is not None:
        a = a.ipv4_mapped
    return a.is_global and not (a.is_multicast or a.is_loopback or a.is_link_local or a.is_private or a.is_reserved)


async def resoudre_dns(hote: str) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(hote, 443, type=socket.SOCK_STREAM)
    return sorted({i[4][0] for i in infos})


async def ouvrir_httpx(ip: str, hote: str, cible: str) -> ReponseHttp:  # pragma: no cover -- réseau réel
    import httpx

    client = httpx.AsyncClient(follow_redirects=False, timeout=DELAI_S, verify=True)
    requete = client.build_request(
        "GET",
        f"https://{ip if ':' not in ip else '[' + ip + ']'}{cible}",
        headers={"Host": hote, "User-Agent": "mark-site-colour/1.0", "Accept": "text/html"},
        extensions={"sni_hostname": hote},
    )
    reponse = await client.send(requete, stream=True)

    async def corps():
        try:
            async for morceau in reponse.aiter_bytes():
                yield morceau
        finally:
            await reponse.aclose()
            await client.aclose()

    return ReponseHttp(reponse.status_code, {k.lower(): v for k, v in reponse.headers.items()}, corps())


def _hote_autorise(hote: str, domaines: list[str]) -> bool:
    reels = [d for d in domaines if str(d).strip() not in ("", "*")]
    return bool(reels) and validate_embed_origin(f"https://{hote}", reels)


def _verifier_adresse(adresse: str, domaines: list[str]) -> tuple[str, str]:
    morceaux = urlsplit(adresse)
    if morceaux.scheme != "https" or not morceaux.hostname:
        raise LectureRefusee("adresse_refusee", "Only https addresses are read.")
    if morceaux.port not in (None, 443) or morceaux.username or morceaux.password:
        raise LectureRefusee("adresse_refusee", "Only the standard https port is read.")
    hote = morceaux.hostname.lower()
    if not _hote_autorise(hote, domaines):
        raise LectureRefusee("domaine_non_autorise", "This domain is not one of the site's allowed domains.")
    cible = (morceaux.path or "/") + (f"?{morceaux.query}" if morceaux.query else "")
    return hote, cible


async def lire_page(
    adresse: str, domaines: list[str], *, resoudre: Resoudre = resoudre_dns, ouvrir: Ouvrir = ouvrir_httpx
) -> tuple[str, str]:
    """La page d'accueil (texte HTML) et l'adresse finale ; toutes les bornes de D203 sont ici."""

    async def _suivre() -> tuple[str, str]:
        courante = adresse
        for _ in range(REDIRECTIONS_MAX + 1):
            hote, cible = _verifier_adresse(courante, domaines)
            ips = await resoudre(hote)
            if not ips or not all(adresse_publique(ip) for ip in ips):
                raise LectureRefusee("adresse_interne", "This address does not resolve to a public address.")
            reponse = await ouvrir(ips[0], hote, cible)
            if 300 <= reponse.statut < 400:
                destination = reponse.entetes.get("location")
                await _fermer(reponse)
                if not destination:
                    raise LectureRefusee("lecture_impossible", "The site answered with an empty redirection.")
                courante = urljoin(courante, destination)
                continue
            if reponse.statut != 200:
                await _fermer(reponse)
                raise LectureRefusee("lecture_impossible", "The site did not answer with a page.")
            if "text/html" not in reponse.entetes.get("content-type", "").lower():
                await _fermer(reponse)
                raise LectureRefusee("type_refuse", "The address is not an HTML page.")
            morceaux: list[bytes] = []
            lu = 0
            async for morceau in reponse.corps:
                lu += len(morceau)
                if lu > TAILLE_MAX:
                    morceaux.append(morceau[: len(morceau) - (lu - TAILLE_MAX)])
                    break
                morceaux.append(morceau)
            await _fermer(reponse)
            return b"".join(morceaux).decode("utf-8", errors="replace"), courante
        raise LectureRefusee("trop_de_redirections", "The site redirects too many times.")

    try:
        return await asyncio.wait_for(_suivre(), timeout=DELAI_S)
    except asyncio.TimeoutError:
        raise LectureRefusee("delai_depasse", "The site did not answer in time.") from None
    except LectureRefusee:
        raise
    except Exception:  # noqa: BLE001 -- jamais le détail d'une erreur réseau à l'écran
        raise LectureRefusee("lecture_impossible", "The site could not be read.") from None


async def _fermer(reponse: ReponseHttp) -> None:
    fermer = getattr(reponse.corps, "aclose", None)
    if fermer is not None:
        try:
            await fermer()
        except Exception:  # noqa: BLE001
            pass


_HEX = r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b"
_META_THEME = re.compile(r"<meta[^>]+name=[\"']theme-color[\"'][^>]*>", re.I)
_CONTENU = re.compile(r"content=[\"']([^\"']+)[\"']", re.I)
_STYLE = re.compile(r"<style[^>]*>(.*?)</style>", re.I | re.S)
_VARIABLE = re.compile(
    r"--[a-z0-9-]*(?:primary|brand|accent|main|principal)[a-z0-9-]*\s*:\s*(" + _HEX + ")", re.I
)
_LIEN = re.compile(r"<link[^>]+>", re.I)
_META_IMAGE = re.compile(r"<meta[^>]+property=[\"']og:image[\"'][^>]*>", re.I)


def _hex6(valeur: str) -> str:
    v = valeur.lower()
    return "#" + "".join(c * 2 for c in v[1:]) if len(v) == 4 else v


def extraire(html: str, adresse_page: str) -> CouleurLue:
    """La couleur principale et le logo d'une page, sans rien exécuter."""
    lue = CouleurLue()
    meta = _META_THEME.search(html)
    if meta:
        contenu = _CONTENU.search(meta.group(0))
        if contenu and re.fullmatch(_HEX, contenu.group(1).strip()):
            lue.couleur, lue.sources = _hex6(contenu.group(1).strip()), ["theme-color"]
    if lue.couleur is None:
        for bloc in _STYLE.findall(html):
            trouve = _VARIABLE.search(bloc)
            if trouve:
                lue.couleur, lue.sources = _hex6(trouve.group(1)), ["css-variable"]
                break
    candidats: list[str] = []
    for lien in _LIEN.findall(html):
        if re.search(r"rel=[\"'][^\"']*(apple-touch-icon|icon)[^\"']*[\"']", lien, re.I):
            href = re.search(r"href=[\"']([^\"']+)[\"']", lien, re.I)
            if href:
                candidats.append(href.group(1))
    image = _META_IMAGE.search(html)
    if image:
        contenu = _CONTENU.search(image.group(0))
        if contenu:
            candidats.append(contenu.group(1))
    for c in candidats:
        absolue = urljoin(adresse_page, c)
        if absolue.startswith("https://") and len(absolue) <= 500:
            lue.logo_url = absolue
            break
    return lue


async def lire_couleur_du_site(
    adresse: str, domaines: list[str], *, resoudre: Resoudre = resoudre_dns, ouvrir: Ouvrir = ouvrir_httpx
) -> CouleurLue:
    html, finale = await lire_page(adresse, domaines, resoudre=resoudre, ouvrir=ouvrir)
    return extraire(html, finale)
