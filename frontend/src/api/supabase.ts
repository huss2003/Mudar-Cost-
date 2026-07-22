import { createClient } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || 'https://pecnshwflkwpnwiskgmg.supabase.co';
const supabaseKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY || 'sb_publishable_GMkHBBICoUbKeg5W1UGtFg_Y-_xU0yb';

export const supabase = createClient(supabaseUrl, supabaseKey);

export default supabase;
