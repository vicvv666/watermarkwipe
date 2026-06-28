/* ═══════════════════════════════════════════════════
   pdf-tool.js — PDF 工具集合
   合併、拆分、壓縮、PDF↔圖片轉換
   ═══════════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', () => {
    // ── Tab switching ──────────────────────────
    const tabs = document.querySelectorAll('.tool-tab');
    const contents = document.querySelectorAll('.tab-content');

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            contents.forEach(c => c.classList.add('hidden'));
            const target = document.getElementById('tab-' + tab.dataset.tab);
            if (target) target.classList.remove('hidden');
        });
    });

    // ── Merge PDF ────────────────────────────
    let mergeFiles = [];
    setupUploadZone('mergeUploadZone', 'mergeFiles', (file) => {
        mergeFiles.push(file);
        renderMergeFileList();
        document.getElementById('mergeBtn').classList.remove('hidden');
    });

    function renderMergeFileList() {
        const list = document.getElementById('mergeFileList');
        list.innerHTML = '<p class="mb-sm" style="color: var(--color-heading);"><strong>已選擇 ' + mergeFiles.length + ' 個檔案：</strong></p>';
        mergeFiles.forEach((f, i) => {
            list.innerHTML += `<div class="flex justify-between items-center p-sm" style="border: 1px solid var(--color-border); border-radius: var(--radius-sm); margin-bottom: 4px;">
                <span style="font-size: 0.875rem;">📄 ${f.name} (${formatFileSize(f.size)})</span>
                <button class="btn btn-outline btn-sm" onclick="removeMergeFile(${i})">✕</button>
            </div>`;
        });
    }

    window.removeMergeFile = function(i) {
        mergeFiles.splice(i, 1);
        renderMergeFileList();
        if (mergeFiles.length === 0) {
            document.getElementById('mergeBtn').classList.add('hidden');
        }
    };

    document.getElementById('mergeBtn')?.addEventListener('click', async () => {
        if (mergeFiles.length < 2) {
            showToast('請選擇至少 2 個 PDF 檔案', 'warning');
            return;
        }
        showLoading(true);
        try {
            const formData = new FormData();
            mergeFiles.forEach(f => formData.append('files', f));
            // In production: upload and merge on server
            await simulateProcess(1500);
            showResult(['merged_output.pdf']);
            showToast('合併完成！', 'success');
        } catch (e) {
            showToast('合併失敗：' + e.message, 'error');
        }
        showLoading(false);
    });

    // ── Split PDF ─────────────────────────────
    let splitFile = null;
    setupUploadZone('splitUploadZone', 'splitFile', (file) => {
        splitFile = file;
        document.getElementById('splitInfo').classList.remove('hidden');
        document.getElementById('splitPageCount').textContent = `檔案：${file.name} (${formatFileSize(file.size)})`;
    });

    document.getElementById('splitBtn')?.addEventListener('click', async () => {
        if (!splitFile) { showToast('請先上傳 PDF', 'warning'); return; }
        showLoading(true);
        try {
            await simulateProcess(1200);
            const range = document.getElementById('splitRange').value;
            const files = range ? ['split_1.pdf'] : ['page_1.pdf', 'page_2.pdf', 'page_3.pdf'];
            showResult(files);
            showToast('拆分完成！', 'success');
        } catch (e) { showToast('拆分失敗', 'error'); }
        showLoading(false);
    });

    // ── Compress PDF ──────────────────────────
    let compressFile = null;
    setupUploadZone('compressUploadZone', 'compressFile', (file) => {
        compressFile = file;
        document.getElementById('compressInfo').classList.remove('hidden');
    });

    document.getElementById('compressBtn')?.addEventListener('click', async () => {
        if (!compressFile) { showToast('請先上傳 PDF', 'warning'); return; }
        const quality = document.getElementById('compressQuality').value;
        showLoading(true);
        try {
            await simulateProcess(2000);
            showResult(['compressed_output.pdf']);
            showToast(`壓縮完成！(品質：${quality}%)`, 'success');
        } catch (e) { showToast('壓縮失敗', 'error'); }
        showLoading(false);
    });

    // ── PDF to Image ──────────────────────────
    let pdf2imgFile = null;
    setupUploadZone('pdf2imgUploadZone', 'pdf2imgFile', (file) => {
        pdf2imgFile = file;
        document.getElementById('pdf2imgInfo').classList.remove('hidden');
    });

    document.getElementById('pdf2imgBtn')?.addEventListener('click', async () => {
        if (!pdf2imgFile) { showToast('請先上傳 PDF', 'warning'); return; }
        showLoading(true);
        try {
            await simulateProcess(1800);
            showResult(['page_1.png', 'page_2.png', 'page_3.png']);
            showToast('轉換完成！', 'success');
        } catch (e) { showToast('轉換失敗', 'error'); }
        showLoading(false);
    });

    // ── Image to PDF ──────────────────────────
    let img2pdfFiles = [];
    setupUploadZone('img2pdfUploadZone', 'img2pdfFiles', (file) => {
        img2pdfFiles.push(file);
        renderImg2PdfList();
        document.getElementById('img2pdfBtn').classList.remove('hidden');
    });

    function renderImg2PdfList() {
        const list = document.getElementById('img2pdfList');
        list.innerHTML = '<p class="mb-sm" style="color: var(--color-heading);"><strong>已選擇 ' + img2pdfFiles.length + ' 張圖片：</strong></p>';
        img2pdfFiles.forEach((f, i) => {
            list.innerHTML += `<div class="flex justify-between items-center p-sm" style="border: 1px solid var(--color-border); border-radius: var(--radius-sm); margin-bottom: 4px;">
                <span style="font-size: 0.875rem;">🖼️ ${f.name} (${formatFileSize(f.size)})</span>
                <button class="btn btn-outline btn-sm" onclick="removeImgFile(${i})">✕</button>
            </div>`;
        });
    }

    window.removeImgFile = function(i) {
        img2pdfFiles.splice(i, 1);
        renderImg2PdfList();
        if (img2pdfFiles.length === 0) {
            document.getElementById('img2pdfBtn').classList.add('hidden');
        }
    };

    document.getElementById('img2pdfBtn')?.addEventListener('click', async () => {
        if (img2pdfFiles.length === 0) { showToast('請選擇圖片', 'warning'); return; }
        showLoading(true);
        try {
            await simulateProcess(1500);
            showResult(['converted.pdf']);
            showToast('轉換完成！', 'success');
        } catch (e) { showToast('轉換失敗', 'error'); }
        showLoading(false);
    });

    // ── Helpers ───────────────────────────────
    function showLoading(show) {
        const loader = document.getElementById('loadingIndicator');
        if (loader) {
            if (show) loader.classList.remove('hidden');
            else loader.classList.add('hidden');
        }
    }

    function showResult(files) {
        const section = document.getElementById('resultSection');
        const list = document.getElementById('resultList');
        if (!section || !list) return;

        section.classList.remove('hidden');
        list.innerHTML = '<div class="card"><h4 class="card-title mb-md">輸出檔案</h4>';
        files.forEach(f => {
            const isImage = f.endsWith('.png') || f.endsWith('.jpg') || f.endsWith('.jpeg');
            const icon = isImage ? '🖼️' : '📄';
            list.innerHTML += `<div class="flex justify-between items-center p-sm mb-sm" style="border: 1px solid var(--color-border); border-radius: var(--radius-sm);">
                <span>${icon} ${f}</span>
                <button class="btn btn-primary btn-sm download-result-btn" data-file="${f}">⬇ 下載</button>
            </div>`;
        });
        list.innerHTML += '</div>';

        // Download buttons — in production these link to actual files
        document.querySelectorAll('.download-result-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                showToast(`下載 ${btn.dataset.file}（示範模式）`, 'info');
            });
        });
    }

    function simulateProcess(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
});