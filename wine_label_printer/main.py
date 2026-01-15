import os
import yaml
import logging
import argparse
from datetime import datetime
try:
    from wine_label_printer.label_generator import LabelGenerator
    from wine_label_printer.printer import Printer
except ImportError:
    # Fallback for running as script
    from label_generator import LabelGenerator
    from printer import Printer
import requests
import pandas as pd
from io import StringIO

def load_secrets(secrets_path=None):
    if secrets_path is None:
        secrets_path = os.path.join(os.path.dirname(__file__), "secrets.yaml")
    with open(secrets_path, "r") as file:
        return yaml.safe_load(file)


def ensure_parent_dir(path):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)


def load_config(config_path=None):
    if config_path is None:
        config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "config.yaml"))
    with open(config_path, "r") as file:
        return yaml.safe_load(file) or {}


def setup_logging(config):
    storage = config.get("storage", {})
    log_path = storage.get("log_path", "logs/wine_label_printer.log")
    handlers = [logging.StreamHandler()]
    absolute_log_path = None
    if log_path:
        absolute_log_path = os.path.abspath(log_path)
        ensure_parent_dir(absolute_log_path)
        handlers.append(logging.FileHandler(absolute_log_path, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=handlers,
    )
    if absolute_log_path:
        logging.info("Logging to %s", absolute_log_path)

def fetch_inventory_from_cellartracker(username, password):
    url = "https://www.cellartracker.com/xlquery.asp"
    params = {
        "User": username,
        "Password": password,
        "Table": "Inventory",
        "Format": "csv",
        "Location": "1"
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    df = pd.read_csv(StringIO(response.text))
    return df

def load_printed_ids(path):
    if not os.path.exists(path):
        return set()
    with open(path, "r") as file:
        return {line.strip() for line in file if line.strip()}

def save_printed_ids(path, printed_ids):
    ensure_parent_dir(path)
    with open(path, "w") as file:
        for item in sorted(printed_ids):
            file.write(f"{item}\n")


class WineLabelPrinter:
    """Main class for printing wine labels from CellarTracker inventory."""
    
    def __init__(self, config_path=None, config_overrides=None):
        """Initialize the wine label printer.
        
        Args:
            config_path: Path to config.yaml file
            config_overrides: Dictionary of config values to override from file
        """
        if config_path is None:
            config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "config.yaml"))
        self.config_path = config_path
        self.label_generator = LabelGenerator(config_path)
        self.config = self.label_generator.config
        
        # Apply any config overrides
        if config_overrides:
            self.config.update(config_overrides)
            logging.info("Applied config overrides")
        
        logging.info("Initialized WineLabelPrinter with config: %s", config_path)
    
    def run(self, test_mode=False):
        """
        Run the label printing process.
        
        Args:
            test_mode: If True, don't update the printed IDs file
        
        Returns:
            int: Number of labels printed, or None if no new wines
        """
        try:
            # Load config
            config = self.config
            logging.info("Using config path: %s", self.config_path)
            
            # Load secrets for CellarTracker
            secrets = load_secrets()
            logging.info("Loaded secrets for user: %s", secrets.get("username"))
            
            # Fetch inventory from CellarTracker
            inventory_df = fetch_inventory_from_cellartracker(
                secrets['username'],
                secrets['password']
            )
            logging.info("Fetched %d inventory rows", len(inventory_df))
            
            # Create printer instance
            printer = Printer(self.config_path, simulate=False)
            
            # Get paths from config
            storage = config.get("storage", {})
            output_dir = storage.get("output_dir", "tmp")
            printed_ids_path = storage.get("printed_ids_path", os.path.join("storage", "printed_ids.txt"))
            cellartracker_csv_path = storage.get(
                "cellartracker_csv_path",
                os.path.join("storage", "cellartracker_inventory.csv")
            )
            
            # Prepare directories
            os.makedirs(output_dir, exist_ok=True)
            if cellartracker_csv_path:
                ensure_parent_dir(cellartracker_csv_path)
                inventory_df.to_csv(cellartracker_csv_path, index=False)
                logging.info("Saved inventory CSV to %s", cellartracker_csv_path)
            
            # Load previously printed IDs
            printed_ids = load_printed_ids(printed_ids_path)
            logging.info("Loaded %d printed IDs", len(printed_ids))
            
            # Get configuration options
            batch_size = int(config.get("batch_size", 25))
            print_new_only = bool(config.get("print_new_only", True))
            test_mode = bool(config.get("test_mode", False))
            copies_per_label = int(config.get("copies_per_label", 1))
            
            # Process inventory
            labels_printed = 0
            printed_this_run = []
            zpl_batches = []
            run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            run_dir = os.path.join(output_dir, run_id)
            
            for _, row in inventory_df.iterrows():
                if labels_printed >= batch_size:
                    break
                
                barcode = str(row.get("Barcode", "")).strip()
                if not barcode:
                    continue
                
                already_printed = barcode in printed_ids
                if print_new_only and already_printed and not test_mode:
                    continue
                
                wine_data = row.to_dict()
                try:
                    label = self.label_generator.generate_label(wine_data)
                    if config.get("preview", {}).get("pillow_enabled", False):
                        label.show()
                    
                    zpl = self.label_generator.generate_zpl(wine_data, copies=copies_per_label)
                    zpl_batches.append(zpl)
                    printed_this_run.append(barcode)
                    labels_printed += 1
                except Exception as exc:
                    logging.exception("Failed to generate/print label for barcode %s: %s", barcode, exc)
            
            # Print labels if any were generated
            if zpl_batches:
                combined_zpl = "".join(zpl_batches)
                printer.print_label(combined_zpl, output_dir=run_dir)
                logging.info("Printed %d labels", labels_printed)
            else:
                logging.info("No new wines to print.")
                return 0
            
            # Update printed IDs
            if not test_mode:
                printed_ids.update(printed_this_run)
                save_printed_ids(printed_ids_path, printed_ids)
                logging.info("Saved printed IDs to %s", printed_ids_path)
            
            return labels_printed
            
        except Exception as e:
            logging.error("Error running label printer: %s", e, exc_info=True)
            raise


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Wine Label Printer - Generate and print wine labels from CellarTracker"
    )
    parser.add_argument(
        "-c", "--config",
        default=None,
        help="Path to config.yaml file (default: config.yaml in script directory)"
    )
    parser.add_argument(
        "-p", "--printer-ip",
        default=None,
        help="Override printer IP address from config"
    )
    parser.add_argument(
        "-b", "--batch-size",
        type=int,
        default=None,
        help="Override batch size for printing"
    )
    parser.add_argument(
        "-s", "--simulate",
        action="store_true",
        help="Run in simulation mode (don't actually print)"
    )
    parser.add_argument(
        "-t", "--test-mode",
        action="store_true",
        help="Test mode - don't update printed IDs file"
    )
    parser.add_argument(
        "--viewer-url",
        default=None,
        help="Override ZPL viewer URL for previews"
    )
    parser.add_argument(
        "--username",
        default=None,
        help="Override CellarTracker username"
    )
    parser.add_argument(
        "--password",
        default=None,
        help="Override CellarTracker password"
    )
    return parser.parse_args()


