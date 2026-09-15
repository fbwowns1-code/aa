let accountsCache = {};

async function api(path, options) {
  const res = await fetch(path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `요청 실패 (${res.status})`);
  return data;
}

function showMsg(el, text, ok) {
  el.textContent = text;
  el.className = "msg " + (ok ? "ok" : "err");
}

// ----- 계정 -----

async function loadAccounts(keepSelection) {
  const select = document.getElementById("account-select");
  const prevValue = keepSelection ? select.value : null;
  try {
    accountsCache = await api("/api/accounts");
  } catch (e) {
    accountsCache = {};
  }
  const names = Object.keys(accountsCache);
  select.innerHTML = "";
  if (names.length === 0) {
    const opt = document.createElement("option");
    opt.textContent = "(등록된 계정 없음 — 먼저 추가하세요)";
    opt.value = "";
    select.appendChild(opt);
    return;
  }
  for (const name of names) {
    const opt = document.createElement("option");
    opt.value = name;
    const info = accountsCache[name];
    opt.textContent = `${name} (${info.blog_id || "blog_id 미입력"})`;
    select.appendChild(opt);
  }
  if (prevValue && names.includes(prevValue)) {
    select.value = prevValue;
  }
  fillAccountForm();
}

function fillAccountForm() {
  const select = document.getElementById("account-select");
  const info = accountsCache[select.value];
  document.getElementById("acc-name").value = select.value || "";
  document.getElementById("acc-blogid").value = info ? info.blog_id || "" : "";
  document.getElementById("acc-naverid").value = info ? info.naver_id || "" : "";
  document.getElementById("acc-naverpw").value = "";
}

document.getElementById("account-select").addEventListener("change", fillAccountForm);

document.getElementById("btn-save-account").addEventListener("click", async () => {
  const msgEl = document.getElementById("account-msg");
  const payload = {
    name: document.getElementById("acc-name").value.trim(),
    blog_id: document.getElementById("acc-blogid").value.trim(),
    naver_id: document.getElementById("acc-naverid").value.trim(),
    naver_pw: document.getElementById("acc-naverpw").value,
  };
  try {
    await api("/api/accounts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    showMsg(msgEl, `'${payload.name}' 계정을 저장했습니다.`, true);
    await loadAccounts(false);
    document.getElementById("account-select").value = payload.name;
  } catch (e) {
    showMsg(msgEl, e.message, false);
  }
});

// ----- 지침 -----

async function loadPrompts() {
  const select = document.getElementById("prompt-select");
  let data;
  try {
    data = await api("/api/prompts");
  } catch (e) {
    data = { files: [] };
  }
  select.innerHTML = "";
  if (data.files.length === 0) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "(저장된 지침 파일 없음)";
    select.appendChild(opt);
    return;
  }
  for (const f of data.files) {
    const opt = document.createElement("option");
    opt.value = f;
    opt.textContent = f;
    select.appendChild(opt);
  }
}

document.getElementById("btn-select-prompt").addEventListener("click", async () => {
  const msgEl = document.getElementById("prompt-select-msg");
  const account = document.getElementById("account-select").value;
  const filename = document.getElementById("prompt-select").value;
  if (!account || !filename) {
    showMsg(msgEl, "계정과 지침 파일을 모두 선택해주세요.", false);
    return;
  }
  try {
    await api("/api/prompts/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ account, filename }),
    });
    showMsg(msgEl, `'${account}' 계정이 이제 '${filename}' 지침을 쓰도록 설정했습니다.`, true);
    await loadAccounts(true);
  } catch (e) {
    showMsg(msgEl, e.message, false);
  }
});

