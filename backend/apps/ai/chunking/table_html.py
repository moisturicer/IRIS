"""Keep a table's supplied cells when splitting its row grid (IR-840).

Fragments repeat the header and clip row spans to the selected rows. A cell
that started before a fragment is continued in its original column, for
display only; the embedding text still comes from the original row grid.
"""

from dataclasses import dataclass, field, replace
from html import escape
from html.parser import HTMLParser


_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


@dataclass
class _Node:
    tag: str
    attrs: tuple[tuple[str, str | None], ...] = ()
    children: list["_Node | str"] = field(default_factory=list)

    def render(self) -> str:
        attrs = "".join(f' {name}="{escape(value or "", quote=True)}"' for name, value in self.attrs)
        body = "".join(child.render() if isinstance(child, _Node) else escape(child, quote=False) for child in self.children)
        return f"<{self.tag}{attrs}>" + ("" if self.tag in _VOID else body + f"</{self.tag}>")


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, tuple(attrs))
        self.stack[-1].children.append(node)
        if tag not in _VOID:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(_Node(tag, tuple(attrs)))

    def handle_data(self, data):
        self.stack[-1].children.append(data)


@dataclass(frozen=True)
class _Cell:
    node: _Node
    row: int
    column: int
    rowspan: int
    colspan: int


def _span(node, name, remaining):
    try:
        value = int(dict(node.attrs).get(name) or 1)
    except ValueError:
        return 1
    return remaining if name == "rowspan" and value == 0 else min(remaining, max(1, value))


def _rows(node):
    result = []
    for child in node.children:
        if not isinstance(child, _Node):
            continue
        if child.tag == "tr":
            result.append(child)
        elif child.tag in {"thead", "tbody", "tfoot"}:
            result.extend(_rows(child))
    return result


class TableHTML:
    """One parsed table, reused while choosing fragment boundaries."""

    def __init__(self, table, rows, columns):
        self.table = table
        self.rows = rows
        self.cells: list[_Cell] = []
        for index, row in enumerate(rows):
            occupied = {
                column for cell in self.cells if cell.row + cell.rowspan > index
                for column in range(cell.column, cell.column + cell.colspan)
            }
            column = 0
            for node in row.children:
                if not isinstance(node, _Node) or node.tag not in {"th", "td"}:
                    continue
                while column in occupied:
                    column += 1
                colspan = _span(node, "colspan", columns)
                node = replace(node, attrs=tuple(
                    (key, str(colspan) if key == "colspan" else value) for key, value in node.attrs
                ))
                self.cells.append(_Cell(node, index, column, _span(node, "rowspan", len(rows) - index), colspan))
                column += colspan

    @classmethod
    def parse(cls, html: str, grid: tuple[tuple[str, ...], ...]) -> "TableHTML | None":
        parser = _Parser()
        parser.feed(html)
        table = next((node for node in parser.root.children if isinstance(node, _Node) and node.tag == "table"), None)
        if table is None:
            return None
        rows = _rows(table)
        columns = max((len(row) for row in grid), default=1)
        return cls(table, rows, max(1, columns)) if len(rows) == len(grid) else None

    def fragment(self, start: int, stop: int) -> str:
        selected = [0, *range(start, stop)]
        rendered = []
        for index in selected:
            cells = [cell for cell in self.cells if cell.row == index]
            if index == start:
                cells += [cell for cell in self.cells if 0 < cell.row < start < cell.row + cell.rowspan]
            nodes = []
            for cell in sorted(cells, key=lambda value: value.column):
                span = sum(row >= index and row < cell.row + cell.rowspan for row in selected)
                attrs = tuple((key, value) for key, value in cell.node.attrs if key != "rowspan")
                if span > 1:
                    attrs += (("rowspan", str(span)),)
                nodes.append(replace(cell.node, attrs=attrs))
            rendered.append(replace(self.rows[index], children=nodes))
        captions = [node for node in self.table.children if isinstance(node, _Node) and node.tag in {"caption", "colgroup"}]
        return replace(self.table, children=captions + [
            _Node("thead", children=rendered[:1]), _Node("tbody", children=rendered[1:]),
        ]).render()
