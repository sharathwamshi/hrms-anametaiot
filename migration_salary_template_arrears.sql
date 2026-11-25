ALTER TABLE salary_templates
  ADD COLUMN arrears_employee_id INTEGER NULL,
  ADD COLUMN arrears_description VARCHAR(150) NULL,
  ADD COLUMN arrears_amount FLOAT NULL,
  ADD COLUMN arrears_month INTEGER NULL,
  ADD COLUMN arrears_year INTEGER NULL,
  ADD CONSTRAINT fk_salary_templates_arrears_employee_id
    FOREIGN KEY (arrears_employee_id) REFERENCES users (id);
