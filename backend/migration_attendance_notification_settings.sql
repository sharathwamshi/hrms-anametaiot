-- Company-wide notification preferences and idempotent scheduled reminder runs.
-- Safe to apply more than once; existing notifications remain enabled by default.
USE anametaiot_hrms;

CREATE TABLE IF NOT EXISTS attendance_notification_settings (
    id INTEGER NOT NULL,
    regularization_enabled BOOL NOT NULL DEFAULT 1,
    leave_enabled BOOL NOT NULL DEFAULT 1,
    attendance_updates_enabled BOOL NOT NULL DEFAULT 1,
    business_alerts_enabled BOOL NOT NULL DEFAULT 1,
    clock_in_reminder_enabled BOOL NOT NULL DEFAULT 1,
    manager_missing_alert_enabled BOOL NOT NULL DEFAULT 1,
    clock_out_reminder_enabled BOOL NOT NULL DEFAULT 1,
    clock_in_reminder_time TIME NOT NULL DEFAULT '09:30:00',
    manager_missing_alert_time TIME NOT NULL DEFAULT '10:00:00',
    clock_out_reminder_time TIME NOT NULL DEFAULT '18:30:00',
    updated_by INTEGER NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT fk_attendance_notification_settings_user
        FOREIGN KEY (updated_by) REFERENCES users (id)
) ENGINE=InnoDB;

INSERT IGNORE INTO attendance_notification_settings (id) VALUES (1);

CREATE TABLE IF NOT EXISTS attendance_reminder_runs (
    id INTEGER NOT NULL AUTO_INCREMENT,
    reminder_kind VARCHAR(40) NOT NULL,
    reminder_date DATE NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_attendance_reminder_run_day (reminder_kind, reminder_date)
) ENGINE=InnoDB;
