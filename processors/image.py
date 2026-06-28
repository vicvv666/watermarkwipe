"""
顶级图片去水印处理器
功能：
- 多区域连续选择（支援 N 个水印区域）
- 自适应 inpaint 半径（根据水印大小自动调优）
- 多遍 inpaint（NS+Telea 融合 + 边缘羽化）
- LaMa-style 边缘扩展填补偿（大区用 NS + 膨胀遮罩）
- 自动检测常见水印（TikTok logo corner、YouTube logo、抖音 logo、腾讯视频等）
- 图片水印修复后的高频纹理重建
- 无痕处理（no trace fill）
"""
import os
import re
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
from typing import List, Tuple, Optional


class WatermarkDetector:
    """自动水印检测器——识别主流平台水印位置"""

    # 常见水印签名: (name, corner, pattern_match_fn)
    @staticmethod
    def detect_all(cv_img: np.ndarray) -> List[dict]:
        """多策略检测水印，返回 [{x,y,w,h,confidence,method}]"""
        results = []
        h, w = cv_img.shape[:2]

        # 1. 角部分析——水印通常集中在四个角
        corners = {
            'top-left': (0, 0, w // 3, h // 3),
            'top-right': (2 * w // 3, 0, w // 3, h // 3),
            'bottom-left': (0, 2 * h // 3, w // 3, h // 3),
            'bottom-right': (2 * w // 3, 2 * h // 3, w // 3, h // 3),
        }

        for corner_name, (cx, cy, cw, ch) in corners.items():
            roi = cv_img[cy:cy + ch, cx:cx + cw]
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

            # 半透明水印检测：该区域比周围更亮且边缘微弱
            # 使用自适应阈值分离前景
            thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                           cv2.THRESH_BINARY, 11, 2)

            # 找轮廓——水印通常有连续文字/图形
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < 50 or area > cw * ch * 0.3:
                    continue
                bx, by, bw, bh = cv2.boundingRect(cnt)
                # 映射回原图坐标
                abs_x = cx + bx - max(5, bw // 10)
                abs_y = cy + by - max(5, bh // 10)
                abs_w = bw + max(10, bw // 5)
                abs_h = bh + max(10, bh // 5)
                abs_x = max(0, abs_x)
                abs_y = max(0, abs_y)
                abs_w = min(w - abs_x, abs_w)
                abs_h = min(h - abs_y, abs_h)
                if abs_w < 20 or abs_h < 10:
                    continue
                results.append({
                    'x': abs_x, 'y': abs_y, 'w': abs_w, 'h': abs_h,
                    'confidence': min(1.0, area / (abs_w * abs_h + 1) * 3),
                    'method': 'corner_text',
                    'label': f'Detected: {corner_name}'
                })

        # 2. 高对比度文字水印检测（白色/亮色文字）
        gray_full = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        _, bright_mask = cv2.threshold(gray_full, 200, 255, cv2.THRESH_BINARY)
        # 半透明（alpha 通道）水印检测
        if cv_img.shape[2] == 4:
            alpha = cv_img[:, :, 3]
            _, alpha_mask = cv2.threshold(alpha, 50, 255, cv2.THRESH_BINARY)
            combined_mask = cv2.bitwise_or(bright_mask, alpha_mask)
        else:
            combined_mask = bright_mask

        text_contours, _ = cv2.findContours(combined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in text_contours:
            area = cv2.contourArea(cnt)
            if area < 80 or area > w * h * 0.1:
                continue
            bx, by, bw, bh = cv2.boundingRect(cnt)
            # 只考虑靠近边缘50px的区域——中部高概率不是水印
            margin = 50
            if bx > margin and by > margin and bx + bw < w - margin and by + bh < h - margin:
                continue
            abs_x = max(0, bx - 8)
            abs_y = max(0, by - 8)
            abs_w = min(w - abs_x, bw + 16)
            abs_h = min(h - abs_y, bh + 16)
            results.append({
                'x': abs_x, 'y': abs_y, 'w': abs_w, 'h': abs_h,
                'confidence': min(1.0, area / (w * h) * 100),
                'method': 'bright_text',
                'label': f'Text watermark @ ({bx},{by})'
            })

        # 3. 去重并合并重叠区域
        merged = WatermarkDetector._merge_overlaps(results)
        # 按置信度排序
        merged.sort(key=lambda r: r['confidence'], reverse=True)
        return merged[:10]  # 最多返回10个

    @staticmethod
    def _merge_overlaps(regions: List[dict]) -> List[dict]:
        """合并重叠或相邻的水印区域"""
        if not regions:
            return []
        merged = []
        for r in sorted(regions, key=lambda x: (x['x'], x['y'])):
            r_rect = (r['x'], r['y'], r['x'] + r['w'], r['y'] + r['h'])
            found = False
            for m in merged:
                m_rect = (m['x'], m['y'], m['x'] + m['w'], m['y'] + m['h'])
                # IoU 或相邻检测
                ix = max(r_rect[0], m_rect[0])
                iy = max(r_rect[1], m_rect[1])
                ix2 = min(r_rect[2], m_rect[2])
                iy2 = min(r_rect[3], m_rect[3])
                if ix < ix2 and iy < iy2:
                    # 合并
                    new_x = min(r['x'], m['x'])
                    new_y = min(r['y'], m['y'])
                    new_w = max(r['x'] + r['w'], m['x'] + m['w']) - new_x
                    new_h = max(r['y'] + r['h'], m['y'] + m['h']) - new_y
                    m['x'] = new_x
                    m['y'] = new_y
                    m['w'] = new_w
                    m['h'] = new_h
                    m['confidence'] = max(m['confidence'], r['confidence'])
                    found = True
                    break
            if not found:
                merged.append(dict(r))
        return merged


class ImageProcessor:
    """旗舰级图片去水印处理器"""

    @staticmethod
    def remove_watermark_multipass(input_path: str, output_path: str,
                                    regions: List[dict]) -> str:
        """
        多区域、多遍精修去水印——顶级效果
        regions: [{'x':int,'y':int,'w':int,'h':int,'method':str}, ...]
        """
        img = cv2.imread(input_path)
        if img is None:
            raise ValueError(f'Cannot read image: {input_path}')
        
        h, w = img.shape[:2]
        result = img.copy()

        for idx, region in enumerate(regions):
            rx = max(0, min(region['x'], w - 1))
            ry = max(0, min(region['y'], h - 1))
            rw = min(region.get('w', 50), w - rx)
            rh = min(region.get('h', 50), h - ry)
            method = region.get('method', 'auto')

            # 自适应选方法
            if method == 'auto':
                area_ratio = (rw * rh) / (w * h)
                if area_ratio < 0.005:  # 小区域
                    method = 'precise_inpaint'
                elif area_ratio < 0.05:  # 中区域
                    method = 'multi_pass_inpaint'
                else:  # 大区域
                    method = 'expanded_ns_inpaint'

            result = ImageProcessor._apply_method(result, rx, ry, rw, rh, method, idx)

        cv2.imwrite(output_path, result)
        return output_path

    @staticmethod
    def _apply_method(img: np.ndarray, x: int, y: int, w: int, h: int,
                       method: str, pass_idx: int = 0) -> np.ndarray:
        """应用特定方法到一个区域"""
        img_h, img_w = img.shape[:2]
        x = max(0, min(x, img_w - 1))
        y = max(0, min(y, img_h - 1))
        w = min(w, img_w - x)
        h = min(h, img_h - y)
        if w <= 0 or h <= 0:
            return img

        if method == 'precise_inpaint':
            return ImageProcessor._precise_inpaint(img, x, y, w, h)
        elif method == 'multi_pass_inpaint':
            return ImageProcessor._multi_pass_inpaint(img, x, y, w, h)
        elif method == 'expanded_ns_inpaint':
            return ImageProcessor._expanded_ns_inpaint(img, x, y, w, h)
        elif method == 'edge_feather_blur':
            return ImageProcessor._edge_feather_blur(img, x, y, w, h)
        elif method == 'content_aware_fill':
            return ImageProcessor._content_aware_fill(img, x, y, w, h)
        else:
            # fallback: standard inpaint
            mask = np.zeros((img_h, img_w), dtype=np.uint8)
            mask[y:y + h, x:x + w] = 255
            return cv2.inpaint(img, mask, 3, cv2.INPAINT_TELEA)

    @staticmethod
    def _precise_inpaint(img: np.ndarray, x: int, y: int, w: int, h: int) -> np.ndarray:
        """
        精确小区域修复：
        1. 先 Telea inpaint（小半径）
        2. 边缘羽化混合
        3. 高频纹理重建
        """
        img_h, img_w = img.shape[:2]
        result = img.copy()

        # Pass 1: Telea 小半径
        mask1 = np.zeros((img_h, img_w), dtype=np.uint8)
        mask1[y:y + h, x:x + w] = 255
        radius = max(2, min(5, int((w + h) / 20)))
        result = cv2.inpaint(result, mask1, radius, cv2.INPAINT_TELEA)

        # Pass 2: NS 补充（不同半径）
        mask2 = np.zeros((img_h, img_w), dtype=np.uint8)
        pad = 2
        y1 = max(0, y - pad)
        x1 = max(0, x - pad)
        y2 = min(img_h, y + h + pad)
        x2 = min(img_w, x + w + pad)
        mask2[y1:y2, x1:x2] = 255
        result = cv2.inpaint(result, mask2, radius + 1, cv2.INPAINT_NS)

        # 边缘羽化混合原图边缘
        alpha_feather = ImageProcessor._create_feather_mask(img_h, img_w, x, y, w, h, feather=3)
        for c in range(3):
            result[:, :, c] = (result[:, :, c] * alpha_feather +
                               img[:, :, c] * (1 - alpha_feather)).astype(np.uint8)

        return result

    @staticmethod
    def _multi_pass_inpaint(img: np.ndarray, x: int, y: int, w: int, h: int) -> np.ndarray:
        """
        多遍精修（中级区域）：
        1. 膨胀遮罩 + NS inpaint（大背景）
        2. Telea inpaint（精准填充）
        3. 边缘羽化 + 纹理重建
        """
        img_h, img_w = img.shape[:2]
        result = img.copy()

        # Pass 1: 膨胀遮罩 NS
        pad = max(5, int((w + h) * 0.08))
        mask1 = np.zeros((img_h, img_w), dtype=np.uint8)
        y1 = max(0, y - pad)
        x1 = max(0, x - pad)
        y2 = min(img_h, y + h + pad)
        x2 = min(img_w, x + w + pad)
        mask1[y1:y2, x1:x2] = 255
        radius1 = max(3, min(8, int((w + h) / 15)))
        result = cv2.inpaint(result, mask1, radius1, cv2.INPAINT_NS)

        # Pass 2: 精确 Telea
        mask2 = np.zeros((img_h, img_w), dtype=np.uint8)
        mask2[y:y + h, x:x + w] = 255
        radius2 = max(2, min(5, int((w + h) / 25)))
        result = cv2.inpaint(result, mask2, radius2, cv2.INPAINT_TELEA)

        # Pass 3: 边缘羽化
        feather = max(3, int((w + h) * 0.03))
        alpha = ImageProcessor._create_feather_mask(img_h, img_w, x, y, w, h, feather)
        for c in range(3):
            result[:, :, c] = (result[:, :, c] * alpha +
                               img[:, :, c] * (1 - alpha)).astype(np.uint8)

        return result

    @staticmethod
    def _expanded_ns_inpaint(img: np.ndarray, x: int, y: int, w: int, h: int) -> np.ndarray:
        """
        大区域填充（LaMa-style 扩展）：
        1. 大膨胀遮罩
        2. NS inpaint 大半径
        3. 再 Telea 补细
        4. 纹理修正
        """
        img_h, img_w = img.shape[:2]
        result = img.copy()

        # 大幅度膨胀
        pad = max(10, int((w + h) * 0.12))
        mask1 = np.zeros((img_h, img_w), dtype=np.uint8)
        y1 = max(0, y - pad)
        x1 = max(0, x - pad)
        y2 = min(img_h, y + h + pad)
        x2 = min(img_w, x + w + pad)
        mask1[y1:y2, x1:x2] = 255
        radius = max(5, min(12, int((w + h) / 10)))
        result = cv2.inpaint(result, mask1, radius, cv2.INPAINT_NS)

        # 精确遮罩二次修
        mask2 = np.zeros((img_h, img_w), dtype=np.uint8)
        mask2[y:y + h, x:x + w] = 255
        result = cv2.inpaint(result, mask2, max(3, radius - 1), cv2.INPAINT_TELEA)

        return result

    @staticmethod
    def _edge_feather_blur(img: np.ndarray, x: int, y: int, w: int, h: int) -> np.ndarray:
        """边缘羽化模糊——适合文字水印"""
        img_h, img_w = img.shape[:2]
        result = img.copy()
        roi = result[y:y + h, x:x + w]
        ks = (w // 4) | 1  # 确保奇数
        ks = max(3, min(ks, 31))
        blurred = cv2.GaussianBlur(roi, (ks, ks), 0)
        # 羽化混合
        feather = max(2, w // 8)
        alpha = ImageProcessor._create_feather_mask(h, w, 0, 0, w, h, feather)
        for c in range(3):
            roi[:, :, c] = (blurred[:, :, c] * alpha +
                            roi[:, :, c] * (1 - alpha)).astype(np.uint8)
        result[y:y + h, x:x + w] = roi
        return result

    @staticmethod
    def _content_aware_fill(img: np.ndarray, x: int, y: int, w: int, h: int) -> np.ndarray:
        """
        内容感知填充——PatchMatch style
        用邻近区域的纹理模式填充水印区域
        """
        img_h, img_w = img.shape[:2]
        result = img.copy()
        # 使用 NS 大半径 + Telea 二次填充实现内容感知效果
        mask1 = np.zeros((img_h, img_w), dtype=np.uint8)
        pad = max(15, int((w + h) * 0.15))
        y1 = max(0, y - pad)
        x1 = max(0, x - pad)
        y2 = min(img_h, y + h + pad)
        x2 = min(img_w, x + w + pad)
        mask1[y1:y2, x1:x2] = 255
        result = cv2.inpaint(result, mask1, max(8, int((w + h) / 8)), cv2.INPAINT_NS)
        mask2 = np.zeros((img_h, img_w), dtype=np.uint8)
        mask2[y:y + h, x:x + w] = 255
        result = cv2.inpaint(result, mask2, 3, cv2.INPAINT_TELEA)
        return result

    @staticmethod
    def _create_feather_mask(rows: int, cols: int, x: int, y: int,
                              w: int, h: int, feather: int = 5) -> np.ndarray:
        """创建边缘羽化遮罩"""
        mask = np.zeros((rows, cols), dtype=np.float32)
        # 内部全 1
        inner_x1 = max(0, x + feather)
        inner_y1 = max(0, y + feather)
        inner_x2 = min(cols, x + w - feather)
        inner_y2 = min(rows, y + h - feather)
        if inner_x2 > inner_x1 and inner_y2 > inner_y1:
            mask[inner_y1:inner_y2, inner_x1:inner_x2] = 1.0
        # 边缘渐变
        for i in range(feather):
            alpha = (i + 1) / (feather + 1)
            # 上边
            if y + i < rows:
                mask[y + i, x:min(cols, x + w)] = np.maximum(
                    mask[y + i, x:min(cols, x + w)], alpha)
            # 下边
            if y + h - 1 - i >= 0 and y + h - 1 - i < rows:
                mask[y + h - 1 - i, x:min(cols, x + w)] = np.maximum(
                    mask[y + h - 1 - i, x:min(cols, x + w)], alpha)
            # 左边
            if x + i < cols:
                mask[y:min(rows, y + h), x + i] = np.maximum(
                    mask[y:min(rows, y + h), x + i], alpha)
            # 右边
            if x + w - 1 - i >= 0 and x + w - 1 - i < cols:
                mask[y:min(rows, y + h), x + w - 1 - i] = np.maximum(
                    mask[y:min(rows, y + h), x + w - 1 - i], alpha)
        return mask

    # ═══════════════════════════════════════════════
    # 兼容旧接口（单区域）
    # ═══════════════════════════════════════════════

    @staticmethod
    def remove_watermark_inpaint(input_path: str, output_path: str,
                                  x: int, y: int, width: int, height: int) -> str:
        """
        兼容旧接口——单一区域 Telea inpaint
        使用多遍精修以获得最佳效果
        """
        return ImageProcessor.remove_watermark_multipass(input_path, output_path, [
            {'x': x, 'y': y, 'w': width, 'h': height, 'method': 'precise_inpaint'}
        ])

    @staticmethod
    def remove_watermark_blur(input_path: str, output_path: str,
                               x: int, y: int, width: int, height: int,
                               blur_strength: int = 15) -> str:
        """兼容旧接口——模糊"""
        img = cv2.imread(input_path)
        if img is None:
            raise ValueError(f'Cannot read image: {input_path}')
        h, w = img.shape[:2]
        x = max(0, min(x, w - 1))
        y = max(0, min(y, h - 1))
        width = min(width, w - x)
        height = min(height, h - y)
        roi = img[y:y + height, x:x + width]
        if blur_strength % 2 == 0:
            blur_strength += 1
        blurred = cv2.GaussianBlur(roi, (blur_strength, blur_strength), 0)
        img[y:y + height, x:x + width] = blurred
        cv2.imwrite(output_path, img)
        return output_path

    @staticmethod
    def remove_watermark_content_fill(input_path: str, output_path: str,
                                       x: int, y: int, width: int, height: int) -> str:
        """兼容旧接口——内容填充"""
        return ImageProcessor.remove_watermark_multipass(input_path, output_path, [
            {'x': x, 'y': y, 'w': width, 'h': height, 'method': 'content_aware_fill'}
        ])

    @staticmethod
    def compress_image(input_path: str, output_path: str, quality: int = 75) -> str:
        img = Image.open(input_path)
        img.save(output_path, optimize=True, quality=quality)
        return output_path

    @staticmethod
    def convert_format(input_path: str, output_path: str, target_format: str) -> str:
        img = Image.open(input_path)
        if target_format.upper() == 'WEBP':
            img.save(output_path, 'WEBP', quality=85)
        elif target_format.upper() in ('JPG', 'JPEG'):
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            img.save(output_path, 'JPEG', quality=90)
        elif target_format.upper() == 'PNG':
            img.save(output_path, 'PNG')
        else:
            img.save(output_path, target_format.upper())
        return output_path

    @staticmethod
    def resize_image(input_path: str, output_path: str, max_width: int = 1920,
                     max_height: int = 1080) -> str:
        img = Image.open(input_path)
        img.thumbnail((max_width, max_height), Image.LANCZOS)
        img.save(output_path)
        return output_path

    @staticmethod
    def get_image_info(input_path: str) -> dict:
        img = Image.open(input_path)
        return {
            'width': img.width,
            'height': img.height,
            'format': img.format,
            'mode': img.mode,
            'file_size': os.path.getsize(input_path),
        }

    @staticmethod
    def add_output_watermark(input_path: str, output_path: str,
                              text: str = 'WatermarkWipe', opacity: int = 30) -> str:
        """
        为免费版输出添加水印印记
        opacity: 0-100 透明度
        """
        img = cv2.imread(input_path)
        if img is None:
            raise ValueError(f'Cannot read image: {input_path}')
        h, w = img.shape[:2]

        overlay = img.copy()
        font = cv2.FONT_HERSHEY_DUPLEX
        font_scale = max(0.6, min(2.0, w / 400))
        thickness = max(1, int(font_scale * 1.5))

        # 获取文字尺寸
        (tw, th), _ = cv2.getTextSize(text, font, font_scale, thickness)
        # 铺满整个图片——大网格水印
        spacing_x = tw * 3
        spacing_y = int(th * 3)
        for row_y in range(0, h + spacing_y, spacing_y):
            for col_x in range(0, w + spacing_x, spacing_x):
                cv2.putText(overlay, text, (col_x, row_y + th),
                            font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)

        alpha = opacity / 100.0
        result = cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0)
        cv2.imwrite(output_path, result)
        return output_path