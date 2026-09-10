"""Initial Atlas schema.

The twelve tables as originally shipped, reconstructed from the hand-applied
``0001_initial_schema.sql`` at commit 289b7d2 — deliberately WITHOUT
``user_profiles.investor_profile`` and ``deal_analyses.assumptions_schema_version``,
which arrived later and are added by revisions 0003 and 0004.

That distinction is the whole point of adopting a runner. The pre-Alembic
``0001_initial_schema.sql`` was regenerated from the models each time the
schema changed, so the file on disk always described the *current* schema and
never the one any deployed database was actually built from. Migrations 0003
and 0004 were both no-ops against it on a fresh database, and nothing said so.
Here the history is linear and each revision does exactly what it claims, so a
database at any point in that history can be moved forward.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001_initial_schema'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the schema from nothing."""
    op.create_table('activity_log',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('actor_id', sa.Uuid(), nullable=True),
    sa.Column('actor_email', sa.String(length=320), nullable=True),
    sa.Column('action', sa.String(length=80), nullable=False),
    sa.Column('entity_type', sa.String(length=60), nullable=True),
    sa.Column('entity_id', sa.Uuid(), nullable=True),
    sa.Column('summary', sa.String(length=500), nullable=True),
    sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_activity_log_action'), 'activity_log', ['action'], unique=False)
    op.create_index(op.f('ix_activity_log_actor_id'), 'activity_log', ['actor_id'], unique=False)
    op.create_index(op.f('ix_activity_log_entity_id'), 'activity_log', ['entity_id'], unique=False)
    op.create_index(op.f('ix_activity_log_occurred_at'), 'activity_log', ['occurred_at'], unique=False)
    op.create_table('properties',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.Column('address', sa.String(length=300), nullable=False),
    sa.Column('city', sa.String(length=120), nullable=True),
    sa.Column('state', sa.String(length=2), nullable=True),
    sa.Column('zip_code', sa.String(length=12), nullable=True),
    sa.Column('county', sa.String(length=120), nullable=True),
    sa.Column('parcel_apn', sa.String(length=80), nullable=True),
    sa.Column('property_type', sa.String(length=50), nullable=True),
    sa.Column('bedrooms', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('bathrooms', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('square_feet', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('lot_size', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('year_built', sa.Integer(), nullable=True),
    sa.Column('property_status', sa.String(length=40), nullable=False),
    sa.Column('listing_price', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('estimated_value', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('estimated_rent', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('days_on_market', sa.Integer(), nullable=True),
    sa.Column('latitude', sa.Numeric(precision=10, scale=7), nullable=True),
    sa.Column('longitude', sa.Numeric(precision=10, scale=7), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_properties_owner_id'), 'properties', ['owner_id'], unique=False)
    op.create_index('ix_properties_owner_state', 'properties', ['owner_id', 'state'], unique=False)
    op.create_index(op.f('ix_properties_parcel_apn'), 'properties', ['parcel_apn'], unique=False)
    op.create_index(op.f('ix_properties_state'), 'properties', ['state'], unique=False)
    op.create_index(op.f('ix_properties_zip_code'), 'properties', ['zip_code'], unique=False)
    op.create_table('user_profiles',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=True),
    sa.Column('display_name', sa.String(length=200), nullable=True),
    sa.Column('default_assumptions', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_profiles_email'), 'user_profiles', ['email'], unique=False)
    op.create_table('communications',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('property_id', sa.Uuid(), nullable=False),
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.Column('contact_name', sa.String(length=200), nullable=True),
    sa.Column('contact_role', sa.String(length=80), nullable=True),
    sa.Column('communication_type', sa.String(length=40), nullable=False),
    sa.Column('direction', sa.String(length=20), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('outcome', sa.String(length=120), nullable=True),
    sa.Column('follow_up_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_communications_owner_id'), 'communications', ['owner_id'], unique=False)
    op.create_index(op.f('ix_communications_property_id'), 'communications', ['property_id'], unique=False)
    op.create_table('comps',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('property_id', sa.Uuid(), nullable=False),
    sa.Column('address', sa.String(length=300), nullable=False),
    sa.Column('distance_miles', sa.Numeric(precision=8, scale=3), nullable=True),
    sa.Column('sale_price', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('sale_date', sa.Date(), nullable=True),
    sa.Column('bedrooms', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('bathrooms', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('square_feet', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('lot_size', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('year_built', sa.Integer(), nullable=True),
    sa.Column('property_type', sa.String(length=50), nullable=True),
    sa.Column('condition', sa.String(length=50), nullable=True),
    sa.Column('price_per_square_foot', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('similarity_score', sa.Numeric(precision=12, scale=6), nullable=True),
    sa.Column('source', sa.String(length=80), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_comps_property_id'), 'comps', ['property_id'], unique=False)
    op.create_table('data_sources',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('property_id', sa.Uuid(), nullable=True),
    sa.Column('provider', sa.String(length=60), nullable=False),
    sa.Column('provider_record_id', sa.String(length=200), nullable=True),
    sa.Column('field_name', sa.String(length=120), nullable=True),
    sa.Column('field_value', sa.String(length=400), nullable=True),
    sa.Column('retrieved_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('source_url', sa.String(length=600), nullable=True),
    sa.Column('confidence', sa.String(length=10), nullable=True),
    sa.Column('payload', sa.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_data_sources_property_id'), 'data_sources', ['property_id'], unique=False)
    op.create_table('deal_analyses',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('property_id', sa.Uuid(), nullable=False),
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=True),
    sa.Column('purchase_price', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('arv_low', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('arv_high', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('arv_confidence', sa.String(length=10), nullable=True),
    sa.Column('rehab_low', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('rehab_high', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('rehab_confidence', sa.String(length=10), nullable=True),
    sa.Column('closing_costs', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('holding_costs', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('financing_costs', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('selling_costs', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('miscellaneous_costs', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('total_basis', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('rent', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('vacancy', sa.Numeric(precision=12, scale=6), nullable=True),
    sa.Column('management', sa.Numeric(precision=12, scale=6), nullable=True),
    sa.Column('maintenance', sa.Numeric(precision=12, scale=6), nullable=True),
    sa.Column('capex', sa.Numeric(precision=12, scale=6), nullable=True),
    sa.Column('taxes', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('insurance', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('hoa', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('monthly_cash_flow', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('annual_cash_flow', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('profit', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('cash_required', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('equity_created', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('deal_score', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('risk_score', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('confidence', sa.String(length=10), nullable=True),
    sa.Column('recommended_strategy', sa.String(length=40), nullable=True),
    sa.Column('verdict', sa.String(length=30), nullable=True),
    sa.Column('requires_human_review', sa.Boolean(), nullable=False),
    sa.Column('inputs_json', sa.JSON(), nullable=True),
    sa.Column('assumptions_json', sa.JSON(), nullable=True),
    sa.Column('results_json', sa.JSON(), nullable=True),
    sa.Column('scoring_json', sa.JSON(), nullable=True),
    sa.Column('ai_analysis_json', sa.JSON(), nullable=True),
    sa.Column('engine_version', sa.String(length=20), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_deal_analyses_owner_id'), 'deal_analyses', ['owner_id'], unique=False)
    op.create_index(op.f('ix_deal_analyses_property_id'), 'deal_analyses', ['property_id'], unique=False)
    op.create_index(op.f('ix_deal_analyses_recommended_strategy'), 'deal_analyses', ['recommended_strategy'], unique=False)
    op.create_index(op.f('ix_deal_analyses_verdict'), 'deal_analyses', ['verdict'], unique=False)
    op.create_table('leads',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('property_id', sa.Uuid(), nullable=False),
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.Column('lead_type', sa.String(length=40), nullable=False),
    sa.Column('source', sa.String(length=120), nullable=True),
    sa.Column('status', sa.String(length=40), nullable=False),
    sa.Column('lead_score', sa.Numeric(precision=10, scale=2), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_leads_owner_id'), 'leads', ['owner_id'], unique=False)
    op.create_index(op.f('ix_leads_property_id'), 'leads', ['property_id'], unique=False)
    op.create_index(op.f('ix_leads_status'), 'leads', ['status'], unique=False)
    op.create_table('offers',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('property_id', sa.Uuid(), nullable=False),
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.Column('offer_amount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('offer_type', sa.String(length=50), nullable=True),
    sa.Column('terms', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=40), nullable=False),
    sa.Column('date_submitted', sa.Date(), nullable=True),
    sa.Column('expiration_date', sa.Date(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_offers_owner_id'), 'offers', ['owner_id'], unique=False)
    op.create_index(op.f('ix_offers_property_id'), 'offers', ['property_id'], unique=False)
    op.create_index(op.f('ix_offers_status'), 'offers', ['status'], unique=False)
    op.create_table('owners',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('property_id', sa.Uuid(), nullable=False),
    sa.Column('owner_name', sa.String(length=300), nullable=True),
    sa.Column('entity_type', sa.String(length=60), nullable=True),
    sa.Column('mailing_address', sa.String(length=300), nullable=True),
    sa.Column('ownership_start_date', sa.Date(), nullable=True),
    sa.Column('estimated_equity', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('estimated_mortgage', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('occupancy_indicator', sa.String(length=40), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_owners_property_id'), 'owners', ['property_id'], unique=False)
    op.create_table('rehab_projects',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('property_id', sa.Uuid(), nullable=False),
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.Column('estimated_rehab', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('actual_rehab', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('materials_cost', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('labor_cost', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('contractors', sa.JSON(), nullable=True),
    sa.Column('scope', sa.Text(), nullable=True),
    sa.Column('start_date', sa.Date(), nullable=True),
    sa.Column('completion_date', sa.Date(), nullable=True),
    sa.Column('status', sa.String(length=40), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['property_id'], ['properties.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_rehab_projects_owner_id'), 'rehab_projects', ['owner_id'], unique=False)
    op.create_index(op.f('ix_rehab_projects_property_id'), 'rehab_projects', ['property_id'], unique=False)
    op.create_table('assumption_audit',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('analysis_id', sa.Uuid(), nullable=False),
    sa.Column('property_id', sa.Uuid(), nullable=True),
    sa.Column('changed_by', sa.Uuid(), nullable=False),
    sa.Column('changed_by_email', sa.String(length=320), nullable=True),
    sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('field_path', sa.String(length=200), nullable=False),
    sa.Column('field_label', sa.String(length=200), nullable=True),
    sa.Column('previous_value', sa.String(length=200), nullable=True),
    sa.Column('new_value', sa.String(length=200), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['analysis_id'], ['deal_analyses.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_assumption_audit_analysis_id'), 'assumption_audit', ['analysis_id'], unique=False)
    op.create_index(op.f('ix_assumption_audit_property_id'), 'assumption_audit', ['property_id'], unique=False)


def downgrade() -> None:
    """Drop everything this revision created.

    Correct, and destructive by definition: downgrading past the initial
    revision empties the database. It exists so the path is testable, not
    because anyone should run it against data they want.
    """
    op.drop_index(op.f('ix_assumption_audit_property_id'), table_name='assumption_audit')
    op.drop_index(op.f('ix_assumption_audit_analysis_id'), table_name='assumption_audit')
    op.drop_table('assumption_audit')
    op.drop_index(op.f('ix_rehab_projects_property_id'), table_name='rehab_projects')
    op.drop_index(op.f('ix_rehab_projects_owner_id'), table_name='rehab_projects')
    op.drop_table('rehab_projects')
    op.drop_index(op.f('ix_owners_property_id'), table_name='owners')
    op.drop_table('owners')
    op.drop_index(op.f('ix_offers_status'), table_name='offers')
    op.drop_index(op.f('ix_offers_property_id'), table_name='offers')
    op.drop_index(op.f('ix_offers_owner_id'), table_name='offers')
    op.drop_table('offers')
    op.drop_index(op.f('ix_leads_status'), table_name='leads')
    op.drop_index(op.f('ix_leads_property_id'), table_name='leads')
    op.drop_index(op.f('ix_leads_owner_id'), table_name='leads')
    op.drop_table('leads')
    op.drop_index(op.f('ix_deal_analyses_verdict'), table_name='deal_analyses')
    op.drop_index(op.f('ix_deal_analyses_recommended_strategy'), table_name='deal_analyses')
    op.drop_index(op.f('ix_deal_analyses_property_id'), table_name='deal_analyses')
    op.drop_index(op.f('ix_deal_analyses_owner_id'), table_name='deal_analyses')
    op.drop_table('deal_analyses')
    op.drop_index(op.f('ix_data_sources_property_id'), table_name='data_sources')
    op.drop_table('data_sources')
    op.drop_index(op.f('ix_comps_property_id'), table_name='comps')
    op.drop_table('comps')
    op.drop_index(op.f('ix_communications_property_id'), table_name='communications')
    op.drop_index(op.f('ix_communications_owner_id'), table_name='communications')
    op.drop_table('communications')
    op.drop_index(op.f('ix_user_profiles_email'), table_name='user_profiles')
    op.drop_table('user_profiles')
    op.drop_index(op.f('ix_properties_zip_code'), table_name='properties')
    op.drop_index(op.f('ix_properties_state'), table_name='properties')
    op.drop_index(op.f('ix_properties_parcel_apn'), table_name='properties')
    op.drop_index('ix_properties_owner_state', table_name='properties')
    op.drop_index(op.f('ix_properties_owner_id'), table_name='properties')
    op.drop_table('properties')
    op.drop_index(op.f('ix_activity_log_occurred_at'), table_name='activity_log')
    op.drop_index(op.f('ix_activity_log_entity_id'), table_name='activity_log')
    op.drop_index(op.f('ix_activity_log_actor_id'), table_name='activity_log')
    op.drop_index(op.f('ix_activity_log_action'), table_name='activity_log')
    op.drop_table('activity_log')
