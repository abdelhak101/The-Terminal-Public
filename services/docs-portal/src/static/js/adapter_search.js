document.addEventListener('DOMContentLoaded', init);

let currentAdapter = null;
let currentResult = null;

// Official site URLs per adapter type — (identifier, metadata) => url
const ADAPTER_URLS = {
    fred: (id) => `https://fred.stlouisfed.org/series/${id}`,
    yahoo: (id) => `https://finance.yahoo.com/quote/${id}`,
    bls: (id, meta) => `https://data.bls.gov/timeseries/${meta?.series_id || id}`,
    census: (id) => `https://data.census.gov/table?q=${encodeURIComponent(id)}`,
};
let currentSchema = null;

async function init() {
    await loadAdapters();
    setupEventListeners();
}

async function loadAdapters() {
    try {
        const res = await fetch('/api/v1/adapters/list');
        const data = await res.json();
        const select = document.getElementById('adapter-select');
        
        data.adapters
            .filter(a => a.supports_search)
            .forEach(adapter => {
                const option = document.createElement('option');
                option.value = adapter.name;
                option.textContent = adapter.label;
                select.appendChild(option);
            });
    } catch (e) {
        console.error('Failed to load adapters:', e);
    }
}

function setupEventListeners() {
    document.getElementById('search-btn').addEventListener('click', handleSearch);
    document.getElementById('search-input').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleSearch();
    });
    document.getElementById('generate-btn').addEventListener('click', generateConfig);
    document.getElementById('copy-btn').addEventListener('click', copyConfig);
}

async function handleSearch() {
    const query = document.getElementById('search-input').value.trim();
    if (!query) return;

    const adapterType = document.getElementById('adapter-select').value;
    const errorsDiv = document.getElementById('search-errors');
    const resultsSection = document.getElementById('results-section');
    
    errorsDiv.innerHTML = '';
    resultsSection.classList.add('hidden');
    
    try {
        const res = await fetch('/api/v1/adapters/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, adapter_type: adapterType })
        });
        
        const data = await res.json();
        
        if (data.errors.length > 0) {
            errorsDiv.innerHTML = data.errors.map(e => `<p class="error">${e}</p>`).join('');
        }
        
        renderResults(data.results);
    } catch (e) {
        console.error('Search failed:', e);
        errorsDiv.innerHTML = `<p class="error">Search failed: ${e.message}</p>`;
    }
}

function renderResults(results) {
    const container = document.getElementById('results-container');
    const section = document.getElementById('results-section');
    
    if (results.length === 0) {
        container.innerHTML = '<p>No results found.</p>';
    } else {
        container.innerHTML = results.map(res => {
            const urlFn = ADAPTER_URLS[res.adapter_type];
            const url = urlFn ? urlFn(res.identifier, res.metadata) : null;
            const linkBtn = url
                ? `<a href="${url}" target="_blank" rel="noopener noreferrer" class="btn btn-source" onclick="event.stopPropagation()" title="Open official source">↗ Source</a>`
                : '';
            return `
            <div class="result-item" data-adapter="${res.adapter_type}" data-result='${JSON.stringify(res)}'>
                <div class="result-header">
                    <span class="result-label">${res.label}</span>
                    <div class="result-header-actions">
                        ${linkBtn}
                        <span class="result-adapter">${res.adapter_type}</span>
                    </div>
                </div>
                <p class="result-description">${res.description}</p>
            </div>`;
        }).join('');
        
        container.querySelectorAll('.result-item').forEach(item => {
            item.addEventListener('click', () => selectResult(item));
        });
    }
    
    section.classList.remove('hidden');
}

async function selectResult(item) {
    currentAdapter = item.dataset.adapter;
    currentResult = JSON.parse(item.dataset.result);
    
    document.querySelectorAll('.result-item').forEach(el => el.classList.remove('selected'));
    item.classList.add('selected');
    
    await loadSchema();
    renderConfigForm();
}

async function loadSchema() {
    try {
        const res = await fetch(`/api/v1/adapters/${currentAdapter}/schema`);
        const data = await res.json();
        currentSchema = data.schema;
    } catch (e) {
        console.error('Failed to load schema:', e);
    }
}

function renderConfigForm() {
    const formDiv = document.getElementById('config-form');
    const configSection = document.getElementById('config-section');
    
    formDiv.innerHTML = '';
    configSection.classList.remove('hidden');
    
    const identifierField = document.createElement('div');
    identifierField.className = 'form-group';
    identifierField.innerHTML = `
        <label>Identifier:</label>
        <input type="text" name="identifier" value="${currentResult.identifier}" readonly>
    `;
    formDiv.appendChild(identifierField);
    
    const labelField = document.createElement('div');
    labelField.className = 'form-group';
    labelField.innerHTML = `
        <label>Label:</label>
        <input type="text" name="label" value="${currentResult.label}">
    `;
    formDiv.appendChild(labelField);
    
    currentSchema.properties.forEach(prop => {
        const field = document.createElement('div');
        field.className = 'form-group';
        
        const label = document.createElement('label');
        label.textContent = `${prop.name}${prop.required ? ' *' : ''}:`;
        field.appendChild(label);
        
        let input;
        if (prop.type === 'select') {
            input = document.createElement('select');
            input.name = prop.name;
            prop.options.forEach(opt => {
                const option = document.createElement('option');
                option.value = opt;
                option.textContent = opt;
                if (opt === prop.default) option.selected = true;
                input.appendChild(option);
            });
        } else if (prop.type === 'bool') {
            input = document.createElement('input');
            input.type = 'checkbox';
            input.name = prop.name;
            input.checked = !!prop.default;
        } else {
            input = document.createElement('input');
            input.type = 'text';
            input.name = prop.name;
            input.value = prop.default || '';
        }
        field.appendChild(input);
        
        if (prop.description) {
            const hint = document.createElement('p');
            hint.className = 'field-hint';
            hint.textContent = prop.description;
            field.appendChild(hint);
        }
        
        formDiv.appendChild(field);
    });
}

function generateConfig() {
    const form = document.getElementById('config-form');
    const inputs = form.querySelectorAll('input, select');
    const config = {
        adapter_type: currentAdapter,
        identifier: currentResult.identifier,
        label: '',
        config: {}
    };
    
    inputs.forEach(input => {
        if (input.name === 'label') {
            config.label = input.value;
        } else if (input.name === 'identifier') {
            // already set
        } else {
            if (input.type === 'checkbox') {
                config.config[input.name] = input.checked;
            } else {
                config.config[input.name] = input.value;
            }
        }
    });
    
    const yaml = generateYAML(config);
    document.getElementById('config-code').textContent = yaml;
    document.getElementById('config-output').classList.remove('hidden');
}

function generateYAML(config) {
    let yaml = `ops:
  register_source_op:
    config:
      adapter_type: "${config.adapter_type}"
      identifier: "${config.identifier}"
      label: "${config.label}"`;
    
    if (Object.keys(config.config).length > 0) {
        yaml += `
      config:`;
        for (const [key, value] of Object.entries(config.config)) {
            if (typeof value === 'boolean' || typeof value === 'number') {
                yaml += `
        ${key}: ${value}`;
            } else {
                yaml += `
        ${key}: "${value}"`;
            }
        }
    }
    
    return yaml;
}

function copyConfig() {
    const code = document.getElementById('config-code').textContent;
    navigator.clipboard.writeText(code).then(() => {
        const btn = document.getElementById('copy-btn');
        const originalText = btn.textContent;
        btn.textContent = 'Copied!';
        setTimeout(() => btn.textContent = originalText, 2000);
    });
}