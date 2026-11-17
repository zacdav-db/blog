"""Keep Quarto's relative CSS paths while invalidating stale browser caches."""

import hashlib
import os
import re
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent.parent
    version = hashlib.sha256((root / "styles.css").read_bytes()).hexdigest()[:12]
    output = Path(os.environ.get("QUARTO_PROJECT_OUTPUT_DIR", root / "_site"))
    links = re.compile(r'(<link\b[^>]*\bhref=")([^"]+)(")')

    def version_link(match):
        href = match[2].split("?", 1)[0]
        if href == "styles.css" or href.endswith("/styles.css"):
            return f"{match[1]}{href}?v={version}{match[3]}"
        return match[0]

    for page in output.rglob("*.html"):
        original = page.read_text(encoding="utf-8")
        updated = links.sub(version_link, original)
        if updated != original:
            page.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    main()
