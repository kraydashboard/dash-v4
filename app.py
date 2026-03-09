import os
import datetime
import requests
import hashlib
import threading
import json
import telebot 
from datetime import date, timedelta
from flask import Flask, render_template, request, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from flask_apscheduler import APScheduler
from functools import wraps
from flask import Flask, render_template, request, jsonify, send_file, session

app = Flask(__name__)
# --- CONFIG ---
app.secret_key = os.environ.get("SECRET_KEY", "sdfeergrthbwefsDSlvsrgpsesvaflsvkvl")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "YOUR_LOCAL_TOKEN")
REQUEST_BOT_TOKEN = os.environ.get("REQUEST_BOT_TOKEN", "") # Токен для нового бота
HASH_USER = os.environ.get("HASH_USER", "a080f87fefbcc9ddfe34650dd5c20659b852fd8cdd8e269a2bc5c3f4ad7cd7cf")
HASH_ADMIN = os.environ.get("HASH_ADMIN", "a5a915b49d0188897ddbdcaf47868a28af8d06851f3430bbe43e49660f05760a")
HASH_WEB = os.environ.get("HASH_WEB", HASH_USER)
database_url = os.environ.get("DATABASE_URL")
basedir = os.path.abspath(os.path.dirname(__file__))

if database_url:
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    db_filename = 'Life_tracker.db'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, db_filename)

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True, 
    "pool_recycle": 280, 
}
class Config:
    SCHEDULER_API_ENABLED = True

app.config.from_object(Config())

db = SQLAlchemy(app)
scheduler = APScheduler()

bot = None
if TG_BOT_TOKEN and "YOUR_LOCAL" not in TG_BOT_TOKEN:
    bot = telebot.TeleBot(TG_BOT_TOKEN)

request_bot = None
if REQUEST_BOT_TOKEN:
    request_bot = telebot.TeleBot(REQUEST_BOT_TOKEN)


# --- MODELS ---

class BotUser(db.Model):
    __tablename__ = 'bot_users'
    chat_id = db.Column(db.BigInteger, primary_key=True)
    role = db.Column(db.String(20), nullable=False)

class Thread(db.Model):
    __tablename__ = 'threads'
    thread_id = db.Column(db.Integer, primary_key=True)
    thread_name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50)) 
    status = db.Column(db.String(20), default='active')
    rank = db.Column(db.Integer, default=1)
    created_at = db.Column(db.Date, default=date.today)
    created_at_40k = db.Column(db.String(20))
    closed_date = db.Column(db.Date, nullable=True)
    thread_name_redacted = db.Column(db.String(100))
    sub_category = db.Column(db.String(50))
    type = db.Column(db.String(20))     
    cadence = db.Column(db.String(50)) 

class Chain(db.Model):
    __tablename__ = 'chains'
    chain_id = db.Column(db.String(50), primary_key=True)
    thread_id = db.Column(db.Integer, db.ForeignKey('threads.thread_id'))
    chain_start_date = db.Column(db.Date)
    chain_end_date = db.Column(db.Date)
    duration = db.Column(db.Integer, default=0)
    end_reason = db.Column(db.String(255))

class Square(db.Model):
    __tablename__ = 'squares'
    square_id = db.Column(db.String(100), primary_key=True)
    thread_id = db.Column(db.Integer, db.ForeignKey('threads.thread_id'))
    period = db.Column(db.Date) 
    status = db.Column(db.String(10), default='empty')
    chain_id = db.Column(db.String(50), db.ForeignKey('chains.chain_id'), nullable=True)
    chain_start = db.Column(db.Boolean, default=False)
    chain_end = db.Column(db.Boolean, default=False)
    chain_end_reason = db.Column(db.Text, default="") 

class Calendar(db.Model):
    __tablename__ = 'calendar'
    actual_date = db.Column(db.Date, primary_key=True)
    date_40k = db.Column(db.String(20))
    week_40k = db.Column(db.String(20))
    top_work_priority = db.Column(db.Text, default="")
    top_other_priority = db.Column(db.String(200), default="")
    off_routine_flag = db.Column(db.Boolean, default=False)
    off_routine_reason = db.Column(db.String(200), default="")
    project_type_this_week = db.Column(db.String(100), default="") 
    day_meds = db.Column(db.Boolean, default=False) 
    comments = db.Column(db.Text, default="") 

