import unittest
from types import SimpleNamespace

from market_data import _parse_margin, _parse_spot, _payload_trading_date, evaluate_regime


class ParserTests(unittest.TestCase):
    def test_weekend_query_uses_actual_date_in_roc_title(self):
        payload = {"title": "115年09月04日 三大法人買賣金額統計表"}
        self.assertEqual(_payload_trading_date(payload, "20260905"), "20260904")

    def test_spot_parser_uses_foreign_net(self):
        payload = {
            "fields": ["單位名稱", "買進金額", "賣出金額", "買賣差額"],
            "data": [["外資及陸資(不含外資自營商)", "100", "60", "40"]],
        }
        self.assertEqual(_parse_spot(payload), 40)

    def test_margin_parser_converts_thousands_to_twd(self):
        payload = {"tables": [{
            "fields": ["項目", "前日餘額", "今日餘額"],
            "data": [["融資金額(仟元)", "500000000", "510000000"]],
        }]}
        self.assertEqual(_parse_margin(payload), 510_000_000_000)


class RegimeTests(unittest.TestCase):
    def row(self, futures, spot, margin):
        return SimpleNamespace(
            foreign_futures_net=futures,
            foreign_spot_net_twd=spot,
            margin_balance_twd=margin,
        )

    def test_strong_bull_requires_confirmation(self):
        history = [
            self.row(-48_000, 12e9, 515e9),
            self.row(-42_000, 15e9, 510e9),
            self.row(-35_000, 18e9, 505e9),
            self.row(-31_000, 20e9, 500e9),
        ]
        current = SimpleNamespace(
            foreign_futures_net=-25_000,
            foreign_spot_net_twd=22e9,
            margin_balance_twd=495e9,
            taiex_close=25_000,
            taiex_ma20=24_500,
            taiex_new_20d_low=False,
        )
        self.assertEqual(evaluate_regime(current, history)["regime"], "強多頭")

    def test_bearish_gate(self):
        current = SimpleNamespace(
            foreign_futures_net=-81_000,
            foreign_spot_net_twd=-35e9,
            margin_balance_twd=540e9,
            taiex_close=23_000,
            taiex_ma20=24_000,
            taiex_new_20d_low=True,
        )
        self.assertEqual(evaluate_regime(current, [self.row(-75_000, -20e9, 535e9)])["regime"], "偏空")


if __name__ == "__main__":
    unittest.main()
