'use strict';

const paths = {
  arrows: '<path d="M4 7h16m-5-5 5 5-5 5M20 17H4m5-5-5 5 5 5"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 0 1 5 .3c0 1.7-2.5 1.9-2.5 3.7m0 3h.01"/>',
  shield: '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z"/><path d="m8 12 3 3 5-6"/>',
  send: '<path d="m21 3-7 18-4-7-7-4L21 3ZM10 14 21 3"/>',
  file: '<path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8l-5-5Z"/><path d="M14 3v5h5M9 13h6m-6 4h4"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="1.5"/><path d="m3 17 5-5 4 4 4-6 5 7"/>',
  video: '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="m10 9 5 3-5 3V9Z"/>',
  archive: '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M12 3v3m-2 0h2v3h2v3h-2v3m-2 0h4v3h-4z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  refresh: '<path d="M20 7v5h-5M4 17v-5h5M5.5 7a7 7 0 0 1 11.6-1L20 9M4 15l2.9 3A7 7 0 0 0 18.5 17"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  inbox: '<path d="m3 13 4-8h10l4 8v7H3v-7Zm0 0h5l2 3h4l2-3h5"/>',
  wifi: '<path d="M3 8a14 14 0 0 1 18 0M6 12a9 9 0 0 1 12 0M9 16a4.5 4.5 0 0 1 6 0m-3 4h.01"/>',
  copy: '<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',
  computer: '<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8m-4-4v4"/>',
  phone: '<rect x="6" y="2" width="12" height="20" rx="3"/><path d="M10 5h4m-3 14h2"/>',
  tablet: '<rect x="3" y="2" width="18" height="20" rx="3"/><path d="M11 19h2"/>',
  chat: '<path d="M5 4h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H9l-5 3v-3a2 2 0 0 1-1-2V6a2 2 0 0 1 2-2Z"/><path d="M7 9h10M7 13h7"/>',
  leaf: '<path d="M20 3C8 2 2 8 6 16c8 5 15-2 14-13ZM4 21 16 9M9 16v-5m0 5h5"/>',
  sparkles: '<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Zm7-2 .8 2.2L22 4l-2.2.8L19 7l-.8-2.2L16 4l2.2-.8L19 1Z"/>',
  'arrow-up-right': '<path d="M6 18 18 6M6 6h12v12"/>',
  'arrow-right': '<path d="M4 12h16m-6-6 6 6-6 6"/>',
  download: '<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
  trash: '<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  pause: '<path d="M8 5v14m8-14v14"/>',
  play: '<path d="m7 4 14 8-14 8V4Z"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  power: '<path d="M12 2v10M6 5a9 9 0 1 0 12 0"/>',
  upload: '<path d="M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5"/>'
};
const $ = id => document.getElementById(id);
const icon = name => `<svg viewBox="0 0 24 24" aria-hidden="true">${paths[name] || paths.file}</svg>`;
document.querySelectorAll('[data-icon]').forEach(node => { node.innerHTML = icon(node.dataset.icon); });
const storage = {
  get(key, fallback = null) { try { return JSON.parse(localStorage.getItem('wifidrop:' + key)) ?? fallback; } catch { return fallback; } },
  set(key, value) { try { localStorage.setItem('wifidrop:' + key, JSON.stringify(value)); } catch { /* Private browsing can disable persistence. */ } }
};
let token = storage.get('token', '');
let state = null;
let currentView = 'transfer';
let currentFilter = 'all';
let stateTimer;
let toastTimer;
let stopped = false;
let polling = false;
let fileSignature = '';
let deviceSignature = '';
let messageSignature = '';
let roomDevices = [];
let targetOwner = '';
let selectedTarget = '';
let sendingMessage = false;
let pendingMessage = null;
let qrSignature = '';
let qrRequest = 0;
let pendingInvite = '';
let running = false;
const queue = [];
let resumables = storage.get('resumables', {});
if (!resumables || typeof resumables !== 'object' || Array.isArray(resumables)) resumables = {};

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function iconNode(name, className = '') {
  const node = el('span', className);
  node.innerHTML = icon(name);
  return node;
}
function iconButton(name, label, handler, className = '') {
  const node = el('button', 'icon-button ' + className);
  node.type = 'button'; node.title = label; node.setAttribute('aria-label', label);
  node.innerHTML = icon(name); node.addEventListener('click', handler);
  return node;
}
function toast(message) {
  $('toast').textContent = message; $('toast').hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { $('toast').hidden = true; }, 4500);
}
async function api(path, {method = 'GET', body, ...options} = {}) {
  const response = await fetch(path, {method, cache: 'no-store', headers: {
    ...(token ? {Authorization: 'Bearer ' + token} : {}),
    ...(body !== undefined ? {'Content-Type': 'application/json'} : {})
  }, ...(body !== undefined ? {body: JSON.stringify(body)} : {}), ...options});
  const result = await response.json();
  if (!response.ok) {
    const error = new Error(result.error || '操作失败，请重试。');
    error.status = response.status; error.data = result; throw error;
  }
  return result;
}
function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}
function typeFor(name) {
  const ext = name.toLowerCase().split('.').pop();
  if (['png','jpg','jpeg','gif','webp','heic','heif','avif','bmp','svg','raw','tiff','tif','dng'].includes(ext)) return 'image';
  if (['mp4','mov','mkv','avi','wmv','flv','m4v','webm','mpeg','mpg','ts','3gp'].includes(ext)) return 'video';
  if (['zip','rar','7z','gz','tar','bz2','xz'].includes(ext)) return 'archive';
  return 'file';
}
function connection(online, text) {
  $('connection-status').classList.toggle('offline', !online);
  $('connection-status').querySelector('span').textContent = text;
}
function setView(view) {
  currentView = view;
  $('transfer-view').hidden = view !== 'transfer' || !state;
  $('connect-view').hidden = view !== 'transfer' || Boolean(state);
  $('help-view').hidden = view !== 'help';
  $('breadcrumb').textContent = view === 'help' ? '使用指南' : '传输房间';
  document.querySelectorAll('[data-view]').forEach(button => button.classList.toggle('active', button.dataset.view === view));
}
function requireConnection(message) {
  state = null; setView(currentView); connection(false, '尚未连接');
  if (message) $('join-error').textContent = message;
}
async function confirmAction(title, description) {
  $('confirm-title').textContent = title; $('confirm-description').textContent = description;
  const dialog = $('confirm-dialog'); dialog.returnValue = 'cancel'; dialog.showModal();
  return new Promise(resolve => dialog.addEventListener('close', () => resolve(dialog.returnValue === 'confirm'), {once: true}));
}

