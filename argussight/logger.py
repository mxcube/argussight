import logging
import os

import colorlog

LOG_FORMAT_SHARED = "%(asctime)s - [%(type)s] - %(name)s - %(levelname)s - %(message)s"
LOG_FORMAT_SPECIFIC = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def snake_to_camel(snake_str: str) -> str:
    components = snake_str.split("_")
    return "".join(x.capitalize() for x in components)


class TypeFilter(logging.Filter):
    def __init__(self, log_type: str):
        self.log_type = log_type

    def filter(self, record: logging.LogRecord) -> bool:
        record.type = self.log_type
        return True


def configure_logger(
    name: str,
    type: str,
    log_directory: str,
    propagate: bool = True,
    add_to_shared: bool = True,
    file_level: int = logging.DEBUG,
) -> logging.Logger:
    """Configures/Creates a single logger."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = propagate

    if logger.handlers:
        return logger

    os.makedirs(log_directory, exist_ok=True)

    # File handlers
    camel_type = snake_to_camel(type)
    type_filter = TypeFilter(camel_type)

    shared_file_handler = logging.FileHandler(
        os.path.join(log_directory, "Shared_logs.log")
    )
    shared_file_handler.setFormatter(logging.Formatter(LOG_FORMAT_SHARED))
    shared_file_handler.addFilter(type_filter)
    shared_file_handler.setLevel(file_level)

    if add_to_shared:
        logger.addHandler(shared_file_handler)

    specific_log_file = os.path.join(log_directory, f"{camel_type}.log")
    type_file_handler = logging.FileHandler(specific_log_file)
    type_file_handler.setFormatter(logging.Formatter(LOG_FORMAT_SPECIFIC))
    type_file_handler.setLevel(file_level)

    # Console handler
    console_handler = colorlog.StreamHandler()
    colored_formatter = colorlog.ColoredFormatter(
        f"%(log_color)s{LOG_FORMAT_SHARED}",
        log_colors={
            "DEBUG": "cyan",
            "INFO": "blue",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "magenta",
        },
    )
    console_handler.setFormatter(colored_formatter)
    console_handler.addFilter(type_filter)

    # Attach handlers
    logger.addHandler(type_file_handler)
    logger.addHandler(console_handler)

    return logger
