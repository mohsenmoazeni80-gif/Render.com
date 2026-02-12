import os
import random
import datetime
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from deep_translator import GoogleTranslator
import requests

app = Flask(__name__)
# تنظیمات امنیتی و دیتابیس
app.config['SECRET_KEY'] = 'dev-secret-key-99'
# استفاده از مسیر مستقیم برای دیتابیس در سرور
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'vocab_pro.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- مدل‌های دیتابیس ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    score = db.Column(db.Integer, default=0)
    words = db.relationship('Word', backref='author', lazy=True)

    @property
    def level(self):
        return (self.score // 100) + 1

class Word(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    eng = db.Column(db.String(100), nullable=False)
    farsi = db.Column(db.String(100))
    definition = db.Column(db.Text)
    category = db.Column(db.String(50), default='General')
    image_url = db.Column(db.String(500))
    next_review = db.Column(db.Date, default=datetime.date.today)
    interval = db.Column(db.Integer, default=1)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- مسیرهای اصلی (Routes) ---

@app.route('/')
@login_required
def index():
    today = datetime.date.today()
    due_words = Word.query.filter(Word.user_id == current_user.id, Word.next_review <= today).all()
    stats = {
        'total': len(current_user.words),
        'due': len(due_words),
        'mastered': Word.query.filter(Word.user_id == current_user.id, Word.interval > 10).count()
    }
    return render_template('index.html', words=due_words, stats=stats)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if User.query.filter_by(username=username).first():
            flash('این نام کاربری قبلاً انتخاب شده است.')
            return redirect(url_for('signup'))
        
        hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, password=hashed_pw)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            login_user(user)
            return redirect(url_for('index'))
        flash('اطلاعات ورود اشتباه است.')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/add', methods=['POST'])
@login_required
def add():
    word_text = request.form.get('word').strip().lower()
    cat = request.form.get('category', 'General')
    if word_text:
        try:
            # ترجمه خودکار
            farsi_mean = GoogleTranslator(source='en', target='fa').translate(word_text)
            # تصویر خودکار
            img = f"https://source.unsplash.com/400x300/?{word_text}"
            
            new_word = Word(
                eng=word_text, farsi=farsi_mean, category=cat,
                image_url=img, user_id=current_user.id
            )
            db.session.add(new_word)
            db.session.commit()
            flash(f'واژه "{word_text}" اضافه شد.')
        except:
            flash('خطا در دریافت اطلاعات واژه.')
    return redirect(url_for('index'))

@app.route('/review/<int:id>/<string:status>')
@login_required
def review(id, status):
    word = Word.query.get_or_404(id)
    if status == 'easy':
        word.interval *= 2
    else:
        word.interval = 1
    
    word.next_review = datetime.date.today() + datetime.timedelta(days=word.interval)
    db.session.commit()
    return redirect(url_for('index'))

# --- بخش کوییز و امتیازدهی ---

@app.route('/quiz')
@login_required
def quiz():
    all_words = Word.query.filter_by(user_id=current_user.id).all()
    if len(all_words) < 4:
        flash("حداقل ۴ واژه برای شروع کوییز لازم است.")
        return redirect(url_for('index'))
    
    target = random.choice(all_words)
    others = [w.farsi for w in all_words if w.id != target.id]
    options = random.sample(others, 3) + [target.farsi]
    random.shuffle(options)
    
    return render_template('quiz.html', word=target, options=options)

@app.route('/update_score', methods=['POST'])
@login_required
def update_score():
    current_user.score += 10
    db.session.commit()
    return jsonify({"score": current_user.score})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000)
