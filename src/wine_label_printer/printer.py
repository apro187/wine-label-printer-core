import socket
import yaml
import os
import time
import logging
from datetime import datetime, timedelta
import base64
import requests

logger = logging.getLogger(__name__)

class Printer:
    def __init__(self, config_path=None, simulate=False):
        if config_path is None:
            config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "config.yaml"))
        self.config = self.load_config(config_path)
        self.printer_ip = self.config["printer"]["ip"]
        self.port = 9100  # Default port for Zebra printers
        self.simulate = simulate
        self.temp_dir = self.config["printer"].get(
            "temp_dir",
            os.path.join(os.path.dirname(__file__), "tmp")
        )
        os.makedirs(self.temp_dir, exist_ok=True)
        self.viewer_config = self.config.get("viewer", {})
        self.network_timeout = float(self.config.get("printer", {}).get("network_timeout", 5))
        self.retry_attempts = int(self.config.get("printer", {}).get("retry_attempts", 1))
        self.retry_delay = float(self.config.get("printer", {}).get("retry_delay", 2))

    def load_config(self, path):
        with open(path, "r") as file:
            return yaml.safe_load(file)

    def _write_zpl_file(self, zpl, output_dir=None):
        """Save ZPL to disk only if enabled; otherwise log the ZPL for debugging.

        Returns: (timestamp, path_or_None, target_dir)
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        save_files = bool(self.config.get("printer", {}).get("save_zpl_files", False))
        target_dir = output_dir or self.temp_dir
        if save_files:
            filename = f"{timestamp}.zpl"
            os.makedirs(target_dir, exist_ok=True)
            path = os.path.join(target_dir, filename)
            with open(path, "w", encoding="utf-8") as file:
                file.write(zpl)
            logger.info("Saved ZPL package to: %s", path)
            return timestamp, path, target_dir

        # Default behaviour: don't write ZPL file, just log (debug) and return None path
        truncated = zpl if len(zpl) < 400 else zpl[:400] + "...[truncated]"
        logger.info("ZPL package created (not saved to disk). First 400 chars: %s", truncated)
        logger.debug("Full ZPL:\n%s", zpl)
        return timestamp, None, target_dir

    def _parse_label_size(self, label_size):
        try:
            width_in, height_in = [float(part) for part in str(label_size).lower().split("x", 1)]
            return width_in, height_in
        except Exception:
            return 3.0, 1.0

    def _render_preview(self, zpl, timestamp, output_dir=None):
        """Deprecated: rendering handled by external viewer/proxy in our new flow.

        Kept for backward compatibility but no longer invoked by default.
        """
        logger.debug("_render_preview called but rendering is disabled in core application.")
        return

    def _wait_for_viewer(self, url, max_wait_seconds=15):
        """Poll the viewer endpoint until it responds, with intelligent backoff."""
        deadline = time.time() + max_wait_seconds
        attempt = 0
        while time.time() < deadline:
            attempt += 1
            try:
                response = requests.head(url, timeout=2)
                if response.ok:
                    logger.info(f"Viewer endpoint ready after {attempt} attempt(s)")
                    return True
            except Exception:
                pass
            # Adaptive delay: 100ms, 200ms, 500ms, 1s, 1s, ...
            delay = min(0.1 * (2 ** (attempt - 1)), 1.0)
            time.sleep(delay)
        logger.debug(f"Viewer endpoint {url} still unavailable after {max_wait_seconds}s")
        return False

    def send_zpl(self, zpl, output_dir=None):
        timestamp, _, target_dir = self._write_zpl_file(zpl, output_dir=output_dir)
        # Rendering is handled externally; just send ZPL to the printer/proxy
        if self.simulate:
            print("[SIMULATION] ZPL Command:")
            print(zpl)
        else:
            self._send_with_retries(zpl, timestamp, target_dir)

    def print_label(self, zpl, output_dir=None):
        print("Sending label to printer...")
        self.send_zpl(zpl, output_dir=output_dir)
        print("Label sent successfully.")
        self.cleanup_old_runs(keep_count=3)
        self.cleanup_temp()

    def _send_with_retries(self, zpl, timestamp, output_dir=None):
        encoded = zpl.encode("utf-8")
        for attempt in range(1, self.retry_attempts + 1):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(self.network_timeout)
                    s.connect((self.printer_ip, self.port))
                    s.sendall(encoded)

                    # Signal EOF for our write side so servers waiting for client close can proceed
                    try:
                        s.shutdown(socket.SHUT_WR)
                    except Exception:
                        pass

                    # Attempt to read optional feedback from the printer/proxy
                    try:
                        s.settimeout(2)
                        data = b""
                        while True:
                            chunk = s.recv(4096)
                            if not chunk:
                                break
                            data += chunk
                    except socket.timeout:
                        # No feedback received within timeout
                        data = data

                logger.info("Printer send succeeded on attempt %d", attempt)

                # Process any feedback received
                if data:
                    try:
                        text = data.decode("utf-8", errors="replace").strip()
                        # Support newline-delimited JSON; take the first non-empty line
                        first_line = next((ln for ln in text.splitlines() if ln.strip()), None)
                        if first_line:
                            import json as _json
                            fb = _json.loads(first_line)
                            nsc = fb.get("nonSupportedCommands") or []
                            if nsc:
                                target_dir = output_dir or self.temp_dir
                                os.makedirs(target_dir, exist_ok=True)
                                issues_path = os.path.join(target_dir, f"{timestamp}.unsupported.txt")
                                with open(issues_path, "w", encoding="utf-8") as file:
                                    for cmd in nsc:
                                        file.write(f"{cmd}\n")
                                logger.info("Saved printer feedback issues to: %s", issues_path)
                    except Exception:
                        logger.debug("Failed to parse printer feedback: %s", data)

                return
            except (socket.timeout, OSError) as exc:
                logger.warning("Printer send attempt %d failed: %s", attempt, exc)
                if attempt < self.retry_attempts:
                    logger.info("Retrying printer send after %.1f seconds", self.retry_delay)
                    time.sleep(self.retry_delay)
        logger.error("Failed to send ZPL after %d attempts", self.retry_attempts)

    def cleanup_temp(self, days=7, keep_runs=10):
        self._cleanup_by_age(days)
        self._prune_old_runs(keep_runs)

    def _cleanup_by_age(self, days):
        cutoff = datetime.now() - timedelta(days=days)
        if not os.path.isdir(self.temp_dir):
            return
        for name in os.listdir(self.temp_dir):
            path = os.path.join(self.temp_dir, name)
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(path))
            except OSError:
                continue
            if mtime < cutoff:
                self._remove_path(path)

    def _prune_old_runs(self, keep_runs):
        if keep_runs <= 0 or not os.path.isdir(self.temp_dir):
            return
        entries = []
        for name in os.listdir(self.temp_dir):
            path = os.path.join(self.temp_dir, name)
            if not os.path.isdir(path):
                continue
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            entries.append((path, mtime))
        entries.sort(key=lambda item: item[1], reverse=True)
        for path, _ in entries[keep_runs:]:
            self._remove_path(path)

    def _remove_path(self, path):
        if os.path.isdir(path):
            for root, dirs, files in os.walk(path, topdown=False):
                for f in files:
                    try:
                        os.remove(os.path.join(root, f))
                    except OSError:
                        pass
                for d in dirs:
                    try:
                        os.rmdir(os.path.join(root, d))
                    except OSError:
                        pass
            try:
                os.rmdir(path)
            except OSError:
                pass
        else:
            try:
                os.remove(path)
            except OSError:
                pass

    def cleanup_old_runs(self, keep_count=3):
        """Remove old run directories, keeping only the most recent `keep_count` runs."""
        if not os.path.isdir(self.temp_dir):
            return
        
        run_dirs = []
        try:
            for entry in os.listdir(self.temp_dir):
                full_path = os.path.join(self.temp_dir, entry)
                if os.path.isdir(full_path) and len(entry) == 15:  # YYYYMMdd_HHMMSS format
                    run_dirs.append((entry, full_path))
        except OSError:
            return
        
        if len(run_dirs) <= keep_count:
            return
        
        run_dirs.sort(reverse=True)
        for _, path in run_dirs[keep_count:]:
            try:
                self._remove_path(path)
                logger.debug("Cleaned up old run: %s", path)
            except Exception as e:
                logger.warning("Failed to clean up %s: %s", path, e)