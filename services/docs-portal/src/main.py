import os
import logging
import requests
import json
import numpy as np
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from shared.registry import DocumentationRegistry, MetadataRegistry
from shared.serialization import safe_json_response
from shared.clickhouse import ClickHouseStorage
from adapters import ADAPTER_MAP
from shared.adapters import SearchableAdapter

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("docs-portal")

app = FastAPI(title="Documentation Portal API", version="1.0.0")

# Initialize Templates and Static Files
# Handle path correctly for both local dev and docker
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static_assets")

# Enable CORS for the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize DocumentationRegistry
DOCS_ROOT = os.getenv("DOCS_ROOT", "docs")
if not os.path.isabs(DOCS_ROOT) and not os.path.exists(DOCS_ROOT):
    # Try common local development path
    DOCS_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "docs")

registry = DocumentationRegistry(docs_root=DOCS_ROOT)
meta_registry = MetadataRegistry()
storage = ClickHouseStorage()

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://gateway:8000")

@app.get("/health")
def health_check():
    """
    Soft Health Check: Verifies ClickHouse connectivity.
    """
    storage_ok = storage.check_health()
    return {
        "status": "healthy",
        "storage": "connected" if storage_ok else "unreachable"
    }

@app.get("/api/v1/docs/tree")
def get_doc_tree():
    """Returns the navigation tree for all documentation."""
    try:
        return registry.get_doc_tree()
    except Exception as e:
        logger.error(f"Failed to fetch doc tree: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/v1/docs/sitemap")
def get_sitemap():
    """Returns a flattened sitemap grouped by pillar."""
    try:
        return registry.get_sitemap()
    except Exception as e:
        logger.error(f"Failed to fetch sitemap: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/v1/docs/content/{path:path}")
def get_doc_content(path: str):
    """Retrieves metadata and content for a specific document by its path."""
    doc = registry.get_doc_by_path(path)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document '{path}' not found")
    return doc

@app.get("/api/v1/docs/search")
def search_docs(q: str = Query(..., min_length=2)):
    """Search across all documentation content and metadata."""
    try:
        results = registry.search_docs(q)
        return {"query": q, "results": results}
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/v1/inventory")
def get_inventory():
    """Returns a list of all ingested assets with storage stats."""
    try:
        assets = meta_registry.get_all_assets()
        inventory = []
        for asset in assets:
            symbol = asset['symbol']
            library = asset['library']
            label = asset.get('label', 'main')
            target_table = asset.get('metadata', {}).get('target_table')
            # Fetch real-time stats from ClickHouse
            info = storage.get_symbol_info(library, symbol, label=label, target_table=target_table)
            inventory.append({
                **asset,
                "row_count": info.get("row_count", 0),
                "size_bytes": info.get("size_bytes", 0),
                "last_updated": str(info.get("last_updated")) if info.get("last_updated") else None
            })
        return inventory
    except Exception as e:
        logger.error(f"Failed to fetch inventory: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/inventory/lineage")
