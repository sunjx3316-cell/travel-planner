import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from backend.app.routers import rail


class RailFaresTests(unittest.TestCase):
    def setUp(self):
        rail._cache.clear()
        self.pair = {"from": "BJP", "to": "TJP", "date": datetime.now(timezone(timedelta(hours=8))).date().isoformat()}

    def test_price_records_discard_inventory_and_zero_prices(self):
        self.assertEqual(rail.parse_fares("O005530021M009330014"), {"O": 55.3, "M": 93.3})
        self.assertEqual(rail.parse_fares("O000000021"), {})
        self.assertEqual(rail.parse_fares("broken"), {})
        self.assertEqual(rail.parse_fares("O005533021"), {"W": 55.3})

    def test_rows_are_bound_to_requested_pair(self):
        fields = [""] * 40
        fields[3], fields[6], fields[7], fields[8], fields[9], fields[39] = "G1", "BJP", "TJP", "09:00", "09:30", "O005530021"
        rows = rail.extract_rows({"status": True, "data": {"result": ["|".join(fields), "bad"]}}, self.pair)
        self.assertEqual(rows[0]["fares"], {"O": 55.3})
        self.assertNotIn("inventory", rows[0])
        self.assertEqual(rail.extract_rows({"data": {"result": ["|".join(fields)]}}, {**self.pair, "to": "SHH"}), [])

    def test_input_limits(self):
        self.assertEqual(rail.validate_pair(self.pair), self.pair)
        for change in ({"from": "https://evil"}, {"to": "BJP"}, {"date": "2026-02-30"}, {"required": ["G1"] * 5}, {"required": ["G1&x=1"]}, {"toName": "x" * 26}):
            with self.assertRaises(ValueError):
                rail.validate_pair({**self.pair, **change})

    def test_unavailable_never_becomes_zero_fare(self):
        with patch.object(rail, "_fetch", side_effect=ValueError("verification page")):
            response = rail._quote_batch([self.pair])
        row = json.loads(response.body)["results"][0]
        self.assertEqual(row["rows"], [])
        self.assertIn("error", row)
        self.assertEqual(len(rail._cache), 0)

    def test_cache_avoids_network(self):
        row = dict(train="G1", **self.pair, fares={"O": 55}, queriedAt=rail._now())
        value = dict(pair=self.pair, rows=[row], queriedAt=rail._now(), source="12306公开查询", cached=False)
        key = (self.pair["from"], self.pair["to"], self.pair["date"])
        rail._cache[key] = (rail.monotonic(), value)
        with patch.object(rail, "_fetch", side_effect=AssertionError("must use cache")):
            response = rail._quote_batch([{**self.pair, "required": ["G1"]}])
        self.assertTrue(json.loads(response.body)["results"][0]["cached"])

    def test_no_unbounded_queue(self):
        rail._gate.acquire()
        try:
            response = rail._quote_batch([self.pair])
            self.assertEqual(response.status_code, 429)
        finally:
            rail._gate.release()


if __name__ == '__main__':
    unittest.main()


def test_api_boundaries():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(rail.router)
    with TestClient(app) as client:
        assert client.get('/api/rail/fares').status_code == 405
        assert client.post('/api/rail/fares', json={"pairs": []}).status_code == 400
        assert client.post('/api/rail/fares', json={"pairs": [{}] * 9}).status_code == 400
        assert client.post('/api/rail/fares', content=b'x' * 16001).status_code == 413
        assert client.post('/api/rail/fares', content=b'{bad').status_code == 400
        with patch.object(rail, '_fetch', side_effect=AssertionError('invalid input must not call upstream')):
            response = client.post('/api/rail/fares', json={"pairs": [{"from": "URL", "to": "URL", "date": "2026-10-28"}]})
        assert response.status_code == 200
        assert response.json()['results'][0]['rows'] == []
        assert response.headers['Cache-Control'] == 'no-store'
