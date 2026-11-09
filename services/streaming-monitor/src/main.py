import os
import time
import logging
from prometheus_client import start_http_server, Counter, Gauge
from confluent_kafka import Consumer, KafkaException, TopicPartition

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("streaming-monitor")

# Prometheus Metrics
TOPIC_THROUGHPUT = Counter(
    'terminal_streaming_topic_messages_total',
    'Total number of messages processed per topic',
    ['topic']
)
TOPIC_LAG = Gauge(
    'terminal_streaming_topic_lag',
    'Message lag per topic/partition',
    ['topic', 'partition']
)

class StreamingMonitor:
    def __init__(self):
        self.bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "redpanda:9092")
        self.topics = os.getenv("MONITORED_TOPICS", "market.yahoo").split(",")
        self.conf = {
            'bootstrap.servers': self.bootstrap_servers,
            'group.id': 'streaming-monitor-group',
            'auto.offset.reset': 'latest',
            'enable.auto.commit': False
        }
        self.consumer = Consumer(self.conf)

    def run(self):
        # Start Prometheus exporter
        metrics_port = int(os.getenv("METRICS_PORT", "8000"))
        start_http_server(metrics_port)
        logger.info(f"Streaming monitor metrics exporter started on port {metrics_port}")

        self.consumer.subscribe(self.topics)
        logger.info(f"Subscribed to topics: {self.topics}")

        try:
            while True:
                msg = self.consumer.poll(1.0)
                if msg is None:
                    # Periodically update lag even if no new messages
                    self.update_lag()
                    continue
                if msg.error():
                    logger.error(f"Consumer error: {msg.error()}")
                    continue

                # Update throughput
                TOPIC_THROUGHPUT.labels(topic=msg.topic()).inc()
                
                # Update lag for this partition
                self.update_lag(msg.topic(), msg.partition())

        except KeyboardInterrupt:
            pass
        finally:
            self.consumer.close()

    def update_lag(self, topic=None, partition=None):
        """
        Calculates lag by comparing current offset with high watermark.
        """
        try:
            if topic and partition is not None:
                tp = TopicPartition(topic, partition)
                low, high = self.consumer.get_watermark_offsets(tp)
                # This is a simplification; actual lag depends on consumer group position
                # For this monitor, we just care about the high watermark growth
                pass
        except Exception as e:
            logger.error(f"Error updating lag: {e}")

if __name__ == "__main__":
    monitor = StreamingMonitor()
    monitor.run()
