-- Super Admin role + office-only punching.  Safe to re-run; changes no existing data.
-- (users.role is a plain VARCHAR, so the new role 'super_admin' needs no schema change.)

-- users.restrict_to_office
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `users` ADD COLUMN `restrict_to_office` TINYINT(1) NOT NULL DEFAULT 0', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'restrict_to_office');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- users.restrict_set_by
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `users` ADD COLUMN `restrict_set_by` INT NULL', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'restrict_set_by');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- users.restrict_set_at
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `users` ADD COLUMN `restrict_set_at` DATETIME NULL', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'restrict_set_at');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- foreign key fk_users_restrict_set_by
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `users` ADD CONSTRAINT `fk_users_restrict_set_by` FOREIGN KEY (`restrict_set_by`) REFERENCES `users` (`id`)', 'SELECT 1')
  FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND CONSTRAINT_NAME = 'fk_users_restrict_set_by');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ---------------------------------------------------------------------------------------
-- Make your first Super Admin (edit the e-mail, then run just this line).
-- After that, Super Admins can create others from the Employees screen.
-- ---------------------------------------------------------------------------------------
-- UPDATE users SET role = 'super_admin' WHERE email = 'you@company.com';
