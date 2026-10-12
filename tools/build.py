#!/usr/bin/env python3
"""Assemble a reproducible overlay from one clean, tracked source tree."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
from ha_yaml import resolve

ROOT = Path(__file__).resolve().parents[1]


def real_path(path):
    """Reject symlinks in the selected file or any of its parent directories."""
    path = Path(path).absolute()
    if path.resolve(strict=True) != path:
        raise ValueError(f"Symlink or non-canonical path in build source: {path}")
    return path


def copy_tracked_config(repository, destination):
    """Copy the reviewed Git file inventory, never ignored or untracked files."""
    repository = real_path(repository)
    entries = subprocess.check_output(
        ["git", "-C", str(repository), "ls-files", "-z", "--", "config"]
    ).split(b"\0")
    files = []
    for entry in entries:
        if not entry:
            continue
        relative = Path(os.fsdecode(entry)).relative_to("config")
        source = real_path(repository / "config" / relative)
        if not source.is_file():
            raise ValueError(f"Tracked configuration must be a regular file: {source}")
        if relative.name == "secrets.yaml":
            raise ValueError("secrets.yaml must be supplied explicitly with --secrets, never copied from Git")
        files.append((source, relative))
    if not files:
        raise ValueError(f"No tracked configuration files in {repository}")
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    for source, relative in files:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        # Tracked .gitkeep files preserve empty include directories in the bundle.
        shutil.copy2(source, target)


def copy_explicit_secrets(source, destination):
    source = real_path(source)
    if not source.is_file():
        raise ValueError("--secrets must point to a regular file")
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as target, source.open("rb") as original:
        shutil.copyfileobj(original, target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New, empty directory outside the source tree")
    parser.add_argument("--secrets", type=Path, help="Local secrets.yaml; never checked into Git")
    parser.add_argument("--seed", action="store_true", help="Keep original automation aliases during initial ID registration")
    args = parser.parse_args()
    output = args.output.resolve()
    if output == ROOT or ROOT in output.parents and output.parts[len(ROOT.parts)] != "build":
        parser.error("Output must be outside the source tree or under ignored build/")
    if output.exists():
        parser.error("Output already exists; choose a new directory")
    root_revision = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    if subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain", "--ignore-submodules=none"], text=True).strip():
        parser.error("Root checkout has uncommitted changes; commit the reviewed release first")
    sources = {name: ROOT / "dependencies" / name for name in ("automations", "scripts")}
    revisions = {}
    for name, source in sources.items():
        if not (source / "config").is_dir():
            parser.error(f"Missing bundled component: dependencies/{name}/config")
        top = subprocess.check_output(["git", "-C", str(source), "rev-parse", "--show-toplevel"], text=True).strip()
        if Path(top).resolve() != ROOT.resolve():
            parser.error(f"{name} must be tracked in the root repository, not a nested repository")
        expected = subprocess.check_output(["git", "-C", str(ROOT), "ls-tree", "HEAD", f"dependencies/{name}"], text=True).split()
        if not expected or expected[:2] != ["040000", "tree"]:
            parser.error(f"{name} must be a committed directory in the root repository")
        revisions[name] = expected[2]
    copy_tracked_config(ROOT, output)
    try:
        for name, source in sources.items():
            if name == "automations" and args.seed:
                subprocess.run(["python3", str(source / "tools/render_seed.py"), str(output / name)], check=True)
            else:
                copy_tracked_config(source, output / name)
        if args.secrets:
            copy_explicit_secrets(args.secrets, output / "secrets.yaml")
        config = resolve(output / "configuration.yaml")
        automation_manifest = json.loads((sources['automations'] / 'migration/automations.json').read_text())
        script_registry = json.loads((sources['scripts'] / 'contracts/script-registry.json').read_text())['scripts']
        script_contract = json.loads((sources['scripts'] / 'contracts/reviewed-runtime.json').read_text())
        retired_scripts = script_contract.get('retired_scripts', {})
        assert set(retired_scripts) <= set(script_registry), 'Unknown script retirement'
        assert len(config["automation"]) == automation_manifest['automation_count'], "Unexpected automation count"
        assert set(config["script"]) == set(script_registry) - set(retired_scripts), "Unexpected folder script inventory"
        (output / "release.json").write_text(json.dumps({"root_revision": root_revision, "components": revisions, "component_revision_type": "git-tree", "home_assistant_version": "2026.9.1", "identity_seed": args.seed}, indent=2) + "\n")
        print(f"Built {output}: {len(config['automation'])} automations, {len(config['script'])} folder scripts; package scripts remain included")
    except Exception:
        # Keep the failed build for diagnosis; never touch the running configuration.
        raise


if __name__ == "__main__":
    main()
