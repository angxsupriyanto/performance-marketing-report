#!/usr/bin/env python3
"""Creates the password hash file for the viewer. The password is read from the terminal, never from arguments.

  docker run --rm -it --entrypoint python <image> -m viewer.hash_password > viewer_password_hash

Or on the host:  python -m viewer.hash_password > secrets/viewer_password_hash
"""
import getpass
import sys

from viewer import auth


def main() -> int:
    first = getpass.getpass("Password viewer (minimal 12 karakter): ", stream=sys.stderr)
    if getpass.getpass("Ulangi password: ", stream=sys.stderr) != first:
        print("Password tidak sama.", file=sys.stderr)
        return 1
    try:
        print(auth.hash_password(first))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
