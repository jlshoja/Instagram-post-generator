import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger("bazarkif.scheduler")


class Scheduler:
    def __init__(self, config, scanner):
        self.config = config
        self.scanner = scanner
        self.sched = BlockingScheduler()

    def start(self) -> None:
        minutes = self.config.scan_interval_minutes
        self.sched.add_job(
            self._job,
            IntervalTrigger(minutes=minutes),
            id="scan",
            replace_existing=True,
        )
        logger.info("scheduler started, interval=%d minutes", minutes)
        self._job()  # run immediately
        try:
            self.sched.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("scheduler stopped")

    def _job(self) -> None:
        logger.info("scheduled scan starting")
        try:
            self.scanner.run_scan()
        except Exception as e:
            logger.critical("scheduled scan crashed", extra={"error": str(e)}, exc_info=True)