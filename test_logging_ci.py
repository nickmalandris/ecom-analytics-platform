import sys
import structlog
import logging
from src.config import settings

# Force production mode to simulate CI... wait, in CI ENVIRONMENT is development!
# Let's set it to development just to be sure.
settings.environment = "development"

# Clear existing loggers
logging.getLogger().handlers.clear()

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.dict_tracebacks,
        structlog.processors.JSONRenderer() if settings.environment == "production" else structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.WriteLoggerFactory(file=sys.stdout),
    cache_logger_on_first_use=True,
)

class StructlogHandler(logging.Handler):
    def emit(self, record):
        logger_for_record = structlog.get_logger(record.name)
        if record.exc_info:
            logger_for_record.exception(record.getMessage(), exc_info=record.exc_info)
        else:
            method = getattr(logger_for_record, record.levelname.lower(), logger_for_record.info)
            method(record.getMessage())

root_logger = logging.getLogger()
root_logger.addHandler(StructlogHandler())
root_logger.setLevel(logging.INFO)

test_logger = logging.getLogger("test_meta_client")
test_logger.info("Meta client initialized")
