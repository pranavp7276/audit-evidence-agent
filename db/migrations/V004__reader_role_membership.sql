-- Managed Postgres services (Neon, Supabase, RDS) give the application's login a role that is not a superuser.
-- Such a role can only `SET ROLE agent_reader` (the agent's read-only mode, agent/db.py) if it is a member of it
-- with the SET option. V001 creates agent_reader but cannot grant that, so grant it here. Safe to re-run, and a
-- no-op where the owner is a superuser.
DO $$
BEGIN
    BEGIN
        EXECUTE format('GRANT agent_reader TO %I WITH SET TRUE, INHERIT FALSE', current_user);  -- PostgreSQL 16+
    EXCEPTION WHEN OTHERS THEN
        BEGIN
            EXECUTE format('GRANT agent_reader TO %I', current_user);                            -- PostgreSQL 15 and older
        EXCEPTION WHEN OTHERS THEN
            NULL;
        END;
    END;
END $$;
