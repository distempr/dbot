CREATE TABLE IF NOT EXISTS ec2 (
  id TEXT PRIMARY KEY NOT NULL,
  name TEXT,
  state TEXT,
  notification_time TEXT 
);

INSERT INTO ec2 (id, name) VALUES (
  'i-0407aa9c088765b25',
  'dev'
);