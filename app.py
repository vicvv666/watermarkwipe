import os
import uuid
import json
import subprocess
import threading
from datetime import datetime, date
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify, send_file, session, g
)
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from config import Config

# ── i18n 多語言 ────────────────────────────────────────
I18N_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'i18n')
SUPPORTED_LANGS = {
    'zh-HK': {'name': '繁體中文', 'flag': '🇭🇰'},
    'zh-CN': {'name': '简体中文', 'flag': '🇨🇳'},
    'en':    {'name': 'English', 'flag': '🇬🇧'},
}
DEFAULT_LANG = 'zh-HK'

def load_i18n(lang_code):
    """載入語言翻譯 JSON"""
    filepath = os.path.join(I18N_DIR, f'{lang_code}.json')
    if not os.path.exists(filepath):
        filepath = os.path.join(I18N_DIR, f'{DEFAULT_LANG}.json')
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_lang():
    """取得當前語言代碼"""
    # 1. URL 參數 ?lang=xx
    lang = request.args.get('lang')
    if lang and lang in SUPPORTED_LANGS:
        session['lang'] = lang
        return lang
    # 2. Session
    lang = session.get('lang')
    if lang and lang in SUPPORTED_LANGS:
        return lang
    # 3. Accept-Language header
    browser_lang = request.accept_languages.best_match(list(SUPPORTED_LANGS.keys()))
    if browser_lang:
        return browser_lang
    return DEFAULT_LANG

# ── 初始化 ─────────────────────────────────────────────
app = Flask(__name__)
app.config.from_object(Config)

db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = '請先登入以使用此功能'
login_manager.login_message_category = 'warning'

# 確保目錄存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

# ── 資料庫模型 ─────────────────────────────────────────

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    plan = db.Column(db.String(20), default='free')  # free / pro / ultimate
    plan_expiry = db.Column(db.DateTime, nullable=True)
    daily_count = db.Column(db.Integer, default=0)
    count_date = db.Column(db.Date, default=date.today)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_admin = db.Column(db.Boolean, default=False)

    # 支付記錄
    payments = db.relationship('Payment', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_daily_limit(self):
        plan_cfg = Config.PLANS.get(self.plan, Config.PLANS['free'])
        return plan_cfg['daily_limit']

    def can_use_tool(self):
        """檢查今日是否還有使用次數"""
        today = date.today()
        if self.count_date != today:
            self.daily_count = 0
            self.count_date = today
            db.session.commit()
        return self.daily_count < self.get_daily_limit()

    def use_tool(self):
        """記錄一次使用"""
        today = date.today()
        if self.count_date != today:
            self.daily_count = 0
            self.count_date = today
        self.daily_count += 1
        db.session.commit()

    @property
    def max_file_size_mb(self):
        return Config.PLANS.get(self.plan, Config.PLANS['free'])['max_file_size_mb']

    @property
    def plan_info(self):
        return Config.PLANS.get(self.plan, Config.PLANS['free'])

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'plan': self.plan,
            'plan_name': self.plan_info['name'],
            'daily_used': self.daily_count,
            'daily_limit': self.get_daily_limit(),
        }


class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    order_id = db.Column(db.String(64), unique=True, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    plan_purchased = db.Column(db.String(20), nullable=False)
    method = db.Column(db.String(20), nullable=False)  # wechat / alipay
    status = db.Column(db.String(20), default='pending')  # pending / paid / expired
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime, nullable=True)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ── 裝飾器 ─────────────────────────────────────────────

