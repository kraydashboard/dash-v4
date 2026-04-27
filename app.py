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
from zoneinfo import ZoneInfo

app = Flask(__name__)
# --- CONFIG ---
app.secret_key = os.environ.get("SECRET_KEY", "sdfeergrthbwefsDSlvsrgpsesvaflsvkvl")
REQUEST_BOT_TOKEN = os.environ.get("REQUEST_BOT_TOKEN", "")
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
    time_of_day = db.Column(db.String(20), default='unspecified')

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
    created_at = db.Column(db.DateTime, default=lambda: datetime.datetime.now(ZoneInfo("America/Chicago")))

class IntentEntry(db.Model):
    __tablename__ = 'intent_entries'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, default=1) 
    entry_date = db.Column(db.Date, nullable=False)
    horizon = db.Column(db.String(20))
    content = db.Column(db.Text)
    notes = db.Column(db.Text, default="")
    plan = db.Column(db.Boolean, default=False)

class ResilienceEntry(db.Model):
    __tablename__ = 'resilience_entries'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, default=1) 
    entry_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='baseline')
    content = db.Column(db.Text)
    notes = db.Column(db.Text, default="")
    
class PartnerRequest(db.Model):
    __tablename__ = 'partner_requests'
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.datetime.now(ZoneInfo("America/Chicago")))

def get_week_data(d_obj):
    year, week, day = d_obj.isocalendar()
    return f"{year}-W{week}-{day}", f"Week {week}"

def ensure_calendar_entry(d_date):
    entry = db.session.get(Calendar, d_date)
    if not entry:
        date_str, week_str = get_week_data(d_date)
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
    if not thread.cadence or thread.cadence == 'daily': 
        return False
        
    target_hits = 1
    start_date = None
    end_date = None
    
    if thread.cadence in ['3x_week', 'weekly']:
        start_date = date_obj - timedelta(days=date_obj.weekday())
        end_date = start_date + timedelta(days=6)
        if thread.cadence == '3x_week': 
            target_hits = 3
    elif thread.cadence == 'monthly':
        start_date = date_obj.replace(day=1)
        next_month = (start_date + timedelta(days=32)).replace(day=1)
        end_date = next_month - timedelta(days=1)
    elif thread.cadence == 'quarterly':
        quarter = (date_obj.month - 1) // 3 + 1
        start_month = (quarter - 1) * 3 + 1
        start_date = date(date_obj.year, start_month, 1)
        if start_month + 3 > 12: 
            end_date = date(date_obj.year, 12, 31)
        else: 
            end_date = date(date_obj.year, start_month + 3, 1) - timedelta(days=1)
    elif thread.cadence == 'yearly':
        start_date = date(date_obj.year, 1, 1)
        end_date = date(date_obj.year, 12, 31)
    else: 
        return False

    hits_count = 0
    delta = (end_date - start_date).days
    for i in range(delta + 1):
        check_date = start_date + timedelta(days=i)
        sq = squares_map.get((thread.thread_id, check_date))
        if sq and sq.status == 'hit': 
            hits_count += 1
    
    current_sq = squares_map.get((thread.thread_id, date_obj))
    is_currently_hit = (current_sq and current_sq.status == 'hit')
    
    if hits_count >= target_hits and not is_currently_hit: 
        return True
        
    return False
        
