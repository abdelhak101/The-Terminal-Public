import os
import logging
from shared.clickhouse import ClickHouseStorage

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("init-clickhouse")

def main():
    logger.info("Initializing ClickHouse Storage...")
    try:
        storage = ClickHouseStorage()
        if not storage.check_health():
            logger.error("ClickHouse is not reachable. Ensure the service is running.")
            return
            
        storage.init_schema()
        logger.info("✨ ClickHouse initialization complete!")
    except Exception as e:
        logger.error(f"Failed to initialize ClickHouse: {e}")

if __name__ == "__main__":
    main()
