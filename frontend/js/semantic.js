/* Semantic detection recommends metadata; every value can be overridden later. */
const Semantic = (() => {
  const TYPES = ["text", "number", "date", "boolean"];
  const ROLES = ["date", "id", "category", "measure", "numeric_attribute", "boolean", "unknown"];

  function meaningfulValues(records, column) {
    return records
      .map((record) => record[column])
      .filter((value) => value !== null && value !== undefined && String(value).trim() !== "");
  }

  function isNumeric(values) {
    return values.length > 0 && values.filter((value) => Number.isFinite(toNumber(value))).length / values.length >= 0.8;
  }

  function isDate(values) {
    if (!values.length) return false;
    const valid = values.filter((value) => {
      const text = String(value).trim();
      if (!/^\d{4}[-/]\d{1,2}[-/]\d{1,2}$/.test(text)) return false;
      return Number.isFinite(new Date(text.replaceAll("/", "-")).getTime());
    });
    return valid.length / values.length >= 0.8;
  }

  function isBoolean(values) {
    const accepted = new Set(["true", "false", "yes", "no", "y", "n", "0", "1"]);
    return values.length > 0 && values.filter((value) => accepted.has(String(value).trim().toLowerCase())).length / values.length >= 0.9;
  }

  function detectType(values) {
    if (isBoolean(values)) return "boolean";
    if (isDate(values)) return "date";
    if (isNumeric(values)) return "number";
    return "text";
  }

  function inferRole(column, type, values) {
    const name = column.toLowerCase().replace(/[^a-z0-9]+/g, "_");
    if (type === "date") return { role: "date", confidence: "high" };
    if (type === "boolean") return { role: "boolean", confidence: "high" };
    if (/(^|_)(id|code|key)($|_)/.test(name)) return { role: "id", confidence: "high" };
    if (type === "text") return { role: "category", confidence: values.length ? "medium" : "low" };
    if (type === "number") {
      const measures = ["revenue", "sales", "profit", "income", "amount", "price", "cost", "spend", "value", "total", "quantity", "qty", "orders"];
      const attributes = ["age", "score", "rating", "year", "month", "day", "rank", "latitude", "longitude", "percent", "percentage"];
      if (measures.some((term) => name.includes(term))) return { role: "measure", confidence: "high" };
      if (attributes.some((term) => name.includes(term))) return { role: "numeric_attribute", confidence: "high" };
      const uniqueness = new Set(values.map(String)).size / Math.max(values.length, 1);
      if (uniqueness < 0.08) return { role: "numeric_attribute", confidence: "medium" };
    }
    return { role: "unknown", confidence: "low" };
  }

  function analyze(records, columns, profiles = {}) {
    return Object.fromEntries(columns.map((column) => {
      const values = meaningfulValues(records, column);
      const profile = profiles[column];
      const type = profile?.analysis_type || detectType(values);
      const inferred = inferRole(column, type, values);
      return [column, {
        detectedType: profile?.detected_type || type,
        type,
        detectedRole: type === "number" ? "measure" : inferred.role,
        role: type === "number" ? "measure" : inferred.role,
        confidence: profile?.confidence || inferred.confidence,
      }];
    }));
  }

  function toNumber(value) {
    return typeof value === "number" ? value : Number(String(value ?? "").replaceAll(",", ""));
  }

  function isNumericField(metadata) {
    return metadata?.type === "number";
  }

  function isDimensionField(metadata) {
    return ["category", "date", "boolean"].includes(metadata?.role);
  }

  return { TYPES, ROLES, analyze, toNumber, isNumericField, isDimensionField };
})();
