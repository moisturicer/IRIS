"""Build breached-12plus.txt.gz from SecLists (IR-819). See README.md.

usage: python -I build_breached_list.py <dir with ncsc100k.txt and pwdb1m.txt> <out.txt.gz>
"""
import gzip
import hashlib
import sys

SOURCES = ("ncsc100k.txt", "pwdb1m.txt")


def build(source_dir: str, out: str) -> None:
    seen: set[str] = set()
    for name in SOURCES:
        kept = 0
        with open(f"{source_dir}/{name}", "rb") as handle:
            for raw in handle:
                try:
                    password = raw.decode("utf-8").rstrip("\r\n")
                except UnicodeDecodeError:
                    continue
                key = password.lower()  # Django's CommonPasswordValidator compares lower-cased
                if 12 <= len(password) <= 128 and key not in seen:
                    seen.add(key)
                    kept += 1
        print(f"{name}: {kept} kept")
    data = "\n".join(sorted(seen)).encode("utf-8") + b"\n"
    with gzip.GzipFile(out, "wb", mtime=0) as gz:  # zero mtime: the same input gives the same bytes
        gz.write(data)
    digest = hashlib.sha256(open(out, "rb").read()).hexdigest()
    print(f"{len(seen)} passwords, sha256 {digest}")


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2])
