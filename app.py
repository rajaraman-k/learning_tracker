import os
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_cors import CORS
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

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
    # Test connection
    client.admin.command('ping')
    print('✅ MongoDB Connected')
except Exception as e:
    print(f'❌ MongoDB Connection Error: {e}')
    exit(1)

# Frontend Routes

@app.route('/')
def index():
    """Main page - shows all entries and stats"""
    try:
        # Get all entries
        all_entries = list(entries_collection.find().sort('date', -1))
        entries = []
        
        for entry in all_entries:
            entries.append({
                '_id': str(entry['_id']),
                'name': entry.get('name', ''),
                'date': entry.get('date', datetime.now()).isoformat() if isinstance(entry.get('date'), datetime) else str(entry.get('date', '')),
                'hours': entry.get('hours', 0),
                'notes': entry.get('notes', '')
            })
        
        # Calculate stats
        total_entries = len(entries)
        total_hours = sum(entry.get('hours', 0) for entry in entries)
        unique_learners = len(set(entry.get('name', '') for entry in entries if entry.get('name')))
        avg_hours = round(total_hours / total_entries, 1) if total_entries > 0 else 0
        
        # Leaderboard
        leaderboard = {}
        for entry in entries:
            name = entry.get('name', '')
            if name:
                if name not in leaderboard:
                    leaderboard[name] = {'name': name, 'hours': 0, 'entries': 0}
                leaderboard[name]['hours'] += entry.get('hours', 0)
                leaderboard[name]['entries'] += 1
        
        # Round hours in leaderboard
        for learner in leaderboard.values():
            learner['hours'] = round(learner['hours'], 1)
        
        top_learners = sorted(leaderboard.values(), key=lambda x: x['hours'], reverse=True)[:5]
        
        stats = {
            'totalEntries': total_entries,
            'totalHours': round(total_hours, 1),
            'uniqueLearners': unique_learners,
            'avgHours': avg_hours,
            'topLearners': top_learners
        }
        
        return render_template('index.html', entries=entries, stats=stats)
    except Exception as e:
        print(f"Error in index route: {str(e)}")
        import traceback
        traceback.print_exc()
        return f"Error: {str(e)}", 500

@app.route('/add', methods=['POST'])
def add_entry():
    """Add a new learning entry"""
    try:
        name = request.form.get('name', '').strip()
        date_str = request.form.get('date')
        hours = request.form.get('hours')
        notes = request.form.get('notes', '').strip()
        
        # Validation
        if not name or not date_str or not hours:
            return "Name, date, and hours are required", 400
        
        if len(name) < 2:
            return "Name must be at least 2 characters", 400
        
        # Parse and validate date
        date = datetime.fromisoformat(date_str)
        if date > datetime.now():
            return "Date cannot be in the future", 400
        
        # Validate hours
        hours = float(hours)
        if hours <= 0 or hours > 24:
            return "Hours must be between 0 and 24", 400
        
        # Create entry
        entry = {
            'name': name,
            'date': date,
            'hours': hours,
            'notes': notes,
            'createdAt': datetime.now()
        }
        
        entries_collection.insert_one(entry)
        return redirect(url_for('index'))
    except Exception as e:
        print(f"Error adding entry: {str(e)}")
        return f"Error: {str(e)}", 500

@app.route('/delete/<entry_id>', methods=['POST'])
def delete_entry(entry_id):
    """Delete an entry"""
    try:
        entries_collection.find_one_and_delete({'_id': ObjectId(entry_id)})
        return redirect(url_for('index'))
    except Exception as e:
        print(f"Error deleting entry: {str(e)}")
        return f"Error: {str(e)}", 500

# API Routes (for external access if needed)

@app.route('/api/entries', methods=['GET'])
def get_entries():
    try:
        entries = list(entries_collection.find().sort('date', -1))
        result = []
        for entry in entries:
            result.append({
                '_id': str(entry['_id']),
                'name': entry.get('name', ''),
                'date': entry.get('date', datetime.now()).isoformat(),
                'hours': entry.get('hours', 0),
                'notes': entry.get('notes', '')
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({'message': 'Error fetching entries', 'error': str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    try:
        entries = list(entries_collection.find())
        
        total_entries = len(entries)
        total_hours = sum(entry.get('hours', 0) for entry in entries)
        unique_learners = len(set(entry.get('name', '') for entry in entries if entry.get('name')))
        avg_hours = total_hours / total_entries if total_entries > 0 else 0

        # Leaderboard
        leaderboard = {}
        for entry in entries:
            name = entry.get('name', '')
            if name:
                if name not in leaderboard:
                    leaderboard[name] = {'name': name, 'hours': 0, 'entries': 0}
                leaderboard[name]['hours'] += entry.get('hours', 0)
                leaderboard[name]['entries'] += 1

        top_learners = sorted(leaderboard.values(), key=lambda x: x['hours'], reverse=True)[:5]

        return jsonify({
            'totalEntries': total_entries,
            'totalHours': round(total_hours, 1),
            'uniqueLearners': unique_learners,
            'avgHours': round(avg_hours, 1),
            'topLearners': top_learners
        })
    except Exception as e:
        return jsonify({'message': 'Error fetching stats', 'error': str(e)}), 500

if __name__ == '__main__':
    print(f'🚀 Server running on http://localhost:{PORT}')
    print(f'📂 Make sure templates/index.html exists!')
    app.run(host='0.0.0.0', port=PORT, debug=True)