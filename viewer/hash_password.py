#!/usr/bin/env python3
"""Creates the password hash file for the viewer. The password is read from the terminal, never from arguments.

  docker run --rm -it -v "${PWD}:/out" --entrypoint python <image> -m viewer.hash_password --output /out/viewer_password_hash

Or on the host:  python -m viewer.hash_password --output viewer_password_hash

--output writes plain ASCII with no BOM, which is safer than a shell redirect (PowerShell `>` writes UTF-16).
Without --output the hash goes to standard output.
"""
import argparse
import getpass
import os
import sys

from viewer import auth


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", help="tulis hash ke berkas ini (ASCII, tanpa BOM) alih-alih ke layar")
    args = parser.parse_args(argv)
    first = getpass.getpass("Password viewer (minimal 12 karakter): ", stream=sys.stderr)
    if getpass.getpass("Ulangi password: ", stream=sys.stderr) != first:
        print("Password tidak sama.", file=sys.stderr)
        return 1
    try:
        hashed = auth.hash_password(first)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.output:
        with open(args.output, "w", encoding="ascii", newline="\n") as handle:
            handle.write(hashed + "\n")
        try:
            os.chmod(args.output, 0o644)  # the container user reads it through a bind mount, so it cannot be 600
        except OSError:
            pass
        print(f"Hash ditulis ke {args.output}", file=sys.stderr)
    else:
        print(hashed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
