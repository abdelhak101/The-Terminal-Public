/**
 * Asset Explorer Client-Side Logic
 */

let currentPage = 1;
const PAGE_SIZE = 50;
let chart = null;
let lineSeries = null;

document.addEventListener('DOMContentLoaded', () => {
    try {
        initChart();
    } catch (e) {
        console.error("Chart initialization failed:", e);
        document.getElementById('chart-status').innerText = "Visualization engine error";
    }
    
    fetchSnapshot();
    fetchData(currentPage);

    // Event Listeners
    document.getElementById('prev-page').addEventListener('click', () => {
        if (currentPage > 1) {
            currentPage--;
            fetchData(currentPage);
        }
    });

    document.getElementById('next-page').addEventListener('click', () => {
        currentPage++;
        fetchData(currentPage);
    });

    document.getElementById('btn-delete').addEventListener('click', handleDelete);
});

/**
 * Initializes the Lightweight Chart
 */
function initChart() {
    const chartContainer = document.getElementById('chart-container');
    if (!chartContainer) {
        console.error("Chart container not found");
        return;
    }

    console.log("Initializing Lightweight Chart...");
    try {
        chart = LightweightCharts.createChart(chartContainer, {
            layout: {
                background: { color: '#ffffff' },
                textColor: '#1c1e21',
            },
            grid: {
                vertLines: { color: '#f0f2f5' },
                horzLines: { color: '#f0f2f5' },
            },
            crosshair: {
                mode: LightweightCharts.CrosshairMode.Normal,
            },
            rightPriceScale: {
                borderVisible: false,
            },
            timeScale: {
                borderVisible: false,
                timeVisible: true,
                secondsVisible: false,
            },
        });

        if (chart && typeof chart.addLineSeries === 'function') {
            lineSeries = chart.addLineSeries({
                color: '#3f51b5',
                lineWidth: 2,
                title: 'Value',
            });
        } else {
            console.error("chart.addLineSeries is not a function.");
            throw new Error("Invalid Chart object returned");
        }

        // Resize handler
        window.addEventListener('resize', () => {
            if (chart) {
                chart.applyOptions({
                    width: chartContainer.clientWidth,
                    height: chartContainer.clientHeight
                });
            }
        });
    } catch (err) {
        console.error("Error during chart setup:", err);
        throw err;
    }
}

/**
 * Fetches downsampled snapshot for the chart
 */
async function fetchSnapshot() {
    const statusEl = document.getElementById('chart-status');
    console.log(`Fetching snapshot for ${ASSET_CONFIG.symbol}...`);
    try {
        const response = await fetch(`/api/v1/inventory/${ASSET_CONFIG.library}/${ASSET_CONFIG.symbol}/snapshot?label=${ASSET_CONFIG.label}`);
        const data = await response.json();

        if (data && data.length > 0) {
            console.log(`Received ${data.length} snapshot points.`);
            // Transform data: ensure 't' is a unix timestamp or valid string format
            const chartData = data.map(item => {
                const normalized = String(item.t).replace(' ', 'T');
                const parsed = Date.parse(normalized);
                let timeVal = item.t;
                if (!isNaN(parsed)) {
                    timeVal = Math.floor(parsed / 1000);
                }
                return {
                    time: timeVal,
                    value: item.v
                };
            }).sort((a, b) => (typeof a.time === 'number' && typeof b.time === 'number') ? a.time - b.time : 0);

            // Lightweight charts needs unique times.
            const uniqueData = [];
            const seenTimes = new Set();
            for (const d of chartData) {
                if (!seenTimes.has(d.time)) {
                    uniqueData.push(d);
                    seenTimes.add(d.time);
                }
            }

            lineSeries.setData(uniqueData);
            chart.timeScale().fitContent();
            statusEl.innerText = `Displaying ${uniqueData.length} points`;
        } else {
            console.warn("Snapshot API returned no data.");
            statusEl.innerText = "No visualization data available";
        }
    } catch (error) {
        console.error("Failed to fetch snapshot:", error);
        statusEl.innerText = "Error loading chart";
    }
}

/**
 * Fetches paginated data slice for the grid
 */
async function fetchData(page) {
    const tableHead = document.getElementById('table-head');
    const tableBody = document.getElementById('table-body');
    const pageInfo = document.getElementById('page-info');
    const prevBtn = document.getElementById('prev-page');
    const nextBtn = document.getElementById('next-page');

    console.log(`Fetching data page ${page} (reverse=true)...`);
    tableBody.innerHTML = '<tr><td colspan="100%" class="loading-cell">Loading page ' + page + '...</td></tr>';

    try {
        const response = await fetch(`/api/v1/inventory/${ASSET_CONFIG.library}/${ASSET_CONFIG.symbol}/data?label=${ASSET_CONFIG.label}&page=${page}&size=${PAGE_SIZE}&reverse=true`);
        const data = await response.json();

        if (data.rows && data.rows.length > 0) {
            console.log(`Received ${data.rows.length} rows for the grid.`);
            // Build Header (Dynamic based on first row)
            const columns = Object.keys(data.rows[0]);
            tableHead.innerHTML = columns.map(col => `<th>${col}</th>`).join('');

            // Build Rows
            tableBody.innerHTML = data.rows.map(row => {
                return `<tr>${columns.map(col => `<td>${formatValue(row[col])}</td>`).join('')}</tr>`;
            }).join('');

            // Update Pagination
            pageInfo.innerText = `Page ${page} of ${data.total_pages}`;
            prevBtn.disabled = (page === 1);
            nextBtn.disabled = (page >= data.total_pages);
        } else {
            console.warn("Data API returned no rows.");
            tableBody.innerHTML = '<tr><td colspan="100%" class="loading-cell">No rows found in this asset.</td></tr>';
            nextBtn.disabled = true;
        }
    } catch (error) {
        console.error("Failed to fetch data:", error);
        tableBody.innerHTML = '<tr><td colspan="100%" class="loading-cell" style="color: var(--danger)">Error loading data from ClickHouse. Check console for details.</td></tr>';
    }
}

/**
 * Formats cell values for display
 */
function formatValue(val) {
    if (val === null || val === undefined) return '<span style="color: #ccc">null</span>';
    if (typeof val === 'number') {
        if (Number.isInteger(val)) return val.toLocaleString();
        return val.toFixed(4);
    }
    if (typeof val === 'object') {
        return '<pre style="max-height: 200px; overflow: auto; margin: 0;">' + JSON.stringify(val, null, 2) + '</pre>';
    }
    if (typeof val === 'string' && (val.startsWith('{') || val.startsWith('['))) {
        try {
            const parsed = JSON.parse(val);
            return '<pre style="max-height: 200px; overflow: auto; margin: 0;">' + JSON.stringify(parsed, null, 2) + '</pre>';
        } catch (e) {
            return val;
        }
    }
    return val;
}

/**
 * Handles Asset Deletion
 */
async function handleDelete() {
    const confirmed = confirm(`Are you sure you want to PERMANENTLY DELETE ${ASSET_CONFIG.symbol} from ${ASSET_CONFIG.library}?\n\nThis action cannot be undone.`);
    if (!confirmed) return;

    try {
        const response = await fetch(`/api/v1/inventory/${ASSET_CONFIG.library}/${ASSET_CONFIG.symbol}?label=${ASSET_CONFIG.label}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            alert("Asset deleted successfully.");
            window.location.href = "/inventory/dashboard";
        } else {
            const err = await response.json();
            alert("Failed to delete asset: " + (err.detail || "Unknown error"));
        }
    } catch (error) {
        console.error("Delete failed:", error);
        alert("Network error while deleting asset.");
    }
}
