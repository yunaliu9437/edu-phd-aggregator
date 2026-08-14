let jobs = [];

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function render(jobsToRender) {
  const list = document.getElementById('job-list');
  list.innerHTML = '';

  if (!jobsToRender.length) {
    list.innerHTML = '<p class="empty">暂无匹配职位</p>';
    return;
  }

  jobsToRender.forEach(job => {
    const card = document.createElement('article');
    card.className = 'job-card';

    const title = escapeHtml(job.title || '无标题');
    const url = escapeHtml(job.url || '#');
    const source = escapeHtml(job.source || '未知');
    const posted = escapeHtml(job.posted || '未知');
    const deadline = escapeHtml(job.deadline || '请查看原文');

    card.innerHTML = `
      <h2><a href="${url}" target="_blank" rel="noopener noreferrer">${title}</a></h2>
      <p class="meta">
        <span>来源：${source}</span>
        <span>发布时间：${posted}</span>
        <span>截止时间：${deadline}</span>
      </p>
    `;
    list.appendChild(card);
  });
}

function updateSourceFilter() {
  const select = document.getElementById('source-filter');
  const current = select.value;
  const sources = [...new Set(jobs.map(j => j.source).filter(Boolean))];

  select.innerHTML = '<option value="">全部来源</option>' +
    sources.map(s => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join('');
  select.value = current;
}

function applyFilters() {
  const query = document.getElementById('search').value.toLowerCase();
  const source = document.getElementById('source-filter').value;

  const filtered = jobs.filter(job => {
    const text = `${job.title} ${job.source}`.toLowerCase();
    const matchQuery = !query || text.includes(query);
    const matchSource = !source || job.source === source;
    return matchQuery && matchSource;
  });

  render(filtered);
}

fetch('data/jobs.json')
  .then(res => {
    if (!res.ok) throw new Error('无法加载数据');
    return res.json();
  })
  .then(data => {
    jobs = Array.isArray(data) ? data : [];
    updateSourceFilter();
    render(jobs);

    const times = jobs.map(j => j.scraped_at).filter(Boolean).sort();
    if (times.length) {
      document.getElementById('updated-at').textContent = times[times.length - 1];
    } else {
      document.getElementById('updated-at').textContent = '暂无数据';
    }
  })
  .catch(err => {
    document.getElementById('job-list').innerHTML =
      '<p class="empty">数据加载失败，请确认 data/jobs.json 是否存在。</p>';
    console.error(err);
  });

document.getElementById('search').addEventListener('input', applyFilters);
document.getElementById('source-filter').addEventListener('change', applyFilters);
