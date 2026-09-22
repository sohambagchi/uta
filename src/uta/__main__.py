"""CLI entrypoint: `uta {import-gtfs,collect,serve,up,snapshot}`."""

import argparse
import logging
import os
import signal
import sys
import threading

from . import collector, db, gtfs_static


def main(argv=None):
    p = argparse.ArgumentParser(prog="uta", description="UTA transit data collector and dashboard")
    p.add_argument("--db", default=db.DEFAULT_DB, help="SQLite path (default: $UTA_DB or ./data/uta.db)")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("import-gtfs", help="download and import the static GTFS feed")
    s.add_argument("--file", help="import a local GTFS zip instead of downloading")
    s.add_argument("--force", action="store_true", help="re-import even if the version is unchanged")

    for name, help_ in (("collect", "poll realtime feeds forever"),
                        ("up", "collector + dashboard in one process")):
        s = sub.add_parser(name, help=help_)
        s.add_argument("--interval", type=float, default=collector.POLL_INTERVAL_S,
                       help="poll interval seconds (UTA updates its feeds every ~10 s)")
        s.add_argument("--no-positions", action="store_true", help="don't store vehicle GPS history")
        if name == "up":
            s.add_argument("--host", default="0.0.0.0", help="bind address (default: all interfaces)")
            s.add_argument("--port", type=int, default=8000)

    s = sub.add_parser("serve", help="dashboard + API only")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--migrate", action="store_true",
                   help="migrate an older database (normally left to the collector)")

    s = sub.add_parser("snapshot", help="consistent copy of the database, safe while collecting")
    s.add_argument("dest", nargs="?", default="data/dev.db", help="output path (default: data/dev.db)")

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    try:
        run(args)
    except db.SchemaMismatch as exc:
        logging.getLogger("uta").error("%s", exc)
        sys.exit(2)  # the systemd unit doesn't restart on this


def run(args):
    if args.cmd == "import-gtfs":
        conn = db.connect(args.db)
        db.init(conn)
        if args.file:
            with open(args.file, "rb") as fh:
                changed = gtfs_static.import_zip(conn, fh.read(), force=args.force)
        else:
            changed = gtfs_static.refresh(conn, force=args.force)
        print("imported" if changed else "already up to date")
    elif args.cmd == "snapshot":
        if os.path.realpath(args.dest) == os.path.realpath(args.db):
            sys.exit("snapshot destination is the database itself")
        conn = db.connect(args.db, readonly=True)
        db.backup(conn, args.dest)
        print(f"{args.db} -> {args.dest}")
    elif args.cmd == "collect":
        # stop cleanly on SIGTERM (systemd) / Ctrl-C so in-flight visits are saved
        stop = threading.Event()
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: stop.set())
        collector.run(args.db, interval=args.interval, store_positions=not args.no_positions, stop_flag=stop)
    elif args.cmd in ("serve", "up"):
        import uvicorn

        from .server import create_app

        # built first so only one of server/collector ever runs a migration
        app = create_app(args.db, migrate=args.cmd == "up" or args.migrate)
        thread = None
        if args.cmd == "up":
            stop = threading.Event()
            thread = threading.Thread(
                target=collector.run, daemon=True, name="collector",
                kwargs=dict(db_path=args.db, interval=args.interval,
                            store_positions=not args.no_positions, stop_flag=stop),
            )
            thread.start()
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
        if thread is not None:
            stop.set()          # save in-flight visits before exiting
            thread.join(timeout=30)


if __name__ == "__main__":
    main()
