"""Relais d'événements temps réel vers les navigateurs (Server-Sent Events).

Rosalie publie depuis sa boucle asyncio ; chaque onglet ouvert lit sa propre file depuis un fil
du serveur HTTP. Un compte peut avoir plusieurs onglets.
"""
from __future__ import annotations

import queue
import threading


class EventHub:
    def __init__(self):
        self.__lock = threading.Lock()
        self.__listeners: dict[int, set[queue.Queue]] = {}

    def subscribe(self, user_id: int) -> queue.Queue:
        listener: queue.Queue = queue.Queue(maxsize=500)
        with self.__lock:
            self.__listeners.setdefault(user_id, set()).add(listener)
        return listener

    def unsubscribe(self, user_id: int, listener: queue.Queue):
        with self.__lock:
            self.__listeners.get(user_id, set()).discard(listener)

    def publish(self, user_id: int, event: dict):
        with self.__lock:
            listeners = list(self.__listeners.get(user_id, ()))
        for listener in listeners:
            try:
                listener.put_nowait(event)
            except queue.Full:   # onglet bloqué : il rechargera l'historique en se reconnectant
                pass

    def listeners(self, user_id: int) -> int:
        with self.__lock:
            return len(self.__listeners.get(user_id, ()))
