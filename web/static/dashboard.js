let allLogs = [];
let currentServer = null;
let filteredCache = [];

const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
}[c]));

async function fetchData() {
    try {
        const response = await fetch('/api/logs_json');
        if (response.status === 403) {
            window.location.href = '/';
            return;
        }
        allLogs = await response.json();
        if (!currentServer) {
            renderGrid();
        } else {
            renderLogs();
        }
    } catch (error) {
        console.error(error);
    }
}

function renderGrid() {
    const el = document.getElementById('server-list');
    const servers = {};
    allLogs.forEach(log => {
        if (!servers[log.guild_id]) {
            servers[log.guild_id] = {
                id: log.guild_id,
                name: log.guild_name,
                icon: log.guild_icon,
                count: 0,
            };
        }
        servers[log.guild_id].count += 1;
    });

    if (!Object.keys(servers).length) {
        el.innerHTML = '<div class="empty">아직 기록된 로그가 없습니다.</div>';
        return;
    }

    el.innerHTML = Object.values(servers).map(server => {
        const fallback = esc(server.name)[0] || '?';
        const iconEl = server.icon
            ? `<img class="srv-icon" src="${esc(server.icon)}" onerror="this.outerHTML='<div class=srv-icon-placeholder>${fallback}</div>'">`
            : `<div class="srv-icon-placeholder">${fallback}</div>`;
        return `
            <div class="srv" onclick="selectServer('${esc(server.id)}','${esc(server.name)}')">
                ${iconEl}
                <div>
                    <div class="srv-name">${esc(server.name)}</div>
                    <div class="srv-count">${server.count}개의 로그</div>
                </div>
            </div>
        `;
    }).join('');
}

function selectServer(id, name) {
    currentServer = id;
    document.getElementById('grid-view').style.display = 'none';
    document.getElementById('log-view').style.display = 'block';
    document.getElementById('log-title').textContent = name;
    document.querySelectorAll('.filters input').forEach(input => {
        input.value = '';
    });
    renderLogs();
}

function showGrid() {
    currentServer = null;
    document.getElementById('log-view').style.display = 'none';
    document.getElementById('grid-view').style.display = 'block';
    renderGrid();
}

function renderLogs() {
    const userFilter = document.getElementById('f-user').value.toLowerCase();
    const commandFilter = document.getElementById('f-cmd').value.toLowerCase();
    const detailFilter = document.getElementById('f-detail').value.toLowerCase();
    const el = document.getElementById('log-list');

    filteredCache = allLogs.filter(log =>
        log.guild_id === currentServer
        && log.user.toLowerCase().includes(userFilter)
        && log.command.toLowerCase().includes(commandFilter)
        && log.details.toLowerCase().includes(detailFilter)
    );

    if (!filteredCache.length) {
        el.innerHTML = '<div class="empty">조건에 맞는 로그가 없습니다.</div>';
        return;
    }

    el.innerHTML = filteredCache.map((log, index) => {
        const chunks = log.time.split(' ');
        const timeStr = chunks.length > 1 ? `${chunks[0].substring(5).replace('-', '/')} ${chunks[1].substring(0, 5)}` : chunks[0];
        return `
            <div class="log" onclick="showDetail(${index})">
                <span class="log-time">${esc(timeStr)}</span>
                <span class="log-user">${esc(log.user)}</span>
                <span class="log-cmd">/${esc(log.command)}</span>
                <span class="log-detail">${esc(log.details)}</span>
            </div>
        `;
    }).join('');
}

function showDetail(index) {
    const log = filteredCache[index];
    if (!log) return;
    document.getElementById('modal-body').innerHTML = [
        ['시간', log.time],
        ['서버', log.guild_name],
        ['유저', log.user],
        ['명령어', `/${log.command}`],
        ['상세', log.details || '-'],
    ].map(([key, value]) => `
        <div class="modal-row">
            <div class="modal-label">${key}</div>
            <div class="modal-value">${esc(value)}</div>
        </div>
    `).join('');
    document.getElementById('modal-bg').style.display = 'block';
}

function closeModal() {
    document.getElementById('modal-bg').style.display = 'none';
}

document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
        closeModal();
    }
});

fetchData();
setInterval(fetchData, 5000);
