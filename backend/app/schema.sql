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
    amap_poi_id TEXT,
    data_source TEXT,
    source_updated_at TEXT,
    UNIQUE(city_id, name)
);

-- 基础事实的来源留痕：保存结构化 POI 证据而不是整篇平台攻略正文。
-- 同一景点可有多个来源；同一来源标识重复采集时只刷新快照与时间。
CREATE TABLE IF NOT EXISTS spot_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spot_id INTEGER NOT NULL REFERENCES spots(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    external_id TEXT NOT NULL,
    source_url TEXT,
    payload_json TEXT,
    fetched_at TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.7,
    UNIQUE(spot_id, provider, external_id)
);

CREATE INDEX IF NOT EXISTS idx_spot_sources_spot ON spot_sources(spot_id, provider);
CREATE UNIQUE INDEX IF NOT EXISTS idx_spot_sources_external
    ON spot_sources(provider, external_id) WHERE external_id <> '';

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

-- 景点图片台账：只向前台发布 rights_status=verified 的媒体。
-- storage_path 可为本地 images/... 路径，或将来的 COS/CDN 地址；origin_url 保留权利追溯。
CREATE TABLE IF NOT EXISTS spot_media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spot_id INTEGER NOT NULL REFERENCES spots(id) ON DELETE CASCADE,
    storage_path TEXT NOT NULL,
    origin_url TEXT NOT NULL,
    provider TEXT NOT NULL,
    license_note TEXT,
    rights_status TEXT NOT NULL DEFAULT 'pending'
        CHECK(rights_status IN ('pending', 'verified', 'rejected')),
    captured_at TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(spot_id, storage_path)
);

CREATE INDEX IF NOT EXISTS idx_spot_media_public
    ON spot_media(spot_id, rights_status, created_at DESC);

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
