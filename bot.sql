CREATE TABLE IF NOT EXISTS ec2 (
  name TEXT PRIMARY KEY NOT NULL,
  state TEXT,
  soft_check_count INTEGER DEFAULT 0,
  notification_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
  last_toggled_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
  active INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS chat (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  role TEXT,
  content TEXT
);
