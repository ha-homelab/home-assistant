"""Small, strict reader for Home Assistant YAML, without resolving credentials."""
from pathlib import Path
from dataclasses import dataclass
import yaml


@dataclass(frozen=True)
class Tagged:
    tag: str
    value: str


class Loader(yaml.SafeLoader):
    pass


def mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ValueError(f"Duplicate YAML key {key!r} at line {key_node.start_mark.line + 1}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
Loader.add_multi_constructor("!", lambda loader, tag, node: Tagged(tag, loader.construct_scalar(node)))


class Dumper(yaml.SafeDumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


Dumper.add_representer(Tagged, lambda dumper, obj: dumper.represent_scalar("!" + obj.tag, obj.value))


def read(path):
    return yaml.load(Path(path).read_text(), Loader=Loader)


def write(path, value, header=""):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + yaml.dump(value, Dumper=Dumper, sort_keys=False, allow_unicode=True, width=110))


def resolve(path, *, permit_missing_components=False, seen=None):
    """Resolve includes like HA, leaving !secret references symbolic."""
    path = Path(path).resolve()
    seen = set() if seen is None else seen
    if path in seen:
        raise ValueError(f"Circular include: {path}")
    seen = seen | {path}

    def walk(value):
        if isinstance(value, Tagged):
            if value.tag == "secret":
                return {"!secret": value.value}
            target = path.parent / value.value
            if value.tag == "include":
                return resolve(target, seen=seen)
            if value.tag.startswith("include_dir_"):
                if not target.is_dir():
                    if permit_missing_components and target.name in {"automations", "scripts"}:
                        return [] if target.name == "automations" else {}
                    raise ValueError(f"Missing include directory: {target}")
                files = sorted(f for f in target.rglob("*.yaml") if not any(p.startswith(".") for p in f.relative_to(target).parts))
                entries = [(f, resolve(f, seen=seen)) for f in files]
                if value.tag == "include_dir_list":
                    return [v for _, v in entries]
                if value.tag == "include_dir_merge_list":
                    if any(not isinstance(v, list) for _, v in entries):
                        raise ValueError(f"Non-list file in {target}")
                    return [item for _, values in entries for item in values]
                result = {}
                for file, values in entries:
                    values = {file.stem: values} if value.tag == "include_dir_named" else values
                    if not isinstance(values, dict):
                        raise ValueError(f"Non-mapping file in {target}")
                    overlap = result.keys() & values.keys()
                    if overlap:
                        raise ValueError(f"Duplicate merged keys in {target}: {sorted(overlap)}")
                    result.update(values)
                return result
            raise ValueError(f"Unsupported YAML tag: {value.tag}")
        if isinstance(value, dict):
            return {k: walk(v) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v) for v in value]
        return value

    return walk(read(path))
