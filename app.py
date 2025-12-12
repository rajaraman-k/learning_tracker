import os
from datetime import datetime
from flask import Flask, request, jsonify
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

# Helper function to serialize MongoDB documents
def serialize_entry(entry):
    if entry:
        entry['_id'] = str(entry['_id'])
        if 'date' in entry and isinstance(entry['date'], datetime):
            entry['date'] = entry['date'].isoformat()
        if 'createdAt' in entry and isinstance(entry['createdAt'], datetime):
            entry['createdAt'] = entry['createdAt'].isoformat()
    return entry

# Routes

@app.route('/', methods=['GET'])
def health_check():
    return jsonify({'message': 'Learning Tracker API is running! 🚀'})

@app.route('/api/entries', methods=['GET'])
def get_entries():
    try:
        entries = list(entries_collection.find().sort('date', -1))
        return jsonify([serialize_entry(entry) for entry in entries])
    except Exception as e:
        return jsonify({'message': 'Error fetching entries', 'error': str(e)}), 500

@app.route('/api/entries/<entry_id>', methods=['GET'])
def get_entry(entry_id):
    try:
        entry = entries_collection.find_one({'_id': ObjectId(entry_id)})
        if not entry:
            return jsonify({'message': 'Entry not found'}), 404
        return jsonify(serialize_entry(entry))
    except Exception as e:
        return jsonify({'message': 'Error fetching entry', 'error': str(e)}), 500

@app.route('/api/entries', methods=['POST'])
def create_entry():
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        date_str = data.get('date')
        hours = data.get('hours')
        notes = data.get('notes', '').strip()

        # Validation
        if not name or not date_str or hours is None:
            return jsonify({'message': 'Name, date, and hours are required'}), 400

        if len(name) < 2:
            return jsonify({'message': 'Name must be at least 2 characters'}), 400

        # Parse and validate date
        try:
            date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            if date > datetime.now():
                return jsonify({'message': 'Date cannot be in the future'}), 400
        except ValueError:
            return jsonify({'message': 'Invalid date format'}), 400

        # Validate hours
        try:
            hours = float(hours)
            if hours <= 0 or hours > 24:
                return jsonify({'message': 'Hours must be between 0 and 24'}), 400
        except ValueError:
            return jsonify({'message': 'Invalid hours value'}), 400

        # Create entry
        entry = {
            'name': name,
            'date': date,
            'hours': hours,
            'notes': notes,
            'createdAt': datetime.now()
        }

        result = entries_collection.insert_one(entry)
        entry['_id'] = result.inserted_id
        
        return jsonify(serialize_entry(entry)), 201
    except Exception as e:
        return jsonify({'message': 'Error creating entry', 'error': str(e)}), 500

@app.route('/api/entries/<entry_id>', methods=['PUT'])
def update_entry(entry_id):
    try:
        data = request.get_json()
        update_data = {}

        # Validate and add name if provided
        if 'name' in data:
            name = data['name'].strip()
            if len(name) < 2:
                return jsonify({'message': 'Name must be at least 2 characters'}), 400
            update_data['name'] = name

        # Validate and add date if provided
        if 'date' in data:
            try:
                date = datetime.fromisoformat(data['date'].replace('Z', '+00:00'))
                if date > datetime.now():
                    return jsonify({'message': 'Date cannot be in the future'}), 400
                update_data['date'] = date
            except ValueError:
                return jsonify({'message': 'Invalid date format'}), 400

        # Validate and add hours if provided
        if 'hours' in data:
            try:
                hours = float(data['hours'])
                if hours <= 0 or hours > 24:
                    return jsonify({'message': 'Hours must be between 0 and 24'}), 400
                update_data['hours'] = hours
            except ValueError:
                return jsonify({'message': 'Invalid hours value'}), 400

        # Add notes if provided
        if 'notes' in data:
            update_data['notes'] = data['notes'].strip()

        # Update entry
        result = entries_collection.find_one_and_update(
            {'_id': ObjectId(entry_id)},
            {'$set': update_data},
            return_document=True
        )

        if not result:
            return jsonify({'message': 'Entry not found'}), 404

        return jsonify(serialize_entry(result))
    except Exception as e:
        return jsonify({'message': 'Error updating entry', 'error': str(e)}), 500

@app.route('/api/entries/<entry_id>', methods=['DELETE'])
def delete_entry(entry_id):
    try:
        result = entries_collection.find_one_and_delete({'_id': ObjectId(entry_id)})
        if not result:
            return jsonify({'message': 'Entry not found'}), 404
        return jsonify({'message': 'Entry deleted successfully', 'entry': serialize_entry(result)})
    except Exception as e:
        return jsonify({'message': 'Error deleting entry', 'error': str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    try:
        entries = list(entries_collection.find())
        
        total_entries = len(entries)
        total_hours = sum(entry.get('hours', 0) for entry in entries)
        unique_learners = len(set(entry.get('name', '') for entry in entries))
        avg_hours = total_hours / total_entries if total_entries > 0 else 0

        # Leaderboard
        leaderboard = {}
        for entry in entries:
            name = entry.get('name', '')
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
    print(f'🚀 Server running on port {PORT}')
    app.run(host='0.0.0.0', port=PORT, debug=False)