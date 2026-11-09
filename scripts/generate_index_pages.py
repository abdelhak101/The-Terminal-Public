import os
from pathlib import Path

def generate_index_files(docs_root="docs"):
    """
    Scans the docs directory and creates an index.md in every folder that doesn't have one.
    The index.md will list all markdown files in that directory.
    """
    docs_path = Path(docs_root)
    
    # Pillar mapping for nice titles
    pillar_map = {
        "guides": "Operational Playbooks",
        "technical": "Service Architecture",
        "features": "System Evolution",
        "adapters": "Data Adapters",
        "examples": "Research Examples",
        "maintenance": "Maintenance Hub",
        "playbooks": "Operational Playbooks",
        "data": "Data Intelligence",
        "services": "Service Architecture",
        "history": "Historical Milestones"
    }

    for root, dirs, files in os.walk(docs_root):
        root_path = Path(root)
        
        # Skip hidden folders
        if any(part.startswith(".") or part.startswith("_") for part in root_path.parts):
            continue
            
        # Check if index.md exists
        if "index.md" not in files:
            print(f"Generating index.md for {root}")
            
            folder_name = root_path.name
            title = pillar_map.get(folder_name, folder_name.replace("-", " ").title())
            
            lines = [
                f"# {title}",
                "",
                f"Welcome to the **{title}** section. Below are the available documentation pages in this category.",
                ""
            ]
            
            # List markdown files (excluding index.md itself)
            md_files = sorted([f for f in files if f.endswith(".md") and f != "index.md"])
            for md in md_files:
                doc_title = md.replace(".md", "").replace("-", " ").title()
                lines.append(f"- [{doc_title}]({md})")
                
            # List subdirectories (excluding hidden/internal)
            subdirs = sorted([d for d in dirs if not d.startswith(".") and not d.startswith("_")])
            if subdirs:
                lines.append("")
                lines.append("## Subcategories")
                for sd in subdirs:
                    sd_title = pillar_map.get(sd, sd.replace("-", " ").title())
                    lines.append(f"- [{sd_title}]({sd}/index.md)")
            
            with open(root_path / "index.md", "w", encoding="utf-8") as f:
                f.write("\n".join(lines))

if __name__ == "__main__":
    generate_index_files()
