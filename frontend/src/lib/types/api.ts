// ─── Company ────────────────────────────────────────────────────────────────
export interface Company {
  id: string;
  name: string;
  email: string;
  industry: string;
  website?: string;
  description?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CompanyCreateResponse extends Company {
  api_key: string;
}

// ─── Product ─────────────────────────────────────────────────────────────────
export type ProductStatus =
  | 'pending'
  | 'processing'
  | 'motivations_generated'
  | 'discovering'
  | 'nlp_processing'
  | 'ocean_scoring'
  | 'matching'
  | 'ranking'
  | 'ranked'
  | 'failed';

export type PriceRange = 'budget' | 'standard' | 'premium';

export interface Product {
  id: string;
  company_id: string;
  name: string;
  description: string;
  category: string;
  subcategory?: string;
  price_range: PriceRange;
  target_location?: string;
  target_city?: string;
  target_country?: string;
  keywords: string[];
  status: ProductStatus;
  pipeline_step: number;
  error_message?: string;
  created_at: string;
  updated_at: string;
}

export interface ProductStatusResponse {
  id: string;
  status: ProductStatus;
  pipeline_step: number;
  error_message?: string;
  updated_at: string;
}

export interface ProductCreateInput {
  name: string;
  description: string;
  category: string;
  subcategory?: string;
  price_range: PriceRange;
  target_location?: string;
  target_city?: string;
  target_country?: string;
  keywords: string[];
}

// ─── Dashboard ───────────────────────────────────────────────────────────────
export interface DashboardProductItem {
  product_id: string;
  name: string;
  status: ProductStatus;
  pipeline_step: number;
  discovered_users: number;
  ranked_leads: number;
  hot_leads: number;
}

export interface ActivityEvent {
  event_type: string;
  product_id: string;
  product_name: string;
  detail: string;
  occurred_at: string;
}

export interface DashboardOverview {
  total_products: number;
  total_discovered_users: number;
  hot_leads_count: number;
  warm_leads_count: number;
  active_pipeline_jobs: number;
  products: DashboardProductItem[];
  recent_activity: ActivityEvent[];
  generated_at: string;
}

// ─── Motivations ─────────────────────────────────────────────────────────────
export interface OceanProfile {
  openness: number;
  conscientiousness: number;
  extraversion: number;
  agreeableness: number;
  emotional_stability: number;
  interest_tags: string[];
  search_keywords: string[];
  hashtags: string[];
}

export interface MotivationCategory {
  id: string;
  product_id: string;
  name: string;
  description: string;
  sort_order: number;
  ocean_profile: OceanProfile;
  created_at: string;
}

export interface MotivationsResponse {
  product_id: string;
  total: number;
  categories: MotivationCategory[];
}

// ─── Discovery ───────────────────────────────────────────────────────────────
export type DiscoveryJobStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface DiscoveryJob {
  id: string;
  product_id: string;
  provider_name: string;
  status: DiscoveryJobStatus;
  sources: string[];
  max_users: number;
  users_discovered: number;
  users_content_collected: number;
  error_message?: string;
  started_at?: string;
  completed_at?: string;
  created_at: string;
}

export interface DiscoveredUser {
  id: string;
  discovery_job_id: string;
  product_id: string;
  platform: string;
  source_provider: string;
  username: string;
  display_name?: string;
  bio?: string;
  location?: string;
  location_confidence?: number;
  follower_count?: number;
  post_count?: number;
  profile_url?: string;
  content_collected: boolean;
  nlp_processed: boolean;
  ocean_scored: boolean;
  matched: boolean;
  created_at: string;
}

export interface DiscoveredUsersResponse {
  product_id: string;
  job_id?: string;
  total: number;
  page: number;
  limit: number;
  users: DiscoveredUser[];
}

export interface UserContent {
  id: string;
  user_id: string;
  content_type: string;
  content_text: string;
  source_url?: string;
  engagement?: number;
  posted_at?: string;
  collected_at: string;
}

export interface ProviderStatus {
  ok: boolean;
  provider: string;
  detail: string;
  mock_mode: boolean;
  credentials_configured: boolean;
}

// ─── NLP ─────────────────────────────────────────────────────────────────────
export interface NlpStatus {
  product_id: string;
  total_users: number;
  nlp_processed: number;
  nlp_pending: number;
  nlp_failed: number;
  progress_pct: number;
}

export interface NlpResult {
  id: string;
  user_id: string;
  empath_scores: Record<string, number>;
  bertopic_topics: string[];
  spacy_entities: string[];
  interest_tags: string[];
  keyword_frequency: Record<string, number>;
  vocabulary_richness: number;
  avg_sentence_length: number;
  total_tokens: number;
  created_at: string;
  updated_at: string;
}

// ─── OCEAN ────────────────────────────────────────────────────────────────────
export interface OceanStatus {
  product_id: string;
  total_users: number;
  ocean_scored: number;
  ocean_pending: number;
  progress_pct: number;
}

export interface OceanScore {
  id: string;
  user_id: string;
  openness: number;
  conscientiousness: number;
  extraversion: number;
  agreeableness: number;
  neuroticism: number;
  confidence: number;
  scoring_method: string;
  reasoning: {
    openness: string;
    conscientiousness: string;
    extraversion: string;
    agreeableness: string;
    neuroticism: string;
  };
  created_at: string;
  updated_at: string;
}

// ─── Leads ────────────────────────────────────────────────────────────────────
export type LeadTier = 'Hot' | 'Warm' | 'Cold';

export interface Lead {
  rank: number;
  user_id: string;
  username: string;
  display_name?: string;
  platform: string;
  profile_url?: string;
  location?: string;
  follower_count?: number;
  best_motivation_category: string;
  motivation_category_id: string;
  final_score: number;
  ocean_score: number;
  embedding_score: number;
  interest_score: number;
  confidence: number;
  reasoning: string[];
}

export interface LeadsResponse {
  total_leads: number;
  page: number;
  page_size: number;
  total_pages: number;
  leads: Lead[];
}

export interface CategoryScore {
  motivation_category_id: string;
  motivation_category: string;
  final_score: number;
  ocean_score: number;
  embedding_score: number;
  interest_score: number;
  confidence: number;
  reasoning: string[];
}

export interface LeadDetail {
  user_id: string;
  username: string;
  display_name?: string;
  platform: string;
  profile_url?: string;
  location?: string;
  location_confidence?: number;
  follower_count?: number;
  best_match: {
    rank: number;
    motivation_category: string;
    final_score: number;
    ocean_score: number;
    embedding_score: number;
    interest_score: number;
    confidence: number;
    reasoning: string[];
  };
  all_category_scores: CategoryScore[];
}

export interface LeadsSummary {
  total_ranked: number;
  avg_score: number;
  top_score: number;
  top_category: string;
}

export interface MatchStatus {
  product_id: string;
  total_users: number;
  matched: number;
  ranked: number;
  pending: number;
  progress_pct: number;
}

// ─── Analytics ───────────────────────────────────────────────────────────────
export interface ScoreDistribution {
  count: number;
  min: number;
  max: number;
  mean: number;
  median: number;
  std_dev: number;
  histogram: Array<{ range: string; count: number }>;
}

export interface QualitySummary {
  passing_all_filters: number;
  pct_passing: number;
  flagged_low_confidence: number;
  flagged_heuristic_ocean: number;
  flagged_insufficient_content: number;
  recommended_min_confidence: number;
}

export interface LeadAnalytics {
  product_id: string;
  total_ranked: number;
  quality_summary: QualitySummary;
  final_score_distribution: ScoreDistribution;
  confidence_distribution: ScoreDistribution;
  ocean_score_distribution: ScoreDistribution;
  embedding_score_distribution: ScoreDistribution;
  interest_score_distribution: ScoreDistribution;
  top_motivation_categories: Array<{ category: string; count: number }>;
  calibration_notes: string[];
}

export interface LeadInspect {
  user_id: string;
  username: string;
  display_name?: string;
  platform: string;
  profile_url?: string;
  location?: string;
  location_confidence?: number;
  follower_count?: number;
  content_quality: {
    total_tokens: number;
    vocabulary_richness: number;
    avg_sentence_length: number;
    num_content_items: number;
  };
  ocean_profile: {
    openness: number;
    conscientiousness: number;
    extraversion: number;
    agreeableness: number;
    neuroticism: number;
    confidence: number;
    scoring_method: string;
  };
  interest_tags: string[];
  top_empath_categories: Array<{ category: string; score: number }>;
  content_samples: Array<{
    content_type: string;
    content_text: string;
    engagement?: number;
    source_url?: string;
  }>;
  best_match: {
    rank: number;
    motivation_category: string;
    final_score: number;
    ocean_score: number;
    embedding_score: number;
    interest_score: number;
    confidence: number;
    reasoning: string[];
  };
  all_category_scores: CategoryScore[];
  quality_flags: string[];
  passes_quality_filter: boolean;
}

// ─── Ollama ───────────────────────────────────────────────────────────────────
export interface OllamaStatus {
  ok: boolean;
  provider: string;
  detail: string;
  models: string[];
  use_mock_llm: boolean;
  fallback_on_error: boolean;
}

// ─── Demo ─────────────────────────────────────────────────────────────────────
export interface DemoSetupResponse {
  status: string;
  product_id: string;
  api_key: string;
  company_id: string;
}
