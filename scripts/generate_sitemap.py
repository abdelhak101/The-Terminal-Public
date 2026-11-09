import os
import sys
from pathlib import Path

# Add the project root to sys.path to import shared modules
sys.path.append(str(Path(__file__).parent.parent))

from shared.registry import DocumentationRegistry

def generate_sitemap(docs_root="docs", output_file="docs/sitemap.md"):
    """
    Generates a markdown sitemap page listing all discovered documentation.
    """
    registry = DocumentationRegistry(docs_root=docs_root)
    sitemap_data = registry.get_sitemap()
    
    lines = [
        "# Global Knowledge Index",
        "",
        "This page provides a flattened, pillar-grouped overview of all documentation available in The Terminal knowledge base.",
        ""
    ]
    
    # Sort pillars to ensure consistent order
    pillar_order = [
        "Operational Playbooks",
        "Service Architecture",
        "Data Intelligence",
        "Maintenance Hub",
        "System Evolution",
        "Data Adapters",
        "Research Examples",
        "General"
    ]
    
    # Add pillars that might not be in the explicit order
    all_pillars = sorted(sitemap_data.keys())
    for p in all_pillars:
        if p not in pillar_order:
            pillar_order.append(p)
            
    for pillar in pillar_order:
        if pillar not in sitemap_data or not sitemap_data[pillar]:
            continue
            
        lines.append(f"## {pillar}")
        for doc in sitemap_data[pillar]:
            # Use relative paths for links so they work in MkDocs
            path = doc['path_id'] + ".md"
            # Adjust path if we are in a subdirectory (though Sitemap is at root)
            lines.append(f"- [{doc['title']}]({path})")
        lines.append("")
        
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        
    print(f"Successfully generated sitemap at {output_file}")

if __name__ == "__main__":
    generate_sitemap()
