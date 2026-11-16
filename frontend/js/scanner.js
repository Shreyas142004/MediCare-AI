/**
 * MediCare AI - Interactive Scanner & Multimodal Recognition Controller
 * Handles Drag & Drop, File Upload, Live Webcam Capture,
 * 5-Stage Progress Animation, and High-Fidelity Results Rendering.
 */

document.addEventListener('DOMContentLoaded', () => {
  initScanner();
});

let currentImageFile = null;
let webcamStream = null;
let latestScanResult = null;

function initScanner() {
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('file-input');
  const browseBtn = document.getElementById('browse-btn');
  const cameraBtn = document.getElementById('camera-btn');
  const startScanBtn = document.getElementById('start-scan-btn');
  const removeImgBtn = document.getElementById('remove-img-btn');

  if (!dropzone) return;

  // Browse file click
  if (browseBtn && fileInput) {
    browseBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      fileInput.click();
    });
    dropzone.addEventListener('click', () => fileInput.click());
  }

  // File input change
  if (fileInput) {
    fileInput.addEventListener('change', (e) => {
      if (e.target.files && e.target.files[0]) {
        handleSelectedFile(e.target.files[0]);
      }
    });
  }

  // Drag & drop handlers
  ['dragenter', 'dragover'].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.add('dragover');
    }, false);
  });

  ['dragleave', 'drop'].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.remove('dragover');
    }, false);
  });

  dropzone.addEventListener('drop', (e) => {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files && files[0]) {
      handleSelectedFile(files[0]);
    }
  });

  // Remove previewed image
  if (removeImgBtn) {
    removeImgBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      resetScanner();
    });
  }

  // Camera toggle button
  if (cameraBtn) {
    cameraBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      openWebcamModal();
    });
  }

  // Start Scan Click
  if (startScanBtn) {
    startScanBtn.addEventListener('click', () => {
      if (!currentImageFile) {
        showToast('Please upload or capture a medicine strip image first.', 'warning');
        return;
      }
      runMedicineScanPipeline(currentImageFile);
    });
  }

  // Reset / Scan another
  const scanAnotherBtn = document.getElementById('scan-another-btn');
  if (scanAnotherBtn) {
    scanAnotherBtn.addEventListener('click', resetScanner);
  }

  // Print summary button
  const printSummaryBtn = document.getElementById('print-summary-btn');
  if (printSummaryBtn) {
    printSummaryBtn.addEventListener('click', () => {
      if (latestScanResult) {
        generatePrintableSummary(latestScanResult);
      }
      window.print();
    });
  }
}

/**
 * Handles a newly selected image file
 */
function handleSelectedFile(file) {
  if (!file.type.match(/^image\/(jpeg|jpg|png|webp)$/)) {
    showToast('Invalid file format. Please upload a JPG, PNG, or WebP image.', 'error');
    return;
  }

  if (file.size > 12 * 1024 * 1024) {
    showToast('Image size exceeds 12MB. Please select a smaller photo.', 'error');
    return;
  }

  currentImageFile = file;

  const reader = new FileReader();
  reader.onload = (e) => {
    const previewImg = document.getElementById('preview-img');
    const previewBox = document.getElementById('image-preview-box');
    const dropPrompt = document.getElementById('drop-prompt');
    const startScanBtn = document.getElementById('start-scan-btn');

    if (previewImg && previewBox) {
      previewImg.src = e.target.result;
      previewBox.style.display = 'block';
    }
    if (dropPrompt) dropPrompt.style.display = 'none';
    if (startScanBtn) startScanBtn.disabled = false;

    // Hide old results if present
    const resultsContainer = document.getElementById('results-container');
    if (resultsContainer) resultsContainer.classList.remove('visible');
  };
  reader.readAsDataURL(file);
}

/**
 * Resets the scanner UI back to initial state
 */
