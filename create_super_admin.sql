-- Create a Super Admin login.  Safe to re-run (does nothing if the e-mail already exists).
-- 1) Change the e-mail, name and employee code below if you like.
-- 2) Import in phpMyAdmin.  Temporary password: ChangeMe@123  (change it after first sign-in).
-- Needs migration_super_admin_office_restriction.sql imported first.

INSERT INTO users (employee_code, full_name, email, password_hash, `role`, designation, date_of_joining, is_active, created_at, updated_at)
SELECT 'SA001', 'Super Admin', 'superadmin@yourcompany.com',
       '$2b$12$2kg.DHa7.tbxrvvSHcJd4.vuVGGdoUnz3y91oV14NWXYxLtoPbViy',
       'super_admin', 'Super Admin', CURDATE(), 1, NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM users WHERE email = 'superadmin@yourcompany.com')
  AND NOT EXISTS (SELECT 1 FROM users WHERE employee_code = 'SA001');

-- ALTERNATIVE: make an EXISTING person a Super Admin instead (edit the e-mail, remove the leading --):
-- UPDATE users SET `role` = 'super_admin' WHERE email = 'you@company.com';
