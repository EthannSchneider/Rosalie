from __future__ import annotations

from enum import Enum
import datetime
import os


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
        if not os.getenv("LOG_QUIET"):   # ex : interface terminal (logs seulement dans le fichier)
            print(self.__log, flush=True)

    def __write_log(self):
        try:
            with open(os.getenv("LOG_FILE") or "log.txt", "a", encoding="utf-8") as log:
                log.write(self.__log + "\n")
        except OSError:
            pass

    @staticmethod
    def message(where: str, message: str, author: str) -> "Log":
        """where : « Discord · en message privé avec ethann69 », « Terminal · … »."""
        return Log("(" + where + ") " + author + ": " + message, LogType.MESSAGE)

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
