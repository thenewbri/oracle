-- Run this once in the Oracle Supabase project to create the recommendations table

CREATE TABLE oracle_recommendations (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    ticker text NOT NULL,
    thesis text NOT NULL,
    put_details jsonb,
    source text,
    macro_context text,
    created_at timestamptz DEFAULT now()
);
