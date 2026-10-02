const $ = id => document.getElementById(id);
let currentSnapshot = null;
let currentSnapshotText = null;
let requestVersion = 0;

async function get(path, keepSerialized = false) {
  const response = await fetch(path);
  const serialized = await response.text();
  const value = JSON.parse(serialized);
  if (!response.ok) throw Error(value.error || '请求失败');
  return keepSerialized ? {value, serialized} : value;
}

function showError(error) {
  $('status').textContent = '加载失败：' + error.message;
}

function showDetail(title, data) {
  $('detailTitle').textContent = title;
  $('detail').textContent = JSON.stringify(data, null, 2);
}

function setButtons(enabled) {
  for (const id of ['raw', 'download', 'snapshotDownload']) $(id).disabled = !enabled;
}

function renderRecords(items, target, policy = false) {
  $(target).replaceChildren();
  const snapshot = currentSnapshot;
  const version = requestVersion;
  for (const item of items) {
    const row = document.createElement('div');
    row.className = 'record';
    const button = document.createElement('button');
    const id = policy ? item.policy_id : item.evidence_id;
    button.textContent = id;
    button.setAttribute('aria-label', '查看 ' + id + ' 的原始来源');
    button.onclick = async () => {
      try {
        const path = '/cases/' + encodeURIComponent(snapshot.case_id) + '/' +
          (policy ? 'policies' : 'evidence') + '/' + encodeURIComponent(id) +
          '?snapshot_id=' + encodeURIComponent(snapshot.snapshot_id);
        const detail = await get(path);
        if (version === requestVersion) showDetail(id + ' · 原始来源', detail);
      } catch (error) {
        if (version === requestVersion) showError(error);
      }
    };
    const text = document.createElement('p');
    text.textContent = policy ? item.rule : item.fact;
    const source = document.createElement('span');
    source.className = 'small';
    source.textContent = '来源：' + item.source;
    row.append(button, text, source);
    $(target).append(row);
  }
}

async function load() {
  const version = ++requestVersion;
  const caseId = $('case').value;
  currentSnapshot = null;
  currentSnapshotText = null;
  setButtons(false);
  for (const id of ['facts', 'policies', 'issues']) $(id).replaceChildren();
  $('origin').textContent = '正在核对来源';
  $('factsTitle').textContent = '事实记录';
  $('status').textContent = '正在读取同一版本的原始记录、证据与来源映射…';
  showDetail('来源与计算', '加载中');
  try {
    const loaded = await get('/cases/' + encodeURIComponent(caseId) + '/snapshot', true);
    if (version !== requestVersion) return;
    const snapshot = loaded.value;
    currentSnapshot = snapshot;
    currentSnapshotText = loaded.serialized;
    const pack = snapshot.evidence_pack;
    const audit = snapshot.audit;
    const synthetic = audit.data_origin === 'synthetic';
    const origins = {synthetic: '合成数据 · 自设规则', organizer_sample: '主办方样例', unverified_input: '来源未核实'};
    $('origin').textContent = origins[audit.data_origin] || '来源未核实';
    $('origin').className = 'badge' + (synthetic ? ' synthetic' : '');
    $('factsTitle').textContent = '事实记录 · ' + pack.facts.length + ' 条';
    $('status').textContent = pack.case_id + ' · ' +
      (audit.requires_policy_or_data_review ? '存在需要核实的数据或政策问题' : '已生成证据与来源映射') +
      ' · 快照 ' + snapshot.snapshot_id.slice(0, 12) + ' · 规范化版本 ' + snapshot.normalizer_version;
    for (const issue of audit.issues) {
      const element = document.createElement('div');
      element.className = 'issue' + (issue.severity === 'info' ? ' info' : '');
      element.textContent = issue.code + ' — ' + issue.message;
      $('issues').append(element);
    }
    renderRecords(pack.facts, 'facts');
    renderRecords(pack.policy, 'policies', true);
    showDetail('数据核对与计算结果', audit);
    setButtons(true);
  } catch (error) {
    if (version === requestVersion) showError(error);
  }
}

function download(value, filename, serialized = null) {
  const link = document.createElement('a');
  const url = URL.createObjectURL(new Blob([serialized ?? JSON.stringify(value, null, 2)], {type: 'application/json'}));
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

$('case').onchange = load;
$('raw').onclick = () => {
  if (currentSnapshot) showDetail(currentSnapshot.case_id + ' · 同一快照的原始 JSON', currentSnapshot.raw);
};
$('download').onclick = () => {
  if (currentSnapshot) download(currentSnapshot.evidence_pack, currentSnapshot.case_id + '.evidence_pack.json');
};
$('snapshotDownload').onclick = () => {
  // Preserve the server serialization: JS would turn JSON 5.0 into 5 on re-encoding.
  if (currentSnapshot) download(currentSnapshot, currentSnapshot.case_id + '.snapshot.json', currentSnapshotText);
};
setButtons(false);
(async () => {
  try {
    for (const item of await get('/cases')) {
      const option = document.createElement('option');
      option.value = item.case_id;
      option.textContent = item.case_id + ' · ' + item.dispute_type;
      $('case').append(option);
    }
    await load();
  } catch (error) {
    showError(error);
  }
})();
