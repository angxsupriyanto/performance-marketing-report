-- Viewer accounts and company display names. Run after 002, connected to marketing_reports as a superuser:
--
--   psql -v ON_ERROR_STOP=1 -d marketing_reports -f database/004_users_and_company_names.sql
--
-- Re-running is safe: tables and grants are only created or refreshed, never dropped.
--
-- Design:
--   * viewer_users: one row per person. Only a scrypt hash is stored, never a password. Users are deactivated
--     (active = false), never deleted, so their history stays. The viewer role gets SELECT, INSERT and UPDATE but no DELETE.
--   * Access: an admin always sees every company. A normal user either sees all companies (all_companies, which includes
--     companies added later) or exactly the companies listed in companies. The CHECK below enforces that shape.
--   * company_names: the display name of each internal company id (bu1, bu2, ...). Ids never change, so reports, links and
--     user access keep working when a name changes. Names are unique ignoring case.
--   * The first admin is created by the viewer at start-up from the existing VIEWER_PASSWORD_HASH secret, only while the table is empty.

SET ROLE report_owner;

CREATE TABLE IF NOT EXISTS reports.viewer_users (
    user_id       uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    username      text        NOT NULL CHECK (username ~ '^[a-z0-9._-]{3,32}$'),
    password_hash text        NOT NULL CHECK (password_hash LIKE 'scrypt$%'),
    role          text        NOT NULL CHECK (role IN ('admin', 'user')),
    all_companies boolean     NOT NULL DEFAULT false,
    companies     text[]      NOT NULL DEFAULT '{}',
    active        boolean     NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    last_login_at timestamptz,
    CONSTRAINT viewer_users_username_unique UNIQUE (username),
    CONSTRAINT viewer_users_access_shape CHECK (
        (role = 'admin' AND all_companies AND cardinality(companies) = 0)
        OR (role = 'user' AND (all_companies AND cardinality(companies) = 0 OR NOT all_companies AND cardinality(companies) > 0))
    )
);

CREATE TABLE IF NOT EXISTS reports.company_names (
    bu           text        PRIMARY KEY CHECK (bu ~ '^[a-z0-9_]{1,32}$'),
    display_name text        NOT NULL CHECK (char_length(display_name) BETWEEN 1 AND 32),
    updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS company_names_display_name_unique ON reports.company_names (lower(display_name));

REVOKE ALL ON reports.viewer_users, reports.company_names FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE ON reports.viewer_users, reports.company_names TO report_viewer;

RESET ROLE;
