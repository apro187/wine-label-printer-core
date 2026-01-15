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
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{timestamp}.zpl"
        target_dir = output_dir or self.temp_dir
        os.makedirs(target_dir, exist_ok=True)
        path = os.path.join(target_dir, filename)
        with open(path, "w", encoding="utf-8") as file:
            file.write(zpl)
        print(f"Saved ZPL package to: {path}")
        return timestamp, path, target_dir

    def _parse_label_size(self, label_size):
        try:
            width_in, height_in = [float(part) for part in str(label_size).lower().split("x", 1)]
            return width_in, height_in
        except Exception:
            return 3.0, 1.0

    def _render_preview(self, zpl, timestamp, output_dir=None):
        if not self.viewer_config.get("enabled", True):
            return

        url = os.environ.get("VIEWER_URL") or self.viewer_config.get("url", "http://localhost:8088/api/v1/Viewer")
        label_size = self.config.get("printer", {}).get("label_size", "3x1")
        width_in, height_in = self._parse_label_size(label_size)
        dpi = int(self.config.get("printer", {}).get("dpi", 203))
        dpmm = self.viewer_config.get("print_density_dpmm")
        if not dpmm:
            dpmm = max(1, int(round(dpi / 25.4)))
        else:
            dpmm = int(dpmm)

        width_mm = width_in * 25.4
        height_mm = height_in * 25.4

        # Wait for viewer to be ready with intelligent polling
        max_wait = float(self.viewer_config.get("max_startup_wait_seconds", 15))
        viewer_ready = self._wait_for_viewer(url, max_wait)

        payload = {
            "zplData": zpl,
            "labelWidth": width_mm,
            "labelHeight": height_mm,
            "printDensityDpmm": dpmm,
        }
        viewer_type = str(self.viewer_config.get("type", "png")).lower()
        if viewer_type == "pdf":
            payload["type"] = "PDF"

        save_images = bool(self.viewer_config.get("save_images", False))

        try:
            response = requests.post(url, json=payload, timeout=15)
            response.raise_for_status()
            data = response.json()
            non_supported = data.get("nonSupportedCommands") or []
            if non_supported:
                target_dir = output_dir or self.temp_dir
                os.makedirs(target_dir, exist_ok=True)
                issues_path = os.path.join(target_dir, f"{timestamp}.unsupported.txt")
                with open(issues_path, "w", encoding="utf-8") as file:
                    for cmd in non_supported:
                        file.write(f"{cmd}\n")
                print(f"Viewer reported unsupported commands; saved to: {issues_path}")
            labels = data.get("labels") or []
            if not labels:
                print("Viewer returned no labels.")
                return
            if not save_images:
                print("Viewer preview images are disabled (viewer.save_images=false).")
                return
            saved_count = 0
            target_dir = output_dir or self.temp_dir
            os.makedirs(target_dir, exist_ok=True)
            for index, label in enumerate(labels, start=1):
                image_base64 = label.get("imageBase64")
                if not image_base64:
                    continue
                image_bytes = base64.b64decode(image_base64)
                suffix = f"_{index:02d}" if len(labels) > 1 else ""
                image_path = os.path.join(target_dir, f"{timestamp}{suffix}.png")
                with open(image_path, "wb") as file:
                    file.write(image_bytes)
                saved_count += 1
            if saved_count:
                print(f"Saved {saved_count} ZPL preview(s) for {len(labels)} label(s).")
            else:
                print("Viewer returned no image data.")
        except Exception as exc:
            print(f"Viewer preview failed: {exc}")

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
        self._render_preview(zpl, timestamp, output_dir=target_dir)
        if self.simulate:
            print("[SIMULATION] ZPL Command:")
            print(zpl)
        else:
            self._send_with_retries(zpl)

    def print_label(self, zpl, output_dir=None):
        print("Sending label to printer...")
        self.send_zpl(zpl, output_dir=output_dir)
        print("Label sent successfully.")
        self.cleanup_old_runs(keep_count=3)
        self.cleanup_temp()

    def _send_with_retries(self, zpl):
        encoded = zpl.encode("utf-8")
        for attempt in range(1, self.retry_attempts + 1):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(self.network_timeout)
                    s.connect((self.printer_ip, self.port))
                    s.sendall(encoded)
                logger.info("Printer send succeeded on attempt %d", attempt)
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