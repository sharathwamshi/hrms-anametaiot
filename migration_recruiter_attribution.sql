-- AnametaIOT HRMS -- safe, re-runnable migration (NO data is deleted or reset)
-- Import via phpMyAdmin: select the anametaiot_hrms database -> Import -> choose this file.
-- Every statement first checks whether the change already exists, so it is safe to run
-- more than once and safe on a database that already has some of these columns.
--
-- Adds: recruiter attribution on vendor placements (vendor_hires.recruiter_id) and
-- back-fills it for existing placements from the candidate's recruiter, plus the columns
-- introduced by the client-requisition / placement / interview-level / insurance work.

USE anametaiot_hrms;

-- job_postings.interview_levels
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `job_postings` ADD COLUMN `interview_levels` TEXT NULL', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'job_postings' AND COLUMN_NAME = 'interview_levels');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- job_postings.requisition_type
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `job_postings` ADD COLUMN `requisition_type` VARCHAR(20) NULL DEFAULT ''internal''', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'job_postings' AND COLUMN_NAME = 'requisition_type');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- job_postings.vendor_id
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `job_postings` ADD COLUMN `vendor_id` INT NULL', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'job_postings' AND COLUMN_NAME = 'vendor_id');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- candidates.location
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `candidates` ADD COLUMN `location` VARCHAR(120) NULL', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'candidates' AND COLUMN_NAME = 'location');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- candidates.open_to_relocation
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `candidates` ADD COLUMN `open_to_relocation` TINYINT(1) NULL DEFAULT 0', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'candidates' AND COLUMN_NAME = 'open_to_relocation');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- candidates.current_level
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `candidates` ADD COLUMN `current_level` VARCHAR(100) NULL', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'candidates' AND COLUMN_NAME = 'current_level');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- vendor_hires.placement_type
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `vendor_hires` ADD COLUMN `placement_type` VARCHAR(20) NULL DEFAULT ''direct''', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'vendor_hires' AND COLUMN_NAME = 'placement_type');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- vendor_hires.billing_type
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `vendor_hires` ADD COLUMN `billing_type` VARCHAR(20) NULL DEFAULT ''one_time''', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'vendor_hires' AND COLUMN_NAME = 'billing_type');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- vendor_hires.last_billed_month
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `vendor_hires` ADD COLUMN `last_billed_month` VARCHAR(7) NULL', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'vendor_hires' AND COLUMN_NAME = 'last_billed_month');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- vendor_hires.recruiter_id
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `vendor_hires` ADD COLUMN `recruiter_id` INT NULL', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'vendor_hires' AND COLUMN_NAME = 'recruiter_id');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- salary_structures.insurance
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `salary_structures` ADD COLUMN `insurance` FLOAT NULL DEFAULT 0', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'salary_structures' AND COLUMN_NAME = 'insurance');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- salary_templates.insurance_pct
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `salary_templates` ADD COLUMN `insurance_pct` FLOAT NULL DEFAULT 0', 'SELECT 1')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'salary_templates' AND COLUMN_NAME = 'insurance_pct');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- foreign key fk_job_postings_vendor
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `job_postings` ADD CONSTRAINT `fk_job_postings_vendor` FOREIGN KEY (`vendor_id`) REFERENCES `vendors` (`id`)', 'SELECT 1')
  FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'job_postings' AND CONSTRAINT_NAME = 'fk_job_postings_vendor');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- foreign key fk_vendor_hires_recruiter
SET @sql = (SELECT IF(COUNT(*) = 0, 'ALTER TABLE `vendor_hires` ADD CONSTRAINT `fk_vendor_hires_recruiter` FOREIGN KEY (`recruiter_id`) REFERENCES `users` (`id`)', 'SELECT 1')
  FROM information_schema.TABLE_CONSTRAINTS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'vendor_hires' AND CONSTRAINT_NAME = 'fk_vendor_hires_recruiter');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Back-fill defaults on existing rows
UPDATE job_postings SET requisition_type = 'internal' WHERE requisition_type IS NULL;
UPDATE vendor_hires SET placement_type = 'direct' WHERE placement_type IS NULL;
UPDATE vendor_hires SET billing_type = 'one_time' WHERE billing_type IS NULL;
UPDATE candidates SET open_to_relocation = 0 WHERE open_to_relocation IS NULL;
UPDATE salary_structures SET insurance = 0 WHERE insurance IS NULL;
UPDATE salary_templates SET insurance_pct = 0 WHERE insurance_pct IS NULL;

-- Credit existing placements to the recruiter who added the candidate
UPDATE vendor_hires vh
  JOIN candidates c ON c.id = vh.candidate_id
  SET vh.recruiter_id = c.added_by
  WHERE vh.recruiter_id IS NULL AND c.added_by IS NOT NULL;
