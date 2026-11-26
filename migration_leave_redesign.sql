-- Apply after reviewing the live database; no tables or records are dropped.
ALTER TABLE leave_requests
    ADD COLUMN duration VARCHAR(20) NOT NULL DEFAULT 'full_day',
    ADD COLUMN final_classification VARCHAR(20) NULL;

ALTER TABLE leave_balances
    ADD COLUMN exhaustion_acknowledged BOOLEAN NOT NULL DEFAULT FALSE;

-- Existing "Earned Leave" is the closest predecessor to the new Paid Leave.
UPDATE leave_types
SET name = 'Paid Leave', annual_quota = 6
WHERE name IN ('Earned Leave', 'Annual Leave');

INSERT INTO leave_types (name, annual_quota)
SELECT 'Paid Leave', 6
WHERE NOT EXISTS (SELECT 1 FROM leave_types WHERE name = 'Paid Leave');

UPDATE leave_types SET annual_quota = 0 WHERE name = 'Casual Leave';
UPDATE leave_types SET annual_quota = 0 WHERE name = 'Sick Leave';

-- Normalize untouched legacy defaults while preserving manager-customized values
-- and all previously used leave.
UPDATE leave_balances AS balances
JOIN leave_types AS types ON types.id = balances.leave_type_id
SET balances.allocated = CASE types.name
    WHEN 'Paid Leave' THEN 6
    WHEN 'Casual Leave' THEN 0
    WHEN 'Sick Leave' THEN 0
END
WHERE (types.name = 'Paid Leave' AND balances.allocated = 15)
   OR (types.name = 'Casual Leave' AND balances.allocated = 12)
   OR (types.name = 'Sick Leave' AND balances.allocated = 8);

INSERT INTO leave_types (name, annual_quota)
SELECT 'Casual Leave', 0
WHERE NOT EXISTS (SELECT 1 FROM leave_types WHERE name = 'Casual Leave');

INSERT INTO leave_types (name, annual_quota)
SELECT 'Sick Leave', 0
WHERE NOT EXISTS (SELECT 1 FROM leave_types WHERE name = 'Sick Leave');
