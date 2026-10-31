"""[.mark] Builder, lot 3 : lire un site, PAGES PUBLIQUES SEULEMENT (``httpx`` + ``html.parser``).

Le cerveau ou la personne donne une adresse ; le serveur la lit. C'est une porte vers le réseau : le risque est la
SSRF (faire lire au serveur une adresse interne). Les gardes, tous testés :

* schémas ``http`` et ``https`` seulement, pas d'identifiants dans l'adresse, ports 80 et 443 seulement ;
* le nom est RÉSOLU ici et chaque adresse obtenue doit être publique (``ipaddress.is_global``) : localhost, réseaux
  privés, lien local, métadonnées d'un nuage, tout est refusé ; on se connecte ensuite à l'adresse vérifiée (pas
  de seconde résolution, donc pas de rebond DNS), en gardant le nom pour le certificat (SNI) ;
* les redirections sont suivies À LA MAIN (3 au plus) et chaque étape est revérifiée ;
* bornes : 10 pages, 1 Mo par page, 12 s par requête, texte HTML seulement ; seuls les liens du MÊME site sont suivis ;
* ``robots.txt`` est respecté ; aucun cookie, aucune authentification.

⛔ Aucun mot de métier. Reprise de rien : écrit pour ce chantier.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

from api.services.builder.dossiers.extraction import Extraction, Page

PAGES_MAX = 10
OCTETS_PAGE_MAX = 1024 * 1024
REDIRECTIONS_MAX = 3
DELAI = 12.0
AGENT = "mark-builder/1.0 (+reading public pages for a client audit)"
PORTS = {80, 443}

Resolveur = Callable[[str], Awaitable[list[str]]]


class SiteRefuse(Exception):
    """Une adresse ou une page refusée, avec la raison (affichable)."""


async def resoudre_par_dns(hote: str) -> list[str]:
    boucle = asyncio.get_running_loop()
    try:
        infos = await boucle.getaddrinfo(hote, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise SiteRefuse("The address of this site cannot be found.") from None
    return sorted({info[4][0] for info in infos})


def _est_publique(adresse: str) -> bool:
    try:
        ip = ipaddress.ip_address(adresse.split("%")[0])
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def normaliser(adresse: str) -> str:
    """L'adresse nettoyée (sans ancre), ou ``SiteRefuse``. Contrôle ce qui se voit avant toute résolution."""
    adresse = (adresse or "").strip()
    if len(adresse) > 2000:
        raise SiteRefuse("The address is too long.")
    if "://" not in adresse:
        adresse = "https://" + adresse
    coupe = urlsplit(adresse)
    if coupe.scheme not in ("http", "https"):
        raise SiteRefuse("Only http and https addresses are read.")
    if not coupe.hostname:
        raise SiteRefuse("The address has no site name.")
    if coupe.username or coupe.password:
        raise SiteRefuse("An address with a login or password is refused.")
    try:
        port = coupe.port
    except ValueError:
        raise SiteRefuse("The port of the address is invalid.") from None
    if port is not None and port not in PORTS:
        raise SiteRefuse("Only the standard web ports (80, 443) are read.")
    return urldefrag(urlunsplit(coupe))[0]


async def _adresses_publiques(hote: str, resolveur: Resolveur) -> list[str]:
    try:
        ipaddress.ip_address(hote)
        candidates = [hote]
    except ValueError:
        candidates = await resolveur(hote)
    if not candidates or not all(_est_publique(a) for a in candidates):
        raise SiteRefuse("This address points to a private or internal network: only public sites are read.")
    return candidates


