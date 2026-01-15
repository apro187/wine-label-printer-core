from PIL import Image, ImageDraw, ImageFont
import yaml
import os
import qrcode
from qrcode.image.pil import PilImage
import math
import datetime

class LabelGenerator:
    def __init__(self, config_path=None):
        if config_path is None:
            config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "config.yaml"))
        self.config = self.load_config(config_path)

    def _round_value_for_label(self, value):
        if not value:
            return value
        normalized = str(value).strip()
        if not normalized or normalized.lower() in ("n/a", "nan"):
            return value
        cleaned = normalized.replace("$", "").replace(",", "")
        try:
            numeric = float(cleaned)
        except ValueError:
            return value
        if math.isnan(numeric):
            return value
        rounded = math.ceil(numeric)
        return str(int(rounded))

    def load_config(self, path):
        if not os.path.exists(path):
            raise FileNotFoundError(f"Config file not found at: {path}")
        with open(path, "r") as file:
            return yaml.safe_load(file)

    def generate_label(self, wine_data):
        # Load label size and layout parameters from config
        canvas_width = self.config["printer"].get("canvas_width")
        canvas_height = self.config["printer"].get("canvas_height")
        dpi = int(self.config["printer"].get("dpi", 203))
        base_width = int(self.config["printer"].get("base_canvas_width", 500))
        base_height = int(self.config["printer"].get("base_canvas_height", 128))
        use_scaled_layout = False
        if not canvas_width or not canvas_height:
            label_size = str(self.config["printer"].get("label_size", "3x1")).lower()
            try:
                width_in, height_in = [float(part) for part in label_size.split("x", 1)]
            except Exception:
                width_in, height_in = 3.0, 1.0
            canvas_width = int(round(width_in * dpi))
            canvas_height = int(round(height_in * dpi))
            use_scaled_layout = True
        qr_size = int(self.config["printer"].get("qr_size", 100))
        qr_x = int(self.config["printer"].get("qr_x", 10))
        qr_y = int(self.config["printer"].get("qr_y", 5))
        text_x = int(self.config["printer"].get("text_x", 140))
        text_y = int(self.config["printer"].get("text_y", 10))
        font_size = int(self.config["printer"].get("font_size", 12))
        line_spacing = float(self.config["printer"].get("line_spacing", 1.0))
        right_margin = int(self.config["printer"].get("right_margin", 30))
        left_margin = int(self.config["printer"].get("left_margin", 10))

        if use_scaled_layout and base_width and base_height:
            scale_x = canvas_width / base_width
            scale_y = canvas_height / base_height
            scale = min(scale_x, scale_y)
            qr_size = max(1, int(round(qr_size * scale)))
            qr_x = int(round(qr_x * scale_x))
            qr_y = int(round(qr_y * scale_y))
            text_x = int(round(text_x * scale_x))
            text_y = int(round(text_y * scale_y))
            font_size = max(8, int(round(font_size * scale_y)))
            line_spacing = line_spacing * scale_y
            right_margin = int(round(right_margin * scale_x))
            left_margin = int(round(left_margin * scale_x))

        # Create a blank label
        img = Image.new("RGB", (canvas_width, canvas_height), color="white")
        draw = ImageDraw.Draw(img)

        # Generate QR code with CellarTracker URL using iWine field
        iwine = wine_data.get("iWine", "")
        qr_url = iwine if not iwine else f"https://www.cellartracker.com/wine.asp?iWine={iwine}"
        
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(qr_url)
        qr.make(fit=True)
        qr_img = qr.make_image(image_factory=PilImage, fill_color="black", back_color="white")
        qr_img = qr_img.resize((qr_size, qr_size), Image.Resampling.NEAREST)

        # Center QR vertically within the canvas
        qr_y = int(round((canvas_height - qr_size) / 2))

        # Paste QR code onto the label
        img.paste(qr_img, (qr_x, qr_y))

        def is_empty(value):
            if value is None:
                return True
            if isinstance(value, float):
                try:
                    return math.isnan(value)
                except Exception:
                    return False
            return str(value).strip().lower() in ("", "n/a", "nan")

        def safe_str(value):
            return "" if is_empty(value) else str(value)

        def parse_year(value):
            if is_empty(value):
                return None
            s = str(value).strip()
            for token in s.split():
                if token.isdigit() and len(token) == 4:
                    return int(token)
            try:
                return int(float(value))
            except Exception:
                return None

        def load_font(size):
            local_fonts = [
                os.path.join(os.path.dirname(__file__), "fonts", "DejaVuSerif.ttf"),
                os.path.join(os.path.dirname(__file__), "fonts", "DejaVuSerifCondensed.ttf"),
            ]
            system_fonts = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSerifCondensed.ttf",
                "/System/Library/Fonts/Helvetica.ttc",
                "/System/Library/Fonts/Verdana.ttf",
                "/System/Library/Fonts/Arial.ttf",
            ]
            for path in local_fonts + system_fonts:
                try:
                    return ImageFont.truetype(path, size)
                except Exception:
                    continue
            return ImageFont.load_default()

        def truncate_to_width(value, font, max_width):
            if not value:
                return value
            if font.getbbox(value)[2] <= max_width:
                return value
            ellipsis = "..."
            max_body = max(0, max_width - font.getbbox(ellipsis)[2])
            left = 0
            right = len(value)
            best = ""
            while left <= right:
                mid = (left + right) // 2
                candidate = value[:mid]
                if font.getbbox(candidate)[2] <= max_body:
                    best = candidate
                    left = mid + 1
                else:
                    right = mid - 1
            return (best + ellipsis) if best else ellipsis

        wine = safe_str(wine_data.get("Wine", "Unknown Wine"))
        vintage = safe_str(wine_data.get("Vintage", ""))

        rating_cols = ["CT", "WS", "WA", "IWC", "BH", "WE", "JR", "WFW", "PR", "JH"]
        ratings = []
        for col in rating_cols:
            val = wine_data.get(col, "")
            if not is_empty(val):
                try:
                    num_val = float(val)
                    if not math.isnan(num_val):
                        ratings.append(f"{col}:{round(num_val, 1)}")
                except (ValueError, TypeError):
                    pass
        rating_line = " ".join(ratings) if ratings else ""

        purchase_date = safe_str(wine_data.get("PurchaseDate", "N/A"))
        if purchase_date and purchase_date != "N/A":
            parts = purchase_date.split("/")
            if len(parts) == 3:
                purchase_date = f"{parts[0]}/{parts[1]}/{parts[2][-2:]}"

        begin_consume = safe_str(wine_data.get("BeginConsume", ""))
        end_consume = safe_str(wine_data.get("EndConsume", ""))
        drink_window = ""
        is_past_window = False
        if begin_consume and end_consume:
            begin_year = parse_year(begin_consume)
            end_year = parse_year(end_consume)
            if begin_year and end_year:
                drink_window = f"{str(begin_year)[-2:]}-'{str(end_year)[-2:]}"
                is_past_window = end_year < datetime.date.today().year
            else:
                drink_window = f"{begin_consume}-{end_consume}"

        value = safe_str(wine_data.get("Valuation", ""))
        if not value:
            value = safe_str(wine_data.get("Price", "N/A"))
        value = self._round_value_for_label(value)
        location = safe_str(wine_data.get("StoreName", "N/A"))
        wine_type = safe_str(wine_data.get("Type", ""))
        category = safe_str(wine_data.get("Category", ""))
        varietal = safe_str(wine_data.get("Varietal", ""))
        style = f"{category} {wine_type}".strip()
        if varietal:
            style += f" / {varietal}"

        region = safe_str(wine_data.get("Locale", ""))
        region_line1 = ""
        region_line2 = ""
        if region:
            parts = region.split(", ")
            if len(parts) >= 2:
                region_line1 = ", ".join(parts[:2])
                if len(parts) > 2:
                    region_line2 = ", ".join(parts[2:])

        text_lines = [wine]
        if rating_line:
            text_lines.append(rating_line)
        text_lines.extend([
            f"Style: {style}" if style else "Style:",
            f"Region: {region_line1}" if region_line1 else "Region:",
        ])
        if region_line2:
            text_lines.append(f"Appellation: {region_line2}")
        text_lines.extend([
            f"Purchased: {purchase_date}" if purchase_date else "Purchased:",
            f"Value: ${value}" if value and str(value).lower() not in ("n/a", "nan", "") else "Value:",
            f"From: {location}" if location else "From:",
        ])

        bar_width = max(6, int(round(right_margin * 0.5))) if is_past_window else 0
        max_width = max(10, canvas_width - text_x - right_margin - bar_width)
        normal_font = load_font(font_size)

        name_font_size = font_size
        name_font = normal_font
        name_text = text_lines[0]
        while name_font.getbbox(name_text)[2] > max_width and name_font_size > 8:
            name_font_size -= 1
            name_font = load_font(name_font_size)

        step = font_size + max(0.0, line_spacing)
        content_height = step * len(text_lines)
        y = max(text_y, int((canvas_height - content_height) / 2))

        # Position vintage above QR and drink window below QR, centered within available space
        top_space = max(0, qr_y)
        bottom_space = max(0, canvas_height - (qr_y + qr_size))
        label_font = load_font(max(8, int(round(font_size * 0.9))))

        if vintage:
            vintage_text = truncate_to_width(str(vintage), label_font, qr_size)
            vintage_w = label_font.getbbox(vintage_text)[2]
            vintage_x = qr_x + max(0, int((qr_size - vintage_w) / 2))
            vintage_y = max(0, int((top_space - label_font.getbbox(vintage_text)[3]) / 2))
            draw.text((vintage_x, vintage_y), vintage_text, fill=0, font=label_font)

        if drink_window:
            drink_text = truncate_to_width(drink_window, label_font, qr_size)
            drink_w = label_font.getbbox(drink_text)[2]
            drink_x = qr_x + max(0, int((qr_size - drink_w) / 2))
            drink_y = qr_y + qr_size + max(0, int((bottom_space - label_font.getbbox(drink_text)[3]) / 2))
            draw.text((drink_x, drink_y), drink_text, fill=0, font=label_font)
        if is_past_window and bar_width > 0:
            bar_x0 = max(0, canvas_width - bar_width)
            draw.rectangle([(bar_x0, 0), (canvas_width, canvas_height)], fill=(128, 128, 128))
        for i, line in enumerate(text_lines):
            font_to_use = name_font if i == 0 else normal_font
            safe_line = truncate_to_width(line, font_to_use, max_width)
            draw.text((text_x, y), safe_line, fill=0, font=font_to_use)
            y += step

        return img

    def generate_zpl(self, wine_data, copies=1):
        canvas_width = self.config["printer"].get("canvas_width")
        canvas_height = self.config["printer"].get("canvas_height")
        dpi = int(self.config["printer"].get("dpi", 203))
        base_width = int(self.config["printer"].get("base_canvas_width", 500))
        base_height = int(self.config["printer"].get("base_canvas_height", 128))
        use_scaled_layout = False
        if not canvas_width or not canvas_height:
            label_size = str(self.config["printer"].get("label_size", "3x1")).lower()
            try:
                width_in, height_in = [float(part) for part in label_size.split("x", 1)]
            except Exception:
                width_in, height_in = 3.0, 1.0
            canvas_width = int(round(width_in * dpi))
            canvas_height = int(round(height_in * dpi))
            use_scaled_layout = True

        qr_size = int(self.config["printer"].get("qr_size", 100))
        qr_x = int(self.config["printer"].get("qr_x", 10))
        qr_y = int(self.config["printer"].get("qr_y", 5))
        text_x = int(self.config["printer"].get("text_x", 140))
        text_y = int(self.config["printer"].get("text_y", 10))
        font_size = int(self.config["printer"].get("font_size", 12))
        line_spacing = float(self.config["printer"].get("line_spacing", 1.0))
        right_margin = int(self.config["printer"].get("right_margin", 30))

        if use_scaled_layout and base_width and base_height:
            scale_x = canvas_width / base_width
            scale_y = canvas_height / base_height
            scale = min(scale_x, scale_y)
            qr_size = max(1, int(round(qr_size * scale)))
            qr_x = int(round(qr_x * scale_x))
            qr_y = int(round(qr_y * scale_y))
            text_x = int(round(text_x * scale_x))
            text_y = int(round(text_y * scale_y))
            font_size = max(8, int(round(font_size * scale_y)))
            line_spacing = line_spacing * scale_y
            right_margin = int(round(right_margin * scale_x))

        def is_empty(value):
            if value is None:
                return True
            if isinstance(value, float):
                try:
                    return math.isnan(value)
                except Exception:
                    return False
            return str(value).strip().lower() in ("", "n/a", "nan")

        def safe_str(value):
            return "" if is_empty(value) else str(value)

        def parse_year(value):
            if is_empty(value):
                return None
            s = str(value).strip()
            for token in s.split():
                if token.isdigit() and len(token) == 4:
                    return int(token)
            try:
                return int(float(value))
            except Exception:
                return None

        wine = safe_str(wine_data.get("Wine", "Unknown Wine"))
        vintage = safe_str(wine_data.get("Vintage", ""))

        rating_cols = ["CT", "WS", "WA", "IWC", "BH", "WE", "JR", "WFW", "PR", "JH"]
        ratings = []
        for col in rating_cols:
            val = wine_data.get(col, "")
            if not is_empty(val):
                try:
                    num_val = float(val)
                    if not math.isnan(num_val):
                        ratings.append(f"{col}:{round(num_val, 1)}")
                except (ValueError, TypeError):
                    pass
        rating_line = " ".join(ratings) if ratings else ""

        purchase_date = safe_str(wine_data.get("PurchaseDate", "N/A"))
        if purchase_date and purchase_date != "N/A":
            parts = purchase_date.split("/")
            if len(parts) == 3:
                purchase_date = f"{parts[0]}/{parts[1]}/{parts[2][-2:]}"

        begin_consume = safe_str(wine_data.get("BeginConsume", ""))
        end_consume = safe_str(wine_data.get("EndConsume", ""))
        drink_window = ""
        is_past_window = False
        if begin_consume and end_consume:
            begin_year = parse_year(begin_consume)
            end_year = parse_year(end_consume)
            if begin_year and end_year:
                drink_window = f"{str(begin_year)[-2:]}-'{str(end_year)[-2:]}"
                is_past_window = end_year < datetime.date.today().year
            else:
                drink_window = f"{begin_consume}-{end_consume}"

        value = safe_str(wine_data.get("Valuation", ""))
        if not value:
            value = safe_str(wine_data.get("Price", "N/A"))
        value = self._round_value_for_label(value)
        location = safe_str(wine_data.get("StoreName", "N/A"))
        wine_type = safe_str(wine_data.get("Type", ""))
        category = safe_str(wine_data.get("Category", ""))
        varietal = safe_str(wine_data.get("Varietal", ""))
        style = f"{category} {wine_type}".strip()
        if varietal:
            style += f" / {varietal}"

        region = safe_str(wine_data.get("Locale", ""))
        region_line1 = ""
        region_line2 = ""
        if region:
            parts = region.split(", ")
            if len(parts) >= 2:
                region_line1 = ", ".join(parts[:2])
                if len(parts) > 2:
                    region_line2 = ", ".join(parts[2:])

        text_lines = [wine]
        if rating_line:
            text_lines.append(rating_line)
        text_lines.extend([
            f"Style: {style}" if style else "Style:",
            f"Region: {region_line1}" if region_line1 else "Region:",
        ])
        if region_line2:
            text_lines.append(f"Appellation: {region_line2}")
        text_lines.extend([
            f"Purchased: {purchase_date}" if purchase_date else "Purchased:",
            f"Value: ${value}" if value and str(value).lower() not in ("n/a", "nan", "") else "Value:",
            f"From: {location}" if location else "From:",
        ])

        qr_y = int(round((canvas_height - qr_size) / 2))
        bar_width = max(6, int(round(right_margin * 0.5))) if is_past_window else 0
        max_width = max(10, canvas_width - text_x - right_margin - bar_width)
        line_step = int(round(font_size + max(0.0, line_spacing)))

        def zpl_escape(value):
            return str(value).replace("^", " ")

        qr_scale = max(2, min(10, int(round(qr_size / 25))))
        iwine = safe_str(wine_data.get("iWine", ""))
        
        # Generate CellarTracker URL for QR code if we have an iWine ID
        qr_data = iwine
        if iwine:
            qr_data = f"https://www.cellartracker.com/wine.asp?iWine={iwine}"

        zpl_lines = [
            "^XA",
            f"^PW{int(canvas_width)}",
            f"^LL{int(canvas_height)}",
            f"^FO{qr_x},{qr_y}^BQN,2,{qr_scale}^FDQA,{zpl_escape(qr_data)}^FS",
        ]

        y = max(text_y, int((canvas_height - (line_step * len(text_lines))) / 2))
        for index, line in enumerate(text_lines):
            line_text = zpl_escape(line)
            max_lines = 2 if index == 0 else 1
            zpl_lines.append(
                f"^FO{text_x},{y}^A0N,{font_size},{font_size}^FB{max_width},{max_lines},0,L^FD{line_text}^FS"
            )
            y += line_step * max_lines

        label_font = max(8, int(round(font_size * 0.9)))
        top_space = max(0, qr_y)
        bottom_space = max(0, canvas_height - (qr_y + qr_size))
        if vintage:
            vintage_y = max(0, int((top_space - label_font) / 2))
            zpl_lines.append(
                f"^FO{qr_x},{vintage_y}^A0N,{label_font},{label_font}^FB{qr_size},1,0,C^FD{zpl_escape(vintage)}\\&^FS"
            )
        if drink_window:
            drink_y = qr_y + qr_size + max(0, int((bottom_space - label_font) / 2))
            zpl_lines.append(
                f"^FO{qr_x},{drink_y}^A0N,{label_font},{label_font}^FB{qr_size},1,0,C^FD{zpl_escape(drink_window)}\\&^FS"
            )

        if is_past_window and bar_width > 0:
            bar_x = max(0, int(canvas_width - bar_width))
            bar_height = int(canvas_height)
            step = 2
            for offset in range(0, bar_width, step):
                x = bar_x + offset
                zpl_lines.append(
                    f"^FO{x},0^GB1,{bar_height},1,B,0^FS"
                )

        copies = max(1, int(copies))
        if copies > 1:
            zpl_lines.append(f"^PQ{copies}")
        zpl_lines.append("^XZ")
        return "".join(zpl_lines)