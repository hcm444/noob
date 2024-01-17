CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_number INTEGER,
    timestamp DATETIME,
    message TEXT,
    parent_post_number INTEGER
);
