-- AnametaIOT HRMS -- EMPLOYEE REMOVAL: safe, re-runnable migration (NO data is deleted or changed)
-- Import via phpMyAdmin: select the anametaiot_hrms database -> Import -> choose this file.
--
-- Adds the audit trail for removing a person: who removed them, when, and why.
-- People are never hard-deleted (payslips, attendance, leave, placements... must be kept),
-- so every existing user stays exactly as they are: active, with these three fields empty.
-- Anyone already deactivated earlier simply shows no removal details.

USE anametaiot_hrms;

-- users.removed_at
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `users` ADD COLUMN `removed_at` DATETIME NULL', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'removed_at');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- users.removed_by
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `users` ADD COLUMN `removed_by` INT NULL', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'removed_by');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- users.removal_reason
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `users` ADD COLUMN `removal_reason` VARCHAR(255) NULL', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'removal_reason');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- foreign key fk_users_removed_by
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `users` ADD CONSTRAINT `fk_users_removed_by` FOREIGN KEY (`removed_by`) REFERENCES `users` (`id`)', 'SELECT 1')
  FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND CONSTRAINT_NAME = 'fk_users_removed_by');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