function resetScanner() {
  currentImageFile = null;
  const fileInput = document.getElementById('file-input');
  if (fileInput) fileInput.value = '';

  const previewBox = document.getElementById('image-preview-box');
  const dropPrompt = document.getElementById('drop-prompt');
  const startScanBtn = document.getElementById('start-scan-btn');
  const resultsContainer = document.getElementById('results-container');
  const progressCard = document.getElementById('scan-progress-card');

  if (previewBox) previewBox.style.display = 'none';
  if (dropPrompt) dropPrompt.style.display = 'block';
  if (startScanBtn) startScanBtn.disabled = true;
  if (resultsContainer) resultsContainer.classList.remove('visible');
  if (progressCard) progressCard.classList.remove('active');

  stopWebcam();
}

/**
 * Webcam Capture Handling
 */
async function openWebcamModal() {
  const modal = document.getElementById('webcam-modal');
  const video = document.getElementById('webcam-video');
  if (!modal || !video) return;

  try {
    webcamStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } }
    });
    video.srcObject = webcamStream;
    modal.classList.add('active');
  } catch (err) {
    showToast('Could not access camera: ' + (err.message || 'Permission denied'), 'error');
  }

  // Capture photo
  const captureBtn = document.getElementById('webcam-capture-btn');
  if (captureBtn) {
    captureBtn.onclick = () => {
      const canvas = document.createElement('canvas');
      canvas.width = video.videoWidth || 640;
      canvas.height = video.videoHeight || 480;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

      canvas.toBlob((blob) => {
        if (blob) {
          const file = new File([blob], 'medicine_camera_capture.jpg', { type: 'image/jpeg' });
          handleSelectedFile(file);
          closeWebcamModal();
        }
      }, 'image/jpeg', 0.92);
    };
  }

  // Close modal
  const closeBtn = document.getElementById('webcam-close-btn');
  if (closeBtn) {
    closeBtn.onclick = closeWebcamModal;
  }
}

function closeWebcamModal() {
  const modal = document.getElementById('webcam-modal');
  if (modal) modal.classList.remove('active');
  stopWebcam();
}

function stopWebcam() {
  if (webcamStream) {
    webcamStream.getTracks().forEach(track => track.stop());
    webcamStream = null;
  }
}

/**
 * Runs the 5-Stage Scan Progress and sends image to backend
 */
async function runMedicineScanPipeline(file) {
  const progressCard = document.getElementById('scan-progress-card');
  const progressBar = document.getElementById('progress-bar-fill');
  const scanBtn = document.getElementById('start-scan-btn');
  const resultsContainer = document.getElementById('results-container');

  if (progressCard) progressCard.classList.add('active');
  if (resultsContainer) resultsContainer.classList.remove('visible');
  if (scanBtn) scanBtn.disabled = true;

  // Stages elements
  const stages = [
    document.getElementById('stage-1'),
    document.getElementById('stage-2'),
    document.getElementById('stage-3'),
    document.getElementById('stage-4'),
    document.getElementById('stage-5')
  ];

  function setStage(index, status, percent) {
    if (progressBar) progressBar.style.width = `${percent}%`;
    stages.forEach((st, i) => {
      if (!st) return;
      if (i < index) {
        st.className = 'stage-item completed';
        const icon = st.querySelector('.stage-icon');
        if (icon) icon.textContent = '✓';
      } else if (i === index) {
        st.className = `stage-item ${status}`;
        const icon = st.querySelector('.stage-icon');
        if (icon) icon.textContent = status === 'completed' ? '✓' : (i + 1);
      } else {
        st.className = 'stage-item';
        const icon = st.querySelector('.stage-icon');
        if (icon) icon.textContent = (i + 1);
      }
    });
  }

  try {
    // Stage 1: Upload & Preprocessing
    setStage(0, 'in-progress', 20);
    await new Promise(r => setTimeout(r, 400));
    setStage(0, 'completed', 25);

    // Stage 2: Multimodal Gemini Vision
    setStage(1, 'in-progress', 45);

    // Make backend call (runs Gemini multimodal analysis & matcher)
    const scanPromise = window.api.scanMedicinePackage(file);
    
    // Simulate progression while server computes
    setTimeout(() => { if (progressBar) setStage(2, 'in-progress', 65); }, 800);
    setTimeout(() => { if (progressBar) setStage(3, 'in-progress', 85); }, 1400);

    const response = await scanPromise;

    // Stage 4 & 5 Complete
    setStage(3, 'completed', 90);
    setStage(4, 'completed', 100);

    await new Promise(r => setTimeout(r, 400));
    if (progressCard) progressCard.classList.remove('active');

    // Render Results
    renderScanResults(response);
    showToast('Medicine analysis completed successfully!', 'success');

  } catch (err) {
    if (progressCard) progressCard.classList.remove('active');
    showToast(err.message || 'Medicine recognition failed. Please try a clearer picture.', 'error');
  } finally {
    if (scanBtn) scanBtn.disabled = false;
  }
}

