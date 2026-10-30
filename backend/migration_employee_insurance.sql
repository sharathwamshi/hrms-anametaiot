-- Additive employee insurance management migration.
-- Safe to apply to an existing database: it creates only new tables.

CREATE TABLE IF NOT EXISTS insurance_policies (
    id INTEGER NOT NULL AUTO_INCREMENT,
    employee_id INTEGER NOT NULL,
    insurance_type VARCHAR(30) NOT NULL,
    provider_name VARCHAR(150) NOT NULL,
    policy_number VARCHAR(150) NOT NULL,
    member_id VARCHAR(150),
    certificate_number VARCHAR(150),
    credentials JSON,
    coverage_amount DECIMAL(14,2),
    coverage_description TEXT,
    policy_start_date DATE NOT NULL,
    policy_expiry_date DATE NOT NULL,
    notes TEXT,
    contact_name VARCHAR(150),
    contact_email VARCHAR(150),
    contact_phone VARCHAR(40),
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    renewed_from_id INTEGER,
    created_by INTEGER NOT NULL,
    updated_by INTEGER NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    INDEX ix_insurance_policies_employee_id (employee_id),
    FOREIGN KEY (employee_id) REFERENCES users (id),
    FOREIGN KEY (renewed_from_id) REFERENCES insurance_policies (id),
    FOREIGN KEY (created_by) REFERENCES users (id),
    FOREIGN KEY (updated_by) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS insurance_type_settings (
    id INTEGER NOT NULL AUTO_INCREMENT,
    available_types JSON NOT NULL,
    updated_by INTEGER,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (updated_by) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS insurance_documents (
    id INTEGER NOT NULL AUTO_INCREMENT,
    policy_id INTEGER NOT NULL,
    document_type VARCHAR(40) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    storage_key VARCHAR(255) NOT NULL,
    mime_type VARCHAR(120) NOT NULL,
    file_size INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    uploaded_by INTEGER NOT NULL,
    uploaded_at DATETIME NOT NULL,
    archived_at DATETIME,
    replaced_by_id INTEGER,
    PRIMARY KEY (id),
    UNIQUE (storage_key),
    INDEX ix_insurance_documents_policy_id (policy_id),
    FOREIGN KEY (policy_id) REFERENCES insurance_policies (id),
    FOREIGN KEY (uploaded_by) REFERENCES users (id),
    FOREIGN KEY (replaced_by_id) REFERENCES insurance_documents (id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS insurance_reminders (
    id INTEGER NOT NULL AUTO_INCREMENT,
    policy_id INTEGER NOT NULL,
    recipient_id INTEGER NOT NULL,
    reminder_date DATE NOT NULL,
    sent_at DATETIME,
    delivery_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    error_message VARCHAR(500),
    PRIMARY KEY (id),
    UNIQUE (policy_id, recipient_id, reminder_date),
    INDEX ix_insurance_reminders_policy_id (policy_id),
    FOREIGN KEY (policy_id) REFERENCES insurance_policies (id),
    FOREIGN KEY (recipient_id) REFERENCES users (id)
) ENGINE=InnoDB;
