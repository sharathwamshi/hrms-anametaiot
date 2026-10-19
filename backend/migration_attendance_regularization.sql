-- AnametaIOT HRMS -- safe, re-runnable migration (NO data is deleted or reset)
-- Import via phpMyAdmin: select the anametaiot_hrms database -> Import -> choose this file.
-- Adds: manager-defined regularization reasons, the self-service regularization
-- workflow on attendance, and the org holiday calendar.

USE anametaiot_hrms;

-- New tables (safe if already present)
CREATE TABLE IF NOT EXISTS attendance_regularization_reasons (
    id INTEGER NOT NULL AUTO_INCREMENT,
    label VARCHAR(100) NOT NULL,
    description VARCHAR(255),
    is_active BOOL DEFAULT 1,
    created_by INTEGER,
    created_at DATETIME,
    PRIMARY KEY (id),
    UNIQUE (label),
    FOREIGN KEY(created_by) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS holidays (
    id INTEGER NOT NULL AUTO_INCREMENT,
    name VARCHAR(150) NOT NULL,
    holiday_date DATE NOT NULL,
    description VARCHAR(255),
    created_by INTEGER,
    created_at DATETIME,
    PRIMARY KEY (id),
    UNIQUE (holiday_date),
    FOREIGN KEY(created_by) REFERENCES users (id)
) ENGINE=InnoDB;

-- attendance.regularization_status
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `attendance` ADD COLUMN `regularization_status` VARCHAR(20) NULL', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance' AND COLUMN_NAME = 'regularization_status');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- attendance.regularization_reason_id
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `attendance` ADD COLUMN `regularization_reason_id` INT NULL', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance' AND COLUMN_NAME = 'regularization_reason_id');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- attendance.regularization_note
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `attendance` ADD COLUMN `regularization_note` VARCHAR(255) NULL', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance' AND COLUMN_NAME = 'regularization_note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;



-- attendance.regularization_requested_at
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `attendance` ADD COLUMN `regularization_requested_at` DATETIME NULL', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance' AND COLUMN_NAME = 'regularization_requested_at');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- attendance.regularization_reviewed_by
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `attendance` ADD COLUMN `regularization_reviewed_by` INT NULL', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance' AND COLUMN_NAME = 'regularization_reviewed_by');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- attendance.regularization_reviewed_at
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `attendance` ADD COLUMN `regularization_reviewed_at` DATETIME NULL', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance' AND COLUMN_NAME = 'regularization_reviewed_at');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- attendance.regularization_review_comment
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `attendance` ADD COLUMN `regularization_review_comment` VARCHAR(255) NULL', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance' AND COLUMN_NAME = 'regularization_review_comment');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- foreign key fk_attendance_regularization_reason
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `attendance` ADD CONSTRAINT `fk_attendance_regularization_reason` FOREIGN KEY (`regularization_reason_id`) REFERENCES `attendance_regularization_reasons` (`id`)', 'SELECT 1')
  FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance' AND CONSTRAINT_NAME = 'fk_attendance_regularization_reason');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- foreign key fk_attendance_reviewed_by
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `attendance` ADD CONSTRAINT `fk_attendance_reviewed_by` FOREIGN KEY (`regularization_reviewed_by`) REFERENCES `users` (`id`)', 'SELECT 1')
  FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance' AND CONSTRAINT_NAME = 'fk_attendance_reviewed_by');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Track every submission so rejected requests and re-submissions count toward
-- the monthly limit. Existing submissions in the current month are backfilled.
CREATE TABLE IF NOT EXISTS attendance_regularization_requests (
    id INTEGER NOT NULL AUTO_INCREMENT,
    user_id INTEGER NOT NULL,
    attendance_id INTEGER NOT NULL,
    submitted_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    INDEX ix_regularization_request_user_submitted (user_id, submitted_at),
    FOREIGN KEY (user_id) REFERENCES users (id),
    FOREIGN KEY (attendance_id) REFERENCES attendance (id)
) ENGINE=InnoDB;

INSERT INTO attendance_regularization_requests (user_id, attendance_id, submitted_at)
SELECT a.user_id, a.id, a.regularization_requested_at
FROM attendance a
WHERE a.regularization_requested_at >= DATE_FORMAT(CURRENT_DATE(), '%Y-%m-01')
  AND a.regularization_requested_at < DATE_ADD(DATE_FORMAT(CURRENT_DATE(), '%Y-%m-01'), INTERVAL 1 MONTH)
  AND NOT EXISTS (
      SELECT 1 FROM attendance_regularization_requests r
      WHERE r.attendance_id = a.id AND r.submitted_at = a.regularization_requested_at
  );