class _Texte(HTMLParser):
    BLOCS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "header", "footer", "table", "ul", "ol"}
    IGNORES = {"script", "style", "noscript", "svg", "head", "template", "iframe"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.morceaux: list[str] = []
        self.liens: list[str] = []
        self.titre = ""
        self._ignore = 0
        self._dans_titre = False

    def handle_starttag(self, balise, attributs):
        if balise == "title":
            self._dans_titre = True
        if balise in self.IGNORES:
            self._ignore += 1
        if balise in self.BLOCS:
            self.morceaux.append("\n")
        if balise == "a":
            href = dict(attributs).get("href")
            if href:
                self.liens.append(href)

    def handle_endtag(self, balise):
        if balise == "title":
            self._dans_titre = False
        if balise in self.IGNORES and self._ignore:
            self._ignore -= 1
        if balise in self.BLOCS:
            self.morceaux.append("\n")

    def handle_data(self, donnees):
        if self._dans_titre:
            self.titre += donnees
        elif not self._ignore:
            self.morceaux.append(donnees)

    def texte(self) -> str:
        brut = "".join(self.morceaux)
        lignes = [" ".join(ligne.split()) for ligne in brut.split("\n")]
        sortie: list[str] = []
        for ligne in lignes:
            if ligne or (sortie and sortie[-1]):
                sortie.append(ligne)
        return "\n".join(sortie).strip()


def lire_le_html(html: str) -> tuple[str, str, list[str]]:
    """(titre, texte, liens) d'une page HTML. Les scripts, styles et en-têtes techniques sont écartés."""
    analyseur = _Texte()
    analyseur.feed(html)
    analyseur.close()
    return " ".join(analyseur.titre.split()), analyseur.texte(), analyseur.liens


@dataclass
class PageDuSite:
    adresse: str
    titre: str
    texte: str


@dataclass
class LectureDuSite:
    pages: list[PageDuSite] = field(default_factory=list)
    refusees: list[tuple[str, str]] = field(default_factory=list)  # (adresse, raison)

    def en_extraction(self) -> Extraction:
        """Au format commun des documents : une « page » par page du site, dont l'étiquette est l'adresse."""
        return Extraction(
            pages=[Page(numero=i, texte=p.texte, etiquette=p.adresse) for i, p in enumerate(self.pages, start=1) if p.texte],
            illisible=None if self.pages else "No public page could be read on this site.",
        )


async def _requete(
    client: httpx.AsyncClient, adresse: str, resolveur: Resolveur, redirections: int = REDIRECTIONS_MAX
) -> tuple[str, httpx.Response]:
    """GET d'UNE adresse déjà normalisée, redirections suivies à la main, chaque étape revérifiée et épinglée."""
    courante = adresse
    for _ in range(redirections + 1):
        coupe = urlsplit(courante)
        hote = coupe.hostname or ""
        ips = await _adresses_publiques(hote, resolveur)
        ip = ips[0]
        cible = coupe._replace(netloc=f"[{ip}]" if ":" in ip else ip).geturl()
        entetes = {"Host": coupe.netloc, "User-Agent": AGENT, "Accept": "text/html,text/plain;q=0.9"}
        extensions = {"sni_hostname": hote} if coupe.scheme == "https" else {}
        async with client.stream("GET", cible, headers=entetes, extensions=extensions) as reponse:
            if reponse.status_code in (301, 302, 303, 307, 308):
                suite = reponse.headers.get("location")
                if not suite:
                    raise SiteRefuse("A redirection without destination.")
                courante = normaliser(urljoin(courante, suite))
                continue
            type_ = reponse.headers.get("content-type", "").split(";")[0].strip().lower()
            if reponse.status_code != 200:
                raise SiteRefuse(f"The page answered {reponse.status_code}.")
            if type_ not in ("text/html", "application/xhtml+xml", "text/plain"):
                raise SiteRefuse("Not a text page (only HTML and text are read).")
            corps = bytearray()
            async for morceau in reponse.aiter_bytes():
                corps.extend(morceau)
                if len(corps) > OCTETS_PAGE_MAX:
                    raise SiteRefuse("The page is too large (more than 1 MB).")
            reponse_complete = httpx.Response(200, headers={"content-type": type_}, content=bytes(corps))
            return courante, reponse_complete
    raise SiteRefuse("Too many redirections.")


def _decoder(reponse: httpx.Response) -> str:
    return reponse.content.decode(reponse.encoding or "utf-8", errors="replace")


async def _robots(client: httpx.AsyncClient, racine: str, resolveur: Resolveur) -> RobotFileParser:
    analyseur = RobotFileParser()
    try:
        _, reponse = await _requete(client, urljoin(racine, "/robots.txt"), resolveur, redirections=1)
        analyseur.parse(_decoder(reponse).splitlines())
    except (SiteRefuse, httpx.HTTPError):
        analyseur.parse([])  # pas de robots.txt lisible : rien n'est interdit
    return analyseur


async def lire_le_site(
    adresse: str,
    *,
    resolveur: Resolveur = resoudre_par_dns,
    transport: httpx.AsyncBaseTransport | None = None,
    pages_max: int = PAGES_MAX,
) -> LectureDuSite:
    """La page d'accueil puis les pages liées du même site, jusqu'à ``pages_max``. ``SiteRefuse`` si l'adresse
    elle-même est refusée ; une page liée refusée est notée dans ``refusees`` et la lecture continue."""
    depart = normaliser(adresse)
    hote = urlsplit(depart).hostname
    resultat = LectureDuSite()
    async with httpx.AsyncClient(
        transport=transport, timeout=DELAI, follow_redirects=False, trust_env=False, verify=True
    ) as client:
        robots = await _robots(client, depart, resolveur)
        if not robots.can_fetch(AGENT, depart):
            raise SiteRefuse("The site asks not to be read (robots.txt).")
        a_lire = [depart]
        vues: set[str] = set()
        while a_lire and len(resultat.pages) < pages_max:
            suivante = a_lire.pop(0)
            if suivante in vues:
                continue
            vues.add(suivante)
            if not robots.can_fetch(AGENT, suivante):
                resultat.refusees.append((suivante, "The site asks not to read this page (robots.txt)."))
                continue
            try:
                finale, reponse = await _requete(client, suivante, resolveur)
                if urlsplit(finale).hostname != hote:
                    raise SiteRefuse("The page is on another site.")
                html = _decoder(reponse)
                titre, texte, liens = lire_le_html(html)
            except SiteRefuse as erreur:
                if suivante == depart:
                    raise
                resultat.refusees.append((suivante, str(erreur)))
                continue
            except httpx.HTTPError:
                if suivante == depart:
                    raise SiteRefuse("The site did not answer.") from None
                resultat.refusees.append((suivante, "The page did not answer."))
                continue
            if texte:
                resultat.pages.append(PageDuSite(adresse=finale, titre=titre, texte=texte))
            for lien in liens:
                try:
                    suite = normaliser(urljoin(finale, lien))
                except SiteRefuse:
                    continue
                if urlsplit(suite).hostname == hote and suite not in vues and suite not in a_lire:
                    a_lire.append(suite)
    return resultat
