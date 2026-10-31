"""
Usage (from the repo folder):

  python -m qbo_loader check     sign in, check settings, count sample data
  python -m qbo_loader clean     delete Intuit's sample transactions (asks first)
  python -m qbo_loader setup     accounts, classes, items, customers, vendors
  python -m qbo_loader load      opening balances + every transaction (resumable)
  python -m qbo_loader verify    compare QuickBooks' trial balance with the ledger
  python -m qbo_loader close     set the closing date to Sep 30, 2026
  python -m qbo_loader all       all of the above, in order

Logs and reports go to the .qbo folder. Your keys stay in .env and .qbo_tokens.json.
"""
import sys

from . import steps
from .client import QBO, log


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "help"
    flags = set(argv[2:])
    if cmd not in ("check", "clean", "setup", "load", "verify", "close", "all", "signin"):
        print(__doc__)
        return 0
    q = QBO()
    if cmd == "signin" or not q.tokens:
        q.sign_in()
    if cmd == "signin":
        return 0
    if cmd == "check":
        return 0 if steps.check(q) else 1
    if cmd == "clean":
        steps.clean(q, assume_yes="--yes" in flags)
    elif cmd == "setup":
        steps.setup(q)
    elif cmd == "load":
        steps.load(q)
    elif cmd == "verify":
        return 0 if steps.verify(q) else 1
    elif cmd == "close":
        steps.close(q)
    elif cmd == "all":
        if not steps.check(q):
            return 1
        steps.clean(q, assume_yes="--yes" in flags)
        steps.setup(q)
        steps.load(q)
        if steps.verify(q):
            steps.close(q)
            log("All done. Fernvale's books are in QuickBooks, closed through Sep 30, 2026.")
        else:
            log("Loaded, but the trial balance doesn't match yet; the closing date was not set.")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
