"""Print the fingerprints of the free scenes, for FreeContent.SCENES in the app.

A scene is free because of its fingerprint, not its name: the id inside a `.chill` is a line of
text in a zip anybody can edit, so the app compares the SHA-256 of the raw `scene.json` bytes
instead. Rebuild a free scene and its fingerprint moves, which means the app must learn the new
one or the rebuilt file stops being free.

**Append, never replace.** Copies people already downloaded carry the old fingerprint and have
to keep working, so the old line stays and the new one goes under it.

The manifest is hashed rather than the whole file on purpose: a zip's bytes change when a
different tool re-compresses it, even when the scene inside is identical.

    python3 tools/scene_hashes.py
"""

import hashlib
import os
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCENES = os.path.join(os.path.dirname(HERE), "scenes")
FREE = ["lantern-alley", "firefly-jar", "village-night"]


def main():
    print("    val SCENES: Map<String, String> = mapOf(")
    for slug in FREE:
        path = os.path.join(SCENES, f"{slug}.chill")
        with zipfile.ZipFile(path) as z:
            raw = z.read("scene.json")
        print(f'        // {slug}')
        print(f'        "{hashlib.sha256(raw).hexdigest()}" to "{slug}",')
    print("    )")


if __name__ == "__main__":
    main()
