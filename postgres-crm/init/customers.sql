CREATE TABLE customers (
    user_id VARCHAR(50) PRIMARY KEY,
    username VARCHAR(100),
    full_name VARCHAR(200),
    email VARCHAR(200),
    prosthetic_id VARCHAR(50),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Создаем публикацию для Debezium
CREATE PUBLICATION debezium_pub FOR TABLE customers;

-- Добавляем тестовые данные в customers
INSERT INTO customers (user_id, username, full_name, email, prosthetic_id) 
VALUES ('user1', 'user1', 'User One', 'user1@example.com', 'PRO-001');