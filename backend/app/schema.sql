PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS cities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    province TEXT NOT NULL,
    lng REAL,
    lat REAL
);

CREATE TABLE IF NOT EXISTS spots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    city_id INTEGER NOT NULL REFERENCES cities(id),
    name TEXT NOT NULL,
    poi_rating REAL,
    address TEXT,
    tags TEXT,
    lng REAL,
    lat REAL,
    grade TEXT,
    price REAL,
    commercial TEXT,
    UNIQUE(city_id, name)
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spot_id INTEGER NOT NULL REFERENCES spots(id),
    title TEXT,
    content TEXT,
    author_hash TEXT,
    images_json TEXT,
    note_type TEXT CHECK(note_type IN ('guide', 'avoid', 'mixed')),
    source_url TEXT,
    fetched_at TEXT,
    is_sample INTEGER DEFAULT 0
);

-- 采集去重:同一来源链接只入库一次
CREATE UNIQUE INDEX IF NOT EXISTS idx_notes_source ON notes(source_url);

CREATE TABLE IF NOT EXISTS spot_summaries (
    spot_id INTEGER PRIMARY KEY REFERENCES spots(id),
    summary_json TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS cart_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spot_id INTEGER NOT NULL REFERENCES spots(id),
    added_at TEXT,
    UNIQUE(spot_id)
);

CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_json TEXT,
    created_at TEXT
);

-- 高门票景点的"平替"推荐(含缺点说明)
CREATE TABLE IF NOT EXISTS spot_alternatives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spot_id INTEGER NOT NULL REFERENCES spots(id),
    alt_spot_id INTEGER NOT NULL REFERENCES spots(id),
    price_note TEXT,
    note TEXT,
    downsides_json TEXT,
    UNIQUE(spot_id, alt_spot_id)
);

-- 住宿推荐(区域级,不点名具体商家以杜绝暗广)
CREATE TABLE IF NOT EXISTS stays (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    town TEXT NOT NULL,
    city TEXT NOT NULL,
    lng REAL,
    lat REAL,
    price_low REAL,
    price_high REAL,
    note TEXT,
    serve TEXT,
    UNIQUE(town, city)
);

-- 城市美食(必吃小吃 + 美食街;区域级,不点名具体餐馆/品牌防暗广)
CREATE TABLE IF NOT EXISTS city_foods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    city TEXT NOT NULL,
    kind TEXT CHECK(kind IN ('dish', 'street')),
    name TEXT NOT NULL,
    where_hint TEXT,
    price_low REAL,
    price_high REAL,
    note TEXT,
    lng REAL,
    lat REAL,
    UNIQUE(city, kind, name)
);
