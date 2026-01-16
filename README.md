# Wine Label Printer - Core Package

Core Python package for printing wine labels from CellarTracker to Zebra printers.

## Features

- Fetch wine inventory from CellarTracker API
- Generate ZPL (Zebra Programming Language) labels
- Print to Zebra printers via network or USB
- Track printed wine IDs to avoid duplicates
- Configurable label templates

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Command Line

```bash
# Basic usage (uses config.yaml in script directory)
python -m wine_label_printer.main

# With custom config file
python -m wine_label_printer.main --config /path/to/config.yaml

# Override printer IP
python -m wine_label_printer.main --printer-ip 192.168.1.200

# Run in simulation mode (don't actually print)
python -m wine_label_printer.main --simulate

# Test mode (don't update printed IDs file)
python -m wine_label_printer.main --test-mode

# Override batch size
python -m wine_label_printer.main --batch-size 10

# Override viewer URL
python -m wine_label_printer.main --viewer-url http://localhost:5001

# Override CellarTracker credentials
python -m wine_label_printer.main --username myuser --password mypass

# Combine multiple options
python -m wine_label_printer.main --printer-ip 192.168.1.200 --batch-size 5 --simulate
```

### Available Flags

- `-c, --config` - Path to config.yaml file
- `-p, --printer-ip` - Override printer IP address
- `-b, --batch-size` - Override batch size for printing
- `-s, --simulate` - Run in simulation mode (don't print)
- `-t, --test-mode` - Don't update printed IDs file
- `--viewer-url` - Override ZPL viewer URL
- `--username` - Override CellarTracker username
- `--password` - Override CellarTracker password

### Python API

```python
from wine_label_printer import WineLabelPrinter

printer = WineLabelPrinter(config_path="config.yaml")
printer.run()
```

## Configuration

Create a `secrets.yaml` file with your CellarTracker credentials:

```yaml
username: your_username
password: your_password
```

Create a `config.yaml` file with printer settings:

```yaml
printer:
  ip: "192.168.1.100"
  port: 9100
  darkness: 15
  # By default we don't save raw ZPL packages to disk. Set to true to retain .zpl files for debugging
  save_zpl_files: false

storage:
  printed_ids_path: "storage/printed_ids.txt"
  cellartracker_csv_path: "storage/cellartracker_inventory.csv"
```

## Testing with local viewer (BinaryKits)

For local testing you can use the BinaryKits viewer + TCP proxy we've prepared in the `utilities/binarykits.zpl` repository (or in this workspace under `../binarykits.zpl`). That stack exposes a virtual printer port (TCP 9100) which forwards ZPL to the viewer and returns JSON feedback.

Quick steps:

1. Start the BinaryKits compose stack (from `utilities/binarykits.zpl`):

```bash
cd ../binarykits.zpl
docker compose -f docker-compose.yml up -d --build
```

2. Run the core integration test (it will send a sample ZPL to `127.0.0.1:9100` and verify feedback):

```bash
pytest -q tests/test_integration_with_viewer.py -q
```

Notes:

- The core application no longer renders or saves preview images locally by default — rendering is handled by the external viewer/proxy.
- The core will attempt to read JSON feedback from the printer/proxy connection; if the feedback includes a `nonSupportedCommands` list, a file named `<timestamp>.unsupported.txt` will be written to the output directory you pass to the run (or `tmp/<run_id>/` when running normally).
- Raw ZPL packages are not saved to disk by default; enable `printer.save_zpl_files: true` in `config.yaml` if you want `.zpl` files retained for debugging.
- This core package is intentionally not dockerized here; if we decide to provide a docker image later it will be implemented as a fork/variant.

## Implementations

This core package is used by:

- **[wine-label-printer-appdaemon](https://github.com/apro187/wine-label-printer-appdaemon)** - Home Assistant AppDaemon app
- **[wine-label-printer-docker](https://github.com/apro187/wine-label-printer-docker)** - Standalone Docker container
- **[wine-label-printer-ha-addon](https://github.com/apro187/wine-label-printer-ha-addon)** - Home Assistant add-on

## License

MIT License - see LICENSE file for details