async function poll() {
  if (polling || stopped || !token) return;
  polling = true;
  try {
    state = await api('/api/state');
    connection(true, '局域网已连接');
    setView(currentView); renderState();
  } catch (error) {
    if (error.status === 401) { token = ''; storage.set('token', ''); requireConnection('连接已失效，请重新扫码或输入连接码。'); }
    else connection(false, '连接中断 · 正在重试');
  } finally { polling = false; }
}
function renderState() {
  const admin = state.me.admin;
  $('room-host').textContent = '主机 · ' + state.host;
  for (const id of ['qr-card','open-folder','invite-actions','host-controls']) $(id).hidden = !admin;
  if (admin) {
    $('pairing-code').textContent = state.code;
    $('storage-info').textContent = `剩余空间 ${formatBytes(state.freeBytes)}`;
    $('toggle-invites').textContent = state.invitesEnabled ? '暂停新设备连接' : '允许新设备连接';
    $('pairing-code').style.textDecoration = state.invitesEnabled ? '' : 'line-through';
    const select = $('address-select');
    const urls = state.urls || [];
    if (select.dataset.urls !== JSON.stringify(urls)) {
      const previous = select.selectedIndex;
      select.replaceChildren(...urls.map((url, index) => {
        const option = el('option', '', new URL(url).origin); option.value = String(index); return option;
      }));
      if (!urls.length) select.append(el('option', '', '未找到局域网地址'));
      if (previous >= 0 && previous < urls.length) select.selectedIndex = previous;
      select.dataset.urls = JSON.stringify(urls);
    }
    updateQR();
  }
  roomDevices = [{id:'host', name:state.host, kind:'computer'}, ...state.devices];
  renderRecipients();
  renderDevices();
  renderMessages();
  renderFiles();
}

