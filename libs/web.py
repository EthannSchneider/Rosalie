"""Accès internet de Rosalie : recherche web et lecture de pages.
Les pages construites en JavaScript sont lues avec le navigateur virtuel (libs/browser.py).

Recherche : DuckDuckGo (par défaut, sans clé), SearXNG (SEARXNG_URL) ou Brave (BRAVE_API_KEY).
Lecture : télécharge une page et en extrait le texte. Les adresses du réseau local sont
bloquées pour qu'un lien piégé ne puisse pas viser ta machine ou ta box.
"""
import asyncio
import html
import ipaddress
import json
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


# --------------------------------------------------------------------------- images

MAX_IMAGE = 8_000_000   # octets (limite des pièces jointes Discord pour un bot : ~10 Mo)
IMAGE_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/gif": "gif", "image/webp": "webp"}


@dataclass
class ImageResult:
    title: str
    image_url: str          # l'image elle-même
    page_url: str           # la page où elle a été trouvée (source)
    thumbnail: str = ""
    width: int = 0
    height: int = 0


@dataclass
class DownloadedImage:
    data: bytes
    content_type: str
    url: str

    @property
    def filename(self) -> str:
        return "image." + IMAGE_TYPES.get(self.content_type, "jpg")


async def _searxng_images(session: aiohttp.ClientSession, base_url: str, query: str,
                          limit: int) -> list[ImageResult]:
    async with session.get(f"{base_url.rstrip('/')}/search",
                           params={"q": query, "format": "json", "categories": "images"}) as response:
        if response.status != 200:
            raise WebError(f"SearXNG a répondu HTTP {response.status}")
        data = await response.json()
    return [ImageResult(r.get("title", ""), r["img_src"], r.get("url", ""), r.get("thumbnail_src", ""))
            for r in data.get("results", []) if r.get("img_src")][:limit]


async def _brave_images(session: aiohttp.ClientSession, api_key: str, query: str,
                        limit: int) -> list[ImageResult]:
    async with session.get("https://api.search.brave.com/res/v1/images/search",
                           params={"q": query, "count": limit, "safesearch": "strict"},
                           headers={"X-Subscription-Token": api_key, "Accept": "application/json"}) as response:
        if response.status != 200:
            raise WebError(f"Brave Images a répondu HTTP {response.status}")
        data = await response.json()
    return [ImageResult(r.get("title", ""), r.get("properties", {}).get("url", ""), r.get("url", ""),
                        r.get("thumbnail", {}).get("src", ""))
            for r in data.get("results", []) if r.get("properties", {}).get("url")][:limit]


async def _openverse_images(session: aiohttp.ClientSession, query: str, limit: int) -> list[ImageResult]:
    """Openverse : API officielle, gratuite et sans clé (images sous licence libre)."""
    async with session.get("https://api.openverse.org/v1/images/",
                           params={"q": query, "page_size": limit, "mature": "false"}) as response:
        if response.status != 200:
            raise WebError(f"Openverse a répondu HTTP {response.status}")
        data = await response.json(content_type=None)
    return [ImageResult(r.get("title") or "", r["url"], r.get("foreign_landing_url", ""),
                        r.get("thumbnail", ""), int(r.get("width") or 0), int(r.get("height") or 0))
            for r in data.get("results", []) if r.get("url")][:limit]


