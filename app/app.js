// Shared logic for both order form versions.
// Each HTML page defines window.FORM with its own selectors and row template.
// Nothing is auto-corrected: whatever is in the form is submitted as-is.
(function () {
  const CUSTOMERS = [
    "Acme Corp", "Blue Ridge Schools", "Northwind Events", "Summit Credit Union",
    "Harbor City Marathon", "Pinecrest Dental", "Lakeside Brewing Co", "Redline Robotics",
  ];
  const COLORS = [
    "Navy", "Black", "White", "Red", "Heather Gray", "Royal Blue",
    "Maroon", "Forest Green", "Silver", "Natural",
  ];
  const SIZES = ["XS", "S", "M", "L", "XL", "2XL", "N/A"];

  const F = window.FORM;
  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  function fillOptions(select, values) {
    select.innerHTML = '<option value="">-- choose --</option>' +
      values.map((v) => `<option value="${v}">${v}</option>`).join("");
  }

  function rows() {
    return $$(F.row, $(F.rows));
  }

  function addRow() {
    const n = rows().length + 1;
    // Parse inside a matching container so <tr> markup is kept intact.
    const tmp = document.createElement(F.rowTag === "tr" ? "tbody" : "div");
    tmp.innerHTML = F.rowHtml.replace(/\{n\}/g, n);
    const row = tmp.firstElementChild;
    $(F.rows).appendChild(row);
    fillOptions($(F.fields.color, row), COLORS);
    fillOptions($(F.fields.size, row), SIZES);
  }

  function num(v) {
    return v === "" ? null : Number(v);
  }

  function readOrder() {
    const lines = rows().map((row) => {
      const get = (k) => $(F.fields[k], row).value.trim();
      return {
        sku: get("sku"), color: get("color"), size: get("size"),
        qty: num(get("qty")), unit_price: num(get("unit_price")),
      };
    }).filter((l) => l.sku || l.color || l.size || l.qty !== null || l.unit_price !== null);
    return {
      customer: $(F.customer).value,
      po_number: $(F.po).value.trim(),
      ship_by: $(F.ship).value,
      lines: lines,
      notes: $(F.notes).value,
    };
  }

  function submit() {
    const order = readOrder();
    const status = $("#status");
    const missing = [];
    if (!order.customer) missing.push(F.labels.customer);
    if (!order.po_number) missing.push(F.labels.po);
    if (order.lines.length === 0) missing.push("at least one line item");
    if (missing.length) {
      status.textContent = "Error: missing " + missing.join(", ");
      return;
    }
    window.__submitted = order;
    status.textContent = "Order submitted";
    $$("input, select, textarea, button").forEach((el) => (el.disabled = true));
  }

  window.__readOrder = readOrder;
  fillOptions($(F.customer), CUSTOMERS);
  addRow();
  $(F.addBtn).addEventListener("click", addRow);
  $(F.submitBtn).addEventListener("click", submit);
})();
