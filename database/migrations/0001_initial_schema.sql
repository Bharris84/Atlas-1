-- Atlas initial schema (PostgreSQL / Supabase)
--
-- Generated from the SQLAlchemy models in apps/api/atlas_api/models.py, which
-- remain the source of truth. Regenerate with `make migration`.
--
-- Conventions:
--   * Money is NUMERIC(14,2) and rates are NUMERIC(12,6). No floats, ever.
--   * NULL means unknown. It never means zero.
--   * owner_id is the Supabase Auth user id (auth.users.id).

BEGIN;

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE activity_log (
	id UUID NOT NULL, 
	actor_id UUID, 
	actor_email VARCHAR(320), 
	action VARCHAR(80) NOT NULL, 
	entity_type VARCHAR(60), 
	entity_id UUID, 
	summary VARCHAR(500), 
	occurred_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_activity_log_entity_id ON activity_log (entity_id);

CREATE INDEX ix_activity_log_action ON activity_log (action);

CREATE INDEX ix_activity_log_actor_id ON activity_log (actor_id);

CREATE INDEX ix_activity_log_occurred_at ON activity_log (occurred_at);

CREATE TABLE properties (
	id UUID NOT NULL, 
	owner_id UUID NOT NULL, 
	address VARCHAR(300) NOT NULL, 
	city VARCHAR(120), 
	state VARCHAR(2), 
	zip_code VARCHAR(12), 
	county VARCHAR(120), 
	parcel_apn VARCHAR(80), 
	property_type VARCHAR(50), 
	bedrooms NUMERIC(10, 2), 
	bathrooms NUMERIC(10, 2), 
	square_feet NUMERIC(10, 2), 
	lot_size NUMERIC(14, 2), 
	year_built INTEGER, 
	property_status VARCHAR(40) NOT NULL, 
	listing_price NUMERIC(14, 2), 
	estimated_value NUMERIC(14, 2), 
	estimated_rent NUMERIC(14, 2), 
	days_on_market INTEGER, 
	latitude NUMERIC(10, 7), 
	longitude NUMERIC(10, 7), 
	notes TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_properties_state ON properties (state);

CREATE INDEX ix_properties_zip_code ON properties (zip_code);

CREATE INDEX ix_properties_owner_id ON properties (owner_id);

CREATE INDEX ix_properties_owner_state ON properties (owner_id, state);

CREATE INDEX ix_properties_parcel_apn ON properties (parcel_apn);

CREATE TABLE user_profiles (
	id UUID NOT NULL, 
	email VARCHAR(320), 
	display_name VARCHAR(200), 
	default_assumptions JSON, 
	investor_profile JSON, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_user_profiles_email ON user_profiles (email);

CREATE TABLE communications (
	id UUID NOT NULL, 
	property_id UUID NOT NULL, 
	owner_id UUID NOT NULL, 
	contact_name VARCHAR(200), 
	contact_role VARCHAR(80), 
	communication_type VARCHAR(40) NOT NULL, 
	direction VARCHAR(20) NOT NULL, 
	occurred_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	notes TEXT, 
	outcome VARCHAR(120), 
	follow_up_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(property_id) REFERENCES properties (id) ON DELETE CASCADE
);

CREATE INDEX ix_communications_property_id ON communications (property_id);

CREATE INDEX ix_communications_owner_id ON communications (owner_id);

CREATE TABLE comps (
	id UUID NOT NULL, 
	property_id UUID NOT NULL, 
	address VARCHAR(300) NOT NULL, 
	distance_miles NUMERIC(8, 3), 
	sale_price NUMERIC(14, 2), 
	sale_date DATE, 
	bedrooms NUMERIC(10, 2), 
	bathrooms NUMERIC(10, 2), 
	square_feet NUMERIC(10, 2), 
	lot_size NUMERIC(14, 2), 
	year_built INTEGER, 
	property_type VARCHAR(50), 
	condition VARCHAR(50), 
	price_per_square_foot NUMERIC(10, 2), 
	similarity_score NUMERIC(12, 6), 
	source VARCHAR(80), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(property_id) REFERENCES properties (id) ON DELETE CASCADE
);

CREATE INDEX ix_comps_property_id ON comps (property_id);

CREATE TABLE data_sources (
	id UUID NOT NULL, 
	property_id UUID, 
	provider VARCHAR(60) NOT NULL, 
	provider_record_id VARCHAR(200), 
	field_name VARCHAR(120), 
	field_value VARCHAR(400), 
	retrieved_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	source_url VARCHAR(600), 
	confidence VARCHAR(10), 
	payload JSON, 
	PRIMARY KEY (id), 
	FOREIGN KEY(property_id) REFERENCES properties (id) ON DELETE CASCADE
);

CREATE INDEX ix_data_sources_property_id ON data_sources (property_id);

CREATE TABLE deal_analyses (
	id UUID NOT NULL, 
	property_id UUID NOT NULL, 
	owner_id UUID NOT NULL, 
	name VARCHAR(200), 
	purchase_price NUMERIC(14, 2), 
	arv_low NUMERIC(14, 2), 
	arv_high NUMERIC(14, 2), 
	arv_confidence VARCHAR(10), 
	rehab_low NUMERIC(14, 2), 
	rehab_high NUMERIC(14, 2), 
	rehab_confidence VARCHAR(10), 
	closing_costs NUMERIC(14, 2), 
	holding_costs NUMERIC(14, 2), 
	financing_costs NUMERIC(14, 2), 
	selling_costs NUMERIC(14, 2), 
	miscellaneous_costs NUMERIC(14, 2), 
	total_basis NUMERIC(14, 2), 
	rent NUMERIC(14, 2), 
	vacancy NUMERIC(12, 6), 
	management NUMERIC(12, 6), 
	maintenance NUMERIC(12, 6), 
	capex NUMERIC(12, 6), 
	taxes NUMERIC(14, 2), 
	insurance NUMERIC(14, 2), 
	hoa NUMERIC(14, 2), 
	monthly_cash_flow NUMERIC(14, 2), 
	annual_cash_flow NUMERIC(14, 2), 
	profit NUMERIC(14, 2), 
	cash_required NUMERIC(14, 2), 
	equity_created NUMERIC(14, 2), 
	deal_score NUMERIC(10, 2), 
	risk_score NUMERIC(10, 2), 
	confidence VARCHAR(10), 
	recommended_strategy VARCHAR(40), 
	verdict VARCHAR(30), 
	requires_human_review BOOLEAN NOT NULL, 
	inputs_json JSON, 
	assumptions_json JSON, 
	results_json JSON, 
	scoring_json JSON, 
	ai_analysis_json JSON, 
	engine_version VARCHAR(20), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(property_id) REFERENCES properties (id) ON DELETE CASCADE
);

CREATE INDEX ix_deal_analyses_owner_id ON deal_analyses (owner_id);

CREATE INDEX ix_deal_analyses_verdict ON deal_analyses (verdict);

CREATE INDEX ix_deal_analyses_property_id ON deal_analyses (property_id);

CREATE INDEX ix_deal_analyses_recommended_strategy ON deal_analyses (recommended_strategy);

CREATE TABLE leads (
	id UUID NOT NULL, 
	property_id UUID NOT NULL, 
	owner_id UUID NOT NULL, 
	lead_type VARCHAR(40) NOT NULL, 
	source VARCHAR(120), 
	status VARCHAR(40) NOT NULL, 
	lead_score NUMERIC(10, 2), 
	notes TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(property_id) REFERENCES properties (id) ON DELETE CASCADE
);

CREATE INDEX ix_leads_property_id ON leads (property_id);

CREATE INDEX ix_leads_owner_id ON leads (owner_id);

CREATE INDEX ix_leads_status ON leads (status);

CREATE TABLE offers (
	id UUID NOT NULL, 
	property_id UUID NOT NULL, 
	owner_id UUID NOT NULL, 
	offer_amount NUMERIC(14, 2) NOT NULL, 
	offer_type VARCHAR(50), 
	terms TEXT, 
	status VARCHAR(40) NOT NULL, 
	date_submitted DATE, 
	expiration_date DATE, 
	notes TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(property_id) REFERENCES properties (id) ON DELETE CASCADE
);

CREATE INDEX ix_offers_status ON offers (status);

CREATE INDEX ix_offers_property_id ON offers (property_id);

CREATE INDEX ix_offers_owner_id ON offers (owner_id);

CREATE TABLE owners (
	id UUID NOT NULL, 
	property_id UUID NOT NULL, 
	owner_name VARCHAR(300), 
	entity_type VARCHAR(60), 
	mailing_address VARCHAR(300), 
	ownership_start_date DATE, 
	estimated_equity NUMERIC(14, 2), 
	estimated_mortgage NUMERIC(14, 2), 
	occupancy_indicator VARCHAR(40), 
	notes TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(property_id) REFERENCES properties (id) ON DELETE CASCADE
);

CREATE INDEX ix_owners_property_id ON owners (property_id);

CREATE TABLE rehab_projects (
	id UUID NOT NULL, 
	property_id UUID NOT NULL, 
	owner_id UUID NOT NULL, 
	estimated_rehab NUMERIC(14, 2), 
	actual_rehab NUMERIC(14, 2), 
	materials_cost NUMERIC(14, 2), 
	labor_cost NUMERIC(14, 2), 
	contractors JSON, 
	scope TEXT, 
	start_date DATE, 
	completion_date DATE, 
	status VARCHAR(40) NOT NULL, 
	notes TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(property_id) REFERENCES properties (id) ON DELETE CASCADE
);

CREATE INDEX ix_rehab_projects_property_id ON rehab_projects (property_id);

CREATE INDEX ix_rehab_projects_owner_id ON rehab_projects (owner_id);

CREATE TABLE assumption_audit (
	id UUID NOT NULL, 
	analysis_id UUID NOT NULL, 
	property_id UUID, 
	changed_by UUID NOT NULL, 
	changed_by_email VARCHAR(320), 
	changed_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	field_path VARCHAR(200) NOT NULL, 
	field_label VARCHAR(200), 
	previous_value VARCHAR(200), 
	new_value VARCHAR(200), 
	reason TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(analysis_id) REFERENCES deal_analyses (id) ON DELETE CASCADE
);

CREATE INDEX ix_assumption_audit_analysis_id ON assumption_audit (analysis_id);

CREATE INDEX ix_assumption_audit_property_id ON assumption_audit (property_id);

COMMIT;