document.getElementById("btn-save-prompt").addEventListener("click", async () => {
  const msgEl = document.getElementById("prompt-save-msg");
  const filename = document.getElementById("prompt-filename").value.trim();
  const content = document.getElementById("prompt-content").value;
  if (!filename || !content) {
    showMsg(msgEl, "파일 이름과 내용을 모두 입력해주세요.", false);
    return;
  }
  try {
    const result = await api("/api/prompts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename, content }),
    });
    showMsg(msgEl, `'${result.filename}' 파일로 저장했습니다.`, true);
    await loadPrompts();
    document.getElementById("prompt-select").value = result.filename;
  } catch (e) {
    showMsg(msgEl, e.message, false);
  }
});

// 지침 선택 드롭다운에서 고르면 내용을 불러와 수정할 수 있게 보여준다.
document.getElementById("prompt-select").addEventListener("change", async (ev) => {
  const filename = ev.target.value;
  if (!filename) return;
  try {
    const data = await api(`/api/prompts/${encodeURIComponent(filename)}`);
    document.getElementById("prompt-filename").value = data.filename;
    document.getElementById("prompt-content").value = data.content;
  } catch (e) {
    // 조용히 무시 — 새 파일 이름일 수도 있다.
  }
});

// ----- 실행 -----

async function runJob(mode) {
  const msgEl = document.getElementById("run-msg");
  const account = document.getElementById("account-select").value;
  if (!account) {
    showMsg(msgEl, "먼저 계정을 선택하거나 추가해주세요.", false);
    return;
  }
  const titleStrategy = document.getElementById("run-title-strategy").value;
  const payload = { mode, account, title_strategy: titleStrategy };
  if (mode === "single") {
    payload.keyword = document.getElementById("run-keyword").value.trim();
    payload.reference = document.getElementById("run-reference").value;
    if (!payload.keyword) {
      showMsg(msgEl, "키워드를 입력해주세요.", false);
      return;
    }
  } else {
    payload.count = parseInt(document.getElementById("run-count").value || "8", 10);
  }

  try {
    await api("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    showMsg(msgEl, "실행을 시작했습니다. 위 진행 현황 패널을 확인하세요.", true);
  } catch (e) {
    showMsg(msgEl, e.message, false);
  }
}

document.getElementById("btn-run-single").addEventListener("click", () => runJob("single"));
document.getElementById("btn-run-daily").addEventListener("click", () => runJob("daily"));

// ----- 상태 패널 -----

function renderStatus(s) {
  document.getElementById("status-label").textContent =
    s.label ? s.label : "대기 중 (아직 실행한 작업 없음)";

  const postEl = document.getElementById("status-post");
  if (s.total_posts) {
    postEl.textContent = `진행: ${s.current_post || 0} / ${s.total_posts}건` +
      (s.running ? " · 실행 중" : s.finished ? " · 종료" : "");
  } else {
    postEl.textContent = "";
  }

  const grid = document.getElementById("dept-grid");
  grid.innerHTML = "";
  const order = s.department_order || ["research", "planning", "writing", "design", "publishing"];
  const labels = s.department_labels || {};
  const departments = s.departments || {};
  const details = s.detail || {};
  for (const key of order) {
    const state = departments[key] || "대기";
    const card = document.createElement("div");
    card.className = `dept-card state-${state}`;
    card.innerHTML = `
      <div class="dept-name">${labels[key] || key}</div>
      <div class="dept-state">${state}</div>
      <div class="dept-detail">${details[key] || ""}</div>
    `;
    grid.appendChild(card);
  }

  const errorEl = document.getElementById("status-error");
  if (s.error) {
    errorEl.hidden = false;
    errorEl.textContent = "오류: " + s.error;
  } else {
    errorEl.hidden = true;
  }
}

async function pollStatus() {
  try {
    const s = await api("/api/status");
    renderStatus(s);
  } catch (e) {
    // 상태 조회 실패는 조용히 무시하고 다음 주기에 다시 시도한다.
  }
}

async function init() {
  await loadAccounts(false);
  await loadPrompts();
  await pollStatus();
  setInterval(pollStatus, 2000);
}

init();
