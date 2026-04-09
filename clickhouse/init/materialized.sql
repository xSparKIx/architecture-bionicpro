CREATE MATERIALIZED VIEW crm_mv TO crm_target AS
SELECT
    JSONExtractString(payload, 'after', 'user_id') AS user_id,
    JSONExtractString(payload, 'after', 'username') AS username,
    JSONExtractString(payload, 'after', 'full_name') AS full_name,
    JSONExtractString(payload, 'after', 'email') AS email,
    JSONExtractString(payload, 'after', 'prosthetic_id') AS prosthetic_id,
    JSONExtractInt(payload, 'ts_ms') AS version,
    JSONExtractString(payload, 'op') = 'd' AS deleted
FROM crm_kafka_queue
WHERE JSONExtractString(payload, 'op') IN ('c', 'u', 'd', 'r');