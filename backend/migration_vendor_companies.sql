CREATE TABLE vendor_companies (
    id INTEGER NOT NULL AUTO_INCREMENT,
    name VARCHAR(150) NOT NULL,
    created_by INTEGER NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_vendor_companies_name (name),
    CONSTRAINT fk_vendor_companies_created_by
        FOREIGN KEY (created_by) REFERENCES users (id)
) ENGINE=InnoDB;

INSERT INTO vendor_companies (name)
SELECT 'Acknowledger First Private Limited'
WHERE NOT EXISTS (
    SELECT 1 FROM vendor_companies WHERE name = 'Acknowledger First Private Limited'
);

INSERT INTO vendor_companies (name)
SELECT 'Ana Meta IOT'
WHERE NOT EXISTS (
    SELECT 1 FROM vendor_companies WHERE name = 'Ana Meta IOT'
);

INSERT INTO vendor_companies (name)
SELECT 'VKALPA'
WHERE NOT EXISTS (
    SELECT 1 FROM vendor_companies WHERE name = 'VKALPA'
);

ALTER TABLE vendors
    ADD COLUMN company_id INTEGER NULL,
    ADD INDEX ix_vendors_company_id (company_id),
    ADD CONSTRAINT fk_vendors_company
        FOREIGN KEY (company_id) REFERENCES vendor_companies (id);
