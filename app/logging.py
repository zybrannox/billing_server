# import logging
# from enum import StrEnum

# LOG_FORMAT_DEBUG = "%(levelname)s:%(message)s:%(pathname)s:%(funcname)s:%(lineno)d"

# class LogLevels(StrEnum):
#     info = "INFO"
#     warn = "WARN"
#     error = "ERROR"
#     debug = "DEBUG"


# def configure_logging(log_level: str = LogLevels.error):
#     log_level = str(log_level).upper()
#     log_levels = [level.value for level in LogLevels]

#     if log_level not in log_levels:
#         logging.basicConfig(level=LogLevels.error)
#         return

#     if log_level == LogLevels.debug:
#         logging.basicConfig(level=log_level, format=LOG_FORMAT_DEBUG)
#         return
#     logging.basicConfig(level=log_level)

import logging
from enum import Enum

LOG_FORMAT_DEBUG = (
    "%(asctime)s | %(levelname)s | %(message)s | "
    "%(pathname)s:%(funcName)s:%(lineno)d"
)

class LogLevels(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    DEBUG = "DEBUG"


LEVEL_MAP = {
    LogLevels.INFO: logging.INFO,
    LogLevels.WARN: logging.WARNING,
    LogLevels.ERROR: logging.ERROR,
    LogLevels.DEBUG: logging.DEBUG,
}


def configure_logging(log_level: LogLevels = LogLevels.ERROR):
    level = LEVEL_MAP.get(log_level, logging.ERROR)

    logging.basicConfig(
        level=level,
        format=LOG_FORMAT_DEBUG if log_level == LogLevels.DEBUG else None,
        force=True,   # important!
    )
