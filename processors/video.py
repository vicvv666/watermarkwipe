"""
影片處理器 — 去水印、裁切、格式轉換
需要安裝 FFmpeg：sudo apt install ffmpeg
"""
import os
import subprocess
import json
import re


class VideoProcessor:
    """影片去水印處理"""

    @staticmethod
    def get_video_info(input_path: str) -> dict:
        """使用 ffprobe 取得影片資訊"""
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_format', '-show_streams', input_path
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                # 嘗試簡單方式
                cmd2 = ['ffprobe', '-v', 'error', '-show_entries',
                        'stream=width,height,duration', '-of', 'csv=p=0', input_path]
                result2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=10)
                parts = result2.stdout.strip().split(',')
                return {
                    'width': int(parts[0]) if len(parts) > 0 and parts[0] else 0,
                    'height': int(parts[1]) if len(parts) > 1 and parts[1] else 0,
                    'duration': float(parts[2]) if len(parts) > 2 and parts[2] else 0,
                }
            info = json.loads(result.stdout)
            video_stream = None
            for stream in info.get('streams', []):
                if stream.get('codec_type') == 'video':
                    video_stream = stream
                    break

            return {
                'width': video_stream.get('width', 0) if video_stream else 0,
                'height': video_stream.get('height', 0) if video_stream else 0,
                'duration': float(info.get('format', {}).get('duration', 0)),
                'codec': video_stream.get('codec_name', '') if video_stream else '',
                'file_size': int(info.get('format', {}).get('size', 0)),
            }
        except Exception as e:
            return {'error': str(e)}

    @staticmethod
    def remove_watermark_blur(input_path: str, output_path: str,
                               x: int, y: int, width: int, height: int,
                               blur_strength: int = 20) -> str:
        """
        使用 FFmpeg delogo 濾鏡去除影片水印
        將水印區域模糊化
        """
        cmd = [
            'ffmpeg', '-y', '-i', input_path,
            '-vf', f'delogo=x={x}:y={y}:w={width}:h={height}:show=0',
            '-c:a', 'copy',
            output_path
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
        return output_path

    @staticmethod
    def remove_watermark_crop(input_path: str, output_path: str,
                               crop_x: int, crop_y: int,
                               crop_width: int, crop_height: int) -> str:
        """
        裁切去除水印（如果水印在邊緣）
        """
        cmd = [
            'ffmpeg', '-y', '-i', input_path,
            '-vf', f'crop={crop_width}:{crop_height}:{crop_x}:{crop_y}',
            '-c:a', 'copy',
            output_path
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
        return output_path

    @staticmethod
    def remove_watermark_advanced(input_path: str, output_path: str,
                                   x: int, y: int, width: int, height: int,
                                   method: str = 'delogo') -> str:
        """
        高級去水印：delogo + 輕微模糊邊緣
        """
        if method == 'delogo':
            return VideoProcessor.remove_watermark_blur(
                input_path, output_path, x, y, width, height, blur_strength=15
            )
        elif method == 'boxblur':
            # 對特定區域做 box blur
            cmd = [
                'ffmpeg', '-y', '-i', input_path,
                '-filter_complex',
                f'[0:v]split[bg][fg];'
                f'[fg]crop={width}:{height}:{x}:{y},boxblur=20[blur];'
                f'[bg][blur]overlay={x}:{y}',
                '-c:a', 'copy',
                output_path
            ]
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
            return output_path
        else:
            return VideoProcessor.remove_watermark_blur(
                input_path, output_path, x, y, width, height
            )

    @staticmethod
    def convert_video(input_path: str, output_path: str, target_format: str) -> str:
        """轉換影片格式"""
        codec_map = {
            'mp4': 'libx264',
            'webm': 'libvpx-vp9',
            'mov': 'libx264',
            'avi': 'libxvid',
        }
        codec = codec_map.get(target_format.lower(), 'libx264')

        cmd = [
            'ffmpeg', '-y', '-i', input_path,
            '-c:v', codec, '-c:a', 'aac',
            '-preset', 'fast',
            output_path
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
        return output_path

    @staticmethod
    def compress_video(input_path: str, output_path: str, crf: int = 28) -> str:
        """壓縮影片（CRF 越高越小，28 係平衡值）"""
        cmd = [
            'ffmpeg', '-y', '-i', input_path,
            '-c:v', 'libx264', '-crf', str(crf),
            '-preset', 'fast', '-c:a', 'aac', '-b:a', '128k',
            output_path
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
        return output_path

    @staticmethod
    def trim_video(input_path: str, output_path: str,
                   start_time: float, end_time: float) -> str:
        """剪輯影片片段"""
        cmd = [
            'ffmpeg', '-y', '-i', input_path,
            '-ss', str(start_time), '-to', str(end_time),
            '-c:v', 'libx264', '-c:a', 'aac',
            '-preset', 'fast',
            output_path
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
        return output_path

    @staticmethod
    def extract_thumbnail(input_path: str, output_path: str,
                          time_pos: float = 1.0) -> str:
        """從影片擷取縮圖"""
        cmd = [
            'ffmpeg', '-y', '-i', input_path,
            '-ss', str(time_pos), '-vframes', '1',
            '-q:v', '2',
            output_path
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=30)
        return output_path