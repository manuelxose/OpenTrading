"""database-level immutability for the governance trail

Revision ID: 0009_audit_trail_immutability
Revises: 0008_live_auto

``audit_events`` and ``system_events`` are the append-only governance trail
(architecture §14, ADR-0025). Immutability was previously a code convention
(INSERT-only sinks); this migration enforces it at the database level so no
compromised application role can rewrite history:

- UPDATE/DELETE/TRUNCATE are revoked from PUBLIC and the least-privilege roles
  (``ot_app``, ``ot_readonly``) when they exist;
- BEFORE UPDATE OR DELETE triggers raise unconditionally for every writer,
  including the table owner, so append-only holds even against privilege bugs.

The downgrade restores the previous permissive state.
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0009_audit_trail_immutability"
down_revision = "0008_live_auto"
branch_labels = None
depends_on = None


def _immutable_trigger_sql(table: str) -> str:
    return f"""
        CREATE OR REPLACE FUNCTION {table}_append_only()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION '{table} is append-only: % is forbidden', TG_OP
                USING ERRCODE = 'read_only_sql_transaction';
        END;
        $$;

        DROP TRIGGER IF EXISTS {table}_no_update_or_delete ON {table};
        CREATE TRIGGER {table}_no_update_or_delete
        BEFORE UPDATE OR DELETE ON {table}
        FOR EACH ROW EXECUTE FUNCTION {table}_append_only();
    """


def upgrade() -> None:
    for table in ("audit_events", "system_events"):
        op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON {table} FROM PUBLIC")
        op.execute(
            f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ot_app') THEN
                    REVOKE UPDATE, DELETE, TRUNCATE ON {table} FROM ot_app;
                END IF;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ot_readonly') THEN
                    REVOKE UPDATE, DELETE, TRUNCATE ON {table} FROM ot_readonly;
                END IF;
            END
            $$;
            """
        )
        op.execute(_immutable_trigger_sql(table))


def downgrade() -> None:
    for table in ("audit_events", "system_events"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_update_or_delete ON {table}")
        op.execute(f"DROP FUNCTION IF EXISTS {table}_append_only()")
        op.execute(f"GRANT UPDATE, DELETE ON {table} TO PUBLIC")
        op.execute(
            f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ot_app') THEN
                    GRANT UPDATE, DELETE ON {table} TO ot_app;
                END IF;
            END
            $$;
            """
        )
