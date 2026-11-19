CREATE TABLE IF NOT EXISTS leave_entitlement_audit (
    id INTEGER NOT NULL AUTO_INCREMENT,
    leave_type_id INTEGER NOT NULL,
    employee_id INTEGER NULL,
    actor_id INTEGER NOT NULL,
    scope VARCHAR(30) NOT NULL,
    year INTEGER NULL,
    old_entitlement FLOAT NOT NULL,
    new_entitlement FLOAT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    FOREIGN KEY (leave_type_id) REFERENCES leave_types (id),
    FOREIGN KEY (employee_id) REFERENCES users (id),
    FOREIGN KEY (actor_id) REFERENCES users (id)
) ENGINE=InnoDB;
