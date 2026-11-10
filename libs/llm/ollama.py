import aiohttp


class OllamaError(Exception):
    pass


class OllamaClient:
    """Petit client async pour l'API HTTP d'Ollama (/api/chat, /api/tags, /api/pull)."""

    def __init__(self, base_url: str, model: str, keep_alive: str = "30m",
                 options: dict | None = None, timeout: int = 300):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.keep_alive = keep_alive
        self.options = options or {}
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
        payload = {
            "model": model or self.model,
            "messages": messages,
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
        return data.get("message", {})

    async def embed(self, texts: list[str], model: str) -> list[list[float]]:
        data = await self.__post("/api/embed", {"model": model, "input": texts,
                                                "keep_alive": self.keep_alive})
        return data.get("embeddings", [])

    async def list_models(self) -> list[str]:
        try:
            async with self.__get_session().get(f"{self.base_url}/api/tags") as response:
                if response.status != 200:
                    raise OllamaError(f"HTTP {response.status}: {await response.text()}")
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
                    raise OllamaError(f"HTTP {response.status}: {await response.text()}")
                return await response.json()
        except aiohttp.ClientError as error:
            raise OllamaError(f"Ollama unreachable at {self.base_url}: {error}") from error
        except TimeoutError as error:
            raise OllamaError("Ollama request timed out") from error

    async def close(self):
        if self.__session and not self.__session.closed:
            await self.__session.close()
