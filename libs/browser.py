"""Navigateur virtuel (Chromium headless via Playwright) pour lire les pages qui
construisent leur contenu en JavaScript.

- un seul Chromium, lancé à la première utilisation puis réutilisé (~200 Mo de RAM)
- un contexte isolé par page (pas de cookies partagés entre deux lectures)
- toutes les requêtes de la page passent par un filtre : rien vers le réseau local,
  pas d'images / vidéos / polices (inutiles pour lire le texte, et plus rapide)
"""
import asyncio
import ipaddress
from urllib.parse import urlparse

from libs.log import Log

BLOCKED_RESOURCES = {"image", "media", "font"}
NAVIGATION_TIMEOUT = 20_000   # ms
SETTLE_TIMEOUT = 6_000        # ms d'attente max que la page finisse de charger ses données


# Texte réellement affiché, y compris dans les shadow DOM des web components
# (que page.content() n'exporte pas) et en suivant les <slot>.
VISIBLE_TEXT_JS = r"""() => {
  const SKIP = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'SVG', 'NAV', 'FOOTER', 'HEADER', 'TEMPLATE', 'IFRAME']);
  const BLOCK = /^(P|DIV|LI|H[1-6]|TR|SECTION|ARTICLE|BR|TD|TH|DT|DD)$/;
  const out = [];
  const walk = (node) => {
    if (node.nodeType === Node.TEXT_NODE) {
      const text = node.textContent.trim();
      if (text) out.push(text + ' ');
      return;
    }
    if (node.nodeType === Node.ELEMENT_NODE) {
      const tag = node.tagName.toUpperCase();
      if (SKIP.has(tag)) return;
      const style = getComputedStyle(node);
      if (style.display === 'none' || style.visibility === 'hidden') return;
      if (BLOCK.test(tag)) out.push('\n');
      if (node.shadowRoot) walk(node.shadowRoot);
    } else if (node.nodeType !== Node.DOCUMENT_FRAGMENT_NODE) {
      return;
    }
    const children = node.tagName === 'SLOT' ? node.assignedNodes({flatten: true}) : node.childNodes;
    for (const child of children) walk(child);
  };
  walk(document.querySelector('main') || document.body);
  return out.join('');
}"""


class BrowserUnavailable(Exception):
    pass


class VirtualBrowser:
    def __init__(self, user_agent: str):
        self.__user_agent = user_agent
        self.__playwright = None
        self.__browser = None
        self.__lock = asyncio.Lock()
        self.__dns_cache: dict[str, bool] = {}

    async def __ensure(self):
        async with self.__lock:
            if self.__browser and self.__browser.is_connected():
                return
            try:
                from playwright.async_api import async_playwright
            except ImportError as error:
                raise BrowserUnavailable("Playwright n'est pas installé") from error
            try:
                self.__playwright = await async_playwright().start()
                self.__browser = await self.__playwright.chromium.launch(headless=True)
            except Exception as error:
                raise BrowserUnavailable(
                    "Chromium introuvable : lance `python -m playwright install chromium`") from error
            Log.info("Virtual browser started")

    async def __is_public(self, host: str) -> bool:
        if host not in self.__dns_cache:
            try:
                infos = await asyncio.get_running_loop().getaddrinfo(host, None)
                self.__dns_cache[host] = all(ipaddress.ip_address(i[4][0]).is_global for i in infos)
            except OSError:
                self.__dns_cache[host] = False
        return self.__dns_cache[host]

    async def __filter(self, route):
        request = route.request
        parsed = urlparse(request.url)
        if request.resource_type in BLOCKED_RESOURCES:
            return await route.abort()
        if parsed.scheme in ("data", "blob"):
            return await route.continue_()
        if parsed.scheme not in ("http", "https") or not parsed.hostname \
                or not await self.__is_public(parsed.hostname):
            return await route.abort()
        await route.continue_()

    async def render(self, url: str) -> tuple[str, str]:
        """Ouvre la page, laisse le JavaScript s'exécuter, retourne (titre, texte affiché)."""
        await self.__ensure()
        context = await self.__browser.new_context(
            user_agent=self.__user_agent, locale="fr-FR", java_script_enabled=True,
            service_workers="block")
        try:
            await context.route("**/*", self.__filter)
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT)
            try:
                await page.wait_for_load_state("networkidle", timeout=SETTLE_TIMEOUT)
            except Exception:
                pass   # sites qui ne s'arrêtent jamais de charger (pubs, sondages…) : on lit quand même
            return await page.title(), await page.evaluate(VISIBLE_TEXT_JS)
        finally:
            await context.close()

    async def close(self):
        if self.__browser:
            await self.__browser.close()
        if self.__playwright:
            await self.__playwright.stop()
        self.__browser = self.__playwright = None