function deviceLabel(id, fallback) {
  if (id === 'all') return '整个房间';
  const device = roomDevices.find(entry => entry.id === id);
  if (!device) return fallback || '已移除设备';
  const duplicates = roomDevices.some(entry => entry.id !== id && entry.name === device.name);
  return duplicates && id !== 'host' ? device.name + ' · ' + id.slice(-4) : device.name;
}

function renderRecipients() {
  const select = $('target-select');
  const targets = [
    {id:'all', label:'整个房间'},
    ...roomDevices.filter(device => device.id !== state.me.id)
      .map(device => ({id:device.id, label:deviceLabel(device.id)}))
  ];
  if (targetOwner !== state.me.id) {
    targetOwner = state.me.id;
    selectedTarget = storage.get('target:' + targetOwner, state.me.admin ? 'all' : 'host');
  }
  if (!targets.some(target => target.id === selectedTarget)) {
    // Losing a selected recipient must never silently turn a private send into a broadcast.
    selectedTarget = '';
    targets.unshift({id:'', label:'原收件人已移除，请重新选择'});
  }
  const signature = JSON.stringify(targets);
  if (select.dataset.signature !== signature) {
    select.replaceChildren(...targets.map(target => {
      const option = el('option', '', target.label);
      option.value = target.id;
      option.disabled = !target.id;
      return option;
    }));
    select.dataset.signature = signature;
  }
  select.value = selectedTarget;
  updateComposer();
}

function selectRecipient(id, focus = false) {
  if (!state || id === state.me.id || (id !== 'all' && !roomDevices.some(device => device.id === id))) {
    toast('这台设备已移除，请选择其他收件人');
    return;
  }
  selectedTarget = id;
  storage.set('target:' + state.me.id, id);
  $('target-select').value = id;
  $('message-status').textContent = '';
  updateComposer();
  if (focus) $('message-input').focus();
}

function updateComposer() {
  const note = !selectedTarget ? '请选择收件人。'
    : selectedTarget === 'all' ? '文字和文件将分享给整个房间，包括之后加入的设备。'
    : '文字和文件将发给「' + deviceLabel(selectedTarget) + '」。';
  $('recipient-note').textContent = note;
  $('send-message').disabled = !state || !selectedTarget || sendingMessage || !$('message-input').value.trim();
  $('choose-files').disabled = !state || !selectedTarget;
  $('drag-label').textContent = selectedTarget ? '松开发送给' + deviceLabel(selectedTarget) : '请先选择收件人';
}

function routeLabel(record) {
  const sender = deviceLabel(record.owner, record.sender);
  const target = deviceLabel(record.target, record.targetName);
  return sender + ' → ' + target;
}

function newClientId() {
  // randomUUID is restricted to secure contexts; LAN HTTP still supports getRandomValues.
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
  return [hex.slice(0,8),hex.slice(8,12),hex.slice(12,16),hex.slice(16,20),hex.slice(20)].join('-');
}

async function sendMessage(event) {
  event.preventDefault();
  const input = $('message-input');
  const text = input.value.trim();
  const target = selectedTarget;
  if (!state || !target || !text || sendingMessage) return;
  if (!pendingMessage || pendingMessage.text !== text || pendingMessage.target !== target) {
    pendingMessage = {text, target, clientId:newClientId()};
  }
  sendingMessage = true;
  $('message-status').textContent = '';
  updateComposer();
  try {
    await api('/api/messages', {method:'POST', body:pendingMessage});
    pendingMessage = null;
    if (input.value.trim() === text && selectedTarget === target) input.value = '';
    await poll();
  } catch (error) {
    $('message-status').textContent = error.status ? error.message : '消息发送状态未知，请重试。';
    if (error.status === 401) requireConnection(error.message);
  } finally {
    sendingMessage = false;
    updateComposer();
  }
}

