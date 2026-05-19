/* ── home.js — 학생용 메인 대시보드 ── */
const state = {
    guilds: [],
    guildId: null,
    user: null,
    showTomorrow: false,
    eventsMonth: new Date().getMonth() + 1,
    eventsYear: new Date().getFullYear(),
};

const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[c]));

/* ── Clock ── */
function updateClock() {
    const now = new Date();
    const h = String(now.getHours()).padStart(2, '0');
    const m = String(now.getMinutes()).padStart(2, '0');
    const el = document.getElementById('hero-clock');
    if (el) el.textContent = `${h}:${m}`;
}
setInterval(updateClock, 10000);
updateClock();

/* ── Init ── */
async function init() {
    await loadGuilds();
    await checkSession();
    loadAll();
}

async function checkSession() {
    try {
        const r = await fetch('/api/me');
        if (r.ok) {
            const data = await r.json();
            if (data.ok && data.user && data.user.id !== '') {
                state.user = data.user;
                renderUser();
            }
        }
    } catch { /* not logged in */ }
}

function renderUser() {
    const pill = document.getElementById('user-pill');
    const announcements = document.getElementById('nav-announcements');
    const admin = document.getElementById('nav-admin');
    if (state.user) {
        pill.innerHTML = `<span>${esc(state.user.name)}</span>`;
        announcements.style.display = 'inline-flex';
        if (state.user.is_operator) admin.style.display = 'inline-flex';
    }
}

async function loadGuilds() {
    try {
        const r = await fetch('/api/public/guilds');
        const data = await r.json();
        state.guilds = data.guilds || [];
    } catch {
        state.guilds = [];
    }

    const select = document.getElementById('guild-select');
    if (!state.guilds.length) {
        select.innerHTML = '<option value="">서버 없음</option>';
        return;
    }
    select.innerHTML = state.guilds.map(g =>
        `<option value="${esc(g.id)}">${esc(g.name)}</option>`
    ).join('');

    // URL 파라미터에 guild_id가 있으면 선택
    const params = new URLSearchParams(location.search);
    const urlGuild = params.get('guild_id');
    if (urlGuild && state.guilds.find(g => g.id === urlGuild)) {
        select.value = urlGuild;
    }
    state.guildId = select.value;

    select.addEventListener('change', () => {
        state.guildId = select.value;
        loadAll();
    });

    // 서버가 1개면 셀렉트 숨기기
    if (state.guilds.length === 1) {
        select.style.display = 'none';
    }
}

function guildParam() {
    return state.guildId ? `guild_id=${encodeURIComponent(state.guildId)}` : '';
}

function loadAll() {
    loadTimetable();
    loadTasks();
    loadExam();
    loadWeekly();
    loadEvents();
}

/* ── Period Emoji ── */
const PERIOD_EMOJI = {
    1: '①', 2: '②', 3: '③', 4: '④',
    5: '⑤', 6: '⑥', 7: '⑦', 8: '⑧',
};

/* ── Timetable ── */
async function loadTimetable() {
    const endpoint = state.showTomorrow ? 'tomorrow' : 'today';
    const btn = document.getElementById('toggle-tomorrow');
    btn.textContent = state.showTomorrow ? '← 오늘' : '내일 →';

    try {
        const r = await fetch(`/api/public/schedule/${endpoint}?${guildParam()}`);
        const data = await r.json();
        if (!data.ok) throw new Error(data.error);

        const titleEl = document.getElementById('timetable-title');
        const dateEl = document.getElementById('timetable-date');
        titleEl.textContent = state.showTomorrow ? '내일 시간표' : '오늘 시간표';
        dateEl.textContent = data.date_label || '';

        const body = document.getElementById('timetable-body');
        if (data.is_weekend) {
            body.innerHTML = '<div class="empty-card">🎉 오늘은 쉬는 날!</div>';
            return;
        }
        if (!data.timetable || !data.timetable.length) {
            body.innerHTML = `<div class="empty-card">${esc(data.message || '시간표 데이터가 없습니다.')}</div>`;
            return;
        }
        const now = new Date();
        const currentPeriod = !state.showTomorrow ? getCurrentPeriod(now) : -1;
        body.innerHTML = '<div class="period-list">' + data.timetable.map(([perio, subject]) => {
            const emoji = PERIOD_EMOJI[perio] || perio;
            const isCurrent = perio === currentPeriod;
            return `<div class="period-item ${isCurrent ? 'current' : ''}">
                <span class="period-num">${emoji}</span>
                <span class="period-subject">${esc(subject)}</span>
                ${isCurrent ? '<span class="period-now">NOW</span>' : ''}
            </div>`;
        }).join('') + '</div>';

        if (data.cached) {
            body.innerHTML += `<div class="cache-note">🕐 저장본 표시 (${esc(data.cached_at || '')})</div>`;
        }
    } catch (err) {
        document.getElementById('timetable-body').innerHTML =
            `<div class="empty-card">⚠️ ${esc(err.message)}</div>`;
    }
}

