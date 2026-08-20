-- AnametaIOT HRMS -- MySQL schema (auto-generated from SQLAlchemy models)
-- Import with: mysql -u root < schema.sql

CREATE DATABASE IF NOT EXISTS anametaiot_hrms CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE anametaiot_hrms;

CREATE TABLE departments (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	name VARCHAR(100) NOT NULL, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (name)
) ENGINE=InnoDB;

CREATE TABLE leave_types (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	name VARCHAR(50) NOT NULL, 
	annual_quota FLOAT, 
	PRIMARY KEY (id), 
	UNIQUE (name)
) ENGINE=InnoDB;

CREATE TABLE topic_library (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	name VARCHAR(80) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
) ENGINE=InnoDB;

CREATE TABLE users (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	employee_code VARCHAR(20) NOT NULL, 
	full_name VARCHAR(150) NOT NULL, 
	email VARCHAR(150) NOT NULL, 
	phone VARCHAR(20), 
	password_hash VARCHAR(255) NOT NULL, 
	`role` VARCHAR(30) NOT NULL, 
	designation VARCHAR(120), 
	department_id INTEGER, 
	manager_id INTEGER, 
	date_of_joining DATE, 
	avatar_url VARCHAR(255), 
	is_active BOOL, 
	self_verify_rights BOOL, 
	self_verify_granted_by INTEGER, 
	revalidation_interval_days INTEGER, 
	created_at DATETIME, 
	updated_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (employee_code), 
	UNIQUE (email), 
	FOREIGN KEY(department_id) REFERENCES departments (id), 
	FOREIGN KEY(manager_id) REFERENCES users (id), 
	FOREIGN KEY(self_verify_granted_by) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE announcements (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	title VARCHAR(200) NOT NULL, 
	body TEXT NOT NULL, 
	posted_by INTEGER, 
	audience_role VARCHAR(30), 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(posted_by) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE assets (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	asset_tag VARCHAR(50) NOT NULL, 
	category VARCHAR(50), 
	description VARCHAR(200), 
	assigned_to INTEGER, 
	assigned_on DATE, 
	returned_on DATE, 
	status VARCHAR(20), 
	PRIMARY KEY (id), 
	UNIQUE (asset_tag), 
	FOREIGN KEY(assigned_to) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE attendance (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	work_date DATE NOT NULL, 
	clock_in DATETIME, 
	clock_out DATETIME, 
	clock_in_note VARCHAR(255), 
	clock_out_note VARCHAR(255), 
	status VARCHAR(20), 
	total_hours FLOAT, 
	is_regularized BOOL, 
	regularization_reason VARCHAR(255), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_attendance_user_date UNIQUE (user_id, work_date), 
	FOREIGN KEY(user_id) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE company_settings (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	company_name VARCHAR(150), 
	address TEXT, 
	gstin VARCHAR(20), 
	pan VARCHAR(20), 
	state VARCHAR(50), 
	updated_by INTEGER, 
	updated_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE employee_documents (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	doc_type VARCHAR(30) NOT NULL, 
	title VARCHAR(150) NOT NULL, 
	file_path VARCHAR(255) NOT NULL, 
	uploaded_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE employee_permissions (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	permission_key VARCHAR(50) NOT NULL, 
	granted_by INTEGER, 
	granted_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_employee_permission UNIQUE (user_id, permission_key), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(granted_by) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE job_postings (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	title VARCHAR(150) NOT NULL, 
	department_id INTEGER, 
	employment_type VARCHAR(30), 
	openings INTEGER, 
	description TEXT, 
	salary_min FLOAT, 
	salary_max FLOAT, 
	priority VARCHAR(20), 
	auto_close_date DATE, 
	requisition_status VARCHAR(20), 
	approved_by INTEGER, 
	approved_at DATETIME, 
	screening_questions TEXT, 
	post_image_url VARCHAR(255), 
	linkedin_post_url VARCHAR(255), 
	naukri_post_url VARCHAR(255), 
	interview_levels TEXT, 
	status VARCHAR(20), 
	created_by INTEGER, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(department_id) REFERENCES departments (id), 
	FOREIGN KEY(approved_by) REFERENCES users (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE leave_balances (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	leave_type_id INTEGER NOT NULL, 
	year INTEGER NOT NULL, 
	allocated FLOAT, 
	used FLOAT, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_balance_user_type_year UNIQUE (user_id, leave_type_id, year), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(leave_type_id) REFERENCES leave_types (id)
) ENGINE=InnoDB;

CREATE TABLE leave_requests (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	leave_type_id INTEGER NOT NULL, 
	start_date DATE NOT NULL, 
	end_date DATE NOT NULL, 
	days FLOAT NOT NULL, 
	reason VARCHAR(500), 
	status VARCHAR(20), 
	reviewed_by INTEGER, 
	review_comment VARCHAR(255), 
	created_at DATETIME, 
	updated_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(leave_type_id) REFERENCES leave_types (id), 
	FOREIGN KEY(reviewed_by) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE payslips (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	month INTEGER NOT NULL, 
	year INTEGER NOT NULL, 
	days_present FLOAT, 
	days_on_leave FLOAT, 
	lop_days FLOAT, 
	gross_earnings FLOAT, 
	total_deductions FLOAT, 
	net_pay FLOAT, 
	status VARCHAR(20), 
	pdf_path VARCHAR(255), 
	generated_by INTEGER, 
	generated_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_payslip_user_month_year UNIQUE (user_id, month, year), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(generated_by) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE salary_structures (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER NOT NULL, 
	basic FLOAT, 
	hra FLOAT, 
	special_allowance FLOAT, 
	other_allowance FLOAT, 
	pf_employee FLOAT, 
	esi_employee FLOAT, 
	professional_tax FLOAT, 
	tds FLOAT, 
	effective_from DATE, 
	PRIMARY KEY (id), 
	UNIQUE (user_id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE salary_templates (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	name VARCHAR(100) NOT NULL, 
	description VARCHAR(255), 
	basic_pct FLOAT, 
	hra_pct FLOAT, 
	special_allowance_pct FLOAT, 
	other_allowance_pct FLOAT, 
	pf_employee_pct FLOAT, 
	esi_employee_pct FLOAT, 
	professional_tax_flat FLOAT, 
	tds_pct FLOAT, 
	created_by INTEGER, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE vendors (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	name VARCHAR(150) NOT NULL, 
	normalized_name VARCHAR(150), 
	address TEXT, 
	state VARCHAR(50), 
	gstin VARCHAR(20), 
	pan VARCHAR(20), 
	contact_person VARCHAR(120), 
	contact_email VARCHAR(150), 
	contact_phone VARCHAR(20), 
	bank_name VARCHAR(120), 
	bank_account_no VARCHAR(40), 
	bank_ifsc VARCHAR(20), 
	bank_branch VARCHAR(120), 
	status VARCHAR(20), 
	created_by INTEGER, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE candidates (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	job_id INTEGER NOT NULL, 
	full_name VARCHAR(150) NOT NULL, 
	email VARCHAR(150), 
	email_normalized VARCHAR(150), 
	phone VARCHAR(20), 
	phone_normalized VARCHAR(20), 
	resume_url VARCHAR(255), 
	resume_file_path VARCHAR(255), 
	source VARCHAR(50), 
	skills VARCHAR(500), 
	location VARCHAR(120), 
	open_to_relocation BOOL, 
	current_level VARCHAR(100), 
	stage VARCHAR(30), 
	notes TEXT, 
	validation_status VARCHAR(20), 
	validation_notes TEXT, 
	duplicate_of_candidate_id INTEGER, 
	verification_status VARCHAR(20), 
	verified_by INTEGER, 
	verified_at DATETIME, 
	next_revalidation_due DATETIME, 
	referring_employee_id INTEGER, 
	referral_bonus_status VARCHAR(20), 
	bgv_status VARCHAR(20), 
	linked_employee_id INTEGER, 
	added_by INTEGER, 
	assigned_to INTEGER, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(job_id) REFERENCES job_postings (id), 
	FOREIGN KEY(duplicate_of_candidate_id) REFERENCES candidates (id), 
	FOREIGN KEY(verified_by) REFERENCES users (id), 
	FOREIGN KEY(referring_employee_id) REFERENCES users (id), 
	FOREIGN KEY(linked_employee_id) REFERENCES users (id), 
	FOREIGN KEY(added_by) REFERENCES users (id), 
	FOREIGN KEY(assigned_to) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE mock_test_templates (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	title VARCHAR(150) NOT NULL, 
	job_id INTEGER, 
	topics VARCHAR(255) NOT NULL, 
	complexity VARCHAR(20), 
	duration_minutes INTEGER, 
	passing_threshold_pct FLOAT, 
	created_by INTEGER, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(job_id) REFERENCES job_postings (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE vendor_agreements (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	vendor_id INTEGER NOT NULL, 
	title VARCHAR(150), 
	file_path VARCHAR(255) NOT NULL, 
	effective_from DATE, 
	effective_to DATE, 
	termination_notice_days INTEGER, 
	confidentiality_days INTEGER, 
	feedback_days INTEGER, 
	status VARCHAR(20), 
	parsed_with_ai BOOL, 
	raw_extracted_text TEXT, 
	uploaded_by INTEGER, 
	uploaded_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(vendor_id) REFERENCES vendors (id), 
	FOREIGN KEY(uploaded_by) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE candidate_audit_log (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	candidate_id INTEGER NOT NULL, 
	action VARCHAR(80) NOT NULL, 
	detail VARCHAR(500), 
	actor_id INTEGER, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(candidate_id) REFERENCES candidates (id), 
	FOREIGN KEY(actor_id) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE candidate_notes (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	candidate_id INTEGER NOT NULL, 
	author_id INTEGER NOT NULL, 
	body TEXT NOT NULL, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(candidate_id) REFERENCES candidates (id), 
	FOREIGN KEY(author_id) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE interviews (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	candidate_id INTEGER NOT NULL, 
	scheduled_at DATETIME NOT NULL, 
	round_name VARCHAR(50), 
	mode VARCHAR(20), 
	status VARCHAR(20), 
	reschedule_reason VARCHAR(255), 
	feedback TEXT, 
	scorecard TEXT, 
	result VARCHAR(20), 
	scheduled_by INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(candidate_id) REFERENCES candidates (id), 
	FOREIGN KEY(scheduled_by) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE mock_test_assignments (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	template_id INTEGER NOT NULL, 
	candidate_id INTEGER NOT NULL, 
	attempt_number INTEGER, 
	assigned_by INTEGER, 
	access_token VARCHAR(64), 
	window_start DATETIME NOT NULL, 
	window_end DATETIME NOT NULL, 
	status VARCHAR(20), 
	started_at DATETIME, 
	submitted_at DATETIME, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(template_id) REFERENCES mock_test_templates (id), 
	FOREIGN KEY(candidate_id) REFERENCES candidates (id), 
	FOREIGN KEY(assigned_by) REFERENCES users (id), 
	UNIQUE (access_token)
) ENGINE=InnoDB;

CREATE TABLE mock_test_questions (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	template_id INTEGER NOT NULL, 
	topic VARCHAR(80), 
	question_text TEXT NOT NULL, 
	question_type VARCHAR(20), 
	options_json TEXT, 
	correct_answer VARCHAR(500), 
	marks FLOAT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(template_id) REFERENCES mock_test_templates (id)
) ENGINE=InnoDB;

CREATE TABLE offers (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	candidate_id INTEGER NOT NULL, 
	designation VARCHAR(120) NOT NULL, 
	salary FLOAT NOT NULL, 
	joining_date DATE NOT NULL, 
	status VARCHAR(20), 
	counter_notes TEXT, 
	drafted_by INTEGER, 
	approver_id INTEGER, 
	approved_at DATETIME, 
	approval_comment VARCHAR(255), 
	created_at DATETIME, 
	updated_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(candidate_id) REFERENCES candidates (id), 
	FOREIGN KEY(drafted_by) REFERENCES users (id), 
	FOREIGN KEY(approver_id) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE screening_calls (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	candidate_id INTEGER NOT NULL, 
	attempt_number INTEGER, 
	scheduled_at DATETIME NOT NULL, 
	called_at DATETIME, 
	status VARCHAR(20), 
	recording_url VARCHAR(255), 
	transcript TEXT, 
	summary TEXT, 
	outcome VARCHAR(20), 
	triggered_by INTEGER, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(candidate_id) REFERENCES candidates (id), 
	FOREIGN KEY(triggered_by) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE vendor_agreement_roles (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	agreement_id INTEGER NOT NULL, 
	role_name VARCHAR(120) NOT NULL, 
	service_fee_pct FLOAT NOT NULL, 
	replacement_days INTEGER, 
	tenure_days INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(agreement_id) REFERENCES vendor_agreements (id)
) ENGINE=InnoDB;

CREATE TABLE vendor_invoices (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	vendor_id INTEGER NOT NULL, 
	agreement_id INTEGER, 
	invoice_number VARCHAR(50) NOT NULL, 
	invoice_date DATE NOT NULL, 
	subtotal FLOAT, 
	cgst_amount FLOAT, 
	sgst_amount FLOAT, 
	igst_amount FLOAT, 
	total_amount FLOAT, 
	status VARCHAR(20), 
	approved_by INTEGER, 
	approved_at DATETIME, 
	approval_comment VARCHAR(255), 
	paid_at DATETIME, 
	pdf_path VARCHAR(255), 
	generated_by INTEGER, 
	generated_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(vendor_id) REFERENCES vendors (id), 
	FOREIGN KEY(agreement_id) REFERENCES vendor_agreements (id), 
	UNIQUE (invoice_number), 
	FOREIGN KEY(approved_by) REFERENCES users (id), 
	FOREIGN KEY(generated_by) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE interview_panelists (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	interview_id INTEGER NOT NULL, 
	interviewer_id INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(interview_id) REFERENCES interviews (id), 
	FOREIGN KEY(interviewer_id) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE mock_test_answers (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	assignment_id INTEGER NOT NULL, 
	question_id INTEGER NOT NULL, 
	answer_text TEXT, 
	score_awarded FLOAT, 
	ai_feedback TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(assignment_id) REFERENCES mock_test_assignments (id), 
	FOREIGN KEY(question_id) REFERENCES mock_test_questions (id)
) ENGINE=InnoDB;

CREATE TABLE mock_test_results (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	assignment_id INTEGER NOT NULL, 
	score FLOAT, 
	max_score FLOAT, 
	percentage FLOAT, 
	topic_breakdown_json TEXT, 
	ai_feedback TEXT, 
	passed BOOL, 
	graded_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (assignment_id), 
	FOREIGN KEY(assignment_id) REFERENCES mock_test_assignments (id)
) ENGINE=InnoDB;

CREATE TABLE vendor_hires (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	vendor_id INTEGER NOT NULL, 
	agreement_id INTEGER NOT NULL, 
	agreement_role_id INTEGER NOT NULL, 
	candidate_id INTEGER, 
	employee_id INTEGER, 
	candidate_name VARCHAR(150) NOT NULL, 
	ctc FLOAT NOT NULL, 
	tenure_start_date DATE NOT NULL, 
	status VARCHAR(20), 
	replacement_of_hire_id INTEGER, 
	assigned_by INTEGER, 
	assigned_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(vendor_id) REFERENCES vendors (id), 
	FOREIGN KEY(agreement_id) REFERENCES vendor_agreements (id), 
	FOREIGN KEY(agreement_role_id) REFERENCES vendor_agreement_roles (id), 
	FOREIGN KEY(candidate_id) REFERENCES candidates (id), 
	FOREIGN KEY(employee_id) REFERENCES users (id), 
	FOREIGN KEY(replacement_of_hire_id) REFERENCES vendor_hires (id), 
	FOREIGN KEY(assigned_by) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE vendor_invoice_items (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	invoice_id INTEGER NOT NULL, 
	hire_id INTEGER NOT NULL, 
	candidate_name VARCHAR(150) NOT NULL, 
	role_name VARCHAR(120), 
	ctc FLOAT NOT NULL, 
	fee_pct FLOAT NOT NULL, 
	fee_amount FLOAT NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(invoice_id) REFERENCES vendor_invoices (id), 
	FOREIGN KEY(hire_id) REFERENCES vendor_hires (id)
) ENGINE=InnoDB;