function renderMessages() {
  const messages = state.messages;
  const signature = JSON.stringify([state.me.id, messages, roomDevices.map(device => [device.id, device.name])]);
  if (messageSignature === signature) return;
  messageSignature = signature;
  const list = $('message-list');
  const followLatest = list.scrollHeight - list.clientHeight - list.scrollTop < 24;
  const previousScroll = list.scrollTop;
  list.hidden = !messages.length;
  $('empty-messages').hidden = Boolean(messages.length);
  $('message-count').textContent = messages.length;
  list.replaceChildren(...messages.map(message => {
    const own = message.owner === state.me.id;
    const row = el('article', own ? 'message-row own' : 'message-row');
    const route = el('span', 'message-route', routeLabel(message));
    const timestamp = new Date(message.created * 1000);
    const time = el('time', 'message-time', timestamp.toLocaleString('zh-CN', {
      month:'numeric', day:'numeric', hour:'2-digit', minute:'2-digit'
    }));
    time.dateTime = timestamp.toISOString();
    const heading = el('div','message-heading');
    heading.append(route, time);
    const content = el('div','message-bubble');
    content.append(heading, el('p','message-text',message.text));
    if (!own) {
      const target = message.target === 'all' ? 'all' : message.owner;
      const canReply = target === 'all' || roomDevices.some(device => device.id === target);
      if (canReply) {
        const reply = el('button','text-button message-reply',target === 'all' ? '回复房间' : '回复');
        reply.type = 'button';
        reply.dataset.reply = target;
        reply.addEventListener('click', () => selectRecipient(target, true));
        content.append(reply);
      }
    }
    row.append(content);
    return row;
  }));
  list.scrollTop = followLatest ? list.scrollHeight : previousScroll;
}
async function updateQR() {
  if (!state?.me.admin) return;
  const index = Math.max(0, $('address-select').selectedIndex);
  const signature = `${state.urls[index]}:${state.invitesEnabled}`;
  if (qrSignature === signature) return;
  qrSignature = signature;
  const request = ++qrRequest;
  $('qr-image').hidden = true; $('qr-placeholder').hidden = false;
  if (!state.invitesEnabled) { $('qr-placeholder').textContent = '已暂停新设备连接'; return; }
  if (!state.urls.length) { $('qr-placeholder').textContent = '请将电脑连接 Wi-Fi 或局域网后，重新启动近传。'; return; }
  $('qr-placeholder').textContent = '正在生成二维码…';
  try {
    const response = await fetch('/api/qr?index=' + index, {headers: {Authorization: 'Bearer ' + token}});
    if (!response.ok) throw new Error('二维码生成失败');
    const svg = await response.text();
    if (request !== qrRequest) return;
    $('qr-image').src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
    $('qr-image').hidden = false; $('qr-placeholder').hidden = true;
  } catch {
    if (request === qrRequest) { $('qr-placeholder').textContent = '二维码加载失败，稍后自动重试'; qrSignature = ''; }
  }
}
function renderDevices() {
  const devices = roomDevices;
  const signature = JSON.stringify([state.me.id, devices.map(d => ({...d, seen:d.seen ? Date.now()/1000 - d.seen < 30 : true}))]);
  if (signature === deviceSignature) return;
  deviceSignature = signature;
  $('device-count').textContent = devices.length;
  $('device-list').replaceChildren(...devices.map(device => {
    const row = el('div','device'); row.append(iconNode(device.kind,'device-icon'));
    const info = el('div','device-info'); const name = el('div','device-name',deviceLabel(device.id));
    if (device.id === state.me.id) name.append(el('span','you','本机'));
    const active = device.id === 'host' || Date.now()/1000 - device.seen < 30;
    const detail = el('div','device-detail'); detail.append(el('i', active ? '' : 'away'), document.createTextNode(device.id === 'host' ? '房间主机' : active ? '在线' : '暂未活动'));
    info.append(name,detail); row.append(info);
    if (device.id !== state.me.id) row.append(iconButton('send', '发给 ' + deviceLabel(device.id), () => selectRecipient(device.id, true)));
    if (state.me.admin && device.id !== 'host') row.append(iconButton('close','移除设备',async () => {
      if (!await confirmAction('移除这台设备？', `${device.name} 将断开连接，需要重新扫码才能继续使用。`)) return;
      try { await api('/api/devices/' + device.id, {method:'DELETE'}); await poll(); toast('设备已移除'); } catch (error) { toast(error.message); }
    },'device-remove'));
    return row;
  }));
  if (devices.length === 1) $('device-list').append(el('p','no-devices','其他设备加入后会出现在这里。'));
}
function renderFiles(force = false) {
  if (!state) return;
  const search = $('file-search').value.toLowerCase().trim();
  const signature = JSON.stringify([state.me.id,state.files,currentFilter,search,roomDevices.map(d => [d.id,d.name])]);
  if (!force && fileSignature === signature) return;
  fileSignature = signature;
  $('file-count').textContent = state.files.length;
  const files = state.files.filter(file => {
    const sent = file.owner === state.me.id;
    return (currentFilter === 'all' || (currentFilter === 'sent' ? sent : !sent)) && file.name.toLowerCase().includes(search);
  });
  $('empty-files').hidden = files.length > 0;
  $('empty-files').querySelector('h3').textContent = search ? '没有找到这份文件' : '暂无文件';
  $('empty-files').querySelector('p').textContent = search ? '试试其他文件名' : '发送或接收的文件会出现在这里';
  $('file-list').replaceChildren(...files.map(file => {
    const type = typeFor(file.name); const row = el('div','file-row');
    row.append(iconNode(type, 'file-type-icon ' + type));
    const info = el('div','file-info'); const name = el('div','file-name',file.name); name.title = file.name;
    const sent = file.owner === state.me.id;
    const meta = el('div','file-meta');
    const date = new Date(file.created * 1000);
    meta.append(el('span','',formatBytes(file.size)), el('span','file-route',routeLabel(file)), el('span','',date.toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'})));
    info.append(name,meta); if (file.sha256) info.title = 'SHA-256: ' + file.sha256;
    const actions = el('div','file-actions');
    actions.append(iconButton('download','下载 ' + file.name,async () => {
      try {
        const result = await api('/api/files/' + file.id + '/ticket', {method:'POST',body:{}});
        const a = el('a'); a.href = result.url; a.download = file.name;
        document.body.append(a); a.click(); a.remove();
        toast('已交给浏览器下载，请查看下载项');
      } catch (error) { toast(error.message); }
    },'download-button'));
    if (state.me.admin || sent) actions.append(iconButton('trash','删除 ' + file.name,async () => {
      if (!await confirmAction('删除这份文件副本？', `将删除电脑 WiFiDrop 目录中的「${file.name}」，其他设备也将无法下载。最初选择的原文件不受影响。`)) return;
      try { await api('/api/files/' + file.id, {method:'DELETE'}); await poll(); toast('文件副本已删除'); } catch (error) { toast(error.message); }
    },'delete-button'));
    row.append(info,actions); return row;
  }));
}

// A quick, deterministic file identity for resume selection. This is NOT a
// cryptographic checksum. The server computes SHA-256 on the completed file.
async function fingerprint(file) {
  const slices = [file.slice(0,65536),file.slice(Math.max(0,file.size-65536))];
  let a = 2166136261, b = 5381;
  for (const slice of slices) {
    const bytes = new Uint8Array(await slice.arrayBuffer());
    for (const byte of bytes) { a = Math.imul(a ^ byte,16777619) >>> 0; b = (Math.imul(b,33) ^ byte) >>> 0; }
  }
  return `${file.size}:${file.lastModified}:${a.toString(16)}:${b.toString(16)}`;
}
function saveResumables() {
  const entries = Object.entries(resumables).sort((a,b)=>(b[1].updated||0)-(a[1].updated||0)).slice(0,128);
  resumables = Object.fromEntries(entries); storage.set('resumables',resumables);
}
async function addFiles(files) {
  if (!state) { toast('请先加入房间'); return; }
  const target = selectedTarget;
  if (!target) { toast('请先选择收件人'); return; }
  for (const file of files) {
    if (queue.some(item => item.target === target && item.file.name === file.name && item.file.size === file.size && item.file.lastModified === file.lastModified && !['done','cancelled'].includes(item.status))) continue;
    const item = {file,target,offset:0,status:'preparing',message:'正在准备文件…',xhr:null,id:null,started:0,initialOffset:0};
    queue.push(item); makeUploadRow(item);
    try {
      item.fingerprint = await fingerprint(file);
      if (item.status !== 'preparing') continue;
      item.key = file.name + '|' + item.fingerprint + '|' + item.target;
      const resume = resumables[item.key];
      if (resume) { item.id = resume.id; item.resumeSecret = resume.secret; }
      item.status = 'queued'; item.message = item.id ? '等待继续传输' : '等待发送'; updateUploadRow(item);
    } catch {
      if (item.status === 'preparing') {
        item.status = 'error'; item.message = '无法读取文件，请重新选择'; updateUploadRow(item);
      }
    }
  }
  pump();
}
function makeUploadRow(item) {
  const type = typeFor(item.file.name); const row = el('div','upload-item');
  row.append(iconNode(type,'file-type-icon ' + type));
  const main = el('div','upload-main'); const name = el('div','upload-name',item.file.name); name.title = item.file.name;
  const meta = el('div','upload-meta'); const status = el('span'); const percent = el('span'); meta.append(status,percent);
  const progress = el('div','upload-progress'); const bar = el('span'); progress.append(bar);
  const action = el('button','upload-action'); action.type = 'button';
  action.addEventListener('click',() => {
    if (item.status === 'uploading' || item.status === 'queued') {
      item.status = 'paused'; item.message = '已暂停，可继续'; item.xhr?.abort(); updateUploadRow(item);
    } else if (['paused','error'].includes(item.status)) {
      item.status = 'queued'; item.message = '等待继续传输'; updateUploadRow(item); pump();
    }
  });
  const cancel = iconButton('close','取消传输',() => cancelUpload(item),'upload-cancel');
  main.append(name,meta,progress); row.append(main,action,cancel); $('upload-queue').append(row);
  item.ui = {row,status,percent,bar,action,cancel}; updateUploadRow(item);
}
function updateUploadRow(item, progress = item.offset) {
  const ui = item.ui;
  const percent = item.file.size ? Math.min(100,progress / item.file.size * 100) : item.status === 'done' ? 100 : 0;
  ui.row.classList.toggle('error',item.status === 'error');
  ui.status.textContent = '收件人：' + deviceLabel(item.target) + ' · ' + item.message;
  ui.percent.textContent = `${formatBytes(progress)} / ${formatBytes(item.file.size)}`;
  ui.bar.style.width = percent.toFixed(2) + '%';
  ui.action.hidden = ['done','cancelled','preparing','completing','cancelling'].includes(item.status);
  ui.action.textContent = ['paused','error'].includes(item.status) ? '继续' : '暂停';
  ui.cancel.hidden = ['done','cancelled','completing','cancelling'].includes(item.status);
}
function chunkRequest(item, blob, offset) {
  return new Promise((resolve,reject) => {
    const xhr = new XMLHttpRequest(); item.xhr = xhr;
    xhr.open('PUT','/api/uploads/' + item.id); xhr.timeout = 120000;
    xhr.setRequestHeader('Authorization','Bearer ' + token);
    xhr.setRequestHeader('Upload-Offset',String(offset));
    xhr.setRequestHeader('Content-Type','application/octet-stream');
    xhr.upload.onprogress = event => {
      const sent = offset + event.loaded;
      const elapsed = Math.max(.2,(performance.now()-item.started)/1000);
      item.message = `正在发送 · ${formatBytes(Math.max(0,sent-item.initialOffset)/elapsed)}/s`;
      updateUploadRow(item,sent);
    };
    xhr.onload = () => {
      item.xhr = null;
      let body; try {body = JSON.parse(xhr.responseText);} catch {reject(new Error('连接中断，请继续重试'));return;}
      if (xhr.status === 409 && Number.isInteger(body.offset)) { resolve(body.offset); return; }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body.offset);
      else { const error = new Error(body.error || '传输失败，请继续重试'); error.status = xhr.status; reject(error); }
    };
    xhr.onerror = () => {item.xhr=null;reject(new Error('网络中断，请保持页面打开后继续'));};
    xhr.ontimeout = () => {item.xhr=null;reject(new Error('传输超时，点击继续重试'));};
    xhr.onabort = () => {item.xhr=null;reject(new Error('传输已暂停'));};
    xhr.send(blob);
  });
}
async function transfer(item) {
  item.status = 'uploading'; item.message = '正在连接接收端…'; updateUploadRow(item);
  try {
    const created = await api('/api/uploads',{method:'POST',body:{name:item.file.name,size:item.file.size,target:item.target,fingerprint:item.fingerprint,resumeId:item.id,resumeSecret:item.resumeSecret}});
    item.id = created.id; item.resumeSecret = created.resumeSecret || item.resumeSecret;
    item.offset = created.offset;
    resumables[item.key] = {id:item.id,secret:item.resumeSecret,updated:Date.now()}; saveResumables();
    if (item.status !== 'uploading') return;
    item.started = performance.now(); item.initialOffset = item.offset;
    while (!created.complete && item.offset < item.file.size && item.status === 'uploading') {
      const next = await chunkRequest(item,item.file.slice(item.offset,item.offset + (state?.chunkSize || 4194304)),item.offset);
      if (!Number.isInteger(next) || next < 0 || next > item.file.size) throw new Error('接收位置不正确，请重试');
      item.offset = next; updateUploadRow(item);
    }
    if (item.status !== 'uploading') return;
    if (!created.complete) {
      item.status = 'completing'; item.message = '正在核验并保存到电脑…'; updateUploadRow(item);
      await api('/api/uploads/' + item.id + '/complete',{method:'POST',body:{}});
    }
    item.status = 'done'; item.offset = item.file.size; item.message = '已送达 · 原文件内容已保存';
    delete resumables[item.key]; saveResumables(); updateUploadRow(item); await poll();
  } catch (error) {
    if (item.status === 'uploading' || item.status === 'completing') {
      item.status = 'error'; item.message = error.message;
      if (error.status === 401) requireConnection('连接已失效，请重新扫码连接后继续。');
      updateUploadRow(item);
    }
  }
}
async function pump() {
  if (running || stopped || !state) return;
  running = true;
  try {
    let item;
    while ((item = queue.find(entry => entry.status === 'queued')) && state && !stopped) await transfer(item);
  } finally { running = false; }
}
async function cancelUpload(item) {
  if (!await confirmAction('取消这次传输？', '电脑上尚未完成的文件分块会被删除。')) return;
  const previous = item.status; item.status = 'cancelling'; item.xhr?.abort(); item.message = '正在取消…'; updateUploadRow(item);
  // Let an in-flight creation request finish so its server-side ID can be removed.
  while (running && !item.id && previous === 'uploading') await new Promise(resolve => setTimeout(resolve,100));
  try {
    if (item.id) await api('/api/uploads/' + item.id,{method:'DELETE'});
    item.status = 'cancelled'; item.ui.row.remove(); delete resumables[item.key]; saveResumables();
  } catch (error) { item.status = 'error'; item.message = error.message; updateUploadRow(item); }
  pump();
}

async function join(invite = '') {
  const button = $('join-button'); button.disabled = true; $('join-error').textContent = '';
  try {
    const result = await api('/api/join',{method:'POST',body:{invite,code:$('pair-code').value.trim(),name:$('device-name').value.trim() || defaultDeviceName(),kind:deviceKind()}});
    token = result.token; storage.set('token',token); pendingInvite = '';
    await poll(); pump(); toast('连接成功，可以传文件了');
  } catch (error) { $('join-error').textContent = error.message; requireConnection(); }
  finally {button.disabled = false;}
}
function defaultDeviceName() {
  const ua = navigator.userAgent;
  if (/iPad/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)) return '我的 iPad';
  if (/iPhone/.test(ua)) return '我的 iPhone';
  if (/Android/.test(ua)) return '我的 Android 手机';
  if (/Macintosh/.test(ua)) return '我的 Mac';
  if (/Windows/.test(ua)) return '我的 Windows 电脑';
  return '我的设备';
}
function deviceKind() {
  const ua = navigator.userAgent;
  if (/iPad/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)) return 'tablet';
  if (/Android/.test(ua)) return /Mobile/.test(ua) ? 'phone' : 'tablet';
  return /iPhone|iPod/.test(ua) ? 'phone' : 'computer';
}
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); }
  catch {
    const input = el('textarea'); input.value = text; input.setAttribute('readonly','');
    document.body.append(input); input.select(); input.setSelectionRange(0,text.length);
    const ok = document.execCommand('copy'); input.remove(); if (!ok) throw new Error('复制失败，请手动选择地址');
  }
}

