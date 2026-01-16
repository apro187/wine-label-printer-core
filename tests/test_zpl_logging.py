import os
import logging

from wine_label_printer.printer import Printer


def test_write_zpl_logs_and_doesnt_save_by_default(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    printer = Printer()
    zpl = '^XA^FO50,50^A0N,40,40^FDHello Logging^FS^XZ'
    timestamp, path, target_dir = printer._write_zpl_file(zpl, output_dir=str(tmp_path))

    # Should not create a .zpl file by default
    assert path is None

    # Should log an info message with truncated zpl
    assert any('ZPL package created' in rec.message for rec in caplog.records)
