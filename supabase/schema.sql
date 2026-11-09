-- Запусти целиком в Supabase -> SQL Editor. Таблицы магазина (products/projects) не трогаются.

create table if not exists lb_settings (
  key   text primary key,
  value jsonb not null
);

create table if not exists lb_queries (
  id         bigint generated always as identity primary key,
  q          text unique not null,
  active     boolean not null default true,
  hits       int not null default 0,
  last_run   timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists lb_seen (
  key        text primary key,
  created_at timestamptz not null default now()
);

create table if not exists lb_leads (
  id          bigint generated always as identity primary key,
  chat_id     bigint,
  msg_id      bigint,
  chat_title  text,
  link        text,
  author      text,
  author_url  text,
  text        text,
  score       int,
  match       text,
  reason      text,
  reply       text,
  query       text,
  status      text not null default 'new',   -- new | work | won | lost | bad
  msg_date    timestamptz,
  created_at  timestamptz not null default now(),
  unique (chat_id, msg_id)
);
create index if not exists lb_leads_status_idx  on lb_leads (status, created_at desc);
create index if not exists lb_leads_created_idx on lb_leads (created_at desc);

create table if not exists lb_runs (
  id         bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  trigger    text,
  queries    int default 0,
  found      int default 0,
  fresh      int default 0,
  passed     int default 0,
  duplicates int default 0,
  quota_skipped int default 0,
  llm        int default 0,
  leads      int default 0,
  errors     int default 0,
  ms         int default 0,
  error      text
);
create index if not exists lb_runs_created_idx on lb_runs (created_at desc);

-- Замок: не даёт двум запускам одновременно использовать одну Telegram-сессию
create table if not exists lb_lock (
  id           int primary key,
  locked_until timestamptz not null default 'epoch'
);
insert into lb_lock (id) values (1) on conflict do nothing;

-- Доступ только через service_role (он обходит RLS). Для anon/authenticated всё закрыто.
alter table lb_settings enable row level security;
alter table lb_queries  enable row level security;
alter table lb_seen     enable row level security;
alter table lb_leads    enable row level security;
alter table lb_runs     enable row level security;
alter table lb_lock     enable row level security;