document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click',() => setView(button.dataset.view)));
document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click',() => {
  currentFilter = button.dataset.filter;
  document.querySelectorAll('[data-filter]').forEach(other => other.classList.toggle('selected',other === button)); renderFiles(true);
}));
$('file-search').addEventListener('input',() => renderFiles(true));
$('join-form').addEventListener('submit',event => {event.preventDefault(); join(pendingInvite);});
$('target-select').addEventListener('change',event => selectRecipient(event.target.value));
$('message-input').addEventListener('input',updateComposer);
$('message-form').addEventListener('submit',sendMessage);
$('choose-files').addEventListener('click',event => {event.stopPropagation(); $('file-input').click();});
$('file-input').addEventListener('change',event => {addFiles(Array.from(event.target.files)); event.target.value = '';});
$('refresh-files').addEventListener('click',async () => {await poll(); if (state) toast('文件列表已刷新');});
$('address-select').addEventListener('change',updateQR);
$('copy-link').addEventListener('click',async () => {
  const url = state?.urls[$('address-select').selectedIndex]; if (!url) return;
  try {await copyText(url);toast('连接链接已复制，在手机浏览器打开即可');} catch (error) {toast(error.message);}
});
$('open-folder').addEventListener('click',async () => {try {await api('/api/open-folder',{method:'POST',body:{}});} catch (error) {toast(error.message);}});
$('toggle-invites').addEventListener('click',async () => {try {await api('/api/invites',{method:'POST',body:{enabled:!state.invitesEnabled}});await poll();} catch (error) {toast(error.message);}});
$('rotate-invite').addEventListener('click',async () => {
  if (!await confirmAction('更新连接码和二维码？', '之前分享的连接链接和连接码将失效，已经连接的设备可以继续传输。')) return;
  try {await api('/api/invites',{method:'POST',body:{enabled:state.invitesEnabled,rotate:true}});await poll();toast('连接码已更新');} catch (error) {toast(error.message);}
});
$('shutdown').addEventListener('click',async () => {
  if (!await confirmAction('退出近传？', '所有设备将断开，正在传输的文件会中断。已确认的分块会保留，可在下次启动后继续。')) return;
  try {
    await api('/api/shutdown',{method:'POST',body:{}}); stopped = true; clearInterval(stateTimer);
    for (const item of queue) {item.status='paused';item.xhr?.abort();}
    $('transfer-view').replaceChildren(); const message = el('div','stopped-message');
    message.append(el('h2','','近传已退出'),el('p','','文件已保留。下次双击启动程序，即可再次连接。')); $('transfer-view').append(message);
    connection(false,'服务已关闭');
  } catch (error) {toast(error.message);}
});
let dragDepth = 0;
document.addEventListener('dragenter',event => {
  if (!state || !Array.from(event.dataTransfer?.types || []).includes('Files')) return;
  event.preventDefault(); dragDepth++; $('drag-overlay').hidden = false;
});
document.addEventListener('dragover',event => {if (state) event.preventDefault();});
document.addEventListener('dragleave',event => {event.preventDefault();dragDepth--;if (dragDepth<=0) {$('drag-overlay').hidden=true;dragDepth=0;}});
document.addEventListener('drop',event => {
  event.preventDefault();dragDepth=0;$('drag-overlay').hidden=true;
  if (state && event.dataTransfer?.files.length) addFiles(Array.from(event.dataTransfer.files));
});
window.addEventListener('beforeunload',event => {
  if (queue.some(item => ['uploading','completing','queued'].includes(item.status))) {event.preventDefault();event.returnValue='';}
});
document.addEventListener('visibilitychange',() => {if (!document.hidden) poll();});
window.addEventListener('online',poll);

async function bootstrap() {
  $('device-name').value = defaultDeviceName();
  setView('transfer');
  const hash = new URLSearchParams(location.hash.slice(1));
  if (hash.has('admin')) {token=hash.get('admin');storage.set('token',token);}
  pendingInvite = hash.get('join') || '';
  if (location.hash) history.replaceState(null,'',location.pathname + location.search);
  if (pendingInvite) {
    // Keep an already authenticated host session when testing its own QR link.
    if (token) await poll();
    if (!state) await join(pendingInvite);
  } else if (token) await poll();
  else requireConnection();
  stateTimer = setInterval(poll,2000);
}
bootstrap();
