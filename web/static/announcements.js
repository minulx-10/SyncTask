const state = { guilds: [], templates: [], targetTypes: [], user: null, busy: false };
const form = document.getElementById('announcement-form');
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
}[c]));

function setMessage(text, type) {
    const el = document.getElementById('message');
    el.textContent = text || '';
    el.className = `message ${text ? type : ''}`;
}

function getPayload() {
    const fd = new FormData(form);
    return {
        guild_id: fd.get('guild_id') || '',
        channel_id: fd.get('channel_id') || '',
        target_type: fd.get('target_type') || '전체',
        target_label: fd.get('target_label') || '',
        template_key: fd.get('template_key') || 'general',
        title: fd.get('title') || '',
        body: fd.get('body') || '',
        date_text: fd.get('date_text') || '',
        location: fd.get('location') || '',
        deadline: fd.get('deadline') || '',
        materials: fd.get('materials') || '',
        note: fd.get('note') || '',
        scheduled_at: fd.get('scheduled_at') || '',
    };
}

function setDefaultSchedule() {
    const target = new Date(Date.now() + 10 * 60 * 1000);
    target.setSeconds(0, 0);
    const local = new Date(target.getTime() - target.getTimezoneOffset() * 60000);
    document.getElementById('scheduled_at').value = local.toISOString().slice(0, 16);
}

function selectedGuild() {
    const id = document.getElementById('guild_id').value;
    return state.guilds.find(guild => guild.id === id);
}

function renderUser() {
    const userEl = document.getElementById('user-pill');
    const logLink = document.getElementById('log-link');
    if (!state.user) return;
    userEl.textContent = `${state.user.name}`;
    logLink.style.display = state.user.is_operator ? 'inline-flex' : 'none';
}

function renderGuilds() {
    const guildSelect = document.getElementById('guild_id');
    const noAccess = document.getElementById('no-access');
    const formPanel = document.getElementById('form-panel');
    if (!state.guilds.length) {
        guildSelect.innerHTML = '<option value="">접근 가능한 서버 없음</option>';
        noAccess.style.display = 'block';
        formPanel.style.opacity = '0.55';
        form.querySelectorAll('input, select, textarea, button').forEach(el => {
            el.disabled = true;
        });
        return;
    }

    noAccess.style.display = 'none';
    formPanel.style.opacity = '1';
    form.querySelectorAll('input, select, textarea, button').forEach(el => {
        el.disabled = false;
    });
    guildSelect.innerHTML = state.guilds.map(guild => `<option value="${esc(guild.id)}">${esc(guild.name)}</option>`).join('');
    renderChannels();
}

function renderChannels() {
    const channelSelect = document.getElementById('channel_id');
    const guild = selectedGuild();
    const channels = guild ? guild.channels : [];
    channelSelect.innerHTML = channels.length
        ? channels.map(channel => `<option value="${esc(channel.id)}">${esc(channel.name)}</option>`).join('')
        : '<option value="">발송 가능한 채널 없음</option>';
    loadAnnouncements();
    updatePreview();
}

function renderTemplateOptions() {
    document.getElementById('template_key').innerHTML = state.templates
        .map(template => `<option value="${esc(template.key)}">${esc(template.label)}</option>`)
        .join('');
    document.getElementById('target_type').innerHTML = state.targetTypes
        .map(type => `<option value="${esc(type)}">${esc(type)}</option>`)
        .join('');
    updateBodyLabel();
}

function updateBodyLabel() {
    const key = document.getElementById('template_key').value;
    const template = state.templates.find(item => item.key === key);
    document.getElementById('body-label').textContent = template ? template.body_label : '내용';
}

function renderPreview(preview) {
    const el = document.getElementById('preview');
    el.style.borderLeftColor = preview.color || '#5865f2';
    el.innerHTML = `
        <div class="preview-title">${esc(preview.title)}</div>
        <div class="preview-body">${esc(preview.description)}</div>
        <div class="preview-fields">
            ${(preview.fields || []).map(field => `
                <div>
                    <div class="preview-field-name">${esc(field.name)}</div>
                    <div class="preview-field-value">${esc(field.value)}</div>
                </div>
            `).join('')}
        </div>
        <div class="preview-footer">${esc(preview.footer)}</div>
    `;
}

let previewTimer = null;
function queuePreview() {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(updatePreview, 180);
}

async function updatePreview() {
    if (!state.guilds.length) return;
    try {
        const response = await fetch('/api/announcements/preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(getPayload()),
        });
        const data = await response.json();
        if (!data.ok) throw new Error(data.error || '미리보기 실패');
        renderPreview(data.preview);
        document.getElementById('preview-status').textContent = '자동 갱신';
    } catch (error) {
        document.getElementById('preview-status').textContent = error.message;
    }
}

