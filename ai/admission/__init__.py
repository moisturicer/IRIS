"""The AI runtime's provider admission (IR-725, ADR-049 §10, §11).

Every physical attempt a run makes reserves its worst case in the ledger
Django's admission already writes (`ai_providercampaign`,
`ai_providerreservation`, IR-545): one ledger, the same campaign lock and the
same settlement rules, rows marked `owner = 'ai'`. `limits` reads the
settings, `ledger` reserves and settles before
sending, `transport` wraps a provider, `report` shows a run's spending.
"""
