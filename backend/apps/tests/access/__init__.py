"""
The endpoint authorization matrix (IR-615, IR-611 slice 3).

`routes` enumerates every route Django resolves, `table` declares who may
reach each one, `world` builds the people and objects the requests act on,
and `apps/tests/test_access_matrix.py` fires every request and compares.
"""
