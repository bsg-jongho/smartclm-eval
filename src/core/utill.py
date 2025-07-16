import re

from inflection import camelize


def camel_to_snake_case(name: str) -> str:
    name = re.sub("([a-z0-9])([A-Z])", r"\1_\2", name)
    return name.lower()


def to_camel(string: str) -> str:
    return camelize(string, False)


def dict_keys_to_camel(d):
    if isinstance(d, dict):
        return {to_camel(k): dict_keys_to_camel(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [dict_keys_to_camel(i) for i in d]
    else:
        return d
