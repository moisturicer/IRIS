"""Private parser subprocess. Exit codes are the complete, safe result protocol."""
import sys


class OverBudget(Exception):
    pass


class ActiveContent(Exception):
    pass


def inspect(path, max_pages, max_objects, max_depth):
    from pypdf import PdfReader
    from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject

    with open(path, "rb") as source:
        if b"%PDF-" not in source.read(1024):
            return 2
        source.seek(0)
        reader = PdfReader(source, strict=False)
        if reader.is_encrypted:
            return 3
        pages = len(reader.pages)
        if not pages:
            return 2
        if pages > max_pages:
            return 5
        visited = set()
        count = 0

        def resolved(obj):
            nonlocal count
            chain = set()
            while isinstance(obj, IndirectObject):
                count += 1
                key = (obj.idnum, obj.generation)
                if count > max_objects or key in chain:
                    raise OverBudget
                chain.add(key)
                obj = obj.get_object()
            return obj

        def visit(obj, depth=0, context="normal"):
            nonlocal count
            count += 1
            if count > max_objects or depth > max_depth:
                raise OverBudget
            if isinstance(obj, IndirectObject):
                key = (obj.idnum, obj.generation, context)
                if key in visited:
                    return
                visited.add(key)
                visit(obj.get_object(), depth + 1, context)
            elif isinstance(obj, DictionaryObject):
                if any(key in obj for key in (
                    "/JS", "/JavaScript", "/EmbeddedFiles", "/EF", "/AF",
                    "/XFA", "/RichMediaContent",
                )):
                    raise ActiveContent
                if resolved(obj.get("/Type")) == "/EmbeddedFile":
                    raise ActiveContent
                action = resolved(obj.get("/S"))
                if context in {"open_action", "automatic_action"} and action != "/GoTo":
                    raise ActiveContent
                if isinstance(action, str) and action in {"/JavaScript", "/Launch", "/SubmitForm", "/ImportData",
                              "/Rendition", "/Movie", "/Sound", "/GoToE"}:
                    raise ActiveContent
                if action == "/URI":
                    from urllib.parse import urlsplit
                    uri = str(resolved(obj.get("/URI", ""))).strip().lower()
                    if (any(ord(char) < 32 or ord(char) == 127 for char in uri)
                            or urlsplit(uri).scheme not in {"", "https", "http", "mailto", "ftp", "ftps", "tel", "doi", "urn"}):
                        raise ActiveContent
                for key, value in obj.items():
                    if context == "automatic_map":
                        child_context = "automatic_action"
                    elif key == "/AA":
                        child_context = "automatic_map"
                    elif key == "/OpenAction":
                        child_context = "open_action"
                    elif key == "/Next" and context in {"open_action", "automatic_action"}:
                        child_context = "automatic_action"
                    else:
                        child_context = "normal"
                    visit(value, depth + 1, child_context)
            elif isinstance(obj, ArrayObject):
                for value in obj:
                    # An OpenAction array is a page destination; a Next array
                    # is a group of actions and retains its security context.
                    visit(value, depth + 1, "normal" if context == "open_action" else context)
            elif context != "normal":
                raise ActiveContent

        visit(reader.trailer)
        for generation, objects in reader.xref.items():
            if generation == 65535:
                continue
            for number in objects:
                if number:
                    visit(IndirectObject(number, generation, reader))
        for number in reader.xref_objStm:
            visit(IndirectObject(number, 0, reader))
    return 0


def main():
    try:
        import resource

        memory_mib, max_pages, max_objects, max_depth = map(int, sys.argv[2:])
        memory = memory_mib * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        return inspect(sys.argv[1], max_pages, max_objects, max_depth)
    except (MemoryError, OverBudget, RecursionError):
        return 5
    except ActiveContent:
        return 4
    except Exception:
        return 2


if __name__ == "__main__":
    sys.exit(main())
