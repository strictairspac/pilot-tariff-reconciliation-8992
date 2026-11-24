export const States = Object.freeze({
  queued: "排队中",
  done: "已完成",
  failed: "执行失败",
});

export const SupplementStates = Object.freeze({
  active: "已生效",
  failed: "待重试",
  retired: "已退回",
});

export const Actions = Object.freeze({
  create_case: "登记资料", enqueue: "提交受理", done: "复核完成", failed: "执行失败",
  review: "复核签署", register_supplement: "登记补录", retry_supplement: "重试补录",
  retire_supplement: "退回补录",
});
