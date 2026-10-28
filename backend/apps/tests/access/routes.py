"""
Every route Django resolves, found by walking the URLconf (IR-615).

Nothing here is hand-listed. `enumerate_routes()` walks `get_resolver()`
recursively, so a route added to any included URLconf -- a router, a
`path()` in an app's `urls.py`, a new `include()` in `config/urls.py` --
appears without anyone remembering to add it. That is the whole point: the
matrix can only refuse an undeclared route it can see.

A route is identified by **its app and its URL name**. The name alone is not
unique: every DRF `DefaultRouter` names its root view `api-root`, and the
records and opportunities routers both have one. Within an app a name is
unique, except for the router's format-suffix variant (`record-list` and
`record-list` with `.json`), which is the same view and is collapsed here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import ModuleType

from django.urls import URLPattern, URLResolver, get_resolver

#: Methods the matrix does not declare. HEAD is GET without a body and OPTIONS
#: is DRF's metadata response; both pass through the same permission checks as
#: the method they describe, so declaring them would double the table and test
#: nothing the GET row does not.
IMPLICIT_METHODS = frozenset({"HEAD", "OPTIONS"})

#: Namespaces whose routes are not this API's, with the reason. They are
#: declared here, visibly, rather than silently skipped.
OUT_OF_SCOPE_NAMESPACES = {
    "admin": (
        "Django admin: gated by Django's own is_staff/is_superuser checks, not "
        "by DRF permissions. IR-165 keeps that separation deliberately."
    ),
    "djdt": "django-debug-toolbar: mounted only when DEBUG is on (config/urls.py).",
}


@dataclass
class Route:
    """One named route, with every pattern that reaches its view."""

    app: str | None
    name: str | None
    pattern: str
    view: object
    methods: frozenset[str]
    namespaces: tuple[str, ...] = ()
    #: Format-suffix variants of the same route, collapsed into this one.
    variants: list[str] = field(default_factory=list)

    @property
    def key(self) -> tuple[str | None, str | None]:
        return (self.app, self.name)

    @property
    def out_of_scope(self) -> str | None:
        for namespace in self.namespaces:
            if namespace in OUT_OF_SCOPE_NAMESPACES:
                return OUT_OF_SCOPE_NAMESPACES[namespace]
        return None

    def __str__(self) -> str:
        return f"{self.app}:{self.name} ({self.pattern})"


def _module_name(urlconf) -> str | None:
    if isinstance(urlconf, str):
        return urlconf
    if isinstance(urlconf, ModuleType):
        return urlconf.__name__
    return None


def _app_of(modules: list[str]) -> str | None:
    """
    The app a route belongs to: the innermost `apps.<app>` URLconf it was
    included through. `config/urls.py` includes `apps.records.urls`, which
    includes a router's list, so the router's routes are the records app's.
    """
    for module in reversed(modules):
        parts = module.split(".")
        if len(parts) >= 2 and parts[0] == "apps":
            return parts[1]
    return None


def view_class(callback):
    """The class behind a view callback: DRF sets `cls`, Django `view_class`."""
    return getattr(callback, "cls", None) or getattr(callback, "view_class", None)


def methods_of(callback) -> frozenset[str]:
    """
    The HTTP methods a route actually answers, HEAD and OPTIONS aside.

    A ViewSet bound by a router or by `as_view({...})` answers exactly the
    methods in its `actions` map. A plain view answers each method in its
    `http_method_names` that it has a handler for. A function view (Django
    admin's) declares nothing, which is empty here: such routes are out of
    scope or undeclared, never fired.
    """
    actions = getattr(callback, "actions", None)
    if actions:
        return frozenset(m.upper() for m in actions) - IMPLICIT_METHODS
    cls = view_class(callback)
    if cls is None:
        return frozenset()
    return frozenset(
        m.upper() for m in cls.http_method_names if hasattr(cls, m)
    ) - IMPLICIT_METHODS


def _walk(resolver, prefix, modules, namespaces):
    for entry in resolver.url_patterns:
        if isinstance(entry, URLResolver):
            module = _module_name(entry.urlconf_name)
            yield from _walk(
                entry,
                prefix + str(entry.pattern),
                modules + ([module] if module else []),
                namespaces + ((entry.namespace,) if entry.namespace else ()),
            )
        elif isinstance(entry, URLPattern):
            yield Route(
                app=_app_of(modules),
                name=entry.name,
                pattern=prefix + str(entry.pattern),
                view=entry.callback,
                methods=methods_of(entry.callback),
                namespaces=namespaces,
            )


def enumerate_routes(urlconf=None) -> list[Route]:
    """
    Every route in `urlconf` (default: `ROOT_URLCONF`), one per app and name.

    Format-suffix variants are folded into the route they suffix. Two routes
    in one app sharing a name but not a view are kept apart, so the matrix can
    report the collision instead of testing one and missing the other.
    """
    routes: dict[tuple, Route] = {}
    for route in _walk(get_resolver(urlconf), "", [_module_name(urlconf) or ""], ()):
        same = routes.get(route.key)
        if same is not None and route.name and view_class(same.view) is view_class(route.view):
            same.variants.append(route.pattern)
            same.methods = same.methods | route.methods
            continue
        key = route.key if same is None else (*route.key, len(routes))
        routes[key] = route
    return list(routes.values())


def name_collisions(routes: list[Route]) -> list[str]:
    """Names used by two different views inside one app."""
    seen: dict[tuple, Route] = {}
    collisions = []
    for route in routes:
        if route.name is None:
            continue
        if route.key in seen:
            collisions.append(f"{route.key}: {seen[route.key].pattern} and {route.pattern}")
        else:
            seen[route.key] = route
    return collisions
