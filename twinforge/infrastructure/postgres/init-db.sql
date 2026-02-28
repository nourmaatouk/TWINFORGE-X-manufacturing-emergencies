-- Initialize TWINFORGE databases
CREATE DATABASE twinforge;
CREATE DATABASE twinforge_security;

\c twinforge;

CREATE TABLE IF NOT EXISTS aas_registry (
    id SERIAL PRIMARY KEY,
    aas_id VARCHAR(255) UNIQUE NOT NULL,
    asset_name VARCHAR(255) NOT NULL,
    asset_type VARCHAR(100),
    submodels JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS knowledge_base (
    id SERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

\c twinforge_security;

CREATE TABLE IF NOT EXISTS security_events (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    source_agent VARCHAR(50),
    threat_type VARCHAR(50),
    severity VARCHAR(20),
    confidence FLOAT,
    details TEXT,
    payload JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
