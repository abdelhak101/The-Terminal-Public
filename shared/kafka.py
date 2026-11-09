import json
import os
from confluent_kafka import Producer
import logging

class KafkaProducer:
    def __init__(self):
        self.bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        self.conf = {
            'bootstrap.servers': self.bootstrap_servers,
            'client.id': 'terminal-producer'
        }
        self.producer = Producer(self.conf)
        self.logger = logging.getLogger(__name__)

    def publish(self, topic: str, key: str, value: dict):
        try:
            self.producer.produce(
                topic,
                key=key,
                value=json.dumps(value).encode('utf-8'),
                callback=self._delivery_report
            )
            self.producer.poll(0)
        except Exception as e:
            self.logger.error(f"Failed to publish to Kafka: {str(e)}")

    def _delivery_report(self, err, msg):
        if err is not None:
            self.logger.error(f"Message delivery failed: {err}")
        else:
            self.logger.debug(f"Message delivered to {msg.topic()} [{msg.partition()}]")

    def flush(self):
        self.producer.flush()
