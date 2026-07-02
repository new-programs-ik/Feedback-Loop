-- Ratings & Feedback module — store schema (PostgreSQL)
-- System of record for the queue, the engine's output, the PM's drafts/approvals, and the audit trail.
-- Metabase stays the source of truth for the raw ratings; this is what the workflow writes to.

-- One row per low-rated class pulled from Metabase.
create table if not exists classes (
    id            bigserial primary key,
    course        text        not null,
    cohort        text,
    instructor    text,
    topic         text,
    class_date    date,
    rating        numeric(3,2),
    num_ratings   integer,
    vimeo_link    text,
    status        text        not null default 'needs_transcript'
                  check (status in ('needs_transcript','analyzing','draft_ready','approved','sent','no_action')),
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    -- de-dupe the same class across weekly pulls
    unique (course, cohort, instructor, topic, class_date)
);

-- One row per engine run on a class (the full structured output lives in `result`).
create table if not exists analyses (
    id             bigserial primary key,
    class_id       bigint      not null references classes(id) on delete cascade,
    model          text        not null,
    result         jsonb       not null,           -- flags + feedback + reclass, exactly as the engine returns it
    reclass        text        check (reclass in ('yes','no','maybe')),
    reclass_reason text,
    tokens_in      integer,
    tokens_out     integer,
    cost_usd       numeric(8,4),
    created_at     timestamptz not null default now()
);

-- The instructor feedback draft, the PM's edits, and the approval/send trail.
create table if not exists feedback (
    id            bigserial primary key,
    class_id      bigint      not null references classes(id) on delete cascade,
    analysis_id   bigint      references analyses(id) on delete set null,
    draft_text    text        not null,            -- what the engine wrote
    edited_text   text,                            -- what the PM changed it to (edit size = an accuracy signal)
    status        text        not null default 'draft'
                  check (status in ('draft','approved','sent','discarded')),
    approved_by   text,
    approved_at   timestamptz,
    sent_at       timestamptz,
    created_at    timestamptz not null default now()
);

-- Append-only audit log of every state change (engine, n8n, or a PM).
create table if not exists audit_log (
    id          bigserial primary key,
    class_id    bigint      references classes(id) on delete set null,
    actor       text        not null,              -- 'engine' | 'n8n' | a PM email
    action      text        not null,              -- 'pulled' | 'analyzed' | 'edited' | 'approved' | 'sent' | ...
    detail      jsonb,
    created_at  timestamptz not null default now()
);

create index if not exists idx_classes_status on classes(status);
create index if not exists idx_analyses_class on analyses(class_id);
create index if not exists idx_feedback_class on feedback(class_id);
create index if not exists idx_audit_class    on audit_log(class_id);
