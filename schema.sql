-- ============================================================
-- Forecast Tracker — Supabase Şeması
-- Supabase → SQL Editor'da çalıştır.
-- ============================================================

-- Eğer eski bir forecast_entries tablosu varsa önce silmek istersen:
-- drop table if exists public.forecast_entries cascade;

-- ============================================================
-- Ana tablo: forecast_entries
-- ============================================================
create table if not exists public.forecast_entries (
    id              bigserial primary key,

    -- Kim? Ne tür katılımcı?
    entry_type      text not null check (entry_type in ('survey', 'person', 'institution')),
    source_name     text not null,                 -- "Reuters", "Haluk Bürümcekçi", "Ak Yatırım" ...

    -- Ne tahmin ediyor? Hangi dönem için?
    forecast_type   text not null,                 -- 'ppk', 'tufe_aylik', 'tufe_yillik', 'yilsonu_enf', ...
    target_period   date not null,                 -- hedef ayın ilk günü: 2026-04-01

    -- Değerler
    -- person/institution tek değer verir → value kullanılır
    -- survey ise median/min/max kullanılır (value null kalır)
    value           numeric,
    median          numeric,
    min_val         numeric,
    max_val         numeric,
    n_participants  integer,                       -- sadece survey için

    -- Ekstra
    source_link     text,
    note            text,

    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

-- ============================================================
-- Revizyon mantığı: aynı gün aynı (kaynak, tür, hedef) için TEK satır
-- Farklı günde yeni satır (geçmiş korunur)
-- ============================================================
-- Bunun için "tarih kısmı" üzerinden unique index kullanıyoruz.
create unique index if not exists forecast_entries_daily_unique
    on public.forecast_entries (
        source_name,
        forecast_type,
        target_period,
        (created_at::date)
    );

-- ============================================================
-- Performans indeksleri
-- ============================================================
create index if not exists forecast_entries_target_idx   on public.forecast_entries (target_period);
create index if not exists forecast_entries_type_idx     on public.forecast_entries (forecast_type);
create index if not exists forecast_entries_source_idx   on public.forecast_entries (source_name);
create index if not exists forecast_entries_entry_idx    on public.forecast_entries (entry_type);
create index if not exists forecast_entries_updated_idx  on public.forecast_entries (updated_at desc);

-- ============================================================
-- updated_at otomatik güncelleme trigger'ı
-- ============================================================
create or replace function public.set_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists forecast_entries_set_updated_at on public.forecast_entries;
create trigger forecast_entries_set_updated_at
    before update on public.forecast_entries
    for each row
    execute function public.set_updated_at();

-- ============================================================
-- Yardımcı tablo: forecast_types (UI için)
-- Hangi tahmin türleri var, Türkçe adları ne, hangi sırada?
-- Bot ve dashboard buradan okur, yeni tür eklemek için sadece
-- bu tabloya satır eklemek yeterli.
-- ============================================================
create table if not exists public.forecast_types (
    code         text primary key,
    label_tr     text not null,
    unit         text not null default '%',
    realized_col text,             -- EVDS/BIS karşılığı: 'Aylık TÜFE', 'Yıllık TÜFE', 'PPK Faizi' veya null
    sort_order   integer not null default 0
);

insert into public.forecast_types (code, label_tr, unit, realized_col, sort_order) values
    ('ppk',           'PPK Politika Faizi',    '%', 'PPK Faizi',   10),
    ('tufe_aylik',    'Aylık TÜFE',            '%', 'Aylık TÜFE',  20),
    ('tufe_yillik',   'Yıllık TÜFE',           '%', 'Yıllık TÜFE', 30),
    ('yilsonu_enf',   'Yıl Sonu Enflasyon',    '%', null,          40),
    ('yilsonu_faiz',  'Yıl Sonu Politika Faizi','%', null,          50)
on conflict (code) do nothing;

-- ============================================================
-- Yardımcı tablo: anket listesi (bot için dropdown)
-- ============================================================
create table if not exists public.surveys (
    name     text primary key,
    active   boolean not null default true,
    sort_order integer not null default 0
);

insert into public.surveys (name, sort_order) values
    ('Reuters', 10),
    ('Bloomberg HT', 20),
    ('AA Finans', 30),
    ('Matriks', 40),
    ('ForInvest', 50),
    ('CNBC-E', 60),
    ('TCMB Piyasa Katılımcıları', 70)
on conflict (name) do nothing;

-- ============================================================
-- RLS (Row Level Security)
-- Streamlit/Bot service_role key kullanıyorsa kapalı bırakılabilir.
-- Public read istersen policy aç:
-- ============================================================
-- alter table public.forecast_entries enable row level security;
-- create policy "public read" on public.forecast_entries for select using (true);