def main():
    """Main entry point for standalone use."""
    args = parse_args()
    
    # Determine config path
    if args.config:
        config_path = os.path.abspath(args.config)
    else:
        config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "config.yaml"))
    
    # Load base config
    base_config = load_config(config_path)
    setup_logging(base_config)
    
    # Apply command-line overrides
    if args.printer_ip:
        base_config["printer"]["ip"] = args.printer_ip
        logging.info("Overriding printer IP to: %s", args.printer_ip)
    
    if args.batch_size:
        base_config["printer"]["batch_size"] = args.batch_size
        logging.info("Overriding batch size to: %d", args.batch_size)
    
    if args.simulate:
        base_config["printer"]["simulate"] = True
        logging.info("Running in simulation mode")
    
    if args.viewer_url:
        base_config["viewer"]["url"] = args.viewer_url
        logging.info("Overriding viewer URL to: %s", args.viewer_url)
    
    if args.username:
        base_config["cellartracker"]["username"] = args.username
        logging.info("Overriding CellarTracker username")
    
    if args.password:
        base_config["cellartracker"]["password"] = args.password
        logging.info("Overriding CellarTracker password")
    
    # Use the new WineLabelPrinter class with modified config
    printer = WineLabelPrinter(config_path, config_overrides=base_config)
    result = printer.run(test_mode=args.test_mode)
    
    logging.info("Completed. Printed %d labels.", result)
    return result

if __name__ == "__main__":
    main()