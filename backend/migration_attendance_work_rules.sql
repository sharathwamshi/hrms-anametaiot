-- Attendance work rules: configurable arrival buffer and manager edit time audit.
SET @sql = (SELECT IF(COUNT(*) = 0,
  'ALTER TABLE `company_settings` ADD COLUMN `attendance_buffer_minutes` INT NOT NULL DEFAULT 10',
  'SELECT 1')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'company_settings'
    AND COLUMN_NAME = 'attendance_buffer_minutes');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (SELECT IF(COUNT(*) = 0,
  'ALTER TABLE `attendance` ADD COLUMN `edit_details` TEXT NULL',
  'SELECT 1')
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance'
    AND COLUMN_NAME = 'edit_details');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
