"""Synthetic booking-command idempotency demo. No network or payments."""
import hashlib
import json
import sqlite3
import unittest


def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False)


class Conflict(ValueError):
    pass


class Guard:
    def __init__(self, db=':memory:'):
        self.db = sqlite3.connect(db)
        self.db.execute('CREATE TABLE IF NOT EXISTS commands (key TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, result TEXT NOT NULL)')

    def execute(self, key, payload):
        if not isinstance(key, str) or not key.strip():
            raise ValueError('A nonempty idempotency key is required')
        required = {'property_id', 'check_in', 'check_out', 'guest_count', 'quote_id'}
        if set(payload) != required:
            raise ValueError('Unexpected or missing booking fields')
        if type(payload['guest_count']) is not int or payload['guest_count'] < 1:
            raise ValueError('guest_count must be a positive integer')
        from datetime import date
        if date.fromisoformat(payload['check_out']) <= date.fromisoformat(payload['check_in']):
            raise ValueError('check_out must follow check_in')
        for f in ('property_id', 'quote_id'):
            if not isinstance(payload[f], str) or not payload[f].strip():
                raise ValueError(f + ' must be nonempty')
        fingerprint = hashlib.sha256(canonical(payload).encode()).hexdigest()
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row = self.db.execute('SELECT fingerprint, result FROM commands WHERE key=?', (key,)).fetchone()
            if row:
                if row[0] != fingerprint:
                    raise Conflict('Key reused with a different command')
                self.db.commit()
                return json.loads(row[1]), True
            # The entire simulated operation is local, inside this transaction.
            result = {'status': 'simulated', 'booking_ref': 'demo-' + hashlib.sha256(key.encode()).hexdigest()[:12]}
            self.db.execute('INSERT INTO commands VALUES (?,?,?)', (key, fingerprint, canonical(result)))
            self.db.commit()
            return result, False
        except Exception:
            self.db.rollback()
            raise


class Tests(unittest.TestCase):
    def setUp(self):
        self.g = Guard()
        self.p = dict(property_id='synthetic-1', check_in='2027-01-11', check_out='2027-01-13', guest_count=1, quote_id='quote-demo')

    def test_first_command(self):
        self.assertFalse(self.g.execute('a', self.p)[1])

    def test_retry_reuses_result(self):
        a, _ = self.g.execute('a', self.p)
        b, replay = self.g.execute('a', self.p)
        self.assertEqual(a, b)
        self.assertTrue(replay)

    def test_field_order_is_irrelevant(self):
        self.g.execute('a', self.p)
        self.assertTrue(self.g.execute('a', dict(reversed(list(self.p.items()))))[1])

    def test_changed_guest_count_conflicts(self):
        self.g.execute('a', self.p)
        with self.assertRaises(Conflict):
            self.g.execute('a', self.p | {'guest_count': 2})

    def test_changed_quote_conflicts(self):
        self.g.execute('a', self.p)
        with self.assertRaises(Conflict):
            self.g.execute('a', self.p | {'quote_id': 'new-quote'})

    def test_distinct_keys_are_independent(self):
        self.assertNotEqual(self.g.execute('a', self.p)[0], self.g.execute('b', self.p)[0])

    def test_blank_key_rejected(self):
        with self.assertRaises(ValueError):
            self.g.execute(' ', self.p)

    def test_invalid_dates_rejected(self):
        with self.assertRaises(ValueError):
            self.g.execute('a', self.p | {'check_out': '2027-01-01'})

    def test_invalid_guest_count_rejected(self):
        for v in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                self.g.execute('a', self.p | {'guest_count': v})

    def test_state_persists(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / 'guard.db')
            first = Guard(path)
            a, _ = first.execute('a', self.p)
            first.db.close()
            second = Guard(path)
            b, replay = second.execute('a', self.p)
            self.assertEqual(a, b)
            self.assertTrue(replay)
            second.db.close()

    def test_unknown_field_rejected(self):
        with self.assertRaises(ValueError):
            self.g.execute('a', self.p | {'card': 'not-accepted'})

    def test_conflict_does_not_damage_original(self):
        self.g.execute('a', self.p)
        with self.assertRaises(Conflict):
            self.g.execute('a', self.p | {'guest_count': 2})
        self.assertTrue(self.g.execute('a', self.p)[1])


if __name__ == '__main__':
    unittest.main(verbosity=2)
