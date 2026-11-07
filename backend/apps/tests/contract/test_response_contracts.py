"""
Does each endpoint a screen reads still answer with the structure recorded for
it? (IR-915)

Every contract in `contracts.py` is fired against the access matrix's world,
and the answer's structure is compared with the sample stored in the
repository's `contracts/<name>.json` (`shape.py` says what counts as a
change). A removed or retyped field fails the test and names the field. The
frontend checks the same fixtures against its own types, so a response that
drifts from either side fails a test.

**Refreshing.** After a deliberate change, record the new answers and commit
the diff, which a reviewer reads as the change to the contract:

    UPDATE_CONTRACTS=1 python -m pytest apps/tests/contract -q

CI never sets it, so a fixture is never rewritten there.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import warnings
from pathlib import Path

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.library.models import SavedRecord
from apps.records.models import Classification
from apps.tests.access.world import build_world
from apps.tests.contract.contracts import CONTRACTS, Contract
from apps.tests.contract.shape import compare, sample_of, shape_of

#: The repository root's `contracts/`: backend/apps/tests/contract/ is four levels down.
CONTRACTS_DIR = Path(os.environ.get("CONTRACTS_DIR") or Path(__file__).resolve().parents[4] / "contracts")
REFRESH = os.environ.get("UPDATE_CONTRACTS") == "1"
REFRESH_COMMAND = "UPDATE_CONTRACTS=1 python -m pytest apps/tests/contract -q"


def _redacted(value, keys):
    if isinstance(value, dict):
        return {k: "<redacted>" if k in keys else _redacted(v, keys) for k, v in value.items()}
    if isinstance(value, list):
        return [_redacted(item, keys) for item in value]
    return value


@pytest.mark.db_required
class ResponseContractTests(APITestCase):
    @classmethod
    def setUpClass(cls):
        # Before super(): setUpTestData writes the fixtures' files.
        cls._media_root = tempfile.mkdtemp(prefix="iris-contracts-")
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        cls.world = build_world()
        # Rows the world does not hold, so a list is not an empty sample.
        Classification.objects.get_or_create(name="Contract classification")
        SavedRecord.objects.create(
            owner=cls.world.users["owner"], record=cls.world.objects["published"],
            reading_status="reading",
        )

    def _ask(self, contract: Contract):
        kwargs = {key: self.world.value(name) for key, name in contract.kwargs}
        url = reverse(contract.route, kwargs=kwargs)
        if contract.query:
            url = f"{url}?" + "&".join(f"{k}={v}" for k, v in contract.query)
        cache.clear()  # DRF's throttles count in it
        self.client.force_authenticate(self.world.users[contract.role])
        try:
            body = contract.body(self.world) if contract.body else None
            send = getattr(self.client, contract.method.lower())
            response = send(url, body, format="json") if body is not None else send(url)
        finally:
            self.client.force_authenticate(None)
        return url, response

    def _path(self, contract: Contract) -> Path:
        return CONTRACTS_DIR / f"{contract.name}.json"

    def _require_directory(self):
        if CONTRACTS_DIR.is_dir() or REFRESH:
            return
        if os.environ.get("CI"):
            self.fail(f"{CONTRACTS_DIR} does not exist: the repository's contracts/ directory is missing")
        # The dev container mounts only backend/, so the fixtures are not there.
        self.skipTest(f"{CONTRACTS_DIR} is not mounted; set CONTRACTS_DIR or run from a checkout")

    def test_every_covered_response_keeps_its_recorded_structure(self):
        self._require_directory()
        failures, added = [], []
        for contract in CONTRACTS:
            with self.subTest(contract=contract.name):
                url, response = self._ask(contract)
                self.assertEqual(
                    response.status_code, 200,
                    f"{contract.name}: {contract.method} {url} answered {response.status_code}, "
                    f"not 200, so there is no response to record",
                )
                live = response.json()
                if REFRESH:
                    self._record(contract, url, live)
                    continue
                path = self._path(contract)
                if not path.is_file():
                    failures.append(
                        f"{contract.name}: no fixture at contracts/{path.name}. Record it with: {REFRESH_COMMAND}"
                    )
                    continue
                stored = json.loads(path.read_text(encoding="utf-8"))
                for key, declared in (("route", contract.route), ("method", contract.method),
                                      ("as", contract.role)):
                    if stored.get(key) != declared:
                        failures.append(
                            f"{contract.name}: the fixture records {key}={stored.get(key)!r} but the "
                            f"contract declares {declared!r}. Re-record it with: {REFRESH_COMMAND}"
                        )
                diff = compare(shape_of(stored["sample"]), shape_of(live))
                failures.extend(f"{contract.name} ({contract.method} {url}) {item}" for item in diff.breaking)
                added.extend(f"{contract.name} {item}" for item in diff.added)
        if added:
            warnings.warn(
                "Fields the response gained since its fixture was recorded (a screen that does not "
                f"read them is unaffected; refresh with {REFRESH_COMMAND} so the frontend's types "
                "are checked against them):\n  " + "\n  ".join(added),
                stacklevel=1,
            )
        self.assertEqual(
            failures, [],
            f"\n{len(failures)} contract(s) changed. If the change is deliberate, update the "
            f"frontend's types and re-record with: {REFRESH_COMMAND}\n  " + "\n  ".join(failures),
        )

    def test_no_fixture_is_left_without_a_contract(self):
        """A deleted contract takes its fixture with it, or the frontend keeps checking a ghost."""
        self._require_directory()
        if not CONTRACTS_DIR.is_dir():
            return
        declared = {contract.name for contract in CONTRACTS}
        stored = {path.stem for path in CONTRACTS_DIR.glob("*.json")}
        self.assertEqual(sorted(stored - declared), [], "fixtures with no contract in contracts.py")

    def _record(self, contract: Contract, url: str, live) -> None:
        CONTRACTS_DIR.mkdir(parents=True, exist_ok=True)
        document = {
            "route": contract.route,
            "method": contract.method,
            "as": contract.role,
            "sample": _redacted(sample_of(live), contract.redact),
        }
        with open(self._path(contract), "w", encoding="utf-8", newline="\n") as handle:
            json.dump(document, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
