"""Accès internet de Gideon : recherche web et lecture de pages.
Les pages construites en JavaScript sont lues avec le navigateur virtuel (libs/browser.py).

Recherche : DuckDuckGo (par défaut, sans clé), SearXNG (SEARXNG_URL) ou Brave (BRAVE_API_KEY).
Lecture : télécharge une page et en extrait le texte. Les adresses du réseau local sont
bloquées pour qu'un lien piégé ne puisse pas viser ta machine ou ta box.
"""
import asyncio
import html
import ipaddress
import re
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import aiohttp

from libs.log import Log

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
TIMEOUT = aiohttp.ClientTimeout(total=20)
MAX_DOWNLOAD = 2_000_000   # octets
MAX_REDIRECTS = 5


class WebError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


def _clean(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


# --------------------------------------------------------------------------- recherche

async def _duckduckgo(session: aiohttp.ClientSession, query: str, limit: int) -> list[SearchResult]:
    async with session.post("https://html.duckduckgo.com/html/",
                            data={"q": query, "kl": "fr-fr"}) as response:
        if response.status != 200:
            raise WebError(f"DuckDuckGo a répondu HTTP {response.status}")
        page = await response.text()
    links = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', page, re.S)
    snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', page, re.S)
    results = []
    for index, (url, title) in enumerate(links):
        if "duckduckgo.com/y.js" in url:   # publicités
            continue
        snippet = snippets[index] if index < len(snippets) else ""
        results.append(SearchResult(_clean(title), html.unescape(url), _clean(snippet)))
    return results[:limit]


async def _searxng(session: aiohttp.ClientSession, base_url: str, query: str, limit: int) -> list[SearchResult]:
    async with session.get(f"{base_url.rstrip('/')}/search",
                           params={"q": query, "format": "json", "language": "fr"}) as response:
        if response.status != 200:
            raise WebError(f"SearXNG a répondu HTTP {response.status}")
        data = await response.json()
    return [SearchResult(r.get("title", ""), r.get("url", ""), r.get("content", ""))
            for r in data.get("results", [])[:limit]]


async def _brave(session: aiohttp.ClientSession, api_key: str, query: str, limit: int) -> list[SearchResult]:
    async with session.get("https://api.search.brave.com/res/v1/web/search",
                           params={"q": query, "count": limit, "search_lang": "fr"},
                           headers={"X-Subscription-Token": api_key, "Accept": "application/json"}) as response:
        if response.status != 200:
            raise WebError(f"Brave Search a répondu HTTP {response.status}")
        data = await response.json()
    return [SearchResult(r.get("title", ""), r.get("url", ""), _clean(r.get("description", "")))
            for r in data.get("web", {}).get("results", [])[:limit]]


async def search(query: str, limit: int = 5, provider: str = "duckduckgo",
                 searxng_url: str = "", brave_api_key: str = "") -> list[SearchResult]:
    async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT) as session:
        try:
            if provider == "searxng" and searxng_url:
                return await _searxng(session, searxng_url, query, limit)
            if provider == "brave" and brave_api_key:
                return await _brave(session, brave_api_key, query, limit)
            return await _duckduckgo(session, query, limit)
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            raise WebError(f"recherche impossible : {error}") from error


# --------------------------------------------------------------------------- lecture de page

