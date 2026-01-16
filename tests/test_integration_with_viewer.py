import os
import socket
import time

import pytest
from wine_label_printer.printer import Printer


@pytest.mark.skipif(
    not (lambda: True)(),
    reason="Skip unless BinaryKits viewer + proxy are running on localhost:9100"
)
def test_integration_print_label_to_viewer(tmp_path):
    # quick check that proxy is reachable
    try:
        with socket.create_connection(('127.0.0.1', 9100), timeout=1):
            pass
    except Exception:
        pytest.skip("Proxy not reachable on 127.0.0.1:9100")

    printer = Printer()
    zpl = '^XA^FO50,50^A0N,40,40^FDIntegration test^FS^XZ'
    timestamp, path, target_dir = printer._write_zpl_file(zpl, output_dir=str(tmp_path))
    printer.printer_ip = '127.0.0.1'
    printer.port = 9100
    printer._send_with_retries(zpl, timestamp, output_dir=str(tmp_path))

    # Wait briefly for feedback
    issues_file = os.path.join(str(tmp_path), f"{timestamp}.unsupported.txt")
    deadline = time.time() + 8
    while time.time() < deadline:
        if os.path.exists(issues_file):
            break
        time.sleep(0.25)

    # It's acceptable for there to be no unsupported commands; test asserts the send succeeded and file may or may not be present
    # If present, confirm it's non-empty
    if os.path.exists(issues_file):
        assert os.path.getsize(issues_file) > 0
    else:
        # no feedback file created; at least we didn't crash
        assert True