function statusClass(status) {
    if (status === 'sent') return 'sent';
    if (status === 'failed') return 'failed';
    if (status === 'cancelled') return 'cancelled';
    return '';
}

function compactTime(value) {
    if (!value) return '';
    return value.replace(/^\d{4}-/, '').replace('-', '/').slice(0, 14);
}

function renderAnnouncements(items) {
    const list = document.getElementById('announcement-list');
    if (!items.length) {
        list.innerHTML = '<div class="empty">등록된 공지가 없습니다.</div>';
        return;
    }
    list.innerHTML = items.map(item => `
        <article class="item">
            <div class="item-top">
                <div class="item-title">
                    <strong>${esc(item.preview.title)}</strong>
                    <div class="item-meta">${esc(item.guild_name)} · ${esc(item.channel_name)} · ${esc(item.target_display)} · ${compactTime(item.scheduled_at)}</div>
                </div>
                <span class="badge ${statusClass(item.status)}">${esc(item.status_label)}</span>
            </div>
            <div class="item-body">${esc(item.preview.description).slice(0, 260)}</div>
            ${item.last_error ? `<div class="item-body" style="color:#ffb3b4;">${esc(item.last_error)}</div>` : ''}
            <div class="item-actions">
                ${item.can_send_now ? `<button class="small-btn warn" onclick="sendNow(${item.id})">지금 발송</button>` : ''}
                ${item.can_cancel ? `<button class="small-btn danger" onclick="cancelAnnouncement(${item.id})">취소</button>` : ''}
            </div>
        </article>
    `).join('');
}

async function loadAnnouncements() {
    if (!state.guilds.length) {
        renderAnnouncements([]);
        return;
    }
    const guildId = document.getElementById('guild_id').value;
    const url = guildId ? `/api/announcements?guild_id=${encodeURIComponent(guildId)}` : '/api/announcements';
    try {
        const response = await fetch(url);
        const data = await response.json();
        if (!data.ok) throw new Error(data.error || '목록 조회 실패');
        renderAnnouncements(data.announcements || []);
        document.getElementById('list-status').textContent = `${(data.announcements || []).length}개`;
    } catch (error) {
        document.getElementById('announcement-list').innerHTML = `<div class="empty">${esc(error.message)}</div>`;
    }
}

async function cancelAnnouncement(id) {
    const response = await fetch(`/api/announcements/${id}/cancel`, { method: 'POST' });
    const data = await response.json();
    setMessage(data.ok ? '예약 공지를 취소했습니다.' : (data.error || '취소할 수 없습니다.'), data.ok ? 'ok' : 'err');
    loadAnnouncements();
}

async function sendNow(id) {
    const response = await fetch(`/api/announcements/${id}/send_now`, { method: 'POST' });
    const data = await response.json();
    setMessage(data.ok ? '공지 발송을 완료했습니다.' : (data.error || '발송에 실패했습니다.'), data.ok ? 'ok' : 'err');
    loadAnnouncements();
}

async function loadContext() {
    try {
        const response = await fetch('/api/announcement_context');
        const data = await response.json();
        state.user = data.user;
        state.guilds = data.guilds || [];
        state.templates = data.templates || [];
        state.targetTypes = data.target_types || ['전체'];
        renderUser();
        renderTemplateOptions();
        renderGuilds();
        document.getElementById('context-status').textContent = `${state.guilds.length}개 서버`;
        setDefaultSchedule();
        updatePreview();
        loadAnnouncements();
    } catch (error) {
        document.getElementById('context-status').textContent = error.message;
    }
}

form.addEventListener('input', queuePreview);
form.addEventListener('change', event => {
    if (event.target.id === 'guild_id') renderChannels();
    if (event.target.id === 'template_key') updateBodyLabel();
    queuePreview();
});

form.addEventListener('submit', async event => {
    event.preventDefault();
    if (state.busy) return;
    state.busy = true;
    setMessage('', '');
    const submitter = event.submitter;
    const action = submitter?.dataset.action || 'schedule';
    const fd = new FormData(form);
    fd.set('action', action);
    document.querySelectorAll('.btn').forEach(btn => { btn.disabled = true; });
    try {
        const response = await fetch('/api/announcements', { method: 'POST', body: fd });
        const data = await response.json();
        if (!data.ok) {
            setMessage(data.send_error || data.error || '처리에 실패했습니다.', 'err');
        } else {
            setMessage(action === 'immediate' ? '공지 발송을 완료했습니다.' : '공지 예약을 저장했습니다.', 'ok');
            form.reset();
            renderGuilds();
            setDefaultSchedule();
        }
        updatePreview();
        loadAnnouncements();
    } catch (error) {
        setMessage(error.message, 'err');
    } finally {
        state.busy = false;
        document.querySelectorAll('.btn').forEach(btn => { btn.disabled = false; });
    }
});

loadContext();
setInterval(loadAnnouncements, 15000);
