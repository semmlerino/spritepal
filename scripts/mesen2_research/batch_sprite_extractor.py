#!/usr/bin/env python3
"""
Batch Sprite Extractor for Multiple SNES Addresses
==================================================
Process multiple sprite addresses found through Mesen 2 debugging.
Useful for extracting entire sprite sets or documenting sprite locations.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Import the main extractor
sys.path.insert(0, str(Path(__file__).parent.parent))
from mesen2_sprite_extractor import SpriteExtractor


class BatchExtractor:
    def __init__(self):
        self.extractor = SpriteExtractor()
        self.results = []

    def process_address_list(self, addresses: list[dict[str, Any]]) -> None:
        """
        Process a list of sprite addresses.
        Each entry should have: {name, address, [notes]}
        """
        print(f"Processing {len(addresses)} sprite addresses...")
        print("=" * 60)

        for idx, entry in enumerate(addresses, 1):
            name = entry.get("name", f"sprite_{idx}")
            addr = entry["address"]
            notes = entry.get("notes", "")

            print(f"\n[{idx}/{len(addresses)}] {name}")
            print(f"  Address: {addr}")
            if notes:
                print(f"  Notes: {notes}")

            # Parse address and convert
            try:
                bank, offset = self.extractor.parse_snes_address(addr)
                rom_offset = self.extractor.snes_to_rom_offset(bank, offset)

                # Extract data
                output_name = name.replace(" ", "_").lower()
                bin_path = self.extractor.extract_compressed_data(rom_offset, output_name)

                if bin_path:
                    png_path = self.extractor.convert_to_png(bin_path)

                    result = {
                        "name": name,
                        "snes_address": f"${bank:02X}:{offset:04X}",
                        "rom_offset": f"0x{rom_offset:06X}",
                        "size": bin_path.stat().st_size,
                        "tiles": bin_path.stat().st_size // 32,
                        "files": {"bin": str(bin_path), "png": str(png_path) if png_path else None},
                        "status": "success",
                        "notes": notes,
                    }
                else:
                    result = {
                        "name": name,
                        "snes_address": f"${bank:02X}:{offset:04X}",
                        "rom_offset": f"0x{rom_offset:06X}",
                        "status": "failed",
                        "notes": notes,
                    }

                self.results.append(result)

            except Exception as e:
                print(f"  ERROR: {e}")
                self.results.append(
                    {"name": name, "snes_address": addr, "status": "error", "error": str(e), "notes": notes}
                )

    def save_report(self, filename: str | None = None) -> Path:
        """Save extraction report as JSON and HTML."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"sprite_extraction_report_{timestamp}"

        report_dir = Path("extracted_sprites/reports")
        report_dir.mkdir(parents=True, exist_ok=True)

        # Save JSON
        json_path = report_dir / f"{filename}.json"
        with open(json_path, "w") as f:
            json.dump(self.results, f, indent=2)

        # Save HTML report
        html_path = report_dir / f"{filename}.html"
        self.generate_html_report(html_path)

        print("\n✓ Reports saved:")
        print(f"  JSON: {json_path}")
        print(f"  HTML: {html_path}")

        return html_path

    def generate_html_report(self, output_path: Path) -> None:
        """Generate an HTML report with sprite previews."""
        html = """<!DOCTYPE html>
<html>
<head>
    <title>Sprite Extraction Report</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }
        h1 {
            color: #333;
            border-bottom: 3px solid #4CAF50;
            padding-bottom: 10px;
        }
        .summary {
            background: white;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .sprite-card {
            background: white;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 15px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .sprite-card.success {
            border-left: 4px solid #4CAF50;
        }
        .sprite-card.failed {
            border-left: 4px solid #f44336;
        }
        .sprite-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        .sprite-name {
            font-size: 1.2em;
            font-weight: bold;
            color: #333;
        }
        .sprite-status {
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.9em;
            font-weight: bold;
        }
        .status-success {
            background: #4CAF50;
            color: white;
        }
        .status-failed {
            background: #f44336;
            color: white;
        }
        .sprite-details {
            display: grid;
            grid-template-columns: auto 1fr;
            gap: 8px;
            margin-bottom: 10px;
        }
        .detail-label {
            font-weight: bold;
            color: #666;
        }
        .detail-value {
            font-family: 'Consolas', 'Courier New', monospace;
        }
        .sprite-preview {
            margin-top: 10px;
            padding: 10px;
            background: #f9f9f9;
            border-radius: 4px;
            text-align: center;
        }
        .sprite-preview img {
            max-width: 100%;
            image-rendering: pixelated;
            border: 1px solid #ddd;
        }
        .notes {
            margin-top: 10px;
            padding: 8px;
            background: #fff3cd;
            border-radius: 4px;
            font-style: italic;
        }
        .stats {
            display: flex;
            gap: 20px;
            flex-wrap: wrap;
        }
        .stat {
            flex: 1;
            min-width: 150px;
        }
        .stat-value {
            font-size: 2em;
            font-weight: bold;
            color: #4CAF50;
        }
        .stat-label {
            color: #666;
            font-size: 0.9em;
        }
    </style>
</head>
<body>
    <h1>🎮 Kirby Super Star - Sprite Extraction Report</h1>
    """

        # Summary stats
        total = len(self.results)
        successful = sum(1 for r in self.results if r["status"] == "success")
        total - successful
        total_tiles = sum(r.get("tiles", 0) for r in self.results)
        total_bytes = sum(r.get("size", 0) for r in self.results)

        html += f"""
    <div class="summary">
        <h2>Summary</h2>
        <div class="stats">
            <div class="stat">
                <div class="stat-value">{successful}/{total}</div>
                <div class="stat-label">Sprites Extracted</div>
            </div>
            <div class="stat">
                <div class="stat-value">{total_tiles:,}</div>
                <div class="stat-label">Total Tiles</div>
            </div>
            <div class="stat">
                <div class="stat-value">{total_bytes:,}</div>
                <div class="stat-label">Total Bytes</div>
            </div>
        </div>
    </div>

    <h2>Extracted Sprites</h2>
    """

        # Individual sprite cards
        for result in self.results:
            status_class = result["status"]
            status_badge_class = f"status-{status_class}"

            html += f"""
    <div class="sprite-card {status_class}">
        <div class="sprite-header">
            <div class="sprite-name">{result["name"]}</div>
            <div class="sprite-status {status_badge_class}">{result["status"].upper()}</div>
        </div>
        <div class="sprite-details">
            <span class="detail-label">SNES Address:</span>
            <span class="detail-value">{result.get("snes_address", "N/A")}</span>
            <span class="detail-label">ROM Offset:</span>
            <span class="detail-value">{result.get("rom_offset", "N/A")}</span>
            """

            if result["status"] == "success":
                html += f"""
            <span class="detail-label">Size:</span>
            <span class="detail-value">{result["size"]:,} bytes</span>
            <span class="detail-label">Tiles:</span>
            <span class="detail-value">{result["tiles"]} tiles</span>
                """

                # Add preview if PNG exists
                if result["files"].get("png"):
                    png_path = Path(result["files"]["png"])
                    if png_path.exists():
                        # Use relative path from report location
                        rel_path = f"../{png_path.name}"
                        html += f"""
        </div>
        <div class="sprite-preview">
            <img src="{rel_path}" alt="{result["name"]} sprite">
        </div>
                        """
                else:
                    html += "</div>"
            else:
                if "error" in result:
                    html += f"""
            <span class="detail-label">Error:</span>
            <span class="detail-value">{result["error"]}</span>
                    """
                html += "</div>"

            if result.get("notes"):
                html += f"""
        <div class="notes">
            📝 {result["notes"]}
        </div>
                """

            html += "</div>\n"

        html += """
    <div style="margin-top: 30px; text-align: center; color: #999; font-size: 0.9em;">
        Generated with Mesen2 Sprite Extractor
    </div>
</body>
</html>
"""

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)


