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

storage:
  printed_ids_path: "storage/printed_ids.txt"
  cellartracker_csv_path: "storage/cellartracker_inventory.csv"
```

## Implementations

This core package is used by:

- **[wine-label-printer-appdaemon](https://github.com/apro187/wine-label-printer-appdaemon)** - Home Assistant AppDaemon app
- **[wine-label-printer-docker](https://github.com/apro187/wine-label-printer-docker)** - Standalone Docker container
- **[wine-label-printer-ha-addon](https://github.com/apro187/wine-label-printer-ha-addon)** - Home Assistant add-on

## License

MIT License - see LICENSE file for details
