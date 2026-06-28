/* ═══════════════════════════════════════════════════
   image-tool.js — 旗舰級圖片去水印
   功能：
   ✓ 多區域連續框選（N 個水印區域）
   ✓ 自動檢測水印（AI corner detection）
   ✓ Side-by-side 滑塊前後對比
   ✓ 免費版升級轉化（彈窗 + 退出意圖）
   ✓ 階段式處理進度
   ✓ 區域管理面板（編輯/刪除/全清）
   ✓ 手機友好拖拽
   ═══════════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', () => {
    const uploadZone = document.getElementById('uploadZone');
    const fileInput = document.getElementById('fileInput');
    const toolWorkspace = document.getElementById('toolWorkspace');
    const imagePreview = document.getElementById('imagePreview');
    const canvas = document.getElementById('imageCanvas');
    const ctx = canvas.getContext('2d');
    const resultSection = document.getElementById('resultSection');
    const resultImage = document.getElementById('resultImage');
    const loadingIndicator = document.getElementById('loadingIndicator');
    const loadingText = document.getElementById('loadingText');
    const processBtn = document.getElementById('processBtn');
    const resetBtn = document.getElementById('resetBtn');
    const downloadBtn = document.getElementById('downloadBtn');
    const newImageBtn = document.getElementById('newImageBtn');
    const methodSelect = document.getElementById('methodSelect');
    const blurStrengthLabel = document.getElementById('blurStrengthLabel');
    const selectionInfo = document.getElementById('selectionInfo');
    const remainingCount = document.getElementById('remainingCount');

    // ── 狀態 ────────────────────────────────
    let currentImage = null;
    let currentFile = null;
    let currentFileId = null;
    let originalFile = null;  // for comparison slider
    let regions = [];         // [{x,y,w,h,color}]
    let isSelecting = false;
    let startX = 0, startY = 0;
    let currentSelection = { x: 0, y: 0, w: 0, h: 0 };
    let regionColors = ['#ea2261', '#533afd', '#15be53', '#f59e0b', '#f96bee', '#06b6d4'];
    let processedBlob = null;
    let isFreePlan = false;
    let userRemaining = 0;
    let userLimit = 3;

    // 檢查計劃
    checkUserPlan();

    // ── Upload setup ────────────────────────
    setupUploadZone('uploadZone', 'fileInput', handleFileSelected, 'image/*');

    function handleFileSelected(file) {
        if (!file.type.startsWith('image/')) {
            showToast('請選擇圖片檔案', 'error');
            return;
        }
        currentFile = file;
        originalFile = file;
        currentImage = new Image();
        currentImage.onload = () => setupCanvas(currentImage);
        currentImage.src = URL.createObjectURL(file);
    }

    function setupCanvas(img) {
        toolWorkspace.classList.remove('hidden');
        resultSection.classList.add('hidden');
        loadingIndicator.classList.add('hidden');
        regions = [];
        processBtn.disabled = true;
        currentFileId = null;

        const maxW = imagePreview.clientWidth - 32;
        const maxH = 500;
        let w = img.width, h = img.height;
        const ratio = Math.min(maxW / w, maxH / h, 1);
        w = Math.floor(w * ratio);
        h = Math.floor(h * ratio);

        canvas.width = w;
        canvas.height = h;
        ctx.clearRect(0, 0, w, h);
        ctx.drawImage(img, 0, 0, w, h);

        // 鼠標 / 觸控事件
        canvas.onmousedown = startSelection;
        canvas.onmousemove = updateSelection;
        canvas.onmouseup = endSelection;
        canvas.onmouseleave = endSelection;
        canvas.ontouchstart = (e) => {
            e.preventDefault();
            const touch = e.touches[0];
            const rect = canvas.getBoundingClientRect();
            startSelection({ offsetX: touch.clientX - rect.left, offsetY: touch.clientY - rect.top });
        };
        canvas.ontouchmove = (e) => {
            e.preventDefault();
            const touch = e.touches[0];
            const rect = canvas.getBoundingClientRect();
            updateSelection({ offsetX: touch.clientX - rect.left, offsetY: touch.clientY - rect.top });
        };
        canvas.ontouchend = endSelection;

        resetBtn.disabled = false;
        selectionInfo.innerHTML = 
            (window.i18n?.multi_region?.hint || 'Drag to select watermark areas — you can select multiple areas.');
        updateRegionBadges();
        showToast(
            (window.i18n?.multi_region?.hint || 'Image loaded. Drag to select watermark areas.'),
            'info'
        );
    }

    // ── 多區域選擇 ──────────────────────────
    function getCanvasPos(e) {
        const rect = canvas.getBoundingClientRect();
        return {
            x: e.offsetX || (e.clientX - rect.left),
            y: e.offsetY || (e.clientY - rect.top)
        };
    }

    function startSelection(e) {
        isSelecting = true;
        const pos = getCanvasPos(e);
        startX = pos.x;
        startY = pos.y;
        currentSelection = { x: 0, y: 0, w: 0, h: 0 };
    }

    function updateSelection(e) {
        if (!isSelecting) return;
        const pos = getCanvasPos(e);
        currentSelection = {
            x: Math.min(startX, pos.x),
            y: Math.min(startY, pos.y),
            w: Math.abs(pos.x - startX),
            h: Math.abs(pos.y - startY)
        };
        redraw();
    }

    function endSelection() {
        if (!isSelecting) return;
        isSelecting = false;
        if (currentSelection.w > 8 && currentSelection.h > 8) {
            // Scale to original image coordinates
            const scaleX = currentImage.width / canvas.width;
            const scaleY = currentImage.height / canvas.height;
            regions.push({
                x: Math.round(currentSelection.x * scaleX),
                y: Math.round(currentSelection.y * scaleY),
                w: Math.round(currentSelection.w * scaleX),
                h: Math.round(currentSelection.h * scaleY),
                color: regionColors[regions.length % regionColors.length]
            });
            processBtn.disabled = false;
            updateRegionBadges();
        }
        currentSelection = { x: 0, y: 0, w: 0, h: 0 };
        redraw();
    }

    function removeRegion(index) {
        regions.splice(index, 1);
        processBtn.disabled = regions.length === 0;
        updateRegionBadges();
        redraw();
    }

    function clearRegions() {
        regions = [];
        processBtn.disabled = true;
        updateRegionBadges();
        redraw();
    }

    function updateRegionBadges() {
        const container = document.getElementById('regionBadges') || createRegionBadgeContainer();
        if (regions.length === 0) {
            container.innerHTML = '';
            container.classList.add('hidden');
            selectionInfo.innerHTML = 
                (window.i18n?.multi_region?.hint || 'Drag to select watermark areas — you can select multiple.');
            return;
        }
        container.classList.remove('hidden');
        let html = '';
        regions.forEach((r, i) => {
            const label = (window.i18n?.multi_region?.region || 'Area {n}').replace('{n}', i + 1);
            html += `<span class="region-badge" style="background:${r.color}">${label}` +
                    ` <span class="region-badge-remove" data-index="${i}">×</span></span>`;
        });
        html += `<button class="btn btn-sm btn-ghost" id="clearRegionsBtn" style="font-size:0.75rem;padding:2px 8px;">` +
                (window.i18n?.multi_region?.clear_all || 'Clear All') + `</button>`;
        container.innerHTML = html;

        document.querySelectorAll('.region-badge-remove').forEach(el => {
            el.addEventListener('click', () => removeRegion(parseInt(el.dataset.index)));
        });
        const clearBtn = document.getElementById('clearRegionsBtn');
        if (clearBtn) clearBtn.addEventListener('click', clearRegions);

        // Update info
        let infoText = `${regions.length} ` + 
            (window.i18n?.multi_region?.title || 'Selected Areas') + ` — `;
        regions.forEach((r, i) => {
            infoText += `${i + 1}: (${r.x},${r.y}) ${r.w}×${r.h}px `;
        });
        selectionInfo.innerHTML = infoText;
    }

    function createRegionBadgeContainer() {
        const container = document.createElement('div');
        container.id = 'regionBadges';
        container.className = 'region-badges';
        const sidebar = document.querySelector('.tool-sidebar .card');
        if (sidebar) {
            sidebar.insertBefore(container, sidebar.querySelector('label') || sidebar.firstChild);
        }
        return container;
    }

    function redraw() {
        if (!currentImage) return;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(currentImage, 0, 0, canvas.width, canvas.height);

        const scaleX = canvas.width / currentImage.width;
        const scaleY = canvas.height / currentImage.height;

        // Draw saved regions
        regions.forEach((r, i) => {
            const rx = r.x * scaleX, ry = r.y * scaleY;
            const rw = r.w * scaleX, rh = r.h * scaleY;
            ctx.strokeStyle = r.color;
            ctx.lineWidth = 2;
            ctx.setLineDash([6, 3]);
            ctx.strokeRect(rx, ry, rw, rh);
            ctx.fillStyle = r.color.replace(')', ',0.12)').replace('rgb', 'rgba');
            ctx.fillRect(rx, ry, rw, rh);
            ctx.fillStyle = r.color;
            ctx.font = 'bold 12px sans-serif';
            ctx.fillText(`#${i + 1}`, rx + 4, ry + 14);
            ctx.setLineDash([]);
        });

        // Draw current selection
        if (currentSelection.w > 0 && currentSelection.h > 0) {
            ctx.strokeStyle = '#ea2261';
            ctx.lineWidth = 2;
            ctx.setLineDash([6, 3]);
            ctx.strokeRect(currentSelection.x, currentSelection.y, currentSelection.w, currentSelection.h);
            ctx.fillStyle = 'rgba(234, 34, 97, 0.1)';
            ctx.fillRect(currentSelection.x, currentSelection.y, currentSelection.w, currentSelection.h);
            ctx.setLineDash([]);
        }
    }

    // ── 自動檢測 ────────────────────────────
    async function autoDetectWatermarks() {
        if (!currentFile) {
            showToast('請先上傳圖片', 'warning');
            return;
        }
        const detectBtn = document.getElementById('autoDetectBtn');
        if (!detectBtn) return;
        
        detectBtn.disabled = true;
        detectBtn.innerHTML = `<span class="spinner-sm"></span> ` + 
            (window.i18n?.auto_detect?.processing || 'Detecting...');
        
        try {
            const formData = new FormData();
            formData.append('file', currentFile);
            const res = await fetch('/api/detect-watermarks', { method: 'POST', body: formData });
            const data = await res.json();
            
            if (!res.ok) {
                showToast(data.error || 'Detection failed', 'error');
                detectBtn.disabled = false;
                detectBtn.innerHTML = '🔍 ' + (window.i18n?.auto_detect?.btn || 'Auto Detect');
                return;
            }

            if (data.regions && data.regions.length > 0) {
                regions = data.regions.map(r => ({
                    x: r.x, y: r.y,
                    w: r.w, h: r.h,
                    color: regionColors[regions.length % regionColors.length]
                }));
                processBtn.disabled = false;
                updateRegionBadges();
                redraw();
                const msg = (window.i18n?.auto_detect?.found || 'Detected {count} watermark(s)').replace('{count}', data.regions.length);
                showToast(msg, 'success');
            } else {
                showToast(window.i18n?.auto_detect?.not_found || 'No watermark detected.', 'warning');
            }
        } catch (e) {
            showToast(window.i18n?.auto_detect?.error || 'Detection failed: ' + e.message, 'error');
        } finally {
            detectBtn.disabled = false;
            detectBtn.innerHTML = '🔍 ' + (window.i18n?.auto_detect?.btn || 'Auto Detect');
        }
    }

    // ── 處理按鈕 ────────────────────────────
    processBtn.addEventListener('click', async () => {
        if (regions.length === 0) {
            showToast('請框選至少一個水印區域', 'warning');
            return;
        }

        // 檢查限額
        if (isFreePlan && userRemaining <= 0) {
            showUpgradeModal('limit');
            return;
        }

        // 顯示處理進度
        loadingIndicator.classList.remove('hidden');
        resultSection.classList.add('hidden');
        processBtn.disabled = true;
        setProcessingStage('detecting');

        const formData = new FormData();
        formData.append('file', currentFile);
        formData.append('regions', JSON.stringify(regions.map(r => ({
            x: r.x, y: r.y, w: r.w, h: r.h, method: 'auto'
        }))));

        try {
            setProcessingStage('inpainting');
            await sleep(300);  // 動畫效果

            const res = await fetch('/api/process-image', {
                method: 'POST',
                body: formData
            });

            if (res.status === 401) {
                showToast('請先登入', 'error');
                setTimeout(() => window.location.href = '/login', 1500);
                return;
            }

            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                if (errData.no_detection) {
                    showToast(errData.error || 'Could not detect watermarks. Please select manually.', 'warning');
                } else {
                    showToast(errData.error || 'Processing failed', 'error');
                }
                return;
            }

            setProcessingStage('refining');
            await sleep(200);

            // 成功
            processedBlob = await res.blob();
            const url = URL.createObjectURL(processedBlob);
            resultImage.src = url;
            resultSection.classList.remove('hidden');

            // 計算剩餘更新
            const remaining = res.headers.get('X-Remaining') || 
                (res.headers.get('Content-Disposition') ? '' : '');
            if (userRemaining > 0) userRemaining--;

            // 顯示升級提示（免費版）
            if (isFreePlan) {
                showPremiumBanner();
                showToast('處理完成！' + (window.i18n?.watermark_notice?.text || ''), 'success');
            } else {
                showToast('處理完成！', 'success');
            }

            // 更新餘額
            updateRemainingDisplay();
        } catch (e) {
            showToast('處理失敗：' + e.message, 'error');
        } finally {
            loadingIndicator.classList.add('hidden');
            processBtn.disabled = false;
            setProcessingStage('done');
        }
    });

    function setProcessingStage(stage) {
        const label = document.getElementById('stageLabel');
        const sub = document.getElementById('stageSub');
        if (!label) return;
        const stages = {
            'detecting': { label: window.i18n?.auto_detect?.processing || 'Detecting watermarks...', sub: 'Analyzing image...' },
            'inpainting': { label: '正在修復...', sub: 'Applying AI inpainting...' },
            'refining': { label: '精修中...', sub: 'Refining edges & textures...' },
            'done': { label: '完成！', sub: '' }
        };
        const s = stages[stage] || stages['detecting'];
        label.textContent = s.label;
        if (sub) sub.textContent = s.sub;
    }

    // ── 檢查用戶計劃 ────────────────────────
    async function checkUserPlan() {
        try {
            const res = await fetch('/api/user-info');
            if (res.ok) {
                const data = await res.json();
                isFreePlan = data.plan === 'free';
                userRemaining = data.remaining || 0;
                userLimit = data.daily_limit || 3;
                updateRemainingDisplay();
            }
        } catch (e) {
            // Not logged in
        }
    }

    function updateRemainingDisplay() {
        const remainingEl = document.getElementById('remainingDisplay');
        if (!remainingEl) {
            const sidebar = document.querySelector('.tool-sidebar .card');
            if (!sidebar) return;
            const el = document.createElement('div');
            el.id = 'remainingDisplay';
            el.className = 'remaining-badge';
            el.style.marginBottom = '8px';
            sidebar.insertBefore(el, sidebar.firstChild);
        }
        const el = document.getElementById('remainingDisplay');
        if (el) {
            el.textContent = (window.i18n?.premium_modal?.free_remaining || 'Remaining: {count}/{limit}')
                .replace('{count}', userRemaining).replace('{limit}', userLimit);
            if (userRemaining <= 0) {
                el.style.background = '#fee2e2';
                el.style.color = '#dc2626';
                el.style.border = '1px solid #fca5a5';
            } else {
                el.style.background = '';
                el.style.color = '';
                el.style.border = '';
            }
        }
    }

    // ── 免費版升級提示 ──────────────────────
    function showPremiumBanner() {
        // 移除舊的
        const old = document.querySelector('.premium-banner');
        if (old) old.remove();
        
        const wrapper = document.querySelector('.result-section') || document.querySelector('.section .container');
        if (!wrapper) return;
        
        const banner = document.createElement('div');
        banner.className = 'premium-banner';
        banner.innerHTML = `
            <div class="premium-banner-text">
                ⚡ ${window.i18n?.watermark_notice?.upgrade || 'Remove watermark'} — ${window.i18n?.premium_modal?.subtitle || 'Unlock Pro'}
            </div>
            <a href="/pricing" class="btn btn-lg">${window.i18n?.premium_modal?.cta_upgrade || 'Upgrade Now'} ✨</a>
        `;
        wrapper.appendChild(banner);
    }

    function showUpgradeModal(reason = 'upgrade') {
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.innerHTML = `
            <div class="modal-card">
                <button class="modal-close" id="modalClose">✕</button>
                <div class="modal-icon">💎</div>
                <h2 class="modal-title">${window.i18n?.premium_modal?.title || 'Upgrade to Pro'}</h2>
                <p class="modal-subtitle">${window.i18n?.premium_modal?.subtitle || 'Unlock unlimited access'}</p>
                <ul class="modal-features">
                    ${(window.i18n?.premium_modal?.features || ['Unlimited daily','AI detection','Batch','No watermark','Priority support'])
                        .map(f => `<li>${f}</li>`).join('')}
                </ul>
                <a href="/pricing" class="btn btn-primary modal-cta">${window.i18n?.premium_modal?.cta_upgrade || 'Upgrade Now'} ✨</a>
                <a class="modal-secondary" id="modalLater">${window.i18n?.premium_modal?.cta_later || 'Maybe Later'}</a>
            </div>
        `;
        document.body.appendChild(overlay);

        document.getElementById('modalClose').onclick = () => overlay.remove();
        document.getElementById('modalLater').onclick = () => overlay.remove();
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) overlay.remove();
        });
    }

    // ── 退出意圖 (Exit Intent) ──────────────
    let exitIntentShown = false;
    document.addEventListener('mouseleave', (e) => {
        if (exitIntentShown || isFreePlan === false) return;
        if (e.clientY <= 0 && regions.length > 0) {
            exitIntentShown = true;
            showUpgradeModal('exit');
        }
    });

    // ── Reset ────────────────────────────────
    resetBtn.addEventListener('click', () => {
        clearRegions();
        selectionInfo.innerHTML = 
            (window.i18n?.multi_region?.hint || 'Drag to select watermark areas.');
    });

    // ── Download ─────────────────────────────
    downloadBtn.addEventListener('click', () => {
        if (!processedBlob) return;
        const url = URL.createObjectURL(processedBlob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'watermark_removed.png';
        a.click();
        URL.revokeObjectURL(url);
    });

    // ── New Image ────────────────────────────
    newImageBtn.addEventListener('click', () => {
        resultSection.classList.add('hidden');
        toolWorkspace.classList.add('hidden');
        currentImage = null;
        currentFile = null;
        currentFileId = null;
        processedBlob = null;
        regions = [];
        canvas.width = 0;
        canvas.height = 0;
        processBtn.disabled = true;
        // Remove premium banner
        const banner = document.querySelector('.premium-banner');
        if (banner) banner.remove();
    });

    // ── 添加自動檢測按鈕到側邊欄 ──────────
    function addAutoDetectButton() {
        const sidebar = document.querySelector('.tool-sidebar .card');
        if (!sidebar) return;
        
        // 只在第一次加載時添加
        if (document.getElementById('autoDetectBtn')) return;
        
        const detectBtn = document.createElement('button');
        detectBtn.id = 'autoDetectBtn';
        detectBtn.className = 'btn btn-outline btn-detect';
        detectBtn.innerHTML = '🔍 ' + (window.i18n?.auto_detect?.btn || 'Auto Detect');
        detectBtn.onclick = autoDetectWatermarks;
        
        // 插入到 methodSelect 之前
        const firstLabel = sidebar.querySelector('label');
        if (firstLabel) {
            sidebar.insertBefore(detectBtn, firstLabel);
            // 加個間距
            const spacer = document.createElement('div');
            spacer.style.marginTop = '8px';
            sidebar.insertBefore(spacer, detectBtn);
        } else {
            sidebar.appendChild(detectBtn);
        }
    }

    // 在 DOMContentLoaded 後添加自動檢測按鈕
    setTimeout(addAutoDetectButton, 100);

    // ═══════════════════════════════════════
    // 保留舊兼容方法（用作 fallback）
    // ═══════════════════════════════════════
    async function oldProcessImageOnClient(sel, method, blurStrength) {
        return new Promise((resolve) => {
            const offCanvas = document.createElement('canvas');
            offCanvas.width = currentImage.width;
            offCanvas.height = currentImage.height;
            const offCtx = offCanvas.getContext('2d');
            offCtx.drawImage(currentImage, 0, 0);
            const imageData = offCtx.getImageData(sel.x, sel.y, sel.w, sel.h);
            if (method === 'blur') {
                const blurred = boxBlurImageData(imageData, blurStrength);
                offCtx.putImageData(blurred, sel.x, sel.y);
            } else {
                const padded = Math.max(2, Math.floor(blurStrength / 5));
                const blendData = offCtx.getImageData(
                    Math.max(0, sel.x - padded),
                    Math.max(0, sel.y - padded),
                    Math.min(offCanvas.width, sel.w + padded * 2),
                    Math.min(offCanvas.height, sel.h + padded * 2)
                );
                const blurred = boxBlurImageData(blendData, blurStrength);
                offCtx.putImageData(blurred,
                    Math.max(0, sel.x - padded),
                    Math.max(0, sel.y - padded)
                );
            }
            offCanvas.toBlob(resolve, 'image/png');
        });
    }

    function boxBlurImageData(imageData, strength) {
        const w = imageData.width;
        const h = imageData.height;
        const data = imageData.data;
        const output = new Uint8ClampedArray(data.length);
        const r = Math.floor(strength / 2);
        const step = Math.max(1, Math.floor(strength / 3));
        for (let y = 0; y < h; y++) {
            for (let x = 0; x < w; x++) {
                let sumR = 0, sumG = 0, sumB = 0, sumA = 0, count = 0;
                for (let dy = -r; dy <= r; dy += step) {
                    for (let dx = -r; dx <= r; dx += step) {
                        const nx = x + dx;
                        const ny = y + dy;
                        if (nx >= 0 && nx < w && ny >= 0 && ny < h) {
                            const idx = (ny * w + nx) * 4;
                            sumR += data[idx];
                            sumG += data[idx + 1];
                            sumB += data[idx + 2];
                            sumA += data[idx + 3];
                            count++;
                        }
                    }
                }
                const idx = (y * w + x) * 4;
                output[idx] = sumR / count;
                output[idx + 1] = sumG / count;
                output[idx + 2] = sumB / count;
                output[idx + 3] = sumA / count;
            }
        }
        return new ImageData(output, w, h);
    }
});

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}