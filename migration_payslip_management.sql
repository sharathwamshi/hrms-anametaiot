-- Safe, additive payroll management migration. Apply once to an existing MySQL database.
-- Company templates, employee payroll details, payslip revisions, and audit history
-- are not created or changed by the application at startup.

SET @sql = (SELECT IF(COUNT(*) = 0,
    'ALTER TABLE users ADD COLUMN employee_category VARCHAR(20) NULL',
    'SELECT 1')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'employee_category');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (SELECT IF(COUNT(*) = 0,
    'ALTER TABLE users ADD COLUMN pan VARCHAR(20) NULL',
    'SELECT 1')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'pan');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (SELECT IF(COUNT(*) = 0,
    'ALTER TABLE users ADD COLUMN pf_number VARCHAR(50) NULL',
    'SELECT 1')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'pf_number');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (SELECT IF(COUNT(*) = 0,
    'ALTER TABLE users ADD COLUMN bank_name VARCHAR(120) NULL',
    'SELECT 1')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'bank_name');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (SELECT IF(COUNT(*) = 0,
    'ALTER TABLE users ADD COLUMN bank_account_name VARCHAR(150) NULL',
    'SELECT 1')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'bank_account_name');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (SELECT IF(COUNT(*) = 0,
    'ALTER TABLE users ADD COLUMN bank_account_number VARCHAR(40) NULL',
    'SELECT 1')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'bank_account_number');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (SELECT IF(COUNT(*) = 0,
    'ALTER TABLE users ADD COLUMN pay_mode VARCHAR(30) NULL',
    'SELECT 1')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'pay_mode');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (SELECT IF(COUNT(*) = 0,
    'ALTER TABLE users ADD COLUMN location VARCHAR(120) NULL',
    'SELECT 1')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'location');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (SELECT IF(
    (SELECT COUNT(*) FROM information_schema.TABLES
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'salary_templates') = 1
    AND
    (SELECT COUNT(*) FROM information_schema.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'salary_templates' AND COLUMN_NAME = 'employer_pf_flat') = 0,
    'ALTER TABLE salary_templates ADD COLUMN employer_pf_flat FLOAT NOT NULL DEFAULT 0',
    'SELECT 1'));
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (SELECT IF(COUNT(*) = 0,
    'ALTER TABLE salary_structures ADD COLUMN custom_earnings JSON NULL',
    'SELECT 1')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'salary_structures' AND COLUMN_NAME = 'custom_earnings');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (SELECT IF(COUNT(*) = 0,
    'ALTER TABLE salary_structures ADD COLUMN custom_deductions JSON NULL',
    'SELECT 1')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'salary_structures' AND COLUMN_NAME = 'custom_deductions');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (SELECT IF(COUNT(*) = 0,
    'ALTER TABLE payslips ADD COLUMN template_snapshot JSON NULL',
    'SELECT 1')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'payslips' AND COLUMN_NAME = 'template_snapshot');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

CREATE TABLE IF NOT EXISTS company_payslip_templates (
    id INTEGER NOT NULL AUTO_INCREMENT,
    company_name VARCHAR(150) NOT NULL,
    layout_key VARCHAR(40) NOT NULL,
    address TEXT NOT NULL,
    primary_color VARCHAR(7) NOT NULL,
    accent_color VARCHAR(7) NOT NULL,
    logo_path VARCHAR(255) NOT NULL,
    earnings_components JSON NOT NULL,
    deductions_components JSON NOT NULL,
    updated_by INTEGER NULL,
    updated_at DATETIME NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_company_payslip_template_company (company_name),
    CONSTRAINT fk_company_payslip_templates_updated_by
        FOREIGN KEY (updated_by) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS payslip_revisions (
    id INTEGER NOT NULL AUTO_INCREMENT,
    payslip_id INTEGER NOT NULL,
    revision INTEGER NOT NULL,
    action VARCHAR(30) NOT NULL,
    actor_id INTEGER NOT NULL,
    snapshot JSON NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_payslip_revision_number (payslip_id, revision),
    CONSTRAINT fk_payslip_revisions_payslip
        FOREIGN KEY (payslip_id) REFERENCES payslips (id) ON DELETE CASCADE,
    CONSTRAINT fk_payslip_revisions_actor
        FOREIGN KEY (actor_id) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS payroll_audit_logs (
    id INTEGER NOT NULL AUTO_INCREMENT,
    employee_id INTEGER NOT NULL,
    payslip_id INTEGER NULL,
    actor_id INTEGER NOT NULL,
    action VARCHAR(40) NOT NULL,
    previous_values JSON NULL,
    new_values JSON NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    KEY ix_payroll_audit_logs_employee_id (employee_id),
    KEY ix_payroll_audit_logs_payslip_id (payslip_id),
    CONSTRAINT fk_payroll_audit_logs_employee
        FOREIGN KEY (employee_id) REFERENCES users (id),
    CONSTRAINT fk_payroll_audit_logs_payslip
        FOREIGN KEY (payslip_id) REFERENCES payslips (id),
    CONSTRAINT fk_payroll_audit_logs_actor
        FOREIGN KEY (actor_id) REFERENCES users (id)
) ENGINE=InnoDB;

INSERT INTO company_payslip_templates
    (company_name, layout_key, address, primary_color, accent_color, logo_path,
     earnings_components, deductions_components)
VALUES
    ('Ana Meta IoT', 'ana_meta_iot',
     'WeWork Manyata Mahogany, Embassy Manyata Business Park, F2 Block, Nagavara, Bangalore - 560045',
     '#1A00B5', '#FF7618', 'assets/payslip_templates/ana_meta_iot.png',
     JSON_ARRAY('Basic Pay', 'House Rent Allowance', 'Conveyance Allowance', 'Personal Pay', 'Bonus'),
     JSON_ARRAY('Professional Tax', 'PF', 'Advance Salary', 'Other Deductions', 'GPA')),
    ('Acknowledger First Pvt Ltd', 'acknowledger_first',
     '# 53, 1st Main Road, Dollars Colony, RMV 2nd Stage, Sanjaynagar, Bangalore - 560 094.',
     '#16325C', '#00867F', 'assets/payslip_templates/acknowledger_first.png',
     JSON_ARRAY('Basic Pay', 'House Rent Allowance', 'Conveyance Allowance', 'Personal Pay', 'Bonus'),
     JSON_ARRAY('Professional Tax', 'PF', 'Advance Salary', 'Other Deductions', 'GPA')),
    ('Vkalpa Innovations', 'vkalpa_innovations',
     'UB CITY, REGUS LEVEL 15, CONCORD TOWER 1, VITTAL MALLYA ROAD, BANGALORE-560001',
     '#073568', '#F5C400', 'assets/payslip_templates/vkalpa_innovations.png',
     JSON_ARRAY('Basic Salary', 'HRA', 'Conveyance Allowance', 'Medical Allowance', 'Special Allowance', 'Performance Incentive'),
     JSON_ARRAY('Provident Fund (PF)', 'Employee State Insurance (ESI)', 'Professional Tax', 'Income Tax (TDS)', 'Other Deductions'))
ON DUPLICATE KEY UPDATE company_name = VALUES(company_name);
