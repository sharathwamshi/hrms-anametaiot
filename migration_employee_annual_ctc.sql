-- AnametaIOT HRMS -- safe, re-runnable migration
-- Adds an optional annual CTC value to existing salary structures.
-- Existing employee and salary records are preserved.

USE anametaiot_hrms;

-- salary_structures.annual_ctc
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `salary_structures` ADD COLUMN `annual_ctc` DECIMAL(12,2) NULL', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'salary_structures' AND COLUMN_NAME = 'annual_ctc');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
