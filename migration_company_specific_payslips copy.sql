-- Company-specific payroll migration. Back up the database before applying.
-- This file is intentionally not run by the application.
ALTER TABLE users
    ADD COLUMN company_name VARCHAR(150) NOT NULL
    DEFAULT 'Acknowledger First Pvt Ltd';

UPDATE users
SET company_name = 'Acknowledger First Pvt Ltd'
WHERE company_name IS NULL OR company_name = '';

ALTER TABLE payslips
    ADD COLUMN company_name VARCHAR(150) NULL,
    ADD COLUMN employee_info JSON NULL,
    ADD COLUMN earnings JSON NULL,
    ADD COLUMN deductions JSON NULL,
    ADD COLUMN total_working_days FLOAT NULL,
    ADD COLUMN total_paid_days FLOAT NULL,
    ADD COLUMN updated_by INTEGER NULL,
    ADD COLUMN updated_at DATETIME NULL,
    ADD COLUMN published_by INTEGER NULL,
    ADD COLUMN published_at DATETIME NULL,
    ADD COLUMN pdf_is_uploaded BOOLEAN NOT NULL DEFAULT 0,
    ADD COLUMN pdf_filename VARCHAR(255) NULL,
    ADD CONSTRAINT fk_payslips_updated_by_users
        FOREIGN KEY (updated_by) REFERENCES users (id),
    ADD CONSTRAINT fk_payslips_published_by_users
        FOREIGN KEY (published_by) REFERENCES users (id);

UPDATE payslips AS p
JOIN users AS u ON u.id = p.user_id
SET p.company_name = u.company_name
WHERE p.company_name IS NULL;