async def _commons_images(session: aiohttp.ClientSession, query: str, limit: int,
                          contact: str) -> list[ImageResult]:
    """Wikimedia Commons : leur règle impose un contact dans le User-Agent (WEB_CONTACT)."""
    params = {"action": "query", "format": "json", "generator": "search",
              "gsrsearch": f"{query} filetype:bitmap", "gsrnamespace": 6, "gsrlimit": limit,
              "prop": "imageinfo", "iiprop": "url|mime", "iiurlwidth": 1280}
    async with session.get("https://commons.wikimedia.org/w/api.php", params=params,
                           headers={"User-Agent": f"RosalieDiscordBot/1.0 ({contact})"}) as response:
        if response.status != 200:
            raise WebError(f"Wikimedia Commons a répondu HTTP {response.status}")
        data = await response.json(content_type=None)
    pages = sorted((data.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
    results = []
    for page in pages:
        info = (page.get("imageinfo") or [{}])[0]
        url = info.get("thumburl") or info.get("url")
        if url:
            results.append(ImageResult(page.get("title", "").removeprefix("File:"), url,
                                       info.get("descriptionurl", "")))
    return results[:limit]


async def search_images(query: str, limit: int = 5, provider: str = "duckduckgo",
                        searxng_url: str = "", brave_api_key: str = "",
                        contact: str = "") -> list[ImageResult]:
    """Essaie les sources dans l'ordre : celle configurée (Brave / SearXNG), puis Openverse,
    et Wikimedia Commons si un contact est configuré. Première qui répond gagne.
    (Repli final côté outil : l'image principale des pages trouvées par la recherche web.)"""
    sources = []
    if provider == "brave" and brave_api_key:
        sources.append(("Brave", lambda s: _brave_images(s, brave_api_key, query, limit)))
    if provider == "searxng" and searxng_url:
        sources.append(("SearXNG", lambda s: _searxng_images(s, searxng_url, query, limit)))
    sources.append(("Openverse", lambda s: _openverse_images(s, query, limit)))
    if contact:
        sources.append(("Commons", lambda s: _commons_images(s, query, limit, contact)))

    errors = []
    async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT) as session:
        for name, source in sources:
            try:
                results = await source(session)
            except (WebError, aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError) as error:
                errors.append(f"{name} : {error or type(error).__name__}")
                continue
            if results:
                return results
            errors.append(f"{name} : aucun résultat")
    Log.warning("Recherche d'images : " + " | ".join(errors))
    if all("aucun résultat" in error for error in errors):
        return []
    raise WebError("recherche d'images impossible (" + " ; ".join(errors) + ")")


_OG_IMAGE = re.compile(
    r"<meta[^>]+(?:property|name)=[\"'](?:og:image(?::url)?|twitter:image)[\"'][^>]*>", re.IGNORECASE)
_CONTENT = re.compile(r"content=[\"']([^\"']+)[\"']", re.IGNORECASE)


def page_image(html_text: str, base_url: str) -> str | None:
    """Image principale d'une page (og:image / twitter:image)."""
    for tag in _OG_IMAGE.findall(html_text):
        content = _CONTENT.search(tag)
        if content:
            return urljoin(base_url, html.unescape(content.group(1)))
    return None


def _image_type(content_type: str, data: bytes) -> str | None:
    kind = content_type.split(";")[0].strip().lower()
    if kind in IMAGE_TYPES:
        return kind
    signatures = {b"\xff\xd8\xff": "image/jpeg", b"\x89PNG": "image/png", b"GIF8": "image/gif"}
    for signature, guessed in signatures.items():
        if data.startswith(signature):
            return guessed
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


async def download_image(url: str, follow_page: bool = True) -> DownloadedImage:
    """Télécharge une image (réseau local refusé, 8 Mo max). Si l'adresse est une page web,
    prend son image principale (og:image)."""
    async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT) as session:
        try:
            for _ in range(MAX_REDIRECTS + 1):
                await _check_public(url)   # vérifié à chaque redirection
                async with session.get(url, allow_redirects=False,
                                       headers={"Accept": "image/*,text/html;q=0.5"}) as response:
                    if response.status in (301, 302, 303, 307, 308) and "Location" in response.headers:
                        url = urljoin(url, response.headers["Location"])
                        continue
                    if response.status != 200:
                        raise WebError(f"l'image a répondu HTTP {response.status}", status=response.status)
                    content_type = response.headers.get("Content-Type", "")
                    chunks, size = [], 0
                    async for chunk in response.content.iter_chunked(65536):
                        chunks.append(chunk)
                        size += len(chunk)
                        if size > MAX_IMAGE:
                            raise WebError("image trop lourde (plus de 8 Mo)")
                    data = b"".join(chunks)
                kind = _image_type(content_type, data)
                if kind:
                    return DownloadedImage(data, kind, url)
                if follow_page and "html" in content_type.lower():
                    found = page_image(data.decode(response.charset or "utf-8", errors="replace"), url)
                    if found:
                        return await download_image(found, follow_page=False)
                    raise WebError("cette page ne contient pas d'image principale")
                raise WebError(f"ce n'est pas une image ({content_type or 'type inconnu'})")
            raise WebError("trop de redirections")
        except (aiohttp.ClientError, asyncio.TimeoutError) as error:
            raise WebError(f"image inaccessible : {error}") from error
