# Breached-password list (IR-819, ASVS 2.1.7)

`breached-12plus.txt.gz` holds 30,402 passwords, lower-cased, one per line, that
have appeared in data breaches and are 12 to 128 characters long, the lengths
IRIS's policy otherwise allows. Shorter ones can't be chosen anyway, so they're
left out. `BreachedPasswordValidator` refuses any new password on it. The check
is local: no password, hash or prefix leaves the server.

**Source.** [SecLists](https://github.com/danielmiessler/SecLists) (MIT
licence, below), commit `51aa7644c96b3fb6db8de9ecf55aa91195209c80`, fetched
2026-11-15:

- `Passwords/Common-Credentials/100k-most-used-passwords-NCSC.txt`, the UK
  NCSC's list drawn from Have I Been Pwned breach data (1,197 entries kept);
- `Passwords/Common-Credentials/Pwdb_top-1000000.txt`, the most common
  passwords across breach dumps (29,205 more kept).

**Rebuild.** Download the two files into one directory as `ncsc100k.txt` and
`pwdb1m.txt`, then run `python -I build_breached_list.py <that dir> <out.txt.gz>`. It keeps lines of 12 to 128 characters that are valid UTF-8,
lower-cases them as Django's `CommonPasswordValidator` compares, deduplicates,
sorts and gzips with a zero mtime, so the same input written to a file of the same name gives the same bytes (gzip stores the name).
SHA-256 of this file:
`9ff0a03108ce30caa8c6d259b2061a2577593de382271d1087c859cffbbac8a3`.

## SecLists licence

Verbatim from the SecLists repository:

```text
MIT License

Copyright (c) 2018 Daniel Miessler

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
