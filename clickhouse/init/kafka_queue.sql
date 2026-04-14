CREATE TABLE crm_kafka_queue (
    payload String
) ENGINE = Kafka()
SETTINGS kafka_broker_list = 'kafka:9092',
         kafka_topic_list = 'crm.public.customers',
         kafka_group_name = 'clickhouse_consumer_group',
         kafka_format = 'JSONAsString';