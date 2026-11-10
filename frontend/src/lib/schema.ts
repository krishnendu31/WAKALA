import type { JsonSchema } from "@/types/api";

export interface FieldRow {
  name: string;
  type: string;
  required: boolean;
  nullable: boolean;
  constraints: string[];
}

function refName(ref: string): string {
  return ref.split("/").pop() ?? ref;
}

function describeType(s: JsonSchema): { type: string; nullable: boolean } {
  if (s.$ref) return { type: refName(s.$ref), nullable: false };
  if (s.anyOf) {
    const nonNull = s.anyOf.filter((x) => x.type !== "null");
    const nullable = nonNull.length !== s.anyOf.length;
    return { type: nonNull.map((x) => describeType(x).type).join(" | "), nullable };
  }
  if (s.const !== undefined) return { type: `"${String(s.const)}"`, nullable: false };
  if (s.enum) return { type: "enum", nullable: false };
  if (s.type === "array") return { type: `${s.items ? describeType(s.items).type : "any"}[]`, nullable: false };
  if (s.type === "object" && s.additionalProperties && typeof s.additionalProperties === "object") {
    return { type: "map", nullable: false };
  }
  if (s.format === "date-time") return { type: "datetime (tz-aware)", nullable: false };
  return { type: s.type ?? "any", nullable: false };
}

function collectConstraints(s: JsonSchema, defs: Record<string, JsonSchema>): string[] {
  const out: string[] = [];
  const inner = s.anyOf?.find((x) => x.type !== "null") ?? s;
  if (inner.pattern) out.push(`pattern ${inner.pattern}`);
  if (inner.enum) out.push(inner.enum.map(String).join(" · "));
  if (inner.minItems !== undefined) out.push(`min ${inner.minItems} item${inner.minItems === 1 ? "" : "s"}`);
  if (inner.maxItems !== undefined) out.push(`max ${inner.maxItems} items`);
  if (inner.minLength !== undefined && inner.minLength > 1) out.push(`min length ${inner.minLength}`);
  if (inner.maxLength !== undefined) out.push(`max length ${inner.maxLength}`);
  if (inner.minimum !== undefined) out.push(`≥ ${inner.minimum}`);
  if (inner.maximum !== undefined) out.push(`≤ ${inner.maximum}`);
  if (inner.items?.pattern) out.push(`each ${inner.items.pattern}`);
  if (inner.items?.$ref) {
    const def = defs[refName(inner.items.$ref)];
    if (def?.enum) out.push(`${def.enum.length} allowed values`);
  }
  if (inner.$ref) {
    const def = defs[refName(inner.$ref)];
    if (def?.enum) out.push(def.enum.map(String).join(" · "));
  }
  if (s.default !== undefined && s.default !== null && !(Array.isArray(s.default) && s.default.length === 0)) {
    out.push(`default ${JSON.stringify(s.default)}`);
  }
  return out;
}

export function schemaRows(schema: JsonSchema): FieldRow[] {
  const required = new Set(schema.required ?? []);
  const defs = schema.$defs ?? {};
  return Object.entries(schema.properties ?? {}).map(([name, prop]) => {
    const { type, nullable } = describeType(prop);
    return { name, type, required: required.has(name), nullable, constraints: collectConstraints(prop, defs) };
  });
}
