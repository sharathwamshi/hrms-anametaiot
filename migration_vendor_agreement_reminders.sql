CREATE TABLE IF NOT EXISTS vendor_agreement_reminders (
    id INTEGER NOT NULL AUTO_INCREMENT,
    agreement_id INTEGER NOT NULL,
    reminder_type VARCHAR(40) NOT NULL,
    expiry_date DATE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    attempted_at DATETIME,
    sent_at DATETIME,
    error_message VARCHAR(255),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT uq_vendor_agreement_reminder UNIQUE (agreement_id, reminder_type, expiry_date),
    INDEX ix_vendor_agreement_reminder_status (status, expiry_date),
    FOREIGN KEY (agreement_id) REFERENCES vendor_agreements (id) ON DELETE CASCADE
) ENGINE=InnoDB;
