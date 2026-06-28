import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'change-this-in-production-!!')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///watermarkwipe.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    OUTPUT_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'outputs')
    MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500MB

    # 會員方案
    PLANS = {
        'free': {
            'name': '免費版',
            'name_en': 'Free',
            'price_cny': 0,
            'price_usd': 0,
            'daily_limit': 3,
            'max_file_size_mb': 10,
            'features': ['每日 3 次', '基本去水印', 'PDF 工具', '有水印輸出'],
        },
        'pro': {
            'name': '專業版',
            'name_en': 'Pro',
            'price_cny': 19,
            'price_usd': 2.9,
            'daily_limit': 30,
            'max_file_size_mb': 100,
            'features': ['每日 30 次', '高清去水印', '全部 PDF 工具', '無水印輸出', '優先處理'],
        },
        'ultimate': {
            'name': '旗艦版',
            'name_en': 'Ultimate',
            'price_cny': 49,
            'price_usd': 7,
            'daily_limit': 999,
            'max_file_size_mb': 500,
            'features': ['無限次數', 'AI 智能去水印', '批量處理', '全部功能', '無水印輸出', 'API 接入', '專屬客服'],
        },
    }

    # ═══════════════════════════════════════════════
    # 微信支付 / 支付寶配置
    # ═══════════════════════════════════════════════
    #
    # 方式一：個人收款碼（推薦起步用，零門檻）
    #   將你嘅微信/支付寶收款 QR Code 圖片放入 static/img/ 目錄
    #   然後修改下面檔名
    #
    # 方式二：商戶 API 接入（需要營業執照）
    #   申請微信支付商戶平台：https://pay.weixin.qq.com
    #   申請支付寶開放平台：https://open.alipay.com
    #   取得 Key 後填入下面環境變數

    # ── 個人收款碼模式 ──────────────────────────
    PAYMENT_MODE = os.environ.get('PAYMENT_MODE', 'qrcode')  # 'qrcode' 或 'api'
    WECHAT_QRCODE = os.environ.get('WECHAT_QRCODE', 'wechat-pay.jpg')   # 微信收款碼圖片
    ALIPAY_QRCODE = os.environ.get('ALIPAY_QRCODE', 'alipay.jpg')       # 支付寶收款碼圖片
    PAYMENT_NOTE = os.environ.get('PAYMENT_NOTE', '付款後請聯繫客服確認')  # 付款提示

    # ── 商戶 API 模式 ──────────────────────────
    WECHAT_APP_ID = os.environ.get('WECHAT_APP_ID', '')
    WECHAT_MCH_ID = os.environ.get('WECHAT_MCH_ID', '')
    WECHAT_API_KEY = os.environ.get('WECHAT_API_KEY', '')

    ALIPAY_APP_ID = os.environ.get('ALIPAY_APP_ID', '')
    ALIPAY_PRIVATE_KEY = os.environ.get('ALIPAY_PRIVATE_KEY', '')
    ALIPAY_PUBLIC_KEY = os.environ.get('ALIPAY_PUBLIC_KEY', '')

    # Google AdSense
    ADSENSE_CLIENT_ID = os.environ.get('ADSENSE_CLIENT_ID', 'ca-pub-XXXXXXXXXXXXXXXX')
    ADSENSE_SLOT_TOP = os.environ.get('ADSENSE_SLOT_TOP', '')
    ADSENSE_SLOT_SIDEBAR = os.environ.get('ADSENSE_SLOT_SIDEBAR', '')
    ADSENSE_SLOT_RESULT = os.environ.get('ADSENSE_SLOT_RESULT', '')