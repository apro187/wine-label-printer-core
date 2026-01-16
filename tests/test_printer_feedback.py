import socket
import threading
import time
import json
import os

from wine_label_printer.printer import Printer


def start_dummy_printer_server(port, response_payload, delay=0):
    """Start a simple TCP server that reads data then sends response_payload (as JSON) and closes."""
    def _server():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('127.0.0.1', port))
            s.listen(1)
            conn, addr = s.accept()
            with conn:
                data = b''
                while True:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                time.sleep(delay)
                conn.sendall((json.dumps(response_payload) + "\n").encode('utf-8'))
    t = threading.Thread(target=_server, daemon=True)
    t.start()
    return t


def test_printer_saves_feedback_to_issues(tmp_path):
    printer = Printer()
    test_port = 19100
    response = {"status":"ok","nonSupportedCommands":["^FO","^A0"]}
    start_dummy_printer_server(test_port, response)

    # ensure output dir is the temp path
    zpl = '^XA^FO50,50^A0N,40,40^FDHello^FS^XZ'
    timestamp, path, target_dir = printer._write_zpl_file(zpl, output_dir=str(tmp_path))
    # send and allow feedback processing
    printer.printer_ip = '127.0.0.1'
    printer.port = test_port
    printer._send_with_retries(zpl, timestamp, output_dir=str(tmp_path))

    issues_file = os.path.join(str(tmp_path), f"{timestamp}.unsupported.txt")
    assert os.path.exists(issues_file), f"Expected issues file {issues_file} to exist"
    with open(issues_file, 'r', encoding='utf-8') as f:
        content = f.read()
    assert '^FO' in content
    assert '^A0' in content
