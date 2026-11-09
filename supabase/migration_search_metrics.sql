-- Run once in Supabase SQL Editor before deploying this version.
alter table lb_runs
  add column if not exists duplicates int not null default 0,
  add column if not exists quota_skipped int not null default 0;