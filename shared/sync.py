"""Copy the canonical shared card assets into the site and game static dirs.

Flask serves each app from its own static directory, so the shared card design
can't be served from one place. This keeps the source of truth in shared/ and
copies it into both apps. Run after editing shared/card.css or
shared/attribute_icons.json:

    python shared/sync.py
"""

import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ASSETS = ["card.css", "attribute_icons.json"]
TARGETS = [
    os.path.join(ROOT, "site", "static"),
    os.path.join(ROOT, "game", "static"),
]


def main():
    for asset in ASSETS:
        src = os.path.join(HERE, asset)
        for target_dir in TARGETS:
            os.makedirs(target_dir, exist_ok=True)
            dst = os.path.join(target_dir, asset)
            shutil.copyfile(src, dst)
            print(f"{asset} -> {os.path.relpath(dst, ROOT)}")


if __name__ == "__main__":
    main()
