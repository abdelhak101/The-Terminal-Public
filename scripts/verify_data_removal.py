import requests
import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verify-removal")

BASE_URL = "http://localhost:23002/api/v1"

def test_inventory_listing():
    logger.info("Testing GET /inventory...")
    try:
        resp = requests.get(f"{BASE_URL}/inventory")
        resp.raise_for_status()
        inventory = resp.json()
        logger.info(f"Success! Found {len(inventory)} assets.")
        for item in inventory:
            if 'size_bytes' not in item:
                logger.error(f"Missing 'size_bytes' for {item['symbol']}")
            else:
                logger.info(f" - {item['symbol']} ({item['library']}): {item['row_count']} rows, {item['size_bytes']} bytes")
        return inventory
    except Exception as e:
        logger.error(f"Inventory test failed: {e}")
        return None

def test_delete_non_existent():
    logger.info("Testing DELETE of non-existent asset...")
    try:
        resp = requests.delete(f"{BASE_URL}/inventory/bronze/MISSING_STOCKS_123")
        if resp.status_code == 404:
            logger.info("Success: Received 404 for non-existent asset.")
            return True
        else:
            logger.error(f"Expected 404, got {resp.status_code}")
            return False
    except Exception as e:
        logger.error(f"Delete test failed: {e}")
        return False

if __name__ == "__main__":
    print("=== Data Removal Hub Verification ===")
    inv = test_inventory_listing()
    if inv is not None:
        test_delete_non_existent()
        print("=== Verification Complete ===")
    else:
        print("=== Verification FAILED (API unreachable) ===")
        sys.exit(1)
