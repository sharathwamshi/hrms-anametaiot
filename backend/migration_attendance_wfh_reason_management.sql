-- Persist WFH reason ordering and link future attendance snapshots to their source option.
SET @sql = (SELECT IF(COUNT(*) = 0,
    'ALTER TABLE `attendance_wfh_reasons` ADD COLUMN `sort_order` INT NOT NULL DEFAULT 0',
    'SELECT 1')
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance_wfh_reasons'
      AND COLUMN_NAME = 'sort_order');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql = (SELECT IF(COUNT(*) = 0,
    'ALTER TABLE `attendance_sessions` ADD COLUMN `wfh_reason_id` INT NULL',
    'SELECT 1')
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance_sessions'
      AND COLUMN_NAME = 'wfh_reason_id');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

UPDATE attendance_sessions AS s
JOIN attendance_wfh_reasons AS r
  ON r.label = s.wfh_reason
SET s.wfh_reason_id = r.id
WHERE s.wfh_reason_id IS NULL;

SET @sql = (SELECT IF(COUNT(*) = 0,
    'ALTER TABLE `attendance_sessions` ADD CONSTRAINT `fk_attendance_session_wfh_reason` FOREIGN KEY (`wfh_reason_id`) REFERENCES `attendance_wfh_reasons` (`id`) ON DELETE SET NULL',
    'SELECT 1')
    FROM information_schema.KEY_COLUMN_USAGE
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'attendance_sessions'
      AND CONSTRAINT_NAME = 'fk_attendance_session_wfh_reason');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
