

from loguru import logger
import sys

# базовая конфигурация
logger.remove()
logger.add(sys.stdout, level="INFO")

__all__ = ["logger"]
