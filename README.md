# Booking Replay Guard

A small, independent travel-software demo prepared for an Agoda software-engineering application. It explores a failure mode in agent workflows: a retry should not silently create a second booking command.

This is not an Agoda integration. All property IDs, quote IDs and results are synthetic. It does not contact a travel service, reserve inventory or charge money.

## Run

Python 3.9 or newer, standard library only:

```sh
python guard.py
```

12 tests cover replay, changed-payload conflicts, field-order stability, input validation, independent keys, rollback and durable replay after reopening a SQLite database.

## Design

- Canonical JSON and SHA-256 identify the command payload.
- An idempotency key is stored with its payload fingerprint and simulated result.
- A matching retry returns the saved result and a replay flag.
- Reusing a key with changed dates, guest count or quote is rejected.
- `BEGIN IMMEDIATE` serializes SQLite writers before the lookup and insert.
- SQL values use bound parameters.

The operation and result are stored in the same local transaction. This provides a useful local invariant, not an exactly-once guarantee for external bookings. A production integration would need provider idempotency, reconciliation of ambiguous outcomes, quote expiry and availability checks, authorization, observability and privacy controls. Keys are not scoped by user in this demo and must be tenant-scoped before shared use. There is no expiry or cleanup policy.

No production readiness, performance or Agoda-system claims are made.
