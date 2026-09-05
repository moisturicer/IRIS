# Marks `apps` as a regular package.
#
# Without this file `apps` is an implicit namespace package. Dotted paths such as
# `manage.py test apps.documents.tests` still resolve, so the gap is invisible day
# to day -- but unittest's *discovery* walk cannot traverse it, and bare
# `manage.py test` reports "Found 0 test(s)" no matter how many test files exist
# under apps/. A CI job running the default command would go green having executed
# nothing (IR-163).
