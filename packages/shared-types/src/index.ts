/**
 * Types shared between the Atlas API and the web app.
 *
 * Money and ratios cross the wire as STRINGS, not numbers. The backend
 * computes in Decimal, and turning "150000.00" into a JavaScript float on the
 * way in would reintroduce exactly the imprecision the engine exists to avoid.
 * Parse to a number only at the point of display.
 *
 * `null` means unknown or undefined — never zero. A null DSCR is a property
 * with no debt; a null cash-on-cash is a deal with no cash left in it. The UI
 * renders these as "—", never as 0.
 */

/** A decimal value serialised as a string, e.g. "150000.00" or "0.2229". */
export type Money = string;
export type Ratio = string;

export type Confidence = "HIGH" | "MEDIUM" | "LOW";

/** The epistemic status of a claim. Atlas never blurs these together. */
export type Assertion = "FACT" | "ESTIMATE" | "INFERENCE" | "UNKNOWN";

export type Verdict = "PURSUE" | "INVESTIGATE" | "PASS" | "HUMAN_REVIEW_REQUIRED";

export type RiskSeverity = "INFO" | "WARNING" | "CRITICAL";

export type StrategyKey =
  | "wholesale"
  | "flip"
  | "buy_hold"
  | "brrrr"
  | "seller_finance";

export type ValueBasis =
  | "comparable_sales"
  | "automated_valuation"
  | "appraisal"
  | "broker_opinion"
  | "list_price"
  | "user_entered"
  | "unknown";

export type RehabBasis =
  | "contractor_bid"
  | "detailed_scope"
  | "walkthrough"
  | "per_sqft_estimate"
  | "user_entered"
  | "unknown";

export type RentBasis =
  | "rent_roll"
  | "lease_in_place"
  | "rental_comps"
  | "automated_estimate"
  | "user_entered"
  | "unknown";

export interface Criterion {
  name: string;
  label: string;
  target: Money | null;
  actual: Money | null;
  met: boolean;
  unit: "currency" | "percent" | "ratio" | "months";
}

export interface StrategyResult {
  strategy: StrategyKey;
  viable: boolean;
  profit: Money | null;
  cash_required: Money | null;
  roi: Ratio | null;
  annualized_roi: Ratio | null;
  monthly_cash_flow: Money | null;
  annual_cash_flow: Money | null;
  equity_created: Money | null;
  dscr: Ratio | null;
  cap_rate: Ratio | null;
  cash_on_cash: Ratio | null;
  max_purchase_price: Money | null;
  time_to_liquidity_months: number | null;
  meets_criteria: boolean;
  criteria: Criterion[];
  confidence: Confidence;
  confidence_reasons: string[];
  warnings: string[];
  missing_inputs: string[];
  not_viable_reason: string | null;
  detail: Record<string, unknown>;
}

export interface StrategyScore {
  strategy: StrategyKey;
  score: Ratio;
  components: Record<string, Ratio>;
  meets_criteria: boolean;
  penalty_applied: Ratio;
}

export interface RiskFlag {
  code: string;
  label: string;
  severity: RiskSeverity;
  detail: string;
  blocks_pursue: boolean;
  source: string;
}

export interface ScoreComponent {
  name: string;
  label: string;
  weight: Ratio;
  score: Ratio | null;
  /** False when Atlas cannot assess this category. It is excluded, not guessed. */
  assessed: boolean;
  reason: string;
}

export interface DealScore {
  score: Ratio | null;
  verdict: Verdict;
  verdict_reason: string;
  /** Share of the scoring rubric that could actually be assessed. */
  coverage: Ratio;
  components: ScoreComponent[];
  risk_flags: RiskFlag[];
  risk_score: Ratio;
  requires_human_review: boolean;
  confidence: Confidence;
}

export interface Claim {
  label: string;
  value: string | null;
  assertion: Assertion;
  source: string | null;
}

export interface AgentOutput {
  agent: string;
  provider: string;
  model: string | null;
  generated_at: string;
  /** True when composed from the engine's numbers with no model involved. */
  deterministic: boolean;
  summary: string;
  claims: Claim[];
  narrative: string[];
  challenges: string[];
  questions: string[];
  risks: string[];
  missing_information: string[];
  sources: string[];
  disclaimer: string;
}

export interface AiAnalysis {
  research: AgentOutput;
  underwriting: AgentOutput;
  strategist: AgentOutput;
}

/**
 * Capital efficiency — how hard each dollar of capital works, and for how long
 * it is stuck. Provisional and additive: it is reported next to the ranking and
 * does NOT feed the ranking or the deal score.
 *
 * `inputs` and `formula` exist so a user can recompute the score by hand.
 */
