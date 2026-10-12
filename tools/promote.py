#!/usr/bin/env python3
"""Promote a checked overlay with drift checks and an on-volume rollback copy."""
import argparse
import json
import os
from pathlib import Path
import subprocess

# Executed inside the existing container. No HA service or device action is called.
REMOTE = r'''
from pathlib import Path
import hashlib,json,os,re,shutil,subprocess,sys,tempfile
r=json.loads(sys.argv[1]); scope=sys.argv[2]
assert scope in ('overlay','automations')
stage=Path(r['remote_stage']); root=Path('/config')
assert stage.parent==root and stage.name.startswith('.ha-homelab-stage-')
assert stage.is_dir() and not stage.is_symlink()
paths=r['files']
selected=[p for p in paths if scope=='overlay' or p.startswith('automations/') or p=='release.json']
assert selected
def safe_path(base,name):
    relative=Path(name)
    assert not relative.is_absolute() and '..' not in relative.parts
    current=base
    for part in relative.parts:
        current=current/part
        assert not current.is_symlink(), 'Symlink in managed path: '+str(current)
    return current
def digest(p):
    if not p.exists(): return None
    assert p.is_file() and not p.is_symlink(), str(p)
    return hashlib.sha256(p.read_bytes()).hexdigest()
def tree(p):
    if not p.exists(): return None
    assert p.is_dir() and not p.is_symlink()
    found={}
    for f in sorted(p.rglob('*')):
        assert not f.is_symlink(), 'Symlink in managed directory: '+str(f)
        if f.is_file(): found[str(f.relative_to(p))]=digest(f)
    return found
directories=['automations'] if scope=='automations' else ['automations','scripts']
for p in paths:
    assert digest(safe_path(stage,p))==paths[p], 'Staged content changed: '+p
    safe_path(root,p)
    if scope=='automations' and p not in selected:
        assert digest(root/p)==paths[p], 'Non-automation content differs; use overlay promotion: '+p
for p in selected:
    if not any(p.startswith(d+'/') for d in directories):
        assert digest(root/p)==r['live_files'][p], 'Live file changed since staging: '+p
for d in ('automations','scripts'):
    expected={str(Path(p).relative_to(d)):value for p,value in paths.items() if p.startswith(d+'/')}
    assert expected and tree(stage/d)==expected, 'Staged directory differs from validated manifest: '+d
    if d in directories:
        assert tree(root/d)==r['live_directories'][d], 'Live directory changed since staging: '+d
    else:
        assert tree(root/d)==expected, 'Non-automation directory differs; use overlay promotion: '+d
backup=Path(tempfile.mkdtemp(prefix='.ha-homelab-backup-',dir=root))
applied=[]
try:
    for d in directories:
        old=root/d; saved=backup/d
        if old.exists(): os.replace(old,saved)
        applied.append((d,saved.exists(),'directory'))
        shutil.copytree(stage/d,old)
    # Write the root configuration last, after all its new includes exist.
    ordinary=[p for p in selected if not any(p.startswith(d+'/') for d in directories)]
    ordinary.sort(key=lambda p:(p=='configuration.yaml',p))
    for p in ordinary:
        target=root/p; saved=backup/p
        assert not target.is_symlink()
        existed=target.exists()
        if existed:
            saved.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(target,saved)
        target.parent.mkdir(parents=True,exist_ok=True)
        applied.append((p,existed,'file'))
        descriptor,temporary_name=tempfile.mkstemp(prefix='.'+target.name+'.ha-homelab-new-',dir=target.parent)
        os.close(descriptor); temporary=Path(temporary_name)
        try:
            shutil.copy2(stage/p,temporary); os.replace(temporary,target)
        finally:
            temporary.unlink(missing_ok=True)
    checked=subprocess.run([sys.executable,'-m','homeassistant','--script','check_config','--config','/config','--json'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (backup/'post-install-check.log').write_bytes(checked.stdout)
    (backup/'post-install-check.log').chmod(0o600)
    raw=checked.stdout.decode(errors='replace')
    report=None
    for match in re.finditer(r'(?m)^\s*\{',raw):
        try: candidate=json.JSONDecoder().raw_decode(raw[match.start():].lstrip())[0]
        except json.JSONDecodeError: continue
        if isinstance(candidate,dict) and candidate.get('config_dir')==str(root) and 'total_errors' in candidate:
            report=candidate; break
    if checked.returncode or not isinstance(report,dict) or report.get('total_errors')!=0:
        raise RuntimeError('Installed HA configuration rejected; restoring pre-promotion files')
except Exception:
    for p,existed,kind in reversed(applied):
        target=root/p; saved=backup/p
        if kind=='directory':
            if target.exists(): shutil.rmtree(target)
            if existed: shutil.copytree(saved,target)
        elif existed: shutil.copy2(saved,target)
        elif target.exists(): target.unlink()
    raise
(backup/'promotion.json').write_text(json.dumps({'release':r['release'],'scope':scope,'applied':applied},indent=2))
print(json.dumps({'backup':str(backup),'scope':scope,'installed_items':len(applied),'check_exit_code':0,'reloaded':False}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--scope", choices=("overlay", "automations"), required=True)
    args = parser.parse_args()
    output = args.receipt.with_suffix(f".{args.scope}.promotion.json")
    if output.exists():
        parser.error("Promotion result already exists; preserve it and use a newly staged receipt")
    receipt = json.loads(args.receipt.read_text())
    assert receipt["check_exit_code"] == 0
    command = ["kubectl", "--context", receipt["context"], "-n", receipt["namespace"]]
    pod = json.loads(subprocess.check_output(command + ["get", "pod", receipt["pod"], "-o", "json"]))
    assert pod["metadata"]["uid"] == receipt["pod_uid"], "Pod changed since staging; stage the release again"
    result = subprocess.check_output(command + ["exec", receipt["pod"], "--", "python", "-c", REMOTE, json.dumps(receipt), args.scope], text=True)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as file:
        file.write(result)
    print(result.strip())
    print("Files promoted and checked. Reload the intended HA domains, then verify runtime state.")


if __name__ == "__main__":
    main()
