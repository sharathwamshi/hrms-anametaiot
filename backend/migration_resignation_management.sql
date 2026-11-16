-- Resignation workflow data. Existing employee rows and legacy resignation
-- fields are preserved; the active_key unique index prevents duplicate active
-- workflow requests for one employee.
CREATE TABLE IF NOT EXISTS resignation_requests (
  id INT NOT NULL AUTO_INCREMENT,
  employee_id INT NOT NULL,
  company_name VARCHAR(150) NOT NULL,
  department_name VARCHAR(100) NULL,
  resignation_date DATE NOT NULL,
  original_last_working_date DATE NOT NULL,
  proposed_last_working_date DATE NOT NULL,
  approved_last_working_date DATE NULL,
  reason TEXT NOT NULL,
  comments TEXT NULL,
  status VARCHAR(30) NOT NULL DEFAULT 'manager_pending',
  current_stage VARCHAR(30) NOT NULL DEFAULT 'manager',
  current_approver_id INT NULL,
  active_key VARCHAR(20) NULL,
  notice_period_days INT NULL,
  dates_approved_at DATETIME NULL,
  document_storage_key VARCHAR(255) NULL,
  document_filename VARCHAR(255) NULL,
  document_mime_type VARCHAR(100) NULL,
  document_size INT NULL,
  pending_revision_id INT NULL,
  withdrawal_approver_id INT NULL,
  withdrawal_approver_role VARCHAR(30) NULL,
  withdrawal_previous_status VARCHAR(30) NULL,
  withdrawal_previous_stage VARCHAR(30) NULL,
  finance_pending_salary DECIMAL(12,2) NULL,
  finance_advances DECIMAL(12,2) NULL,
  finance_reimbursements DECIMAL(12,2) NULL,
  finance_other_dues DECIMAL(12,2) NULL,
  final_settlement_amount DECIMAL(12,2) NULL,
  final_settlement_status VARCHAR(30) NULL,
  finance_cleared_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_resignation_active_key (active_key),
  KEY ix_resignation_employee (employee_id),
  KEY ix_resignation_company (company_name),
  KEY ix_resignation_status (status),
  CONSTRAINT fk_resignation_employee FOREIGN KEY (employee_id) REFERENCES users (id),
  CONSTRAINT fk_resignation_approver FOREIGN KEY (current_approver_id) REFERENCES users (id),
  CONSTRAINT fk_resignation_withdraw_approver FOREIGN KEY (withdrawal_approver_id) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS resignation_date_revisions (
  id INT NOT NULL AUTO_INCREMENT,
  resignation_id INT NOT NULL,
  requested_by INT NOT NULL,
  proposed_last_working_date DATE NOT NULL,
  reason TEXT NOT NULL,
  status VARCHAR(30) NOT NULL DEFAULT 'manager_pending',
  current_stage VARCHAR(30) NOT NULL DEFAULT 'manager',
  prior_status VARCHAR(30) NOT NULL,
  prior_stage VARCHAR(30) NOT NULL,
  prior_approved_last_working_date DATE NULL,
  prior_notice_period_days INT NULL,
  prior_dates_approved_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  decided_at DATETIME NULL,
  PRIMARY KEY (id),
  KEY ix_resignation_revision_request (resignation_id),
  CONSTRAINT fk_resignation_revision_request FOREIGN KEY (resignation_id) REFERENCES resignation_requests (id),
  CONSTRAINT fk_resignation_revision_user FOREIGN KEY (requested_by) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS resignation_routing (
  id INT NOT NULL AUTO_INCREMENT,
  company_name VARCHAR(150) NOT NULL,
  approver_user_id INT NOT NULL,
  created_by INT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_resignation_routing_company_approver (company_name, approver_user_id),
  KEY ix_resignation_routing_approver (approver_user_id),
  CONSTRAINT fk_resignation_routing_user FOREIGN KEY (approver_user_id) REFERENCES users (id),
  CONSTRAINT fk_resignation_routing_creator FOREIGN KEY (created_by) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS resignation_events (
  id INT NOT NULL AUTO_INCREMENT,
  resignation_id INT NOT NULL,
  actor_id INT NOT NULL,
  event_type VARCHAR(40) NOT NULL,
  stage VARCHAR(30) NULL,
  status VARCHAR(30) NULL,
  comments TEXT NULL,
  details TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_resignation_event_request (resignation_id),
  KEY ix_resignation_event_created (created_at),
  CONSTRAINT fk_resignation_event_request FOREIGN KEY (resignation_id) REFERENCES resignation_requests (id),
  CONSTRAINT fk_resignation_event_actor FOREIGN KEY (actor_id) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS resignation_checklist_items (
  id INT NOT NULL AUTO_INCREMENT,
  resignation_id INT NOT NULL,
  item_key VARCHAR(40) NOT NULL,
  label VARCHAR(100) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'pending',
  completed_by INT NULL,
  completed_at DATETIME NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_resignation_checklist_item (resignation_id, item_key),
  CONSTRAINT fk_resignation_checklist_request FOREIGN KEY (resignation_id) REFERENCES resignation_requests (id),
  CONSTRAINT fk_resignation_checklist_user FOREIGN KEY (completed_by) REFERENCES users (id)
) ENGINE=InnoDB;

-- Seed the initial L2 routing without changing employee rows. Names are used
-- only to associate the supplied initial approvers; administrators can manage
-- routing through the application thereafter.
INSERT IGNORE INTO resignation_routing (company_name, approver_user_id, created_by)
SELECT 'Acknowledger First Pvt Ltd', u.id, u.id
FROM users u
WHERE (LOWER(TRIM(u.full_name)) LIKE 'rohith%' OR LOWER(TRIM(u.full_name)) LIKE 'megha%')
  AND u.is_active = 1;

INSERT IGNORE INTO resignation_routing (company_name, approver_user_id, created_by)
SELECT 'Ana Meta IoT', u.id, u.id
FROM users u
WHERE LOWER(TRIM(u.full_name)) LIKE 'manish%' AND u.is_active = 1;

INSERT IGNORE INTO resignation_routing (company_name, approver_user_id, created_by)
SELECT 'Vkalpa Innovations', u.id, u.id
FROM users u
WHERE LOWER(TRIM(u.full_name)) LIKE 'kiran%' AND u.is_active = 1;