export interface CapitalEfficiency {
  strategy: StrategyKey;
  /** Transactional profit lands once at exit; annual income repeats yearly. */
  horizon: "transactional" | "annual_income";
  horizon_months: number | null;
  capital_deployed: Money | null;
  profit: Money | null;
  return_on_capital: Ratio | null;
  /** Times per year the capital could turn over. */
  capital_velocity: Ratio | null;
  annualized_return_on_capital: Ratio | null;
  profit_per_1k_deployed: Money | null;
  capital_recycled_percent: Ratio | null;
  share_of_available_capital: Ratio | null;
  /** Affordability, kept separate from efficiency. Null means unknown. */
  within_capital_limit: boolean | null;
  capital_ceiling: Money | null;
  capital_free: boolean;
  computable: boolean;
  score: Ratio | null;
  score_target: Ratio | null;
  formula: string;
  notes: string[];
  inputs: Record<string, string | null>;
  confidence: Confidence;
  provisional: boolean;
}

export type RiskTolerance = "conservative" | "moderate" | "aggressive";

export type CapitalEfficiencyPreference =
  | "maximize_velocity"
  | "balanced"
  | "maximize_absolute_profit";

/**
 * Describes the INVESTOR, not the deal — capital available, return
 * requirements, risk tolerance. Deliberately separate from the buy box.
 *
 * A null figure means unstated, never zero. An investor who has not said what
 * capital they have does not have no capital.
 */
export interface InvestorProfile {
  name: string | null;
  available_capital: Money | null;
  max_capital_deployment: Money | null;
  preferred_minimum_cash_flow: Money | null;
  minimum_roi: Ratio | null;
  max_cash_left_in_deal: Money | null;
  minimum_wholesale_assignment: Money | null;
  risk_tolerance: RiskTolerance;
  capital_efficiency_preference: CapitalEfficiencyPreference;
  preferred_strategies: StrategyKey[];
}

