// TypeScript mirrors of the backend Pydantic contracts (backend/app/schemas).
// Keep in sync with the schemas; the backend is the source of truth.

export type RiskLevel = "low" | "medium" | "high" | "critical";
export type AgentStatus = "active" | "suspended" | "revoked" | "pending_review";

export interface Money {
  amount: string; // Decimal serialised as string, e.g. "500.00"
  currency: "AED";
}

export interface AgentPassport {
  agent_id: string;
  name: string;
  name_ar: string;
  description: string;
  owner_entity: string;
  accountable_officer: { name: string; title: string; officer_id: string };
  platform: string;
  risk_level: RiskLevel;
  status: AgentStatus;
  identity_key_reference: {
    key_id: string;
    algorithm: "Ed25519";
    provisioning_status: "not_provisioned" | "provisioned" | "rotated" | "revoked";
    public_key_fingerprint: string | null;
  };
  declared_tools: string[];
  restrictions: string[];
  synthetic: true;
}

export interface Citizen {
  citizen_ref: string;
  full_name: string;
  full_name_ar: string;
  residency: { permit_ref: string; status: "active" | "expiring_soon" | "expired"; expiry_date: string; emirate: string };
  insurance: { policy_ref: string; provider: string; status: "valid" | "expired" | "none"; valid_until: string | null };
  service_attributes: {
    sponsor_type: string;
    renewal_eligible: boolean;
    outstanding_fines: Money;
    preferred_language: "ar" | "en";
  };
  account_ref: string;
  synthetic: true;
}

export interface GovernmentService {
  service_id: string;
  name: string;
  name_ar: string;
  operating_entity: string;
  fee: Money;
  official_payment_destination: string;
  tools: string[];
  synthetic: true;
}

export interface DocumentFixture {
  document_id: string;
  title: string;
  citizen_ref: string;
  filename: string;
  trust_classification: "untrusted_input";
  contains_injected_instruction: boolean;
  content: string;
  sha256: string;
  synthetic: true;
}

export interface Scenario {
  scenario_id: string;
  title: string;
  summary: string;
  citizen_ref: string;
  service_id: string;
  document_id: string;
  category: "baseline" | "prompt_injection";
  planned_expected_outcome: string;
  target_phase: number;
  execution_enabled: false;
  synthetic: true;
}

export interface ScenarioWithDocument {
  scenario: Scenario;
  document: DocumentFixture;
}

export type ReasonCode = string;

export interface AuditEvent {
  event_id: string;
  timestamp: string;
  actor: string;
  action: string;
  decision: "allowed" | "denied" | "escalated" | "informational";
  request_id: string | null;
  related_mandate: string | null;
  evidence_metadata: Record<string, string | number | boolean | null>;
  sequence: number | null;
  authenticated: boolean;
  claimed_agent_id: string | null;
  mandate_version: number | null;
  decision_id: string | null;
  reason_codes: ReasonCode[];
  policy_version: string | null;
  decision_latency_ms: number | null;
  previous_event_hash: string | null;
  event_hash: string | null;
}

export interface DigitalMandate {
  mandate_id: string;
  version: number;
  agent_id: string;
  issuer_id: string;
  service_id: string;
  purpose: string;
  citizen_or_request_scope: { citizen_ref: string; request_id: string };
  allowed_tools: string[];
  denied_tools: string[];
  resource_constraints: { resource_type: string; access: string; identifiers: string[] }[];
  amount_limit: Money | null;
  recipient_allowlist: string[];
  issued_at: string;
  expires_at: string;
  status: "active" | "revoked" | "suspended";
  parent_mandate_id: string | null;
  signature_metadata: { algorithm: "Ed25519"; key_id: string; signature: string; signed_at: string } | null;
}

export interface MandateView {
  mandate: DigitalMandate;
  verification: {
    valid: boolean;
    effective_status: "active" | "revoked" | "expired" | "not_yet_valid" | "invalid";
    signature_valid: boolean;
    issuer_trusted: boolean;
    within_issuer_authority: boolean;
    reason_codes: ReasonCode[];
    checked_at: string;
  };
  revoked: boolean;
  revoked_at: string | null;
  revocation_reason: string | null;
}

export interface IssuerView {
  issuer: {
    issuer_id: string;
    name: string;
    status: "active" | "revoked";
    key_id: string;
    authority: {
      services: string[];
      agents: string[];
      tools: string[];
      max_amount: Money | null;
      recipients: string[];
      max_lifetime_hours: number;
    };
  };
  key_fingerprint: string | null;
  key_registered: boolean;
}

export interface AuthorizationDecision {
  decision_id: string;
  allowed: boolean;
  reason_codes: ReasonCode[];
  human_readable_explanation: string;
  policy_version: string;
  decision_latency_ms: number;
  audit_reference: string;
  mandate_id: string | null;
  request_digest: string | null;
}

export interface DevScenarioInfo {
  key: string;
  title: string;
  description: string;
  designed_to_test: string;
}

export interface DevScenarioResult {
  scenario: DevScenarioInfo;
  request: {
    agent_id: string;
    tool_name: string;
    mandate_id: string;
    target_resource: string;
    parameters: Record<string, string | number | boolean | null>;
    nonce: string;
    request_digest: string;
  };
  decision: AuthorizationDecision;
  executed: boolean;
  execution_status: string;
  result: Record<string, string | number | boolean | null> | null;
  checks: { name: string; status: "passed" | "failed" | "not_evaluated"; reason_codes: ReasonCode[] }[];
  note: string | null;
  development_only: true;
}

