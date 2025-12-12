import os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from flask_cors import CORS
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv
from functools import wraps
from collections import defaultdict

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

if __name__ == '__main__':
    print(f'🚀 Server running on http://localhost:{PORT}')
    print(f'📂 Make sure templates folder exists with all HTML files!')
    app.run(host='0.0.0.0', port=PORT, debug=True)