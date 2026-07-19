"""独立 Agent worker 进程入口。

M0 阶段刻意不包含 LLM 或数据库集成。
"""

import logging

logger = logging.getLogger(__name__)


def main() -> None:
    """启动占位 worker，并明确当前尚未配置任何任务。"""
    logging.basicConfig(level=logging.INFO)
    logger.info("faultAgent worker skeleton is ready; no tasks are configured")


if __name__ == "__main__":
    main()
