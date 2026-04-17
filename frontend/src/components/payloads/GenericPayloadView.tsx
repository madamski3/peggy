/**
 * GenericPayloadView -- fallback renderer for unrecognized structured payloads.
 *
 * Instead of dumping raw JSON, renders data in a human-readable format:
 *   - Arrays of objects → table with column headers
 *   - Key-value objects → definition list
 *   - Other → formatted JSON with syntax highlighting
 */

interface Props {
  payload: Record<string, unknown>;
}

function isArrayOfObjects(val: unknown): val is Record<string, unknown>[] {
  return (
    Array.isArray(val) &&
    val.length > 0 &&
    typeof val[0] === "object" &&
    val[0] !== null
  );
}

function formatValue(val: unknown): string {
  if (val === null || val === undefined) return "—";
  if (typeof val === "boolean") return val ? "Yes" : "No";
  if (typeof val === "object") return JSON.stringify(val);
  return String(val);
}

/** Render an array of objects as a table. */
function ArrayTable({ items }: { items: Record<string, unknown>[] }) {
  const columns = Object.keys(items[0]).filter((k) => k !== "type");

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-gray-200">
            {columns.map((col) => (
              <th
                key={col}
                className="text-left py-1.5 px-2 font-medium text-gray-500 capitalize"
              >
                {col.replace(/_/g, " ")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((item, i) => (
            <tr key={i} className="border-b border-gray-100 last:border-0">
              {columns.map((col) => (
                <td key={col} className="py-1.5 px-2 text-gray-700">
                  {formatValue(item[col])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Render a key-value object as a definition list. */
function KeyValueList({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data).filter(([k]) => k !== "type");

  return (
    <dl className="space-y-1.5 text-sm">
      {entries.map(([key, val]) => (
        <div key={key} className="flex gap-2">
          <dt className="text-gray-500 font-medium capitalize min-w-[100px] shrink-0">
            {key.replace(/_/g, " ")}
          </dt>
          <dd className="text-gray-700">
            {isArrayOfObjects(val) ? (
              <ArrayTable items={val} />
            ) : Array.isArray(val) ? (
              val.map(formatValue).join(", ")
            ) : (
              formatValue(val)
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export default function GenericPayloadView({ payload }: Props) {
  // Check if the payload's main content is an array of objects
  // (look for the first array-of-objects field, e.g. "results", "items", "data")
  const arrayField = Object.entries(payload).find(
    ([k, v]) => k !== "type" && isArrayOfObjects(v),
  );

  // Extract a title from the type field
  const typeLabel = typeof payload.type === "string"
    ? payload.type.replace(/_/g, " ")
    : null;

  return (
    <div className="mt-2 rounded-xl border border-gray-200 bg-gray-50/50 p-3">
      {typeLabel && (
        <div className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">
          {typeLabel}
        </div>
      )}
      {arrayField ? (
        <ArrayTable items={arrayField[1] as Record<string, unknown>[]} />
      ) : (
        <KeyValueList data={payload} />
      )}
    </div>
  );
}
