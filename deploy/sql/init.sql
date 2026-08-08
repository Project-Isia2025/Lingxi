-- 爆款商品记录
CREATE TABLE IF NOT EXISTS hot_products (
    id SERIAL PRIMARY KEY,
    platform VARCHAR(32) NOT NULL,
    product_name VARCHAR(256) NOT NULL,
    product_url TEXT,
    price DECIMAL(10, 2),
    sales_count INTEGER,
    trend_score FLOAT,
    first_seen TIMESTAMP DEFAULT NOW(),
    last_updated TIMESTAMP DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- 投放记录
CREATE TABLE IF NOT EXISTS ad_campaigns (
    id SERIAL PRIMARY KEY,
    platform VARCHAR(32) NOT NULL,
    product_id INTEGER REFERENCES hot_products(id),
    video_url TEXT,
    daily_budget DECIMAL(10, 2),
    bid_cpc DECIMAL(10, 2),
    impressions INTEGER DEFAULT 0,
    clicks INTEGER DEFAULT 0,
    conversions INTEGER DEFAULT 0,
    spend DECIMAL(10, 2) DEFAULT 0,
    revenue DECIMAL(10, 2) DEFAULT 0,
    roi FLOAT GENERATED ALWAYS AS (
        CASE WHEN spend > 0 THEN revenue / spend ELSE 0 END
    ) STORED,
    status VARCHAR(32) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Agent 决策日志
CREATE TABLE IF NOT EXISTS agent_decisions (
    id SERIAL PRIMARY KEY,
    agent_name VARCHAR(64) NOT NULL,
    decision_type VARCHAR(64) NOT NULL,
    input_data JSONB,
    output_data JSONB,
    confidence FLOAT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 话术 SOP
CREATE TABLE IF NOT EXISTS sop_documents (
    id SERIAL PRIMARY KEY,
    category VARCHAR(64) NOT NULL,
    title VARCHAR(256) NOT NULL,
    content TEXT NOT NULL,
    tags JSONB DEFAULT '[]',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
