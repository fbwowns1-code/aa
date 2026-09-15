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

// ----- 상태 패널 (automation.db 기반: 오늘 배치 전체/계정별/게시물별 9단계) -----

const POST_STATUS_LABELS = {
  PENDING: "대기", RUNNING: "진행중", COMPLETED: "완료", FAILED: "실패",
  REVIEW: "검토 필요", DUPLICATE_WARNING: "중복 의심",
};
const STEP_STATUS_CLASS = {
  PENDING: "step-pending", RUNNING: "step-running", SUCCESS: "step-success",
  FAILED: "step-failed", RETRY: "step-retry", SKIPPED: "step-skipped",
};

function renderStatus(s) {
  const sum = s.summary || {};
  document.getElementById("status-summary").textContent =
    `전체 ${sum.total || 0}건 / 완료 ${sum.completed || 0}건 / 진행중 ${sum.in_progress || 0}건 / ` +
    `실패 ${sum.failed || 0}건 / 검토 필요 ${sum.review || 0}건`;

  const badge = document.getElementById("scheduler-badge");
  const sched = s.scheduler || {};
  if (!sched.last_seen) {
    badge.textContent = "스케줄러: 기록 없음(단발/수동 실행만 했거나 scheduler.py 미실행)";
    badge.className = "scheduler-badge unknown";
  } else if (sched.online) {
    badge.textContent = `스케줄러: 정상 · 마지막 응답 ${sched.seconds_ago}초 전`;
    badge.className = "scheduler-badge online";
  } else {
    badge.textContent = `스케줄러: OFFLINE · 마지막 응답 ${sched.seconds_ago}초 전`;
    badge.className = "scheduler-badge offline";
  }

  const container = document.getElementById("accounts-container");
  container.innerHTML = "";
  const accounts = s.accounts || [];
  if (accounts.length === 0) {
    container.innerHTML = '<p class="hint">오늘 아직 실행된 배치/단발 작업이 없습니다.</p>';
    return;
  }
  const stepNames = s.step_names || [];
  const stepLabels = s.step_labels || {};

  for (const acc of accounts) {
    const asum = acc.summary || {};
    const accDiv = document.createElement("div");
    accDiv.className = "account-block";

    const heading = document.createElement("h3");
    heading.textContent = `${acc.account_id} — 완료 ${asum.completed || 0} / 전체 ${asum.total || 0}` +
      ` (실패 ${asum.failed || 0}, 검토 필요 ${asum.review || 0})`;
    accDiv.appendChild(heading);

    const table = document.createElement("div");
    table.className = "posts-table";

    const header = document.createElement("div");
    header.className = "posts-row posts-header";
    header.innerHTML = `<div class="col-post">게시물</div>` +
      stepNames.map((n) => `<div class="col-step">${stepLabels[n] || n}</div>`).join("");
    table.appendChild(header);

    for (const post of acc.posts) {
      table.appendChild(_buildPostRow(post, stepNames, stepLabels));
    }
    accDiv.appendChild(table);
    container.appendChild(accDiv);
  }
}

function _buildPostRow(post, stepNames, stepLabels) {
  const row = document.createElement("div");
  row.className = "posts-row";

  const postCell = document.createElement("div");
  postCell.className = "col-post";
  postCell.innerHTML = `
    <div class="post-title">${post.title || post.topic || post.post_id}</div>
    <div class="post-id">${post.post_id} · ${POST_STATUS_LABELS[post.status] || post.status}</div>
  `;
  row.appendChild(postCell);

  const steps = post.steps || {};
  for (const stepName of stepNames) {
    const step = steps[stepName] || { status: "PENDING", attempt: 0 };
    const cell = document.createElement("div");
    cell.className = `col-step ${STEP_STATUS_CLASS[step.status] || ""}`;
    if (step.last_error) cell.title = step.last_error;

    const label = document.createElement("div");
    label.className = "step-status";
    label.textContent = step.status + (step.attempt > 1 ? ` (${step.attempt}회)` : "");
    cell.appendChild(label);

    const btn = document.createElement("button");
    btn.className = "retry-btn";
    btn.textContent = `${stepLabels[stepName] || stepName}부터 재시도`;
    btn.addEventListener("click", () => retryStep(post.post_id, stepName, btn));
    cell.appendChild(btn);

    row.appendChild(cell);
  }
  return row;
}

async function retryStep(postId, step, btn) {
  if (step === "NAVER_DRAFT") {
    const ok = confirm(
      `${postId}의 NAVER_DRAFT를 강제로 재시도합니다.\n` +
      "이미 임시저장이 완료된 글이라도 다시 저장을 시도합니다(중복 방지 예외). 계속할까요?"
    );
    if (!ok) return;
  }
  btn.disabled = true;
  const original = btn.textContent;
  btn.textContent = "재시도 요청 중...";
  try {
    await api("/api/retry", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ post_id: postId, step }),
    });
    btn.textContent = "재시도 시작됨";
  } catch (e) {
    btn.textContent = "실패: " + e.message;
    setTimeout(() => {
      btn.textContent = original;
      btn.disabled = false;
    }, 3000);
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