class BoardItem(db.Model):
    __tablename__ = 'board_items'
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.now)
    
class PartnerRequest(db.Model):
    __tablename__ = 'partner_requests'
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.now)

def get_40k_data(d_obj):
    age = d_obj.year - 1992 - ((d_obj.month, d_obj.day) < (2, 16))
    bday = date(1992 + age, 2, 16)
    
    delta_days = (d_obj - bday).days
    week_num = (delta_days // 7) + 1
    day_num = (delta_days % 7) + 1
    
    return f"{age}.{week_num}.{day_num}", f"{age}.{week_num}"

def ensure_calendar_entry(d_date):
    entry = db.session.get(Calendar, d_date)
    if not entry:
        date_str, week_str = get_40k_data(d_date)
        entry = Calendar(
            actual_date=d_date,
            date_40k=date_str,
            week_40k=week_str
        )
        db.session.add(entry)
        db.session.commit()
    return entry

def recalculate_chains(thread_id):
    try:
        Chain.query.filter_by(thread_id=thread_id).delete()
        thread = db.session.get(Thread, thread_id)
        if not thread: return
        
        tolerance_days = 1 
        if thread.cadence == 'weekly': tolerance_days = 7
        elif thread.cadence == '3x_week': tolerance_days = 3
        elif thread.cadence == 'monthly': tolerance_days = 31
        elif thread.cadence == 'quarterly': tolerance_days = 92
        elif thread.cadence == 'yearly': tolerance_days = 366

        hits = Square.query.filter_by(thread_id=thread_id, status='hit').order_by(Square.period).all()
        if not hits:
            db.session.commit()
            return
        
        current_chain = None
        for i, sq in enumerate(hits):
            if current_chain is None:
                new_chain_id = f"CH_{thread_id}_{sq.period.strftime('%Y%m%d')}"
                current_chain = Chain(chain_id=new_chain_id, thread_id=thread_id, chain_start_date=sq.period, chain_end_date=sq.period, duration=1, end_reason="")
                db.session.add(current_chain)
                sq.chain_id = new_chain_id 
            else:
                gap = (sq.period - current_chain.chain_end_date).days
                if gap <= tolerance_days:
                    current_chain.chain_end_date = sq.period
                    current_chain.duration += 1
                    sq.chain_id = current_chain.chain_id
                else:
                    last_end = current_chain.chain_end_date
                    miss_sq = Square.query.filter(Square.thread_id==thread_id, Square.status=='miss', Square.period > last_end, Square.period < sq.period).first()
                    current_chain.end_reason = miss_sq.chain_end_reason if miss_sq else "gap"
                    new_chain_id = f"CH_{thread_id}_{sq.period.strftime('%Y%m%d')}"
                    current_chain = Chain(chain_id=new_chain_id, thread_id=thread_id, chain_start_date=sq.period, chain_end_date=sq.period, duration=1, end_reason="")
                    db.session.add(current_chain)
                    sq.chain_id = new_chain_id
        db.session.commit()
    except Exception as e:
        print(f"Chain error: {e}")

def is_day_fulfilled(thread, date_obj, squares_map):
    try:
        if not thread.cadence or thread.cadence == 'daily': return False
        target_hits = 1
        start_date = None
        end_date = None
        
        if thread.cadence == '3x_week' or thread.cadence == 'weekly':
            age = date_obj.year - 1992 - ((date_obj.month, date_obj.day) < (2, 16))
            bday = date(1992 + age, 2, 16)
            delta_days = (date_obj - bday).days
            week_start_delta = (delta_days // 7) * 7
            start_date = bday + timedelta(days=week_start_delta)
            end_date = start_date + timedelta(days=6)
            
            if thread.cadence == '3x_week': target_hits = 3
            
        elif thread.cadence == 'monthly':
            start_date = date_obj.replace(day=1)
            next_month = (start_date + timedelta(days=32)).replace(day=1)
            end_date = next_month - timedelta(days=1)
        elif thread.cadence == 'quarterly':
            quarter = (date_obj.month - 1) // 3 + 1
            start_month = (quarter - 1) * 3 + 1
            start_date = date(date_obj.year, start_month, 1)
            if start_month + 3 > 12: end_date = date(date_obj.year, 12, 31)
            else: end_date = date(date_obj.year, start_month + 3, 1) - timedelta(days=1)
        elif thread.cadence == 'yearly':
            start_date = date(date_obj.year, 1, 1)
            end_date = date(date_obj.year, 12, 31)
        else: return False

        hits_count = 0
        delta = (end_date - start_date).days
        for i in range(delta + 1):
            check_date = start_date + timedelta(days=i)
            sq = squares_map.get((thread.thread_id, check_date))
            if sq and sq.status == 'hit': hits_count += 1
        
        current_sq = squares_map.get((thread.thread_id, date_obj))
        is_currently_hit = (current_sq and current_sq.status == 'hit')
        if hits_count >= target_hits and not is_currently_hit: return True
        return False
    except Exception as e: 
        print(f"Error in is_day_fulfilled: {e}")
        return False
    
def create_full_backup_json():
    data = {}
    data['threads'] = [{
        'thread_id': t.thread_id, 'thread_name': t.thread_name, 'category': t.category,
        'status': t.status, 'rank': t.rank, 'created_at': str(t.created_at),
        'created_at_40k': t.created_at_40k, 'closed_date': str(t.closed_date) if t.closed_date else None,
        'sub_category': t.sub_category, 'type': t.type, 'cadence': t.cadence,
        'thread_name_redacted': t.thread_name_redacted
    } for t in Thread.query.all()]
    data['squares'] = [{
        'square_id': s.square_id, 'thread_id': s.thread_id, 'period': str(s.period), 
        'status': s.status, 'chain_id': s.chain_id, 'chain_start': s.chain_start,
        'chain_end': s.chain_end, 'chain_end_reason': s.chain_end_reason
    } for s in Square.query.filter(Square.status != 'empty').all()]
    data['calendar'] = [{
        'actual_date': str(c.actual_date), 'date_40k': c.date_40k, 'week_40k': c.week_40k,
        'top_work_priority': c.top_work_priority, 'top_other_priority': c.top_other_priority,
        'off_routine_flag': c.off_routine_flag, 'off_routine_reason': c.off_routine_reason,
        'project_type_this_week': c.project_type_this_week, 'day_meds': c.day_meds,
        'comments': c.comments
    } for c in Calendar.query.all()]
    data['board'] = [{'text': b.text} for b in BoardItem.query.all()]
    data['chains'] = [{
        'chain_id': c.chain_id, 'thread_id': c.thread_id,
        'chain_start_date': str(c.chain_start_date), 'chain_end_date': str(c.chain_end_date),
        'duration': c.duration, 'end_reason': c.end_reason
    } for c in Chain.query.all()]
    return json.dumps(data, indent=2, ensure_ascii=False)

def restore_from_json(json_content):
    try:
        data = json.loads(json_content)
        db.session.query(Square).delete()
        db.session.query(Chain).delete()
        db.session.query(BoardItem).delete()
        db.session.query(Calendar).delete()
        db.session.query(Thread).delete()
        db.session.commit()
        
        for t in data.get('threads', []):
            dt = datetime.datetime.strptime(t['created_at'], '%Y-%m-%d').date()
            closed = datetime.datetime.strptime(t['closed_date'], '%Y-%m-%d').date() if t.get('closed_date') else None
            th = Thread(
                thread_id=t['thread_id'], thread_name=t['thread_name'], category=t['category'],
                status=t['status'], rank=t['rank'], created_at=dt, 
                created_at_40k=t.get('created_at_40k'), closed_date=closed, 
                sub_category=t.get('sub_category'), type=t.get('type'), 
                cadence=t.get('cadence'), thread_name_redacted=t.get('thread_name_redacted')
            )
            db.session.add(th)
        db.session.commit() 
        
        for s in data.get('squares', []):
            d_date = datetime.datetime.strptime(s['period'], '%Y-%m-%d').date()
            sq = Square(
                square_id=s['square_id'], thread_id=s['thread_id'], period=d_date,
                status=s['status'], chain_id=None,
                chain_start=s.get('chain_start', False),
                chain_end=s.get('chain_end', False), 
                chain_end_reason=s.get('chain_end_reason', "")
            )
            db.session.add(sq)
            
        for c in data.get('calendar', []):
            d_date = datetime.datetime.strptime(c['actual_date'], '%Y-%m-%d').date()
            cal = Calendar(
                actual_date=d_date, date_40k=c.get('date_40k'), week_40k=c.get('week_40k'),
                comments=c.get('comments'), top_work_priority=c.get('top_work_priority'),
                top_other_priority=c.get('top_other_priority'), 
                project_type_this_week=c.get('project_type_this_week'),
                day_meds=c.get('day_meds', False), 
                off_routine_flag=c.get('off_routine_flag', False),
                off_routine_reason=c.get('off_routine_reason', "")
            )
            db.session.add(cal)
            
        for b in data.get('board', []):
            db.session.add(BoardItem(text=b['text']))
            
        db.session.commit()
        
        active_threads = Thread.query.all()
        for th in active_threads:
            recalculate_chains(th.thread_id)
            
        return True, "Відновлено успішно."
    except Exception as e:
        return False, str(e)

def send_scheduled_backup():
    try:
        with app.app_context():
            admins = BotUser.query.filter_by(role='admin').all()
            if not admins: return
            
            backup_content = create_full_backup_json()
            timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M')
            filename = f"backup_{timestamp}.json"
            
            for admin in admins:
                bot.send_document(admin.chat_id, backup_content.encode('utf-8'), visible_file_name=filename, caption=f"📦 Full Backup (JSON)")
    except Exception as e:
        print(f"Backup failed: {e}")

# --- BOT ---
if bot:
    @bot.message_handler(commands=['start'])
    def send_welcome(message):
        bot.reply_to(message, "Enter your password:")

    @bot.message_handler(commands=['logout'])
    def handle_logout(message):
        with app.app_context():
            user = db.session.get(BotUser, message.chat.id)
            if user:
                db.session.delete(user)
                db.session.commit()
                bot.reply_to(message, "ok")

    @bot.message_handler(content_types=['document'])
    def handle_docs(message):
        with app.app_context():
            user = db.session.get(BotUser, message.chat.id)
            if not user or user.role != "admin": return
            
        try:
            file_name = message.document.file_name
            if not file_name.endswith('.json'):
                bot.reply_to(message, "❌ I need .json file")
                return
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            json_content = downloaded_file.decode('utf-8')
            bot.reply_to(message, "⏳ restoring...")
            with app.app_context():
                success, msg = restore_from_json(json_content)
            if success:
                bot.reply_to(message, "✅ Success.")
            else:
                bot.reply_to(message, f"❌ Error: {msg}")
        except Exception as e:
            bot.reply_to(message, f"Error: {e}")

    @bot.message_handler(func=lambda message: True)
    def handle_all_messages(message):
        chat_id = message.chat.id
        txt = message.text.strip()
        
        with app.app_context():
            user = db.session.get(BotUser, chat_id)
            
            if not user:
                pwd_hash = hashlib.sha256(txt.encode()).hexdigest()
                if pwd_hash == HASH_USER:
                    db.session.add(BotUser(chat_id=chat_id, role="user"))
                    db.session.commit()
                    bot.reply_to(message, "✅ User Mode.")
                elif pwd_hash == HASH_ADMIN:
                    db.session.add(BotUser(chat_id=chat_id, role="admin"))
                    db.session.commit()
                    bot.reply_to(message, "👨‍💻 Admin Mode.")
                else: 
                    bot.reply_to(message, "❌ wrong password.")
                return
            
            user_role = user.role

            if user_role == "user":
                if txt.startswith('/del'):
                    parts = txt.split()
                    if len(parts) > 1 and parts[1].isdigit():
                        item = db.session.get(BoardItem, int(parts[1]))
                        if item:
                            db.session.delete(item)
                            db.session.commit()
                            bot.reply_to(message, "🗑 ok.")
                elif txt == "/list":
                    items = BoardItem.query.order_by(BoardItem.id.desc()).all()
                    msg = "\n".join([f"{item.id}. {item.text}" for item in items]) if items else "Empty."
                    bot.reply_to(message, msg)
                elif txt.startswith("/b "):
                    note = txt[3:].strip()
                    db.session.add(BoardItem(text=note))
                    db.session.commit()
                    bot.reply_to(message, "📌 added.")
                else:
                    try:
                        cal = ensure_calendar_entry(date.today())
                        timestamp = datetime.datetime.now().strftime("%H:%M")
                        entry = f"[{timestamp}] {txt}"
                        if cal.comments: cal.comments += "\n" + entry
                        else: cal.comments = entry
                        db.session.commit()
                        bot.reply_to(message, "🐦 saved.")
                    except Exception as e:
                        bot.reply_to(message, f"DB Error: {e}")
                    
            elif user_role == "admin":
                if txt == "/backup":
                    send_scheduled_backup()
                else:
                    bot.reply_to(message, "bro, where is json")
                    
# --- REQUEST BOT LOGIC ---
if request_bot:
    @request_bot.message_handler(commands=['start', 'help'])
    def req_send_welcome(message):
        request_bot.reply_to(message, "Hello! Write your requests here. \n\nTo get all requests as a list, type /list\nTo clear the list, type /clear")

    @request_bot.message_handler(commands=['list'])
    def req_list_requests(message):
        with app.app_context():
            reqs = PartnerRequest.query.order_by(PartnerRequest.id.asc()).all()
            if not reqs:
                request_bot.reply_to(message, "📭 The request list is currently empty.")
                return
            
            msg = "📝 <b>List of requests:</b>\n\n"
            for i, r in enumerate(reqs, 1):
                msg += f"{i}. {r.text}\n"
            
            request_bot.reply_to(message, msg, parse_mode="HTML")

    @request_bot.message_handler(commands=['clear'])
    def req_clear_requests(message):
        with app.app_context():
            PartnerRequest.query.delete()
            db.session.commit()
            request_bot.reply_to(message, "🗑 The list has been successfully cleared.")

    @request_bot.message_handler(func=lambda message: True)
    def req_add_request(message):
        txt = message.text.strip()
        with app.app_context():
            new_req = PartnerRequest(text=txt)
            db.session.add(new_req)
            db.session.commit()
        request_bot.reply_to(message, "✅ Added to the list!")

def run_bot_thread():
    if bot:
        try:
            print("Main Bot polling started...")
            bot.polling(none_stop=True)
        except Exception as e:
            print(f"Main Bot crash: {e}")

def run_request_bot_thread():
    if request_bot:
        try:
            print("Request Bot polling started...")
            request_bot.polling(none_stop=True)
        except Exception as e:
            print(f"Request Bot crash: {e}")

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated_function

@app.route('/api/login', methods=['POST'])
def api_login():
    pwd = request.json.get('password', '')
    if hashlib.sha256(pwd.encode()).hexdigest() == HASH_WEB:
        session['logged_in'] = True
        return jsonify({'success': True})
    return jsonify({'success': False})

@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.pop('logged_in', None)
    return jsonify({'success': True})

@app.route('/')
def index():
    try:
        today = date.today()
        cal = ensure_calendar_entry(today)
        
        recent_cals = Calendar.query.filter(
            Calendar.comments != "", 
            Calendar.comments.is_not(None)
        ).order_by(Calendar.actual_date.desc()).limit(10).all()
        
        global_parsed_comments = []
        for c in recent_cals:
            lines = [line for line in c.comments.split('\n') if line.strip()]
            day_comments = []
            for line in lines:
                if line.startswith('[') and ']' in line:
                    end_bracket = line.find(']')
                    time_str = line[1:end_bracket]
                    text_str = line[end_bracket+1:].strip()
                    day_comments.append({'date': c.actual_date.strftime('%Y-%m-%d'), 'time': time_str, 'text': text_str})
                else:
                    day_comments.append({'date': c.actual_date.strftime('%Y-%m-%d'), 'time': '', 'text': line})
            
            day_comments.reverse()
            global_parsed_comments.extend(day_comments)
            
            if len(global_parsed_comments) >= 5:
                break
                
        parsed_comments = global_parsed_comments[:5]

        board_items = BoardItem.query.order_by(BoardItem.id.desc()).all()
        board_data = [{'id': b.id, 'text': b.text} for b in board_items]

        ctx = {
            'top_work': cal.top_work_priority or "",
            'top_other': cal.top_other_priority or "",
            'project': cal.project_type_this_week or "",
            'meds': cal.day_meds,
            'off_routine': cal.off_routine_flag,
            'off_reason': cal.off_routine_reason or "",
            'comment_list': parsed_comments,
            'board_data': board_data,
            'date_40k': cal.date_40k,
            'week_40k': cal.week_40k
        }

        categories = ['work', 'maintenance', 'family', 'self care']
        threads = Thread.query.filter(Thread.status == 'active').order_by(Thread.rank.desc()).all()
        grouped_threads = {c: [] for c in categories}
        
        age = today.year - 1992 - ((today.month, today.day) < (2, 16))
        bday = date(1992 + age, 2, 16)
        delta_today = (today - bday).days
        current_week_num = (delta_today // 7) + 1
        
        start_of_current_week = bday + timedelta(days=(current_week_num - 1) * 7)
        
        start_date = start_of_current_week - timedelta(days=21)
        end_date = start_of_current_week + timedelta(days=6)
        
        week_headers = []
        for i in range(4):
            w_start = start_date + timedelta(days=i*7)
            _, w_str = get_40k_data(w_start)
            week_headers.append(w_str)
        
        off_routine_days = {c.actual_date: True for c in Calendar.query.filter(Calendar.off_routine_flag == True).all()}
        all_squares = Square.query.filter(Square.period >= start_date, Square.period <= end_date).all()
        sq_map = {(s.thread_id, s.period): s for s in all_squares}
        
        for th in threads:
            cat = th.category if th.category in grouped_threads else 'maintenance'
            days = []
            
            for i in range(28):
                curr = start_date + timedelta(days=i)
                sq = sq_map.get((th.thread_id, curr))
                status = sq.status if sq else 'empty'
                is_off = off_routine_days.get(curr, False)
                is_fulfilled = is_day_fulfilled(th, curr, sq_map)
                days.append({
                    'date': curr.strftime('%Y-%m-%d'), 
                    'is_today': (curr == today), 
                    'status': status, 
                    'is_off_routine': is_off, 
                    'is_fulfilled': is_fulfilled, 
                    'is_padding': False,
                    'miss_reason': sq.chain_end_reason if sq else ""
                })
            weeks = [days[i:i + 7] for i in range(0, len(days), 7)]
            grouped_threads[cat].append({'info': th, 'weeks': weeks})
            
        return render_template('dashboard.html', grouped_threads=grouped_threads, categories=categories, ctx=ctx, today_date=today.strftime('%Y-%m-%d'), week_headers=week_headers, is_auth=session.get('logged_in', False))
    except Exception as e: return f"CRITICAL ERROR: {str(e)}"

@app.route('/api/get_day_info', methods=['POST'])
def get_day_info():
    d_str = request.json.get('date')
    try:
        d_date = datetime.datetime.strptime(d_str, '%Y-%m-%d').date()
        cal = db.session.get(Calendar, d_date)
        if cal:
            return jsonify({
                'success': True,
                'comments': cal.comments or "",
                'work': cal.top_work_priority or "",
                'other': cal.top_other_priority or "",
                'project': cal.project_type_this_week or "",
                'meds': cal.day_meds,
                'off': cal.off_routine_flag,
                'off_reason': cal.off_routine_reason or ""
            })
        else:
            return jsonify({'success': True, 'comments': "No data for this day.", 'work':"", 'other':"", 'project':"", 'meds':False, 'off':False, 'off_reason':""})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/update_day_context', methods=['POST'])
@login_required
def update_day_context():
    data = request.json
    cal = ensure_calendar_entry(date.today())
    if 'top_work' in data: cal.top_work_priority = data['top_work']
    if 'top_other' in data: cal.top_other_priority = data['top_other']
    if 'project' in data: cal.project_type_this_week = data['project']
    if 'meds' in data: cal.day_meds = data['meds']
    if 'off_routine' in data: cal.off_routine_flag = data['off_routine']
    if 'off_reason' in data: cal.off_routine_reason = data['off_reason']
    if 'comments' in data and data['comments']:
        timestamp = datetime.datetime.now().strftime("%H:%M")
        new_entry = f"[{timestamp}] {data['comments']}"
        if cal.comments: cal.comments += "\n" + new_entry
        else: cal.comments = new_entry
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/toggle_status', methods=['POST'])
@login_required
def toggle_status():
    data = request.json
    t_id = data.get('thread_id')
    d_str = data.get('date')
    d_date = datetime.datetime.strptime(d_str, '%Y-%m-%d').date()
    sq_id = f"{t_id}_{d_str}"
    sq = db.session.get(Square, sq_id)
    if not sq:
        sq = Square(square_id=sq_id, thread_id=t_id, period=d_date)
        db.session.add(sq)
    sq.status = data.get('status')
    sq.chain_end_reason = data.get('miss_reason', '') if sq.status == 'miss' else ""
    db.session.commit()
    recalculate_chains(t_id)
    return jsonify({'success': True})

@app.route('/api/add_thread', methods=['POST'])
@login_required
def add_thread():
    try:
        data = request.json
        max_rank = db.session.query(func.max(Thread.rank)).scalar() or 0
        today = date.today()
        new_th = Thread(
            thread_name=data.get('name'), thread_name_redacted=data.get('redacted', ''),
            category=data.get('category'), sub_category=data.get('sub_category', ''),
            type=data.get('type', 'perpetual'), cadence=data.get('cadence', 'daily'),
            status='active', rank=max_rank + 1, created_at=today, created_at_40k=get_40k_data(today)[0]
        )
        db.session.add(new_th)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e: return jsonify({'success': False, 'error': str(e)})

@app.route('/api/delete_thread', methods=['POST'])
@login_required
def delete_thread():
    t_id = request.json.get('id')
    thread = db.session.get(Thread, t_id)
    if thread:
        thread.status = 'deleted'
        thread.closed_date = date.today()
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False})

@app.route('/api/edit_thread', methods=['POST'])
@login_required
def edit_thread():
    try:
        data = request.json
        t_id = data.get('id')
        thread = db.session.get(Thread, t_id)
        
        if thread:
            thread.thread_name = data.get('name')
            thread.thread_name_redacted = data.get('redacted', '')
            thread.sub_category = data.get('sub_category', '')
            thread.type = data.get('type', 'perpetual')
            thread.cadence = data.get('cadence', 'daily')
            db.session.commit()
            return jsonify({'success': True})
            
        return jsonify({'success': False, 'error': 'Звичку не знайдено'})
    except Exception as e: 
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/move_thread', methods=['POST'])
@login_required
def move_thread():
    t_id = request.json.get('id')
    direction = request.json.get('direction')
    thread = db.session.get(Thread, t_id)
    if not thread: return jsonify({'success': False})
    if direction == 'up':
        neighbor = Thread.query.filter(Thread.rank > thread.rank, Thread.status == 'active').order_by(Thread.rank.asc()).first()
    else:
        neighbor = Thread.query.filter(Thread.rank < thread.rank, Thread.status == 'active').order_by(Thread.rank.desc()).first()
    if neighbor:
        thread.rank, neighbor.rank = neighbor.rank, thread.rank
        db.session.commit()
    return jsonify({'success': True})

# --- STARTUP LOGIC ---
with app.app_context():
    db.create_all()
    scheduler.init_app(app)
    scheduler.start()
    if not scheduler.get_job('auto_backup'):
        scheduler.add_job(id='auto_backup', func=send_scheduled_backup, trigger='cron', hour=23, minute=59)

if not any(t.name == "BotThread" for t in threading.enumerate()):
    t = threading.Thread(target=run_bot_thread, name="BotThread")
    t.daemon = True
    t.start()

if not any(t.name == "RequestBotThread" for t in threading.enumerate()):
    t2 = threading.Thread(target=run_request_bot_thread, name="RequestBotThread")
    t2.daemon = True
    t2.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=False, use_reloader=False)
