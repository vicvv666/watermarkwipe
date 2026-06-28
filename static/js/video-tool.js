/* ═══════════════════════════════════════════════════
   video-tool.js — 影片去水印功能
   擷取影片畫面 → 框選水印 → 後端 FFmpeg 處理
   ═══════════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', () => {
    const uploadZone = document.getElementById('uploadZone');
    const fileInput = document.getElementById('fileInput');
    const toolWorkspace = document.getElementById('toolWorkspace');
    const videoPlayer = document.getElementById('videoPlayer');
    const frameCanvas = document.getElementById('frameCanvas');
    const frameCanvas2 = document.getElementById('frameCanvas2');
    const framePreview = document.getElementById('framePreview');
    const frameHint = document.getElementById('frameHint');
    const resultSection = document.getElementById('resultSection');
    const resultVideo = document.getElementById('resultVideo');
    const loadingIndicator = document.getElementById('loadingIndicator');
    const loadingText = document.getElementById('loadingText');
    const progressBar = document.getElementById('progressBar');
    const processBtn = document.getElementById('processBtn');
    const resetBtn = document.getElementById('resetBtn');
    const downloadBtn = document.getElementById('downloadBtn');
    const newVideoBtn = document.getElementById('newVideoBtn');
    const captureFrameBtn = document.getElementById('captureFrameBtn');
    const playPauseBtn = document.getElementById('playPauseBtn');
    const methodSelect = document.getElementById('methodSelect');
    const selectionInfo = document.getElementById('selectionInfo');
    const cropArea = document.getElementById('cropArea');
    const remainingCount = document.getElementById('remainingCount');

    let currentFile = null;
    let currentVideoURL = null;
    let capturedFrame = null;
    let selection = { x: 0, y: 0, width: 0, height: 0 };
    let isSelecting = false;
    let startX = 0, startY = 0;
    let selectionMade = false;
    let resultURL = null;

    // ── Upload setup ────────────────────────────
    setupUploadZone('uploadZone', 'fileInput', handleFileSelected, 'video/*');

    function handleFileSelected(file) {
        if (!file.type.startsWith('video/')) {
            showToast('請選擇影片檔案', 'error');
            return;
        }
        currentFile = file;
        if (currentVideoURL) URL.revokeObjectURL(currentVideoURL);
        currentVideoURL = URL.createObjectURL(file);
        videoPlayer.src = currentVideoURL;
        toolWorkspace.classList.remove('hidden');
        resultSection.classList.add('hidden');
        loadingIndicator.classList.add('hidden');
        framePreview.classList.add('hidden');
        frameHint.classList.add('hidden');
        selectionMade = false;
        selection = { x: 0, y: 0, width: 0, height: 0 };
        processBtn.disabled = true;
        resetBtn.disabled = false;
        frameCanvas.classList.add('hidden');
        showToast('影片已載入，請播放到有水印嘅畫面，然後擷取截圖', 'info');
    }

    // ── Capture Frame ───────────────────────────
    captureFrameBtn.addEventListener('click', () => {
        videoPlayer.pause();
        const vw = videoPlayer.videoWidth;
        const vh = videoPlayer.videoHeight;

        if (!vw || !vh) {
            showToast('影片尚未載入完成', 'warning');
            return;
        }

        frameCanvas2.width = vw;
        frameCanvas2.height = vh;
        const ctx2 = frameCanvas2.getContext('2d');
        ctx2.drawImage(videoPlayer, 0, 0, vw, vh);

        capturedFrame = ctx2.getImageData(0, 0, vw, vh);
        framePreview.classList.remove('hidden');
        frameHint.classList.remove('hidden');
        selectionMade = false;
        selection = { x: 0, y: 0, width: 0, height: 0 };
        selectionInfo.textContent = '尚未框選區域';
        processBtn.disabled = true;

        // Fit to preview
        const maxW = framePreview.clientWidth - 32;
        const ratio = Math.min(maxW / vw, 400 / vh, 1);
        frameCanvas2.style.width = Math.floor(vw * ratio) + 'px';
        frameCanvas2.style.height = Math.floor(vh * ratio) + 'px';

        // Selection on frame
        frameCanvas2.onmousedown = startFrameSelection;
        frameCanvas2.onmousemove = updateFrameSelection;
        frameCanvas2.onmouseup = endFrameSelection;
        frameCanvas2.onmouseleave = endFrameSelection;

        showToast('請在截圖上框選水印區域', 'info');
    });

    function getFrameCanvasPos(e) {
        const rect = frameCanvas2.getBoundingClientRect();
        return {
            x: (e.offsetX || (e.clientX - rect.left)) * (frameCanvas2.width / rect.width),
            y: (e.offsetY || (e.clientY - rect.top)) * (frameCanvas2.height / rect.height)
        };
    }

    function startFrameSelection(e) {
        isSelecting = true;
        const pos = getFrameCanvasPos(e);
        startX = pos.x;
        startY = pos.y;
        selection = { x: 0, y: 0, width: 0, height: 0 };
        redrawFrameCanvas();
    }

    function updateFrameSelection(e) {
        if (!isSelecting) return;
        const pos = getFrameCanvasPos(e);
        selection = {
            x: Math.round(Math.min(startX, pos.x)),
            y: Math.round(Math.min(startY, pos.y)),
            width: Math.round(Math.abs(pos.x - startX)),
            height: Math.round(Math.abs(pos.y - startY))
        };
        redrawFrameCanvas();
    }

    function endFrameSelection() {
        if (!isSelecting) return;
        isSelecting = false;
        if (selection.width > 5 && selection.height > 5) {
            selectionMade = true;
            processBtn.disabled = false;
            selectionInfo.innerHTML = `
                水印位置：(${selection.x}, ${selection.y})<br>
                尺寸：${selection.width} × ${selection.height}
            `;
        }
    }

    function redrawFrameCanvas() {
        if (!capturedFrame) return;
        const ctx2 = frameCanvas2.getContext('2d');
        ctx2.putImageData(capturedFrame, 0, 0);

        if (selection.width > 0 && selection.height > 0) {
            ctx2.strokeStyle = '#ea2261';
            ctx2.lineWidth = 2;
            ctx2.setLineDash([6, 3]);
            ctx2.strokeRect(selection.x, selection.y, selection.width, selection.height);
            ctx2.fillStyle = 'rgba(234, 34, 97, 0.1)';
            ctx2.fillRect(selection.x, selection.y, selection.width, selection.height);
            ctx2.setLineDash([]);
        }
    }

    // ── Play/Pause ──────────────────────────────
    playPauseBtn.addEventListener('click', () => {
        if (videoPlayer.paused) {
            videoPlayer.play();
            playPauseBtn.textContent = '⏸️ 暫停';
        } else {
            videoPlayer.pause();
            playPauseBtn.textContent = '▶️ 播放';
        }
    });

    videoPlayer.addEventListener('play', () => playPauseBtn.textContent = '⏸️ 暫停');
    videoPlayer.addEventListener('pause', () => playPauseBtn.textContent = '▶️ 播放');

    // ── Method toggle ───────────────────────────
    methodSelect.addEventListener('change', () => {
        if (methodSelect.value === 'crop') {
            cropArea.style.display = '';
        } else {
            cropArea.style.display = 'none';
        }
    });

    // ── Process video ──────────────────────────
    processBtn.addEventListener('click', async () => {
        if (!selectionMade || !currentFile) {
            showToast('請先擷取畫面並框選水印區域', 'warning');
            return;
        }

        loadingIndicator.classList.remove('hidden');
        resultSection.classList.add('hidden');
        processBtn.disabled = true;
        loadingText.textContent = '正在上傳影片...';
        progressBar.style.width = '10%';

        const formData = new FormData();
        formData.append('file', currentFile);
        formData.append('x', selection.x);
        formData.append('y', selection.y);
        formData.append('width', selection.width);
        formData.append('height', selection.height);
        formData.append('method', methodSelect.value);

        try {
            // 直接呼叫後端 FFmpeg 處理
            loadingText.textContent = '正在上傳影片...';
            progressBar.style.width = '10%';

            const res = await fetch('/api/process-video', {
                method: 'POST',
                body: formData
            });

            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                if (res.status === 401 || res.status === 429) {
                    showToast(errData.error, 'warning');
                    return;
                }
                showToast(errData.error || '處理失敗', 'error');
                return;
            }

            progressBar.style.width = '90%';
            loadingText.textContent = '處理完成！';

            // 取回影片 blob
            const blob = await res.blob();
            resultURL = URL.createObjectURL(blob);
            resultVideo.src = resultURL;
            resultSection.classList.remove('hidden');
            showToast('影片處理完成！', 'success');
            loadingIndicator.classList.add('hidden');
            processBtn.disabled = false;

        } catch (e) {
            showToast('處理失敗：' + e.message, 'error');
            loadingIndicator.classList.add('hidden');
            processBtn.disabled = false;
        }
    });

    // ── Reset ────────────────────────────────────
    resetBtn.addEventListener('click', () => {
        selection = { x: 0, y: 0, width: 0, height: 0 };
        selectionMade = false;
        selectionInfo.textContent = '尚未框選水印區域';
        processBtn.disabled = true;
        redrawFrameCanvas();
    });

    // ── Download ─────────────────────────────────
    downloadBtn.addEventListener('click', () => {
        if (!resultURL) return;
        const a = document.createElement('a');
        a.href = resultURL;
        a.download = 'watermark_removed.mp4';
        a.click();
    });

    // ── New Video ────────────────────────────────
    newVideoBtn.addEventListener('click', () => {
        resultSection.classList.add('hidden');
        toolWorkspace.classList.add('hidden');
        framePreview.classList.add('hidden');
        frameHint.classList.add('hidden');
        currentFile = null;
        capturedFrame = null;
        selectionMade = false;
        processBtn.disabled = true;
        if (currentVideoURL) URL.revokeObjectURL(currentVideoURL);
        videoPlayer.src = '';
    });
});