function getCurrentPeriod(now) {
    const h = now.getHours(), m = now.getMinutes();
    const t = h * 60 + m;
    // GSM 기준 시간표 (대략)
    const periods = [
        [520, 570], [570, 620], [630, 680], [680, 730],
        [790, 840], [840, 890], [900, 950],
    ];
    for (let i = 0; i < periods.length; i++) {
        if (t >= periods[i][0] && t < periods[i][1]) return i + 1;
    }
    return -1;
}

document.getElementById('toggle-tomorrow').addEventListener('click', () => {
    state.showTomorrow = !state.showTomorrow;
    loadTimetable();
});

/* ── Tasks ── */
async function loadTasks() {
    try {
        const r = await fetch(`/api/public/tasks?${guildParam()}`);
        const data = await r.json();
        if (!data.ok) throw new Error(data.error);

        const countEl = document.getElementById('tasks-count');
        countEl.textContent = `${data.total || 0}개 등록`;

        const body = document.getElementById('tasks-body');
        if (!data.tasks || !data.tasks.length) {
            body.innerHTML = '<div class="empty-card">🎉 등록된 일정이 없습니다!</div>';
            return;
        }

        body.innerHTML = data.tasks.map(t => {
            let urgency = 'green';
            let dText = '';
            if (t.days_left === null || t.days_left === undefined) {
                urgency = 'dim';
                dText = '마감 미정';
            } else if (t.days_left <= 0) {
                urgency = 'red';
                dText = t.days_left === 0 ? '오늘 마감' : `D+${-t.days_left}`;
            } else if (t.days_left <= 3) {
                urgency = 'yellow';
                dText = `D-${t.days_left}`;
            } else {
                dText = `D-${t.days_left}`;
            }
            return `<div class="task-item urgency-${urgency}">
                <div class="task-left">
                    <span class="task-type">${esc(t.task_type)}</span>
                    <span class="task-content">${esc(t.content)}</span>
                </div>
                <div class="task-right">
                    <span class="task-deadline">${esc(t.deadline)}</span>
                    <span class="task-dday">${esc(dText)}</span>
                </div>
            </div>`;
        }).join('');
    } catch (err) {
        document.getElementById('tasks-body').innerHTML =
            `<div class="empty-card">⚠️ ${esc(err.message)}</div>`;
    }
}

/* ── Exam ── */
async function loadExam() {
    try {
        const r = await fetch(`/api/public/exam?${guildParam()}`);
        const data = await r.json();
        if (!data.ok) throw new Error(data.error);

        const body = document.getElementById('exam-body');
        if (!data.exams || !data.exams.length) {
            body.innerHTML = '<div class="empty-card">시험 일정이 설정되지 않았습니다.</div>';
            return;
        }

        body.innerHTML = data.exams.map(exam => {
            let statusClass = '';
            let statusText = '';
            if (exam.status === 'upcoming') {
                statusClass = 'exam-upcoming';
                statusText = `D-${exam.days_to_start}`;
            } else if (exam.status === 'ongoing') {
                statusClass = 'exam-ongoing';
                statusText = `${exam.day_number}일차`;
            } else {
                statusClass = 'exam-done';
                statusText = '종료';
            }

            let scopeHtml = '';
            if (exam.scopes && exam.scopes.length) {
                scopeHtml = '<div class="exam-scopes">' +
                    exam.scopes.map(s =>
                        `<div class="scope-item">
                            <span class="scope-subject">${esc(s.subject)}</span>
                            <span class="scope-range">${esc(s.range)}</span>
                        </div>`
                    ).join('') + '</div>';
            }

            return `<div class="exam-block ${statusClass}">
                <div class="exam-header">
                    <span class="exam-name">${esc(exam.name)}</span>
                    <span class="exam-badge ${statusClass}">${esc(statusText)}</span>
                </div>
                <div class="exam-dates">${esc(exam.date_range)}</div>
                ${scopeHtml}
            </div>`;
        }).join('');
    } catch (err) {
        document.getElementById('exam-body').innerHTML =
            `<div class="empty-card">⚠️ ${esc(err.message)}</div>`;
    }
}

