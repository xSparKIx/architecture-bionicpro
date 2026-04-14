CREATE TABLE crm_target (
    user_id String,
    username String,
    full_name String,
    email String,
    prosthetic_id String,
    version UInt64,
    deleted UInt8 DEFAULT 0
) ENGINE = ReplacingMergeTree(version)
ORDER BY (user_id, version);

-- INSERT INTO crm_target (user_id, username, full_name, email, prosthetic_id) 
-- VALUES ('user1@bionicpro.com', 'user1', 'User One', 'user1@example.com', 'PRO-001');