def get_lineage_dashboard():
    """Returns grouped Bronze and Silver assets with their metrics for the dashboard."""
    try:
        pairs = meta_registry.get_lineage_pairs()
        dashboard_data = []
        
        for pair in pairs:
            symbol = pair['symbol']
            label = pair['label']
            
            entry = {
                "symbol": symbol,
                "label": label,
                "bronze": None,
                "silver": None,
                "status": "orphaned"
            }
            
            # Fetch Bronze metrics if exists
            if pair['bronze']:
                target_table = pair['bronze'].get('metadata', {}).get('target_table')
                info = storage.get_symbol_info("bronze", symbol, label=label, target_table=target_table)
                entry['bronze'] = {
                    **pair['bronze'],
                    "row_count": info.get("row_count", 0),
                    "size_bytes": info.get("size_bytes", 0),
                    "last_updated": str(info.get("last_updated")) if info.get("last_updated") else None
                }
            
            # Fetch Silver metrics if exists
            if pair['silver']:
                target_table = pair['silver'].get('metadata', {}).get('target_table')
                info = storage.get_symbol_info("silver", symbol, label=label, target_table=target_table)
                entry['silver'] = {
                    **pair['silver'],
                    "row_count": info.get("row_count", 0),
                    "size_bytes": info.get("size_bytes", 0),
                    "last_updated": str(info.get("last_updated")) if info.get("last_updated") else None
                }
            
            # Determine Status
            if entry['bronze'] and entry['silver']:
                b_rows = entry['bronze']['row_count']
                s_rows = entry['silver']['row_count']
                # Basic check: matching rows
                if b_rows == s_rows and b_rows > 0:
                    entry['status'] = "synced"
                elif b_rows == 0 or s_rows == 0:
                     entry['status'] = "orphaned"
                else:
                    entry['status'] = "lagging"
            else:
                entry['status'] = "orphaned"
                
            dashboard_data.append(entry)
            
        return dashboard_data
    except Exception as e:
        logger.error(f"Failed to fetch lineage dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def _get_target_table(library: str, symbol: str, label: str = "main") -> Optional[str]:
    assets = meta_registry.get_all_assets()
    for a in assets:
        if a["library"] == library and a["symbol"] == symbol and a.get("label", "main") == label:
            return a.get("metadata", {}).get("target_table")
    return None

@app.get("/api/v1/inventory/{library}/{symbol}/data")
def get_asset_data(
    library: str, 
    symbol: str, 
    label: str = "main", 
    page: int = Query(1, ge=1), 
    size: int = Query(50, ge=1, le=100),
    reverse: bool = Query(False)
):
    """Returns a paginated slice of an asset's data."""
    try:
        target_table = _get_target_table(library, symbol, label)
        rows = storage.get_symbol_data_slice(library, symbol, label=label, page=page, size=size, reverse=reverse, target_table=target_table)
        
        # Get total row count for pagination
        info = storage.get_symbol_info(library, symbol, label=label, target_table=target_table)
        total_rows = info.get("row_count", 0)
        total_pages = (total_rows + size - 1) // size if total_rows > 0 else 1
        
        return safe_json_response({
            "rows": rows,
            "total_rows": total_rows,
            "total_pages": total_pages
        })
    except Exception as e:
        logger.error(f"Failed to fetch data slice for {symbol} ({label}): {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/inventory/{library}/{symbol}/snapshot")
def get_asset_snapshot(library: str, symbol: str, label: str = "main"):
    """Returns a downsampled snapshot for charting."""
    try:
        target_table = _get_target_table(library, symbol, label)
        return safe_json_response(storage.get_symbol_snapshot(symbol, library, label=label, target_table=target_table))
    except Exception as e:
        logger.error(f"Failed to fetch snapshot for {symbol} ({label}): {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/inventory/explorer/{library}/{symbol}")
def serve_explorer_ui(request: Request, library: str, symbol: str, label: str = "main"):
    """Serves a rich HTML UI for the Asset Explorer."""
    try:
        target_table = _get_target_table(library, symbol, label)
        # Fetch initial metadata for the render
        metadata = storage.get_symbol_info(library, symbol, label=label, target_table=target_table)
        
        return templates.TemplateResponse("explorer.html", {
            "request": request,
            "library": library,
            "symbol": symbol,
            "label": label,
            "metadata": metadata
        })
    except Exception as e:
        logger.error(f"Failed to render explorer for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/inventory/dashboard")
def serve_lineage_dashboard():
    """Serves a rich split-screen UI for the Unified Lineage Dashboard."""
    from fastapi.responses import HTMLResponse
    html_content = """
    <html>
    <head>
        <title>Lineage Dashboard - The Eagle Eye</title>
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; background: #f8fafc; color: #1e293b; }
            .container { padding: 40px; max-width: 1300px; margin: 0 auto; }
            header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
            h1 { color: #1e3a8a; margin: 0; font-weight: 700; font-size: 28px; }
            .subtitle { color: #64748b; margin-top: 4px; font-size: 14px; }
            
            .controls-card { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); margin-bottom: 24px; display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }
            .search-input { flex: 1; min-width: 250px; padding: 10px 16px; border: 1px solid #cbd5e1; border-radius: 8px; font-size: 14px; outline: none; transition: border-color 0.2s; }
            .search-input:focus { border-color: #2563eb; }
            
            .filter-group { display: flex; gap: 8px; }
            .filter-btn { padding: 8px 14px; background: #f1f5f9; border: 1px solid #e2e8f0; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; color: #475569; transition: all 0.2s; }
            .filter-btn:hover { background: #e2e8f0; }
            .filter-btn.active { background: #2563eb; color: white; border-color: #2563eb; }
            
            .refresh-btn { padding: 10px 20px; background: #1e3a8a; color: white; border: none; border-radius: 8px; font-weight: bold; cursor: pointer; font-size: 14px; display: flex; align-items: center; gap: 6px; transition: background-color 0.2s; }
            .refresh-btn:hover { background: #172554; }
            
            .table-container { background: white; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); overflow-x: auto; -webkit-overflow-scrolling: touch; border: 1px solid #e2e8f0; }
            table { width: 100%; border-collapse: collapse; text-align: left; font-size: 14px; min-width: 800px; }
            th { background: #f8fafc; padding: 14px 20px; font-weight: 600; color: #475569; border-bottom: 1px solid #e2e8f0; cursor: pointer; user-select: none; transition: background-color 0.2s; }
            th:hover { background: #f1f5f9; }
            th.sort-asc::after { content: " ▴"; }
            th.sort-desc::after { content: " ▾"; }
            
            td { padding: 16px 20px; border-bottom: 1px solid #f1f5f9; vertical-align: middle; }
            tr:last-child td { border-bottom: none; }
            tr:hover td { background-color: #fafaf9; }
            
            .symbol-cell { font-weight: 700; color: #0f172a; }
            .label-cell { font-family: monospace; background: #f1f5f9; color: #475569; padding: 2px 6px; border-radius: 4px; font-size: 12px; }
            
            /* Status Badges */
            .badge { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600; text-transform: uppercase; }
            
            .badge-active { background-color: #dcfce7; color: #166534; }
            .badge-empty { background-color: #fef9c3; color: #854d0e; }
            .badge-missing { background-color: #f1f5f9; color: #64748b; border: 1px dashed #cbd5e1; }
            
            .badge-synced { background-color: #dcfce7; color: #166534; }
            .badge-lagging { background-color: #ffedd5; color: #9a3412; }
            .badge-orphaned { background-color: #fee2e2; color: #991b1b; }
            
            .metric-text { font-size: 12px; color: #64748b; margin-top: 4px; display: block; }
            
            .layer-actions { display: inline-flex; gap: 4px; align-items: center; margin-left: auto; }
            .action-btn { display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px; border-radius: 4px; text-decoration: none; border: 1px solid #e2e8f0; background: white; color: #475569; cursor: pointer; transition: all 0.2s; font-size: 12px; }
            .action-btn:hover { background: #f1f5f9; color: #0f172a; border-color: #cbd5e1; }
            .action-btn.delete:hover { background: #fee2e2; color: #dc2626; border-color: #fca5a5; }
            
            .error-banner { background-color: #fee2e2; border: 1px solid #fca5a5; color: #991b1b; padding: 16px; border-radius: 8px; margin-bottom: 24px; font-weight: 500; display: flex; justify-content: space-between; align-items: center; }
            .error-banner button { background: #991b1b; color: white; border: none; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-weight: 600; }
            
            .empty-state { text-align: center; color: #64748b; padding: 40px; font-style: italic; }

            /* Responsive Adjustments */
            @media (max-width: 768px) {
                .container { padding: 16px; }
                header { flex-direction: column; align-items: flex-start; gap: 16px; }
                .controls-card { flex-direction: column; align-items: stretch; gap: 12px; padding: 16px; }
                .filter-group { flex-wrap: wrap; }
                .search-input { min-width: 100%; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <div>
                    <h1>Lineage Dashboard</h1>
                    <div class="subtitle">Unified Eagle-Eye View of Data Pipelines</div>
                </div>
                <div style="display: flex; gap: 12px;">
                    <a href="/inventory/adapter-search" class="refresh-btn" style="background: #3b82f6; text-decoration: none;">🔍 Search Adapters</a>
                    <button class="refresh-btn" onclick="fetchData()">🔄 Refresh</button>
                </div>
            </header>
            
            <div id="error-container"></div>
            
            <div class="controls-card">
                <input type="text" id="search-input" class="search-input" placeholder="Search by Symbol or Label..." oninput="handleSearchFilter()">
                <div class="filter-group">
                    <button class="filter-btn active" data-filter="all" onclick="setStatusFilter('all')">All</button>
                    <button class="filter-btn" data-filter="synced" onclick="setStatusFilter('synced')">Synced</button>
                    <button class="filter-btn" data-filter="lagging" onclick="setStatusFilter('lagging')">Lagging</button>
                    <button class="filter-btn" data-filter="missing-bronze" onclick="setStatusFilter('missing-bronze')">Missing Bronze</button>
                    <button class="filter-btn" data-filter="missing-silver" onclick="setStatusFilter('missing-silver')">Missing Silver</button>
                </div>
            </div>
            
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th id="th-symbol" onclick="handleSort('symbol')">Symbol</th>
                            <th id="th-label" onclick="handleSort('label')">Label</th>
                            <th id="th-bronze" onclick="handleSort('bronze_rows')">Bronze Status</th>
                            <th id="th-silver" onclick="handleSort('silver_rows')">Silver Status</th>
                        </tr>
                    </thead>
                    <tbody id="table-body">
                        <tr>
                            <td colspan="4" class="empty-state">Loading data lineage...</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>

        <script>
            let windowState = {
                allAssets: [],
                searchQuery: '',
                statusFilter: 'all',
                sortColumn: 'symbol',
                sortDirection: 'asc'
            };

            async function fetchData() {
                const errorContainer = document.getElementById('error-container');
                errorContainer.innerHTML = '';
                try {
                    const res = await fetch('/api/v1/inventory/lineage');
                    if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
                    windowState.allAssets = await res.json();
                    applyFiltersAndRender();
                } catch (e) {
                    errorContainer.innerHTML = `
                        <div class="error-banner">
                            <span>Failed to fetch lineage metrics: ${e.message}</span>
                            <button onclick="fetchData()">Retry</button>
                        </div>
                    `;
                }
            }

            function setStatusFilter(filterValue) {
                windowState.statusFilter = filterValue;
                document.querySelectorAll('.filter-btn').forEach(btn => {
                    if (btn.getAttribute('data-filter') === filterValue) {
                        btn.classList.add('active');
                    } else {
                        btn.classList.remove('active');
                    }
                });
                applyFiltersAndRender();
            }

            function handleSearchFilter() {
                windowState.searchQuery = document.getElementById('search-input').value.toLowerCase();
                applyFiltersAndRender();
            }

            function handleSort(column) {
                if (windowState.sortColumn === column) {
                    windowState.sortDirection = windowState.sortDirection === 'asc' ? 'desc' : 'asc';
                } else {
                    windowState.sortColumn = column;
                    windowState.sortDirection = 'asc';
                }

                // Update column headers classes
                document.querySelectorAll('th').forEach(th => {
                    th.classList.remove('sort-asc', 'sort-desc');
                });
                const activeTh = document.getElementById(`th-${column}`);
                if (activeTh) {
                    activeTh.classList.add(windowState.sortDirection === 'asc' ? 'sort-asc' : 'sort-desc');
                }

                applyFiltersAndRender();
            }

            function applyFiltersAndRender() {
                let data = [...windowState.allAssets];

                // 1. Search Query Filter
                if (windowState.searchQuery) {
                    data = data.filter(item => 
                        item.symbol.toLowerCase().includes(windowState.searchQuery) ||
                        item.label.toLowerCase().includes(windowState.searchQuery)
                    );
                }

                // 2. Status Filter
                if (windowState.statusFilter !== 'all') {
                    if (windowState.statusFilter === 'synced') {
                        data = data.filter(item => item.status === 'synced');
                    } else if (windowState.statusFilter === 'lagging') {
                        data = data.filter(item => item.status === 'lagging');
                    } else if (windowState.statusFilter === 'missing-bronze') {
                        data = data.filter(item => !item.bronze);
                    } else if (windowState.statusFilter === 'missing-silver') {
                        data = data.filter(item => !item.silver);
                    }
                }

                // 3. Sort logic
                data.sort((a, b) => {
                    let valA, valB;
                    if (windowState.sortColumn === 'symbol') {
                        valA = a.symbol;
                        valB = b.symbol;
                    } else if (windowState.sortColumn === 'label') {
                        valA = a.label;
                        valB = b.label;
                    } else if (windowState.sortColumn === 'bronze_rows') {
                        valA = a.bronze ? a.bronze.row_count : -1;
                        valB = b.bronze ? b.bronze.row_count : -1;
                    } else if (windowState.sortColumn === 'silver_rows') {
                        valA = a.silver ? a.silver.row_count : -1;
                        valB = b.silver ? b.silver.row_count : -1;
                    }

                    if (valA === undefined || valA === null) return 1;
                    if (valB === undefined || valB === null) return -1;

                    if (typeof valA === 'string') {
                        return windowState.sortDirection === 'asc' 
                            ? valA.localeCompare(valB) 
                            : valB.localeCompare(valA);
                    } else {
                        return windowState.sortDirection === 'asc'
                            ? valA - valB
                            : valB - valA;
                    }
                });

                renderTable(data);
            }

            function renderTable(data) {
                const tbody = document.getElementById('table-body');
                tbody.innerHTML = '';

                if (data.length === 0) {
                    tbody.innerHTML = `<tr><td colspan="4" class="empty-state">No matching data lineage entries found.</td></tr>`;
                    return;
                }

                data.forEach(pair => {
                    const tr = document.createElement('tr');

                    // Symbol and Label
                    const tdSymbol = document.createElement('td');
                    tdSymbol.className = 'symbol-cell';
                    tdSymbol.innerText = pair.symbol;
                    tr.appendChild(tdSymbol);

                    const tdLabel = document.createElement('td');
                    const spanLabel = document.createElement('span');
                    spanLabel.className = 'label-cell';
                    spanLabel.innerText = pair.label;
                    tdLabel.appendChild(spanLabel);
                    tr.appendChild(tdLabel);

                    // Bronze Column
                    const tdBronze = document.createElement('td');
                    if (pair.bronze) {
                        const status = pair.bronze.row_count > 0 ? 'active' : 'empty';
                        const badgeClass = `badge-${status}`;
                        const labelParam = pair.label === 'main' ? '' : `?label=${pair.label}`;
                        tdBronze.innerHTML = `
                            <div style="display: flex; align-items: center;">
                                <div>
                                    <span class="badge ${badgeClass}">${status}</span>
                                    <span class="metric-text">Rows: ${pair.bronze.row_count.toLocaleString()}<br>Size: ${(pair.bronze.size_bytes / 1024).toFixed(1)} KB</span>
                                </div>
                                <div class="layer-actions">
                                    <a class="action-btn" href="/inventory/explorer/bronze/${pair.symbol}${labelParam}" title="Inspect Bronze">🔍</a>
                                    <button class="action-btn delete" title="Delete Bronze" onclick="handleDelete('bronze', '${pair.symbol}', '${pair.label}')">🗑️</button>
                                </div>
                            </div>
                        `;
                    } else {
                        tdBronze.innerHTML = `<span class="badge badge-missing">Missing</span>`;
                    }
                    tr.appendChild(tdBronze);

                    // Silver Column
                    const tdSilver = document.createElement('td');
                    if (pair.silver) {
                        const status = pair.silver.row_count > 0 ? 'active' : 'empty';
                        const badgeClass = `badge-${status}`;
                        const labelParam = pair.label === 'main' ? '' : `?label=${pair.label}`;
                        tdSilver.innerHTML = `
                            <div style="display: flex; align-items: center;">
                                <div>
                                    <span class="badge ${badgeClass}">${status}</span>
                                    <span class="metric-text">Rows: ${pair.silver.row_count.toLocaleString()}<br>Size: ${(pair.silver.size_bytes / 1024).toFixed(1)} KB</span>
                                </div>
                                <div class="layer-actions">
                                    <a class="action-btn" href="/inventory/explorer/silver/${pair.symbol}${labelParam}" title="Inspect Silver">🔍</a>
                                    <button class="action-btn delete" title="Delete Silver" onclick="handleDelete('silver', '${pair.symbol}', '${pair.label}')">🗑️</button>
                                </div>
                            </div>
                        `;
                    } else {
                        tdSilver.innerHTML = `<span class="badge badge-missing">Missing</span>`;
                    }
                    tr.appendChild(tdSilver);

                    tbody.appendChild(tr);
                });
            }

            async function handleDelete(library, symbol, label) {
                const confirmMsg = `Are you sure you want to permanently delete the ${library} asset "${symbol}" (label: ${label})? This deletes the physical table data and metadata registry for this layer.`;
                if (!confirm(confirmMsg)) return;

                try {
                    const res = await fetch(`/api/v1/inventory/${library}/${symbol}?label=${label}`, { method: 'DELETE' });
                    if (!res.ok) throw new Error(`Failed to delete ${library}: status ${res.status}`);
                    alert(`Successfully deleted ${library} asset.`);
                    fetchData();
                } catch (e) {
                    alert(`Error deleting asset: ${e.message}`);
                }
            }

            // Init load
            fetchData();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.delete("/api/v1/inventory/{library}/{symbol}")
def delete_asset(library: str, symbol: str, label: str = "main"):
    """Hard wipes an asset from both ClickHouse and Metadata Registry."""
    try:
        target_table = _get_target_table(library, symbol, label)
        # 1. Delete from physical storage
        storage.delete_symbol(library, symbol, label=label, target_table=target_table)
        # 2. Delete from metadata registry
        meta_registry.delete_asset_metadata(symbol, library, label=label)
        return {"status": "deleted", "symbol": symbol, "library": library, "label": label}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Deletion failed for {symbol} ({label}) in {library}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/api/v1/docs/run-example/{example_id}")
async def run_example(example_id: str, payload: Dict[str, Any] = None):
    """
    Proxies a 'Run' request from an example to the Research Gateway.
    """
    example = registry.get_doc_by_id("examples", example_id)
    if not example or 'gateway_route' not in example:
        raise HTTPException(status_code=404, detail=f"Example '{example_id}' not found or has no data route")
    
    url = f"{GATEWAY_URL}{example['gateway_route']}"
    method = example.get('method', 'GET').upper()
    
    try:
        if method == 'POST':
            # Handle list/dict payloads correctly
            response = requests.post(url, json=payload or {}, timeout=10)
        else:
            response = requests.get(url, timeout=10)
            
        return {
            "example_id": example_id,
            "url": url,
            "status": response.status_code,
            "data": response.json()
        }
    except Exception as e:
        logger.error(f"Failed to run example {example_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class AdapterSearchRequest(BaseModel):
    query: str
    adapter_type: Optional[str] = None


@app.get("/api/v1/adapters/list")
def list_adapters():
    """Returns list of available adapters and whether they support search."""
    adapters = []
    for name, cls in ADAPTER_MAP.items():
        supports_search = issubclass(cls, SearchableAdapter)
        adapters.append({
            "name": name,
            "label": cls.__name__,
            "supports_search": supports_search
        })
    return {"adapters": adapters}


@app.post("/api/v1/adapters/search")
def search_adapters(request: AdapterSearchRequest):
    """Searches for data identifiers using specified or all searchable adapters."""
    results = []
    errors = []
    
    if request.adapter_type:
        # Search specific adapter
        if request.adapter_type not in ADAPTER_MAP:
            raise HTTPException(status_code=404, detail=f"Adapter '{request.adapter_type}' not found")
        
        adapter_cls = ADAPTER_MAP[request.adapter_type]
        if not issubclass(adapter_cls, SearchableAdapter):
            raise HTTPException(status_code=400, detail=f"Adapter '{request.adapter_type}' does not support search")
        
        try:
            adapter = adapter_cls()
            search_results = adapter.search(request.query)
            for res in search_results:
                results.append({
                    "adapter_type": request.adapter_type,
                    "identifier": res.identifier,
                    "label": res.name,
                    "description": res.description,
                    "metadata": res.metadata
                })
        except Exception as e:
            logger.error(f"Search failed for adapter {request.adapter_type}: {e}")
            errors.append(f"{request.adapter_type}: {str(e)}")
    else:
        # Search all searchable adapters
        for name, cls in ADAPTER_MAP.items():
            if not issubclass(cls, SearchableAdapter):
                continue
            try:
                adapter = cls()
                search_results = adapter.search(request.query)
                for res in search_results:
                    results.append({
                        "adapter_type": name,
                        "identifier": res.identifier,
                        "label": res.name,
                        "description": res.description,
                        "metadata": res.metadata
                    })
            except Exception as e:
                logger.error(f"Search failed for adapter {name}: {e}")
                errors.append(f"{name}: {str(e)}")
    
    return {"results": results, "errors": errors}


@app.get("/api/v1/adapters/{adapter_type}/schema")
def get_adapter_schema(adapter_type: str):
    """Returns parameter schema for an adapter, serialized for the frontend."""
    if adapter_type not in ADAPTER_MAP:
        raise HTTPException(status_code=404, detail=f"Adapter '{adapter_type}' not found")
    adapter_cls = ADAPTER_MAP[adapter_type]
    raw_schema = adapter_cls.get_parameter_schema()

    # Map Python types to frontend-friendly type strings
    type_map = {str: "text", bool: "bool", int: "number", float: "number"}

    properties = []
    for name, spec in raw_schema.items():
        prop = {
            "name": name,
            "type": type_map.get(spec.get("type"), "text"),
            "default": spec.get("default"),
            "required": spec.get("required", False),
            "description": spec.get("description", ""),
        }
        properties.append(prop)

    return {"schema": {"properties": properties}}


@app.get("/inventory/adapter-search")
def serve_adapter_search_ui(request: Request):
    """Serves a UI for searching adapters and generating config."""
    return templates.TemplateResponse("adapter_search.html", {"request": request})


# Serve static files (compiled MkDocs site) via catch-all route.
# Using a route instead of app.mount("/", ...) so that explicit API routes
# (e.g. /inventory/adapter-search) are matched first by the router.
STATIC_DIR = os.getenv("STATIC_DIR", "site")
if os.path.exists(STATIC_DIR):
    @app.get("/{path:path}")
    async def serve_mkdocs_fallback(path: str):
        """Fallback: serves MkDocs static files for paths not handled by API routes."""
        base = os.path.join(STATIC_DIR, path)
        # Exact file match (css, js, images, etc.)
        if os.path.isfile(base):
            return FileResponse(base)
        # HTML page: path.html
        if os.path.isfile(base + ".html"):
            return FileResponse(base + ".html")
        # Directory with index.html
        index = os.path.join(base, "index.html")
        if os.path.isfile(index):
            return FileResponse(index)
        # Root path fallback
        if path == "":
            root_index = os.path.join(STATIC_DIR, "index.html")
            if os.path.isfile(root_index):
                return FileResponse(root_index)
        raise HTTPException(status_code=404, detail="Not found")
else:
    logger.warning(f"Static directory '{STATIC_DIR}' not found. UI will not be served.")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "23002"))
    uvicorn.run(app, host="0.0.0.0", port=port)
