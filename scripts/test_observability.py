import os
import requests
import time
import sys

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:29090")
GRAFANA_URL = os.getenv("GRAFANA_URL", "http://localhost:23000")

def test_prometheus_targets():
    print("Checking Prometheus targets...")
    try:
        response = requests.get(f"{PROMETHEUS_URL}/api/v1/targets")
        response.raise_for_status()
        targets = response.json()['data']['activeTargets']
        
        required_jobs = ['postgres', 'terminal-observer', 'cadvisor']
        found_jobs = {}
        
        for t in targets:
            job = t['labels']['job']
            if job in required_jobs:
                found_jobs[job] = t['health']
        
        for job in required_jobs:
            if job not in found_jobs:
                print(f"FAILED: Job '{job}' not found in Prometheus targets")
                return False
            if found_jobs[job] != 'up':
                print(f"FAILED: Job '{job}' is in health state: {found_jobs[job]}")
                return False
        
        print("SUCCESS: All required targets are UP")
        return True
    except Exception as e:
        print(f"ERROR: Could not connect to Prometheus: {e}")
        return False

def test_metrics_presence():
    print("Checking for critical metrics...")
    metrics_to_check = [
        'pg_up',
        'terminal_asset_storage_bytes',
        'terminal_asset_freshness_seconds',
        'container_cpu_usage_seconds_total',
        'terminal_inventory_scan_total',
        'terminal_registry_assets_count',
        'terminal_inventory_library_symbols_total',
        'terminal_clickhouse_compression_ratio',
        'terminal_clickhouse_oldest_record_days'
    ]
    
    all_present = True
    try:
        for metric in metrics_to_check:
            response = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={'query': metric})
            response.raise_for_status()
            data = response.json()['data']['result']
            if not data:
                print(f"FAILED: Metric '{metric}' is empty or not found")
                all_present = False
            else:
                print(f"SUCCESS: Metric '{metric}' is present")
        return all_present
    except Exception as e:
        print(f"ERROR: Could not query Prometheus: {e}")
        return False

def test_grafana_dashboards():
    print("Checking Grafana dashboards...")
    dashboards = [
        ("terminal-storage-health", "Terminal Storage Health"),
        ("mission-control", "Mission Control"),
        ("data-inventory", "Data Inventory")
    ]
    try:
        for uid, name in dashboards:
            response = requests.get(f"{GRAFANA_URL}/api/dashboards/uid/{uid}")
            if response.status_code == 200:
                print(f"SUCCESS: Grafana dashboard '{name}' is provisioned")
            else:
                print(f"FAILED: Grafana dashboard '{name}' not found (Status: {response.status_code})")
                return False
        return True
    except Exception as e:
        print(f"ERROR: Could not connect to Grafana: {e}")
        return False

if __name__ == "__main__":
    print("=== Observability Pipeline Validation ===")
    
    success = True
    success &= test_prometheus_targets()
    success &= test_metrics_presence()
    success &= test_grafana_dashboards()
    
    if success:
        print("\nOVERALL STATUS: PASSED")
        sys.exit(0)
    else:
        print("\nOVERALL STATUS: FAILED")
        sys.exit(1)
