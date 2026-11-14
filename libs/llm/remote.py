"""Clients HTTP des fournisseurs distants : OpenAI, Anthropic et Gemini."""
import json

import aiohttp

from libs.llm.ollama import OllamaError


class RemoteClient:
    def __init__(self, timeout: int = 300):
        self.__timeout = aiohttp.ClientTimeout(total=timeout)
        self.__session = None

    def __get_session(self):
        if self.__session is None or self.__session.closed:
            self.__session = aiohttp.ClientSession(timeout=self.__timeout)
        return self.__session

    async def chat_message(self, provider, model, key, messages, *, tools=None, options=None,
                           format=None):
        """Même forme de réponse qu'Ollama : content, tool_calls, done_reason."""
        options = dict(options or {})
        if "num_predict" in options:   # nom Ollama de la longueur max de réponse
            options["max_tokens"] = options.pop("num_predict")
        if provider == "openai":
            payload = {"model": model, "messages": messages, "stream": False}
            if tools:
                payload["tools"] = tools
            payload.update({k: v for k, v in options.items()
                            if k in ("temperature", "max_tokens", "top_p")})
            if format:
                payload["response_format"] = {"type": "json_object"} if format == "json" else format
            data = await self.__request("https://api.openai.com/v1/chat/completions", payload,
                                        {"Authorization": f"Bearer {key}"})
            choice = (data.get("choices") or [{}])[0]
            result = dict(choice.get("message") or {})
            result["done_reason"] = "length" if choice.get("finish_reason") == "length" else choice.get("finish_reason")
            return result
        if provider == "anthropic":
            system, history = self.__anthropic_history(messages)
            payload = {"model": model, "max_tokens": options.get("max_tokens", 4096),
                       "messages": history}
            if system:
                payload["system"] = system
            if tools:
                payload["tools"] = [{"name": t["function"]["name"],
                                     "description": t["function"].get("description", ""),
                                     "input_schema": t["function"].get("parameters", {})} for t in tools]
            if "temperature" in options:
                payload["temperature"] = options["temperature"]
            data = await self.__request("https://api.anthropic.com/v1/messages", payload,
                                        {"x-api-key": key, "anthropic-version": "2023-06-01"})
            blocks = data.get("content", [])
            calls = [{"id": b["id"], "type": "function", "function": {
                "name": b["name"], "arguments": json.dumps(b.get("input", {}))}}
                     for b in blocks if b.get("type") == "tool_use"]
            return {"content": "".join(b.get("text", "") for b in blocks if b.get("type") == "text"),
                    "tool_calls": calls,
                    "done_reason": "length" if data.get("stop_reason") == "max_tokens" else data.get("stop_reason")}
        payload = self.__gemini_payload(messages, tools, options, format)
        data = await self.__request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            payload, {"x-goog-api-key": key})
        candidate = (data.get("candidates") or [{}])[0]
        parts = candidate.get("content", {}).get("parts", [])
        calls = [{"id": f"gemini-{i}", "type": "function", "function": {
            "name": p["functionCall"]["name"],
            "arguments": json.dumps(p["functionCall"].get("args", {}))}}
                 for i, p in enumerate(parts) if "functionCall" in p]
        return {"content": "".join(p.get("text", "") for p in parts), "tool_calls": calls,
                "done_reason": "length" if candidate.get("finishReason") == "MAX_TOKENS" else candidate.get("finishReason")}

    @staticmethod
    def __anthropic_history(messages):
        system, result = [], []
        for message in messages:
            role, content = message.get("role"), message.get("content") or ""
            if role == "system":
                system.append(content)
            elif role == "tool":
                result.append({"role": "user", "content": [{"type": "tool_result",
                               "tool_use_id": message.get("tool_call_id", ""), "content": content}]})
            elif role == "assistant" and message.get("tool_calls"):
                blocks = [{"type": "text", "text": content}] if content else []
                for call in message["tool_calls"]:
                    fn = call.get("function", {})
                    args = fn.get("arguments", {})
                    blocks.append({"type": "tool_use", "id": call.get("id", ""),
                                   "name": fn.get("name", ""),
                                   "input": json.loads(args) if isinstance(args, str) else args})
                result.append({"role": "assistant", "content": blocks})
            else:
                result.append({"role": "assistant" if role == "assistant" else "user", "content": content})
        return "\n".join(system), result

    @staticmethod
    def __gemini_payload(messages, tools, options, format):
        contents = []
        system = []
        for message in messages:
            role, text = message.get("role"), message.get("content") or ""
            if role == "system":
                system.append(text)
            elif role == "tool":
                contents.append({"role": "user", "parts": [{"functionResponse": {
                    "name": message.get("name", "tool"), "response": {"content": text}}}]})
            elif role == "assistant" and message.get("tool_calls"):
                parts = ([{"text": text}] if text else [])
                for call in message["tool_calls"]:
                    fn = call.get("function", {})
                    args = fn.get("arguments", {})
                    parts.append({"functionCall": {"name": fn.get("name", ""),
                                  "args": json.loads(args) if isinstance(args, str) else args}})
                contents.append({"role": "model", "parts": parts})
            else:
                contents.append({"role": "model" if role == "assistant" else "user",
                                 "parts": [{"text": text}]})
        payload = {"contents": contents}
        if system:
            payload["systemInstruction"] = {"parts": [{"text": "\n".join(system)}]}
        config = {"temperature": (options or {}).get("temperature", 0.6)}
        if (options or {}).get("max_tokens"):
            config["maxOutputTokens"] = options["max_tokens"]
        if format:
            config["responseMimeType"] = "application/json"
        payload["generationConfig"] = config
        if tools:
            payload["tools"] = [{"functionDeclarations": [
                {"name": t["function"]["name"], "description": t["function"].get("description", ""),
                 "parameters": t["function"].get("parameters", {})} for t in tools]}]
        return payload

    async def embed(self, provider, model, key, texts):
        """Un vecteur par texte (OpenAI et Gemini ; Anthropic n'a pas d'embeddings)."""
        if provider == "openai":
            data = await self.__request("https://api.openai.com/v1/embeddings",
                                        {"model": model, "input": texts},
                                        {"Authorization": f"Bearer {key}"})
            return [item["embedding"] for item in data.get("data", [])]
        if provider == "gemini":
            data = await self.__request(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents",
                {"requests": [{"model": f"models/{model}", "content": {"parts": [{"text": text}]}}
                              for text in texts]},
                {"x-goog-api-key": key})
            return [item["values"] for item in data.get("embeddings", [])]
        raise OllamaError(f"{provider} ne propose pas d'embeddings")

    async def __request(self, url, payload, headers):
        try:
            async with self.__get_session().post(url, json=payload, headers=headers) as response:
                if response.status != 200:
                    raise OllamaError(f"Erreur fournisseur HTTP {response.status}: {await response.text()}")
                return await response.json()
        except aiohttp.ClientError as error:
            raise OllamaError(f"Fournisseur inaccessible : {error}") from error
        except TimeoutError as error:
            raise OllamaError("La requête au fournisseur a expiré") from error

    async def close(self):
        if self.__session and not self.__session.closed:
            await self.__session.close()