def load_address_file(filepath: Path) -> list[dict[str, Any]]:
    """Load addresses from JSON or text file."""
    if filepath.suffix == ".json":
        with open(filepath) as f:
            return json.load(f)
    else:
        # Parse text file (one address per line, optionally with name)
        addresses = []
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                # Format: "address [name] [# notes]"
                parts = line.split("#", 1)
                main = parts[0].strip()
                notes = parts[1].strip() if len(parts) > 1 else ""

                tokens = main.split(None, 1)
                addr = tokens[0]
                name = tokens[1] if len(tokens) > 1 else f"sprite_{addr.replace(':', '_')}"

                addresses.append({"address": addr, "name": name, "notes": notes})

        return addresses


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Batch extract multiple sprites from Kirby Super Star",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Input file formats:

JSON format:
[
  {"name": "Cappy", "address": "$95:B000", "notes": "Enemy sprite"},
  {"name": "Kirby", "address": "$C0:0000", "notes": "Main character"}
]

Text format:
$95:B000 Cappy # Enemy sprite
$C0:0000 Kirby # Main character

Example usage:
  %(prog)s sprite_addresses.txt
  %(prog)s addresses.json --report my_sprites
""",
    )

    parser.add_argument("input_file", help="File containing sprite addresses")
    parser.add_argument("--report", help="Report filename (without extension)")

    args = parser.parse_args()

    input_path = Path(args.input_file)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)

    try:
        # Load addresses
        addresses = load_address_file(input_path)

        if not addresses:
            print("No addresses found in input file")
            sys.exit(1)

        print(f"Loaded {len(addresses)} sprite addresses from {input_path.name}")

        # Process sprites
        extractor = BatchExtractor()
        extractor.process_address_list(addresses)

        # Generate report
        report_path = extractor.save_report(args.report)

        # Summary
        successful = sum(1 for r in extractor.results if r["status"] == "success")
        print(f"\n{'=' * 60}")
        print(f"  Extraction Complete: {successful}/{len(addresses)} sprites extracted")
        print(f"  Open report: {report_path}")
        print("=" * 60)

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
