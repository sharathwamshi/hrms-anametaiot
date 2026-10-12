-- AnametaIOT HRMS -- ATTENDANCE: one safe, re-runnable migration (NO data is deleted or reset)
-- Import via phpMyAdmin: select the anametaiot_hrms database -> Import -> choose this file.
-- Every statement checks first, so it is safe to run more than once, and safe whether
-- or not any earlier attendance migration was applied.
--
-- Covers the whole attendance flow:
--   * regularization workflow (reasons table, request/approve/reject columns)
--   * holiday calendar
--   * mobile app: push device tokens, office geofences, soft-geofence columns
--   * selfie proof: per-punch selfie columns + the company-wide on/off policy (OFF by default)
--   * multiple check-in/check-out sessions per day (attendance_sessions), with the reason for each
--     re-check-in, plus a one-time backfill so every existing day becomes session #1 (nothing lost)
--   * manager/HR Ops direct corrections: who edited a day's times, when, and why (attendance.edited_*)

USE anametaiot_hrms;


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

CREATE TABLE IF NOT EXISTS device_tokens (
    id INTEGER NOT NULL AUTO_INCREMENT,
    user_id INTEGER NOT NULL,
    token VARCHAR(255) NOT NULL,
    platform VARCHAR(20),
    created_at DATETIME,
    last_seen_at DATETIME,
    PRIMARY KEY (id),
    CONSTRAINT uq_device_token UNIQUE (token),
    FOREIGN KEY(user_id) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS office_locations (
    id INTEGER NOT NULL AUTO_INCREMENT,
    name VARCHAR(150) NOT NULL,
    latitude FLOAT NOT NULL,
    longitude FLOAT NOT NULL,
    radius_meters INTEGER NOT NULL DEFAULT 200,
    is_active BOOL DEFAULT 1,
    created_by INTEGER,
    created_at DATETIME,
    PRIMARY KEY (id),
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

-- attendance.clock_in_lat
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `attendance` ADD COLUMN `clock_in_lat` FLOAT NULL', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance' AND COLUMN_NAME = 'clock_in_lat');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- attendance.clock_in_lng
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `attendance` ADD COLUMN `clock_in_lng` FLOAT NULL', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance' AND COLUMN_NAME = 'clock_in_lng');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- attendance.clock_in_within_geofence
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `attendance` ADD COLUMN `clock_in_within_geofence` BOOL NULL', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance' AND COLUMN_NAME = 'clock_in_within_geofence');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- attendance.clock_out_lat
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `attendance` ADD COLUMN `clock_out_lat` FLOAT NULL', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance' AND COLUMN_NAME = 'clock_out_lat');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- attendance.clock_out_lng
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `attendance` ADD COLUMN `clock_out_lng` FLOAT NULL', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance' AND COLUMN_NAME = 'clock_out_lng');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- attendance.clock_out_within_geofence
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `attendance` ADD COLUMN `clock_out_within_geofence` BOOL NULL', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance' AND COLUMN_NAME = 'clock_out_within_geofence');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- attendance.clock_in_selfie
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `attendance` ADD COLUMN `clock_in_selfie` VARCHAR(255) NULL', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance' AND COLUMN_NAME = 'clock_in_selfie');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- attendance.clock_out_selfie
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `attendance` ADD COLUMN `clock_out_selfie` VARCHAR(255) NULL', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance' AND COLUMN_NAME = 'clock_out_selfie');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- company_settings.selfie_required
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `company_settings` ADD COLUMN `selfie_required` BOOL NOT NULL DEFAULT 0', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'company_settings' AND COLUMN_NAME = 'selfie_required');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- foreign key fk_attendance_regularization_reason
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `attendance` ADD CONSTRAINT `fk_attendance_regularization_reason` FOREIGN KEY (`regularization_reason_id`) REFERENCES `attendance_regularization_reasons` (`id`)', 'SELECT 1')
  FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance' AND CONSTRAINT_NAME = 'fk_attendance_regularization_reason');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- foreign key fk_attendance_reviewed_by
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `attendance` ADD CONSTRAINT `fk_attendance_reviewed_by` FOREIGN KEY (`regularization_reviewed_by`) REFERENCES `users` (`id`)', 'SELECT 1')
  FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance' AND CONSTRAINT_NAME = 'fk_attendance_reviewed_by');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;


-- One row per check-in -> check-out stretch. The attendance row stays the day's summary.
CREATE TABLE IF NOT EXISTS attendance_sessions (
    id INTEGER NOT NULL AUTO_INCREMENT,
    attendance_id INTEGER NOT NULL,
    session_no INTEGER NOT NULL,
    clock_in DATETIME NOT NULL,
    clock_out DATETIME,
    clock_in_note VARCHAR(255),
    clock_out_note VARCHAR(255),
    clock_in_lat FLOAT,
    clock_in_lng FLOAT,
    clock_in_within_geofence BOOL,
    clock_out_lat FLOAT,
    clock_out_lng FLOAT,
    clock_out_within_geofence BOOL,
    clock_in_selfie VARCHAR(255),
    clock_out_selfie VARCHAR(255),
    reentry_reason VARCHAR(255),
    created_at DATETIME,
    PRIMARY KEY (id),
    CONSTRAINT uq_attendance_session_no UNIQUE (attendance_id, session_no),
    FOREIGN KEY(attendance_id) REFERENCES attendance (id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Backfill: every existing attendance day that has a check-in becomes session #1, so history,
-- reports and the new manager views include it. Safe to re-run (skips days already migrated).
INSERT INTO attendance_sessions
  (attendance_id, session_no, clock_in, clock_out, clock_in_note, clock_out_note,
   clock_in_lat, clock_in_lng, clock_in_within_geofence, clock_out_lat, clock_out_lng, clock_out_within_geofence,
   clock_in_selfie, clock_out_selfie, reentry_reason, created_at)
SELECT a.id, 1, a.clock_in, a.clock_out, a.clock_in_note, a.clock_out_note,
       a.clock_in_lat, a.clock_in_lng, a.clock_in_within_geofence, a.clock_out_lat, a.clock_out_lng, a.clock_out_within_geofence,
       a.clock_in_selfie, a.clock_out_selfie, NULL, a.clock_in
FROM attendance a
WHERE a.clock_in IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM attendance_sessions s WHERE s.attendance_id = a.id);

-- Direct manager/HR Ops correction audit (no employee request needed)
-- attendance.edited_by
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `attendance` ADD COLUMN `edited_by` INT NULL', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance' AND COLUMN_NAME = 'edited_by');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- attendance.edited_at
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `attendance` ADD COLUMN `edited_at` DATETIME NULL', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance' AND COLUMN_NAME = 'edited_at');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- attendance.edit_note
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `attendance` ADD COLUMN `edit_note` VARCHAR(255) NULL', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance' AND COLUMN_NAME = 'edit_note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- foreign key fk_attendance_edited_by
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `attendance` ADD CONSTRAINT `fk_attendance_edited_by` FOREIGN KEY (`edited_by`) REFERENCES `users` (`id`)', 'SELECT 1')
  FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance' AND CONSTRAINT_NAME = 'fk_attendance_edited_by');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
