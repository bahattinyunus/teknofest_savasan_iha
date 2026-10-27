import os
import sys
import logging
from datetime import datetime

class ColoredFormatter(logging.Formatter):
    """Konsol çıktısı için ANSI renk kodlu log formatlayıcı."""
    
    GREY = "\x1b[38;20m"
    BLUE = "\x1b[34;20m"
    GREEN = "\x1b[32;20m"
    YELLOW = "\x1b[33;20m"
    RED = "\x1b[31;20m"
    BOLD_RED = "\x1b[31;1m"
    RESET = "\x1b[0m"
    
    FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s"
    
    FORMATS = {
        logging.DEBUG: GREY + FORMAT + RESET,
        logging.INFO: GREEN + FORMAT + RESET,
        logging.WARNING: YELLOW + FORMAT + RESET,
        logging.ERROR: RED + FORMAT + RESET,
        logging.CRITICAL: BOLD_RED + FORMAT + RESET
    }
    
    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno, self.FORMAT)
        formatter = logging.Formatter(log_fmt, datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)


def setup_logger(name: str = "AeroCombat", log_dir: str = "logs", level: str = "INFO") -> logging.Logger:
    """Modül için konfigüre edilmiş logger örneği döndürür."""
    os.makedirs(log_dir, exist_ok=True)
    
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger_instance = logging.getLogger(name)
    logger_instance.setLevel(log_level)
    
    # Önceden handler eklenmişse tekrar ekleme
    if logger_instance.handlers:
        return logger_instance
        
    # Konsol Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(ColoredFormatter())
    logger_instance.addHandler(console_handler)
    
    # Dosya Handler (Günün tarihiyle log dosyası)
    today = datetime.now().strftime("%Y_%m_%d")
    file_path = os.path.join(log_dir, f"savasan_iha_{today}.log")
    file_handler = logging.FileHandler(file_path, encoding="utf-8")
    file_handler.setLevel(log_level)
    file_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)
    logger_instance.addHandler(file_handler)
    
    return logger_instance

# Varsayılan global logger nesnesi
logger = setup_logger()
