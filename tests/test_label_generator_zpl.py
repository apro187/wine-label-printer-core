import pandas as pd
from wine_label_printer.label_generator import LabelGenerator


def test_generate_zpl_contains_qr_and_fields():
    lg = LabelGenerator()
    wine_data = {
        "Barcode": "TEST123",
        "Wine": "My Test Wine",
        "Vintage": "2018",
        "StoreName": "My Cellar",
        "Price": "25",
    }
    zpl = lg.generate_zpl(wine_data, copies=1)
    assert zpl.startswith("^XA")
    assert zpl.endswith("^XZ")
    # QR command
    assert "^BQN" in zpl
    # Barcode encoded somewhere
    assert "TEST123" in zpl
    # Text fields (Style/Region/Value) should be present as ^FD segments
    assert "Style:" in zpl or "Value:" in zpl
