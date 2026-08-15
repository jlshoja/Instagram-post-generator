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
    sub.add_parser("retry-failed", help="force retry all failed jobs now, then run once")
    sub.add_parser("publish", help="send drafted POST_GENERATED cards to Telegram only")

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
    elif command == "retry-failed":
        forced = scanner.db.execute(
            "UPDATE failed_jobs SET next_retry_at=datetime('now') WHERE resolved=0"
        ).rowcount
        print(f"forced {forced} failed job(s) to retry now")
        scanner.resume()
    elif command == "publish":
        from .models import ProductState

        ids = [r["id"] for r in scanner.db.query(
            "SELECT id FROM products WHERE state=? AND is_active=1",
            (ProductState.POST_GENERATED.value,),
        )]
        ok = failed = 0
        for pid in ids:
            good, err = scanner.publisher.publish_pending(pid)
            if good:
                ok += 1
            else:
                failed += 1
                print(f"  publish failed: product {pid}: {err}")
        print(f"published: {ok}")
        print(f"failed: {failed}")
        scanner.db.close()
        return 0 if failed == 0 else 1
    stats = scanner.run_scan(publish=publish, until=args.until)
    for k, v in stats.items():
        print(f"{k}: {v}")
    scanner.db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())