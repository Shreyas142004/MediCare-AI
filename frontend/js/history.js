/**
 * MediCare AI - Scan History & Archive Controller
 * Search, filter, view details modal, and delete records
 */

document.addEventListener('DOMContentLoaded', () => {
  initHistoryPage();
});

let allScans = [];

async function initHistoryPage() {
  await loadHistory();

  // Search input filter
  const searchInput = document.getElementById('history-search');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      filterAndRenderScans();
    });
  }

  // Confidence filter
  const confFilter = document.getElementById('confidence-filter');
  if (confFilter) {
    confFilter.addEventListener('change', () => {
      filterAndRenderScans();
    });
  }

  // Modal close handler
  const closeBtn = document.getElementById('modal-close-btn');
  const modalBackdrop = document.getElementById('history-modal');
  if (closeBtn && modalBackdrop) {
    closeBtn.addEventListener('click', () => modalBackdrop.classList.remove('active'));
    modalBackdrop.addEventListener('click', (e) => {
      if (e.target === modalBackdrop) modalBackdrop.classList.remove('active');
    });
  }
}

async function loadHistory() {
  const container = document.getElementById('history-table-body');
  try {
    const data = await window.api.getScanHistory(50);
    allScans = data.scans || [];
    filterAndRenderScans();
  } catch (err) {
    showToast('Failed to load scan history: ' + err.message, 'error');
    if (container) {
      container.innerHTML = `<tr><td colspan="6" class="text-center text-muted">Error loading scan history.</td></tr>`;
    }
  }
}

function filterAndRenderScans() {
  const container = document.getElementById('history-table-body');
  const searchInput = document.getElementById('history-search');
  const confFilter = document.getElementById('confidence-filter');
  const countLabel = document.getElementById('scans-count-label');

  if (!container) return;

  const query = searchInput ? searchInput.value.trim().toLowerCase() : '';
  const conf = confFilter ? confFilter.value : 'ALL';

  const filtered = allScans.filter(s => {
    const nameMatch = !query || 
      (s.medicine_name && s.medicine_name.toLowerCase().includes(query)) ||
      (s.matched_name && s.matched_name.toLowerCase().includes(query)) ||
      (s.brand_name && s.brand_name.toLowerCase().includes(query));

    const confMatch = conf === 'ALL' || s.confidence === conf;
    return nameMatch && confMatch;
  });

  if (countLabel) {
    countLabel.textContent = `Showing ${filtered.length} of ${allScans.length} scans`;
  }

  if (filtered.length === 0) {
    container.innerHTML = `
      <tr>
        <td colspan="6" style="text-align:center; padding: 2.5rem; color: var(--text-muted);">
          No matching scans found.
        </td>
      </tr>
    `;
    return;
  }

  container.innerHTML = filtered.map(s => {
    const dateStr = s.timestamp ? new Date(s.timestamp).toLocaleDateString(undefined, {
      month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit'
    }) : 'Recent';

    const confClass = s.confidence === 'HIGH' ? 'badge-success' : s.confidence === 'MEDIUM' ? 'badge-warning' : 'badge-neutral';
    const displayMed = s.matched_name || s.medicine_name || s.brand_name || 'Unlabeled Scan';

    return `
      <tr>
        <td><strong>${escapeHtml(displayMed)}</strong></td>
        <td>${escapeHtml(s.strength || 'N/A')}</td>
        <td><span class="badge ${confClass}">${escapeHtml(s.confidence || 'NORMAL')}</span></td>
        <td><span class="badge badge-info">${escapeHtml(s.model_used || 'Gemini')}</span></td>
        <td style="color:var(--text-muted); font-size:0.85rem;">${dateStr}</td>
        <td>
          <div style="display:flex; gap:0.5rem;">
            <button class="btn btn-outline btn-sm" onclick="viewScanDetails('${s.id}')">View</button>
            <button class="btn btn-outline btn-sm" style="color:var(--danger); border-color:#fecaca;" onclick="deleteScan('${s.id}')">Delete</button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

window.viewScanDetails = function(scanId) {
  const scan = allScans.find(s => s.id === scanId);
  if (!scan) return;

  const modal = document.getElementById('history-modal');
  const modalBody = document.getElementById('modal-details-body');
  if (!modal || !modalBody) return;

  modalBody.innerHTML = `
    <h3 style="margin-bottom:0.5rem; color:var(--primary);">${escapeHtml(scan.matched_name || scan.medicine_name || 'Medicine Details')}</h3>
    <p class="text-muted" style="margin-bottom:1.5rem;">Scanned on ${scan.timestamp ? new Date(scan.timestamp).toLocaleString() : 'N/A'}</p>
    
    <div style="background:#f8fafc; border:1px solid var(--border-light); border-radius:var(--radius-md); padding:1rem; margin-bottom:1.25rem;">
      <div class="field-pair"><span class="field-label">Detected Packaging:</span> <span class="field-value">${escapeHtml(scan.medicine_name || 'N/A')}</span></div>
      <div class="field-pair"><span class="field-label">Matched Database:</span> <span class="field-value highlight text-secondary">${escapeHtml(scan.matched_name || 'No catalog match')}</span></div>
      <div class="field-pair"><span class="field-label">Dosage Form:</span> <span class="field-value">${escapeHtml(scan.dosage_form || 'N/A')}</span></div>
      <div class="field-pair"><span class="field-label">Strength:</span> <span class="field-value">${escapeHtml(scan.strength || 'N/A')}</span></div>
      <div class="field-pair"><span class="field-label">Match Score:</span> <span class="field-value">${Math.round(scan.match_score || 0)}%</span></div>
      <div class="field-pair"><span class="field-label">Recognition Model:</span> <span class="field-value">${escapeHtml(scan.model_used || 'Gemini Vision')}</span></div>
      <div class="field-pair"><span class="field-label">Processing Time:</span> <span class="field-value">${Math.round(scan.processing_time_ms || 0)} ms</span></div>
    </div>
  `;

  modal.classList.add('active');
};

window.deleteScan = async function(scanId) {
  if (!confirm('Are you sure you want to delete this scan from history?')) return;
  try {
    await window.api.deleteScanRecord(scanId);
    showToast('Scan deleted successfully.', 'success');
    allScans = allScans.filter(s => s.id !== scanId);
    filterAndRenderScans();
  } catch (err) {
    showToast('Failed to delete scan: ' + err.message, 'error');
  }
};

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

