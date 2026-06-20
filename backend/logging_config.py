import logging
import sys
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parents[1] / "logs"

def setup_logging(name: str, level=logging.DEBUG):
    """
    Call once at process startup.
    name: used for the log filename, e.g. "server" or "sub-agent-1"
    """
    LOG_DIR.mkdir(exist_ok=True)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # file handler — one file per process
    file_handler = logging.FileHandler(LOG_DIR / f"{name}.log", mode="w")
    file_handler.setFormatter(formatter)

    # stderr handler — only for main server, not sub-agents (stdout must stay clean)
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(stderr_handler)