"""Package only the portable frame-cache module and verify isolated installations."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from pathlib import Path

from release_version_adapter import checked_version

FILES = (
    "pyproject.toml",
    "docs/notification-frame-cache.md",
    "config/housekeeping/notification_frame_cache.py",
)
PACKAGE = "ha-notification-frame-cache"


def snapshot(root: Path, destination: Path) -> None:
    tracked = set(
        subprocess.check_output(["git", "ls-files", "-z"], cwd=root)
        .decode()
        .split("\0")
    )
    for name in FILES:
        path = root / name
        if (
            name not in tracked
            or not path.is_file()
            or path.resolve() != root.resolve() / name
        ):
            raise ValueError(
                "Cache package requires a regular tracked source input: " + name
            )
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


def environment(root: Path, destination: Path) -> Path:
    subprocess.run(
        [sys.executable, "-I", "-m", "venv", str(destination)],
        check=True,
    )
    python = destination / "bin/python"
    subprocess.run(
        [
            str(python),
            "-I",
            "-m",
            "pip",
            "--isolated",
            "install",
            "--require-hashes",
            "--only-binary=:all:",
            "-r",
            str(root / ".github/requirements-build.txt"),
        ],
        check=True,
    )
    return python


def verify_inventory(artifact: Path) -> None:
    """Reject accidental inclusion of configuration, helpers or runtime state."""
    if artifact.suffix == ".whl":
        with zipfile.ZipFile(artifact) as archive:
            names = archive.namelist()
        if "notification_frame_cache.py" not in names or any(
            name != "notification_frame_cache.py" and ".dist-info/" not in name
            for name in names
        ):
            raise ValueError("Wheel contains an unexpected module or resource")
    else:
        with tarfile.open(artifact) as archive:
            names = [
                member.name.split("/", 1)[1] for member in archive if member.isfile()
            ]
        if not set(FILES) <= set(names):
            raise ValueError("Source distribution lacks a required input")
        for name in names:
            if (
                name not in FILES
                and name not in {"PKG-INFO", "setup.cfg"}
                and not name.startswith(
                    "config/housekeeping/ha_notification_frame_cache.egg-info/"
                )
            ):
                raise ValueError("Source distribution contains an unexpected resource")


def verify_install(artifact: Path, root: Path, version: str, destination: Path) -> None:
    python = environment(root, destination / "venv")
    subprocess.run(
        [
            str(python),
            "-I",
            "-m",
            "pip",
            "--isolated",
            "install",
            "--no-deps",
            "--no-build-isolation",
            f"{PACKAGE} @ {artifact.as_uri()}",
        ],
        check=True,
    )
    source_hash = hashlib.sha256((root / FILES[2]).read_bytes()).hexdigest()
    smoke = f"""
import base64, hashlib, importlib.metadata, json, tempfile
from pathlib import Path
import notification_frame_cache as module
assert importlib.metadata.version({PACKAGE!r}) == {version!r}
assert hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest() == {source_hash!r}
with tempfile.TemporaryDirectory() as temporary:
    cache = module.NotificationFrameCache(Path(temporary) / 'cache')
    try:
        cache.feed(b'\\xff\\xd8synthetic-frame\\xff\\xd9')
        assert base64.b64decode(json.loads(cache.path.read_text())['jpeg']) == b'\\xff\\xd8synthetic-frame\\xff\\xd9'
        assert cache.path.stat().st_mode & 0o777 == 0o600
    finally:
        cache.close()
    assert not cache.path.exists()
"""
    subprocess.run([str(python), "-I", "-c", smoke], cwd=destination, check=True)


def build(root: Path, base: str, channel: str, output: Path) -> list[Path]:
    if channel not in {"beta", "rc", "nightly"}:
        raise ValueError("Stable requires an accepted RC")
    checked_version(root, base, channel)
    version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("Package output must be empty")
    with tempfile.TemporaryDirectory(prefix="cache-package-") as temporary:
        work = Path(temporary)
        source = work / "source"
        snapshot(root, source)
        python = environment(root, work / "build-env")
        subprocess.run(
            [
                str(python),
                "-c",
                "import setuptools.build_meta as b,sys; output=sys.argv[1]; b.build_sdist(output); b.build_wheel(output)",
                str(output),
            ],
            cwd=source,
            check=True,
        )
        artifacts = sorted(output.glob("*.whl")) + sorted(output.glob("*.tar.gz"))
        if len(artifacts) != 2:
            raise ValueError("Expected exactly one wheel and one source distribution")
        for index, artifact in enumerate(artifacts):
            verify_inventory(artifact)
            verify_install(artifact, root, version, work / f"install-{index}")
    (output / "SHA256SUMS").write_text(
        "".join(
            hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n"
            for path in artifacts
        )
    )
    return artifacts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base")
    parser.add_argument("channel", choices=("beta", "rc", "nightly"))
    parser.add_argument("--output", type=Path, default=Path("release-dist"))
    args = parser.parse_args()
    for path in build(
        Path(__file__).resolve().parents[1], args.base, args.channel, args.output
    ):
        print(path)


if __name__ == "__main__":
    main()
