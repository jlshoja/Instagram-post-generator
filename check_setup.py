import sys


def check_deps():
    try:
        import requests
        import bs4
        import PIL
        import apscheduler
    except ImportError:
        return 2
    return 0


def check_telegram():
    sys.path.insert(0, "src")
    from bazarkif.config import Config
    c = Config.from_env()
    if not (c.telegram_bot_token and c.telegram_chat_id):
        return 3
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "deps":
        return check_deps()
    if len(sys.argv) > 1 and sys.argv[1] == "telegram":
        return check_telegram()
    return 0


if __name__ == "__main__":
    sys.exit(main())