"""
PDF 處理器 — 合併、拆分、壓縮、轉換
需要 PyMuPDF (fitz)
"""
import os
import fitz  # PyMuPDF
from PIL import Image
import io


class PDFProcessor:
    """PDF 工具集合"""

    @staticmethod
    def get_pdf_info(input_path: str) -> dict:
        """取得 PDF 資訊"""
        doc = fitz.open(input_path)
        info = {
            'pages': len(doc),
            'file_size': os.path.getsize(input_path),
            'metadata': doc.metadata,
        }
        doc.close()
        return info

    @staticmethod
    def merge_pdfs(pdf_paths: list, output_path: str) -> str:
        """合併多個 PDF"""
        merged = fitz.open()

        for path in pdf_paths:
            doc = fitz.open(path)
            merged.insert_pdf(doc)
            doc.close()

        merged.save(output_path, garbage=3, deflate=True)
        merged.close()
        return output_path

    @staticmethod
    def split_pdf(input_path: str, output_dir: str,
                  page_ranges: list = None) -> list:
        """
        拆分 PDF
        page_ranges: list of (start, end) tuples (1-indexed)
        如果無指定，每頁拆一個
        """
        doc = fitz.open(input_path)
        output_files = []

        if page_ranges is None:
            # 每頁一個檔案
            for i in range(len(doc)):
                new_doc = fitz.open()
                new_doc.insert_pdf(doc, from_page=i, to_page=i)
                out_path = os.path.join(output_dir, f'page_{i + 1}.pdf')
                new_doc.save(out_path)
                new_doc.close()
                output_files.append(out_path)
        else:
            for idx, (start, end) in enumerate(page_ranges):
                new_doc = fitz.open()
                new_doc.insert_pdf(doc, from_page=start - 1, to_page=end - 1)
                out_path = os.path.join(output_dir, f'split_{idx + 1}.pdf')
                new_doc.save(out_path)
                new_doc.close()
                output_files.append(out_path)

        doc.close()
        return output_files

    @staticmethod
    def compress_pdf(input_path: str, output_path: str,
                     quality: int = 50) -> str:
        """壓縮 PDF（降低內嵌圖片質量）"""
        doc = fitz.open(input_path)

        for page in doc:
            images = page.get_images(full=True)
            for img_info in images:
                xref = img_info[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image['image']
                image_ext = base_image['ext']

                try:
                    pil_image = Image.open(io.BytesIO(image_bytes))
                    if pil_image.mode in ('RGBA', 'P'):
                        pil_image = pil_image.convert('RGB')

                    output_buffer = io.BytesIO()
                    pil_image.save(output_buffer, format='JPEG', quality=quality)
                    compressed = output_buffer.getvalue()

                    # 替代原圖
                    new_xref = 0
                    if image_ext.lower() in ('jpeg', 'jpg'):
                        doc.update_image(xref, stream=compressed, alpha=0)
                    else:
                        # PNG -> JPEG 替代
                        new_rect = fitz.Rect(0, 0, pil_image.width, pil_image.height)
                        doc.update_image(xref, pixmap=fitz.Pixmap(compressed))
                except Exception:
                    pass

        doc.save(output_path, garbage=4, deflate=True)
        doc.close()
        return output_path

    @staticmethod
    def pdf_to_images(input_path: str, output_dir: str,
                      dpi: int = 150, fmt: str = 'png') -> list:
        """PDF 轉圖片"""
        doc = fitz.open(input_path)
        output_files = []

        for i, page in enumerate(doc):
            pix = page.get_pixmap(dpi=dpi)
            out_path = os.path.join(output_dir, f'page_{i + 1}.{fmt}')
            pix.save(out_path)
            output_files.append(out_path)

        doc.close()
        return output_files

    @staticmethod
    def images_to_pdf(image_paths: list, output_path: str) -> str:
        """圖片轉 PDF"""
        doc = fitz.open()

        for img_path in image_paths:
            img = Image.open(img_path)
            if img.mode != 'RGB':
                img = img.convert('RGB')

            # Save to buffer and open with fitz
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='JPEG', quality=90)
            img_bytes.seek(0)

            pdf_page = fitz.open('jpeg', img_bytes.read())
            doc.insert_pdf(pdf_page)
            pdf_page.close()

        doc.save(output_path)
        doc.close()
        return output_path

    @staticmethod
    def extract_text(input_path: str) -> str:
        """提取 PDF 文字"""
        doc = fitz.open(input_path)
        text = ''
        for page in doc:
            text += page.get_text()
        doc.close()
        return text

    @staticmethod
    def rotate_pages(input_path: str, output_path: str,
                     rotation: int = 90) -> str:
        """旋轉 PDF 頁面"""
        doc = fitz.open(input_path)
        for page in doc:
            page.set_rotation(page.rotation + rotation)
        doc.save(output_path)
        doc.close()
        return output_path

    @staticmethod
    def remove_pages(input_path: str, output_path: str,
                     pages_to_remove: list) -> str:
        """刪除指定頁面"""
        doc = fitz.open(input_path)
        for page_num in sorted(pages_to_remove, reverse=True):
            if 0 <= page_num - 1 < len(doc):
                doc.delete_page(page_num - 1)
        doc.save(output_path)
        doc.close()
        return output_path

    @staticmethod
    def reorder_pages(input_path: str, output_path: str,
                      new_order: list) -> str:
        """重新排序頁面"""
        doc = fitz.open(input_path)
        new_doc = fitz.open()

        for page_num in new_order:
            if 0 <= page_num - 1 < len(doc):
                new_doc.insert_pdf(doc, from_page=page_num - 1, to_page=page_num - 1)

        new_doc.save(output_path)
        new_doc.close()
        doc.close()
        return output_path