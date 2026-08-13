"""The grammar registry (per the generality-first ruling).

A grammar is a CORPUS-specific parsing rule: how one project's tables
and cells encode meaning (a prerequisites phrase, a blocked layout, a
matrix with decorated headers). The engine HOSTS grammars, it does not
contain them: engine modules resolve declared `parser:` names through
this registry, and each corpus's grammar module registers its own.
Generic structural machinery (markdown, mentions, CSV cell parsing)
stays in graph/parsers.py — the membership test is the storybook test:
would a corpus that never heard of any one project need it?

A consuming corpus registers its grammars by importing its own grammar
module before extraction runs (each grammar function decorated with
@register). The engine ships no grammars of its own; an ontology that
declares a parser no loaded grammar module provides gets the missing-
grammar refusal below, naming the gap.
"""

_REGISTRY = {}


def register(name):
    """Decorator: register a grammar callable under its declared name."""
    def wrap(fn):
        _REGISTRY[name] = fn
        return fn
    return wrap


def get(name):
    """The grammar registered under `name` — a missing grammar is a
    corpus-configuration error, reported in the engine's error form."""
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"Attempted to parse with grammar '{name}'. Failed due to: "
            "no grammar registered under that name — the ontology "
            "declares a parser this corpus's grammar module does not "
            "provide.") from None


def get_optional(name):
    return _REGISTRY.get(name)
