-- ProofPay schema. Run in Supabase -> SQL Editor. The API uses the service role; browsers only use Supabase for auth.
create extension if not exists pgcrypto;

create table public.profiles (
  id uuid primary key references auth.users on delete cascade,
  email text not null,
  name text,
  handle text unique check (handle ~ '^[a-z0-9_-]{3,24}$'),
  wallet text unique check (wallet ~ '^0x[0-9a-f]{40}$'),
  is_admin boolean not null default false,
  created_at timestamptz not null default now()
);

create function public.handle_new_user() returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, email) values (new.id, lower(new.email));
  return new;
end $$;
create trigger on_auth_user_created after insert on auth.users for each row execute function public.handle_new_user();

create table public.contracts (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null references public.profiles,
  freelancer_id uuid references public.profiles,
  freelancer_email text,
  freelancer_wallet text not null check (freelancer_wallet ~ '^0x[0-9a-f]{40}$'),
  title text not null,
  description text not null default '',
  status text not null default 'draft' check (status in ('draft','created','accepted','active','completed','cancelled')),
  escrow_id text unique,
  contract_hash text,
  hidden_tests_hash text,
  hidden_salt text,                      -- server secret until the contract completes
  total_amount numeric(38,18) not null,
  created_tx text,
  created_at timestamptz not null default now()
);
create index on public.contracts (client_id);
create index on public.contracts (freelancer_id);
create index on public.contracts (freelancer_wallet);

create table public.milestones (
  id uuid primary key default gen_random_uuid(),
  contract_id uuid not null references public.contracts on delete cascade,
  idx int not null,
  title text not null,
  amount numeric(38,18) not null check (amount > 0),
  deadline timestamptz not null,
  status text not null default 'pending' check (status in ('pending','funded','passed','disputed','released','refunded')),
  evidence_hash text,
  unique (contract_id, idx)
);

create table public.requirements (
  id uuid primary key default gen_random_uuid(),
  contract_id uuid not null references public.contracts on delete cascade,
  milestone_idx int not null,
  position int not null default 0,
  title text not null,
  criteria text not null default '',
  kind text not null check (kind in ('file_exists','file_contains','http','command')),
  spec jsonb not null,
  hidden boolean not null default false
);
create index on public.requirements (contract_id, milestone_idx);

create table public.verification_runs (
  id uuid primary key default gen_random_uuid(),
  contract_id uuid not null references public.contracts on delete cascade,
  milestone_idx int not null,
  requested_by uuid not null references public.profiles,
  repo_url text not null,
  deploy_url text,
  commit_sha text,
  status text not null default 'running' check (status in ('running','passed','failed','error')),
  passed int not null default 0,
  total int not null default 0,
  evidence_hash text,
  report jsonb,
  attest_tx text,
  error text,
  created_at timestamptz not null default now(),
  finished_at timestamptz
);
create index on public.verification_runs (contract_id, milestone_idx);
create index on public.verification_runs (evidence_hash);

create table public.chain_events (
  id bigserial primary key,
  tx_hash text not null,
  log_index int not null,
  block_number bigint not null,
  name text not null,
  escrow_id text not null,
  idx int,
  args jsonb not null,
  created_at timestamptz not null default now(),
  unique (tx_hash, log_index)
);
create index on public.chain_events (escrow_id);

create table public.indexer_state (id int primary key default 1 check (id = 1), last_block bigint not null default 0);
insert into public.indexer_state values (1, 0) on conflict do nothing;

create table public.disputes (
  id uuid primary key default gen_random_uuid(),
  contract_id uuid not null references public.contracts on delete cascade,
  milestone_idx int not null,
  opened_by uuid not null references public.profiles,
  requirement_id uuid,
  reason text not null,
  reason_hash text not null,
  status text not null default 'pending' check (status in ('pending','open','resolved')),
  freelancer_bps int,
  created_at timestamptz not null default now(),
  resolved_at timestamptz
);

create table public.audit_logs (
  id bigserial primary key,
  actor uuid,
  action text not null,
  entity text,
  entity_id text,
  meta jsonb not null default '{}',
  created_at timestamptz not null default now()
);

-- Lock everything down: only the backend (service role) reads/writes.
alter table public.profiles enable row level security;
alter table public.contracts enable row level security;
alter table public.milestones enable row level security;
alter table public.requirements enable row level security;
alter table public.verification_runs enable row level security;
alter table public.chain_events enable row level security;
alter table public.indexer_state enable row level security;
alter table public.disputes enable row level security;
alter table public.audit_logs enable row level security;
create policy "read own profile" on public.profiles for select using (auth.uid() = id);

insert into storage.buckets (id, name, public) values ('evidence', 'evidence', false) on conflict do nothing;

-- To make yourself an admin (admin dashboard):  update public.profiles set is_admin = true where email = 'you@example.com';
