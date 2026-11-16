-- Add the exit-choice policy fields to older resignation_policies tables.
-- Existing legacy policy values are copied only where the new fields are NULL.
SET @resignation_policy_divisor_exists = (
  SELECT COUNT(*)
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'resignation_policies'
    AND COLUMN_NAME = 'buyback_daily_divisor'
);

SET @resignation_policy_divisor_ddl = IF(
  @resignation_policy_divisor_exists = 0,
  'ALTER TABLE resignation_policies ADD COLUMN buyback_daily_divisor INT NULL',
  'SELECT 1'
);

PREPARE resignation_policy_divisor_stmt FROM @resignation_policy_divisor_ddl;
EXECUTE resignation_policy_divisor_stmt;
DEALLOCATE PREPARE resignation_policy_divisor_stmt;

SET @resignation_policy_multiplier_exists = (
  SELECT COUNT(*)
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'resignation_policies'
    AND COLUMN_NAME = 'buyback_multiplier'
);

SET @resignation_policy_multiplier_ddl = IF(
  @resignation_policy_multiplier_exists = 0,
  'ALTER TABLE resignation_policies ADD COLUMN buyback_multiplier DECIMAL(8,4) NULL',
  'SELECT 1'
);

PREPARE resignation_policy_multiplier_stmt FROM @resignation_policy_multiplier_ddl;
EXECUTE resignation_policy_multiplier_stmt;
DEALLOCATE PREPARE resignation_policy_multiplier_stmt;

SET @resignation_policy_version_exists = (
  SELECT COUNT(*)
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'resignation_policies'
    AND COLUMN_NAME = 'version'
);

SET @resignation_policy_version_ddl = IF(
  @resignation_policy_version_exists = 0,
  'ALTER TABLE resignation_policies ADD COLUMN version INT NOT NULL DEFAULT 1',
  'SELECT 1'
);

PREPARE resignation_policy_version_stmt FROM @resignation_policy_version_ddl;
EXECUTE resignation_policy_version_stmt;
DEALLOCATE PREPARE resignation_policy_version_stmt;

SET @legacy_divisor_exists = (
  SELECT COUNT(*)
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'resignation_policies'
    AND COLUMN_NAME = 'buyout_salary_period_days'
);

SET @legacy_divisor_backfill = IF(
  @legacy_divisor_exists > 0,
  'UPDATE resignation_policies SET buyback_daily_divisor = buyout_salary_period_days WHERE buyback_daily_divisor IS NULL AND buyout_salary_period_days IS NOT NULL',
  'SELECT 1'
);

PREPARE resignation_policy_divisor_backfill_stmt FROM @legacy_divisor_backfill;
EXECUTE resignation_policy_divisor_backfill_stmt;
DEALLOCATE PREPARE resignation_policy_divisor_backfill_stmt;

SET @legacy_multiplier_exists = (
  SELECT COUNT(*)
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'resignation_policies'
    AND COLUMN_NAME = 'buyout_rate_multiplier'
);

SET @legacy_multiplier_backfill = IF(
  @legacy_multiplier_exists > 0,
  'UPDATE resignation_policies SET buyback_multiplier = buyout_rate_multiplier WHERE buyback_multiplier IS NULL AND buyout_rate_multiplier IS NOT NULL',
  'SELECT 1'
);

PREPARE resignation_policy_multiplier_backfill_stmt FROM @legacy_multiplier_backfill;
EXECUTE resignation_policy_multiplier_backfill_stmt;
DEALLOCATE PREPARE resignation_policy_multiplier_backfill_stmt;
