import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from shared.registry import MetadataRegistry
from shared.clickhouse import ClickHouseStorage

def generate_inventory_page(output_file="docs/data-inventory.md"):
    meta_registry = MetadataRegistry()
    storage = ClickHouseStorage()
    
    try:
        assets = meta_registry.get_all_assets()
    except Exception:
        assets = []

    lines = [
        "# Data Inventory (The Vault)",
        "",
        "Below is a master list of all datasets currently ingested into ClickHouse. This page is automatically updated.",
        "",
        "| Symbol | Layer | Rows | Last Updated | Actions |",
        "| :--- | :--- | :--- | :--- | :--- |"
    ]
    
    for asset in assets:
        symbol = asset['symbol']
        library = asset['library']
        try:
            info = storage.get_symbol_info(library, symbol)
            row_count = f"{info.get('row_count', 0):,}"
            last_updated = str(info.get("last_updated"))[:19] if info.get("last_updated") else "N/A"
        except Exception:
            row_count = "Error"
            last_updated = "Error"
            
        # Add a placeholder for removal action
        remove_btn = f"🗑️ `DELETE {library}/{symbol}`"
        lines.append(f"| **{symbol}** | `{library}` | {row_count} | {last_updated} | {remove_btn} |")
        
    if not assets:
        lines.append("| N/A | N/A | 0 | N/A | - |")
        
    lines.append("")
    lines.append("---")
    lines.append("*To remove data programmatically, use the API: `DELETE /api/v1/inventory/{library}/{symbol}`*")
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Inventory page generated at {output_file}")

if __name__ == "__main__":
    generate_inventory_page()
