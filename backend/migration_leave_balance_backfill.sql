-- Backfill this calendar year's per-employee leave allocations.
-- New users receive their balances when their employee record is created.
INSERT INTO leave_balances (user_id, leave_type_id, year, allocated, used)
SELECT
    users.id,
    leave_types.id,
    YEAR(CURDATE()),
    COALESCE(leave_types.annual_quota, 0),
    COALESCE((
        SELECT SUM(
            DATEDIFF(
                LEAST(requests.end_date, STR_TO_DATE(CONCAT(YEAR(CURDATE()), '-12-31'), '%Y-%m-%d')),
                GREATEST(requests.start_date, STR_TO_DATE(CONCAT(YEAR(CURDATE()), '-01-01'), '%Y-%m-%d'))
            ) + 1
        )
        FROM leave_requests AS requests
        WHERE requests.user_id = users.id
          AND requests.leave_type_id = leave_types.id
          AND requests.status = 'approved'
          AND requests.start_date <= STR_TO_DATE(CONCAT(YEAR(CURDATE()), '-12-31'), '%Y-%m-%d')
          AND requests.end_date >= STR_TO_DATE(CONCAT(YEAR(CURDATE()), '-01-01'), '%Y-%m-%d')
    ), 0)
FROM users
CROSS JOIN leave_types
WHERE users.is_active = 1
  AND NOT EXISTS (
      SELECT 1
      FROM leave_balances
      WHERE leave_balances.user_id = users.id
        AND leave_balances.leave_type_id = leave_types.id
        AND leave_balances.year = YEAR(CURDATE())
  );

UPDATE leave_balances AS balances
SET used = COALESCE((
    SELECT SUM(
        DATEDIFF(
            LEAST(requests.end_date, STR_TO_DATE(CONCAT(YEAR(CURDATE()), '-12-31'), '%Y-%m-%d')),
            GREATEST(requests.start_date, STR_TO_DATE(CONCAT(YEAR(CURDATE()), '-01-01'), '%Y-%m-%d'))
        ) + 1
    )
    FROM leave_requests AS requests
    WHERE requests.user_id = balances.user_id
      AND requests.leave_type_id = balances.leave_type_id
      AND requests.status = 'approved'
      AND requests.start_date <= STR_TO_DATE(CONCAT(YEAR(CURDATE()), '-12-31'), '%Y-%m-%d')
      AND requests.end_date >= STR_TO_DATE(CONCAT(YEAR(CURDATE()), '-01-01'), '%Y-%m-%d')
), 0)
WHERE balances.year = YEAR(CURDATE());