async def _check_public(url: str):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise WebError("seules les adresses http(s) sont autorisées")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(parsed.hostname, None)
    except socket.gaierror as error:
        raise WebError(f"domaine introuvable : {parsed.hostname}") from error
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise WebError("adresse du réseau local refusée")


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form", "iframe"}
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr", "section", "article"}
    MAIN = {"main", "article"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.main_parts: list[str] = []   # texte dans <main>/<article> (sans menus ni pub)
        self.title = ""
        self.__skip = 0
        self.__main = 0
        self.__in_title = False

    def __add(self, text: str):
        self.parts.append(text)
        if self.__main:
            self.main_parts.append(text)

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.__skip += 1
        elif tag == "title":
            self.__in_title = not self.__skip and not self.title   # pas les <title> des SVG
        else:
            if tag in self.MAIN:
                self.__main += 1
            if tag in self.BLOCK:
                self.__add("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.__skip:
            self.__skip -= 1
        elif tag == "title":
            self.__in_title = False
        elif tag in self.MAIN and self.__main:
            self.__main -= 1

    def handle_data(self, data):
        if self.__in_title and not self.__skip:
            self.title += data
        elif not self.__skip:
            self.__add(data)

    def text(self) -> str:
        main = "".join(self.main_parts)
        text = main if len(main.strip()) > 200 else "".join(self.parts)
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n\n", text)
        return text.strip()


# Moins de texte que ça après lecture HTTP simple => page probablement construite en JavaScript
MIN_STATIC_TEXT = 1500
JS_REQUIRED_HINTS = re.compile(
    r"chargement\s*(en cours)?\s*\.\.\.|chargement…|loading\s*\.\.\.|enable javascript|"
    r"activer javascript|activez javascript|requires javascript|nécessite javascript",
    re.IGNORECASE)
# Codes renvoyés par les protections anti-robots, qu'un vrai navigateur passe souvent
BROWSER_RETRY_STATUSES = {403, 429, 503}


async def _download(url: str) -> tuple[str, str, str]:
    """Téléchargement HTTP simple. Retourne (url finale, content-type, corps)."""
    async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT) as session:
        try:
            for _ in range(MAX_REDIRECTS + 1):
                await _check_public(url)   # vérifié à chaque redirection
                async with session.get(url, allow_redirects=False) as response:
                    if response.status in (301, 302, 303, 307, 308) and "Location" in response.headers:
                        url = urljoin(url, response.headers["Location"])
                        continue
                    if response.status != 200:
                        raise WebError(f"la page a répondu HTTP {response.status}",
                                       status=response.status)
                    kind = response.headers.get("Content-Type", "")
                    chunks, size = [], 0
                    async for chunk in response.content.iter_chunked(65536):
                        chunks.append(chunk)
                        size += len(chunk)
                        if size >= MAX_DOWNLOAD:
                            break
                    charset = response.charset or "utf-8"
                    return url, kind, b"".join(chunks).decode(charset, errors="replace")
            raise WebError("trop de redirections")
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            raise WebError(f"page inaccessible : {error}") from error


def _extract(body: str) -> tuple[str, str]:
    parser = _TextExtractor()
    parser.feed(body)
    return parser.title.strip(), parser.text()


def _tidy(text: str) -> str:
    """Normalise les espaces et retire les lignes courtes répétées (boutons, menus…)."""
    seen, lines = set(), []
    for line in re.sub(r"[ \t]+", " ", text).splitlines():
        line = line.strip()
        if not line or (len(line) < 80 and line in seen):
            continue
        seen.add(line)
        lines.append(line)
    return "\n".join(lines)


def _needs_browser(text: str) -> bool:
    return len(text) < MIN_STATIC_TEXT or bool(JS_REQUIRED_HINTS.search(text[:3000]))


async def fetch(url: str, max_chars: int = 6000, browser=None, mode: str = "auto") -> tuple[str, str]:
    """Retourne (titre, texte) d'une page web publique.

    mode « auto » : lecture HTTP rapide, puis navigateur virtuel si la page est vide
    (JavaScript) ou bloquée par un anti-robot. « always » : toujours le navigateur.
    « never » : jamais.
    """
    use_browser = browser is not None and mode != "never"
    title, text = "", ""

    if not (use_browser and mode == "always"):
        try:
            url, kind, body = await _download(url)
        except WebError as error:
            if not (use_browser and error.status in BROWSER_RETRY_STATUSES):
                raise
        else:
            if "html" not in kind and "xml" not in kind:
                if kind.startswith("text/") or "json" in kind:
                    return url, body[:max_chars]
                raise WebError(f"type de contenu non lisible : {kind or 'inconnu'}")
            title, text = _extract(body)

    if use_browser and (mode == "always" or _needs_browser(text)):
        await _check_public(url)
        try:
            browser_title, browser_text = await browser.render(url)
        except Exception as error:   # navigateur absent, timeout, page qui plante…
            Log.warning(f"Virtual browser failed on {url}: {error}")
            if not text:
                raise WebError(f"page illisible, même avec le navigateur : {error}") from error
        else:
            browser_text = _tidy(browser_text)
            if len(browser_text) > len(text):
                title, text = browser_title or title, browser_text

    text = _tidy(text)
    if not text:
        raise WebError("la page ne contient pas de texte lisible")
    if len(text) > max_chars:
        text = text[:max_chars] + "\n[… page tronquée]"
    return title or url, text
