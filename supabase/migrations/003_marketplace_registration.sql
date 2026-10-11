-- Run after 002. Adds: registration details, open jobs board, product/site delivery, zip submissions, pre-acceptance chat threads.

-- ---------- registration ----------
alter table public.profiles
  add column first_name text,
  add column last_name text,
  add column phone text check (phone is null or phone ~ '^\+?[0-9 ()-]{7,20}$'),
  add column heard_from text,
  add column heard_other text;

-- Store the sign-up form (sent as user metadata) and never let a taken username break sign-up.
create or replace function public.handle_new_user() returns trigger language plpgsql security definer set search_path = public as $$
declare
  md jsonb := coalesce(new.raw_user_meta_data, '{}'::jsonb);
  h text := lower(nullif(md->>'handle', ''));
  fn text := nullif(left(md->>'first_name', 60), '');
  ln text := nullif(left(md->>'last_name', 60), '');
begin
  if h is not null and h !~ '^[a-z0-9_-]{3,24}$' then h := null; end if;
  begin
    insert into public.profiles (id, email, handle, first_name, last_name, name, phone, heard_from, heard_other)
    values (new.id, lower(new.email), h, fn, ln, nullif(trim(coalesce(fn, '') || ' ' || coalesce(ln, '')), ''),
            case when md->>'phone' ~ '^\+?[0-9 ()-]{7,20}$' then md->>'phone' end,
            left(md->>'heard_from', 40), left(md->>'heard_other', 120));
  exception when unique_violation then
    insert into public.profiles (id, email, first_name, last_name, name, heard_from, heard_other)
    values (new.id, lower(new.email), fn, ln, nullif(trim(coalesce(fn, '') || ' ' || coalesce(ln, '')), ''),
            left(md->>'heard_from', 40), left(md->>'heard_other', 120));
  end;
  return new;
end $$;

-- ---------- contracts: funded up front, named or open ----------
alter table public.contracts alter column freelancer_wallet drop not null;
alter table public.contracts drop constraint contracts_status_check;
alter table public.contracts add constraint contracts_status_check
  check (status in ('draft','open','created','accepted','active','completed','cancelled'));
alter table public.contracts
  add column is_open boolean not null default false,           -- true: anyone may accept (no username given)
  add column freelancer_handle text,
  add column cancel_requested boolean not null default false,
  add column idea text not null default '',                    -- the buyer's own words
  add column ai_notes jsonb;                                    -- what the AI understood / suggested / how it checks
create index on public.contracts (status, is_open);

-- ---------- milestones: delivery type, own review window ----------
alter table public.milestones
  add column delivery_type text not null default 'software' check (delivery_type in ('software','live_site','product')),
  add column window_secs int not null default 172800 check (window_secs between 3600 and 2592000),
  add column review_ends_at timestamptz,
  add column shipment jsonb;                                    -- {carrier, tracking, note, shipped_at} for physical products

-- ---------- requirements: AI checks and manual confirmation ----------
alter table public.requirements drop constraint requirements_kind_check;
alter table public.requirements add constraint requirements_kind_check
  check (kind in ('file_exists','file_contains','http','command','ai_review','manual'));

-- ---------- submissions: zip / site / shipment, not only GitHub ----------
alter table public.verification_runs alter column repo_url drop not null;
alter table public.verification_runs
  add column source text not null default 'github' check (source in ('github','zip','site','shipment')),
  add column file_name text,
  add column file_path text,                                    -- storage path of the delivered zip
  add column ai_summary text;

-- ---------- chat: pre-acceptance threads between the poster and one interested worker ----------
alter table public.messages add column thread_user uuid references public.profiles;
create index on public.messages (contract_id, thread_user, created_at);
