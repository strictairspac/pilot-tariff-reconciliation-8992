import { api } from "../api/workbench.js";
import { errorText, field } from "../components/common/fields.js";
import { empty, pageHeading, section } from "../components/common/panel.js";
import { resultTable, table } from "../components/common/table.js";
import { submit } from "../hooks/submit.js";
import { el } from "../utils/dom.js";
import { cell, download, time } from "../utils/format.js";

function reviewForm(id, saved) {
  const form = el("form", {id: "review-form"},
    field("复核意见", el("textarea", {name: "note", required: true, minlength: 3, maxlength: 500, rows: 3})),
    errorText(), el("button", {type: "submit"}, "签署复核"));
  submit(form, async values => saved(await api.submitReview(id, {note: values.get("note")})));
  return form;
}

function signature(review) {
  return el("div", {"data-testid": "reviewed", class: "signature"},
    el("strong", {}, `已签署 · ${review.actor}`), el("p", {}, review.note), el("time", {}, time(review.created_at)));
}

export async function evidencePage(config, user, route) {
  const runs = (await api.runs()).filter(item => item.status === "done");
  const run = route.id ? await api.run(route.id) : runs[0];
  if (!run?.result) return el("div", {class: "page"},
    pageHeading(config.modules[3], null), empty("成功执行一个批次后可以查看、签核和下载证据。"),
    el("a", {href: "#runs"}, config.modules[2]));

  const review = await api.review(run.id);
  const versions = await api.versions(run.id);
  const issue = errorText();
  const button = el("button", {type: "button", onclick: async () => {
    button.disabled = true;
    issue.textContent = "";
    try {
      await download(await api.export(run.id), `evidence-${run.id}.json`);
    } catch (error) {
      issue.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  }}, "导出证据");
  const signing = el("div", {});
  signing.append(review ? signature(review) : user.role === "reviewer" ?
    reviewForm(run.id, data => signing.replaceChildren(signature(data))) : empty("待复核员签署。"));
  const options = el("select", {"aria-label": "选择已完成的批次", onchange: event => {
    location.hash = `evidence/${event.target.value}`;
  }}, runs.map(item => el("option", {value: item.id, selected: item.id === run.id}, `#${item.id} ${item.case_title}`)));
  return el("div", {class: "page evidence"},
    pageHeading(config.modules[3], run.case_title, button),
    issue, options,
    el("section", {class: "feature evidence-summary"}, el("div", {}, el("h2", {}, "批次判定"), el("p", {}, run.result.summary)),
      el("details", {}, el("summary", {}, "证据摘要"), el("code", {}, run.digest))),
    el("dl", {class: "metrics"}, Object.entries(run.result.metrics).map(([label, value]) =>
      el("div", {}, el("dt", {}, label), el("dd", {}, cell(value))))),
    section("业务结果明细", run.result.rows.length ? resultTable(run.result.rows) : empty("此批次无明细。")),
    versionSection(versions),
    section("复核签署", signing));
}

function versionTable(records) {
  const keys = ["条款", "航段", "业务生效起", "业务生效止", "系统登记起", "系统登记止", "计费费率（分）", "最低收费（分）", "来源"];
  return resultTable(records.map(record => Object.fromEntries(keys.map(key => [key, record[key]]))));
}

function versionSection(versions) {
  const applied = versions.applications || [];
  const blocked = versions.blocked || [];
  const parts = [];
  if (versions.versions?.length) {
    parts.push(el("h3", {}, "所用费率版本"), versionTable(versions.versions));
  }
  parts.push(el("h3", {}, "本批生效的补录单"),
    applied.length ? table(["补录单号", "航段", "服务日", "费率（分）"],
      applied.map(item => [item.supplement_code, item.zone,
        item.valid_until ? `${item.valid_from} → ${item.valid_until}` : `${item.valid_from} 起`,
        `${item.rate_cents} / 最低 ${item.min_cents}`]), "生效补录单") : empty("本批没有实际替换费率的补录单。"));
  if (blocked.length) {
    parts.push(el("h3", {}, "暂缓的补录单"),
      table(["补录单号", "航段", "服务日", "原因"],
        blocked.map(item => [item.code, item.zone,
          item.valid_until ? `${item.valid_from} → ${item.valid_until}` : `${item.valid_from} 起`,
          item.reason || "待处理"]), "暂缓补录单"));
  }
  parts.push(el("p", {}, versions.accepted_at
    ? `费率版本取受理时快照，排队后不换版；受理时间 ${time(versions.accepted_at)}。`
    : "此批次创建早于补录单机制，按原开账条款复核。"));
  return section("所用费率版本", parts);
}
