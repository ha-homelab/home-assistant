#!/usr/bin/env python3
"""Stage and check a configuration bundle in the existing HA container; do not activate it."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile


FINGERPRINT = r'''
from pathlib import Path
import hashlib,json,sys
stage=Path(sys.argv[1]); files=json.loads(sys.argv[2]); root=Path('/config')
assert stage.parent==root and stage.name.startswith('.ha-homelab-stage-')
def digest(path):
    if not path.exists(): return None
    assert path.is_file() and not path.is_symlink(), str(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()
def tree(path):
    if not path.exists(): return None
    assert path.is_dir() and not path.is_symlink(), str(path)
    found={}
    for file in sorted(path.rglob('*')):
        assert not file.is_symlink(), str(file)
        if file.is_file(): found[str(file.relative_to(path))]=digest(file)
    return found
for name, expected in files.items():
    relative=Path(name)
    assert not relative.is_absolute() and '..' not in relative.parts
    assert digest(stage/relative)==expected, 'Staging transfer changed file: '+name
print(json.dumps({'live_files':{name:digest(root/name) for name in files},
                  'live_directories':{name:tree(root/name) for name in ('automations','scripts')}}))
'''


PREPARE_ENVIRONMENT = r'''
from pathlib import Path
import sys
stage=Path(sys.argv[1]); root=Path('/config')
assert stage.parent==root and stage.name.startswith('.ha-homelab-stage-')
assert stage.is_dir() and not stage.is_symlink(), 'Invalid staging directory'
secrets=stage/'secrets.yaml'
assert secrets.is_file() and not secrets.is_symlink(), 'Invalid staged secrets'
secrets.chmod(0o600)
staged=stage/'custom_components'; installed=root/'custom_components'
assert not staged.is_symlink(), 'Staged custom_components must be a real directory'
staged.mkdir(exist_ok=True)
if installed.exists():
    assert installed.is_dir(), 'Installed custom_components must be a directory'
    for source in sorted(installed.iterdir()):
        target=staged/source.name
        # A bundled component must be checked as a complete replacement. Never
        # overlay its files with the installed version or follow a target link.
        # is_symlink also protects a preexisting broken link from replacement.
        if target.exists() or target.is_symlink():
            continue
        target.symlink_to(source, target_is_directory=source.is_dir())
'''


def write_private(path, content):
    """Create evidence without overwriting a previous receipt or exposing secrets."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as file:
        file.write(content)


def check_report(output, remote):
    """Find the JSON report even when integrations log warnings before it."""
    decoder = json.JSONDecoder()
    for candidate in re.finditer(r"(?m)^\s*\{", output):
        try:
            value, _ = decoder.raw_decode(output[candidate.start():].lstrip())
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and value.get("config_dir") == remote and "total_errors" in value:
            return value
    raise ValueError("Home Assistant did not return its structured check_config report")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("receipt", type=Path, help="New private local JSON receipt")
    parser.add_argument("--context", default="k3s-heaven")
    parser.add_argument("--namespace", default="homeassistant")
    parser.add_argument("--pod", default="home-assistant-0")
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    if not (bundle / "release.json").is_file() or not (bundle / "secrets.yaml").is_file():
        parser.error("Bundle must include release.json and a local secrets.yaml")
    if args.receipt.exists():
        parser.error("Receipt already exists")
    log = args.receipt.with_suffix(".check.log")
    if log.exists():
        parser.error("Private check log already exists")
    release = json.loads((bundle / "release.json").read_text())
    assert release["home_assistant_version"] == "2026.9.1", "Unexpected bundle target version"
    kubectl = ["kubectl", "--context", args.context, "-n", args.namespace]
    pod = json.loads(subprocess.check_output(kubectl + ["get", "pod", args.pod, "-o", "json"]))
    expected = "ghcr.io/home-assistant/home-assistant:2026.9.1"
    assert pod["spec"]["nodeName"] == "h7", "Unexpected Home Assistant node"
    assert pod["spec"]["containers"][0]["image"] == expected, "Revalidate against the installed HA version"
    execute = kubectl + ["exec", args.pod, "--"]
    remote = subprocess.check_output(execute + ["python", "-c", "import tempfile; print(tempfile.mkdtemp(prefix='.ha-homelab-stage-', dir='/config'))"], text=True).strip()
    stream = io.BytesIO()
    files = {}
    with tarfile.open(fileobj=stream, mode="w") as tar:
        for file in sorted(bundle.rglob("*")):
            if file.is_symlink():
                raise ValueError(f"Bundle must not contain symlinks: {file}")
            if file.is_file():
                content = file.read_bytes()
                relative = str(file.relative_to(bundle))
                files[relative] = hashlib.sha256(content).hexdigest()
                if relative == "release.json":
                    release = json.loads(content)
                    assert release["home_assistant_version"] == "2026.9.1", "Bundle target changed during staging"
                member = tarfile.TarInfo(relative)
                member.size = len(content)
                member.mode = 0o600 if relative == "secrets.yaml" else 0o644
                tar.addfile(member, io.BytesIO(content))
    subprocess.run(kubectl + ["exec", "-i", args.pod, "--", "tar", "-xf", "-", "-C", remote], input=stream.getvalue(), check=True)
    # Check bundled integration code, while making installed components that
    # are absent from this bundle available for schema validation. No HA start.
    subprocess.run(execute + ["python", "-c", PREPARE_ENVIRONMENT, remote], check=True)
    live = json.loads(subprocess.check_output(execute + ["python", "-c", FINGERPRINT, remote, json.dumps(files)], text=True))
    check = subprocess.run(execute + ["python", "-m", "homeassistant", "--script", "check_config", "--config", remote, "--json"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    write_private(log, check.stdout)
    if check.returncode:
        raise SystemExit(f"Home Assistant rejected the staged configuration. See private log: {log}")
    report = check_report(check.stdout.decode(errors="replace"), remote)
    assert report["total_errors"] == 0, f"Home Assistant reported configuration errors; see {log}"
    checked_pod = json.loads(subprocess.check_output(kubectl + ["get", "pod", args.pod, "-o", "json"]))
    assert checked_pod["metadata"]["uid"] == pod["metadata"]["uid"], "Pod changed during staging; stage the release again"
    receipt = {"context": args.context, "namespace": args.namespace, "pod": args.pod, "pod_uid": pod["metadata"]["uid"], "remote_stage": remote, "release": release, "check_exit_code": check.returncode,
               "files": files, **live,
               "check_summary": {"total_errors": report["total_errors"], "total_warnings": report.get("total_warnings")}}
    write_private(args.receipt, (json.dumps(receipt, indent=2) + "\n").encode())
    print(f"Staged and validated with Home Assistant 2026.9.1: {remote}")
    print(f"Receipt: {args.receipt}; no live files changed and no actions invoked")


if __name__ == "__main__":
    main()
