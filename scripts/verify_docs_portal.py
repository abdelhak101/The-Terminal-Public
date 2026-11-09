import sys
import os

# Add project root to path for local imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.registry import DocumentationRegistry

def verify_docs():
    print("--- Verifying DocumentationRegistry ---")
    registry = DocumentationRegistry(docs_root="docs")
    tree = registry.get_doc_tree()
    
    categories = ["technical", "guides", "examples", "adapters"]
    for cat in categories:
        if cat in tree:
            print(f"SUCCESS: Found {len(tree[cat])} docs in '{cat}'.")
        else:
            print(f"FAIL: Category '{cat}' not found in tree.")
            return False
            
    # Check search
    print("\n--- Verifying Search ---")
    results = registry.search_docs("FRED")
    if len(results) > 0:
        print(f"SUCCESS: Search for 'FRED' found {len(results)} results.")
        for res in results:
            print(f" - [{res['category']}] {res['title']}")
    else:
        print("FAIL: Search for 'FRED' returned no results.")
        return False
        
    return True

if __name__ == "__main__":
    if verify_docs():
        print("\nDOCUMENTATION PORTAL BACKEND VERIFIED")
        sys.exit(0)
    else:
        print("\nVERIFICATION FAILED")
        sys.exit(1)