/**
 * Renders the full structured response
 */
function renderScanResults(data) {
  const container = document.getElementById('results-container');
  if (!container) return;

  const rec = data.recognition || {};
  const pkg = data.extracted_package_details || {};
  const match = data.dataset_match || {};
  const info = data.medicine_information || {};
  const warnings = data.warnings_and_uncertain_fields || [];

  // 1. Status Banner
  const statusBanner = document.getElementById('result-status-banner');
  if (statusBanner) {
    let iconClass = 'status-icon-success';
    let iconSymbol = '✓';
    let titleText = 'Medicine Recognized & Verified';
    let statusBadgeClass = 'badge-success';

    if (rec.status === 'NOT_A_MEDICINE' || rec.status === 'UNREADABLE') {
      iconClass = 'status-icon-danger';
      iconSymbol = '✕';
      titleText = rec.status === 'NOT_A_MEDICINE' ? 'Non-Pharmaceutical Image' : 'Unreadable Packaging';
      statusBadgeClass = 'badge-danger';
    } else if (match.match_status !== 'MATCHED') {
      iconClass = 'status-icon-warning';
      iconSymbol = '⚠';
      titleText = 'Extracted Packaging (Uncertain / Uncataloged)';
      statusBadgeClass = 'badge-warning';
    }

    statusBanner.innerHTML = `
      <div class="result-status-main">
        <div class="result-status-icon ${iconClass}">${iconSymbol}</div>
        <div>
          <h3>${titleText}</h3>
          <p class="text-muted" style="margin:0;">
            ${data.message || 'Analyzed via Multimodal Vision Engine'}
          </p>
        </div>
      </div>
      <div style="display:flex; gap:0.5rem; align-items:center; flex-wrap:wrap;">
        <span class="badge ${statusBadgeClass}">${match.match_status || rec.status}</span>
        <span class="badge badge-info">${rec.model_used || 'Gemini Vision'}</span>
        <span class="badge badge-neutral">⚡ ${rec.processing_time_ms || 0} ms</span>
      </div>
    `;
  }

  // 2. Extracted Packaging Card (Column A)
  const pkgCol = document.getElementById('extracted-package-fields');
  if (pkgCol) {
    pkgCol.innerHTML = `
      <div class="field-pair">
        <span class="field-label">Printed Name</span>
        <span class="field-value highlight">${escapeHtml(pkg.medicine_name || pkg.brand_name || 'Not detected')}</span>
      </div>
      <div class="field-pair">
        <span class="field-label">Brand</span>
        <span class="field-value">${escapeHtml(pkg.brand_name || 'N/A')}</span>
      </div>
      <div class="field-pair">
        <span class="field-label">Active Ingredient</span>
        <span class="field-value">${escapeHtml(pkg.active_ingredient || 'N/A')}</span>
      </div>
      <div class="field-pair">
        <span class="field-label">Strength</span>
        <span class="field-value">${escapeHtml(pkg.strength || 'N/A')}</span>
      </div>
      <div class="field-pair">
        <span class="field-label">Dosage Form</span>
        <span class="field-value">${escapeHtml(pkg.dosage_form || 'N/A')}</span>
      </div>
      <div class="field-pair">
        <span class="field-label">Manufacturer (Printed)</span>
        <span class="field-value">${escapeHtml(pkg.manufacturer || 'N/A')}</span>
      </div>
      <div class="field-pair">
        <span class="field-label">Batch / Lot Number</span>
        <span class="field-value">${escapeHtml(pkg.batch_number || 'Uncertain / Not visible')}</span>
      </div>
      <div class="field-pair">
        <span class="field-label">Mfg Date (MFG)</span>
        <span class="field-value">${escapeHtml(pkg.manufacturing_date || 'N/A')}</span>
      </div>
      <div class="field-pair">
        <span class="field-label">Expiry Date (EXP)</span>
        <span class="field-value ${pkg.expiry_date ? 'text-danger font-semibold' : ''}">${escapeHtml(pkg.expiry_date || 'N/A')}</span>
      </div>
    `;
  }

  // 3. Dataset Match Card (Column B)
  const matchCol = document.getElementById('dataset-match-fields');
  const matchedMed = match.matched_medicine;
  if (matchCol) {
    if (matchedMed) {
      matchCol.innerHTML = `
        <div class="field-pair">
          <span class="field-label">Matched Database Entry</span>
          <span class="field-value highlight text-secondary">${escapeHtml(matchedMed.name)}</span>
        </div>
        <div class="field-pair">
          <span class="field-label">Match Confidence</span>
          <span class="field-value"><span class="badge ${match.match_score >= 80 ? 'badge-success' : 'badge-warning'}">${Math.round(match.match_score)}% Match</span></span>
        </div>
        <div class="field-pair">
          <span class="field-label">Database Composition</span>
          <span class="field-value">${escapeHtml(matchedMed.composition || 'Standard')}</span>
        </div>
        <div class="field-pair">
          <span class="field-label">Database Manufacturer</span>
          <span class="field-value">${escapeHtml(matchedMed.manufacturer || 'Information not available')}</span>
        </div>
        <div class="field-pair">
          <span class="field-label">Approximate Price</span>
          <span class="field-value">${escapeHtml(matchedMed.price || 'Not listed')}</span>
        </div>
        <div class="field-pair">
          <span class="field-label">Primary Salt Class</span>
          <span class="field-value">${escapeHtml(matchedMed.salt_composition || matchedMed.composition || 'Therapeutic salt')}</span>
        </div>
      `;
    } else {
      matchCol.innerHTML = `
        <div style="padding: 2rem 1rem; text-align: center; color: var(--text-muted);">
          <div style="font-size: 2rem; margin-bottom: 0.5rem;">📁</div>
          <p>No exact catalog match found in our 149,000+ medicine database for this specific packaging string.</p>
          <span class="badge badge-neutral">Match Score: ${Math.round(match.match_score || 0)}%</span>
        </div>
      `;
    }
  }

  // 4. Warnings and Uncertainties
  const warningsWrap = document.getElementById('warnings-wrapper');
  if (warningsWrap) {
    if (warnings && warnings.length > 0) {
      warningsWrap.innerHTML = `
        <div class="warning-banner">
          <h4>⚠️ Packaging Notices & Uncertain Readings</h4>
          <ul style="margin:0.5rem 0 0 1.25rem;">
            ${warnings.map(w => `<li>${escapeHtml(w)}</li>`).join('')}
          </ul>
        </div>
      `;
      warningsWrap.style.display = 'block';
    } else {
      warningsWrap.style.display = 'none';
    }
  }

  // 5. Patient Explanation Layout
  const expSection = document.getElementById('patient-explanation-body');
  if (expSection) {
    const uses = info.primary_uses || [];
    const sideEffects = info.common_side_effects || [];
    const alerts = info.critical_safety_alerts || {};

    let alertsHtml = '';
    if (alerts && Object.keys(alerts).length > 0) {
      alertsHtml = `
        <div class="explanation-section" style="background:#fff1f2; border:1px solid #fecdd3; border-radius: var(--radius-md); padding:1.25rem;">
          <h4 style="color:#be123c;">🚨 Critical Safety Alerts & Precautions</h4>
          <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:1rem; margin-top:0.75rem;">
            ${Object.entries(alerts).map(([key, val]) => `
              <div style="font-size:0.88rem;">
                <strong style="text-transform:capitalize; color:#9f1239;">${escapeHtml(key)}:</strong> 
                <span>${escapeHtml(val)}</span>
              </div>
            `).join('')}
          </div>
        </div>
      `;
    }

    expSection.innerHTML = `
      <div class="explanation-section">
        <h4>💊 What is this medicine?</h4>
        <p>${escapeHtml(info.medicine_name || pkg.medicine_name || 'Standard Pharmaceutical Product')} is composed of <strong>${escapeHtml(info.active_ingredients || pkg.composition || 'active salts')}</strong> (${escapeHtml(info.dosage_and_form || pkg.dosage_form || 'Form')}).</p>
      </div>

      <div class="explanation-section">
        <h4>🎯 Commonly Used For</h4>
        ${uses.length > 0 ? `
          <ul>
            ${uses.map(u => `<li>${escapeHtml(u)}</li>`).join('')}
          </ul>
        ` : `<p class="text-muted">Information not available in local catalog.</p>`}
      </div>

      <div class="explanation-section">
        <h4>🔬 How it Generally Works</h4>
        <p>${escapeHtml(info.how_it_works || 'Mechanism details not available.')}</p>
      </div>

      <div class="explanation-section">
        <h4>📋 How to Take Safely</h4>
        <p>${escapeHtml(info.how_to_take || 'Take strictly as instructed by your prescribing doctor or printed on packaging.')}</p>
      </div>

      <div class="explanation-section">
        <h4>⚠️ Common Side Effects</h4>
        ${sideEffects.length > 0 ? `
          <ul>
            ${sideEffects.map(s => `<li>${escapeHtml(s)}</li>`).join('')}
          </ul>
        ` : `<p class="text-muted">No specific side effects noted in catalog entry.</p>`}
      </div>

      ${alertsHtml}
    `;
  }

  // 6. Alternative Matches
  const altSection = document.getElementById('alternative-matches-container');
  const alts = match.alternative_matches || [];
  if (altSection) {
    if (alts.length > 0) {
      altSection.innerHTML = `
        <h4 style="margin-bottom:0.75rem;">Alternative Database Candidates</h4>
        <div style="display:flex; gap:0.75rem; flex-wrap:wrap;">
          ${alts.map(a => `
            <div style="background:#f8fafc; border:1px solid var(--border-light); border-radius:var(--radius-md); padding:0.6rem 1rem; font-size:0.85rem;">
              <strong>${escapeHtml(a.name)}</strong>
              <div style="color:var(--text-muted); font-size:0.78rem;">${escapeHtml(a.composition || '')}</div>
            </div>
          `).join('')}
        </div>
      `;
      altSection.style.display = 'block';
    } else {
      altSection.style.display = 'none';
    }
  }

  // Reveal results container
  container.classList.add('visible');
  container.scrollIntoView({ behavior: 'smooth' });

  // Pre-generate structured printable summary
  latestScanResult = data;
  generatePrintableSummary(data);
}

