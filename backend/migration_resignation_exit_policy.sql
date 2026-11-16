-- Company-level resignation policy and immutable request calculation snapshots.
CREATE TABLE IF NOT EXISTS resignation_policies (
  id INT NOT NULL AUTO_INCREMENT,
  company_name VARCHAR(150) NOT NULL,
  notice_period_days INT NOT NULL,
  buyback_daily_divisor INT NULL,
  buyback_multiplier DECIMAL(8,4) NULL,
  version INT NOT NULL DEFAULT 1,
  updated_by INT NOT NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_resignation_policy_company (company_name),
  CONSTRAINT fk_resignation_policy_updated_by FOREIGN KEY (updated_by) REFERENCES users (id)
) ENGINE=InnoDB;

ALTER TABLE resignation_requests
  ADD COLUMN exit_choice VARCHAR(40) NULL,
  ADD COLUMN exit_policy_snapshot JSON NULL,
  ADD COLUMN buyback_estimated_amount DECIMAL(12,2) NULL,
  ADD COLUMN buyback_unserved_days INT NULL,
  ADD COLUMN buyback_calculation_verified_by INT NULL,
  ADD COLUMN buyback_calculation_verified_at DATETIME NULL,
  ADD COLUMN buyback_payment_status VARCHAR(30) NULL,
  ADD COLUMN buyback_payment_reference VARCHAR(255) NULL,
  ADD COLUMN buyback_payment_verified_by INT NULL,
  ADD COLUMN buyback_payment_verified_at DATETIME NULL,
  ADD CONSTRAINT fk_resignation_buyback_hr_verifier FOREIGN KEY (buyback_calculation_verified_by) REFERENCES users (id),
  ADD CONSTRAINT fk_resignation_buyback_finance_verifier FOREIGN KEY (buyback_payment_verified_by) REFERENCES users (id);
