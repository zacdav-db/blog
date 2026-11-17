"""Compare full materialization of shared data as Pandas and Arrow tables."""

from pathlib import Path

import delta_sharing

from common import arguments, measure, run

METHODS = ("legacy_pandas", "snapshot_pandas", "snapshot_arrow")


def read(args):
    if args.worker == "legacy_pandas":
        result = delta_sharing.load_as_pandas(
            f"{args.profile}#{args.table}", limit=args.rows, version=args.version
        )
        return len(result)
    snapshot = delta_sharing.SharingClient(args.profile).table(args.table).snapshot(
        limit=args.rows, version=args.version
    )
    if args.worker == "snapshot_pandas":
        result = snapshot.to_pandas()
        return len(result)
    result = snapshot.to_arrow()
    return result.num_rows


if __name__ == "__main__":
    args = arguments()
    if args.worker:
        measure(args, read)
    else:
        run(args, Path(__file__), METHODS)