/**
 * Builds a structured, publication-grade clinical summary report for PDF and Printing
 */
function generatePrintableSummary(data) {
  const sheet = document.getElementById('printable-summary-sheet');
  if (!sheet || !data) return;

  const rec = data.recognition || {};
  const pkg = data.extracted_package_details || {};
  const match = data.dataset_match || {};
  const med = match.matched_medicine || {};
  const info = data.medicine_information || {};
  const warnings = data.warnings_and_uncertain_fields || [];

  const now = new Date();
  const dateStr = now.toLocaleDateString('en-US', { day: '2-digit', month: 'short', year: 'numeric' });
  const timeStr = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  const reportId = 'MCA-' + Math.floor(100000 + Math.random() * 900000);

  const medName = info.medicine_name || med.name || pkg.medicine_name || pkg.brand_name || 'Unspecified Medicine';
  const composition = info.active_ingredients || med.composition || pkg.composition || pkg.active_ingredient || 'Not specified';
  const formStrength = info.dosage_and_form || `${pkg.dosage_form || med.dosage_form || 'Form'} (${pkg.strength || med.strength || 'Standard'})`;
  const manufacturer = pkg.manufacturer || med.manufacturer || 'Information not specified';
  const matchScore = Math.round(match.match_score || 0);

  const uses = info.primary_uses || [];
  const sideEffects = info.common_side_effects || [];
  const alerts = info.critical_safety_alerts || {};

  sheet.innerHTML = `
    <div class="print-report-container">
      <!-- Report Header -->
      <div class="print-report-header">
        <div>
          <div style="display:flex; align-items:center; gap:6pt; margin-bottom:3pt;">
            <span style="font-size:16pt; color:#0284c7; font-weight:bold;">✚</span>
            <span style="font-size:14pt; font-weight:800; color:#0f172a; letter-spacing:-0.5px;">MediCare<span style="color:#0284c7;">AI</span></span>
          </div>
          <div class="print-report-title">Clinical Medicine Verification &amp; Patient Summary Report</div>
          <div class="print-report-subtitle">Validated through Multimodal Packaging OCR, NLP Entity Extraction &amp; 149k+ Medicine Database</div>
        </div>
        <div class="print-meta-box">
          <div><strong>Report ID:</strong> ${reportId}</div>
          <div><strong>Date:</strong> ${dateStr}, ${timeStr}</div>
          <div><strong>Engine:</strong> ${escapeHtml(rec.model_used || 'OCR.space / Gemini Vision')}</div>
          <div class="print-meta-badge">${match.match_status === 'MATCHED' ? `✓ VERIFIED MATCH (${matchScore}%)` : `⚠ UNCATALOGED PACKAGING (${matchScore}%)`}</div>
        </div>
      </div>

      <!-- Medicine Primary Identity Block -->
      <div class="print-med-identity">
        <div class="print-med-name">${escapeHtml(medName)}</div>
        <div class="print-med-salts"><strong>Active Composition:</strong> ${escapeHtml(composition)}</div>
        <div class="print-med-details-row">
          <div><strong>Formulation:</strong> ${escapeHtml(formStrength)}</div>
          <div><strong>Manufacturer:</strong> ${escapeHtml(manufacturer)}</div>
          <div><strong>Approx. Price:</strong> ${escapeHtml(med.price || 'N/A')}</div>
          <div><strong>Habit Forming:</strong> ${escapeHtml(med.habit_forming || 'No')}</div>
        </div>
      </div>

      <!-- Packaging vs Verified Catalog Cross-Comparison Table -->
      <div class="print-section-heading">1. Packaging Reading vs. Clinical Catalog Cross-Verification</div>
      <table class="print-table">
        <thead>
          <tr>
            <th style="width:28%;">Pharmaceutical Field</th>
            <th style="width:36%;">Physical Packaging (Scanned Strip)</th>
            <th style="width:36%;">Verified Database Catalog</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><strong>Brand / Trade Name</strong></td>
            <td>${escapeHtml(pkg.brand_name || pkg.medicine_name || 'Not detected')}</td>
            <td>${escapeHtml(med.brand_name || med.name || 'Not cataloged')}</td>
          </tr>
          <tr>
            <td><strong>Active Composition / Salts</strong></td>
            <td>${escapeHtml(pkg.active_ingredient || pkg.composition || 'Not detected')}</td>
            <td>${escapeHtml(med.composition || 'Standard clinical formula')}</td>
          </tr>
          <tr>
            <td><strong>Dosage Form &amp; Strength</strong></td>
            <td>${escapeHtml(`${pkg.dosage_form || 'Form N/A'} (${pkg.strength || 'Strength N/A'})`)}</td>
            <td>${escapeHtml(`${med.dosage_form || 'Catalog Form'} (${med.strength || 'Catalog Strength'})`)}</td>
          </tr>
          <tr>
            <td><strong>Batch / Lot Number</strong></td>
            <td><strong>${escapeHtml(pkg.batch_number || 'Uncertain / Not visible on image')}</strong></td>
            <td><em>Physical packaging property only</em></td>
          </tr>
          <tr>
            <td><strong>Expiry Date (EXP)</strong></td>
            <td><strong style="color:#b91c1c;">${escapeHtml(pkg.expiry_date || 'Uncertain / Not visible on image')}</strong></td>
            <td><em>Physical packaging property only</em></td>
          </tr>
          <tr>
            <td><strong>Manufacturing Date (MFG)</strong></td>
            <td>${escapeHtml(pkg.manufacturing_date || 'Not visible on image')}</td>
            <td><em>Physical packaging property only</em></td>
          </tr>
          <tr>
            <td><strong>Manufacturer / Marketer</strong></td>
            <td>${escapeHtml(pkg.manufacturer || 'Printed on packaging')}</td>
            <td>${escapeHtml(med.manufacturer || 'Information not specified')}</td>
          </tr>
        </tbody>
      </table>

      <!-- Clinical & Patient Care Guidance -->
      <div class="print-section-heading">2. Patient Administration &amp; Clinical Guidance</div>
      <div class="print-guidance-grid">
        <div class="print-guidance-box">
          <h5>🎯 Primary Indications &amp; Uses</h5>
          ${uses.length > 0 ? `
            <ul>${uses.map(u => `<li>${escapeHtml(u)}</li>`).join('')}</ul>
          ` : `<p style="margin:0; color:#64748b;">Consult physician for clinical indications.</p>`}
        </div>
        <div class="print-guidance-box">
          <h5>🔬 How it Works in the Body</h5>
          <p style="margin:0;">${escapeHtml(info.how_it_works || med.how_works || 'Clinical pharmacology details not available.')}</p>
        </div>
        <div class="print-guidance-box">
          <h5>📋 Directions for Safe Use</h5>
          <p style="margin:0;">${escapeHtml(info.how_to_take || med.how_to_use || 'Take strictly in dose and duration advised by your doctor.')}</p>
        </div>
        <div class="print-guidance-box">
          <h5>⚠️ Common Side Effects</h5>
          ${sideEffects.length > 0 ? `
            <ul>${sideEffects.map(s => `<li>${escapeHtml(s)}</li>`).join('')}</ul>
          ` : `<p style="margin:0; color:#64748b;">No adverse reactions specifically reported in catalog.</p>`}
        </div>
      </div>

      <!-- Critical Precautions / Safety Alerts if present -->
      ${alerts && Object.keys(alerts).length > 0 ? `
        <div class="print-safety-box">
          <strong style="color:#c2410c;">🚨 Critical Precautions &amp; Organ Alerts:</strong>
          <div style="display:grid; grid-template-columns:1fr 1fr; gap:6pt; margin-top:4pt;">
            ${Object.entries(alerts).map(([k, v]) => `
              <div><strong style="text-transform:capitalize;">${escapeHtml(k)}:</strong> ${escapeHtml(v)}</div>
            `).join('')}
          </div>
        </div>
      ` : ''}

      <!-- Packaging Notices & Uncertainties if present -->
      ${warnings.length > 0 ? `
        <div style="background:#fef2f2; border:0.5pt solid #fecaca; border-radius:3pt; padding:5pt 8pt; margin-bottom:8pt; font-size:8pt; color:#991b1b;">
          <strong>⚠️ Packaging Observation Notes:</strong>
          <ul style="margin:2pt 0 0 12pt; padding:0;">
            ${warnings.map(w => `<li>${escapeHtml(w)}</li>`).join('')}
          </ul>
        </div>
      ` : ''}

      <!-- Disclaimer & Sign-off Footer -->
      <div class="print-footer">
        <div>
          <strong>IMPORTANT MEDICAL DISCLAIMER:</strong> This report is produced by the MediCare AI computational verification platform for patient guidance, dosage form confirmation, and medication verification. It does not replace independent clinical evaluation or constitute a medical prescription. Never initiate, change, or cease prescription medication without consulting a registered medical doctor or certified pharmacist.
        </div>
        <div class="print-sign-row">
          <div class="print-sign-col">
            Patient / Caregiver Acknowledgement
          </div>
          <div class="print-sign-col">
            Verified by Pharmacist / Healthcare Professional
          </div>
        </div>
      </div>
    </div>
  `;
}

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

