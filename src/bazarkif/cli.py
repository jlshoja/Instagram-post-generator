import argparse
import sys

from .config import Config
from .logging_conf import setup_logging
from .scanner import Scanner
from .scheduler import Scheduler


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(prog="bazarkif")
    parser.add_argument("--publish", action="store_true", help="send cards to Telegram (default off)")
    parser.add_argument("--no-publish", action="store_true", help="build posts but do not send")
    parser.add_argument(
        "--until",
        choices=["detail", "media", "optimize", "post", "publish"],
        default=None,
        help="stop the scan after this stage (resumable partial runs)",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("run-once", help="run a single scan then exit")
    sub.add_parser("daemon", help="run the scheduler daemon")
    sub.add_parser("resume", help="requeue pending/failed jobs and run once")

    args = parser.parse_args(argv)
    config = Config.from_env()
    setup_logging(config.log_dir, config.log_level)

    command = args.command or "run-once"
    publish = args.publish and not args.no_publish

    if command == "daemon":
        if not config.enable_scheduler:
            print("Scheduler disabled (ENABLE_SCHEDULER=0)")
            return 0
        scanner = Scanner(config)
        Scheduler(config, scanner).start()
        return 0

    scanner = Scanner(config)
    if command == "resume":
        scanner.resume()
    stats = scanner.run_scan(publish=publish, until=args.until)
    for k, v in stats.items():
        print(f"{k}: {v}")
    scanner.db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())