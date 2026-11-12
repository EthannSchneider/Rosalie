from __future__ import annotations

from enum import Enum
import datetime
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # discord n'est pas requis pour les commandes CLI (ex: dataset)
    import discord


class LogType(Enum):
    INFO = "INFO"
    ERROR = "ERROR"
    WARNING = "WARNING"
    MESSAGE = "MESSAGE"
    COMMAND = "COMMAND"


class Log():
    """This class is designed to manage the log."""
    __log: str

    def __init__(self, message: str, type: LogType = LogType.INFO) -> None:
        self.__log = str(datetime.datetime.now()) + \
            " [" + type.value + "] : " + str(message)
        self.__print()
        self.__write_log()

    def __print(self):
        print(self.__log, flush=True)

    def __write_log(self):
        try:
            with open(os.getenv("LOG_FILE") or "log.txt", "a", encoding="utf-8") as log:
                log.write(self.__log + "\n")
        except OSError:
            pass

    @staticmethod
    def message(channel: discord.abc.Messageable, message: str, author: str, bot: str,
                recipient: str | None = None) -> "Log":
        """recipient : la personne avec qui le bot parle en DM. À donner quand c'est le bot
        qui écrit : py-cord ne connaît pas toujours channel.recipient."""
        import discord

        if isinstance(channel, discord.DMChannel):
            if channel.recipient:
                recipient = channel.recipient.name
            channel_name = bot + " DM with " + (recipient or author)
        else:
            channel_name = getattr(channel, "name", str(channel))
        return Log("(" + channel_name + ") " + author + ": " + message, LogType.MESSAGE)

    @staticmethod
    def info(message: str) -> "Log":
        return Log(message, LogType.INFO)

    @staticmethod
    def error(message: str) -> "Log":
        return Log(message, LogType.ERROR)

    @staticmethod
    def warning(message: str) -> "Log":
        return Log(message, LogType.WARNING)

    @staticmethod
    def command(message: str) -> "Log":
        return Log(message, LogType.COMMAND)
