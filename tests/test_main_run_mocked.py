import pandas as pd
import os
import types
import pytest

from wine_label_printer.main import WineLabelPrinter, fetch_inventory_from_cellartracker


def test_run_with_mocked_cellartracker_and_printer(monkeypatch, tmp_path):
    # Prepare a fake DataFrame with one row
    df = pd.DataFrame([{
        'Barcode': 'MOCK123',
        'Wine': 'Mock Wine',
        'Vintage': '2020',
        'Price': '30'
    }])

    # Monkeypatch the cellartracker fetch to return our df
    monkeypatch.setattr('wine_label_printer.main.fetch_inventory_from_cellartracker', lambda u, p: df)

    sent = {}

    # Monkeypatch Printer._send_with_retries to capture the ZPL
    def fake_send(self, zpl, timestamp, output_dir=None):
        sent['zpl'] = zpl

    monkeypatch.setattr('wine_label_printer.printer.Printer._send_with_retries', fake_send)

    # Use a temp config where storage.output_dir points to tmp_path
    cfg_overrides = {
        'storage': {
            'output_dir': str(tmp_path)
        },
        'printer': {
            'ip': '127.0.0.1',
            'port': 9100,
            'simulate': True
        }
    }

    wp = WineLabelPrinter(config_overrides=cfg_overrides)
    result = wp.run(test_mode=True)

    # Should have printed one label
    assert result == 1
    assert 'zpl' in sent
    assert '^XA' in sent['zpl'] and '^XZ' in sent['zpl']
    assert 'MOCK123' in sent['zpl']