def check_daily_limit(f):
    """檢查每日使用次數"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'error': '請先登入'}), 401
        if not current_user.can_use_tool():
            return jsonify({
                'error': '今日使用次數已用完',
                'upgrade_url': url_for('pricing'),
                'daily_limit': current_user.get_daily_limit(),
                'daily_used': current_user.daily_count,
            }), 429
        return f(*args, **kwargs)
    return decorated_function


def require_plan(min_plan):
    """要求最低會員等級"""
    plan_order = {'free': 0, 'pro': 1, 'ultimate': 2}
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify({'error': '請先登入'}), 401
            if plan_order.get(current_user.plan, 0) < plan_order.get(min_plan, 0):
                return jsonify({
                    'error': f'此功能需要 {Config.PLANS[min_plan]["name"]} 或以上',
                    'upgrade_url': url_for('pricing'),
                }), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# ── 頁面路由 ───────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html', plans=Config.PLANS)


@app.route('/pricing')
def pricing():
    return render_template('pricing.html', plans=Config.PLANS)


@app.route('/pay/<plan_key>')
def pay(plan_key):
    """直接收款碼頁面"""
    if plan_key not in Config.PLANS or plan_key == 'free':
        return redirect(url_for('pricing'))

    plan_info = Config.PLANS[plan_key]
    plans_i18n = load_i18n(get_lang())['pricing']

    # Map plan key to i18n name
    name_map = {
        'pro': plans_i18n['pro']['name'],
        'ultimate': plans_i18n['ultimate_plan']['name'],
    }

    return render_template('pay.html',
        plan_key=plan_key,
        plan_name=name_map.get(plan_key, plan_info['name']),
        price_cny=plan_info['price_cny'],
        price_usd=plan_info['price_usd'],
        plans=Config.PLANS)


@app.route('/image-watermark')
def image_watermark():
    return render_template('image-watermark.html', plans=Config.PLANS)


@app.route('/video-watermark')
def video_watermark():
    return render_template('video-watermark.html', plans=Config.PLANS)


@app.route('/pdf-tools')
def pdf_tools():
    return render_template('pdf-tools.html', plans=Config.PLANS)


@app.route('/blog')
def blog():
    lang = get_lang()
    i18n = load_i18n(lang)
    articles = []
    for i in range(1, 11):
        title_key = f'article{i}_title'
        desc_key = f'article{i}_desc'
        if title_key in i18n.get('blog', {}):
            # Assign dates — recent ones first
            days = ['2026-05-15', '2026-05-12', '2026-05-08', '2026-05-04',
                    '2026-04-30', '2026-04-25', '2026-04-20', '2026-04-15',
                    '2026-04-10', '2026-04-05']
            articles.append({
                'date': days[i-1] if i <= len(days) else '2026-04-01',
                'title': i18n['blog'][title_key],
                'desc': i18n['blog'][desc_key],
            })
    return render_template('blog.html', articles=articles)


@app.route('/faq')
def faq():
    return render_template('faq.html')


@app.route('/privacy')
def privacy():
    return render_template('privacy.html')


@app.route('/terms')
def terms():
    return render_template('terms.html')


# ── 認證路由 ───────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user, remember=remember)
            flash('登入成功！', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        flash('電郵或密碼錯誤', 'error')
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not username or not email or not password:
            flash('請填寫所有欄位', 'error')
            return render_template('register.html')

        if len(password) < 6:
            flash('密碼至少需要 6 個字元', 'error')
            return render_template('register.html')

        if User.query.filter_by(email=email).first():
            flash('此電郵已被註冊', 'error')
            return render_template('register.html')

        if User.query.filter_by(username=username).first():
            flash('此用戶名已被使用', 'error')
            return render_template('register.html')

        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        login_user(user)
        flash('註冊成功！歡迎加入 WatermarkWipe！', 'success')
        return redirect(url_for('index'))

    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('已登出', 'info')
    return redirect(url_for('index'))


@app.route('/profile')
@login_required
def profile():
    payments = Payment.query.filter_by(user_id=current_user.id).order_by(Payment.created_at.desc()).limit(10).all()
    return render_template('profile.html', user=current_user, payments=payments)


# ── 支付路由 ───────────────────────────────────────────

@app.route('/api/create-order', methods=['POST'])
@login_required
def create_order():
    data = request.get_json()
    plan_key = data.get('plan', 'pro')
    method = data.get('method', 'wechat')  # wechat / alipay

    if plan_key not in Config.PLANS or plan_key == 'free':
        return jsonify({'error': '無效的會員方案'}), 400

    plan_info = Config.PLANS[plan_key]
    amount = plan_info['price_cny']

    order_id = f'WW{datetime.utcnow().strftime("%Y%m%d%H%M%S")}{uuid.uuid4().hex[:8].upper()}'

    payment = Payment(
        user_id=current_user.id,
        order_id=order_id,
        amount=amount,
        plan_purchased=plan_key,
        method=method,
        status='pending'
    )
    db.session.add(payment)
    db.session.commit()

    # 在正式環境中，這裡會調用微信/支付寶 API 生成支付連結
    # 而家模擬返回一個支付頁面
    return jsonify({
        'order_id': order_id,
        'amount': amount,
        'plan': plan_key,
        'plan_name': plan_info['name'],
        'method': method,
        'pay_url': url_for('payment_page', order_id=order_id),
    })


@app.route('/payment/<order_id>')
@login_required
def payment_page(order_id):
    payment = Payment.query.filter_by(order_id=order_id, user_id=current_user.id).first()
    if not payment:
        flash('訂單不存在', 'error')
        return redirect(url_for('pricing'))
    return render_template('payment.html', payment=payment, plans=Config.PLANS)


@app.route('/api/payment-callback', methods=['POST'])
def payment_callback():
    """支付回調 - 微信支付 / 支付寶會在付款成功時調用此接口"""
    data = request.get_json() if request.is_json else request.form
    order_id = data.get('order_id') or data.get('out_trade_no')

    if not order_id:
        return jsonify({'error': '缺少訂單號'}), 400

    payment = Payment.query.filter_by(order_id=order_id).first()
    if not payment:
        return jsonify({'error': '訂單不存在'}), 404

    payment.status = 'paid'
    payment.paid_at = datetime.utcnow()

    # 升級用戶會員
    user = db.session.get(User, payment.user_id)
    if user:
        user.plan = payment.plan_purchased
        # 會員有效期：30 天
        from datetime import timedelta
        user.plan_expiry = datetime.utcnow() + timedelta(days=30)

    db.session.commit()
    return jsonify({'status': 'ok'})


@app.route('/api/payment-status/<order_id>')
@login_required
def payment_status(order_id):
    payment = Payment.query.filter_by(order_id=order_id, user_id=current_user.id).first()
    if not payment:
        return jsonify({'error': '訂單不存在'}), 404
    return jsonify({
        'order_id': payment.order_id,
        'status': payment.status,
        'amount': payment.amount,
        'plan': payment.plan_purchased,
        'created_at': payment.created_at.isoformat(),
    })


# ── 工具 API ───────────────────────────────────────────

@app.route('/api/user-info')
def user_info():
    if current_user.is_authenticated:
        return jsonify({
            'authenticated': True,
            'user': current_user.to_dict(),
        })
    return jsonify({'authenticated': False})


@app.route('/api/upload', methods=['POST'])
@check_daily_limit
def upload_file():
    """上傳檔案"""
    if 'file' not in request.files:
        return jsonify({'error': '沒有選擇檔案'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '沒有選擇檔案'}), 400

    max_size = current_user.max_file_size_mb * 1024 * 1024
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)

    if file_size > max_size:
        return jsonify({
            'error': f'檔案大小超過限制（{current_user.max_file_size_mb}MB）',
            'upgrade_url': url_for('pricing'),
        }), 413

    # 生成唯一檔名
    ext = os.path.splitext(secure_filename(file.filename))[1].lower()
    file_id = uuid.uuid4().hex
    filename = f'{file_id}{ext}'
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    current_user.use_tool()

    return jsonify({
        'file_id': file_id,
        'filename': file.filename,
        'ext': ext,
        'size': file_size,
        'remaining': current_user.get_daily_limit() - current_user.daily_count,
    })


def _cleanup_files(*paths, delay=30):
    """延遲清理臨時文件"""
    def _do_clean():
        for p in paths:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass
    threading.Timer(delay, _do_clean).start()


@app.route('/api/detect-watermarks', methods=['POST'])
def detect_watermarks():
    """自動檢測圖片水印區域"""
    if 'file' not in request.files:
        return jsonify({'error': '沒有選擇檔案'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '沒有選擇檔案'}), 400

    file_id = uuid.uuid4().hex
    ext = os.path.splitext(secure_filename(file.filename))[1].lower() or '.png'
    input_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{file_id}_detect{ext}')
    file.save(input_path)

    try:
        from processors.image import WatermarkDetector
        import cv2
        cv_img = cv2.imread(input_path)
        if cv_img is None:
            return jsonify({'error': '無法讀取圖片'}), 400
        results = WatermarkDetector.detect_all(cv_img)
        return jsonify({
            'regions': results,
            'count': len(results),
            'message': f'已檢測到 {len(results)} 個水印區域' if results else '未檢測到水印'
        })
    except Exception as e:
        return jsonify({'error': f'檢測失敗：{str(e)}'}), 500
    finally:
        _cleanup_files(input_path, delay=20)


@app.route('/api/process-image', methods=['POST'])
@check_daily_limit
def process_image():
    """
    後端圖片去水印——頂級多區域/多遍精修
    支援：
    - 多區域 regions JSON (新接口)
    - 單區域 x/y/w/h/method (舊接口兼容)
    - 自動檢測 (regions 為空時)
    - 免費版輸出加品牌水印
    """
    if 'file' not in request.files:
        return jsonify({'error': '沒有選擇檔案'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '沒有選擇檔案'}), 400

    # 解析 regions —— 新接口
    regions_json = request.form.get('regions')
    regions = None
    if regions_json:
        try:
            regions = json.loads(regions_json)
        except (json.JSONDecodeError, TypeError):
            return jsonify({'error': '無效的 regions 參數'}), 400

    # 如果沒有 regions，用舊接口單區域參數
    if not regions:
        try:
            x = int(request.form.get('x', 0))
            y = int(request.form.get('y', 0))
            width = int(request.form.get('width', 0))
            height = int(request.form.get('height', 0))
            method = request.form.get('method', 'inpaint')
        except (ValueError, TypeError):
            return jsonify({'error': '無效的參數'}), 400

        if width <= 0 or height <= 0:
            return jsonify({'error': '請框選水印區域'}), 400

        method_map = {'inpaint': 'precise_inpaint', 'ns': 'content_aware_fill',
                       'blur': 'edge_feather_blur', 'auto': 'auto'}
        regions = [{'x': x, 'y': y, 'w': width, 'h': height,
                     'method': method_map.get(method, 'precise_inpaint')}]

    # 儲存上傳檔案
    file_id = uuid.uuid4().hex
    ext = os.path.splitext(secure_filename(file.filename))[1].lower() or '.png'
    input_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{file_id}_in{ext}')
    output_path = os.path.join(app.config['OUTPUT_FOLDER'], f'{file_id}_out.png')
    file.save(input_path)

    try:
        from processors.image import ImageProcessor, WatermarkDetector
        import cv2

        # 如果 regions 為空或請求自動檢測，自動調用檢測器
        if not regions or (len(regions) == 1 and regions[0].get('auto', False)):
            cv_img = cv2.imread(input_path)
            if cv_img is not None:
                detected = WatermarkDetector.detect_all(cv_img)
                if detected:
                    regions = detected
                else:
                    return jsonify({'error': '未能自動檢測水印，請手動框選', 'no_detection': True}), 400

        # 執行多區域去水印
        ImageProcessor.remove_watermark_multipass(input_path, output_path, regions)

        # 免費版輸出加品牌水印
        if current_user.is_authenticated and current_user.plan == 'free':
            # 生成含品牌水印的版本
            watermarked_path = os.path.join(app.config['OUTPUT_FOLDER'], f'{file_id}_out_wm.png')
            ImageProcessor.add_output_watermark(output_path, watermarked_path)
            os.replace(watermarked_path, output_path)

        # 計算剩餘
        remaining = current_user.get_daily_limit() - current_user.daily_count
        current_user.use_tool()

        return send_file(output_path, mimetype='image/png', as_attachment=True,
                         download_name=f'watermark_removed.png')
    except Exception as e:
        return jsonify({'error': f'處理失敗：{str(e)}'}), 500
    finally:
        _cleanup_files(input_path, output_path, delay=30)


@app.route('/api/process-video', methods=['POST'])
@check_daily_limit
def process_video():
    """後端影片去水印——使用 FFmpeg"""
    if 'file' not in request.files:
        return jsonify({'error': '沒有選擇檔案'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '沒有選擇檔案'}), 400

    try:
        x = int(request.form.get('x', 0))
        y = int(request.form.get('y', 0))
        width = int(request.form.get('width', 0))
        height = int(request.form.get('height', 0))
        method = request.form.get('method', 'delogo')
    except (ValueError, TypeError):
        return jsonify({'error': '無效的參數'}), 400

    if width <= 0 or height <= 0:
        return jsonify({'error': '請框選水印區域'}), 400

    file_id = uuid.uuid4().hex
    ext = os.path.splitext(secure_filename(file.filename))[1].lower() or '.mp4'
    input_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{file_id}_in{ext}')
    output_path = os.path.join(app.config['OUTPUT_FOLDER'], f'{file_id}_out.mp4')
    file.save(input_path)

    current_user.use_tool()

    try:
        from processors.video import VideoProcessor

        if method == 'crop':
            info = VideoProcessor.get_video_info(input_path)
            crop_w = info.get('width', 1920) - x
            crop_h = info.get('height', 1080) - y
            VideoProcessor.remove_watermark_crop(input_path, output_path, 0, 0, crop_w, crop_h)
        elif method == 'boxblur':
            VideoProcessor.remove_watermark_advanced(input_path, output_path, x, y, width, height, method='boxblur')
        else:
            VideoProcessor.remove_watermark_blur(input_path, output_path, x, y, width, height)

        return send_file(output_path, mimetype='video/mp4', as_attachment=True,
                         download_name=f'watermark_removed.mp4')
    except subprocess.CalledProcessError as e:
        return jsonify({'error': f'FFmpeg 處理失敗，請確認已安裝 FFmpeg'}), 500
    except Exception as e:
        return jsonify({'error': f'處理失敗：{str(e)}'}), 500


# ── 後台管理 ───────────────────────────────────────────

@app.route('/admin')
@login_required
def admin():
    if not current_user.is_admin:
        flash('沒有管理權限', 'error')
        return redirect(url_for('index'))
    users = User.query.order_by(User.created_at.desc()).all()
    payments = Payment.query.order_by(Payment.created_at.desc()).limit(50).all()
    return render_template('admin.html', users=users, payments=payments)


# ── 上下文注入 ─────────────────────────────────────────

@app.context_processor
def inject_globals():
    lang = get_lang()
    i18n = load_i18n(lang)
    # Load SEO data
    seo_path = os.path.join(I18N_DIR, 'seo.json')
    with open(seo_path, 'r', encoding='utf-8') as f:
        seo_data = json.load(f)
    return {
        'lang': lang,
        'i18n': i18n,
        'seo_data': seo_data,
        'config': Config,
        'supported_langs': SUPPORTED_LANGS,
        'plans': Config.PLANS,
        'adsense_client_id': Config.ADSENSE_CLIENT_ID,
        'adsense_slot_top': Config.ADSENSE_SLOT_TOP,
        'adsense_slot_sidebar': Config.ADSENSE_SLOT_SIDEBAR,
        'adsense_slot_result': Config.ADSENSE_SLOT_RESULT,
    }


@app.route('/set-lang/<lang_code>')
def set_lang(lang_code):
    if lang_code in SUPPORTED_LANGS:
        session['lang'] = lang_code
    return redirect(request.referrer or url_for('index'))


@app.route('/sitemap.xml')
def sitemap():
    """自動生成 Sitemap"""
    base = request.host_url.rstrip('/')
    pages = [
        ('', 'daily', '1.0'),
        ('/image-watermark', 'weekly', '0.9'),
        ('/video-watermark', 'weekly', '0.9'),
        ('/pdf-tools', 'weekly', '0.9'),
        ('/pricing', 'monthly', '0.8'),
        ('/blog', 'weekly', '0.7'),
        ('/faq', 'monthly', '0.6'),
    ]

    urls = []
    for path, freq, priority in pages:
        url_en = f'{base}{path}?lang=en'
        url_hk = f'{base}{path}?lang=zh-HK'
        url_cn = f'{base}{path}?lang=zh-CN'
        urls.append(f'''  <url>
    <loc>{url_en}</loc>
    <changefreq>{freq}</changefreq>
    <priority>{priority}</priority>
    <xhtml:link rel="alternate" hreflang="en" href="{url_en}"/>
    <xhtml:link rel="alternate" hreflang="zh-HK" href="{url_hk}"/>
    <xhtml:link rel="alternate" hreflang="zh-CN" href="{url_cn}"/>
    <xhtml:link rel="alternate" hreflang="x-default" href="{url_en}"/>
  </url>''')

    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:xhtml="http://www.w3.org/1999/xhtml">
{chr(10).join(urls)}
</urlset>'''
    return xml, 200, {'Content-Type': 'application/xml; charset=utf-8'}


@app.route('/robots.txt')
def robots():
    """Robots.txt"""
    base = request.host_url.rstrip('/')
    txt = f"""User-agent: *
Allow: /
Disallow: /admin
Disallow: /api/
Disallow: /payment/

Sitemap: {base}/sitemap.xml

# Crawl-delay for Baidu
User-agent: Baiduspider
Crawl-delay: 1

User-agent: Googlebot
Crawl-delay: 0
"""
    return txt, 200, {'Content-Type': 'text/plain; charset=utf-8'}


# ── 啟動 ───────────────────────────────────────────────

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)