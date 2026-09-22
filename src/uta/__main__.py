"""CLI entrypoint: `uta {import-gtfs,collect,serve,up}`."""

import argparse
import logging
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
        s.add_argument("--interval", type=float, default=30.0, help="poll interval seconds")
        s.add_argument("--no-positions", action="store_true", help="don't store vehicle GPS history")
        if name == "up":
            s.add_argument("--host", default="127.0.0.1")
            s.add_argument("--port", type=int, default=8000)

    s = sub.add_parser("serve", help="dashboard + API only")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.cmd == "import-gtfs":
        conn = db.connect(args.db)
        db.init(conn)
        if args.file:
            with open(args.file, "rb") as fh:
                changed = gtfs_static.import_zip(conn, fh.read(), force=args.force)
        else:
            changed = gtfs_static.refresh(conn, force=args.force)
        print("imported" if changed else "already up to date")
    elif args.cmd == "collect":
        collector.run(args.db, interval=args.interval, store_positions=not args.no_positions)
    elif args.cmd in ("serve", "up"):
        import uvicorn

        from .server import create_app

        if args.cmd == "up":
            stop = threading.Event()
            threading.Thread(
                target=collector.run, daemon=True, name="collector",
                kwargs=dict(db_path=args.db, interval=args.interval,
                            store_positions=not args.no_positions, stop_flag=stop),
            ).start()
        uvicorn.run(create_app(args.db), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