/* ── Weekly ── */
async function loadWeekly() {
    try {
        const r = await fetch(`/api/public/weekly?${guildParam()}`);
        const data = await r.json();
        if (!data.ok) throw new Error(data.error);

        document.getElementById('weekly-range').textContent = data.range || '';

        const body = document.getElementById('weekly-body');
        if (!data.upcoming || !data.upcoming.length) {
            let html = '<div class="empty-card">🎉 이번 주 마감 일정 없음!</div>';
            if (data.tbd && data.tbd.length) {
                html += '<div class="weekly-tbd">';
                html += '<div class="weekly-tbd-label">마감 미정</div>';
                data.tbd.forEach(t => {
                    html += `<div class="task-item urgency-dim">
                        <div class="task-left">
                            <span class="task-type">${esc(t.task_type)}</span>
                            <span class="task-content">${esc(t.content)}</span>
                        </div>
                    </div>`;
                });
                html += '</div>';
            }
            body.innerHTML = html;
            return;
        }

        let html = data.upcoming.map(t => {
            let urgency = t.days <= 0 ? 'red' : t.days <= 2 ? 'yellow' : 'green';
            let dText = t.days === 0 ? '오늘' : `D-${t.days}`;
            return `<div class="task-item urgency-${urgency}">
                <div class="task-left">
                    <span class="task-type">${esc(t.task_type)}</span>
                    <span class="task-content">${esc(t.content)}</span>
                </div>
                <div class="task-right">
                    <span class="task-deadline">${esc(t.deadline)}</span>
                    <span class="task-dday">${esc(dText)}</span>
                </div>
            </div>`;
        }).join('');

        if (data.tbd && data.tbd.length) {
            html += '<div class="weekly-tbd">';
            html += '<div class="weekly-tbd-label">마감 미정</div>';
            data.tbd.forEach(t => {
                html += `<div class="task-item urgency-dim">
                    <div class="task-left">
                        <span class="task-type">${esc(t.task_type)}</span>
                        <span class="task-content">${esc(t.content)}</span>
                    </div>
                </div>`;
            });
            html += '</div>';
        }
        body.innerHTML = html;
    } catch (err) {
        document.getElementById('weekly-body').innerHTML =
            `<div class="empty-card">⚠️ ${esc(err.message)}</div>`;
    }
}

/* ── School Events ── */
async function loadEvents() {
    const y = state.eventsYear;
    const m = state.eventsMonth;
    document.getElementById('events-month').textContent = `${y}년 ${m}월`;

    try {
        const r = await fetch(`/api/public/school_events?${guildParam()}&year=${y}&month=${m}`);
        const data = await r.json();
        if (!data.ok) throw new Error(data.error);

        const body = document.getElementById('events-body');
        if (!data.events || !data.events.length) {
            body.innerHTML = '<div class="empty-card">이 달에 등록된 학교 행사가 없습니다.</div>';
            return;
        }

        body.innerHTML = '<div class="events-list">' + data.events.map(ev => {
            return `<div class="event-item">
                <span class="event-date">${esc(ev.date)}</span>
                <span class="event-name">${esc(ev.name)}</span>
            </div>`;
        }).join('') + '</div>';
    } catch (err) {
        document.getElementById('events-body').innerHTML =
            `<div class="empty-card">⚠️ ${esc(err.message)}</div>`;
    }
}

document.getElementById('month-prev').addEventListener('click', () => {
    state.eventsMonth--;
    if (state.eventsMonth < 1) { state.eventsMonth = 12; state.eventsYear--; }
    loadEvents();
});
document.getElementById('month-next').addEventListener('click', () => {
    state.eventsMonth++;
    if (state.eventsMonth > 12) { state.eventsMonth = 1; state.eventsYear++; }
    loadEvents();
});

/* ── Auto Refresh ── */
setInterval(loadAll, 60000); // every 60s
init();
