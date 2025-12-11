const express = require('express');
const mongoose = require('mongoose');
const cors = require('cors');

const app = express();

// Middleware
app.use(cors());
app.use(express.json());

// MongoDB Connection - REPLACE WITH YOUR ACTUAL CONNECTION STRING
const MONGODB_URI = 'mongodb+srv://raja:rajaraja@cluster0.3k5mfau.mongodb.net/learning-tracker?retryWrites=true&w=majority&appName=Cluster0';
const PORT = 5000;

mongoose.connect(MONGODB_URI)
.then(() => console.log('✅ MongoDB Connected'))
.catch(err => console.error('❌ MongoDB Connection Error:', err));

// Learning Entry Schema
const entrySchema = new mongoose.Schema({
  name: {
    type: String,
    required: true,
    trim: true,
    minlength: 2
  },
  date: {
    type: Date,
    required: true,
    validate: {
      validator: function(v) {
        return v <= new Date();
      },
      message: 'Date cannot be in the future'
    }
  },
  hours: {
    type: Number,
    required: true,
    min: 0.1,
    max: 24
  },
  notes: {
    type: String,
    default: '',
    trim: true
  },
  createdAt: {
    type: Date,
    default: Date.now
  }
}, {
  timestamps: true
});

const Entry = mongoose.model('Entry', entrySchema);

// Routes

// Health check
app.get('/', (req, res) => {
  res.json({ message: 'Learning Tracker API is running! 🚀' });
});

// Get all entries
app.get('/api/entries', async (req, res) => {
  try {
    const entries = await Entry.find().sort({ date: -1 });
    res.json(entries);
  } catch (error) {
    res.status(500).json({ message: 'Error fetching entries', error: error.message });
  }
});

// Get single entry
app.get('/api/entries/:id', async (req, res) => {
  try {
    const entry = await Entry.findById(req.params.id);
    if (!entry) {
      return res.status(404).json({ message: 'Entry not found' });
    }
    res.json(entry);
  } catch (error) {
    res.status(500).json({ message: 'Error fetching entry', error: error.message });
  }
});

// Create new entry
app.post('/api/entries', async (req, res) => {
  try {
    const { name, date, hours, notes } = req.body;

    // Validation
    if (!name || !date || !hours) {
      return res.status(400).json({ message: 'Name, date, and hours are required' });
    }

    if (name.trim().length < 2) {
      return res.status(400).json({ message: 'Name must be at least 2 characters' });
    }

    if (new Date(date) > new Date()) {
      return res.status(400).json({ message: 'Date cannot be in the future' });
    }

    if (hours <= 0 || hours > 24) {
      return res.status(400).json({ message: 'Hours must be between 0 and 24' });
    }

    const entry = new Entry({
      name: name.trim(),
      date,
      hours: parseFloat(hours),
      notes: notes ? notes.trim() : ''
    });

    const savedEntry = await entry.save();
    res.status(201).json(savedEntry);
  } catch (error) {
    res.status(500).json({ message: 'Error creating entry', error: error.message });
  }
});

// Update entry
app.put('/api/entries/:id', async (req, res) => {
  try {
    const { name, date, hours, notes } = req.body;

    // Validation
    if (name && name.trim().length < 2) {
      return res.status(400).json({ message: 'Name must be at least 2 characters' });
    }

    if (date && new Date(date) > new Date()) {
      return res.status(400).json({ message: 'Date cannot be in the future' });
    }

    if (hours && (hours <= 0 || hours > 24)) {
      return res.status(400).json({ message: 'Hours must be between 0 and 24' });
    }

    const updateData = {};
    if (name) updateData.name = name.trim();
    if (date) updateData.date = date;
    if (hours) updateData.hours = parseFloat(hours);
    if (notes !== undefined) updateData.notes = notes.trim();

    const entry = await Entry.findByIdAndUpdate(
      req.params.id,
      updateData,
      { new: true, runValidators: true }
    );

    if (!entry) {
      return res.status(404).json({ message: 'Entry not found' });
    }

    res.json(entry);
  } catch (error) {
    res.status(500).json({ message: 'Error updating entry', error: error.message });
  }
});

// Delete entry
app.delete('/api/entries/:id', async (req, res) => {
  try {
    const entry = await Entry.findByIdAndDelete(req.params.id);
    if (!entry) {
      return res.status(404).json({ message: 'Entry not found' });
    }
    res.json({ message: 'Entry deleted successfully', entry });
  } catch (error) {
    res.status(500).json({ message: 'Error deleting entry', error: error.message });
  }
});

// Get statistics
app.get('/api/stats', async (req, res) => {
  try {
    const entries = await Entry.find();
    
    const totalEntries = entries.length;
    const totalHours = entries.reduce((sum, entry) => sum + entry.hours, 0);
    const uniqueLearners = [...new Set(entries.map(e => e.name))].length;
    const avgHours = totalEntries > 0 ? totalHours / totalEntries : 0;

    // Leaderboard
    const leaderboard = entries.reduce((acc, entry) => {
      if (!acc[entry.name]) {
        acc[entry.name] = { name: entry.name, hours: 0, entries: 0 };
      }
      acc[entry.name].hours += entry.hours;
      acc[entry.name].entries += 1;
      return acc;
    }, {});

    const topLearners = Object.values(leaderboard)
      .sort((a, b) => b.hours - a.hours)
      .slice(0, 5);

    res.json({
      totalEntries,
      totalHours: parseFloat(totalHours.toFixed(1)),
      uniqueLearners,
      avgHours: parseFloat(avgHours.toFixed(1)),
      topLearners
    });
  } catch (error) {
    res.status(500).json({ message: 'Error fetching stats', error: error.message });
  }
});

// Start server
app.listen(PORT, () => {
  console.log(`🚀 Server running on port ${PORT}`);
});