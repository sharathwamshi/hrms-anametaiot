ALTER TABLE salary_templates
  ADD COLUMN company_name VARCHAR(150) NULL,
  ADD COLUMN transport_flat FLOAT NOT NULL DEFAULT 0,
  ADD COLUMN employee_pf_rate_pct FLOAT NOT NULL DEFAULT 0,
  ADD COLUMN employer_pf_rate_pct FLOAT NOT NULL DEFAULT 0,
  ADD COLUMN employer_pf_flat FLOAT NOT NULL DEFAULT 0,
  ADD COLUMN tds_flat FLOAT NOT NULL DEFAULT 0,
  ADD COLUMN insurance_months JSON NULL,
  ADD COLUMN insurance_amounts JSON NULL,
  ADD INDEX ix_salary_templates_company_name (company_name);

ALTER TABLE salary_structures
  ADD COLUMN salary_template_id INTEGER NULL,
  ADD COLUMN employee_overrides JSON NULL,
  ADD CONSTRAINT fk_salary_structures_salary_template_id
    FOREIGN KEY (salary_template_id) REFERENCES salary_templates (id);
