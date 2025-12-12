import os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from flask_cors import CORS
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv
from functools import wraps
from collections import defaultdict
from threading import Thread
import smtplib
import ssl
import schedule
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-in-production')

# Get MongoDB URI from environment variable
MONGODB_URI = os.getenv('MONGODB_URI')
PORT = int(os.getenv('PORT', 5000))

# Check if MongoDB URI is provided
if not MONGODB_URI:
    print('❌ ERROR: MONGODB_URI environment variable is not set!')
    print('Please create a .env file with MONGODB_URI or set it in your environment')
    exit(1)

# MongoDB Connection
try:
    client = MongoClient(MONGODB_URI)
    db = client['learning-tracker']
    entries_collection = db['entries']
    users_collection = db['users']
    goals_collection = db['goals']
    # Test connection
    client.admin.command('ping')
    print('✅ MongoDB Connected')
except Exception as e:
    print(f'❌ MongoDB Connection Error: {e}')
    exit(1)

# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash('Please log in to access this page', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Helper function to get week start date
def get_week_start(date=None):
    if date is None:
        date = datetime.now()
    return date - timedelta(days=date.weekday())

# Authentication Routes

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Simple login page"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        
        if not username or len(username) < 2:
            flash('Username must be at least 2 characters', 'error')
            return render_template('login.html')
        
        # Check if user exists, if not create them
        user = users_collection.find_one({'username': username})
        if not user:
            users_collection.insert_one({
                'username': username,
                'createdAt': datetime.now(),
                'lastLogin': datetime.now()
            })
        else:
            users_collection.update_one(
                {'username': username},
                {'$set': {'lastLogin': datetime.now()}}
            )
        
        session['username'] = username
        flash(f'Welcome back, {username}!', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logout user"""
    username = session.get('username', 'User')
    session.clear()
    flash(f'Goodbye, {username}!', 'info')
    return redirect(url_for('login'))

# Main Application Routes

@app.route('/')
@login_required
def dashboard():
    """User's personal dashboard"""
    username = session.get('username')
    
    try:
        # Get user's entries
        all_entries = list(entries_collection.find({'username': username}).sort('date', -1))
        entries = []
        
        for entry in all_entries:
            entries.append({
                '_id': str(entry['_id']),
                'username': entry.get('username', ''),
                'date': entry.get('date', datetime.now()).isoformat() if isinstance(entry.get('date'), datetime) else str(entry.get('date', '')),
                'hours': entry.get('hours', 0),
                'notes': entry.get('notes', ''),
                'category': entry.get('category', 'General'),
                'status': entry.get('status', 'completed')
            })
        
        # Calculate personal stats
        total_entries = len(entries)
        total_hours = sum(entry.get('hours', 0) for entry in entries)
        
        # Category breakdown
        category_hours = defaultdict(float)
        for entry in entries:
            category_hours[entry.get('category', 'General')] += entry.get('hours', 0)
        
        # Weekly stats
        week_start = get_week_start()
        week_entries = [e for e in entries if datetime.fromisoformat(e['date']) >= week_start]
        weekly_hours = sum(e.get('hours', 0) for e in week_entries)
        
        # Get user's goals
        goals = list(goals_collection.find({'username': username}))
        goals_data = []
        for goal in goals:
            category = goal['category']
            target_hours = goal['targetHours']
            # Calculate actual hours for this category
            actual_hours = sum(e.get('hours', 0) for e in entries if e.get('category') == category)
            progress = min(100, int((actual_hours / target_hours) * 100)) if target_hours > 0 else 0
            
            goals_data.append({
                '_id': str(goal['_id']),
                'category': category,
                'targetHours': target_hours,
                'actualHours': round(actual_hours, 1),
                'progress': progress,
                'status': goal.get('status', 'in_progress')
            })
        
        stats = {
            'totalEntries': total_entries,
            'totalHours': round(total_hours, 1),
            'weeklyHours': round(weekly_hours, 1),
            'categoryBreakdown': dict(category_hours),
            'weeklyEntries': len(week_entries)
        }
        
        return render_template('dashboard.html', 
                             entries=entries, 
                             stats=stats, 
                             username=username,
                             goals=goals_data)
    except Exception as e:
        print(f"Error in dashboard route: {str(e)}")
        import traceback
        traceback.print_exc()
        return f"Error: {str(e)}", 500

@app.route('/add', methods=['POST'])
@login_required
def add_entry():
    """Add a new learning entry"""
    try:
        username = session.get('username')
        date_str = request.form.get('date')
        hours = request.form.get('hours')
        notes = request.form.get('notes', '').strip()
        category = request.form.get('category', 'General').strip()
        status = request.form.get('status', 'completed')
        
        # Validation
        if not date_str or not hours:
            flash('Date and hours are required', 'error')
            return redirect(url_for('dashboard'))
        
        # Parse and validate date
        date = datetime.fromisoformat(date_str)
        if date > datetime.now():
            flash('Date cannot be in the future', 'error')
            return redirect(url_for('dashboard'))
        
        # Validate hours
        hours = float(hours)
        if hours <= 0 or hours > 24:
            flash('Hours must be between 0 and 24', 'error')
            return redirect(url_for('dashboard'))
        
        # Create entry
        entry = {
            'username': username,
            'date': date,
            'hours': hours,
            'notes': notes,
            'category': category,
            'status': status,
            'createdAt': datetime.now()
        }
        
        entries_collection.insert_one(entry)
        flash('Learning entry added successfully!', 'success')
        return redirect(url_for('dashboard'))
    except Exception as e:
        print(f"Error adding entry: {str(e)}")
        flash(f'Error adding entry: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

@app.route('/delete/<entry_id>', methods=['POST'])
@login_required
def delete_entry(entry_id):
    """Delete an entry (only if it belongs to the user)"""
    try:
        username = session.get('username')
        result = entries_collection.find_one_and_delete({
            '_id': ObjectId(entry_id),
            'username': username  # Only delete if it's the user's entry
        })
        
        if result:
            flash('Entry deleted successfully', 'success')
        else:
            flash('Entry not found or you do not have permission to delete it', 'error')
        
        return redirect(url_for('dashboard'))
    except Exception as e:
        print(f"Error deleting entry: {str(e)}")
        flash(f'Error deleting entry: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

@app.route('/goals', methods=['GET', 'POST'])
@login_required
def goals():
    """Manage learning goals"""
    username = session.get('username')
    
    if request.method == 'POST':
        try:
            category = request.form.get('category', '').strip()
            target_hours = request.form.get('targetHours')
            status = request.form.get('status', 'in_progress')
            
            if not category or not target_hours:
                flash('Category and target hours are required', 'error')
                return redirect(url_for('goals'))
            
            target_hours = float(target_hours)
            if target_hours <= 0:
                flash('Target hours must be greater than 0', 'error')
                return redirect(url_for('goals'))
            
            # Check if goal already exists for this category
            existing = goals_collection.find_one({
                'username': username,
                'category': category
            })
            
            if existing:
                goals_collection.update_one(
                    {'_id': existing['_id']},
                    {'$set': {
                        'targetHours': target_hours,
                        'status': status,
                        'updatedAt': datetime.now()
                    }}
                )
                flash(f'Goal for {category} updated!', 'success')
            else:
                goals_collection.insert_one({
                    'username': username,
                    'category': category,
                    'targetHours': target_hours,
                    'status': status,
                    'createdAt': datetime.now()
                })
                flash(f'Goal for {category} created!', 'success')
            
            return redirect(url_for('goals'))
        except Exception as e:
            flash(f'Error saving goal: {str(e)}', 'error')
            return redirect(url_for('goals'))
    
    # GET request - show goals
    goals_list = list(goals_collection.find({'username': username}))
    entries = list(entries_collection.find({'username': username}))
    
    goals_data = []
    for goal in goals_list:
        category = goal['category']
        target_hours = goal['targetHours']
        actual_hours = sum(e.get('hours', 0) for e in entries if e.get('category') == category)
        progress = min(100, int((actual_hours / target_hours) * 100)) if target_hours > 0 else 0
        
        goals_data.append({
            '_id': str(goal['_id']),
            'category': category,
            'targetHours': target_hours,
            'actualHours': round(actual_hours, 1),
            'progress': progress,
            'status': goal.get('status', 'in_progress')
        })
    
    return render_template('goals.html', goals=goals_data, username=username)

@app.route('/delete-goal/<goal_id>', methods=['POST'])
@login_required
def delete_goal(goal_id):
    """Delete a goal"""
    try:
        username = session.get('username')
        result = goals_collection.find_one_and_delete({
            '_id': ObjectId(goal_id),
            'username': username
        })
        
        if result:
            flash('Goal deleted successfully', 'success')
        else:
            flash('Goal not found', 'error')
        
        return redirect(url_for('goals'))
    except Exception as e:
        flash(f'Error deleting goal: {str(e)}', 'error')
        return redirect(url_for('goals'))

@app.route('/weekly-summary')
@login_required
def weekly_summary():
    """Show weekly learning summary"""
    username = session.get('username')
    
    try:
        # Get current week
        week_start = get_week_start()
        week_end = week_start + timedelta(days=7)
        
        # Get entries for this week
        entries = list(entries_collection.find({
            'username': username,
            'date': {'$gte': week_start, '$lt': week_end}
        }).sort('date', 1))
        
        # Process entries
        daily_hours = defaultdict(float)
        category_hours = defaultdict(float)
        total_hours = 0
        
        for entry in entries:
            date = entry['date']
            day = date.strftime('%A')
            hours = entry.get('hours', 0)
            category = entry.get('category', 'General')
            
            daily_hours[day] += hours
            category_hours[category] += hours
            total_hours += hours
        
        # Format for template
        week_data = {
            'weekStart': week_start.strftime('%B %d, %Y'),
            'weekEnd': week_end.strftime('%B %d, %Y'),
            'totalHours': round(total_hours, 1),
            'totalEntries': len(entries),
            'dailyBreakdown': dict(daily_hours),
            'categoryBreakdown': dict(category_hours),
            'avgHoursPerDay': round(total_hours / 7, 1)
        }
        
        return render_template('weekly_summary.html', 
                             week_data=week_data, 
                             username=username)
    except Exception as e:
        print(f"Error in weekly summary: {str(e)}")
        flash(f'Error loading weekly summary: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

@app.route('/leaderboard')
@login_required
def leaderboard():
    """Global leaderboard - see all users' stats"""
    try:
        # Get all entries
        all_entries = list(entries_collection.find())
        
        # Calculate leaderboard
        user_stats = defaultdict(lambda: {'hours': 0, 'entries': 0})
        
        for entry in all_entries:
            username = entry.get('username', '')
            if username:
                user_stats[username]['hours'] += entry.get('hours', 0)
                user_stats[username]['entries'] += 1
        
        # Format leaderboard
        leaderboard_data = []
        for username, stats in user_stats.items():
            leaderboard_data.append({
                'username': username,
                'hours': round(stats['hours'], 1),
                'entries': stats['entries']
            })
        
        # Sort by hours
        leaderboard_data.sort(key=lambda x: x['hours'], reverse=True)
        
        return render_template('leaderboard.html', 
                             leaderboard=leaderboard_data,
                             username=session.get('username'))
    except Exception as e:
        print(f"Error in leaderboard: {str(e)}")
        flash(f'Error loading leaderboard: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

# API Routes (for external access if needed)

@app.route('/api/entries', methods=['GET'])
def get_entries():
    """Get all entries (optionally filtered by user)"""
    try:
        username = request.args.get('username')
        query = {'username': username} if username else {}
        
        entries = list(entries_collection.find(query).sort('date', -1))
        result = []
        for entry in entries:
            result.append({
                '_id': str(entry['_id']),
                'username': entry.get('username', ''),
                'date': entry.get('date', datetime.now()).isoformat(),
                'hours': entry.get('hours', 0),
                'notes': entry.get('notes', ''),
                'category': entry.get('category', 'General'),
                'status': entry.get('status', 'completed')
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({'message': 'Error fetching entries', 'error': str(e)}), 500

# Email Configuration
SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
SMTP_EMAIL = os.getenv('SMTP_EMAIL')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
REMINDER_TIME = os.getenv('REMINDER_TIME', '20:00')  # 8 PM default

# Helper Functions

def send_email_reminder(user_email, username):
    """Send email reminder to user"""
    try:
        if not SMTP_EMAIL or not SMTP_PASSWORD:
            print("❌ Email credentials not configured")
            return False
        
        print(f"📧 Preparing email for {user_email}...")
        
        msg = MIMEMultipart()
        msg['From'] = SMTP_EMAIL
        msg['To'] = user_email
        msg['Subject'] = '📚 Daily Learning Reminder - Learning Tracker'
        
        # Get the deployed URL from environment or use placeholder
        base_url = os.getenv('RENDER_EXTERNAL_URL', 'https://your-app.onrender.com')
        
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px; background: #f5f5f5;">
            <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px;">
                <h2 style="color: #667eea;">📚 Hi {username}!</h2>
                <p style="font-size: 16px; color: #333;">
                    Don't forget to log your learning for today! 🎯
                </p>
                <p style="font-size: 14px; color: #666;">
                    Even 15 minutes of learning counts! Keep your streak alive! 🔥
                </p>
                <a href="{base_url}/dashboard" 
                   style="display: inline-block; margin-top: 20px; padding: 12px 24px; 
                          background: linear-gradient(135deg, #667eea, #764ba2); 
                          color: white; text-decoration: none; border-radius: 8px; font-weight: bold;">
                    Log Your Learning →
                </a>
                <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                <p style="font-size: 12px; color: #999;">
                    You're receiving this because you have reminders enabled in Learning Tracker.
                </p>
            </div>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(body, 'html'))
        
        print(f"📤 Connecting to SMTP server: {SMTP_SERVER}:{SMTP_PORT}")
        
        # Create SSL context
        context = ssl.create_default_context()
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
            print("🔐 Starting TLS...")
            server.starttls(context=context)
            
            print("🔑 Logging in...")
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            
            print("📨 Sending message...")
            server.send_message(msg)
        
        print(f"✅ Reminder sent successfully to {username}")
        return True
        
    except smtplib.SMTPAuthenticationError as e:
        print(f"❌ SMTP Authentication failed: {str(e)}")
        print("💡 Make sure you're using a Gmail App Password, not your regular password")
        return False
    except smtplib.SMTPException as e:
        print(f"❌ SMTP Error: {str(e)}")
        return False
    except Exception as e:
        print(f"❌ Failed to send email to {username}: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
```

### 3. **Add Environment Variable in Render**

Add this to your Render environment variables:
```
RENDER_EXTERNAL_URL=https://your-app-name.onrender.com

def check_user_logged_today(username):
    """Check if user has logged any entry today"""
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    
    entry = entries_collection.find_one({
        'username': username,
        'date': {'$gte': today_start, '$lt': today_end}
    })
    
    return entry is not None

def get_user_streak(username):
    """Calculate user's current learning streak"""
    entries = list(entries_collection.find({'username': username}).sort('date', -1))
    
    if not entries:
        return 0
    
    streak = 0
    current_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Get unique dates
    dates_logged = set()
    for entry in entries:
        entry_date = entry['date'].replace(hour=0, minute=0, second=0, microsecond=0)
        dates_logged.add(entry_date)
    
    dates_logged = sorted(dates_logged, reverse=True)
    
    # Check if logged today or yesterday (to not break streak)
    if dates_logged:
        most_recent = dates_logged[0]
        if (current_date - most_recent).days > 1:
            return 0  # Streak broken
    
    # Count consecutive days
    for i, date in enumerate(dates_logged):
        expected_date = current_date - timedelta(days=i)
        if date.date() == expected_date.date():
            streak += 1
        else:
            break
    
    return streak

def send_daily_reminders():
    """Send reminders to all users who haven't logged today"""
    print("🔔 Checking for users who need reminders...")
    
    users = list(users_collection.find({'reminderEnabled': True}))
    
    for user in users:
        username = user['username']
        user_email = user.get('email')
        
        if not user_email:
            continue
        
        # Check if user has logged today
        if not check_user_logged_today(username):
            print(f"📧 Sending reminder to {username}...")
            send_email_reminder(user_email, username)
        else:
            print(f"✅ {username} already logged today")

def run_scheduler():
    """Run the reminder scheduler in background"""
    schedule.every().day.at(REMINDER_TIME).do(send_daily_reminders)
    
    print(f"⏰ Reminder scheduler started! Will send reminders at {REMINDER_TIME}")
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

# Start scheduler in background thread
def start_reminder_scheduler():
    """Start the reminder scheduler in a background thread"""
    scheduler_thread = Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

# ============================================
# NEW ROUTES TO ADD TO YOUR APP
# ============================================

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """User settings - configure reminders"""
    username = session.get('username')
    user = users_collection.find_one({'username': username})
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        reminder_enabled = request.form.get('reminderEnabled') == 'on'
        reminder_time = request.form.get('reminderTime', '20:00')
        
        users_collection.update_one(
            {'username': username},
            {'$set': {
                'email': email,
                'reminderEnabled': reminder_enabled,
                'reminderTime': reminder_time,
                'updatedAt': datetime.now()
            }}
        )
        
        flash('Settings updated successfully!', 'success')
        return redirect(url_for('settings'))
    
    # Calculate streak
    streak = get_user_streak(username)
    
    return render_template('settings.html', 
                         user=user or {}, 
                         username=username,
                         streak=streak)

@app.route('/api/reminder-test')
@login_required
def test_reminder():
    """Test endpoint to send a reminder immediately"""
    try:
        username = session.get('username')
        user = users_collection.find_one({'username': username})
        
        if not user or not user.get('email'):
            return jsonify({'error': 'Email not configured'}), 400
        
        print(f"Attempting to send email to {user.get('email')}")
        success = send_email_reminder(user['email'], username)
        
        if success:
            return jsonify({'message': 'Test reminder sent!'}), 200
        else:
            return jsonify({'error': 'Failed to send reminder - check server logs'}), 500
            
    except Exception as e:
        print(f"Error in test_reminder: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Exception occurred: {str(e)}'}), 500

@app.route('/streak')
@login_required
def streak():
    """Show user's learning streak"""
    username = session.get('username')
    streak_count = get_user_streak(username)
    
    # Get last 30 days activity
    thirty_days_ago = datetime.now() - timedelta(days=30)
    entries = list(entries_collection.find({
        'username': username,
        'date': {'$gte': thirty_days_ago}
    }).sort('date', -1))
    
    # Create activity calendar
    activity_map = {}
    for entry in entries:
        date_str = entry['date'].strftime('%Y-%m-%d')
        if date_str not in activity_map:
            activity_map[date_str] = 0
        activity_map[date_str] += entry.get('hours', 0)
    
    return render_template('streak.html', 
                         username=username,
                         streak=streak_count,
                         activity_map=activity_map)



if __name__ == '__main__':
    print(f'🚀 Server running on http://localhost:{PORT}')
    print(f'📂 Make sure templates folder exists with all HTML files!')
    
    # Start reminder scheduler if email is configured
    if SMTP_EMAIL and SMTP_PASSWORD:
        print(f'⏰ Starting reminder scheduler (reminders at {REMINDER_TIME})')
        start_reminder_scheduler()
    else:
        print('⚠️  Email reminders disabled (configure SMTP_EMAIL and SMTP_PASSWORD in .env)')
    
    app.run(host='0.0.0.0', port=PORT, debug=True)