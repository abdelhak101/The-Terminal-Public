from shared.clickhouse import ClickHouseStorage

storage = ClickHouseStorage()
storage.execute("DROP TABLE IF EXISTS bronze_raw")
storage.init_schema()
print("Dropped and recreated bronze_raw!")
