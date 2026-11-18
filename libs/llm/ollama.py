import aiohttp

from libs.config.schema import PROVIDER_LABELS, split_model


CONTEXT_FULL = ("la conversation ne rentre plus dans la mémoire de travail du modèle : Ollama a "
                "coupé des messages (augmente OLLAMA_NUM_CTX, ou OLLAMA_CONTEXT_LENGTH sur le serveur)")


def _to_ollama_messages(messages: list[dict]) -> list[dict]:
    """Ollama attend du base64 brut ; la forme interne est une data URI.
    On ne copie que les messages qui portent des images (les autres passés tels quels)."""
    result = []
    for message in messages:
        images = message.get("images")
        if images:
            message = {**message, "images": [str(uri).rsplit(",", 1)[-1] for uri in images]}
        result.append(message)
    return result


class OllamaError(Exception):
    pass


class OllamaClient:
    """Client async des modèles. Un modèle s'écrit « fournisseur:nom » (sans préfixe : Ollama) :
    Ollama est appelé ici (/api/chat, /api/embed, /api/tags, /api/pull), les autres fournisseurs
    passent par `RemoteClient` (libs/llm/remote.py). On peut donc mélanger les fournisseurs :
    un modèle principal chez l'un, les embeddings chez l'autre."""

    def __init__(self, base_url: str, model: str, keep_alive: str = "30m",
                 options: dict | None = None, timeout: int = 300):
        self.base_url = base_url.rstrip("/")
        self.model = model                      # modèle principal, « fournisseur:nom »
        self.keep_alive = keep_alive
        self.options = options or {}
        self.api_keys: dict[str, str] = {}      # fournisseur distant -> clé API
        self.__remote = None
        self.__timeout = aiohttp.ClientTimeout(total=timeout)
        self.__session: aiohttp.ClientSession | None = None

    def __get_session(self) -> aiohttp.ClientSession:
        if self.__session is None or self.__session.closed:
            self.__session = aiohttp.ClientSession(timeout=self.__timeout)
        return self.__session

    async def chat(self, messages: list[dict], *, model: str | None = None,
                   options: dict | None = None, format: str | dict | None = None) -> str:
        message = await self.chat_message(messages, model=model, options=options, format=format)
        return message.get("content", "")

    async def chat_message(self, messages: list[dict], *, tools: list[dict] | None = None,
                           model: str | None = None, options: dict | None = None,
                           format: str | dict | None = None) -> dict:
        """Retourne le message brut de l'assistant (content + éventuels tool_calls)."""
        provider, name = split_model(model or self.model)
        if provider != "ollama":
            return await self.__get_remote().chat_message(
                provider, name, self.__key(provider), messages, tools=tools,
                options={**self.options, **(options or {})}, format=format)
        payload = {
            "model": name,
            "messages": _to_ollama_messages(messages),
            "stream": False,
            "think": False,
            "keep_alive": self.keep_alive,
            "options": {**self.options, **(options or {})},
        }
        if tools:
            payload["tools"] = tools
        if format:
            payload["format"] = format
        data = await self.__post("/api/chat", payload)
        message = dict(data.get("message", {}))
        message["done_reason"] = data.get("done_reason")   # "length" = réponse coupée
        return message

    async def embed(self, texts: list[str], model: str) -> list[list[float]]:
        provider, name = split_model(model)
        if provider != "ollama":
            return await self.__get_remote().embed(provider, name, self.__key(provider), texts)
        data = await self.__post("/api/embed", {"model": name, "input": texts,
                                                "keep_alive": self.keep_alive})
        return data.get("embeddings", [])

    def __get_remote(self):
        if self.__remote is None:
            from libs.llm.remote import RemoteClient   # import tardif : remote importe OllamaError
            self.__remote = RemoteClient()
        return self.__remote

    def __key(self, provider: str) -> str:
        key = self.api_keys.get(provider, "")
        if not key:
            raise OllamaError(f"clé API {PROVIDER_LABELS.get(provider, provider)} manquante "
                              "(Réglages → Providers)")
        return key

    async def list_models(self) -> list[str]:
        """Modèles installés dans Ollama."""
        try:
            async with self.__get_session().get(f"{self.base_url}/api/tags") as response:
                if response.status != 200:
                    text = await response.text()
                    if "no user query found" in text:
                        raise OllamaError(CONTEXT_FULL)
                    raise OllamaError(f"HTTP {response.status}: {text}")
                data = await response.json()
        except aiohttp.ClientError as error:
            raise OllamaError(f"Ollama unreachable at {self.base_url}: {error}") from error
        return [model["name"] for model in data.get("models", [])]

    async def pull(self, model: str):
        await self.__post("/api/pull", {"model": model, "stream": False},
                          timeout=aiohttp.ClientTimeout(total=None))

    async def __post(self, path: str, payload: dict, timeout=None) -> dict:
        try:
            async with self.__get_session().post(
                    f"{self.base_url}{path}", json=payload,
                    timeout=timeout or self.__timeout) as response:
                if response.status != 200:
                    text = await response.text()
                    if "no user query found" in text:
                        raise OllamaError(CONTEXT_FULL)
                    raise OllamaError(f"HTTP {response.status}: {text}")
                return await response.json()
        except aiohttp.ClientError as error:
            raise OllamaError(f"Ollama unreachable at {self.base_url}: {error}") from error
        except TimeoutError as error:
            raise OllamaError("Ollama request timed out") from error

    async def close(self):
        if self.__session and not self.__session.closed:
            await self.__session.close()
        if self.__remote:
            await self.__remote.close()