def create_full_backup_json():
    data = {}
    data['threads'] = [{
        'thread_id': t.thread_id, 'thread_name': t.thread_name, 'category': t.category,
        'status': t.status, 'rank': t.rank, 
        'created_at': t.created_at.strftime('%Y-%m-%d') if t.created_at else None,
        'created_at_40k': t.created_at_40k, 'closed_date': t.closed_date.strftime('%Y-%m-%d') if t.closed_date else None,
        'sub_category': t.sub_category, 'type': t.type, 'cadence': t.cadence,
        'thread_name_redacted': t.thread_name_redacted,
        'time_of_day': t.time_of_day
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
    
    data['board'] = [{
        'id': b.id, 'text': b.text, 
        'created_at': b.created_at.isoformat() if b.created_at else None
    } for b in BoardItem.query.all()]
    
    data['chains'] = [{
        'chain_id': c.chain_id, 'thread_id': c.thread_id,
        'chain_start_date': c.chain_start_date.strftime('%Y-%m-%d') if c.chain_start_date else None, 
        'chain_end_date': c.chain_end_date.strftime('%Y-%m-%d') if c.chain_end_date else None,
        'duration': c.duration, 'end_reason': c.end_reason
    } for c in Chain.query.all()]
    
    data['intent_entries'] = [{
        'id': e.id, 'user_id': e.user_id, 'entry_date': str(e.entry_date),
        'horizon': e.horizon, 'content': e.content, 'notes': e.notes, 'plan': e.plan
    } for e in IntentEntry.query.all()]
    
    data['resilience_entries'] = [{
        'id': e.id, 'user_id': e.user_id, 'entry_date': str(e.entry_date),
        'status': e.status, 'content': e.content, 'notes': e.notes
    } for e in ResilienceEntry.query.all()]

    data['bot_users'] = [{
        'chat_id': u.chat_id, 'role': u.role
    } for u in BotUser.query.all()]
    
    data['partner_requests'] = [{
        'id': r.id, 'text': r.text, 
        'created_at': r.created_at.isoformat() if r.created_at else None
    } for r in PartnerRequest.query.all()]

    return json.dumps(data, indent=2, ensure_ascii=False)   

def restore_from_json(json_content):
    try:
        data = json.loads(json_content)
        
        db.session.query(Square).delete()
        db.session.query(Chain).delete()
        db.session.query(BoardItem).delete()
        db.session.query(Calendar).delete()
        db.session.query(Thread).delete()
        db.session.query(IntentEntry).delete()
        db.session.query(ResilienceEntry).delete() 
        db.session.query(BotUser).delete()         
        db.session.query(PartnerRequest).delete()  
        
        for t in data.get('threads', []):
            dt = datetime.datetime.strptime(t['created_at'], '%Y-%m-%d').date() if t.get('created_at') else None
            closed = datetime.datetime.strptime(t['closed_date'], '%Y-%m-%d').date() if t.get('closed_date') else None
            th = Thread(
                thread_id=t['thread_id'], thread_name=t['thread_name'], category=t['category'],
                status=t['status'], rank=t['rank'], created_at=dt, 
                created_at_40k=t.get('created_at_40k'), closed_date=closed, 
                sub_category=t.get('sub_category'), type=t.get('type'), 
                cadence=t.get('cadence'), thread_name_redacted=t.get('thread_name_redacted'),
                time_of_day=t.get('time_of_day', 'unspecified')
            )
            db.session.add(th)
            
        for c in data.get('chains', []):
            start_date = datetime.datetime.strptime(c['chain_start_date'], '%Y-%m-%d').date() if c.get('chain_start_date') else None
            end_date = datetime.datetime.strptime(c['chain_end_date'], '%Y-%m-%d').date() if c.get('chain_end_date') else None
            chain = Chain(
                chain_id=c['chain_id'], thread_id=c['thread_id'],
                chain_start_date=start_date, chain_end_date=end_date,
                duration=c['duration'], end_reason=c.get('end_reason', "")
            )
            db.session.add(chain)

        for s in data.get('squares', []):
            d_date = datetime.datetime.strptime(s['period'], '%Y-%m-%d').date()
            sq = Square(
                square_id=s['square_id'], thread_id=s['thread_id'], period=d_date,
                status=s['status'], chain_id=s.get('chain_id'), 
                chain_start=s.get('chain_start', False),
                chain_end=s.get('chain_end', False), 
                chain_end_reason=s.get('chain_end_reason', "")
            )
            db.session.add(sq)
        
        for e in data.get('intent_entries', []):
            d_date = datetime.datetime.strptime(e['entry_date'], '%Y-%m-%d').date()
            db.session.add(IntentEntry(
                id=e.get('id'), user_id=e.get('user_id', 1), entry_date=d_date,
                horizon=e.get('horizon'), content=e.get('content'),
                notes=e.get('notes', ''), plan=e.get('plan') or False
            ))
            
        for e in data.get('resilience_entries', []):
            d_date = datetime.datetime.strptime(e['entry_date'], '%Y-%m-%d').date()
            db.session.add(ResilienceEntry(
                id=e.get('id'), user_id=e.get('user_id', 1), entry_date=d_date,
                status=e.get('status', 'baseline'), content=e.get('content', ''),
                notes=e.get('notes', '')
            ))

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
            c_at = datetime.datetime.fromisoformat(b['created_at']) if b.get('created_at') else datetime.datetime.now(ZoneInfo("America/Chicago"))
            db.session.add(BoardItem(id=b.get('id'), text=b['text'], created_at=c_at))
            
        for u in data.get('bot_users', []):
            db.session.add(BotUser(chat_id=u['chat_id'], role=u['role']))
            
        for r in data.get('partner_requests', []):
            c_at = datetime.datetime.fromisoformat(r['created_at']) if r.get('created_at') else datetime.datetime.now(ZoneInfo("America/Chicago"))
            db.session.add(PartnerRequest(id=r.get('id'), text=r['text'], created_at=c_at))
            
        db.session.commit()
        
        if db.engine.name == 'postgresql':
            tables_to_sync = [
                ('threads', 'thread_id'),
                ('board_items', 'id'),
                ('intent_entries', 'id'),
                ('resilience_entries', 'id'),
                ('partner_requests', 'id')
            ]
            for table, pk in tables_to_sync:
                try:
                    query = f"SELECT setval(pg_get_serial_sequence('{table}', '{pk}'), COALESCE((SELECT MAX({pk}) FROM {table}), 1))"
                    db.session.execute(db.text(query))
                except Exception as sync_e:
                    print(f"Failed to sync sequence for {table}: {sync_e}")
            db.session.commit()

        if not data.get('chains'):
            active_threads = Thread.query.all()
            for th in active_threads:
                recalculate_chains(th.thread_id)
            
        return True, "Success."
    except Exception as e:
        db.session.rollback()
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
                if request_bot:
                    request_bot.send_document(admin.chat_id, backup_content.encode('utf-8'), visible_file_name=filename, caption=f"📦 Full Backup (JSON)")
    except Exception as e:
        print(f"Backup failed: {e}")
            
# --- REQUEST BOT LOGIC ---
if request_bot:
    @request_bot.message_handler(commands=['start', 'help'])
    def req_send_welcome(message):
        request_bot.reply_to(message, "Hello! Write your requests here. \n\nTo get all requests as a list, type /list\nTo clear the list, type /clear\n\n(Enter password for Admin Mode)")

    @request_bot.message_handler(commands=['logout'])
    def handle_logout(message):
        with app.app_context():
            user = db.session.get(BotUser, message.chat.id)
            if user:
                db.session.delete(user)
                db.session.commit()
                request_bot.reply_to(message, "ok")

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

    @request_bot.message_handler(commands=['backup'])
    def handle_backup(message):
        with app.app_context():
            user = db.session.get(BotUser, message.chat.id)
            if user and user.role == "admin":
                send_scheduled_backup()
            else:
                request_bot.reply_to(message, "bro, where is json")

    @request_bot.message_handler(content_types=['document'])
    def handle_docs(message):
        with app.app_context():
            user = db.session.get(BotUser, message.chat.id)
            if not user or user.role != "admin": return
            
        try:
            file_name = message.document.file_name
            if not file_name.endswith('.json'):
                request_bot.reply_to(message, "❌ I need .json file")
                return
            file_info = request_bot.get_file(message.document.file_id)
            downloaded_file = request_bot.download_file(file_info.file_path)
            json_content = downloaded_file.decode('utf-8')
            request_bot.reply_to(message, "⏳ restoring...")
            with app.app_context():
                success, msg = restore_from_json(json_content)
            if success:
                request_bot.reply_to(message, "✅ Success.")
            else:
                request_bot.reply_to(message, f"❌ Error: {msg}")
        except Exception as e:
            request_bot.reply_to(message, f"Error: {e}")

    @request_bot.message_handler(func=lambda message: True)
    def handle_all_text(message):
        chat_id = message.chat.id
        txt = message.text.strip()
        
        with app.app_context():
            pwd_hash = hashlib.sha256(txt.encode()).hexdigest()
            if pwd_hash == HASH_ADMIN:
                user = db.session.get(BotUser, chat_id)
                if not user:
                    db.session.add(BotUser(chat_id=chat_id, role="admin"))
                    db.session.commit()
                request_bot.reply_to(message, "👨‍💻 Admin Mode.")
                return

            new_req = PartnerRequest(text=txt)
            db.session.add(new_req)
            db.session.commit()
            
        request_bot.reply_to(message, "✅ Added to the list!")

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
        week_offset = request.args.get('offset', 0, type=int)
        
        today = datetime.datetime.now(ZoneInfo("America/Chicago")).date()
        start_of_current_week = today - timedelta(days=today.weekday())
        
        base_week = start_of_current_week + timedelta(weeks=week_offset)
        
        start_date = base_week - timedelta(days=35)
        end_date = base_week + timedelta(days=6)
        cal = ensure_calendar_entry(today)
        
        recent_cals = Calendar.query.filter(
            Calendar.comments != "", 
            Calendar.comments.is_not(None)
        ).order_by(Calendar.actual_date.desc()).limit(10).all()
        
        global_parsed_comments = []
        for c in recent_cals:
            lines = [line for line in c.comments.split('\n') if line.strip()]
            day_comments = []
            
            current_comment = None
            
            for line in lines:
                if line.startswith('[') and ']' in line:
                    if current_comment:
                        day_comments.append(current_comment)
                    
                    end_bracket = line.find(']')
                    time_str = line[1:end_bracket]
                    text_str = line[end_bracket+1:].strip()
                    
                    current_comment = {
                        'date': c.actual_date.strftime('%Y-%m-%d'), 
                        'time': time_str, 
                        'text': text_str
                    }
                else:
                    if current_comment:
                        current_comment['text'] += "\n" + line
                    else:
                        current_comment = {'date': c.actual_date.strftime('%Y-%m-%d'), 'time': '', 'text': line}
            
            if current_comment:
                day_comments.append(current_comment)
                
            day_comments.reverse()
            global_parsed_comments.extend(day_comments)
                
        parsed_comments = global_parsed_comments

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

        categories = ['work', 'scaffolding', 'family', 'quests', 'self care']
        threads = Thread.query.filter(Thread.status == 'active').order_by(Thread.rank.desc()).all()
        grouped_threads = {c: [] for c in categories}
        
        week_headers = []
        for i in range(6):
            w_start = start_date + timedelta(days=i*7)
            _, w_str = get_week_data(w_start)
            week_headers.append(w_str)
        
        off_routine_days = {c.actual_date: True for c in Calendar.query.filter(Calendar.off_routine_flag == True).all()}
        all_squares = Square.query.filter(Square.period >= start_date, Square.period <= end_date).all()
        sq_map = {(s.thread_id, s.period): s for s in all_squares}
        
        for th in threads:
            cat = th.category if th.category in grouped_threads else 'scaffolding'
            days = []
            
            for i in range(42):
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
            
        return render_template(
            'dashboard.html', 
            grouped_threads=grouped_threads, 
            categories=categories, 
            ctx=ctx, 
            today_date=today.strftime('%Y-%m-%d'), 
            week_headers=week_headers, 
            is_auth=session.get('logged_in', False),
            current_offset=week_offset 
        )
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
    cal = ensure_calendar_entry(datetime.datetime.now(ZoneInfo("America/Chicago")).date())
    if 'top_work' in data: cal.top_work_priority = data['top_work']
    if 'top_other' in data: cal.top_other_priority = data['top_other']
    if 'project' in data: cal.project_type_this_week = data['project']
    if 'meds' in data: cal.day_meds = data['meds']
    if 'off_routine' in data: cal.off_routine_flag = data['off_routine']
    if 'off_reason' in data: cal.off_routine_reason = data['off_reason']
    if 'comments' in data and data['comments']:
        timestamp = datetime.datetime.now(ZoneInfo("America/Chicago")).strftime("%H:%M")
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
    sq.chain_end_reason = data.get('miss_reason', '')
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
            time_of_day=data.get('time_of_day', 'unspecified'),
            status='active', rank=max_rank + 1, created_at=today, created_at_40k=get_week_data(today)[0]
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
            thread.time_of_day = data.get('time_of_day', 'unspecified')
            db.session.commit()
            return jsonify({'success': True})
            
        return jsonify({'success': False, 'error': 'Not found'})
    except Exception as e: 
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/move_thread', methods=['POST'])
@login_required
def move_thread():
    data = request.json
    t_id = data.get('id')
    direction = data.get('direction')
    mode = data.get('mode', 'type')
    
    thread = db.session.get(Thread, t_id)
    if not thread: return jsonify({'success': False})
    
    query = Thread.query.filter(Thread.status == 'active')
    
    if mode == 'type':
        query = query.filter(Thread.category == thread.category)
    elif mode == 'time':
        query = query.filter(Thread.time_of_day == thread.time_of_day)
    
    if direction == 'up':
        neighbor = query.filter(Thread.rank > thread.rank).order_by(Thread.rank.asc()).first()
    else:
        neighbor = query.filter(Thread.rank < thread.rank).order_by(Thread.rank.desc()).first()
        
    if neighbor:
        thread.rank, neighbor.rank = neighbor.rank, thread.rank
        db.session.commit()
        
    return jsonify({'success': True})
@app.route('/calendar')
@login_required
def calendar():
    return render_template('m_page.html')

# --- STARTUP LOGIC ---
with app.app_context():
    db.create_all()
    
    try:
        db.session.execute(db.text("ALTER TABLE threads ADD COLUMN time_of_day VARCHAR(20) DEFAULT 'unspecified'"))
        db.session.commit()
    except Exception:
        db.session.rollback()
    
    try:
        db.session.execute(db.text("ALTER TABLE intent_entries ADD COLUMN notes TEXT DEFAULT ''"))
        db.session.commit()
    except Exception:
        db.session.rollback()

    try:
        db.session.execute(db.text("ALTER TABLE intent_entries ADD COLUMN plan BOOLEAN DEFAULT FALSE"))
        db.session.commit()
    except Exception:
        db.session.rollback()

    if db.engine.name == 'postgresql':
        try:
            db.session.execute(db.text("SELECT setval(pg_get_serial_sequence('threads', 'thread_id'), COALESCE((SELECT MAX(thread_id) FROM threads), 1))"))
            db.session.commit()
            print("PostgreSQL sequence synced.")
        except Exception as e:
            db.session.rollback()
            print(f"Sequence sync error: {e}")

    scheduler.init_app(app)
    scheduler.start()
    if not scheduler.get_job('auto_backup'):
        scheduler.add_job(id='auto_backup', func=send_scheduled_backup, trigger='cron', hour=23, minute=59)

def run_request_bot_thread():
    if request_bot:
        try:
            print("Request Bot polling started...")
            request_bot.polling(none_stop=True)
        except Exception as e:
            print(f"Request Bot crash: {e}")

if not any(t.name == "RequestBotThread" for t in threading.enumerate()):
    t2 = threading.Thread(target=run_request_bot_thread, name="RequestBotThread")
    t2.daemon = True
    t2.start()

@app.route('/api/calendar/<cal_type>/<int:year>/<int:month>', methods=['GET'])
@login_required
def get_calendar_data(cal_type, year, month):
    start_date = date(year, month + 1, 1)
    if month == 11:
        end_date = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = date(year, month + 2, 1) - timedelta(days=1)

    data = {}
    if cal_type == 'resilience':
        entries = ResilienceEntry.query.filter(ResilienceEntry.entry_date >= start_date, ResilienceEntry.entry_date <= end_date).all()
        for e in entries:
            data[e.entry_date.day] = {"header": e.content or "", "notes": e.notes or "", "status": e.status or "baseline"}
    else:
        entries = IntentEntry.query.filter(IntentEntry.entry_date >= start_date, IntentEntry.entry_date <= end_date).all()
        for e in entries:
            db_horizon = e.horizon.strip() if e.horizon and e.horizon.strip() else "survival"
            data[e.entry_date.day] = {"header": e.content or "", "notes": e.notes or "", "horizon": db_horizon, "plan": e.plan or False}
    
    return jsonify(data)

@app.route('/api/calendar/<cal_type>/save', methods=['POST'])
@login_required
def save_calendar_data(cal_type):
    req = request.json
    d_date = datetime.datetime.strptime(req.get('date'), '%Y-%m-%d').date()
    
    if cal_type == 'resilience':
        ResilienceEntry.query.filter_by(entry_date=d_date).delete()
        db.session.add(ResilienceEntry(
            entry_date=d_date, 
            status=req.get('status', 'baseline'),
            content=req.get('header', ''),
            notes=req.get('notes', '')
        ))
    else:
        IntentEntry.query.filter_by(entry_date=d_date).delete()
        db.session.add(IntentEntry(
            entry_date=d_date, 
            horizon=req.get('horizon', 'survival'),
            content=req.get('header', ''),
            notes=req.get('notes', ''),
            plan=req.get('plan', False)
        ))
        
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/aggregate/<int:year>', methods=['GET'])
@login_required
def get_aggregate_data(year):
    start_date = date(year, 1, 1)
    end_date = date(year, 12, 31)

    counts = db.session.query(
        Thread.category,
        Square.period,
        func.count(Square.square_id)
    ).join(Square, Thread.thread_id == Square.thread_id)\
     .filter(Square.period >= start_date, Square.period <= end_date, Square.status == 'hit')\
     .group_by(Thread.category, Square.period).all()

    target_cats = ['work', 'quests', 'self care']
    data = {cat: {} for cat in target_cats}

    for cat, period, count in counts:
        cat_lower = cat.lower() if cat else 'scaffolding'
        if cat_lower in data:
            data[cat_lower][period.strftime('%Y-%m-%d')] = count

    intent_entries = IntentEntry.query.filter(
        IntentEntry.entry_date >= start_date,
        IntentEntry.entry_date <= end_date
    ).all()

    intent_data = {}
    for entry in intent_entries:
        if entry.content or entry.notes:
            intent_data[entry.entry_date.strftime('%Y-%m-%d')] = {
                'horizon': entry.horizon or 'survival',
                'plan': entry.plan or False
            }
            
    data['intentionality'] = intent_data

    return jsonify({'success': True, 'data': data, 'year': year})
@app.route('/api/delete_log', methods=['POST'])
@login_required
def delete_log():
    data = request.json
    d_str = data.get('date')
    time_str = data.get('time', '')
    text_to_delete = data.get('text', '').replace('\r\n', '\n').strip()

    try:
        d_date = datetime.datetime.strptime(d_str, '%Y-%m-%d').date()
        cal = db.session.get(Calendar, d_date)
        if cal and cal.comments:
            lines = [line for line in cal.comments.split('\n') if line.strip()]
            parsed = []
            current_entry = None

            for line in lines:
                if line.startswith('[') and ']' in line:
                    if current_entry:
                        parsed.append(current_entry)
                    end_idx = line.find(']')
                    current_entry = {'time': line[1:end_idx], 'text': line[end_idx+1:].strip(), 'raw': [line]}
                else:
                    if current_entry:
                        current_entry['text'] += '\n' + line
                        current_entry['raw'].append(line)
                    else:
                        current_entry = {'time': '', 'text': line, 'raw': [line]}

            if current_entry:
                parsed.append(current_entry)

            new_raw_lines = []
            deleted = False
            for p in parsed:
                if not deleted and p['time'] == time_str and p['text'].strip() == text_to_delete:
                    deleted = True 
                else:
                    new_raw_lines.extend(p['raw'])

            cal.comments = '\n'.join(new_raw_lines)
            db.session.commit()

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=False, use_reloader=False)
