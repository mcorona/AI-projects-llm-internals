-- Synthetic inventory schema given to the model (trimmed to the columns the questions use).
CREATE TABLE suppliers (
    supplier_id    SERIAL PRIMARY KEY,
    name           TEXT NOT NULL,
    country        TEXT NOT NULL,          -- ISO 3166-1 alpha-2, e.g. 'CN', 'DE', 'US'
    lead_time_days INT NOT NULL
);

CREATE TABLE products (
    sku           TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    category      TEXT NOT NULL,           -- e.g. 'Tornilleria', 'Electrico', 'Hidraulico'
    unit_cost     NUMERIC(12,2) NOT NULL,
    reorder_point INT NOT NULL,
    critical      BOOLEAN NOT NULL DEFAULT FALSE,
    supplier_id   INT REFERENCES suppliers(supplier_id)
);

CREATE TABLE warehouses (
    warehouse_id  SERIAL PRIMARY KEY,
    name          TEXT NOT NULL,
    city          TEXT NOT NULL            -- 'Ciudad de Mexico', 'Guadalajara', 'Monterrey'
);

CREATE TABLE stock (
    sku           TEXT REFERENCES products(sku),
    warehouse_id  INT REFERENCES warehouses(warehouse_id),
    on_hand       INT NOT NULL,
    PRIMARY KEY (sku, warehouse_id)
);

CREATE TABLE sales_daily (
    sku           TEXT REFERENCES products(sku),
    day           DATE NOT NULL,
    units         INT NOT NULL,
    PRIMARY KEY (sku, day)
);

CREATE TABLE purchase_orders (
    po_id         SERIAL PRIMARY KEY,
    sku           TEXT REFERENCES products(sku),
    qty           INT NOT NULL,
    status        TEXT NOT NULL            -- 'PENDING_APPROVAL', 'APPROVED', 'REJECTED'
);
