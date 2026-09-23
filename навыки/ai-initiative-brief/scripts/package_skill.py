#!/usr/bin/env python3
"""Build identical, reproducible ZIP and .skill downloads from an explicit file list."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parent.parent
FILES = (
    "SKILL.md",
    "README.md",
    "requirements.txt",
    "assets/template.md",
    "assets/example_filled.md",
    "scripts/read_transcript.py",
    "scripts/build_brief.py",
    "scripts/package_skill.py",
)


def main():
    # Read every input before replacing an existing archive.
    inputs = [(name, (ROOT / name).read_bytes()) for name in FILES]
    destination = ROOT / "ai-initiative-brief.zip"
    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in inputs:
            info = ZipInfo(f"ai-initiative-brief/{name}", (2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    skill = ROOT / "ai-initiative-brief.skill"
    skill.write_bytes(destination.read_bytes())
    print(f"Created {destination.name} and {skill.name}: {len(inputs)} files each")


if __name__ == "__main__":
    main()
