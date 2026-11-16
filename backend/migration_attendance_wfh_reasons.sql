SET @sql = (SELECT IF(COUNT(*) = 0,
    'ALTER TABLE `company_settings` ADD COLUMN `wfh_reasons_enabled` BOOLEAN NOT NULL DEFAULT FALSE',
    'SELECT 1')
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'company_settings'
      AND COLUMN_NAME = 'wfh_reasons_enabled');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (SELECT IF(COUNT(*) = 0,
    'ALTER TABLE `attendance_work_locations` ADD COLUMN `is_wfh` BOOLEAN NOT NULL DEFAULT FALSE',
    'SELECT 1')
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance_work_locations'
      AND COLUMN_NAME = 'is_wfh');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

UPDATE attendance_work_locations
SET is_wfh = TRUE
WHERE LOWER(TRIM(name)) IN ('wfh', 'work from home');

SET @sql = (SELECT IF(COUNT(*) = 0,
    'ALTER TABLE `attendance_sessions` ADD COLUMN `wfh_reason` VARCHAR(100) NULL',
    'SELECT 1')
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance_sessions'
      AND COLUMN_NAME = 'wfh_reason');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (SELECT IF(COUNT(*) = 0,
    'ALTER TABLE `attendance_sessions` ADD COLUMN `wfh_reason_explanation` VARCHAR(255) NULL',
    'SELECT 1')
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance_sessions'
      AND COLUMN_NAME = 'wfh_reason_explanation');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

CREATE TABLE IF NOT EXISTS attendance_wfh_reasons (
    id INT NOT NULL AUTO_INCREMENT,
    label VARCHAR(100) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by INT NULL,
    created_at DATETIME NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_attendance_wfh_reason_label UNIQUE (label),
    CONSTRAINT fk_attendance_wfh_reason_created_by
        FOREIGN KEY (created_by) REFERENCES users (id)
) ENGINE=InnoDB;

SET @sql = (SELECT IF(COUNT(*) = 0,
    'ALTER TABLE `attendance_wfh_reasons` ADD COLUMN `label` VARCHAR(100) NULL',
    'SELECT 1')
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance_wfh_reasons'
      AND COLUMN_NAME = 'label');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (SELECT IF(COUNT(*) = 0,
    'ALTER TABLE `attendance_wfh_reasons` ADD COLUMN `is_active` BOOLEAN NOT NULL DEFAULT TRUE',
    'SELECT 1')
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance_wfh_reasons'
      AND COLUMN_NAME = 'is_active');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (SELECT IF(COUNT(*) = 0,
    'ALTER TABLE `attendance_wfh_reasons` ADD COLUMN `created_by` INT NULL',
    'SELECT 1')
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance_wfh_reasons'
      AND COLUMN_NAME = 'created_by');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (SELECT IF(COUNT(*) = 0,
    'ALTER TABLE `attendance_wfh_reasons` ADD COLUMN `created_at` DATETIME NULL',
    'SELECT 1')
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance_wfh_reasons'
      AND COLUMN_NAME = 'created_at');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (SELECT IF(COUNT(*) > 0,
    'ALTER TABLE `attendance_wfh_reasons` MODIFY COLUMN `name` VARCHAR(100) NULL',
    'SELECT 1')
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance_wfh_reasons'
      AND COLUMN_NAME = 'name');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

UPDATE attendance_wfh_reasons
SET label = CONCAT('WFH reason ', id)
WHERE label IS NULL OR TRIM(label) = '';

ALTER TABLE attendance_wfh_reasons
    MODIFY COLUMN label VARCHAR(100) NOT NULL;
