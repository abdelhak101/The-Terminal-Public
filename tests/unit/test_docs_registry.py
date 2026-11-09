import pytest
import os
import shutil
from pathlib import Path
from shared.registry import DocumentationRegistry

@pytest.fixture
def temp_docs(tmp_path):
    """Creates a temporary docs directory with nested structure."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    
    # Pillar 1: Guides (Nested)
    guides = docs_dir / "guides"
    guides.mkdir()
    playbooks = guides / "playbooks"
    playbooks.mkdir()
    (playbooks / "local-dev.md").write_text("# Local Dev")
    (guides / "getting-started.md").write_text("# Getting Started")
    
    # Pillar 2: Features (with History)
    features = docs_dir / "features"
    features.mkdir()
    history = features / "history"
    history.mkdir()
    (history / "legacy-feature.md").write_text("# Legacy Feature")
    (features / "new-feature.md").write_text("---\nid: new-feat\ntitle: Super Feature\n---\n# New Feature")
    
    # Hidden files and folders
    (docs_dir / "_internal.md").write_text("# Hidden")
    (docs_dir / ".hidden-folder").mkdir()
    
    return docs_dir

def test_recursive_discovery(temp_docs):
    registry = DocumentationRegistry(docs_root=str(temp_docs))
    tree = registry.get_doc_tree()
    
    # Verify structure
    pillar_names = [n['name'] for n in tree]
    assert "guides" in pillar_names
    assert "features" in pillar_names
    assert "history" not in pillar_names # It's nested
    assert "_internal.md" not in [n['name'] for n in tree]
    
    # Verify nesting in Guides
    guides_node = next(n for n in tree if n['name'] == "guides")
    assert guides_node['type'] == "directory"
    child_names = [c['name'] for c in guides_node['children']]
    assert "playbooks" in child_names
    assert "getting-started.md" in child_names
    
    # Verify nested playbook
    playbooks_node = next(n for n in guides_node['children'] if n['name'] == "playbooks")
    playbook_file = next(f for f in playbooks_node['children'] if f['name'] == "local-dev.md")
    assert playbook_file['path_id'] == "guides/playbooks/local-dev"

def test_get_doc_by_path(temp_docs):
    registry = DocumentationRegistry(docs_root=str(temp_docs))
    
    # Nested doc
    doc = registry.get_doc_by_path("guides/playbooks/local-dev")
    assert doc is not None
    assert doc['title'] == "Local Dev"
    
    # Frontmatter doc
    doc = registry.get_doc_by_path("features/new-feature")
    assert doc is not None
    assert doc['id'] == "new-feat"
    assert doc['title'] == "Super Feature"
    
    # Non-existent
    assert registry.get_doc_by_path("non/existent") is None

def test_security_traversal(temp_docs):
    registry = DocumentationRegistry(docs_root=str(temp_docs))
    
    # Attempt traversal
    assert registry.get_doc_by_path("../workspace.yaml") is None
    assert registry.get_doc_by_path("/etc/passwd") is None

def test_get_sitemap(temp_docs):
    registry = DocumentationRegistry(docs_root=str(temp_docs))
    sitemap = registry.get_sitemap()
    
    # Verify pillars
    assert "Operational Playbooks" in sitemap
    assert "System Evolution" in sitemap
    
    # Verify flattening (playbooks is flattened into Operational Playbooks)
    guides = sitemap["Operational Playbooks"]
    titles = [d['title'] for d in guides]
    assert "Local Dev" in titles
    assert "Getting Started" in titles
    
    # Verify path_ids are correct
    playbook = next(d for d in guides if d['title'] == "Local Dev")
    assert playbook['path_id'] == "guides/playbooks/local-dev"
