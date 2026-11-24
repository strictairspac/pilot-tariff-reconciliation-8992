import { api } from "../api/workbench.js";
import { errorText, field } from "../components/common/fields.js";
import { empty, section } from "../components/common/panel.js";
import { table } from "../components/common/table.js";
import { SupplementStates } from "../constants/states.js";
import { submit } from "../hooks/submit.js";
import { el } from "../utils/dom.js";

function supplementForm(onDone) {
  const form = el("form", {id: "supplement-form"},
    el("div", {class: "pair"},
      field("补录单号", el("input", {name: "code", required: true, maxlength: 30})),
      field("航段", el("input", {name: "zone", required: true, maxlength: 30}))),
    el("div", {class: "pair"},
      field("服务起始日", el("input", {name: "valid_from", type: "date", required: true})),
      field("服务结束日（留空无上限）", el("input", {name: "valid_until", type: "date"}))),
    el("div", {class: "pair"},
      field("计费费率（分）", el("input", {name: "rate", type: "number", min: 0, required: true})),
      field("最低收费（分）", el("input", {name: "minimum", type: "number", min: 0, required: true}))),
    field("补录说明", el("input", {name: "note", maxlength: 500})),
    errorText(), el("button", {type: "submit"}, "登记补录单"),
    el("small", {}, "补录只替换所填服务日期内的费率，区间外与原开账认知照旧。同单号内容一致会回读原单，内容不同则退回。"));
  submit(form, async values => {
    const entry = await api.registerSupplement({
      code: values.get("code").trim(), zone: values.get("zone").trim(),
      valid_from: values.get("valid_from"), valid_until: values.get("valid_until") || null,
      rate: Number(values.get("rate")), minimum: Number(values.get("minimum")), note: values.get("note"),
    });
    form.reset();
    await onDone(entry);
  });
  return form;
}

function supplementTable(entries, actions) {
  return table(["单号", "航段", "服务日", "费率（分）", "状态", "操作"], entries.map(entry => [
    entry.code,
    entry.zone,
    entry.valid_until ? `${entry.valid_from} → ${entry.valid_until}` : `${entry.valid_from} 起`,
    `${entry.rate_cents} / 最低 ${entry.min_cents}`,
    el("div", {class: "stack"},
      el("span", {class: `status state-${entry.status}`}, SupplementStates[entry.status] || entry.status),
      entry.failure ? el("small", {class: "feedback"}, entry.failure) : null),
    actions(entry),
  ]), "补录单列表");
}

/** Register and manage supplement orders inside the "航次与费率" module. */
export async function supplementsSection(user) {
  const feedback = errorText();
  const body = el("div", {});
  const operator = user.role === "operator";

  async function reload() {
    const entries = await api.supplements();
    body.replaceChildren(entries.length ? supplementTable(entries, actions) : empty("还没有补录单。"));
  }

  async function retry(entry) {
    feedback.textContent = "";
    try {
      const next = await api.retrySupplement(entry.id);
      feedback.textContent = next.status === "active" ? "补录单已生效。" : next.failure || "补录单仍待处理。";
      await reload();
    } catch (error) {
      feedback.textContent = error.message;
    }
  }

  async function retire(entry) {
    if (!window.confirm(`退回补录单 ${entry.code}？退回后需以新单号重新登记。`)) return;
    feedback.textContent = "";
    try {
      await api.retireSupplement(entry.id);
      await reload();
    } catch (error) {
      feedback.textContent = error.message;
    }
  }

  function actions(entry) {
    if (!operator) return "—";
    return el("div", {class: "row-actions"},
      entry.status === "failed" ? el("button", {type: "button", onclick: () => retry(entry)}, "重试") : null,
      entry.status !== "retired" ? el("button", {class: "quiet", type: "button", onclick: () => retire(entry)}, "退回") : null) ;
  }

  await reload();
  return section("补录单（按航段）", feedback, body,
    operator ? supplementForm(async entry => {
      feedback.textContent = entry.status === "active"
        ? `补录单 ${entry.code} 已生效。`
        : `${entry.code} 登记为待重试：${entry.failure || ""}`;
      await reload();
    }) : empty("当前账号可查看补录单。"));
}
