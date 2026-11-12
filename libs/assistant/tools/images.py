"""Images : chercher des photos sur le web et les envoyer (en fichiers joints) là où on parle."""
from libs import web
from libs.assistant.tools.base import ToolContext, tool, _int
from libs.core.types import OutgoingFile
from libs.log import Log


MIN_IMAGE_BYTES = 12_000   # en dessous : presque toujours un logo ou une icône


async def _send_images(ctx: ToolContext, images: list[web.DownloadedImage], sources: list[str],
                       caption: str | None, channel: str | None) -> str:
    target = await ctx.interface().destination(channel, ctx.conversation) if channel else ctx.conversation
    links = [f"<{url}>" for url in dict.fromkeys(sources) if url]
    content = "\n".join(filter(None, [(caption or "").strip(),
                                      ("Source : " + " ".join(links)) if links else ""]))
    files = [OutgoingFile(f"image{i}.{image.filename.split('.')[-1]}", image.data)
             for i, image in enumerate(images, 1)]
    await ctx.rosalie.send(target, content or None, files=files, record=target.key != ctx.conversation.key,
                           record_as=f"[{len(files)} image(s) envoyée(s)] {content}".strip())
    where = "ici" if target.key == ctx.conversation.key else target.place
    return f"{len(files)} image(s) envoyée(s) {where}"


@tool("send_image",
      "Cherche des photos/images sur internet et les ENVOIE directement dans la conversation (fichiers "
      "joints, avec la source). Pour « montre-moi », « envoie une photo de… », « à quoi ressemble… ». "
      "Formule la recherche avec des mots-clés précis (l'anglais donne souvent de meilleurs résultats).",
      {"query": ("string", "Ce que l'image doit montrer, en mots-clés"),
       "count": ("integer", "Nombre d'images (1 à 4, défaut 1)"),
       "caption": ("string", "Petit texte à mettre avec l'image (optionnel)"),
       "channel": ("string", "Salon où l'envoyer (vide = ici)")},
      required=("query",))
async def send_image(ctx: ToolContext, query: str, count: int = 1, caption: str | None = None,
                     channel: str | None = None) -> str:
    config = ctx.config
    wanted = _int(count, 1, 1, 4)
    try:
        results = await web.search_images(query, wanted * 4, config.web_search_provider,
                                          config.searxng_url, config.brave_api_key,
                                          getattr(config, "web_contact", ""))
        follow_page = False
    except web.WebError as error:
        Log.warning(f"send_image: {error}")
        results = []
    if not results:   # repli : l'image principale (og:image) des pages trouvées sur le sujet
        try:
            pages = await web.search(query, 8, config.web_search_provider,
                                     config.searxng_url, config.brave_api_key)
        except web.WebError as error:
            return f"Erreur : {error}"
        results = [web.ImageResult(page.title, page.url, page.url) for page in pages]
        follow_page = True
    images, sources, titles, failures = [], [], [], 0
    for result in results:
        if len(images) >= wanted:
            break
        try:
            image = await web.download_image(result.image_url, follow_page=follow_page)
        except web.WebError:
            failures += 1
            continue
        if len(image.data) < MIN_IMAGE_BYTES or any(image.data == other.data for other in images):
            continue   # logo / icône, ou même image sur deux pages
        images.append(image)
        sources.append(result.page_url or result.image_url)
        titles.append(result.title or "sans titre")
    if not images:
        return ("Aucune image trouvée ou téléchargeable pour cette recherche"
                + (f" ({failures} échec(s))" if failures else "") + ". Essaie d'autres mots-clés.")
    sent = await _send_images(ctx, images, sources, caption, channel)
    described = "\n".join(f"{i}. {title} — {source}"
                          for i, (title, source) in enumerate(zip(titles, sources), 1))
    return (f"{sent}, avec la source. Ce qu'elles montrent (titres) :\n{described}\n"
            "Ne renvoie pas les liens : l'image est déjà affichée. Commente brièvement si tu veux.")


@tool("send_image_url",
      "Envoie dans la conversation une image précise à partir de son adresse (lien direct vers l'image, "
      "ou page web : son image principale est alors prise).",
      {"url": ("string", "Adresse http(s) de l'image ou de la page"),
       "caption": ("string", "Petit texte à mettre avec l'image (optionnel)"),
       "channel": ("string", "Salon où l'envoyer (vide = ici)")},
      required=("url",))
async def send_image_url(ctx: ToolContext, url: str, caption: str | None = None,
                         channel: str | None = None) -> str:
    try:
        image = await web.download_image(url)
    except web.WebError as error:
        return f"Erreur : {error}"
    return await _send_images(ctx, [image], [url], caption, channel) + "."
