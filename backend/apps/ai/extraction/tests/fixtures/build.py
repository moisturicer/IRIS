"""Write the fixture PDFs: ``python -m apps.ai.extraction.tests.fixtures.build``."""

from . import DIRECTORY, FIXTURES, render


def main() -> None:
    for fixture in FIXTURES.values():
        (DIRECTORY / fixture.filename).write_bytes(render(fixture))
        print(f"wrote {fixture.filename}")


if __name__ == "__main__":
    main()
