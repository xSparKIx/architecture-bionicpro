CREATE TABLE telemetry (
    session_id VARCHAR(100),
    user_id VARCHAR(50),
    duration_seconds INT,
    response_time_ms INT,
    event_time TIMESTAMP
);

-- (Опционально) тестовые данные
INSERT INTO telemetry (session_id, user_id, duration_seconds, response_time_ms, event_time) VALUES 
('sess1', 'user1@bionicpro.com', 120, 85, NOW());