export interface AuditIntegrity {
  valid: boolean;
  event_count: number;
  head_hash: string;
  first_broken_sequence: number | null;
  detail: string;
  scope_note: string;
}

export interface Capability {
  key: string;
  name: string;
  status: "implemented" | "planned";
  phase: number;
  description: string;
}

export interface SystemCapabilities {
  product: "WAKALA";
  version: string;
  current_phase: number;
  enforcement_engine_connected: boolean;
  developer_demo_enabled: boolean;
  synthetic_data_only: true;
  external_llm_dependency: false;
  capabilities: Capability[];
  implemented_count: number;
  planned_count: number;
}

export interface ListResponse<T> {
  items: T[];
  count: number;
  synthetic_data: true;
}

export interface AuditEventList extends ListResponse<AuditEvent> {
  allowed_count: number;
  denied_count: number;
  enforcement_engine_connected: boolean;
}

export interface Health {
  status: "ok";
  service: string;
  version: string;
  synthetic_data_only: true;
}

/** Subset of JSON Schema emitted by Pydantic's model_json_schema(). */
export interface JsonSchema {
  title?: string;
  description?: string;
  type?: string;
  format?: string;
  pattern?: string;
  enum?: unknown[];
  const?: unknown;
  default?: unknown;
  minLength?: number;
  maxLength?: number;
  minItems?: number;
  maxItems?: number;
  minimum?: number;
  maximum?: number;
  $ref?: string;
  items?: JsonSchema;
  anyOf?: JsonSchema[];
  properties?: Record<string, JsonSchema>;
  required?: string[];
  additionalProperties?: boolean | JsonSchema;
  $defs?: Record<string, JsonSchema>;
}

// --- Phase 2: government workflow ------------------------------------------

export type CaseState =
  | "CREATED"
  | "VERIFYING"
  | "AWAITING_PAYMENT"
  | "READY_TO_COMPLETE"
  | "COMPLETED"
  | "PAUSED_FOR_REVIEW"
  | "FAILED";

export interface CaseEvent {
  at: string;
  actor: string;
  kind: string;
  detail: string;
  audit_reference: string | null;
  from_state: CaseState | null;
  to_state: CaseState | null;
}

export interface RenewalCase {
  case_id: string;
  citizen_ref: string;
  service_id: string;
  service_owner: string;
  authorized_purpose: string;
  request_id: string;
  state: CaseState;
  paused_from: CaseState | null;
  assigned_agents: string[];
  mandate_refs: Record<string, string>;
  authorized_operations: string[];
  completed_prerequisites: string[];
  created_at: string;
  expires_at: string;
  recovery_status: string;
  authority_revoked: boolean;
  authority_model: "direct" | "delegated";
  version: number;
  history: CaseEvent[];
}

export type Scalars = Record<string, string | number | boolean | null>;

export interface WorkflowStep {
  index: number;
  title: string;
  intent: "legitimate" | "out_of_scope" | "unauthorized" | "prerequisite_check" | "safety_control";
  agent_id: string;
  tool_name: string;
  parameters: Scalars;
  target_resource: string;
  case_id: string;
  mandate_id: string;
  request_digest: string | null;
  decision: AuthorizationDecision | null;
  checks: { name: string; status: "passed" | "failed" | "not_evaluated"; reason_codes: string[] }[];
  executed: boolean;
  execution_status: string;
  result: Scalars | null;
  case_state_before: CaseState;
  case_state_after: CaseState;
  execution_audit_reference: string | null;
  note: string | null;
}

export interface BaselineComparison {
  label: string;
  description: string;
  request: Record<string, unknown>;
  baseline_allowed: boolean;
  baseline_checks_performed: string[];
  baseline_returned_data: Record<string, unknown> | null;
  wakala_allowed: boolean;
  wakala_reason_codes: string[];
  wakala_returned_data: Record<string, unknown> | null;
  wakala_audit_reference: string;
}

export interface WorkflowRun {
  scenario: string;
  title: string;
  description: string;
  simulated_agents: true;
  case: RenewalCase;
  steps: WorkflowStep[];
  ledger: Record<string, string>[];
  renewals: Record<string, string>[];
  audit_events: AuditEvent[];
  baseline: BaselineComparison | null;
  related_cases: RenewalCase[];
  delegations: Record<string, string>[];
}

export interface CaseDetail {
  case: RenewalCase;
  ledger: Record<string, string>[];
  renewals: Record<string, string>[];
  audit_events: AuditEvent[];
}

export interface WorkflowScenarioInfo {
  key: string;
  title: string;
  description: string;
  citizen_selectable: boolean;
}

export interface CaseSummary {
  case_id: string;
  citizen_ref: string;
  state: CaseState;
  created_at: string;
  expires_at: string;
  completed_prerequisites: string[];
  recovery_status: string;
  authority_model?: "direct" | "delegated";
  authority_revoked?: boolean;
}

// --- Phase 3: authority chains ----------------------------------------------

export type GraphNodeKind = "case" | "issuer" | "mandate" | "child_mandate" | "agent" | "denied_attempt";

export interface AuthorityGraphNode {
  id: string;
  kind: GraphNodeKind;
  label: string;
  sublabel: string;
  status: string;
  data: Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
}

export interface AuthorityGraphEdge {
  id: string;
  source: string;
  target: string;
  kind: "signed" | "binds" | "delegated" | "held_by" | "denied_delegation";
  label: string;
  status: string;
}

export interface AuthorityGraph {
  case_id: string;
  generated_at: string;
  nodes: AuthorityGraphNode[];
  edges: AuthorityGraphEdge[];
  delegations: Record<string, string>[];
}
