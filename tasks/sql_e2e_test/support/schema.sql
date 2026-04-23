CREATE TABLE IF NOT EXISTS rules (
  rule_id TEXT PRIMARY KEY,
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS instructors (
  instructor_id TEXT PRIMARY KEY,
  full_name TEXT NOT NULL
);
