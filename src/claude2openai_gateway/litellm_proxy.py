from __future__ import annotations

import sys

import litellm

from .litellm_patch import apply_litellm_patch


def main(argv: list[str] | None = None) -> int:
    apply_litellm_patch()
    args = list(sys.argv[1:] if argv is None else argv)
    return int(
        litellm.run_server.main(
            args=args,
            prog_name="litellm",
            standalone_mode=False,
        )
        or 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
