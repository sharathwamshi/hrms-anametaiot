-- Additive employee profile, document-security, and HR audit fields.
-- Safe to run again; existing profile data and employee-document rows are preserved.
USE anametaiot_hrms;

DELIMITER $$
DROP PROCEDURE IF EXISTS add_employee_profile_column_if_missing$$
CREATE PROCEDURE add_employee_profile_column_if_missing(
    IN table_name_value VARCHAR(64),
    IN column_name_value VARCHAR(64),
    IN column_definition_value VARCHAR(255)
)
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = table_name_value
          AND COLUMN_NAME = column_name_value
    ) THEN
        SET @employee_profile_ddl = CONCAT(
            'ALTER TABLE `', table_name_value, '` ADD COLUMN `',
            column_name_value, '` ', column_definition_value
        );
        PREPARE employee_profile_stmt FROM @employee_profile_ddl;
        EXECUTE employee_profile_stmt;
        DEALLOCATE PREPARE employee_profile_stmt;
    END IF;
END$$

DROP PROCEDURE IF EXISTS add_employee_profile_fk_if_missing$$
CREATE PROCEDURE add_employee_profile_fk_if_missing(
    IN table_name_value VARCHAR(64),
    IN constraint_name_value VARCHAR(64),
    IN column_name_value VARCHAR(64),
    IN referenced_table_value VARCHAR(64),
    IN referenced_column_value VARCHAR(64),
    IN delete_rule_value VARCHAR(30)
)
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.REFERENTIAL_CONSTRAINTS
        WHERE CONSTRAINT_SCHEMA = DATABASE()
          AND TABLE_NAME = table_name_value
          AND CONSTRAINT_NAME = constraint_name_value
    ) THEN
        SET @employee_profile_fk_ddl = CONCAT(
            'ALTER TABLE `', table_name_value, '` ADD CONSTRAINT `',
            constraint_name_value, '` FOREIGN KEY (`', column_name_value,
            '`) REFERENCES `', referenced_table_value, '` (`',
            referenced_column_value, '`)',
            IF(delete_rule_value = 'SET NULL', ' ON DELETE SET NULL', '')
        );
        PREPARE employee_profile_fk_stmt FROM @employee_profile_fk_ddl;
        EXECUTE employee_profile_fk_stmt;
        DEALLOCATE PREPARE employee_profile_fk_stmt;
    END IF;
END$$

CALL add_employee_profile_column_if_missing('users', 'date_of_birth', 'DATE NULL')$$
CALL add_employee_profile_column_if_missing('users', 'gender', 'VARCHAR(30) NULL')$$
CALL add_employee_profile_column_if_missing('users', 'residential_address', 'TEXT NULL')$$
CALL add_employee_profile_column_if_missing('users', 'permanent_address', 'TEXT NULL')$$
CALL add_employee_profile_column_if_missing('users', 'emergency_contact_name', 'VARCHAR(150) NULL')$$
CALL add_employee_profile_column_if_missing('users', 'emergency_contact_relationship', 'VARCHAR(100) NULL')$$
CALL add_employee_profile_column_if_missing('users', 'emergency_contact_phone', 'VARCHAR(30) NULL')$$
CALL add_employee_profile_column_if_missing('users', 'uan', 'VARCHAR(12) NULL')$$

CALL add_employee_profile_column_if_missing('employee_documents', 'original_filename', 'VARCHAR(255) NULL')$$
CALL add_employee_profile_column_if_missing('employee_documents', 'storage_key', 'VARCHAR(255) NULL')$$
CALL add_employee_profile_column_if_missing('employee_documents', 'mime_type', 'VARCHAR(100) NULL')$$
CALL add_employee_profile_column_if_missing('employee_documents', 'file_size', 'BIGINT NULL')$$
CALL add_employee_profile_column_if_missing('employee_documents', 'uploaded_by', 'INTEGER NULL')$$
CALL add_employee_profile_column_if_missing('employee_documents', 'verification_status', 'VARCHAR(20) NOT NULL DEFAULT ''pending''')$$
CALL add_employee_profile_column_if_missing('employee_documents', 'verification_note', 'VARCHAR(500) NULL')$$
CALL add_employee_profile_column_if_missing('employee_documents', 'verified_by', 'INTEGER NULL')$$
CALL add_employee_profile_column_if_missing('employee_documents', 'verified_at', 'DATETIME NULL')$$

CALL add_employee_profile_column_if_missing('attendance', 'absence_reason', 'VARCHAR(100) NULL')$$
CALL add_employee_profile_column_if_missing('attendance', 'absence_note', 'VARCHAR(500) NULL')$$
CALL add_employee_profile_column_if_missing('attendance', 'absence_recorded_by', 'INTEGER NULL')$$
CALL add_employee_profile_column_if_missing('attendance', 'absence_recorded_at', 'DATETIME NULL')$$
CALL add_employee_profile_fk_if_missing('employee_documents', 'fk_employee_documents_uploaded_by', 'uploaded_by', 'users', 'id', '')$$
CALL add_employee_profile_fk_if_missing('employee_documents', 'fk_employee_documents_verified_by', 'verified_by', 'users', 'id', '')$$
CALL add_employee_profile_fk_if_missing('attendance', 'fk_attendance_absence_recorded_by', 'absence_recorded_by', 'users', 'id', '')$$
DROP PROCEDURE add_employee_profile_column_if_missing$$
DROP PROCEDURE add_employee_profile_fk_if_missing$$
DELIMITER ;

CREATE TABLE IF NOT EXISTS employee_family_members (
    id INTEGER NOT NULL AUTO_INCREMENT,
    user_id INTEGER NOT NULL,
    name VARCHAR(150) NOT NULL,
    relationship VARCHAR(100) NOT NULL,
    date_of_birth DATE NULL,
    phone VARCHAR(30) NULL,
    is_emergency_contact BOOL NOT NULL DEFAULT 0,
    notes VARCHAR(500) NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    INDEX ix_employee_family_members_user_id (user_id),
    FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS employee_emergency_communications (
    id INTEGER NOT NULL AUTO_INCREMENT,
    employee_id INTEGER NOT NULL,
    family_member_id INTEGER NULL,
    contact_name VARCHAR(150) NOT NULL,
    relationship VARCHAR(100) NULL,
    contact_phone VARCHAR(30) NULL,
    communication_method VARCHAR(30) NOT NULL,
    purpose VARCHAR(255) NOT NULL,
    notes VARCHAR(1000) NULL,
    outcome VARCHAR(255) NULL,
    contacted_at DATETIME NOT NULL,
    recorded_by INTEGER NOT NULL,
    PRIMARY KEY (id),
    INDEX ix_employee_emergency_communications_employee_id (employee_id),
    FOREIGN KEY (employee_id) REFERENCES users (id),
    FOREIGN KEY (family_member_id) REFERENCES employee_family_members (id) ON DELETE SET NULL,
    FOREIGN KEY (recorded_by) REFERENCES users (id)
) ENGINE=InnoDB;