export interface AnalysisResponse {
  id?: string | null;
  property_id?: string | null;
  name?: string | null;
  inputs: Record<string, unknown>;
  strategies: Record<StrategyKey, StrategyResult>;
  ranking: StrategyScore[];
  recommended_strategy: StrategyKey | null;
  alternative_strategy: StrategyKey | null;
  rationale: string[];
  viable_exit_count: number;
  overall_confidence: Confidence;
  missing_information: string[];
  scoring: DealScore;
  capital_efficiency: Record<StrategyKey, CapitalEfficiency>;
  ai_analysis: AiAnalysis | null;
  engine_version: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface Evidence {
  arv_basis: ValueBasis;
  comp_count: number;
  average_comp_similarity: Ratio | null;
  average_comp_age_days: number | null;
  rehab_basis: RehabBasis;
  rent_basis: RentBasis;
  inspection_completed: boolean;
  title_reviewed: boolean;
  property_visited: boolean;
}

export interface AnalysisRequest {
  purchase_price?: Money | null;
  arv?: Money | null;
  arv_low?: Money | null;
  arv_high?: Money | null;
  rehab?: Money | null;
  rehab_low?: Money | null;
  rehab_high?: Money | null;
  monthly_rent?: Money | null;
  as_is_value?: Money | null;
  listing_price?: Money | null;
  property_facts?: Record<string, unknown> | null;
  evidence?: Partial<Evidence> | null;
  assumptions?: Record<string, unknown> | null;
  investor_profile?: Partial<InvestorProfile> | null;
  risk_flags?: string[];
  include_ai?: boolean;
  name?: string | null;
  change_reason?: string | null;
}

export type PropertyStatus =
  | "prospect"
  | "analyzing"
  | "offer_made"
  | "under_contract"
  | "closed"
  | "rehabbing"
  | "listed"
  | "rented"
  | "sold"
  | "dead";

export interface Property {
  id: string;
  owner_id: string;
  address: string;
  city: string | null;
  state: string | null;
  zip_code: string | null;
  county: string | null;
  parcel_apn: string | null;
  property_type: string | null;
  bedrooms: Money | null;
  bathrooms: Money | null;
  square_feet: Money | null;
  lot_size: Money | null;
  year_built: number | null;
  property_status: PropertyStatus;
  listing_price: Money | null;
  estimated_value: Money | null;
  estimated_rent: Money | null;
  days_on_market: number | null;
  latitude: Money | null;
  longitude: Money | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface PropertySummary {
  id: string;
  address: string;
  city: string | null;
  state: string | null;
  zip_code: string | null;
  property_type: string | null;
  property_status: PropertyStatus;
  bedrooms: Money | null;
  bathrooms: Money | null;
  square_feet: Money | null;
  estimated_value: Money | null;
  updated_at: string;
  latest_analysis_id: string | null;
  deal_score: Ratio | null;
  verdict: Verdict | null;
  recommended_strategy: StrategyKey | null;
  profit: Money | null;
  cash_required: Money | null;
  confidence: Confidence | null;
  requires_human_review: boolean;
}

export interface AnalysisSummary {
  id: string;
  property_id: string;
  name: string | null;
  recommended_strategy: StrategyKey | null;
  verdict: Verdict | null;
  deal_score: Ratio | null;
  profit: Money | null;
  cash_required: Money | null;
  monthly_cash_flow: Money | null;
  confidence: Confidence | null;
  requires_human_review: boolean;
  created_at: string;
  updated_at: string;
}

export interface AssumptionAudit {
  id: string;
  analysis_id: string;
  field_path: string;
  field_label: string | null;
  previous_value: string | null;
  new_value: string | null;
  reason: string | null;
  changed_by: string;
  changed_by_email: string | null;
  changed_at: string;
}

export type LeadType =
  | "FSBO"
  | "expired"
  | "vacant"
  | "absentee"
  | "high_equity"
  | "tax_delinquent"
  | "probate"
  | "code_violation"
  | "pre_foreclosure"
  | "tired_landlord"
  | "price_reduction"
  | "long_DOM"
  | "off_market"
  | "other";

export interface Lead {
  id: string;
  property_id: string;
  lead_type: LeadType;
  source: string | null;
  status: string;
  lead_score: Money | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface Comp {
  id: string;
  property_id: string;
  address: string;
  distance_miles: Money | null;
  sale_price: Money | null;
  sale_date: string | null;
  bedrooms: Money | null;
  bathrooms: Money | null;
  square_feet: Money | null;
  year_built: number | null;
  property_type: string | null;
  condition: string | null;
  price_per_square_foot: Money | null;
  similarity_score: Ratio | null;
  source: string | null;
  created_at: string;
}

export interface Offer {
  id: string;
  property_id: string;
  offer_amount: Money;
  offer_type: string | null;
  terms: string | null;
  status: string;
  date_submitted: string | null;
  expiration_date: string | null;
  notes: string | null;
  created_at: string;
}

export interface Communication {
  id: string;
  property_id: string;
  contact_name: string | null;
  contact_role: string | null;
  communication_type: string;
  direction: string;
  occurred_at: string;
  notes: string | null;
  outcome: string | null;
  follow_up_at: string | null;
  created_at: string;
}

export interface RehabProject {
  id: string;
  property_id: string;
  estimated_rehab: Money | null;
  actual_rehab: Money | null;
  materials_cost: Money | null;
  labor_cost: Money | null;
  scope: string | null;
  start_date: string | null;
  completion_date: string | null;
  status: string;
  notes: string | null;
  variance: Money | null;
  created_at: string;
}

export interface UserSettings {
  id: string;
  email: string | null;
  display_name: string | null;
  default_assumptions: Record<string, any>;
  investor_profile: InvestorProfile;
  provisional_defaults_note: string;
  provisional_profile_note: string;
}

export interface PipelineBucket {
  status: string;
  count: number;
}

export interface ActivityEntry {
  id: string;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  summary: string | null;
  occurred_at: string;
}

export interface Dashboard {
  property_count: number;
  analyzed_count: number;
  pipeline: PipelineBucket[];
  top_opportunities: PropertySummary[];
  needs_human_review: PropertySummary[];
  projected_wholesale_revenue: Money;
  projected_flip_profit: Money;
  projected_monthly_cash_flow: Money;
  portfolio_equity: Money;
  follow_ups: Communication[];
  recent_activity: ActivityEntry[];
}

export interface ProviderStatus {
  name: string;
  configured: boolean;
  capabilities: string[];
  detail: string;
}

export interface SystemStatus {
  status: string;
  environment: string;
  engine_version: string;
  database: string;
  authentication: string;
  ai_provider: ProviderStatus;
  data_providers: ProviderStatus[];
}

export const STRATEGY_LABELS: Record<StrategyKey, string> = {
  wholesale: "Wholesale",
  flip: "Fix & Flip",
  buy_hold: "Buy & Hold",
  brrrr: "BRRRR",
  seller_finance: "Seller Finance",
};

export const STRATEGY_ORDER: StrategyKey[] = [
  "wholesale",
  "flip",
  "buy_hold",
  "brrrr",
  "seller_finance",
];
