import os
import re
import sys
from pathlib import Path

def verify_links(docs_dir="docs"):
    """
    Scans markdown files for internal links and verifies they point to existing files.
    """
    docs_path = Path(docs_dir)
    if not docs_path.exists():
        print(f"Error: {docs_dir} directory not found.")
        sys.exit(1)

    # Regex to find internal markdown links: [text](path.md) or [text](path/to/file.md)
    # Excludes external http/https links
    link_pattern = re.compile(r'\[.*?\]\(((?!http|https|#).*?\.md)\)')
    
    broken_links = []
    checked_files = 0
    total_links = 0

    for md_file in docs_path.rglob("*.md"):
        checked_files += 1
        with open(md_file, "r", encoding="utf-8") as f:
            content = f.read()
            
        links = link_pattern.findall(content)
        for link in links:
            total_links += 1
            # Resolve relative link
            link_path = (md_file.parent / link).resolve()
            
            if not link_path.exists():
                # Try relative to docs root if relative to file fails
                alt_path = (docs_path / link).resolve()
                if not alt_path.exists():
                    broken_links.append((md_file, link))

    print(f"\n--- Documentation Link Audit ---")
    print(f"Files scanned: {checked_files}")
    print(f"Links found:   {total_links}")
    
    if broken_links:
        print(f"\n❌ Found {len(broken_links)} broken links:")
        for source, target in broken_links:
            print(f"  - {source}: '{target}'")
        return False
    else:
        print("\n✅ All internal links are valid.")
        return True

if __name__ == "__main__":
    success = verify_links()
    if not success:
        sys.exit(1)
    sys.exit(0)
