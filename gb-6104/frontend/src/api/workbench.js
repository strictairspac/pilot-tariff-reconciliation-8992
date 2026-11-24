import { request } from "./http.js";

export const api = {
  config: () => request("/workbench"),
  login: data => request("/auth/login", {method: "POST", data}),
  cases: () => request("/cases"),
  createCase: data => request("/cases", {method: "POST", data}),
  runs: () => request("/runs"),
  run: (id, signal) => request(`/runs/${id}`, {signal}),
  enqueue: (id, data) => request(`/cases/${id}/runs`, {method: "POST", data}),
  review: id => request(`/runs/${id}/review`),
  submitReview: (id, data) => request(`/runs/${id}/review`, {method: "POST", data}),
  versions: id => request(`/runs/${id}/versions`),
  export: id => request(`/runs/${id}/export`, {raw: true}),
  supplements: () => request("/supplements"),
  supplement: id => request(`/supplements/${id}`),
  registerSupplement: data => request("/supplements", {method: "POST", data}),
  retrySupplement: id => request(`/supplements/${id}/retry`, {method: "POST"}),
  retireSupplement: id => request(`/supplements/${id}/retire`, {method: "POST"}),
  audit: () => request("/audit", {signal: AbortSignal.timeout(5000)}),
};
