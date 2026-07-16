"""Separate Agent worker process entry point.

The worker intentionally contains no LLM or database integration at M0.
"""

import logging

logger = logging.getLogger(__name__)


def main() -> None:
    """Start the placeholder worker process."""
    logging.basicConfig(level=logging.INFO)
    logger.info("faultAgent worker skeleton is ready; no tasks are configured")


if __name__ == "__main__":
    main()
