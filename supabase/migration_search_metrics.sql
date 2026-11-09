-- Run in Supabase SQL Editor before deploying this version; safe to re-run.
alter table lb_runs
  add column if not exists duplicates int not null default 0,
  add column if not exists quota_skipped int not null default 0,
  add column if not exists qwen_rejected int not null default 0,
  add column if not exists low_score int not null default 0;