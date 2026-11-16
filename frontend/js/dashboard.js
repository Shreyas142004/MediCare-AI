/**
 * MediCare AI - User Dashboard Controller
 * Displays account overview, scanner metrics, and recent scans table
 */

document.addEventListener('DOMContentLoaded', () => {
  initDashboard();
});

async function initDashboard() {
  const welcomeName = document.getElementById('user-welcome-name');
  const user = window.api ? window.api.getUser() : null;

  if (welcomeName && user) {
    welcomeName.textContent = user.full_name || 'Member';
  }

  await loadDashboardMetricsAndHistory();
}

async function loadDashboardMetricsAndHistory() {
  const tableBody = document.getElementById('recent-scans-body');
  const totalScansElem = document.getElementById('metric-total-scans');
  const highConfElem = document.getElementById('metric-high-conf');
  const matchRateElem = document.getElementById('metric-match-rate');

  try {
    const data = await window.api.getScanHistory(10);
    const scans = data.scans || [];

    // Calculate metrics
    const total = scans.length;
    const highConf = scans.filter(s => s.confidence === 'HIGH' || (s.match_score && s.match_score >= 80)).length;
    const rate = total > 0 ? Math.round((highConf / total) * 100) : 100;

    if (totalScansElem) totalScansElem.textContent = total;
    if (highConfElem) highConfElem.textContent = highConf;
    if (matchRateElem) matchRateElem.textContent = `${rate}%`;

    // Render Table
    if (tableBody) {
      if (scans.length === 0) {
        tableBody.innerHTML = `
          <tr>
            <td colspan="5" style="text-align:center; padding: 2.5rem; color: var(--text-muted);">
              <div style="font-size: 2rem; margin-bottom: 0.5rem;">📷</div>
              <p>No scans recorded yet. Upload a medicine package image to see analysis history.</p>
              <a href="scanner.html" class="btn btn-primary btn-sm" style="margin-top:0.5rem;">Scan Medicine Now</a>
            </td>
          </tr>
        `;
        return;
      }

      tableBody.innerHTML = scans.map(s => {
        const dateStr = s.timestamp ? new Date(s.timestamp).toLocaleDateString(undefined, {
          month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit'
        }) : 'Recent';

        const confClass = s.confidence === 'HIGH' ? 'badge-success' : s.confidence === 'MEDIUM' ? 'badge-warning' : 'badge-neutral';
        const displayMed = s.matched_name || s.medicine_name || s.brand_name || 'Unlabeled Scan';

        return `
          <tr>
            <td>
              <strong>${escapeHtml(displayMed)}</strong>
              ${s.strength ? `<span class="badge badge-neutral" style="margin-left:6px;">${escapeHtml(s.strength)}</span>` : ''}
            </td>
            <td><span class="badge ${confClass}">${escapeHtml(s.confidence || 'NORMAL')}</span></td>
            <td><span class="badge badge-info">${escapeHtml(s.model_used || 'Gemini Vision')}</span></td>
            <td><span style="color:var(--text-muted); font-size:0.85rem;">${dateStr}</span></td>
            <td>
              <a href="history.html" class="btn btn-outline btn-sm">Inspect</a>
            </td>
          </tr>
        `;
      }).join('');
    }

  } catch (err) {
    console.warn('Could not load dashboard data:', err);
    if (tableBody) {
      tableBody.innerHTML = `<tr><td colspan="5" class="text-muted text-center">Unable to load scan activity at this moment.</td></tr>`;
    }
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

