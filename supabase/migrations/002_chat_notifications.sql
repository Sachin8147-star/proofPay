-- Run after 001. Adds chat, notifications and practice (dry) runs.
create table public.messages (
  id uuid primary key default gen_random_uuid(),
  contract_id uuid not null references public.contracts on delete cascade,
  sender_id uuid not null references public.profiles,
  body text not null check (char_length(body) between 1 and 2000),
  created_at timestamptz not null default now()
);
create index on public.messages (contract_id, created_at);

create table public.contract_reads (
  contract_id uuid not null references public.contracts on delete cascade,
  user_id uuid not null references public.profiles on delete cascade,
  last_read_at timestamptz not null default now(),
  primary key (contract_id, user_id)
);

create table public.notifications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles on delete cascade,
  kind text not null,
  title text not null,
  body text not null default '',
  link text,
  dedupe_key text,
  read_at timestamptz,
  created_at timestamptz not null default now(),
  unique (user_id, dedupe_key)
);
create index on public.notifications (user_id, created_at desc);

alter table public.verification_runs add column dry_run boolean not null default false;

alter table public.messages enable row level security;
alter table public.contract_reads enable row level security;
alter table public.notifications enable row level security;
