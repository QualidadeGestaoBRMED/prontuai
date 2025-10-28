import logging
import os

def setup_logging(log_file: str = "logs/app.log"):
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler()
        ]
    )

# Exemplo de uso:
# from app.core.logging import setup_logging
# setup_logging()
# logger = logging.getLogger(__name__)
# logger.info("Mensagem de log") 